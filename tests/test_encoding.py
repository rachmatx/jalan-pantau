"""Penjaga encoding: sumber dan halaman render harus bebas mojibake.

Mojibake di sini bukan termasuk bug lama. Saat Auditor memakai
`Set-Content -Encoding UTF8` di PowerShell 5.1 untuk menulis ulang
berkas, byte UTF-8 yang sudah ada dibaca sebagai teks lalu ditulis lagi
sebagai UTF-8. Setiap tulisan menambah satu lapis kerusakan, dan
tanda baca seperti em-dash jadi tampil sebagai 'a€"' di browser.

Jadi dua lapis dijaga:
  1. Sumber: berkas di repo tidak boleh memuat urutan byte mojibake.
  2. Render: HTML yang dikirim ke browser tidak boleh memuatnya juga,
     karena data yang masuk ke DB bisa sudah rusak dari luar.
"""
import glob
import os
import unittest

# Urutan byte hasil salah-decode CP1252, dalam bentuk teks UTF-8.
MOJIBAKE = {
    "\u00e2\u20ac\u201d": ("em-dash", "\u2014"),
    "\u00e2\u20ac\u00a2": ("bullet", "\u2022"),
    "\u00e2\u20ac\u00a6": ("ellipsis", "\u2026"),
    "\u00e2\u20ac\u00b9": ("guillemet-kiri", "\u2039"),
    "\u00e2\u20ac\u00ba": ("guillemet-kanan", "\u203a"),
    "\u00e2\u20ac\u201c": ("en-dash", "\u2013"),
    "\u00e2\u20ac\u0153": ("kutip-kiri", "\u201c"),
}

EXT = (".html", ".js", ".css", ".py", ".md", ".txt", ".json", ".yml", ".yaml")
LEWATI = {".git", ".venv", "__pycache__", "node_modules", ".kilo",
          ".commandcode", "_arsip", "backups", "artifacts", "runs", "data",
          "reports", "docs", "Obsidian Vault", "yolov11s-rdd-only"}

# Tanda baca non-ASCII yang SAH dan boleh muncul di teks Indonesia.
SAH = set("\u00b7\u2026\u2039\u203a\u2014\u2022\u00b1\u00d7\u00f7"
          "\u00a9\u00ae\u2019\u201c\u201d\u00e9\u00e8\u00e0\u00e2"  # é è à â
          "\u00f4\u00fb\u00e5\u00bf")


def berkas_sumber():
    out = []
    for akar, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in LEWATI]
        for fn in files:
            if fn.lower().endswith(EXT):
                out.append(os.path.join(akar, fn))
    return out


def carikunci(teks):
    """Kembalikan {(baris, jenis, karakter_benar)} untuk semua temuan."""
    out = []
    for i, ln in enumerate(teks.splitlines(), 1):
        for kunci, (jenis, benar) in MOJIBAKE.items():
            if kunci in ln:
                out.append((i, jenis, benar))
    return out


class TestEncoding(unittest.TestCase):
    def test_sumber_tidak_ada_mojibake(self):
        rusak = []
        for p in berkas_sumber():
            try:
                teks = open(p, "rb").read().decode("utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for baris, jenis, benar in carikunci(teks):
                rusak.append(f"{p}:{baris} [{jenis}] -> {ascii(benar)}")
        self.assertEqual(
            rusak, [],
            "Mojibake di sumber (tanda baca salah-decode):\n  "
            + "\n  ".join(rusak[:40]))

    def test_sumber_tidak_punya_bom(self):
        """BOM hasil Set-Content PowerShell tidak merusak render, tapi
        membuat diff satu baris utuh dan menyesatkan tooling."""
        salah = []
        for p in berkas_sumber():
            try:
                with open(p, "rb") as fh:
                    raw = fh.read(3)
            except OSError:
                continue
            if raw == b"\xef\xbb\xbf":
                salah.append(p)
        self.assertEqual(salah, [], "Berkas bereksan BOM UTF-8:\n  "
                         + "\n  ".join(salah))

    def test_halaman_render_tidak_ada_mojibake(self):
        """Periksa HTML yang benar-benar dikirim ke browser."""
        import shutil
        import tempfile
        src = "web/instance/riwayat.db"
        if not os.path.exists(src):
            self.skipTest("database tidak ada")
        tmp = os.path.join(tempfile.gettempdir(), "guard_enc.db")
        shutil.copyfile(src, tmp)

        import web.app as app_mod
        app = app_mod.create_app()
        app.config["DB_PATH"] = tmp
        app.config["TESTING"] = True
        c = app.test_client()

        dicek = 0
        for path in ("/", "/riwayat", "/peta", "/tentang", "/login"):
            r = c.get(path)
            if r.status_code != 200:
                continue
            dicek += 1
            html = r.get_data(as_text=True)
            for kunci, (jenis, benar) in MOJIBAKE.items():
                self.assertNotIn(
                    kunci, html,
                    f"{path} mengirim mojibake [{jenis}]; seharusnya {ascii(benar)}")
        self.assertGreater(dicek, 0, "tidak ada halaman yang sempat dicek")

    def test_halaman_punya_meta_charset(self):
        import shutil
        import tempfile
        src = "web/instance/riwayat.db"
        if not os.path.exists(src):
            self.skipTest("database tidak ada")
        tmp = os.path.join(tempfile.gettempdir(), "guard_enc2.db")
        shutil.copyfile(src, tmp)

        import web.app as app_mod
        app = app_mod.create_app()
        app.config["DB_PATH"] = tmp
        app.config["TESTING"] = True
        c = app.test_client()
        html = c.get("/riwayat").get_data(as_text=True)
        self.assertIn('<meta charset="utf-8"', html.lower())