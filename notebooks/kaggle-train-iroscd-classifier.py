# -*- coding: utf-8 -*-
"""
FASE 1 — Latih scene classifier IROSCD (YOLOv11n-cls). Ditulis ulang dari nol.

Tujuan: model kecil penjawab "foto ini jalan basah atau bukan?" sebagai gate
di aplikasi: bila scene = wet_road, ambang confidence kelas pothole dinaikkan
sehingga false positive pada bercak air berkurang.

Alur sel (jalankan BERURUTAN):
  Sel 1  — setup. Bila muncul pesan RESTART, restart kernel dulu baru lanjut.
  Sel 2  — cek lokasi & sebaran dataset (otomatis cari level folder yang benar).
  Sel 2b — resize sekali jalan ke maks 640 px. Foto asli 3000x4000 px terlalu
           berat di-decode tiap epoch; untuk klasifikasi imgsz=224, 640 px
           sudah lebih dari cukup. Dilewati otomatis bila sudah ada.
  Sel 3  — latih di GPU. Gagal cepat dengan pesan jelas bila CUDA tak terlihat
           (tidak lagi diam-diam latih di CPU berjam-jam).
  Sel 4  — evaluasi pada TEST split + confusion matrix.
  Sel 5  — uji cepat 3 contoh foto wet_road.

Dataset: IROSCD, Mendeley Data, CC BY 4.0 (wajib sitasi Haryono dkk. 2026),
~2.600 foto jalan Indonesia, 4 kelas. Baseline README: ResNet-50 86,15%,
EfficientNet-B4 90,77%.
"""

# ============================================================
# Sel 1 — setup. Jalankan sel ini sendirian dulu.
# ============================================================
import importlib
import subprocess
import sys

