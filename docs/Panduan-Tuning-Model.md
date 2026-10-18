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
| `imgsz` | 960 (gambar statis) | retak tipis; **latihan ≠ inferensi** — aplikasi memakai `imgsz_gambar: 640` dan itu yang terbukti lebih baik pada data lokal (§6d). Kalau ingin skala latih = skala infer, uji dulu |
| `close_mosaic` | 15 | matikan mosaic di akhir |
| `label_smoothing` | 0,05 | kurangi overconfidence |
| `weight_decay` | 0,0005 | regularisasi |
| `copy_paste` | 0,3 | objek kecil (pothole) |

---

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
- Evaluasi pipeline aplikasi (TTA + saring + fragmen + gate): `scripts/evaluasi_pipa_app.py`

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
  Default aplikasi saat analisis ini (0,25) agak konservatif (precision naik, **recall turun**);
  sejak 18 Okt 2026 default menjadi 0,30 (`web/app.py CONF_DEFAULT`, lihat §6d). Untuk pothole
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
- Catatan: pengukuran ini di `conf` seragam 0.25. **Koreksi 18 Okt 2026:** setelan
  aplikasi kini `imgsz_gambar: 640` dan ambang pothole 0,25 (bukan 960 / 0,17), jadi
  tabel ini bukan lagi deskripsi setelan terkini. Pada 161 gambar BPID berlabel,
  640 memberi F1 0,630 vs 0,536 untuk 960 — konsisten dengan tabel di sini, di mana
  v11n @640 (F1 0,5125) mengalahkan v11s @960+TTA (0,4771). Lihat §6d.


### 6c. Prosedur kalibrasi `toleransi_kelas` per kelas (2026-10-16)

Nilai saat ini (`config/inferensi.yaml`):

| Kelas | Ambang | Rasional |
|---|---|---|
| longitudinal_crack | 0.13 | AP50 menengah (0.582); retak tipis butuh ambang agak rendah |
| transverse_crack | 0.13 | sama seperti longitudinal |
| alligator_crack | 0.10 | AP50 baik (0.676); pola khas, FP relatif rendah |
| other_corruption | 0.10 | AP50 tertinggi (0.748) |
| pothole | 0 (sebelumnya 0,08) | **diukur ulang 18 Okt 2026 di BPID**: lowering 0,08 → ambang efektif 0,17 → P 0,324 / R 0,688 / **F1 0,440**; tanpa lowering (ambang 0,25) → P 0,546 / R 0,677 / **F1 0,604**; F1 optimum ada di conf 0,35 (P 0,629 / R 0,631). Lihat §6d |

**Koreksi 18 Okt 2026 — APT "recall > precision" TIDAK berlaku untuk pothole.**
Aturan keputusan poin 2 di bawah ditulis 16 Okt berdasarkan AP50 model, tanpa
ground truth lokal. Setelah BPID punya label, lowering 0,08 ternyata **menurunkan**
F1 (0,440 vs 0,604), bukan menaikkannya: kerikil, daun, dan bayangan jauh lebih
banyak yang lolos ambang longgar. Untuk pothole, false alarm dari kerikil lebih
merusak secara operasional daripada satu pothole yang terlewat, jadi aturan 2
dibalik untuk kelas ini.

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
| waktu (mode teliti) | 47,9 dtk | **9,7 dtk** |

FP32 juga **lebih cepat** di sini: tensor penuh NaN membuat NMS/fusion lambat.
(Kedua angka mode teliti kini tidak relevan sebagai setelan default — mode teliti
sudah dicabut otomatis; lihat bagian "Penyebab ketiga" di bawah.)

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

#### Penyebab kedua: skala inferensi — 960 terlalu besar (diperbaiki 18 Okt 2026)

Model dilatih pada **imgsz 768** (`yolov11s-rdd-only/args.rekonstruksi.yaml`, baris
`imgsz: 768`; kolom `imgsz` di `results.rekonstruksi.csv` juga 768). Jalur gambar
sementara memakai 960 — 192 px di atas skala latih. Yang terjadi: kerikil, daun, dan
bayangan makin mudah terbaca pothole, tanpa recall yang bertambah.

Diukur di BPID (161 gambar berlabel, 263 GT pothole, IoU 0,5, +TTA, FP32):

