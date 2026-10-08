"""Uji halaman kontraktor: daftar SPK, peta khusus, dan isolasi data."""
import os
import re
import sys
import tempfile
import unittest

PASS = os.environ.get("JP_DEMO_PASS", "jalanpantau2026")


def _app():
    sys.path.insert(0, os.getcwd())
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    with app.app_context():
        from database import (init_admin, migrasi_admin_v2, migrasi_disposisi_v2,
                              migrasi_sesi_v2, init_kontraktor, simpan_disposisi,
                              rekap_temuan, simpan_sesi)
        migrasi_admin_v2()
        migrasi_disposisi_v2()
        migrasi_sesi_v2()
        init_admin()
        init_kontraktor()
        rows = [{"kelas": "pothole", "severity": "Berat", "dasar": "18 cm",
                 "total_rp": 1500000, "total_str": "Rp1.500.000"}]
        d = []
        for i, (lat, lon) in enumerate([(-6.90, 107.60), (-6.91, 107.61),
                                        (-6.92, 107.62)]):
            s = simpan_sesi("u", f"Jl. Uji {i}", "m", rows, 0, lat=lat, lon=lon)
            r = rekap_temuan(s)
            d.append(simpan_disposisi(
                s, f"BAP-{i}", f"Jl. Uji {i}", lat, lon, r["n_temuan"],
                r["total_rp"], r["worst"], None, "D", "Bandung", "x@y.z",
                "Kritis" if i == 0 else "Tinggi"))
        app.extensions["d"] = d
    return app


def _login(app, user):
    c = app.test_client()
    r = c.post("/login", data={"username": user, "password": PASS})
    return c, r.status_code


