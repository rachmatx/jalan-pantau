# -*- coding: utf-8 -*-
"""Benchmark kecepatan vs jumlah temuan deteksi foto.

Dijalankan di MESIN USER (bukan di VM ini):
    python scripts/bench_inferensi.py foto1.jpg [foto2.jpg ...]
    python scripts/bench_inferensi.py test_foto          (boleh folder)

Mengukur tiap kombinasi (tta on/off x imgsz 960/800/640) memakai pipeline
asli `analisis_gambar`, lalu mencetak tabel waktu + jumlah temuan.
Pilih konfigurasi tercepat (<5 dtk) yang jumlah temuannya tidak turun
dibanding bawaan. Hasilnya tempel ke chat untuk diputuskan bersama.
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "app"))

import deteksi  # noqa: E402

KONFIGS = [
    ("tta=on  imgsz=960 (bawaan)", dict(tta=True, imgsz=960)),
    ("tta=off imgsz=960", dict(tta=False, imgsz=960)),
    ("tta=on  imgsz=800", dict(tta=True, imgsz=800)),
    ("tta=off imgsz=800", dict(tta=False, imgsz=800)),
    ("tta=on  imgsz=640", dict(tta=True, imgsz=640)),
    ("tta=off imgsz=640", dict(tta=False, imgsz=640)),
]

EKSTENSI = (".jpg", ".jpeg", ".png")


def kumpulkan(daftar):
    out = []
    for d in daftar:
        p = Path(d)
        if p.is_dir():
            out += sorted(str(x) for x in p.iterdir()
                          if x.suffix.lower() in EKSTENSI)
        elif p.is_file():
            out.append(str(p))
        else:
            print(f"  ! diabaikan (tidak ditemukan): {d}")
    return out


def main(daftar):
    fotos = kumpulkan(daftar)
    if not fotos:
        print("Tidak ada foto. Pakai: python scripts/bench_inferensi.py "
              "foto.jpg | folder/")
        sys.exit(1)
    inf = deteksi.get_inferensi()
    print("model :", deteksi.nama_model(kunci="model_gambar"))
    print("device:", deteksi.pilih_device(inf.get("device")))
    print("warming up (load model + inferensi pertama)...")
    deteksi.analisis_gambar(Path(fotos[0]).read_bytes(), conf=0.25)
    for f in fotos:
        raw = Path(f).read_bytes()
        print(f"\n== {Path(f).name} ({len(raw) // 1024} KB) ==")
        for nama, cfg in KONFIGS:
            deteksi.get_inferensi()["tta"] = cfg["tta"]
            t0 = time.perf_counter()
            hasil = deteksi.analisis_gambar(raw, conf=0.25, imgsz=cfg["imgsz"])
            dt = time.perf_counter() - t0
            print(f"  {nama:28s} {dt:5.2f} dtk   {len(hasil['rows'])} temuan")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Pakai: python scripts/bench_inferensi.py foto.jpg | folder/")
        sys.exit(1)
    main(sys.argv[1:])
