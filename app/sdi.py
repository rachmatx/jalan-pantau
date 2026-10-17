"""SDI-visual (modul SDI per segmen): dari deteksi per segmen menjadi skor SDI.

Status: INSTRUMEN PRIORITAS (keputusan tim 2026-10-17, menggantikan skor
severity 33/67/100). app/prioritas.py dipertahankan sebagai legacy untuk
kompatibilitas data lama.

Alur:
  deteksi per temuan (kelas, panjang_cm, lebar_cm -- kompatibel dengan
  output app/severity.py::diagnose)
    -> agregasi_segmen() : komponen SDI per segmen
    -> hitung_sdi()      : SDI1..SDI4, total, kategori

Acuan angka: "Bina Marga, 2011b" via paper Untan JMHMS 2021
(Fitriyadi, Erwan, Mukti; Pontianak-Sungai Kakap).

Catatan varian (jujur, dari riset 2026-10-17):
- Dokumen primer "Panduan Survei Kondisi Jalan No. SMD-03/RCS (Jan 2011)"
  TIDAK ditemukan publik; angka di bawah dari paper sekunder.
- Ambang lebar "lebar": >3mm (Untan) vs >5mm (sebagian paper). Modul
  memakai >3mm (dapat diubah via parameter ambang_lebar_mm).
- Satuan lubang: paper Untan inkonsisten (tabel referensi /100m, tabel
  data /km); verifikasi matematika 2026-10-17 menunjukkan perhitungannya
  memakai per km (Segmen 13: 26 lubang/802m -> SDI 85 hanya cocok per km).
  Modul memakai per km.
- Bekas roda TIDAK terdeteksi pipeline -> SDI parsial (SDI4 selalu "-").
  Di data Untan pun komponen ini nol di semua 13 segmen.

Keterbatasan agregasi:
- Luas retak linier = panjang x lebar (metode lapangan Ar = Pr x Lr).
  Untuk retak diagonal, bbox melebih-lebihkan luas -> potensi
  overestimasi komponen luas; ambang SDI1 kasar (10%/30%) sehingga
  efeknya kecil, tetapi dicatat sebagai keterbatasan.
- "other_corruption" tidak ada padanannya di skema SDI -> dikecualikan
  dari komponen (jumlahnya dilaporkan di output).

Hanya stdlib agar ringan.
"""

def kategori_sdi(nilai):
    """Kategori kondisi dari nilai SDI total.

    Batas (Untan JMHMS, Tabel 16): <50 Baik; 50-100 Sedang;
    100-150 Rusak Ringan; >150 Rusak Berat. Batas atas inklusif.
    """
    try:
        v = float(nilai)
    except (TypeError, ValueError):
        return "-"
    if v < 50:
        return "Baik"
    if v <= 100:
        return "Sedang"
    if v <= 150:
        return "Rusak Ringan"
    return "Rusak Berat"


def _jenis(kelas):
    c = str(kelas or "").lower()
    if "pothole" in c or "lubang" in c:
        return "lubang"
    if "crack" in c or "retak" in c:
        if "alligator" in c or "buaya" in c:
            return "retak_buaya"
        return "retak_linier"
    return "lainnya"


def agregasi_segmen(detections, panjang_segmen_m, lebar_jalan_m):
    """Agregasi temuan deteksi menjadi komponen SDI satu segmen.

    detections: list dict {"kelas", "panjang_cm", "lebar_cm"}
      (kompatibel dengan output app/severity.py::diagnose).
    Mengembalikan dict komponen untuk hitung_sdi().
    """
    try:
        L = max(0.0, float(panjang_segmen_m or 0))
    except (TypeError, ValueError):
        L = 0.0
    try:
        W = max(0.0, float(lebar_jalan_m or 0))
    except (TypeError, ValueError):
        W = 0.0
    luas_segmen_m2 = L * W

    tot_luas_cm2 = 0.0
    w_sum = 0.0  # panjang_cm * lebar_mm (rata-rata tertimbang panjang)
    l_sum = 0.0
    n_lin = n_bug = n_lub = n_lain = 0

    for d in detections or []:
        j = _jenis(d.get("kelas"))
        try:
            pj = max(0.0, float(d.get("panjang_cm") or 0))
        except (TypeError, ValueError):
            pj = 0.0
        try:
            lb = max(0.0, float(d.get("lebar_cm") or 0))
        except (TypeError, ValueError):
            lb = 0.0
        if j == "lubang":
            n_lub += 1
        elif j == "retak_linier":
            n_lin += 1
            tot_luas_cm2 += pj * lb
            w_sum += pj * (lb * 10.0)
            l_sum += pj
        elif j == "retak_buaya":
            n_bug += 1
            tot_luas_cm2 += pj * lb
        else:
            n_lain += 1

    luas_retak_m2 = tot_luas_cm2 / 10_000.0
    if (n_lin + n_bug) == 0 or luas_segmen_m2 <= 0:
        luas_retak_pct = None
    else:
        luas_retak_pct = luas_retak_m2 / luas_segmen_m2 * 100.0

    return {
        "panjang_segmen_m": L,
        "lebar_jalan_m": W,
        "luas_segmen_m2": round(luas_segmen_m2, 2),
        "n_retak_linier": n_lin,
        "n_retak_buaya": n_bug,
        "n_lubang": n_lub,
        "n_lainnya_dikecualikan": n_lain,
        "luas_retak_m2": round(luas_retak_m2, 3),
        "luas_retak_pct": None if luas_retak_pct is None else round(luas_retak_pct, 3),
        # rata-rata lebar retak (mm), tertimbang panjang, hanya retak linier
        "lebar_retak_mm": None if l_sum <= 0 else round(w_sum / l_sum, 2),
        "lubang_per_km": round(n_lub / (L / 1000.0), 2) if L > 0 else 0.0,
    }


