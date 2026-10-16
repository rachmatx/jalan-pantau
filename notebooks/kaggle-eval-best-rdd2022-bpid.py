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
# Sel 6 — export ONNX + zip untuk diunduh
# (best.pt asli di /kaggle/input read-only -> disalin ke working dulu)
# ============================================================
import shutil
import zipfile

best_work = Path("/kaggle/working/best_eval.pt")
if not best_work.exists():
    shutil.copy(BEST, best_work)
    print(f"disalin: {BEST} -> {best_work}")

m2 = YOLO(str(best_work))
m2.export(format="onnx", imgsz=640, simplify=True)
onnx_path = best_work.with_suffix(".onnx")
print("ONNX:", onnx_path, "ada:", onnx_path.exists())

run_out = Path("/kaggle/working/hasil-eval")
run_out.mkdir(exist_ok=True)
for f in [best_work, onnx_path]:
    if f.exists():
        shutil.copy(f, run_out / f.name)

zip_path = Path("/kaggle/working/hasil-eval-rdd2022-bpid.zip")
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(run_out.rglob("*")):
        if f.is_file():
            z.write(f, f.relative_to(run_out.parent))
print(f"ZIP: {zip_path} ({zip_path.stat().st_size / 1e6:.1f} MB) — download dari tab Output")
