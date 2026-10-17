# -*- coding: utf-8 -*-
"""Gate kondisi jalan basah (scene classifier IROSCD).

Ide: classifier kecil (YOLOv11n-cls, latih pada IROSCD — 4 kondisi jalan
Indonesia) menilai tiap foto. Bila scene = wet_road dengan keyakinan cukup,
ambang confidence kelas pothole dinaikkan — menekan false positive pada
bercak air/genangan tanpa mengorbankan recall di jalan kering.

Modul ini murni logika (tanpa cv2/torch) agar bisa di-unit-test.
"""

WET_LABEL = "wet_road"
WET_MIN_BAWAAN = 0.25        # probabilitas wet_road minimum agar gate aktif
AMBANG_LUBANG_BAWAAN = 0.45  # ambang pothole saat gate aktif (slider 0.25)
KELAS_GATE = "pothole"


def putuskan_gate(probs, wet_min=WET_MIN_BAWAAN):
    """Aktifkan gate? True bila P(wet_road) >= wet_min.

    probs: dict {label_kanonik: probabilitas}. Memakai probabilitas langsung
    (bukan top-1) agar foto ambigu — mis. jalan basah yang rusak,
    terklasifikasi "damaged_road" 51% dengan P(wet) ~30% — tetap memicu gate.
    Aturan lama (top-1 wet_road, conf>=0.70) adalah kasus khusus dari ini.
    """
    try:
        return float((probs or {}).get(WET_LABEL, 0.0)) >= float(wet_min)
    except (TypeError, ValueError):
        return False


def saring_gate_basah(rows, ambang_lubang=AMBANG_LUBANG_BAWAAN):
    """Buang temuan pothole di bawah ambang saat gate aktif.

    rows: list dict dengan kunci 'kelas' dan 'conf'.
    Kembalikan (lolos, n_buang).
    """
    ok, buang = [], 0
    for r in rows:
        try:
            cf = float(r.get("conf", 0))
        except (TypeError, ValueError):
            buang += 1
            continue
        if str(r.get("kelas", "")) == KELAS_GATE and cf < float(ambang_lubang):
            buang += 1
            continue
        ok.append(r)
    return ok, buang


def label_id(label):
    """Label Indonesia untuk badge UI."""
    peta = {
        "wet_road": "Jalan Basah",
        "normal_road": "Jalan Normal",
        "damaged_road": "Jalan Rusak",
        "bumpy_road": "Jalan Bergelombang",
    }
    return peta.get(str(label or "").strip().lower(), "-")
