"""Uji gate kondisi jalan basah (app/scene_gate.py).

Kontrak gate:
1. Gate aktif HANYA bila scene == wet_road dengan conf >= conf_min.
2. Saat aktif: pothole di bawah ambang_lubang dibuang, kelas lain tak tersentuh.
3. Kegagalan gate = perilaku normal (tak ada error, tak ada temuan hilang).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from scene_gate import (  # noqa: E402
    putuskan_gate, saring_gate_basah, label_id,
)


def _row(kelas, conf):
    return {"kelas": kelas, "conf": conf}


def test_gate_aktif_prob_basah_cukup():
    # Aturan lama (top-1 wet, conf tinggi) tetap tercakup:
    assert putuskan_gate({"wet_road": 0.92}, 0.25) is True
    # Kasus foto ambigu: top-1 damaged 51%, sinyal basah 32% -> gate aktif:
    assert putuskan_gate({"damaged_road": 0.51, "wet_road": 0.32,
                          "bumpy_road": 0.10}, 0.25) is True
    assert putuskan_gate({"wet_road": 0.25}, 0.25) is True  # batas inklusif


def test_gate_tidak_aktif():
    assert putuskan_gate({"wet_road": 0.24}, 0.25) is False   # di bawah ambang
    assert putuskan_gate({"damaged_road": 0.90, "wet_road": 0.05},
                         0.25) is False
    assert putuskan_gate({}, 0.25) is False
    assert putuskan_gate(None, 0.25) is False
    assert putuskan_gate({"wet_road": "rusak"}, 0.25) is False  # input aneh


def test_saring_buang_lubang_rendah_saat_gate():
    rows = [_row("pothole", 0.41),   # FP bercak air khas -> dibuang
            _row("pothole", 0.60),   # lubang nyata -> lolos
            _row("longitudinal_crack", 0.30),  # bukan lubang -> lolos
            _row("pothole", 0.45)]   # tepat di ambang -> lolos
    ok, buang = saring_gate_basah(rows, 0.45)
    assert buang == 1
    assert len(ok) == 3
    assert all(r["conf"] >= 0.45 or r["kelas"] != "pothole" for r in ok)


def test_saring_tak_menyentuh_kelas_lain():
    rows = [_row("pothole", 0.10), _row("other_corruption", 0.10)]
    ok, buang = saring_gate_basah(rows, 0.45)
    assert buang == 1 and len(ok) == 1 and ok[0]["kelas"] == "other_corruption"


def test_saring_rows_kosong():
    ok, buang = saring_gate_basah([], 0.45)
    assert ok == [] and buang == 0


def test_saring_conf_rusak_tak_crash():
    rows = [{"kelas": "pothole"}, {"kelas": "pothole", "conf": None}]
    ok, buang = saring_gate_basah(rows, 0.45)
    assert buang == 2 and ok == []


def test_label_id():
    assert label_id("wet_road") == "Jalan Basah"
    assert label_id("normal_road") == "Jalan Normal"
    assert label_id("entah") == "-"
