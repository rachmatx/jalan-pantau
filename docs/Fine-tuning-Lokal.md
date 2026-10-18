# P2 — Fine-tuning dengan data lokal

Bagian ini menjawab satu pertanyaan yang tersisa setelah semua tuning di
[`Panduan-Tuning-Model.md`](Panduan-Tuning-Model.md) selesai: **kenapa masih ada
false positive, dan apa yang harus dilakukan untuk benar-benarkannya.**

Ringkas: tuning sudah_borderline-mentok batasnya (precision pothole 0,64 di
161 gambar berlabel). Selebihnya bukan soal angka — tapi soal **domain**.

---

## 1. Diagnosis: apa yang masih salah (berdasar data, bukan perkiraan)

| Temuan | Bukti |
|---|---|
| Precision pothole 0,636 | 161 gambar BPID berlabel, IoU 0,5, slider 0,30 (§6d) |
| **False positive utama = genangan air** | Audit 137 gambar negatif lokal: 14 gambar ditandai model, dan polanya didominasi genangan/aspal basah → `pothole` (conf sampai **0,80**) |
| Gate jalan basah bekerja, tapi tipis | `pub_0042.jpg`: scene `wet_road` (prob 0,66), gate AKTIF dengan `ambang_lubang: 0.45`, tetapi pothole conf 0,55 tetap lolos karena di atas ambang |
| Gate kadang tidak aktif | `pub_0026.jpg`: scene `normal_road` conf 0,95 (`prob_basah` 0,000) walau gambarnya bermasalah |
| Foto malam hampir tak terbaca | `000059.jpg`: 2 temuan berkualitas rendah; CLAHE tidak menyelamatkannya |

Kenapa tidak bisa diatasi dengan penyaring atau ambang:

- Menaikkan ambang pothole dari 0,30 → 0,40 memang menurunkan FP, tetapi recall
  ikut turun (diukur di §6d: F1 optimum justru di 0,30–0,35). Itu trades recall,
  bukan memperbaiki model.
- `masuk_akal` (diameter/luas/rasio) tidak membedakan **lubang berisi kerikil**
  dari **kerikil di aspal** — keduanya satuacism bentuk.-filter geometri buta
  terhadap perbedaan ini; hanya contoh latih yang bisa membedakan.
- Gate jalan basah hanya menyaring **pothole ber-confidence rendah** di jalan
  basah. Genangan yang sangat meyakinkan (conf > 0,45) lolos, dan gate yang lebih
  agresif akan membuang pothole asli di jalan basah tanpa bukti pengukuran.

Jadi langkah berikutnya wajib: **modelnya harus melihat jalan lokal**.

---

## 2. Data yang dibutuhkan

| Kebutuhan | Saran minimum | Alasan |
|---|---|---|
| Pothole lokal berlabel | 150 foto / ≥ 300 kotak | kelas terlemah + keselamatan; sekarang hanya 263 GT dari dataset luar |
| Retak lokal (4 jenis) | 150 foto | model hanya punya gaya retak Tiongkok |
| Foto malam (pothole & retak) | 60 foto | nol data malam di RDD2022 |
| Negatif bersih | **sudah ada 137** (`data/lokal/negatif-*`) | menahan FP; jangan dilatih tanpa ditinjau dulu (§4) |

Aturan pengambilan data: HP sendiri, beberapa ruas sekitar, ambil kondisi beragam (terang,
redup, hujan, dekat-jauh, motor lalu lintas). Foto close-up kerikil juga penting —
itulah mode FP yang paling dikeluhkan operator.

---

## 3. Alur kerja (siap dijalankan hari ini)

```bash
# 1) Pra-annotasi: model jalan dulu, hasilnya jadi pre-label
.\.venv\Scripts\python scripts\pra_label.py --mode dataset \
    --sumber "<folder foto Anda>" --keluar data\lokal\terlabel

# 2) Koreksi pre-label di LabelImg / Gradio / CVAT (hanya yang salah)
#    Format: YOLO txt, `cls cx cy w h` ternormalisasi, 1 baris per kotak.
#    Urutan kelas: 0 longitudinal, 1 transverse, 2 alligator, 3 other_corruption, 4 pothole.

# 3) Split train/val 80/20 (folder terpisah). JANGAN latih dari BPID test.
#    Lihat peringatan di bawah.

# 4) Audit kandidat hard-negative (menulis TIDAK apa pun)
.\.venv\Scripts\python scripts\pra_label.py --mode audit --sumber data\lokal

# 5) Latih (butuh Kaggle — RDD2022 hanya ada di sana; lihat §5)

# 6) Evaluasi & aturan terima (§6)
```

