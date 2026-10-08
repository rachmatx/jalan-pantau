"""Backup database SQLite (VACUUM INTO) ke folder backups/ dengan timestamp.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\backup_db.py
    .\\.venv\\Scripts\\python scripts\\backup_db.py --db web/instance/riwayat.db --out backups

`VACUUM INTO` menghasilkan salinan konsisten tanpa perlu menghentikan server.
Restore: hentikan server, salin berkas backup menimpa DB asli (simpan dulu
DB lama), lalu jalankan server kembali.
"""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "web" / "instance" / "riwayat.db"
DEFAULT_OUT = ROOT / "backups"


def main():
    ap = argparse.ArgumentParser(description="Backup DB SQLite (VACUUM INTO).")
    ap.add_argument("--db", default=str(DEFAULT_DB), help="path DB sumber")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="folder tujuan backup")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.is_file():
        print("DB tidak ditemukan:", db)
        return 1
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = out_dir / f"{db.stem}-{cap}.db"
    if target.exists():
        print("Sudah ada:", target)
        return 1

    con = sqlite3.connect(str(db))
    try:
        con.execute("VACUUM INTO ?", (str(target),))  # butuh SQLite >= 3.27
    finally:
        con.close()

    ukuran_kb = target.stat().st_size / 1024
    try:
        rel = target.relative_to(ROOT)
    except ValueError:
        rel = target
    print(f"Backup: {rel} ({ukuran_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
