# API JalanPantau

Server: Flask, default `http://127.0.0.1:5000` (jalankan `python web/app.py`).
Semua respons JSON (`application/json`) kecuali yang bertanda lain.

> **Catatan scope (Okt 2026):** aplikasi ini satu peran saja (**admin**).
> Fitur lama (disposisi, SPK, kontraktor, portal dinas, mode mobile) sudah
> dihapus dari kode; lihat riwayat git. Dokumen ini mengikuti route yang
> benar-benar terdaftar di `web/app.py`.

## Konvensi umum

- **CSRF**: semua request yang mengubah state (`POST`, `PUT`, `PATCH`, `DELETE`)
  wajib menyertakan token per-sesi, salah satu dari:
  - header `X-CSRF-Token` (dipakai otomatis oleh wrapper `fetch` di halaman), atau
  - field form `_csrf`.
  Token tersedia di `<meta name="csrf-token">` tiap halaman dan `{{ csrf_token() }}`
  di template. Bila tidak valid → `403`.
  Nonaktif saat `app.config["TESTING"]=True` atau env `JP_CSRF=0`.
- **Auth**: endpoint bertanda 🔒 butuh login (peran tunggal: admin). Bila belum
  login, API membalas `401` JSON; halaman HTML diarahkan ke `/login`.
- **Rate limit**: `flask-limiter`, default `600 per hour`. Batas lebih ketat:
  login `5/menit; 20/jam` · `POST /api/detect` `30/menit; 300/jam` ·
  `POST /api/laporan` & `POST /api/riwayat` `20/menit; 200/jam` ·
  `POST /api/video` `10/menit; 100/jam` · `POST /api/demo` &
  `POST /api/stream/start` `10/menit; 60/jam` · `POST /api/kalibrasi/foto`
  `10/menit; 60/jam` · `DELETE /api/riwayat/<sid>` `10/jam`.
  `/api/stream` dan `/api/stream/stats` dikecualikan (MJPEG long-lived + polling).
- **Error**: `{"error": "<pesan berbahasa Indonesia>"}` dengan status yang sesuai.
  Rute `/api/*` yang tidak dikenal / metode salah membalas JSON (`404`/`405`),
  bukan halaman HTML.
- **Ukuran upload**: gambar deteksi ≤ 15 MB, foto kalibrasi ≤ 5 MB,
  video ≤ 200 MB.
