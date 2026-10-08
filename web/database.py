"""Riwayat SQLite: sesi analisis + temuan per titik + thumbnail.

DB: web/instance/riwayat.db (boleh dioverride via app.config["DB_PATH"], mis. untuk tes).
Thumbnail: <instance>/hasil/<id>.jpg. PDF tidak disimpan — selalu generate ulang.
"""
import base64
import os
import sqlite3
from datetime import datetime, timedelta
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
  worst TEXT NOT NULL DEFAULT '-',
  client_ref TEXT
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
  pembaruan_terakhir TEXT,
  client_ref TEXT
);
CREATE INDEX IF NOT EXISTS idx_disposisi_waktu ON disposisi(waktu);
CREATE INDEX IF NOT EXISTS idx_disposisi_instansi ON disposisi(instansi_daerah);
CREATE INDEX IF NOT EXISTS idx_disposisi_status ON disposisi(status);

-- Tabel Kontraktor (pihak penerima SPK dari Dinas Bina Marga)
CREATE TABLE IF NOT EXISTS kontraktor (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kode TEXT NOT NULL UNIQUE,
  nama TEXT NOT NULL,
  perusahaan TEXT NOT NULL DEFAULT '-',
  alamat TEXT NOT NULL DEFAULT '-',
  telepon TEXT NOT NULL DEFAULT '-',
  email TEXT NOT NULL DEFAULT '-',
  bidang TEXT NOT NULL DEFAULT '-',
  is_active INTEGER NOT NULL DEFAULT 1,
  dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Akun login kontraktor. Terpisah dari tabel admin (dinas) supaya data
-- perusahaan tidak bercampur dengan akun instansi.
CREATE TABLE IF NOT EXISTS kontraktor_akun (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  kontraktor_id INTEGER NOT NULL REFERENCES kontraktor(id) ON DELETE CASCADE,
  nama_kontak TEXT NOT NULL DEFAULT '-',
  sandi_diatur INTEGER NOT NULL DEFAULT 0,
  dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_kakun_kontraktor ON kontraktor_akun(kontraktor_id);

-- SPK: perintah kerja yang diterbitkan Dinas ke satu kontraktor.
CREATE TABLE IF NOT EXISTS spk (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nomor TEXT NOT NULL UNIQUE,
  kontraktor_id INTEGER NOT NULL REFERENCES kontraktor(id) ON DELETE CASCADE,
  daerah TEXT NOT NULL,
  judul TEXT NOT NULL,
  deskripsi TEXT NOT NULL DEFAULT '-',
  prioritas TEXT NOT NULL DEFAULT 'Rutin',
  status TEXT NOT NULL DEFAULT 'Diterbitkan',
  tenggat TEXT,
  dibuat_oleh TEXT NOT NULL DEFAULT '-',
  dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
  diterima_pada TEXT,
  dikerjakan_pada TEXT,
  selesai_pada TEXT,
  catatan_dinas TEXT NOT NULL DEFAULT '-',
  catatan_kontraktor TEXT NOT NULL DEFAULT '-'
);
CREATE INDEX IF NOT EXISTS idx_spk_kontraktor ON spk(kontraktor_id);
CREATE INDEX IF NOT EXISTS idx_spk_daerah ON spk(daerah);
CREATE INDEX IF NOT EXISTS idx_spk_status ON spk(status);

-- Titik pekerjaan di dalam SPK (satu baris = satu laporan kerusakan).
CREATE TABLE IF NOT EXISTS spk_tugas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  spk_id INTEGER NOT NULL REFERENCES spk(id) ON DELETE CASCADE,
  disposisi_id INTEGER NOT NULL REFERENCES disposisi(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'Menunggu',
  catatan TEXT NOT NULL DEFAULT '-',
  foto_selesai TEXT,
  UNIQUE(spk_id, disposisi_id)
);
CREATE INDEX IF NOT EXISTS idx_tugas_spk ON spk_tugas(spk_id);

-- Jejak audit perubahan status SPK (siapa, kapan, status berapa).
CREATE TABLE IF NOT EXISTS spk_catatan (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  spk_id INTEGER NOT NULL REFERENCES spk(id) ON DELETE CASCADE,
  waktu TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT '-',
  catatan TEXT NOT NULL DEFAULT '-',
  oleh TEXT NOT NULL DEFAULT '-'
);
CREATE INDEX IF NOT EXISTS idx_spcatatan_spk ON spk_catatan(spk_id);
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
                  "JP_DEMO_PASS atau ganti lewat halaman Instansi sebelum "
                  "dipakai di luar demo.")


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


def simpan_sesi(sumber, lokasi, model, rows, total, lat=None, lon=None, image_b64=None,
                client_ref=None):
    """rows = list dict dari /api/detect atau snapshot. Kembalikan id sesi.

    `client_ref` (bila ada) dipakai sebagai kunci idempotensi: simpan ulang dengan
    ref yang sama tidak membuat baris baru (dijamin indeks unik parsial).

    CATATAN PENTING: parameter `total` TIDAK dipercaya. Nilai sesi dihitung
    ulang dari jumlah `temuan[].total_rp` supaya kolom sesi.total_rp selalu
    sama dengan jumlah baris temuan. Sebelumnya angka datang dari client,
    sehingga (a) bisa disuntik nilai berapa pun, dan (b) bisa tidak cocok
    dengan rincian temuan di bawahnya.
    """
    db = get_db()
    if not isinstance(rows, (list, tuple)):
        rows = []
    rows = [r for r in rows if isinstance(r, dict)]
    if not rows:
        raise ValueError("Tidak ada temuan untuk disimpan.")
    # Batas wajar: luas, volume, dan nominal yang tidak mungkin melebihi ini.
    B_RP, B_M2, B_M3, B_CONF = 10 ** 13, 10 ** 5, 10 ** 4, 1.0
    temuan = []
    for r in rows:
        temuan.append({
            "kelas": str(r.get("kelas", "-"))[:120],
            "dasar": str(r.get("dasar", "-"))[:200],
            "severity": str(r.get("severity", "-"))[:40],
            "bahan": str(r.get("bahan", "-"))[:120],
            "luas_m2": _angka(r.get("luas_m2"), B_M2),
            "volume_m3": _angka(r.get("volume_m3"), B_M3),
            "total_rp": int(_angka(r.get("total_rp"), B_RP)),
            "total_str": str(r.get("total_str", "-"))[:60],
            "conf": (_angka(r.get("conf"), B_CONF, bawaan=-1.0)
                     if r.get("conf") is not None else None),
            "track_id": (int(_angka(r.get("track_id"), 10 ** 6))
                         if r.get("track_id") is not None else None),
        })
    total = sum(t["total_rp"] for t in temuan)
    sev = [t["severity"] for t in temuan]
    worst = max(sev, key=lambda s: URUT_SEV.get(s, -1))
    cur = db.execute(
        "INSERT INTO sesi (waktu, sumber, lokasi, lat, lon, model, n_temuan, total_rp, worst, client_ref)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), sumber, lokasi or "-",
         lat, lon, model, len(temuan), int(total), worst, client_ref))
    sid = cur.lastrowid
    for i, t in enumerate(temuan, 1):
        db.execute(
            "INSERT INTO temuan (sesi_id, idx, track_id, kelas, dasar, severity, bahan,"
            " luas_m2, volume_m3, total_rp, total_str, conf)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, i, t["track_id"], t["kelas"], t["dasar"], t["severity"], t["bahan"],
             t["luas_m2"], t["volume_m3"], t["total_rp"], t["total_str"], t["conf"]))
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


