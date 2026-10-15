# API JalanPantau

Server: Flask, default `http://127.0.0.1:5000` (jalankan `python web/app.py`).
Semua respons JSON (`application/json`) kecuali yang bertanda lain.

## Konvensi umum

- **CSRF**: semua request yang mengubah state (`POST`, `PUT`, `PATCH`, `DELETE`)
  wajib menyertakan token per-sesi, salah satu dari:
  - header `X-CSRF-Token` (dipakai otomatis oleh wrapper `fetch` di halaman), atau
  - field form `_csrf`, atau
  - query `?_csrf=...`.
  Token tersedia di `<meta name="csrf-token">` tiap halaman dan `{{ csrf_token() }}`
  di template. Bila tidak valid → `403`.
  Nonaktif saat `app.config["TESTING"]=True` atau env `JP_CSRF=0`.
- **Auth**: endpoint bertanda 🔒 butuh login. Tanda 🔒🔑 butuh superadmin.
  Endpoint kontraktor bertanda "Kontraktor" hanya bisa dipakai akun
  kontraktor. API mengembalikan `401` (belum login) / `403` (bukan wewenang)
  JSON.
- **Rate limit**: `flask-limiter`, default 600/jam; login 5/menit; beberapa
  endpoint tulis dibatasi lebih ketat. `/api/stream` dan `/api/stream/stats`
  dikecualikan.
- **Error**: `{"error": "<pesan berbahasa Indonesia>"}` dengan status yang sesuai.
- **Ukuran upload**: gambar deteksi ≤ 15 MB, foto kalibrasi/disposisi ≤ 5 MB,
  video ≤ 200 MB.

## Halaman (HTML)

| Route | Fungsi |
|---|---|
| `/` | Deteksi (tab Gambar & Live) |
| `/peta` | Peta sebaran GPS |
| `/riwayat` | Riwayat inspeksi |
| `/tentang` | Tentang & metrik model |
| `/kalibrasi` | Kalibrasi `pixels_per_cm` |
| `/mobile` | Mode lapangan (mockup demo) |
| `/laporan/preview/<sid>` | Pratinjau berita acara |
| `/disposisi`, `/disposisi/<sid>` | Kirim / lacak disposisi |
| `/login`, `/logout` | Autentikasi admin |
| `/pupr-<daerah>/dashboard[/<halaman>]` | 🔒 Portal dinas |
| `/kontraktor/dashboard`, `/kontraktor/spk/<id>` | 🔒 Ruang kerja kontraktor |

### Cara kerja otorisasi dua peran

Satu form login melayani dua jenis akun, dibedakan oleh peran di sesi:

| Peran | Akun contoh | Boleh |
|---|---|---|
| Superadmin | `admin` | Semua daerah, kelola instansi dan sandi |
| Admin dinas | `pupr_bandung` | Hanya daerahnya sendiri |
| Kontraktor | `kt_mitrakarya` | Hanya SPK miliknya sendiri |

Aturan yang ditegakkan di server:

- Akun kontraktor **tidak** bisa membuka halaman/API dinas (diarahkan balik
  ke ruang kerjanya).
- Akun dinas **tidak** bisa memakai endpoint kontraktor (`403`).
- Kontraktor hanya melihat SPK dengan `kontraktor_id` miliknya. ID lain
  dijawab `404`, bukan `403`, supaya keberadaan SPK milik orang tidak
  terkonfirmasi.
- SPK hanya bisa maju satu tahap. Kontraktor tidak bisa membatalkan SPK;
  pembatalan hanya milik dinas.
- Titik pekerjaan tidak bisa ditandai Selesai sebelum foto bukti diunggah.

## Deteksi & laporan

| Metode | Endpoint | Catatan |
|---|---|---|
| POST | `/api/detect` | multipart: `gambar`, `conf`, `malam`, `teliti`, `segmentasi` → `{rows, total, image_b64, model, ...}` |
| POST | `/api/verifikasi` | JSON `{rows, hapus[], severity{}}` → hasil koreksi operator + total |
| POST | `/api/laporan` | JSON `{rows, total, image_b64, source, model}` → **PDF** (`application/pdf`) |

### Catatan penting soal parameter `segmentasi`

Field `segmentasi` pada `/api/detect` **bukan** segmentasi dari model.
Model yang dipakai adalah YOLO dalam mode **deteksi bounding box**, dan
dataset latihnya juga hanya beranotasi kotak.

