# Sistem Inventarisasi Kerusakan Jalan Berbasis YOLOv11 dengan Severity Terkalibrasi dan Visualisasi Geospasial

Aplikasi web untuk **deteksi otomatis kerusakan permukaan jalan** dari foto,
dilengkapi penilaian tingkat keparahan (*severity*), **indeks prioritas
perbaikan**, kalibrasi pengukuran, pemetaan GIS, dan laporan PDF otomatis.

Alur kerja: **kalibrasi** → unggah foto → deteksi YOLOv11 → severity
(Ringan/Sedang/Berat) → skor prioritas 0–100 → simpan ke SQLite →
visualisasi di **peta Leaflet** → unduh **laporan PDF**. Hasil deteksi
tersimpan sebagai inventarisasi kerusakan yang menjadi dasar prioritas
penanganan.

> ### Catatan metodologi — harap dibaca
>
> - **Deteksi memakai bounding box, bukan segmentasi.** Dataset latih
>   (RDD2022) hanya menyediakan anotasi kotak; melatih segmentasi tanpa
>   ground truth mask tidak sah secara metodologi.
> - **Tidak ada estimasi biaya (rupiah).** Aplikasi memakai **indeks
>   prioritas 0–100 per temuan** (bobot severity × luas ternormalisasi)
>   karena tidak ada tabel harga resmi yang dapat dikutip.
> - **Kalibrasi wajib.** Kamera mono tidak mengukur jarak absolut; parameter
>   `pixels_per_cm` harus dikalibrasi per pemasangan kamera (halaman
>   Kalibrasi). Tanpa kalibrasi, dimensi hanya estimasi kasar.
> - **Inferensi ±3 FPS, bukan real-time.** Preview kamera berjalan ±15 FPS
>   lewat arsitektur *decouple* (capture/inferensi/tampil di thread
>   terpisah) — keduanya metrik yang berbeda.

---

## Stack

- **Model foto statis:** YOLOv11s — `app/weights/best_yolo11s.pt` (18,3 MB)
- **Model live:** YOLOv11n ONNX — `app/weights/best.onnx` (9,9 MB)
- **Web:** Flask + Leaflet (OpenStreetMap)
- **Database:** SQLite (`web/instance/riwayat.db`)
- **Inferensi:** Ultralytics / ONNX Runtime (CPU)

### Akurasi terukur

| Model | Val mAP50 | Test mAP50 | OOD Bandung mAP50 |
|---|---|---|---|
| YOLOv11s (`best_yolo11s.pt`) | 0,6483 | 0,5262 | 0,4516 |
| YOLOv11n (`best.onnx`) | 0,5914 | 0,5557* | 0,5514 |

\* Evaluasi pada 161 citra test (P 0,571 · R 0,574 · F1 0,573).
Sumber: `reports/keputusan-ablasi-cbam-yolo26.md`, `reports/evaluasi-test-*.json`.

Uji fungsional pada 17 foto jalan: **48 temuan**, kelima kelas
(`longitudinal_crack`, `transverse_crack`, `alligator_crack`,
`other_corruption`, `pothole`) terdeteksi; lihat
`reports/uji-foto-17/hasil.json`.

---

## Fitur

1. **Deteksi gambar** — unggah JPG/PNG; EXIF GPS terbaca otomatis bila ada.
2. **Kalibrasi pengukuran** — dua metode: nilai `pixels_per_cm` langsung,
   atau foto penggaris + klik 2 titik.
3. **Severity otomatis** — Ringan/Sedang/Berat dari dimensi terkalibrasi
   (ambang di `config/severity.yaml`).
4. **Indeks prioritas** — skor 0–100 per temuan; agregat per sesi inspeksi.
5. **Peta GIS** — marker temuan berfilter severity, popup detail, ringkasan
   wilayah.
6. **Riwayat** — arsip sesi inspeksi + filter tanggal/severity/pencarian.
7. **Laporan PDF** — generate otomatis per sesi (foto + tabel temuan + skor).
8. **Live streaming (demo)** — pratinjau kamera terpisah dari inferensi.

---

## Cara menjalankan

```bash
# 1) Install dependensi
pip install -r requirements.txt

# 2) Pastikan bobot model ada di app/weights/
#    best_yolo11s.pt · best.onnx · best.pt (+ SHA256SUMS.txt)

# 3) Jalankan server
python web/app.py
# -> http://127.0.0.1:5000
```

Halaman: `/` (Deteksi) · `/peta` · `/riwayat` · `/kalibrasi` · `/tentang` ·
`/login` (satu peran: admin).

---

## Struktur folder

```
.
├── web/                 # Aplikasi Flask
│   ├── app.py           # routes halaman + API JSON
│   ├── deteksi.py       # pipeline YOLO -> severity
│   ├── streaming.py     # live stream (decouple 3-thread)
│   ├── database.py      # SQLite: admin, sesi, temuan
│   ├── templates/       # base/deteksi/peta/riwayat/tentang/kalibrasi/login/...
│   ├── static/          # css/civic.css + js/
│   └── instance/        # riwayat.db (runtime, gitignored)
├── app/                 # modul inti
│   ├── severity.py      # dimensi -> Ringan/Sedang/Berat
│   ├── prioritas.py     # skor prioritas 0-100
│   ├── laporan.py       # PDF laporan (fpdf2)
│   └── weights/         # best_yolo11s.pt · best.onnx · best.pt (gitignored)
├── config/              # severity.yaml · inferensi.yaml (editable)
├── reports/             # hasil evaluasi model
├── scripts/             # utilitas (smoke test, benchmark, uji foto)
├── tests/               # unit tests
└── requirements.txt
```

## Konfigurasi penting

- `config/severity.yaml` — ambang severity, `pixels_per_cm`, tebal asumsi
  per severity. **Kalibrasi ulang setiap ganti kamera/ketinggian.**
- `config/inferensi.yaml` — imgsz, IoU, confidence, parameter live stream.
