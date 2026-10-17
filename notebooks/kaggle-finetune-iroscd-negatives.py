# -*- coding: utf-8 -*-
# PERINGATAN (17 Okt 2026): JANGAN jalankan script ini apa adanya — user menemukan
# label noise di IROSCD: ada foto berkerusakan kecil di normal_road, dan foto jalan
# rusak di wet_road. Memakai keduanya sebagai background images akan meracuni model
# (detektor belajar "kerusakan kecil = bukan kerusakan" dan "kerusakan di jalan
# basah = bukan kerusakan"). Lihat MEMORY.md untuk jalur pengganti yang disepakati.
#
"""
Fine-tune YOLOv11s — hard negatives dari IROSCD (Indonesia Road Surface
Classification Dataset, Mendeley Data, CC BY 4.0).

Latar belakang: IROSCD adalah dataset KLASIFIKASI (label per gambar, tanpa
bounding box) sehingga TIDAK bisa dipakai langsung untuk melatih detektor.
Yang dipakai: foto `wet_road` + `normal_road` sebagai BACKGROUND IMAGES
(label .txt kosong) — cara resmi Ultralytics menekan false positive
(direkomendasikan 0-10% dari data latih). Kasus nyata: deteksi "pothole 0.41"
pada bercak air jalan basah.

Strategi (disepakati pola retrain 16 Okt 2026):
- Basis : best.pt YOLOv11s RDD2022 (mAP50 test 0,617) — FINE-TUNE, bukan dari nol
- Tambahan train: IROSCD train/wet_road + train/normal_road (~1.000 gambar,
  ~4% dari 26.900 gambar latih RDD2022) sebagai background
- damaged_road TIDAK dipakai (ada kerusakan tapi tanpa box -> butuh
  pseudo-label + verifikasi manual; di luar scope sekarang)
- bumpy_road TIDAK dipakai (di luar 5 kelas repo)
- Val : RDD2022 val (cek tidak ada regresi)
- Test : RDD2022 test + IROSCD test/wet_road (hitung FP sebelum vs sesudah)
- Konfig: 30 epoch, patience 10, lr0=0.001 (kecil karena fine-tune),
  SGD momentum 0.937, imgsz 640 (keputusan: tetap 640), batch 16

Cara pakai:
1. Upload IROSCD ke Kaggle sebagai dataset (mis. nama: iroscd), 2,29 GB.
2. Upload best.pt (YOLOv11s RDD2022) sebagai dataset Kaggle (mis. jalanpantau-weights).
3. Copy-paste sel per sel ke Kaggle Notebook (GPU T4 ON), "Save & Run All".
4. Download best.pt + best.onnx + results.csv dari tab Output.

Catatan Kaggle: /kaggle/input read-only — salin best.pt ke /kaggle/working
SEBELUM export ONNX (OSError 30 bila dari /kaggle/input).
"""

# ============================================================
# Sel 1 — setup
# ============================================================
import importlib, subprocess, sys

if importlib.util.find_spec("ultralytics") is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ultralytics"])

