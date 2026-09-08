"""Regresi untuk bugfix B1-B5 + Langkah 1-3 (stdlib unittest, tanpa server/model).

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_bugfix_b1b5 -v
"""
import io
import math
import os
import sys
import tempfile
import threading
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
WEB_DIR = os.path.join(ROOT, "web")
APP_DIR = os.path.join(ROOT, "app")
for p in (WEB_DIR, APP_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)


def _fake_thread():
    return type("FakeThread", (), {
        "start": lambda self: None,
        "join": lambda self, **k: None,
    })()


class TestB1StreamMalam(unittest.TestCase):
    def test_malam_bertahan_setelah_start(self):
        from streaming import StreamManager
        m = StreamManager()
        m._loop = lambda *a, **k: None
        m._reset_tracker = lambda: None
        asli = threading.Thread
        threading.Thread = lambda *a, **k: _fake_thread()
        try:
            m.start("file", "dummy.mp4", conf=0.3, frame_skip=2,
                    label="Uji", malam=True)
            self.assertTrue(m.malam)
            self.assertEqual(m.conf, 0.3)
            self.assertEqual(m.frame_skip, 2)
            self.assertEqual(m.source_label, "Uji")
        finally:
            threading.Thread = asli
            m.stop()


class TestLangkah1ModelLock(unittest.TestCase):
    def test_load_hanya_sekali_saat_bersamaan(self):
        import deteksi
        calls = []

        class FakeYOLO:
            def __init__(self, path):
                calls.append(path)

        import types
        fake_mod = types.ModuleType("ultralytics")
        fake_mod.YOLO = FakeYOLO
        asli_mod = sys.modules.get("ultralytics")
        sys.modules["ultralytics"] = fake_mod
        deteksi._models.clear()
        try:
            hasil = []
            ts = [threading.Thread(target=lambda: hasil.append(deteksi.get_model("palsu.pt")))
                  for _ in range(8)]
            for t in ts:
                t.start()
            for t in ts:
                t.join()
            self.assertEqual(len(calls), 1)
            self.assertTrue(all(h is hasil[0] for h in hasil))
        finally:
            if asli_mod is None:
                sys.modules.pop("ultralytics", None)
            else:
                sys.modules["ultralytics"] = asli_mod
            deteksi._models.clear()

    def test_lock_ada(self):
        import deteksi
        self.assertTrue(hasattr(deteksi, "_model_lock"))


class _BasisDB(unittest.TestCase):
    def setUp(self):
        from web.app import create_app
        self.tmp = tempfile.mkdtemp()
        self.app = create_app()
        self.app.config["DB_PATH"] = os.path.join(self.tmp, "t.db")
        self.app.config["TESTING"] = True
        self.ctx = self.app.app_context()
        self.ctx.push()
        from database import init_instansi, migrasi_disposisi_v2, init_admin
        init_instansi()
        migrasi_disposisi_v2()
        init_admin()  # seed akun admin demo (login_wajib butuh ini)

    def _client_admin(self):
        """Test client yang sudah login sebagai admin demo."""
        c = self.app.test_client()
        from database import AKUN_DEMO
        r = c.post("/login", data={"username": AKUN_DEMO[0],
                                  "password": AKUN_DEMO[1]})
        assert r.status_code == 302, "login admin demo gagal di test"
        return c

    def tearDown(self):
        self.ctx.pop()


