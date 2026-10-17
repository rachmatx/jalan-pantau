# -*- coding: utf-8 -*-
"""Uji hipotesis thread: apakah inferensi di thread baru (seperti request
Flask/Werkzeug) jauh lebih lambat daripada di main thread?

    python scripts/diag_thread.py test_foto/China_MotorBike_000382.jpg

Bila 'thread baru #1' ~10 dtk tapi '#2' (thread yang sama) ~0.7 dtk,
penyebabnya = biaya inisialisasi CUDA per-thread.
"""
import sys
import time
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "web"))
sys.path.insert(0, str(ROOT / "app"))

import deteksi  # noqa: E402


def main(foto):
    raw = Path(foto).read_bytes()
    print("warming up di main thread...")
    deteksi.analisis_gambar(raw, conf=0.25)

    t0 = time.perf_counter()
    deteksi.analisis_gambar(raw, conf=0.25)
    print(f"main thread      : {time.perf_counter() - t0:.2f} dtk")

    out = {}

    def kerja():
        t1 = time.perf_counter()
        deteksi.analisis_gambar(raw, conf=0.25)
        d1 = time.perf_counter() - t1
        t2 = time.perf_counter()
        deteksi.analisis_gambar(raw, conf=0.25)
        d2 = time.perf_counter() - t2
        out["d1"], out["d2"] = d1, d2

    th = threading.Thread(target=kerja)
    th.start()
    th.join()
    print(f"thread baru #1   : {out['d1']:.2f} dtk")
    print(f"thread baru #2   : {out['d2']:.2f} dtk (thread yang sama)")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Pakai: python scripts/diag_thread.py foto.jpg")
        sys.exit(1)
    main(sys.argv[1])