import torch
print("ultralytics ok | CUDA:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "-")

# ============================================================
# Sel 2 — path dataset + sanity check
# ============================================================
from pathlib import Path
from collections import Counter

RDD = "/kaggle/input/datasets/aliabdelmenam/rdd-2022/RDD_SPLIT"
IRO = "/kaggle/input/iroscd/IROSCD"          # SESUAIKAN dengan nama dataset Kaggle
BOBOT = "/kaggle/input/jalanpantau-weights/best.pt"  # SESUAIKAN

for split in ("train", "val", "test"):
    for kelas in ("Bumpy_Road", "Damaged_Road", "Normal_Road", "Wet_Road"):
        d = Path(IRO) / split / kelas
        n = len(list(d.glob("*.jpg"))) if d.exists() else -1
        print(f"IROSCD {split}/{kelas}: {n} gambar")

# ============================================================
# Sel 3 — siapkan background images (wet + normal, label kosong)
# ============================================================
import shutil

NEG_IMG = Path("/kaggle/working/neg/images")
NEG_LBL = Path("/kaggle/working/neg/labels")
NEG_IMG.mkdir(parents=True, exist_ok=True)
NEG_LBL.mkdir(parents=True, exist_ok=True)

n_neg = 0
for kelas in ("Wet_Road", "Normal_Road"):
    for p in (Path(IRO) / "train" / kelas).glob("*.jpg"):
        shutil.copy(p, NEG_IMG / p.name)
        (NEG_LBL / (p.stem + ".txt")).write_text("")  # kosong = background
        n_neg += 1
print("background ditambahkan:", n_neg)

# ============================================================
# Sel 4 — data.yaml (RDD2022 + folder negatives sebagai 2 sumber train)
# ============================================================
WORK = Path("/kaggle/working")
yaml_txt = f"""path: {RDD}
train:
- {RDD}/train/images
- {WORK}/neg/images
val: {RDD}/val/images
test: {RDD}/test/images
names:
  0: longitudinal_crack
  1: transverse_crack
  2: alligator_crack
  3: other_corruption
  4: pothole
"""
(WORK / "data_ft.yaml").write_text(yaml_txt)
print(yaml_txt)
# Ultralytics memetakan tiap folder images -> sibling folder labels secara otomatis.

# ============================================================
# Sel 5 — FINE-TUNE dari best.pt (lr kecil, epoch pendek)
# ============================================================
from ultralytics import YOLO

model = YOLO(BOBOT)
model.train(
    data=str(WORK / "data_ft.yaml"),
    epochs=30, patience=10,
    imgsz=640, batch=16,
    optimizer="SGD", lr0=0.001, momentum=0.937,
    warmup_epochs=3, close_mosaic=10, seed=42,
    project="/kaggle/working/runs", name="ft-iroscd-neg",
)

# ============================================================
# Sel 6 — evaluasi: (a) regresi RDD2022, (b) FP di IROSCD wet_road
# ============================================================
FT = "/kaggle/working/runs/ft-iroscd-neg/weights/best.pt"

def hitung_fp(weights, img_dir, conf=0.25):
    """Hitung total deteksi pada gambar yang seharusnya bersih (proxy FP)."""
    m = YOLO(weights)
    n_det = 0
    n_img = 0
    for p in sorted(Path(img_dir).glob("*.jpg")):
        r = m.predict(str(p), conf=conf, imgsz=640, verbose=False)[0]
        n_det += len(r.boxes)
        n_img += 1
    return n_img, n_det

# (a) pastikan tidak ada regresi di test RDD2022
mft = YOLO(FT)
met = mft.val(data=str(WORK / "data_ft.yaml"), split="test", imgsz=640)
print(f"RDD2022 test  FT  : mAP50={met.box.map50:.4f} mAP50-95={met.box.map:.4f}")

m0 = YOLO(BOBOT)
met0 = m0.val(data=str(WORK / "data_ft.yaml"), split="test", imgsz=640)
print(f"RDD2022 test BASE : mAP50={met0.box.map50:.4f} mAP50-95={met0.box.map:.4f}")

# (b) FP pada wet_road Indonesia (sebelum vs sesudah) — metrik kunci jurnal
wet_test = str(Path(IRO) / "test" / "Wet_Road")
i0, d0 = hitung_fp(BOBOT, wet_test)
i1, d1 = hitung_fp(FT, wet_test)
print(f"Wet_Road test: {i0} gambar")
print(f"  baseline : {d0} deteksi ({d0/i0:.2f} per gambar)")
print(f"  fine-tune: {d1} deteksi ({d1/i1:.2f} per gambar)")
print(f"  penurunan FP: {(d0-d1)/max(d0,1)*100:.1f}%")

# ============================================================
# Sel 7 — export ONNX (dari /kaggle/working, BUKAN /kaggle/input)
# ============================================================
shutil.copy(FT, "/kaggle/working/best_ft.pt")
mft = YOLO("/kaggle/working/best_ft.pt")  # reload dari working (read-write)
mft.export(format="onnx", imgsz=640, dynamic=True)
print("ONNX tersimpan di /kaggle/working/runs/ft-iroscd-neg/weights/best.onnx")
# Download: best_ft.pt, best.onnx, results.csv (runs/ft-iroscd-neg/)
