"""Ekstrak frame dari video untuk bahan data (kandidat negatif / unlabeled).

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\ekstrak_frame.py --video web/static/demo/demo_jalan.mp4 --setiap 0.25 --maks 20
    .\\.venv\\Scripts\\python scripts\\ekstrak_frame.py --video data/lokal/video --setiap 1.0

Catatan: frame berurutan dari video sering mirip; ambil interval agak longgar
agar beragam. Hasil dinilai manual / disaring lewat scripts/kandidat_negatif.py.
"""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EKST_VIDEO = {".mp4", ".avi", ".mov", ".mkv"}


def ekstrak(video, out_dir, setiap_detik, maks, lebar):
    import cv2
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        print("Gagal buka:", video)
        return 0
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    langkah = max(1, int(round(fps * setiap_detik)))
    out_dir.mkdir(parents=True, exist_ok=True)
    idx = simpan = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if idx % langkah == 0:
            if lebar and frame.shape[1] > lebar:
                skala = lebar / frame.shape[1]
                frame = cv2.resize(frame, (lebar, int(frame.shape[0] * skala)))
            cv2.imwrite(str(out_dir / f"{video.stem}_{simpan:04d}.jpg"), frame)
            simpan += 1
            if maks and simpan >= maks:
                break
        idx += 1
    cap.release()
    print(f"{video.name}: {simpan} frame -> {out_dir}")
    return simpan


def main():
    ap = argparse.ArgumentParser(description="Ekstrak frame dari video (bahan data).")
    ap.add_argument("--video", required=True, help="file video ATAU folder berisi video")
    ap.add_argument("--out", default=str(ROOT / "data" / "lokal" / "video-frames"))
    ap.add_argument("--setiap", type=float, default=1.0, help="1 frame tiap N detik (default 1.0)")
    ap.add_argument("--maks", type=int, default=0, help="batas frame per video (0=semua)")
    ap.add_argument("--lebar", type=int, default=1280, help="lebar maksimum hasil (0=asli)")
    args = ap.parse_args()

    src = Path(args.video)
    if not src.exists():
        print("Tidak ditemukan:", src)
        return 1
    vids = (sorted(p for p in src.rglob("*") if p.suffix.lower() in EKST_VIDEO)
            if src.is_dir() else [src])
    if not vids:
        print("Tidak ada berkas video.")
        return 1
    out = Path(args.out)
    total = sum(ekstrak(v, out, args.setiap, args.maks, args.lebar) for v in vids)
    print("Total frame:", total)
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
