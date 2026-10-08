"""Uji alur Verifikasi -> Terbitkan SPK, dan batas akses antar peran.

Alur yang diuji:
  Verifikasi  = menentukan laporan mana yang SAH (terima/tolak)
  SPK         = menerbitkan SPK: memilih kontraktor, tenggat, instruksi

Keduanya dulu bercampur: tombol di Verifikasi bernama "Terbitkan SPK" padahal
hanya mengubah status disposisi. Test ini mengunci pemisahan itu.
"""
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
        s1 = simpan_sesi("u", "Jl. Uji A", "m", rows, 0, lat=-6.9, lon=107.6)
        s2 = simpan_sesi("u", "Jl. Uji B", "m", rows, 0, lat=-6.91, lon=107.61)
        r1 = rekap_temuan(s1)
        r2 = rekap_temuan(s2)
        app.extensions["d1"] = simpan_disposisi(
            s1, "BAP-A", "Jl. Uji A", -6.9, 107.6, r1["n_temuan"],
            r1["total_rp"], r1["worst"], None, "D", "Bandung", "x@y.z", "Kritis")
        app.extensions["d2"] = simpan_disposisi(
            s2, "BAP-B", "Jl. Uji B", -6.91, 107.61, r2["n_temuan"],
            r2["total_rp"], r2["worst"], None, "D", "Bandung", "x@y.z", "Tinggi")
    return app


class _Dasar(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.d1 = self.app.extensions["d1"]
        self.d2 = self.app.extensions["d2"]
        self.c = self.app.test_client()
        r = self.c.post("/login", data={"username": "admin", "password": PASS})
        self.assertEqual(r.status_code, 302)


class TestVerifikasiBukanPenerbitSpk(unittest.TestCase):
    """Verifikasi hanya memvalidasi laporan, tidak menerbitkan SPK."""

    def setUp(self):
        self.app = _app()
        self.c = self.app.test_client()
        self.c.post("/login", data={"username": "admin", "password": PASS})
        self.html = self.c.get(
            "/pupr-bandung/dashboard/verifikasi").get_data(as_text=True)

    def test_tidak_ada_tOMB_label_terbits(self):
        """Tombol tidak boleh lagi bernama "Terbitkan SPK (Proses)"."""
        self.assertNotIn('id="btn-spk"', self.html)
        self.assertNotIn("Terbitkan SPK (Proses)", self.html)
        self.assertNotIn("SPK Terbit", self.html)

    def test_ada_tOMB_terima_sah(self):
        self.assertIn('id="btn-terima"', self.html)
        self.assertIn("btn-terima", self.html)

    def test_ada_jalan_ke_penerbitan_spk(self):
        self.assertIn('id="btn-terbitkan"', self.html)
        self.assertIn('dashboard/spk?pilih=', self.html)

    def test_setiap_tOMB_punya_listener(self):
        """Tombol yang tidak punya listener adalah tombol mati."""
        markup = set(re.findall(r'<button[^>]*id="(btn-[a-z]+)"', self.html))
        listener = set(re.findall(r'getElementById\("(btn-[a-z]+)"\)'
                                  r'\.addEventListener', self.html))
        self.assertEqual(markup - listener, set(),
                         "tombol tanpa listener: %s" % (markup - listener))

    def test_tidak_ada_kata_asing_di_tampil(self):
        self.assertNotIn("ready", self.html.lower())


class TestPreselectSpk(_Dasar):
    def test_tanpa_pilih_tidak_ada_tercentang(self):
        html = self.c.get("/pupr-bandung/dashboard/spk").get_data(as_text=True)
        n = len(re.findall(r'class="pilih-titik"[^>]*\bchecked\b', html))
        self.assertEqual(n, 0)

    def test_pilih_dua_titik_tercentang(self):
        html = self.c.get(
            f"/pupr-bandung/dashboard/spk?pilih={self.d1},{self.d2}"
        ).get_data(as_text=True)
        n = len(re.findall(r'class="pilih-titik"[^>]*\bchecked\b', html))
        self.assertEqual(n, 2)
        self.assertIn("sudah dicentang dari halaman Verifikasi", html)

    def test_pilih_satu_titik(self):
        html = self.c.get(
            f"/pupr-bandung/dashboard/spk?pilih={self.d1}").get_data(as_text=True)
        n = len(re.findall(r'class="pilih-titik"[^>]*\bchecked\b', html))
        self.assertEqual(n, 1)

    def test_pilih_sampah_tidak_meledak(self):
        for q in ("pilih=abc", "pilih=", "pilih=99999",
                  "pilih=1;drop", "pilih=-1", "pilih=1,2,3,4,5"):
            with self.subTest(q=q):
                r = self.c.get("/pupr-bandung/dashboard/spk?" + q)
                self.assertEqual(r.status_code, 200)

    def test_pilih_id_lain_tidak_tercentang(self):
        """ID di luar daftar daerah ini tidak boleh ikut tercentang."""
        html = self.c.get(
            "/pupr-bandung/dashboard/spk?pilih=99999").get_data(as_text=True)
        n = len(re.findall(r'class="pilih-titik"[^>]*\bchecked\b', html))
        self.assertEqual(n, 0)


class TestBatasAksesAntarPeran(unittest.TestCase):
    """Dinas dan kontraktor tidak boleh saling menembus."""

    def _login(self, user):
        app = _app()
        c = app.test_client()
        r = c.post("/login", data={"username": user, "password": PASS})
        return app, c, r.status_code

    def test_dinas_buka_halaman_kontraktor_tolak_jelas(self):
        """Dinas tidak boleh melihat ruang kontraktor.

        Sebelumnya dialihkan ke /login lalu balik ke dashboard dinas,
        sehingga terlihat seperti halaman hilang tanpa penjelasan.
        """
        _, c, _ = self._login("admin")
        r = c.get("/kontraktor/dashboard")
        self.assertEqual(r.status_code, 403)
        html = r.get_data(as_text=True)
        self.assertIn("Halaman Khusus Kontraktor", html)
        self.assertIn("Ke Dashboard Dinas", html)

    def test_halaman_403_peran_tidak_meloloskan_placeholder(self):
        _, c, _ = self._login("admin")
        html = c.get("/kontraktor/dashboard").get_data(as_text=True)
        self.assertNotIn("{{", html)
        self.assertNotIn("{%", html)

    def test_kontraktor_ke_dashboard_dinas_kembali_ke_ruangnya(self):
        _, c, _ = self._login("kt_mitrakarya")
        r = c.get("/pupr-bandung/dashboard", follow_redirects=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("Ruang Kerja", r.get_data(as_text=True))

    def test_api_kontraktor_tolak_untuk_dinas(self):
        _, c, _ = self._login("admin")
        self.assertEqual(c.get("/api/kontraktor/spk").status_code, 403)

    def test_kontraktor_tetap_bisa_ruangnya(self):
        _, c, _ = self._login("kt_mitrakarya")
        self.assertEqual(c.get("/kontraktor/dashboard").status_code, 200)


class TestLabelVerifikasi(unittest.TestCase):
    """Label dashboard harus jujur soal apa yang benar-benar terjadi."""

    def test_label_status_tidak_menjanji_spk(self):
        app = _app()
        c = app.test_client()
        c.post("/login", data={"username": "admin", "password": PASS})
        html = c.get("/pupr-bandung/dashboard/verifikasi").get_data(as_text=True)
        # Status "Diproses" berarti laporan sah, bukan SPK terbit.
        self.assertIn("Diterima", html)


if __name__ == "__main__":
    unittest.main()