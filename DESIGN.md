# DESIGN.md — JalanPantau (Deteksi Kerusakan Jalan Real-Time)

> Dokumen ini adalah **brief desain resmi** untuk redesign UI/UX — boleh dikerjakan
> tool AI mana pun (Google Stitch, dsb.) lalu di-port ke Flask. Desain lama
> (industrial biru) **dibuang total** bila hasil baru lebih baik.

## 1. Produk

**JalanPantau** — aplikasi web Tugas Akhir: foto jalan → AI (YOLOv11n) mendeteksi
5 jenis kerusakan (`longitudinal_crack`, `transverse_crack`, `alligator_crack`,
`other_corruption`, `pothole`) → severity (Ringan/Sedang/Berat) → estimasi biaya →
laporan PDF → riwayat SQLite → peta GPS (Leaflet). Bahasa UI: **Indonesia**.
Pengguna: mahasiswa saat **sidang** (demo live!) + petugas survei jalan.
Run: `.\.venv\Scripts\python web/app.py` → `http://127.0.0.1:5000` (offline-safe wajib).

## 2. Batasan implementasi (HARGA MATI untuk siapa pun yang mem-port)

- Flask server-render (Jinja), **tanpa build step**, vanilla JS, Leaflet via CDN.
  Semua `id=` di bawah **wajib dipertahankan** (JS sudah jadi dan teruji).
- Internet tersedia saat demo, tapi desain harus tetap waras bila font/peta lambat.
- Kontras teks ≥ 4,5 (WCAG AA). Tanpa emoji sebagai ikon (SVG inline).
- **Dilarang data fiktif**: tanpa testimoni palsu, tanpa paket harga. Angka yang
  boleh tampil — mAP val 0,59 / test 0,47 / OOD Bandung 0,55 / bobot 5,2 MB /
  train 14.176 gambar. Selain itu hanya teks fungsional.

## 3. Halaman & fitur (cakupan redesign = SEMUA)

### 3.1 Deteksi (`/`) — halaman utama & layar demo sidang
- Tab **Gambar** | **Live**.
- Panel Gambar: upload JPG/PNG + slider confidence (0,05–0,8, default 0,25) +
  checkbox mode malam + lokasi + lintang/bujur (auto: EXIF foto, GPS browser,
  koma desimal OK) + tombol Deteksi.
- **Viewer zoom** (wajib, pola PCB Inspector): fit otomatis, wheel zoom, seret,
  dobel-klik, toolbar −/+/1:1/Pas/Layar-penuh, keyboard, indikator %. Label hasil
  **selalu tampil** (terbakar di gambar) — tanpa hover, tanpa ambang zoom.
- Hasil (pola dashboard: KPI atas → tabel bawah): kartu Temuan / Prioritas berat /
  Estimasi total + tabel (#, Kelas, Ukuran, Severity, Estimasi) + tombol
  Unduh PDF + Simpan ke riwayat (anti-klik-ganda).
- Panel Live: sumber webcam / HP IP-camera / file video / video contoh;
  confidence + frame skip + mode malam; KPI FPS/Titik unik/Deteksi/Frame;
  Mulai/Berhenti; snapshot → hasil + simpan (pola sama dengan Gambar).
- Status bar eksplisit untuk tiap aksi + error berbahasa Indonesia.

### 3.2 Peta (`/peta`)
- Peta Leaflet selalu tampil (default Bandung), **tidak boleh tertutup nav**
  (z-index!). Filter checkbox severity + penghitung "N dari M titik tampil".
- Marker dot warna severity; popup: lokasi, severity, temuan, total, link foto bukti.
- Empty state = **chip overlay di atas peta** (bukan pengganti peta) + tombol Tutup.

### 3.3 Riwayat (`/riwayat`)
- Filter: rentang tanggal + severity + pencarian + tombol Tampilkan.
- Tabel: Waktu, Sumber, Lokasi, Severity terparah, Temuan, Total (klik waktu = detail).
- Detail = **modal**: judul, foto (dibatasi, tidak mendorong layout), tabel temuan,
  Unduh PDF + Hapus (konfirmasi) + Tutup + X. Esc menutup.

### 3.4 Tentang (`/tentang`)
- Alur kerja, batasan jujur (kamera mono, siang hari, estimasi bukan RAB, kalibrasi),
  tabel harga acuan per severity, metrik model. Nada: transparan, bukan marketing.

## 4. Kontrak ID (JS hook — jangan rename/hapus)

- Deteksi gambar: `form-deteksi gambar conf conf-out malam lokasi-gambar
  lat-gambar lon-gambar tombol status slot-gambar viewer-gambar hasil
  temuan-nilai berat-nilai total-nilai tabel unduh simpan`
- Tab: `tab-gambar tab-live panel-gambar panel-live`
- Live: `slot-live viewer-live stat-cards fps-stat unik-stat deteksi-stat
  frame-stat sumber in-webcam webcam-idx in-ipcam ipcam-url in-file video
  conf-live conf-live-out skip malam-live lokasi lat-live lon-live mulai
  berhenti demo status-live hasil-live total-live-nilai tabel-live unduh-live
  simpan-live`
- Peta: `map peta-kosong peta-hitung chip-tutup` (+ class `f-sev`)
- Riwayat: `filter f-dari f-sampai f-sev f-q daftar detail d-judul d-foto
  d-tabel d-pdf d-hapus d-tutup d-x d-status`
- Global: `main-content toast-container nav-toggle nav-tray`

## 5. Alur kerja Stitch → Flask

1. Generate desain per halaman di Stitch (lihat `PROMPT_STITCH.md`).
2. Export HTML/CSS (Tailwind CDN boleh saat desain, akan saya ganti CSS murni).
3. Saya yang port ke `web/templates/` + `web/static/css/` dengan kontrak ID di atas.