| `imgsz_gambar` | P @0,25 | R @0,25 | F1 terbaik | recall GT besar | recall GT kecil |
|---|---|---|---|---|---|
| **640** | **0,546** | **0,677** | **0,630** (conf 0,35) | **79%** | 47% |
| 768 (= skala latih) | 0,506 | 0,650 | 0,571 (conf 0,30) | 75% | 47% |
| 960 (setelan lama) | 0,409 | 0,635 | 0,536 (conf 0,40) | 66% | **58%** |
| 960 tanpa TTA | 0,410 | 0,502 | 0,462 (conf 0,40) | 39% | 67% |

Kesimpulan: **`imgsz_gambar` 640** (bukan 960) — F1 +18% relatif, recall pothole besar
+13 poin, dan lebih cepat. Ini juga mengoreksi catatan 7 Sep 2026 di bagian atas
file ini ("imgsz 960 menemukan 1,5-5x lebih banyak temuan") — banyak kotak **bukan**
recall yang lebih baik; terhadap ground truth, 960 justru lebih buruk.

> **Trade-off yang perlu disebut terang-terangan:** recall **objek kecil** justru
> lebih tinggi di 960 (58% vs 47%). Pothole kecil praktis sepadan dengan retak tipis,
> jadi ada risiko nyata bahwa 640 memotong recall retak. Pemeriksaan ini **belum
> bisa ditutup di mesin ini**: label RDD2022 hanya ada di Kaggle
> (`/kaggle/input/.../RDD_SPLIT`), sedangkan BPID hanya berlabel pothole — jadi
> tabel di atas sah untuk pothole saja. Yang bisa dilakukan:
> (1) jalankan `scripts/evaluasi_model.py` di Kaggle pada split val RDD dengan
> `--imgsz 640` vs `--imgsz 960`, lalu bandingkan kolom per-kelas crack;
> (2) sampai itu selesai, **jangan** menaikkan `imgsz_gambar` hanya demi "lebih
> aman" — angka di atas menunjukkan 960 justru menurunkan F1 pothole.

Perintah untuk menutup pengukuran itu di Kaggle (split **yang sama dengan saat
training**, yaitu `/kaggle/working/rdd_only` — bukan `RDD_SPLIT` mentah yang `nc: 4`):

```bash
# imgsz 640 (setelan aplikasi) vs 960 (setelan lama), ambang conf sama
python scripts/evaluasi_model.py --data /kaggle/working/rdd_only --model best.pt \
    --imgsz 640 --conf-list 0.05,0.10,0.25,0.35
python scripts/evaluasi_model.py --data /kaggle/working/rdd_only --model best.pt \
    --imgsz 960 --conf-list 0.05,0.10,0.25,0.35
# TANPA --remap: kelas di rdd_only sudah 0..4 sesuai model. Bandingkan kolom
# longitudinal/transverse/alligator pada ambang yang sama. Kalau retak jelas
# turun di 640, pertimbangkan 768 (F1 pothole 0,571 — di antara keduanya).
```

Kalau tidak ada akses Kaggle, alternatifnya: labelkan ~100 foto retak lokal
(Gradio/LabelImg, format YOLO `class cx cy w h` dengan kelas 0/1/2 sesuai
`nama_kelas`), taruh sebagai `images/` + `labels/`, lalu jalankan perintah yang sama
dengan `--data <folder itu>`. Format persis: satu baris per instance.

#### Penyebab ketiga: mode teliti (tiling) — bukan cocok untuk jalur gambar

Dulu ada pemicu otomatis: foto dengan sisi > `imgsz × 2` otomatis dipecah jadi
tile 640 px (tiap tile di-upscale ke `imgsz_tile` 960). Diukur pada 129 gambar
BPID yang GT-nya > 600 px (kelas pothole, IoU 0,5, ambang 0,17):

| jalur | TP | FP | FN | P | R | F1 | dtk/gambar | recall GT besar |
|---|---|---|---|---|---|---|---|---|
| **A** full-frame @960 + TTA (dulu jadi default) | 157 | 347 | 68 | 0,312 | 0,698 | 0,431 | 0,12 | 71% |
| B tiling 640→960 apa adanya | 5 | 705 | 220 | 0,007 | 0,022 | 0,011 | 2,56 | **0%** |
| C tiling 640→960 tanpa aturan buang-tepi | 7 | 847 | 218 | 0,008 | 0,031 | 0,013 | 2,56 | **0%** |
| D gabungan A + C | 158 | 1181 | 67 | 0,118 | 0,702 | 0,202 | 2,68 | 71% |

