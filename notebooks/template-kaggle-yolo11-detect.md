# Training di Kaggle (T4/P100) — RDD2022 deteksi, YOLOv11n

Dataset: Kaggle Input `aliabdelmenam/rdd-2022` (tambah via + Add Input, TANPA download)
+ RDDC2024-ID (upload sebagai Kaggle private dataset setelah remap) + foto lokal.
Dataset RDD2022 TIDAK menyertakan data.yaml → pakai `data/dataset-rdd2022.yaml` dari repo ini
(urutan kelas sudah dikonfirmasi dari Data Card: 0 longitudinal, 1 transverse, 2 alligator,
3 other_corruption, 4 pothole).
Model: YOLOv11n DETEKSI (`yolo11n.pt`), bukan `-seg`, karena label box-only.
Strategi data: lihat `docs/Strategi-Subset-5k.md` (train 5k + 5k + lokal, test full).

```python
# Sel 1: install + cek GPU
!pip install -q ultralytics
import torch
print(torch.cuda.is_available(), torch.cuda.get_device_name(0))
```

```python
# Sel 2: verifikasi label RDD2022 (wajib, 2 menit)
from pathlib import Path
import random
base = Path("/kaggle/input/rdd-2022/RDD_SPLIT")  # SESUAIKAN path aktual
imgs = list((base/"train/images").glob("*.jpg"))
print("train images:", len(imgs))
for p in random.sample(imgs, 20):
    t = base/"train/labels"/(p.stem + ".txt")
    rows = [l.split() for l in t.read_text().strip().splitlines()]
    assert all(len(r) == 5 for r in rows), t
    assert all(0 <= float(v) <= 1 for r in rows for v in r[1:]), t
print("label OK")
from collections import Counter
c = Counter()
for t in (base/"train/labels").glob("*.txt"):
    for l in t.read_text().strip().splitlines():
        c[int(l.split()[0])] += 1
print("distribusi kelas:", dict(sorted(c.items())))
```

```python
# Sel 3: stratified subset 8k RDD2022 (seed 42, minority floor, exclude Norway)
# Stratifikasi per signature kelas + top-up kelas minoritas. Simpan daftar file.
import shutil
from collections import defaultdict
SEED, TARGET = 42, 8000
random.seed(SEED)
src_i, src_l = base/"train/images", base/"train/labels"
KEEP_PREFIX = ("India_", "China_MotorBike_", "Japan_")  # relevan untuk Indonesia; cek prefix aktual dulu
pool = [p for p in src_i.glob("*.jpg") if p.name.startswith(KEEP_PREFIX)]
print("pool relevan:", len(pool))
def sig(p):
    t = src_l/(p.stem + ".txt")
    return tuple(sorted({int(l.split()[0]) for l in t.read_text().strip().splitlines()})) if t.exists() else ()
buckets = defaultdict(list)
for p in pool:
    buckets[sig(p)].append(p)
sel, quota = [], TARGET // max(len(buckets), 1)
for k, v in buckets.items():
    random.shuffle(v)
    sel += v[:max(quota, 1)]
random.shuffle(pool)
for p in pool:  # penuhi sisa tanpa duplikat
    if len(sel) >= TARGET:
        break
    if p not in sel:
        sel.append(p)
sel = sel[:TARGET]
dst = Path("/kaggle/working/subset_rdd"); (dst/"images").mkdir(parents=True, exist_ok=True); (dst/"labels").mkdir(parents=True, exist_ok=True)
for p in sel:
    shutil.copy(p, dst/"images"/p.name)
    q = src_l/(p.stem + ".txt")
    if q.exists():
        shutil.copy(q, dst/"labels"/q.name)
(dst/"subset_files.txt").write_text("\n".join(sorted(p.name for p in sel)))
print("subset:", len(sel))
```

