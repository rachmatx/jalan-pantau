"""Penjaga UX keadaan "tanpa temuan": harus TERLIHAT sebagai peringatan.

Alasan kuatnya bukan estetika: "tidak ada temuan" mudah disalahartikan sebagai
"jalan aman", padahal model bisa melewatkan kerusakan (recall pothole kecil
hanya ~41% di BPID). Sebelum perbaikan ini pesannya hanya satu kalimat panjang
abu-abu di statusbar dan tidak ada kartu peringatan sama sekali.

Yang dikunci di sini adalah hal-hal yang rusak DIAM-DIAM:
- kontrak CSS<->JS: kartu memakai `display:flex`, sehingga atribut `hidden`
  hanya berfungsi karena aturan global `[hidden] { display: none !important }`.
  Kalau aturan itu hilang/berubah, kartu "tanpa temuan" akan MUNCUL SELALU
  (termasuk saat ada temuan) tanpa galat apa pun di konsol;
- kelas `.jp-status.kosong` sudah ada di CSS tetapi dulu tidak pernah dipakai
  JS (aturan mati) — sekarang dikunci agar tetap terpakai;
- pesan statusbar tetap RINGKAS; penjelasan panjang pindah ke kartu.
"""
import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = os.path.join(ROOT, "web", "templates", "deteksi.html")
CIVIC = os.path.join(ROOT, "web", "static", "css", "civic.css")
JS = os.path.join(ROOT, "web", "static", "js", "deteksi.js")

# Emoji + dingbat + simbol + panah: rentang yang sama dengan guard repo
# (scripts/grep-emoji.cjs). Ikon UI harus SVG, bukan karakter.
DILARANG = re.compile(
    "[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F"
    "\u2049\u203C\u2139\u2190-\u21FF]")


def _teks(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestKartuTanpaTemuan(unittest.TestCase):
    def setUp(self):
        self.tpl = _teks(TEMPLATE)
        self.css = _teks(CIVIC)
        self.js = _teks(JS)

    def _blok_kartu(self):
        i = self.tpl.index('id="tanpa-temuan"')
        blok = self.tpl[i:]
        return blok[:blok.index("</section>")]

    def _badan(self, nama):
        """Isi satu fungsi JS. Penutup `}` pada kolom 0 = akhir fungsi."""
        m = re.search(r"function %s\([^)]*\)\s*\{(.*?)\n\}" % nama,
                      self.js, re.S)
        self.assertIsNotNone(m, "fungsi %s tidak ditemukan di deteksi.js" % nama)
        return m.group(1)

    def test_template_punya_kartu_tersembunyi_dengan_slot_isi(self):
        m = re.search(r"<section[^>]*id=\"tanpa-temuan\"[^>]*>", self.tpl)
        self.assertIsNotNone(m, "kartu #tanpa-temuan tidak ada di template")
        tag = m.group(0)
        self.assertIn("hidden", tag,
                      "kartu harus tersembunyi saat halaman dimuat")
        self.assertIn("jp-tanpa-temuan", tag, "kartu harus memakai kelas gayanya")
        for slot in ("tanpa-sebab", "tanpa-coba"):
            self.assertIn('id="%s"' % slot, self.tpl, "slot #%s hilang" % slot)

    def test_ikon_svg_bukan_emoji(self):
        blok = self._blok_kartu()
        self.assertIn("<svg", blok, "kartu butuh ikon SVG")
        m = DILARANG.search(blok)
        self.assertIsNone(
            m, "kartu memakai karakter terlarang %r (pakai SVG)"
            % (m and m.group()))

    def test_aturan_hidden_global_ada(self):
        """Kartu memakai display:flex -> `hidden` hanya jalan berkat [hidden]."""
        self.assertRegex(self.css,
                         r"\[hidden\]\s*\{\s*display\s*:\s*none\s*!?\s*important")
        blok = re.search(r"\.jp-tanpa-temuan\s*\{([^}]*)\}", self.css)
        self.assertIsNotNone(blok, ".jp-tanpa-temuan tidak ada di civic.css")
        self.assertRegex(blok.group(1), r"display\s*:\s*flex",
                         "bila bukan flex, tes [hidden] di atas tak relevan")

    def test_warna_peringatan_amber_bukan_abu_abu(self):
        blok = re.search(r"\.jp-tanpa-temuan\s*\{([^}]*)\}",
                         self.css).group(1)
        self.assertIn("--jp-sev-m-bg", blok, "kartu harus memakai token amber")
        self.assertIn("--jp-sev-m-bd", blok, "kartu butuh garis tepi amber")

    def test_kelas_status_kosong_tidak_jadi_aturan_mati(self):
        self.assertRegex(self.css, r"\.jp-status\.kosong\s*\{")
        # Spesifik ke `status`, bukan sekadar `classList.add("kosong")` — string
        # itu juga cocok dengan `slot.classList.add("kosong")` milik placeholder
        # viewer, sehingga tes versi longgar tetap hijau walau statusbar tidak
        # pernah ditandai (ketahuan lewat uji mutasi).
        self.assertIn('status.classList.add("kosong")', self.js,
                      "JS tidak menandai statusbar 'kosong' -> aturan CSS mati")

    def test_kartu_dibuka_di_jalur_tanpa_temuan(self):
        # Harus tertulis sebagai pemanggilan hasil (bukan definisi fungsinya):
        # `assertIn("tampilkanTanpaTemuan(json)")` tetap hijau walau call-site
        # dihapus, karena definisinya memuat teks yang sama.
        self.assertIn("status.textContent = tampilkanTanpaTemuan(json)", self.js,
                      "jalur tanpa temuan tidak membuka kartu peringatan")

    def test_kartu_ditutup_di_jalur_ada_temuan(self):
        badan = self._badan("refreshVerifikasiUI")
        self.assertIn("sembunyikanTanpaTemuan", badan,
                      "jalur ada temuan tidak menutup kartu -> kartu bisa nyangkut")

    def test_deteksi_baru_membersihkan_kartu_dan_kelas_kosong(self):
        """Tanpa ini, kartu/kuning dari hasil sebelumnya nyangkut di hasil baru."""
        self.assertRegex(
            self.js,
            r'classList\.remove\("kosong"\);\s*\n\s*sembunyikanTanpaTemuan\(\);'
            r'\s*\n\s*status\.textContent = "Mendeteksi',
            "awal deteksi tidak mereset kartu + kelas 'kosong'")

    def test_pesan_statusbar_ringkas(self):
        self.assertNotIn(
            "Tidak ada temuan pada ambang ini.", self.js,
            "pesan lama yang panjang masih dipakai di statusbar")
        badan = re.search(r"function rincianKosong\(json\)\s*\{(.*?)\n\}",
                          self.js, re.S)
        self.assertIsNotNone(badan, "fungsi rincianKosong tidak ditemukan")
        m = re.search(r'status:\s*"([^"]*)"', badan.group(1))
        self.assertIsNotNone(m, "literal status tidak ditemukan")
        self.assertLess(
            len(m.group(1)), 45,
            "pesan statusbar harus ringkas (detail penjelasan ada di kartu)")


if __name__ == "__main__":
    unittest.main()