Tiga sebabnya:
1. **Magnifikasi 1,5×.** Tile 640 px di-upscale ke 960 → kerikil tampak 1,5× lebih
   besar dan terbaca pothole (foto `000006.jpg`: 2 temuan full-frame → 16 temuan
   tiling, hampir semuanya batu).
2. **Konteks hilang.** Di dalam tile 640 px, pothole besar (>632 px) memenuhi
   hampir seluruh bidang pandang — model tidak melihat "lubang di dalam jalan".
   Pada `46bee6fc.jpeg` (GT 926×768 dan 1099×550 px), **0 dari 54 tile** melihat
   pothole itu utuh, jadi mustahil lolos `buang_tepi_tile`.
3. **21× lebih lambat** (0,12 → 2,56 dtk/gambar) untuk hasil yang nyaris nol.

Yang dikoreksi dari hipotesis sebelumnya: penyebab utama **bukan** aturan
`buang_tepi_tile`. Melepas aturan itu (B → C) hanya menaikkan TP dari 5 ke 7
sementara menambah 142 FP. Aturan itu tetap dipertahankan karena berguna untuk
menekan duplikat lintas tile, hanya bukan penyebab kebutaan.

**Kesimpulan & tindakan:** pemicu otomatis **dicabut** (18 Okt 2026). Mode teliti
tetap ada sebagai kotak centang manual untuk eksperimen recall retak, tapi tidak
lagi diaktifkan sendiri, dan UI tidak lagi menyarankannya.

#### Preset live "akurat" (960): label menyesatkan, metrik kumulatif menipu (2026-10-18)

Preset live `akurat` (`imgsz_live: 960`) diukur di desktop user (i5-3470 + GTX 1650,
video yang sama sampai selesai): inferensi 12,2 FPS vs 45,5 FPS (halus/320) vs
22 FPS (seimbang/640); "titik unik" 17 vs 41 vs 33; "deteksi aktif" 193 vs 816
vs 686. Kelihatannya akurat paling buruk — dan memang buruk, tapi angkanya
menipu karena dua sebab:

1. **Metriknya kumulatif.** "Deteksi aktif" (`n_deteksi`) dan "titik unik"
   (`len(tracks)`) adalah total sepanjang sesi. Mode lambat menginferensi ~4x
   lebih sedikit frame dalam durasi yang sama, jadi otomatis kalah angka tanpa
   mencerminkan kualitas per frame.
2. **960 memang lebih buruk untuk model ini** (§ "Penyebab kedua" di atas):
   F1 0,536 vs 0,630 di 640. Label "Akurat" tidak terbukti pengukuran.

Tindakan (18 Okt 2026):
- Label UI: "Akurat (FPS rendah)" → "Resolusi tinggi (FPS rendah)";
  "Halus (FPS tinggi, akurasi turun)" → "Halus (FPS tinggi)" (klaim penurunan
  akurasi di 320 belum diukur); catatan terukur ditampilkan di bawah dropdown.
- Metrik adil: `stats()` kini menyertakan `n_inferensi` dan `rata_deteksi`
  (deteksi per inferensi) — apel-ke-apel antar mode; metrik kumulatif dilabeli
  "total sesi" di UI.
- Preset 960 **dipertahankan** (bukan dihapus): recall objek sangat kecil 58%
  vs 47% di 640 — berguna untuk kasus retak tipis, hanya bukan default dan
  bukan "akurat".

#### Ambang pothole: lowering 0,08 justru merusak

`conf_prediksi()`/`ambang_efektif()` memakai `slider − toleransi_kelas`. Nilai lama
`pothole: 0.08` membuat ambang efektif 0,17 pada slider 0,25 (dibuat 30 Sep 2026 dari
"recall naik" pada 3 foto **tanpa ground truth**). Dengan label BPID:

