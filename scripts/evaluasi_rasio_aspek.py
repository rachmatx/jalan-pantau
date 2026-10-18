"""Ukur dampak filter rasio aspek retak (rasio_aspek_min_retak) dengan ANGKA.

Latar: `masuk_akal()` di web/deteksi.py membuang deteksi retak
longitudinal/transversal yang box-nya near-square (panjang/lebar < ambang,
default 1.5) dengan klaim "hampir pasti false positive". Klaim ini belum pernah
diukur — post-mortem FP16 (docs/Panduan-Tuning-Model.md §6d) menunjukkan angka
besar "ukuran ditolak" kemarin berasal dari box NaN, bukan geometri.

Skrip ini memakai PIPELINE PENYARING APLIKASI YANG SEBENARNYA (saring_rows)
pada dataset berlabel, lalu membandingkan P/R/F1 per kelas untuk tiap nilai
rasio. Rasio 1.0 = filter NONAKTIF (syarat di kode: rasio_min > 1.0).

Pakai (dari root repo), di Kaggle dengan GPU:
    python scripts/evaluasi_rasio_aspek.py --data /kaggle/input/.../val \
        --model /kaggle/input/.../best.pt --imgsz 640 --conf 0.25 \
        --rasio-list 1.0,1.2,1.5,2.0

Satu inferensi per gambar (conf floor 0.01); sapuan rasio hanya mengulang
tahap penyaring yang murah. Estimasi: ~15-25 dtk per 160 gambar di T4.
"""
import argparse
import copy
import json
import os
import sys
from datetime import datetime
from pathlib import Path

os.environ.setdefault("YOLO_AUTOINSTALL", "false")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "web"))

NAMA_KE_ID = {"longitudinal_crack": 0, "transverse_crack": 1,
              "alligator_crack": 2, "other_corruption": 3, "pothole": 4}
ID_KE_NAMA = {v: k for k, v in NAMA_KE_ID.items()}
EKST_IMG = {".jpg", ".jpeg", ".png"}


def _iou(a, b):
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    iw, ih = max(0.0, x2 - x1), max(0.0, y2 - y1)
    inter = iw * ih
    if inter <= 0:
        return 0.0
    la = max(0.0, a[2] - a[0]) * max(0.0, a[3] - a[1])
    lb = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return inter / (la + lb - inter) if (la + lb - inter) > 0 else 0.0


def baca_gt(label_path, remap, w, h):
    gt = []
    if not label_path.is_file():
        return gt
    for baris in label_path.read_text(encoding="utf-8").splitlines():
        s = baris.split()
        if len(s) < 5:
            continue
        cid = remap.get(int(float(s[0])), int(float(s[0])))
        cx, cy, bw, bh = (float(s[1]) * w, float(s[2]) * h,
                          float(s[3]) * w, float(s[4]) * h)
        gt.append((cid, [cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2]))
    return gt


def cocokkan(dets, gts, iou_min=0.5):
    """Greedy per kelas: deteksi urut conf -> GT IoU terbesar. -> (tp, fp, fn)."""
    tp = fp = fn = 0
    for cid in set([d[0] for d in dets] + [g[0] for g in gts]):
        dd = sorted([d for d in dets if d[0] == cid], key=lambda d: -d[1])
        gg = [g[1] for g in gts if g[0] == cid]
        terpakai = [False] * len(gg)
        for _, conf, box in dd:
            terbaik, bi = -1.0, -1
            for i, gbox in enumerate(gg):
                if terpakai[i]:
                    continue
                v = _iou(box, gbox)
                if v > terbaik:
                    terbaik, bi = v, i
            if terbaik >= iou_min:
                tp += 1
                terpakai[bi] = True
            else:
                fp += 1
        fn += sum(1 for t in terpakai if not t)
    return tp, fp, fn


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = (2 * p * r / (p + r)) if (p + r) else 0.0
    return p, r, f


