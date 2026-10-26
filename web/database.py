"""Riwayat SQLite: sesi analisis + temuan per titik + thumbnail.

DB: web/instance/riwayat.db (boleh dioverride via app.config["DB_PATH"], mis. untuk tes).
Thumbnail: <instance>/hasil/<id>.jpg. PDF tidak disimpan — selalu generate ulang.
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

# Formula skor prioritas (Ringan 33 / Sedang 67 / Berat 100) dipakai bersama
# dengan app/prioritas.py supaya tidak ada dua sumber kebenaran.
_APP_DIR = Path(__file__).resolve().parent.parent / "app"
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))
from prioritas import bobot as _bobot_severity  # noqa: E402
from sdi import agregasi_segmen as _agregasi_sdi, hitung_sdi as _hitung_sdi  # noqa: E402

SKEMA = """
CREATE TABLE IF NOT EXISTS admin (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  daerah TEXT NOT NULL DEFAULT '-',
  sandi_diatur INTEGER NOT NULL DEFAULT 0,
  dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS sesi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  waktu TEXT NOT NULL,
  sumber TEXT NOT NULL,
  lokasi TEXT NOT NULL DEFAULT '-',
  lat REAL, lon REAL,
  model TEXT NOT NULL DEFAULT '-',
  n_temuan INTEGER NOT NULL,
  skor_prioritas INTEGER NOT NULL,
  worst TEXT NOT NULL DEFAULT '-',
  client_ref TEXT,
  segmen_id INTEGER REFERENCES segmen(id)
);
CREATE TABLE IF NOT EXISTS segmen (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  jalan TEXT NOT NULL DEFAULT '-',
  panjang_m REAL NOT NULL DEFAULT 100,
  lebar_m REAL NOT NULL DEFAULT 6,
  sdi_manual REAL,
  catatan TEXT NOT NULL DEFAULT '',
  dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE TABLE IF NOT EXISTS temuan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sesi_id INTEGER NOT NULL REFERENCES sesi(id) ON DELETE CASCADE,
  idx INTEGER NOT NULL,
  track_id INTEGER,
  kelas TEXT NOT NULL,
  dasar TEXT NOT NULL DEFAULT '-',
  severity TEXT NOT NULL,
  bahan TEXT NOT NULL DEFAULT '-',
  luas_m2 REAL NOT NULL DEFAULT 0,
  volume_m3 REAL NOT NULL DEFAULT 0,
  skor_prioritas INTEGER NOT NULL,
  total_str TEXT NOT NULL DEFAULT '-',
  conf REAL,
  panjang_cm REAL,
  lebar_cm REAL
);
CREATE INDEX IF NOT EXISTS idx_temuan_sesi ON temuan(sesi_id);
-- idx_sesi_segmen dibuat di migrasi_segmen_v4 (kolom segmen_id belum ada
-- saat SKEMA dieksekusi pada database lama).
"""


URUT_SEV = {"Ringan": 0, "Sedang": 1, "Berat": 2}

# Versi skema DB. Naikkan tiap kali menambah migrasi baru.
# Dipakai (via PRAGMA user_version) agar skema + migrasi berat hanya dijalankan
# SEKALI per database, bukan pada setiap koneksi/request.
SKEMA_VERSI = 4


def _paths():
    db = Path(current_app.config["DB_PATH"])
    db.parent.mkdir(parents=True, exist_ok=True)
    hasil = db.parent / "hasil"
    hasil.mkdir(exist_ok=True)
    return db, hasil


def _siapkan(db):
    """Buat skema + jalankan migrasi SEKALI per database (dijaga user_version).

    Sebelumnya skema + `migrasi_prioritas_v2` (yang menulis ulang kolom skor
    SELURUH tabel temuan + sesi) dijalankan pada SETIAP koneksi/request. Kini
    blok berat itu hanya berjalan saat database masih di bawah SKEMA_VERSI.

    Aman untuk DB baru (user_version = 0) dan untuk DB lama: migrasi bersifat
    idempoten, jadi satu kali jalan tetap menghasilkan skema/nilai yang benar.
    """
    if db.execute("PRAGMA user_version").fetchone()[0] >= SKEMA_VERSI:
        return
    db.executescript(SKEMA)
    migrasi_prioritas_v1(db)   # rename total_rp -> skor_prioritas (bila ada)
    migrasi_admin_v2()         # kolom admin.sandi_diatur
    migrasi_sesi_v2()          # kolom sesi.client_ref + indeks unik
    migrasi_prioritas_v2(db)   # hitung ulang skor dari severity (berat)
    migrasi_segmen_v4(db)      # tabel segmen + sesi.segmen_id + dimensi temuan
    db.execute("PRAGMA user_version = %d" % SKEMA_VERSI)
    db.commit()


def get_db():
    if "db" not in g:
        db_path, _ = _paths()
        g.db = sqlite3.connect(str(db_path))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        _siapkan(g.db)
    return g.db


def tutup_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---- Autentikasi admin (satu peran) ----
# Kredensial demo (fallback bila belum diganti). Sandi bisa dioverride via env
# JP_DEMO_PASS; JANGAN pakai nilai default ini di deployment/sidang nyata.
AKUN_DEMO = ("admin", os.environ.get("JP_DEMO_PASS", "jalanpantau2026"), "-")


def migrasi_admin_v2():
    """Tambah kolom sandi_diatur (penanda sandi sudah diatur superadmin). Aman diulang."""
    db = get_db()
    cols = {r[1] for r in db.execute("PRAGMA table_info(admin)").fetchall()}
    if "sandi_diatur" not in cols:
        db.execute("ALTER TABLE admin ADD COLUMN sandi_diatur INTEGER NOT NULL DEFAULT 0")
    db.commit()


def init_admin():
    """Buat tabel + akun admin demo bila belum ada admin sama sekali."""
    migrasi_admin_v2()
    db = get_db()
    if db.execute("SELECT COUNT(*) c FROM admin").fetchone()["c"] == 0:
        db.execute(
            "INSERT INTO admin (username, password_hash, daerah, sandi_diatur) VALUES (?, ?, ?, 1)",
            (AKUN_DEMO[0], generate_password_hash(AKUN_DEMO[1]), AKUN_DEMO[2]))
        db.commit()
        if AKUN_DEMO[1] == "jalanpantau2026":
            print("PERINGATAN: akun admin memakai sandi demo default. Set env "
                  "JP_DEMO_PASS sebelum "
                  "dipakai di luar demo.")


def cek_login(username, password):
    """Kembalikan dict admin bila kredensial valid, selain itu None."""
    db = get_db()
    row = db.execute("SELECT * FROM admin WHERE username = ?", (username,)).fetchone()
    if row is None:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return dict(row)


def migrasi_sesi_v2():
    """Tambah kolom client_ref (idempotensi simpan) + indeks unik parsial.
    Aman diulang. Indeks parsial mengizinkan banyak baris NULL (data lama)."""
    db = get_db()
    cols = {r[1] for r in db.execute("PRAGMA table_info(sesi)").fetchall()}
    if "client_ref" not in cols:
        db.execute("ALTER TABLE sesi ADD COLUMN client_ref TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_sesi_client_ref "
               "ON sesi(client_ref) WHERE client_ref IS NOT NULL")
    db.commit()


def migrasi_prioritas_v1(db):
    """Rename kolom total_rp -> skor_prioritas (sesi, temuan).

    Penggantian estimasi biaya -> indeks prioritas (2026-10-16).
    Aman diulang; RENAME COLUMN butuh SQLite >= 3.25.
    """
    for tabel in ("sesi", "temuan"):
        cols = {r[1] for r in db.execute(f"PRAGMA table_info({tabel})").fetchall()}
        if "total_rp" in cols and "skor_prioritas" not in cols:
            db.execute(f"ALTER TABLE {tabel} RENAME COLUMN total_rp TO skor_prioritas")
    db.commit()


def migrasi_prioritas_v2(db):
    """Hitung ulang skor_prioritas dari severity (formula M8, 2026-10-16).

    Formula lama memakai luas; formula baru hanya severity (33/67/100).
    Idempoten dan aman dijalankan tiap startup: nilai baru maupun lama
    selalu menghasilkan skor yang benar.
    """
    db.execute(
        "UPDATE temuan SET skor_prioritas = CASE "
        "WHEN LOWER(severity) = 'berat' THEN 100 "
        "WHEN LOWER(severity) = 'sedang' THEN 67 "
        "ELSE 33 END"
    )
    db.execute(
        "UPDATE sesi SET skor_prioritas = COALESCE("
        "(SELECT SUM(skor_prioritas) FROM temuan WHERE temuan.sesi_id = sesi.id), 0)"
    )
    db.commit()


def migrasi_segmen_v4(db):
    """Segmen jalan + relasi sesi->segmen + dimensi per temuan (2026-10-17).

    Instrumen prioritas baru: SDI-visual per segmen (app/sdi.py), menggantikan
    skor severity 33/67/100 sebagai acuan prioritas. Kolom skor_prioritas
    dipertahankan apa adanya untuk kompatibilitas data lama.
    Idempoten; aman diulang.
    """
    db.execute(
        "CREATE TABLE IF NOT EXISTS segmen ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " nama TEXT NOT NULL,"
        " jalan TEXT NOT NULL DEFAULT '-',"
        " panjang_m REAL NOT NULL DEFAULT 100,"
        " lebar_m REAL NOT NULL DEFAULT 6,"
        " sdi_manual REAL,"
        " catatan TEXT NOT NULL DEFAULT '',"
        " dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime')))")
    for tabel, kolom, ddl in (
        ("sesi", "segmen_id", "INTEGER REFERENCES segmen(id)"),
        ("temuan", "panjang_cm", "REAL"),
        ("temuan", "lebar_cm", "REAL"),
    ):
        cols = {r[1] for r in db.execute(f"PRAGMA table_info({tabel})").fetchall()}
        if kolom not in cols:
            db.execute(f"ALTER TABLE {tabel} ADD COLUMN {kolom} {ddl}")
    db.execute("CREATE INDEX IF NOT EXISTS idx_sesi_segmen ON sesi(segmen_id)")
    db.commit()


# ---- Segmen jalan + SDI-visual ----
# Segmen = ruas 100 m (baku) tempat temuan-temuan dikelompokkan untuk
# dihitung SDI-visual-nya (app/sdi.py). Satu sesi foto dapat dimasukkan
# ke satu segmen; SDI dihitung dari gabungan seluruh temuan anggotanya.

def _angka_segmen(nilai, bawaan):
    """Coerce ke float >= 0; junk/None -> bawaan."""
    try:
        x = float(nilai)
    except (TypeError, ValueError):
        return float(bawaan)
    if x != x or x in (float("inf"), float("-inf")):
        return float(bawaan)
    return max(0.0, x)


def tambah_segmen(nama, jalan="-", panjang_m=100, lebar_m=6, sdi_manual=None,
                  catatan=""):
    """Buat segmen baru. Kembalikan id."""
    db = get_db()
    nama = str(nama or "").strip()[:120] or "Segmen tanpa nama"
    if sdi_manual in (None, ""):
        sdi_manual = None
    else:
        try:
            sdi_manual = float(sdi_manual)
        except (TypeError, ValueError):
            raise ValueError("SDI manual tidak valid.")
    cur = db.execute(
        "INSERT INTO segmen (nama, jalan, panjang_m, lebar_m, sdi_manual,"
        " catatan, dibuat) VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))",
        (nama, str(jalan or "-")[:160], _angka_segmen(panjang_m, 100) or 100,
         _angka_segmen(lebar_m, 6) or 6, sdi_manual, str(catatan or "")[:500]))
    db.commit()
    return cur.lastrowid


def daftar_segmen():
    """Semua segmen + ringkasan SDI-visual tiap segmen."""
    db = get_db()
    rows = db.execute("SELECT * FROM segmen ORDER BY id DESC").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["n_sesi"] = db.execute(
            "SELECT COUNT(*) c FROM sesi WHERE segmen_id = ?",
            (d["id"],)).fetchone()["c"]
        d["sdi"] = sdi_segmen(d["id"])
        out.append(d)
    return out


def detail_segmen(sid):
    """Segmen + SDI-visual + daftar sesi anggota."""
    db = get_db()
    s = db.execute("SELECT * FROM segmen WHERE id = ?", (sid,)).fetchone()
    if s is None:
        return None
    d = dict(s)
    anggota = db.execute(
        "SELECT id, waktu, sumber, lokasi, lat, lon, n_temuan, worst"
        " FROM sesi WHERE segmen_id = ? ORDER BY id", (sid,)).fetchall()
    d["anggota"] = [dict(r) for r in anggota]
    d["sdi"] = sdi_segmen(sid)
    return d


def ubah_segmen(sid, nama=None, jalan=None, panjang_m=None, lebar_m=None,
                sdi_manual="__kosong__", catatan=None):
    """Ubah field segmen. sdi_manual=None menghapus nilai manual."""
    db = get_db()
    bagian, arg = [], []
    if nama is not None:
        bagian.append("nama = ?")
        arg.append(str(nama).strip()[:120] or "Segmen tanpa nama")
    if jalan is not None:
        bagian.append("jalan = ?")
        arg.append(str(jalan or "-")[:160])
    if panjang_m is not None:
        bagian.append("panjang_m = ?")
        arg.append(_angka_segmen(panjang_m, 100) or 100)
    if lebar_m is not None:
        bagian.append("lebar_m = ?")
        arg.append(_angka_segmen(lebar_m, 6) or 6)
    if sdi_manual != "__kosong__":
        if sdi_manual in (None, ""):
            bagian.append("sdi_manual = NULL")
        else:
            try:
                bagian.append("sdi_manual = ?")
                arg.append(float(sdi_manual))
            except (TypeError, ValueError):
                raise ValueError("SDI manual tidak valid.")
    if catatan is not None:
        bagian.append("catatan = ?")
        arg.append(str(catatan or "")[:500])
    if not bagian:
        return False
    arg.append(sid)
    cur = db.execute(f"UPDATE segmen SET {', '.join(bagian)} WHERE id = ?", arg)
    db.commit()
    return cur.rowcount > 0


def hapus_segmen(sid):
    """Hapus segmen; sesi anggotanya menjadi tak ber-segmen (tidak ikut terhapus)."""
    db = get_db()
    db.execute("UPDATE sesi SET segmen_id = NULL WHERE segmen_id = ?", (sid,))
    cur = db.execute("DELETE FROM segmen WHERE id = ?", (sid,))
    db.commit()
    return cur.rowcount > 0


def tetapkan_segmen_sesi(sesi_id, segmen_id):
    """Masukkan/keluarkan sesi dari segmen (segmen_id=None = keluarkan)."""
    db = get_db()
    if segmen_id is not None:
        ada = db.execute("SELECT id FROM segmen WHERE id = ?",
                         (segmen_id,)).fetchone()
        if ada is None:
            raise ValueError("Segmen tidak ditemukan.")
    cur = db.execute("UPDATE sesi SET segmen_id = ? WHERE id = ?",
                     (segmen_id, sesi_id))
    db.commit()
    return cur.rowcount > 0


def sesi_tanpa_segmen(limit=200):
    """Sesi yang belum dimasukkan ke segmen mana pun (untuk UI penugasan)."""
    db = get_db()
    cur = db.execute(
        "SELECT id, waktu, sumber, lokasi, lat, lon, n_temuan, worst"
        " FROM sesi WHERE segmen_id IS NULL ORDER BY id DESC LIMIT ?",
        (int(limit),))
    return [dict(r) for r in cur.fetchall()]


def sdi_segmen(segmen_id):
    """SDI-visual satu segmen dari gabungan temuan seluruh sesi anggotanya.

    Mengembalikan dict app/sdi.py::hitung_sdi() + info cakupan data.
    None bila segmen tidak ada.
    """
    db = get_db()
    s = db.execute("SELECT panjang_m, lebar_m FROM segmen WHERE id = ?",
                   (segmen_id,)).fetchone()
    if s is None:
        return None
    rows = db.execute(
        "SELECT t.kelas, t.panjang_cm, t.lebar_cm FROM temuan t"
        " JOIN sesi s ON s.id = t.sesi_id WHERE s.segmen_id = ?",
        (segmen_id,)).fetchall()
    det, tanpa_dimensi = [], 0
    for r in rows:
        if r["panjang_cm"] is None or r["lebar_cm"] is None:
            tanpa_dimensi += 1
            continue
        det.append({"kelas": r["kelas"], "panjang_cm": r["panjang_cm"],
                    "lebar_cm": r["lebar_cm"]})
    komp = _agregasi_sdi(det, s["panjang_m"], s["lebar_m"])
    hasil = _hitung_sdi(komp)
    hasil["n_temuan_total"] = len(rows)
    hasil["n_tanpa_dimensi"] = tanpa_dimensi
    hasil["komp"] = komp  # data pengukuran agregat (untuk penjelasan visual)
    return hasil


def sesi_by_client_ref(ref):
    """Id sesi untuk client_ref tertentu (idempotensi). None bila belum ada."""
    if not ref:
        return None
    row = get_db().execute(
        "SELECT id FROM sesi WHERE client_ref = ?", (ref,)).fetchone()
    return row["id"] if row else None


def sesi_duplikat_coord(lat, lon, sumber=None, dalam_menit=10):
    """Heuristik anti-duplikat titik: id sesi dengan koordinat sama (dibulatkan
    4 desimal ≈ 11 m) yang tersimpan dalam `dalam_menit` terakhir. None bila tak ada.

    Catatan: ini heuristik, bukan larangan mutlak — pemanggil bisa memaksa simpan
    lewat flag `izinkan_duplikat` (mis. inspeksi ulang yang memang disengaja).
    """
    if lat is None or lon is None:
        return None
    batas = (datetime.now() - timedelta(minutes=int(dalam_menit))).isoformat(timespec="seconds")
    sql = ("SELECT id FROM sesi WHERE lat IS NOT NULL AND lon IS NOT NULL "
           "AND ROUND(lat, 4) = ROUND(?, 4) AND ROUND(lon, 4) = ROUND(?, 4) "
           "AND waktu >= ?")
    arg = [lat, lon, batas]
    if sumber:
        sql += " AND sumber = ?"
        arg.append(sumber)
    sql += " ORDER BY id DESC LIMIT 1"
    row = get_db().execute(sql, arg).fetchone()
    return row["id"] if row else None


def _angka(nilai, batas, bawaan=0.0):
    """Coerce ke float dan jepit ke [0, batas]. Tahan NaN/inf/string aneh.

    Dipakai untuk kolom numerik yang berasal dari client: endpoint simpan
    menerima JSON bebas, jadi nilai harus diperlakukan sebagai tidak dipercaya.
    """
    try:
        x = float(nilai)
    except (TypeError, ValueError):
        return float(bawaan)
    if x != x or x in (float("inf"), float("-inf")):
        return float(bawaan)
    return max(0.0, min(x, float(batas)))


def simpan_sesi(sumber, lokasi, model, rows, total, lat=None, lon=None, image_bytes=None,
                client_ref=None, segmen_id=None):
    """rows = list dict dari /api/detect atau snapshot. Kembalikan id sesi.

    `client_ref` (bila ada) dipakai sebagai kunci idempotensi: simpan ulang dengan
    ref yang sama tidak membuat baris baru (dijamin indeks unik parsial).

    CATATAN PENTING: parameter `total` TIDAK dipercaya. Nilai sesi dihitung
    ulang dari jumlah `temuan[].skor_prioritas` supaya kolom sesi.skor_prioritas
    selalu sama dengan jumlah baris temuan. Sebelumnya angka datang dari client,
    sehingga (a) bisa disuntik nilai berapa pun, dan (b) bisa tidak cocok
    dengan rincian temuan di bawahnya.

    Kolom skor_prioritas dipertahankan sebagai data legacy (kompatibilitas);
    instrumen prioritas kini SDI-visual per segmen (app/sdi.py). Dimensi
    panjang_cm/lebar_cm disimpan untuk agregasi SDI.
    """
    db = get_db()
    if not isinstance(rows, (list, tuple)):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        raise ValueError("Tidak ada temuan untuk disimpan.")
    if segmen_id is not None:
        ada = db.execute("SELECT id FROM segmen WHERE id = ?",
                         (segmen_id,)).fetchone()
        if ada is None:
            raise ValueError("Segmen tidak ditemukan.")
    # Batas wajar: luas dan volume yang tidak mungkin melebihi ini.
    B_M2, B_M3, B_CONF = 10 ** 5, 10 ** 4, 1.0
    temuan = []
    for r in rows:
        sev = str(r.get("severity", "-")).strip().capitalize()[:40] or "-"
        # Skor TIDAK dipercaya dari klien: dihitung ulang dari severity
        # (Ringan 33 / Sedang 67 / Berat 100) memakai bobot app/prioritas.py,
        # supaya tiap baris selalu konsisten dengan rumus dan tidak bisa disuntik.
        # LEGACY: kolom dipertahankan untuk data lama; tidak lagi ditampilkan
        # sebagai instrumen prioritas (digantikan SDI per segmen).
        skor_server = int(max(0, min(100, round(100 * _bobot_severity(sev) / 3))))
        temuan.append({
            "kelas": str(r.get("kelas", "-"))[:120],
            "dasar": str(r.get("dasar", "-"))[:200],
            "severity": sev,
            "bahan": str(r.get("bahan", "-"))[:120],
            "luas_m2": _angka(r.get("luas_m2"), B_M2),
            "volume_m3": _angka(r.get("volume_m3"), B_M3),
            "skor_prioritas": skor_server,
            "total_str": str(skor_server)[:60],
            "conf": (_angka(r.get("conf"), B_CONF, bawaan=-1.0)
                     if r.get("conf") is not None else None),
            "track_id": (int(_angka(r.get("track_id"), 10 ** 6))
                         if r.get("track_id") is not None else None),
            "panjang_cm": _angka(r.get("panjang_cm"), 10 ** 4),
            "lebar_cm": _angka(r.get("lebar_cm"), 10 ** 4),
        })
    total = sum(t["skor_prioritas"] for t in temuan)
    sev = [t["severity"] for t in temuan]
    worst = max(sev, key=lambda s: URUT_SEV.get(s, -1))
    cur = db.execute(
        "INSERT INTO sesi (waktu, sumber, lokasi, lat, lon, model, n_temuan, skor_prioritas, worst, client_ref, segmen_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), sumber, lokasi or "-",
         lat, lon, model, len(temuan), int(total), worst, client_ref, segmen_id))
    sid = cur.lastrowid
    for i, t in enumerate(temuan, 1):
        db.execute(
            "INSERT INTO temuan (sesi_id, idx, track_id, kelas, dasar, severity, bahan,"
            " luas_m2, volume_m3, skor_prioritas, total_str, conf, panjang_cm, lebar_cm)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, i, t["track_id"], t["kelas"], t["dasar"], t["severity"], t["bahan"],
             t["luas_m2"], t["volume_m3"], t["skor_prioritas"], t["total_str"], t["conf"],
             t["panjang_cm"], t["lebar_cm"]))
    if image_bytes:
        try:
            import io
            from PIL import Image
            _, hasil = _paths()
            # Simpan gambar penuh untuk unduhan/arsip
            (hasil / f"{sid}.jpg").write_bytes(image_bytes)
            # Turunan tampil: 1280 untuk modal/peta, 300 untuk daftar.
            with Image.open(io.BytesIO(image_bytes)) as im:
                for suffix, sisi, kualitas in (("_layar", 1280, 82),
                                                ("_thumb", 300, 75)):
                    kecil = im.copy()
                    kecil.thumbnail((sisi, sisi))
                    buf = io.BytesIO()
                    kecil.save(buf, format="JPEG", quality=kualitas)
                    (hasil / f"{sid}{suffix}.jpg").write_bytes(buf.getvalue())
        except Exception:
            current_app.logger.exception("gagal simpan gambar/thumbnail")
    db.commit()
    return sid


def _klausa_sesi(dari=None, sampai=None, severity=None, q=None):
    klausa, arg = [], []
    if dari:
        klausa.append("date(waktu) >= date(?)")
        arg.append(dari)
    if sampai:
        klausa.append("date(waktu) <= date(?)")
        arg.append(sampai)
    if severity in URUT_SEV:
        klausa.append("worst = ?")
        arg.append(severity)
    if q:
        klausa.append("(lokasi LIKE ? OR sumber LIKE ?)")
        arg += [f"%{q}%", f"%{q}%"]
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    return where, arg


def daftar_sesi(dari=None, sampai=None, severity=None, q=None, limit=200, offset=0):
    db = get_db()
    where, arg = _klausa_sesi(dari, sampai, severity, q)
    # Kolom di klausa WHERE (waktu, sumber, lokasi, worst) hanya ada di tabel
    # sesi sehingga tidak ambigu meski JOIN dengan segmen.
    cur = db.execute(
        "SELECT sesi.id, sesi.waktu, sesi.sumber, sesi.lokasi, sesi.lat, sesi.lon,"
        " sesi.model, sesi.n_temuan, sesi.skor_prioritas, sesi.worst,"
        " sesi.segmen_id, segmen.nama AS segmen_nama"
        " FROM sesi LEFT JOIN segmen ON segmen.id = sesi.segmen_id"
        f" {where} ORDER BY sesi.id DESC LIMIT ? OFFSET ?", (*arg, limit, offset))
    return [dict(r) for r in cur.fetchall()]


def hitung_sesi(dari=None, sampai=None, severity=None, q=None):
    """Total baris sesi untuk filter yang sama (pendamping paginasi)."""
    db = get_db()
    where, arg = _klausa_sesi(dari, sampai, severity, q)
    return db.execute(f"SELECT COUNT(*) FROM sesi {where}", arg).fetchone()[0]


def detail_sesi(sid):
    db = get_db()
    s = db.execute(
        "SELECT sesi.*, segmen.nama AS segmen_nama FROM sesi"
        " LEFT JOIN segmen ON segmen.id = sesi.segmen_id WHERE sesi.id = ?",
        (sid,)).fetchone()
    if s is None:
        return None
    rows = db.execute("SELECT * FROM temuan WHERE sesi_id = ? ORDER BY idx", (sid,)).fetchall()
    ada_gambar = (_paths()[1] / f"{sid}.jpg").exists()
    return {"sesi": dict(s), "temuan": [dict(r) for r in rows], "ada_gambar": ada_gambar}


def hapus_sesi(sid):
    db = get_db()
    cur = db.execute("DELETE FROM sesi WHERE id = ?", (sid,))
    db.commit()
    hasil = _paths()[1]
    # Hapus gambar PENUH dan semua turunannya. Sebelumnya hanya gambar penuh
    # yang dihapus sehingga thumbnail yatim menumpuk di disk (terverifikasi:
    # id 40-44 punya _thumb.jpg tapi tidak ada di tabel sesi).
    for suffix, label in ((".jpg", "gambar"), ("_layar.jpg", "gambar layar"),
                          ("_thumb.jpg", "thumbnail")):
        try:
            (hasil / f"{sid}{suffix}").unlink(missing_ok=True)
        except OSError as e:
            current_app.logger.warning("gagal hapus %s sesi %s: %s",
                                       label, sid, e)
    return cur.rowcount > 0


def titik_peta():
    db = get_db()
    cur = db.execute(
        "SELECT sesi.id, sesi.waktu, sesi.lokasi, sesi.lat, sesi.lon,"
        " sesi.n_temuan, sesi.skor_prioritas, sesi.worst,"
        " sesi.segmen_id, segmen.nama AS segmen_nama"
        " FROM sesi LEFT JOIN segmen ON segmen.id = sesi.segmen_id"
        " WHERE sesi.lat IS NOT NULL AND sesi.lon IS NOT NULL"
        " ORDER BY sesi.id DESC LIMIT 500")
    rows = [dict(r) for r in cur.fetchall()]
    hasil = _paths()[1]
    for r in rows:
        r["ada_gambar"] = (hasil / f"{r['id']}.jpg").exists()
    return rows


