"""Tes untuk scripts/pra_label.py (jalur P2: pra-annotasi dataset lokal).

Skripnya alat command-line di luar paket aplikasi, jadi dimuat lewat importlib.
Fokus tes: format label YOLO harus benar dan konsisten dengan urutan kelas model
— kalau salah, dataset latih nantiDiam-diam trainswith kelas yang tertukar.

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_pra_label -v
"""
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "web"), os.path.join(ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)


def _muat_skrip(nama):
    """Muat scripts/<nama>.py sebagai modul (bukan package install)."""
    jalur = os.path.join(ROOT, "scripts", nama)
    spec = importlib.util.spec_from_file_location("jp_" + nama[:-3], jalur)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pra_label = _muat_skrip("pra_label.py")


class TestFormatLabel(unittest.TestCase):
    PETA = {"longitudinal_crack": 0, "transverse_crack": 1,
            "alligator_crack": 2, "other_corruption": 3, "pothole": 4}

    def test_kotak_terpusat_ternormalisasi(self):
        # box [400,300,600,500] pada citra 1000x1000 -> cx 0,5 cy 0,4 w 0,2 h 0,2
        baris = {"kelas": "pothole", "box": [400, 300, 600, 500]}
        hasil = pra_label.ke_yolo(baris, 1000, 1000, self.PETA)
        self.assertEqual(hasil, "4 0.50000 0.40000 0.20000 0.20000")

    def test_kotak_di_pojok_kiri_atas(self):
        baris = {"kelas": "transverse_crack", "box": [0, 0, 200, 100]}
        hasil = pra_label.ke_yolo(baris, 1000, 400, self.PETA)
        # cx=0,1 cy=0,125 w=0,2 h=0,25
        self.assertEqual(hasil, "1 0.10000 0.12500 0.20000 0.25000")

    def test_kelas_tak_dikenal_dilewati(self):
        baris = {"kelas": "lubang_mysterious", "box": [0, 0, 10, 10]}
        self.assertIsNone(pra_label.ke_yolo(baris, 100, 100, self.PETA))

    def test_semua_kelas_punya_id(self):
        for nama in self.PETA:
            self.assertIn(nama, self.PETA)
        self.assertEqual(sorted(self.PETA.values()), [0, 1, 2, 3, 4])

    def test_id_kelas_cocok_dengan_model(self):
        """Peta id harus mengikuti urutan kelas model saat ini (bukan hard-code)."""
        peta = pra_label.id_kelas()
        self.assertEqual(sorted(peta.values()), [0, 1, 2, 3, 4])
        for nama, idx in self.PETA.items():
            self.assertEqual(peta.get(nama), idx)

    def test_telusuri_menemukan_gambar_rekursif(self):
        with tempfile.TemporaryDirectory() as d:
            for nama in ("a.jpg", "b.PNG", "catatan.txt"):
                with open(os.path.join(d, nama), "wb") as f:
                    f.write(b"x")
            sub = os.path.join(d, "sub")
            os.mkdir(sub)
            with open(os.path.join(sub, "c.jpeg"), "wb") as f:
                f.write(b"x")
            hasil = pra_label.telusuri(d)
            self.assertEqual([p.name for p in hasil], ["a.jpg", "b.PNG", "c.jpeg"])

    def test_telusuri_folder_hilang_gagal_jelas(self):
        with self.assertRaises(SystemExit):
            pra_label.telusuri(os.path.join(ROOT, "tidak-ada-_folder-xyz"))