def rekap_temuan(bap_id):
    """Rekap otoritatif dari tabel `temuan` untuk sebuah sesi.

    Dipakai endpoint simpan disposisi: angka yang masuk ke laporan harus
    berasal dari database, bukan dari JSON client. Kalau nama angka tidak
    ada di sini, berarti baris temuan-nya tidak pernah tersimpan dan
    nomor yang dikirim client tidak punya dasar apa pun.

    Return dict {n_temuan, total_rp, worst} atau None bila sesi tidak ada.
    """
    db = get_db()
    s = db.execute("SELECT id FROM sesi WHERE id = ?", (bap_id,)).fetchone()
    if s is None:
        return None
    agg = db.execute(
        "SELECT COUNT(*) AS n, COALESCE(SUM(total_rp), 0) AS total FROM temuan"
        " WHERE sesi_id = ?", (bap_id,)).fetchone()
    baris = db.execute(
        "SELECT severity FROM temuan WHERE sesi_id = ?", (bap_id,)).fetchall()
    sev = [r["severity"] for r in baris if r["severity"]]
    worst = max(sev, key=lambda x: URUT_SEV.get(x, -1)) if sev else "-"
    return {"n_temuan": int(agg["n"] or 0),
            "total_rp": int(agg["total"] or 0),
            "worst": worst}


def hapus_sesi(sid):
    db = get_db()
    cur = db.execute("DELETE FROM sesi WHERE id = ?", (sid,))
    db.commit()
    hasil = _paths()[1]
    # Hapus gambar PENUH dan THUMBNAIL. Sebelumnya hanya gambar penuh yang
    # dihapus sehingga thumbnail yatim menumpuk di disk (terverifikasi:
    # id 40-44 punya _thumb.jpg tapi tidak ada di tabel sesi).
    for suffix in (".jpg", "_thumb.jpg"):
        try:
            (hasil / f"{sid}{suffix}").unlink(missing_ok=True)
        except OSError as e:
            current_app.logger.warning("gagal hapus %s sesi %s: %s",
                                       "thumbnail" if suffix.startswith("_") else "gambar",
                                       sid, e)
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


def titik_peta_kontraktor(kontraktor_id, limit=500):
    """Titik kerusakan di dalam SPK milik SATU kontraktor.

    Berbeda dengan titik_peta() yang mengembalikan seluruh riwayat sesi
    milik semua orang, fungsi ini hanya melihat tabel spk_tugas milik
    kontraktor tersebut. Itu sebabnya peta dalam ruang kerja kontraktor
    TIDAK boleh memakai endpoint publik /api/peta: kontraktor tidak berhak
    melihat inspeksi jalan milik dinas atau pengguna lain.
    """
    db = get_db()
    cur = db.execute(
        "SELECT t.id AS tugas_id, t.status AS status_tugas, t.foto_selesai,"
        " s.id AS spk_id, s.nomor AS spk_nomor,"
        " d.id AS disposisi_id, d.bap_id, d.bap_nomor, d.lokasi, d.lat, d.lon,"
        " d.n_temuan, d.total_rp, d.worst, d.urgensi, d.instansi_nama"
        " FROM spk_tugas t"
        " JOIN spk s ON s.id = t.spk_id"
        " JOIN disposisi d ON d.id = t.disposisi_id"
        " WHERE s.kontraktor_id = ?"
        "   AND d.lat IS NOT NULL AND d.lon IS NOT NULL"
        " ORDER BY t.id DESC LIMIT ?", (kontraktor_id, limit))
    rows = [dict(r) for r in cur.fetchall()]
    hasil = _paths()[1]
    for r in rows:
        r["ada_foto"] = bool(r.pop("foto_selesai", None))
        # Foto asli hasil deteksi mengikuti nama berkas sesi (bap_id).
        try:
            r["ada_gambar"] = (hasil / f"{int(r['bap_id'])}.jpg").exists()
        except (TypeError, ValueError):
            r["ada_gambar"] = False
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

