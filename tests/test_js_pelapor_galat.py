"""Penjaga: setiap handler .catch harus menerima dan melaporkan galat.

Sebelum overhaul ini ada 27 `catch(function(){...})` yang membuang objek
galat. Akibatnya penyebab kegagalan hilang begitu toast "Kesalahan
jaringan." tampil, persis seperti bug tombol Terbitkan SPK yang baru
saja diperbaiki: tidak ada jejak apa pun untuk ditelusuri.
"""
import os
import re
import unittest

# Halaman yang punya helper bersama jp_core.js (bisa pakai jpLaporGagal).
HELPER = "web/static/js/jp_core.js"
BERKAS = [
    "web/templates/dashboard/disposisi_detail.html",
    "web/templates/dashboard/index.html",
    "web/templates/dashboard/instansi.html",
    "web/templates/dashboard/kontraktor.html",
    "web/templates/dashboard/spk.html",
    "web/templates/dashboard/spk_detail.html",
    "web/templates/kontraktor/spk_detail.html",
    "web/templates/dashboard/verifikasi.html",
    "web/static/js/deteksi.js",
    "web/static/js/disposisi.js",
    "web/static/js/live.js",
    "web/static/js/riwayat.js",
]

# Pola catch tanpa parameter -- persis yang bikin galat hilang.
TANPA_PARAM = re.compile(r"\.catch\(\s*function\(\s*\)\s*\{")
DENGAN_PARAM = re.compile(r"\.catch\(\s*function\s*\(\s*\w")


def _teks(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class TestCatchMelapor(unittest.TestCase):
    def test_tidak_ada_catch_tanpa_parameter(self):
        buruk = []
        for p in BERKAS:
            for i, ln in enumerate(_teks(p).splitlines(), 1):
                if TANPA_PARAM.search(ln):
                    buruk.append(f"{p}:{i}")
        self.assertEqual(
            buruk, [],
            "Handler .catch tanpa parameter (galat dibuang):\n  " + "\n  ".join(buruk))

    def test_setiap_catch_memanggil_pelapor(self):
        """Setiap .catch(function(e){ ... }) harus melapor galatnya.

        Dicek per blok handler, bukan per baris, karena pelapor boleh
        ditulis di baris berikutnya seperti di kebanyakan template.
        """
        kurang = []
        for p in BERKAS:
            src = _teks(p)
            for m in DENGAN_PARAM.finditer(src):
                # ambil teks handler sampai .then/.catch berikutnya
                acct = src[m.start():m.start() + 600]
                if ("jpLaporGagal(" not in acct
                        and "jpLaporGagalSekali(" not in acct
                        and "console.error" not in acct
                        and "console.warn" not in acct):
                    baris = src[:m.start()].count("\n") + 1
                    kurang.append(f"{p}:{baris}")
        self.assertEqual(
            kurang, [],
            "Handler .catch yang menerima 'e' tapi tidak melapor:\n  "
            + "\n  ".join(kurang))

    def test_pelapor_terdefinisi_di_helper(self):
        src = _teks(HELPER)
        self.assertIn("window.jpLaporGagal =", src)
        self.assertIn("window.jpLaporGagalSekali =", src)

    def test_halaman_spk_memakai_helper_teririt(self):
        """Tombol Terbitkan wajib punya jejak galat; dulu tidak ada sama sekali."""
        src = _teks("web/templates/dashboard/spk.html")
        self.assertIn('getElementById("btn-terbitkan")', src)
        self.assertIn('window.jpLaporGagal("terbitkan SPK"', src)


class TestTanpaArtefakBahasa(unittest.TestCase):
    def test_tidak_ada_huruf_cjk_atau_cyrillic(self):
        """Komentar helper sempat sempat berisi huruf CJK/cyrillic."""
        pola = re.compile(r"[\u0400-\u04FF\u4E00-\u9FFF\u3040-\u30FF]")
        for p in BERKAS + [HELPER]:
            for i, ln in enumerate(_teks(p).splitlines(), 1):
                m = pola.search(ln)
                if m:
                    self.fail(f"{p}:{i} ada huruf '{m.group()}' di: {ln.strip()}")