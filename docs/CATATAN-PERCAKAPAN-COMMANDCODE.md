# Catatan Percakapan Command-Code

> **Model**: longcat-2.0
> **Aplikasi**: Command-Code CLI
> **Tanggal**: 2026-09-06
> **Topik**: Perbaikan UI/UX Aplikasi JalanPantau + Integrasi Dashboard PUPR

---

## Daftar Isi
1. [Perbaikan UI/UX Awal](#perbaikan-uiux-awal)
2. [Penghapusan Pico CSS](#penghapusan-pico-css)
3. [Fitur Session Storage](#fitur-session-storage)
4. [Halaman Riwayat](#halaman-riwayat)
5. [Halaman Peta](#halaman-peta)
6. [Halaman Disposisi](#halaman-disposisi)
7. [Dashboard PUPR](#dashboard-pupr)
8. [Responsive Mobile](#responsive-mobile)
9. [Database Instansi Jawa Barat](#database-instansi-jawa-barat)
10. [Bug & Solusi](#bug--solusi)

---

## Perbaikan UI/UX Awal

### Masalah
- Navbar terlalu pendek (27px, seharusnya 64px)
- Badge "YOLOv11n • TA 2025 Model Siap" mengganggu
- Animasi loading terlalu kecil dan di pojok kiri atas
- Peta tidak menampilkan lokasi GPS pengguna

### Solusi
```css
/* Navbar height */
.jp-topbar-in { height: 64px; }
body { padding-top: 64px; } /* Dihapus setelah sticky */

/* Loading animation - centered */
.jp-loading {
  position: absolute;
  top: 50%; left: 50%;
  transform: translate(-50%, -50%);
}
.jp-loading-spinner {
  width: 56px; height: 56px;
  border: 4px solid var(--jp-line);
  border-top-color: var(--jp-primary);
  border-radius: 50%;
  animation: jp-spin 0.8s linear infinite;
}
```

### File yang Diubah
- `web/static/css/civic.css`
- `web/templates/base.html`
- `web/static/js/peta.js`

---

## Penghapusan Pico CSS

### Masalah
Pico CSS menambah padding/margin yang tidak diinginkan:
- `padding: 20px` pada `<header>` dan `<main>`
- `margin-bottom: 20px` pada semua `<button>`
- `padding: 15px` + `height` spesifik pada `<input>`

Ini membuat elemen membengkak dan harus di-override terus-menerus dengan `!important`.

### Solusi
1. Hapus link `pico.min.css` dari `base.html`
2. Hapus blok netralisasi Pico di `civic.css`
3. civic.css menjadi satu-satunya otoritas styling

```html
<!-- DIHAPUS dari base.html -->
<link rel="stylesheet" href="/static/css/pico.min.css">
```

---

## Fitur Session Storage

### Masalah
Hasil deteksi hilang saat user pindah halaman (Peta/Riwayat) lalu kembali ke Deteksi.

### Solusi
```javascript
// Simpan hasil ke sessionStorage
sessionStorage.setItem("jp_hasil_terakhir", JSON.stringify(data));

// Saat halaman load, restore dari sessionStorage
var saved = sessionStorage.getItem("jp_hasil_terakhir");
if (saved) { tampilkanHasil(JSON.parse(saved)); }
```

### File yang Diubah
- `web/static/js/deteksi.js`

---

## Halaman Riwayat

### Masalah
- Filter card terlalu tinggi (142px)
- Ikon search dan placeholder terlalu berdekatan
- Tombol Hapus/Tutup/PDF di modal terpotong

### Solusi
```css
/* Filter card lebih ramping */
.jp-filtercard { padding: 14px 16px; }
.jp-filtergrid label { margin-bottom: 5px; }

/* Modal footer selalu terlihat */
.dialog-body { flex: 1; overflow-y: auto; }
.dialog-footer { flex-shrink: 0; padding-top: 16px; border-top: 1px solid var(--jp-line); }
```

### File yang Diubah
- `web/templates/riwayat.html`
- `web/static/css/civic.css`

---

## Halaman Peta

### Masalah
- Drawer Ringkasan Wilayah terlalu kecil
- GPS tidak terbaca (marker tidak muncul)
- Tidak ada fitur navigasi ke titik terdekat

### Solusi
```javascript
// GPS Live Tracking
navigator.geolocation.watchPosition(function(pos) {
  var lat = pos.coords.latitude;
  var lon = pos.coords.longitude;
  // Update marker posisi user setiap 5 detik atau bergerak > 10 meter
}, { enableHighAccuracy: true, maximumAge: 5000, distanceFilter: 10 });

// Reverse Geocoding (koordinat → nama jalan)
fetch("https://nominatim.openstreetmap.org/reverse?format=json&lat=" + lat + "&lon=" + lon)
  .then(r => r.json())
  .then(data => {
    document.getElementById("lokasi-gambar").value = data.display_name || "";
  });
```

### File yang Diubah
- `web/templates/peta.html`
- `web/static/js/peta.js`

---

## Halaman Disposisi

### Masalah
- Tidak ada halaman untuk kirim laporan ke instansi pemerintah
- Tidak ada tracking status laporan
- Layout tidak sesuai desain Stitch

### Solusi
Dibuat 2 halaman baru:
1. **`/disposisi`** - Form kirim laporan ke instansi
2. **`/disposisi/<id>`** - Detail tracking status laporan

### Fitur
- Pilih BAP (10 entry terbaru + pagination)
- Pilih instansi berdasarkan koordinat (otomatis rekomendasi terdekat)
- Cari instansi lain (search)
- Preview BAP sebelum kirim
- Catatan pengantar otomatis dari YOLOv11
- Penerima resmi menyesuaikan instansi tujuan

### File yang Dibuat
- `web/templates/disposisi_kirim.html`
- `web/templates/disposisi_detail.html`
- `web/static/js/disposisi.js`
- Route di `app.py`

---

## Dashboard PUPR

### Masalah
- Tidak ada dashboard untuk petugas pemerintah
- Tidak bisa melihat detail laporan yang dikirim pengguna
- Status tidak sinkron antara dashboard dan detail

### Solusi
Dibuat dashboard dengan route spesifik per daerah:
```
/pupr-{daerah}/dashboard          → Dashboard utama
/pupr-{daerah}/dashboard/disposisi → Daftar laporan
/pupr-{daerah}/dashboard/disposisi/{id} → Detail laporan
```

### Fitur Dashboard
- KPI Cards (Baru, Diproses, Selesai, Total)
- Filter status (Semua, Terkirim, Diproses, Selesai)
- Pencarian by nomor tiket atau lokasi
- Detail BAP: foto bukti, tabel kerusakan, peta lokasi
- Timeline status penanganan
- Form update status

### File yang Dibuat
- `web/templates/dashboard/base.html`
- `web/templates/dashboard/index.html`
- `web/templates/dashboard/disposisi.html`
- `web/templates/dashboard/disposisi_detail.html`
- `web/static/css/dashboard.css`
- `web/static/js/dashboard.js`

---

## Responsive Mobile

### Masalah
- Navbar terlalu panjang di mobile
- Container terlalu lebar
- Dropdown menu hilang saat scroll
- Beberapa menu (Disposisi, Kalibrasi) tidak muncul di mobile

### Solusi
```css
/* Mobile (< 768px) */
@media (max-width: 768px) {
  /* Navbar */
  .jp-topbar { height: 48px; }
  .jp-nav { display: none; } /* Ganti hamburger */
  
  /* Nav-tray sticky */
  .nav-tray { position: sticky; top: 48px; z-index: 1500; }
  
  /* Disposisi 1 kolom */
  .disp-grid { grid-template-columns: 1fr; }
  
  /* Tabel compact */
  table { font-size: 10px; }
  td, th { padding: 4px 2px; }
  
  /* Tombol lebih kecil */
  .jp-btn { padding: 8px 12px; font-size: 12px; }
}
```

### File yang Diubah
- `web/templates/base.html` (nav-tray ditambah menu Disposisi & Kalibrasi)
- `web/templates/disposisi_kirim.html` (class responsive)
- `web/static/css/civic.css` (media query mobile)

---

## Database Instansi Jawa Barat

### Masalah
Hanya ada 3 instansi (Bandung, Bogor, Jakarta). User ingin semua kota di Jawa Barat.

### Solusi
Ditambah **37 instansi pemerintah** (18 Kabupaten + 9 Kota di Jawa Barat + 4 luar Jabar):

| # | Instansi | Daerah |
|---|----------|--------|
| 1 | DSDABM Kota Bandung | Bandung |
| 2 | Dinas Bina Marga Kab. Bandung | Bandung |
| ... | ... | ... |
| 18 | Dinas Bina Marga Kab. Cirebon | Cirebon |
| 19 | Dinas Bina Marga Kota Banjar | Banjar |
| 20-23 | Kota Bogor, Depok, Cimahi, Bekasi | Bogor/Depok/Cimahi/Bekasi |
| 24 | Dinas Bina Marga DKI Jakarta | Jakarta |

### Struktur Tabel
```sql
CREATE TABLE instansi_pemerintah (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nama TEXT NOT NULL UNIQUE,
  daerah TEXT NOT NULL,
  alamat TEXT,
  email TEXT,
  telepon TEXT,
  lat REAL,
  lon REAL
);
```

### Fungsi Pencarian Terdekat
```python
def instansi_terdekat(lat, lon, limit=5):
    # Haversine formula
    # Return instansi terdekat berdasarkan koordinat
```

### File yang Diubah
- `web/database.py` (tabel + fungsi CRUD instansi)
- `web/app.py` (API endpoints)

---

## Bug & Solusi

### 1. Jinja2 Template Cache
**Gejala**: Perubahan template tidak terlihat meski sudah restart server.
**Penyebab**: Flask production mode cache template.
**Solusi**:
```python
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True
```

### 2. CSS Desktop Override Mobile
**Gejala**: Tampilan mobile tidak berubah meski sudah hard refresh.
**Penyebab**: CSS desktop ditulis SETELAH media query, sehingga selalu menimpa.
**Solusi**: Gunakan pendekatan mobile-first atau pastikan media query di akhir file.

### 3. Jinja2 `|format` Filter Error
**Gejala**: `ValueError: unsupported format character` atau `TypeError: not all arguments converted`.
**Penyebab**: Menggunakan syntax Python `.format()` (`{:,.0f}`) di Jinja2 `|format` filter yang menggunakan `%`.
**Solusi**: Gunakan syntax `%` untuk Jinja2:
```jinja
{# SALAH #}
{{ '{:,.0f'|format(value) }}

{# BENAR #}
{{ '%.0f'|format(value) }}  {# Untuk float #}
{{ '%d'|format(value) }}    {# Untuk integer #}
```

### 4. `current_app` Not Defined
**Gejala**: `NameError: name 'current_app' is not defined` di route.
**Penyebab**: Menggunakan `current_app` tanpa import.
**Solusi**:
```python
from flask import Flask, render_template, current_app
```

### 5. Pico CSS Conflict
**Gejala**: Elemen membengkak (padding/margin berlebih).
**Penyebab**: Reset Pico memberi `padding: 20px` pada header/main, `margin-bottom: 20px` pada button, dll.
**Solusi**: Hapus Pico CSS sepenuhnya.

### 6. BAP ID vs Disposisi ID
**Gejala**: Status tidak sinkron antara dashboard dan detail publik.
**Penyebab**: Route `/disposisi/{id}` mencari by `id` disposisi, tapi yang dikirim adalah `bap_id`.
**Solusi**: Query by `bap_id` dulu, fallback by `id`:
```python
def detail_disposisi_by_bap(bap_id):
    row = query("SELECT * FROM disposisi WHERE bap_id = ?", [bap_id])
    return row[0] if row else None
```

### 7. Sticky Nav-tray Hilang Saat Scroll
**Gejala**: Dropdown menu mobile hilang saat user scroll ke bawah.
**Penyebab**: Nav-tray tidak sticky.
**Solusi**:
```css
.nav-tray { position: sticky; top: 48px; z-index: 1500; }
```

---

## Cara Mengatasi Bug Cache

### Browser Cache
1. **Hard Refresh**: `Ctrl + Shift + R` (Windows) atau `Cmd + Shift + R` (Mac)
2. **DevTools**: F12 → klik kanan tombol refresh → "Empty Cache and Hard Reload"
3. **Query String**: `http://127.0.0.1:5000/?v=29`

### Jinja2 Cache
```python
# Di app.py
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True
```

### Python Cache
```bash
# Hapus __pycache__
Remove-Item -Recurse -Force web/__pycache__
Remove-Item -Recurse -Force app/__pycache__
```

---

## Cache-Buster Version History

| Versi | Perubahan |
|-------|-----------|
| v29 | Responsive disposisi, search icon kanan |
| v28 | Dashboard detail BAP lengkap |
| v27 | Hapus spinner loading, pagination tabel |
| v26 | Integrasi dashboard eksekutif |
| v25 | Sinkronisasi status BAP |
| v24 | Detail disposisi sesuai Stitch |
| v23 | Animasi loading, sticky navbar |
| v22 | 37 instansi Jawa Barat |
| v21 | Pagination tabel hasil deteksi |
| v20 | Sinkronisasi status |
| ... | ... |

---

## Struktur File Akhir

```
web/
├── app.py                    # Routes + API
├── database.py               # Database schema + queries
├── deteksi.py                # YOLO inference
├── laporan.py                # PDF generation
├── static/
│   ├── css/
│   │   ├── civic.css         # Main styles
│   │   └── dashboard.css     # Dashboard styles
│   └── js/
│       ├── deteksi.js        # Detection logic
│       ├── peta.js           # Map + GPS
│       ├── riwayat.js        # History + modal
│       ├── disposisi.js      # Disposisi form
│       ├── dashboard.js      # Dashboard logic
│       └── lokasi_dinamis.js # Location helper
└── templates/
    ├── base.html             # Main layout
    ├── deteksi.html          # Detection page
    ├── peta.html             # Map page
    ├── riwayat.html          # History page
    ├── tentang.html          # About page
    ├── disposisi_kirim.html  # Send report
    ├── disposisi_detail.html # Report tracking
    ├── kalibrasi.html        # Calibration
    ├── mobile.html           # Mobile view
    ├── laporan_preview.html  # PDF preview
    └── dashboard/
        ├── base.html         # Dashboard layout
        ├── index.html        # Dashboard home
        ├── disposisi.html    # Report list
        └── disposisi_detail.html  # Report detail
```

---

## Referensi

- **Stitch Design**: `stitch_aplikasi_deteksi_kerusakan_jalan/`
- **Command-Code Model**: longcat-2.0
- **Framework**: Flask + Jinja2 + SQLite
- **CSS**: Custom civic-design (tanpa framework)
- **JS**: Vanilla JS (tanpa framework)