# Urutan ini adalah urutan TUNGGAL yang dipakai seluruh frontend
# (URUT_U di dashboard/index.html dan dashboard/disposisi.html).
URGENSI_VALID = ("Kritis", "Tinggi", "Rutin")


def normalisasi_urgensi(nilai, bawaan="Rutin"):
    """Ubah sembarang ejaan menjadi kapital kanonik.

    Form mengirim 'kritis'/'tinggi'/'rutin' (lowercase) sementara seluruh
    konsumen membandingkan 'Kritis'/'Tinggi'/'Rutin' (kapital). Tanpa
    normalisasi, baris lowercase lolos ke cabang "Rutin": SLA selalu 48
    jam, chip Kritis di dashboard selalu 0, dan filter urgensi tidak pernah
    cocok. Semua jalur tulis & filter harus lewat fungsi ini.
    """
    s = str(nilai or "").strip()
    if not s:
        return bawaan
    kanonik = s.capitalize()
    return kanonik if kanonik in URGENSI_VALID else bawaan


def migrasi_urgensi_v1():
    """Samakan ejaan urgensi lama ke bentuk kanonik. Idempoten.

    Menyentuh baris yang TIDAK sudah kanonik saja, jadi aman dipanggil
    berulang kali di setiap boot.
    """
    db = get_db()
    for kanonik in URGENSI_VALID:
        for varian in {kanonik.lower(), kanonik.upper(), kanonik.capitalize()}:
            if varian == kanonik:
                continue
            db.execute("UPDATE disposisi SET urgensi = ? WHERE urgensi = ?",
                       (kanonik, varian))
    db.commit()


def simpan_disposisi(bap_id, bap_nomor, lokasi, lat, lon, n_temuan, total_rp, worst,
                     instansi_id, instansi_nama, instansi_daerah, instansi_email,
                     urgensi="Rutin", catatan="-", client_ref=None):
    """Simpan disposisi baru. Return ID.

    `client_ref` (bila ada) = kunci idempotensi: kirim ulang dengan ref sama
    tidak membuat baris baru (dijamin indeks unik parsial).
    """
    db = get_db()
    now = datetime.now().isoformat(timespec="seconds")
    cur = db.execute(
        "INSERT INTO disposisi (waktu, bap_id, bap_nomor, lokasi, lat, lon, n_temuan,"
        " total_rp, worst, instansi_id, instansi_nama, instansi_daerah, instansi_email,"
        " urgensi, catatan, status, pembaruan_terakhir, client_ref)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Terkirim', ?, ?)",
        (now, bap_id, bap_nomor, lokasi or "-", lat, lon, n_temuan, int(total_rp), worst,
         instansi_id, instansi_nama or "-", instansi_daerah or "-", instansi_email or "-",
         normalisasi_urgensi(urgensi), catatan, now, client_ref))
    db.commit()
    return cur.lastrowid


def disposisi_by_client_ref(ref):
    """Id disposisi untuk client_ref (idempotensi). None bila belum ada."""
    if not ref:
        return None
    row = get_db().execute(
        "SELECT id FROM disposisi WHERE client_ref = ?", (ref,)).fetchone()
    return row["id"] if row else None


def disposisi_duplikat(bap_id, instansi_id, dalam_menit=10):
    """Heuristik anti-duplikat: id disposisi dengan bap_id (+ instansi_id bila ada)
    sama yang dibuat dalam `dalam_menit` terakhir. None bila tidak ada."""
    if bap_id is None:
        return None
    batas = (datetime.now() - timedelta(minutes=int(dalam_menit))).isoformat(timespec="seconds")
    sql = "SELECT id FROM disposisi WHERE bap_id = ? AND waktu >= ?"
    arg = [bap_id, batas]
    if instansi_id is not None:
        sql += " AND instansi_id = ?"
        arg.append(instansi_id)
    sql += " ORDER BY id DESC LIMIT 1"
    row = get_db().execute(sql, arg).fetchone()
    return row["id"] if row else None


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
        # Terima "kritis" maupun "Kritis" dari client mana pun.
        klausa.append("urgensi = ?")
        arg.append(normalisasi_urgensi(urgensi, bawaan=urgensi.strip()))
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    cur = db.execute(
        "SELECT * FROM disposisi " + where + " ORDER BY id DESC LIMIT ?", (*arg, limit))
    return [dict(r) for r in cur.fetchall()]


def path_foto_sesudah(item):
    """Path absolut foto 'sesudah' untuk sebuah baris disposisi, atau None.

    Delegasi ke path_foto_bukti supaya validasi nama berkas (basename + ekstensi
    gambar, berkas benar-benar ada) hanya punya satu implementasi.
    """
    return path_foto_bukti((item or {}).get("foto_sesudah"))


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


