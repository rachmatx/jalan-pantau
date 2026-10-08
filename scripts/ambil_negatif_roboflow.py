"""Ambil gambar NEGATIF dari ekspor Roboflow (format YOLO) — yaitu gambar yang
file labelnya kosong / tidak ada (tidak punya anotasi objek).

Ini cara mengambil kandidat "background / jalan tanpa kerusakan" dari dataset
Roboflow (mis. filter `class:null` = gambar tanpa anotasi).

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\ambil_negatif_roboflow.py --dir data/lokal/roboflow --out data/lokal/negatif-roboflow
    .\\.venv\\Scripts\\python scripts\\ambil_negatif_roboflow.py --dir data/lokal/roboflow --out data/lokal/negatif-roboflow --maks 300

Struktur ekspor YOLO Roboflow yang didukung (dicari otomatis, rekursif):
    <dir>/train/images/*.jpg  +  <dir>/train/labels/*.txt
    <dir>/valid/images/*.jpg  +  <dir>/valid/labels/*.txt
    <dir>/test/images/*.jpg   +  <dir>/test/labels/*.txt
Label dianggap "negatif" bila: file .txt tidak ada, ATAU isinya kosong.
WAJIB ditinjau manual (tanpa anotasi != pasti tidak ada kerusakan).
"""
import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EKST_IMG = {".jpg", ".jpeg", ".png"}


def _label_untuk(img: Path) -> Path | None:
    """Cari file label .txt yang berpasangan dengan gambar."""
    # 1) label di folder 'labels' sejajar 'images'
    parts = list(img.parts)
    if "images" in parts:
        idx = len(parts) - 1 - parts[::-1].index("images")
        cand = Path(*parts[:idx], "labels", img.stem + ".txt")
        if cand.is_file():
            return cand
        return cand  # belum ada -> dianggap tanpa anotasi
    # 2) label di folder yang sama
    return img.with_suffix(".txt")


def main():
    ap = argparse.ArgumentParser(description="Ambil gambar negatif (label kosong) dari ekspor YOLO Roboflow.")
    ap.add_argument("--dir", required=True, help="folder hasil ekspor Roboflow")
    ap.add_argument("--out", default=str(ROOT / "data" / "lokal" / "negatif-roboflow"))
    ap.add_argument("--maks", type=int, default=0, help="batas jumlah gambar disalin (0=semua)")
    args = ap.parse_args()

    src = Path(args.dir)
    if not src.is_dir():
        print("Folder tidak ditemukan:", src)
        return 1
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    gambar = sorted(p for p in src.rglob("*") if p.suffix.lower() in EKST_IMG)
    if not gambar:
        print("Tidak ada gambar di", src)
        return 1

    negatif, positif, tanpa_label = [], 0, 0
    for p in gambar:
        lp = _label_untuk(p)
        if lp is None or not lp.is_file():
            tanpa_label += 1
            negatif.append(p)
        elif not lp.read_text(encoding="utf-8", errors="ignore").strip():
            negatif.append(p)  # label ada tapi kosong
        else:
            positif += 1

    if args.maks:
        negatif = negatif[:args.maks]
    for p in negatif:
        shutil.copy(p, out / p.name)

    print(f"Total gambar   : {len(gambar)}")
    print(f"Berlabel (positif): {positif}")
    print(f"Tanpa file label : {tanpa_label}")
    print(f"Negatif (label kosong/tanpa): {len(negatif)} -> {out}")
    print("TINJAU MANUAL sebelum dipakai (tanpa anotasi belum tentu tanpa kerusakan).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
