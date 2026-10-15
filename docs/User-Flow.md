# User Flow — JalanPantau

Dokumen ini memetakan alur pengguna (user flow) aplikasi **JalanPantau**: aplikasi
deteksi kerusakan jalan *real-time* berbasis Flask + YOLOv11.

Dokumen ini bersifat **deskriptif**, bukan kontrak engineering. Batasan
implementasi yang mengikat ada di [`../DESIGN.md`](../DESIGN.md).

---

## 1. Daftar Isi

- [2. Ringkasan Arsitektur](#2-ringkasan-arsitektur)
- [3. Persona & Peran](#3-persona--peran)
- [4. Peta Navigasi](#4-peta-navigasi)
- [5. Alur Utama — Deteksi Gambar](#5-alur-utama--deteksi-gambar)
- [6. Alur Utama — Live Stream Real-Time](#6-alur-utama--live-stream-real-time)
- [7. Alur Verifikasi & Penerbitan SPK](#7-alur-verifikasi--penerbitan-spk)
- [8. Alur Kerja Kontraktor](#8-alur-kerja-kontraktor)
- [9. Alur Penerimaan Hasil Kerja (BAST)](#9-alur-penerimaan-hasil-kerja-bast)
- [10. Diagram State Machine Status](#10-diagram-state-machine-status)
- [11. Diagram Pipeline Inferensi](#11-diagram-pipeline-inferensi)
- [12. Arsitektur 3-Thread Live Streaming](#12-arsitektur-3-thread-live-streaming)
- [13. Peta Kode Sumber](#13-peta-kode-sumber)

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

**Model Machine Learning:**

| Peran | Model | Format | Config |
|-------|-------|--------|--------|
| Deteksi gambar (statis) | YOLOv11s | `.pt` (PyTorch) | `model_gambar` |
| Live stream (webcam/IP-cam/video) | YOLOv11n | `.onnx` (ONNX Runtime) | `model_live` |
| Cadangan (ensemble, nonaktif) | — | `.pt` | `ensemble` |

Kelas yang dideteksi: `longitudinal_crack`, `transverse_crack`,
`alligator_crack`, `other_corruption`, `pothole`.

Dataset latih: **RDD2022** (14.176 gambar, anotasi *bounding box* 5 kolom).

---

## 3. Persona & Peran

Aplikasi ini memiliki **tiga persona utama** dengan hak akses berbeda.

| Persona | Peran di DB | Halaman Utama | Kemampuan |
|---------|-------------|----------------|-----------|
| **Operator lapangan** | (tanpa login, publik) | `/` , `/peta` , `/riwayat` , `/disposisi` | Deteksi, simpan riwayat, kirim laporan, pantau peta |
| **Administrator dinas** | `admin` dengan `daerah` | `/pupr-<slug>/dashboard/*` | Verifikasi, terbitkan SPK, kelola kontraktor, terima hasil kerja |
| **Kontraktor** | `kontraktor_akun` | `/kontraktor/*` | Lihat SPK sendiri, kerjakan, unggah foto bukti |
| **Superadmin** | `admin` dengan `daerah = '-'` | Semua + `/dashboard/instansi` | Kelola instansi & akun daerah |

### Aturan Otorisasi ( ditegakkan di server )

- Admin berdaerah **terkunci** ke daerahnya sendiri (`_dashboard_ok`, `_wewenang_ok`).
- Kontraktor **hanya** melihat SPK miliknya (`spk_boleh_akses`). SPK milik
  orang lain dijawab **404** (bukan 403) agar keberadaan tidak terkonfirmasi.
- Peta kontraktor **tidak** memakai `/api/peta` publik; memakai
  `titik_peta_kontraktor`.
- Transisi status **hanya satu tahap** — tidak bisa melompat.

---

## 4. Peta Navigasi

```mermaid
graph TD
    START([Buka aplikasi]) --> LOGIN{Ada sesi?}
    LOGIN -->|Tidak| LOGIN_PAGE["/login"]
    LOGIN -->|Ya| CEK{Peran apa?}

    LOGIN_PAGE -->|"admin"| DASH
    LOGIN_PAGE -->|"kt_*"| KT_DASH
    LOGIN_PAGE -->|lainnya| PUBLIK

    PUBLIK["Halaman Publik"]
    PUBLIK --> HOME["/ — Deteksi<br/>(tab: Gambar | Live)"]
    PUBLIK --> PETA["/peta"]
    PUBLIK --> RIWAYAT["/riwayat"]
    PUBLIK --> DISPOSISI["/disposisi"]
    PUBLIK --> TENTANG["/tentang"]
    PUBLIK --> KALIBRASI["/kalibrasi 🔒"]

    DASH["Dashboard Dinas"]
    DASH --> D_BERANDA["/beranda — KPI"]
    DASH --> D_VERIFIKASI["/verifikasi"]
    DASH --> D_SPK["/spk"]
    DASH --> D_KONTRAKTOR["/kontraktor"]
    DASH --> D_INSTANSI["/instansi 🔑"]
    DASH --> D_ANALITIK["/analitik"]

    KT_DASH["Ruang Kerja Kontraktor"]
    KT_DASH --> K_SPK["/kontraktor/spk"]
    KT_DASH --> K_PETA["/kontraktor/peta"]
    KT_DASH --> K_DETAIL["/kontraktor/spk/<id>"]
```

---

## 5. Alur Utama — Deteksi Gambar

```mermaid
flowchart TD
    U(["Pengguna membuka halaman utama"]) --> TAB["Tab: Gambar"]
    TAB --> PILIH["Pilih file gambar<br/>(jpg/png, ≤15MB)"]
    PILIH --> KALIB["Butuh kalibrasi px/cm?<br/>/kalibrasi"]

    PILIH --> POST["POST /api/detect"]
    POST --> VAL{"Validasi:<br/>ext · magic-byte · ukuran"}
    VAL -->|Gagal| ERR1["Tolak: /error"]
    VAL -->|OK| ANALISIS["analisis_gambar()"]

    ANALISIS --> PRE["Preprocessing:<br/>decode · CLAHE malam"]
    PRE --> INFER["predict<br/>YOLOv11s @ imgsz=960"]
    INFER --> POST1["Postprocessing:<br/>severity · biaya"]
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
   `\x89PNG`) diperiksa, bukan hanya header.
2. **Mode malam** — CLAHE diterapkan di kanal L (LAB), hanya fotometrik;
   geometri tidak berubah.
3. **Mode teliti** — *tiling* grid 640 dengan overlap 0,25; box yang menyentuh
   tepi dalam tile dibuang; digabung lintas tile via NMS/WBF.
4. **Pseudo-segmentation** — luas diestimasi dari kontur (Otsu/adaptive +
   morphology) di dalam bounding box. **Bukan** mask segmentasi model.
5. **Angka otoritatif** — saat kirim disposisi, angka total **diambil ulang
   dari DB** (`rekap_temuan`), bukan dipercaya dari klien.

---

## 6. Alur Utama — Live Stream Real-Time

```mermaid
flowchart TD
    U(["Pengguna membuka halaman utama"]) --> TAB["Tab: Live"]
    TAB --> PILIH_SRC{"Pilih sumber"}

    PILIH_SRC -->|Webcam| WEBCAM["POST /api/stream/start<br/>sumber=webcam, index=0..10"]
    PILIH_SRC -->|IP Camera| IPCAM["POST /api/stream/start<br/>sumber=ipcam, URL"]
    PILIH_SRC -->|Upload Video| UPLOAD["POST /api/video<br/>≤200MB → tempfile"]
    PILIH_SRC -->|Contoh| DEMO["POST /api/demo<br/>demo_jalan.mp4"]

    IPCAM --> SSRF{"Validasi anti-SSRF"}
    SSRF -->|Gagal| ERR["Tolak"]

    WEBCAM --> TOKEN
    UPLOAD --> TOKEN
    DEMO --> TOKEN

    TOKEN["Terbit token kepemilikan<br/>(_stream_token)"]
    TOKEN --> MJPEG["GET /api/stream<br/>MJPEG multipart"]
    TOKEN --> STATS["GET /api/stream/stats<br/>polling ~1 detik"]

    MJPEG --> LAYER["Compose: overlay terakhir<br/>→ frame segar → JPEG"]
    STATS --> MONITOR["FPS tampil · FPS infer<br/>frame · track unik · deteksi"]

    LAYER --> SNAP{"Aksi pengguna?"}
    SNAP -->|Snapshot| SNAPSHOOT["POST /api/stream/snapshot<br/>rows per track-id"]
    SNAP -->|Toggle anotasi| ANNOTASI["POST /api/stream/anotasi"]
    SNAP -->|Berhenti| STOP["POST /api/stream/stop"]

    SNAPSHOOT --> SAMA["Sama seperti alur gambar:<br/>PDF · Simpan riwayat · Disposisi"]
    ANNOTASI --> SNAP
    STOP --> TAB
```

### Catatan Kinerja

- Inferensi YOLOv11n ONNX @480 ≈ **326 ms/frame** (~3 FPS infer).
- FPS **tampil** preview tetap **15+** karena arsitektur *decouple* 3-thread.
- Preset performa: `halus` (320/3/30) · `seimbang` (480/2/25) · `akurat` (640/1/15).

---

## 7. Alur Verifikasi & Penerbitan SPK

Setelah operator menyimpan riwayat dan mengirim laporan ke instansi, pihak
dinas melakukan verifikasi.

```mermaid
flowchart TD
    LAPOR(["Laporan dikirim ke instansi<br/>status: Terkirim"]) --> VERIF

    subgraph DINAS ["Dashboard Dinas · /verifikasi"]
        VERIF["Verifikasi laporan"]
        VERIF --> TINJAU{"Tinjau temuan<br/>+ foto bukti"}
        TINJAU -->|"Terima / tolak"| KEPUTUSAN
    end

    KEPUTUSAN{Status disposisi?}
    KEPUTUSAN -->|Terkirim| TERIMA["✅ Diterima Dinas"]
    KEPUTUSAN -->|Ditolak| TOLAK["❌ Ditolak"]
    KEPUTUSAN -->|Diproses| PROSES["🔄 Diproses"]

    TERIMA --> SPK
    PROSES --> SPK

    subgraph SPKSTEP ["Terbitkan SPK · /spk"]
        SPK["Pilih kontraktor"]
        SPK --> CEK_TITIK["Centang titik damage<br/>dari peta / daftar"]
        CEK_TITIK --> TERBIT["POST /api/spk<br/>terbitkan_spk()"]
    end

    TERBIT --> KERJA_INTI

    subgraph KONTRAKTOR ["Kontraktor Mengerjakan · /kontraktor/spk/&lt;id&gt;"]
        KERJA_INTI["Lihat titik kerja di peta"]
        KERJA_INTI --> KERJAKAN["Status per titik:<br/>Menunggu → Dikerjakan → Selesai"]
        KERJAKAN --> FOTO["Unggah foto bukti<br/>(WAJIB sebelum 'Selesai')"]
    end

    KERJA_INTI --> KEMBALIAN

    subgraph KEMBALIAN ["Kembali ke Dinas"]
        MONITOR["Dashboard memonitor progres"]
        MONITOR --> BAST{"SPK selesai?"}
    end

    BAST -->|"Diterima Dinas"| SELESAI(["✅ Proyek Selesai"])
    BAST -->|"Perlu revisi"| REVISI["↻ Minta revisi<br/>POST /api/spk/&lt;sid&gt;/revisi"]
    REVISI --> KONTRAKTOR
    BAST -->|"Batalkan"| BATAL["🚫 Batal<br/>POST /api/spk/&lt;sid&gt;/batal"]
```

---

## 8. Alur Kerja Kontraktor

Kontraktor bekerja di ruang kerja terpisah dengan sidebar aksen **hijau**
(berbeda dari dashboard dinas).

```mermaid
flowchart TD
    LOGIN(["Login kt_*"]) --> DASH["/kontraktor/dashboard<br/>KPI + 5 SPK terbaru"]
    DASH --> DAFTAR["/kontraktor/spk<br/>daftar SPK + filter status"]

    DAFTAR --> DETAIL["/kontraktor/spk/&lt;id&gt;"]
    DAFTAR --> PETA["/kontraktor/peta<br/>hanya titik dalam SPK miliknya"]

    DETAIL --> TITIK["Daftar tugas (titik damage)"]
    TITIK --> AKSI{"Aksi per titik"}

    AKSI -->|Mulai| KERJA["Status: Dikerjakan"]
    KERJA --> UNGGAH["Unggah foto bukti<br/>POST /api/kontraktor/spk/&lt;sid&gt;/tugas/&lt;tid&gt;/foto"]
    UNGGAH --> SELESAI["Status: Selesai"]

    AKSI -->|Ajukan selesai| MENUNGGU["Status SPK:<br/>Menunggu Penerimaan"]

    MENUNGGU --> WAIT["Tunggu verifikasi dinas"]

    PETA --> LIHAT["Marker di peta<br/>hanya area kerja sendiri"]
```

### Aturan Ketat

- Kontraktor **tidak bisa** melihat SPK kontraktor lain → **404**.
- Titik **tidak bisa** berstatus "Selesai" tanpa foto bukti.
- Transisi status **hanya satu tahap** (`SPK_TRANSISI`, `TUGAS_TRANSISI`).

---

## 9. Alur Penerimaan Hasil Kerja (BAST)

```mermaid
flowchart TD
    MENUNGGU(["SPK: Menunggu Penerimaan"]) --> INSP["Inspeksi hasil kerja<br/>dinas"]
    INSP --> TINJAU{"Cukup baik?"}

    TINJAU -->|Ya| BAST1["POST /api/spk/&lt;sid&gt;/terima<br/>Isi BAST"]
    BAST1 --> BAST2["Simpan: nomor_bast · diterima_oleh<br/>waktu_diterima · catatan_penerimaan"]
    BAST2 --> FINAL(["✅ Status: Diterima Dinas<br/>SPK selesai · Terminasi"])

    TINJAU -->|Tidak| REVISI["POST /api/spk/&lt;sid&gt;/revisi<br/>catatan revisi"]
    REVISI --> BACK["Kembalikan ke kontraktor"]

    subgraph KOREKSI ["Pembatalan Penerimaan (opsional)"]
        BATAL_TERIMA["POST /api/spk/&lt;sid&gt;/batalkan-terima"]
        BATAL_TERIMA --> UNDO["Batalkan BAST<br/>kembalikan ke Menunggu"]
    end

    FINAL -.-> BATAL_TERIMA
```

---

## 10. Diagram State Machine Status

### 10a. Status SPK

```mermaid
stateDiagram-v2
    [*] --> Diterahkan: dinas terbitkan SPK

    Diterahkan --> Dikerjakan: kontraktor mulai
    Dikerjakan --> Diterahkan: mundur

    Diterahkan --> Selesai: semua tugas Selesai<br/>+ foto bukti lengkap
    Selesai --> MenungguPenerimaan: kontraktor ajukan

    MenungguPenerimaan --> DiterimaDinas: 🚀 DITERIMA (BAST)
    MenungguPenerimaan --> Dikerjakan: ↻ revisi dari dinas

    Diterahkan --> Dibatalkan: batal dari dinas
    Dikerjakan --> Dibatalkan: batal dari dinas

    DiterimaDinas --> MenungguPenerimaan: batalkan-terima
    DiterimaDinas --> [*]

    note right of DiterimaDinas
        Status TERMINAL.
        Ditulis dengan BAST:
        nomor_bast · diterima_oleh
        waktu_diterima
    end note
```

### 10b. Status Tugas (per titik)

```mermaid
stateDiagram-v2
    [*] --> Menunggu
    Menunggu --> Dikerjakan: kontraktor mulai
    Dikerjakan --> Selesai: + foto bukti WAJIB
    Selesai --> [*]

    note right of Selesai
       _server_: titik tidak bisa
        Selesai tanpa foto
    end note
```

### 10c. Status Disposisi (laporan ke instansi)

```mermaid
stateDiagram-v2
    [*] --> Terkirim: operator kirim laporan

    Terkirim --> Diproses: instansi proses
    Diproses --> Selesai: instansi selesaikan
    Diproses --> Terkirim: dikembalikan
    Terkirim --> Ditolak: instansi tolak

    note right of Selesai
        Selesai → opsional foto
        sesudah perbaikan
    end note
```

---

## 11. Diagram Pipeline Inferensi

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

    MODE -->|Normal| NORMAL["predict @ imgsz=960"]
    MODE -->|Teliti| TELITI["Tiling 640 · overlap 0.25<br/>buang tepi · gabung NMS/WBF"]
    MODE -->|Ensemble| ENSEMBLE["prediksi_ensemble<br/>WBF / NMS per kelas"]
    MODE -->|Live| LIVE["model.track + ByteTrack<br/>@ imgsz=480 · persist"]

    NORMAL --> HASIL
    TELITI --> HASIL
    ENSEMBLE --> HASIL
    LIVE --> HASIL

    subgraph HASIL ["Postprocessing — analisis_gambar()"]
        H1["proses_detections()"]
        H1 --> H2["diagnose() → severity<br/>Ringan / Sedang / Berat"]
        H2 --> H3["estimasi() → indeks biaya<br/>volume × harga acuan"]
        H3 --> H4["Pseudo-segmentation<br/>kontur Otsu → mask_area_cm2"]
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
| 1 | `conf < ambang_efektif` per kelas | `toleransi_kelas` di `inferensi.yaml` |
| 2 | Ukuran fisik tidak masuk akal | `batas_ukuran` (300cm / 100cm / 100m²) |
| 3 | Luas piksel < `luas_min_px` (default 900) | `saring.luas_min_px` |

---

## 12. Arsitektur 3-Thread Live Streaming

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

## 13. Peta Kode Sumber

### Entry Point

| Peran | File | Baris |
|-------|------|-------|
| Web app (WAJIB) | `web/app.py` | `app = create_app()` @ 1951 |
| Blok `__main__` | `web/app.py` | 1970–1974 |
| Preload model di background | `web/app.py` | 1953–1968 |
| Prototipe lama (deprecated) | `app/app_streamlit.py` | — |

### Route Penting

| Route | Baris | Fungsi |
|-------|-------|--------|
| `POST /api/detect` | 663 | Deteksi gambar |
| `POST /api/verifikasi` | 776 | Koreksi operator |
| `POST /api/laporan` | 797 | Generate PDF |
| `POST /api/stream/start` | 889 | Mulai live stream |
| `GET /api/stream` | 827 | MJPEG |
| `POST /api/stream/snapshot` | 956 | Snapshot live |
| `POST /api/riwayat` | 1053 | Simpan sesi |
| `GET /api/peta` | 1141 | Titik peta (publik) |
| `POST /api/disposisi` | 1282 | Kirim laporan |
| `POST /api/spk` | 1826 | Terbitkan SPK |
| `POST /api/spk/<sid>/terima` | 1869 | BAST |
| `POST /api/kontraktor/spk/<sid>/tugas/<tid>/foto` | 1778 | Foto bukti |

### Fungsi Inti

| Fungsi | File | Baris |
|--------|------|-------|
| `analisis_gambar` | `web/deteksi.py` | 1085 |
| `prediksi_teliti` | `web/deteksi.py` | 991 |
| `proses_detections` | `web/deteksi.py` | 662 |
| `gabung_fragmen` | `web/deteksi.py` | 700 |
| `get_model` (singleton) | `web/deteksi.py` | 546 |
| `diagnose` (severity) | `app/severity.py` | 53 |
| `estimasi` (biaya) | `app/biaya.py` | 53 |
| `buat_laporan` (PDF) | `app/laporan.py` | 34 |
| `simpan_sesi` | `web/database.py` | 405 |
| `rekap_temuan` | `web/database.py` | 522 |
| `terbitkan_spk` | `web/database.py` | 1302 |
| `terima_hasil_kerja` | `web/database.py` | 1708 |
| `StreamManager` | `web/streaming.py` | 42 |

---

## Lampiran — Catatan Limitation yang Jujur

Aplikasi ini **sengaja** menyatakan batasan berikut (dari README & DESIGN):

1. **Bukan segmentasi.** Deteksi *bounding box*; luas diestimasi dari kontur
   di dalam box (*pseudo-segmentation*), bukan mask model.
2. **Akurasi belum mencapai target.** YOLOv11s: mAP50 val 0,6483 (target
   ≥ 0,65 belum tercapai). Dataset latih RDD2022 (India/Jepang).
3. **Kamera mono tidak mengukur kedalaman.** Tebal = asumsi per severity.
4. **Harga = indeks relatif**, bukan RAB resmi. Semua tabel harga berlabel
   `CONTOH-...`.
5. **Mode malam hanya fotometrik** (CLAHE), tidak menambah sumber cahaya.
6. **Istilah**: selalu "indeks biaya" / "indeks prioritas", **tidak pernah**
   "biaya perbaikan" mutlak.

---

*Dokumen ini dibuat untuk keperluan dokumentasi skripsi. Struktur route dan
nama fungsi diverifikasi langsung dari kode sumber.*