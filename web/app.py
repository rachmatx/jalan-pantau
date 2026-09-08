"""JalanPantau (Flask): deteksi kerusakan jalan + severity + biaya + PDF + peta + riwayat.

Run dari root repo:
    .\\.venv\\Scripts\\python web/app.py
Buka: http://127.0.0.1:5000
"""
import atexit
import functools
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

# Pastikan folder web/ ada di path untuk import lokal
sys.path.insert(0, str(Path(__file__).resolve().parent))

from flask import (Flask, Response, current_app, jsonify, redirect,
                   render_template, request, send_file, session, url_for)

from deteksi import (analisis_gambar, buat_pdf, get_kalibrasi, get_prices,
                     hitung_ppc, nama_model, simpan_kalibrasi,
                     terapkan_koreksi)
from biaya import rupiah
from streaming import MANAGER
from database import (daftar_sesi, detail_sesi, hapus_sesi, simpan_sesi,
                       titik_peta, tutup_db, init_instansi, daftar_instansi,
                       instansi_terdekat, simpan_instansi, hapus_instansi,
                       instansi_by_id, simpan_disposisi, daftar_disposisi,
                       detail_disposisi, detail_disposisi_by_bap,
                       update_status_disposisi, hapus_disposisi,
                       statistik_disposisi, hitung_disposisi,
                       migrasi_disposisi_v2, migrasi_admin_v2,
                       pastikan_akun_daerah, daftar_admin,
                       riwayat_catatan, init_admin, cek_login,
                       set_password_admin, hitung_sesi)

WEB_DIR = Path(__file__).parent

# Slug URL dashboard -> nama daerah resmi (kolom instansi_daerah).
# Handler /pupr-<daerah>/dashboard + normalisasi param ?daerah= di API,
# agar klien boleh kirim slug ('kab-bogor') ATAU nama lengkap.
SLUG_DAERAH = {
    # Kota di Jawa Barat
    "bogor": "Bogor", "sukabumi": "Sukabumi", "cianjur": "Cianjur",
    "bandung": "Bandung", "garut": "Garut",
    "tasikmalaya": "Tasikmalaya", "ciamis": "Ciamis",
    "kuningan": "Kuningan", "cirebon": "Cirebon",
    "majalengka": "Majalengka", "sumedang": "Sumedang",
    "indramayu": "Indramayu", "subang": "Subang",
    "purwakarta": "Purwakarta", "karawang": "Karawang",
    "bekasi": "Bekasi", "depok": "Depok", "cimahi": "Cimahi",
    "banjar": "Banjar",
    # Kabupaten di Jawa Barat
    "kab-bogor": "Kabupaten Bogor",
    "kab-sukabumi": "Kabupaten Sukabumi",
    "kab-cianjur": "Kabupaten Cianjur",
    "kab-bandung": "Kabupaten Bandung",
    "kab-garut": "Kabupaten Garut",
    "kab-tasikmalaya": "Kabupaten Tasikmalaya",
    "kab-ciamis": "Kabupaten Ciamis",
    "kab-kuningan": "Kabupaten Kuningan",
    "kab-cirebon": "Kabupaten Cirebon",
    "kab-majalengka": "Kabupaten Majalengka",
    "kab-sumedang": "Kabupaten Sumedang",
    "kab-indramayu": "Kabupaten Indramayu",
    "kab-subang": "Kabupaten Subang",
    "kab-purwakarta": "Kabupaten Purwakarta",
    "kab-karawang": "Kabupaten Karawang",
    "kab-bekasi": "Kabupaten Bekasi",
    "kab-bandung-barat": "Kabupaten Bandung Barat",
    "kab-pangandaran": "Kabupaten Pangandaran",
    # Luar Jawa Barat
    "jakarta": "Jakarta", "tangerang": "Tangerang",
    "semarang": "Semarang", "surabaya": "Surabaya", "medan": "Medan",
}


def normalisasi_daerah(nilai):
    """Terima slug ('kab-bogor') atau nama lengkap ('Kabupaten Bogor'),
    kembalikan nama daerah resmi. None bila tak dikenal."""
    if not nilai:
        return None
    k = nilai.strip().lower()
    if k in SLUG_DAERAH:
        return SLUG_DAERAH[k]
    for nama in SLUG_DAERAH.values():
        if nama.lower() == k:
            return nama
    return None


