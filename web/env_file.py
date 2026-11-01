"""Muat berkas .env (opsional) ke os.environ tanpa menimpa env yang sudah ada.

Harus dipanggil SEBELUM modul membaca os.environ (mis. database.AKUN_DEMO),
bukan saat create_app(), supaya nilai dari .env benar-benar berlaku.
`JP_ENV_FILE` bisa menunjuk berkas lain (dipakai tes).
"""
import os
from pathlib import Path

AKAR = Path(__file__).resolve().parent.parent


def muat_env_file(path=None):
    p = Path(path or os.environ.get("JP_ENV_FILE") or (AKAR / ".env"))
    if not p.is_file():
        return
    try:
        for baris in p.read_text(encoding="utf-8").splitlines():
            baris = baris.strip()
            if not baris or baris.startswith("#") or "=" not in baris:
                continue
            k, v = baris.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v
    except OSError:
        pass
