# Kaggle Notebook — RDD2022 Only, Final Run YOLOv11s (single maximal training)

> Revisi dari baseline YOLOv11n (2026-09-04). Keputusan run ini: dataset TETAP subset 15k
> balanced-quota (konsisten dengan eksperimen sebelumnya untuk perbandingan fair), model
> naik ke **YOLOv11s polos** (tanpa CBAM — prioritas hasil predictable), budget waktu
> **6-8 jam** (agresif, mepet limit sesi Kaggle single-session).
>
> **Kenapa berubah dari baseline lama:**
> - Analisis `results.csv` run YOLOv11n 50-epoch kemarin menunjukkan mAP50 & mAP50-95
>   MASIH NAIK di epoch terakhir (0.593 → belum plateau) — training dihentikan terlalu
>   dini, bukan karena model sudah mentok kapasitasnya.
> - YOLOv11n cuma 2.58M parameter — kemungkinan besar underfitting untuk kompleksitas
>   5 kelas kerusakan jalan dengan variasi visual besar (terutama pothole & transverse_crack).
> - Maka: naikkan kapasitas model (YOLOv11s, ~9.4M param) DAN kasih waktu training yang
>   cukup untuk benar-benar converge (bukan cuma nambah epoch di model kecil yang sama).
>
> **Estimasi waktu jujur:** dengan model 3.6x lebih besar + imgsz naik 640→768, per-epoch
> time diperkirakan ~4-5x lebih lambat dari run kemarin (yang ~2 menit/epoch). Dalam
> budget 6-8 jam, realistisnya kamu dapat **~35-55 epoch efektif**, BUKAN 200 penuh.
> `epochs=200` di config ini adalah CEILING (batas atas), bukan target — `patience=40`
> akan auto-stop kalau model plateau sebelum itu.
>
> **Fitur baru paling penting: resume otomatis.** Sel 5 didesain idempotent — kalau
> kernel Kaggle mati/timeout di tengah training (risiko nyata untuk sesi 6-8 jam),
> tinggal run ulang Sel 0-5 dan training akan otomatis lanjut dari checkpoint terakhir
> (`last.pt`), BUKAN mulai dari epoch 0. Ini bikin "1x training" kamu tahan terhadap
> gangguan sesi.
>
> ⚠️ **Catatan platform Kaggle:** resume otomatis ini hanya bekerja kalau `/kaggle/working`
> masih terisi (kernel restart karena OOM/crash, tapi sesi edit belum benar-benar ditutup).
> Kalau kamu menutup total tab/sesi Kaggle dan buka browser baru, `/kaggle/working` bisa
> ke-reset kosong. Untuk jaga-jaga di training panjang ini: **lakukan "Save Version" tiap
> ~2 jam** (klik kanan atas) supaya `last.pt` ikut ter-commit sebagai output — kalau
> working directory hilang, kamu masih bisa ambil checkpoint dari output versi sebelumnya
> dan copy manual ke `/kaggle/working/runs/.../weights/last.pt` sebelum run ulang Sel 5.

---

## Sel 0 — Setup

```python
!pip install -q ultralytics
import torch
print("torch:", torch.__version__, "| cuda:", torch.cuda.is_available())
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0))
from ultralytics import YOLO
print("ultralytics:", __import__("ultralytics").__version__)
```

## Sel 1 — CONFIG (edit path bila beda)

