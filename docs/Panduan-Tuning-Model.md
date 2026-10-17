# Panduan Tuning Model — JalanPantau

> **⚠️ Catatan (Okt 2026):** angka & perbandingan di bawah berasal dari model
> **pra-retrain** (saat itu live ONNX = YOLOv11n). Setelah retrain, model gambar
> **dan** live = **YOLOv11s**, dengan metrik terkini di `README.md`.
> Anggap dokumen ini catatan historis.

Tujuan: menaikkan mAP50 (target ≥ 0,65) dan **generalisasi OOD** tanpa retrain
membabi-buta. Urutkan berdasar (dampak ÷ usaha).

## Diagnosa (dari `reports/keputusan-ablasi-cbam-yolo26.md`)
- Galat dominan = **background**: miss 260–400/kelas, **false alarm 150–420/kelas**.
  Artinya model "melihat" kerusakan di tempat yang tidak ada → EOQ = data negatif +
  ambang, bukan arsitektur.
- **Gap OOD Bandung** (±3–4 poin mAP50 vs val/test) → butuh *domain adaptation*.
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


### 6c. Prosedur kalibrasi `toleransi_kelas` per kelas (2026-10-16)

Nilai saat ini (`config/inferensi.yaml`):

| Kelas | Ambang | Rasional |
|---|---|---|
| longitudinal_crack | 0.13 | AP50 menengah (0.582); retak tipis butuh ambang agak rendah |
| transverse_crack | 0.13 | sama seperti longitudinal |
| alligator_crack | 0.10 | AP50 baik (0.676); pola khas, FP relatif rendah |
| other_corruption | 0.10 | AP50 tertinggi (0.748) |
| pothole | 0.08 | AP50 terendah (0.513); keselamatan → recall diprioritaskan |

**Cara kalibrasi** (butuh dataset berlabel lokal, mis. BPID):

```bash
# 1. Sapuan ambang per kelas target, catat P/R/F1 per titik
.\.venv\Scripts\python scripts\evaluasi_model.py --data data/publik/bpid/test \
    --remap 0:4 --model best.pt --imgsz 640 --conf-list 0.05,0.08,0.10,0.13,0.15,0.20,0.25
```

**Aturan keputusan:**
1. Pilih ambang di **titik F1-optimal** per kelas (kolom "Titik F1-optimal" di output).
2. Untuk **pothole**, boleh 1–2 titik di bawah F1-optimal (recall > precision;
   lubang yang terlewat lebih berbahaya daripada false alarm).
3. Untuk kelas dengan **FP dominan** (banyak deteksi di background), naikkan 1–2 titik
   di atas F1-optimal.
4. Jangan ubah lebih dari satu kelas sekaligus tanpa mengukur ulang — interaksi
   antar-kelas via `iou_agnostik` bisa menggeser hasil.

**Catatan interaksi dengan filter baru (Okt 2026):**
- `rasio_aspek_min_retak: 1.5` di `batas_ukuran` sudah membuang sebagian FP retak
  (box near-square). Setelah filter ini aktif, ambang longitudinal/transverse
  *boleh* diturunkan sedikit bila recall dirasa kurang — ukur dulu dengan skrip di atas.


### 6d. Skala inferensi & bug FP16: kenapa foto besar bisa 0 temuan (2026-10-17)

Gejala: foto yang jelas rusak, confidence sudah diturunkan sampai **minimum 0,05**,
tetap "tidak ada temuan" — dengan pesan ratusan kandidat "ukuran tidak masuk akal"
(pernah 913).

> **Koreksi penting.** Versi pertama bagian ini (pagi 17 Okt) diukur lewat jalur
> **FP16 yang ternyata rusak**, sehingga angka "0 box @960" tidak sah. Semua angka
> di bawah sudah diukur ulang pada jalur FP32 (`half_gambar: false`).

#### Penyebab utama: FP16 + TTA menghasilkan box NaN

`half=True` (FP16) + `augment=True` (TTA) pada `imgsz_gambar: 960` meluap secara
numerik di GPU: model mengeluarkan box `[nan, nan, nan, nan]` yang tetap membawa
confidence tinggi.

| 4080x3060 @960, conf 0,01 | box | NaN |
|---|---|---|
| TTA + FP16 (setelan lama) | 107 | **102** |
| TTA + FP32 | 28 | **0** |
| tanpa TTA + FP16 | 0 | 0 |
| tanpa TTA + FP32 | 25 | 0 |

Rantai kerusakannya:
1. Box NaN masuk `wbf_gabung()` yang melebur dengan **rata-rata berbobot** → satu
   box NaN membuat seluruh box tetangganya NaN.
2. `masuk_akal()` membandingkan `NaN > 300` → selalu `False` → box dibuang dan
   dihitung sebagai "ukuran tidak masuk akal". Pesan UI jadi menyesatkan: bukan
   soal geometri, dan bukan salah penyaring.
3. Deteksi **asli** yang bertumpuk dengan box NaN ikut menjadi NaN → **hilang**.

Bukan hanya foto malam: foto **siang** 12 MP pun 89% box-nya NaN (16 dari 18).
Foto kecil (512x512) tidak terpengaruh karena tak ada overflow.

**Perbaikan:** `half_gambar: false` (FP32) untuk jalur gambar. Jalur live (imgsz
640, tanpa TTA) tetap FP16 karena terbukti 0 NaN dan hemat VRAM 4 GB.

| 000003.jpg (12,5 MP), conf 0,25 | FP16 | FP32 |
|---|---|---|
| temuan | 2 | **3** |
| `ukuran` ditolak | 34 | **2** |
| waktu (auto-tiling) | 47,9 dtk | **9,7 dtk** |

FP32 juga **lebih cepat** di sini: tensor penuh NaN membuat NMS/fusion lambat.

