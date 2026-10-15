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
  skor_prioritas INTEGER NOT NULL,
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
  skor_prioritas INTEGER NOT NULL,
  total_str TEXT NOT NULL DEFAULT '-',
  conf REAL
);
CREATE INDEX IF NOT EXISTS idx_temuan_sesi ON temuan(sesi_id);
"""


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
        migrasi_prioritas_v1(g.db)
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
    ulang dari jumlah `temuan[].skor_prioritas` supaya kolom sesi.skor_prioritas
    selalu sama dengan jumlah baris temuan. Sebelumnya angka datang dari client,
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
    B_SKOR, B_M2, B_M3, B_CONF = 10 ** 6, 10 ** 5, 10 ** 4, 1.0
    temuan = []
    for r in rows:
        temuan.append({
            "kelas": str(r.get("kelas", "-"))[:120],
            "dasar": str(r.get("dasar", "-"))[:200],
            "severity": str(r.get("severity", "-"))[:40],
            "bahan": str(r.get("bahan", "-"))[:120],
            "luas_m2": _angka(r.get("luas_m2"), B_M2),
            "volume_m3": _angka(r.get("volume_m3"), B_M3),
            "skor_prioritas": int(_angka(r.get("skor_prioritas"), B_SKOR)),
            "total_str": str(r.get("skor_prioritas", "-"))[:60],
            "conf": (_angka(r.get("conf"), B_CONF, bawaan=-1.0)
                     if r.get("conf") is not None else None),
            "track_id": (int(_angka(r.get("track_id"), 10 ** 6))
                         if r.get("track_id") is not None else None),
        })
    total = sum(t["skor_prioritas"] for t in temuan)
    sev = [t["severity"] for t in temuan]
    worst = max(sev, key=lambda s: URUT_SEV.get(s, -1))
    cur = db.execute(
        "INSERT INTO sesi (waktu, sumber, lokasi, lat, lon, model, n_temuan, skor_prioritas, worst, client_ref)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), sumber, lokasi or "-",
         lat, lon, model, len(temuan), int(total), worst, client_ref))
    sid = cur.lastrowid
    for i, t in enumerate(temuan, 1):
        db.execute(
            "INSERT INTO temuan (sesi_id, idx, track_id, kelas, dasar, severity, bahan,"
            " luas_m2, volume_m3, skor_prioritas, total_str, conf)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sid, i, t["track_id"], t["kelas"], t["dasar"], t["severity"], t["bahan"],
             t["luas_m2"], t["volume_m3"], t["skor_prioritas"], t["total_str"], t["conf"]))
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
        "SELECT id, waktu, sumber, lokasi, lat, lon, model, n_temuan, skor_prioritas, worst"
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
        "SELECT id, waktu, lokasi, lat, lon, n_temuan, skor_prioritas, worst FROM sesi"
        " WHERE lat IS NOT NULL AND lon IS NOT NULL ORDER BY id DESC LIMIT 500")
    rows = [dict(r) for r in cur.fetchall()]
    hasil = _paths()[1]
    for r in rows:
        r["ada_gambar"] = (hasil / f"{r['id']}.jpg").exists()
    return rows


