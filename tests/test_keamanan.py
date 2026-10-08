"""Uji proteksi CSRF, header keamanan, dan guard kredensial demo.

Catatan: CSRF otomatis nonaktif saat app.config["TESTING"]=True, sehingga
test lama yang POST ke /api/* tanpa token tetap hijau. Di sini kita sengaja
membuat app TANPA TESTING agar jalur CSRF benar-benar diuji.
"""
import os
import tempfile
import unittest


def _app(**cfg):
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    for k, v in cfg.items():
        app.config[k] = v
    return app


class TestCsrf(unittest.TestCase):
    def test_post_tanpa_token_ditolak(self):
        app = _app()  # CSRF aktif (TESTING tidak diset)
        c = app.test_client()
        r = c.post("/api/verifikasi", json={"rows": [{"kelas": "pothole"}]})
        self.assertEqual(r.status_code, 403)
        self.assertIn("CSRF", r.get_json()["error"])

    def test_post_dengan_token_header_lolos(self):
        app = _app()
        c = app.test_client()
        c.get("/")  # memicu set token di session
        with c.session_transaction() as s:
            tok = s.get("_csrf")
        self.assertTrue(tok)
        r = c.post("/api/verifikasi", json={"rows": [{"kelas": "pothole"}]},
                   headers={"X-CSRF-Token": tok})
        self.assertNotEqual(r.status_code, 403)

    def test_login_form_punya_field_csrf(self):
        app = _app()
        c = app.test_client()
        html = c.get("/login").get_data(as_text=True)
        self.assertIn('name="_csrf"', html)

    def test_csrf_nonaktif_saat_testing(self):
        app = _app(TESTING=True)
        c = app.test_client()
        r = c.post("/api/verifikasi", json={"rows": []})
        self.assertNotEqual(r.status_code, 403)

    def test_csrf_nonaktif_via_env(self):
        os.environ["JP_CSRF"] = "0"
        try:
            app = _app()
            c = app.test_client()
            r = c.post("/api/verifikasi", json={"rows": []})
            self.assertNotEqual(r.status_code, 403)
        finally:
            os.environ.pop("JP_CSRF", None)


class TestHeaderKeamanan(unittest.TestCase):
    def test_header_ada(self):
        app = _app(TESTING=True)
        c = app.test_client()
        r = c.get("/")
        self.assertEqual(r.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(r.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertIn("Referrer-Policy", r.headers)


if __name__ == "__main__":
    unittest.main()
