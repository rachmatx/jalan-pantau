"""Severity kerusakan jalan dari bounding box (pseudo-measurement).

Acuan ambang retak: README RDDC2024-ID (Low <10mm, Moderate 10-75mm, High >75mm).
Aturan per kelas:
- longitudinal/transverse crack -> lebar retak = sisi pendek box (mm)
- pothole -> diameter = sisi panjang box (cm)
- alligator crack -> luas area terdampak (cm2), karena berupa jaringan
- other_corruption -> luas area (cm2)
Semua ambang di config/severity.yaml (editable).
"""
import yaml

def load_config(path="config/severity.yaml"):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)

def box_size_cm(x1, y1, x2, y2, px_per_cm):
    w = abs(x2 - x1) / px_per_cm
    h = abs(y2 - y1) / px_per_cm
    return w, h, w * h

def crack_severity(lebar_mm, cfg):
    t = cfg["crack_width_mm"]
    if lebar_mm < t["ringan_max"]:
        return "Ringan"
    if lebar_mm < t["sedang_max"]:
        return "Sedang"
    return "Berat"

def pothole_severity(diameter_cm, cfg):
    t = cfg["pothole_diameter_cm"]
    if diameter_cm < t["ringan_max"]:
        return "Ringan"
    if diameter_cm < t["sedang_max"]:
        return "Sedang"
    return "Berat"

def area_severity(luas_cm2, cfg=None):
    # Asumsi dokumentasi untuk alligator/other: dinilai dari luas area.
    # Ambang editable di config/severity.yaml (area_cm2); fallback = nilai lama.
    try:
        t = (cfg or {})["area_cm2"]
        ringan_max = float(t["ringan_max"])
        sedang_max = float(t["sedang_max"])
    except (KeyError, TypeError, ValueError):
        ringan_max, sedang_max = 200, 900
    if luas_cm2 < ringan_max:
        return "Ringan"
    if luas_cm2 < sedang_max:
        return "Sedang"
    return "Berat"

def diagnose(cls_name, x1, y1, x2, y2, cfg):
    """Hasil: dict kelas, panjang_cm, lebar_cm, luas_cm2, severity, bahan, tebal_asumsi_cm, dasar."""
    w, h, area = box_size_cm(x1, y1, x2, y2, cfg["pixels_per_cm"])
    c = cls_name.lower()
    if "crack" in c and "alligator" not in c:
        sev = crack_severity(min(w, h) * 10, cfg)
        dasar = f"lebar retak {min(w, h) * 10:.0f} mm"
    elif "pothole" in c:
        sev = pothole_severity(max(w, h), cfg)
        dasar = f"diameter ±{max(w, h):.0f} cm"
    else:  # alligator_crack, other_corruption
        sev = area_severity(area, cfg)
        dasar = f"luas area {area:.0f} cm2"
    return {
        "kelas": cls_name,
        "panjang_cm": round(max(w, h), 1),
        "lebar_cm": round(min(w, h), 1),
        "luas_cm2": round(area, 1),
        "severity": sev,
        "bahan": cfg["bahan"][sev],
        "tebal_asumsi_cm": cfg["tebal_asumsi_cm"][sev],
        "dasar": dasar,
    }
