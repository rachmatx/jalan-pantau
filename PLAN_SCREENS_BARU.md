# Rencana Implementasi 7 Screen Baru dari Stitch

## 1. Hapus Pico CSS
- Hapus `<link pico.min.css>` dari `web/templates/base.html`
- Hapus semua `!important` netralisasi di `civic.css` (tidak diperlukan lagi)
- civic.css menjadi satu-satunya otoritas styling

## 2. Screen Baru → Halaman Baru

### 2.1 Mode Mobile Petugas Lapangan (`mobile.html`, route `/mobile`)
- Referensi: `stitch/.../mode_mobile_petugas_lapangan/code.html`
- Layout mobile-first, aspect ratio 4:5 untuk viewfinder
- Telemetry strip: RTK Fix, Battery, Flask API status
- 3 KPI cards: FPS, Temuan, Est. Biaya
- Quick controls: CLAHE toggle, Grid toggle, Snapshot button (glove-friendly 48px+)
- Segment path selector
- Temuan terakhir card
- Bottom action bar: Jeda Rekam + Tandai Kritis + Log Rute

### 2.2 Pengaturan Kalibrasi Sensor (`kalibrasi.html`, route `/kalibrasi`)
- Referensi: `stitch/.../pengaturan_kalibrasi_sensor_kamera_ai/code.html`
- Sub-header: status CAL-OK, profil rig
- Workbench 12-col grid (7:5)
  - Kolom kiri: viewport kalibrasi (460px height), SVG grid perspektif + GSD marker, toggle IPM/Grid/BBox
  - Kolom kanan: form sensor geometry (height, pitch, RTK offset X/Y/Z), metrik (GSD, thresholds), matriks tarif
- Matriks homografi 3x3 preview
- Tombol: Simpan config.json, Uji Ulang, Reset
- Bottom QA banner: status kalibrasi + unduh berita acara PDF

### 2.3 Pratinjau Berita Acara PDF (`laporan_preview.html`, route `/laporan/preview/<id>`)
- Referensi: `stitch/.../pratinjau_berita_acara_laporan_audit_pdf/code.html`
- Layout A4 formal (max-width 850px, shadow-2xl)
- Kop dinas: logo + judul + alamat
- Judul berita acara + nomor + tanggal
- Bagian I: Data Umum (lokasi, instrumen, operator)
- Bagian II: Tabel rekapitulasi kerusakan (kode Bina Marga, severity, estimasi)
- Bagian III: Lampiran foto bukti dengan AI bounding box overlay
- Bagian IV: Kesimpulan & rekomendasi
- Bagian V: Pengesahan 3 kolom tanda tangan
- Sticky top bar: zoom controller, kirim email, cetak, unduh PDF

## 3. Screen Baru → Enhance Halaman Existing

### 3.1 Live Streaming (enhance `deteksi.html` tab Live)
- Referensi: `stitch/.../layar_1_deteksi_live_streaming/code.html`
- Tambah 4 KPI cards di atas viewer (FPS, Titik Unik, Deteksi, Total Frame) — sudah ada, perbaiki layout
- Source selector: 4 tab (Webcam, IP Cam, Berkas, Preset Demo) — sudah ada, tambah preset
- Tambah toggle box/OSD/floating toolbar di viewer
- Tambah status live footer

### 3.2 State Gangguan Kamera (enhance `deteksi.html`)
- Referensi: `stitch/.../layar_1_deteksi_state_gangguan_kamera_panduan_solusi/code.html`
- Error banner merah di atas (status kritis + kode error)
- Modal/error state di viewer: ikon videocam_off, diagnosa, 3 langkah troubleshooting
- Tombol: Coba Hubungkan Ulang, Beralih Kamera Cadangan, Unduh Log

### 3.3 Viewer Foto Inspeksi (enhance `peta.html`)
- Referensi: `stitch/.../layar_2_viewer_foto_inspeksi/code.html`
- Ubah `foto-dialog` jadi modal besar (max-w-7xl) dengan layout 12-col
- Kolom kiri (8): viewport foto dengan toolbar zoom + toggle Box/CLAHE
- Kolom kanan (4): ringkasan diagnostik, tabel klasifikasi kerusakan, estimasi biaya Bina Marga
- Footer: Kembali ke Peta, Unduh JPG, Unduh PDF

### 3.4 Modal Detail Berita Acara (enhance `riwayat.html`)
- Referensi: `stitch/.../layar_3_riwayat_modal_detail_berita_acara/code.html`
- Perluas modal `#detail` jadi layout A4 formal (seperti laporan_preview)
- Tambah: kop dinas, foto dengan AI bbox overlay, tabel RAB, catatan legalisasi, tanda tangan 3 kolom

## 4. Update Navigasi & Routes

### `base.html`
- Tambah link nav: "Mobile" (hanya mobile), "Kalibrasi"
- Nav顺序: Deteksi | Peta | Riwayat | Kalibrasi | Tentang

### `app.py`
- `@app.get("/mobile")` → mobile()
- `@app.get("/kalibrasi")` → kalibrasi()
- `@app.get("/laporan/preview/<int:sid>")` → laporan_preview(sid)

## 5. Urutan Pengerjaan
1. Hapus Pico + bersihkan civic.css
2. mobile.html (halaman baru, mandiri)
3. kalibrasi.html (halaman baru, mandiri)
4. laporan_preview.html (halaman baru, mandiri)
5. Enhance deteksi.html (live streaming + gangguan kamera)
6. Enhance peta.html (viewer foto)
7. Enhance riwayat.html (modal detail)
8. Update nav + routes + final test
