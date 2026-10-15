"""Cek sintaks JavaScript inline pada template dashboard.

Pagination diubah dari loop for ke forEach beberapa waktu lalu; sisa
kurung kurawet yang tidak seimbang tidak akan tertangkap test Python
karena template hanya dirender sebagai teks.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())

TARGET = [
    "web/templates/dashboard/base.html",
    "web/templates/kontraktor/base.html",
    "web/templates/dashboard/index.html",
    "web/templates/dashboard/instansi.html",
    "web/templates/dashboard/kontraktor.html",
    "web/templates/dashboard/spk.html",
    "web/templates/dashboard/spk_detail.html",
    "web/templates/dashboard/verifikasi.html",
    "web/templates/kontraktor/index.html",
    "web/templates/kontraktor/peta.html",
    "web/templates/kontraktor/spk_list.html",
    "web/templates/kontraktor/spk_detail.html",
    "web/templates/dashboard/disposisi_detail.html",
    "web/templates/disposisi_detail.html",
]


def _script_inline(path):
    with open(path, encoding="utf-8") as f:
        html = f.read()
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)


def _bersihkan_jinja(js):
    """Ganti placeholder Jinja supaya snippet bisa diuji node --check.

    Tiga bentuk, karena fungsinya berbeda:
    - pemisah loop  {{ "," if not loop.last }} -> dihapus. Koma JEJAK
      sah di JavaScript, jadi [{a}, {b}, ] tetap valid; kalau diganti
      nilai lain, koma antar elemen ikut hilang dan sintaks pecah.
    - di dalam ekspresi -> _J_ (identifier polos, aman di dalam string)
    - berdiri sendiri di luar ekspresi -> 0, supaya tidak jadi
      pernyataan liar.
    Nilai aslinya tidak relevan untuk pemeriksaan sintaks; yang penting
    kurung kurawet dan koma antar elemen tetap utuh.
    """
    js = re.sub(r"\{\{\s*[\"'][^\"']*[\"']\s*if\s+not\s+loop\.last\s*\}\}", "", js)
    js = re.sub(r"\{%.*?%\}", "", js, flags=re.S)

    def ganti(m):
        baris = js.rfind("\n", 0, m.start()) + 1
        return "0" if not js[baris:m.start()].strip() else "_J_"

    return re.sub(r"\{\{.*?\}\}", ganti, js, flags=re.S)


class TestSintaksInline(unittest.TestCase):
    def test_semua_script_inline_valid(self):
        for path in TARGET:
            with self.subTest(template=os.path.basename(path)):
                for i, js in enumerate(_script_inline(path)):
                    if not js.strip():
                        continue
                    # Tag <script> nyasar di dalam blok berarti template
                    # rusak dan browser akan salah memotong blok script.
                    self.assertNotIn("<script", js, f"blok #{i} pada {path}")
                    with tempfile.NamedTemporaryFile(
                            "w", suffix=".js", delete=False, encoding="utf-8") as tmp:
                        tmp.write(_bersihkan_jinja(js))
                        nama = tmp.name
                    try:
                        hasil = subprocess.run(
                            ["node", "--check", nama],
                            capture_output=True, text=True)
                        self.assertEqual(
                            hasil.returncode, 0,
                            f"blok script #{i} pada {path}:\n{hasil.stderr}")
                    finally:
                        os.unlink(nama)


class TestPaginasiSeragam(unittest.TestCase):
    """Tiga daftar besar harus pakai ukuran halaman dan helper yang sama."""

    HALAMAN = {
        "web/templates/dashboard/instansi.html": "PER_HALAMAN_INSTANSI = 10",
            "web/templates/dashboard/index.html": "PER_HALAMAN_DASH = 10",
    }

    def test_semua_sepuluh_per_halaman(self):
        for path, pola in self.HALAMAN.items():
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertIn(pola, src)
                # Nilai lama 25 tidak boleh tersisa untuk tabel ini.
                self.assertNotIn(pola.replace("10", "25"), src)

    def test_semua_pakai_helper_bersama(self):
        for path in self.HALAMAN:
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertIn("window.jpNomorHalaman(", src)

    def test_tidak_ada_versi_lokal_helper(self):
        """Helper hanya boleh hidup di base.html, jangan diduplikasi."""
        for path in self.HALAMAN:
            if path.endswith("base.html"):
                continue
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertNotIn("function nomorHalamanTampil", src)

    def test_handler_pakai_data_hal(self):
        """Indeks DOM tidak lagi sama dengan nomor halaman saat ada elipsis."""
        for path in self.HALAMAN:
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertIn("Number(btn.dataset.hal)", src)
                self.assertNotIn("= idx + 1", src)

    def test_halaman_dijepit_ketidak_hilang(self):
        """Setelah data dihapus, halaman aktif tidak boleh di luar jangkauan."""
        for path in self.HALAMAN:
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertRegex(src, r"if \(halaman\D* > totalHal\)")

    def test_helper_ada_di_satu_berkas(self):
        src = open("web/static/js/jp_core.js", encoding="utf-8").read()
        self.assertIn("window.jpNomorHalaman = function", src)
        # Elipsis harus berbasis selisih, bukan tebakan posisi.
        self.assertIn("daftar[i] - daftar[i - 1] > 1", src)


class TestSemuaDaftarTerbatas(unittest.TestCase):
    """Setiap daftar yang bisa bertambah harus punya batas 10 baris.

    Halaman tanpa paginasi bisa memuat ratusan baris sekaligus dan
    membuat tabel sulit dibaca. Daftar kecil yang memang statis
    (preview, tentang, detail) dikecualikan.
    """

    # (template, id container, konteks)
    DAFTAR = [
        ("web/templates/dashboard/instansi.html", "akun-tbody", "akun login"),
        ("web/templates/dashboard/instansi.html", "instansi-tbody", "instansi"),
        ("web/templates/dashboard/kontraktor.html", "kontraktor-tbody", "kontraktor"),
        ("web/templates/dashboard/spk.html", "spk-tbody", "SPK dinas"),
        ("web/templates/dashboard/spk_detail.html", "tugas-tbody", "titik SPK dinas"),
        ("web/templates/dashboard/verifikasi.html", "vrf-tbody", "laporan verifikasi"),
            ("web/templates/dashboard/index.html", None, "beranda dinas"),
        ("web/templates/kontraktor/spk_list.html", "spk-list-tbody", "SPK kontraktor"),
        ("web/templates/kontraktor/peta.html", "peta-tbody", "titik peta"),
        ("web/templates/kontraktor/spk_detail.html", "kartu-tugas", "kartu titik"),
    ]

    def test_tiap_daftar_punya_paginasi(self):
        for path, _tbody_id, nama in self.DAFTAR:
            with self.subTest(daftar=nama):
                src = open(path, encoding="utf-8").read()
                self.assertTrue(
                    "jpPaginasi(" in src or "PER_HALAMAN" in src,
                    f"{nama} di {path} belum punya paginasi")

    def test_baris_data_ditandai(self):
        """Helper hanya memaginasi baris ber-data-jp-row.

        Baris status ("belum ada data") tidak boleh ikut terpotong.
        """
        for path, tbody_id, nama in self.DAFTAR:
            if tbody_id is None:
                continue
            with self.subTest(daftar=nama):
                src = open(path, encoding="utf-8").read()
                self.assertIn(f'id="{tbody_id}"', src, f"container {tbody_id} hilang")
                self.assertIn('data-jp-row="1"', src,
                              f"{nama} tidak menandai baris data")

    def test_helper_hanya_dua_satu(self):
        """Helper jpPaginasi hanya boleh di dua base layout.

        Disalin ke tiap template berarti perbaikannya bisa terlewat di
        salah satu tempat.
        """
        base = ("web/templates/dashboard/base.html",
                "web/templates/kontraktor/base.html")
        for path in TARGET:
            if path in base:
                continue
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertNotIn("window.jpPaginasi = function", src)

    def test_helper_tidak_ditulis_ulang_di_base(self):
        """Kedua base hanya memuat helper, bukan menyalin definisinya.

        Helper pernah ditulis dua kali, sekali di tiap base layout. Perbaikan
        di satu berkas bisa terlewat di yang lain, jadi sekarang keduanya
        harus memuat satu berkas yang sama.
        """
        core = "web/static/js/jp_core.js"
        for path in ("web/templates/dashboard/base.html",
                     "web/templates/kontraktor/base.html"):
            with self.subTest(base=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertNotIn("window.jpPaginasi = function", src)
                self.assertNotIn("window.jpNomorHalaman = function", src)
                self.assertNotIn("window.jpToast = function", src)
                self.assertNotIn("window.jpConfirm = function", src)
                self.assertIn("jp_core.js", src)
        self.assertTrue(os.path.exists(core), "jp_core.js tidak ada")

    def test_ukuran_seluruh_helper_sepuluh(self):
        """Tidak boleh ada per-halaman selain 10 di helper generik."""
        src = open("web/static/js/jp_core.js", encoding="utf-8").read()
        m = re.search(r"var per = opsi\.perHalaman \|\| (\d+)", src)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), "10")

    def test_semua_panggilan_meminta_sepuluh(self):
        """Panggilan eksplisit juga harus 10, biar tidak ada yang diam-diam lain."""
        for path, _t, nama in self.DAFTAR:
            with self.subTest(daftar=nama):
                src = open(path, encoding="utf-8").read()
                for nilai in re.findall(r"perHalaman:\s*(\d+)", src):
                    self.assertEqual(nilai, "10", f"{nama} pakai {nilai}/halaman")


class TestDaftarKecilTidakDiberiPaginasi(unittest.TestCase):
    """Guard agar paginasi tidak ditambahkan ke tabel statis.

    Tabel kecil yang isinya tetap tidak akan pernah melewati 10 baris;
    memberi paginasi padanya hanya menambah kode tanpa manfaat.
    """

    STATIS = [
        "web/templates/disposisi_kirim.html",
        "web/templates/laporan_preview.html",
        "web/templates/tentang.html",
    ]

    def test_tabel_statis_tetap_tanpa_paginasi(self):
        for path in self.STATIS:
            with self.subTest(template=os.path.basename(path)):
                src = open(path, encoding="utf-8").read()
                self.assertNotIn("jpPaginasi", src)
                self.assertNotIn("data-jp-row", src)


if __name__ == "__main__":
    unittest.main()