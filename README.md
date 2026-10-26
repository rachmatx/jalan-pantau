# Sistem Inventarisasi Kerusakan Jalan Berbasis YOLOv11 dengan Severity Terkalibrasi dan Visualisasi Geospasial

Aplikasi web untuk **deteksi otomatis kerusakan permukaan jalan** dari foto,
dilengkapi penilaian tingkat keparahan (*severity*) per temuan, kalibrasi
pengukuran, pemetaan GIS, dan laporan PDF otomatis. Prioritas penanganan
ditentukan di tingkat **segmen jalan** lewat **SDI-visual** per 100 m.

Alur kerja: **kalibrasi** → unggah foto → deteksi YOLOv11 → severity
(Ringan/Sedang/Berat, deskriptif per temuan) → simpan ke SQLite →
visualisasi di **peta Leaflet** → agregasi per segmen → **SDI-visual** →
unduh **laporan PDF**. Hasil deteksi tersimpan sebagai inventarisasi
kerusakan yang menjadi dasar prioritas penanganan.

> ### Catatan metodologi — harap dibaca
>
> - **Deteksi memakai bounding box, bukan segmentasi.** Dataset latih
>   (RDD2022) hanya menyediakan anotasi kotak; melatih segmentasi tanpa
>   ground truth mask tidak sah secara metodologi.
> - **Tidak ada estimasi biaya (rupiah).** Prioritas penanganan memakai
>   **SDI-visual per segmen 100 m** (Bina Marga, dihitung dari deteksi +
>   dimensi terkalibrasi) karena tidak ada tabel harga resmi yang dapat
>   dikutip. Skor severity per temuan (33/67/100) hanya data *legacy* di
>   database; tidak ditampilkan dan tidak dipakai sebagai instrumen.
> - **Kalibrasi wajib.** Kamera mono tidak mengukur jarak absolut; parameter
>   `pixels_per_cm` harus dikalibrasi per pemasangan kamera (halaman
>   Kalibrasi). Tanpa kalibrasi, dimensi hanya estimasi kasar.
> - **Inferensi terukur: CPU ONNX ±6 FPS @640, ±23 FPS @320; GPU CUDA ±21 FPS.**
>   Di dalam app angka lebih rendah karena capture/encode berbagi CPU. Di CPU
>   preset otomatis memilih `halus` (320); di GPU `seimbang` (640). Pemilihan
>   manual tetap dihormati, dan **akurasi identik** — device tidak mengubah bobot.
> - **Preview kamera ±25–30 FPS** lewat arsitektur *decouple* (capture/inferensi/
>   tampil di thread terpisah) — metrik yang berbeda dari FPS inferensi.

---

## Stack

- **Model (gambar & live):** YOLOv11s — `app/weights/best.pt` untuk keduanya;
  `app/weights/best.onnx` disimpan sebagai cadangan CPU
- **Web:** Flask + Leaflet (OpenStreetMap)
- **Database:** SQLite (`web/instance/riwayat.db`)
- **Inferensi:** Ultralytics/PyTorch — GPU bila `device: auto` dan CUDA ada,
  jika tidak CPU; ONNX Runtime (CPU) untuk cadangan `best.onnx`

### Akurasi terukur

Model tunggal **YOLOv11s** (dipakai untuk foto statis maupun live), epoch terbaik:

| Split | mAP50 | mAP50-95 | Presisi | Recall | F1 |
|---|---|---|---|---|---|
| Validasi | 0,631 | 0,349 | 0,661 | 0,587 | 0,622 |
| Test RDD2022 (5.758 citra / 9.675 instance) | 0,632 | 0,345 | 0,654 | 0,600 | 0,626 |
| Bandung OOD — BPID (161 citra / 263 instance) | 0,540 | 0,294 | 0,558 | 0,534 | 0,546 |

Per kelas (AP50, test RDD2022): `other_corruption` 0,756 · `alligator_crack`
0,690 · `longitudinal_crack` 0,595 · `transverse_crack` 0,587 · `pothole` 0,531.

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
4. **Indeks prioritas (SDI-visual)** — temuan diagregasi per segmen 100 m
   menjadi SDI1–SDI4, total SDI, dan kategori kondisi sebagai dasar
   prioritas penanganan.
5. **Peta GIS** — marker temuan berfilter severity, popup detail, ringkasan
   wilayah.
6. **Riwayat** — arsip sesi inspeksi + filter tanggal/severity/pencarian.
7. **Laporan PDF** — generate otomatis per sesi (foto + tabel temuan) dan
   per segmen (rincian SDI-visual).
8. **Live streaming (demo)** — pratinjau kamera terpisah dari inferensi.
9. **Segmen jalan** — kelola ruas (buat/ubah/hapus), tetapkan sesi ke
   segmen, dan bandingkan SDI-visual dengan SDI manual lapangan.

