# Decision Log — Ablasi CBAM + YOLO26 (2026-09-04/05)

Pertanyaan: apakah sisipan attention CBAM atau arsitektur YOLO26 mengalahkan baseline YOLOv11n pada data RDD-only 15k?

## Setup (disamakan, fair)
- Data identik baseline B: train 12049 / val 2127 / test RDD full 5758 / seed 42.
- Resep identik: 50 epoch, patience 10, batch 16, imgsz 640, Tesla T4, ultralytics 8.4.138.
- CBAM disisip setelah C2PSA P5/32 backbone; transfer learning 240/502 layer cocok.
- Notebook: `notebooks/rdd-yolov11n.ipynb` Sel 12 (modul CBAM), Sel 13 (edit YAML terverifikasi assert), Sel 14 (train CBAM), Sel 15 (train YOLO26).

## Hasil (val, best.pt)

| Run | epoch best | P | R | mAP50 | mAP50-95 | best.pt | best.onnx |
|---|---|---|---|---|---|---|---|
| B baseline v11n | — | 0,6200 | 0,5463 | 0,5914 | 0,3059 | 5,2 MB | 10,1 MB |
| v11n + CBAM | 50 | 0,6140 | 0,5225 | 0,5687 | 0,2900 | 5,2 MB | 10,2 MB |
| YOLO26n | 46 | 0,6061 | 0,5327 | 0,5706 | 0,2988 | 5,1 MB | 9,4 MB |

Acuan baseline lain (tidak berubah): test mAP50 0,4702; OOD Bandung 0,5514. Per-kelas test mAP50-95 baseline: longitudinal 0,2018; transverse 0,1770; alligator 0,3079; other 0,3459; pothole 0,1708.

## Temuan confusion matrix (val)
- Tertukar antar-kelas KECIL (satu digit) di ketiga run → taksonomi 5 kelas bersih.
- Galat dominan = background: miss 260–400/kelas, false alarm 150–420/kelas. Ini EOQ berikutnya (bukan arsitektur): ambang conf, hard-negative mining, atau data lokal.
- CBAM sedikit lebih baik di transverse_crack (253 vs 228 benar) — satu-satunya sinyal positif CBAM, tapi tidak cukup mengubah ranking.

## Vonis (final 2026-09-05: val + test konsisten)
Baseline B (YOLOv11n) TETAP model final. CBAM −2,3 poin val / −1,8 poin test; YOLO26 −2,1 poin val / −1,9 poin test (mAP50). Gap test sedikit lebih kecil dari gap val — keunggulan baseline menyusut di data baru tapi tetap menang. Fakta pendukung skripsi: (1) loss YOLO26 memakai l1_loss vs dfl_loss di v11 — perbedaan objektif yang tercatat; (2) CBAM best di epoch 50 (kurva masih naik) vs YOLO26 plateau di 46 — dilaporkan apa adanya, bukan dijadikan alasan.

## Hasil TEST RDD full 5758 gambar (Kaggle T4, 2026-09-05)
Sel adaptasi Sel 8 (test saja — val sudah ada dari results.csv) + Sel A mandiri (`%%writefile cbam.py`, isi identik file training, tanpa Sel 12/14). Kendala yang dilewati: `ModuleNotFoundError: No module named 'cbam'` (solusi: tulis ulang cbam.py + registrasi `_T.CBAM`), `FileNotFoundError rdd-only.yaml` (solusi: run Sel 5 dulu).

| Run | TEST mAP50 | TEST mAP50-95 | P | R |
|---|---|---|---|---|
| B baseline v11n | 0,4702 | 0,2407 | 0,5670 | 0,4656 |
| v11n + CBAM | 0,4524 | 0,2304 | 0,5300 | 0,4624 |
| YOLO26n | 0,4517 | 0,2359 | 0,5592 | 0,4520 |

Per-kelas TEST mAP50-95 — baseline menang 5/5 vs CBAM, 4/5 vs YOLO26:

| Kelas | Baseline | CBAM | YOLO26 |
|---|---|---|---|
| longitudinal_crack | 0,2018 | 0,1916 | 0,2009 |
| transverse_crack | 0,1770 | 0,1589 | 0,1657 |
| alligator_crack | 0,3079 | 0,2968 | 0,3028 |
| other_corruption | 0,3459 | 0,3431 | 0,3334 |
| pothole | 0,1708 | 0,1617 | 0,1767 ← satu-satunya sel kemenangan non-baseline (+0,6 poin, sinyal kecil) |

## Hasil OOD Bandung 161 gambar (Kaggle T4, 2026-09-05) — ABLASI TERTUTUP
Sel adaptasi Sel 9 (prep bpid_eval reuse-or-build + eval 2 bobot; remap kelas 0→4 pothole, label utuh 161/161).

| Run | OOD mAP50 | OOD mAP50-95 | Δ vs baseline |
|---|---|---|---|
| B baseline v11n | 0,5514 | — | — |
| v11n + CBAM | 0,4934 | 0,2520 | −5,8 poin |
| YOLO26n | 0,4782 | 0,2498 | −7,3 poin |

Gap OOD (±6–7 poin) LEBIH BESAR dari gap val/test (±2 poin) → baseline generalisasi terbaik ke kondisi Indonesia. Ranking B > CBAM ≈ YOLO26 konsisten di SEMUA level (val + test + OOD). Tidak ada tindak lanjut tersisa untuk ablasi ini.

## Batasan kejujuran (final)
- Semua angka di atas memakai resep 50 epoch. Klaim "CBAM butuh epoch lebih" tidak diuji (butuh kuota baru) — dilaporkan sebagai future work, bukan kesimpulan.

## Artefak
- `artifacts/hasil-ablasi-cbam-yolo26-20260904-1534/` (runs/ + artifacts_ablasi/ + zip)
- Strategi: `docs/Strategi-Training.md` Tahap 2d
