"""Riwayat SQLite: sesi analisis + temuan per titik + thumbnail.

DB: web/instance/riwayat.db (boleh dioverride via app.config["DB_PATH"], mis. untuk tes).
Thumbnail: <instance>/hasil/<id>.jpg. PDF tidak disimpan — selalu generate ulang.
"""
import base64
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

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
  total_rp INTEGER NOT NULL,
  worst TEXT NOT NULL DEFAULT '-'
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
  total_rp INTEGER NOT NULL,
  total_str TEXT NOT NULL DEFAULT '-',
  conf REAL
);
CREATE INDEX IF NOT EXISTS idx_temuan_sesi ON temuan(sesi_id);

-- Tabel Instansi Pemerintah
CREATE TABLE IF NOT EXISTS instansi_pemerintah (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL,
  daerah TEXT NOT NULL,
  alamat TEXT NOT NULL DEFAULT '-',
  email TEXT NOT NULL DEFAULT '-',
  telepon TEXT NOT NULL DEFAULT '-',
  lat REAL,
  lon REAL,
  radius_km REAL DEFAULT 50,
  is_active INTEGER DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_instansi_daerah ON instansi_pemerintah(daerah);
CREATE INDEX IF NOT EXISTS idx_instansi_active ON instansi_pemerintah(is_active);

-- Tabel Disposisi (Laporan Terkirim ke Dashboard Pemerintah)
CREATE TABLE IF NOT EXISTS disposisi (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  waktu TEXT NOT NULL,
  bap_id INTEGER NOT NULL,
  bap_nomor TEXT NOT NULL,
  lokasi TEXT NOT NULL DEFAULT '-',
  lat REAL,
  lon REAL,
  n_temuan INTEGER NOT NULL,
  total_rp INTEGER NOT NULL,
  worst TEXT NOT NULL DEFAULT '-',
  instansi_id INTEGER,
  instansi_nama TEXT NOT NULL DEFAULT '-',
  instansi_daerah TEXT NOT NULL DEFAULT '-',
  instansi_email TEXT NOT NULL DEFAULT '-',
  urgensi TEXT NOT NULL DEFAULT 'Rutin',
  catatan TEXT DEFAULT '-',
  status TEXT NOT NULL DEFAULT 'Terkirim',
  pembaruan_terakhir TEXT
);
CREATE INDEX IF NOT EXISTS idx_disposisi_waktu ON disposisi(waktu);
CREATE INDEX IF NOT EXISTS idx_disposisi_instansi ON disposisi(instansi_daerah);
CREATE INDEX IF NOT EXISTS idx_disposisi_status ON disposisi(status);
"""

# Data default instansi pemerintah
DATA_INSTANSI_DEFAULT = [
    # --- Kota/Kabupaten di Jawa Barat ---
    ("DSDABM Kota Bandung", "Bandung", "Jl. Cianjur No. 34, Kacapiring, Batununggal, Bandung", "kontak@binamarga.bandung.go.id", "(022) 7278819", -6.9175, 107.6191, 40),
    ("Dinas Bina Marga Kabupaten Bandung", "Kabupaten Bandung", "Jl. Raya Soreang No. 1, Soreang", "binamarga@bandab.go.id", "(022) 8771234", -7.0333, 107.5167, 50),
    ("Dinas Bina Marga Kabupaten Bandung Barat", "Kabupaten Bandung Barat", "Jl. Raya Padalarang No. 1, Padalarang", "binamarga@bandungbaratkab.go.id", "(022) 6801234", -6.8400, 107.4800, 50),
    ("Dinas Bina Marga Kota Bogor", "Bogor", "Jl. Raya Bogor No. 1, Kota Bogor", "binamarga@bogorkota.go.id", "(0251) 8321234", -6.5956, 106.7916, 40),
    ("Dinas Bina Marga Kabupaten Bogor", "Kabupaten Bogor", "Jl. Raya Cibinong No. 1, Cibinong", "binamarga@bogorkab.go.id", "(021) 8751234", -6.4800, 106.8300, 50),
    ("Dinas Bina Marga Kota Sukabumi", "Sukabumi", "Jl. Raya Sukabumi No. 1, Sukabumi", "binamarga@sukabumikota.go.id", "(0266) 212345", -6.9200, 106.9300, 35),
    ("Dinas Bina Marga Kabupaten Sukabumi", "Kabupaten Sukabumi", "Jl. Raya Cisaat No. 1, Sukabumi", "binamarga@sukabumikab.go.id", "(0266) 221234", -6.8700, 106.9800, 50),
    ("Dinas Bina Marga Kota Cianjur", "Cianjur", "Jl. Raya Cianjur No. 1, Cianjur", "binamarga@cianjurkota.go.id", "(0263) 212345", -6.8200, 107.1400, 35),
    ("Dinas Bina Marga Kabupaten Cianjur", "Kabupaten Cianjur", "Jl. Raya Cianjur No. 1, Cianjur", "binamarga@cianjurkab.go.id", "(0263) 221234", -6.8700, 107.1300, 50),
    ("Dinas Bina Marga Kota Garut", "Garut", "Jl. Raya Garut No. 1, Garut", "binamarga@garutkota.go.id", "(0262) 212345", -7.2200, 107.9100, 40),
    ("Dinas Bina Marga Kabupaten Garut", "Kabupaten Garut", "Jl. Raya Bayongbong No. 1, Garut", "binamarga@garutkab.go.id", "(0262) 221234", -7.2500, 107.9100, 55),
    ("Dinas Bina Marga Kota Tasikmalaya", "Tasikmalaya", "Jl. Raya Tasikmalaya No. 1, Tasikmalaya", "binamarga@tasikmalayakota.go.id", "(0265) 312345", -7.3500, 108.2200, 35),
    ("Dinas Bina Marga Kabupaten Tasikmalaya", "Kabupaten Tasikmalaya", "Jl. Raya Singaparna No. 1, Singaparna", "binamarga@tasikmalayakab.go.id", "(0265) 321234", -7.3500, 108.1100, 55),
    ("Dinas Bina Marga Kota Ciamis", "Ciamis", "Jl. Raya Ciamis No. 1, Ciamis", "binamarga@ciamiskota.go.id", "(0265) 712345", -7.3300, 108.3500, 30),
    ("Dinas Bina Marga Kabupaten Ciamis", "Kabupaten Ciamis", "Jl. Raya Ciamis No. 1, Ciamis", "binamarga@ciamiskab.go.id", "(0265) 721234", -7.3400, 108.3500, 50),
    ("Dinas Bina Marga Kota Kuningan", "Kuningan", "Jl. Raya Kuningan No. 1, Kuningan", "binamarga@uningankota.go.id", "(0232) 812345", -6.9800, 108.4800, 30),
    ("Dinas Bina Marga Kabupaten Kuningan", "Kabupaten Kuningan", "Jl. Raya Kuningan No. 1, Kuningan", "binamarga@uningankab.go.id", "(0232) 821234", -6.9900, 108.4800, 50),
    ("Dinas Bina Marga Kota Majalengka", "Majalengka", "Jl. Raya Majalengka No. 1, Majalengka", "binamarga@majalengkakota.go.id", "(0233) 212345", -6.8400, 108.2300, 30),
    ("Dinas Bina Marga Kabupaten Majalengka", "Kabupaten Majalengka", "Jl. Raya Majalengka No. 1, Majalengka", "binamarga@majalengkakab.go.id", "(0233) 221234", -6.8100, 108.2300, 45),
    ("Dinas Bina Marga Kota Sumedang", "Sumedang", "Jl. Raya Sumedang No. 1, Sumedang", "binamarga@sumedangkota.go.id", "(0261) 212345", -6.8600, 107.9200, 30),
    ("Dinas Bina Marga Kabupaten Sumedang", "Kabupaten Sumedang", "Jl. Raya Sumedang No. 1, Sumedang", "binamarga@sumedangkab.go.id", "(0261) 221234", -6.8300, 107.9800, 50),
    ("Dinas Bina Marga Kota Indramayu", "Indramayu", "Jl. Raya Indramayu No. 1, Indramayu", "binamarga@indramayukota.go.id", "(0234) 212345", -6.3300, 108.3200, 35),
    ("Dinas Bina Marga Kabupaten Indramayu", "Kabupaten Indramayu", "Jl. Raya Indramayu No. 1, Indramayu", "binamarga@indramayukab.go.id", "(0234) 221234", -6.3500, 108.3200, 55),
    ("Dinas Bina Marga Kota Subang", "Subang", "Jl. Raya Subang No. 1, Subang", "binamarga@subangkota.go.id", "(0260) 412345", -6.5700, 107.7600, 30),
    ("Dinas Bina Marga Kabupaten Subang", "Kabupaten Subang", "Jl. Raya Subang No. 1, Subang", "binamarga@subangkab.go.id", "(0260) 421234", -6.5500, 107.7600, 50),
    ("Dinas Bina Marga Kota Purwakarta", "Purwakarta", "Jl. Raya Purwakarta No. 1, Purwakarta", "binamarga@purwakartakota.go.id", "(0264) 212345", -6.5500, 107.4300, 30),
    ("Dinas Bina Marga Kabupaten Purwakarta", "Kabupaten Purwakarta", "Jl. Raya Purwakarta No. 1, Purwakarta", "binamarga@purwakartakab.go.id", "(0264) 221234", -6.5400, 107.4300, 45),
    ("Dinas Bina Marga Kota Karawang", "Karawang", "Jl. Raya Karawang No. 1, Karawang", "binamarga@karawangkota.go.id", "(0267) 412345", -6.3000, 107.3000, 35),
    ("Dinas Bina Marga Kabupaten Karawang", "Kabupaten Karawang", "Jl. Raya Karawang No. 1, Karawang", "binamarga@karawangkab.go.id", "(0267) 421234", -6.3200, 107.3000, 55),
    ("Dinas Bina Marga Kota Bekasi", "Bekasi", "Jl. Ir. H. Juanda No. 1, Bekasi", "binamarga@bekasikota.go.id", "(021) 8801234", -6.2333, 106.9833, 35),
    ("Dinas Bina Marga Kabupaten Bekasi", "Kabupaten Bekasi", "Jl. Raya Cibitung No. 1, Cibitung", "binamarga@bekasikab.go.id", "(021) 8812345", -6.2500, 107.0800, 50),
    ("Dinas Bina Marga Kota Cirebon", "Cirebon", "Jl. Raya Cirebon No. 1, Cirebon", "binamarga@cirebonkota.go.id", "(0231) 212345", -6.7300, 108.5500, 30),
    ("Dinas Bina Marga Kabupaten Cirebon", "Kabupaten Cirebon", "Jl. Raya Cirebon No. 1, Cirebon", "binamarga@cirebonkab.go.id", "(0231) 221234", -6.7500, 108.5500, 50),
    ("Dinas Bina Marga Kota Banjar", "Banjar", "Jl. Raya Banjar No. 1, Banjar", "banjar@binamarga.go.id", "(0265) 912345", -7.3700, 108.5300, 25),
    ("Dinas Bina Marga Kota Depok", "Depok", "Jl. Margonda Raya No. 1, Depok", "binamarga@depok.go.id", "(021) 7712345", -6.4000, 106.8186, 30),
    ("Dinas Bina Marga Kota Cimahi", "Cimahi", "Jl. Rd. Demang No. 1, Cimahi", "binamarga@cimahikota.go.id", "(022) 6612345", -6.8800, 107.5400, 25),
    ("Dinas Bina Marga Kabupaten Pangandaran", "Kabupaten Pangandaran", "Jl. Raya Parigi No. 1, Parigi", "binamarga@pangandarankab.go.id", "(0265) 621234", -7.6833, 108.4900, 45),
    # --- Luar Jawa Barat ---
    ("Dinas Bina Marga DKI Jakarta", "Jakarta", "Jl. Raya Bogor Km 28, Cimanggis, Jakarta Timur", "binamarga@jakarta.go.id", "(021) 8001234", -6.2088, 106.8456, 50),
    ("Dinas Bina Marga Kota Tangerang", "Tangerang", "Jl. Raya Serpong No. 1, Tangerang", "binamarga@tangerangkota.go.id", "(021) 5521234", -6.1700, 106.6400, 30),
    ("Dinas Bina Marga Kota Semarang", "Semarang", "Jl. Pemuda No. 145, Semarang", "binamarga@semarangkota.go.id", "(024) 3541234", -6.9667, 110.4167, 40),
    ("Dinas Bina Marga Kota Surabaya", "Surabaya", "Jl. Jimerto No. 1, Surabaya", "binamarga@surabayakota.go.id", "(031) 5341234", -7.2500, 112.7500, 45),
]

URUT_SEV = {"Ringan": 0, "Sedang": 1, "Berat": 2}


def _paths():
    db = Path(current_app.config["DB_PATH"])
    db.parent.mkdir(parents=True, exist_ok=True)
    hasil = db.parent / "hasil"
    hasil.mkdir(exist_ok=True)
    return db, hasil


def get_db():
    if "db" not in g:
        db_path, _ = _paths()
        g.db = sqlite3.connect(str(db_path))
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.executescript(SKEMA)
    return g.db


def tutup_db(_e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


# ---- Autentikasi dashboard dinas (tabel admin) ----
# Superadmin = baris dengan daerah '-'. Hanya superadmin yang boleh
# tambah/hapus instansi dan mengatur sandi akun pupr_* tiap daerah.
AKUN_DEMO = ("admin", "jalanpantau2026", "-")  # ganti sebelum sidang! (lihat init_admin)


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


def pastikan_akun_daerah(akun):
    """Pastikan akun login tiap daerah ada (username, daerah).

    Akun baru disegel sandi acak tak-tertebak + sandi_diatur=0 sehingga
    belum bisa dipakai sebelum superadmin mengatur sandinya. Akun yang
    sudah ada TIDAK disentuh (sandi existing aman). Kembalikan jumlah
    akun yang baru dibuat.
    """
    import secrets as _secrets

    migrasi_admin_v2()
    db = get_db()
    baru = 0
    for username, daerah in (akun or []):
        u = (username or "").strip().lower()
        if not u or not daerah:
            continue
        ada = db.execute("SELECT 1 FROM admin WHERE username = ?", (u,)).fetchone()
        if ada is None:
            db.execute(
                "INSERT INTO admin (username, password_hash, daerah, sandi_diatur)"
                " VALUES (?, ?, ?, 0)",
                (u, generate_password_hash(_secrets.token_hex(16)), daerah))
            baru += 1
    if baru:
        db.commit()
    return baru


def cek_login(username, password):
    """Kembalikan dict admin bila kredensial valid, selain itu None."""
    db = get_db()
    row = db.execute("SELECT * FROM admin WHERE username = ?", (username,)).fetchone()
    if row is None:
        return None
    if not check_password_hash(row["password_hash"], password):
        return None
    return dict(row)


def daftar_admin():
    db = get_db()
    return [dict(r) for r in db.execute(
        "SELECT id, username, daerah, sandi_diatur, dibuat FROM admin ORDER BY daerah, username").fetchall()]


def set_password_admin(username, password, daerah="-"):
    """Set/ganti password admin (hash baru). Return True bila sukses."""
    if not username or not password or len(password) < 8:
        return False
    migrasi_admin_v2()
    db = get_db()
    db.execute(
        "INSERT INTO admin (username, password_hash, daerah, sandi_diatur) VALUES (?, ?, ?, 1) "
        "ON CONFLICT(username) DO UPDATE SET password_hash = excluded.password_hash,"
        " daerah = excluded.daerah, sandi_diatur = 1",
        (username.strip().lower(), generate_password_hash(password), daerah))
    db.commit()
    return True


def simpan_sesi(sumber, lokasi, model, rows, total, lat=None, lon=None, image_b64=None):
    """rows = list dict dari /api/detect atau snapshot. Kembalikan id sesi."""
    db = get_db()
    sev = [r.get("severity", "-") for r in rows]
    worst = max(sev, key=lambda s: URUT_SEV.get(s, -1))
    cur = db.execute(
        "INSERT INTO sesi (waktu, sumber, lokasi, lat, lon, model, n_temuan, total_rp, worst)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), sumber, lokasi or "-",
         lat, lon, model, len(rows), int(total), worst))
    sid = cur.lastrowid
    for i, r in enumerate(rows, 1):
        db.execute(
            "INSERT INTO temuan (sesi_id, idx, track_id, kelas, dasar, severity, bahan,"
            " luas_m2, volume_m3, total_rp, total_str, conf)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, i, r.get("track_id"), r.get("kelas", "-"), r.get("dasar", "-"),
             r.get("severity", "-"), r.get("bahan", "-"), r.get("luas_m2", 0),
             r.get("volume_m3", 0), int(r.get("total_rp", 0)), r.get("total_str", "-"),
             r.get("conf")))
    if image_b64:
        try:
            import io
            from PIL import Image
            _, hasil = _paths()
            img_bytes = base64.b64decode(image_b64)
            # Simpan gambar penuh untuk detail
            (hasil / f"{sid}.jpg").write_bytes(img_bytes)
            # Buat thumbnail kecil (300px) untuk tabel
            with Image.open(io.BytesIO(img_bytes)) as im:
                im.thumbnail((300, 300))
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=75)
                (hasil / f"{sid}_thumb.jpg").write_bytes(buf.getvalue())
        except Exception:
            current_app.logger.exception("gagal simpan thumbnail")
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
    cur = db.execute(
        "SELECT id, waktu, sumber, lokasi, lat, lon, model, n_temuan, total_rp, worst"
        f" FROM sesi {where} ORDER BY id DESC LIMIT ? OFFSET ?", (*arg, limit, offset))
    return [dict(r) for r in cur.fetchall()]


def hitung_sesi(dari=None, sampai=None, severity=None, q=None):
    """Total baris sesi untuk filter yang sama (pendamping paginasi)."""
    db = get_db()
    where, arg = _klausa_sesi(dari, sampai, severity, q)
    return db.execute(f"SELECT COUNT(*) FROM sesi {where}", arg).fetchone()[0]


def detail_sesi(sid):
    db = get_db()
    s = db.execute("SELECT * FROM sesi WHERE id = ?", (sid,)).fetchone()
    if s is None:
        return None
    rows = db.execute("SELECT * FROM temuan WHERE sesi_id = ? ORDER BY idx", (sid,)).fetchall()
    ada_gambar = (_paths()[1] / f"{sid}.jpg").exists()
    return {"sesi": dict(s), "temuan": [dict(r) for r in rows], "ada_gambar": ada_gambar}


def hapus_sesi(sid):
    db = get_db()
    cur = db.execute("DELETE FROM sesi WHERE id = ?", (sid,))
    db.commit()
    try:
        (_paths()[1] / f"{sid}.jpg").unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("gagal hapus thumbnail sesi %s", sid)
    return cur.rowcount > 0


def titik_peta():
    db = get_db()
    cur = db.execute(
        "SELECT id, waktu, lokasi, lat, lon, n_temuan, total_rp, worst FROM sesi"
        " WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY id DESC LIMIT 500")
    rows = [dict(r) for r in cur.fetchall()]
    hasil = _paths()[1]
    for r in rows:
        r["ada_gambar"] = (hasil / f"{r['id']}.jpg").exists()
    return rows


# ============================================================
# Manajemen Instansi Pemerintah
# ============================================================

def init_instansi():
    """Inisialisasi data instansi default jika belum ada."""
    db = get_db()
    for inst in DATA_INSTANSI_DEFAULT:
        existing = db.execute("SELECT id FROM instansi_pemerintah WHERE nama = ?", (inst[0],)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO instansi_pemerintah (nama, daerah, alamat, email, telepon, lat, lon, radius_km)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)", inst)
    db.commit()


def daftar_instansi(daerah=None, aktif_only=True):
    """Daftar instansi pemerintah."""
    db = get_db()
    klausa, arg = [], []
    if aktif_only:
        klausa.append("is_active = 1")
    if daerah:
        klausa.append("daerah LIKE ?")
        arg.append(f"%{daerah}%")
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    cur = db.execute(
        f"SELECT * FROM instansi_pemerintah {where} ORDER BY daerah, nama", arg)
    return [dict(r) for r in cur.fetchall()]


def instansi_by_id(iid):
    """Get instansi by ID."""
    db = get_db()
    r = db.execute("SELECT * FROM instansi_pemerintah WHERE id = ?", (iid,)).fetchone()
    return dict(r) if r else None


def simpan_instansi(nama, daerah, alamat, email, telepon, lat, lon, radius_km=50):
    """Simpan/update instansi."""
    db = get_db()
    db.execute(
        "INSERT INTO instansi_pemerintah (nama, daerah, alamat, email, telepon, lat, lon, radius_km)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (nama, daerah, alamat, email, telepon, lat, lon, radius_km))
    db.commit()
    return db.execute("SELECT last_insert_rowid()").fetchone()[0]


def hapus_instansi(iid):
    """Hapus instansi."""
    db = get_db()
    cur = db.execute("DELETE FROM instansi_pemerintah WHERE id = ?", (iid,))
    db.commit()
    return cur.rowcount > 0


def instansi_terdekat(lat, lon):
    """Cari instansi terdekat berdasarkan koordinat menggunakan Haversine formula."""
    import math

    db = get_db()
    cur = db.execute("SELECT * FROM instansi_pemerintah WHERE is_active = 1 AND lat IS NOT NULL AND lon IS NOT NULL")
    instansi_list = [dict(r) for r in cur.fetchall()]

    if not instansi_list:
        return None

    # Haversine formula (radian + sin/cos/asin yang benar)
    R = 6371.0  # radius bumi km
    min_jarak = float("inf")
    terdekat = None
    lat_rad = math.radians(lat)

    for inst in instansi_list:
        try:
            ilat = float(inst["lat"])
            ilon = float(inst["lon"])
        except (TypeError, ValueError):
            continue
        dlat = math.radians(ilat - lat)
        dlon = math.radians(ilon - lon)
        a = (math.sin(dlat / 2) ** 2
             + math.cos(lat_rad) * math.cos(math.radians(ilat)) * math.sin(dlon / 2) ** 2)
        a = min(max(a, 0.0), 1.0)
        jarak = R * 2 * math.asin(math.sqrt(a))

        if jarak < min_jarak:
            min_jarak = jarak
            terdekat = dict(inst)
            terdekat["jarak_km"] = round(jarak, 2)

    return terdekat


# ============================================================
# Manajemen Disposisi (Laporan Terkirim)
# ============================================================

def simpan_disposisi(bap_id, bap_nomor, lokasi, lat, lon, n_temuan, total_rp, worst,
                     instansi_id, instansi_nama, instansi_daerah, instansi_email,
                     urgensi="Rutin", catatan="-"):
    """Simpan disposisi baru. Return ID."""
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    cur = db.execute(
        "INSERT INTO disposisi (waktu, bap_id, bap_nomor, lokasi, lat, lon, n_temuan,"
        " total_rp, worst, instansi_id, instansi_nama, instansi_daerah, instansi_email,"
        " urgensi, catatan, status, pembaruan_terakhir)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Terkirim', ?)",
        (now, bap_id, bap_nomor, lokasi or "-", lat, lon, n_temuan, int(total_rp), worst,
         instansi_id, instansi_nama or "-", instansi_daerah or "-", instansi_email or "-",
         urgensi, catatan, now))
    db.commit()
    return cur.lastrowid


def daftar_disposisi(daerah=None, status=None, urgensi=None, limit=200, exact=False):
    """Daftar disposisi dengan filter."""
    db = get_db()
    klausa, arg = [], []
    if daerah:
        if exact:
            klausa.append("instansi_daerah = ?")
            arg.append(daerah)
        else:
            klausa.append("instansi_daerah LIKE ?")
            arg.append(f"%{daerah}%")
    if status:
        klausa.append("status = ?")
        arg.append(status)
    if urgensi:
        klausa.append("urgensi = ?")
        arg.append(urgensi)
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    cur = db.execute(
        "SELECT * FROM disposisi " + where + " ORDER BY id DESC LIMIT ?", (*arg, limit))
    return [dict(r) for r in cur.fetchall()]


def detail_disposisi(did):
    """Get disposisi by ID."""
    db = get_db()
    r = db.execute("SELECT * FROM disposisi WHERE id = ?", (did,)).fetchone()
    return dict(r) if r else None


def detail_disposisi_by_bap(bap_id):
    """Get disposisi by BAP id (sesi id)."""
    db = get_db()
    r = db.execute("SELECT * FROM disposisi WHERE bap_id = ? ORDER BY id DESC LIMIT 1", (bap_id,)).fetchone()
    return dict(r) if r else None


def update_status_disposisi(did, status, catatan=None, penanggung_jawab=None):
    """Update status disposisi + cap waktu tahap + arsip catatan."""
    db = get_db()
    if db.execute("SELECT 1 FROM disposisi WHERE id = ?", (did,)).fetchone() is None:
        return False  # P2: jangan True untuk did fiktif via total_changes INSERT catatan
    now = datetime.now().isoformat(timespec="seconds")
    if catatan:
        db.execute("UPDATE disposisi SET status = ?, catatan = ?, pembaruan_terakhir = ? WHERE id = ?",
                   (status, catatan, now, did))
    else:
        db.execute("UPDATE disposisi SET status = ?, pembaruan_terakhir = ? WHERE id = ?",
                   (status, now, did))
    if penanggung_jawab:
        db.execute("UPDATE disposisi SET penanggung_jawab = ? WHERE id = ?",
                   (penanggung_jawab, did))
    if status == "Diproses":
        db.execute("UPDATE disposisi SET waktu_diproses = COALESCE(waktu_diproses, ?) WHERE id = ?",
                   (now, did))
    elif status == "Selesai":
        db.execute("UPDATE disposisi SET waktu_selesai = COALESCE(waktu_selesai, ?) WHERE id = ?",
                   (now, did))
    if catatan:
        db.execute("INSERT INTO disposisi_catatan (disposisi_id, waktu, status, catatan)"
                   " VALUES (?, ?, ?, ?)", (did, now, status, catatan))
    db.commit()
    return True


def riwayat_catatan(disposisi_id):
    """Riwayat catatan penanganan per disposisi."""
    db = get_db()
    cur = db.execute("SELECT * FROM disposisi_catatan WHERE disposisi_id = ? ORDER BY id ASC",
                     (disposisi_id,))
    return [dict(r) for r in cur.fetchall()]


def migrasi_disposisi_v2():
    """Tambah kolom tahap + tabel riwayat catatan. Aman diulang."""
    db = get_db()
    cols = {r[1] for r in db.execute("PRAGMA table_info(disposisi)").fetchall()}
    for nama, tipe in [("waktu_diproses", "TEXT"), ("waktu_selesai", "TEXT"),
                       ("penanggung_jawab", "TEXT DEFAULT '-'"),
                       ("foto_sesudah", "TEXT")]:
        if nama not in cols:
            db.execute(f"ALTER TABLE disposisi ADD COLUMN {nama} {tipe}")
    db.execute(
        "CREATE TABLE IF NOT EXISTS disposisi_catatan ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, disposisi_id INTEGER NOT NULL, "
        "waktu TEXT NOT NULL, status TEXT NOT NULL DEFAULT '-', "
        "catatan TEXT NOT NULL DEFAULT '-')")
    db.execute("CREATE INDEX IF NOT EXISTS idx_catatan_disposisi"
               " ON disposisi_catatan(disposisi_id)")
    db.commit()


def hapus_disposisi(did):
    """Hapus disposisi."""
    db = get_db()
    cur = db.execute("DELETE FROM disposisi WHERE id = ?", (did,))
    db.commit()
    return cur.rowcount > 0


def statistik_disposisi(daerah=None, exact=False):
    """Statistik untuk KPI dashboard."""
    db = get_db()
    if daerah:
        if exact:
            where = "WHERE instansi_daerah = ?"
            arg = [daerah]
        else:
            where = "WHERE instansi_daerah LIKE ?"
            arg = [f"%{daerah}%"]
    else:
        where = ""
        arg = []

    total = db.execute("SELECT COUNT(*) FROM disposisi " + where, arg).fetchone()[0]
    baru = db.execute("SELECT COUNT(*) FROM disposisi " + where + (" AND" if daerah else "WHERE") + " status = 'Terkirim'", arg).fetchone()[0]
    diproses = db.execute("SELECT COUNT(*) FROM disposisi " + where + (" AND" if daerah else "WHERE") + " status = 'Diproses'", arg).fetchone()[0]
    selesai = db.execute("SELECT COUNT(*) FROM disposisi " + where + (" AND" if daerah else "WHERE") + " status = 'Selesai'", arg).fetchone()[0]

    return {"total": total, "baru": baru, "diproses": diproses, "selesai": selesai}


def hitung_disposisi(daerah=None, status=None, urgensi=None, exact=False):
    """Total baris disposisi untuk filter yang sama (pendamping paginasi)."""
    db = get_db()
    klausa, arg = [], []
    if daerah:
        if exact:
            klausa.append("instansi_daerah = ?")
            arg.append(daerah)
        else:
            klausa.append("instansi_daerah LIKE ?")
            arg.append(f"%{daerah}%")
    if status:
        klausa.append("status = ?")
        arg.append(status)
    if urgensi:
        klausa.append("urgensi = ?")
        arg.append(urgensi)
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    return db.execute("SELECT COUNT(*) FROM disposisi " + where, arg).fetchone()[0]