```python
# Sel 3b: remap Roma 3 kelas -> standar repo (ambil SEMUA 2.009 gambar)
# 0 pothole -> 4 | 1 crack -> 1 (kasar, catat di keterbatasan) | 2 manhole -> 3
# Pastikan ambil folder label box 5 kolom (labels-YOLO), bukan polygon.
REMAP_ROMA = {"0": "4", "1": "1", "2": "3"}
roma_i = Path("/kaggle/input/roma/images")  # SESUAIKAN path
roma_l = Path("/kaggle/input/roma/labels-YOLO")  # SESUAIKAN: pilih folder 5-kolom
outs = Path("/kaggle/working/subset_roma"); (outs/"images").mkdir(parents=True, exist_ok=True); (outs/"labels").mkdir(parents=True, exist_ok=True)
n = 0
for p in list(roma_i.glob("*.jpg")) + list(roma_i.glob("*.jpeg")) + list(roma_i.glob("*.png")):
    t = roma_l/(p.stem + ".txt")
    if not t.exists():
        continue
    shutil.copy(p, outs/"images"/p.name)
    lines = []
    for l in t.read_text().strip().splitlines():
        s = l.split(); s[0] = REMAP_ROMA[s[0]]; lines.append(" ".join(s))
    (outs/"labels"/t.name).write_text("\n".join(lines))
    n += 1
print("subset roma:", n)
# Gabung subset_rdd + subset_roma -> merged (lihat Sel 6)
```

```python
# Sel 4: latih YOLOv11n (utama)
from ultralytics import YOLO
model = YOLO("yolo11n.pt")
model.train(
    data="/kaggle/working/merged.yaml",  # path train/val merged
    epochs=100,
    imgsz=640,
    batch=16,
    patience=20,  # early stopping hemat kuota
    project="/kaggle/working/runs",
    name="yolo11n-jalan",
)
```

```python
# Sel 5: latih YOLOv8n (pembanding jurnal)
model8 = YOLO("yolov8n.pt")
model8.train(
    data="/kaggle/working/merged.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    patience=20,
    project="/kaggle/working/runs",
    name="yolov8n-jalan",
)
```

```python
# Sel 6: evaluasi di test FULL (murah, jangan dibatasi) + export
m11 = YOLO("/kaggle/working/runs/yolo11n-jalan/weights/best.pt")
print("test RDD:", m11.val(data="/kaggle/working/merged.yaml", split="test"))

# Sel 6b: evaluasi OOD BPID Bandung (upload folder bpid/ ke Kaggle). BPID id 0 = pothole,
# standar repo id 4 = pothole -> remap pada SALINAN, lalu val dengan yaml 5 kelas yang sama.
from pathlib import Path
bpid = Path("/kaggle/input/bpid-bandung")  # SESUAIKAN: berisi test/images + test/labels
out = Path("/kaggle/working/bpid_eval"); (out/"images").mkdir(parents=True, exist_ok=True); (out/"labels").mkdir(parents=True, exist_ok=True)
import shutil
for p in (bpid/"test/images").glob("*"):
    shutil.copy(p, out/"images"/p.name)
for t in (bpid/"test/labels").glob("*.txt"):
    lines = []
    for l in t.read_text().strip().splitlines():
        s = l.split(); s[0] = "4"; lines.append(" ".join(s))  # 0 (BPID pothole) -> 4 (standar repo)
    (out/"labels"/t.name).write_text("\n".join(lines))
print("OOD Bandung:", m11.val(data="/kaggle/working/merged.yaml", imgsz=640))  # arahkan split/path ke bpid_eval
# Catat mAP drop (RDD test vs Bandung) sebagai bahan analisis generalisasi di jurnal.

m11.export(format="onnx")  # untuk inferensi CPU i5
# Download: best.pt + best.onnx + confusion_matrix.png + results.csv + subset_files.txt
```

Eksperimen wajib untuk jurnal:
1. v11n vs v8n (mAP50, mAP50-95, Precision, Recall, FPS)
2. RDD saja vs RDD + Roma-remap (uji kontribusi data tambahan; foto lokal menyusul)
3. mAP per test set (RDD test vs BPID Bandung vs lokal) = analisis generalisasi
