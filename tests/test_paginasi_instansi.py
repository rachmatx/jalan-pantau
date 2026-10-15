"""Kunci angka paginasi Instansi dan bentuk windowing-nya.

Nomor per halaman adalah keputusan tampilan yang mudah berubah diam-diam
(20 -> 10) dan tidak tertangkap test lain. Test ini mengunci angkanya.
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.getcwd())

SRC = "web/templates/dashboard/instansi.html"


def _teks():
    with open(SRC, encoding="utf-8") as f:
        return f.read()


class TestPaginasiInstansi(unittest.TestCase):
    def test_sepuluh_instansi_per_halaman(self):
        """Permintaan eksplisit: maksimal 10 instansi per halaman."""
        self.assertIn("PER_HALAMAN_INSTANSI = 10", _teks())
        self.assertNotIn("PER_HALAMAN_INSTANSI = 20", _teks())

    def test_halaman_dipakai_di_semua_tempat(self):
        """Semua perhitungan baris harus memakai konstanta yang sama.

        Kalau ada satu tempat yang menulis angka langsung, baris bisa
        terpotong atau melompati data.
        """
        src = _teks()
        self.assertEqual(len(re.findall(r"PER_HALAMAN_INSTANSI", src)), 6)
        # Tidak ada angka polos yang dipakai sebagai ukuran halaman.
        # Hanya pola aritmetika halaman yang diperiksa; "start + 1" di
        # dalam teks "Menampilkan 1-10 dari ..." bukan ukuran halaman.
        for pola in (r"Math\.min\(start \+ \d+",
                     r"\(halamanInstansi - 1\) \* \d+",
                     r"Math\.ceil\(total / \d+"):
            self.assertIsNone(re.search(pola, src), pola)

    def test_tidak_ada_limit_halaman_yang_ditulis_ulang(self):
        """Angka 20 yang pernah jadi per-halaman tidak boleh tersisa di template."""
        self.assertNotIn("Math.min(start + 20", _teks())

    def test_nomor_halaman_dibaca_dari_data_hal(self):
        """Handler harus pakai data-hal, bukan indeks DOM.

        Pakai indeks DOM bikin salah begitu ada elipsis atau tombol lain
        di antara nomor halaman: klik pertama bisa membuka halaman 3.
        """
        src = _teks()
        self.assertIn("Number(btn.dataset.hal)", src)
        self.assertNotIn("halamanInstansi = idx + 1", src)

    def test_elipsis_bukan_tombol(self):
        """Elipsis tidak boleh ikut punya kelas inst-pag-num."""
        self.assertIn("inst-pag-gap", _teks())
        self.assertIn('n === "..."', _teks())

    def test_helper_windowing_dipakai_bersama(self):
        """Algoritma jendela hanya hidup di base.html, bukan di salinan lokal."""
        self.assertIn("window.jpNomorHalaman(", _teks())
        self.assertNotIn("function nomorHalamanTampil", _teks())


if __name__ == "__main__":
    unittest.main()