# SOP Rekam Data Lokal (HP Android)

## Setting HP
- Resolusi 1280x720, 30fps (jangan 4K, berat + tidak konsisten dengan dataset publik)
- Pasang di holder dashboard motor, tinggi ~1m, sudut sama setiap rekaman
- Nyalakan GPS Logger bersamaan untuk koordinat

## Protokol
- Kecepatan 20-40 km/jam, rute yang sama direkam pagi / siang / sore
- Total target 1-2 jam video + ekstrak frame tiap 1 detik
- Pilih 150 frame ada kerusakan + 50 jalan mulus
- Foto kalibrasi: letakkan penggaris 10cm di aspal, foto dari ketinggian pasang yang sama → hitung pixels_per_cm

## Anotasi (Roboflow)
- Kelas: pothole, crack, manhole
- Pakai polygon (segmentasi) karena butuh luas, bukan box saja
- Export: YOLOv11-seg format
- Split: train 80 / val 10 / test 10 (test usahakan foto lokal semua)

## Penamaan
- Foto: `lokal_YYYYMMDD_lokasi_nomor.jpg`
- Video: `VID_YYYYMMDD_jam_cuaca.mp4`
