"""Unit test untuk app/ringkasan.py (agregasi ringkasan deteksi).

Jalankan dari root repo:
    .\\.venv\\Scripts\\python -m unittest tests.test_ringkasan -v
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from ringkasan import ringkasan, per_kelas  # noqa: E402


def item(kelas="pothole", severity="Ringan", luas=100.0, total=1000.0):
    return {"kelas": kelas, "severity": severity,
            "luas_cm2": luas, "total_rp": total}


class TestBasic(unittest.TestCase):
    def test_kosong(self):
        r = ringkasan([])
        self.assertEqual(r["jumlah"], 0)
        self.assertEqual(r["per_severity"], {"Ringan": 0, "Sedang": 0, "Berat": 0})
        self.assertEqual(r["per_kelas"], {})
        self.assertEqual(r["luas_total_cm2"], 0)
        self.assertEqual(r["total_rp"], 0)
        self.assertEqual(r["persen_biaya"], {"Ringan": 0.0, "Sedang": 0.0, "Berat": 0.0})
        self.assertEqual(r["severity_tertinggi"], "-")

    def test_satu_item(self):
        r = ringkasan([item("pothole", "Berat", 250.0, 5000.0)])
        self.assertEqual(r["jumlah"], 1)
        self.assertEqual(r["per_severity"], {"Ringan": 0, "Sedang": 0, "Berat": 1})
        self.assertEqual(r["per_kelas"], {"pothole": 1})
        self.assertEqual(r["luas_total_cm2"], 250.0)
        self.assertEqual(r["total_rp"], 5000)
        self.assertEqual(r["severity_tertinggi"], "Berat")
        self.assertEqual(r["persen_biaya"]["Berat"], 100.0)
        self.assertEqual(r["persen_biaya"]["Ringan"], 0.0)

    def test_total_rp_eksplisit_lebih_besar_dari_sum(self):
        """Total dari argumen eksplisit dipakai, bukan penjumlahan item."""
        r = ringkasan([item(total=1000.0)], total_rp=5000.0)
        self.assertEqual(r["total_rp"], 5000)
        self.assertEqual(r["persen_biaya"]["Ringan"], 20.0)

    def test_total_rp_nol_eksplisit_dihormati(self):
        """total_rp=0 eksplisit = nol nyata, TIDAT di-fallback ke sum item."""
        r = ringkasan([item(total=2500.0)], total_rp=0)
        self.assertEqual(r["total_rp"], 0)


class TestPerKelas(unittest.TestCase):
    def test_urutan_count_desc_kemudian_nama_asc(self):
        r = ringkasan([
            item("pothole"), item("pothole"), item("pothole"),
            item("alligator_crack"),
            item("longitudinal_crack"), item("longitudinal_crack"),
            item("transverse_crack"),
        ])
        self.assertEqual(
            list(r["per_kelas"]),
            ["pothole", "longitudinal_crack", "alligator_crack", "transverse_crack"],
        )

    def test_kelas_kosong_diabaikan(self):
        r = ringkasan([item(""), item("pothole"), item(None)])
        self.assertEqual(r["per_kelas"], {"pothole": 1})


class TestSeverity(unittest.TestCase):
    def test_case_insensitive_dan_whitespace(self):
        r = ringkasan([
            item("a", "ringan"), item("b", "  Ringan "),
            item("c", "SEDANG"), item("d", "berat"),
        ])
        self.assertEqual(r["per_severity"], {"Ringan": 2, "Sedang": 1, "Berat": 1})

    def test_severity_tertinggi_ambil_yang_paling_berat(self):
        r = ringkasan([item("a", "Ringan"), item("b", "Berat"), item("c", "Sedang")])
        self.assertEqual(r["severity_tertinggi"], "Berat")

    def test_severity_asing_diabaikan_tapi_tetap_dihitung_jumlah(self):
        r = ringkasan([item("a", "Kritis"), item("b", "Ringan")])
        self.assertEqual(r["jumlah"], 2)
        self.assertEqual(r["per_severity"], {"Ringan": 1, "Sedang": 0, "Berat": 0})
        self.assertEqual(r["severity_tertinggi"], "Ringan")


class TestItemTidakLengkap(unittest.TestCase):
    def test_item_tanpa_key_financial_default_nol(self):
        r = ringkasan([{"kelas": "pothole", "severity": "Ringan"}])
        self.assertEqual(r["luas_total_cm2"], 0)
        self.assertEqual(r["total_rp"], 0)
        self.assertEqual(r["jumlah"], 1)

    def test_item_bukan_dict_dilewati(self):
        r = ringkasan([item("pothole", "Ringan", 50.0, 500.0), None, "x", 42])
        self.assertEqual(r["jumlah"], 1)
        self.assertEqual(r["total_rp"], 500)

    def test_nilai_non_numerik_di_default_nol(self):
        r = ringkasan([{"kelas": "p", "severity": "Ringan",
                        "luas_cm2": "abc", "total_rp": None}])
        self.assertEqual(r["luas_total_cm2"], 0)
        self.assertEqual(r["total_rp"], 0)

    def test_none_items(self):
        self.assertEqual(ringkasan(None)["jumlah"], 0)


class TestPembagian(unittest.TestCase):
    def test_pembagian_nol_tidak_boom(self):
        r = ringkasan([item("a", "Ringan", 10.0, 0.0)])
        self.assertEqual(r["total_rp"], 0)
        self.assertEqual(r["persen_biaya"], {"Ringan": 0.0, "Sedang": 0.0, "Berat": 0.0})

    def test_persen_bulat_setengah_ke_atas(self):
        """Banker's rounding salah di sini: 0.125 -> 0.12, harus 0.13."""
        r = ringkasan([
            item("a", "Ringan", 1.0, 1.0),
            item("b", "Sedang", 1.0, 1.0),
            item("c", "Berat", 1.0, 6.0),
        ], total_rp=8.0)
        self.assertEqual(r["persen_biaya"]["Ringan"], 12.5)
        self.assertEqual(r["persen_biaya"]["Sedang"], 12.5)
        self.assertEqual(r["persen_biaya"]["Berat"], 75.0)

    def test_persen_bulat_setengah_ke_atas_bukan_bankers(self):
        # 0.125 -> 0.13 (bukan 0.12 seperti round() bawaan Python)
        r = ringkasan([item("a", "Ringan", 1.0, 1.0),
                       item("b", "Sedang", 1.0, 7.0)], total_rp=8.0)
        self.assertEqual(r["persen_biaya"]["Ringan"], 12.5)
        # total 100: 1/8 = 12.5, 7/8 = 87.5
        self.assertEqual(r["persen_biaya"]["Sedang"], 87.5)

    def test_persen_mendekati_100_setelah_pembulatan(self):
        """33.3 x3 = 99.9; selisih < 0.15 inevitable karena pembulatan 1 desimal."""
        r = ringkasan([
            item("a", "Ringan", 1.0, 1.0),
            item("b", "Sedang", 1.0, 1.0),
            item("c", "Berat", 1.0, 1.0),
        ], total_rp=3.0)
        p = r["persen_biaya"]
        self.assertEqual(p, {"Ringan": 33.3, "Sedang": 33.3, "Berat": 33.3})
        self.assertLessEqual(abs(sum(p.values()) - 100.0), 0.15)

    def test_persen_bulat_half_up_bukan_bankers(self):
        """0.25 -> 0.3 (half-up). round() bawaan Python -> 0.2 (banker's)."""
        # 1 dari total 400 = 0.25% ; butuh 3 severity biar total_rp tetap 400
        r = ringkasan([
            item("a", "Ringan", 1.0, 1.0),
            item("b", "Sedang", 1.0, 399.0),
        ], total_rp=400.0)
        self.assertEqual(r["persen_biaya"]["Ringan"], 0.3)   # bukan 0.2
        self.assertEqual(r["persen_biaya"]["Sedang"], 99.8)   # bukan 99.8? cek
        self.assertNotEqual(r["persen_biaya"]["Ringan"], round(0.25, 1))


class TestPerKelasHelper(unittest.TestCase):
    def test_standalone(self):
        self.assertEqual(per_kelas([item("a"), item("a"), item("b")]),
                         {"a": 2, "b": 1})

    def test_kosong(self):
        self.assertEqual(per_kelas([]), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