> ⚠️ **BPID test (161 gambar) tidak boleh ikut latih.** Itu satu-satunya set uji
> OOD yang dipakai untuk semua keputusan tuning di §6d. Kalau ikut dilatih,
> seluruh bukti di panduan ini jadi tidak sah. Pakai untuk **uji akhir saja**.

---

## 4. Mining hard-negative: 14 kandidat dari 137 gambar negatif

Audit hari ini (18 Okt 2026, model `best.pt`, imgsz 640, conf 0,30) menemukan
14 dari 137 gambar "bersih" yang tetap ditandainya:

| gambar | kotak | conf maks | yang dipredict |
|---|---|---|---|
| `pub_043077cf_rain_on_a_puddle_in_tuntorp_4_jpg.jpg` | 3 | 0,45 | pothole + 2 other_corruption |
| `pub_6c17d9f0_rain_water_on_road_jpg.jpg` | 3 | 0,43 | 3 other_corruption |
| `pub_0026.jpg` | 2 | **0,80** | other_corruption + pothole |
| `pub_8d8a0e59_wet_asphalt_campus_road_jpg.jpg` | 1 | 0,66 | other_corruption |
| `pub_4f798406_image_from_page_78_of_city_roads...` | 1 | 0,61 | alligator_crack |
| `pub_c7010f2c_reflected_bus_stop...` | 1 | 0,56 | pothole |
| `pub_0042.jpg` | 1 | 0,55 | pothole (scene wet_road, gate aktif) |
| `pub_0041.jpg` | 1 | 0,54 | pothole |
| `pub_0682861f_child_fetching_water_from_a_puddle...` | 1 | 0,37 | pothole |
| `pub_af71e908_large_ice_crystals_in_a_frozen_puddle...` | 1 | 0,36 | pothole |
| `pub_efb02500_2025_04_26_16_14_39_vehicles...` | 1 | 0,33 | transverse_crack |
| `pub_28691dcc_puddle_from_melted_ice...` | 1 | 0,31 | pothole |
| `pub_3e3fa8c2_20180604_tantalus_koa_tree_wet_asphalt...` | 1 | 0,24 | longitudinal_crack |
| `pub_83033ec7_large_puddle_on_the_newport_road...` | 1 | 0,17 | longitudinal_crack |

**Aturan emas:** pada folder negatif, gambar yang ditandai model justru **kemungkinan
paling berisi kerusakan nyata** — itulah sebabnya ia disimpan sebagai kandidat.
Jangan menuliskan label kosong secara otomatis; itu melatih model membutakan diri
sendiri. Periksa satu per satu: yang ternyata rusak → pindahkan ke dataset latih
(bernilai data, jangan dibuang); yang benar-benar bersih → jadi negatif dengan
label kosong **dan** meyakinkan (lihat daftar di atas: 4 di antaranya genangan air).

---

## 5. Resep latih (Kaggle)

RDD2022 + labelnya hanya ada di Kaggle, jadi training run dilakukan di sana.

**Resepnya sudah ada di
[`notebooks/template-kaggle-hard-negative-finetune.md`](../notebooks/template-kaggle-hard-negative-finetune.md)** —
gunakan template itu apa adanya. Dua koreksi hasil ukur 18 Okt 2026 sudah
diterapkan ke sana, jadi jangan memakai versi template yang lama:

| Sel | Koreksi | Alasan |
|---|---|---|
| 3 (hard-negative) | tidak lagi menulis `.txt` kosong otomatis | audit 137 gambar: 14 yang ditandai model justru berisi genangan air → itu kerusakan nyata, bukan negatif |
| 5 (fine-tune) | `imgsz` 960 → **768** | skala latih asal (`args.rekonstruksi.yaml`) supaya selisihnya murni dari data tambahan, bukan perubahan skala |
| 5 | tambah `scale=0.5`, `hsv_v=0.4` | objek lokal lebih dekat dari mobil; variasi cahaya lokal termasuk malam |
| 7 (evaluasi) | `imgsz` 960 → **640** | harus sama dengan `imgsz_gambar` aplikasi, kalau tidak angkanya tidak sebanding dengan yang pengguna alami |
| 7b (baru) | **gerbang terima** | jangan unduh bobot sebelum a/b/c lolos (§6) |
| 8 (ekspor) | `imgsz` 960 → **640** | ONNX harus ikut skala aplikasi |