---

## Tangkapan Layar

### Deteksi gambar
![Hasil deteksi gambar dengan bounding box dan severity](<screenshot aplikasi/deteksi-hasil.png>)

### Segmen jalan + SDI-visual
![Detail segmen dengan agregasi temuan, SDI-visual, SDI manual, dan kategori](<screenshot aplikasi/segmen-detail.png>)

### Live stream
![Live stream dengan bounding box dan metrik FPS](<screenshot aplikasi/live-stream.png>)

### Peta GIS
![Peta temuan dengan filter severity dan popup detail](<screenshot aplikasi/peta.png>)

### Riwayat inspeksi
![Tabel riwayat sesi dengan filter tanggal dan severity](<screenshot aplikasi/riwayat.png>)

### Kalibrasi pengukuran
![Halaman kalibrasi pixels_per_cm](<screenshot aplikasi/kalibrasi.png>)

### Laporan PDF
![Halaman pertama laporan PDF berisi foto dan tabel temuan](<screenshot aplikasi/pdf.png>)

---

## Cara menjalankan

Butuh **Python 3.10 atau 3.11** (venv proyek ini memakai 3.11). Langkahnya sama
untuk semua terminal — yang beda cuma cara mengaktifkan venv. Pilih salah satu:
**CMD**, **PowerShell**, **Git Bash**, atau **Linux/macOS**.

### 1) Buat virtual environment (wajib — jangan install ke Python global)

```bash
python -m venv .venv
```

> Windows: kalau `python` tidak dikenali, pakai `py -3 -m venv .venv`.
> Linux/macOS: pakai `python3 -m venv .venv`.

### 2) Aktifkan venv — sesuai terminal yang dipakai

| Terminal | Perintah aktivasi |
|---|---|
| Windows CMD | `.venv\Scripts\activate.bat` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows Git Bash | `source .venv/Scripts/activate` |
| Linux / macOS | `source .venv/bin/activate` |

Prompt akan diawali `(.venv)` kalau berhasil. Bila PowerShell menolak dengan
*"running scripts is disabled on this system"*, izinkan sekali untuk sesi itu:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Tidak mau repot aktivasi? Panggil Python venv-nya langsung — Windows:
`.venv\Scripts\python.exe web\app.py`, Linux/macOS:
`.venv/bin/python web/app.py` (dependensi tetap harus sudah ter-install).

### 3) Install dependensi

```bash
pip install -r requirements.txt
```

### 3b) OPSIONAL — agar inferensi lebih cepat, pasang torch dengan CUDA

```bash
pip install --upgrade torch torchvision --index-url https://download.pytorch.org/whl/cu126
```

Tanpa langkah ini aplikasi tetap jalan di CPU (ONNX ±6 FPS @640, ±23 FPS @320
dengan preset `halus`). Perintah di atas menggantikan torch CPU yang ikut
terpasang lewat `ultralytics` dengan build CUDA; dengan GPU ±21 FPS.

### 4) Pastikan bobot model ada di `app/weights/`

`best.pt` (gambar + live) · `best.onnx` (cadangan CPU) · `SHA256SUMS.txt`

### 5) Jalankan server

```bash
python web/app.py
# -> http://127.0.0.1:5000
```

Halaman: `/` (Deteksi) · `/peta` · `/riwayat` · `/segmen` · `/kalibrasi` ·
`/tentang` · `/login` (satu peran: admin).

---

## Struktur folder

```
.
├── web/                 # Aplikasi Flask
│   ├── app.py           # routes halaman + API JSON
│   ├── deteksi.py       # pipeline YOLO -> severity
│   ├── streaming.py     # live stream (decouple 3-thread)
│   ├── database.py      # SQLite: admin, sesi, temuan, segmen
│   ├── gambar_sementara.py # gambar anotasi via token URL (bukan base64)
│   ├── templates/       # base/deteksi/peta/riwayat/tentang/kalibrasi/login/...
│   ├── static/          # css/civic.css + js/
│   └── instance/        # riwayat.db (runtime, gitignored)
├── app/                 # modul inti
│   ├── severity.py      # dimensi -> Ringan/Sedang/Berat (deskriptif)
│   ├── sdi.py           # SDI-visual per segmen (instrumen prioritas)
│   ├── scene_gate.py    # gate jalan basah (scene classifier)
│   ├── ringkasan.py     # ringkasan sesi/segmen
│   ├── prioritas.py     # LEGACY: skor severity 33/67/100 (kompat data lama)
│   ├── laporan.py       # PDF laporan sesi + segmen (fpdf2)
│   └── weights/         # best.pt · best.onnx (gitignored)
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
