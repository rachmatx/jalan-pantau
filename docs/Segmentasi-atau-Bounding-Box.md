# Bounding Box, Bukan Segmentasi

Catatan keputusan metodologi untuk tugas akhir ini.

## 1. Pertanyaan yang paling sering muncul

Saat sidang, pertanyaan ini hampir pasti keluar:

> "Bukankah judulnya YOLO-Segmentation? Kalau begitu segmentasinya di mana?"

Jawaban singkat: **tidak ada segmentasi.** Proyek ini memakai deteksi
bounding box. Itu keputusan yang disengaja, bukan kelalaian.

## 2. Kenyataan di proyek ini

| Aspek | Kenyataan |
|---|---|
| Mode model | Deteksi objek (bounding box) |
| Format anotasi latih | YOLO detect, 5 kolom: class cx cy w h |
| Keluaran mask dari model | Tidak ada |
| Luas area temuan | Diestimasi dari dimensi bounding box terkalibrasi (px/cm) |
| Jumlah kelas | 5 |

Daftar kelas: `longitudinal_crack`, `transverse_crack`, `alligator_crack`,
`other_corruption`, `pothole`.

Judul awal proposal menyebut YOLO-Segmentation, ketika rencana segmentasi
masih mencakup. Judul akhir sudah disesuaikan — "…dengan Severity
Terkalibrasi dan Visualisasi Geospasial" — dan dokumen ini dipertahankan
untuk menjelaskan kenapa segmentasi tidak dipakai.

## 3. Bukti format latihnya bounding box

Dataset RDD2022 adalah sumber training utama, 14.176 gambar. Anotasi yang
dipakai di proyek ini adalah kotak.

Contoh isi satu berkas label di `data/publik/bpid/test/labels/`:

```
0 0.47003254613799794 0.7025839045950854 0.1752091698352906 0.16516326368075454
```

Lima kolom, semua nilai ternormalisasi 0 sampai 1. Tidak ada koordinat
polygon sama sekali.

Sebagai pembanding, format YOLO untuk segmentasi memakai 7 kolom atau lebih:
satu kolom class, lalu titik-titik polygon. Yang dipakai proyek ini jelas
bukan format itu.

Bukti tambahan: recipe training di `notebooks/kaggle-retrain-yolo11s-rdd2022.py`
memakai `YOLO("yolo11s.pt")` lalu `model.train(...)` tanpa `retina_masks` —
yaitu model deteksi bawaan, bukan segmentasi.
(Koreksi 19 Okt 2026: versi dokumen ini mengutip
`yolov11s-rdd-only/args.rekonstruksi.yaml`; folder itu artefak rekonstruksi run
lama yang sudah dihapus, dan isinya tidak cocok dengan recipe sebenarnya.)

## 4. Kenapa tidak dilatih dengan segmentasi

1. **Anotasi polygon tidak tersedia di dataset ini.** Melatih model
   segmentasi berarti memakai loss khusus segmentasi, dan loss itu menuntut
   ground truth berupa mask. Kalau mask tidak ada, yang dilatih adalah
   tebakan.
2. **Mengubah kotak jadi polygon secara otomatis tidak menambah
   ketepatan.** Kalau kotak dipakai sebagai polygon, hasilnya persis sama
   dengan kotak itu. Seluruh kompleksitas segmentasi jadi sia-sia.
3. **Anotasi ulang 14.176 gambar tidak proporsional.** Butuh ribuan jam
   kerja untuk menghasilkan batas presisi, sementara kebutuhan proyek ini
   hanya estimasi dimensi untuk agregasi SDI per segmen.

Prinsipnya begini: segmentasi unggul kalau yang dibutuhkan adalah batas
tepat. Kalau yang dibutuhkan urutan prioritas perbaikan, bounding box sudah
cukup, dan justru lebih kokoh terhadap noise.

## 5. Yang dipakai sebagai gantinya