| ambang efektif pothole | P | R | F1 |
|---|---|---|---|
| 0,17 (toleransi 0,08) | 0,324 | 0,688 | 0,440 |
| 0,25 (toleransi 0) — **sekarang** | 0,546 | 0,677 | 0,604 |
| 0,35 (F1 optimum) | **0,629** | 0,631 | **0,630** |

Jadi `toleransi_kelas.pothole` → **0**. Keluhan operator "batu/daun terbaca pothole"
sebagian besar berasal dari ambang yang terlalu longgar ini. Toleransi retak belum
diukur ulang (BPID tidak berlabel retak) — biarkan dulu, jangan ikut diturunkan.

#### Sapuan ambang per kelas di RDD val: toleransi retak terukur (18 Okt 2026)

Berawal dari temuan operator: pada satu foto, slider 0,20 menangkap 3 true positive
(alligator 0,11/0,12, other 0,17) yang dibuang slider default 0,30. Notebook
`~/workspace/sweep_ambang_per_kelas.ipynb`: inferensi **sekali** @conf 0,01
(imgsz 640, +TTA, FP32), sapuan 9 ambang di Python, matching IoU 0,5 per kelas —
val RDD n=5758 gambar (GT: longitudinal 3890, transverse 1769, alligator 1553,
other 1564, pothole 965):

| kelas | ambang F1-opt | P | R | F1 | toleransi lama → baru |
|---|---|---|---|---|---|
| longitudinal_crack | 0,30 | 0,687 | 0,531 | 0,599 | 0,13 → **0,0** |
| transverse_crack | 0,25 | 0,637 | 0,553 | 0,592 | 0,13 → **0,05** |
| alligator_crack | 0,25 | 0,705 | 0,661 | 0,682 | 0,10 → **0,05** |
| other_corruption | 0,35* | 0,754 | 0,735 | 0,744 | 0,10 → **tunda** |
| pothole | 0,20 | 0,604 | 0,515 | 0,556 | 0 → **tunda** |

\* Optimum tepat di tepi sapuan dan kurva masih naik — kemungkinan optimum
sebenarnya >0,35. Perlu sapuan lanjutan (0,40/0,45/0,50); cache inferensi sudah
ada sehingga tanpa GPU tambahan.

**Dua hal yang ditahan jujur:**
1. `other_corruption` menunggu sapuan lanjutan (lihat \*).
2. `pothole`: **SELESAI 18 Okt 2026** — konflik RDD val (optimum 0,20) vs BPID
   (optimum 0,35) diselesaikan dengan menjalankan notebook yang *sama* di BPID
   (161 gambar, REMAP {0:4}, 263 GT): F1 masih naik di 0,35 (0,620; P 0,605 /
   R 0,635). Jadi bedanya **dataset, bukan metodologi** — dua metodologi
   berbeda di BPID sepakat (≥0,35). Domain target aplikasi = jalan Indonesia →
   ikut BPID: `pothole` **tetap 0**. (Optimum tepatnya mungkin >0,35, tetapi
   itu tidak mengubah keputusan: toleransi tidak bisa negatif.)

Catatan metodologi: sapuan ini memakai deteksi mentah model (tanpa filter
geometri `saring_rows` aplikasi yang membuang FP) — sehingga ambang optimumnya
cenderung konservatif (arah aman). Validasi akhir tetap di foto asli operator.

#### Ringkasan yang diterapkan (18 Okt 2026)

**Hasil akhir — aplikasi sungguhan di 161 gambar BPID** (slider sesuai default app,
IoU 0,5, kelas pothole, 263 GT, 0 gambar gagal, JSON bebas NaN):

| konfigurasi | TP | FP | FN | P | R | **F1** | dtk/gambar | recall GT besar | recall GT kecil |
|---|---|---|---|---|---|---|---|---|---|
| **lama** (imgsz 960 + toleransi 0,08 + oto-tiling) | 9 | 695 | 254 | 0,013 | 0,034 | **0,019** | 3,13 | **1%** | 8% |
| **sekarang** (imgsz 640 + toleransi 0 + fragmen 0,30/0,50 + slider 0,30) | 157 | 90 | 106 | 0,636 | 0,597 | **0,616** | **0,58** | **70%** | 41% |

F1 naik **32×**, false positive turun 87% (695 → 90), recall pothole besar naik dari
1% menjadi 70%, dan waktu turun 5,4×. Angka ini yang dipakai untuk keputusan —
bukan jumlah kotak per foto.

