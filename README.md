# TA Machine Learning — Deteksi Kerusakan Jalan Real-Time

**Judul skripsi:** Deteksi Kerusakan Jalan Real-Time Berbasis YOLO-Segmentation dengan Estimasi Tingkat Keparahan, Biaya, dan Laporan Otomatis untuk Pemetaan Pemda

Prototype web live (deteksi gambar + live webcam/IP-cam/video + severity + biaya + PDF + peta + riwayat + alur SPK kontraktor). Cocok buat sidang demo di laptop i5-3470 + RX550 (CPU-only).

> ### Catatan metodologi penting, silakan dibaca
>
> **Proyek ini memakai deteksi bounding box, BUKAN segmentasi mask.**
>
> Judul di atas menyebut "YOLO-Segmentation" karena judul disusun saat
> proposal. Kenyataannya berbeda, dan alasannya disengaja:
>
> - Dataset latih (RDD2022, 14.176 gambar) **hanya menyediakan anotasi
>   bounding box**, format 5 kolom `class cx cy w h`. Tidak ada polygon.
> - Melatih model segmentasi butuh ground truth berupa mask. Kalau mask tidak
>   ada, yang dilatih adalah tebakan.
> - Mengubah kotak jadi polygon secara otomatis tidak menambah ketepatan:
>   hasilnya persis sama dengan kotak itu.
> - Luas area temuan diestimasi dari **kontur di dalam bounding box**
>   (threshold adaptif + morfologi) — bukan dari keluaran mask model.
>   Implementasi: `web/deteksi.py::pseudo_segmentation`.
>
> Karena luas hanya estimasi untuk **skoring prioritas**, seluruh teks aplikasi
> memakai sebutan "indeks biaya" atau "indeks prioritas", tidak pernah
> "biaya perbaikan" mutlak.
>
> Jawaban singkat kalau ditanya di sidang: **tidak ada segmentasi.**
>
> Alasan lengkap, bukti format label, batasan, dan naskah jawaban ada di
> **[`docs/Segmentasi-atau-Bounding-Box.md`](docs/Segmentasi-atau-Bounding-Box.md)**.

---

## Stack final (terverifikasi)
- **Model gambar:** YOLOv11s (deteksi), 5 kelas — `app/weights/best_yolo11s.pt` (18,3 MB), aktif untuk foto statis (imgsz 960, TTA)
- **Model live:** YOLOv11n ONNX — `app/weights/best.onnx` (9,9 MB), aktif untuk webcam/IP-cam/video (CPU, lebih cepat)
- **Training:** Kaggle/Colab T4/P100 (template: `notebooks/template-kaggle-yolo11-detect.md`)
- **Inferensi:** laptop i5-3470 + RX550 (CPU), OpenCV + Ultralytics + ONNX Runtime
- **Web:** Flask 3.x + Leaflet (OSM) — `web/`
- **DB riwayat:** SQLite (`web/instance/riwayat.db`)

### Akurasi terukur (RDD-only 14.176 gambar)
- **YOLOv11s** (model gambar, `best_yolo11s.pt`): Val mAP50 **0.6483** · Test RDD-full **0.5262** · OOD Bandung **0.4516**
- **YOLOv11n** (baseline B, dipakai live `best.onnx`): Val mAP50 0.593 · Test RDD-full 0.470 · OOD Bandung 0.551

> Catatan jujur: target jurnal mAP50 ≥ 0.65 belum terpenuhi (val terbaik 0,6483 pada YOLOv11s); ablasi CBAM/YOLO26 sudah ditutup — lihat `reports/keputusan-ablasi-cbam-yolo26.md`.

### Performa inferensi (CPU; artefak di `artifacts/`)

Dua metrik berbeda — jangan dicampur:
- **Latensi inferensi per frame** (biaya CPU per frame):
  - `best_yolo11s.pt` @ imgsz 960 → **mean ~1.309 ms/frame (~0,8 FPS)** — model foto statis (akurasi; siap TTA/tiling).
  - `best.onnx` (YOLOv11n) @ imgsz 480 → **mean ~326 ms/frame (~3 FPS)** — model live.
