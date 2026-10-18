"""Klasifikasi dimensi temuan kerusakan jalan dari bounding box (pseudo-measurement).

REFRAMING (keputusan 2026-10-18, agar defensif di depan dosen/reviewer):
hanya RETAK yang dilaporkan sebagai "tingkat keparahan" (ambangnya memang
dari standar). Untuk LUBANG yang dilaporkan adalah KELAS UKURAN berdasar
diameter, dan untuk RETAK BUAYA / OTHER_CORRUPTION adalah KELAS LUASAN —
karena severity menurut standar butuh informasi yang tak terukur dari foto
monokular (kedalaman lubang; spalling/pumping pada retak buaya).

Dasar per kelas (lihat juga config/severity.yaml):
- Retak longitudinal/transversal: lebar = sisi pendek box (mm);
  <10 / 10-75 / >75 mm dari README RDDC2024-ID (gaya ASTM D6433).
  Status: BERDASAR STANDAR. Penyederhanaan: hanya komponen lebar dipakai
  (standar aslinya juga menilai sealant & retak sekitar).
- Lubang: diameter = sisi panjang box; bin 100-200 / 200-450 / 450-750 mm
  mengikuti KOLOM Tabel X1.1 ASTM D6433 (via gambar P6 README RDDC2024-ID).
  Status: SEBAGIAN STANDAR (bin diameter saja; severity butuh kedalaman).
- Retak buaya / other: luas area box; ambang 200/900 cm2 = HEURISTIK TIM.

Keterbatasan: bounding box melingkupi objek aktual sehingga angka yang
dilaporkan adalah BATAS ATAS (upper bound). Klasifikasi "Ringan" bersifat
sound (nilai sebenarnya <= yang dilaporkan); "Berat" indikatif. Konversi
px->cm bergantung kalibrasi pixels_per_cm (wajib kalibrasi ulang per
pemasangan kamera). Klasifikasi ini DESKRIPTIF per temuan; instrumen
prioritas adalah SDI-visual per segmen (app/sdi.py).

Field "makna" pada output diagnose() menyatakan apa yang sebenarnya
diklasifikasikan: "tingkat keparahan" | "kelas ukuran" | "kelas luasan".
"""
import yaml

# Makna klasifikasi per jenis kerusakan (untuk kejujuran terminologi).
MAKNA_KEPARAHAN = "tingkat keparahan"  # retak: ambang dari standar
MAKNA_UKURAN = "kelas ukuran"          # lubang: bin diameter ASTM, tanpa kedalaman
MAKNA_LUASAN = "kelas luasan"          # buaya/other: heuristik tim


def makna_untuk_kelas(cls_name):
    """Makna klasifikasi untuk sebuah nama kelas (tanpa perlu box)."""
    c = str(cls_name or "").lower()
    if "pothole" in c:
        return MAKNA_UKURAN
    if "crack" in c and "alligator" not in c:
        return MAKNA_KEPARAHAN
    return MAKNA_LUASAN


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
    """Kelas ukuran lubang berdasar bin diameter ASTM D6433 Tabel X1.1.

    Nama fungsi dipertahankan demi kompatibilitas; yang dikembalikan
    adalah kelas ukuran (kecil/sedang/besar dipetakan ke
    Ringan/Sedang/Berat), BUKAN severity ASTM (butuh kedalaman).
    """
    t = cfg["pothole_diameter_cm"]
    if diameter_cm < t["ringan_max"]:
        return "Ringan"
    if diameter_cm < t["sedang_max"]:
        return "Sedang"
    return "Berat"

def area_severity(luas_cm2, cfg=None):
    """Kelas luasan untuk alligator/other (heuristik tim, tanpa rujukan standar)."""
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
    """Hasil: dict kelas, panjang_cm, lebar_cm, luas_cm2, severity, makna,
    bahan, tebal_asumsi_cm, dasar.

    "severity" memakai label Ringan/Sedang/Berat untuk semua kelas (kompatibel
    dengan konsumen lama: badge UI, koreksi operator, PDF, DB); "makna"
    menjelaskan apa yang sebenarnya diklasifikasikan per kelas.
    "dasar" adalah jejak audit perhitungannya.
    """
    w, h, area = box_size_cm(x1, y1, x2, y2, cfg["pixels_per_cm"])
    c = cls_name.lower()
    makna = makna_untuk_kelas(c)
    if "crack" in c and "alligator" not in c:
        sev = crack_severity(min(w, h) * 10, cfg)
        dasar = f"lebar retak {min(w, h) * 10:.0f} mm"
    elif "pothole" in c:
        sev = pothole_severity(max(w, h), cfg)
        dasar = f"diameter ±{max(w, h):.0f} cm (kelas ukuran)"
    else:  # alligator_crack, other_corruption
        sev = area_severity(area, cfg)
        dasar = f"luas area {area:.0f} cm2 (kelas luasan)"
    return {
        "kelas": cls_name,
        "panjang_cm": round(max(w, h), 1),
        "lebar_cm": round(min(w, h), 1),
        "luas_cm2": round(area, 1),
        "severity": sev,
        "makna": makna,
        "bahan": cfg["bahan"][sev],
        "tebal_asumsi_cm": cfg["tebal_asumsi_cm"][sev],
        "dasar": dasar,
    }