| Perubahan | Dasar bukti |
|---|---|
| `imgsz_gambar: 960 → 640` | F1 0,536 → 0,630 pada BPID (§6d) |
| `toleransi_kelas.pothole: 0.08 → 0` | F1 0,440 → 0,604 pada ambang slider 0,25 |
| **`gabung_fragmen` 0,05/0,30 → 0,30/0,50** | F1 0,567 → 0,597 di ambang 0,25; recall 0,563 → 0,601 (audit penyaring di bawah) |
| **Default slider 0,25 → 0,30** (`web/app.py CONF_DEFAULT`) | recall tetap 0,597, FP 108 → 90, F1 0,597 → 0,616 |
| `half_gambar: false` (FP32, jalur gambar) | box NaN hilang, 0,19–0,68 dtk lebih cepat |
| Oto-tiling dicabut (config + kode) | F1 0,011 vs 0,431; recall pothole besar 0% |
| `MemoryError`/OOM → 503 (bukan 500) | RAM habis saat decode 12 MP bikin klien dapat halaman HTML debugger |
| `disaring.rusak` | box NaN tak lagi menyamar jadi "ukuran tidak masuk akal" |
| `gelap: true` | saran CLAHE untuk foto gelap (model dilatih RDD2022 = siang) |
| Pesan "tanpa temuan" kontekstual | tak lagi menyuruh turunkan conf saat slider sudah 0,05 |

Contoh nyata (foto dari BPID yang sebelumnya gagal):

| foto | lama | sekarang |
|---|---|---|
| `46bee6fc.jpeg` (2 pothole besar) | 18 temuan, **0 benar**, 8–9 dtk | conf 0,25 → 1 benar (kotak 1032×825 px ≈ pothole 81 cm); conf 0,05 → **2 benar**; 0,5 dtk |
| `486ceedd.jpeg` | 3 temuan, **0 benar** | 2 temuan, **1 benar** |
| `000006.jpg` (kerikil, tanpa GT) | 16 "pothole" pada batu | **0 temuan** pada conf 0,25 |

#### Audit penyaring hilir (P1, 18 Okt 2026)

F1 model polos pada setelan yang sama adalah 0,630, sedangkan melewati pipeline
aplikasi menjadi 0,567. Selisih ~0,06 F1 itu traced dengan **ablasi satu penyaring
per satu** (161 gambar BPID, slider 0,25, IoU 0,5, kelas pothole) — bukan dengan
tebakan:

| varian | TP | FP | P | R | F1 | recall GT besar / kecil |
|---|---|---|---|---|---|---|
| BASE (semua penyaring aktif) | 148 | 111 | 0,571 | 0,563 | 0,567 | 65% / 40% |
| `luas_min_px: 900` dimatikan | 148 | 111 | 0,571 | 0,563 | 0,567 | **tidak ada efek** |
| `maks_temuan: 20` dimatikan | 148 | 111 | 0,571 | 0,563 | 0,567 | **tidak ada efek** |
| `masuk_akal` dimatikan | 148 | 111 | 0,571 | 0,563 | 0,567 | **tidak ada efek** |
| **`gabung_fragmen` dimatikan** | **178** | 149 | 0,544 | **0,677** | **0,603** | **79% / 47%** |
| slider 0,20 | 149 | 126 | 0,542 | 0,567 | 0,554 | 66% / 40% |
| slider 0,30 | 149 | 92 | 0,618 | 0,567 | 0,591 | 66% / 39% |

Tiga pelajaran:
1. **Penyaring yang paling mahal adalah `gabung_fragmen`.** Aturan lamanya
   (`iou_min: 0.05` **atau** 30% kotak kecil berada di dalam kotak besar)
   menganggap dua pothole yang **berdampingan** sebagai fragmen satu kerusakan, lalu
   menyatukannya jadi satu box. Akibatnya satu pothole GT hilang dari hitungan —
   recall turun 11 poin (0,563 → 0,677 kalau dimatikan) dan recall pothole besar
   14 poin (65% → 79%).