class TestB2Haversine(_BasisDB):
    def test_terdekat_bandung(self):
        from database import instansi_terdekat
        t = instansi_terdekat(-6.9175, 107.6191)
        self.assertIn("Bandung", t["nama"])
        self.assertLess(t["jarak_km"], 5)

    def test_terdekat_jakarta(self):
        from database import instansi_terdekat
        t = instansi_terdekat(-6.2088, 106.8456)
        self.assertIn("Jakarta", t["nama"])
        self.assertLess(t["jarak_km"], 5)

    def test_jarak_bdg_jkt_masuk_akal(self):
        # Great-circle Bandung-Jakarta ~116 km (bukan orde puluhan ribu km)
        R = 6371.0
        lat1, lon1 = math.radians(-6.9175), math.radians(107.6191)
        lat2, lon2 = math.radians(-6.2088), math.radians(106.8456)
        dlat, dlon = lat2 - lat1, lon2 - lon1
        a = (math.sin(dlat / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2)
        jarak = R * 2 * math.asin(math.sqrt(a))
        self.assertTrue(100 < jarak < 140, jarak)


class TestB3Hapus(_BasisDB):
    def test_hapus_fiktif_false(self):
        from database import hapus_disposisi, hapus_instansi, hapus_sesi
        self.assertFalse(hapus_sesi(999999))
        self.assertFalse(hapus_instansi(999999))
        self.assertFalse(hapus_disposisi(999999))

    def test_hapus_valid_lalu_ganda(self):
        from database import hapus_sesi, simpan_sesi
        rows = [{"kelas": "pothole", "dasar": "d", "severity": "Ringan",
                 "bahan": "b", "luas_m2": 0.1, "volume_m3": 0.01,
                 "total_rp": 1000, "total_str": "Rp1.000", "conf": 0.9}]
        sid = simpan_sesi("uji", "Jl Uji", "m", rows, 1000)
        self.assertTrue(hapus_sesi(sid))
        self.assertFalse(hapus_sesi(sid))


class TestB4Severity(unittest.TestCase):
    def test_ambang_dari_yaml(self):
        from severity import area_severity, diagnose, load_config
        cfg = load_config(os.path.join(ROOT, "config", "severity.yaml"))
        self.assertEqual(cfg["area_cm2"]["ringan_max"], 200)
        self.assertEqual(area_severity(199, cfg), "Ringan")
        self.assertEqual(area_severity(500, cfg), "Sedang")
        self.assertEqual(area_severity(950, cfg), "Berat")

    def test_fallback_tanpa_cfg(self):
        from severity import area_severity
        self.assertEqual(area_severity(500, None), "Sedang")

    def test_diagnose_alligator_pakai_cfg(self):
        from severity import diagnose, load_config
        cfg = load_config(os.path.join(ROOT, "config", "severity.yaml"))
        d = diagnose("alligator_crack", 0, 0, 80, 80, cfg)  # 100 cm2
        self.assertEqual(d["severity"], "Ringan")


class TestB5UploadFoto(_BasisDB):
    def _disposisi(self):
        from database import simpan_disposisi, simpan_sesi
        rows = [{"kelas": "pothole", "dasar": "d", "severity": "Berat",
                 "bahan": "b", "luas_m2": 1.0, "volume_m3": 0.1,
                 "total_rp": 85000, "total_str": "Rp85.000", "conf": 0.9}]
        sid = simpan_sesi("uji", "Jl Uji", "m", rows, 85000,
                          lat=-6.9, lon=107.6)
        did = simpan_disposisi(sid, "BAP-1", "Jl Uji", -6.9, 107.6, 1,
                               85000, "Berat", 1, "DSDABM Kota Bandung",
                               "Bandung", "a@b.go.id")
        return sid, did

    def test_file_palsu_ditolak(self):
        sid, did = self._disposisi()
        c = self._client_admin()
        r = c.post(f"/api/disposisi/{did}/foto",
                   data={"foto": (io.BytesIO(b"BUKAN-GAMBAR" + b"x" * 100),
                                  "evil.jpg")},
                   content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_png_valid_jadi_jpeg(self):
        from pathlib import Path
        from PIL import Image
        sid, did = self._disposisi()
        buf = io.BytesIO()
        Image.new("RGB", (50, 40), "red").save(buf, format="PNG")
        buf.seek(0)
        c = self._client_admin()
        r = c.post(f"/api/disposisi/{did}/foto",
                   data={"foto": (buf, "asli.png")},
                   content_type="multipart/form-data")
        j = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(j["foto"], f"{sid}_sesudah_{did}.jpg")
        p = Path(self.app.config["DB_PATH"]).parent / "hasil" / j["foto"]
        self.assertEqual(p.read_bytes()[:3], b"\xff\xd8\xff")


class TestLangkah2TempVideo(unittest.TestCase):
    def test_buang_video_tmp(self):
        import web.app as app_mod
        fd, path = tempfile.mkstemp(suffix=".mp4")
        os.close(fd)
        app_mod._video_tmp = path
        app_mod._video_tmp_aktif = True
        app_mod._buang_video_tmp()
        self.assertIsNone(app_mod._video_tmp)
        self.assertFalse(app_mod._video_tmp_aktif)
        self.assertFalse(os.path.exists(path))
        app_mod._buang_video_tmp()  # idempoten


class TestLangkah3Laporan(unittest.TestCase):
    def test_buat_laporan_pdf(self):
        from laporan import buat_laporan
        rows = [{"kelas": "pothole", "dasar": "diameter ±30 cm",
                 "severity": "Ringan", "bahan": "cold-mix patching",
                 "total_str": "Rp150.000"}]
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        try:
            buat_laporan(path, rows, 150000, meta={"Sumber": "uji"})
            with open(path, "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
        finally:
            if os.path.exists(path):
                os.remove(path)


if __name__ == "__main__":
    unittest.main()
