"""Pilih kandidat gambar NEGATIF (jalan tanpa kerusakan) dengan menjalankan model.

Gambar yang TIDAK menghasilkan deteksi di atas ambang conf dianggap kandidat
negatif (background) -> dipakai untuk hard-negative mining.

PENTING: WAJIB ditinjau manual sebelum dipakai. Model bisa "luput" mendeteksi
kerusakan asli, sehingga kandidat ini bukan negatif yang pasti benar.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\kandidat_negatif.py --in data/lokal/video-frames --out data/lokal/negatif-kandidat
    .\\.venv\\Scripts\\python scripts\\kandidat_negatif.py --in data/lokal/foto --conf 0.3
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "app" / "weights"
EKST = {".jpg", ".jpeg", ".png"}


def main():
    ap = argparse.ArgumentParser(description="Pilih kandidat negatif via model deteksi.")
    ap.add_argument("--in", dest="masuk", required=True, help="folder berisi gambar (rekursif)")
    ap.add_argument("--out", dest="keluar",
                    default=str(ROOT / "data" / "lokal" / "negatif-kandidat"))
    ap.add_argument("--model", default="best_yolo11s.pt",
                    help="nama di app/weights/ atau path penuh")
    ap.add_argument("--imgsz", type=int, default=960)
    ap.add_argument("--conf", type=float, default=0.25)
    args = ap.parse_args()

    from ultralytics import YOLO
    mp = Path(args.model)
    if not mp.is_absolute():
        mp = WEIGHTS / args.model
    if not mp.is_file():
        print("Bobot tidak ditemukan:", mp)
        return 1
    model = YOLO(str(mp))

    masuk = Path(args.masuk)
    keluar = Path(args.keluar)
    if not masuk.is_dir():
        print("Folder tidak ditemukan:", masuk)
        return 1
    keluar.mkdir(parents=True, exist_ok=True)
    gambar = sorted(p for p in masuk.rglob("*") if p.suffix.lower() in EKST)
    if not gambar:
        print("Tidak ada gambar di", masuk)
        return 1

    n_neg = 0
    for p in gambar:
        r = model.predict(str(p), imgsz=args.imgsz, conf=args.conf, verbose=False)[0]
        if len(r.boxes) == 0:
            shutil.copy(p, keluar / p.name)
            n_neg += 1
    print(f"{n_neg}/{len(gambar)} kandidat negatif -> {keluar}")
    print("TINJAU MANUAL sebelum dipakai (model bisa luput mendeteksi kerusakan).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
