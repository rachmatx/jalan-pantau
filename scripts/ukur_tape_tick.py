"""Ukur pitch tanda skala pada pita meteran dari foto (untuk kalibrasi px/cm).

Metode: segmentasi warna kuning (pita) -> deteksi baris bertanda gelap (tick)
di dalam pita -> median jarak antar-tick = pitch skala.

Hasil dipakai untuk mengecek silang asumsi ukuran objek (tile 30/60 cm) dan
satuan meteran (mm vs inci). Tidak menulis apa pun; hanya melaporkan.

Pakai:
    .\\.venv\\Scripts\\python scripts/ukur_tape_tick.py --gambar "web/static/demo/jarak foto 49 - 53 cm.jpg"
"""
import argparse
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gambar", required=True)
    args = ap.parse_args()

    p = Path(args.gambar)
    if not p.is_absolute():
        p = ROOT / args.gambar
    img = cv2.imread(str(p))
    if img is None:
        raise SystemExit(f"Gagal buka {p}")
    h, w = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    kuning = cv2.inRange(hsv, (18, 70, 120), (42, 255, 255))

    kol = kuning.sum(axis=0) / 255.0
    if kol.max() <= 0:
        raise SystemExit("Pita meteran (kuning) tidak terdeteksi.")
    batas = kol >= kol.max() * 0.4
    xs = np.where(batas)[0]
    x0, x1 = int(xs.min()), int(xs.max())
    print(f"pita meteran: x {x0}..{x1} (lebar {x1-x0} px)")

    abu = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    pita = abu[:, x0:x1 + 1]
    gelap = (pita < 90).sum(axis=1)          # piksel gelap (tick hitam) per baris
    amb = max(3, int(gelap.max() * 0.35))
    puncak = []
    i = 0
    while i < len(gelap):
        if gelap[i] >= amb:
            j = i
            while j + 1 < len(gelap) and gelap[j + 1] >= amb:
                j += 1
            puncak.append((i + j) / 2)
            i = j + 1
        else:
            i += 1
    if len(puncak) < 3:
        raise SystemExit("Tick terlalu sedikit terdeteksi.")

    jarak = np.diff(puncak)
    med = float(np.median(jarak))
    print(f"jumlah tick : {len(puncak)}")
    print(f"pitch median: {med:.2f} px  (min {jarak.min():.1f}, maks {jarak.max():.1f})")
    print(f"rentang tick: {puncak[0]:.0f}..{puncak[-1]:.0f} px "
          f"(total {puncak[-1]-puncak[0]:.0f} px, {len(puncak)-1} interval)")

    print("\n-- hipotesis --")
    print(f"jika tick = 1 mm  -> {med*10:.2f} px/cm  (pita {puncak[-1]-puncak[0]:.0f}px = "
          f"{(puncak[-1]-puncak[0])/ (med*10):.1f} cm)")
    print(f"jika tick = 1/16\" -> {med*2.54*16:.2f} px/cm (pita = "
          f"{(puncak[-1]-puncak[0]) / (med*2.54*16) * 2.54:.1f} cm)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
