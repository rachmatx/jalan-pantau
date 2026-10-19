"""JalanPantau (Flask): deteksi kerusakan jalan + severity + indeks prioritas + PDF + peta + riwayat.

Run dari root repo:
    .\\.venv\\Scripts\\python web/app.py
Buka: http://127.0.0.1:5000
"""
import atexit
import functools
import os
import secrets
import sys
import time
from datetime import timedelta
from io import BytesIO
import tempfile
import threading
from pathlib import Path

# Pastikan folder web/ ada di path untuk import lokal
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import (Flask, Response, current_app, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

from deteksi import (WorkerInferensiMati, analisis_gambar,
                     analisis_gambar_terjadwal, buat_pdf, get_kalibrasi,
                     hitung_ppc, nama_model, nama_model_live,
                     ringkasan_perangkat, simpan_kalibrasi, status_sistem,
                     terapkan_koreksi)
from streaming import MANAGER
from database import (daftar_sesi, detail_sesi, hapus_sesi, simpan_sesi,
                       titik_peta, tutup_db,
                       migrasi_admin_v2, migrasi_sesi_v2, sesi_by_client_ref,
                       sesi_duplikat_coord,
                       init_admin, cek_login,
                       hitung_sesi, get_db,
                       tambah_segmen, daftar_segmen, detail_segmen, ubah_segmen,
                       hapus_segmen, tetapkan_segmen_sesi, sesi_tanpa_segmen,
                       sdi_segmen)

WEB_DIR = Path(__file__).parent

ALLOWED_IMG = {"jpg", "jpeg", "png"}
ALLOWED_VIDEO = {"mp4", "avi", "mov", "mkv"}
MAX_VIDEO_BYTES = 200 * 1024 * 1024  # video live (global Flask)
MAX_IMG_BYTES = 15 * 1024 * 1024  # gambar deteksi: 12MP JPEG ~3-8MB; di atas ini tolak cepat
# Default 0,30 (18 Okt 2026): diukur pada 161 gambar BPID berlabel, recall
# pothole tetap 0,60 sementara FP turun 111 -> 90 dibanding 0,25 (F1 0,591 ->
# 0,616). Slider tetap bisa diturunkan operator ke 0,05.
CONF_MIN, CONF_MAX, CONF_DEFAULT = 0.05, 0.8, 0.30
FRAME_SKIP_MIN, FRAME_SKIP_MAX = 1, 30
_PESAN_MEMORI = ("Memori tidak cukup untuk memproses gambar ini. "
                 "Tutup tab lain, tunggu sebentar, atau pakai gambar beresolusi lebih kecil.")


def _kurang_memori(e):
    """True bila exception menandakan kehabisan memori, bukan gambar rusak.

    Python melempar MemoryError, tetapi OpenCV melempar cv2.error dengan
    "Insufficient memory" / "OutOfMemoryError" (terukur saat decode 12 MP di
    mesin yang RAM-nya habis). Keduanya harus dibalas 503, bukan 500, supaya
    operator tahu ini sementara — bukan perlu mengganti foto.
    """
    if isinstance(e, MemoryError):
        return True
    teks = str(e).lower()
    return "insufficient memory" in teks or "outofmemory" in teks


_video_tmp = None
_video_tmp_aktif = False  # True bila stream file saat ini memakai _video_tmp hasil upload
_video_lock = threading.Lock()  # P1: jaga _video_tmp dari race upload konkuren

# Kepemilikan stream live.
#
# StreamManager adalah satu-satu objek untuk SELURUH server, jadi tanpa
# penjaga, tab kedua cukup memanggil /api/stream/stop untuk mematikan stream
# milik orang lain, atau /api/stream/start untuk merebutnya. Aplikasi ini
# sengaja dibangun untuk satu operator (bind ke 127.0.0.1), jadi kita tidak
# membuat registry per sesi; cukup satu token kepemilikan.
#
# Token hanya DIBUTAHKAN saat stream sedang berjalan. Saat tidak berjalan,
# stop/anotasi/snapshot tetap terbuka supaya idempoten dan tidak mengganggu
# state antarmuka.
_stream_token = None
_stream_lock = threading.Lock()


def _token_terbit():
    """Terbitkan token baru; pemanggil menjadi pemilik stream."""
    global _stream_token
    with _stream_lock:
        _stream_token = secrets.token_urlsafe(18)
        return _stream_token


def _token_dimiliki(data):
    """True bila request ini menyertakan token pemilik stream yang sah."""
    return _token_dimilik_form((data or {}).get("token"))


def _token_dimilik_form(nilai):
    """Pemeriksaan token untuk body JSON maupun form multipart."""
    global _stream_token
    with _stream_lock:
        sah = _stream_token
    if not sah or not nilai:
        return False
    return secrets.compare_digest(str(nilai), sah)


def _klamp_skip(v, bawaan=1):
    try:
        return min(max(int(v), FRAME_SKIP_MIN), FRAME_SKIP_MAX)
    except (TypeError, ValueError):
        return bawaan


def _buang_video_tmp():
    """Hapus file temp video upload; aman dipanggil berulang/atexit."""
    global _video_tmp, _video_tmp_aktif
    with _video_lock:
        if _video_tmp:
            try:
                os.remove(_video_tmp)
            except OSError:
                pass
            _video_tmp = None
        _video_tmp_aktif = False


atexit.register(_buang_video_tmp)


def _muat_env_file():
    """Muat berkas .env (opsional) ke os.environ TANPA menimpa env yang sudah ada.

    Format sederhana: KEY=VALUE per baris; abaikan komentar (#) dan baris kosong.
    Berguna agar `.env.example` -> `.env` benar-benar berfungsi (tanpa dependensi).
    """
    p = WEB_DIR.parent / ".env"
    if not p.is_file():
        return
    try:
        for baris in p.read_text(encoding="utf-8").splitlines():
            baris = baris.strip()
            if not baris or baris.startswith("#") or "=" not in baris:
                continue
            k, v = baris.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass



def create_app():
    _muat_env_file()
    app = Flask(__name__, template_folder=str(WEB_DIR / "templates"),
                static_folder=str(WEB_DIR / "static"))
    app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES
    app.config.setdefault("DB_PATH", str(WEB_DIR / "instance" / "riwayat.db"))
    app.config["TEMPLATES_AUTO_RELOAD"] = True  # Disable template cache
    # P4: cookie session eksplisit aman (HttpOnly + SameSite).
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    # Umur sesi login (jam). Default 8; override via env JP_SESSION_HOURS.
    # Catatan: ini batas TETAP sejak login pertama (dicek via session["login_at"]
    # di login_wajib), bukan sliding window.
    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(
        hours=int(os.environ.get("JP_SESSION_HOURS", "8")))
    # Cookie Secure saat di balik HTTPS (set JP_HTTPS=1).
    if str(os.environ.get("JP_HTTPS", "")).strip().lower() in ("1", "true", "yes"):
        app.config["SESSION_COOKIE_SECURE"] = True
    app.teardown_appcontext(tutup_db)

    @app.after_request
    def _kepala_aman(resp):
        # P4: cegah MIME-sniffing + clickjacking; API JSON jangan di-cache browser.
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    # Migrasi skema + seed akun admin default
    with app.app_context():
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()  # seed akun admin default (lihat database.init_admin)

    # Session login admin. Kunci WAJIB via env JP_SECRET_KEY di produksi.
    # Fallback dev: secret acak per-proses (sesi tidak valid antar restart)
    # agar tidak ada secret statis yang bisa ditebak penyerang.
    _secret = os.environ.get("JP_SECRET_KEY")
    if not _secret:
        import secrets as _secrets
        _secret = _secrets.token_hex(32)
        print("PERINGATAN: JP_SECRET_KEY tidak diset, memakai secret acak "
              "sementara. Set env JP_SECRET_KEY untuk produksi/demo.")
    app.secret_key = _secret

    # ---- Proteksi CSRF (state-changing request) ----
    # Token per-sesi; klien mengirim via header X-CSRF-Token (fetch/wrapper
    # global) atau field form _csrf. Nonaktif saat TESTING atau bila env
    # JP_CSRF=0 (escape hatch agar demo tetap bisa dimatikan bila perlu).
    _METODE_AMAN = ("GET", "HEAD", "OPTIONS", "TRACE")
    CSRF_ENABLED = str(os.environ.get("JP_CSRF", "1")).strip().lower() not in (
        "0", "false", "off", "no")

    def csrf_token():
        tok = session.get("_csrf")
        if not tok:
            tok = secrets.token_urlsafe(32)
            session["_csrf"] = tok
        return tok

    app.jinja_env.globals["csrf_token"] = csrf_token

    @app.before_request
    def _periksa_csrf():
        if not CSRF_ENABLED or app.config.get("TESTING"):
            return None
        if request.method in _METODE_AMAN:
            return None
        kirim = (request.headers.get("X-CSRF-Token")
                 or request.form.get("_csrf"))
        simpan = session.get("_csrf")
        if (kirim and simpan
                and secrets.compare_digest(str(kirim).encode("utf-8", "ignore"),
                                           str(simpan).encode("utf-8", "ignore"))):
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "CSRF token tidak ada/tidak valid. "
                                     "Muat ulang halaman lalu coba lagi."}), 403
        return render_template("error/403.html"), 403

    # Rate limiting global: anti brute-force login + spam endpoint POST.
    # Catatan: /api/stream & /api/stream/stats di-exempt (MJPEG long-lived
    # + polling 1x/detik dari halaman live) agar demo tidak terputus.
    try:
        from flask_limiter import Limiter
        from flask_limiter.util import get_remote_address
        limiter = Limiter(
            get_remote_address, app=app, default_limits=["600 per hour"],
            storage_uri="memory://",
        )
    except ImportError:  # pragma: no cover - fallback bila dependency hilang
        limiter = None

    def _exempt(fn):
        """No-op bila flask-limiter tak ada, else exempt route dari limit."""
        if limiter is None:
            return fn
        return limiter.exempt()(fn)

    def login_wajib(fn):
        """Proteksi halaman/API: redirect ke login (HTML) atau 401 JSON (API)
        bila belum login. Satu peran saja (admin).
        Sesi bersifat TETAP: dihitung sejak login pertama (session["login_at"]);
        lewat batas PERMANENT_SESSION_LIFETIME -> wajib login ulang."""
        @functools.wraps(fn)
        def pembungkus(*a, **kw):
            batas = app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()
            login_at = session.get("login_at")
            if session.get("admin_id") and not login_at:
                # Sesi lama (sebelum ada login_at): anggap baru login sekarang.
                login_at = time.time()
                session["login_at"] = login_at
            kedaluwarsa = (not session.get("admin_id")
                          or (time.time() - (login_at or 0) > batas))
            if kedaluwarsa:
                habis = bool(session.get("admin_id"))
                # Bersihkan sesi tapi PERTAHANKAN token CSRF agar form/modal
                # di halaman yang sama tetap bisa dipakai (mis. login ulang).
                csrf = session.get("_csrf")
                session.clear()
                if csrf:
                    session["_csrf"] = csrf
                if request.path.startswith("/api/"):
                    pesan = ("Sesi berakhir. Silakan login ulang." if habis
                             else "Login diperlukan.")
                    return jsonify({"error": pesan}), 401
                return redirect(url_for("login_form", next=request.path))
            return fn(*a, **kw)
        return pembungkus

