# Panduan Tuning Model — JalanPantau

Tujuan: menaikkan mAP50 (target ≥ 0,65) dan **generalisasi OOD** tanpa retrain
membabi-buta. Urutkan berdasar (dampak ÷ usaha).

## Diagnosa (dari `reports/keputusan-ablasi-cbam-yolo26.md`)
- Galat dominan = **background**: miss 260–400/kelas, **false alarm 150–420/kelas**.
  Artinya model "melihat" kerusakan di tempat yang tidak ada → EOQ = data negatif +
  ambang, bukan arsitektur.
- **Gap OOD Bandung besar** (±6–7 poin mAP50 vs val/test) → butuh *domain adaptation*.
- Rata-rata mAP menyembunyikan kelas lemah (longitudinal/transverse) → **laporkan per-kelas**.

## Urutan eksperimen
1. Hard-negative mining (murah, dampak besar)
2. Fine-tune data lokal Bandung (sedang, dampak besar untuk OOD)
3. Pseudo-labeling / self-training (menambah data tanpa anotasi penuh)
4. Hyperparameter (sedang)
5. Arsitektur (mahal — CBAM/YOLO26 sudah terbukti kalah, jangan diulang)

---

## 1. Hard-negative mining
Tambahkan gambar **jalan tanpa kerusakan** (background) ke training dengan label
**kosong** (`.txt` kosong). Ini menekan false alarm.

- Kumpulkan 300–1000 foto: aspal baik, marka, bayangan, pola non-kerusakan, kondisi Bandung.
- Simpan `train/images/<nama>.jpg` + `train/labels/<nama>.txt` (kosong).
- Ultralytics otomatis memperlakukannya sebagai background.
- Ukur efeknya: false alarm per kelas turun? mAP naik?

## 2. Domain adaptation (data lokal)
- Label 200–500 foto jalan Bandung (kelas sama) dengan anotator (CVAT/LabelImg/roboflow).
- Fine-tune dari bobot terbaik (bukan dari `yolo11n.pt`) dengan LR kecil.
- Uji: mAP OOD Bandung harus naik; kalau turun, data lokal terlalu sedikit/berisik.

## 3. Pseudo-labeling (semi-supervised)
1. Jalankan model terbaik pada banyak foto lokal **tanpa label** dengan conf tinggi (mis. 0,5).
2. Simpan deteksi sebagai label; **verifikasi/bersihkan manual** (koreksi cepat).
3. Latih ulang dengan data asli + pseudo-label. Ulangi 1–2 putaran.
- Hati-hati *confirmation bias*: selalu sisihkan set uji yang tidak pernah dipakai pseudo-label.

## 4. Hyperparameter (rekomendasi)
| Param | Nilai | Alasan |
|---|---|---|
| `optimizer` | `AdamW` | stabil untuk fine-tune |
| `lr0` | 0,001 (fine-tune) / 0,01 (from scratch) | hindari lupa bobot |
| `cos_lr` | `True` | penurunan halus |
| `epochs` | 100–150 | kurva CBAM masih naik di epoch 50 |
| `patience` | 25 | early stopping hemat kuota |
| `imgsz` | 960 (gambar statis) | retak tipis |
| `close_mosaic` | 15 | matikan mosaic di akhir |
| `label_smoothing` | 0,05 | kurangi overconfidence |
| `weight_decay` | 0,0005 | regularisasi |
| `copy_paste` | 0,3 | objek kecil (pothole) |

## 5. Evaluasi (protokol)
- **Per-kelas** mAP50 & mAP50-95, bukan hanya rata-rata.
- **Test RDD full** + **OOD Bandung** + (bila ada) **lokal**.
- **Multi-seed** (3 seed) → laporkan mean ± simpangan baku.
- Simpan `results.csv` tiap run ke `artifacts/` (bukti provenance).
- Latensi: `scripts/benchmark_inferensi.py`.

## Pelaporan jujur
- Laporkan n sampel & sebaran kelas; jangan klaim umum dari sedikit data.
- Selisih antar-run < 1 poin bisa noise — jangan dijadikan kesimpulan.
- Arsitektur yang kalah (CBAM/YOLO26) tetap dilaporkan.

## Berkas terkait
- Template siap-tempel: `notebooks/template-kaggle-hard-negative-finetune.md`
- Baseline & ablasi: `reports/keputusan-ablasi-cbam-yolo26.md`, `artifacts/`
- Benchmark: `scripts/benchmark_inferensi.py`

---

## 6. Tuning ambang & pilihan model dengan data lokal (tanpa retrain)

