"""Uji helper penanda tenggat SPK.

Fungsinya kecil tapi memengaruhi urgensi: kalau salah, SPK telat bisa
terlihat aman atau sebaliknya. Karena itu batasannya diuji langsung.
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())


def _app():
    import web.app as app_mod
    app = app_mod.create_app()
    app.config["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "t.db")
    app.config["TESTING"] = True
    return app


class TestStatusTenggat(unittest.TestCase):
    def setUp(self):
        self.app = _app()
        self.ctx = self.app.test_request_context("/")
        self.ctx.push()
        from web.app import status_tenggat
        self.f = status_tenggat

    def tearDown(self):
        self.ctx.pop()

    def _tgl(self, offset_hari):
        from datetime import date, timedelta
        return (date.today() + timedelta(days=offset_hari)).isoformat()

    def test_tanpa_tenggat_tidak_ada_urgensi(self):
        label, kelas = self.f(None, "Dikerjakan")
        self.assertIsNone(label)
        self.assertEqual(kelas, "")

    def test_tenggat_aman(self):
        label, kelas = self.f(self._tgl(30), "Dikerjakan")
        self.assertIn("30 hari lagi", label)
        self.assertEqual(kelas, "tenggat-aman")

    def test_tenggat_dekat(self):
        label, kelas = self.f(self._tgl(2), "Dikerjakan")
        self.assertIn("2 hari lagi", label)
        self.assertEqual(kelas, "tenggat-dekat")

    def test_jatuh_tempo_hari_ini(self):
        label, kelas = self.f(self._tgl(0), "Dikerjakan")
        self.assertEqual(label, "Jatuh tempo hari ini")
        self.assertEqual(kelas, "tenggat-hari-ini")

    def test_telat(self):
        label, kelas = self.f(self._tgl(-3), "Dikerjakan")
        self.assertIn("Telat 3 hari", label)
        self.assertEqual(kelas, "tenggat-lewat")

    def test_status_akhir_tidak_punya_urgensi(self):
        for s in ("Diterima Dinas", "Dibatalkan"):
            with self.subTest(status=s):
                label, _ = self.f(self._tgl(-5), s)
                self.assertIsNone(label)

    def test_tanggal_rusak_tidak_melempar(self):
        label, kelas = self.f("bukan-tanggal", "Dikerjakan")
        self.assertIsNone(label)
        self.assertEqual(kelas, "")

    def test_tenggat_dengan_jam_diterima(self):
        """Kolom bisa menyimpan ISO berjam; bagian tanggal tetap dipakai."""
        label, kelas = self.f(self._tgl(1) + "T10:00:00", "Dikerjakan")
        self.assertEqual(kelas, "tenggat-dekat")


class TestNavigasiLayarKecil(unittest.TestCase):
    """Sidebar tidak boleh hilang tanpa ada cara membukanya."""

    def test_tombol_menu_ada_di_kedua_layout(self):
        for nama in ("dashboard/base.html", "kontraktor/base.html"):
            with self.subTest(layout=nama):
                src = open(f"web/templates/{nama}", encoding="utf-8").read()
                self.assertIn('id="nav-toggle"', src)
                self.assertIn('id="nav-scrim"', src)

    def test_sidebar_tidak_di_hide_total_di_hp(self):
        css = open("web/static/css/dash.css", encoding="utf-8").read()
        # Sidebar wajib punya kelas pembuka di dalam media query.
        self.assertIn("dash-sidebar-buka", css)
        # Tidak boleh ada "display: none" yang menutup sidebar di HP.
        blok = css.split("@media (max-width: 768px)")[1]
        self.assertNotIn(".dash-sidebar {\n    display: none", blok)

    def test_urutan_css_toggle_sebelum_media_query(self):
        """display:none default harus mendahului @media, kalau tidak
        menimpa display:flex yang di-set di dalam media query."""
        css = open("web/static/css/dash.css", encoding="utf-8").read()
        self.assertLess(css.index(".dash-nav-toggle { display: none; }"),
                        css.index("@media (max-width: 768px)"))


if __name__ == "__main__":
    unittest.main()