- **Header keamanan**: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: strict-origin-when-cross-origin`; respons `/api/*` `no-store`.

## Halaman (HTML)

| Route | Fungsi |
|---|---|
| `/` | Deteksi (tab Gambar & Live) |
| `/peta` | Peta sebaran GPS (Leaflet) |
| `/riwayat` | Riwayat inspeksi |
| `/tentang` | Tentang & metrik model |
| `/kalibrasi` | 🔒 Kalibrasi `pixels_per_cm` |
| `/laporan/preview/<sid>` | Pratinjau berita acara |
| `/login`, `/logout` | Autentikasi admin |

## Deteksi & laporan

| Metode | Endpoint | Batas | Catatan |
|---|---|---|---|
| POST | `/api/detect` | 30/menit | multipart: `gambar`, `conf`, `malam`, `teliti` → `{rows, total, model, image_b64, gps, malam, teliti, gelap, disaring, scene}` |
| POST | `/api/verifikasi` | — | JSON `{rows, hapus[], severity{}}` → hasil koreksi operator + total |
| POST | `/api/laporan` | 20/menit | JSON `{rows, total, image_b64, source, model, verifikasi}` → **PDF** (`application/pdf`) |

> Model yang dipakai adalah YOLO dalam mode **deteksi bounding box**, bukan
> segmentasi; dataset latih (RDD2022) hanya beranotasi kotak. Lihat
> `docs/Segmentasi-atau-Bounding-Box.md`.

Parameter `conf` dijepit ke rentang `0.05–0.8` (default `0.30`). `malam` dan
`teliti` bernilai `1`/`true`/`on`. Jalur normal adalah **full-frame** pada
`imgsz_gambar` (640) — server me-letterbox foto 12 MP ke 640×640, bukan
memberi 4000 px mentah ke model. `teliti=1` menyalakan mode tiling (potong jadi
tile 640 px); **mode ini hanya eksperimen dan bukan default** — diukur pada
161 gambar BPID berlabel, tiling memberi F1 0,011 vs 0,431 untuk full-frame
(`docs/Panduan-Tuning-Model.md` §6d). `gelap: true` = rata-rata kanal L < 60; UI
memakainya untuk menyarankan opsi `malam` (CLAHE). Opsi `maks_sisi_proses` dapat
memperkecil gambar untuk analisis, tetapi box tetap dikembalikan pada **koordinat
gambar asli** sehingga kalibrasi px/cm tidak berubah (§6e).

Kunci `disaring` merinci kandidat yang dibuang (umumnya bilangan bulat;
`gate` berupa objek, `skala_proses` berupa pecahan):

| Kunci | Arti |
|---|---|
| `rusak` | box/conf NaN atau Inf dari model (mis. overflow FP16) — diabaikan |
| `ambang` | confidence di bawah ambang efektif kelasnya |
| `ukuran` | geometri mustahil menurut kalibrasi px/cm (`masuk_akal`) |
| `mungil` | luas box < `saring.luas_min_px` |
| `tepi_tile` | box terpotong tepi-dalam tile (hanya mode teliti) |
| `silang_kelas` | box lintas kelas yang dilebur NMS agnostik (hanya mode teliti) |
| `fragmen` | fragmen yang dilebur `gabung_fragmen` |
| `gate` | `{aktif, disaring, ambang_lubang}` — gate jalan basah |
| `topk` | baris dipangkas `saring.maks_temuan` |
| `skala_proses` | faktor pengecil analisis (1,0 = resolusi asli, lihat `maks_sisi_proses`) |

`rusak` **bukan** kesalahan penyaring: box-nya memang tidak sah, dan bila
dibiarkan bisa merusak deteksi lain lewat `wbf_gabung` serta membuat JSON
mengandung `NaN` (ditolak `JSON.parse` di browser).

## Kalibrasi

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/kalibrasi` | status + dampak (`box_100px_cm`, `lubang_25cm_px`) |
| POST | `/api/kalibrasi` | 🔒 JSON `{pixels_per_cm}` atau `{panjang_px, panjang_cm}` |
| POST | `/api/kalibrasi/foto` | 🔒 multipart `foto` → `{image_b64, lebar, tinggi}` (untuk klik 2 titik). `lebar`/`tinggi` = ukuran **asli** foto (bukan ukuran tampil), agar `pixels_per_cm` satu ruang dengan koordinat box deteksi |

`pixels_per_cm` disimpan ke `config/severity.yaml` (tulis atomik, komentar
dipertahankan) dan langsung berlaku untuk deteksi berikutnya.

## Live stream

| Metode | Endpoint | Catatan |
|---|---|---|
| GET | `/api/stream` | **MJPEG** (`multipart/x-mixed-replace`) |
| POST | `/api/stream/start` | JSON `{source, target, conf, frame_skip, malam, performa}` → `{ok, token}` |
| POST | `/api/stream/stop` | hentikan sesi (butuh `token` bila stream berjalan) |
| GET | `/api/stream/stats` | FPS tampil/infer, jumlah track, deteksi |
| POST | `/api/stream/anotasi` | toggle anotasi box |
| POST | `/api/stream/snapshot` | snapshot track → `{rows, total, ...}` |
| POST | `/api/demo` | putar video contoh bawaan |
| POST | `/api/video` | multipart `video` → putar berkas |

`source` = `webcam` (target = index 0-10) · `ipcam` (target = URL http/https) ·
`file` (dari `/api/video`). `performa` opsional: `halus` | `seimbang` | `akurat`.
Satu stream aktif dalam satu waktu; saat stream berjalan, `start`/`stop`/`anotasi`/
`snapshot` dari tab lain ditolak (`409`/`403`) kecuali menyertakan `token` pemilik
yang dikembalikan `start`.

## Riwayat & peta

| Metode | Endpoint | Catatan |
|---|---|---|
| POST | `/api/riwayat` | simpan sesi → `{id}` atau `{id, duplikat: true, ...}`; 20/menit; `image_b64` ≤ 12 MB |
| GET | `/api/riwayat` | daftar (`dari`, `sampai`, `severity`, `q`); `{data, overflow, total_db}` |
| GET | `/api/riwayat/<sid>` | detail sesi + temuan |
| DELETE | `/api/riwayat/<sid>` | 🔒 hapus (10/jam) |
| GET | `/api/riwayat/<sid>/gambar` | JPEG bukti (`?thumb=1` untuk thumbnail) |
| GET | `/api/peta` | titik GPS untuk peta (maks 500 terbaru) |

Simpan sesi idempoten: menyertakan `client_ref` yang sama tidak membuat baris
baru. Ada juga heuristik anti-duplikat koordinat (±11 m, 10 menit terakhir) yang
bisa dilewati dengan `izinkan_duplikat: true`. Nilai yang dihitung server dan
**tidak** dipercaya dari klien: `total` sesi = jumlah skor temuan, dan **skor
tiap temuan** diturunkan dari `severity` (Ringan 33 / Sedang 67 / Berat 100,
rumus `app/prioritas.py`).

## Contoh

```bash
# Deteksi (perhatikan token CSRF dari meta halaman)
TOKEN=$(curl -s -c cj.txt http://127.0.0.1:5000/ | grep -o 'csrf-token" content="[^"]*' | cut -d'"' -f3)
curl -b cj.txt -H "X-CSRF-Token: $TOKEN" -X POST http://127.0.0.1:5000/api/detect \
  -F "gambar=@data/publik/bpid/test/images/04a8f35f.jpeg" -F "conf=0.25"
```

Catatan: skrip `scripts/cek_detect.py` dan `scripts/smoke_web.py` sudah menangani
pengambilan token otomatis.
