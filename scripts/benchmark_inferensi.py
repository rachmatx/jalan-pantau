"""Benchmark latensi inferensi YOLO (CPU) untuk JalanPantau.

Mengukur waktu inferensi per gambar (mean / median / p95) pada model & imgsz
tertentu, lalu menulis artefak JSON ke ``artifacts/`` supaya klaim performa
punya sumber yang bisa diaudit (bukan angka tanpa jejak).

Contoh pemakaian (dari root repo):
    .\\.venv\\Scripts\\python scripts\\benchmark_inferensi.py --runs 20
    .\\.venv\\Scripts\\python scripts\\benchmark_inferensi.py --model best_yolo11s.pt --imgsz 960
    .\\.venv\\Scripts\\python scripts\\benchmark_inferensi.py --model best.onnx --imgsz 480

Catatan: ini mengukur inferensi GAMBAR STATIS. FPS live (webcam) bergantung
sumber kamera + 3-thread decouple di web/streaming.py — ukur lewat UI live
(stat "FPS Tampil" / "FPS Inferensi") dan catat hasilnya secara manual.
"""
from __future__ import annotations

import argparse
import json
import platform
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "app" / "weights"
ARTIFACTS = ROOT / "artifacts"
CONTOH_GAMBAR = [
    ROOT / "data" / "publik" / "bpid" / "test" / "images",
    ROOT / "data" / "lokal" / "foto",
]


def cari_gambar(eksplisit):
    """Gambar uji: pakai --gambar bila ada, else cari .jpg/.jpeg/.png pertama
    di folder data contoh."""
    if eksplisit:
        p = Path(eksplisit)
        if not p.is_file():
            raise SystemExit(f"Gambar tidak ditemukan: {p}")
        return p
    for folder in CONTOH_GAMBAR:
        if folder.is_dir():
            for pola in ("*.jpg", "*.jpeg", "*.png"):
                kandidat = sorted(folder.glob(pola))
                if kandidat:
                    return kandidat[0]
    raise SystemExit("Tidak ada gambar uji. Berikan --gambar path/ke/foto.jpg")


def _persentil(nilai, p):
    """Persentil sederhana (interpolasi linear) — stdlib saja."""
    if not nilai:
        return float("nan")
    urut = sorted(nilai)
    if len(urut) == 1:
        return urut[0]
    pos = (len(urut) - 1) * p
    bawah = int(pos)
    atas = min(bawah + 1, len(urut) - 1)
    frac = pos - bawah
    return urut[bawah] * (1 - frac) + urut[atas] * frac


def benchmark(model_name, imgsz, runs, gambar, conf, warmup):
    from ultralytics import YOLO  # import lambat: hanya bila script dijalankan

    model_path = Path(model_name)
    if not model_path.is_absolute():
        model_path = WEIGHTS / model_name
    if not model_path.is_file():
        raise SystemExit(f"Bobot tidak ditemukan: {model_path}")

    model = YOLO(str(model_path))

    # Warmup (tidak dihitung): inisialisasi graph/runtime + cache ONNX.
    for _ in range(max(1, warmup)):
        model.predict(source=str(gambar), imgsz=imgsz, conf=conf, verbose=False)

    waktu_ms = []
    for _ in range(runs):
        t0 = time.perf_counter()
        model.predict(source=str(gambar), imgsz=imgsz, conf=conf, verbose=False)
        waktu_ms.append((time.perf_counter() - t0) * 1000.0)

    rata = statistics.fmean(waktu_ms)
    try:
        rel = str(gambar.relative_to(ROOT))
    except ValueError:
        rel = str(gambar)
    return {
        "model": model_path.name,
        "format": "onnx" if model_path.suffix.lower() == ".onnx" else "pytorch",
        "imgsz": imgsz,
        "conf": conf,
        "runs": runs,
        "warmup": warmup,
        "gambar": rel,
        "latency_ms": {
            "mean": round(rata, 2),
            "median": round(statistics.median(waktu_ms), 2),
            "p95": round(_persentil(waktu_ms, 0.95), 2),
            "min": round(min(waktu_ms), 2),
            "max": round(max(waktu_ms), 2),
        },
        "fps_from_mean": round(1000.0 / rata, 2) if rata > 0 else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Benchmark latensi inferensi YOLO (CPU).")
    ap.add_argument("--model", default="best_yolo11s.pt",
                    help="nama file di app/weights/ atau path penuh (default: best_yolo11s.pt)")
    ap.add_argument("--imgsz", type=int, default=960, help="ukuran input (default: 960)")
    ap.add_argument("--runs", type=int, default=15, help="jumlah iterasi terukur (default: 15)")
    ap.add_argument("--warmup", type=int, default=2, help="iterasi pemanasan (default: 2)")
    ap.add_argument("--conf", type=float, default=0.25, help="ambang confidence (default: 0.25)")
    ap.add_argument("--gambar", default=None, help="path gambar uji (default: otomatis)")
    args = ap.parse_args()

    gambar = cari_gambar(args.gambar)
    hasil = benchmark(args.model, args.imgsz, args.runs, gambar, args.conf, args.warmup)
    hasil["dibuat"] = datetime.now().isoformat(timespec="seconds")
    hasil["hardware"] = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
    }

    ARTIFACTS.mkdir(exist_ok=True)
    cap = datetime.now().strftime("%Y%m%d-%H%M%S")
    keluar = ARTIFACTS / f"benchmark-inferensi-{cap}.json"
    keluar.write_text(json.dumps(hasil, indent=2, ensure_ascii=False), encoding="utf-8")

    lat = hasil["latency_ms"]
    print("\n=== Benchmark inferensi ===")
    print(f"model   : {hasil['model']} ({hasil['format']})")
    print(f"imgsz   : {hasil['imgsz']}  conf: {hasil['conf']}  runs: {hasil['runs']}")
    print(f"latency : mean {lat['mean']} ms | median {lat['median']} ms | "
          f"p95 {lat['p95']} ms | min {lat['min']} | max {lat['max']}")
    print(f"FPS     : {hasil['fps_from_mean']} (dari rata-rata latency)")
    print(f"artefak : {keluar.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
