"""Uji anti-duplikat simpan riwayat.

- Idempotensi: simpan ulang dengan client_ref sama -> id sama, tidak ada baris baru.
- Heuristik koordinat: titik sama dalam 10 menit -> dicegah (duplikat) kecuali
  diminta eksplisit lewat izinkan_duplikat.
"""
import os
import tempfile
import unittest


def _client():
    app, c = _app_client()
    # Simpan riwayat kini butuh login (deferred login) -> masuk dulu.
    from database import AKUN_DEMO
    c.post("/login", data={"username": AKUN_DEMO[0], "password": AKUN_DEMO[1]})
    return c


def _app_client():
    """Return (app, client). Butuh app kalau test mau membaca DB langsung."""
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():  # seed admin di DB sementara (sebelum login)
        from database import migrasi_admin_v2, migrasi_sesi_v2, init_admin
        migrasi_admin_v2()
        migrasi_sesi_v2()
        init_admin()
    return app, app.test_client()


ROWS = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
         "skor_prioritas": 90}]


class TestDuplikatRiwayat(unittest.TestCase):
    def _simpan(self, c, **extra):
        payload = {"sumber": "uji", "lokasi": "Jl Uji", "model": "m",
                   "rows": ROWS, "total": 1000}
        payload.update(extra)
        return c.post("/api/riwayat", json=payload)

    def test_client_ref_idempoten(self):
        c = _client()
        r1 = self._simpan(c, lat=-6.9, lon=107.6, client_ref="ref-A")
        r2 = self._simpan(c, lat=-6.9, lon=107.6, client_ref="ref-A")
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.get_json()["id"], r2.get_json()["id"])
        self.assertTrue(r2.get_json().get("duplikat"))

    def test_koordinat_sama_dicegah(self):
        c = _client()
        r1 = self._simpan(c, lat=-6.9111, lon=107.6111, client_ref="a")
        r2 = self._simpan(c, lat=-6.9111, lon=107.6111, client_ref="b")
        j2 = r2.get_json()
        self.assertTrue(j2.get("duplikat"))
        self.assertEqual(j2.get("alasan"), "koordinat")
        self.assertEqual(j2["id"], r1.get_json()["id"])

    def test_izinkan_duplikat_bypass(self):
        c = _client()
        r1 = self._simpan(c, lat=-6.9222, lon=107.6222, client_ref="a")
        r2 = self._simpan(c, lat=-6.9222, lon=107.6222, client_ref="b",
                          izinkan_duplikat=True)
        self.assertFalse(r2.get_json().get("duplikat"))
        self.assertNotEqual(r1.get_json()["id"], r2.get_json()["id"])

    def test_tanpa_koordinat_tidak_dicegah(self):
        c = _client()
        self._simpan(c, client_ref="a")
        r2 = self._simpan(c, client_ref="b")
        self.assertFalse(r2.get_json().get("duplikat"))


