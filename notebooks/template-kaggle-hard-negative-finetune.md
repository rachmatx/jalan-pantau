# Training lanjutan di Kaggle — hard-negative + fine-tune + pseudo-label (YOLOv11)

Lanjutan dari `template-kaggle-yolo11-detect.md`. Fokus menaikkan mAP50 & OOD
sesuai `docs/Panduan-Tuning-Model.md`. Jalankan sel berurutan.

> **Baca dulu `docs/Fine-tuning-Lokal.md`** — di situ diagnosisnya (pola FP =
> genangan air), daftar kandidat hard-negative, dan **aturan terima** model baru.
> Dua koreksi hasil ukur 18 Okt 2026 yang sudah diterapkan di template ini:
> 1. **Hard-negative tidak boleh dilabel kosong secara otomatis.** Audit 137
>    gambar negatif lokal: 14 di antaranya ditandainya model (conf sampai 0,80)
>    dan mayoritas memang berisi genangan air → itu **kerusakan nyata**, bukan
>    negatif. Label kosong otomatis melatih model membutakan diri sendiri.
> 2. **Skala latih 768, skala inferensi 640.** Training tetap 768 (sama seperti
>    `args.rekonstruksi.yaml`) supaya perbandingannya bersih; inferensi dan
>    evaluasi memakai **640** karena di 640 F1 pothole 0,630 vs 0,536 pada 960
>    (161 gambar BPID berlabel, `Panduan-Tuning-Model.md` §6d).

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
# Sel 3: HARD-NEGATIVE MINING — background, TAPI SETELAH DIVERIFIKASI MANUAL
# Sumber: folder 'negatives' (aspal baik, marka, bayangan, non-kerusakan).
#
# WAJIB: jangan langsung dilabel kosong. Di mesin lokal, audit 137 gambar
# negatif menemukan 14 yang justru ditandainya model dengan conf sampai 0,80,
# dan sebagian besar berisi GENANGAN AIR — itu kerusakan nyata. Gambar seperti
# itu justru paling berharga sebagai data latih (pada label yang benar).
# Verifikasi dengan:  python scripts/pra_label.py --mode audit --sumber <folder>
# lalu: gambar yang ternyata rusak -> pindahkan ke dataset berlabel (dengan label
# yang benar); hanya yang benar-benar bersih yang boleh dapat .txt kosong.
NEG = Path("/kaggle/input/negatives")          # SESUAIKAN
VERIFIED_NEG = Path("/kaggle/input/negatives-verified")   # hasil review manual
n_neg = 0
if VERIFIED_NEG.exists():
    for p in list(VERIFIED_NEG.glob("*.jpg")) + list(VERIFIED_NEG.glob("*.png")) + list(VERIFIED_NEG.glob("*.jpeg")):
        shutil.copy(p, WORK/"train"/"images"/p.name)
        # .txt kosong HANYA untuk gambar yang sudah dikonfirmasi bersih.
        lab = VERIFIED_NEG.parent/(p.stem + ".txt")
        (WORK/"train"/"labels"/(p.stem + ".txt")).write_text(
            lab.read_text(encoding="utf-8") if lab.exists() else "")
        n_neg += 1
print("background terverifikasi ditambahkan:", n_neg)
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
# imgsz=768 SAMA dengan run asal (args.rekonstruksi.yaml) supaya selisihnya murni
# dari data tambahan, bukan dari perubahan skala latih. Inferensi/evaluasi tetap 640.
from ultralytics import YOLO
model = YOLO("/kaggle/input/jalanpantau-weights/best.pt")  # SESUAIKAN
model.train(
    data=str(WORK/"data.yaml"),
    epochs=120, imgsz=768, batch=8, patience=25,
    optimizer="AdamW", lr0=0.001, cos_lr=True, warmup_epochs=3,
    scale=0.5,      # objek lokal lebih dekat dari mobil -> rentang skala lebar
    hsv_v=0.4,      # tahan variasi cahaya lokal (termasuk foto malam)
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
# imgsz=640 = imgsz_gambar aplikasi. Kalau evaluasi memakai 960, angkanya tidak
# sebanding dengan yang pengguna alami (lihat Panduan-Tuning-Model.md §6d).
best = YOLO("/kaggle/working/runs/finetune-hardneg/weights/best.pt")
m = best.val(data=str(WORK/"data.yaml"), split="test", imgsz=640, plots=True)
print("TEST mAP50:", m.box.map50, "mAP50-95:", m.box.map)
print("per-kelas mAP50-95:", dict(zip(m.box.ap_class_index.tolist(), m.box.maps.tolist())))
# Salin results.csv run ke artifacts/ repo sebagai bukti provenance.
shutil.copy("/kaggle/working/runs/finetune-hardneg/results.csv", "/kaggle/working/results.csv")
```

```python
# Sel 7b: GERBANG TERIMA — jangan unduh model sebelum ini lolos.
# Aturan lengkap: docs/Fine-tuning-Lokal.md §6.
#   a) P/R/F1 pothole di BPID test (IoU 0,5, --remap 0:4, imgsz 640) naik >= 0,03
#      ATAU recall turun <= 2 poin sementara FP turun >= 20%;
#   b) tidak ada kelas yang F1-nya turun > 20% relatif di test di atas;
#   c) audit 137 gambar negatif lokal: jumlah gambar yang ditandai turun (14 -> <= 5).
# Jalankan a) & c) di mesin lokal (repo), b) di sini. Kalau gagal: jangan pakai,
# tulis hasil negatifnya di Panduan-Tuning-Model.md §7 — itu bahan skripsi.
print("LALU GERBANG TERIMA? periksa a/b/c sebelum mengunduh bobot.")
```

```python
# Sel 8: export ONNX (dinamis) untuk inferensi CPU — imgsz ikut aplikasi (640)
best.export(format="onnx", imgsz=640, dynamic=True)
# Download: best.pt, best.onnx, results.csv, confusion_matrix.png, PR/F1 curves
```

## Checklist eksperimen (untuk jurnal)
- [ ] Baseline vs +hard-negative **terverifikasi** (efek pada false alarm & mAP)
- [ ] Baseline vs +data lokal (efek pada OOD Bandung)
- [ ] Baseline vs +pseudo-label (efek pada mAP, dengan set uji bersih)
- [ ] Gerbang terima §6 `docs/Fine-tuning-Lokal.md` lolos SEBELUM bobot dipakai
- [ ] 3 seed → mean ± simpangan baku
- [ ] Per-kelas mAP50-95 dilaporkan apa adanya
- [ ] Artefak `results.csv` disimpan di `artifacts/`
