# Penjelasan Artefak Rekonstruksi Run YOLOv11s Final

Dokumen ini menjelaskan asal-usul `args.rekonstruksi.yaml` dan
`results.rekonstruksi.csv` di folder ini.

## Mengapa perlu ada

Run `yolo11s-rdd-only` adalah **model akhir yang dipakai aplikasi** dan
satu-satunya run tanpa artefak training standar. Yang tersedia hanya
`results.png` (grafik), `best.zip`/`last.zip` (checkpoint PyTorch yang
di-zip), dan salinan notebook. Tidak ada `args.yaml` maupun
`results.csv`.

Akibatnya, kalau ditanya reviewer "apa hyperparameter training-nya?" atau
"kurva loss per epoch-nya seperti apa?", jawabannya hanya bisa diambil dari
teks di dalam file `.md`/`.ipynb`, yang tidak bisa dihitung ulang.

## Yang direkonstruksi, dari mana

| Isi | Sumber | Keyakinan |
|---|---|---|
| `model`, `epochs`, `imgsz`, `batch`, `patience`, `seed`, `cos_lr`, `mixup`, `copy_paste`, `save_period`, `name`, `project` | Panggilan `model.train()` di Sel 6 `rdd-yolov11s.ipynb` | **Tinggi** — ditulis eksplisit |
| Konstanta `IMGSZ=768`, `BATCH=16`, `EPOCHS=200`, `PATIENCE=40`, `SEED=42`, `MODEL_NAME=yolo11s.pt` | Sel 1 `rdd-yolov11s.ipynb` | **Tinggi** |
| Metrik per-epoch (box/cls/dfl loss, P, R, mAP50, mAP50-95, GPU mem, durasi) | Baris log di output Sel 6 | **Tinggi** untuk nilai yang tercetak |
| Seluruh parameter lain (augmentasi, optimizer, loss gain, dll.) | `args.yaml` run baseline YOLOv11n | **Sedang** — diwarisi, bukan diukur |
| Versi lingkungan | Header output Sel 7 | **Tinggi** |

## Environment (dari header Sel 7)

```
Ultralytics 8.4.142 · Python 3.12.13 · torch 2.10.0+cu128
CUDA:0 Tesla T4 (14912 MiB)
YOLO11s fused: 100 layers, 9.414.735 parameter, 21.4 GFLOPs
```

Baseline YOLOv11n yang dipakai sebagai kerangka `args` memakai
ultralytics **8.4.138** — berbeda empat patch version. Bila ada default
yang berubah di antara keduanya, baris yang diwarisi pada
`args.rekonstruksi.yaml` bisa stale. Cara memastikan: jalankan ulang
training lalu bandingkan dengan `args.yaml` asli yang dihasilkan
Ultralytics.

## Batasan yang harus dinyatakan kalau file ini dipakai di laporan

1. **Kolom `time` resmi tidak ada.** Ultralytics mencatat akumulasi waktu
   presisi tinggi; log hanya mencetak durasi per epoch (`4:01`) dan durasi
   validasi (`21.6s`). `time_est_s` di CSV ini adalah jumlah keduanya, jadi
   **estimasi**, bukan angka asli.

2. **`fitness_log` hanya akurat sampai sekitar 0,0005.** `mAP50` dicetak 3
   desimal dan `mAP50-95` 4 desimal di log. Karena itu `fitness_log` tidak
   boleh dipakai untuk membandingkan epoch yang selisihnya di bawah presisi
   tersebut.

3. **Epoch "best" tidak bisa dibaca dari log.** Epoch 87-92 dan 131 memiliki
   metrik yang identik setelah dibulatkan (mAP50 0,648 dan mAP50-95 0,3460).
   Angka **91** pada `args.rekonstruksi.yaml` berasal dari aritmetika
   early-stop (`131 - patience 40 = 91`), bukan dari perbandingan fitness.
   Ini konsisten dengan aturan Ultralytics yang menghentikan training saat
   `epoch - best_epoch >= patience`, tapi ia tetap **turan**, bukan pembacaan
   langsung.

4. **`instances` per epoch bukan jumlah ground-truth.** Kolom itu berisi
   jumlah instance yang seen per batch pada baris log; ground truth ada di
   kolom `val_instances` (4.059 untuk val).

5. **Angka ini bukan pengganti `results.csv` asli.** Kalau suatu saat artefak
   asli dari Kaggle ditemukan, gunakan itu dan hapus file rekonstruksi ini.

## Konsistensi silang

Nilai berikut dari dokumen lain di repo sudah cocok dengan hasil
ekstraksi, jadi rekonstruksi ini tidak bertentangan dengan yang sudah
dipublikasikan:

| Sumber | Nilai | Cocok |
|---|---|---|
| Sel 7 (evaluasi `best.pt`) | val mAP50 0,648 · mAP50-95 0,346 | Ya |
| `README.md` | val mAP50 0,6483 | Ya (pembulatan log 3 desimal) |
| `README.md` / analisis | 131 epoch efektif | Ya |
| `README.md` | wall time 9,55 jam | Ya (estimasi 9 jam 31 menit + waktu val yang tidak tercetak penuh) |

## Cara memperbarui

Kalau training diulang, ganti file rekonstruksi ini dengan `args.yaml` dan
`results.csv` asli dari folder run Ultralytics, lalu hapus dokumen ini.
Jangan menyimpan dua sumber yang berbeda tanpa catatan.