- **FPS tampil (preview)**: karena arsitektur *decouple* 3-thread (capture / infer / compose), preview jalan di laju terpisah dari inferensi → **15+ FPS** saat live webcam walaupun inferensi hanya ~3 FPS.

Cara reproduksi (menulis artefak JSON berisi latency mean/median/p95 + info hardware):

```bash
.\.venv\Scripts\python scripts\benchmark_inferensi.py --model best.onnx --imgsz 480 --runs 20
.\.venv\Scripts\python scripts\benchmark_inferensi.py --model best_yolo11s.pt --imgsz 960 --runs 10
```

---

## Fitur Utama

### 1. Deteksi Gambar & Live Stream
- Upload gambar JPG/PNG → deteksi kerusakan dengan **bounding box** (bukan mask)
- Live webcam/IP-cam/video dengan ByteTrack tracking
- Mode malam (CLAHE) untuk foto gelap
- Mode teliti (tiling) untuk retak kecil
- Luas area diestimasi dari kontur di dalam box (opsional, lihat catatan metodologi)

### 2. Severity & Estimasi Biaya
- 5 kelas kerusakan: `longitudinal_crack`, `transverse_crack`, `alligator_crack`, `other_corruption`, `pothole`
- Severity otomatis: Ringan/Sedang/Berat berdasarkan dimensi
- Estimasi **indeks biaya relatif** (bukan RAB) dari tabel harga acuan editable (`config/harga_acuan.csv`)

### 3. Kalibrasi Pengukuran
- Metode A: Input pixels_per_cm langsung
- Metode B: Foto penggaris + klik 2 titik
- Dampak kalibrasi langsung terlihat (box 100px = X cm)

### 4. Laporan PDF
- Generate PDF otomatis dengan foto + tabel temuan + total estimasi
- Metadata: sumber, model, waktu deteksi
- Bukti foto sesudah perbaikan ikut dilampirkan bila tersedia

### 5. Peta Sebaran
- Leaflet map dengan marker GPS
- Filter severity
- Popup detail tiap titik
- Lihat foto bukti sebelum dan sesudah perbaikan

### 6. Riwayat & Disposisi
- Riwayat deteksi dengan thumbnail
- Filter: tanggal, severity, pencarian
- Disposisi laporan ke instansi pemerintah
- Dashboard admin dinas dengan KPI, verifikasi, dan analitik

### 7. Alur SPK & Ruang Kerja Kontraktor
Alur kerja dari laporkan sampai dikerjakan, ujung ke ujung:

1. **Deteksi** → laporan dikirim ke dashboard dinas sebagai *disposisi*.
2. **Verifikasi** dinas menerima laporan, lalu menerbitkan **SPK** ke
   kontraktor dengan memilih titik kerusakan yang menjadi lingkup kerja.
3. **Kontraktor** masuk ke ruang kerjanya: melihat daftar SPK, membuka detail,
   dan memeriksa titik kerusakan di peta.
4. **Pengerjaan**: kontraktor mengubah status secara bertahap
   (Diterima → Dikerjakan → Selesai), wajib melampirkan **foto bukti**
   pada tiap titik sebelum ditandai selesai.
5. **Verifikasi dinas** melihat progres dan foto bukti dari dashboard.

Detail teknis dan batasan otorisasi ada di `docs/API.md`.

### 8. UI/UX
- Reduced-motion support (`prefers-reduced-motion`)
- Pagination untuk dataset besar
- Toast notification
- Skeleton loading states
- Responsive design

---

## Cara menjalankan di localhost

### 1) Aktifkan virtualenv
```bash
. .venv/Scripts/activate        # git-bash
# atau: .\.venv\Scripts\activate      # PowerShell
```

### 2) Install dependensi (sekali, bila belum)
```bash
pip install -r requirements.txt
```

### 3) Pastikan model ada
```bash
ls app/weights/best.pt app/weights/best.onnx
# (keduanya sudah ada: best.pt ~5,2 MB, best.onnx ~9,9 MB; best_yolo11s.pt 18,3 MB)
```

### 4) Jalankan server
```bash
python web/app.py
# output di akhir: * Running on http://127.0.0.1:5000
```

