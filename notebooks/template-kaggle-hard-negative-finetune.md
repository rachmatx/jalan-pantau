# Training lanjutan di Kaggle — hard-negative + fine-tune + pseudo-label (YOLOv11)

Lanjutan dari `template-kaggle-yolo11-detect.md`. Fokus menaikkan mAP50 & OOD
sesuai `docs/Panduan-Tuning-Model.md`. Jalankan sel berurutan.

Asumsi: Anda sudah punya dataset RDD-subset ter-*merge* dari template lama
(atau sesuaikan path). Kelas standar repo:
`0 longitudinal_crack, 1 transverse_crack, 2 alligator_crack, 3 other_corruption, 4 pothole`.

```python
# Sel 1: setup + GPU
!pip install -q ultralytics
import torch, shutil, random
from pathlib import Path
from collections import Counter
print(torch.cuda.is_available(), torch.cuda.get_device_name(0))
```

```python
# Sel 2: siapkan struktur kerja (images/labels train-val-test)
# Ganti 'merged' dengan dataset dasar Anda bila berbeda.
WORK = Path("/kaggle/working/data"); 
for split in ("train", "val", "test"):
    (WORK/split/"images").mkdir(parents=True, exist_ok=True)
    (WORK/split/"labels").mkdir(parents=True, exist_ok=True)
print("struktur siap:", WORK)
```

```python
# Sel 3: HARD-NEGATIVE MINING — tambah gambar background (label kosong: .txt kosong)
# Sumber: upload folder 'negatives' (aspal baik, marka, bayangan, non-kerusakan).
NEG = Path("/kaggle/input/negatives")          # SESUAIKAN
n_neg = 0
if NEG.exists():
    for p in list(NEG.glob("*.jpg")) + list(NEG.glob("*.png")) + list(NEG.glob("*.jpeg")):
        shutil.copy(p, WORK/"train"/"images"/p.name)
        (WORK/"train"/"labels"/(p.stem + ".txt")).write_text("")   # kosong = background
        n_neg += 1
print("background ditambahkan:", n_neg)
```

```python
# Sel 4: tulis data.yaml (5 kelas)
yaml_txt = f"""path: {WORK}
train: train/images
val: val/images
test: test/images
names:
  0: longitudinal_crack
  1: transverse_crack
  2: alligator_crack
  3: other_corruption
  4: pothole
"""
(WORK/"data.yaml").write_text(yaml_txt)
print(yaml_txt)
```

```python
# Sel 5: FINE-TUNE dari bobot terbaik (bukan yolo11n.pt) dengan hyperparameter rekomendasi
from ultralytics import YOLO
model = YOLO("/kaggle/input/jalanpantau-weights/best_yolo11s.pt")  # SESUAIKAN
model.train(
    data=str(WORK/"data.yaml"),
    epochs=120, imgsz=960, batch=8, patience=25,
    optimizer="AdamW", lr0=0.001, cos_lr=True, warmup_epochs=3,
    label_smoothing=0.05, weight_decay=0.0005, copy_paste=0.3,
    close_mosaic=15, seed=42,
    project="/kaggle/working/runs", name="finetune-hardneg",
)
```

```python
# Sel 6: PSEUDO-LABELING (opsional, 1 putaran)
# 1) Prediksi pada foto lokal tanpa label (conf tinggi), 2) verifikasi manual,
# 3) masukkan sebagai label, 4) latih ulang. Contoh pembuatan pseudo-label:
from ultralytics import YOLO
best = YOLO("/kaggle/working/runs/finetune-hardneg/weights/best.pt")
UNLABELED = Path("/kaggle/input/lokal-unlabeled")   # SESUAIKAN
for p in UNLABELED.glob("*.jpg"):
    r = best.predict(str(p), conf=0.5, imgsz=960, verbose=False)[0]
    lines = []
    for b in r.boxes:
        c, xywhn = int(b.cls), b.xywhn[0].tolist()
        lines.append(f"{c} {xywhn[0]:.6f} {xywhn[1]:.6f} {xywhn[2]:.6f} {xywhn[3]:.6f}")
    # >>> VERIFIKASI MANUAL sebelum dipakai latih ulang <<<
    (WORK/"train"/"labels"/(p.stem + ".txt")).write_text("\n".join(lines))
print("pseudo-label dibuat — WAJIB diverifikasi manual sebelum retrain")
```

```python
# Sel 7: EVALUASI protokol — per-kelas + test full + OOD + simpan results.csv
best = YOLO("/kaggle/working/runs/finetune-hardneg/weights/best.pt")
m = best.val(data=str(WORK/"data.yaml"), split="test", imgsz=960, plots=True)
print("TEST mAP50:", m.box.map50, "mAP50-95:", m.box.map)
print("per-kelas mAP50-95:", dict(zip(m.box.ap_class_index.tolist(), m.box.maps.tolist())))
# Salin results.csv run ke artifacts/ repo sebagai bukti provenance.
shutil.copy("/kaggle/working/runs/finetune-hardneg/results.csv", "/kaggle/working/results.csv")
```

```python
# Sel 8: export ONNX (dinamis) untuk inferensi CPU
best.export(format="onnx", imgsz=960, dynamic=True)
# Download: best.pt, best.onnx, results.csv, confusion_matrix.png, PR/F1 curves
```

## Checklist eksperimen (untuk jurnal)
- [ ] Baseline vs +hard-negative (efek pada false alarm & mAP)
- [ ] Baseline vs +data lokal (efek pada OOD Bandung)
- [ ] Baseline vs +pseudo-label (efek pada mAP, dengan set uji bersih)
- [ ] 3 seed → mean ± simpangan baku
- [ ] Per-kelas mAP50-95 dilaporkan apa adanya
- [ ] Artefak `results.csv` disimpan di `artifacts/`