Kalau `segmentasi=1` dikirim, yang dijalankan adalah
`web/deteksi.py::pseudo_segmentation`: pencarian kontur **di dalam** bounding
box hasil deteksi, lalu luas dihitung dari kontur itu. Field ini opsional
dan hanya memengaruhi overlay polygon pada gambar keluaran serta ketepatan
hitungan luas. Nilai `0` (atau tidak dikirim) membuat seluruh baris hasil
tanpa data luas yang bergantung pada segmentasi.

Kalau butuh mask presisi, itu proyek terpisah: butuh anotasi polygon pada
dataset. Lihat `docs/Segmentasi-atau-Bounding-Box.md`.

## Kalibrasi

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/kalibrasi` | status + dampak (`box_100px_cm`, `lubang_25cm_px`) |
| POST | `/api/kalibrasi` | JSON `{pixels_per_cm}` atau `{panjang_px, panjang_cm}` |
| POST | `/api/kalibrasi/foto` | multipart `foto` → `{image_b64, lebar, tinggi}` (untuk klik 2 titik) |

## Live stream

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/stream` | **MJPEG** (`multipart/x-mixed-replace`) |
| POST | `/api/stream/start` | JSON `{source, target, conf, frame_skip, malam, performa}` |
| POST | `/api/stream/stop` | hentikan sesi |
| GET | `/api/stream/stats` | FPS tampil/infer, jumlah track, deteksi |
| POST | `/api/stream/anotasi` | toggle anotasi box |
| POST | `/api/stream/snapshot` | snapshot track → `{rows, total, ...}` |
| POST | `/api/demo` | putar video contoh bawaan |
| POST | `/api/video` | multipart `video` → putar berkas |

## Riwayat & peta

| Metode | Endpoint | Catatan |
|---|---|---|
| POST | `/api/riwayat` | simpan sesi → `{id}` |
| GET | `/api/riwayat` | daftar (`dari`, `sampai`, `severity`, `q`); `{data, overflow, total_db}` |
| GET | `/api/riwayat/<sid>` | detail sesi + temuan |
| DELETE | `/api/riwayat/<sid>` | 🔒 hapus |
| GET | `/api/riwayat/<sid>/gambar` | JPEG bukti (`?thumb=1` untuk thumbnail) |
| GET | `/api/peta` | titik GPS untuk peta |

## Instansi & disposisi

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/instansi` | daftar (`?daerah=slug`) |
| GET | `/api/instansi/terdekat` | `?lat=&lon=` → instansi terdekat (Haversine) |
| GET | `/api/instansi/<iid>` | detail |
| POST | `/api/instansi` | 🔒🔑 tambah |
| DELETE | `/api/instansi/<iid>` | 🔒🔑 hapus |
| GET | `/api/disposisi` | daftar (`?daerah=&status=&urgensi=&exact=`) |
| GET | `/api/disposisi/stats` | total untuk filter sama |
| GET | `/api/disposisi/<did>` | detail + riwayat catatan |
| POST | `/api/disposisi` | kirim disposisi → `{id}` |
| PUT | `/api/disposisi/<did>` | 🔒 update status |
| POST | `/api/disposisi/<did>/foto` | 🔒 multipart `foto` — **ditolak bila laporan sudah punya SPK** |
| DELETE | `/api/disposisi/<did>` | 🔒 hapus |

## Admin

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/admin` | 🔒🔑 daftar akun dinas |
| POST | `/api/admin/sandi` | 🔒🔑 set/ganti sandi `{username, sandi_baru}` (min 8) |

## Kontraktor & SPK

Dinas menerbitkan SPK; kontraktor yang mengerjakannya. Kontraktor hanya
melihat SPK miliknya sendiri.

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/spk` | 🔒 daftar SPK (`?daerah=`; admin berdaerah dikunci ke daerahnya) |
| POST | `/api/spk` | 🔒 terbitkan SPK `{daerah, kontraktor_id, judul, disposisi_ids[], prioritas, tenggat, catatan_dinas}` |
| POST | `/api/spk/<sid>/batal` | 🔒 batalkan SPK (hanya dinas daerah penerbit) |

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/kontraktor/spk` | Kontraktor daftar SPK miliknya |
| POST | `/api/kontraktor/spk/<sid>/status` | Kontraktor `{status: Diterima\|Dikerjakan\|Selesai, catatan}` |
| POST | `/api/kontraktor/spk/<sid>/tugas/<tid>` | Kontraktor status satu titik `{status: Dikerjakan\|Selesai, catatan}` |
| POST | `/api/kontraktor/spk/<sid>/tugas/<tid>/foto` | Kontraktor unggah foto bukti (JPG/PNG, maks 5 MB) |
| GET | `/api/kontraktor/spk/<sid>/tugas/<tid>/foto` | Foto bukti; boleh dibuka pemilik SPK atau dinas daerah penerbit |