Selain itu `saring_rows()` kini menghitung kategori `rusak` terpisah, dan
`wbf_gabung()` / `prediksi_teliti()` membuang baris non-finite **sebelum** fusion.
Kalaupun bug serupa muncul lagi (model/driver lain), NaN tidak bisa menulari
temuan asli, tidak menyamar sebagai "ukuran tidak masuk akal", dan tidak bocor ke
JSON (browser gagal `JSON.parse` bila ada `NaN`).

**Kenapa confidence bukan tuasnya.** `conf_prediksi()` memanggil `predict()` di
`slider − maks(toleransi_kelas)` (≈ slider − 0,13, lantai 0,01). Slider 0,05 → model
sudah berjalan di conf 0,01: menurunkan slider tidak menambah apa yang *dilihat*
model, hanya melonggarkan penyaring setelahnya. Karena itu UI tidak lagi menyarankan
"turunkan confidence" bila slider sudah di batas bawah.

**Kenapa penyaring ukuran juga bukan penyebabnya.** Diuji dengan mematikan
`luas_min_px` dan `masuk_akal`: temuan akhir tidak bertambah (di beberapa foto
malah berkurang karena `gabung_fragmen` melebur lebih banyak box). Setelah bug FP16
diperbaiki, `ukuran` langsung anjlok (34 → 2; 12 → 0) tanpa mengubah penyaring —
bukti bahwa angka besar itu berasal dari NaN, bukan geometri.

#### Penyebab kedua (masih nyata): downscale

Setelah FP16 diperbaiki, jalur full-frame memang **tidak** buta — tetapi retak tipis
tetap kehilangan detail saat 12 MP dipaksa ke 960 (4,2x). Diukur ulang pada FP32,
conf 0,10:

| Foto | mentah @960 | mentah @1280 | full-frame | tiling |
|---|---|---|---|---|
| 4080x3060 (12,5 MP) | 28 | 32 | 2 (1,2 dtk) | **18** (9,1 dtk) |
| 3000x4000 (12,0 MP) | 21 | 47 | 4 (0,6 dtk) | **20** (5,0 dtk) |
| 4032x2268 ( 9,1 MP) | 12 | 17 | 2 (0,5 dtk) | **20** (4,6 dtk) |
| 1280x720  ( 0,9 MP) | 26 | 22 | 2 (0,2 dtk) | 5 (0,7 dtk) |
| 512x512   ( 0,3 MP) | 6 | 12 | 3 (0,3 dtk) | 3 (0,1 dtk) |

Tiling menambah recall terutama untuk **retak** (`longitudinal`/`transverse`), tetapi
box retak itu umumnya ber-confidence rendah (0,14–0,34). Jadi tiling adalah alat
**recall retak**, bukan penambah presisi.

Dua hal yang **tidak** dipakai:
1. **`imgsz_gambar` 1280** — menaikkan box mentah, tetapi memperbesar biaya untuk
   semua foto tanpa menjamin presisi. Tetap **960**.
2. **Tiling global** — pada 0,3–0,9 MP, tile 640 px memotong objek besar
   (`buang_tepi_tile`) dan menambah waktu tanpa manfaat sepadan.

**Yang diterapkan:**
- `half_gambar: false` — FP32 untuk jalur gambar (lihat di atas).
- `teliti.otomatis_aktif: true` + `otomatis_ambang: 2.0` → bila
  `max(w,h) > imgsz_gambar × 2` (> 1920 px pada 960), `analisis_gambar()` beralih
  ke tiling (`perlu_teliti_otomatis()`) dan mengembalikan `teliti_otomatis: true`.
- `disaring.rusak` — jumlah box NaN/Inf yang diabaikan (kategori baru).
- `gelap: true` bila rata-rata kanal L < 60 → UI menyarankan opsi
  "Pencahayaan Rendah / Malam" (model dilatih pada RDD2022 = siang).

**Biayanya jujur:** foto 12 MP full-frame ≈ 0,5–1,2 dtk, tiling 5–9 dtk (≈ 48 tile
640 px + lebur WBF). UI menyetel ekspektasi: "Gambar N MP — analisis foto besar bisa
15–30 detik…". Untuk foto ≤ 2 MP ambang 2x membuat tiling tak terpicu.

**Cara memastikan untuk satu foto tertentu** (sebelum mengubah config apa pun):

```bash
.\.venv\Scripts\python scripts\diag_teliti.py test_foto\foto.jpg
```

> Catatan: `scripts/diag_teliti.py` masih memakai `half_untuk()` (FP16) demi
> hemat VRAM, sedangkan aplikasi kini memakai FP32 di jalur gambar. Pada GPU,
> langkah [1] skrip itu bisa mencetak **0 box** karena overflow FP16 — jangan
> simpulkan "model buta" dari skrip sebelum skripnya disamakan dengan
> `half_gambar`.

Pesan "tanpa temuan" di UI kini menyebut `disaring.ambang` / `ukuran` / `mungil` /
`rusak`, dan menyesuaikan saran: tidak lagi menyuruh menurunkan confidence bila
slider sudah di batas bawah 0,05, dan tidak menyuruh mengaktifkan mode teliti bila
sudah aktif.

**Catatan jujur untuk laporan:** setelah bug FP16 diperbaiki, foto 12 MP yang
sebelumnya 0 temuan memberi 2–4 temuan full-frame dan 18–20 dengan tiling (conf
0,10). Tetapi **foto malam tetap lemah** — `000059.jpg` hanya 2 temuan berkualitas
rendah dan CLAHE tidak menyelamatkannya. Itu masalah domain/data (foto malam/lokal
tidak ada di data latih, §2), bukan tuning ambang. Solusinya retrain dengan data
lokal, bukan menurunkan ambang sampai noise lolos.
