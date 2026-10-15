"""Agregasi ringkasan hasil deteksi + skor prioritas (stdlib only).

Konsumen: ringkasan() buat kartu statistik di UI/laporan.
Modul ini TIDAK sentuh config/ atau jaringan.

Ketentuan:
- Tiga severity kanonik: Ringan, Sedang, Berat. `per_severity` selalu punya
  ketiga key (nilai 0 bila nihil) supaya frontend/UI bisa iterate tanpa
  cek ketersediaan key.
- Severity dari data dibersihkan (strip + lower) lalu dipetakan ke forma
  kanonik. Nilai di luar tiga itu diabaikan untuk `per_severity`, tapi item
  tetap dihitung di `jumlah` supaya tidak hilang diam-diam.
- `total` argumen dipakai kalau bukan None (mis. total live yang sudah
  dihitung caller); None = jumlahkan dari item. 0 dianggap nilai nyata.
- Pembagian persen memakai pembulatan half-away-from-zero. round() bawaan
  Python itu banker's rounding (0.125 -> 0.12) yang salah untuk laporan
  keuangan; persen yang meleset jauh dari perhitungan manual bikin pembaca ragu.
- Skor agregat memakai `skor_prioritas` per item (0-100).
"""
from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

SEVERITY = ("Ringan", "Sedang", "Berat")
_URUT = {s: i for i, s in enumerate(SEVERITY)}
_KANONIK = {s.lower(): s for s in SEVERITY}

__all__ = ["SEVERITY", "ringkasan", "per_kelas", "persen_skor"]


def _num(v, default=0.0):
    """Coerce ke float; nilai junk/None jadi default (bukan crash)."""
    if isinstance(v, bool) or v is None:
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return default
    return f


def _teks(v):
    return str(v).strip() if isinstance(v, str) else ""


def _bulat(n, digit=1):
    """Half-away-from-zero, bukan banker's rounding."""
    d = digit if digit >= 0 else 0
    q = Decimal(1).scaleb(-d)
    return float(Decimal(str(n)).quantize(q, rounding=ROUND_HALF_UP))


def _item_valid(it):
    return isinstance(it, dict)


def per_kelas(items):
    """Kelas -> jumlah. Key kosong/None dibuang. Urutan: count desc, nama asc."""
    c = Counter()
    for it in (items or []):
        if not _item_valid(it):
            continue
        k = _teks(it.get("kelas"))
        if k:
            c[k] += 1
    return dict(sorted(c.items(), key=lambda kv: (-kv[1], kv[0])))


def _per_severity(items):
    c = {s: 0 for s in SEVERITY}
    for it in (items or []):
        if not _item_valid(it):
            continue
        s = _KANONIK.get(_teks(it.get("severity")).lower())
        if s:
            c[s] += 1
    return c


def persen_skor(per_sev_skor, total):
    """Persen tiap severity terhadap total. Total 0/Nol -> semua 0.0."""
    out = {s: 0.0 for s in SEVERITY}
    t = _num(total)
    if t <= 0:
        return out
    for s in SEVERITY:
        out[s] = _bulat(_num(per_sev_skor.get(s, 0.0)) / t * 100.0, 1)
    return out


def ringkasan(items, total=None):
    """Ringkasan list item deteksi. Kunci: jumlah, per_severity, per_kelas,
    luas_total_cm2, total_skor, persen_skor, severity_tertinggi."""
    items = [it for it in (items or []) if _item_valid(it)]

    luas = sum(_num(it.get("luas_cm2")) for it in items)
    per_sev_skor = {s: 0.0 for s in SEVERITY}
    for it in items:
        s = _KANONIK.get(_teks(it.get("severity")).lower())
        if s:
            per_sev_skor[s] += _num(it.get("skor_prioritas"))

    # total=None -> jumlahkan; 0 dianggap eksplisit (nol nyata, bukan "hitung").
    total = sum(_num(it.get("skor_prioritas")) for it in items) if total is None else _num(total)

    per_sev = _per_severity(items)
    ada = [s for s in SEVERITY if per_sev[s] > 0]
    tertinggi = max(ada, key=lambda s: _URUT[s]) if ada else "-"

    return {
        "jumlah": len(items),
        "per_severity": per_sev,
        "per_kelas": per_kelas(items),
        "luas_total_cm2": _bulat(luas, 1),
        "total_skor": int(round(total)),
        "persen_skor": persen_skor(per_sev_skor, total),
        "severity_tertinggi": tertinggi,
    }
