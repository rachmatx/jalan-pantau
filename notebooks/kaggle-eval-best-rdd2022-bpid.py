# -*- coding: utf-8 -*-
"""
Evaluasi best.pt hasil retrain — RDD2022 test + BPID Bandung (OOD) + export ONNX.
Dipakai SETELAH training selesai/terhenti (terpisah dari notebook training).

Cara pakai:
  1. Download best.pt dari tab Output Version training.
  2. Buat notebook Kaggle baru (GPU T4 disarankan; BPID saja bisa CPU).
  3. Via "Add Input": (a) upload best.pt tadi, (b) dataset aliabdelmenam/rdd-2022,
     (c) dataset arkv99/bpid-test. (Alternatif: attach output notebook training.)
  4. Copy-paste sel per sel, jalankan berurutan.
"""

# ============================================================
# Sel 1 — setup
# ============================================================
import importlib, subprocess, sys

if importlib.util.find_spec("ultralytics") is None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ultralytics"])

from pathlib import Path
print("setup ok")

# ============================================================
# Sel 2 — path (otomatis cari best.pt di /kaggle/input)
# ============================================================
cands = list(Path("/kaggle/input").rglob("best.pt"))
print("kandidat best.pt:", [str(c) for c in cands])
BEST = str(cands[0]) if cands else None
assert BEST, "best.pt tidak ditemukan di /kaggle/input — tambahkan via Add Input dulu"

RDD   = "/kaggle/input/datasets/aliabdelmenam/rdd-2022/RDD_SPLIT"
BPID  = "/kaggle/input/datasets/arkv99/bpid-test"
NAMES = ['longitudinal crack', 'transverse crack', 'alligator crack',
         'other corruption', 'Pothole']

# ============================================================
# Sel 3 — remap label BPID (0 -> 4) ke working dir
# ============================================================
import shutil

work = Path("/kaggle/working/bpid_eval")
shutil.rmtree(work, ignore_errors=True)
(work / "images").mkdir(parents=True)
(work / "labels").mkdir(parents=True)

for img in (Path(BPID) / "images").glob("*"):
    (work / "images" / img.name).symlink_to(img)
n = 0
for lbl in (Path(BPID) / "labels").glob("*.txt"):
    out = []
    for line in lbl.read_text().splitlines():
        p = line.split()
        if p and p[0] == "0":
            p[0] = "4"
        out.append(" ".join(p))
    (work / "labels" / lbl.name).write_text("\n".join(out) + "\n")
    n += 1
print(f"BPID siap: {n} label diremap")

# ============================================================
# Sel 4 — data.yaml
# ============================================================
Path("/kaggle/working/rdd2022.yaml").write_text(f"""path: {RDD}
train: train/images
val: val/images
test: test/images
nc: 5
names: {NAMES}
""")
Path("/kaggle/working/bpid.yaml").write_text(f"""path: /kaggle/working/bpid_eval
train: images
val: images
nc: 5
names: {NAMES}
""")
print("yaml ok")

# ============================================================
# Sel 5 — evaluasi ganda
# ============================================================
from ultralytics import YOLO

m = YOLO(BEST)
print("model:", BEST)

print("\n===== RDD2022 test split =====")
m.val(data="/kaggle/working/rdd2022.yaml", split="test")

print("\n===== BPID Bandung (OOD) =====")
m.val(data="/kaggle/working/bpid.yaml")

# ============================================================
# Sel 5b — visualisasi untuk paper (jalankan SEBELUM Sel 6)
# Mengumpulkan plot val + contoh prediksi + grafik AP50 per kelas.
# Semua disimpan di /kaggle/working/hasil-eval/visual/ (otomatis ikut zip).
# ============================================================
import random
import shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

vis_dir = Path("/kaggle/working/hasil-eval/visual")
vis_dir.mkdir(parents=True, exist_ok=True)

# --- 1) kumpulkan plot bawaan val (confusion matrix, kurva PR/F1/P/R) ---
n_plot = 0
for png in list(Path("/kaggle/working").rglob("confusion_matrix*.png")) + \
           list(Path("/kaggle/working").rglob("*_curve.png")):
    if "hasil-eval" in str(png):
        continue
    tag = "bpid" if "bpid" in str(png).lower() else "rdd"
    dst = vis_dir / f"{tag}_{png.name}"
    if not dst.exists():
        shutil.copy(png, dst)
        n_plot += 1
print(f"plot val terkumpul: {n_plot} file")

