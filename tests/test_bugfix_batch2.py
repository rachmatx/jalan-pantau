"""Regresi 10 temuan audit lanjutan (1 Nov 2026).

Mengunci bug yang lolos tes fungsional biasa:
- koreksi verifikasi salah baris setelah hasil dipulihkan (idx_asli);
- toast sukses palsu di live (retry & snapshot);
- skeleton riwayat menggantung / "DB kosong" palsu saat fetch gagal;
- jpToast/jpConfirm menyisipkan teks mentah ke innerHTML;
- balapan upload foto kalibrasi;
- marker "Lokasi Anda" hilang saat filter peta digambar ulang;
- PDF segmen kosong mencetak SDI 0 + pita kategori kosong;
- kolom UKURAN PDF meluber ke badge SEVERITY;
- elipsis PDF berubah jadi '?' (latin-1);
- teks dasar severity membulat ke sisi ambang yang salah.
"""
import os
import re
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "web"), str(ROOT / "app")):
    if p not in sys.path:
        sys.path.insert(0, p)

LAPORAN = str(ROOT / "app" / "laporan.py")
BASE = str(ROOT / "web" / "templates" / "base.html")
KALIBRASI = str(ROOT / "web" / "templates" / "kalibrasi.html")
DETEKSI_JS = str(ROOT / "web" / "static" / "js" / "deteksi.js")
LIVE_JS = str(ROOT / "web" / "static" / "js" / "live.js")
RIWAYAT_JS = str(ROOT / "web" / "static" / "js" / "riwayat.js")
PETA_JS = str(ROOT / "web" / "static" / "js" / "peta.js")