Luas setiap temuan diestimasi dari **dimensi bounding box terkalibrasi**:
lebar dan panjang box (piksel) dikonversi ke cm lewat `pixels_per_cm` hasil
kalibrasi, lalu luas = lebar × panjang (implementasi:
`app/severity.py::box_size_cm`; pemakaian di `web/deteksi.py`).

Versi awal proyek ini sempat memakai *pseudo-segmentation* (kontur
Otsu/adaptive di dalam box, `web/deteksi.py::pseudo_segmentation`) untuk
mengestimasi luas — **sudah dihapus dari kode (Okt 2026)** dan digantikan
dimensi box terkalibrasi di atas. Jangan mengutip pseudo-segmentation
sebagai implementasi aktif.

## 6. Batasnya, apa adanya

- **Bukan mask presisi.** Luas adalah luas *kotak* terkalibrasi, bukan luas
  bentuk kerusakan sebenarnya — untuk retak tipis, luas box
  melebih-lebihkan luas retak. Karena itu angka ini dipakai sebagai
  komponen agregasi SDI per segmen, bukan klaim luas eksak.
- **Box bisa memotong objek.** Bila kerusakan melebar melewati bounding box,
  bagian yang terlewat tidak akan tertangkap, karena box-nya sendiri sudah
  terpotong.
- **Bukan angka siap RAB.** Luas di sini adalah masukan agregasi SDI, bukan
  luas-property dalam meter persegi yang siap jadi anggaran.

Karena itu prioritas di aplikasi dinyatakan sebagai SDI-visual per segmen.
Aplikasi ini tidak pernah menyebut hasil ini sebagai "biaya perbaikan"
secara mutlak.

## 7. Kalau ditanya di sidang

> **"Bukannya harusnya segmentasi?"**
>
> Segmentasi memang lebih akurat untuk memetakan batas tepat kerusakan.
> Tapi yang dibutuhkan dalam proyek ini adalah urutan prioritas perbaikan.
> Untuk itu, luas di dalam bounding box sudah cukup.
>
> Kendala yang mendasar adalah data. Dataset RDD2022 yang dipakai hanya
> menyediakan anotasi bounding box. Melatih model segmentasi butuh polygon
> untuk tiap gambar, jadi seluruh 14.176 gambar harus dianotasi ulang.
> Itu tidak proporsional untuk tujuan skripsi ini.
>
> Sebagai gantinya, luas diestimasi dari dimensi bounding box terkalibrasi.
> Jadi ini bukan segmentasi, dan memang tidak diklaim sebagai segmentasi.
> Yang diklaim adalah deteksi objek dengan estimasi dimensi untuk agregasi
> SDI-visual per segmen.

## 8. Kalau nanti mau benar-benar segmentasi

Urutannya harus begini:

1. Anotasi ulang sebuah subset, bukan 14.176 sekaligus. Mulai dari
   sekitar 2.000 gambar yang mewakili.
2. Evaluasi baseline bounding box dan model segmentasi pada subset yang
   sama. Bandingkan mAP50-95 dan IoU mask.
3. Baru putuskan apakah biaya kompleksitasnya sebanding dengan perbaikan
   yang terukur. Jangan diasumsikan otomatis lebih baik.

Selama langkah pertama belum dikerjakan, klaim segmentasi di dokumen
manapun adalah klaim yang belum didukung bukti.

## 9. Berkas terkait

| Berkas | Isi |
|---|---|
| `app/severity.py::box_size_cm` | Dimensi box terkalibrasi → luas temuan |
| `config/severity.yaml` | Ambang luas dan volume ke Ringan/Sedang/Berat |
| `app/severity.py` | Pemetaan dimensi ke severity |
| `docs/RDD2022-catatan.md` | Catatan asal dataset, termasuk keputusan awal Seg ke Detect |
| `notebooks/kaggle-retrain-yolo11s-rdd2022.py` | Recipe training (deteksi, tanpa retina_masks) |
| `reports/keputusan-ablasi-cbam-yolo26.md` | Decision log ablasi model |