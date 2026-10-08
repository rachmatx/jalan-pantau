"""Evaluasi model + sapuan ambang confidence pada dataset berlabel lokal.

Tujuan: menentukan ambang confidence (global & per kelas) dengan BUKTI, bukan
perasaan. Berguna untuk mengisi `toleransi_kelas` / conf di config/inferensi.yaml.

Fitur:
- Membangun dataset sementara dari folder images/ + labels/ (gambar di-hardlink,
  hemat ruang) dan menulis data.yaml.
- Opsi `--remap 0:4` untuk menerjemahkan id kelas (mis. BPID: 0 -> 4 pothole).
- Menjalankan val() pada beberapa nilai conf, lalu melaporkan mAP50, mAP50-95,
  Precision, Recall, F1 -> dan conf terbaik (F1 maksimum).
- Menyimpan artefak JSON ke reports/.

Pakai (dari root repo):
    .\\.venv\\Scripts\\python scripts\\evaluasi_model.py --data data/publik/bpid/test --remap 0:4 --model best.onnx --imgsz 640 --conf-list 0.15,0.25,0.35,0.45
    .\\.venv\\Scripts\\python scripts\\evaluasi_model.py --data data/publik/bpid/test --remap 0:4 --model best_yolo11s.pt --imgsz 960
"""
import argparse
import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = ROOT / "app" / "weights"
REPORTS = ROOT / "reports"
EKST_IMG = {".jpg", ".jpeg", ".png"}
NAMA_KELAS = {0: "longitudinal_crack", 1: "transverse_crack", 2: "alligator_crack",
              3: "other_corruption", 4: "pothole"}


def _remap(peta, teks):
    if not peta:
        return teks
    keluar = []
    for baris in teks.splitlines():
        s = baris.split()
        if not s:
            continue
        s[0] = str(peta.get(int(s[0]), int(s[0])))
        keluar.append(" ".join(s))
    return "\n".join(keluar)


def bangun_dataset(data_dir, remap, tmp):
    """Buat struktur train/val sementara: images (hardlink) + labels (remap)."""
    img_dir = data_dir / "images"
    lbl_dir = data_dir / "labels"
    if not img_dir.is_dir():
        raise SystemExit(f"Folder images tidak ditemukan: {img_dir}")
    out = Path(tmp)
    (out / "images").mkdir(parents=True, exist_ok=True)
    (out / "labels").mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(img_dir.iterdir()):
        if p.suffix.lower() not in EKST_IMG:
            continue
        tujuan = out / "images" / p.name
        try:
            os.link(p, tujuan)          # hardlink (instan, tanpa admin)
        except OSError:
            shutil.copy(p, tujuan)      # fallback
        lp = lbl_dir / (p.stem + ".txt")
        teks = lp.read_text(encoding="utf-8") if lp.is_file() else ""
        (out / "labels" / (p.stem + ".txt")).write_text(_remap(remap, teks), encoding="utf-8")
        n += 1
    yaml_path = out / "data.yaml"
    nama = "\n".join(f"  {k}: {v}" for k, v in NAMA_KELAS.items())
    yaml_path.write_text(
        f"path: {out.as_posix()}\ntrain: images\nval: images\nnames:\n{nama}\n",
        encoding="utf-8")
    return yaml_path, n


def main():
    ap = argparse.ArgumentParser(description="Evaluasi + sapuan ambang pada dataset lokal.")
    ap.add_argument("--data", required=True, help="folder berisi images/ dan labels/")
    ap.add_argument("--model", default="best.onnx", help="nama di app/weights/ atau path")
    ap.add_argument("--imgsz", type=int, default=640)
    ap.add_argument("--remap", default="", help='peta kelas, mis. "0:4"')
    ap.add_argument("--conf-list", default="0.15,0.25,0.35,0.45")
    args = ap.parse_args()

    from ultralytics import YOLO
    mp = Path(args.model)
    if not mp.is_absolute():
        mp = WEIGHTS / args.model
    if not mp.is_file():
        raise SystemExit(f"Bobot tidak ditemukan: {mp}")

    remap = {}
    for pasangan in filter(None, args.remap.split(",")):
        a, b = pasangan.split(":")
        remap[int(a)] = int(b)

    data_dir = Path(args.data)
    if not data_dir.is_absolute():
        data_dir = ROOT / data_dir

    confs = [float(c) for c in args.conf_list.split(",") if c.strip()]
    with tempfile.TemporaryDirectory(prefix="eval_") as tmp:
        yaml_path, n = bangun_dataset(data_dir, remap, tmp)
        print(f"Dataset: {data_dir.name} ({n} gambar) | model {mp.name} imgsz {args.imgsz}")
        print("CATATAN: P/R/F1 di bawah = pada conf F1-optimal (bawaan ultralytics),")
        print("        BUKAN pada conf-floor yang diminta. conf-floor hanya menentukan")
        print("        batas bawah kurva PR -> mAP. Laporkan mAP pada floor rendah (mis. 0.001).")
        model = YOLO(str(mp))
        hasil = []
        for c in confs:
            m = model.val(data=str(yaml_path), split="val", imgsz=args.imgsz,
                          conf=c, iou=0.5, plots=False, verbose=False,
                          project=tmp, name=f"v{c}", exist_ok=True)
            p, r = float(m.box.mp), float(m.box.mr)
            f1 = (2 * p * r / (p + r)) if (p + r) else 0.0
            hasil.append({"conf_floor": c, "map50": round(float(m.box.map50), 4),
                          "map50_95": round(float(m.box.map), 4),
                          "precision_bestF1": round(p, 4),
                          "recall_bestF1": round(r, 4), "f1_bestF1": round(f1, 4)})
            print(f"  conf-floor {c:<5} mAP50 {hasil[-1]['map50']:.4f} "
                  f"mAP50-95 {hasil[-1]['map50_95']:.4f} | pada conf F1-optimal: "
                  f"P {p:.4f} R {r:.4f} F1 {f1:.4f}")

    terbaik = max(hasil, key=lambda x: x["map50"])
    puncak_f1 = max(hasil, key=lambda x: x["f1_bestF1"])
    print(f"\n- mAP50 tertinggi pada conf-floor terendah yang diuji: {terbaik['conf_floor']} "
          f"(mAP50 {terbaik['map50']})")
    print(f"- Titik operasi F1-optimal (bawaan ultralytics): P {puncak_f1['precision_bestF1']} "
          f"/ R {puncak_f1['recall_bestF1']} / F1 {puncak_f1['f1_bestF1']}")

    REPORTS.mkdir(exist_ok=True)
    cap = datetime.now().strftime("%Y%m%d-%H%M%S")
    keluar = REPORTS / f"evaluasi-{data_dir.name}-{cap}.json"
    keluar.write_text(json.dumps({
        "dataset": str(data_dir), "n_gambar": n, "model": mp.name,
        "imgsz": args.imgsz, "remap": remap, "iou": 0.5,
        "dibuat": datetime.now().isoformat(timespec="seconds"),
        "catatan": ("P/R/F1 = pada conf F1-optimal (bawaan ultralytics). conf_floor hanya "
                    "batas bawah kurva PR; laporkan mAP pada conf_floor rendah."),
        "sapuan": hasil, "map50_tertinggi": terbaik, "titik_f1_optimal": puncak_f1,
    }, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Artefak: {keluar.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
