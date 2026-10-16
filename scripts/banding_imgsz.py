"""Bandingkan imgsz 640/960/1280 memakai best.pt (ultralytics) — jalan di komputer user.

Cara pakai (di folder repo, venv aktif):
    python scripts/banding_imgsz.py
"""
import sys
import time
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parents[1]
SIZES = [640, 960, 1280]
CONF, IOU = 0.25, 0.5


def iou_xyxy(a, b):
    xx1, yy1 = max(a[0], b[0]), max(a[1], b[1])
    xx2, yy2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, xx2 - xx1) * max(0, yy2 - yy1)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / (ua + 1e-9)


def main():
    model = YOLO(str(ROOT / "app" / "weights" / "best.pt"))
    fotos = sorted((ROOT / "test_foto").glob("China_MotorBike_*.jpg"))
    if not fotos:
        print("Tidak ada foto di test_foto/")
        return
    hasil = {sz: {"n": 0, "conf": [], "ms": []} for sz in SIZES}
    baru_1280 = []
    for fp in fotos:
        det = {}
        for sz in SIZES:
            t0 = time.perf_counter()
            r = model.predict(str(fp), imgsz=sz, conf=CONF, iou=IOU, verbose=False)[0]
            ms = (time.perf_counter() - t0) * 1000
            d = [(model.names[int(c)], float(cf), tuple(map(float, b)))
                 for b, cf, c in zip(r.boxes.xyxy.cpu().numpy(),
                                     r.boxes.conf.cpu().numpy(),
                                     r.boxes.cls.cpu().numpy())]
            det[sz] = d
            hasil[sz]["n"] += len(d)
            hasil[sz]["conf"].extend([x[1] for x in d])
            hasil[sz]["ms"].append(ms)
        baru = sum(1 for c1, _, b1 in det[1280]
                   if not any(c1 == c0 and iou_xyxy(b1, b0) > 0.5
                              for c0, _, b0 in det[640]))
        baru_1280.append(baru)
    n = len(fotos)
    print(f"\n{'imgsz':>6} | {'total':>6} | {'rata2/foto':>10} | {'mean conf':>9} | {'mean ms':>8}")
    for sz in SIZES:
        h = hasil[sz]
        mc = sum(h["conf"]) / len(h["conf"]) if h["conf"] else 0
        print(f"{sz:>6} | {h['n']:>6} | {h['n']/n:>10.1f} | {mc:>9.3f} | "
              f"{sum(h['ms'])/len(h['ms']):>8.1f}")
    print(f"\nDeteksi 'baru' di 1280 yang tak ada di 640: {sum(baru_1280)} "
          f"(per foto: {baru_1280})")
    print("Catatan: tanpa ground truth, 'baru' belum tentu benar — "
          "cek visual beberapa contoh.")


if __name__ == "__main__":
    main()
