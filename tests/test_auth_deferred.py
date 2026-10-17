"""Uji deferred login & sesi 8 jam tetap.

- Simpan riwayat (foto & live snapshot) butuh login -> 401 tanpa sesi.
- Lihat snapshot live (tabel temuan) TIDAK butuh login: tanpa sesi pun 400
  (belum ada track), bukan 401.
- POST /api/login (JSON): sukses -> 200 + sesi; gagal -> 401.
- Sesi kedaluwarsa: login_at lebih tua dari batas -> 401 + pesan khusus.
- Halaman publik tetap terbuka tanpa login; /kalibrasi redirect ke login.
"""
import os
import tempfile
import time
import unittest


def _app_client():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import migrasi_admin_v2, migrasi_sesi_v2, init_admin
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app, app.test_client()


def _login(c):
    from database import AKUN_DEMO
    return c.post("/login", data={"username": AKUN_DEMO[0],
                                  "password": AKUN_DEMO[1]})


PAYLOAD = {"sumber": "uji", "lokasi": "Jl Uji", "model": "m",
           "rows": [{"kelas": "pothole", "severity": "Berat"}],
           "total": 1, "lat": -6.9, "lon": 107.6}


class TestDeferredLogin(unittest.TestCase):
    def test_simpan_tanpa_login_401(self):
        _, c = _app_client()
        r = c.post("/api/riwayat", json=PAYLOAD)
        self.assertEqual(r.status_code, 401)
        self.assertIn("Login", r.get_json()["error"])

    def test_snapshot_tanpa_login_tetap_terbuka(self):
        """Lihat tabel temuan tidak digerbangi login (hanya aksi simpan).

        Tanpa sesi pun endpoint mengembalikan 400 "belum ada track", bukan 401.
        """
        _, c = _app_client()
        r = c.post("/api/stream/snapshot", json={})
        self.assertEqual(r.status_code, 400)

    def test_api_login_json_sukses(self):
        _, c = _app_client()
        from database import AKUN_DEMO
        r = c.post("/api/login", json={"username": AKUN_DEMO[0],
                                       "password": AKUN_DEMO[1]})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("ok"))
        # sesudah login, simpan berhasil
        r2 = c.post("/api/riwayat", json=dict(PAYLOAD, client_ref="t1"))
        self.assertEqual(r2.status_code, 200)

    def test_api_login_json_gagal(self):
        _, c = _app_client()
        r = c.post("/api/login", json={"username": "admin",
                                       "password": "salah"})
        self.assertEqual(r.status_code, 401)

    def test_sesi_kedaluwarsa_8jam(self):
        app, c = _app_client()
        _login(c)
        batas = app.config["PERMANENT_SESSION_LIFETIME"].total_seconds()
        self.assertEqual(batas, 8 * 3600)
        # mundurkan login_at melewati batas
        with c.session_transaction() as s:
            s["login_at"] = time.time() - batas - 60
        r = c.post("/api/riwayat", json=PAYLOAD)
        self.assertEqual(r.status_code, 401)
        self.assertIn("berakhir", r.get_json()["error"])

    def test_halaman_publik_tanpa_login(self):
        _, c = _app_client()
        for path in ["/", "/peta", "/riwayat", "/tentang"]:
            self.assertEqual(c.get(path).status_code, 200, path)

    def test_kalibrasi_tanpa_login_redirect(self):
        _, c = _app_client()
        r = c.get("/kalibrasi")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login", r.headers["Location"])


if __name__ == "__main__":
    unittest.main()
