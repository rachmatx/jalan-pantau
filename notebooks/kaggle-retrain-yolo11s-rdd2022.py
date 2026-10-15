# -*- coding: utf-8 -*-
"""
Retrain YOLOv11s — RDD2022 (+ evaluasi OOD BPID Bandung)
Target: Kaggle, GPU T4 (free plan, kuota 30 jam), Ultralytics.

Strategi (disepakati 16 Okt 2026):
- Train : RDD2022 split (aliabdelmenam) — train/
- Val   : RDD2022 split — val/
- Test  : RDD2022 split — test/  +  BPID Bandung (OOD, 161 foto pothole)
- BPID TIDAK masuk training (aset klaim generalisasi paper).
- Model : yolo11s.pt (COCO pretrained), 150 epoch, patience 20,
          SGD lr0=0.01 momentum 0.937, imgsz 640, batch 16, close_mosaic=10.

Cara pakai: upload / copy-paste sel per sel ke Kaggle Notebook (GPU T4 ON),
lalu jalankan berurutan. Output (best.pt, onnx) ada di /kaggle/working —
download manual sebelum sesi berakhir.
"""

# ============================================================
# Sel 1 — setup
# ============================================================
# !pip install -q ultralytics

import torch
print("CUDA:", torch.cuda.is_available(), "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-")

# ============================================================
# Sel 2 — path dataset (read-only, jangan diubah)
# ============================================================
RDD  = "/kaggle/input/datasets/aliabdelmenam/rdd-2022/RDD_SPLIT"
BPID = "/kaggle/input/datasets/arkv99/bpid-test"

NAMES = ['longitudinal crack', 'transverse crack', 'alligator crack',
         'other corruption', 'Pothole']   # 0..4, sesuai deskripsi dataset
# Catatan: BPID memakai id 0 = Pothole -> diremap ke 4 (standar repo) di Sel 3.

# ============================================================
# Sel 3 — sanity check dataset
# ============================================================
from pathlib import Path
from collections import Counter

def cek_split(img_dir, lbl_dir, nama):
    imgs = list(Path(img_dir).glob("*.*"))
    lbls = list(Path(lbl_dir).glob("*.txt"))
    cls = Counter()
    for l in lbls:
        for line in l.read_text().splitlines():
            p = line.split()
            if p:
                cls[p[0]] += 1
    print(f"{nama}: {len(imgs)} gambar, {len(lbls)} label, sebaran kelas {dict(cls)}")

cek_split(f"{RDD}/train/images", f"{RDD}/train/labels", "RDD train")
cek_split(f"{RDD}/val/images",   f"{RDD}/val/labels",   "RDD val")
cek_split(f"{RDD}/test/images",  f"{RDD}/test/labels",  "RDD test")
cek_split(f"{BPID}/images",      f"{BPID}/labels",      "BPID (OOD)")

# ============================================================
# Sel 4 — siapkan label BPID terrema p (0 -> 4) di working dir
# (input Kaggle read-only, jadi disalin ke /kaggle/working)
# ============================================================
import shutil

work = Path("/kaggle/working/bpid_eval")
shutil.rmtree(work, ignore_errors=True)
(work / "images").mkdir(parents=True)
(work / "labels").mkdir(parents=True)

for img in (Path(BPID) / "images").glob("*"):
    (work / "images" / img.name).symlink_to(img)          # symlink hemat ruang
n = 0
for lbl in (Path(BPID) / "labels").glob("*.txt"):
    out = []
    for line in lbl.read_text().splitlines():
        p = line.split()
        if p and p[0] == "0":
            p[0] = "4"                                     # pothole -> id 4
        out.append(" ".join(p))
    (work / "labels" / lbl.name).write_text("\n".join(out) + "\n")
    n += 1
print(f"BPID siap: {n} label diremap, gambar via symlink")

# ============================================================
# Sel 5 — data.yaml
# ============================================================
rdd_yaml = f"""path: {RDD}
train: train/images
val: val/images
test: test/images
nc: 5
names: {NAMES}
"""
Path("/kaggle/working/rdd2022.yaml").write_text(rdd_yaml)

bpid_yaml = f"""path: /kaggle/working/bpid_eval
train: images
val: images
nc: 5
names: {NAMES}
"""
Path("/kaggle/working/bpid.yaml").write_text(bpid_yaml)
print("yaml ok")

# ============================================================
# Sel 6 — TRAINING (ini yang lama; biarkan jalan)
# ============================================================
from ultralytics import YOLO

model = YOLO("yolo11s.pt")          # COCO pretrained (resep standar paper)
model.train(
    data="/kaggle/working/rdd2022.yaml",
    epochs=150,                     # disepakati: muat kuota T4
    patience=20,                    # early stop bila 20 epoch tanpa peningkatan
    imgsz=640,
    batch=16,                       # aman untuk T4 16GB
    optimizer="SGD",
    lr0=0.01,
    momentum=0.937,
    weight_decay=0.0005,
    close_mosaic=10,                # matikan mosaic 10 epoch terakhir
    workers=4,
    seed=42,
    project="/kaggle/working/runs",
    name="yolo11s_rdd2022_150ep",
    exist_ok=True,
    verbose=True,
)

# ============================================================
# Sel 7 — evaluasi: RDD test + BPID Bandung (OOD)
# ============================================================
best = "/kaggle/working/runs/yolo11s_rdd2022_150ep/weights/best.pt"
m = YOLO(best)

print("===== RDD2022 test split =====")
rdd_test = m.val(data="/kaggle/working/rdd2022.yaml", split="test")

print("===== BPID Bandung (OOD, tak pernah dilihat saat training) =====")
bpid_test = m.val(data="/kaggle/working/bpid.yaml")

# ============================================================
# Sel 8 — export ONNX (untuk aplikasi Flask)
# ============================================================
m.export(format="onnx", imgsz=640, simplify=True)
print("Selesai. Download dari /kaggle/working/runs/yolo11s_rdd2022_150ep/weights/:")
print("  - best.pt   -> ganti app/weights/best_yolo11s.pt")
print("  - best.onnx -> ganti app/weights/best.onnx")