def update_status_disposisi(did, status, catatan=None, penanggung_jawab=None, oleh=None):
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
    # Audit trail: SELALU catat perubahan status (walau tanpa catatan), lengkap
    # dengan pelaku (username admin) untuk akuntabilitas.
    db.execute("INSERT INTO disposisi_catatan (disposisi_id, waktu, status, catatan, oleh)"
               " VALUES (?, ?, ?, ?, ?)", (did, now, status, catatan or '-', oleh or '-'))
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
                       ("client_ref", "TEXT"),
                       ("foto_sesudah", "TEXT")]:
        if nama not in cols:
            db.execute(f"ALTER TABLE disposisi ADD COLUMN {nama} {tipe}")
    db.execute(
        "CREATE TABLE IF NOT EXISTS disposisi_catatan ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, disposisi_id INTEGER NOT NULL, "
        "waktu TEXT NOT NULL, status TEXT NOT NULL DEFAULT '-', "
        "catatan TEXT NOT NULL DEFAULT '-', oleh TEXT DEFAULT '-')")
    db.execute("CREATE INDEX IF NOT EXISTS idx_catatan_disposisi"
               " ON disposisi_catatan(disposisi_id)")
    # Kolom "oleh" (pelaku perubahan) untuk audit trail; tambah bila DB lama.
    cols_cat = {r[1] for r in db.execute("PRAGMA table_info(disposisi_catatan)").fetchall()}
    if "oleh" not in cols_cat:
        db.execute("ALTER TABLE disposisi_catatan ADD COLUMN oleh TEXT DEFAULT '-'")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_disposisi_client_ref"
               " ON disposisi(client_ref) WHERE client_ref IS NOT NULL")
    db.commit()


def hapus_disposisi(did):
    """Hapus disposisi (dan foto bukti 'sesudah' bila ada)."""
    db = get_db()
    # Ambil nama file dulu: setelah DELETE kolomnya sudah hilang.
    row = db.execute("SELECT foto_sesudah FROM disposisi WHERE id = ?", (did,)).fetchone()
    cur = db.execute("DELETE FROM disposisi WHERE id = ?", (did,))
    db.commit()
    nama = (row["foto_sesudah"] if row else None)
    if nama:
        try:
            (_paths()[1] / nama).unlink(missing_ok=True)
        except OSError as e:
            current_app.logger.warning("gagal hapus foto sesudah disposisi %s: %s", did, e)
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
        # Terima "kritis" maupun "Kritis" dari client mana pun.
        klausa.append("urgensi = ?")
        arg.append(normalisasi_urgensi(urgensi, bawaan=urgensi.strip()))
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    return db.execute("SELECT COUNT(*) FROM disposisi " + where, arg).fetchone()[0]


# ============================================================
# Kontraktor + SPK (alur dinas -> kontraktor -> bukti perbaikan)
# ============================================================

# Status SPK. Urutan ini adalah urutan TUNGGAL yang dipakai seluruh frontend.
SPK_STATUS = ("Diterbitkan", "Diterima", "Dikerjakan", "Selesai", "Dibatalkan")

# Transisi status yang boleh dilakukan tiap pihak. Dinas boleh membatalkan;
# kontraktor hanya boleh maju Maju. Tanpa tabel ini kontraktor bisa melompat
# langsung ke "Selesai" tanpa menerima atau dikerjakan.
SPK_TRANSISI = {
    "kontraktor": {
        "Diterbitkan": ("Diterima",),
        "Diterima": ("Dikerjakan",),
        "Dikerjakan": ("Selesai",),
        "Selesai": (),
        "Dibatalkan": (),
    },
    "dinas": {
        "Diterbitkan": ("Dibatalkan",),
        "Diterima": ("Dibatalkan",),
        "Dikerjakan": ("Dibatalkan",),
        "Selesai": (),
        "Dibatalkan": (),
    },
}

# Status satu titik pekerjaan di dalam SPK.
TUGAS_STATUS = ("Menunggu", "Dikerjakan", "Selesai")
TUGAS_TRANSISI = {
    "Menunggu": ("Dikerjakan",),
    "Dikerjakan": ("Selesai",),
    "Selesai": (),
}

KONTRAKTOR_SEED = Path(__file__).resolve().parent.parent / "config" / "kontraktor.yaml"


def normalisasi_kode_kontraktor(nilai, bawaan="KT"):
    """Kode kontraktor jadi huruf besar + tanda hubung, mis. 'kt 01' -> 'KT-01'."""
    s = "".join(ch for ch in str(nilai or "") if ch.isalnum() or ch in "-_ ").strip().upper()
    s = s.replace(" ", "-").replace("_", "-")
    while "--" in s:
        s = s.replace("--", "-")
    return s.strip("-") or bawaan


