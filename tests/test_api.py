"""Uji endpoint API web/app.py (deterministik: tanpa model, kamera, atau jaringan).

Menutup celah coverage terbesar (web/app.py). Perhatian:
- Kalibrasi POST menulis config/severity.yaml -> di-PATCH agar tidak mengubah berkas.
- Laporan POST menulis PDF sementara -> ditangani route (dihapus sendiri).
"""
import io
import os
import tempfile
import unittest
from unittest import mock

ROWS = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
         "skor_prioritas": 80}]


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():          # seed DB sementara
        from database import (migrasi_admin_v2, migrasi_sesi_v2, init_admin)
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app


def _login(c):
    from database import AKUN_DEMO
    return c.post("/login", data={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]})


class TestApiPublik(unittest.TestCase):
    def setUp(self):
        self.c = _app().test_client()

    def test_peta(self):
        r = self.c.get("/api/peta")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.get_json(), list)




    def test_riwayat_daftar_bentuk(self):
        r = self.c.get("/api/riwayat")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        for k in ("data", "overflow", "total_db"):
            self.assertIn(k, j)

    def test_riwayat_detail_dan_gambar_tidak_ada(self):
        self.assertEqual(self.c.get("/api/riwayat/999999").status_code, 404)
        self.assertEqual(self.c.get("/api/riwayat/999999/gambar").status_code, 404)


    def test_kalibrasi_status(self):
        r = self.c.get("/api/kalibrasi")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("pixels_per_cm", j)
        self.assertIn("dampak", j)

    def test_verifikasi_tanpa_rows_400(self):
        self.assertEqual(self.c.post("/api/verifikasi", json={"rows": []}).status_code, 400)


class TestApiButuhLogin(unittest.TestCase):
    def setUp(self):
        self.c = _app().test_client()

    def test_endpoint_admin_mengembalikan_401(self):
        self.assertEqual(self.c.post("/api/kalibrasi", json={"pixels_per_cm": 11.0}).status_code, 401)
        self.assertEqual(self.c.delete("/api/riwayat/1").status_code, 401)


class TestApiSetelahLogin(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.c = self.app.test_client()
        _login(self.c)


    def test_kalibrasi_simpan_dipatch(self):
        palsu = {"pixels_per_cm": 11.0, "metode": "manual", "catatan": "-",
                 "diperbarui": "x"}
        with mock.patch("web.app.simpan_kalibrasi", return_value=palsu):
            r = self.c.post("/api/kalibrasi", json={"pixels_per_cm": 11.0})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["pixels_per_cm"], 11.0)

    def test_kalibrasi_nilai_salah_400(self):
        with mock.patch("web.app.hitung_ppc", side_effect=ValueError("panjang tidak valid")):
            r = self.c.post("/api/kalibrasi", json={"panjang_px": 0, "panjang_cm": 0})
        self.assertEqual(r.status_code, 400)

    def test_stream_stats_dan_anotasi(self):
        self.assertEqual(self.c.get("/api/stream/stats").status_code, 200)
        from streaming import MANAGER
        semula = MANAGER.anotasi_aktif
        try:
            r = self.c.post("/api/stream/anotasi")
            self.assertEqual(r.status_code, 200)
            self.assertIn("anotasi", r.get_json())
        finally:
            MANAGER.anotasi_aktif = semula

    def test_stream_snapshot_tanpa_track_400(self):
        self.assertEqual(self.c.post("/api/stream/snapshot").status_code, 400)

    def test_stream_stop(self):
        self.assertEqual(self.c.post("/api/stream/stop").status_code, 200)

    def test_stream_dimiliki_sesi_lain_ditolak(self):
        """Regression: hanya ada SATU StreamManager untuk seluruh server.

        Tanpa token kepemilikan, tab kedua bisa mematikan atau merebut stream
        milik tab pertama. Token hanya wajib saat stream sedang berjalan.
        """
        from streaming import MANAGER
        import web.app as app_mod
        MANAGER.running = True
        holders = []
        try:
            app_mod._stream_token = "TOKEN-PEMILIK"
            # Tanpa token: stop/anotasi/snapshot ditolak, start ditolak 409.
            for path, kode in (("/api/stream/stop", 403),
                               ("/api/stream/anotasi", 403),
                               ("/api/stream/snapshot", 403)):
                r = self.c.post(path, json={})
                self.assertEqual(r.status_code, kode, path)
            r = self.c.post("/api/stream/start",
                            json={"source": "webcam", "target": "0"})
            self.assertEqual(r.status_code, 409)
            # Token salah juga ditolak.
            r = self.c.post("/api/stream/stop", json={"token": "SALAH"})
            self.assertEqual(r.status_code, 403)
            # Pemilik sah boleh menghentikan.
            r = self.c.post("/api/stream/stop", json={"token": "TOKEN-PEMILIK"})
            self.assertEqual(r.status_code, 200)
        finally:
            MANAGER.running = False
            MANAGER.anotasi_aktif = True
            app_mod._stream_token = None

    def test_stream_terbuka_saat_tidak_berjalan(self):
        """Saat tidak ada stream, endpoint tetap terbuka agar idempoten
        dan tidak mengganggu state antarmuka."""
        from streaming import MANAGER
        MANAGER.running = False
        self.assertEqual(self.c.post("/api/stream/stop", json={}).status_code, 200)
        self.assertEqual(self.c.post("/api/stream/anotasi", json={}).status_code, 200)
        self.assertEqual(self.c.post("/api/stream/snapshot", json={}).status_code, 400)