# --- 2) contoh prediksi (8 citra test, untuk gambar paper) ---
pred_dir = vis_dir / "prediksi_contoh"
pred_dir.mkdir(exist_ok=True)
test_imgs = sorted((Path(RDD) / "test" / "images").glob("*.*"))
sampel = test_imgs[::max(1, len(test_imgs) // 8)][:8]
res = m.predict([str(p) for p in sampel], imgsz=640, conf=0.25, verbose=False)
for r, img in zip(res, sampel):
    r.save(filename=str(pred_dir / f"pred_{img.stem}.jpg"))
print(f"contoh prediksi: {len(list(pred_dir.glob('*.jpg')))} gambar")

# --- 3) grafik AP50 per kelas (subset 600 citra, cepat) ---
sub_dir = Path("/kaggle/working/subset_eval")
shutil.rmtree(sub_dir, ignore_errors=True)
(sub_dir / "images").mkdir(parents=True)
(sub_dir / "labels").mkdir(parents=True)
random.seed(7)
for img in random.sample(test_imgs, min(600, len(test_imgs))):
    (sub_dir / "images" / img.name).symlink_to(img)
    lbl = Path(RDD) / "test" / "labels" / (img.stem + ".txt")
    if lbl.exists():
        (sub_dir / "labels" / lbl.name).symlink_to(lbl)

sub_yaml = Path("/kaggle/working/subset.yaml")
sub_yaml.write_text(f"""path: {sub_dir}
train: images
val: images
nc: 5
names: {NAMES}
""")
sub_res = m.val(data=str(sub_yaml), verbose=False)
ap50 = np.array(sub_res.box.maps)  # AP50 per kelas
plt.figure(figsize=(9, 4.5))
bars = plt.bar(NAMES, ap50)
plt.ylim(0, 1)
plt.ylabel("AP50")
plt.title("AP50 per kelas (subset 600 citra test RDD2022)")
for b, v in zip(bars, ap50):
    plt.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.3f}",
             ha="center", fontsize=9)
plt.tight_layout()
plt.savefig(vis_dir / "ap50_per_kelas_subset.png", dpi=150)
plt.close()
print("AP50 per kelas:", {n: round(float(v), 3) for n, v in zip(NAMES, ap50)})

# --- 4) ringkasan metrik (txt) ---
(vis_dir / "ringkasan_metrik.txt").write_text(
    "RINGKASAN METRIK (YOLOv11s retrain RDD2022)\n"
    "==========================================\n"
    "Subset 600 citra test — AP50 per kelas: "
    + ", ".join(f"{n}={v:.3f}" for n, v in zip(NAMES, ap50)) + "\n"
    f"Subset mAP50: {float(np.mean(ap50)):.4f}\n"
    "Angka final (full test 5758 citra + BPID): lihat output Sel 5.\n"
)
print("visual selesai ->", vis_dir)

# ============================================================
# Sel 6 — export ONNX + zip SEMUA file penting untuk diunduh
# (best.pt asli di /kaggle/input read-only -> disalin ke working dulu)
# ============================================================
import shutil
import zipfile

best_work = Path("/kaggle/working/best_eval.pt")
if not best_work.exists():
    shutil.copy(BEST, best_work)
    print(f"disalin: {BEST} -> {best_work}")

m2 = YOLO(str(best_work))
m2.export(format="onnx", imgsz=640, dynamic=True, simplify=True)
onnx_path = best_work.with_suffix(".onnx")
print("ONNX:", onnx_path, "ada:", onnx_path.exists())

# kumpulkan semua file penting ke satu folder (nama siap pakai di aplikasi)
run_out = Path("/kaggle/working/hasil-eval")
run_out.mkdir(exist_ok=True)
if best_work.exists():
    shutil.copy(best_work, run_out / "best.pt")          # -> app/weights/best.pt
if onnx_path.exists():
    shutil.copy(onnx_path, run_out / "best.onnx")        # -> app/weights/best.onnx
for y in ["rdd2022.yaml", "bpid.yaml", "subset.yaml"]:
    yf = Path("/kaggle/working") / y
    if yf.exists():
        shutil.copy(yf, run_out / yf.name)
# (folder visual/ dari Sel 5b sudah di dalam hasil-eval/)

zip_path = Path("/kaggle/working/hasil-eval-rdd2022-bpid.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(run_out.rglob("*")):
        if f.is_file():
            z.write(f, f.relative_to(run_out.parent))
print(f"\nZIP: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB)")
print("Isi zip:")
for f in sorted(run_out.rglob("*")):
    if f.is_file():
        print("  -", f.relative_to(run_out))
print("Download dari tab Output.")