def _teks(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _fungsi(js, nama):
    m = re.search(r"(?:async\s+)?function\s+%s\([^)]*\)\s*\{(.*?)\n\}" % nama,
                  js, re.S)
    if m is None:
        raise AssertionError("fungsi %s tidak ditemukan" % nama)
    return m.group(1)


def _teks_pdf(path):
    """Ambil teks dari stream PDF fpdf2 (FlateDecode) untuk diperiksa."""
    raw = Path(path).read_bytes()
    bagian = []
    for s in re.findall(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            data = zlib.decompress(s)
        except zlib.error:
            data = s
        for m in re.finditer(rb"\((?:[^()\\]|\\.)*\)\s*Tj", data):
            isi = m.group(0)
            isi = isi[:isi.rindex(b")")][1:]
            isi = (isi.replace(rb"\(", b"(").replace(rb"\)", b")")
                   .replace(rb"\\", b"\\"))
            bagian.append(isi.decode("latin-1"))
    return " ".join(bagian)


def _angka(teks):
    return float(teks.replace(",", "."))


class TestKoreksiSetelahMuatUlang(unittest.TestCase):
    """Payload hasil verifikasi membawa idx_asli yang tidak lagi berurutan."""

    def _rows(self):
        return [
            {"kelas": "pothole", "conf": 0.8, "severity": "Berat",
             "box": [0, 0, 80, 80], "idx_asli": 0,
             "dasar": "d", "bahan": "b", "skor_prioritas": 33},
            {"kelas": "transverse_crack", "conf": 0.5, "severity": "Ringan",
             "box": [0, 0, 400, 8], "idx_asli": 2,
             "dasar": "d", "bahan": "b", "skor_prioritas": 33},
        ]

    def test_koreksi_severity_memakai_idx_asli(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi(self._rows(),
                                         severity={"2": "Berat"})
        self.assertEqual(info["severity"], 1, "koreksi idx_asli=2 tidak masuk")
        self.assertEqual(baru[1]["severity"], "Berat")
        self.assertEqual(baru[1]["idx_asli"], 2)

    def test_hapus_memakai_idx_asli(self):
        from deteksi import terapkan_koreksi
        baru, _, info = terapkan_koreksi(self._rows(), hapus=[2])
        self.assertEqual(info["hapus"], 1, "hapus idx_asli=2 tidak masuk")
        self.assertEqual(len(baru), 1)
        self.assertEqual(baru[0]["idx_asli"], 0)

    def test_idx_asli_dipertahankan_bukan_dinomori_ulang(self):
        from deteksi import terapkan_koreksi
        baru, _, _ = terapkan_koreksi(self._rows())
        self.assertEqual([r["idx_asli"] for r in baru], [0, 2])

    def test_frontend_mencari_baris_berdasarkan_idx_asli(self):
        js = _teks(DETEKSI_JS)
        self.assertNotIn("barisAsli[Number(ia)]", js,
                         "lookup posisi array gagal saat idx_asli berlubang")
        self.assertIn("barisAsliDenganId", js)
        self.assertIn("barisAsliDenganId(ia)", js)


class TestLiveTidakBerbohong(unittest.TestCase):
    def test_mulai_meneruskan_galat(self):
        blok = _fungsi(_teks(LIVE_JS), "mulai")
        self.assertIn("throw err", blok,
                      "mulai() menelan galat sehingga retry selalu 'sukses'")

    def test_snapshot_gagal_tidak_diumumkan_sukses(self):
        js = _teks(LIVE_JS)
        awal = js.index('var btnSnap = document.getElementById("btn-snapshot")')
        blok = js[awal:awal + 900]
        self.assertIn("if (!snap)", blok,
                      "handler snapshot merayakan sukses walau ambilSnapshot() "
                      "mengembalikan null")


class TestRiwayatGagalMuat(unittest.TestCase):
    def test_muat_punya_penanganan_galat(self):
        js = _teks(RIWAYAT_JS)
        blok = _fungsi(js, "muat")
        self.assertIn("try", blok)
        self.assertIn("catch", blok, "fetch gagal meninggalkan skeleton")
        self.assertIn("res.ok", blok, "HTTP 500 tetap dirender sebagai data")

    def test_ada_keadaan_galat_dan_tombol_coba_lagi(self):
        js = _teks(RIWAYAT_JS)
        self.assertIn("Gagal memuat riwayat", js)
        self.assertIn("Coba Lagi", js)


class TestEscapeToastConfirm(unittest.TestCase):
    def test_toast_dan_confirm_memakai_escape(self):
        tpl = _teks(BASE)
        self.assertIn("jpEsc", tpl)
        self.assertGreaterEqual(tpl.count("jpEsc(title"), 2,
                                "title toast/confirm masih mentah")
        self.assertGreaterEqual(tpl.count("jpEsc(message"), 2,
                                "message toast/confirm masih mentah")
        self.assertIn("jpEsc(opts.okText", tpl)
        self.assertIn("jpEsc(opts.cancelText", tpl)


class TestBalapanUploadKalibrasi(unittest.TestCase):
    def test_token_dinaikkan_sebelum_fetch(self):
        tpl = _teks(KALIBRASI)
        awal = tpl.index('id="foto-penggaris"')
        if "addEventListener('change'" not in tpl[awal:]:
            awal = tpl.index("foto-penggaris")
        fetch_i = tpl.index("fetch('/api/kalibrasi/foto'", awal)
        token_i = tpl.index("++muatToken", awal)
        self.assertLess(token_i, fetch_i,
                        "token baru naik setelah respons: balapan tetap terjadi")
        self.assertGreaterEqual(tpl.count("token !== muatToken"), 2,
                                "respons usang harus dibuang, termasuk saat galat")


class TestMarkerPenggunaBertahan(unittest.TestCase):
    def test_marker_dipasang_ulang_setelah_clear_layers(self):
        js = _teks(PETA_JS)
        self.assertRegex(js, r"(?:var|let|const)\s+markerLokasi\s*=\s*null")
        blok = _fungsi(js, "gambar")
        self.assertIn("markerLokasi", blok,
                      "clearLayers() menghapus marker Lokasi Anda")
        self.assertIn("gpsMarker", blok,
                      "marker GPS live juga ikut terhapus clearLayers()")


class TestPdfSegmenKosong(unittest.TestCase):
    def _pdf(self):
        from laporan import buat_laporan_segmen
        detail = {
            "id": 1, "nama": "Segmen Kosong", "jalan": "Jl. Uji",
            "panjang_m": 100, "lebar_m": 6, "sdi_manual": None, "anggota": [],
            "sdi": {"sdi_total": 0, "kategori": None, "sdi1": None,
                    "sdi2": None, "sdi3": None, "sdi4": None,
                    "n_temuan_total": 0, "n_tanpa_dimensi": 0},
        }
        fd, path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        buat_laporan_segmen(path, detail)
        return _teks_pdf(path)

    def test_tidak_mencetak_sdi_nol_untuk_tanpa_data(self):
        teks = self._pdf()
        self.assertIn("Belum ada data terukur", teks)
        self.assertNotIn("SDI total 0", teks,
                         "angka 0 adalah artefak komponen kosong")
        self.assertNotIn("termasuk kategori -", teks)


class TestPdfKolomUkuran(unittest.TestCase):
    def test_potong_lebar_mengikuti_lebar_font(self):
        from fpdf import FPDF
        from laporan import _potong_lebar
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("courier", "", 8.4)
        teks = _potong_lebar(pdf, "diameter 100 cm (kelas ukuran)", 33)
        self.assertLessEqual(pdf.get_string_width(teks), 33)
        self.assertTrue(teks.endswith("..."))

    def test_tabel_memakai_potong_lebar_untuk_dasar(self):
        src = _teks(LAPORAN)
        self.assertIn('_potong_lebar(pdf, it.get("dasar"', src)


class TestPdfElipsis(unittest.TestCase):
    def test_pemotongan_memakai_titik_ascii(self):
        from laporan import _aman
        hasil = _aman("A" * 60, 10)
        self.assertEqual(hasil, "AAAAAAA...")
        self.assertNotIn("?", hasil)

    def test_elipsis_unicode_dipetakan_sebelum_encode(self):
        from laporan import _aman
        self.assertEqual(_aman("A" * 20 + "\u2026", 60), "A" * 20 + "...")


class TestDasarTidakMelewatiAmbang(unittest.TestCase):
    def setUp(self):
        from severity import load_config
        self.cfg = load_config(str(ROOT / "config" / "severity.yaml"))
        self.ppc = self.cfg["pixels_per_cm"]

    def test_lebar_retak_di_bawah_10mm_tidak_ditulis_10(self):
        from severity import diagnose
        d = diagnose("transverse_crack", 0, 0, 100 * self.ppc,
                     0.999 * self.ppc, self.cfg)
        self.assertEqual(d["severity"], "Ringan")
        mm = _angka(re.search(r"([\d.,]+)\s*mm", d["dasar"]).group(1))
        self.assertLess(mm, 10, d["dasar"])

    def test_diameter_di_bawah_20cm_tidak_ditulis_20(self):
        from severity import diagnose
        d = diagnose("pothole", 0, 0, 19.99 * self.ppc, 19.99 * self.ppc,
                     self.cfg)
        self.assertEqual(d["severity"], "Ringan")
        cm = _angka(re.search(r"([\d.,]+)\s*cm", d["dasar"]).group(1))
        self.assertLess(cm, 20, d["dasar"])

    def test_luas_di_bawah_900_tidak_ditulis_900(self):
        from severity import diagnose
        sisi = 899.9 ** 0.5 * self.ppc
        d = diagnose("alligator_crack", 0, 0, sisi, sisi, self.cfg)
        self.assertEqual(d["severity"], "Sedang")
        cm2 = _angka(re.search(r"([\d.,]+)\s*cm2", d["dasar"]).group(1))
        self.assertLess(cm2, 900, d["dasar"])


if __name__ == "__main__":
    unittest.main()
