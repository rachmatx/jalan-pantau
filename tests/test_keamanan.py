"""Uji proteksi CSRF, header keamanan, dan guard kredensial demo.

Catatan: CSRF otomatis nonaktif saat app.config["TESTING"]=True, sehingga
test lama yang POST ke /api/* tanpa token tetap hijau. Di sini kita sengaja
membuat app TANPA TESTING agar jalur CSRF benar-benar diuji.
"""
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent


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

    def test_token_lama_tetap_valid_setelah_login_modal(self):
        """Regresi: /api/login memanggil session.clear() sehingga token di
        <meta> halaman mati; retry simpan/hapus pasca-login langsung 403."""
        app = _app()
        with app.app_context():
            from database import (AKUN_DEMO, init_admin, migrasi_admin_v2,
                                  migrasi_sesi_v2)
            migrasi_admin_v2()
            migrasi_sesi_v2()
            init_admin()
        c = app.test_client()
        c.get("/")
        with c.session_transaction() as s:
            tok = s.get("_csrf")
        self.assertTrue(tok)
        r = c.post("/api/login",
                   json={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]},
                   headers={"X-CSRF-Token": tok})
        self.assertEqual(r.status_code, 200)
        # Aksi yang sama yang dipicu ulang klien memakai token lama dari meta.
        r = c.post("/api/verifikasi", json={"rows": [{"kelas": "pothole"}]},
                   headers={"X-CSRF-Token": tok})
        self.assertEqual(r.status_code, 200)

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


class TestEnvFile(unittest.TestCase):
    def test_env_file_mengisi_password_sebelum_database_diimpor(self):
        """Regresi: AKUN_DEMO dievaluasi saat import database, sedangkan .env
        baru dimuat di create_app() -> JP_DEMO_PASS dari .env diabaikan."""
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "uji.env")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write("JP_DEMO_PASS=rahasia-dari-env-file\n")
            env = dict(os.environ)
            env.pop("JP_DEMO_PASS", None)
            env["JP_ENV_FILE"] = p
            hasil = subprocess.run(
                [sys.executable, "-c",
                 "import database; print(database.AKUN_DEMO[1])"],
                cwd=str(ROOT / "web"), env=env,
                capture_output=True, text=True)
            self.assertEqual(hasil.returncode, 0, hasil.stderr)
            self.assertEqual(hasil.stdout.strip(), "rahasia-dari-env-file")


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