```python
from pathlib import Path
RDD  = Path("/kaggle/input/datasets/aliabdelmenam/rdd-2022/RDD_SPLIT")  # berisi train/val/test
# BPID: slug input beda tiap sesi Kaggle — auto-detect, isi manual bila gagal.
_BPID_CANDS = [Path("/kaggle/input/bpid-bandung"),                      # sesi A
               Path("/kaggle/input/datasets/arkv99/bpid-bandung/bpid"), # sesi B 2026-09-04
               Path("/kaggle/input/bpid-bandung/bpid")]
BPID = next((c for c in _BPID_CANDS if (c/"test/images").exists()
             and any((c/"test/images").iterdir())), _BPID_CANDS[0])
print("BPID =", BPID)  # berisi test/images + test/labels
WORK = Path("/kaggle/working")
SEED = 42

# --- Konfigurasi run final YOLOv11s (revisi 2026-09) ---
MODEL_NAME = "yolo11s.pt"   # naik dari yolo11n — kapasitas lebih besar utk 5-kelas kompleks
RUN_NAME   = "yolo11s-rdd-only"
IMGSZ      = 768            # naik dari 640 — bantu deteksi objek kecil (pothole/transverse)
BATCH      = 16             # sama dgn run lama; turunkan ke 12/8 kalau OOM di imgsz 768
EPOCHS     = 200            # CEILING, bukan target — lihat estimasi waktu di atas
PATIENCE   = 40             # naik dari 10 — run lama BELUM plateau di epoch 50
CLASSES = ["longitudinal_crack", "transverse_crack", "alligator_crack",
           "other_corruption", "pothole"]

# --- Resume LINTAS COMMIT (isi manual HANYA kalau commit sebelumnya keputus) ---
# Kalau "Save and Run All (Commit)" kamu mati di tengah jalan (misal di epoch 45):
#   1. Buka Output versi commit yang keputus itu, pastikan folder runs/.../weights/last.pt ada
#   2. Di notebook ini: "+ Add Input" -> cari notebook kamu sendiri -> pilih versi tsb
#   3. Kaggle mount jadi /kaggle/input/<slug-notebook-kamu>/ -- cek nama pastinya di
#      panel Input kanan setelah ditambahkan, lalu isi di bawah ini
PREV_RUN_CANDS = [
    Path("/kaggle/input/rdd-yolov11s/runs"),   # slug default -- SESUAIKAN kalau beda
]
```

## Sel 2 — AUDIT RDD2022 (wajib sebelum latih)

```python
import random, cv2
from collections import Counter
random.seed(SEED)

IMG_EXTS = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")

def list_images(d):
    out = set()
    for e in IMG_EXTS:
        out.update(Path(d).glob(e))
    return sorted(out)

def audit(img_dir, lbl_dir, tag="", sample_labels=3000):
    img_dir, lbl_dir = Path(img_dir), Path(lbl_dir)
    imgs = list_images(img_dir)
    lbl_paths = sorted(lbl_dir.glob("*.txt"))
    print(f"[{tag}] images={len(imgs)} label-files={len(lbl_paths)}", flush=True)
    if not imgs:
        print(f"[{tag}] KOSONG — path salah atau ekstensi beda. Isi {img_dir}:")
        base = img_dir
        while not base.exists() and base != base.parent:
            base = base.parent
        for p in sorted(base.rglob("*"))[:30]:
            print("   ", p.relative_to(base), "<DIR>" if p.is_dir() else "")
        return []
    img_stems = {p.stem for p in imgs}
    lbl_stems = {p.stem for p in lbl_paths}
    print(f"[{tag}] tanpa-label={len(img_stems - lbl_stems)} tanpa-gambar={len(lbl_stems - img_stems)}", flush=True)
    take = random.sample(lbl_paths, min(sample_labels, len(lbl_paths)))
    cnt, bad = Counter(), []
    for i, t in enumerate(take, 1):
        for l in t.read_text().strip().splitlines():
            r = l.split()
            if len(r) != 5:
                bad.append((t.name, l)); continue
            c = int(r[0]); v = [float(x) for x in r[1:]]
            if not (0 <= c <= 4) or not all(0 <= x <= 1 for x in v):
                bad.append((t.name, l)); continue
            cnt[c] += 1
        if i % 1000 == 0:
            print(f"[{tag}] ...{i}/{len(take)} label dibaca", flush=True)
    print(f"[{tag}] distribusi box (sampel {len(take)} berkas):", dict(sorted(cnt.items())), flush=True)
    corrupt = [p.name for p in random.sample(imgs, min(20, len(imgs))) if cv2.imread(str(p)) is None]
    print(f"[{tag}] label rusak={len(bad)} gambar korup(sampel 20)={len(corrupt)}", flush=True)
    if bad[:3]: print("contoh rusak:", bad[:3])
    return imgs

for s in ["train", "val", "test"]:
    audit(RDD/s/"images", RDD/s/"labels", tag=f"RDD-{s}")
```

