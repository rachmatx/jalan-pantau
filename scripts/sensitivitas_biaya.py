"""Analisis sensitivitas biaya: pengaruh variasi harga acuan terhadap total.

Karena `config/harga_acuan.csv` adalah indeks biaya relatif (bukan RAB), total
rupiah bergantung pada asumsi harga. Skrip ini menunjukkan sebaran total bila
seluruh harga naik/turun sekian persen — supaya angka tidak diklaim sebagai pasti.

Pakai:
    .\\.venv\\Scripts\\python scripts\\sensitivitas_biaya.py --total 1857000
    .\\.venv\\Scripts\\python scripts\\sensitivitas_biaya.py --total 1857000 --langkah 5 --rentang 30
"""
import argparse


def rupiah(n):
    return "Rp" + f"{round(n):,}".replace(",", ".")


def main():
    ap = argparse.ArgumentParser(description="Sensitivitas total biaya terhadap variasi harga.")
    ap.add_argument("--total", type=float, required=True, help="total biaya acuan (Rp)")
    ap.add_argument("--rentang", type=float, default=20, help="variasi maksimum dalam %% (default 20)")
    ap.add_argument("--langkah", type=float, default=10, help="langkah dalam %% (default 10)")
    args = ap.parse_args()

    n = int(args.rentang // args.langkah)
    print(f"Total acuan: {rupiah(args.total)}  (indeks biaya relatif, bukan RAB)\n")
    print(f"{'variasi':>9s} {'total':>16s} {'selisih':>16s}")
    for i in range(-n, n + 1):
        pct = i * args.langkah
        tot = args.total * (1 + pct / 100.0)
        print(f"{pct:>8.0f}% {rupiah(tot):>16s} {rupiah(tot - args.total):>16s}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
