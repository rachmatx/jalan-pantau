# Strategi Training (disusun 2026-09-03)

Prinsip: bakar kuota T4 sedikit demi sedikit — prototipe murah dulu, full-run sekali di akhir.
Semua latih di Kaggle (GPU T4/P100). Template sel: `notebooks/template-kaggle-yolo11-detect.md`.

## Tahap 0 — Persiapan (revisi 2026-09-03: RDDC drop, Kaggle tetap di Kaggle)
- [ ] RDD2022 11 GB + Roma 195 MB + mini India: JANGAN download. Dipakai via + Add Input di notebook Kaggle.
- [ ] RDDC2024-ID: DROP (dataset tidak tersedia). Pengganti = Roma-remap (Sel 3b/5 template).
- [ ] BPID Bandung (161 foto): SUDAH di `data/publik/bpid/` → upload sebagai Kaggle private dataset (TEST SAJA).
- [ ] Rekam + anotasi 150 foto lokal (Roboflow, format YOLO detect 5 kelas, samakan urutan!)

## Tahap 1 — Prototipe Roma (validasi pipeline, ±30 menit T4)
- Data: Roma 2.009 gambar (YOLO-ready). Mapping FINAL: pothole->4, crack->1, manhole->3 (dipakai juga saat gabung train).
- Model: `yolo11n.pt`, imgsz 640, batch 16, epochs 30, patience 10.
- Target: pipeline hijau (train → val → predict 5 gambar → export ONNX → jalan di Streamlit laptop).
- Berhenti bila: mAP50 > 0,5 dan tidak ada error shape. JANGAN kejar skor di sini.

## Tahap 2 — Subset utama (run pembanding jurnal, ±1-1,5 jam T4)
- Data: merged train = RDD2022-8k (India/MotorBike/Japan) + Roma-2k (remapped).
- Dua run identik: `yolo11n.pt` vs `yolov8n.pt`, epochs 50 (MAKS 60),
  imgsz 640, batch 16, patience 10 (MAKS 15),
  augmentasi default + hsv_h 0,015 (simulasi aspal beda cahaya).
  Batas dicatat 2026-09-04: normal 50+10, maks 60+15 (kuota T4).
- Catat: mAP50, mAP50-95, Precision, Recall, F1 per kelas, confusion matrix, waktu/epoch, GPU.
- Pilih juara (ekspektasi: v11n). Yang kalah tetap masuk tabel pembanding jurnal.

## Tahap 2c — DIBATALKAN, digabung ke varian B (2026-09-04, sesi A dihentikan)
- B-15k langsung = baseline utama (note RDD-only). Two-stage batal karena pasangannya (A) mati.
- Angka acuan tetap: target 15000 → train ~12,7k / val ~2,2k, ±2,6 jam.
- Full 26,8k tetap TIDAK dipakai final (domain salju Norway/drone bukan proksi Indonesia).

## Tahap 2b — Ablasi merge (jawab: apakah gabung Roma salah?)
- A (selesai): RDD8k + Roma-full → mAP50 0,59. Baseline, jangan dihapus.
- B: RDD15k LANGSUNG sebagai baseline utama (sesi A dihentikan 2026-09-04):
  target 15000, pool + prefix + seed sama, 50ep + patience 10, ±2,6 jam.
  Template notebook: `[[Kaggle Notebook - RDD2022 Only Baseline YOLOv11n]]`.
- C: RDD8k + Roma pothole+manhole saja (Sel 5b → merged_C, latih identik).
- Bandingkan mAP50 overall + mAP transverse + recall pothole antar A/B/C.
- Vonis: B≫A di transverse = crack Roma mengotori (mapping kasar salah); C terbaik = merge selektif benar;
  A≈B≈C = merge bukan masalah, lanjut ke imgsz 960 / data lokal.

## Tahap 2d — Ablasi CBAM + YOLO26 (SELESAI 2026-09-04, notebook `notebooks/rdd-yolov11n.ipynb` Sel 12-15)
- Data: SAMA persis dengan baseline B (train 12049 / val 2127 / test RDD full, seed 42). Resep identik: 50 epoch, patience 10, batch 16, imgsz 640.
- CBAM: modul Channel+Spatial Attention disisip setelah C2PSA P5/32 backbone (`artifacts/.../artifacts_ablasi/cbam.py`, `yolo11n-cbam.yaml`); edit YAML terverifikasi assert; transfer 240/502 layer cocok, bobot CBAM random by design; waktu 1,677 jam.
- YOLO26: `yolo26n.pt` (ultralytics 8.4.138) resep identik; loss berbeda (l1_loss, bukan dfl_loss) — dicatat untuk pembahasan skripsi.
- Hasil VAL (best.pt):
  | Run | epoch best | P | R | mAP50 | mAP50-95 | best.pt | best.onnx |
  |---|---|---|---|---|---|---|---|
  | B baseline v11n | — | 0,6200 | 0,5463 | 0,5914 | 0,3059 | 5,2 MB | 10,1 MB |
  | v11n + CBAM | 50 (terakhir, kurva masih naik) | 0,6140 | 0,5225 | 0,5687 | 0,2900 | 5,2 MB | 10,2 MB |
  | YOLO26n | 46 | 0,6061 | 0,5327 | 0,5706 | 0,2988 | 5,1 MB | 9,4 MB |
