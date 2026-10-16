"""Penjaga kontrak CSS<->JS untuk viewer zoom (.zoom-inner).

zoom.js memposisikan gambar lewat `transform: translate(...) scale(...)` dan
menghitung koordinat terhadap sudut KIRI-ATAS elemen. Kalau `.zoom-inner`
tidak menetapkan `transform-origin: 0 0`, CSS memakai default `50% 50%` dari
wadah yang setinggi gambar mentah (mis. foto 12 MP). Skala lalu mendorong
gambar jauh ke bawah area viewer yang ber-overflow hidden -> panel tampak
kosong walau gambar sudah termuat. Regresi ini pernah terjadi di halaman
Deteksi/Live, jadi dikunci lewat tes.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CIVIC = os.path.join(ROOT, "web", "static", "css", "civic.css")
ZOOM_JS = os.path.join(ROOT, "web", "static", "js", "zoom.js")

# zoom.js selalu mengemas konten viewer ke dalam div ini.
KELAS_INNER = "zoom-inner"


class TestZoomInnerOrigin(unittest.TestCase):
    def test_civic_menetapkan_transform_origin_kiri_atas(self):
        with open(CIVIC, encoding="utf-8") as fh:
            css = fh.read()
        m = re.search(r"\.%s\s*\{([^}]*)\}" % KELAS_INNER, css)
        self.assertIsNotNone(
            m, f".{KELAS_INNER} tidak ditemukan di {CIVIC}")
        blok = m.group(1)
        self.assertRegex(
            blok, r"transform-origin\s*:\s*0(?:px)?\s+0(?:px)?",
            f".{KELAS_INNER} harus punya transform-origin: 0 0; "
            "default 50% 50% mendorong gambar keluar area viewer.")

    def test_zoom_js_memakai_kelas_inner(self):
        """Kalau zoom.js berganti nama kelas, tes CSS di atas jadi tak relevan."""
        with open(ZOOM_JS, encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn(KELAS_INNER, js,
                      f"zoom.js tidak lagi memakai kelas .{KELAS_INNER} — "
                      "perbarui kontrak CSS/tes ini.")


if __name__ == "__main__":
    unittest.main()