### 5) Buka di browser
- Deteksi (gambar / live): http://127.0.0.1:5000
- Peta titik kerusakan:  http://127.0.0.1:5000/peta
- Riwayat:               http://127.0.0.1:5000/riwayat
- Tentang:               http://127.0.0.1:5000/tentang
- Kalibrasi:             http://127.0.0.1:5000/kalibrasi
- Disposisi:             http://127.0.0.1:5000/disposisi

### 6) Login
Satu form login dipakai dua jenis akun. **Sandinya sama semua: sandi demo.**

| Peran | Username | Password | Masuk ke |
|---|---|---|---|
| Admin dinas (superadmin) | `admin` | `jalanpantau2026` | `/pupr-bandung/dashboard` |
| Kontraktor | `kt_mitrakarya` | `jalanpantau2026` | `/kontraktor/dashboard` |

Sandi dapat diganti lewat env `JP_DEMO_PASS`. **Ganti sebelum dipakai di luar
demo.**

#### Akun dinas per daerah (`pupr_*`) tidak bisa langsung dipakai
Semuanya sudah ada sebagai akun, tetapi **disegel dengan sandi acak yang
tidak tertebak** (`sandi_diatur = 0`), termasuk `pupr_bandung`. Jadi
`pupr_bandung` **tidak** bisa login dengan sandi demo.

Supaya bisa dipakai, superadmin harus mengatur sandinya lebih dulu:

1. Masuk sebagai `admin`
2. Buka menu **Kontraktor** untuk sandi akun kontraktor, atau
   menu **Instansi** untuk sandi akun dinas daerah
3. Setelah sandi diatur, akun `pupr_bandung` bisa dipakai untuk demo
   dashboard daerah Bandung

Untuk demo sidang, **`admin` sudah cukup**: superadmin melihat semua
daerah, dan secara bawaan login langsung ke `/pupr-bandung/dashboard`.

#### Akun kontraktor lain
Seluruh akun kontraktor ada di `config/kontraktor.yaml` dan memakai sandi
demo yang sama. Satu di antaranya, `kt_togugede`, sengaja dibuat nonaktif
sebagai contoh kontraktor yang tidak bisa login.

### 7) Demo tanpa webcam (fallback sidang)
Klik tombol **"Pakai video contoh"** di tab Live — memutar `web/static/demo/demo_jalan.mp4` (32 frame) jadi bisa demo meski kamera nggak kepepet.

---

## Reproduksibilitas & validasi

- **Versi terkunci**: `requirements.lock.txt` (hasil `pip freeze` dari environment yang terbukti jalan). Pasang dengan `pip install -r requirements.lock.txt`.
- **Integritas bobot**: `app/weights/SHA256SUMS.txt` + verifikasi `python scripts/verifikasi_bobot.py` (pastikan bobot identik dengan yang dilaporkan).
- **Benchmark performa**: `python scripts/benchmark_inferensi.py` (lihat bagian Performa).
- **Validasi kalibrasi & severity**: `scripts/validasi_kalibrasi.py`, `scripts/validasi_severity.py` — panduan di `docs/Validasi-Pengukuran.md`.
- **Tuning model**: playbook `docs/Panduan-Tuning-Model.md` + template Kaggle `notebooks/template-kaggle-hard-negative-finetune.md`.
- **Cara menjalankan di Kaggle**: `docs/Cara-Training-Kaggle.md` (langkah demi langkah).
- **Dokumentasi API**: `docs/API.md`.
- **CI**: `.github/workflows/ci.yml` menjalankan seluruh test (test yang butuh bobot otomatis di-skip bila bobot tidak ada).
- **Konfigurasi**: salin `.env.example` → `.env` (mis. `JP_SECRET_KEY`, `JP_DEMO_PASS`, `JP_SESSION_HOURS`, `JP_CSRF`, `JP_HTTPS`). Tanpa `JP_SECRET_KEY`, sesi login hangus tiap restart server.
- **Backup DB**: `python scripts/backup_db.py` (VACUUM INTO ke `backups/`, aman saat server jalan).
- **Audit trail**: perubahan status disposisi tercatat (pelaku + waktu) di `disposisi_catatan`; perubahan status SPK tercatat di `spk_catatan`.
- **Catatan metodologi**: keputusan memakai bounding box dan bukan segmentasi dijelaskan di `docs/Segmentasi-atau-Bounding-Box.md`.

