"""Uji gambar sementara bertoken: pengganti base64 di alur deteksi -> PDF/simpan.

Kontrak baru (26 Okt 2026): server menulis gambar anotasi SEKALI ke folder tmp,
klien memegang token saja. Tidak ada lagi base64 1 MB yang bolak-balik lewat
JSON /api/detect -> /api/riwayat -> /api/laporan.
"""
import io
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, "web"), os.path.join(ROOT, "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

ROWS = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
         "skor_prioritas": 80}]


def _jpg():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (48, 32), (120, 120, 120)).save(buf, format="JPEG")
    return buf.getvalue()


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import migrasi_admin_v2, migrasi_sesi_v2, init_admin
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app


def _login(c):
    from database import AKUN_DEMO
    return c.post("/login", data={"username": AKUN_DEMO[0],
                                  "password": AKUN_DEMO[1]})


class TestGambarSementara(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.ctx = self.app.app_context()
        self.ctx.push()
        import gambar_sementara
        self.gs = gambar_sementara

    def tearDown(self):
        self.ctx.pop()

    def test_simpan_lalu_path_mengembalikan_file(self):
        token = self.gs.simpan(b"isi-jpeg")
        p = self.gs.path(token)
        self.assertIsNotNone(p)
        self.assertEqual(p.read_bytes(), b"isi-jpeg")

    def test_token_ngawur_tidak_bisa_keluar_folder(self):
        for token in ("../../rahasia", "abc/def", "a" * 500, "", None):
            self.assertIsNone(self.gs.path(token), token)

    def test_bersihkan_hapus_kedaluwarsa_dan_sisakan_baru(self):
        lama = self.gs.simpan(b"lama")
        baru = self.gs.simpan(b"baru")
        p_lama = self.gs.path(lama)
        os.utime(p_lama, (time.time() - self.gs.TTL_DETIK - 10,) * 2)
        self.gs.bersihkan()
        self.assertIsNone(self.gs.path(lama))
        self.assertIsNotNone(self.gs.path(baru))

    def test_batas_jumlah_berkas_membuang_yang_paling_lama(self):
        asli = self.gs.MAKS_BERKAS
        self.gs.MAKS_BERKAS = 2
        try:
            t1 = self.gs.simpan(b"satu")
            time.sleep(0.02)
            t2 = self.gs.simpan(b"dua")
            time.sleep(0.02)
            t3 = self.gs.simpan(b"tiga")
            self.gs.bersihkan()
        finally:
            self.gs.MAKS_BERKAS = asli
        self.assertIsNone(self.gs.path(t1))
        self.assertIsNotNone(self.gs.path(t2))
        self.assertIsNotNone(self.gs.path(t3))


class TestRouteGambarSementara(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.c = self.app.test_client()
        self.ctx = self.app.app_context()
        self.ctx.push()
        import gambar_sementara
        self.gs = gambar_sementara
        self.jpg = _jpg()

    def tearDown(self):
        self.ctx.pop()

    def test_gambar_token_disajikan_dengan_cache(self):
        token = self.gs.simpan(self.jpg)
        r = self.c.get("/api/gambar/" + token)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "image/jpeg")
        self.assertEqual(r.data, self.jpg)
        self.assertIn("max-age", r.headers.get("Cache-Control", ""))

    def test_gambar_token_tidak_ada_404(self):
        r = self.c.get("/api/gambar/" + "a" * 24)
        self.assertEqual(r.status_code, 404)
        # Route asli membalas JSON; 404 HTML berarti route-nya memang belum ada.
        self.assertIn("error", r.get_json())

    def test_detect_mengembalikan_token_bukan_base64(self):
        import web.app as app_mod
        hasil = {"rows": ROWS, "total": 80, "model": "uji",
                 "gambar_jpg": self.jpg, "gps": {"lat": None, "lon": None},
                 "malam": False, "teliti": False, "gelap": False,
                 "disaring": {}, "scene": None}
        with mock.patch.object(app_mod, "analisis_gambar_terjadwal",
                               return_value=hasil):
            r = self.c.post("/api/detect",
                            data={"gambar": (io.BytesIO(self.jpg), "a.jpg")},
                            content_type="multipart/form-data")
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("gambar_token", j)
        self.assertNotIn("image_b64", j)
        self.assertNotIn("gambar_jpg", j)
        g = self.c.get("/api/gambar/" + j["gambar_token"])
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.data, self.jpg)

    def test_snapshot_mengembalikan_token_bukan_base64(self):
        import web.app as app_mod
        snap = {"rows": ROWS, "total": 80, "disaring": {},
                "gambar_jpg": self.jpg}
        with mock.patch.object(app_mod.MANAGER, "snapshot",
                               return_value=snap), \
                mock.patch.object(app_mod, "nama_model_live",
                                  return_value="uji"):
            r = self.c.post("/api/stream/snapshot", json={})
        self.assertEqual(r.status_code, 200)
        j = r.get_json()
        self.assertIn("gambar_token", j)
        self.assertNotIn("image_b64", j)

    def test_simpan_riwayat_dari_token(self):
        token = self.gs.simpan(self.jpg)
        _login(self.c)
        r = self.c.post("/api/riwayat", json={
            "sumber": "Gambar (a.jpg)", "lokasi": "Jl Uji", "model": "uji",
            "rows": ROWS, "total": 80, "gambar_token": token,
            "izinkan_duplikat": True})
        self.assertEqual(r.status_code, 200)
        sid = r.get_json()["id"]
        g = self.c.get(f"/api/riwayat/{sid}/gambar")
        self.assertEqual(g.status_code, 200)
        self.assertEqual(g.data, self.jpg)

    def test_simpan_riwayat_token_kedaluwarsa_400(self):
        _login(self.c)
        r = self.c.post("/api/riwayat", json={
            "sumber": "Gambar (a.jpg)", "lokasi": "Jl Uji", "model": "uji",
            "rows": ROWS, "total": 80, "gambar_token": "a" * 24,
            "izinkan_duplikat": True})
        self.assertEqual(r.status_code, 400)
        self.assertIn("kedaluwarsa", r.get_json()["error"].lower())

    def test_laporan_memakai_path_dari_token(self):
        import web.app as app_mod
        token = self.gs.simpan(self.jpg)
        fd, pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        with open(pdf, "wb") as f:
            f.write(b"%PDF-uji")
        self.addCleanup(lambda: os.path.exists(pdf) and os.remove(pdf))
        with mock.patch.object(app_mod, "buat_pdf", return_value=pdf) as bp:
            r = self.c.post("/api/laporan",
                            json={"rows": ROWS, "gambar_token": token})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(bp.call_args.kwargs["img_path"]
                        .endswith(token + ".jpg"))

    def test_laporan_memakai_path_dari_sesi_id(self):
        import web.app as app_mod
        from database import simpan_sesi
        sid = simpan_sesi("uji", "Jl Uji", "uji", ROWS, 0,
                          image_bytes=self.jpg)
        fd, pdf = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        with open(pdf, "wb") as f:
            f.write(b"%PDF-uji")
        self.addCleanup(lambda: os.path.exists(pdf) and os.remove(pdf))
        with mock.patch.object(app_mod, "buat_pdf",
                               return_value=pdf) as bp:
            r = self.c.post("/api/laporan",
                            json={"rows": ROWS, "sesi_id": sid})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(bp.call_args.kwargs["img_path"]
                        .endswith(f"{sid}.jpg"))

    def test_laporan_token_kedaluwarsa_400(self):
        r = self.c.post("/api/laporan",
                        json={"rows": ROWS, "gambar_token": "a" * 24})
        self.assertEqual(r.status_code, 400)
        self.assertIn("kedaluwarsa", r.get_json()["error"].lower())

    def test_laporan_pdf_nyata_dengan_token(self):
        token = self.gs.simpan(self.jpg)
        r = self.c.post("/api/laporan",
                        json={"rows": ROWS, "gambar_token": token,
                              "source": "uji.jpg", "model": "uji"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[:5], b"%PDF-")
        # Bukti gambar benar-benar ikut: FPDF menulis objek /Subtype /Image.
        self.assertIn(b"/Subtype /Image", r.data)
        # Tanpa gambar, PDF tetap dibuat tetapi tanpa objek gambar.
        r2 = self.c.post("/api/laporan",
                         json={"rows": ROWS, "source": "uji.jpg",
                               "model": "uji"})
        self.assertEqual(r2.status_code, 200)
        self.assertNotIn(b"/Subtype /Image", r2.data)


if __name__ == "__main__":
    unittest.main()
