"""Uji anti-duplikat simpan riwayat.

- Idempotensi: simpan ulang dengan client_ref sama -> id sama, tidak ada baris baru.
- Heuristik koordinat: titik sama dalam 10 menit -> dicegah (duplikat) kecuali
  diminta eksplisit lewat izinkan_duplikat.
"""
import os
import tempfile
import unittest


def _client():
    return _app_client()[1]


def _app_client():
    """Return (app, client). Butuh app kalau test mau membaca DB langsung."""
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    return app, app.test_client()


ROWS = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
         "total_rp": 1000, "total_str": "Rp1.000"}]


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


class TestDuplikatDisposisi(unittest.TestCase):
    """Endpoint /api/disposisi mengambil angka dari rekap tabel temuan,
    jadi bap_id WAJIB menunjuk sesi yang benar-benar ada. Setiap test
    membuat sesi nyata lebih dulu lewat /api/riwayat."""

    def _sesi(self, c, **extra):
        payload = {"sumber": "uji", "lokasi": "Jl Uji", "model": "m",
                   "rows": ROWS, "total": 1000}
        payload.update(extra)
        r = c.post("/api/riwayat", json=payload)
        self.assertEqual(r.status_code, 200, r.get_json())
        return r.get_json()["id"]

    def _p(self, c, bap_id, **extra):
        payload = {"bap_id": bap_id, "bap_nomor": f"BA-INS/{bap_id}",
                   "lokasi": "Jl Uji",
                   "n_temuan": 2, "total_rp": 1000, "worst": "Berat",
                   "instansi_id": 0, "instansi_nama": "Dinas Uji",
                   "instansi_daerah": "Bandung", "instansi_email": "a@b.c",
                   "urgensi": "Kritis", "catatan": "-"}
        payload.update(extra)
        return payload

    def test_client_ref_idempoten(self):
        c = _client()
        sid = self._sesi(c, client_ref="s-A")
        r1 = c.post("/api/disposisi", json=self._p(c, sid, client_ref="d-A"))
        r2 = c.post("/api/disposisi", json=self._p(c, sid, client_ref="d-A"))
        self.assertEqual(r1.get_json()["id"], r2.get_json()["id"])
        self.assertTrue(r2.get_json().get("duplikat"))

    def test_bap_instansi_sama_dicegah(self):
        c = _client()
        sid = self._sesi(c, client_ref="s-b")
        r1 = c.post("/api/disposisi", json=self._p(c, sid, client_ref="d-a"))
        r2 = c.post("/api/disposisi", json=self._p(c, sid, client_ref="d-b"))
        j2 = r2.get_json()
        self.assertTrue(j2.get("duplikat"))
        self.assertEqual(j2.get("alasan"), "bap_instansi")
        self.assertEqual(j2["id"], r1.get_json()["id"])

    def test_izinkan_duplikat_bypass(self):
        c = _client()
        sid = self._sesi(c, client_ref="s-c")
        r1 = c.post("/api/disposisi", json=self._p(c, sid, client_ref="d-a"))
        r2 = c.post("/api/disposisi",
                    json=self._p(c, sid, client_ref="d-b", izinkan_duplikat=True))
        self.assertFalse(r2.get_json().get("duplikat"))
        self.assertNotEqual(r1.get_json()["id"], r2.get_json()["id"])

    def test_angka_diambil_dari_temuan_bukan_client(self):
        """Regresi: total_rp & n_temuan harus sama dengan rekap temuan,
        apa pun yang dikirim client."""
        app, c = _app_client()
        sid = self._sesi(c, client_ref="s-d")   # ROWS = 1 temuan, Rp1.000
        r = c.post("/api/disposisi", json=self._p(
            c, sid, n_temuan=9999, total_rp=999_999_999_999, client_ref="d-x"))
        self.assertEqual(r.status_code, 200, r.get_json())
        did = r.get_json()["id"]
        import database
        with app.app_context():
            row = database.detail_disposisi(did)
        self.assertEqual(row["n_temuan"], 1)      # bukan 9999
        self.assertEqual(row["total_rp"], 1000)    # bukan 999.999.999.999

    def test_bap_id_tidak_ada_ditolak(self):
        """Disposisi tanpa sesi nyata harus ditolak (anti injeksi)."""
        c = _client()
        r = c.post("/api/disposisi", json=self._p(c, 999999, client_ref="d-y"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("tidak ada", r.get_json()["error"].lower())


if __name__ == "__main__":
    unittest.main()