def main():
    ap = argparse.ArgumentParser(description="Ukur dampak filter rasio aspek.")
    ap.add_argument("--data", required=True, help="folder berisi images/ dan labels/")
    ap.add_argument("--model", required=True, help="path bobot (.pt)")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--conf", type=float, default=0.25,
                    help="conf operasi (slider aplikasi)")
    ap.add_argument("--remap", default="", help='peta kelas, mis. "0:4"')
    ap.add_argument("--rasio-list", default="1.0,1.2,1.5,2.0",
                    help="nilai rasio_aspek_min_retak; 1.0 = filter mati")
    ap.add_argument("--half", action="store_true",
                    help="FP16 (default FP32, sesuai jalur foto aplikasi)")
    args = ap.parse_args()

    import cv2
    from ultralytics import YOLO
    from deteksi import (ambang_efektif, get_config, get_inferensi,
                         kanonik_kelas, nama_kelas, saring_rows, _baris_rusak)
    from severity import diagnose
    from prioritas import skor as skor_prioritas

    remap = {}
    for pasangan in filter(None, args.remap.split(",")):
        a, b = pasangan.split(":")
        remap[int(a)] = int(b)

    data_dir = Path(args.data)
    img_dir, lbl_dir = data_dir / "images", data_dir / "labels"
    if not img_dir.is_dir():
        raise SystemExit(f"Folder images tidak ditemukan: {img_dir}")
    gambars = sorted(p for p in img_dir.iterdir()
                     if p.suffix.lower() in EKST_IMG)
    if not gambars:
        raise SystemExit(f"Tidak ada gambar di {img_dir}")

    inf = get_inferensi()
    cfg = get_config()
    toleransi = inf.get("toleransi_kelas") or {}
    batas_dasar = dict(inf.get("batas_ukuran") or {})
    luas_min = float((inf.get("saring") or {}).get("luas_min_px", 0) or 0)
    rasios = [float(x) for x in args.rasio_list.split(",") if x.strip()]

    mp = Path(args.model)
    if not mp.is_file():
        raise SystemExit(f"Bobot tidak ditemukan: {mp}")
    model = YOLO(str(mp))
    print(f"Model {mp.name} | {len(gambars)} gambar | imgsz {args.imgsz} | "
          f"conf operasi {args.conf} | half={args.half}", flush=True)

    # --- Satu inferensi per gambar pada conf floor rendah -----------------
    pra = []  # (rows mentah siap saring, gt)
    for gi, gp in enumerate(gambars):
        if gi % 50 == 0:
            print(f"  inferensi {gi}/{len(gambars)}...", flush=True)
        res = model.predict(str(gp), conf=0.01, iou=0.5, imgsz=args.imgsz,
                            half=args.half, verbose=False)[0]
        img = cv2.imread(str(gp))
        h, w = img.shape[:2]
        rows = []
        for b in res.boxes:
            nama = kanonik_kelas(nama_kelas(model.names, int(b.cls[0])))
            if nama not in NAMA_KE_ID:
                continue
            x1, y1, x2, y2 = (float(v) for v in b.xyxy[0])
            item = diagnose(nama, x1, y1, x2, y2, cfg)
            item["conf"] = round(float(b.conf[0]), 3)
            item["box"] = [x1, y1, x2, y2]
            rows.append(skor_prioritas(item))
        gt = baca_gt(lbl_dir / (gp.stem + ".txt"), remap, w, h)
        pra.append((rows, gt))
    print(f"Inferensi selesai: {len(pra)} gambar.", flush=True)

    # --- Sapuan rasio: hanya ulang tahap penyaring (murah) -----------------
    hasil = []
    for rasio in rasios:
        batas = dict(batas_dasar)
        batas["rasio_aspek_min_retak"] = rasio
        stat = {cid: {"tp": 0, "fp": 0, "fn": 0,
                      "n_aspek": 0, "n_ukuran": 0}
                for cid in ID_KE_NAMA}
        tot_aspek = tot_ukuran = 0
        for rows, gt in pra:
            lolos, info = saring_rows(rows, args.conf, toleransi, batas,
                                     luas_min)
            tot_aspek += info.get("aspek", 0)
            tot_ukuran += info.get("ukuran", 0)
            dets = [(NAMA_KE_ID[r["kelas"]], float(r["conf"]), r["box"])
                    for r in lolos if r.get("kelas") in NAMA_KE_ID]
            # Atribusikan penolakan aspek ke kelasnya. Mengikuti urutan
            # saring_rows: baris rusak (NaN) dan di bawah ambang sudah gugur
            # duluan, jadi tak dihitung sebagai aspek.
            for r in rows:
                try:
                    cf = float(r.get("conf", 0))
                except (TypeError, ValueError):
                    continue
                if _baris_rusak(r, cf):
                    continue
                if cf < ambang_efektif(r.get("kelas", ""), args.conf,
                                       toleransi):
                    continue
                if r.get("kelas") in ("longitudinal_crack",
                                      "transverse_crack"):
                    pj = float(r.get("panjang_cm", 0) or 0)
                    lb = float(r.get("lebar_cm", 0) or 0)
                    if lb > 0 and rasio > 1.0 and pj / lb < rasio:
                        stat[NAMA_KE_ID[r["kelas"]]]["n_aspek"] += 1
            per_kelas_gt = {}
            for cid, gbox in gt:
                per_kelas_gt.setdefault(cid, []).append(gbox)
            for cid in ID_KE_NAMA:
                dd = [(c, cf, bx) for c, cf, bx in dets if c == cid]
                gg = [(cid, bx) for bx in per_kelas_gt.get(cid, [])]
                tp, fp, fn = cocokkan(dd, gg)
                stat[cid]["tp"] += tp
                stat[cid]["fp"] += fp
                stat[cid]["fn"] += fn
        baris = {"rasio": rasio, "ditolak_aspek": tot_aspek,
                 "ditolak_ukuran": tot_ukuran, "kelas": {}}
        for cid, nama in ID_KE_NAMA.items():
            s = stat[cid]
            p, r, f = prf(s["tp"], s["fp"], s["fn"])
            baris["kelas"][nama] = {
                "tp": s["tp"], "fp": s["fp"], "fn": s["fn"],
                "precision": round(p, 4), "recall": round(r, 4),
                "f1": round(f, 4), "n_aspek_kelas": s["n_aspek"]}
        hasil.append(baris)
        fokus = baris["kelas"]
        print(f"\nrasio {rasio} (OFF)" if rasio <= 1.0 else f"\nrasio {rasio}",
              flush=True)
        print(f"  ditolak: aspek={tot_aspek} ukuran={tot_ukuran}", flush=True)
        for nama in ("longitudinal_crack", "transverse_crack",
                     "alligator_crack", "pothole"):
            k = fokus[nama]
            print(f"  {nama:20s} P {k['precision']:.3f} R {k['recall']:.3f} "
                  f"F1 {k['f1']:.3f} (tp {k['tp']} fp {k['fp']} fn {k['fn']})",
                  flush=True)

    # --- Ringkasan keputusan ------------------------------------------------
    print("\n=== Ringkasan (retak longitudinal + transversal gabungan) ===",
          flush=True)
    for baris in hasil:
        tps = sum(baris["kelas"][n]["tp"]
                  for n in ("longitudinal_crack", "transverse_crack"))
        fps = sum(baris["kelas"][n]["fp"]
                  for n in ("longitudinal_crack", "transverse_crack"))
        fns = sum(baris["kelas"][n]["fn"]
                  for n in ("longitudinal_crack", "transverse_crack"))
        p, r, f = prf(tps, fps, fns)
        label = "OFF" if baris["rasio"] <= 1.0 else "on "
        print(f"  rasio {baris['rasio']:<4} [{label}] "
              f"P {p:.3f} R {r:.3f} F1 {f:.3f} | "
              f"aspek ditolak: {baris['ditolak_aspek']}", flush=True)

    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    cap = datetime.now().strftime("%Y%m%d-%H%M%S")
    keluar = reports / f"evaluasi-rasio-aspek-{cap}.json"
    keluar.write_text(json.dumps({
        "dataset": str(data_dir), "n_gambar": len(gambars),
        "model": mp.name, "imgsz": args.imgsz, "conf_operasi": args.conf,
        "remap": remap, "iou": 0.5, "half": args.half,
        "dibuat": datetime.now().isoformat(timespec="seconds"),
        "catatan": ("Rasio 1.0 = filter rasio aspek NONAKTIF. Pipeline penyaring "
                    "= saring_rows aplikasi (ambang+toleransi+geometri). "
                    "Klaim 'hampir pasti FP' terbukti bila F1 naik & recall "
                    "tak turun signifikan saat filter ON."),
        "hasil": hasil,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nArtefak: {keluar.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