def slug_daerah(nilai):
    """Kebalikan normalisasi: nama daerah resmi -> slug URL, None bila tak
    dikenal. Dipakai login utk redirect ke dashboard yang benar."""
    if not nilai:
        return None
    nama = normalisasi_daerah(nilai)
    if not nama:
        return None
    for slug, n in SLUG_DAERAH.items():
        if n == nama:
            return slug
    return None

ALLOWED_IMG = {"jpg", "jpeg", "png"}
ALLOWED_VIDEO = {"mp4", "avi", "mov", "mkv"}
MAX_VIDEO_BYTES = 200 * 1024 * 1024  # video live (global Flask)
MAX_IMG_BYTES = 15 * 1024 * 1024  # gambar deteksi: 12MP JPEG ~3-8MB; di atas ini tolak cepat
CONF_MIN, CONF_MAX, CONF_DEFAULT = 0.05, 0.8, 0.25
FRAME_SKIP_MIN, FRAME_SKIP_MAX = 1, 30
_video_tmp = None
_video_tmp_aktif = False  # True bila stream file saat ini memakai _video_tmp hasil upload
_video_lock = threading.Lock()  # P1: jaga _video_tmp dari race upload konkuren


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


def create_app():
    app = Flask(__name__, template_folder=str(WEB_DIR / "templates"),
                static_folder=str(WEB_DIR / "static"))
    app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES
    app.config.setdefault("DB_PATH", str(WEB_DIR / "instance" / "riwayat.db"))
    app.config["TEMPLATES_AUTO_RELOAD"] = True  # Disable template cache
    # P4: cookie session eksplisit aman (HttpOnly + SameSite).
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.teardown_appcontext(tutup_db)

    @app.after_request
    def _kepala_aman(resp):
        # P4: cegah MIME-sniffing; API JSON jangan di-cache browser.
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    # Inisialisasi data instansi default + migrasi kolom disposisi v2
    with app.app_context():
        init_instansi()
        migrasi_disposisi_v2()
        migrasi_admin_v2()
        init_admin()  # seed akun admin default (lihat database.init_admin)
        # Akun login tiap daerah: pupr_<slug> -> dashboard daerahnya.
        # Disegel sandi acak hingga superadmin mengaturnya di halaman Instansi.
        pastikan_akun_daerah(
            [(f"pupr_{slug}", nama) for slug, nama in SLUG_DAERAH.items()])

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
        """Proteksi halaman/API khusus admin dinas: redirect ke login
        (HTML) atau 401 JSON (API) bila belum login."""
        @functools.wraps(fn)
        def pembungkus(*a, **kw):
            if not session.get("admin_id"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Login diperlukan."}), 401
                return redirect(url_for("login_form", next=request.path))
            return fn(*a, **kw)
        return pembungkus

    def superadmin_wajib(fn):
        """Khusus superadmin (daerah '-'): tambah/hapus instansi + kelola sandi.
        HTML -> redirect login; API -> 401/403 JSON."""
        @functools.wraps(fn)
        def pembungkus(*a, **kw):
            if not session.get("admin_id"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Login diperlukan."}), 401
                return redirect(url_for("login_form", next=request.path))
            if session.get("admin_daerah") != "-":
                if request.path.startswith("/api/"):
                    return jsonify({"error": "Hanya superadmin yang boleh."}), 403
                return redirect(url_for("login_form"))
            return fn(*a, **kw)
        return pembungkus

    # ---- Autentikasi ----
    @app.get("/login")
    def login_form():
        if session.get("admin_id"):
            return redirect(url_for("dashboard_handler", daerah="bandung"))
        return render_template("login.html")

    @app.post("/login")
    @(limiter.limit("5 per minute; 20 per hour") if limiter else (lambda f: f))
    def login_post():
        user = (request.form.get("username") or "").strip().lower()
        pwd = request.form.get("password") or ""
        admin = cek_login(user, pwd)
        if not admin:
            return render_template("login.html", galat="Username atau password salah."), 401
        session.clear()
        session["admin_id"] = admin["id"]
        session["admin_user"] = admin["username"]
        session["admin_daerah"] = admin["daerah"]
        tujuan = request.form.get("next") or ""
        # Default: dashboard sesuai daerah admin (fallback bandung utk akun umum)
        d = session.get("admin_daerah")
        if not tujuan and d and d not in ("-", None):
            s = slug_daerah(d)
            if s:
                tujuan = f"/pupr-{s}/dashboard"
        if not tujuan:
            tujuan = "/pupr-bandung/dashboard"
        # cegah open-redirect: hanya path relatif
        if not tujuan.startswith("/") or tujuan.startswith("//"):
            tujuan = "/pupr-bandung/dashboard"
        # P3: normalisasi slug daerah case-insensitive (/pupr-Bogor/... -> /pupr-bogor/...)
        # agar login dari URL kapital tidak berakhir 404.
        import re as _re
        m = _re.match(r"^(/pupr-)([^/]+)(/.*)?$", tujuan, flags=_re.IGNORECASE)
        if m:
            slug = m.group(2).lower()
            if slug in SLUG_DAERAH:
                tujuan = f"/pupr-{slug}{m.group(3) or ''}"
        return redirect(tujuan)

    @app.get("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login_form"))

    # Cache-buster: versi ini akan ditambahkan ke semua asset static
    STATIC_VERSION = "30"

    @app.context_processor
    def inject_static_version():
        return {"static_v": STATIC_VERSION}

    @app.errorhandler(413)
    def terlalu_besar(e):
        """Global 200MB (video) terlampaui -> JSON, bukan halaman HTML Flask."""
        return jsonify({"error": "Berkas terlalu besar (maks 200MB untuk "
                                 "video, 15MB gambar, 5MB foto kalibrasi/disposisi)."}), 413

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

    @app.get("/tentang")
    def tentang():
        prices = []
        for h in get_prices():
            h = dict(h)
            try:
                h["harga_fmt"] = f"{float(h['harga_satuan_rp']):,.0f}".replace(",", ".")
            except (TypeError, ValueError):
                h["harga_fmt"] = h["harga_satuan_rp"]
            prices.append(h)
        return render_template("tentang.html", active="tentang", prices=prices)

    @app.get("/mobile")
    def mobile():
        return render_template("mobile.html", active="deteksi")

    @app.get("/kalibrasi")
    def kalibrasi():
        return render_template("kalibrasi.html", active="kalibrasi")

    @app.get("/laporan/preview/<int:sid>")
    def laporan_preview(sid):
        d = detail_sesi(sid)
        if d is None:
            return render_template("laporan_preview.html", active="riwayat", sesi=None, temuan=[], total_rp=0, sid=sid), 404
        s = d["sesi"]
        return render_template("laporan_preview.html", active="riwayat", sesi=s, temuan=d["temuan"], total_rp=s["total_rp"], sid=sid)

    @app.get("/disposisi")
    def disposisi():
        return render_template("disposisi_kirim.html", active="disposisi")

    @app.get("/disposisi/<int:sid>")
    def disposisi_detail(sid):
        # Cari disposisi berdasarkan bap_id (sid dari BAP)
        d = detail_disposisi_by_bap(sid)
        if d is None:
            # Coba cari berdasarkan id disposisi langsung
            d = detail_disposisi(sid)
        if d is None:
            # Fallback: tampilkan data sesi saja
            s = detail_sesi(sid)
            if s is None:
                return render_template("disposisi_detail.html", active="disposisi", sesi=None, sid=sid, disposisi=None), 404
            return render_template("disposisi_detail.html", active="disposisi", sesi=s["sesi"], sid=sid, disposisi=None)
        # Ambil juga data sesi untuk tampilan
        s = detail_sesi(d["bap_id"])
        return render_template("disposisi_detail.html", active="disposisi", sesi=s["sesi"] if s else None, sid=sid, disposisi=d)

    @app.post("/api/detect")
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
        data = f.read(MAX_IMG_BYTES + 1)
        if len(data) > MAX_IMG_BYTES:
            return jsonify({"error": "Ukuran gambar maks 15MB. "
                                     "Kecilkan resolusi lalu coba lagi."}), 400
        if not (data[:3] == b"\xff\xd8\xff"
                or data[:8] == b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "Berkas bukan gambar JPG/PNG yang valid."}), 400
        try:
            hasil = analisis_gambar(data, conf=conf, malam=malam,
                                    teliti=teliti)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        except Exception:
            app.logger.exception("detect gagal")
            return jsonify({"error": "Deteksi gagal. Coba gambar lain."}), 500
        hasil["total_str"] = rupiah(hasil["total"])
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
    def api_kalibrasi_foto():
        """Upload foto penggaris (maks 5MB) -> {image_b64, lebar, tinggi}.

        Hardening pola B5: magic bytes + verifikasi PIL + re-encode JPEG.
        Titik klik dihitung di frontend (koordinat skala ke ukuran asli).
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
                if max(rgb.size) > 2000:
                    rgb.thumbnail((2000, 2000))
                w, h = rgb.size
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
        return jsonify({"rows": baru, "total": total,
                        "total_str": rupiah(total), "info": info})

    @app.post("/api/laporan")
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
        try:
            return send_file(pdf_path, as_attachment=True,
                             download_name="laporan_jalan.pdf",
                             mimetype="application/pdf")
        finally:
            for p in (pdf_path, ann_path):
                try:
                    if p:
                        os.remove(p)
                except OSError:
                    pass

    # ---- live stream (Fase 2) ----
    @app.get("/api/stream")
    @_exempt
    def api_stream():
        def gen():
            idle = 0
            try:
                while True:
                    jpg, running = MANAGER.get_frame()
                    if jpg is not None:
                        idle = 0
                        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")
                    elif not running:
                        idle += 1
                        if idle > 20:
                            break
                    time.sleep(1 / 15)
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
        if host in ("localhost", "ip6-localhost"):
            return "URL IP-camera tidak boleh localhost."
        import ipaddress as _ip
        try:
            ip = _ip.ip_address(host)
            if (ip.is_private or ip.is_loopback or ip.is_link_local
                    or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                return "URL IP-camera tidak boleh alamat privat/lokal."
            if ip == _ip.ip_address("169.254.169.254"):
                return "URL IP-camera tidak boleh metadata cloud."
        except ValueError:
            # hostname biasa: tolak suffix lokal
            if host.endswith((".local", ".internal", ".lan", ".home")):
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
        MANAGER.start(source, target, conf=conf, frame_skip=skip, malam=malam)
        return jsonify({"ok": True,
                        "tips": "FPS rendah? Coba: naikkan frame_skip (2-3), turunkan confidence (0.15-0.2), atau gunakan video contoh."})

    @app.post("/api/stream/stop")
    def api_stream_stop():
        MANAGER.stop()
        with _video_lock:
            aktif = _video_tmp_aktif
        if aktif:
            _buang_video_tmp()
        return jsonify({"ok": True})

    @app.get("/api/stream/stats")
    @_exempt
    def api_stream_stats():
        return jsonify(MANAGER.stats())

    @app.post("/api/stream/anotasi")
    def api_stream_anotasi():
        """Toggle anotasi box pada stream live (dipakai tombol toolbar)."""
        MANAGER.anotasi_aktif = not MANAGER.anotasi_aktif
        return jsonify({"ok": True, "anotasi": MANAGER.anotasi_aktif})

    @app.post("/api/stream/snapshot")
    def api_stream_snapshot():
        snap = MANAGER.snapshot()
        if not snap["rows"]:
            return jsonify({"error": "Belum ada track terekam. Tunggu deteksi muncul."}), 400
        snap["total_str"] = rupiah(snap["total"])
        snap["source"] = f"Live ({MANAGER.stats()['source']})"
        snap["model"] = nama_model(kunci="model_live")
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
        MANAGER.start("file", str(demo), conf=conf, frame_skip=skip,
                      label="Video contoh (fallback sidang)", malam=malam)
        return jsonify({"ok": True})

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
        # P1: simpan ke file baru dulu, stop stream lama, baru tukar pointer
        # di bawah lock agar upload konkuren tidak saling unlink.
        with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as tmp:
            f.save(tmp.name)
            baru = tmp.name
        MANAGER.stop()
        with _video_lock:
            lama = _video_tmp
            _video_tmp, _video_tmp_aktif = baru, True
        if lama:
            try:
                os.remove(lama)
            except OSError:
                pass
        MANAGER.start("file", baru, conf=conf, frame_skip=skip, label=f.filename, malam=malam)
        return jsonify({"ok": True})

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
    def api_riwayat_simpan():
        data = request.get_json(force=True, silent=True) or {}
        rows = data.get("rows", [])
        if not rows:
            return jsonify({"error": "Tidak ada hasil untuk disimpan."}), 400
        try:
            lat, lon = _koordinat(data)
            try:
                total = int(data.get("total", 0))
            except (TypeError, ValueError):
                raise ValueError("Total tidak valid.")
            sid = simpan_sesi(
                sumber=data.get("sumber", "-"), lokasi=data.get("lokasi", "-"),
                model=data.get("model", "-"), rows=rows, total=total,
                lat=lat, lon=lon, image_b64=data.get("image_b64"))
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

    # ---- API Instansi Pemerintah ----
    @app.get("/api/instansi")
    def api_instansi_daftar():
        daerah = normalisasi_daerah(request.args.get("daerah"))
        return jsonify(daftar_instansi(daerah=daerah))

    @app.get("/api/instansi/terdekat")
    def api_instansi_terdekat():
        """Cari instansi terdekat berdasarkan lat/lon."""
        try:
            lat = float(request.args.get("lat", 0))
            lon = float(request.args.get("lon", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Parameter lat/lon tidak valid."}), 400
        inst = instansi_terdekat(lat, lon)
        if not inst:
            return jsonify({"error": "Tidak ada instansi ditemukan."}), 404
        return jsonify(inst)

    @app.get("/api/instansi/<int:iid>")
    def api_instansi_detail(iid):
        inst = instansi_by_id(iid)
        if not inst:
            return jsonify({"error": "Instansi tidak ditemukan."}), 404
        return jsonify(inst)

    @app.post("/api/instansi")
    @login_wajib
    @superadmin_wajib
    def api_instansi_simpan():
        data = request.get_json(force=True, silent=True) or {}
        required = ["nama", "daerah", "alamat", "email", "telepon"]
        for f in required:
            if not data.get(f):
                return jsonify({"error": f"Field {f} wajib diisi."}), 400
            if len(str(data.get(f))) > 200:
                return jsonify({"error": f"Field {f} terlalu panjang (maks 200)."}), 400
        try:
            lat = float(data.get("lat") or 0) or None
            lon = float(data.get("lon") or 0) or None
            radius = float(data.get("radius_km", 50))
        except (TypeError, ValueError):
            return jsonify({"error": "Format angka tidak valid."}), 400
        if lat is not None and not -90 <= lat <= 90:
            return jsonify({"error": "Latitude di luar rentang."}), 400
        if lon is not None and not -180 <= lon <= 180:
            return jsonify({"error": "Longitude di luar rentang."}), 400
        if not 1 <= radius <= 500:
            return jsonify({"error": "Radius harus 1-500 km."}), 400
        iid = simpan_instansi(data["nama"], data["daerah"], data["alamat"],
                             data["email"], data["telepon"], lat, lon, radius)
        return jsonify({"id": iid, "ok": True})

    @app.delete("/api/instansi/<int:iid>")
    @login_wajib
    @superadmin_wajib
    def api_instansi_hapus(iid):
        if not hapus_instansi(iid):
            return jsonify({"error": "Instansi tidak ditemukan."}), 404
        return jsonify({"ok": True})

    # ---- API Kelola Akun (superadmin saja) ----
    @app.get("/api/admin")
    @login_wajib
    @superadmin_wajib
    def api_admin_daftar():
        return jsonify(daftar_admin())

    @app.post("/api/admin/sandi")
    @login_wajib
    @superadmin_wajib
    @(limiter.limit("30 per minute") if limiter else (lambda f: f))
    def api_admin_sandi():
        """Atur/ganti sandi akun login (min 8 karakter)."""
        data = request.get_json(force=True, silent=True) or {}
        username = (data.get("username") or "").strip().lower()
        sandi = data.get("sandi_baru") or ""
        if not username:
            return jsonify({"error": "Username wajib diisi."}), 400
        if len(sandi) < 8:
            return jsonify({"error": "Sandi minimal 8 karakter."}), 400
        if len(sandi) > 200:
            return jsonify({"error": "Sandi terlalu panjang."}), 400
        from database import get_db
        row = get_db().execute(
            "SELECT daerah FROM admin WHERE username = ?", (username,)).fetchone()
        if row is None:
            return jsonify({"error": "Akun tidak ditemukan."}), 404
        if not set_password_admin(username, sandi, row["daerah"]):
            return jsonify({"error": "Gagal mengatur sandi."}), 400
        return jsonify({"ok": True})

    # ---- API Disposisi ----
    # GET daftar: publik untuk halaman disposisi publik petugas (kirim laporan),
    # tapi bila login admin dinas, tambah limit longgar. PUT/DELETE + foto =
    # mutasi status dinas -> wajib login admin.
    @app.get("/api/disposisi")
    def api_disposisi_daftar():
        # Normalisasi: terima slug ('kab-bogor') ATAU nama lengkap
        daerah = normalisasi_daerah(request.args.get("daerah"))
        status = request.args.get("status")
        urgensi = request.args.get("urgensi")
        # exact=1 -> cocokkan daerah persis (dashboard dinas tidak boleh
        # mencampur "Bogor" dengan "Kabupaten Bogor", dll.)
        exact = request.args.get("exact", "") in ("1", "true", "yes")
        return jsonify(daftar_disposisi(daerah=daerah, status=status,
                                         urgensi=urgensi, exact=exact))

    @app.get("/api/disposisi/stats")
    def api_disposisi_stats():
        """Total disposisi untuk filter yang sama (pendamping paginasi)."""
        daerah = normalisasi_daerah(request.args.get("daerah"))
        exact = request.args.get("exact", "") in ("1", "true", "yes")
        return jsonify({"total": hitung_disposisi(
            daerah=daerah, status=request.args.get("status"),
            urgensi=request.args.get("urgensi"), exact=exact)})

    @app.get("/api/disposisi/<int:did>")
    def api_disposisi_detail(did):
        d = detail_disposisi(did)
        if not d:
            return jsonify({"error": "Disposisi tidak ditemukan."}), 404
        d["riwayat_catatan"] = riwayat_catatan(did)
        return jsonify(d)

    @app.post("/api/disposisi")
    @(limiter.limit("30 per minute; 600 per hour") if limiter else (lambda f: f))
    def api_disposisi_simpan():
        data = request.get_json(force=True, silent=True) or {}
        required = ["bap_id", "bap_nomor", "lokasi", "n_temuan", "total_rp", "worst",
                    "instansi_id", "instansi_nama", "instansi_daerah", "instansi_email"]
        for f in required:
            if not data.get(f) and data.get(f) != 0:
                return jsonify({"error": f"Field {f} wajib diisi."}), 400
        for f in ("bap_nomor", "lokasi", "worst", "instansi_nama",
                  "instansi_daerah", "instansi_email"):
            if len(str(data.get(f) or "")) > 200:
                return jsonify({"error": f"Field {f} terlalu panjang (maks 200)."}), 400
        if len(str(data.get("urgensi") or "")) > 50:
            return jsonify({"error": "Urgensi terlalu panjang."}), 400
        if len(str(data.get("catatan") or "")) > 2000:
            return jsonify({"error": "Catatan terlalu panjang (maks 2000)."}), 400
        try:
            n_temuan = int(data["n_temuan"])
            total_rp = int(data["total_rp"])
            lat = float(data.get("lat") or 0) or None
            lon = float(data.get("lon") or 0) or None
        except (TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400
        if not 0 <= n_temuan <= 10000:
            return jsonify({"error": "n_temuan di luar wajar (0-10000)."}), 400
        if not 0 <= total_rp <= 10**15:
            return jsonify({"error": "total_rp di luar wajar."}), 400
        if lat is not None and not -90 <= lat <= 90:
            return jsonify({"error": "Latitude di luar rentang."}), 400
        if lon is not None and not -180 <= lon <= 180:
            return jsonify({"error": "Longitude di luar rentang."}), 400
        try:
            did = simpan_disposisi(
                bap_id=int(data["bap_id"]),
                bap_nomor=data["bap_nomor"],
                lokasi=data.get("lokasi"),
                lat=lat, lon=lon,
                n_temuan=n_temuan,
                total_rp=total_rp,
                worst=data.get("worst", "-"),
                instansi_id=int(data.get("instansi_id") or 0) or None,
                instansi_nama=data.get("instansi_nama"),
                instansi_daerah=data.get("instansi_daerah"),
                instansi_email=data.get("instansi_email"),
                urgensi=data.get("urgensi", "Rutin"),
                catatan=data.get("catatan", "-")
            )
            return jsonify({"id": did, "ok": True})
        except (TypeError, ValueError) as e:
            return jsonify({"error": str(e)}), 400

    # ---- Guard wewenang daerah: admin '-' = superadmin (boleh semua);
    # admin berdaerah hanya boleh memutasi disposisi daerahnya sendiri.
    def _wewenang_ok(item):
        d = session.get("admin_daerah")
        if not d or d == "-":
            return True
        return (item or {}).get("instansi_daerah") == d

    def _dashboard_ok(nama_daerah):
        """P2: admin berdaerah hanya boleh buka dashboard daerahnya sendiri."""
        d = session.get("admin_daerah")
        if not d or d == "-":
            return True
        return d == nama_daerah

    @app.put("/api/disposisi/<int:did>")
    @login_wajib
    def api_disposisi_update(did):
        data = request.get_json(force=True, silent=True) or {}
        item = detail_disposisi(did)
        if not item:
            return jsonify({"error": "Disposisi tidak ditemukan."}), 404
        if not _wewenang_ok(item):
            return jsonify({"error": "Disposisi ini di luar wewenang daerah Anda."}), 403
        status_baru = data.get("status")
        if status_baru not in ("Terkirim", "Diproses", "Selesai", "Ditolak"):
            return jsonify({"error": "Status tidak valid."}), 400
        catatan = data.get("catatan")
        pj = (data.get("penanggung_jawab") or "").strip() or None
        if update_status_disposisi(did, status_baru, catatan, pj):
            return jsonify({"ok": True})
        return jsonify({"error": "Gagal update status."}), 400

    @app.post("/api/disposisi/<int:did>/foto")
    @login_wajib
    def api_disposisi_foto(did):
        """Upload foto sesudah penanganan (maks 5MB, jpg/png).

        Hardening B5: ekstensi saja tidak cukup — validasi magic bytes,
        verifikasi via PIL, lalu re-encode ke JPEG (menanggalkan payload
        tersembunyi). Nama file deterministik per disposisi agar tidak
        menimpa disposisi lain dengan bap_id sama.
        """
        import io
        d = detail_disposisi(did)
        if not d:
            return jsonify({"error": "Disposisi tidak ditemukan."}), 404
        if not _wewenang_ok(d):
            return jsonify({"error": "Disposisi ini di luar wewenang daerah Anda."}), 403
        f = request.files.get("foto")
        if not f or not f.filename:
            return jsonify({"error": "File foto wajib diisi."}), 400
        ext = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
        if ext not in ("jpg", "jpeg", "png"):
            return jsonify({"error": "Format harus JPG/PNG."}), 400
        data = f.read(5 * 1024 * 1024 + 1)
        if len(data) > 5 * 1024 * 1024:
            return jsonify({"error": "Ukuran maks 5MB."}), 400
        if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
            return jsonify({"error": "Berkas bukan gambar JPG/PNG yang valid."}), 400
        try:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                im.verify()
            with Image.open(io.BytesIO(data)) as im:
                rgb = im.convert("RGB")
                if max(rgb.size) > 3000:
                    rgb.thumbnail((3000, 3000))
                buf = io.BytesIO()
                rgb.save(buf, format="JPEG", quality=90)
                bersih = buf.getvalue()
        except Exception:
            return jsonify({"error": "Berkas bukan gambar JPG/PNG yang valid."}), 400
        from pathlib import Path
        hasil_dir = Path(current_app.config["DB_PATH"]).parent / "hasil"
        hasil_dir.mkdir(parents=True, exist_ok=True)
        try:
            bap_id = int(d["bap_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "Data disposisi rusak (bap_id)."}), 500
        nama_file = f"{bap_id}_sesudah_{did}.jpg"
        (hasil_dir / nama_file).write_bytes(bersih)
        # Bersihkan nama lama yang predictable bila yatim (tidak dipakai disposisi lain)
        lama = hasil_dir / f"{bap_id}_sesudah.jpg"
        if lama.name != nama_file and lama.exists():
            try:
                from database import get_db as _get_db
                db_cek = _get_db()
                dipakai = db_cek.execute(
                    "SELECT COUNT(*) FROM disposisi WHERE foto_sesudah = ? AND id != ?",
                    (lama.name, did)).fetchone()[0]
                if not dipakai:
                    lama.unlink(missing_ok=True)
            except Exception:
                app.logger.warning("gagal bersihkan foto lama %s", lama.name)
        from database import get_db
        db = get_db()
        db.execute("UPDATE disposisi SET foto_sesudah = ? WHERE id = ?",
                   (nama_file, did))
        db.commit()
        return jsonify({"ok": True, "foto": nama_file})

    @app.delete("/api/disposisi/<int:did>")
    @login_wajib
    def api_disposisi_hapus(did):
        item = detail_disposisi(did)
        if not item:
            return jsonify({"error": "Disposisi tidak ditemukan."}), 404
        if not _wewenang_ok(item):
            return jsonify({"error": "Disposisi ini di luar wewenang daerah Anda."}), 403
        if not hapus_disposisi(did):
            return jsonify({"error": "Disposisi tidak ditemukan."}), 404
        return jsonify({"ok": True})

    # ---- Dashboard Pemerintah (PUPR) ----
    # (SLUG_DAERAH & normalisasi_daerah kini di module level, lihat atas)

    @app.route("/pupr-<daerah>/dashboard", defaults={"sub": None})
    @app.route("/pupr-<daerah>/dashboard/<path:sub>")
    @login_wajib
    def dashboard_handler(daerah, sub):
        """Handler untuk semua route /pupr-{daerah}/dashboard[/subroute]"""
        if daerah not in SLUG_DAERAH:
            return render_template("dashboard/404.html", daerah=daerah,
                                   nama_daerah=daerah), 404
        nama = SLUG_DAERAH[daerah]
        if not _dashboard_ok(nama):
            return render_template("dashboard/404.html", daerah=daerah,
                                   nama_daerah=nama), 403
        
        # Parse subroute
        subroute = sub.split("/")[0] if sub else None
        did = None
        if sub and len(sub.split("/")) > 1 and sub.split("/")[1].isdigit():
            did = int(sub.split("/")[1])
        
        if subroute is None:
            # Dashboard utama
            stats = statistik_disposisi(nama, exact=True)
            return render_template("dashboard/index.html", active="dashboard", daerah=daerah, nama_daerah=nama, stats=stats)
        elif subroute == "instansi":
            # Manajemen instansi (CRUD via API + halaman ini)
            return render_template("dashboard/instansi.html", active="instansi", daerah=daerah, nama_daerah=nama,
                                   superadmin=(session.get("admin_daerah") == "-"))
        elif subroute == "disposisi":
            if did:
                # Detail disposisi
                item = detail_disposisi(did)
                if not item:
                    return render_template("dashboard/404.html", daerah=daerah, nama_daerah=nama), 404
                if not _wewenang_ok(item) or item.get("instansi_daerah") != nama:
                    return render_template("dashboard/404.html", daerah=daerah, nama_daerah=nama), 403
                sesi_data = detail_sesi(item["bap_id"])
                image_b64 = None
                sesudah_b64 = None
                if sesi_data:
                    # Load gambar dari file jika ada
                    from pathlib import Path
                    import base64
                    hasil_dir = Path(current_app.config["DB_PATH"]).parent / "hasil"
                    img_path = hasil_dir / f"{item['bap_id']}.jpg"
                    if img_path.exists():
                        image_b64 = base64.b64encode(img_path.read_bytes()).decode()
                    if item.get("foto_sesudah"):
                        sesudah_path = hasil_dir / item["foto_sesudah"]
                        if sesudah_path.exists():
                            sesudah_b64 = base64.b64encode(sesudah_path.read_bytes()).decode()
                return render_template("dashboard/disposisi_detail.html", active="disposisi", daerah=daerah, nama_daerah=nama, item=item, sesi=sesi_data["sesi"] if sesi_data else None, rows=sesi_data.get("temuan", []) if sesi_data else [], image_b64=image_b64, sesudah_b64=sesudah_b64, catatan_list=riwayat_catatan(did))
            else:
                # Daftar disposisi
                items = daftar_disposisi(daerah=nama, limit=200, exact=True)
                return render_template("dashboard/disposisi.html", active="disposisi", daerah=daerah, nama_daerah=nama, items=items)
        else:
            return render_template("dashboard/404.html", daerah=daerah, nama_daerah=nama), 404

    return app


app = create_app()

def _preload_model_di_background():
    """Preload model di thread terpisah agar deteksi pertama tidak lambat."""
    import threading
    def _load():
        try:
            from deteksi import get_model, nama_model
            print("[preload] Memuat model gambar...")
            get_model(kunci="model_gambar")
            print(f"[preload] Model gambar siap: {nama_model(kunci='model_gambar')}")
            print("[preload] Memuat model live...")
            get_model(kunci="model_live")
            print(f"[preload] Model live siap: {nama_model(kunci='model_live')}")
        except Exception as e:
            print(f"[preload] Gagal preload model: {e}")
    t = threading.Thread(target=_load, daemon=True)
    t.start()

if __name__ == "__main__":
    _debug = os.environ.get("JP_DEBUG", "0") in ("1", "true", "True", "yes")
    if not _debug:
        _preload_model_di_background()
    app.run(host="127.0.0.1", port=5000, debug=_debug)
