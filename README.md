# TA Machine Learning — Deteksi Kerusakan Jalan Real-Time

**Judul:** Deteksi Kerusakan Jalan Real-Time Berbasis YOLO-Segmentation dengan Estimasi Tingkat Keparahan, Biaya, dan Laporan Otomatis untuk Pemetaan Pemda

Prototype web live (deteksi gambar + live webcam/IP-cam/video + severity + biaya + PDF + peta + riwayat). Cocok buat sidang demo di laptop i5-3470 + RX550 (CPU-only).

---

## Stack final (terverifikasi)
- **Model:** YOLOv11n (deteksi), 5 kelas — `app/weights/best.pt` + `best.onnx` (CPU)
- **Training:** Kaggle/Colab T4/P100 (template: `notebooks/template-kaggle-yolo11-detect.md`)
- **Inferensi:** laptop i5-3470 + RX550 (CPU), OpenCV + Ultralytics + ONNX Runtime
- **Web:** Flask 3.x + Leaflet (OSM) — `web/`
- **DB riwayat:** SQLite (`web/instance/riwayat.db`)

### Akurasi terukur (baseline B, RDD-only 14.176 gambar)
- Val mAP50: 0.593 · Test RDD-full mAP50: 0.470 · OOD Bandung mAP50: 0.551
- Inference ONNX CPU: ~313 ms/frame (~3,2 FPS); `.pt` ~1,7 s/frame

> Catatan jujur: target jurnal mAP50 ≥ 0.65 belum terpenuhi → `Sel 10` notebook (CBAM) terbuka.

---

## Fitur Utama

### 1. Deteksi Gambar & Live Stream
- Upload gambar JPG/PNG → deteksi kerusakan dengan bounding box
- Live webcam/IP-cam/video dengan ByteTrack tracking
- Mode malam (CLAHE) untuk foto gelap
- Mode teliti (tiling) untuk retak kecil

### 2. Severity & Estimasi Biaya
- 5 kelas kerusakan: `longitudinal_crack`, `transverse_crack`, `alligator_crack`, `other_corruption`, `pothole`
- Severity otomatis: Ringan/Sedang/Berat berdasarkan dimensi
- Estimasi biaya berdasarkan tabel harga acuan editable (`config/harga_acuan.csv`)

### 3. Kalibrasi Pengukuran
- Metode A: Input pixels_per_cm langsung
- Metode B: Foto penggaris + klik 2 titik
- Dampak kalibrasi langsung terlihat (box 100px = X cm)

### 4. Laporan PDF
- Generate PDF otomatis dengan foto + tabel temuan + total estimasi
- Metadata: sumber, model, waktu deteksi

### 5. Peta Sebaran
- Leaflet map dengan marker GPS
- Filter severity
- Popup detail tiap titik

### 6. Riwayat & Disposisi
- Riwayat deteksi dengan thumbnail
- Filter: tanggal, severity, pencarian
- Disposisi laporan ke instansi pemerintah
- Dashboard admin dinas dengan KPI

### 7. UI/UX
- Dark mode + reduced-motion support
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
# (keduanya sudah ada: 5.5 MB .pt + 10.6 MB .onnx)
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

### 6) Demo tanpa webcam (fallback sidang)
Klik tombol **"Pakai video contoh"** di tab Live — memutar `web/static/demo/demo_jalan.mp4` (32 frame) jadi bisa demo meski kamera nggak kepepet.

---

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
│   ├── app.py           # routes: / /peta /riwayat /tentang + API JSON
│   ├── deteksi.py       # adaptor: YOLO -> severity -> biaya (pakai modul app/ di bawah)
│   ├── streaming.py     # StreamManager: webcam/IP-cam/video -> MJPEG + ByteTrack + snapshot
│   ├── database.py      # SQLite riwayat sesi + temuan + thumbnail
│   ├── templates/       # base/deteksi/peta/riwayat/tentang (.html)
│   ├── static/          # css/style.css + js/{deteksi,live,peta,riwayat,gps}.js + demo.mp4
│   └── instance/        # riwayat.db + hasil/<id>.jpg  (runtime, gitignored)
├── app/                 # modul inti (reusable) + weights
│   ├── severity.py      # luas/mask box → Ringan/Sedang/Berat (ambang di config/severity.yaml)
│   ├── biaya.py         # volume × harga acuan editable → total_rp
│   ├── laporan.py       # fpdf2 → PDF laporan (foto + tabel + total)
│   ├── app_streamlit.py # prototype Streamlit lama (deprecated — pakai web/ sekarang)
│   └── weights/         # best.pt + best.onnx (gitignored)
├── config/              # editable: severity.yaml, harga_acuan.csv, inferensi.yaml
├── data/                # dataset publik + hasil training .zip
├── docs/                # SOP rekam, strategi subset/training, catatan dataset
├── notebooks/           # template training Kaggle
├── reports/             # output PDF + backup hasil Kaggle
├── tests/               # unit tests
├── requirements.txt
├── .gitignore
├── DESIGN.md            # brief desain UI/UX (kontrak ID untuk frontend)
└── README.md            # file ini
```

---

## Konfigurasi penting (editable tanpa kode)
- `config/harga_acuan.csv` — tabel harga Ringan/Sedang/Berat (ganti sumber jadi AHSP/Dinas asli)
- `config/severity.yaml` — ambang `pixels_per_cm` (WAJIB kalibrasi per kamera: foto penggarus 10 cm), lebar retak, diameter lubang, tebal & bahan per severity
- `config/inferensi.yaml` — parameter inferensi (imgsz, iou, conf, frame_skip, mode teliti)

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
- Model `best.pt` di `web/deteksi.py` dimuat sekali (singleton), path override lewat query bila perlu.
- Live tracking pakai ByteTrack (persist tiap sesi); ID reset tiap start.
- Dark mode + reduced-motion sudah di-handle di CSS (`prefers-color-scheme`, `prefers-reduced-motion`).
- Lihat catatan hidup lengkap di `Obsidian Vault/TA Machine Learning - Deteksi Kerusakan Jalan Real-Time.md`.

---

## Pengembangan Selanjutnya

### Segmentation (Rencana)
- Pseudo-segmentation menggunakan kontur detection dari bounding box
- Visualisasi polygon overlay (bukan hanya box)
- Perhitungan luas berdasarkan mask area (lebih akurat dari box area)

### Optimasi
- INT8 quantization untuk inferensi lebih cepat di CPU
- OpenVINO optimization (untuk CPU Intel)
- ROI (Region of Interest) untuk fokus ke area jalan

---

## Lisensi
Tugas Akhan Mahasiswa — Universitas Terbuka / Institusi terkait.
