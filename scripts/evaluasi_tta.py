"""Evaluasi P/R/F1 dengan pencocokan IoU — mendukung TTA (augment=True).

Alasan: `model.val()` ultralytics TIDAK menerapkan TTA, padahal jalur gambar
aplikasi memakai TTA. Skrip ini menghitung Precision/Recall/F1 pada satu titik
operasi (conf) dengan pencocokan IoU 0.5 per kelas, sehingga perbandingan
antar-model / dengan-vs-tanpa-TTA menjadi adil.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\evaluasi_tta.py --model best_yolo11s.pt --imgsz 960 --maks 60
    .\\.venv\\Scripts\\python scripts\\evaluasi_tta.py --model best_yolo11s.pt --imgsz 960 --maks 60 --augment
    .\\.venv\\Scripts\\python scripts\\evaluasi_tta.py --model best.onnx --imgsz 640 --maks 60
"""
import argparse
import json
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "app" / "weights"
REPORTS = ROOT / "reports"
EKST_IMG = {".jpg", ".jpeg", ".png"}
IOU_MIN = 0.5


def baca_gt(label_path, w, h, remap):
    """YOLO txt -> daftar (cls, x1, y1, x2, y2) dalam piksel."""
    keluar = []
    if not label_path.is_file():
        return keluar
    for baris in label_path.read_text(encoding="utf-8").splitlines():
        s = baris.split()
        if len(s) < 5:
            continue
        c = remap.get(int(s[0]), int(s[0]))
        cx, cy, bw, bh = (float(v) for v in s[1:5])
        keluar.append((c,
                       (cx - bw / 2) * w, (cy - bh / 2) * h,
                       (cx + bw / 2) * w, (cy + bh / 2) * h))
    return keluar


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter)


def cocokkan(pred, gt):
    """Greedy per kelas: pred diurut conf desc -> TP/FP/FN.

    `gt` = daftar (cls, x1, y1, x2, y2); `pred` = daftar (cls, box, conf).
    """
    tp = fp = 0
    dipakai = set()
    for pcls, pbox, pconf in pred:
        terbaik, idx_terbaik = 0.0, None
        for i, g in enumerate(gt):
            if i in dipakai or g[0] != pcls:
                continue
            v = iou(pbox, g[1:])
            if v > terbaik:
                terbaik, idx_terbaik = v, i
        if idx_terbaik is not None and terbaik >= IOU_MIN:
            dipakai.add(idx_terbaik)
            tp += 1
        else:
            fp += 1
    fn = len(gt) - len(dipakai)
    return tp, fp, fn


def main():
    ap = argparse.ArgumentParser(description="Evaluasi P/R/F1 (IoU) dengan/TANPA TTA.")
    ap.add_argument("--data", default="data/publik/bpid/test")
    ap.add_argument("--model", default="best_yolo11s.pt")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--augment", action="store_true", help="aktifkan TTA")
    ap.add_argument("--maks", type=int, default=60, help="batasi jumlah gambar (0=semua)")
    ap.add_argument("--remap", default="0:4")
    args = ap.parse_args()

    from PIL import Image
    from ultralytics import YOLO

    mp = Path(args.model)
    if not mp.is_absolute():
        mp = WEIGHTS / args.model
    if not mp.is_file():
        raise SystemExit(f"Bobot tidak ditemukan: {mp}")

    remap = {}
    for p in filter(None, args.remap.split(",")):
        a, b = p.split(":")
        remap[int(a)] = int(b)

    data = ROOT / args.data
    img_dir, lbl_dir = data / "images", data / "labels"
    gambar = sorted(p for p in img_dir.iterdir() if p.suffix.lower() in EKST_IMG)
    if args.maks:
        gambar = gambar[:args.maks]
    if not gambar:
        raise SystemExit(f"Tidak ada gambar di {img_dir}")

    model = YOLO(str(mp))
    tp = fp = fn = 0
    t0 = time.perf_counter()
    for p in gambar:
        with Image.open(p) as im:
            w, h = im.size
        gt = baca_gt(lbl_dir / (p.stem + ".txt"), w, h, remap)
        r = model.predict(str(p), imgsz=args.imgsz, conf=args.conf,
                          augment=args.augment, verbose=False)[0]
        pred = [(int(b.cls), tuple(float(v) for v in b.xyxy[0]), float(b.conf))
                for b in r.boxes]
        pred.sort(key=lambda x: -x[2])
        a, b2, c = cocokkan(pred, gt)
        tp += a; fp += b2; fn += c
    durasi = time.perf_counter() - t0

    P = tp / (tp + fp) if (tp + fp) else 0.0
    R = tp / (tp + fn) if (tp + fn) else 0.0
    F1 = (2 * P * R / (P + R)) if (P + R) else 0.0
    nama = mp.name
    print(f"\nmodel={nama} imgsz={args.imgsz} conf={args.conf} "
          f"TTA={'ON' if args.augment else 'off'} n={len(gambar)}")
    print(f"  TP {tp} | FP {fp} | FN {fn}")
    print(f"  Precision {P:.4f} | Recall {R:.4f} | F1 {F1:.4f} | {durasi/len(gambar):.2f}s/gambar")

    REPORTS.mkdir(exist_ok=True)
    cap = datetime.now().strftime("%Y%m%d-%H%M%S")
    keluar = REPORTS / f"evaluasi-tta-{cap}.json"
    keluar.write_text(json.dumps({
        "model": nama, "imgsz": args.imgsz, "conf": args.conf,
        "tta": bool(args.augment), "n_gambar": len(gambar),
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(P, 4), "recall": round(R, 4), "f1": round(F1, 4),
        "detik_per_gambar": round(durasi / len(gambar), 3),
        "dibuat": datetime.now().isoformat(timespec="seconds"),
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Artefak: {keluar.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