| Metode | Endpoint | Catatan |
|---|---|---|
| POST | `/api/kontraktor` | 🔒 tambah/update kontraktor (kunci = kode) |
| POST | `/api/kontraktor/sandi` | 🔒🔑 set sandi akun kontraktor `{username, sandi}` (min 8) |

### Status SPK

Tujuh status, dipisah menurut siapa yang boleh menjalankannya
(`SPK_TRANSISI` di `web/database.py`):

| Status | Situs | Kontraktor boleh | Dinas boleh |
|---|---|---|---|
| `Diterbitan` | dinas terbitkan SPK | → `Diterima` | → `Dibatalkan` |
| `Diterima` | kontraktor menerima penugasan | → `Dikerjakan` | → `Dibatalkan` |
| `Dikerjakan` | kontraktor mengerjakan | → `Menunggu Penerimaan` | → `Dibatalkan` |
| `Menunggu Penerimaan` | hasil kerja diajukan | — | → `Diterima Dinas`, `Perlu Revisi` |
| `Perlu Revisi` | dinas menolak hasil kerja | → `Menunggu Penerimaan` (otomatis) | → `Dibatalkan` |
| `Diterima Dinas` | BAST, status final | — | → `Menunggu Penerimaan` (batalkan terima) |
| `Dibatalkan` | dibatalkan dinas, final | — | — |

Dinas **tidak pernah** bisa menaikkan status ke `Dikerjakan`: pekerjaan
lapangan dinaikkan kontraktor, atau otomatis server saat titik pertama
dimulai.

Kalau seluruh titik pekerjaan sudah Selesai, SPK otomatis naik ke
`Menunggu Penerimaan` tanpa perlu klik tambahan. Ini juga berlaku setelah
revisi — kontraktor tidak punya tombol submit saat status `Perlu Revisi`.

Status `Diterima Dinas` mengunci bukti foto: unggahan foto baru ditolak
karena bukti publik harus sama dengan yang pernah diperiksa dinas.

### Bukti foto

Tiga jenis berkas, tidak saling menimpa:

| Jenis | Kolom | Diunggah | Keterangan |
|---|---|---|---|
| Foto inspeksi | `sesi.gambar` | Operator | Saat deteksi, otomatis |
| Bukti hasil kerja | `spk_tugas.foto_selesai` | Kontraktor | Wajib sebelum tugas Selesai; terkunci setelah BAST |
| Foto sesudah | `disposisi.foto_sesudah` | Dinas | **Hanya untuk laporan tanpa SPK** |

Untuk laporan yang sudah punya SPK, bukti yang otoritatif adalah foto hasil
kerja kontraktor yang disetujui dinas lewat BAST, disajikan lewat
`GET /api/disposisi/<did>/foto-bukti`. Endpoint itu publik tanpa login, tapi
hanya melayani SPK berstatus `Diterima Dinas`.

Endpoint foto yang tersedia:

| Method | Path | Akses |
|---|---|---|
| POST | `/api/disposisi/<did>/foto` | 🔒 dinas daerah; ditolak bila sudah ada SPK |
| GET | `/api/disposisi/<did>/foto` | publik |
| GET | `/api/disposisi/<did>/foto-bukti` | publik; hanya bila SPK `Diterima Dinas` |

## Contoh

```bash
# Deteksi (perhatikan token CSRF dari meta halaman)
TOKEN=$(curl -s -c cj.txt http://127.0.0.1:5000/ | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
curl -b cj.txt -H "X-CSRF-Token: $TOKEN" -X POST http://127.0.0.1:5000/api/detect \
  -F "gambar=@data/publik/bpid/test/images/04a8f35f.jpeg" -F "conf=0.25"
```

Catatan: skrip `scripts/cek_detect.py` dan `scripts/smoke_web.py` sudah menangani
pengambilan token otomatis.
