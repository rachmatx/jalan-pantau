# -*- coding: utf-8 -*-
"""Diagnostik mode teliti (tiling): cari tahap di mana box hilang.

Dijalankan di MESIN USER:
    python scripts/diag_teliti.py foto.jpg

Mencetak:
 1. predict full-frame @imgsz 960 (jalur normal)
 2. predict full-frame @imgsz 640 (tanpa tiling)
 3. per-tile: jumlah box mentah @conf=0.01
Lalu bandingkan: bila (2) ada box tapi (3) kosong -> bug di loop tiling;
bila (2) pun kosong -> model butuh imgsz besar untuk gambar ini.

Memakai half=... sama seperti aplikasi agar hemat VRAM (penting di GPU 4GB).
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