## Uji cepat API (bisa lewat curl)
```bash
# deteksi 1 foto
curl -X POST http://127.0.0.1:5000/api/detect \
  -F "gambar=@data/publik/bpid/test/images/04a8f35f.jpeg" -F "conf=0.25"

# PDF laporan (feedkan rows dari response di atas)
curl -X POST http://127.0.0.1:5000/api/laporan \
  -H "Content-Type: application/json" -d '{"rows":[...],"total":...,"image_b64":"...","source":"foto.jpg"}' \
  --output laporan.pdf
```

---

## Struktur folder
```
.
├── web/                 # PROTOTIPE AKTIF — Flask app + UI
│   ├── app.py           # routes halaman + API JSON (lihat daftar route di bagian bawah)
│   ├── deteksi.py       # adaptor: YOLO -> severity -> biaya (pakai modul app/ di bawah)
│   ├── streaming.py     # StreamManager: webcam/IP-cam/video -> MJPEG + ByteTrack + snapshot
│   ├── database.py      # SQLite: riwayat, temuan, instansi, disposisi, admin, kontraktor, SPK
│   ├── templates/       # base/deteksi/peta/riwayat/tentang/kalibrasi/mobile/login/laporan_preview/disposisi_*.html
│   │                    #   + dashboard/* (dinas) + kontraktor/* (ruang kerja kontraktor) + error/*
│   ├── static/          # css/{civic,dash,style}.css + js/{deteksi,live,peta,riwayat,disposisi,
│   │                    #   dash,gps,zoom,lokasi_dinamis,kontraktor_peta}.js + demo/demo_jalan.mp4
│   └── instance/        # riwayat.db + hasil/<id>.jpg  (runtime, gitignored)
├── app/                 # modul inti (reusable) + weights
│   ├── severity.py      # luas dari box -> Ringan/Sedang/Berat (ambang di config/severity.yaml)
│   ├── biaya.py         # volume × harga acuan editable → total_rp
│   ├── laporan.py       # fpdf2 → PDF laporan (foto + tabel + total)
│   ├── ringkasan.py     # agregasi ringkasan hasil (per-kelas, per-severity, biaya)
│   ├── app_streamlit.py # prototype Streamlit lama (deprecated — pakai web/ sekarang)
│   └── weights/         # best_yolo11s.pt (gambar) · best.onnx (live) · best.pt, best_yolo11s.onnx (cadangan)
├── config/              # editable: severity.yaml, harga_acuan.csv, inferensi.yaml, kontraktor.yaml
├── data/                # dataset publik + sampel lokal
├── docs/                # SOP rekam, strategi, catatan dataset, API, keputusan segmentasi
├── notebooks/           # template training Kaggle
├── scripts/             # utilitas: smoke_web.py, cek_detect.py, cek_id_dom.py, grep-emoji.cjs, grep-cjk.cjs
├── tests/               # unit tests (stdlib unittest)
├── artifacts/           # hasil training/ablasi (bukti pengujian)
├── reports/             # output PDF + backup hasil Kaggle + decision log
├── yolov11s-rdd-only/   # run training YOLOv11s + kurva evaluasi
├── stitch_aplikasi_deteksi_kerusakan_jalan/  # mockup desain Stitch (referensi UI)
├── requirements.txt
├── .gitignore
├── DESIGN.md            # brief desain UI/UX (kontrak ID untuk frontend)
└── README.md            # file ini
```

### Route utama `web/app.py`

**Halaman publik:** `/` · `/peta` · `/riwayat` · `/tentang` · `/mobile` ·
`/kalibrasi` · `/laporan/preview/<sid>` · `/disposisi[/<sid>]` · `/login` · `/logout`

**Portal dinas** (butuh login admin): `/pupr-<daerah>/dashboard[/<halaman>]`
dengan halaman `beranda` · `disposisi[/<id>]` · `verifikasi` · `analitik` ·
`spk[/<id>]` · `kontraktor` · `instansi`