def init_kontraktor(path=None):
    """Seed kontraktor + akun dari config/kontraktor.yaml. Aman diulang.

    Kontrak seed (sudah disepakati): daftar kontraktor awal berasal dari
    konfigurasi berkas, lalu dapat disunting dari dashboard Dinas.

    Perkembangan sandi akun kontraktor:
    - `akun.sandi` diisi  -> dipakai apa adanya.
    - `akun.segel: true` -> akun disegel dengan sandi acak tak-tertebak
      (sandi_diatur=0) sampai@dinas mengaturnya.
    - Selain itu -> pakai sandi demo yang sama dengan akun admin
      (AKUN_DEMO, bisa di-override env JP_DEMO_PASS) supaya demo langsung
      bisa dicoba, dengan peringatan di console seperti akun admin.

    Kontraktor yang sudah ada TIDAK disentuh saat seed diulang.
    """
    import secrets as _secrets

    db = get_db()
    try:
        import yaml
        with open(str(path or KONTRAKTOR_SEED), encoding="utf-8") as f:
            isi = yaml.safe_load(f) or {}
    except (OSError, ValueError) as exc:
        current_app.logger.warning("config kontraktor tidak terbaca: %s", exc)
        return 0
    except Exception as exc:  # yaml.YAMLError ikut tertangkap di sini
        current_app.logger.warning("config kontraktor rusak: %s", exc)
        return 0

    baris = isi.get("kontraktor") if isinstance(isi, dict) else isi
    if not isinstance(baris, (list, tuple)):
        return 0

    baru = 0
    demo_pakai_default = False
    for item in baris:
        if not isinstance(item, dict):
            continue
        kode = normalisasi_kode_kontraktor(item.get("kode"))
        nama = str(item.get("nama") or "").strip()
        if not nama:
            continue
        if db.execute("SELECT 1 FROM kontraktor WHERE kode = ?", (kode,)).fetchone() is None:
            db.execute(
                "INSERT INTO kontraktor (kode, nama, perusahaan, alamat, telepon, email,"
                " bidang, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (kode, nama, str(item.get("perusahaan") or "-"),
                 str(item.get("alamat") or "-"), str(item.get("telepon") or "-"),
                 str(item.get("email") or "-"), str(item.get("bidang") or "-"),
                 0 if item.get("nonaktif") else 1))
            baru += 1
        kid = db.execute("SELECT id FROM kontraktor WHERE kode = ?", (kode,)).fetchone()["id"]

        akun = item.get("akun")
        if not isinstance(akun, dict):
            continue
        u = str(akun.get("username") or "").strip().lower()
        if not u:
            continue
        if db.execute("SELECT 1 FROM kontraktor_akun WHERE username = ?", (u,)).fetchone():
            continue  # akun existing tidak disentuh (sandi existing aman)
        sandi = str(akun.get("sandi") or "")
        if bool(akun.get("segel")):
            hash_, diatur = generate_password_hash(_secrets.token_hex(16)), 0
        elif sandi:
            hash_, diatur = generate_password_hash(sandi), 1
        else:
            hash_, diatur = generate_password_hash(AKUN_DEMO[1]), 1
            demo_pakai_default = True
        db.execute(
            "INSERT INTO kontraktor_akun (username, password_hash, kontraktor_id,"
            " nama_kontak, sandi_diatur) VALUES (?, ?, ?, ?, ?)",
            (u, hash_, kid, str(akun.get("nama_kontak") or "-"), diatur))
        baru += 1
    db.commit()
    if baru:
        print(f"[kontraktor] seed {baru} baris baru dari "
              f"{Path(str(path or KONTRAKTOR_SEED)).name}")
    if demo_pakai_default:
        print("PERINGATAN: akun kontraktor memakai sandi demo yang sama dengan "
              "akun admin. Ganti lewat menu Kontraktor di dashboard Dinas "
              "(atau set env JP_DEMO_PASS) sebelum dipakai di luar demo.")
    return baru


def cek_login_kontraktor(username, password):
    """Dict profil bila kredensial akun kontraktor valid, selain itu None.

    Dict hasil sudah menyatu profil kontraktor supaya pemanggil tidak perlu
    query kedua. Akun yang kontraktornya dinonaktifkan TIDAK bisa login.
    """
    if not username or not password:
        return None
    db = get_db()
    row = db.execute(
        "SELECT a.id AS akun_id, a.username, a.nama_kontak, a.sandi_diatur,"
        " k.id AS kontraktor_id, k.kode, k.nama, k.perusahaan, k.bidang"
        " FROM kontraktor_akun a JOIN kontraktor k ON k.id = a.kontraktor_id"
        " WHERE a.username = ? AND k.is_active = 1", (username.strip().lower(),)).fetchone()
    if row is None:
        return None
    akun = db.execute("SELECT password_hash FROM kontraktor_akun WHERE id = ?",
                      (row["akun_id"],)).fetchone()
    if akun is None or not check_password_hash(akun["password_hash"], password):
        return None
    return dict(row)


def daftar_kontraktor(aktif_only=True):
    db = get_db()
    where = "WHERE is_active = 1" if aktif_only else ""
    return [dict(r) for r in db.execute(
        f"SELECT * FROM kontraktor {where} ORDER BY kode").fetchall()]


def kontraktor_by_id(kid):
    if kid is None:
        return None
    r = get_db().execute("SELECT * FROM kontraktor WHERE id = ?", (kid,)).fetchone()
    return dict(r) if r else None


def daftar_akun_kontraktor():
    db = get_db()
    return [dict(r) for r in db.execute(
        "SELECT a.id, a.username, a.nama_kontak, a.sandi_diatur, a.dibuat,"
        " k.id AS kontraktor_id, k.kode, k.nama AS kontraktor_nama"
        " FROM kontraktor_akun a JOIN kontraktor k ON k.id = a.kontraktor_id"
        " ORDER BY k.kode, a.username").fetchall()]


