"""Isi database dengan data DEMO untuk sidang (hasil DETEKSI NYATA).

- Menjalankan pipeline deteksi asli (`web/deteksi.py`) pada beberapa foto contoh,
  lalu menyimpannya ke riwayat + membuat 1-2 disposisi.
- Tujuan: dashboard / peta / riwayat **tidak kosong** saat demo.
- Idempoten: memakai `client_ref` tetap -> aman dijalankan berulang (tidak menggandakan).
- Semua catatan demo diberi penanda: sumber diawali `Demo:` dan catatan berisi
  `CONTOH-DEMO`, sehingga mudah dibersihkan.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\siapkan_data_demo.py
    .\\.venv\\Scripts\\python scripts\\siapkan_data_demo.py --jumlah 6
    .\\.venv\\Scripts\\python scripts\\siapkan_data_demo.py --bersih

Catatan: koordinat memakai **lokasi nyata di Bandung** sebagai contoh titik, TAPI
fotonya bukan dari lokasi itu — ini data contoh untuk demo, bukan hasil survei.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "web"), str(ROOT / "app")]

FOTO_DIR = ROOT / "data" / "publik" / "bpid" / "test" / "images"
# (lokasi contoh, lintang, bujur) — nama ruas nyata, dipakai sebagai contoh titik peta
TITIK = [
    ("Jl. Asia Afrika (contoh demo)", -6.9218, 107.6109),
    ("Jl. Soekarno-Hatta KM 12 (contoh demo)", -6.9430, 107.6570),
    ("Jl. Buah Batu (contoh demo)", -6.9450, 107.6320),
    ("Jl. Setiabudi (contoh demo)", -6.8800, 107.5900),
    ("Jl. Dago (contoh demo)", -6.8850, 107.6130),
    ("Jl. Pasteur (contoh demo)", -6.8930, 107.5880),
]

PENANDA = "CONTOH-DEMO"


def bersihkan():
    from database import get_db
    db = get_db()
    hasil = Path(__file__).resolve().parents[1] / "web" / "instance" / "hasil"
    sids = [r["id"] for r in db.execute(
        "SELECT id FROM sesi WHERE sumber LIKE 'Demo:%'").fetchall()]
    n_disp = db.execute(
        "DELETE FROM disposisi WHERE catatan LIKE ? OR bap_nomor LIKE 'BA-DEMO/%'",
        (f"%{PENANDA}%",)).rowcount
    n_sesi = db.execute("DELETE FROM sesi WHERE sumber LIKE 'Demo:%'").rowcount
    db.commit()
    for sid in sids:
        for nama in (f"{sid}.jpg", f"{sid}_thumb.jpg"):
            try:
                (hasil / nama).unlink(missing_ok=True)
            except OSError:
                pass
    print(f"Bersih: {n_sesi} sesi, {n_disp} disposisi dihapus.")


def isi(jumlah, conf):
    import json
    from database import (disposisi_by_client_ref, instansi_terdekat,
                          sesi_by_client_ref, simpan_disposisi, simpan_sesi)
    from deteksi import analisis_gambar

    foto = sorted(p for p in FOTO_DIR.iterdir()
                  if p.suffix.lower() in (".jpg", ".jpeg", ".png"))[:jumlah]
    if not foto:
        raise SystemExit(f"Tidak ada foto contoh di {FOTO_DIR}")

    dibuat = []
    for i, p in enumerate(foto):
        ref = f"demo-sesi-{i}"
        ada = sesi_by_client_ref(ref)
        if ada:
            print(f"  (lewati {p.name} — sudah ada sebagai sesi {ada})")
            continue
        lokasi, lat, lon = TITIK[i % len(TITIK)]
        data = p.read_bytes()
        r = analisis_gambar(data, conf=conf, malam=False, teliti=False, segmentasi=False)
        sid = simpan_sesi(
            sumber=f"Demo: {p.name}", lokasi=lokasi, model=r["model"],
            rows=r["rows"], total=r["total"], lat=lat, lon=lon,
            image_b64=r.get("image_b64"), client_ref=ref)
        print(f"  [sesi {sid}] {p.name} -> {len(r['rows'])} temuan, "
              f"Rp{r['total']:,}".replace(",", "."))
        dibuat.append((sid, lokasi, lat, lon, r))

    # Disposisi untuk 2 sesi pertama (agar dashboard dinas terisi)
    for i, (sid, lokasi, lat, lon, r) in enumerate(dibuat[:2]):
        ref = f"demo-disposisi-{i}"
        if disposisi_by_client_ref(ref):
            print(f"  (lewati disposisi-{i} — sudah ada)")
            continue
        inst = instansi_terdekat(lat, lon) or {}
        worst = r["rows"][0]["severity"] if r["rows"] else "-"
        did = simpan_disposisi(
            bap_id=sid, bap_nomor=f"BA-DEMO/{sid}", lokasi=lokasi, lat=lat, lon=lon,
            n_temuan=len(r["rows"]), total_rp=r["total"], worst=worst,
            instansi_id=inst.get("id"), instansi_nama=inst.get("nama", "-"),
            instansi_daerah=inst.get("daerah", "-"), instansi_email=inst.get("email", "-"),
            urgensi="Kritis" if i == 0 else "Rutin",
            catatan=f"Data {PENANDA} untuk demo sidang (bukan laporan resmi).",
            client_ref=f"demo-disposisi-{i}")
        print(f"  [disposisi {did}] dari sesi {sid} -> {inst.get('nama', '-')}")
    print(f"\nSelesai: {len(dibuat)} sesi contoh tersimpan.")
    print("Bersihkan nanti: .\\.venv\\Scripts\\python scripts\\siapkan_data_demo.py --bersih")


def main():
    ap = argparse.ArgumentParser(description="Isi data demo sidang (deteksi nyata).")
    ap.add_argument("--jumlah", type=int, default=4, help="jumlah foto contoh (default 4)")
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--bersih", action="store_true", help="hapus semua data demo lalu keluar")
    args = ap.parse_args()

    import app as app_mod
    app = app_mod.create_app()
    with app.app_context():
        if args.bersih:
            bersihkan()
        else:
            isi(args.jumlah, args.conf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