## Sel 2b — Visual check 6 gambar + box (bukti label waras)

```python
import matplotlib.pyplot as plt
imgs = list_images(RDD/"train/images")
if not imgs:
    print("Folder kosong / path salah. Struktur aktual di bawah input RDD:")
    for p in sorted(RDD.rglob("*"))[:40]:
        print("  ", p.relative_to(RDD), "<DIR>" if p.is_dir() else "")
    raise SystemExit("Perbaiki path RDD di Sel 1 sesuai struktur di atas, lalu run ulang.")
k = min(6, len(imgs))
fig, ax = plt.subplots(2, 3, figsize=(15, 10))
for a, p in zip(ax.flat, random.sample(imgs, k)):
    im = cv2.cvtColor(cv2.imread(str(p)), cv2.COLOR_BGR2RGB)
    h, w = im.shape[:2]
    t = RDD/"train/labels"/(p.stem + ".txt")
    for l in t.read_text().strip().splitlines():
        c, cx, cy, bw, bh = int(l.split()[0]), *[float(x) for x in l.split()[1:]]
        x1, y1, x2, y2 = (cx-bw/2)*w, (cy-bh/2)*h, (cx+bw/2)*w, (cy+bh/2)*h
        cv2.rectangle(im, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)
        cv2.putText(im, CLASSES[c], (int(x1), max(int(y1)-5, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
    a.imshow(im); a.set_title(p.name[:25]); a.axis("off")
for a in list(ax.flat)[k:]:
    a.axis("off")
plt.tight_layout(); plt.show()
```

## Sel 3 — Subset 15k balanced-quota sampling

> Metodologi TIDAK berubah dari run lama — dataset harus tetap identik supaya perbandingan
> "YOLOv11n baseline vs YOLOv11s final" fair (variabel yang beda cuma model+config training).

```python
import shutil
from collections import defaultdict

shutil.rmtree(WORK/"sub_rdd", ignore_errors=True)  # idempotency: bersih sebelum isi ulang

def stratified_subset(src_i, src_l, dst, target, keep_prefix=None, seed=SEED):
    src_i, src_l, dst = Path(src_i), Path(src_l), Path(dst)
    (dst/"images").mkdir(parents=True, exist_ok=True)
    (dst/"labels").mkdir(parents=True, exist_ok=True)
    _exts = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")
    _all = sorted({p for e in _exts for p in Path(src_i).glob(e)})
    pool = [p for p in _all
            if (not keep_prefix or p.name.startswith(keep_prefix))]
    def sig(p):
        t = src_l/(p.stem + ".txt")
        if not t.exists():
            return ()
        cls = set()
        for l in t.read_text().strip().splitlines():
            r = l.split()
            if len(r) != 5:
                continue
            try:
                c = int(r[0])
            except ValueError:
                continue
            if 0 <= c <= 4:
                cls.add(c)
        return tuple(sorted(cls))
    buckets = defaultdict(list)
    for i, p in enumerate(pool, 1):
        buckets[sig(p)].append(p)
        if i % 3000 == 0:
            print(f"...{i}/{len(pool)} signature dibaca", flush=True)
    random.seed(seed)
    sel, quota = [], max(target // max(len(buckets), 1), 1)
    for v in buckets.values():
        random.shuffle(v)
        sel += v[:quota]
    random.shuffle(pool)
    sel_set = set(sel)
    for p in pool:
        if len(sel) >= target: break
        if p not in sel_set:
            sel.append(p); sel_set.add(p)
    sel = sel[:target]
    for p in sel:
        shutil.copy(p, dst/"images"/p.name)
        q = src_l/(p.stem + ".txt")
        if q.exists(): shutil.copy(q, dst/"labels"/q.name)
    (dst/"subset_files.txt").write_text("\n".join(sorted(p.name for p in sel)))
    print(f"{dst.name}: {len(sel)} gambar dari pool {len(pool)} | bucket signature: {len(buckets)}")
    return dst

rdd15k = stratified_subset(RDD/"train/images", RDD/"train/labels", WORK/"sub_rdd", 15000,
                          keep_prefix=("India_", "China_MotorBike_", "Japan_"))
```

