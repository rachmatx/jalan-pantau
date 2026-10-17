"""Uji segmen jalan + SDI-visual di web/database.py (tanpa model/jaringan)."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "web"), os.path.join(ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)


def _ctx():
    from flask import Flask
    app = Flask(__name__)
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    return app


ROWS = [
    {"kelas": "longitudinal_crack", "panjang_cm": 200, "lebar_cm": 0.5,
     "luas_m2": 0.01, "severity": "Ringan", "dasar": "lebar retak 5 mm",
     "bahan": "-", "conf": 0.8},
    {"kelas": "pothole", "panjang_cm": 40, "lebar_cm": 35,
     "luas_m2": 0.14, "severity": "Berat", "dasar": "diameter 40 cm",
     "bahan": "-", "conf": 0.9},
]


class TestSegmen(unittest.TestCase):
    def setUp(self):
        self.app = _ctx()
        self._ctx = self.app.app_context()
        self._ctx.push()
        import database as db
        self.db = db

    def tearDown(self):
        self._ctx.pop()

    def test_crud_segmen(self):
        db = self.db
        gid = db.tambah_segmen("Segmen 1", jalan="Jl. A", panjang_m=100,
                               lebar_m=6, catatan="uji")
        self.assertGreater(gid, 0)
        d = db.detail_segmen(gid)
        self.assertEqual(d["nama"], "Segmen 1")
        self.assertEqual(d["anggota"], [])
        # SDI segmen kosong -> 0 / Baik
        self.assertEqual(d["sdi"]["sdi_total"], 0)
        self.assertEqual(d["sdi"]["kategori"], "Baik")
        # ubah + manual
        self.assertTrue(db.ubah_segmen(gid, nama="Segmen 1A", sdi_manual=25))
        d = db.detail_segmen(gid)
        self.assertEqual(d["nama"], "Segmen 1A")
        self.assertEqual(d["sdi_manual"], 25.0)
        # hapus
        self.assertTrue(db.hapus_segmen(gid))
        self.assertIsNone(db.detail_segmen(gid))
        self.assertFalse(db.hapus_segmen(999999))

    def test_tambah_segmen_tanpa_nama(self):
        db = self.db
        gid = db.tambah_segmen("  ")
        self.assertEqual(db.detail_segmen(gid)["nama"], "Segmen tanpa nama")

    def test_sdi_dari_anggota(self):
        db = self.db
        gid = db.tambah_segmen("Seg-Uji", panjang_m=100, lebar_m=6)
        sid = db.simpan_sesi("foto", "km 1", "yolo", ROWS, 0, segmen_id=gid)
        d = db.detail_segmen(gid)
        sdi = d["sdi"]
        # 1 retak 200x0.5cm + 1 lubang/0.1km=10/km -> 5x2 + 75 = 85
        self.assertEqual(sdi["sdi_total"], 85)
        self.assertEqual(sdi["kategori"], "Sedang")
        self.assertEqual(sdi["n_temuan_total"], 2)
        self.assertEqual(len(d["anggota"]), 1)
        # sesi tercatat di segmen
        self.assertEqual(db.daftar_sesi()[0]["segmen_nama"], "Seg-Uji")
        # keluarkan -> SDI kembali 0
        self.assertTrue(db.tetapkan_segmen_sesi(sid, None))
        self.assertEqual(db.detail_segmen(gid)["sdi"]["sdi_total"], 0)
        self.assertEqual(len(db.sesi_tanpa_segmen()), 1)

    def test_simpan_sesi_dimensi(self):
        db = self.db
        sid = db.simpan_sesi("foto", "km 2", "yolo", ROWS, 0)
        t = db.detail_sesi(sid)["temuan"]
        self.assertEqual(t[0]["panjang_cm"], 200)
        self.assertEqual(t[0]["lebar_cm"], 0.5)
        self.assertEqual(t[1]["panjang_cm"], 40)
        # segmen_id tak valid -> ValueError
        with self.assertRaises(ValueError):
            db.simpan_sesi("foto", "km 3", "yolo", ROWS, 0, segmen_id=999999)

    def test_tetapkan_segmen_tak_valid(self):
        db = self.db
        sid = db.simpan_sesi("foto", "km 4", "yolo", ROWS, 0)
        with self.assertRaises(ValueError):
            db.tetapkan_segmen_sesi(sid, 999999)
        self.assertFalse(db.tetapkan_segmen_sesi(999999, None))

    def test_hapus_segmen_tidak_hapus_sesi(self):
        db = self.db
        gid = db.tambah_segmen("Seg-H")
        sid = db.simpan_sesi("foto", "km 5", "yolo", ROWS, 0, segmen_id=gid)
        self.assertTrue(db.hapus_segmen(gid))
        # sesi tetap ada, menjadi tanpa segmen
        self.assertIsNotNone(db.detail_sesi(sid))
        self.assertEqual(len(db.sesi_tanpa_segmen()), 1)


if __name__ == "__main__":
    unittest.main()
