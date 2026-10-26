"""Kontrak UX Batch 1 (audit 26 Okt): label jujur, penanda admin, pemulihan
kegagalan deteksi, dan menu mobile yang bisa ditutup wajar.

Tes ini mengunci hal yang mudah rusak tanpa terlihat:
- KPI "TINGKAT TERPARAH" harus berasal dari severity sebenarnya, bukan
  hitungan "Berat (0)" yang bertentangan dengan data.
- Tombol simpan harus memberi tahu syarat login SEBELUM operator menyelesaikan
  deteksi, bukan setelah POST ditolak 401.
- Kegagalan fetch tidak boleh meninggalkan overlay "Menganalisis…" selamanya.
- Esc/tap luar wajib menutup tray navigasi dan mengembalikan fokus.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "web", "templates", "deteksi.html")
BASE = os.path.join(ROOT, "web", "templates", "base.html")
LOGIN = os.path.join(ROOT, "web", "templates", "login.html")
JS = os.path.join(ROOT, "web", "static", "js", "deteksi.js")
CIVIC = os.path.join(ROOT, "web", "static", "css", "civic.css")
USER_FLOW = os.path.join(ROOT, "docs", "User-Flow.md")


def _teks(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestLabelDanKPI(unittest.TestCase):
    def setUp(self):
        self.tpl = _teks(TEMPLATE)
        self.js = _teks(JS)
        self.login = _teks(LOGIN)

    def test_kpi_tingkat_terparah_memakai_severity_sebenarnya(self):
        self.assertIn("function tingkatTerparah(rows)", self.js)
        self.assertIn(
            'document.getElementById("berat-nilai").textContent = tingkatTerparah(rows)',
            self.js,
            "KPI harus diisi hasil tingkatTerparah, bukan hitungan Berat")
        self.assertNotIn("Berat (${nBerat})", self.js,
                         "hitungan 'Berat (0)' lama masih dipakai")
        self.assertNotIn('"Berat (" + nBerat', self.js,
                         "jalur restore masih memakai hitungan 'Berat (n)'")
        self.assertNotIn(">Berat (0)<", self.tpl,
                         "nilai awal template masih menyesatkan")

    def test_label_satu_istilah_satu_konsep(self):
        blok_unduh = self.tpl[
            self.tpl.index('id="unduh-live"'):self.tpl.index('id="simpan-live"')]
        self.assertIn("Unduh Laporan PDF", blok_unduh)
        awal_simpan = self.tpl.index('id="simpan-live"')
        blok_simpan = self.tpl[awal_simpan:self.tpl.index("</div>", awal_simpan)]
        self.assertIn("Simpan ke Riwayat", blok_simpan)
        self.assertNotIn("Simpan Sesi", self.tpl,
                         "satu konsep masih punya dua label")
        self.assertIn("<h1>Masuk</h1>", self.login)
        self.assertNotIn("<h1>Login</h1>", self.login)


class TestPenandaAdmin(unittest.TestCase):
    def setUp(self):
        self.tpl = _teks(TEMPLATE)
        self.css = _teks(CIVIC)
        self.user_flow = _teks(USER_FLOW)

    def test_badge_admin_tampil_untuk_pengunjung_publik(self):
        self.assertIn('{% if not session.get("admin_id") %}', self.tpl)
        self.assertGreaterEqual(
            self.tpl.count("jp-need-admin"), 2,
            "badge harus ada di tombol simpan gambar DAN live")
        self.assertIn("Butuh sesi admin", self.tpl)
        self.assertIn(".jp-need-admin", self.css)

    def test_dokumentasi_tidak_menjanjikan_simpan_tanpa_login(self):
        baris_operator = next(
            l for l in self.user_flow.splitlines()
            if l.startswith("| **Operator**"))
        self.assertNotIn("simpan riwayat", baris_operator,
                         "docs masih bilang operator publik bisa simpan")
        self.assertIn("`POST /api/riwayat`", self.user_flow,
                      "POST /api/riwayat harus tercantum sebagai aksi butuh login")


class TestPemulihanKegagalan(unittest.TestCase):
    def setUp(self):
        self.tpl = _teks(TEMPLATE)
        self.js = _teks(JS)
        self.css = _teks(CIVIC)

    def test_blok_error_inline_ada_dan_tersembunyi_awal(self):
        tag = re.search(r'<div[^>]*id="galat-deteksi"[^>]*>', self.tpl)
        self.assertIsNotNone(tag, "blok #galat-deteksi tidak ada")
        self.assertIn("hidden", tag.group(0))
        self.assertIn('role="alert"', tag.group(0))
        self.assertIn('id="galat-deteksi-pesan"', self.tpl)
        self.assertIn('id="galat-deteksi-ulang"', self.tpl)
        self.assertIn(".jp-inline-error", self.css)

    def test_catch_menghentikan_overlay_dan_menawarkan_coba_lagi(self):
        self.assertIn("tampilkanGalatDeteksi(err.message)", self.js)
        self.assertIn("slot.innerHTML = window.__jpPratinjauUrl", self.js,
                      "viewer tidak dikembalikan ke pratinjau setelah gagal")
        self.assertIn('form.requestSubmit()', self.js,
                      "tombol Coba lagi tidak memicu ulang form")
        self.assertIn("sembunyikanGalatDeteksi();", self.js,
                      "error lama tidak dibersihkan saat deteksi baru")


class TestMenuMobile(unittest.TestCase):
    def setUp(self):
        self.base = _teks(BASE)
        self.css = _teks(CIVIC)

    def test_esc_dan_tap_luar_menutup_tray(self):
        self.assertIn('e.key === "Escape"', self.base)
        self.assertIn("tray.contains(e.target)", self.base)
        self.assertIn('t.focus()', self.base,
                      "fokus tidak dikembalikan ke tombol menu")
        self.assertIn('"Tutup menu navigasi"', self.base)

    def test_ikon_berubah_menjadi_x_saat_terbuka(self):
        self.assertIn(".nav-toggle.terbuka span:nth-child(1)", self.css)
        self.assertRegex(self.css, r"\.nav-toggle\.terbuka span:nth-child\(1\)\s*\{[^}]*rotate\(45deg\)")


if __name__ == "__main__":
    unittest.main()
