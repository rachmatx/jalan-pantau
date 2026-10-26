"""Gambar hasil deteksi sementara: token acak -> satu file JPEG.

Gambar anotasi tidak lagi dikirim bolak-balik sebagai base64 (detect -> simpan
riwayat -> PDF). Server menulisnya sekali, klien hanya memegang token; token
dipakai untuk <img>, simpan riwayat, dan PDF.

Berkas kedaluwarsa dibersihkan oportunistik setiap ada gambar baru. Batas
jumlah berkas mencegah /api/detect (publik, rate-limited) memenuhi disk.
"""
import os
import re
import secrets
import time
from pathlib import Path

from flask import current_app

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
TTL_DETIK = 6 * 3600
MAKS_BERKAS = 200


def _folder() -> Path:
    folder = Path(current_app.config["DB_PATH"]).parent / "tmp"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def simpan(jpg: bytes) -> str:
    folder = _folder()
    token = secrets.token_urlsafe(18)
    while (folder / f"{token}.jpg").exists():
        token = secrets.token_urlsafe(18)
    # Tulis atomik: route gambar tidak boleh menyajikan file yang separuh jadi.
    sementara = folder / f".{token}.part"
    sementara.write_bytes(jpg)
    os.replace(sementara, folder / f"{token}.jpg")
    bersihkan(folder)
    return token


def path(token) -> Path | None:
    if not isinstance(token, str) or TOKEN_RE.fullmatch(token) is None:
        return None
    p = _folder() / f"{token}.jpg"
    return p if p.is_file() else None


def bersihkan(folder: Path | None = None) -> None:
    folder = folder or _folder()
    berkas = []
    for p in folder.glob("*.jpg"):
        try:
            berkas.append((p.stat().st_mtime, p))
        except OSError:
            continue
    berkas.sort()
    batas = time.time() - TTL_DETIK
    for mtime, p in berkas:
        if mtime < batas:
            _hapus(p)
    hidup = [(mtime, p) for mtime, p in berkas if mtime >= batas]
    for _, p in hidup[:max(0, len(hidup) - MAKS_BERKAS)]:
        _hapus(p)


def _hapus(p: Path) -> None:
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