# ---- Autentikasi ----
    @app.get("/login")
    def login_form():
        if session.get("admin_id"):
            return redirect(url_for("deteksi"))
        return render_template("login.html")

    @app.post("/login")
    @(limiter.limit("5 per minute; 20 per hour") if limiter else (lambda f: f))
    def login_post():
        user = (request.form.get("username") or "").strip().lower()
        pwd = request.form.get("password") or ""
        tujuan = request.form.get("next") or ""

        admin = cek_login(user, pwd)
        if not admin:
            return render_template("login.html", galat="Username atau password salah."), 401

        session.clear()
        session.permanent = True
        session["admin_id"] = admin["id"]
        session["admin_user"] = admin["username"]
        session["login_at"] = time.time()

        # cegah open-redirect: hanya path relatif (tolak //, backslash, CR/LF)
        if (not tujuan.startswith("/") or tujuan.startswith("//")
                or "\\" in tujuan or "\n" in tujuan or "\r" in tujuan):
            tujuan = "/"
        return redirect(tujuan)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login_form"))

    @app.post("/api/login")
    @(limiter.limit("5 per minute; 20 per hour") if limiter else (lambda f: f))
    def api_login():
        """Login via JSON (dipakai dialog login modal saat aksi simpan).
        Mengembalikan 200 + username bila sukses, 401 bila gagal."""
        data = request.get_json(silent=True) or {}
        user = (data.get("username") or "").strip().lower()
        pwd = data.get("password") or ""
        admin = cek_login(user, pwd)
        if not admin:
            return jsonify({"error": "Username atau password salah."}), 401
        session.clear()
        session.permanent = True
        session["admin_id"] = admin["id"]
        session["admin_user"] = admin["username"]
        session["login_at"] = time.time()
        return jsonify({"ok": True, "username": admin["username"]})

    # Cache-buster: versi ini akan ditambahkan ke semua asset static
    STATIC_VERSION = "39"

    @app.context_processor
    def inject_static_version():
        return {"static_v": STATIC_VERSION}

    @app.errorhandler(413)
    def terlalu_besar(e):
        """Global 200MB (video) terlampaui -> JSON, bukan halaman HTML Flask."""
        return jsonify({"error": "Berkas terlalu besar (maks 200MB untuk "
                                 "video, 15MB gambar, 5MB foto kalibrasi)."}), 413

    @app.errorhandler(404)
    def halaman_tidak_ada(e):
        """Rute /api/ harus balas JSON; halaman biasa tetap 404 HTML.

        Tanpa ini, klien API yang salah alamat (misalnya GET ke endpoint
        POST) menerima halaman galat HTML dan tidak tahu apa yang terjadi.
        """
        if request.path.startswith("/api/"):
            return jsonify({"error": "Alamat API tidak dikenal."}), 404
        return e

    @app.errorhandler(405)
    def metode_salah(e):
        """Misalnya GET ke endpoint POST: balas JSON, bukan HTML.

        405 memang jawaban yang benar, tapi formatnya harus sesuai dengan
        endpoint yang dipanggil supaya bisa dibaca pemanggil program.
        """
        if request.path.startswith("/api/"):
            return jsonify({
                "error": "Metode HTTP tidak diizinkan untuk alamat ini.",
                "method": request.method,
            }), 405
        return e

    @app.errorhandler(429)
    def kebanyakan_request(e):
        """Rate limit tercapai. Form login -> render ulang dengan pesan ramah
        (bukan halaman hitam-putih bawaan flask-limiter); API -> JSON."""
        if request.path == "/login":
            retry = 60
            if hasattr(e, "description") and isinstance(getattr(e, "description"), str):
                import re as _re
                m = _re.search(r"(\d+)\s*second", e.description)
                if m:
                    retry = int(m.group(1))
            menit = max(1, round(retry / 60))
            return render_template(
                "login.html",
                galat="Terlalu banyak percobaan login. Untuk keamanan, "
                      "tunggu sekitar " + str(menit) + " menit sebelum coba lagi."), 429
        if request.path.startswith("/api/"):
            return jsonify({"error": "Terlalu banyak permintaan. "
                                     "Coba lagi beberapa saat lagi."}), 429
        return render_template("error/429.html"), 429

    @app.get("/")
    def deteksi():
        return render_template("deteksi.html", active="deteksi")

    @app.get("/peta")
    def peta():
        return render_template("peta.html", active="peta")

    @app.get("/riwayat")
    def riwayat():
        return render_template("riwayat.html", active="riwayat")

    @app.get("/segmen")
    def segmen():
        return render_template("segmen.html", active="segmen")

    @app.get("/tentang")
    def tentang():
        return render_template("tentang.html", active="tentang")

    @app.get("/health")
    def health():
        """Kesehatan sistem TANPA efek samping: tidak memuat model, tidak
        membangunkan worker. 200 bila worker inferensi hidup, 503 bila mati
        (untuk monitoring; _pastikan_pekerja akan me-restart-nya saat ada
        request deteksi berikutnya)."""
        s = status_sistem()
        kode = 200 if s["worker_inferensi"]["hidup"] else 503
        return s, kode

    @app.get("/kalibrasi")
    @login_wajib
    def kalibrasi():
        return render_template("kalibrasi.html", active="kalibrasi")

    @app.get("/laporan/preview/<int:sid>")
    def laporan_preview(sid):
        d = detail_sesi(sid)
        if d is None:
            return render_template("laporan_preview.html", active="riwayat", sesi=None, temuan=[], total_prioritas=0, sid=sid), 404
        s = d["sesi"]
        return render_template("laporan_preview.html", active="riwayat", sesi=s, temuan=d["temuan"], total_prioritas=s["skor_prioritas"], sid=sid)

    @app.post("/api/detect")
    @(limiter.limit("30 per minute; 300 per hour") if limiter else (lambda f: f))
    def api_detect():
        f = request.files.get("gambar")
        if f is None or not f.filename:
            return jsonify({"error": "Pilih berkas gambar dulu (JPG/PNG)."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_IMG:
            return jsonify({"error": "Format harus JPG atau PNG."}), 400
        try:
            conf = float(request.form.get("conf", CONF_DEFAULT))
        except ValueError:
            return jsonify({"error": "Confidence tidak valid."}), 400
        conf = min(max(conf, CONF_MIN), CONF_MAX)
        malam = request.form.get("malam", "") in ("1", "true", "on")
        teliti = request.form.get("teliti", "") in ("1", "true", "on")
        try:
            data = f.read(MAX_IMG_BYTES + 1)
        except MemoryError:
            # Terukur 18 Okt 2026: saat RAM mesin habis, spooled upload + decode
            # 12 MP melempar MemoryError. Tanpa penanganan ini klien dapat halaman
            # HTML 500 dari debugger dan tidak tahu harus menunggu/mengecilkan
            # gambar. 503 = sementara, bukan gambar rusak.
            app.logger.exception("memori habis saat membaca unggahan")
            return jsonify({"error": _PESAN_MEMORI}), 503
        if len(data) > MAX_IMG_BYTES:
            return jsonify({"error": "Ukuran gambar maks 15MB. "
                                     "Kecilkan resolusi lalu coba lagi."}), 400
        if not (data[:3] == b"\xff\xd8\xff"
                or data[:8] == b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "Berkas bukan gambar JPG/PNG yang valid."}), 400
        try:
            # Via worker thread GPU khusus: tiap request Flask = thread baru dan
            # inferensi CUDA pertama di thread baru memakan ~10 dtk (terukur).
            hasil = analisis_gambar_terjadwal(data, conf=conf, malam=malam,
                                              teliti=teliti)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except WorkerInferensiMati:
            # Worker GPU berhenti di tengah job -> layanan sedang pulih,
            # bukan kesalahan gambar. 503 supaya klien tahu bisa coba lagi.
            app.logger.warning("worker inferensi mati saat detect")
            return jsonify({"error": "Layanan inferensi sedang pulih. "
                                     "Coba lagi sebentar."}), 503
        except Exception as e:
            if _kurang_memori(e):
                # cv2 melempar cv2.error ("Insufficient memory") untuk OOM,
                # bukan MemoryError, jadi keduanya perlu dikenali.
                app.logger.warning("memori habis saat detect: %s", e)
                return jsonify({"error": _PESAN_MEMORI}), 503
            app.logger.exception("detect gagal")
            return jsonify({"error": "Deteksi gagal. Coba gambar lain."}), 500
        return jsonify(hasil)

    def _dampak_kalibrasi(ppc):
        return {"box_100px_cm": round(100.0 / ppc, 1),
                "lubang_25cm_px": round(25.0 * ppc)}

    @app.get("/api/kalibrasi")
    def api_kalibrasi_status():
        """Status kalibrasi NYATA dari config/severity.yaml."""
        try:
            st = get_kalibrasi()
        except Exception:
            app.logger.exception("status kalibrasi gagal")
            return jsonify({"error": "Gagal baca status kalibrasi."}), 500
        st["dampak"] = _dampak_kalibrasi(st["pixels_per_cm"])
        return jsonify(st)

    @app.post("/api/kalibrasi")
    @login_wajib
    def api_kalibrasi_simpan():
        """Simpan kalibrasi: {pixels_per_cm} atau {panjang_px, panjang_cm}.

        Langsung berlaku untuk deteksi berikutnya (cache config dibuang).
        """
        data = request.get_json(force=True, silent=True) or {}
        catatan = str(data.get("catatan", "") or "")[:200]
        try:
            if "pixels_per_cm" in data:
                ppc = float(data["pixels_per_cm"])
                metode = "manual"
            else:
                ppc = hitung_ppc(data.get("panjang_px"),
                                 data.get("panjang_cm"))
                metode = "penggaris"
            st = simpan_kalibrasi(ppc, metode=metode, catatan=catatan)
        except (ValueError, TypeError) as e:
            return jsonify({"error": str(e)}), 400
        except OSError:
            app.logger.exception("simpan kalibrasi gagal")
            return jsonify({"error": "Gagal tulis config."}), 500
        st["dampak"] = _dampak_kalibrasi(st["pixels_per_cm"])
        return jsonify(st)

    @app.post("/api/kalibrasi/foto")
    @login_wajib
    @(limiter.limit("10 per minute; 60 per hour") if limiter else (lambda f: f))
    def api_kalibrasi_foto():
        """Upload foto penggaris (maks 5MB) -> {image_b64, lebar, tinggi}.

        Hardening pola B5: magic bytes + verifikasi PIL + re-encode JPEG.
        Titik klik dihitung di frontend (koordinat skala ke ukuran asli).
        `lebar`/`tinggi` = ukuran **asli** foto, bukan ukuran tampil; frontend
        memakainya untuk memetakan klik ke ruang koordinat asli, ruang yang sama
        dengan koordinat box deteksi (`maks_sisi_proses` di web/deteksi.py).
        """
        import io
        f = request.files.get("foto")
        if f is None or not f.filename:
            return jsonify({"error": "Pilih foto penggaris dulu."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_IMG:
            return jsonify({"error": "Format harus JPG atau PNG."}), 400
        data = f.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            return jsonify({"error": "Ukuran maks 5MB."}), 400
        if not (data[:3] == b"\xff\xd8\xff"
                or data[:8] == b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "Berkas bukan gambar valid."}), 400
        try:
            import base64
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                rgb = im.convert("RGB")
                # PENTING: ukuran yang DILAPORKAN harus ukuran ASLI, diambil
                # SEBELUM thumbnail. Frontend memetakan klik ke ruang ini
                # (`dimAsli.w / r.width`), dan koordinat box deteksi juga di
                # ruang asli. Bila yang dilaporkan ukuran thumbnail (<=2000),
                # pixels_per_cm terukur di ruang yang salah sehingga dimensi cm
                # dan severity meleset sebesar faktor pengecilan pada foto
                # > 2000 px (bug ini pernah ada: ukuran diambil SETELAH
                # thumbnail, jadi px/cm tidak selaras dengan box).
                w, h = rgb.size
                if max(rgb.size) > 2000:
                    rgb.thumbnail((2000, 2000))  # hanya untuk tampil & hemat muatan
                buf = io.BytesIO()
                rgb.save(buf, format="JPEG", quality=88)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        except Exception:
            return jsonify({"error": "Berkas bukan gambar valid."}), 400
        return jsonify({"image_b64": b64, "lebar": w, "tinggi": h})

    @app.post("/api/verifikasi")
    def api_verifikasi():
        """Verifikasi operator: hasil mentah AI + daftar koreksi -> hasil final.

        Body: {rows: [...mentah...], hapus: [idx...], severity: {idx: sev}}.
        Stateless: frontend menyimpan state koreksi, backend menghitung ulang.
        """
        data = request.get_json(force=True, silent=True) or {}
        rows = data.get("rows", [])
        if not rows:
            return jsonify({"error": "Tidak ada hasil untuk diverifikasi."}), 400
        try:
            baru, total, info = terapkan_koreksi(
                rows, data.get("hapus"), data.get("severity"))
        except Exception:
            app.logger.exception("verifikasi gagal")
            return jsonify({"error": "Verifikasi gagal. Coba lagi."}), 500
        return jsonify({"rows": baru, "total": total, "info": info})

    @app.post("/api/laporan")
    @(limiter.limit("20 per minute; 200 per hour") if limiter else (lambda f: f))
    def api_laporan():
        data = request.get_json(force=True, silent=True) or {}
        rows, total = data.get("rows", []), data.get("total", 0)
        if not rows:
            return jsonify({"error": "Tidak ada hasil untuk dilaporkan."}), 400
        try:
            pdf_path, ann_path = buat_pdf(
                rows, total, image_b64=data.get("image_b64"),
                source=data.get("source", "-"), model_name=data.get("model", "-"),
                verifikasi=data.get("verifikasi", ""))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            app.logger.exception("buat pdf gagal")
            return jsonify({"error": "Gagal membuat PDF. Coba lagi."}), 500
        try:  # baca ke memori dulu; di Windows file terkunci selama send_file
            with open(pdf_path, "rb") as f:
                isi_pdf = f.read()
        finally:
            for p in (pdf_path, ann_path):
                try:
                    if p:
                        os.remove(p)
                except OSError:
                    pass
        return send_file(BytesIO(isi_pdf), as_attachment=True,
                         download_name="laporan_jalan.pdf",
                         mimetype="application/pdf")

    # ---- live stream (Fase 2) ----
    @app.get("/api/stream")
    @_exempt
    def api_stream():
        def gen():
            # Event-driven: kirim frame begitu compose selesai (tanpa batas 15 FPS
            # dan tanpa mengirim ulang JPEG yang sama saat frame baru belum siap).
            seq, idle = -1, 0
            try:
                while True:
                    jpg, running, seq2 = MANAGER.wait_frame(seq, timeout=1.0)
                    if jpg is not None and seq2 != seq:
                        seq = seq2
                        idle = 0
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
                               + jpg + b"\r\n")
                    elif not running:
                        idle += 1
                        if idle > 20:
                            break
            except GeneratorExit:
                # P3: client putus -> hentikan generator segera, jangan loop sampai idle>20
                pass
        return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")

    def _galat_ipcam(url):
        """P4: validasi URL IP-camera publik. Tolak skema selain http/https,
        kredensial di URL, host lokal/pribadi (SSRF), dan URL raksasa."""
        s = str(url or "")
        if len(s) > 500:
            return "URL IP-camera terlalu panjang (maks 500 karakter)."
        if "@" in s.split("://", 1)[-1].split("/", 1)[0]:
            return "URL IP-camera tidak boleh memuat kredensial."
        try:
            from urllib.parse import urlparse as _up
            u = _up(s)
        except Exception:
            return "URL IP-camera tidak valid."
        if u.scheme not in ("http", "https"):
            return "URL IP-camera harus diawali http:// atau https://."
        host = (u.hostname or "").lower().strip(".")
        if not host:
            return "URL IP-camera tidak valid."
        # Untuk penggunaan lokal/izin IP privat (192.168.x.x, 10.x.x.x, dll)
        # Hanya blokir localhost dan alamat yang benar-benar tidak valid
        if host in ("localhost", "ip6-localhost"):
            return "URL IP-camera tidak boleh localhost. Gunakan IP privat (192.168.x.x) atau IP publik."
        import ipaddress as _ip
        try:
            ip = _ip.ip_address(host)
            # Hanya blokir loopback, multicast, reserved, dan unspecified
            # IP privat (192.168.x.x, 10.x.x.x, 172.16-31.x.x) DIIZINKAN untuk penggunaan lokal
            if (ip.is_loopback or ip.is_multicast or ip.is_reserved
                    or ip.is_unspecified):
                return "URL IP-camera tidak boleh alamat loopback/multicast."
            if ip == _ip.ip_address("169.254.169.254"):
                return "URL IP-camera tidak boleh metadata cloud."
        except ValueError:
            # Bentuk IP terobfuskasi tetap ditafsirkan resolver/ffmpeg (desimal
            # 2130706433, heksa 0x7f000001, oktal 0177.0.0.1, bentuk pendek
            # 127.1) tetapi lolos dari ip_address() -> tolak eksplisit.
            import re as _re
            if _re.fullmatch(r"(0x[0-9a-f]+|0[0-7]+|[0-9]+)(\.[0-9a-f]+)*", host):
                return ("URL IP-camera tidak boleh IP terobfuskasi; "
                        "gunakan bentuk titik biasa.")
            # hostname biasa: hanya blokir suffix yang jelas-jelas lokal
            if host.endswith((".local", ".internal")):
                return "URL IP-camera tidak boleh host lokal."
        return None

    @app.post("/api/stream/start")
    @(limiter.limit("10 per minute; 100 per hour") if limiter else (lambda f: f))
    def api_stream_start():
        data = request.get_json(force=True, silent=True) or {}
        source = data.get("source", "webcam")
        if source not in ("webcam", "ipcam"):
            return jsonify({"error": "Sumber harus webcam atau ipcam."}), 400
        target = data.get("target", 0 if source == "webcam" else "")
        if source == "webcam":
            try:
                target = int(target)
            except (TypeError, ValueError):
                return jsonify({"error": "Index webcam harus angka."}), 400
            if not 0 <= target <= 10:
                return jsonify({"error": "Index webcam harus 0-10."}), 400
        else:
            galat = _galat_ipcam(target)
            if galat:
                return jsonify({"error": galat}), 400
            target = str(target)
        try:
            conf = float(data.get("conf", CONF_DEFAULT))
            skip = int(data.get("frame_skip", 2 if source == "webcam" else 1))  # default skip 2 untuk webcam
        except (TypeError, ValueError):
            return jsonify({"error": "confidence/frame_skip tidak valid."}), 400
        conf = min(max(conf, CONF_MIN), CONF_MAX)
        skip = min(max(skip, FRAME_SKIP_MIN), FRAME_SKIP_MAX)
        malam = data.get("malam", False) in (True, 1, "1", "true", "on")
        performa = str(data.get("performa", "") or "").strip().lower() or None
        # Preset "akurat" dihapus 19 Okt 2026 (duplikat "seimbang"); nilai tak
        # dikenal diabaikan -> pakai imgsz_live dari config.
        if performa not in (None, "halus", "seimbang"):
            performa = None
        if MANAGER.running and not _token_dimiliki(data):
            return jsonify({
                "error": "Stream sedang berjalan di tab/perangkat lain. "
                         "Hentikan dulu dari sana sebelum mulai yang baru."}), 409
        MANAGER.start(source, target, conf=conf, frame_skip=skip, malam=malam,
                      performa=performa)
        return jsonify({"ok": True, "token": _token_terbit(),
                        "tips": "FPS tampil rendah? Coba Mode Performa 'Halus'. "
                                "Deteksi jarang? Pakai 'Akurat' atau kecilkan "
                                "interval inferensi."})

    @app.post("/api/stream/stop")
    def api_stream_stop():
        if MANAGER.running and not _token_dimiliki(
                request.get_json(force=True, silent=True) or {}):
            return jsonify({"error": "Stream ini milik sesi lain."}), 403
        MANAGER.stop()
        with _video_lock:
            aktif = _video_tmp_aktif
        if aktif:
            _buang_video_tmp()
        return jsonify({"ok": True})

    @app.get("/api/stream/stats")
    @_exempt
    def api_stream_stats():
        s = MANAGER.stats()
        # Perangkat + backend live aktif, supaya UI bisa jujur soal mode yang
        # benar-benar jalan (GPU+.pt atau CPU+.onnx) tanpa menebak.
        try:
            s["perangkat"] = ringkasan_perangkat()
        except Exception:
            pass
        return jsonify(s)

    @app.post("/api/stream/anotasi")
    def api_stream_anotasi():
        """Toggle anotasi box pada stream live (dipakai tombol toolbar)."""
        if MANAGER.running and not _token_dimiliki(
                request.get_json(force=True, silent=True) or {}):
            return jsonify({"error": "Stream ini milik sesi lain."}), 403
        MANAGER.anotasi_aktif = not MANAGER.anotasi_aktif
        return jsonify({"ok": True, "anotasi": MANAGER.anotasi_aktif})

    @app.post("/api/stream/snapshot")
    def api_stream_snapshot():
        # Lihat tabel temuan TIDAK butuh login (konsisten dengan /api/stream,
        # /api/stream/stats, dan /api/laporan yang publik). Gerbang login ada di
        # penyimpanan sesi (/api/riwayat) dan aksi tulis lain.
        if MANAGER.running and not _token_dimiliki(
                request.get_json(force=True, silent=True) or {}):
            return jsonify({"error": "Stream ini milik sesi lain."}), 403
        snap = MANAGER.snapshot()
        if not snap["rows"]:
            return jsonify({"error": "Belum ada track terekam. Tunggu deteksi muncul."}), 400
        snap["source"] = f"Live ({MANAGER.stats()['source']})"
        snap["model"] = nama_model_live()
        return jsonify(snap)

    @app.post("/api/demo")
    @(limiter.limit("10 per minute; 100 per hour") if limiter else (lambda f: f))
    def api_demo():
        """Fallback sidang: putar video contoh bawaan bila webcam bermasalah."""
        demo = WEB_DIR / "static" / "demo" / "demo_jalan.mp4"
        if not demo.exists():
            return jsonify({"error": "Video contoh tidak ada."}), 404
        data = request.get_json(force=True, silent=True) or {}
        try:
            conf = float(data.get("conf", CONF_DEFAULT))
            skip = int(data.get("frame_skip", 2))
        except (TypeError, ValueError):
            return jsonify({"error": "confidence/frame_skip tidak valid."}), 400
        conf = min(max(conf, CONF_MIN), CONF_MAX)
        skip = min(max(skip, FRAME_SKIP_MIN), FRAME_SKIP_MAX)
        malam = data.get("malam", False) in (True, 1, "1", "true", "on")
        performa = str(data.get("performa", "") or "").strip().lower() or None
        # Preset "akurat" dihapus 19 Okt 2026 (duplikat "seimbang"); nilai tak
        # dikenal diabaikan -> pakai imgsz_live dari config.
        if performa not in (None, "halus", "seimbang"):
            performa = None
        if MANAGER.running and not _token_dimiliki(data):
            return jsonify({
                "error": "Stream sedang berjalan di tab/perangkat lain. "
                         "Hentikan dulu dari sana sebelum mulai yang baru."}), 409
        MANAGER.start("file", str(demo), conf=conf, frame_skip=skip,
                      label="Video contoh (fallback sidang)", malam=malam,
                      performa=performa)
        return jsonify({"ok": True, "token": _token_terbit()})

    @app.post("/api/video")
    @(limiter.limit("10 per minute; 100 per hour") if limiter else (lambda f: f))
    def api_video():
        global _video_tmp, _video_tmp_aktif
        f = request.files.get("video")
        if f is None or not f.filename:
            return jsonify({"error": "Pilih berkas video dulu (MP4)."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ALLOWED_VIDEO:
            return jsonify({"error": "Format harus MP4/AVI/MOV/MKV."}), 400
        try:
            conf = float(request.form.get("conf", CONF_DEFAULT))
            skip = int(request.form.get("frame_skip", 1))
        except (TypeError, ValueError):
            return jsonify({"error": "confidence/frame_skip tidak valid."}), 400
        conf = min(max(conf, CONF_MIN), CONF_MAX)
        skip = min(max(skip, FRAME_SKIP_MIN), FRAME_SKIP_MAX)
        malam = request.form.get("malam", "") in ("1", "true", "on")
        if MANAGER.running and not _token_dimilik_form(request.form.get("token")):
            return jsonify({
                "error": "Stream sedang berjalan di tab/perangkat lain. "
                         "Hentikan dulu dari sana sebelum mulai yang baru."}), 409
        # P1: simpan ke file baru, lalu (tukar pointer + start + hapus lama)
        # di bawah satu lock. Upload konkuren jadi berurutan, sehingga file
        # lama tidak pernah di-unlink sebelum start menggantikannya.
        with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as tmp:
            f.save(tmp.name)
            baru = tmp.name
        with _video_lock:
            lama = _video_tmp
            MANAGER.stop()
            _video_tmp, _video_tmp_aktif = baru, True
            MANAGER.start("file", baru, conf=conf, frame_skip=skip, label=f.filename,
                          malam=malam,
                          performa=(request.form.get("performa") or None))
            if lama and lama != baru:
                try:
                    os.remove(lama)
                except OSError:
                    pass
        return jsonify({"ok": True, "token": _token_terbit()})

    # ---- riwayat + peta (Fase 3) ----
    def _koordinat(data):
        def _f(k, lo, hi):
            v = data.get(k)
            if v in (None, ""):
                return None
            try:
                f = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"Koordinat {k} tidak valid.")
            if not lo <= f <= hi:
                raise ValueError(f"Koordinat {k} di luar rentang.")
            return f
        return _f("lat", -90, 90), _f("lon", -180, 180)

    @app.post("/api/riwayat")
    @login_wajib
    @(limiter.limit("20 per minute; 200 per hour") if limiter else (lambda f: f))
    def api_riwayat_simpan():
        from sqlite3 import IntegrityError
        data = request.get_json(force=True, silent=True) or {}
        rows = data.get("rows", [])
        if not rows:
            return jsonify({"error": "Tidak ada hasil untuk disimpan."}), 400
        img = data.get("image_b64")
        if img and len(str(img)) > 12 * 1024 * 1024:
            return jsonify({"error": "Gambar terlalu besar untuk disimpan."}), 413
        client_ref = str(data.get("client_ref") or "").strip()[:128] or None
        # Idempotensi: simpan ulang dengan client_ref sama -> kembalikan yang lama
        # (mencegah baris ganda dari klik dobel / retry jaringan).
        if client_ref:
            ada = sesi_by_client_ref(client_ref)
            if ada:
                return jsonify({"id": ada, "duplikat": True, "alasan": "client_ref"})
        try:
            lat, lon = _koordinat(data)
            try:
                total = int(data.get("total", 0))
            except (TypeError, ValueError):
                raise ValueError("Total tidak valid.")
            # Heuristik anti-duplikat titik: koordinat sama dalam 10 menit terakhir.
            # Bisa dilewati dengan izinkan_duplikat (inspeksi ulang yang disengaja).
            if not data.get("izinkan_duplikat"):
                kembar = sesi_duplikat_coord(lat, lon, sumber=data.get("sumber"))
                if kembar:
                    return jsonify({
                        "id": kembar, "duplikat": True, "alasan": "koordinat",
                        "pesan": "Riwayat di titik ini baru saja tersimpan."})
            try:
                sid = simpan_sesi(
                    sumber=data.get("sumber", "-"), lokasi=data.get("lokasi", "-"),
                    model=data.get("model", "-"), rows=rows, total=total,
                    lat=lat, lon=lon, image_b64=data.get("image_b64"),
                    client_ref=client_ref)
            except IntegrityError:
                # Balapan: request lain menyimpan client_ref sama lebih dulu.
                ada = sesi_by_client_ref(client_ref)
                if ada:
                    return jsonify({"id": ada, "duplikat": True, "alasan": "client_ref"})
                raise
        except (TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"id": sid})

    @app.get("/api/riwayat")
    def api_riwayat_daftar():
        LIMIT_MAX = 200
        rows = daftar_sesi(
            dari=request.args.get("dari"), sampai=request.args.get("sampai"),
            severity=request.args.get("severity"), q=request.args.get("q"),
            limit=LIMIT_MAX + 1)
        overflow = len(rows) > LIMIT_MAX
        return jsonify({
            "data": rows[:LIMIT_MAX],
            "overflow": overflow,
            "total_db": hitung_sesi(
                dari=request.args.get("dari"), sampai=request.args.get("sampai"),
                severity=request.args.get("severity"), q=request.args.get("q"))
        })

    @app.get("/api/riwayat/<int:sid>")
    def api_riwayat_detail(sid):
        d = detail_sesi(sid)
        if d is None:
            return jsonify({"error": "Riwayat tidak ditemukan."}), 404
        return jsonify(d)

    @app.delete("/api/riwayat/<int:sid>")
    @login_wajib
    @(limiter.limit("10 per hour") if limiter else (lambda f: f))
    def api_riwayat_hapus(sid):
        if not hapus_sesi(sid):
            return jsonify({"error": "Riwayat tidak ditemukan."}), 404
        return jsonify({"ok": True})

    @app.put("/api/riwayat/<int:sid>/segmen")
    @login_wajib
    def api_riwayat_segmen(sid):
        data = request.get_json(force=True, silent=True) or {}
        segmen_id = data.get("segmen_id")
        if segmen_id is not None:
            try:
                segmen_id = int(segmen_id)
            except (TypeError, ValueError):
                return jsonify({"error": "segmen_id tidak valid."}), 400
        try:
            ok = tetapkan_segmen_sesi(sid, segmen_id)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not ok:
            return jsonify({"error": "Riwayat tidak ditemukan."}), 404
        return jsonify({"ok": True})

    @app.get("/api/riwayat/<int:sid>/gambar")
    def api_riwayat_gambar(sid):
        # ?thumb=1 untuk thumbnail kecil (tabel), default = gambar penuh (detail)
        thumb = request.args.get("thumb", "") in ("1", "true", "yes")
        nama = f"{sid}_thumb.jpg" if thumb else f"{sid}.jpg"
        p = Path(app.config["DB_PATH"]).parent / "hasil" / nama
        if not p.exists() and thumb:
            # Fallback ke gambar penuh kalau thumbnail belum ada (data lama)
            p = Path(app.config["DB_PATH"]).parent / "hasil" / f"{sid}.jpg"
        if not p.exists():
            return jsonify({"error": "Gambar tidak ada."}), 404
        return send_file(p, mimetype="image/jpeg")

    @app.get("/api/peta")
    def api_peta():
        return jsonify(titik_peta())

    # ---- segmen jalan + SDI-visual (instrumen prioritas) ----
    @app.post("/api/segmen")
    @login_wajib
    def api_segmen_buat():
        data = request.get_json(force=True, silent=True) or {}
        try:
            sid = tambah_segmen(
                data.get("nama"), jalan=data.get("jalan", "-"),
                panjang_m=data.get("panjang_m", 100),
                lebar_m=data.get("lebar_m", 6),
                sdi_manual=data.get("sdi_manual"),
                catatan=data.get("catatan", ""))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        return jsonify({"id": sid})

    @app.get("/api/segmen")
    def api_segmen_daftar():
        return jsonify(daftar_segmen())

    @app.get("/api/segmen/<int:sid>")
    def api_segmen_detail(sid):
        d = detail_segmen(sid)
        if d is None:
            return jsonify({"error": "Segmen tidak ditemukan."}), 404
        d["tanpa_segmen"] = sesi_tanpa_segmen()
        return jsonify(d)

    @app.put("/api/segmen/<int:sid>")
    @login_wajib
    def api_segmen_ubah(sid):
        data = request.get_json(force=True, silent=True) or {}
        try:
            ok = ubah_segmen(
                sid, nama=data.get("nama"), jalan=data.get("jalan"),
                panjang_m=data.get("panjang_m"), lebar_m=data.get("lebar_m"),
                sdi_manual=data.get("sdi_manual", "__kosong__"),
                catatan=data.get("catatan"))
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not ok:
            return jsonify({"error": "Segmen tidak ditemukan."}), 404
        return jsonify({"ok": True})

    @app.delete("/api/segmen/<int:sid>")
    @login_wajib
    def api_segmen_hapus(sid):
        if not hapus_segmen(sid):
            return jsonify({"error": "Segmen tidak ditemukan."}), 404
        return jsonify({"ok": True})

    @app.post("/api/segmen/<int:sid>/anggota")
    @login_wajib
    def api_segmen_tambah_anggota(sid):
        data = request.get_json(force=True, silent=True) or {}
        try:
            sesi_id = int(data.get("sesi_id"))
        except (TypeError, ValueError):
            return jsonify({"error": "sesi_id tidak valid."}), 400
        try:
            ok = tetapkan_segmen_sesi(sesi_id, sid)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        if not ok:
            return jsonify({"error": "Sesi tidak ditemukan."}), 404
        return jsonify({"ok": True})

    @app.delete("/api/segmen/<int:sid>/anggota/<int:sesi_id>")
    @login_wajib
    def api_segmen_hapus_anggota(sid, sesi_id):
        # sid hanya untuk kejelasan URL; yang diubah adalah sesi tersebut.
        if not tetapkan_segmen_sesi(sesi_id, None):
            return jsonify({"error": "Sesi tidak ditemukan."}), 404
        return jsonify({"ok": True})

    @app.get("/api/segmen/<int:sid>/pdf")
    def api_segmen_pdf(sid):
        from laporan import buat_laporan_segmen
        d = detail_segmen(sid)
        if d is None:
            return jsonify({"error": "Segmen tidak ditemukan."}), 404
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                pdf_path = f.name
            buat_laporan_segmen(pdf_path, d)
            with open(pdf_path, "rb") as f:
                isi = f.read()
        except Exception:
            app.logger.exception("buat pdf segmen gagal")
            return jsonify({"error": "Gagal membuat PDF."}), 500
        finally:
            try:
                os.remove(pdf_path)
            except OSError:
                pass
        return send_file(BytesIO(isi), as_attachment=True,
                         download_name=f"sdi-segmen-{sid}.pdf",
                         mimetype="application/pdf")

    return app



app = create_app()

def _preload_model_di_background():
    """Preload model di thread terpisah agar deteksi pertama tidak lambat."""
    import threading
    def _load():
        try:
            from deteksi import (get_model, get_scene_model, model_live_aktif,
                                 nama_model, nama_model_live,
                                 resolve_scene_model, ringkasan_perangkat)
            print("[preload] Memuat model gambar...")
            get_model(kunci="model_gambar")
            print(f"[preload] Model gambar siap: {nama_model(kunci='model_gambar')}")
            p = ringkasan_perangkat()
            print("[preload] Memuat model live...")
            ml = model_live_aktif()
            print(f"[preload] Model live siap: {nama_model_live()} "
                  f"(perangkat: {'GPU ' + p['gpu'] if p['cuda'] else 'CPU'}, "
                  f"mode_backend={p['mode_backend']})")
            # Scene classifier (gate jalan basah, ~5MB): preload + warmup dummy
            # agar klasifikasi foto pertama tidak menunggu.
            try:
                if resolve_scene_model() is not None:
                    print("[preload] Memuat scene classifier...")
                    ms = get_scene_model()
                    import numpy as np
                    ms.predict(np.zeros((224, 224, 3), dtype=np.uint8), verbose=False)
                    print("[preload] Scene classifier siap.")
                else:
                    print("[preload] Scene classifier tidak ada -> gate nonaktif.")
            except Exception as e:
                print(f"[preload] Scene classifier dilewati: {e}")
            # Warmup: satu inferensi dummy agar sesi ONNX/CUDA + kernel siap,
            # sehingga deteksi pertama saat stream dimulai tidak menunggu.
            try:
                import numpy as np
                ml.predict(np.zeros((480, 640, 3), dtype=np.uint8), verbose=False)
                print("[preload] Warmup model live selesai.")
            except Exception as e:
                print(f"[preload] Warmup dilewati: {e}")
            # Worker inferensi GPU khusus: start + warmup di thread-nya sendiri
            # (anti pajak ~10 dtk inisialisasi CUDA per request Flask).
            try:
                from deteksi import start_worker_inferensi
                print("[preload] Memulai worker inferensi GPU...")
                start_worker_inferensi()
                print("[preload] Worker inferensi GPU berjalan.")
            except Exception as e:
                print(f"[preload] Worker inferensi dilewati: {e}")
            # Thread inferensi live PERSISTEN: hangatkan CUDA sekali di thread
            # yang sama yang akan menginferensi live, agar mulai stream langsung
            # menampilkan kotak (tanpa jeda inisialisasi per-thread ~3-8 dtk).
            try:
                from streaming import MANAGER as _mgr
                print("[preload] Menghangatkan inferensi live...")
                _mgr.panaskan()
                print("[preload] Inferensi live siap.")
            except Exception as e:
                print(f"[preload] Warmup live dilewati: {e}")
        except Exception as e:
            print(f"[preload] Gagal preload model: {e}")
    t = threading.Thread(target=_load, daemon=True)
    t.start()

if __name__ == "__main__":
    _debug = os.environ.get("JP_DEBUG", "0") in ("1", "true", "True", "yes")
    if not _debug:
        _preload_model_di_background()
    app.run(host="127.0.0.1", port=5000, debug=_debug)
