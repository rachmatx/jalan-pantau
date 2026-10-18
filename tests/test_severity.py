"""Uji aturan klasifikasi dimensi severity (app/severity.py).

Keputusan 2026-10-18: reframing defensif untuk dosen/reviewer.
- Retak: "tingkat keparahan", ambang <10 / 10-75 / >75 mm (RDDC2024-ID README,
  gaya ASTM D6433) — TIDAK berubah.
- Lubang: "kelas ukuran", bin diameter 20/45 cm (= 200/450 mm, kolom
  Tabel X1.1 ASTM D6433 via gambar P6 README RDDC2024-ID).
- Alligator/other: "kelas luasan", ambang 200/900 cm2 (heuristik tim).

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_severity -v
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
for p in (ROOT, APP_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


def _cfg():
    from severity import load_config
    return load_config(os.path.join(ROOT, "config", "severity.yaml"))


class TestAmbangRetak(unittest.TestCase):
    """Ambang retak TIDAK berubah (acuan standar)."""

    def test_batas(self):
        from severity import crack_severity
        cfg = _cfg()
        # Batas atas eksklusif (<): perilaku lama dipertahankan.
        self.assertEqual(crack_severity(9.99, cfg), "Ringan")
        self.assertEqual(crack_severity(10, cfg), "Sedang")
        self.assertEqual(crack_severity(74.99, cfg), "Sedang")
        self.assertEqual(crack_severity(75, cfg), "Berat")


class TestBinLubangASTM(unittest.TestCase):
    """Bin diameter lubang mengikuti kolom Tabel X1.1 ASTM D6433 (20/45 cm)."""

    def test_yaml_memakai_bin_astm(self):
        cfg = _cfg()
        self.assertEqual(cfg["pothole_diameter_cm"]["ringan_max"], 20)
        self.assertEqual(cfg["pothole_diameter_cm"]["sedang_max"], 45)

    def test_batas_bin(self):
        from severity import pothole_severity
        cfg = _cfg()
        # Batas atas eksklusif (<): 20 cm masuk bin Sedang, 45 cm Berat.
        self.assertEqual(pothole_severity(19.99, cfg), "Ringan")
        self.assertEqual(pothole_severity(20, cfg), "Sedang")
        self.assertEqual(pothole_severity(44.99, cfg), "Sedang")
        self.assertEqual(pothole_severity(45, cfg), "Berat")


class TestKelasLuasan(unittest.TestCase):
    """Ambang luas TIDAK berubah (heuristik tim, dinyatakan eksplisit)."""

    def test_batas(self):
        from severity import area_severity
        cfg = _cfg()
        # Batas atas eksklusif (<): perilaku lama dipertahankan.
        self.assertEqual(area_severity(199.9, cfg), "Ringan")
        self.assertEqual(area_severity(200, cfg), "Sedang")
        self.assertEqual(area_severity(899.9, cfg), "Sedang")
        self.assertEqual(area_severity(900, cfg), "Berat")

    def test_fallback_tanpa_cfg(self):
        from severity import area_severity
        self.assertEqual(area_severity(500, None), "Sedang")


class TestMakna(unittest.TestCase):
    """Reframing: makna klasifikasi per jenis kerusakan."""

    def test_makna_per_kelas(self):
        from severity import makna_untuk_kelas
        self.assertEqual(makna_untuk_kelas("longitudinal_crack"), "tingkat keparahan")
        self.assertEqual(makna_untuk_kelas("transverse_crack"), "tingkat keparahan")
        self.assertEqual(makna_untuk_kelas("pothole"), "kelas ukuran")
        self.assertEqual(makna_untuk_kelas("alligator_crack"), "kelas luasan")
        self.assertEqual(makna_untuk_kelas("other_corruption"), "kelas luasan")

    def test_diagnose_membawa_makna_dan_dasar(self):
        from severity import diagnose
        cfg = _cfg()
        ppc = cfg["pixels_per_cm"]
        # Lubang: box 30 cm x 30 cm -> diameter 30 cm -> Sedang (bin 20-45)
        d = diagnose("pothole", 0, 0, 30 * ppc, 30 * ppc, cfg)
        self.assertEqual(d["severity"], "Sedang")
        self.assertEqual(d["makna"], "kelas ukuran")
        self.assertIn("kelas ukuran", d["dasar"])
        # Retak: box 100 cm x 0.5 cm -> lebar 5 mm -> Ringan
        d = diagnose("transverse_crack", 0, 0, 100 * ppc, 0.5 * ppc, cfg)
        self.assertEqual(d["severity"], "Ringan")
        self.assertEqual(d["makna"], "tingkat keparahan")
        # Alligator: box 10 cm x 10 cm -> 100 cm2 -> Ringan, kelas luasan
        d = diagnose("alligator_crack", 0, 0, 10 * ppc, 10 * ppc, cfg)
        self.assertEqual(d["severity"], "Ringan")
        self.assertEqual(d["makna"], "kelas luasan")


if __name__ == "__main__":
    unittest.main()