2. **`luas_min_px`, `maks_temuan`, `masuk_akal` tidak memakan recall di dataset ini**
   (hasil identik sampai digit terakhir). Ketiganya mungkin berguna untuk kelas retak
   atau foto ekstrem, tapi **tidak boleh diklaim sebagai peningkatan kualitas** —
   buktinya nol pada 161 gambar berlabel.
3. **Slider 0,30 menang telan atas 0,25**: recall tetap 0,567, FP turun 111 → 92.
   Karena itu default slider dinaikkan ke 0,30 (lihat `web/app.py CONF_DEFAULT`).

 Setelan `gabung_fragmen` yang dipakai, diukur silang (8 varian × 2 ambang):

| slider | `iou_min` / `inter_min` | TP | FP | P | R | **F1** | recall besar/kecil |
|---|---|---|---|---|---|---|---|
| 0,25 | 0,05 / 0,30 (lama) | 148 | 111 | 0,571 | 0,563 | 0,567 | 65% / 40% |
| 0,25 | 0,30 / 0,50 | 158 | 108 | 0,594 | 0,601 | 0,597 | 70% / 42% |
| 0,25 | 0,20 / 0,80 | 158 | 110 | 0,590 | 0,601 | 0,595 | 70% / 42% |
| 0,25 | dimatikan | 178 | 149 | 0,544 | 0,677 | 0,603 | 79% / 47% |
| 0,30 | 0,05 / 0,30 (lama) | 149 | 92 | 0,618 | 0,567 | 0,591 | 66% / 39% |
| **0,30** | **0,30 / 0,50 (dipakai)** | 157 | **90** | **0,636** | 0,597 | **0,616** | 70% / 41% |
| 0,30 | 0,20 / 0,80 | 157 | 91 | 0,633 | 0,597 | 0,614 | 70% / 41% |
| 0,30 | dimatikan | 171 | 120 | 0,588 | 0,650 | 0,617 | 76% / 44% |

Kenapa **tidak** mematikan fiturnya padahal F1-nya nyaris sama (0,617 vs 0,616):
mematikannya memberi recall +5 poin, tetapi FP **+33%** (90 → 120) dan precision
turun (0,636 → 0,588), serta satu konsekuensi yang tidak bisa diukur di sini —
Berita-Acara akan menghitung satu kerusakan yang terpecah jadi beberapa box sebagai
beberapa kerusakan terpisah, sehingga skor prioritas terhitung dobel. Kalau nanti
terbukti recall jauh lebih penting dan kita siap menerima FP lebih banyak,
`aktif: false` cukup satu baris config.

Catatan jujur soal "recall kecil lebih rendah": di BPID, pothole kecil justru lebih
sulit dibedakan dari kerikil, sehingga menurunkan ambang untuk menaikkan recall kecil
menambah FP lebih banyak daripada pothole yang ditemukan — itu gejalanya domain gap,
bukan sekadar setelan angka.

#### Cara memastikan untuk satu foto tertentu

```bash
.\.venv\Scripts\python scripts\diag_teliti.py test_foto\foto.jpg
```

> Skrip ini hanya relevan untuk mode teliti (yang kini manual) dan masih memakai
> `half_untuk()` (FP16) — bukan setelan jalur gambar. Untuk menilai jalur gambar,
> andalkan P/R/F1 di atas, bukan jumlah kotak.

**Catatan jujur untuk laporan:** sisa masalah mutu (kerikil/daun vs pothole pada
foto close-up, foto malam yang hanya menghasilkan 1–2 temuan berkualitas rendah)
adalah masalah **domain/data**, bukan tuning ambang — model dilatih pada RDD2022
(Tiongkok, siang) sementara target aplikasi adalah jalan lokal, termasuk malam.
Solusinya retrain dengan data lokal (§2 dan §7), bukan menurunkan ambang sampai noise lolos.
Semua keputusan tuning di atas sengaja dijaga agar P/R/F1 diukur terhadap label,
bukan berdasarkan "berapa banyak kotak per foto". Pelajaran metodologi ini yang
paling penting: pengukuran tanpa ground truth menghasilkan kesimpulan yang
terbalik (tiling tampak "lebih baik" hanya karena lebih banyak kotak, padahal
F1-nya 0,011).

### 6e. Gambar resolusi tinggi: mengapa lambat, dan knob `maks_sisi_proses` (2026-10-18)