## Sel 4 — Split train/val + tulis rdd-only.yaml (test = RDD test full)

```python
import shutil
shutil.rmtree(WORK/"rdd_only", ignore_errors=True)
merged = WORK/"rdd_only"
for s in ["train", "val"]:
    (merged/s/"images").mkdir(parents=True, exist_ok=True)
    (merged/s/"labels").mkdir(parents=True, exist_ok=True)
all_items = []
for p in (WORK/"sub_rdd/images").glob("*"):
    q = WORK/"sub_rdd/labels"/(p.stem + ".txt")
    if q.exists(): all_items.append((p, q))
random.seed(SEED); random.shuffle(all_items)
cut = int(len(all_items) * 0.85)
for i, (p, q) in enumerate(all_items):
    s = "train" if i < cut else "val"
    shutil.copy(p, merged/s/"images"/p.name)
    shutil.copy(q, merged/s/"labels"/q.name)
(merged/"rdd-only.yaml").write_text(
    f"path: {merged}\ntrain: train/images\nval: val/images\n"
    f"test: {RDD/'test/images'}\nnc: 5\nnames: {CLASSES}\n")
print(f"train={len(list((merged/'train/images').glob('*')))} "
      f"val={len(list((merged/'val/images').glob('*')))} | test = RDD test full")
```

## Sel 5 — TRAIN YOLOv11s final (~6-8 jam, RESUME-SAFE)

> **PENTING (koreksi):** resume otomatis di bawah ini hanya melindungi dari restart
> DALAM sesi/container yang sama (mis. kernel crash lalu kamu run ulang cell ini tanpa
> commit baru). Kaggle "Save and Run All (Commit)" baru = container BARU dengan
> `/kaggle/working` KOSONG — checkpoint lama TIDAK otomatis kebawa. Kalau commit kamu
> keputus di tengah jalan, ikuti instruksi `PREV_RUN_CANDS` di Sel 1 sebelum commit ulang.
> Cell ini cek DUA sumber: checkpoint lokal dulu, baru checkpoint dari commit
> sebelumnya (via Input) kalau lokal kosong.

```python
import shutil as _sh2

def find_local_ckpt():
    found = sorted((WORK/"runs").glob(f"{RUN_NAME}*/weights/last.pt"))
    return found[-1] if found else None

last_ckpt = find_local_ckpt()

if last_ckpt is None:
    # Tidak ada checkpoint lokal -> cek apakah ada checkpoint dari COMMIT SEBELUMNYA
    # yang sempat keputus (baru ketemu kalau sudah di-+Add Input sesuai Sel 1)
    for cand in PREV_RUN_CANDS:
        if not cand.exists():
            continue
        prev_found = sorted(cand.glob(f"{RUN_NAME}*/weights/last.pt"))
        if prev_found:
            prev_run_dir = prev_found[-1].parent.parent
            dst_run_dir = WORK/"runs"/prev_run_dir.name
            print(f"Checkpoint dari commit sebelumnya ditemukan: {prev_found[-1]}")
            print(f"Menyalin {prev_run_dir} -> {dst_run_dir} sebelum resume...")
            _sh2.copytree(prev_run_dir, dst_run_dir, dirs_exist_ok=True)
            break
    last_ckpt = find_local_ckpt()

if last_ckpt:
    print(f"Checkpoint ditemukan: {last_ckpt} — MELANJUTKAN training (bukan mulai ulang).")
    model = YOLO(str(last_ckpt))
    model.train(resume=True)
else:
    print("Belum ada checkpoint sama sekali — MULAI training baru dari pretrained COCO.")
    model = YOLO(MODEL_NAME)
    model.train(
        data=str(WORK/"rdd_only/rdd-only.yaml"),
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        patience=PATIENCE,
        seed=SEED,
        cos_lr=True,        # scheduler lebih smooth utk training panjang
        mixup=0.1,          # bantu generalisasi + kelas minoritas (pothole)
        copy_paste=0.1,     # sama tujuannya — variasi instance kelas jarang
        project=str(WORK/"runs"),
        name=RUN_NAME,
        save_period=10,     # checkpoint terpisah tiap 10 epoch, jaga2 last.pt korup
    )
# best.pt otomatis = epoch terbaik berdasar fitness (mAP), jadi early-stop tidak merusak model
```

