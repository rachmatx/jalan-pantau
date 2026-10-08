"""Validasi klasifikasi severity: confusion matrix + akurasi terhadap label manual.

Input CSV (lihat docs/contoh-validasi/severity.csv):
    prediksi,aktual
Nilai: Ringan / Sedang / Berat (tidak peka huruf besar-kecil).

Pakai:
    .\\.venv\\Scripts\\python scripts\\validasi_severity.py
    .\\.venv\\Scripts\\python scripts\\validasi_severity.py --csv data.csv
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "docs" / "contoh-validasi" / "severity.csv"
KELAS = ["Ringan", "Sedang", "Berat"]


def normal(v):
    s = str(v or "").strip().lower()
    for k in KELAS:
        if s == k.lower():
            return k
    return None


def main():
    ap = argparse.ArgumentParser(description="Validasi severity (confusion matrix).")
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="path CSV masukan")
    args = ap.parse_args()

    path = Path(args.csv)
    if not path.is_file():
        print("CSV tidak ditemukan:", path)
        return 1

    pasangan = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            p, a = normal(r.get("prediksi")), normal(r.get("aktual"))
            if p and a:
                pasangan.append((p, a))
    if not pasangan:
        print("Tidak ada baris valid. Isi docs/contoh-validasi/severity.csv dulu.")
        return 1

    # matriks[aktual][prediksi]
    matriks = {a: {p: 0 for p in KELAS} for a in KELAS}
    for p, a in pasangan:
        matriks[a][p] += 1

    benar = sum(matriks[k][k] for k in KELAS)
    total = len(pasangan)
    print(f"n = {total}  akurasi = {benar}/{total} = {benar / total * 100:.1f}%\n")

    judul = "aktual \\ prediksi"
    print(f"{judul:18s}" + "".join(f"{p:>9s}" for p in KELAS) + f"{'recall':>10s}")
    for a in KELAS:
        baris_total = sum(matriks[a].values())
        recall = matriks[a][a] / baris_total * 100 if baris_total else 0.0
        print(f"{a:18s}" + "".join(f"{matriks[a][p]:>9d}" for p in KELAS) + f"{recall:>9.1f}%")

    print(f"\n{'precision':18s}", end="")
    for p in KELAS:
        kolom_total = sum(matriks[a][p] for a in KELAS)
        prec = matriks[p][p] / kolom_total * 100 if kolom_total else 0.0
        print(f"{prec:>8.1f}%", end="")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
