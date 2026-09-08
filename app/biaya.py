"""Estimasi biaya perbaikan dari hasil diagnose + tabel harga acuan.

Tabel: config/harga_acuan.csv (editable). Ini ESTIMASI ACUAN, bukan RAB resmi dinas.
Rumus: luas_m2 = luas_cm2/10000; volume_m3 = luas_m2 * tebal/100.
total = luas_m2*harga (m2) | volume_m3*harga (m3) | panjang_m*harga (m).
Kolom jenis_kerusakan: kelompok ("crack" utk retak memanjang/melintang,
"alligator", "pothole", "other"; kosong = fallback semua jenis).
Pencocokan: (severity, kelompok) dulu, lalu severity saja.
Hanya stdlib (csv) agar ringan.
"""
import csv

KELOMPOK = {"longitudinal_crack": "crack", "transverse_crack": "crack",
            "alligator_crack": "alligator", "pothole": "pothole",
            "other_corruption": "other"}

def kelompok_jenis(kelas):
    """Nama kelas model -> kelompok harga. Tak dikenal = None (fallback)."""
    try:
        return KELOMPOK.get(str(kelas).strip().lower())
    except (AttributeError, TypeError):
        return None

def load_harga(path="config/harga_acuan.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def cari_harga(rows, severity, jenis=None):
    sev = str(severity).strip().lower()
    cari = [r for r in rows if r["severity"].strip().lower() == sev]
    if not cari:
        raise ValueError(f"severity '{severity}' tidak ada di {len(rows)} baris tabel harga")
    if jenis:
        for r in cari:
            if r.get("jenis_kerusakan", "").strip().lower() == jenis:
                return r
    for r in cari:  # fallback: baris tanpa jenis (berlaku semua)
        if not r.get("jenis_kerusakan", "").strip():
            # P2: jangan diam-diam pakai satuan m2/m3 untuk crack (over-estimasi).
            # Crack harus satuan m; bila blank tidak cocok, lanjut ke fallback satuan.
            if jenis == "crack" and r.get("satuan", "").strip().lower() != "m":
                continue
            return r
    if jenis == "crack":  # prefer satuan m dalam severity yang sama
        for r in cari:
            if r.get("satuan", "").strip().lower() == "m":
                return r
    return cari[0]  # fallback terakhir: severity saja (perilaku lama)

def rupiah(n):
    return f"Rp{n:,.0f}".replace(",", ".")

def estimasi(item, rows):
    h = cari_harga(rows, item["severity"],
                   kelompok_jenis(item.get("kelas", "")))
    harga = float(h["harga_satuan_rp"])
    satuan = h["satuan"].strip().lower()
    luas_m2 = item["luas_cm2"] / 10_000
    volume_m3 = luas_m2 * (item["tebal_asumsi_cm"] / 100)
    if satuan == "m":  # crack sealing: per panjang retak
        panjang_m = item.get("panjang_cm", 0) / 100
        total = panjang_m * harga
    else:
        total = luas_m2 * harga if satuan == "m2" else volume_m3 * harga
    return {
        **item,
        "harga_satuan_rp": harga,
        "satuan": h["satuan"],
        "luas_m2": round(luas_m2, 3),
        "volume_m3": round(volume_m3, 3),
        "total_rp": round(total),
        "total_str": rupiah(total),
        "sumber_harga": h.get("sumber_harga", "-"),
    }
