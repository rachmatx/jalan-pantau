# SOP Rekam Data Lokal (HP Android)

## Setting HP
- Resolusi 1280x720, 30fps. Jangan 4K, karena berat dan tidak konsisten
  dengan dataset publik.
- Pasang di holder dashboard motor, tinggi sekitar 1 meter, sudut sama
  setiap rekaman.
- Nyalakan GPS Logger bersamaan untuk koordinat.

## Protokol
- Kecepatan 20-40 km/jam, rute yang sama direkam pagi, siang, dan sore.
- Total target 1-2 jam video, ekstrak frame tiap 1 detik.
- Pilih 150 frame ada kerusakan dan 50 jalan mulus.
- Foto kalibrasi: letakkan penggaris 10 cm di aspal, foto dari ketinggian
  pasang yang sama. Hitung `pixels_per_cm`.

## Anotasi (Roboflow)

**Pakai bounding box, bukan polygon.** Dataset RDD2022 yang dipakai sebagai
data training utama hanya menyediakan anotasi kotak. Kelas dan format label
harus ikut dataset itu supaya bisa digabung.

- **Kelas:** pakai lima kelas yang sama dengan model, supaya bisa digabung
  dengan data training: `longitudinal_crack`, `transverse_crack`,
  `alligator_crack`, `other_corruption`, `pothole`. Jangan pakai `crack` atau
  `manhole`, karena itu akan menjadi kelas baru yang tidak dikenali model.
- **Anotasi:** bounding box yang persis mengitari kerusakan. Jangan polygon,
  kecuali proyek sudah memutuskan untuk beralih ke segmentasi. Alasan
  lengkapnya ada di `docs/Segmentasi-atau-Bounding-Box.md`.
- **Export:** format YOLO detect, 5 kolom `class cx cy w h`.
- **Split:** train 80, val 10, test 10. Untuk test, usahakan memakai foto
  lokal semua.

Kalau nanti butuh segmentasi sungguhan, urutan yang benar adalah: anotasi
ulang sebuah subset kecil dengan polygon, bandingkan dengan baseline box pada
data yang sama, baru putuskan. Bukan langsung menganotasi ulang semuanya.

## Penamaan
- Foto: `lokal_YYYYMMDD_lokasi_nomor.jpg`
- Video: `VID_YYYYMMDD_jam_cuaca.mp4`

Contoh: `lokal_20260905_jl-mangga_001.jpg`, `VID_20260905_0800_cerah.mp4`.