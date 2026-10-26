"""Uji gate kondisi jalan basah (app/scene_gate.py).

Kontrak gate:
1. Gate aktif HANYA bila P(wet_road) >= wet_min (probabilitas langsung,
   bukan top-1 label — foto ambigu "damaged_road" pun bisa memicu gate).
2. Saat aktif: pothole di bawah ambang_lubang dibuang, kelas lain tak tersentuh.
3. Kegagalan gate = perilaku normal (tak ada error, tak ada temuan hilang).
"""
# Ditulis sebagai unittest.TestCase agar tereksekusi `unittest discover` (CI).
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from scene_gate import (  # noqa: E402
    putuskan_gate, saring_gate_basah, label_id,
)


def _row(kelas, conf):
    return {"kelas": kelas, "conf": conf}


class TestSceneGate(unittest.TestCase):
    def test_gate_aktif_wet_conf_tinggi(self):
        assert putuskan_gate({"wet_road": 0.92}, 0.70) is True
        assert putuskan_gate({"wet_road": 0.70}, 0.70) is True  # batas inklusif


    def test_gate_aktif_walau_bukan_top1(self):
        # Foto ambigu: label top-1 "damaged_road" tapi sinyal basah tetap cukup
        # (kontrak baru memakai P(wet_road), bukan label top-1).
        assert putuskan_gate({"damaged_road": 0.51, "wet_road": 0.30}, 0.25) is True


    def test_gate_tidak_aktif(self):
        assert putuskan_gate({"wet_road": 0.69}, 0.70) is False   # prob kurang
        assert putuskan_gate({"normal_road": 0.99}, 0.70) is False  # bukan basah
        assert putuskan_gate({"damaged_road": 0.95}, 0.70) is False
        assert putuskan_gate(None, 0.9) is False
        assert putuskan_gate({"wet_road": "rusak"}, 0.70) is False  # input aneh


    def test_saring_buang_lubang_rendah_saat_gate(self):
        rows = [_row("pothole", 0.41),   # FP bercak air khas -> dibuang
                _row("pothole", 0.60),   # lubang nyata -> lolos
                _row("longitudinal_crack", 0.30),  # bukan lubang -> lolos
                _row("pothole", 0.45)]   # tepat di ambang -> lolos
        ok, buang = saring_gate_basah(rows, 0.45)
        assert buang == 1
        assert len(ok) == 3
        assert all(r["conf"] >= 0.45 or r["kelas"] != "pothole" for r in ok)


    def test_saring_tak_menyentuh_kelas_lain(self):
        rows = [_row("pothole", 0.10), _row("other_corruption", 0.10)]
        ok, buang = saring_gate_basah(rows, 0.45)
        assert buang == 1 and len(ok) == 1 and ok[0]["kelas"] == "other_corruption"


    def test_saring_rows_kosong(self):
        ok, buang = saring_gate_basah([], 0.45)
        assert ok == [] and buang == 0


    def test_saring_conf_rusak_tak_crash(self):
        rows = [{"kelas": "pothole"}, {"kelas": "pothole", "conf": None}]
        ok, buang = saring_gate_basah(rows, 0.45)
        assert buang == 2 and ok == []


    def test_label_id(self):
        assert label_id("wet_road") == "Jalan Basah"
        assert label_id("normal_road") == "Jalan Normal"
        assert label_id("entah") == "-"


if __name__ == "__main__":
    unittest.main()