def simpan_kontraktor(kode, nama, perusahaan="-", alamat="-", telepon="-", email="-",
                      bidang="-", aktif=True):
    """Tambah/update kontraktor berdasarkan kode. Return id."""
    db = get_db()
    k = normalisasi_kode_kontraktor(kode)
    n = str(nama or "").strip()
    if not n:
        raise ValueError("Nama kontraktor wajib diisi.")
    db.execute(
        "INSERT INTO kontraktor (kode, nama, perusahaan, alamat, telepon, email, bidang,"
        " is_active) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(kode) DO UPDATE SET nama = excluded.nama,"
        " perusahaan = excluded.perusahaan, alamat = excluded.alamat,"
        " telepon = excluded.telepon, email = excluded.email,"
        " bidang = excluded.bidang, is_active = excluded.is_active",
        (k, n, perusahaan or "-", alamat or "-", telepon or "-", email or "-",
         bidang or "-", 1 if aktif else 0))
    db.commit()
    return db.execute("SELECT id FROM kontraktor WHERE kode = ?", (k,)).fetchone()[0]


def set_password_kontraktor(username, password):
    if not username or not password or len(password) < 8:
        return False
    db = get_db()
    cur = db.execute(
        "UPDATE kontraktor_akun SET password_hash = ?, sandi_diatur = 1"
        " WHERE username = ?",
        (generate_password_hash(password), username.strip().lower()))
    db.commit()
    return cur.rowcount > 0


def nomor_spk_berikutnya(db=None):
    """Nomor SPK unik per tahun: SPK/2026/0007."""
    db = db or get_db()
    tahun = datetime.now().year
    pref = f"SPK/{tahun}/"
    n = db.execute("SELECT COUNT(*) c FROM spk WHERE nomor LIKE ?", (pref + "%",)
                   ).fetchone()["c"] + 1
    # Lewati nomor yang sudah dipakai (mis. dihapus lalu dipakai ulang).
    while db.execute("SELECT 1 FROM spk WHERE nomor = ?",
                     (f"{pref}{n:04d}",)).fetchone():
        n += 1
    return f"{pref}{n:04d}"


def terbitkan_spk(kontraktor_id, daerah, judul, disposisi_ids, deskripsi="-",
                  prioritas="Rutin", tenggat=None, dibuat_oleh="-", catatan_dinas="-"):
    """Terbitkan SPK baru berisi titik-titik kerusakan dari tabel disposisi.

    Hanya disposisi yang BENAR-BENAR ada dan milik daerah penerbit yang bisa
    dimasukkan: kalau IDs berasal dari form/browser, angka karangan akan
    membuat SPK menunjuk laporan yang tidak pernah ada.
    """
    db = get_db()
    if kontraktor_by_id(kontraktor_id) is None:
        raise ValueError("Kontraktor tidak ditemukan.")
    judul = str(judul or "").strip()
    if not judul:
        raise ValueError("Judul SPK wajib diisi.")

    ids = []
    for v in (disposisi_ids or []):
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n > 0 and n not in ids:
            ids.append(n)
    if not ids:
        raise ValueError("Pilih minimal satu titik kerusakan untuk SPK.")

    _q = ",".join("?" * len(ids))
    rows = db.execute(
        f"SELECT id, instansi_daerah FROM disposisi WHERE id IN ({_q})", ids).fetchall()
    sah = [r["id"] for r in rows if daerah in (None, "-") or r["instansi_daerah"] == daerah]
    if not sah:
        raise ValueError("Tidak ada titik kerusakan yang cocok dengan daerah penerbit.")

    nomor = nomor_spk_berikutnya(db)
    cur = db.execute(
        "INSERT INTO spk (nomor, kontraktor_id, daerah, judul, deskripsi, prioritas,"
        " status, tenggat, dibuat_oleh, catatan_dinas) VALUES (?, ?, ?, ?, ?, ?,"
        " 'Diterbitkan', ?, ?, ?)",
        (nomor, kontraktor_id, daerah or "-", judul, deskripsi or "-",
         normalisasi_urgensi(prioritas), tenggat or None, dibuat_oleh or "-",
         catatan_dinas or "-"))
    sid = cur.lastrowid
    for did in sah:
        db.execute("INSERT INTO spk_tugas (spk_id, disposisi_id) VALUES (?, ?)", (sid, did))
    db.execute("INSERT INTO spk_catatan (spk_id, waktu, status, catatan, oleh)"
               " VALUES (?, ?, 'Diterbitkan', ?, ?)",
               (sid, datetime.now().isoformat(timespec="seconds"),
                f"SPK terbit dengan {len(sah)} titik kerusakan.", dibuat_oleh or "-"))
    db.commit()
    return sid


def daftar_spk(kontraktor_id=None, daerah=None, status=None, limit=200):
    db = get_db()
    klausa, arg = [], []
    if kontraktor_id is not None:
        klausa.append("s.kontraktor_id = ?")
        arg.append(kontraktor_id)
    if daerah:
        klausa.append("s.daerah = ?")
        arg.append(daerah)
    if status:
        klausa.append("s.status = ?")
        arg.append(status)
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    cur = db.execute(
        "SELECT s.*, k.kode AS kontraktor_kode, k.nama AS kontraktor_nama,"
        " (SELECT COUNT(*) FROM spk_tugas t WHERE t.spk_id = s.id) AS n_tugas,"
        " (SELECT COUNT(*) FROM spk_tugas t WHERE t.spk_id = s.id"
        "  AND t.status = 'Selesai') AS n_tugas_selesai"
        f" FROM spk s JOIN kontraktor k ON k.id = s.kontraktor_id {where}"
        " ORDER BY s.id DESC LIMIT ?", (*arg, limit))
    return [dict(r) for r in cur.fetchall()]


