# -*- coding: utf-8 -*-
"""Diagnostik mode teliti (tiling): cari tahap di mana box hilang.

Dijalankan di MESIN USER:
    python scripts/diag_teliti.py foto.jpg

Mencetak:
 1. predict full-frame @imgsz 960, conf 0.01 (tanpa augment)
 2. predict full-frame @imgsz 640, conf 0.01 — sama dengan jalur gambar aplikasi
 3. per-tile: jumlah box mentah @conf 0.01 pada imgsz = ukuran tile (640)
Lalu bandingkan: bila (2) ada box tapi (3) kosong -> masalah di loop tiling.

CATATAN PENTING (18 Okt 2026): mode teliti tidak lagi diaktifkan otomatis dan
diukur jauh lebih BURUK daripada full-frame pada data lokal berlabel (F1 0,011
vs 0,567 pada 161 gambar BPID; recall pothole besar 0%). Jadi skrip ini hanya
alat eksperimen, bukan alat menilai jalur gambar. Untuk menilai jalur gambar,
lihat docs/Panduan-Tuning-Model.md §6d (P/R/F1 terhadap ground truth).

Skrip memakai half=... (FP16) demi hemat VRAM, SEDANGKAN jalur gambar aplikasi
sekarang berjalan FP32 (`half_gambar: false`). Sebagian karena itu angka skrip ini
tidak boleh dibandingkan langsung dengan output UI.

Tiap tahap dibungkus try/except: satu OOM tidak membunuh sisanya.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "app"))

import deteksi  # noqa: E402


def ringkas(res, names, maks=5):
    out = []
    for b in res.boxes[:maks]:
        out.append((deteksi.nama_kelas(names, int(b.cls[0])),
                    round(float(b.conf[0]), 3)))
    return out


def aman_predict(model, img, label, **kw):
    try:
        r = model.predict(img, verbose=False, **kw)[0]
        print(f"    {label}: {len(r.boxes)} box ->", ringkas(r, model.names))
    except RuntimeError as e:
        print(f"    {label}: GAGAL ({str(e).splitlines()[0][:110]})")


def main(foto):
    raw = Path(foto).read_bytes()
    img = deteksi.decode_image(raw)
    h, w = img.shape[:2]
    print(f"gambar: {w}x{h}")
    inf = deteksi.get_inferensi()
    model = deteksi.get_model()
    device = deteksi.pilih_device(inf.get("device"), str(deteksi.resolve_model()))
    half = deteksi.half_untuk(device)
    print(f"device: {device}  half: {half}")

    print("\n[1] full-frame @imgsz=960, conf=0.01 (tanpa augment):")
    aman_predict(model, img, "960", conf=0.01, imgsz=960,
                 device=device, half=half)

    print("\n[2] full-frame @imgsz=640, conf=0.01 (tanpa augment):")
    aman_predict(model, img, "640", conf=0.01, imgsz=640,
                 device=device, half=half)

    print("\n[3] per-tile @imgsz=640, conf=0.01:")
    tcfg = inf["teliti"]
    tile = int(tcfg.get("tile", 640))
    tiles = deteksi.grid_tile(w, h, tile, tcfg.get("overlap", 0.25))
    print("    tiles:", tiles)
    for (x0, y0) in tiles:
        crop = img[y0:y0 + tile, x0:x0 + tile]
        aman_predict(model, crop, f"tile ({x0},{y0}) {crop.shape}",
                     conf=0.01, imgsz=tile, device=device, half=half)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Pakai: python scripts/diag_teliti.py foto.jpg")
        sys.exit(1)
    main(sys.argv[1])