**Pertanyaan:** kalau pengguna mengunggah foto resolusi tinggi, apakah waktu
deteksi jadi jauh lebih lama? Perlu diturunkan ke 640 di server?

**Jawaban singkat: tidak jauh lebih lama, dan menurunkan ke 640 bukan tuas yang
tepat untuk akurasi.** Model di jalur gambar **sudah** menerima 640: `predict`
dipanggil dengan `imgsz_gambar=640`, dan Ultralytics melakukan *letterbox*
(gambar apa pun diskalakan agar sisi panjang 640, lalu di-pad). Jadi foto 4032×3024
yang masuk ke GPU tetap berukuran 640×480 — forward pass-nya tidak tumbuh dengan
resolusi asli. Bukti: 141 dari 161 gambar BPID adalah 12 MP (4032×3024), dan
**seluruh angka F1 di §6d diukur pada gambar 12 MP itu**.

**Di mana waktunya benar-benar pergi** (1 foto 3000×4000, rata-rata 7×, sudah
dipanaskan, GTX 1650):

| Tahap | 12 MP | jika diperkecil ke 640 dulu |
|---|---|---|
| `decode_image` (JPEG) | 0,072 s | 0,002 s |
| `deteksi_gelap` (LAB + mean) | 0,082 s | 0,002 s |
| `klasifikasi_scene` | 0,083 s | 0,013 s |
| `model.predict @640 + TTA` | 0,084 s | 0,059 s |
| `anotasi + encode_jpg + base64` | 0,079 s | 0,002 s |
| **Subtotal** | **0,400 s** | **0,078 s** |
| CLAHE (hanya bila opsi `malam` dicentang) | 0,327 s | 0,007 s |
| **`analisis_gambar` total** | **0,475 s** | ~0,15 s |

Catatan: `predict` 0,084 s itu **bukan** forward pass (tanpa TTA hanya 0,026 s),
melainkan biaya *letterbox* yang harus membaca 12 juta piksel — dan 3× lipat
karena TTA. Jadi seluruh biaya jalur gambar bersifat **linier terhadap jumlah
piksel**, bukan didominasi model.

**Sumber "jauh lebih lama" yang sebenarnya adalah mode teliti**, bukan foto besar:
pada foto yang sama, `analisis_gambar(teliti=True)` memakan **2,945 s (6,6×)** —
dan pada foto kerikil `test_foto/000006.jpg` ia menghasilkan **10 temuan palsu**
(jalur biasa: 0 temuan, benar). Ini konsisten dengan vonis §6d: tiling sudah
dicabut sebagai pemicu otomatis dan kini manual saja.

#### Knob `maks_sisi_proses`

Karena letterbox membuat resolusi analisis tidak menentukan akurasi model,
resolusi itu bisa dibatasi. `config/inferensi.yaml` menyediakan
`maks_sisi_proses` (0 = nonaktif). Bila gambar lebih besar dari batas ini, gambar
diperkecil dengan `cv2.INTER_AREA` **hanya untuk analisis**; tahap murah di atas
ikut murah, dan bukti yang dikirim ke browser ikut mengecil.

Yang **tidak** berubah: box tetap dikembalikan di **koordinat gambar asli**
(dikali `skala_box` di `proses_detections`/`prediksi_ensemble`). Akibatnya
`pixels_per_cm`, `masuk_akal`, `luas_px`, `gabung_fragmen`, dan verifikasi
operator (`terapkan_koreksi`) bekerja persis seperti sebelumnya — tidak ada satu
pun rumus cm yang disentuh. Mode teliti **selalu** resolusi asli.

Diukur di BPID (161 gambar, IoU 0,5, kelas pothole, conf 0,30, TTA aktif):

| `maks_sisi_proses` | F1 | P | R | FP | s/gambar | bukti base64 |
|---|---|---|---|---|---|---|
| 0 (asli) | 0,616 | 0,636 | 0,597 | 90 | 0,49 | 2,77 MB |
| 2048 | 0,602 | 0,638 | 0,570 | 85 | 0,42 | — |
| 1536 | 0,614 | 0,659 | 0,574 | 78 | 0,36 | 0,62 MB |
| 1280 | 0,614 | 0,681 | 0,559 | 69 | 0,36 | 0,45 MB |
| 960 | 0,617 | 0,695 | 0,555 | 64 | 0,33 | 0,27 MB |
| 640 | 0,614 | 0,681 | 0,559 | 69 | 0,32 | 0,13 MB |

