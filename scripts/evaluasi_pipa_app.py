"""Evaluasi P/R/F1 PIPELINE APLIKASI pada dataset berlabel (default: BPID test).

Bedanya dengan `scripts/evaluasi_tta.py`: skrip itu menilai keluaran MENTAH model
(`predict` + augment), sedangkan skrip ini menjalankan
`web/deteksi.py:analisis_gambar()` apa adanya — TTA, `saring_rows`,
`gabung_fragmen`, gate jalan basah, dan `batas_topk` semuanya ikut aktif.
Hasilnya sebanding dengan yang benar-benar dilihat pengguna, jadi cocok untuk
mengunci angka di `docs/Panduan-Tuning-Model.md` §6d/§6e dan untuk menguji efek
`maks_sisi_proses` (lihat `config/inferensi.yaml`).

Prasyarat data (folder `data/` gitignored — salin sendiri, JANGAN di-commit):
    data/publik/bpid/test/images/*.jpg
    data/publik/bpid/test/labels/*.txt
Bila data ada di tempat lain, arahkan dengan `--bpid`.

PENTING: BPID test (161 gambar berlabel) adalah satu-satunya set uji OOD. Jangan
pernah dipakai untuk melatih/menyetel model — hanya untuk mengukur.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\evaluasi_pipa_app.py --maks 0
    .\\.venv\\Scripts\\python scripts\\evaluasi_pipa_app.py --maks 0 1536 960
    .\\.venv\\Scripts\\python scripts\\evaluasi_pipa_app.py --conf 0.30 --remap 0:4

TTA ON (mengikuti jalur gambar aplikasi) membuat ~161 gambar memakan beberapa
menit di GPU kelas GTX 1650 (±0,5 s/gambar pada foto 12 MP). Skrip ini TIDAK
mengukur ukuran muatan `gambar_jpg` (encode sengaja dilewati demi kecepatan);
ukur muatan lewat UI atau pemanggilan `analisis_gambar` langsung.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for _p in (str(ROOT), str(ROOT / "web"), str(ROOT / "app")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Cegah unduhan paket otomatis saat skrip berjalan (lihat evaluasi_model.py).
os.environ.setdefault("YOLO_AUTOINSTALL", "false")

EKST_IMG = {".jpg", ".jpeg", ".png"}


def baca_gt(label_path, w, h, remap):
    """Label YOLO (normalized) -> [(kelas_id, x1, y1, x2, y2)] piksel gambar asli."""
    out = []
    if not label_path.is_file():
        return out
    for baris in label_path.read_text(encoding="utf-8").splitlines():
        s = baris.split()
        if len(s) < 5:
            continue
        c = int(s[0])
        c = remap.get(c, c)
        cx, cy, bw, bh = (float(v) for v in s[1:5])
        out.append((c, (cx - bw / 2) * w, (cy - bh / 2) * h,
                    (cx + bw / 2) * w, (cy + bh / 2) * h))
    return out


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    if inter <= 0:
        return 0.0
    aa = (a[2] - a[0]) * (a[3] - a[1])
    bb = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (aa + bb - inter)


def cocokkan(pred, gt, iou_min):
    """Greedy 1-ke-1 per kelas. pred = [(kelas, box, conf)] urut conf menurun;
    gt = [(kelas, box)]. Kembalikan (tp, fp, fn) agregat.
    """
    tp = fp = 0
    dipakai = set()
    for pcls, pbox, _pc in pred:
        terbaik, idx = 0.0, None
        for i, g in enumerate(gt):
            if i in dipakai or g[0] != pcls:
                continue
            v = iou(pbox, g[1])
            if v > terbaik:
                terbaik, idx = v, i
        if idx is not None and terbaik >= iou_min:
            dipakai.add(idx)
            tp += 1
        else:
            fp += 1
    return tp, fp, len(gt) - len(dipakai)


def putar(args, maks, remap, konf):
    import deteksi as d
    from PIL import Image

    # Eval hanya butuh `rows`; encode JPEG + base64 dibuang agar cepat.
    d.encode_jpg = lambda _img: ""
    d._infer = None  # paksa baca ulang config dari disk
    asli_inf = d.get_inferensi
    if maks:
        d.get_inferensi = (lambda m: (lambda path=None: {
            **asli_inf(path), "maks_sisi_proses": int(m)}))(maks)

    model = d.get_model(kunci="model_gambar")
    nama_ke_id = {d.nama_kelas(model.names, i): i
                  for i in range(len(model.names))}

    imgs = sorted(p for p in (args.bpid / "images").iterdir()
                  if p.suffix.lower() in EKST_IMG)
    if not imgs:
        print("Tidak ada gambar di %s" % (args.bpid / "images"))
        return None

    per_kelas = {}
    n_baris = 0
    t0 = time.perf_counter()
    for i, p in enumerate(imgs, 1):
        with Image.open(p) as im:
            w, h = im.size
        gt = [(c, box) for c, *box in baca_gt(
            args.bpid / "labels" / (p.stem + ".txt"), w, h, remap)]
        out = d.analisis_gambar(p.read_bytes(), conf=konf)
        n_baris += len(out["rows"])
        # Baris aplikasi memakai NAMA kelas; ubah ke id supaya bisa dicocokkan
        # dengan label mentah (nama kelas bisa berubah tanpa mengubah arti angka).
        pred = [(nama_ke_id.get(r.get("kelas"), -1), [float(v) for v in r["box"]],
                 float(r["conf"])) for r in out["rows"]]
        for cid in {g[0] for g in gt} | {x[0] for x in pred}:
            g = [x for x in gt if x[0] == cid]
            pr = sorted((x for x in pred if x[0] == cid),
                        key=lambda x: -x[2])
            a, b, c = cocokkan(pr, g, args.iou)
            t = per_kelas.setdefault(cid, [0, 0, 0])
            t[0] += a
            t[1] += b
            t[2] += c
        if i % 25 == 0:
            print("   ... %d/%d gambar (%.1f s)" % (i, len(imgs),
                                                   time.perf_counter() - t0))
    dt = (time.perf_counter() - t0) / len(imgs)
    return {"maks": maks, "per_kelas": per_kelas, "n_baris": n_baris,
            "n_gambar": len(imgs), "detik": dt,
            "nama_kelas": {i: d.nama_kelas(model.names, i)
                           for i in range(len(model.names))}}


def ringkas(hasil):
    """(tp, fp, fn) agregat semua kelas."""
    tp = sum(v[0] for v in hasil["per_kelas"].values())
    fp = sum(v[1] for v in hasil["per_kelas"].values())
    fn = sum(v[2] for v in hasil["per_kelas"].values())
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return tp, fp, fn, prec, rec, f1


def main():
    ap = argparse.ArgumentParser(
        description="Evaluasi P/R/F1 pipeline aplikasi (analisis_gambar).")
    ap.add_argument("--bpid", default="data/publik/bpid/test",
                    help="folder dataset: harus punya images/ + labels/")
    ap.add_argument("--conf", type=float, default=0.30,
                    help="ambang slider (default 0.30 = web/app.py CONF_DEFAULT)")
    ap.add_argument("--iou", type=float, default=0.5, help="ambang IoU cocok")
    ap.add_argument("--remap", default="0:4",
                    help="terjemah id label, mis. '0:4' (BPID pothole -> model)")
    ap.add_argument("--maks", type=int, nargs="+", default=[0],
                    help="nilai maks_sisi_proses yang diuji (0 = resolusi asli)")
    ap.add_argument("--json", default=None,
                    help="tulis ringkasan ke berkas JSON (opsional)")
    args = ap.parse_args()

    args.bpid = Path(args.bpid)
    if not (args.bpid / "images").is_dir():
        print("Folder tidak ditemukan: %s" % (args.bpid / "images"))
        print("Salin BPID test ke sana, atau pakai --bpid <lokasi>.")
        return 2
    remap = {}
    for pasangan in (args.remap or "").split(","):
        if ":" in pasangan:
            a, b = pasangan.split(":", 1)
            remap[int(a)] = int(b)

    print("Dataset : %s" % args.bpid)
    print("Conf    : %.2f | IoU cocok: %.2f | remap: %s"
          % (args.conf, args.iou, remap or "tanpa"))

    hasil = []
    for m in args.maks:
        print("\n== maks_sisi_proses = %s =="
              % ("asli/tanpa batas" if m == 0 else m))
        h = putar(args, m, remap, args.conf)
        if h is None:
            return 2
        tp, fp, fn, prec, rec, f1 = ringkas(h)
        print("   TP %d  FP %d  FN %d | P %.3f  R %.3f  F1 %.3f | "
              "%.2f s/gbr | %d baris total"
              % (tp, fp, fn, prec, rec, f1, h["detik"], h["n_baris"]))
        for cid, (t, f, n) in sorted(h["per_kelas"].items()):
            nm = h["nama_kelas"].get(cid, "kelas-%d" % cid)
            p = t / (t + f) if t + f else 0.0
            r = t / (t + n) if t + n else 0.0
            ff = 2 * p * r / (p + r) if p + r else 0.0
            print("      %-22s TP %4d FP %4d FN %4d | P %.3f R %.3f F1 %.3f"
                  % (nm, t, f, n, p, r, ff))
        h["ringkas"] = {"tp": tp, "fp": fp, "fn": fn, "precision": prec,
                        "recall": rec, "f1": f1, "detik": h["detik"]}
        hasil.append(h)

    print("\nRINGKASAN (semua kelas digabung)")
    print("  %-10s %6s %6s %6s %8s %8s %8s %9s"
          % ("maks", "TP", "FP", "FN", "P", "R", "F1", "s/gbr"))
    for h in hasil:
        r = h["ringkas"]
        print("  %-10s %6d %6d %6d %8.3f %8.3f %8.3f %9.2f"
              % (("asli" if h["maks"] == 0 else h["maks"]), r["tp"], r["fp"],
                 r["fn"], r["precision"], r["recall"], r["f1"], r["detik"]))
    print("\n  PERINGATAN METODE: baris 'digabung' hanya bermakna bila SEMUA")
    print("  kelas berlabel. Pada BPID labelnya pothole saja, sehingga deteksi")
    print("  retak/kelas lain dihitung FP padahal belum tentu salah (tidak ada")
    print("  label pembandingnya). Untuk laporan, kutip baris kelas yang memang")
    print("  berlabel — lihat tabel per kelas di atas, bukan baris digabung.")

    if args.json:
        Path(args.json).write_text(
            json.dumps([{k: v for k, v in h.items() if k != "nama_kelas"}
                        for h in hasil], indent=2, ensure_ascii=False),
            encoding="utf-8")
        print("\nRingkasan JSON: %s" % args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
