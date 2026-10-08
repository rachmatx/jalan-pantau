"""Validasi kalibrasi `pixels_per_cm`: hitung galat ukuran (cm) terhadap acuan nyata.

Input CSV (lihat docs/contoh-validasi/kalibrasi.csv):
    nama,panjang_px,panjang_cm_nyata,ppc
- `ppc` boleh dikosongkan per baris; baris tanpa ppc memakai --ppc
  (default: dibaca dari config/severity.yaml bila ada).

Pakai:
    .\\.venv\\Scripts\\python scripts\\validasi_kalibrasi.py
    .\\.venv\\Scripts\\python scripts\\validasi_kalibrasi.py --csv data.csv --ppc 11.4342

Keluaran: galat per objek + ringkasan (MAE, MAPE, bias, galat maksimum).
"""
import argparse
import csv
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "docs" / "contoh-validasi" / "kalibrasi.csv"


def ppc_dari_config():
    try:
        import yaml
        data = yaml.safe_load((ROOT / "config" / "severity.yaml").read_text(encoding="utf-8"))
        for jalur in (("kalibrasi", "pixels_per_cm"), ("pixels_per_cm",)):
            node = data
            for k in jalur:
                node = (node or {}).get(k) if isinstance(node, dict) else None
            if node:
                return float(node)
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser(description="Validasi galat kalibrasi pixels_per_cm.")
    ap.add_argument("--csv", default=str(DEFAULT_CSV), help="path CSV masukan")
    ap.add_argument("--ppc", type=float, default=None,
                    help="pixels_per_cm default (bila kolom ppc kosong)")
    args = ap.parse_args()

    ppc_default = args.ppc if args.ppc is not None else ppc_dari_config()
    path = Path(args.csv)
    if not path.is_file():
        print("CSV tidak ditemukan:", path)
        return 1

    baris = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                px = float(r["panjang_px"])
                nyata = float(r["panjang_cm_nyata"])
            except (KeyError, TypeError, ValueError):
                continue
            ppc = float(r["ppc"]) if (r.get("ppc") or "").strip() else ppc_default
            if not ppc:
                print(f"  (skip '{r.get('nama')}' — ppc tidak ada)")
                continue
            terukur = px / ppc
            baris.append({
                "nama": r.get("nama", "-"),
                "nyata": nyata,
                "terukur": terukur,
                "err": terukur - nyata,
                "err_pct": (terukur - nyata) / nyata * 100.0 if nyata else 0.0,
            })

    if not baris:
        print("Tidak ada baris valid. Isi docs/contoh-validasi/kalibrasi.csv dulu.")
        return 1

    print(f"ppc default: {ppc_default if ppc_default else '(per baris)'}\n")
    print(f"{'objek':28s} {'nyata':>8s} {'terukur':>8s} {'err_cm':>8s} {'err_%':>8s}")
    for b in baris:
        print(f"{b['nama'][:28]:28s} {b['nyata']:8.2f} {b['terukur']:8.2f} "
              f"{b['err']:8.2f} {b['err_pct']:8.2f}")

    abs_err = [abs(b["err"]) for b in baris]
    abs_pct = [abs(b["err_pct"]) for b in baris]
    print("\nRingkasan:")
    print(f"  n           : {len(baris)}")
    print(f"  MAE (cm)    : {statistics.fmean(abs_err):.3f}")
    print(f"  MAPE (%)    : {statistics.fmean(abs_pct):.3f}")
    print(f"  galat maks  : {max(abs_err):.3f} cm")
    print(f"  bias (cm)   : {statistics.fmean(b['err'] for b in baris):+.3f} "
          "(positif = cenderung lebih besar dari nyata)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
