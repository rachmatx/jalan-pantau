"""Verifikasi kesiapan demo/sidang — satu perintah, TANPA server.

Memeriksa cepat: .env & kunci sesi, bobot + checksum, berkas konfigurasi,
database, video demo (fallback sidang), aset offline, dan semua route utama
(lewat Flask test client).

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\cek_pra_sidang.py
Exit 0 bila semua penting lulus; 1 bila ada yang gagal.
"""
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "web"), str(ROOT / "app")]

gagal = 0


def cek(nama, ok, detail=""):
    global gagal
    if not ok:
        gagal += 1
    print(f"[{'OK   ' if ok else 'GAGAL'}] {nama}" + (f" - {detail}" if detail else ""))


# 1. .env / kunci sesi
env = ROOT / ".env"
punya_key = bool(os.environ.get("JP_SECRET_KEY"))
if not punya_key and env.is_file():
    punya_key = "JP_SECRET_KEY=" in env.read_text(encoding="utf-8", errors="ignore")
cek(".env / JP_SECRET_KEY", punya_key,
    "" if punya_key else "salin .env.example -> .env dan isi JP_SECRET_KEY")

# 2. bobot + checksum
W = ROOT / "app" / "weights"
for n in ("best_yolo11s.pt", "best.onnx", "best.pt"):
    cek(f"bobot {n}", (W / n).is_file())
manif = W / "SHA256SUMS.txt"
if manif.is_file():
    ok = True
    for baris in manif.read_text(encoding="utf-8").splitlines():
        b = baris.split()
        if len(b) != 2:
            continue
        f = W / b[1]
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest() != b[0].lower():
            ok = False
            break
    cek("checksum bobot (SHA256SUMS)", ok, "" if ok else "jalankan scripts/verifikasi_bobot.py")

# 3. konfigurasi
for c in ("severity.yaml", "inferensi.yaml", "harga_acuan.csv"):
    cek(f"config/{c}", (ROOT / "config" / c).is_file())

# 4. database
try:
    con = sqlite3.connect(str(ROOT / "web" / "instance" / "riwayat.db"))
    con.execute("SELECT 1 FROM sesi LIMIT 1").fetchall()
    con.close()
    cek("database SQLite", True)
except Exception as e:
    cek("database SQLite", False, str(e)[:70])

# 5. video demo (fallback sidang)
cek("video demo (fallback sidang)", (ROOT / "web" / "static" / "demo" / "demo_jalan.mp4").is_file())

# 6. aset offline
vendor = [ROOT / "web" / "static" / "vendor" / "leaflet" / "leaflet.js",
          ROOT / "web" / "static" / "vendor" / "leaflet" / "leaflet.css",
          ROOT / "web" / "static" / "vendor" / "fonts" / "fonts.css"]
cek("aset offline (leaflet + fonts)", all(p.is_file() for p in vendor))

# 7. route (via test client)
try:
    import app as app_mod
    a = app_mod.create_app()
    a.config["TESTING"] = True
    c = a.test_client()
    for u in ["/", "/peta", "/riwayat", "/tentang", "/disposisi", "/login"]:
        s = c.get(u).status_code
        cek(f"route {u}", s == 200, f"status {s}")
    s = c.get("/pupr-bandung/dashboard").status_code
    cek("route terlindungi (anon -> 302)", s == 302, f"status {s}")
except Exception as e:
    cek("render route", False, str(e)[:80])

print()
if gagal:
    print(f"ADA {gagal} MASALAH - perbaiki sebelum sidang.")
else:
    print("SEMUA PENTING LULUS - siap demo.")
raise SystemExit(1 if gagal else 0)
