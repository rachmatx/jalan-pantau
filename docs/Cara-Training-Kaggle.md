# Cara Menjalankan Training di Kaggle (JalanPantau)

Panduan praktis: dari persiapan data sampai artefak kembali ke repo.
Alur: **siapkan data → buat notebook (GPU) → jalankan sel → unduh hasil → taruh di repo → catat untuk skripsi.**

Template sel: `notebooks/template-kaggle-yolo11-detect.md` (baseline) dan
`notebooks/template-kaggle-hard-negative-finetune.md` (lanjutan: hard-negative + fine-tune + pseudo-label).
Notebook run sebelumnya (contoh nyata): `yolov11s-rdd-only/Kaggle_Notebook_-_RDD2022_YOLOv11s_Final_Run1.md`.

---

## 1. Yang harus disiapkan

**Akun**
- Akun Kaggle + **verifikasi nomor HP** (syarat akses GPU).

**Data yang TIDAK perlu diunduh** (pakai "+ Add Input"):
- `aliabdelmenam/rdd-2022` — dataset RDD2022 (11 GB, tetap di server Kaggle).
- Roma / dataset lain bila dipakai (`docs/Dataset-Roma-manhole-prototipe.md`).

**Data yang HARUS kamu unggah sebagai Kaggle Dataset (private)** — hanya terlihat olehmu:
- `data/publik/bpid/` → dataset `bpid-bandung` (evaluasi OOD Bandung, test saja).
- `app/weights/best_yolo11s.pt` → dataset `jalanpantau-weights` (titik awal fine-tune).
- `negatives/` (foto aspal baik tanpa kerusakan) → dataset `negatives` (hard-negative mining).
- `lokal-unlabeled/` (foto lokal tanpa label) → dataset `lokal-unlabeled` (pseudo-label).
- `data/dataset-rdd2022.yaml` (dari repo) → ikutkan ke notebook.

Cara unggah: Kaggle → **Datasets → New Dataset** → unggah (boleh .zip) → beri nama → **Create**.

---

## 2. Membuat notebook

1. Kaggle → **Code → New Notebook**.
2. Panel kanan → **Notebook options**:
   - **Accelerator: GPU T4 x2** (atau P100).
   - **Internet: On** (untuk `pip install -q ultralytics` bila perlu).
3. **+ Add Input** → tambahkan semua dataset di atas.
4. **Cek path aktual** (slug berubah tiap sesi!) sebelum menjalankan:
   ```python
   !ls /kaggle/input
   !ls /kaggle/input/<nama-dataset>
   ```
   Sesuaikan variabel path di sel Config (contoh kanonik dari run sebelumnya:
   `/kaggle/input/datasets/aliabdelmenam/rdd-2022/RDD_SPLIT`).
5. Salin sel dari template yang sesuai:
   - Baseline/awal → `notebooks/template-kaggle-yolo11-detect.md`
   - Lanjutan (untuk menaikkan mAP/OOD) → `notebooks/template-kaggle-hard-negative-finetune.md`

---

## 3. Menjalankan

- Jalankan sel berurutan. Sel 0 wajib memastikan **CUDA aktif**.
- Untuk run panjang (jam-jaman), **jangan biarkan tab idle**: pakai
  **Save Version → Save & Run All (Commit)** agar berjalan di latar.
- **Save Version tiap ~1–2 jam** pada run panjang supaya `last.pt` ikut ter-commit
  bila sesi mati. Catatan platform: `/kaggle/working` bisa ter-reset bila tab/sesi
  Kaggle ditutup total (lihat catatan di notebook v11s).
- Ada **batas durasi sesi & kuota GPU mingguan** (cek angka terkini di Kaggle;
  T4 sekitar puluhan jam/minggu). Rencanakan run 2–3 jam per sesi, sisakan margin.

---

## 4. Setelah selesai — unduh (dari Output / versi yang di-commit)

- `best.pt`, `best.onnx`
- `results.csv` (bukti training per-epoch)
- `confusion_matrix.png`, `BoxPR_curve.png`, `BoxF1_curve.png`, `results.png`

---

## 5. Taruh kembali ke repo

- Bobot → `app/weights/` (mis. `best_yolo11s.pt`, `best.onnx`).
- **Setelah mengganti bobot, perbarui checksum**: jalankan
  `python scripts/verifikasi_bobot.py` → akan melaporkan **[BEDA]**, lalu regenerasi
  `app/weights/SHA256SUMS.txt` (agar bukti integritas tetap valid).
- Bila angka mAP berubah: perbarui README bagian "Akurasi terukur" dan `web/templates/tentang.html`.
- `results.csv` + kurva → `artifacts/hasil-<nama-run>/` (bukti provenance).
- Catat keputusan di `docs/Strategi-Training.md` (decision log).

---

## 6. Yang wajib dicatat untuk skripsi

- Dataset & split (train/val/test), jumlah gambar, **seed**.
- Model awal (from-scratch vs fine-tune dari bobot mana) + hyperparameter.
- GPU & waktu (menit/epoch, total).
- **mAP50 & mAP50-95 per kelas**, Precision, Recall, F1, confusion matrix.
- Perbandingan: baseline vs varian (hard-negative / domain adaptation / pseudo-label).
- Bila bisa: 3 seed → laporkan **mean ± simpangan baku**.

---

## 7. Jebakan umum

- **Path input berubah tiap sesi** → selalu `!ls /kaggle/input` dan sesuaikan variabel.
- **ONNX export**: gunakan `dynamic=True` (agar imgsz bebas di laptop; statis 640 tidak
  bisa jalan di 960).
- **Kuota/sesi habis** → pecah jadi beberapa run; lanjutkan dari `last.pt` (notebook
  sel training dibuat idempotent untuk ini).
- **Urutan kelas** 0..4 harus sama dengan aplikasi:
  `0 longitudinal, 1 transverse, 2 alligator, 3 other_corruption, 4 pothole`.
- **Ukuran output** besar → unduh hanya yang perlu.
- **Jangan** menjadikan test set sebagai pseudo-label (bias); sisihkan test murni.