- Confusion matrix val: antar-kelas TERTUKAR KECIL (satu digit); galat dominan = background (miss 260-400/kelas + false alarm 150-420/kelas). CBAM sedikit lebih baik di transverse_crack (253 vs 228 benar).
- VONIS (final, val + test konsisten): baseline B MENANG di kedua level. Gap test ±1,8 poin (CBAM −1,8; YOLO26 −1,9) sedikit lebih kecil dari gap val (±2,2) — keunggulan baseline menyusut di data baru tapi tetap menang. CBAM best di epoch 50 → klaim butuh epoch lebih LEMAH tanpa bukti (YOLO26 plateau di 46). Model final tetap baseline B.
- Hasil TEST RDD full 5758 gambar (Kaggle T4, 2026-09-05, sel adaptasi Sel 8 + Sel A cbam.py mandiri):
  | Run | TEST mAP50 | TEST mAP50-95 | P | R |
  |---|---|---|---|---|
  | B baseline v11n | 0,4702 | 0,2407 | 0,5670 | 0,4656 |
  | v11n + CBAM | 0,4524 | 0,2304 | 0,5300 | 0,4624 |
  | YOLO26n | 0,4517 | 0,2359 | 0,5592 | 0,4520 |
- Per-kelas TEST mAP50-95: baseline menang 5/5 vs CBAM dan 4/5 vs YOLO26. Satu-satunya sel kemenangan non-baseline = pothole oleh YOLO26 (0,1767 vs 0,1708, +0,6 poin) — sinyal kecil, dilaporkan apa adanya.
  | Kelas | Baseline | CBAM | YOLO26 |
  |---|---|---|---|
  | longitudinal_crack | 0,2018 | 0,1916 | 0,2009 |
  | transverse_crack | 0,1770 | 0,1589 | 0,1657 |
  | alligator_crack | 0,3079 | 0,2968 | 0,3028 |
  | other_corruption | 0,3459 | 0,3431 | 0,3334 |
  | pothole | 0,1708 | 0,1617 | 0,1767 |
- OOD Bandung 161 gambar (Kaggle T4, 2026-09-05, sel adaptasi Sel 9): baseline 0,5514 vs CBAM 0,4934 (−5,8 poin) vs YOLO26 0,4782 (−7,3 poin). Gap OOD LEBIH BESAR dari gap val/test (±2 poin) → baseline generalisasi terbaik; ranking B > CBAM ≈ YOLO26 berlaku di SEMUA level. Ablasi DINYATAKAN TERTUTUP (val + test + OOD).
- Artefak: `artifacts/hasil-ablasi-cbam-yolo26-20260904-1534/` (runs lengkap + `artifacts_ablasi/` + zip); decision log: `reports/keputusan-ablasi-cbam-yolo26.md`.

## Tahap 3 — Final + evaluasi generalisasi (run terakhir, murah)
- Opsional bila kuota sisa: tambah epoch juara (resume best.pt, +10 epoch, lr lebih kecil).
- Naik status menjadi Tahap 2c (bukan future work lagi): 1 run subset 15k (pool + seed sama,
  resep pemenang) untuk model final + cek stabilitas ranking terhadap ukuran data.
- Evaluasi 3 test set TERPISAH, catat mAP drop:
  1. RDD2022 test split (in-distribution)
  2. BPID Bandung 50 foto (OOD cuaca Indonesia)
  3. Foto lokal sendiri (target deployment)
- Uji manhole: hitung false-positive pothole pada gambar manhole Roma.
- Export: `best.pt` + `best.onnx` → `app/weights/` di laptop → uji FPS CPU i5.

## Hyperparameter kunci (tetap, jangan diutak-atik tiap run)
- imgsz 640, batch 16, optimizer auto (AdamW), lr0 default, single_cls=False
- epochs: normal 50, MAKS 60. patience: normal 10, MAKS 15 (catat 2026-09-04).
  Yang BOLEH diubah antar run dan dicatat: augmentasi (hsv/flip/mosaic) saja.
- Seed: 42 di sampling data; training seed default Ultralytics (deterministic=False — catat ini)

## Checklist anti-gagal T4 gratis
- [ ] Internet ON di notebook, GPU T4 terpilih (bukan CPU)
- [ ] Dataset ditambah via + Add Input (jangan upload 11 GB manual)
- [ ] Save interrupt: simpan best.pt ke /kaggle/working tiap run (output hilang bila sesi mati)
- [ ] Satu run besar per hari (kuota ±30 jam/minggu); prototipe Roma dulu sebelum run 8 jam
- [ ] Semua metrik + confusion matrix di-download (bahan tabel jurnal)

## Definisi "selesai training"
mAP50 test ≥ 0,65 DAN drop OOD Bandung < 15 poin DAN FPS ONNX di i5 ≥ 8. Bila belum:
tambah data lokal dulu (bukan tambah epoch buta).