def hitung_sdi(komp, ambang_lebar_mm=3.0):
    """Hitung SDI1..SDI4, total, dan kategori dari komponen segmen.

    komp: dict dari agregasi_segmen(), atau dict manual dengan kunci
      luas_retak_pct, lebar_retak_mm (atau lebar_kategori:
      "halus"/"sedang"/"lebar"), n_lubang, panjang_segmen_m,
      bekas_roda_cm (opsional; None = tidak terdeteksi -> SDI parsial).
    """
    komp = dict(komp or {})

    # SDI1: % luas retak
    pct = komp.get("luas_retak_pct")
    try:
        pct = None if pct is None else float(pct)
    except (TypeError, ValueError):
        pct = None
    if pct is None:
        sdi1, k1 = None, "tidak ada retak"
    elif pct < 10:
        sdi1, k1 = 5, "<10%"
    elif pct <= 30:
        sdi1, k1 = 20, "10-30%"
    else:
        sdi1, k1 = 40, ">30%"

    # SDI2: rata-rata lebar retak
    wk = komp.get("lebar_kategori")
    w = komp.get("lebar_retak_mm")
    if wk is None and w is not None:
        try:
            w = float(w)
        except (TypeError, ValueError):
            w = None
        if w is not None:
            wk = "halus" if w < 1 else ("sedang" if w <= ambang_lebar_mm else "lebar")
    if wk == "lebar":
        sdi2, k2 = (sdi1 or 0) * 2, "lebar >%gmm: SDI1 x 2" % ambang_lebar_mm
    else:
        sdi2, k2 = None, "-"

    # SDI3: jumlah lubang per km
    try:
        n = int(komp.get("n_lubang") or 0)
    except (TypeError, ValueError):
        n = 0
    L = komp.get("panjang_segmen_m") or 0
    try:
        per_km = n / (float(L) / 1000.0) if float(L) > 0 else 0.0
    except (TypeError, ValueError):
        per_km = 0.0
    base = sdi2 if sdi2 is not None else (sdi1 if sdi1 is not None else 0)
    if n == 0:
        sdi3, k3 = None, "-"
    elif per_km < 10:
        sdi3, k3 = base + 15, "<10/km: +15"
    elif per_km <= 50:
        sdi3, k3 = base + 75, "10-50/km: +75"
    else:
        sdi3, k3 = base + 225, ">50/km: +225"

    # SDI4: bekas roda -- tidak terdeteksi pipeline (SDI parsial)
    br = komp.get("bekas_roda_cm")
    if br is None:
        sdi4, k4 = None, "tidak terdeteksi -> SDI parsial"
    else:
        try:
            br = float(br)
        except (TypeError, ValueError):
            br = None
        if br is None:
            sdi4, k4 = None, "tidak terdeteksi -> SDI parsial"
        else:
            basis4 = sdi3 if sdi3 is not None else base
            if br < 1:
                sdi4, k4 = basis4 + 5 * 0.5, "<1cm: +5x0,5"
            elif br <= 3:
                sdi4, k4 = basis4 + 5 * 2, "1-3cm: +5x2"
            else:
                sdi4, k4 = basis4 + 5 * 4, ">3cm: +5x4"

    total = sdi4 if sdi4 is not None else (sdi3 if sdi3 is not None else base)
    total = int(round(total))

    return {
        "sdi1": sdi1, "sdi1_ket": k1,
        "sdi2": sdi2, "sdi2_ket": k2,
        "sdi3": sdi3, "sdi3_ket": k3,
        "sdi4": sdi4, "sdi4_ket": k4,
        "lubang_per_km": round(per_km, 2),
        "sdi_total": total,
        "kategori": kategori_sdi(total),
        "varian": "ambang lebar >%gmm; lubang per km; tanpa bekas roda (parsial)"
                  % ambang_lebar_mm,
    }