Cara membacanya:

* **F1 nyaris datar** (0,602–0,617, selisih di dalam derau pengukuran). Artinya
  pilihan ini *bukan* soal akurasi agregat.
* **Recall turun** dari 0,597 → ~0,555–0,574: sekitar 6–11 temuan benar (dari 263
  instance) hilang. Presisi naik hampir sebanding, jadi F1 menutupinya — tetapi
  bagi aplikasi ini, temuan yang hilang lebih merugikan daripada FP, karena
  prioritasnya menemukan kerusakan nyata.
* **Penghematan waktu kecil** (0,49 → 0,32–0,36 s) tetapi **penghematan payload
  besar** (2,77 MB → 0,13–0,62 MB). Muatan inilah yang terasa di HP, bukan
  selisih 0,15 detik.

Angka pada tabel adalah **baris kelas `pothole` saja** (BPID hanya berlabel
pothole). Skrip pelaporan sengaja juga menampilkan baris "semua kelas digabung"
dengan peringatan: di BPID, deteksi retak dihitung FP padahal tidak ada label
pembandingnya, sehingga baris itu **bukan** ukuran mutu — jangan dikutip.

Cara mengukur ulang (butuh data BPID di `data/publik/bpid/test`, lihat "Berkas
terkait"); skrip menjalankan `analisis_gambar()` apa adanya, jadi TTA, saring,
`gabung_fragmen`, dan gate ikut aktif:

```bash
.\.venv\Scripts\python scripts\evaluasi_pipa_app.py --maks 0 1536 960
```

**Keputusan:** default tetap **0** (tidak mengubah perilaku/angka §6d). Naikkan
ke **1536** hanya bila kecepatan + payload dinilai lebih penting daripada ~2 poin
recall; satu baris config, bisa dibalik tanpa kode.

**Catatan jujur (batas bukti):**

* BPID hanya berlabel pothole. **Recall retak pada berbagai skala belum terukur**
  (label RDD2022 hanya ada di Kaggle) — jadi klaim "aman untuk semua kelas" tidak
  bisa dibuat dari tabel di atas.
* Memperkecil gambar juga memperkecil **bukti visual**: penampil zoom sampai
  "1 = ukuran asli" akan menampilkan gambar berbatas `maks_sisi_proses`, bukan
  foto asli. Trade-off ini nyata untuk aplikasi laporan.
* Angka detik di tabel adalah mesin pengembang (GTX 1650). Di mesin tanpa GPU,
  tahap murah (decode/gelap/scene/CLAHE) akan jauh lebih dominan, sehingga
  penghematannya lebih besar dalam satuan mutlak.

---

## 7. P2 — melangkah ke fine-tuning data lokal

Semua keputusan tuning di atas sudah mentok batasnya: precision pothole 0,636 di
BPID. FP yang tersisa **bukan** masalah angka — mining 137 gambar negatif lokal
menemukan polanya: **genangan air dan aspal basah dibaca pothole** (conf sampai
0,80), bukan sekadar batu. Tidak ada penyaring yang bisa membedakan "lubang
berisi kerikil" dari "kerikil di aspal" tanpa konteks — hanya data latih lokal
yang bisa mengerjakannya.

Prosedur, resep latih Kaggle, dan **aturan terima** (jangan memakai model baru
kecuali buktinya memenuhi syarat) ada di
[`Fine-tuning-Lokal.md`](Fine-tuning-Lokal.md), beserta alat pra-anotasi
[`scripts/pra_label.py`](../scripts/pra_label.py). Ringkasnya:

1. `scripts/pra_label.py --mode dataset` → pre-label, lalu koreksi manual.
2. Split train/val; **jangan pernah** latih dari BPID test (itu satu-satunya uji OOD).
3. Latih dari `best.pt` di Kaggle (imgsz 768, lr0 0,001, campur data lokal).
4. Uji dengan protokol §6d **plus** audit 137 gambar negatif; terima model baru
   hanya kalau recall tidak turun lebih dari 2 poin atau F1 naik minimal 0,03.
