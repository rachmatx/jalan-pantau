# User Flow — JalanPantau

Dokumen ini memetakan alur pengguna (user flow) aplikasi **JalanPantau**: aplikasi
deteksi kerusakan jalan berbasis Flask + YOLOv11.

Dokumen ini bersifat **deskriptif**, bukan kontrak engineering. Batasan
implementasi yang mengikat ada di [`../DESIGN.md`](../DESIGN.md); daftar route
lengkap ada di [`API.md`](API.md).

> **Scope (Okt 2026):** aplikasi ini **satu peran saja (admin)** dan berjalan
> lokal (bind `127.0.0.1`). Fitur lama — dashboard PUPR, disposisi/instansi,
> peran kontraktor, dan mode mobile — sudah **dihapus** dari kode; lihat riwayat
> git. Alur di bawah mengikuti route yang benar-benar terdaftar di `web/app.py`.

---

## 1. Daftar Isi

- [2. Ringkasan Arsitektur](#2-ringkasan-arsitektur)
- [3. Persona & Peran](#3-persona--peran)
- [4. Peta Navigasi](#4-peta-navigasi)
- [5. Alur Utama — Deteksi Gambar](#5-alur-utama--deteksi-gambar)
- [6. Alur Utama — Live Stream Real-Time](#6-alur-utama--live-stream-real-time)
- [7. Alur Riwayat, Peta & Laporan](#7-alur-riwayat-peta--laporan)
- [8. Diagram Pipeline Inferensi](#8-diagram-pipeline-inferensi)
- [9. Arsitektur 3-Thread Live Streaming](#9-arsitektur-3-thread-live-streaming)
- [10. Peta Kode Sumber](#10-peta-kode-sumber)

---

## 2. Ringkasan Arsitektur

Aplikasi ini adalah **Flask monolith** tanpa build step, server-side rendering
menggunakan Jinja2, dan vanilla JavaScript di sisi klien.

```
┌────────────────────────────┐
│         Browser            │
│  (Jinja2 + Leaflet + JS)   │
└───────────┬────────────────┘
            │ HTTP / JSON / MJPEG
┌───────────▼────────────────┐
│      Flask App             │
│      web/app.py            │
│  ┌───────────────────────┐ │
│  │ Auth · CSRF · Rate    │ │
│  │ Limit · Security Hdrs │ │
│  └───────────────────────┘ │
└───┬───────────┬───────────┘
    │           │
    │           ├──► web/deteksi.py     (Pipeline inferensi gambar)
    │           ├──► web/streaming.py   (Live 3-thread + ByteTrack)
    │           └──► app/laporan.py     (PDF via fpdf2)
    │
┌───▼────────────────────────┐
│   web/database.py          │
│   SQLite (riwayat.db)      │
└────────────────────────────┘
```

**Model Machine Learning** (satu model: YOLOv11s untuk gambar **dan** live):

| Peran | Model | Format | Config |
|-------|-------|--------|--------|
| Deteksi gambar (statis) | YOLOv11s | `.pt` (PyTorch) | `model_gambar` |
| Live stream (webcam/IP-cam/video) | YOLOv11s | `.onnx` (ONNX Runtime) | `model_live` |
| Cadangan (ensemble, nonaktif) | — | `.pt` | `ensemble` |

Kelas yang dideteksi: `longitudinal_crack`, `transverse_crack`,
`alligator_crack`, `other_corruption`, `pothole`.

Dataset latih: **RDD2022** (anotasi *bounding box*, bukan mask).

---

## 3. Persona & Peran

Hanya ada **satu peran terautentikasi (admin)**. Operator lapangan memakai
halaman publik tanpa login (aplikasi sengaja berjalan lokal untuk satu operator).

| Persona | Login | Halaman | Kemampuan |
|---------|-------|---------|-----------|
| **Operator** (publik) | tidak | `/`, `/peta`, `/riwayat`, `/tentang` | Deteksi gambar/live, koreksi hasil, simpan riwayat, unduh PDF, lihat peta |
| **Admin** | ya (session) | `+ /kalibrasi` | Semua di atas **plus** ubah kalibrasi `px/cm` dan hapus riwayat |

### Aturan Otorisasi (ditegakkan di server)

- Hanya **`POST /api/kalibrasi`**, **`POST /api/kalibrasi/foto`**, dan
  **`DELETE /api/riwayat/<sid>`** yang butuh login (API → `401` JSON; halaman
  `/kalibrasi` → redirect `/login`).
- Sisanya publik, namun dibatasi **rate-limit** (lihat [`API.md`](API.md)).
- Kepemilikan stream live dijaga satu **token**: saat stream berjalan,
  `start`/`stop`/`anotasi`/`snapshot` dari tab lain ditolak (`409`/`403`) bila
  tak menyertakan token pemilik.

---

## 4. Peta Navigasi

```mermaid
graph TD
    START([Buka aplikasi]) --> HOME["/ — Deteksi<br/>(tab: Gambar | Live)"]

    HOME --> PETA["/peta"]
    HOME --> RIWAYAT["/riwayat"]
    HOME --> TENTANG["/tentang"]
    HOME --> KALIBRASI["/kalibrasi 🔒"]

    KALIBRASI -->|belum login| LOGIN["/login"]
    LOGIN -->|sukses| KALIBRASI

    PETA --> DETAIL["Klik marker<br/>→ detail + foto bukti"]
    RIWAYAT --> DETAILR["Klik baris<br/>→ modal detail"]
    DETAILR --> PDF["Unduh / pratinjau PDF"]
```

---

## 5. Alur Utama — Deteksi Gambar

```mermaid
flowchart TD
    U(["Pengguna membuka halaman utama"]) --> TAB["Tab: Gambar"]
    TAB --> PILIH["Pilih file gambar<br/>(jpg/png, ≤15MB)"]
    PILIH --> KALIB["Butuh kalibrasi px/cm?<br/>/kalibrasi 🔒"]

    PILIH --> POST["POST /api/detect"]
    POST --> VAL{"Validasi:<br/>ext · magic-byte · ukuran"}
    VAL -->|Gagal| ERR1["Tolak (400)"]
    VAL -->|OK| ANALISIS["analisis_gambar()"]

    ANALISIS --> PRE["Preprocessing:<br/>decode · CLAHE malam"]
    PRE --> INFER["predict<br/>YOLOv11s @ imgsz=960 (+TTA)"]
    INFER --> POST1["Postprocessing:<br/>severity · skor prioritas"]
    POST1 --> SARING["Saring 3 lapis:<br/>conf · masuk akal · luas min"]
    SARING --> GABUNG["Gabung fragmen<br/>union-find IoU"]
    GABUNG --> TOPK["Batas top-20"]
    TOPK --> ANOT["Anotasi gambar<br/>→ base64 JPEG"]

    ANOT --> TAMPIL["Tampilkan tabel + gambar anotasi"]

    TAMPIL --> VERIF{"Butuh koreksi?"}
    VERIF -->|Ya| VERIFIKASI["POST /api/verifikasi<br/>(hapus baris / ubah severity)"]
    VERIF -->|Tidak| LANJUT

    VERIFIKASI --> LANJUT{"Pilih aksi"}

    LANJUT --> PDF["Unduh PDF<br/>POST /api/laporan<br/>berita acara"]
    LANJUT --> SIMPAN["Simpan riwayat<br/>POST /api/riwayat"]
    LANJUT --> KEMBALI["Ulangi / ganti gambar"]

    SIMPAN --> DB[("SQLite:<br/>sesi + temuan<br/>+ gambar + thumbnail")]
```

### Kunci Teknis Alur Ini

1. **Validasi berlapis** — ekstensi **dan** magic byte (`\xff\xd8\xff` /
   `\x89PNG`) diperiksa, bukan hanya header. Batas ukuran 15 MB.
2. **Mode malam** — CLAHE diterapkan di kanal L (LAB), hanya fotometrik;
   geometri tidak berubah.
3. **Mode teliti** — *tiling* grid 640 dengan overlap 0,25; box yang menyentuh
   tepi dalam tile dibuang; digabung lintas tile via NMS/WBF.
4. **Pseudo-segmentation** — luas diestimasi dari kontur (Otsu/adaptive +
   morphology) di dalam bounding box. **Bukan** mask segmentasi model.
5. **Angka otoritatif** — skor tidak dipercaya dari klien: server menghitung
   ulang **total sesi** (= jumlah skor temuan) dan **skor tiap temuan** dari
   `severity` (Ringan 33 / Sedang 67 / Berat 100, rumus `app/prioritas.py`).

---

## 6. Alur Utama — Live Stream Real-Time

```mermaid
flowchart TD
    U(["Pengguna membuka halaman utama"]) --> TAB["Tab: Live"]
    TAB --> PILIH_SRC{"Pilih sumber"}

    PILIH_SRC -->|Webcam| WEBCAM["POST /api/stream/start<br/>sumber=webcam, index=0..10"]
    PILIH_SRC -->|IP Camera| IPCAM["POST /api/stream/start<br/>sumber=ipcam, URL http/https"]
    PILIH_SRC -->|Upload Video| UPLOAD["POST /api/video<br/>≤200MB → tempfile"]
    PILIH_SRC -->|Contoh| DEMO["POST /api/demo<br/>demo_jalan.mp4"]

    IPCAM --> SSRF{"Validasi anti-SSRF<br/>(loopback/IP terobfuskasi ditolak)"}
    SSRF -->|Gagal| ERR["Tolak (400)"]

    WEBCAM --> TOKEN
    UPLOAD --> TOKEN
    DEMO --> TOKEN

    TOKEN["Terbit token kepemilikan"]
    TOKEN --> MJPEG["GET /api/stream<br/>MJPEG multipart"]
    TOKEN --> STATS["GET /api/stream/stats<br/>polling ~1 detik"]

    MJPEG --> LAYER["Compose: overlay terakhir<br/>→ frame segar → JPEG"]
    STATS --> MONITOR["FPS tampil · FPS infer<br/>frame · track unik · deteksi"]

    LAYER --> SNAP{"Aksi pengguna?"}
    SNAP -->|Snapshot| SNAPSHOOT["POST /api/stream/snapshot<br/>rows per track-id"]
    SNAP -->|Toggle anotasi| ANNOTASI["POST /api/stream/anotasi"]
    SNAP -->|Berhenti| STOP["POST /api/stream/stop"]

    SNAPSHOOT --> SAMA["Sama seperti alur gambar:<br/>PDF · Simpan riwayat"]
    ANNOTASI --> SNAP
    STOP --> TAB
```

### Catatan Kinerja

- Inferensi live ONNX @480 ≈ **326 ms/frame** (~3 FPS infer).
- FPS **tampil** preview tetap **15+** karena arsitektur *decouple* 3-thread.
- Preset performa: `halus` (320/3/30) · `seimbang` (480/2/25) · `akurat` (640/1/15).

---

## 7. Alur Riwayat, Peta & Laporan

Setelah hasil deteksi (gambar atau snapshot live) ditinjau dan — bila perlu —
dikoreksi operator:

```mermaid
flowchart TD
    HASIL(["rows + total + image_b64"]) --> PILIH{"Pilih aksi"}

    PILIH --> SIMPAN["POST /api/riwayat"]
    PILIH --> PDF["POST /api/laporan → PDF"]

    SIMPAN --> IDEM{"client_ref sudah ada?"}
    IDEM -->|Ya| DUP["Kembalikan id lama<br/>(idempoten)"]
    IDEM -->|Tidak| CEK{"Koordinat sama<br/>≤10 menit?"}
    CEK -->|Ya, tanpa izinkan_duplikat| TOLAK["Kembalikan id lama<br/>(alasan: koordinat)"]
    CEK -->|Tidak| TULIS[("INSERT sesi + temuan<br/>+ gambar + thumbnail")]
    TULIS --> MAP["Muncul di /peta<br/>(GET /api/peta)"]

    RIWAYAT["/riwayat"] --> DAFTAR["GET /api/riwayat<br/>(filter dari/sampai/severity/q)"]
    DAFTAR --> DETAIL["GET /api/riwayat/&lt;sid&gt;<br/>detail + temuan"]
    DETAIL --> GAMBAR["GET /api/riwayat/&lt;sid&gt;/gambar<br/>(?thumb=1)"]
    DETAIL --> PREVIEW["/laporan/preview/&lt;sid&gt;"]
    RIWAYAT --> HAPUS["DELETE /api/riwayat/&lt;sid&gt; 🔒"]
```

### Aturan Penting

- **Idempoten**: `client_ref` yang sama tidak membuat baris baru (aman dari klik
  dobel / retry jaringan).
- **Anti-duplikat titik**: koordinat sama dalam 10 menit terakhir ditolak kecuali
  `izinkan_duplikat: true`.
- **Skor server-side**: `total` = jumlah skor temuan, dan skor tiap temuan
  diturunkan dari `severity` — nilai dari klien diabaikan.
- **PDF** (`POST /api/laporan`) dibangun ulang tiap permintaan; berkas sementara
  dihapus setelah dikirim (dibaca ke memori lebih dulu agar tidak terkunci di
  Windows).

---

## 8. Diagram Pipeline Inferensi

```mermaid
flowchart TD
    IN["Input: gambar / frame"] --> PRE

    subgraph PRE ["Preprocessing"]
        DECODE["Decode (OpenCV)"]
        DECODE --> MALAM{"Mode malam?"}
        MALAM -->|Ya| CLAHE["CLAHE kanal L (LAB)"]
        MALAM -->|Tidak| LANJUT
        CLAHE --> LANJUT["Siap inferensi"]
    end

    LANJUT --> MODE{"Mode inferensi?"}

    MODE -->|Normal| NORMAL["predict @ imgsz=960 (+TTA)"]
    MODE -->|Teliti| TELITI["Tiling 640 · overlap 0.25<br/>buang tepi · gabung NMS/WBF"]
    MODE -->|Ensemble| ENSEMBLE["prediksi_ensemble<br/>WBF / NMS per kelas (nonaktif)"]
    MODE -->|Live| LIVE["model.track + ByteTrack<br/>@ imgsz=480 · persist"]

    NORMAL --> HASIL
    TELITI --> HASIL
    ENSEMBLE --> HASIL
    LIVE --> HASIL

    subgraph HASIL ["Postprocessing — analisis_gambar()"]
        H1["proses_detections()"]
        H1 --> H2["diagnose() → severity<br/>Ringan / Sedang / Berat"]
        H2 --> H3["skor() → indeks prioritas<br/>Ringan 33 / Sedang 67 / Berat 100"]
        H3 --> H4["Pseudo-segmentation<br/>kontur Otsu → luas (m²)"]
        H4 --> H5["saring_rows()<br/>3 lapis saringan"]
        H5 --> H6["gabung_fragmen()<br/>union-find IoU"]
        H6 --> H7["batas_topk()<br/>maks 20 temuan"]
        H7 --> H8["anotasi + encode JPEG"]
    end

    HASIL --> OUT(["Kirim ke klien:<br/>rows[] · total · image_b64 · gps"])
```

### Jalur Saringan (3 Lapis)

| Lapis | Kriteria | Sumber |
|-------|----------|--------|
| 1 | `conf < ambang_efektif` per kelas | `toleransi_kelas` di `config/inferensi.yaml` |
| 2 | Ukuran fisik tidak masuk akal | `batas_ukuran` (300cm / 100cm / 100m²) |
| 3 | Luas piksel < `luas_min_px` (default 900) | `saring.luas_min_px` |

---

## 9. Arsitektur 3-Thread Live Streaming

Kunci kenapa preview tetap halus meski inferensi lambat: **decoupling** tiga
pekerjaan ke thread terpisah.

```mermaid
flowchart LR
    subgraph T1 ["Thread 1 · _capture_worker"]
        CAM["Kamera / Video"] -->|"frame terbaru"| BUF[("Buffer<br/>BUFFERSIZE=1")]
    end

    subgraph T2 ["Thread 2 · _infer_worker"]
        BUF --> PULL["Tarik tiap<br/>infer_interval frame"]
        PULL --> YOLO["model.track<br/>ByteTrack"]
        YOLO --> OVERLAY[("Overlay terakhir<br/>boxes + track-id")]
        YOLO --> EMA["FPS EMA"]
    end

    subgraph T3 ["Thread 3 · _loop"]
        BUF --> FRESH["Frame segar"]
        OVERLAY --> FRESH
        FRESH --> COMPOSE["Compose & resize"]
        COMPOSE --> JPEG["Encode JPEG<br/>quality 72"]
        JPEG --> NOTIFY["Condition.notify()"]
    end

    NOTIFY --> BROWSER["Browser <img src=/api/stream><br/>MJPEG multipart"]
    EMA --> STATS["/api/stream/stats"]

    OVERLAY --> TRACKS[("_simpan_tracks<br/>voting temporal<br/>MAX_TRACKS=500")]
    TRACKS --> SNAP["/api/stream/snapshot<br/>min_frames + kelas suara"]
```

**Prinsip:** thread capture tidak pernah menunggu inferensi. Inferensi boleh
lag, tapi preview tidak boleh *stall*.

---

## 10. Peta Kode Sumber

Baris dapat bergeser seiring perubahan; nama fungsi/route adalah acuan utama.

### Route (`web/app.py`)

| Route | Baris | Catatan |
|-------|-------|---------|
| `GET/POST /login`, `GET /logout` | 244 / 250 / 272 | Autentikasi admin |
| `GET /` | 336 | Deteksi (tab Gambar & Live) |
| `GET /peta` | 340 | Peta sebaran GPS |
| `GET /riwayat` | 344 | Riwayat inspeksi |
| `GET /tentang` | 348 | Tentang & metrik model |
| `GET /kalibrasi` | 352 | 🔒 Kalibrasi `px/cm` |
| `GET /laporan/preview/<sid>` | 357 | Pratinjau berita acara |
| `POST /api/detect` | 365 | Deteksi gambar |
| `GET /api/kalibrasi` | 402 | Status kalibrasi |
| `POST /api/kalibrasi` | 413 | 🔒 Simpan kalibrasi |
| `POST /api/kalibrasi/foto` | 439 | 🔒 Foto penggaris → gambar+ukuran |
| `POST /api/verifikasi` | 478 | Koreksi operator |
| `POST /api/laporan` | 497 | Generate PDF |
| `GET /api/stream` | 529 | MJPEG |
| `POST /api/stream/start` | 598 | Mulai live stream |
| `POST /api/stream/stop` | 640 | Hentikan (token pemilik) |
| `GET /api/stream/stats` | 652 | FPS · track · deteksi |
| `POST /api/stream/anotasi` | 657 | Toggle anotasi box |
| `POST /api/stream/snapshot` | 666 | Snapshot per track |
| `POST /api/demo` | 678 | Video contoh bawaan |
| `POST /api/video` | 706 | Upload berkas video |
| `POST /api/riwayat` | 763 | Simpan sesi |
| `GET /api/riwayat` | 811 | Daftar riwayat |
| `GET /api/riwayat/<sid>` | 827 | Detail sesi |
| `DELETE /api/riwayat/<sid>` | 834 | 🔒 Hapus sesi |
| `GET /api/riwayat/<sid>/gambar` | 842 | JPEG bukti |
| `GET /api/peta` | 855 | Titik peta (publik) |

### Fungsi Inti

| Fungsi | File | Baris |
|--------|------|-------|
| `analisis_gambar` | `web/deteksi.py` | 1014 |
| `prediksi_teliti` | `web/deteksi.py` | 920 |
| `proses_detections` | `web/deteksi.py` | 625 |
| `gabung_fragmen` | `web/deteksi.py` | 647 |
| `saring_rows` | `web/deteksi.py` | 384 |
| `terapkan_koreksi` | `web/deteksi.py` | 419 |
| `get_model` (singleton) | `web/deteksi.py` | 567 |
| `kanonik_kelas` / `nama_kelas` | `web/deteksi.py` | 539 / 558 |
| `diagnose` (severity) | `app/severity.py` | 53 |
| `skor` (indeks prioritas) | `app/prioritas.py` | 31 |
| `total_prioritas` | `app/prioritas.py` | 56 |
| `buat_laporan` (PDF) | `app/laporan.py` | 35 |
| `simpan_sesi` | `web/database.py` | 248 |
| `daftar_sesi` | `web/database.py` | 344 |
| `detail_sesi` | `web/database.py` | 360 |
| `titik_peta` | `web/database.py` | 388 |
| `StreamManager` | `web/streaming.py` | 42 |

---

## Lampiran — Catatan Limitation yang Jujur

Aplikasi ini **sengaja** menyatakan batasan berikut (dari README & DESIGN):

1. **Bukan segmentasi.** Deteksi *bounding box*; luas diestimasi dari kontur
   di dalam box (*pseudo-segmentation*), bukan mask model.
2. **Akurasi belum mencapai target.** YOLOv11s: mAP50 val 0,616, test 0,617
   (target ≥ 0,65 belum tercapai). Dataset latih RDD2022 (India/Jepang).
3. **Kamera mono tidak mengukur kedalaman.** Tebal = asumsi per severity.
4. **Skor prioritas = indeks relatif** (Ringan 33 / Sedang 67 / Berat 100),
   bukan RAB/biaya resmi. Tidak ada komponen harga.
5. **Mode malam hanya fotometrik** (CLAHE), tidak menambah sumber cahaya.
6. **Istilah**: selalu "indeks/skor prioritas", **tidak pernah** "biaya
   perbaikan" mutlak.

---

*Dokumen ini dibuat untuk keperluan dokumentasi skripsi. Struktur route dan
nama fungsi diverifikasi langsung dari kode sumber (baris per Okt 2026).*
