"""Pra-annotasi foto jadi dataset YOLO (fine-tuning lokal) + audit hard-negative.

Model sekarang masih dilatih pada RDD2022 (jalan Tiongkok, siang), sementara
target aplikasi adalah jalan lokal — itu sebabnya kerikil/daun sering terbaca
pothole dan foto malam hampir tak terbaca (lihat docs/Panduan-Tuning-Model.md
§6d). Menyembuhkan itu berarti menambah data latih lokal, dan hambatan terbesarnya
adalah makin label: tools anotasi butuh kotak yang benar untuk tiap foto.

Skrip ini memangkas sebagian besar pekerjaan itu: model berjalan dulu, hasilnya
dipakai sebagai PRE-LABEL, lalu operator hanya PERBAIKI yang salah — bukan
menggambar kotak dari nol.

Dua mode:

  --mode dataset  Tulis dataset YOLO (images/ + labels/ + data.yaml + ringkasan.csv)
                  untuk folder foto yang akan dipakai latih.
  --mode audit    Tulis APA SAJA. Hanya laporkan gambar yang DITANDAI model pada
                  folder yang dianggap negatif — inilah kandidat hard-negative:
                  foto "bersih" yang justru menghasilkan pothole palsu.

KENAPA TIDAK OTOMATIS MENYIMPUL "INI NEGATIF": pada folder negatif, gambar yang
ditandai model justru PESANG paling mungkin berisi kerusakan sungguhan (bukan
false positive). Menulis label kosong secara otomatis akan melatih model
membutakan diri sendiri. Semua hasil wajib ditinjau manusia dulu.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\pra_label.py --mode dataset --sumber test_foto --keluar data\\lokal\\terlabel
    .\\.venv\\Scripts\\python scripts\\pra_label.py --mode dataset --kering        # pratinjau tanpa menulis
    .\\.venv\\Scripts\\python scripts\\pra_label.py --mode audit --sumber "..\\TA Machine Learning - Deteksi Kerusakan Jalan Real-Time\\data\\lokal\\negatif-bersih"
    .\\.venv\\Scripts\\python scripts\\pra_label.py --mode dataset --malam         # foto malam (CLAHE)

Setelah label dikoreksi manual (LabelImg/Gradio/CVAT), latih ulang:

    .\\.venv\\Scripts\\python scripts\\evaluasi_model.py --data <dataset> --imgsz 640 --model best.pt

Dan JANGAN pernah latih dari BPID test (161 gambar berlabel) — itu satu-satunya
set uji OOD yang dipakai untuk semua keputusan tuning di §6d.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

# Cegah unduhan paket otomatis saat skrip berjalan (lihat evaluasi_model.py).
os.environ.setdefault("YOLO_AUTOINSTALL", "false")

ROOT = Path(__file__).resolve().parents[1]
for _p in (ROOT, ROOT / "web", ROOT / "app"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

EKST = {".jpg", ".jpeg", ".png", ".bmp"}


def id_kelas():
    """id YOLO per nama kelas kanonik (ikut urutan kelas model saat ini).

    Kalau urutan kelas model berubah, label lama jadi salah Diam-diam — jadi
    konvensi ini dipakai bersama (bukan angka hard-code per kelas).
    """
    import deteksi
    model = deteksi.get_model(kunci="model_gambar")
    return {deteksi.kanonik_kelas(nama): int(idx)
            for idx, nama in model.names.items()}


def telusuri(sumber):
    """Semua berkas gambar di `sumber` (rekursif), urut agar hasil reproducible."""
    p = Path(sumber)
    if not p.exists():
        raise SystemExit("Folder tidak ditemukan: %s" % p)
    if p.is_file():
        return [p]
    return sorted((f for f in p.rglob("*") if f.suffix.lower() in EKST),
                  key=lambda f: str(f).lower())


def ke_yolo(baris, W, H, peta_id):
    """Satu baris YOLO: `cls cx cy w h` dengan koordinat ternormalisasi 0..1."""
    x1, y1, x2, y2 = [float(v) for v in baris["box"]]
    cls = peta_id.get(baris["kelas"])
    if cls is None:
        return None
    cx, cy = ((x1 + x2) / 2) / W, ((y1 + y2) / 2) / H
    bw, bh = (x2 - x1) / W, (y2 - y1) / H
    return "%d %.5f %.5f %.5f %.5f" % (cls, cx, cy, bw, bh)


def main():
    ap = argparse.ArgumentParser(
        description="Pra-annotasi YOLO + audit hard-negative.")
    ap.add_argument("--mode", choices=("dataset", "audit"), default="dataset")
    ap.add_argument("--sumber", required=True, help="folder foto (atau satu berkas)")
    ap.add_argument("--keluar", default=str(ROOT / "data" / "lokal" / "terlabel"),
                    help="folder dataset keluaran (mode dataset)")
    ap.add_argument("--conf", type=float, default=None,
                    help="ambang (default: DEFAULT slider aplikasi)")
    ap.add_argument("--malam", action="store_true",
                    help="aktifkan CLAHE untuk foto gelap")
    ap.add_argument("--teliti", action="store_true",
                    help="mode teliti (lambat; hanya untuk eksperimen)")
    ap.add_argument("--kering", action="store_true",
                    help="hitung dan tampilkan, jangan tulis berkas apa pun")
    ap.add_argument("--timpa", action="store_true",
                    help="timpa label yang sudah ada")
    ap.add_argument("--teratas", type=int, default=15,
                    help="berapa gambar teratas yang ditampilkan")
    args = ap.parse_args()

    import deteksi
    import web.app as app_mod

    conf = args.conf if args.conf is not None else app_mod.CONF_DEFAULT
    peta_id = id_kelas()
    inf = deteksi.get_inferensi()
    print("model       : %s" % deteksi.resolve_model(kunci="model_gambar").name)
    print("kelas (YOLO): %s" % ", ".join(
        "%d=%s" % (v, k) for k, v in sorted(peta_id.items(), key=lambda x: x[1])))
    print("setelan     : imgsz=%s tta=%s conf=%.2f malam=%s teliti=%s"
          % (inf["imgsz_gambar"], inf["tta"], conf, args.malam, args.teliti))
    print("mode        : %s%s" % (args.mode, " (kering)" if args.kering else ""))

    foto = telusuri(args.sumber)
    if not foto:
        raise SystemExit("Tidak ada gambar di %s" % args.sumber)

    keluar = Path(args.keluar)
    (keluar / "images").mkdir(parents=True, exist_ok=True)
    (keluar / "labels").mkdir(parents=True, exist_ok=True)
    ringkasan = []
    curiga = []
    n_ada_label = 0
    for i, f in enumerate(foto, 1):
        try:
            raw = f.read_bytes()
            img = deteksi.decode_image(raw)
        except Exception as e:  # berkas rusak / bukan gambar
            print("  [%d/%d] LEWAT %s (%s)" % (i, len(foto), f.name, type(e).__name__))
            continue
        H, W = img.shape[:2]
        try:
            out = deteksi.analisis_gambar(raw, conf=conf, malam=args.malam,
                                          teliti=args.teliti)
        except Exception as e:
            print("  [%d/%d] GAGAL %s (%s)" % (i, len(foto), f.name, type(e).__name__))
            continue
        baris = [ke_yolo(r, W, H, peta_id) for r in out["rows"]]
        baris = [b for b in baris if b]
        per_kelas = {}
        for r in out["rows"]:
            per_kelas[r["kelas"]] = per_kelas.get(r["kelas"], 0) + 1
        conf_maks = max([r["conf"] for r in out["rows"]], default=0.0)
        ringkasan.append({
            "berkas": f.name, "lebar": W, "tinggi": H,
            "jumlah": len(baris), "conf_maks": round(conf_maks, 3),
            "kelas": ";".join("%s=%d" % (k, v) for k, v in sorted(per_kelas.items())),
        })
        if baris:
            curiga.append((len(baris), conf_maks, f, out["rows"]))
        if args.mode == "dataset" and not args.kering:
            label = keluar / "labels" / (f.stem + ".txt")
            if label.exists() and not args.timpa:
                n_ada_label += 1
            else:
                label.write_text(
                    ("\n".join(baris) + "\n") if baris else "",
                    encoding="utf-8")
            tujuan = keluar / "images" / f.name
            if not tujuan.exists() or args.timpa:
                tujuan.write_bytes(raw)
        if i % 25 == 0:
            print("  ... %d/%d" % (i, len(foto)))

    total = sum(r["jumlah"] for r in ringkasan)
    print("\n=== RINGKASAN ===")
    print("gambar diproses : %d" % len(ringkasan))
    print("gambar bertanda : %d  (total kotak %d)" % (len(curiga), total))
    if ringkasan:
        print("conf maks       : %.3f" % max(r["conf_maks"] for r in ringkasan))
    if args.mode == "dataset":
        if not args.kering:
            print("keluaran        : %s" % keluar)
            print("labels          : %d ditulis, %d sudah ada (pakai --timpa untuk tulis ulang)"
                  % (len(ringkasan) - n_ada_label, n_ada_label))
            yaml = ("# Dibuat scripts/pra_label.py. Urutan kelas WAJIB sama dengan model.\n"
                    "path: .\ntrain: images\nval: images\n\nnc: %d\nnames:\n"
                    % len(peta_id))
            for nama, idx in sorted(peta_id.items(), key=lambda x: x[1]):
                yaml += "  %d: %s\n" % (idx, nama)
            (keluar / "data.yaml").write_text(yaml, encoding="utf-8")
            with (keluar / "ringkasan.csv").open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(ringkasan[0].keys()))
                w.writeheader()
                w.writerows(ringkasan)
            print("data.yaml       : ditulis (%d kelas)" % len(peta_id))
    if curiga:
        curiga.sort(key=lambda t: (-t[0], -t[1]))
        print("\n%s %d gambar (urutan kotak x conf):"
              % ("KANDIDAT HARD-NEGATIVE" if args.mode == "audit"
                 else "GAMBAR YANG DIDETEKSI", len(curiga)))
        for n, cm, f, baris in curiga[:args.teratas]:
            ringkas = ", ".join(
                "%s %.2f" % (r["kelas"], r["conf"]) for r in
                sorted(baris, key=lambda r: -r["conf"])[:3])
            print("  %-28s %2d kotak, conf %.2f | %s" % (f.name, n, cm, ringkas))
        if len(curiga) > args.teratas:
            print("  ... %d lainnya (lihat ringkasan.csv)"
                  % (len(curiga) - args.teratas))
    if args.mode == "audit":
        print("\nCatatan: pada folder negatif, gambar di atas justru PESANG berisi")
        print("kerusakan sungguhan. Periksa satu per satu; JANGAN label kosong")
        print("otomatis — itu melatih model membutakan diri sendiri.")


if __name__ == "__main__":
    main()