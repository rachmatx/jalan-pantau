"""Kontrak UX Batch 2 (audit 26 Okt): umpan balik alur utama.

Yang dikunci:
- Hasil deteksi/live harus dibawa ke area pandang dan disorot, bukan muncul
  diam-diam di bawah fold.
- Hasil deteksi bertahan 24 jam (payload token, bukan base64) dan koreksi
  operator ikut tersimpan.
- Sesi live selesai menyebut jumlah titik yang siap disimpan dan memfokuskan
  tombol simpan.
- Unduh PDF memberi umpan balik sukses/gagal di gambar dan live.
- Empty state Riwayat membedakan "belum ada data" dari "filter tidak cocok";
  empty state Segmen punya CTA membuat segmen.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "web", "templates", "deteksi.html")
JS = os.path.join(ROOT, "web", "static", "js", "deteksi.js")
LIVE = os.path.join(ROOT, "web", "static", "js", "live.js")
RIWAYAT = os.path.join(ROOT, "web", "static", "js", "riwayat.js")
SEGMEN = os.path.join(ROOT, "web", "static", "js", "segmen.js")
CIVIC = os.path.join(ROOT, "web", "static", "css", "civic.css")


def _teks(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestHasilLangsungTerlihat(unittest.TestCase):
    def setUp(self):
        self.js = _teks(JS)
        self.css = _teks(CIVIC)

    def test_sukses_scroll_dan_sorot_hasil(self):
        self.assertIn("el.scrollIntoView(", self.js)
        self.assertIn('sorotBagian(hasil)', self.js,
                      "hasil gambar tidak dibawa ke area pandang")
        self.assertIn('sorotBagian(document.getElementById("tanpa-temuan"))',
                      self.js, "kartu tanpa temuan tidak disorot")
        self.assertIn('showToast("Deteksi Selesai"', self.js,
                      "tidak ada ringkasan temuan setelah deteksi")
        self.assertIn('"Tidak Ada Temuan"', self.js)

    def test_css_menyediakan_sorotan_dan_offset_header(self):
        self.assertIn(".jp-hasil-sorot", self.css)
        self.assertIn(
            "#hasil, #tanpa-temuan, #hasil-live { scroll-margin-top: 84px; }",
            self.css)


class TestHasilBertahan(unittest.TestCase):
    def setUp(self):
        self.js = _teks(JS)

    def test_ttl_24_jam_bukan_10_detik(self):
        self.assertIn("24 * 60 * 60 * 1000", self.js)
        self.assertNotIn("> 10000", self.js,
                         "TTL 10 detik lama masih dipakai")
        self.assertNotIn("setInterval", self.js,
                         "keep-alive 3 detik tidak lagi diperlukan")

    def test_koreksi_operator_ikut_disimpan(self):
        blok = self.js[
            self.js.index("async function syncVerifikasi"):
            self.js.index("function teksVerifikasi")]
        self.assertIn("simpanDeteksiRingkas(terakhir, terakhir.namaBerkas)", blok,
                      "koreksi severity/hapus tidak ikut dipersist")

    def test_restore_menampilkan_waktu_dan_status_verifikasi(self):
        self.assertIn("dipulihkan", self.js)
        self.assertIn("data.info", self.js)
        self.assertIn('document.getElementById("verifikasi-hitung")', self.js)


class TestLiveSelesai(unittest.TestCase):
    def setUp(self):
        self.live = _teks(LIVE)

    def test_selesai_menyebut_siap_disimpan_dan_fokus_ke_simpan(self):
        self.assertIn("titik siap disimpan", self.live)
        self.assertIn("sorotHasilLive()", self.live)
        self.assertIn("simpan.focus({ preventScroll: true })", self.live)
        self.assertIn('"Sesi Live Siap"', self.live)

    def test_snapshot_dikembalikan_untuk_keputusan_umpan_balik(self):
        self.assertIn("return snapshot;", self.live)
        self.assertIn('hentikan(false, "selesai")', self.live)

    def test_pdf_live_ada_status_dan_toast(self):
        self.assertIn("Membuat laporan PDF…", self.live)
        self.assertIn('showToast("PDF Terunduh"', self.live)
        self.assertIn('showToast("Gagal Membuat PDF"', self.live)


class TestPdfGambar(unittest.TestCase):
    def test_pdf_gambar_ada_status_dan_toast(self):
        js = _teks(JS)
        self.assertIn("Membuat laporan PDF…", js)
        self.assertIn('showToast("PDF Terunduh"', js)
        self.assertIn('showToast("Gagal Membuat PDF"', js)


class TestEmptyState(unittest.TestCase):
    def test_riwayat_membedakan_filter_kosong(self):
        js = _teks(RIWAYAT)
        self.assertIn("Tidak ada riwayat yang cocok", js)
        self.assertIn("data-reset-filter", js)
        self.assertIn("resetFilter", js)
        self.assertIn("adaFilterAktif", js,
                      "cabang empty state harus melihat filter aktif, "
                      "bukan total_db yang ikut terfilter")

    def test_segmen_empty_state_punya_cta_buat(self):
        js = _teks(SEGMEN)
        self.assertIn("jp-empty", js)
        self.assertIn("Belum ada segmen", js)
        self.assertIn("data-buat", js)
        self.assertIn('document.getElementById("btn-buat")', js)


if __name__ == "__main__":
    unittest.main()
