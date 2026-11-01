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
sound (nilai sebenarnya <= yang dilaporkan); "Berat" indikatif. Lebih parah
lagi pada retak miring/berkelok: sisi pendek box mengukur SIMPANGAN LATRAL
retak, bukan lebar bukaan, sehingga bisa berlipat di atas kenyataan. Karena
itu teks jejak audit memakai istilah "lebar kotak" (sisi box), bukan "lebar
retak" — istilah "lebar retak" dipakai hanya untuk ukuran hasil ukur manual
(diagnose_cm, jalur koreksi dimensi operator). Konversi px->cm bergantung
kalibrasi pixels_per_cm yang hanya sah pada jarak kalibrasinya (wajib
kalibrasi ulang per pemasangan kamera; lihat docs/Validasi-Pengukuran.md).
Klasifikasi ini DESKRIPTIF per temuan; instrumen prioritas adalah SDI-visual
per segmen (app/sdi.py).

Field "makna" pada output diagnose() menyatakan apa yang sebenarnya
diklasifikasikan: "tingkat keparahan" | "kelas ukuran" | "kelas luasan".
"""
import math

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


def _angka_bawah(nilai, desimal=1):
    """Format angka dengan pembulatan KE BAWAH.

    Teks 'dasar' dipakai sebagai jejak audit severity. Pembulatan biasa bisa
    menaruh angka di sisi ambang yang salah (9,99 mm tampil '10 mm' padahal
    severity-nya Ringan), jadi selalu potong ke bawah.
    """
    p = 10 ** desimal
    teks = f"{math.floor(nilai * p) / p:.{desimal}f}"
    if "." in teks:
        teks = teks.rstrip("0").rstrip(".")
    return teks


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
    """Hasil dari sisi bounding box: dict kelas, panjang_cm, lebar_cm, luas_cm2,
    severity, makna, bahan, tebal_asumsi_cm, dasar.

    "severity" memakai label Ringan/Sedang/Berat untuk semua kelas (kompatibel
    dengan konsumen lama: badge UI, koreksi operator, PDF, DB); "makna"
    menjelaskan apa yang sebenarnya diklasifikasikan per kelas.
    "dasar" adalah jejak audit perhitungannya.
    """
    w, h, area = box_size_cm(x1, y1, x2, y2, cfg["pixels_per_cm"])
    return _klasifikasi(cls_name, max(w, h), min(w, h), area, cfg, manual=False)


def diagnose_cm(cls_name, panjang_cm, lebar_cm, cfg):
    """Klasifikasi dari ukuran cm hasil ukur manual (koreksi dimensi operator).

    Ambangnya identik dengan diagnose() — hanya sumber sisinya yang berbeda,
    jadi satu temuan tidak bisa punya severity berbeda hanya karena datanya
    masuk lewat jalur lain. Sisi dinormalkan (panjang >= lebar) supaya
    konsumen lama (app/sdi.py, PDF, DB) tetap mendapat invariant yang sama;
    istilah pada jejak audit berubah jadi "lebar retak" karena angka ini
    memang hasil ukur, bukan sisi kotak.
    """
    p, l = float(panjang_cm), float(lebar_cm)
    return _klasifikasi(cls_name, max(p, l), min(p, l), p * l, cfg, manual=True)


def _klasifikasi(cls_name, sisi_p, sisi_l, area, cfg, manual):
    """Inti klasifikasi: dua sisi (cm) + luas (cm2) -> severity + jejak audit.

    `manual` hanya mengubah ISTILAH pada jejak audit (lebar kotak vs lebar
    retak), bukan ambangnya.
    """
    c = cls_name.lower()
    if "crack" in c and "alligator" not in c:
        sev = crack_severity(sisi_l * 10, cfg)
        if manual:
            dasar = f"lebar retak {_angka_bawah(sisi_l * 10)} mm (manual)"
        else:
            dasar = f"lebar kotak {_angka_bawah(sisi_l * 10)} mm"
    elif "pothole" in c:
        sev = pothole_severity(sisi_p, cfg)
        angka = _angka_bawah(sisi_p)
        dasar = (f"diameter {angka} cm (manual, kelas ukuran)" if manual
                 else f"diameter ±{angka} cm (kelas ukuran)")
    else:  # alligator_crack, other_corruption
        sev = area_severity(area, cfg)
        angka = _angka_bawah(area)
        dasar = (f"luas area {angka} cm2 (manual, kelas luasan)" if manual
                 else f"luas area {angka} cm2 (kelas luasan)")
    return {
        "kelas": cls_name,
        "panjang_cm": round(sisi_p, 1),
        "lebar_cm": round(sisi_l, 1),
        "luas_cm2": round(area, 1),
        "severity": sev,
        "makna": makna_untuk_kelas(c),
        "bahan": cfg["bahan"][sev],
        "tebal_asumsi_cm": cfg["tebal_asumsi_cm"][sev],
        "dasar": dasar,
    }
