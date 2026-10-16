"""Indeks prioritas penanganan dari hasil diagnose.

Menggantikan estimasi biaya (app/biaya.py, dihapus 2026-10-16): sumber harga
resmi tidak tersedia sehingga klaim nominal rupiah tidak dapat dipertahankan
dalam naskah jurnal.

Rumus (didokumentasikan untuk bagian Metode paper, direvisi 2026-10-16
menanggapi kritik double-counting):
  bobot severity : Ringan=1, Sedang=2, Berat=3
  skor           : round(100 * (bobot/3))

Ringan -> 33, Sedang -> 67, Berat -> 100. Luas TIDAK masuk skor karena
severity (dari lebar/diameter) dan luas (dari dimensi bounding box) keduanya
diturunkan dari pengukuran dimensi yang sama; mengalikannya menghitung ulang
sinyal yang sama. Dalam satu tier severity, temuan diurutkan menurun
berdasarkan luas sebagai heuristik tampilan, bukan komponen skor.

Formula ini dinyatakan sebagai usulan yang belum tervalidasi secara
metodologis dan tidak memuat komponen biaya.
Hanya stdlib agar ringan.
"""

BOBOT_SEVERITY = {"Ringan": 1, "Sedang": 2, "Berat": 3}


def bobot(severity):
    """Bobot numerik severity. Tak dikenal -> 1 (paling ringan)."""
    return BOBOT_SEVERITY.get(str(severity).strip().capitalize(), 1)


def skor(item):
    """Hitung skor prioritas 0-100 untuk satu temuan + dimensi turunan.

    item: dict hasil diagnose (wajib ada kunci 'severity'; 'luas_cm2' dan
    'tebal_asumsi_cm' opsional, dipakai untuk info tampilan saja).
    Mengembalikan dict baru = item + 'luas_m2' + 'volume_m3' (bila tebal
    tersedia) + 'skor_prioritas' (int: 33/67/100).
    """
    d = dict(item or {})
    try:
        luas = max(0.0, float(d.get("luas_cm2", 0) or 0))
    except (TypeError, ValueError):
        luas = 0.0
    d["luas_m2"] = round(luas / 10_000.0, 3)
    try:
        tebal = float(d.get("tebal_asumsi_cm") or 0)
    except (TypeError, ValueError):
        tebal = 0.0
    if tebal > 0:
        d["volume_m3"] = round(d["luas_m2"] * (tebal / 100), 3)
    nilai = round(100 * (bobot(d.get("severity")) / 3))
    d["skor_prioritas"] = int(max(0, min(100, nilai)))
    return d


def total_prioritas(rows):
    """Jumlah skor prioritas seluruh temuan (int)."""
    total = 0
    for r in rows or []:
        try:
            total += int(r.get("skor_prioritas", 0) or 0)
        except (TypeError, ValueError):
            continue
    return total


def urutkan(temuan):
    """Urutkan temuan: skor menurun, lalu luas menurun (heuristik tampilan).

    Mengembalikan list baru; tidak mengubah skor.
    """
    def kunci(t):
        try:
            luas = float(t.get("luas_cm2", 0) or 0)
        except (TypeError, ValueError):
            luas = 0.0
        return (-int(t.get("skor_prioritas", 0) or 0), -luas)
    return sorted(temuan or [], key=kunci)