def detail_spk(sid):
    r = get_db().execute(
        "SELECT s.*, k.kode AS kontraktor_kode, k.nama AS kontraktor_nama,"
        " k.perusahaan AS kontraktor_perusahaan, k.telepon AS kontraktor_telepon"
        " FROM spk s JOIN kontraktor k ON k.id = s.kontraktor_id"
        " WHERE s.id = ?", (sid,)).fetchone()
    return dict(r) if r else None


def spk_boleh_akses(sid, kontraktor_id):
    """Kontraktor hanya boleh membuka SPK miliknya sendiri.

    Ini penjaga utama otorisasi kontraktor: seluruh query detail SPK HARUS
    dilewatkan fungsi ini, bukan sekadar menyembunyikan tautan di UI.
    """
    if kontraktor_id is None or sid is None:
        return False
    return get_db().execute(
        "SELECT 1 FROM spk WHERE id = ? AND kontraktor_id = ?",
        (sid, kontraktor_id)).fetchone() is not None


def daftar_tugas_spk(sid):
    """Titik pekerjaan sebuah SPK, lengkap dengan data laporan + koordinat.

    Ini sumber data peta dashboard kontraktor: satu baris = satu titik
    kerusakan yang harus dikerjakan. Urutan Kritis lebih dulu memakai CASE
    terhadap URGENSI_VALID supaya tidak bergantung pada urutan kolom.
    """
    urutan = " ".join(
        f"WHEN '{u}' THEN {i}" for i, u in enumerate(URGENSI_VALID))
    cur = get_db().execute(
        "SELECT t.id, t.disposisi_id, t.status, t.catatan, t.foto_selesai,"
        " d.bap_nomor, d.lokasi, d.lat, d.lon, d.n_temuan, d.total_rp, d.worst,"
        " d.urgensi, d.instansi_nama"
        " FROM spk_tugas t JOIN disposisi d ON d.id = t.disposisi_id"
        f" WHERE t.spk_id = ? ORDER BY CASE d.urgensi {urutan} ELSE 99 END, d.id",
        (sid,))
    return [dict(r) for r in cur.fetchall()]


def riwayat_spk(sid):
    cur = get_db().execute(
        "SELECT waktu, status, catatan, oleh FROM spk_catatan WHERE spk_id = ?"
        " ORDER BY id ASC", (sid,))
    return [dict(r) for r in cur.fetchall()]


def statistik_spk(kontraktor_id=None, daerah=None):
    """KPI untuk dashboard kontraktor (per kontraktor) atau dinas (per daerah)."""
    db = get_db()
    klausa, arg = [], []
    if kontraktor_id is not None:
        klausa.append("kontraktor_id = ?")
        arg.append(kontraktor_id)
    if daerah:
        klausa.append("daerah = ?")
        arg.append(daerah)
    where = ("WHERE " + " AND ".join(klausa)) if klausa else ""
    hitung = {s: 0 for s in SPK_STATUS}
    for r in db.execute(f"SELECT status, COUNT(*) c FROM spk {where} GROUP BY status", arg):
        if r["status"] in hitung:
            hitung[r["status"]] = r["c"]
    tugas = db.execute(
        "SELECT COUNT(*) n, SUM(CASE WHEN t.status='Selesai' THEN 1 ELSE 0 END) s"
        f" FROM spk_tugas t JOIN spk s ON s.id = t.spk_id {where}", arg).fetchone()
    return {"total": sum(hitung.values()), "status": hitung,
            "n_tugas": int(tugas["n"] or 0), "n_tugas_selesai": int(tugas["s"] or 0)}


def update_status_spk(sid, status, catatan=None, oleh="-", peran="kontraktor"):
    """Ubah status SPK sesuai transisi yang sah untuk pihak pemanggil.

    Mengembalikan (True, pesan) atau (False, alasan). `peran` menentukan
    tabel transisi mana yang dipakai sehingga kontraktor tidak bisa
    membatalkan SPK dan dinas tidak bisa menandai pekerjaan kontraktor selesai.
    """
    db = get_db()
    spk = detail_spk(sid)
    if spk is None:
        return False, "SPK tidak ditemukan."
    if status not in SPK_STATUS:
        return False, "Status tidak dikenal."
    allowed = SPK_TRANSISI.get(peran, {}).get(spk["status"], ())
    if status not in allowed:
        return False, (f"Status tidak bisa diubah dari {spk['status']} ke {status}.")
    now = datetime.now().isoformat(timespec="seconds")

    kolom = {"diterima_pada": status == "Diterima",
             "dikerjakan_pada": status == "Dikerjakan",
             "selesai_pada": status == "Selesai"}
    setel = ["status = ?"]
    arg = [status]
    for k, aktif in kolom.items():
        if aktif:
            setel.append(f"{k} = COALESCE({k}, ?)")
            arg.append(now)
    if peran == "kontraktor" and catatan:
        setel.append("catatan_kontraktor = ?")
        arg.append(str(catatan)[:2000])
    if peran == "dinas" and catatan:
        setel.append("catatan_dinas = ?")
        arg.append(str(catatan)[:2000])
    arg += [sid]
    db.execute(f"UPDATE spk SET {', '.join(setel)} WHERE id = ?", arg)
    db.execute("INSERT INTO spk_catatan (spk_id, waktu, status, catatan, oleh)"
               " VALUES (?, ?, ?, ?, ?)", (sid, now, status, catatan or '-', oleh or '-'))
    db.commit()
    return True, f"Status SPK menjadi {status}."