## Sel 6 — Evaluasi val + test + metrik per kelas

```python
cands = sorted((WORK/"runs").glob(f"{RUN_NAME}*"))
assert cands, f"tidak ada folder runs/{RUN_NAME}* — Sel 5 belum sukses?"
run_dir = cands[-1]
print("pakai run:", run_dir.name)
m = YOLO(str(run_dir/"weights/best.pt"))
rv = m.val(data=str(WORK/"rdd_only/rdd-only.yaml"), imgsz=IMGSZ)
print(f"VAL  mAP50={rv.box.map50:.4f} mAP50-95={rv.box.map:.4f} P={rv.box.mp:.4f} R={rv.box.mr:.4f}")
r = m.val(data=str(WORK/"rdd_only/rdd-only.yaml"), split="test", imgsz=IMGSZ)
print(f"TEST mAP50={r.box.map50:.4f} mAP50-95={r.box.map:.4f} P={r.box.mp:.4f} R={r.box.mr:.4f}")
print("Per-kelas mAP50-95:", {c: round(float(v), 4) for c, v in zip(CLASSES, r.box.maps[:len(CLASSES)])})
print("confusion_matrix:", run_dir/"confusion_matrix.png")
print("results.csv:", run_dir/"results.csv")
print("--- Bandingkan manual dengan baseline YOLOv11n: test mAP50=0.470, test pothole=0.396 ---")
```

## Sel 7 — Evaluasi OOD BPID Bandung (remap 0->4 pada salinan)

```python
orig_classes = {l.split()[0] for t in (BPID/"test/labels").glob("*.txt")
                for l in t.read_text().strip().splitlines() if l.split()}
audit(BPID/"test/images", BPID/"test/labels", tag="BPID")
assert orig_classes == {"0"}, f"BPID harus tepat 1 kelas (0); ketemu: {sorted(orig_classes) or 'KOSONG — dataset bpid-bandung belum di-+Add Input?!'} — cek dulu sebelum remap!"
bpid_out = WORK/"bpid_eval"
(bpid_out/"images").mkdir(parents=True, exist_ok=True)
(bpid_out/"labels").mkdir(parents=True, exist_ok=True)
for p in (BPID/"test/images").glob("*"):
    shutil.copy(p, bpid_out/"images"/p.name)
for t in (BPID/"test/labels").glob("*.txt"):
    lines = []
    for l in t.read_text().strip().splitlines():
        s = l.split(); s[0] = "4"; lines.append(" ".join(s))
    (bpid_out/"labels"/t.name).write_text("\n".join(lines))
n_img = len(list((bpid_out/"images").glob("*")))
n_lbl = len(list((bpid_out/"labels").glob("*.txt")))
print(f"bpid_eval: {n_img} gambar, {n_lbl} label")
if n_img == 0:
    print("KOSONG — kemungkinan dataset bpid-bandung belum di-+Add Input, atau struktur beda:")
    for p in sorted(BPID.rglob("*"))[:40]:
        print("  ", p.relative_to(BPID) if BPID.exists() else p)
    raise SystemExit("Tambah input / perbaiki path BPID di Sel 1, lalu run ulang Sel 7.")
(bpid_out/"bpid.yaml").write_text(
    f"path: {bpid_out}\ntrain: images\nval: images\ntest: images\nnc: 5\nnames: {CLASSES}\n")
if "m" not in dir():
    from ultralytics import YOLO as _Y
    run_dir = sorted((WORK/"runs").glob(f"{RUN_NAME}*"))[-1]
    m = _Y(str(run_dir/"weights/best.pt"))
    print("m di-bootstrap dari:", run_dir.name)
rb = m.val(data=str(bpid_out/"bpid.yaml"), imgsz=IMGSZ)
print(f"OOD Bandung mAP50={rb.box.map50:.4f} (baseline YOLOv11n = 0.551 — bandingkan)")
```

