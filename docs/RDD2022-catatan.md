# RDD2022 (Kaggle mirror aliabdelmenam/rdd-2022) — catatan keputusan

Sumber: https://www.kaggle.com/datasets/aliabdelmenam/rdd-2022
Tanggal cek: 2026-09-03. Wajib sitasi paper asli bila dipakai jurnal:
Arya et al. (2024), "RDD2022: A multi-national image dataset for automatic road damage detection",
Geoscience Data Journal. Lisensi: CC BY-SA 4.0 (cantumkan di TA + jurnal).

## Fakta dataset
- Ukuran: 11,07 GB, ~76.800 file, ~38.400 gambar (train ~26.900 / val ~5.758 / test ~5.758)
- Format: YOLO `.txt` siap latih (tidak perlu konversi VOC). Struktur: train/images+labels, val/..., test/...
- TIDAK ada data.yaml di dataset (konfirmasi screenshot 2026-09-03) → pakai `data/dataset-rdd2022.yaml` repo ini.
- 6 negara: Japan, India, Czech, Norway, US, China. Norway sendiri 9,9 GB (salju, tidak relevan untuk Indonesia).
- Kelas (5): longitudinal crack, transverse crack, alligator crack, other corruption, Pothole
- BUKAN segmentasi: label berupa bounding box deteksi, bukan polygon mask.

## 4 konsekuensi untuk plan kita
1. Seg → Detect. Plan awal YOLOv11n-seg butuh mask; dataset ini box-only.
   Keputusan: pakai YOLOv11n DETEKSI (bukan seg). Luas = luas box x kalibrasi.
   Tulis di batasan: "luas diestimasi dari bounding box, bukan mask presisi".
2. Kelas jadi 5, bukan 3. Tidak ada manhole. Kelas `other corruption` (bekas tambalan/corrupt lain)
   tetap dipakai apa adanya saat latih; mapping ke severity hanya di modul (bukan ubah label).
   Mapping severity: alligator crack + pothole besar = Berat; pothole sedang + transverse lebar = Sedang;
   longitudinal tipis = Ringan; other corruption = ikut luas (atau abaikan bila confidence rendah).
3. Full 38rb gambar x 100 epoch KEBERATAN untuk T4 gratis (bisa >10 jam, limit sesi ~12 jam, kuota ~30 jam/minggu).
   Strategi: prototype di subset India (+ Japan bila perlu), EXCLUDE Norway. Final: train subset + 150 lokal.
   Alternatif prototipe cepat: `vidishbijalwan/rdd2022-india-pothole-d40` (84 MB) untuk smoke-test pipeline.
4. Domain gap: tidak ada Indonesia. India paling mirip kondisi jalan kita → prioritas subset India.
   Data lokal 150 foto tetap WAJIB sebagai novelty + uji real.

## Cara pakai (jangan download ke laptop — sisa disk C: 17 GB)
- JANGAN download 11 GB ke PC. Di Kaggle notebook: + Add Input → pilih dataset ini → latih langsung.
- Lokal cukup download SAMPEL ±300 gambar untuk tes visual + EDA, bukan full.
- Format TERVERIFIKASI (2026-09-03, screenshot China_Drone_000001.txt): class cx cy w h ternormalisasi 0-1, valid. Isi 2 baris: kelas 1 box pipih melebar (w=0,359 h=0,057 = retak melintang) + kelas 0 box ramping vertikal (w=0,049 h=0,309 = retak memanjang). Bentuk box konsisten dengan mapping 0=longitudinal, 1=transverse di dataset.yaml.
- CATATAN: file contoh dari folder test + China_Drone (sudut drone, bukan HP motor). Untuk TA prioritaskan street-level (India / China_MotorBike / Japan); subset drone secukupnya. Jangan campur test ke train.
