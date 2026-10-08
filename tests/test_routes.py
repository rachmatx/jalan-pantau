"""Uji route/render dasar (tanpa model, tanpa server).

Menangkap template rusak / route hilang sejak dini. CSRF dinonaktifkan via
TESTING; endpoint yang butuh login diuji dengan sesi login admin demo.
"""
import os
import tempfile
import unittest


def _app(testing=True):
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    if testing:
        app.config["TESTING"] = True
    return app


class TestRoutePublik(unittest.TestCase):
    def test_halaman_publik_render(self):
        c = _app().test_client()
        for u in ["/", "/peta", "/riwayat", "/tentang", "/disposisi", "/login"]:
            with self.subTest(url=u):
                self.assertEqual(c.get(u).status_code, 200, u)

    def test_aset_vendor_offline(self):
        c = _app().test_client()
        for u in ["/static/vendor/leaflet/leaflet.js",
                  "/static/vendor/leaflet/leaflet.css",
                  "/static/vendor/fonts/fonts.css",
                  "/static/js/kontraktor_peta.js"]:
            with self.subTest(url=u):
                self.assertEqual(c.get(u).status_code, 200, u)

    def test_ikon_ada_di_halaman(self):
        c = _app().test_client()
        for u in ["/login", "/peta", "/"]:
            with self.subTest(url=u):
                self.assertIn('rel="icon"', c.get(u).get_data(as_text=True))

    def test_base_html_punya_wrapper_csrf(self):
        """Regresi: halaman publik WAJIB menyisipkan header X-CSRF-Token di fetch.

        Tanpa ini, semua aksi POST dari halaman publik (deteksi, simpan riwayat,
        laporan, disposisi, kalibrasi) gagal 403 karena CSRF aktif.
        """
        html = _app().test_client().get("/").get_data(as_text=True)
        self.assertIn("X-CSRF-Token", html)
        self.assertIn('name="csrf-token"', html)


class TestRouteTerlindungi(unittest.TestCase):
    def test_tanpa_login_redirect(self):
        c = _app().test_client()
        self.assertEqual(c.get("/kalibrasi").status_code, 302)
        self.assertEqual(c.get("/pupr-bandung/dashboard").status_code, 302)
        self.assertEqual(c.get("/kontraktor/dashboard").status_code, 302)


class TestSetelahLoginRender(unittest.TestCase):
    def test_setelah_login_render(self):
        app = _app()
        with app.app_context():          # seed akun admin di DB sementara
            from database import init_admin
            init_admin()
        c = app.test_client()
        from database import AKUN_DEMO
        c.post("/login", data={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]})
        for u in ["/pupr-bandung/dashboard", "/pupr-bandung/dashboard/verifikasi",
                  "/pupr-bandung/dashboard/analitik", "/pupr-bandung/dashboard/disposisi",
                  "/pupr-bandung/dashboard/instansi", "/pupr-bandung/dashboard/spk",
                  "/pupr-bandung/dashboard/kontraktor", "/kalibrasi"]:
            with self.subTest(url=u):
                self.assertEqual(c.get(u).status_code, 200, u)
        self.assertEqual(c.get("/pupr-bandung/dashboard/xyz").status_code, 404)


class TestCsrfHtml(unittest.TestCase):
    def test_post_tanpa_token_render_403_html(self):
        c = _app(testing=False).test_client()  # CSRF aktif
        r = c.post("/login", data={"username": "admin", "password": "x"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("Permintaan Ditolak", r.get_data(as_text=True))

    def test_env_loader(self):
        from web.app import _muat_env_file
        _muat_env_file()  # tidak error bila .env tidak ada


if __name__ == "__main__":
    unittest.main()