## Sel 8 — Export ONNX + paket artefak

```python
if "WORK" not in dir():
    from pathlib import Path as _P
    WORK = _P("/kaggle/working")
run_dir = sorted((WORK/"runs").glob(f"{RUN_NAME}*"))[-1]
print("pakai run:", run_dir.name)
if "m" not in dir():
    from ultralytics import YOLO as _Y
    m = _Y(str(run_dir/"weights/best.pt"))
m.export(format="onnx")
import shutil as _sh
_out = WORK/"artifacts"; _out.mkdir(exist_ok=True)
for f in ["best.pt", "best.onnx", "confusion_matrix.png", "results.csv", "args.yaml"]:
    src = run_dir/f"weights/{f}" if f in ("best.pt", "best.onnx") else run_dir/f"{f}"
    if Path(src).exists(): _sh.copy(src, _out/f)
for src in [WORK/"sub_rdd/subset_files.txt"]:
    if src.exists(): _sh.copy(src, _out/f"sub_rdd_subset_files.txt")
_sh.copy(WORK/"rdd_only/rdd-only.yaml", _out/"rdd-only.yaml")
print("Download isi folder:", _out, "-> best.pt + best.onnx masuk app/weights/ di laptop")
```

## Sel 9 — ZIP semua hasil

```python
from pathlib import Path as _P
import zipfile, datetime

if "WORK" not in dir():
    WORK = Path("/kaggle/working")
    print("WORK di-bootstrap ke default:", WORK)

STAMP = datetime.datetime.now().strftime("%Y%m%d-%H%M")
ZIP_PATH = WORK / f"hasil-rdd-yolo11s-{STAMP}.zip"
SKIP_DIR_NAMES = {"images"}
KEPT = []

def add_file(src):
    KEPT.append((src, src.relative_to(WORK)))

runs = WORK / "runs"
if runs.exists():
    for p in sorted(runs.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIR_NAMES for part in p.parts):
            continue
        add_file(p)
else:
    print("WARN: folder runs/ tidak ada (belum train?)")

art = WORK / "artifacts"
if art.exists():
    for p in sorted(art.rglob("*")):
        if p.is_file():
            add_file(p)

for rel in ["rdd_only/rdd-only.yaml", "bpid_eval/bpid.yaml",
            "sub_rdd/subset_files.txt"]:
    p = WORK / rel
    if p.exists():
        add_file(p)

seen, uniq = set(), []
for src, arc in KEPT:
    if str(arc) not in seen:
        seen.add(str(arc))
        uniq.append((src, arc))

with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    for src, arc in uniq:
        z.write(src, arc)

bad = zipfile.ZipFile(ZIP_PATH).testzip()
print(f"ZIP: {ZIP_PATH} | {len(uniq)} berkas | {ZIP_PATH.stat().st_size/1e6:.1f} MB | testzip={bad}")
print("Download: panel kanan Output ->", ZIP_PATH.name, "+ File -> Save Version.")
```

Cara pakai di laptop setelah download:

```powershell
# dari root repo
Expand-Archive .\hasil-rdd-yolo11s-YYYYMMDD-HHMM.zip -DestinationPath .\_kaggle_out_yolo11s\
copy .\_kaggle_out_yolo11s\artifacts\best.pt .\app\weights\best_yolo11s_rddonly.pt
copy .\_kaggle_out_yolo11s\artifacts\best.onnx .\app\weights\best_yolo11s_rddonly.onnx
```

---

## Opsi lanjutan (DISIMPAN, tidak dipakai run ini)