def update_tugas_tugas(tid, status, catatan=None):
    """Ubah status satu titik pekerjaan. Kembalikan (True, pesan)/(False, alasan).

    `tid` HARUS sudah dipastikan milik SPK pemanggil (lihat update_tugas_untuk_spk)
    supaya kontraktor tidak bisa menandai titik milik SPK orang lain.
    """
    db = get_db()
    if status not in TUGAS_STATUS:
        return False, "Status tidak dikenal."
    row = db.execute("SELECT status FROM spk_tugas WHERE id = ?", (tid,)).fetchone()
    if row is None:
        return False, "Titik pekerjaan tidak ditemukan."
    if status not in TUGAS_TRANSISI.get(row["status"], ()):
        return False, f"Status tidak bisa diubah dari {row['status']} ke {status}."
    if status == "Selesai" and not db.execute(
            "SELECT 1 FROM spk_tugas WHERE id = ? AND foto_selesai IS NOT NULL",
            (tid,)).fetchone():
        return False, "Lampirkan foto bukti sebelum menandai titik selesai."
    db.execute("UPDATE spk_tugas SET status = ?, catatan = ? WHERE id = ?",
               (status, str(catatan or "-")[:2000], tid))
    db.commit()
    return True, f"Status titik menjadi {status}."


def update_tugas_untuk_spk(sid, tid, status, catatan=None, oleh="-"):
    """Ubah status titik pada SPK tertentu lalu selaraskan status SPK.

    Otorisasi TIDAK dicek di sini: pemanggil harus memastikan `tid` milik SPK
    milik kontraktor yang sedang login (lihat spk_boleh_akses). Fungsi ini
    hanya menjaga titik benar-benar berada di dalam SPK tersebut.
    """
    db = get_db()
    row = db.execute("SELECT spk_id FROM spk_tugas WHERE id = ?", (tid,)).fetchone()
    if row is None or row["spk_id"] != sid:
        return False, "Titik pekerjaan tidak ada di SPK ini."
    ok, pesan = update_tugas_tugas(tid, status, catatan)
    if not ok:
        return False, pesan
    db.execute("INSERT INTO spk_catatan (spk_id, waktu, status, catatan, oleh)"
               " VALUES (?, ?, ?, ?, ?)",
               (sid, datetime.now().isoformat(timespec="seconds"), status,
                catatan or '-', oleh or '-'))
    db.commit()

    # Bila seluruh titik sudah Selesai, SPK ikut diselesaikan otomatis supaya
    # kontraktor tidak perlu satu klik lagi yang mudah terlupa.
    sisa = db.execute("SELECT COUNT(*) c FROM spk_tugas"
                      " WHERE spk_id = ? AND status <> 'Selesai'", (sid,)).fetchone()["c"]
    spk = detail_spk(sid)
    if sisa == 0 and spk and spk["status"] == "Dikerjakan":
        update_status_spk(sid, "Selesai", "Seluruh titik pekerjaan selesai.", oleh, "kontraktor")
    elif spk and spk["status"] == "Diterima" and status == "Dikerjakan":
        update_status_spk(sid, "Dikerjakan", "Pekerjaan lapangan dimulai.", oleh, "kontraktor")
    return True, pesan


def batalkan_spk(sid, oleh="-"):
    """Dinas membatalkan SPK. Penugasan yang sudah dikerjakan tidak dihapus."""
    return update_status_spk(sid, "Dibatalkan", None, oleh, "dinas")


def path_foto_bukti(nama):
    """Path absolut berkas bukti atas nama kolom foto, atau None.

    Nama file wajib berupa basename sederhana berekstensi gambar supaya nilai
    dari database tidak bisa dipakai untuk keluar dari folder hasil/.
    """
    nama = str(nama or "").strip()
    if not nama or nama == "-" or not nama.lower().endswith((".jpg", ".jpeg", ".png")):
        return None
    if Path(nama).name != nama:
        return None
    p = _paths()[1] / nama
    return p if p.is_file() else None


def simpan_foto_tugas(tid, data, ext):
    """Simpan foto bukti sebuah titik pekerjaan. Return nama berkas atau None.

    Nama berkas memakai awalan 'spk_' supaya tidak mungkin menimpa
    <id_sesi>.jpg milik riwayat yang sudah ada.
    """
    if not data or not ext:
        return None
    import secrets as _sec

    _, hasil = _paths()
    nama = f"spk_{int(tid)}_{_sec.token_hex(8)}.{ext}"
    (hasil / nama).write_bytes(data)
    get_db().execute("UPDATE spk_tugas SET foto_selesai = ? WHERE id = ?", (nama, tid))
    get_db().commit()
    return nama


def hapus_spk(sid):
    db = get_db()
    nama = [r["foto_selesai"] for r in db.execute(
        "SELECT foto_selesai FROM spk_tugas WHERE spk_id = ? AND foto_selesai IS NOT NULL",
        (sid,)).fetchall()]
    cur = db.execute("DELETE FROM spk WHERE id = ?", (sid,))
    db.commit()
    for n in nama:
        try:
            (_paths()[1] / n).unlink(missing_ok=True)
        except OSError as e:
            current_app.logger.warning("gagal hapus foto SPK %s: %s", n, e)
    return cur.rowcount > 0
