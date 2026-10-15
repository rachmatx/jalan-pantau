"""Indeks prioritas penanganan dari hasil diagnose.

Menggantikan estimasi biaya (app/biaya.py, dihapus 2026-10-16): sumber harga
resmi tidak tersedia sehingga klaim nominal rupiah tidak dapat dipertahankan
dalam naskah jurnal. Skor 0-100 per temuan; total laporan = jumlah skor.

Rumus (didokumentasikan untuk bagian Metode paper):
  bobot severity : Ringan=1, Sedang=2, Berat=3
  a_norm         : min(1, luas_cm2 / LUAS_ACUAN_CM2), LUAS_ACUAN_CM2 = 10.000 (1 m2)
  skor           : round(100 * (bobot/3) * a_norm)

Contoh: pothole Berat seluas 1 m2 -> 100; retak Ringan 200 cm2 -> 1.
Hanya stdlib agar ringan.
"""

BOBOT_SEVERITY = {"Ringan": 1, "Sedang": 2, "Berat": 3}
LUAS_ACUAN_CM2 = 10_000.0


def bobot(severity):
    """Bobot numerik severity. Tak dikenal -> 1 (paling ringan)."""
    return BOBOT_SEVERITY.get(str(severity).strip().capitalize(), 1)


def skor(item):
    """Hitung skor prioritas 0-100 untuk satu temuan.

    item: dict hasil diagnose (wajib ada kunci 'severity' dan 'luas_cm2').
    Mengembalikan dict baru = item + 'skor_prioritas' (int).
    """
    try:
        luas = max(0.0, float(item.get("luas_cm2", 0) or 0))
    except (TypeError, ValueError):
        luas = 0.0
    a_norm = min(1.0, luas / LUAS_ACUAN_CM2)
    nilai = round(100 * (bobot(item.get("severity")) / 3) * a_norm)
    return {**item, "skor_prioritas": int(max(0, min(100, nilai)))}


def total_prioritas(rows):
    """Jumlah skor prioritas seluruh temuan (int)."""
    total = 0
    for r in rows or []:
        try:
            total += int(r.get("skor_prioritas", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total
