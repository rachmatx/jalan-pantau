"""Kontrak UI pengukuran 2 titik di halaman kalibrasi.

Bug yang dikunci: titik (dot) dulu ditempel ke `.jp-viewer` yang ber-padding
16px + flex centering, tetapi posisinya dihitung relatif terhadap `<img>`.
Akibatnya dot meleset ~16 px dari kursor. Posisi dot juga memakai piksel
tampilan, sehingga ikut bergeser saat gambar diskalakan ulang (resize).

Kontrak sekarang:
- gambar dibungkus stage `position: relative` yang mengepak gambar,
- titik/handle diposisikan PERSEN dari ukuran asli gambar -> tepat di titik
  klik dan tetap menempel saat resize,
- handle bisa digeser, dinudge lewat panah, dan dihapus satu per satu.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "web", "templates", "kalibrasi.html")
CIVIC = os.path.join(ROOT, "web", "static", "css", "civic.css")


def baca(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestKalibrasiStage(unittest.TestCase):
    def setUp(self):
        self.html = baca(TEMPLATE)
        self.css = baca(CIVIC)

    def _blok_css(self, kelas):
        m = re.search(r"\.%s\s*\{([^}]*)\}" % kelas, self.css)
        self.assertIsNotNone(m, f".{kelas} tidak ditemukan di {CIVIC}")
        return m.group(1)

    def test_stage_mengepak_gambar(self):
        """Overlay harus seukuran gambar, bukan seukuran viewer ber-padding."""
        self.assertIn("stage.id = 'stage-penggaris'", self.html)
        self.assertIn("stage.appendChild", self.html)
        self.assertNotIn(
            "img.parentElement.appendChild(dot)", self.html,
            "regresi lama: dot ditempel ke .jp-viewer ber-padding")
        blok = self._blok_css("kalibrasi-stage")
        self.assertRegex(blok, r"position\s*:\s*relative")
        self.assertRegex(blok, r"display\s*:\s*inline-block")
        self.assertRegex(blok, r"line-height\s*:\s*0")

    def test_titik_diposisikan_persen_ukuran_asli(self):
        """Piksel tampilan berubah saat resize; persen ukuran asli tidak."""
        self.assertIn("function pctX", self.html)
        self.assertIn("function pctY", self.html)
        self.assertIn("style.left = pctX(", self.html)
        self.assertIn("style.top = pctY(", self.html)

    def test_titik_bisa_digeser_dan_dinudge(self):
        for token in ("pointerdown", "setPointerCapture",
                      "pointermove", "pointerup"):
            self.assertIn(token, self.html)
        self.assertIn("kalibrasi-handle", self.html)
        self.assertIn("ArrowLeft", self.html)
        self.assertIn("Shift", self.html)

    def test_crosshair_dan_loupe_presisi(self):
        self.assertIn("kalibrasi-crosshair", self.html)
        self.assertIn("kalibrasi-loupe", self.html)
        self.assertIn("drawImage", self.html)
        # Gambar tampil bisa berupa thumbnail; crop loupe wajib dipetakan ke
        # piksel natural, bukan langsung ke koordinat asli (pernah hitam).
        self.assertIn("imgEl.naturalWidth / dimAsli.w", self.html)
        self._blok_css("kalibrasi-handle")
        self._blok_css("kalibrasi-loupe")

    def test_hapus_titik_terakhir_dan_hasil_hidup(self):
        self.assertIn('id="btn-hapus-titik"', self.html)
        self.assertIn("function perbaruiHasil", self.html)
        self.assertIn("refEl.addEventListener('input'", self.html)


if __name__ == "__main__":
    unittest.main()