Alat: `scripts/evaluasi_model.py` — evaluasi pada dataset berlabel lokal (mis. BPID),
mendukung `--remap` (BPID: kelas 0 → 4 pothole), dan **sapuan conf-floor**.

```bash
.\.venv\Scripts\python scripts\evaluasi_model.py --data data/publik/bpid/test --remap 0:4 \
    --model best.onnx --imgsz 640 --conf-list 0.001
.\.venv\Scripts\python scripts\evaluasi_model.py --data data/publik/bpid/test --remap 0:4 \
    --model best_yolo11s.pt --imgsz 960 --conf-list 0.001
```

**Hasil BPID (161 gambar, 263 instance pothole), 2026-09-30:**

| Model | mAP50 | mAP50-95 | Titik F1-optimal (P/R/F1) |
|---|---|---|---|
| `best.onnx` (YOLOv11n) @640 | **0.5557** | 0.2742 | 0.571 / 0.574 / **0.5726** |
| `best_yolo11s.pt` @960 | 0.4587 | 0.2316 | 0.513 / 0.497 / 0.5046 |

**Interpretasi (penting):**
- **Laporkan mAP pada conf-floor rendah** (mis. 0.001). Parameter `conf` di ultralytics
  `val()` hanya **batas bawah kurva PR**; mengukur di conf 0.25 membuat mAP tampak lebih
  rendah (di BPID: 0.4875 @0.15 vs 0.5557 @0.001). Conf aplikasi = **ambang operasi**, bukan
  parameter metrik.
- **Titik operasi terbaik** ≈ P 0.57 / R 0.57 (v11n) — setara conf kira-kira **0.15–0.20**.
  Default aplikasi 0.25 agak konservatif (precision naik, **recall turun**). Untuk pothole
  (keselamatan), recall tinggi lebih diinginkan.
- **Di Bandung (OOD), YOLOv11n ONNX mengalahkan YOLOv11s** (0.5557 vs 0.4587; F1 0.573 vs
  0.505) — **konsisten** dengan catatan OOD repo (v11n 0.5514 vs v11s 0.4516). Trade-off:
  v11s unggul **in-domain** (RDD test 0.526 vs 0.470), jadi jalur gambar memakai v11s+TTA.
- **Catatan kejujuran:** `val()` ultralytics **tidak** memakai TTA, sedangkan jalur gambar
  aplikasi memakai TTA → angka v11s di atas bisa lebih tinggi saat runtime. Ukur versi TTA
  sebelum mengubah model.

**Tindak lanjut yang bisa dipilih (semua tanpa retrain):**
1. Turunkan conf default, atau tambah `toleransi_kelas.pothole` (mis. 0.08) agar ambang
   efektif pothole ≈ 0.17 dan recall naik.
2. Uji `best.onnx` (v11n) sebagai `model_gambar` bila target utama Bandung.
3. Nyalakan `ensemble` (v11s + v11n, WBF) lalu ukur dengan skrip ini.

### 6b. Efek TTA (diukur dengan `scripts/evaluasi_tta.py`)

`val()` ultralytics tidak memakai TTA, jadi dibuat skrip P/R/F1 berbasis pencocokan IoU 0.5
yang mendukung `--augment`. Subset sama (40 gambar BPID, conf 0.25):

| Konfigurasi | Precision | Recall | F1 | detik/gambar |
|---|---|---|---|---|
| v11n ONNX @640 (tanpa TTA) | **0.4824** | 0.5467 | **0.5125** | **0.76** |
| v11s @960 tanpa TTA | 0.3711 | 0.4800 | 0.4186 | 2.13 |
| v11s @960 **+ TTA** | 0.3636 | **0.6933** | 0.4771 | 4.97 |

**Kesimpulan (mengoreksi klaim sebelumnya):**
- **TTA memang berharga untuk recall**: R 0.48 → **0.69** (F1 +0.06) dengan biaya 2,3× waktu.
  Untuk pothole (keselamatan), ini penting → pilihan `tta: true` di jalur gambar **tepat**.
- Perbandingan model bukan sekadar "v11n menang": **v11n menang F1 & kecepatan** (0.5125; 0.76 s),
  **v11s + TTA menang recall** (0.6933) tapi paling lambat & presisi terendah (false alarm).
- Jadi keputusan model bergantung tujuan: **deteksi statis yang mengejar recall → v11s+TTA**;
  **live/kecepatan → v11n ONNX** (sudah dipakai). Bila butuh keduanya: coba `ensemble` (v11s+TTA
  + v11n) lalu ukur dengan skrip ini.
- Catatan: pengukuran ini di `conf` seragam 0.25; aplikasi kini memakai ambang pothole 0.17 →
  recall aktual lebih tinggi lagi.


