"""Smoke test runtime untuk bugfix 1-5 (tanpa model YOLO, DB temp)."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "web"))

from web.app import create_app  # noqa: E402


def main():
    tmp = tempfile.mkdtemp(prefix="smoke_")
    app = create_app()
    app.config["DB_PATH"] = os.path.join(tmp, "t.db")
    app.config["TESTING"] = True
    ctx = app.app_context()
    ctx.push()
    from database import init_instansi, migrasi_disposisi_v2, simpan_sesi, simpan_disposisi
    init_instansi()
    migrasi_disposisi_v2()

    rows = [
        {"kelas": "pothole", "severity": "Berat"},
        {"kelas": "alligator_crack", "severity": "Sedang"},
        {"kelas": "transverse_crack", "severity": "Ringan"},
        {"kelas": "longitudinal_crack", "severity": "Ringan"},
    ]
    tot = len(rows) * 100

    def sesi(lat, lon):
        return simpan_sesi("uji", "-", "yolo", rows, tot, lat=lat, lon=lon)

    s1, s2, s3 = sesi(-6.2, 106.8), sesi(-6.25, 106.85), sesi(-6.9, 107.5)
    simpan_disposisi(s1, "BAP-001", "Jl A", -6.2, 106.8, 4, tot, "Berat",
                     1, "Dinas A", "Bogor", "a@b.c", "Kritis", "{}")
    simpan_disposisi(s2, "BAP-002", "Jl B", -6.25, 106.85, 4, tot, "Sedang",
                     1, "Dinas B", "Kabupaten Bogor", "a@b.c", "Tinggi", "{}")
    simpan_disposisi(s3, "BAP-003", "Jl C", -6.9, 107.5, 4, tot, "Ringan",
                     1, "Dinas C", "Kabupaten Bandung Barat", "a@b.c", "Rutin", "{}")

    c = app.test_client()
    gagal = 0

    def cek(nama, kondisi, detail=""):
        nonlocal gagal
        status = "PASS" if kondisi else "FAIL"
        if not kondisi:
            gagal += 1
        print(f"[{status}] {nama} {detail}")

    print("== SMOKE 1: filter daerah exact (bug 1) ==")
    r1 = c.get("/api/disposisi?daerah=Bogor").get_json()
    cek("tanpa exact 'Bogor' masih LIKE (legacy)",
        sorted(x["instansi_daerah"] for x in r1) == ["Bogor", "Kabupaten Bogor"],
        f"-> {sorted(x['instansi_daerah'] for x in r1)}")
    r2 = c.get("/api/disposisi?daerah=Bogor&exact=1").get_json()
    cek("exact=1 'Bogor' hanya Kota Bogor",
        [x["instansi_daerah"] for x in r2] == ["Bogor"],
        f"-> {[x['instansi_daerah'] for x in r2]}")
    r3 = c.get("/api/disposisi?daerah=Kabupaten+Bogor&exact=1").get_json()
    cek("exact=1 'Kabupaten Bogor' terisolasi",
        [x["instansi_daerah"] for x in r3] == ["Kabupaten Bogor"],
        f"-> {[x['instansi_daerah'] for x in r3]}")
    r4 = c.get("/api/disposisi?daerah=Bandung&exact=1").get_json()
    cek("exact=1 'Bandung' tidak nyedot KBB",
        r4 == [], f"-> {len(r4)} baris")

    print("== SMOKE 2: toggle anotasi server (bug 4) ==")
    r = c.post("/api/stream/anotasi")
    j1 = r.get_json()
    cek("POST pertama -> anotasi off", r.status_code == 200 and j1.get("anotasi") is False,
        f"-> {r.status_code} {j1}")
    r = c.post("/api/stream/anotasi")
    j2 = r.get_json()
    cek("POST kedua -> anotasi on", r.status_code == 200 and j2.get("anotasi") is True,
        f"-> {r.status_code} {j2}")

    print("== SMOKE 3: temuan asli untuk rekap (bug 5) ==")
    d = c.get(f"/api/riwayat/{s1}").get_json()
    kelas = sorted(t["kelas"] for t in d["temuan"])
    cek("detail sesi balikin 4 temuan per kelas",
        kelas == sorted(["pothole", "alligator_crack",
                         "transverse_crack", "longitudinal_crack"]),
        f"-> {kelas}")

    print("== SMOKE 4: halaman render pasca-patch ==")
    for url in ("/", "/mobile"):
        r = c.get(url)
        cek(f"GET {url}", r.status_code == 200, f"-> {r.status_code}")
    # Dashboard wajib login -> anon 302 ke /login, login superadmin -> 200
    r = c.get("/pupr-bogor/dashboard")
    cek("GET /pupr-bogor/dashboard anon -> 302 login", r.status_code == 302,
        f"-> {r.status_code}")
    from database import AKUN_DEMO, init_admin
    init_admin()
    c.post("/login", data={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]})
    r = c.get("/pupr-bogor/dashboard")
    cek("GET /pupr-bogor/dashboard login -> 200", r.status_code == 200,
        f"-> {r.status_code}")

    ctx.pop()
    print()
    print("GAGAL:", gagal) if gagal else print("SEMUA SMOKE PASS")
    return 1 if gagal else 0


if __name__ == "__main__":
    sys.exit(main())
