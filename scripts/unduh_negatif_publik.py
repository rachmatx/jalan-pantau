"""Unduh kandidat gambar NEGATIF (jalan aspal, tanpa kerusakan) dari Wikimedia Commons.

TANPA login / API key. Sumber utama = KATEGORI Commons (lebih presisi daripada
pencarian kata kunci). Lisensi dicatat di Kredit.csv untuk atribusi. Gambar gelap /
terlalu kecil / bukan JPEG-PNG disaring otomatis.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\unduh_negatif_publik.py --maks 60
    .\\.venv\\Scripts\\python scripts\\unduh_negatif_publik.py --kategori "Asphalt pavement,Roads in Indonesia"

Setelah terunduh, saring lagi dengan model agar hanya yang benar-benar tanpa deteksi:
    .\\.venv\\Scripts\\python scripts\\kandidat_negatif.py --in data/lokal/negatif-publik --out data/lokal/negatif-bersih
"""
import argparse
import csv
import io
import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
API = "https://commons.wikimedia.org/w/api.php"
UA = "JalanPantau-TA/1.0 (riset tugas akhir)"
EKST_OK = (".jpg", ".jpeg", ".png")
KATEGORI_DEFAULT = [
    "Asphalt roads",
    "Asphalt pavement",
    "Asphalt concrete",
    "Roads in Indonesia",
]


def _api(params):
    p = dict(params)
    p["format"] = "json"
    req = urllib.request.Request(API + "?" + urllib.parse.urlencode(p),
                                 headers={"User-Agent": UA})
    return json.load(urllib.request.urlopen(req, timeout=45))


def _teks(v, n=70):
    v = re.sub(r"<[^>]+>", "", str(v or "")).strip()
    return v.encode("ascii", "replace").decode()[:n]


def _kumpulkan(params_umum):
    d = _api(dict(params_umum, prop="imageinfo",
                  iiprop="url|extmetadata|size", iiurlwidth=1280))
    return d.get("query", {}).get("pages", {})


def dari_kategori(kat, limit):
    return _kumpulkan({"action": "query", "generator": "categorymembers",
                       "gcmtitle": f"Category:{kat}", "gcmtype": "file",
                       "gcmlimit": limit})


def dari_pencarian(q, limit):
    return _kumpulkan({"action": "query", "generator": "search",
                       "gsrsearch": q, "gsrnamespace": 6, "gsrlimit": limit})


def unduh(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=90).read()


def main():
    ap = argparse.ArgumentParser(description="Unduh kandidat negatif dari Wikimedia Commons.")
    ap.add_argument("--maks", type=int, default=60)
    ap.add_argument("--out", default=str(ROOT / "data" / "lokal" / "negatif-publik"))
    ap.add_argument("--kategori", default=",".join(KATEGORI_DEFAULT))
    ap.add_argument("--queries", default="", help="opsional: pencarian kata kunci tambahan")
    ap.add_argument("--kecerahan-min", type=int, default=80)
    ap.add_argument("--lebar-min", type=int, default=800)
    args = ap.parse_args()

    from PIL import Image, ImageStat

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kredit, n = [], 0
    sudah = set()

    sumber = ([("kategori", k.strip()) for k in args.kategori.split(",") if k.strip()]
              + [("pencarian", q.strip()) for q in args.queries.split(",") if q.strip()])

    for jenis, nama in sumber:
        if n >= args.maks:
            break
        try:
            pages = (dari_kategori(nama, min(50, args.maks - n)) if jenis == "kategori"
                     else dari_pencarian(nama, min(50, args.maks - n)))
        except Exception as e:
            print(f"  (gagal {jenis} '{_teks(nama,40)}': {_teks(e)})")
            continue
        for v in pages.values():
            if n >= args.maks:
                break
            judul = v.get("title", "")
            if not judul.lower().endswith(EKST_OK):
                continue
            if judul in sudah:
                continue
            ii = (v.get("imageinfo") or [{}])[0]
            src = ii.get("thumburl") or ii.get("url")
            if not src:
                continue
            if (ii.get("width") or 0) and ii["width"] < args.lebar_min:
                continue
            try:
                data = unduh(src)
                im = Image.open(io.BytesIO(data))
                luma = ImageStat.Stat(im.convert("L")).mean[0]
            except Exception:
                continue
            if luma < args.kecerahan_min:
                continue
            nama_file = f"pub_{n:04d}.jpg"
            try:
                Image.open(io.BytesIO(data)).convert("RGB").save(
                    out / nama_file, "JPEG", quality=88)
            except Exception:
                continue
            md = ii.get("extmetadata", {})
            kredit.append({
                "file": nama_file, "judul": judul,
                "artis": _teks((md.get("Artist") or {}).get("value", ""), 120),
                "lisensi": _teks((md.get("LicenseShortName") or {}).get("value", ""), 40),
                "url_halaman": "https://commons.wikimedia.org/wiki/"
                               + urllib.parse.quote(judul.replace(" ", "_")),
                "url_file": ii.get("url", ""),
                "kecerahan": round(luma, 1),
                "sumber": f"{jenis}:{nama}",
            })
            sudah.add(judul)
            n += 1
            print(f"  [{n}] {_teks(judul)} | {_teks((md.get('LicenseShortName') or {}).get('value',''), 16)} | luma {luma:.0f}")
            time.sleep(0.3)

    with open(out / "Kredit.csv", "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=["file", "judul", "artis", "lisensi",
                                           "url_halaman", "url_file", "kecerahan", "sumber"])
        wr.writeheader()
        wr.writerows(kredit)
    print(f"\n{n} gambar -> {out}")
    print("Atribusi: Kredit.csv (WAJIB untuk lisensi CC BY-SA).")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