class TestAutentikasiDan404(unittest.TestCase):
    def test_login_salah_401(self):
        c = _app().test_client()
        self.assertEqual(
            c.post("/login", data={"username": "admin", "password": "salah"}).status_code, 401)

    def test_halaman_tidak_ditemukan(self):
        c = _app().test_client()
        self.assertEqual(c.get("/laporan/preview/999999").status_code, 404)

    def test_mobile_dihapus_dan_kalibrasi_anon(self):
        c = _app().test_client()
        self.assertEqual(c.get("/mobile").status_code, 404)  # halaman mockup dihapus (Fase 2)
        self.assertEqual(c.get("/kalibrasi").status_code, 302)  # butuh login


class TestValidasiInput(unittest.TestCase):
    """Jalur validasi (400) — murah, deterministik, dan mengunci perilaku."""

    def setUp(self):
        self.app = _app()
        self.c = self.app.test_client()
        _login(self.c)

    def test_detect_tanpa_berkas_400(self):
        self.assertEqual(self.c.post("/api/detect", data={}).status_code, 400)

    def test_detect_format_salah_400(self):
        r = self.c.post("/api/detect", data={"gambar": (io.BytesIO(b"xx"), "a.txt")},
                        content_type="multipart/form-data")
        self.assertEqual(r.status_code, 400)

    def test_kalibrasi_foto_tanpa_berkas_400(self):
        self.assertEqual(self.c.post("/api/kalibrasi/foto", data={}).status_code, 400)

    def test_kalibrasi_foto_lapor_ukuran_asli_bukan_tampil(self):
        """px/cm harus diukur di ruang koordinat ASLI, sama dengan box deteksi.

        Regresi: dulu `lebar`/`tinggi` diambil SETELAH `thumbnail()`, sehingga
        pada foto > 2000 px nilai px/cm terukur di ruang yang lebih kecil
        daripada ruang koordinat box — dimensi cm dan severity meleset sebesar
        faktor pengecilan (foto 4032 px -> thumbnail 2000 px = salah ~2x).
        """
        import base64
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (2500, 1500), (120, 120, 120)).save(buf, format="JPEG")
        buf.seek(0)
        r = self.c.post("/api/kalibrasi/foto",
                        data={"foto": (buf, "penggaris.jpg")},
                        content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertEqual((j["lebar"], j["tinggi"]), (2500, 1500))
        # Gambar yang dikirim tetap diperkecil — hanya untuk tampil, bukan ukuran.
        with Image.open(io.BytesIO(base64.b64decode(j["image_b64"]))) as im:
            self.assertEqual(max(im.size), 2000)

    def test_video_tanpa_berkas_400(self):
        self.assertEqual(self.c.post("/api/video", data={}).status_code, 400)

    def test_stream_start_sumber_salah_400(self):
        self.assertEqual(
            self.c.post("/api/stream/start", json={"source": "xyz"}).status_code, 400)

    def test_stream_start_ipcam_localhost_400(self):
        r = self.c.post("/api/stream/start",
                        json={"source": "ipcam", "target": "http://localhost:8080/x"})
        self.assertEqual(r.status_code, 400)

    def test_stream_start_ipcam_terobfuskasi_400(self):
        """IP loopback dalam bentuk desimal/heksa/pendek tetap ditolak (SSRF)."""
        for target in ("http://0x7f000001/", "http://2130706433/",
                       "http://127.1/", "http://0177.0.0.1/"):
            r = self.c.post("/api/stream/start",
                            json={"source": "ipcam", "target": target})
            self.assertEqual(r.status_code, 400, target)

    def test_stream_start_webcam_idx_bukan_angka_400(self):
        r = self.c.post("/api/stream/start",
                        json={"source": "webcam", "target": "bukan-angka"})
        self.assertEqual(r.status_code, 400)

    def test_stream_start_performa_tak_dikenal_diabaikan(self):
        """Preset "akurat" dihapus 19 Okt 2026 (duplikat "seimbang").

        Nilai tak dikenal tidak ditolak, tetapi diabaikan -> None (fallback
        imgsz_live config), supaya klien lama tidak pecah.
        """
        import web.app as app_mod
        terlihat = {}
        asli = app_mod.MANAGER.start
        app_mod.MANAGER.start = lambda *a, **k: terlihat.update(k)
        try:
            r = self.c.post("/api/stream/start",
                            json={"source": "webcam", "target": "0",
                                  "performa": "akurat"})
            self.assertEqual(r.status_code, 200)
            self.assertIsNone(terlihat.get("performa"))
            r = self.c.post("/api/stream/start",
                            json={"source": "webcam", "target": "0",
                                  "performa": "seimbang"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(terlihat.get("performa"), "seimbang")
        finally:
            app_mod.MANAGER.start = asli

    def test_riwayat_koordinat_luar_rentang_400(self):
        r = self.c.post("/api/riwayat", json={"rows": ROWS, "total": 1, "lat": 999, "lon": 0})
        self.assertEqual(r.status_code, 400)