Keputusan run ini: **YOLOv11s polos** dipilih atas CBAM demi hasil predictable dalam
satu kali training. Opsi berikut tetap tersimpan sebagai bahan iterasi berikutnya kalau
hasil run ini masih di bawah target:

- **YOLOv11s + CBAM** — modul CBAM di notebook lama diverifikasi jalan di arsitektur
  `yolo11n.yaml`; kalau mau dipakai di size `s`, yaml `yolo11s.yaml` perlu di-cek ulang
  (channel width beda dari `n`, jadi baris `CBAM, [256]` di Sel 10b lama BISA salah
  dimensi untuk `s` — jangan asal copy, perlu verifikasi ulang seperti Sel 10a-10c lama).
- **YOLOv26n** — sudah terkonfirmasi tersedia di ultralytics 8.4.138 sebagai pembanding
  arsitektur baru, param sekelas v11n. Belum diuji sekelas `s`.

## Catatan metodologi subset 15k (tidak berubah dari run lama)

- Istilah akurat: "balanced/quota sampling per class-signature" — BUKAN stratified
  sampling murni.
- Limitasi: val dipotong dari subset rebalance sehingga TIDAK merepresentasikan distribusi
  asli — hanya valid untuk perbandingan internal. Klaim dunia nyata = test RDD full
  (Sel 6) + OOD BPID (Sel 7).

## Tabel hasil (isi setelah run ini selesai)

| Metrik | YOLOv11n baseline (lama) | YOLOv11s final (run ini) | Selisih |
|---|---|---|---|
| val mAP50 | 0.593 | **0.6483** (P 0.687, R 0.590) | +0.055 |
| test mAP50 (RDD full) | 0.470 | **0.5262** (P 0.597, R 0.514) | +0.056 |
| test pothole (mAP50-95) | 0.396 (mAP50!) | 0.2252 (mAP50-95 — TIDAK sebanding langsung) | n/a |
| test transverse (mAP50-95) | 0.403 (mAP50!) | 0.2019 (mAP50-95 — TIDAK sebanding langsung) | n/a |
| OOD Bandung mAP50 | 0.551 (imgsz 768) | **0.4516 lokal** (imgsz 960; n-lama 0.4497 di setup sama → seri) | +0.002 |
| waktu train | 1.64 jam (50ep) | **9.55 jam (131ep)** | — |
| epoch efektif tercapai | 50 | **131 (best ep 91, early-stop patience 40)** | — |

> Diisi 2026-09-08 dari output Sel 6 notebook. Per-kelas run ini (mAP50-95):
> long 0.2393, trans 0.2019, allig 0.3277, other 0.3866, pothole 0.2252.
> Sel 7 OOD GAGAL di Kaggle (dataset bpid-bandung tidak di-Add Input, assert
> `orig_classes == {"0"}`); angka OOD di atas dari eval lokal 161 foto
> (`bpid.yaml` remap 0→4, imgsz 960, CPU i5-3470). Sel 8 (export ONNX) tidak
> jalan — belum ada `best.onnx` untuk model s.

---

## Checklist run

- [ ] Add Input: rdd-2022 + bpid-bandung + GPU T4 + Internet ON
- [ ] Sel 0-2b hijau (audit + visual)
- [ ] Sel 3-4 hijau (sub_rdd 15k + rdd-only.yaml — pool/seed SAMA dgn run lama)
- [ ] Sel 5 train dimulai — catat waktu/epoch setelah beberapa epoch pertama utk
      validasi estimasi (~8-10 menit/epoch pada imgsz 768 + yolo11s di T4)
- [ ] **Kalau sesi terputus**: run ulang Sel 0-5, cek log print "MELANJUTKAN training"
      (bukan "MULAI training baru") — kalau salah, last.pt hilang, cek /kaggle/working
- [ ] **Save Version tiap ~2 jam** selama training panjang ini, jaga-jaga
- [ ] Sel 6-8 hijau (isi angka ke tabel hasil di atas)
- [ ] Sel 9 zip + download OK
- [ ] Update tabel hasil + bandingkan vs target awal (0.65 mAP50 test)