BARU_INSTALL = False
if importlib.util.find_spec("ultralytics") is None:
    print("ultralytics belum ada — menginstal...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "ultralytics"])
    BARU_INSTALL = True

import torch

print("torch:", torch.__version__)
print("cuda :", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu  :", torch.cuda.get_device_name(0))

if BARU_INSTALL:
    print()
    print(">>> PENTING: pilih menu Run > Restart, lalu jalankan ulang dari Sel 1.")
    print("    torch yang baru terinstal hanya aktif setelah kernel direstart.")
    print("    (Melewati ini = training jatuh ke CPU secara diam-diam.)")

# ============================================================
# Sel 2 — lokasi dataset + sanity check sebaran kelas
# ============================================================
from pathlib import Path

_KANDIDAT = [
    Path("/kaggle/input/iroscd/IROSCD"),
    Path("/kaggle/input/datasets/arkv99/iroscd/IROSCD"),
    Path("/kaggle/input/datasets/arkv99/iroscd"),
]
IRO = None
for _k in _KANDIDAT:
    if (_k / "train").is_dir() and (_k / "val").is_dir():
        IRO = _k
        break
assert IRO is not None, (
    "Folder train/val tidak ditemukan. "
    "Tambahkan path dataset-mu ke _KANDIDAT di Sel 2."
)
print("dataset:", IRO)

KELAS = ["Bumpy_Road", "Damaged_Road", "Normal_Road", "Wet_Road"]
for _split in ("train", "val", "test"):
    _total = 0
    for _kl in KELAS:
        _n = len(list((IRO / _split / _kl).glob("*.jpg")))
        _total += _n
        print(f"  {_split}/{_kl}: {_n} gambar")
    print(f"  [{_split}] total: {_total} gambar")

# ============================================================
# Sel 2b — resize sekali jalan (maks 640 px). WAJIB sebelum latih.
# ============================================================
import os
from concurrent.futures import ProcessPoolExecutor

from PIL import Image

IRO_SMALL = Path("/kaggle/working/iro_small")
MAX_SISI = 640


def _resize_one(args):
    src, dst = args
    try:
        im = Image.open(src).convert("RGB")
        im.thumbnail((MAX_SISI, MAX_SISI), Image.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        im.save(dst, "JPEG", quality=90)
        return True
    except Exception:
        return False


if (IRO_SMALL / "train").is_dir():
    print("Folder resize sudah ada — dilewati.")
else:
    _tugas = []
    for _split in ("train", "val", "test"):
        for _kl in KELAS:
            for _p in (IRO / _split / _kl).glob("*.jpg"):
                _tugas.append((_p, IRO_SMALL / _split / _kl / _p.name))
    _w = min(4, os.cpu_count() or 2)
    print(f"Meresize {len(_tugas)} gambar ({_w} worker)...")
    with ProcessPoolExecutor(max_workers=_w) as _ex:
        _hasil = list(_ex.map(_resize_one, _tugas, chunksize=20))
    print(f"selesai: {sum(_hasil)}/{len(_tugas)} -> {IRO_SMALL}")

DATA_LATIH = IRO_SMALL if (IRO_SMALL / "train").is_dir() else IRO
print("data latih:", DATA_LATIH)

# ============================================================
# Sel 3 — latih classifier (WAJIB GPU; gagal cepat bila tidak ada)
# ============================================================
import torch
from ultralytics import YOLO

assert torch.cuda.is_available(), (
    "CUDA tidak terlihat. Pastikan Accelerator = GPU lalu RESTART kernel, "
    "kemudian jalankan ulang dari Sel 1."
)
print("Melatih di:", torch.cuda.get_device_name(0))

model = YOLO("yolo11n-cls.pt")  # ~5 MB, cukup untuk 4 kelas
model.train(
    data=str(DATA_LATIH),  # root berisi train/ val/ (test dipakai di Sel 4)
    epochs=50,
    patience=15,
    imgsz=224,
    batch=64,
    device=0,      # paksa GPU pertama; error bila GPU tak ada
    workers=8,     # imbangi decode JPEG
    optimizer="AdamW",
    lr0=0.001,
    seed=42,
    project="/kaggle/working/runs",
    name="iroscd-cls",
)
print("Training selesai.")

# ============================================================
# Sel 4 — evaluasi pada TEST split (data yang tak dilihat saat latih)
# ============================================================
from pathlib import Path
from ultralytics import YOLO

_runs = sorted(
    Path("/kaggle/working/runs").glob("iroscd-cls*"),
    key=lambda p: p.stat().st_mtime,
)
assert _runs, "Belum ada hasil training di /kaggle/working/runs."
CLS = _runs[-1] / "weights" / "best.pt"
print("model:", CLS)

m = YOLO(str(CLS))
met = m.val(data=str(DATA_LATIH), split="test", imgsz=224)
print(f"Test top-1 : {met.top1:.4f}")
print(f"Test top-5 : {met.top5:.4f}")
print("Baseline README: ResNet-50 0,8615 · EfficientNet-B4 0,9077")
print()
print("Buka confusion_matrix.png di folder run —")
print("pastikan RECALL kelas Wet_Road tinggi (itu yang dipakai sebagai gate).")

# ============================================================
# Sel 5 — uji cepat pada 3 foto wet_road
# ============================================================
from pathlib import Path
from ultralytics import YOLO

_runs = sorted(
    Path("/kaggle/working/runs").glob("iroscd-cls*"),
    key=lambda p: p.stat().st_mtime,
)
m = YOLO(str(_runs[-1] / "weights" / "best.pt"))
for _p in sorted((DATA_LATIH / "test" / "Wet_Road").glob("*.jpg"))[:3]:
    _r = m.predict(str(_p), verbose=False)[0]
    print(f"{_p.name} -> {_r.names[_r.probs.top1]} ({_r.probs.top1conf:.2f})")

print()
print("Download dari tab Output: best.pt, confusion_matrix.png, results.csv")

# ============================================================
# Sel 6 — ZIP hasil untuk diunduh (wajib ada di setiap script training)
# Catatan: Sel 4 (evaluasi TEST) menyimpan ke folder terpisah
# runs/classify/val*, jadi keduanya ikut di-zip.
# ============================================================
import zipfile
from pathlib import Path


def _run_terbaru(pola):
    _runs = sorted(Path("/kaggle/working/runs").glob(pola),
                   key=lambda p: p.stat().st_mtime)
    return _runs[-1] if _runs else None


_latih = _run_terbaru("iroscd-cls*")   # best.pt, results.csv, confusion matrix val
_uji = _run_terbaru("classify/val*")   # confusion matrix TEST split (Sel 4)

_zip = Path("/kaggle/working") / "iroscd-cls-hasil.zip"
_berkas = ["weights/best.pt", "weights/last.pt", "results.csv",
           "confusion_matrix.png", "confusion_matrix_normalized.png",
           "args.yaml"]
with zipfile.ZipFile(_zip, "w", zipfile.ZIP_DEFLATED) as _z:
    if _latih:
        for _b in _berkas:
            _p = _latih / _b
            if _p.exists():
                _z.write(_p, arcname=f"train/{_b}")
    if _uji:
        for _b in ["confusion_matrix.png", "confusion_matrix_normalized.png"]:
            _p = _uji / _b
            if _p.exists():
                _z.write(_p, arcname=f"test/{_b}")
print(f"ZIP: {_zip} ({_zip.stat().st_size/1e6:.1f} MB)")
print("Unduh dari tab Output (bila Save Version) atau panel output sesi.")