Campur data lokal: salin `data/lokal/terlabel/{images,labels}` ke
`/kaggle/working/data/train` (struktur YOLO), lalu **ulang beberapa kali**
(file lokal di-oversample) supaya model tidak kembali ke domain Tiongkok. Untuk
subset foto malam, naikkan variasi pencahayaan saat latih — labelnya tetap sama
(gelap bukan alasan melabel ulang).

Fine-tuning **hanya** dengan negatif jelas berbahaya: model bisa belajar
"jalan = tidak ada kerusakan" dan recall anjlok. Karena itu data latih harus
mengandung kerusakan nyata, dan recall **harus selalu diukur** (§6).

---

## 6. Evaluasi & aturan terima

Ukur dengan protokol yang sama seperti §6d supaya angkanya sebanding:

```bash
# a) Set uji lokal (yang kamu buat) — per kelas
.\.venv\Scripts\python scripts\evaluasi_model.py --data <dataset lokal> --model best_v2.pt --imgsz 640 \
    --conf-list 0.10,0.20,0.30,0.40

# b) BPID test — OOD, pothole-only, IoU 0,5 (JANGAN pernah dipakai latih)
.\.venv\Scripts\python scripts\evaluasi_model.py --data "<BPID test>" --remap 0:4 \
    --model best_v2.pt --imgsz 640

# c) RDD val — pastikan tidak ada kelas yang anjlok
.\.venv\Scripts\python scripts\evaluasi_model.py --data /kaggle/working/rdd_only --model best_v2.pt --imgsz 640
```

**Aturan terima (semuanya harus lolos):**

1. F1 pothole di BPID test naik minimal 0,03 **atau** recall turun ≤ 2 poin
   sementara FP turun ≥ 20%.
2. Tidak ada kelas yang F1-nya turun > 20% relatif di RDD val (proteksi dari
   "model jadi lebih picky").
3. Audit 137 gambar negatif lokal: jumlah gambar yang ditandai turun (target: dari
   14 ke ≤ 5).

Kalau salah satu gagal → jangan dipakai, tulis negatifnya di
`Panduan-Tuning-Model.md` §7 (riwayat keputusan), karena hasil negatif di sini
justru bahan skripsi.

---

## 7. Ekspektasi & risiko (jujur)

- **Target realistis**: precision pothole 0,64 → 0,75 dengan ~150 foto lokal.
  FP kerikil akan turun, tapi tidak akan hilang — secara visual "lubang berisi
  kerikil" memang nyaris identik dengan "kerikil di aspal" tanpa konteks 3D.
- **Foto malam** tetap paling sulit; 60 foto malam mungkin hanya menaikkan
  sedikit. Tetap layak dicoba karena sekarangHoliday nol.
- **Data lokal 150 foto itu sedikit.** Kemungkinan besar lebih baik dari nol, tapi
  janganPUBLIK-kan model baru kalau tidak lewat aturan terima §6.
- **Angka BPID bisa naik karena kebetulan** (161 gambar, pothole-only). Karena itu
  aturan terima juga dicek di RDD val dan audit negatif - jangan melihat satu angka.

---

## 8. Yang sudah disiapkan di repo

| Berkas | Gunanya |
|---|---|
| `scripts/pra_label.py` | pra-annotasi YOLO + audit hard-negative |
| `scripts/evaluasi_model.py` | P/R/F1 + sapuan ambang (sudah dipakai di §6) |
| `scripts/kandidat_negatif.py` | penguinsaing lama (tanpa pre-label) |
| `docs/Panduan-Tuning-Model.md` §6d | bukti semua keputusan tuning |

Butuh satu hal yang tidak bisa dibuat di mesin ini: **k fueled putusan contoh
lokal**. Setelah 150 foto terlabel, sisanya (§5–§6) adalah kerja rutin.