**Ruang kerja kontraktor** (butuh login kontraktor): `/kontraktor/dashboard` ·
`/kontraktor/spk/<id>`

---

## Konfigurasi penting (editable tanpa kode)
- `config/harga_acuan.csv` — tabel harga Ringan/Sedang/Berat. **Ini indeks biaya relatif untuk skoring prioritas, bukan RAB**; semua nilai contoh — ganti dengan sitasi publik (mis. AHSP/HSPK) bila ingin lebih kuat
- `config/severity.yaml` — ambang `pixels_per_cm` (WAJIB kalibrasi per kamera: foto penggaris 10 cm), lebar retak, diameter lubang, tebal & bahan per severity
- `config/inferensi.yaml` — parameter inferensi (imgsz, iou, conf, frame_skip, mode teliti)
- `config/kontraktor.yaml` — seed daftar kontraktor dan akun loginnya. Dibaca sekali saat aplikasi pertama kali jalan; setelah itu ubah lewat menu Kontraktor di dashboard dinas

---

## Optimasi Performa

### Untuk deteksi gambar
- Model di-preload saat server start (tidak perlu tunggu loading saat pertama deteksi)
- Mode teliti (tiling) untuk retak kecil — lebih lambat tapi lebih akurat

### Untuk live webcam
- **Decouple capture/inferensi/tampilan** — capture, inferensi (YOLO+ByteTrack), dan
  compose gambar jalan di thread terpisah. Tampilan (frame kamera segar + box terakhir)
  berjalan di laju `display_fps`, terpisah dari laju inferensi — jadi preview tetap
  mulus walau inferensi CPU lambat. `BUFFERSIZE=1` mencegah buffer kamera menumpuk.
- **Mode Performa** di UI: Halus / Seimbang / Akurat (mengatur `imgsz` + interval
  inferensi + batas FPS tampil sekaligus).
- `imgsz_live=480` (default) — naikkan ke 960 untuk akurasi maksimal (lebih lambat).
- `frame_skip` (kini "Interval Inferensi") = inferensi tiap N frame; frame lain tetap
  ditampilkan.
- Frame differencing — skip inferensi jika frame statis (tampilan tetap jalan).
- Knob lain di `config/inferensi.yaml` blok `live:` (`display_fps`, `jpeg_quality`,
  `display_width`, `cam_width/height/fps`).

### Untuk dataset besar
- Pagination di semua tabel (10-25 entry per halaman)
- Thumbnail cache (300px) untuk tabel riwayat
- Lazy load gambar ukuran penuh di modal detail

---

## Catatan
- Model di `web/deteksi.py` dimuat sekali (singleton per path): `best_yolo11s.pt` untuk gambar, `best.onnx` untuk live.
- Live tracking pakai ByteTrack (persist tiap sesi); ID reset tiap start.
- Reduced-motion sudah di-handle di CSS (`prefers-reduced-motion`).
- Lihat catatan hidup lengkap di folder `Obsidian Vault/` (mis. `Model YOLOv11s RDD-only - JalanPantau.md`).

---

## Pengembangan Selanjutnya

### Segmentasi (belum, dan perlu keputusan sadar biaya)
Lihat penjelasan lengkap di
[`docs/Segmentasi-atau-Bounding-Box.md`](docs/Segmentasi-atau-Bounding-Box.md).

- **Sekarang:** deteksi bounding box. Luas diestimasi dari kontur di dalam
  box (`web/deteksi.py::pseudo_segmentation`).
- **Yang belum:** model segmentasi sungguhan (YOLO-seg) dengan mask asli.
- **Syarat agar layak dikerjakan:** harus mulai dari anotasi ulang polygon
  pada subset dulu, lalu membandingkan baseline box dengan model segmentasi
  pada subset yang sama. Jangan dikerjakan lebih dulu tanpa data polygon, karena
  yang dilatih hanya tebakan.

### Optimasi
- INT8 quantization untuk inferensi lebih cepat di CPU
- OpenVINO optimization (untuk CPU Intel)
- ROI (Region of Interest) untuk fokus ke area jalan

---

## Lisensi
Tugas Akhir Mahasiswa — Universitas Terbuka / Institusi terkait.