class TestHalamanSPKSaya(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.c, self.kode = _login(self.app, "kt_mitrakarya")
        self.assertEqual(self.kode, 302)

    def test_halaman_spk_saya_ada(self):
        r = self.c.get("/kontraktor/spk")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SPK Saya", r.get_data(as_text=True))

    def test_bukan_lagi_anchor(self):
        """Menu SPK harus halaman tersendiri, bukan anchor ke beranda."""
        base = open("web/templates/kontraktor/base.html",
                    encoding="utf-8").read()
        self.assertNotIn("#daftar-spk", base)
        self.assertIn('href="/kontraktor/spk"', base)

    def test_nav_tidak_menunjuk_peta_publik(self):
        """Menu peta kontraktor tidak boleh ke /peta publik."""
        base = open("web/templates/kontraktor/base.html",
                    encoding="utf-8").read()
        self.assertNotIn('href="/peta"', base)
        self.assertIn('href="/kontraktor/peta"', base)

    def test_filter_status_valid(self):
        for s in ("Diterbitkan", "Diterima", "Dikerjakan", "Selesai"):
            with self.subTest(s=s):
                r = self.c.get("/kontraktor/spk?status=" + s)
                self.assertEqual(r.status_code, 200)

    def test_filter_status_sampah_ditolak_rapi(self):
        for q in ("status=ngawur", "status=", "status=<script>",
                  "status=" + "A" * 500):
            with self.subTest(q=q[:30]):
                r = self.c.get("/kontraktor/spk?" + q)
                self.assertEqual(r.status_code, 200)

    def test_beranda_tidak_menampilkan_semua_spk(self):
        html = self.c.get("/kontraktor/dashboard").get_data(as_text=True)
        self.assertNotIn("#daftar-spk", html)


class TestPetaKontraktorTerisolasi(unittest.TestCase):
    """Peta kontraktor hanya boleh berisi titik dari SPK miliknya."""

    def setUp(self):
        self.app = _app()
        self.d = self.app.extensions["d"]

        # Terbitkan SPK: 2 titik untuk KT-001, 1 titik untuk KT-002.
        admin = self.app.test_client()
        admin.post("/login", data={"username": "admin", "password": PASS})
        r1 = admin.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 1, "judul": "SPK A",
            "disposisi_ids": [self.d[0], self.d[1]]})
        self.assertEqual(r1.status_code, 200, r1.get_json())
        r2 = admin.post("/api/spk", json={
            "daerah": "Bandung", "kontraktor_id": 2, "judul": "SPK B",
            "disposisi_ids": [self.d[2]]})
        self.assertEqual(r2.status_code, 200, r2.get_json())
        self.spk_a = r1.get_json()["id"]

    def test_peta_kontraktor_ada(self):
        c, _ = _login(self.app, "kt_mitrakarya")
        r = c.get("/kontraktor/peta")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Peta Tugas", r.get_data(as_text=True))

    def test_api_peta_kontraktor_hanya_titiknya(self):
        c, _ = _login(self.app, "kt_mitrakarya")
        titik = c.get("/api/kontraktor/peta").get_json()
        # Hanya 2 titik milik KT-001; titik KT-002 tidak boleh muncul.
        self.assertEqual(len(titik), 2)
        nomor = {t["bap_nomor"] for t in titik}
        self.assertIn("BAP-0", nomor)
        self.assertIn("BAP-1", nomor)
        self.assertNotIn("BAP-2", nomor,
                         "titik kontraktor lain bocor ke peta kontraktor")

    def test_kontraktor_lain_tidak_saling_lihat(self):
        c1, _ = _login(self.app, "kt_mitrakarya")
        c2, _ = _login(self.app, "kt_jalanpresisi")
        t1 = c1.get("/api/kontraktor/peta").get_json()
        t2 = c2.get("/api/kontraktor/peta").get_json()
        self.assertEqual(len(t1), 2)
        self.assertEqual(len(t2), 1)
        self.assertNotEqual({t["spk_id"] for t in t1},
                            {t["spk_id"] for t in t2})

    def test_halaman_peta_tidak_memakai_endpoint_publik(self):
        """Peta kontraktor harus punya sumber data sendiri.

        Data titik dirender server-side, jadi halaman tidak boleh memanggil
        endpoint peta publik yang mengembalikan seluruh riwayat semua orang.
        """
        c, _ = _login(self.app, "kt_mitrakarya")
        halaman = c.get("/kontraktor/peta").get_data(as_text=True)
        skrip = halaman.split("<script")[-1]
        # Tidak boleh fetch ke endpoint peta publik.
        self.assertNotIn('fetch("/api/peta")', skrip)
        self.assertNotIn("'/api/peta'", skrip)
        # Titik dirender server-side, jadi datanya harus ada di halaman.
        self.assertIn("var TITIK = [", halaman)
        self.assertIn("BAP-0", halaman)
        self.assertNotIn("BAP-2", halaman,
                         "titik kontraktor lain bocor ke halaman peta kontraktor")

    def test_halaman_peta_tidak_perlu_login_umum(self):
        """Peta publik tetap bisa dibuka tanpa login (halaman umum)."""
        c = self.app.test_client()
        self.assertEqual(c.get("/peta").status_code, 200)

    def test_titik_koordinat_null_tidak_muncul(self):
        """Titik tanpa koordinat tidak bisa digambar, jadi tidak dikirim."""
        c, _ = _login(self.app, "kt_mitrakarya")
        for t in c.get("/api/kontraktor/peta").get_json():
            self.assertIsNotNone(t["lat"])
            self.assertIsNotNone(t["lon"])

    def test_footo_bukti_terlihat_di_peta(self):
        c, _ = _login(self.app, "kt_mitrakarya")
        titik = c.get("/api/kontraktor/peta").get_json()
        self.assertTrue(all("ada_foto" in t for t in titik))
        self.assertTrue(all("ada_gambar" in t for t in titik))


class TestHalamanBaruTerlindungi(unittest.TestCase):
    def test_tanpa_login_halaman_diarahkan(self):
        """Halaman HTML tanpa login -> redirect ke form login."""
        c = _app().test_client()
        for p in ("/kontraktor/spk", "/kontraktor/peta"):
            with self.subTest(p=p):
                self.assertEqual(c.get(p).status_code, 302)

    def test_tanpa_login_api_json_401(self):
        """Endpoint API tanpa login -> JSON 401, bukan redirect HTML."""
        c = _app().test_client()
        r = c.get("/api/kontraktor/peta")
        self.assertEqual(r.status_code, 401)
        self.assertIn("error", r.get_json())

    def test_dinas_tidak_bisa_buka_halaman_kontraktor(self):
        c, _ = _login(_app(), "admin")
        for p in ("/kontraktor/spk", "/kontraktor/peta"):
            with self.subTest(p=p):
                self.assertEqual(c.get(p).status_code, 403)


if __name__ == "__main__":
    unittest.main()