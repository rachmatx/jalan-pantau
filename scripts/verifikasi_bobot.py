"""Verifikasi integritas bobot model (SHA-256) terhadap app/weights/SHA256SUMS.txt.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\verifikasi_bobot.py

Exit 0 bila semua cocok; 1 bila ada berkas yang hilang atau hash tidak cocok.
Berguna setelah mengunduh/menaruh bobot agar menjalankan model yang identik
dengan yang dilaporkan (reproduksibilitas).
"""
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "app" / "weights"
MANIFEST = WEIGHTS / "SHA256SUMS.txt"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blok in iter(lambda: f.read(1024 * 1024), b""):
            h.update(blok)
    return h.hexdigest()


def main():
    if not MANIFEST.is_file():
        print("Manifest tidak ada:", MANIFEST)
        return 1
    gagal = 0
    total = 0
    for baris in MANIFEST.read_text(encoding="utf-8").splitlines():
        baris = baris.strip()
        if not baris or baris.startswith("#"):
            continue
        bagian = baris.split()
        if len(bagian) != 2:
            continue
        harap, nama = bagian[0].lower(), bagian[1]
        total += 1
        f = WEIGHTS / nama
        if not f.is_file():
            print(f"[HILANG]  {nama}")
            gagal += 1
            continue
        nyata = sha256(f)
        if nyata == harap:
            print(f"[OK]      {nama}")
        else:
            print(f"[BEDA]    {nama}\n  harap: {harap}\n  nyata: {nyata}")
            gagal += 1
    print(f"\n{total - gagal}/{total} cocok")
    return 1 if gagal else 0


if __name__ == "__main__":
    raise SystemExit(main())
