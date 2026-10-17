"""Uji modul SDI per segmen (app/sdi.py).

Data acuan: paper Untan JMHMS 2021 (Fitriyadi, Erwan, Mukti),
ruas Batas Kota Pontianak - Sungai Kakap, Tabel 7/8/9/10/14/15.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sdi import agregasi_segmen, hitung_sdi, kategori_sdi

# (luas_retak_pct, lebar_retak_mm, n_lubang, panjang_segmen_m, sdi_harapan)
UNTAN_13 = [
    (0.60, 4.4, 0, 1000, 10),
    (0.58, 3.5, 3, 1000, 25),
    (0.15, 6.3, 0, 1000, 10),
    (0.005, 4.4, 0, 1000, 10),
    (0.01, 4.0, 0, 1000, 10),
    (0.16, 5.1, 1, 1000, 25),
    (0.09, 4.8, 1, 1000, 25),
    (1.76, 6.4, 1, 1000, 25),
    (0.04, 4.4, 5, 1000, 25),
    (0.21, 6.2, 1, 1000, 25),
    (0.13, 4.7, 3, 1000, 25),
    (0.05, 4.6, 3, 1000, 25),
    (2.15, 22.6, 26, 802, 85),
]


def _komp(pct, lebar_mm=None, lebar_kategori=None, n_lubang=0, panjang_m=1000):
    return {
        "luas_retak_pct": pct,
        "lebar_retak_mm": lebar_mm,
        "lebar_kategori": lebar_kategori,
        "n_lubang": n_lubang,
        "panjang_segmen_m": panjang_m,
    }


def test_untan_13_segmen():
    for i, (pct, w, n, L, harap) in enumerate(UNTAN_13, start=1):
        h = hitung_sdi(_komp(pct, lebar_mm=w, n_lubang=n, panjang_m=L))
        assert h["sdi_total"] == harap, f"segmen {i}: {h['sdi_total']} != {harap}"
    kat = [hitung_sdi(_komp(p, lebar_mm=w, n_lubang=n, panjang_m=L))["kategori"]
           for p, w, n, L, _ in UNTAN_13]
    assert kat[:12] == ["Baik"] * 12
    assert kat[12] == "Sedang"


def test_untan_subsegmen_13():
    # Tabel 14/15: SDI 235 (Rusak Berat) untuk A/B/C.
    # Satuan lebar di paper ambigu ("cm"); paper mengklasifikasikan wide,
    # sehingga uji memakai lebar_kategori="lebar" sesuai klasifikasi paper.
    data = [
        (42.071 / 539 * 100, 6, 98),
        (42.882 / 550 * 100, 13, 100),
        (0.998 / 550 * 100, 7, 100),
    ]
    for pct, n, L in data:
        h = hitung_sdi(_komp(pct, lebar_kategori="lebar", n_lubang=n, panjang_m=L))
        assert h["sdi_total"] == 235, h
        assert h["kategori"] == "Rusak Berat"


def test_agregasi_sintetis():
    det = [
        {"kelas": "longitudinal_crack", "panjang_cm": 300, "lebar_cm": 0.8},
        {"kelas": "longitudinal_crack", "panjang_cm": 150, "lebar_cm": 0.4},
        {"kelas": "alligator_crack", "panjang_cm": 100, "lebar_cm": 80},
        {"kelas": "pothole", "panjang_cm": 40, "lebar_cm": 35},
        {"kelas": "pothole", "panjang_cm": 30, "lebar_cm": 28},
        {"kelas": "pothole", "panjang_cm": 25, "lebar_cm": 20},
        {"kelas": "other_corruption", "panjang_cm": 50, "lebar_cm": 50},
    ]
    k = agregasi_segmen(det, 100, 6)
    assert k["n_retak_linier"] == 2
    assert k["n_retak_buaya"] == 1
    assert k["n_lubang"] == 3
    assert k["n_lainnya_dikecualikan"] == 1
    # luas = 300*.8 + 150*.4 + 100*80 = 8300 cm2 = 0.83 m2 dari 600 m2
    assert abs(k["luas_retak_pct"] - 0.1383) < 0.001
    # lebar rata-rata tertimbang panjang: (300*8 + 150*4)/450 = 6.67 mm
    assert abs(k["lebar_retak_mm"] - 6.67) < 0.01
    assert k["lubang_per_km"] == 30.0
    h = hitung_sdi(k)
    assert h["sdi1"] == 5 and h["sdi2"] == 10 and h["sdi3"] == 85
    assert h["sdi_total"] == 85 and h["kategori"] == "Sedang"


def test_segitiga_kosong():
    h = hitung_sdi(agregasi_segmen([], 100, 6))
    assert h["sdi_total"] == 0
    assert h["kategori"] == "Baik"


def test_hanya_lubang():
    det = [{"kelas": "pothole", "panjang_cm": 30, "lebar_cm": 25} for _ in range(5)]
    h = hitung_sdi(agregasi_segmen(det, 100, 6))
    assert h["sdi1"] is None and h["sdi2"] is None
    assert h["sdi3"] == 75  # 50/km -> +75 dari basis 0
    assert h["kategori"] == "Sedang"


def test_batas_ambang():
    assert hitung_sdi(_komp(10.0))["sdi1"] == 20
    assert hitung_sdi(_komp(30.0))["sdi1"] == 20
    assert hitung_sdi(_komp(30.1))["sdi1"] == 40
    assert hitung_sdi(_komp(5.0, lebar_mm=3.0))["sdi2"] is None
    assert hitung_sdi(_komp(5.0, lebar_mm=3.1))["sdi2"] == 10
    assert hitung_sdi(_komp(None, n_lubang=10, panjang_m=1000))["sdi3"] == 75
    assert hitung_sdi(_komp(None, n_lubang=9, panjang_m=1000))["sdi3"] == 15


def test_kategori():
    assert kategori_sdi(0) == "Baik"
    assert kategori_sdi(49.9) == "Baik"
    assert kategori_sdi(50) == "Sedang"
    assert kategori_sdi(100) == "Sedang"
    assert kategori_sdi(101) == "Rusak Ringan"
    assert kategori_sdi(150) == "Rusak Ringan"
    assert kategori_sdi(151) == "Rusak Berat"
    assert kategori_sdi(235) == "Rusak Berat"
