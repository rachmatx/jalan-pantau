# Negatif dari Roboflow & Data Sintetis (AI) — Panduan

Dua topik yang sering bikin salah langkah. Ringkas: **negatif dari Roboflow = bagus**;
**video AI = boleh, TAPI tidak boleh disebut "dataset lokal" dan berisiko metodologis.**

---

## A. Mengambil NEGATIF dari Roboflow (disarankan)

Tujuan negatif: gambar **jalan tanpa kerusakan** (background) → menekan false alarm.

**Cara mencari (universe.roboflow.com):**
- Kata kunci: `road damage`, `pothole`, `asphalt`, `road surface`, `street`, `crack`.
- **Prioritaskan** dataset yang:
  1. punya kelas **"no damage" / "background" / "normal"**, atau
  2. lokasinya **Asia tropis / Indonesia** (kedekatan domain), atau
  3. berisi banyak gambar **tanpa anotasi**.

**Mengambil yang benar-benar negatif:**
- Ekspor dataset format **YOLOv8 / YOLO (txt)** atau **Folder Structure**.
- Setelah diekstrak, **ambil gambar yang file labelnya kosong** (0 baris) → itu negatif.
- Rumus cepat: untuk tiap `images/x.jpg`, cek `labels/x.txt` ada & kosong.

**Alat:** `scripts/ambil_negatif_roboflow.py` — arahkan ke folder hasil **ekspor YOLO**
Roboflow; skrip menyalin gambar yang **labelnya kosong / tanpa label** ke folder negatif,
lengkap dengan ringkasan (total / berlabel / tanpa label / negatif). Contoh:
```bash
.\.venv\Scripts\python scripts\ambil_negatif_roboflow.py --dir data/lokal/roboflow --out data/lokal/negatif-roboflow
```

**Dua dataset yang sudah diperiksa (2026-09):**

| Dataset | Gambar | Kelas | Lisensi | Versi | Catatan |
|---|---|---|---|---|---|
| Suprava Priyadarshini — *Road damage detection* | 50 (25 "no damage") | `damage`, `no damage` | **CC BY 4.0** | 0 (perlu **Fork + generate version**) | domain India (`India_...`); cek overlap subset |
| Yeeun KIm — *pothole* | **1.302** | `pothole` (filter `class:null` = tanpa anotasi) | **CC BY 4.0** | 13 (siap ekspor) | filter null = kandidat negatif; campur & domain tak jelas → **review manual** |

Catatan: nama file pada dataset kedua sangat beragam (`dry000xx.jpg`, `-11-.jpg`,
`2010042156358698.jpg`, `beautiful-road.jpg`) → kemungkinan gabungan dari berbagai sumber,
sehingga **kualitas/kedekatan domain tidak terjamin**. Pastikan ekspor menyertakan gambar
tanpa anotasi; bila tidak, unduh per gambar dari halaman browse.


**Tanpa login (Wikimedia Commons):** `scripts/unduh_negatif_publik.py` — mengunduh foto
jalan/aspal dari **kategori** Commons (lebih presisi daripada kata kunci), menyaring gambar
gelap/terlalu kecil, dan menulis `Kredit.csv` untuk atribusi (lisensi CC BY-SA / CC0 / PD).
Contoh: 60 gambar → 32 lolos saring model. Batasan: mayoritas **luar Indonesia** (domain gap)
dan sebagian tak relevan → tetap **tinjau manual**. Alur:
```bash
.\.venv\Scripts\python scripts\unduh_negatif_publik.py --maks 60
.\.venv\Scripts\python scripts\kandidat_negatif.py --in data/lokal/negatif-publik --out data/lokal/negatif-bersih
```
Catatan: pencarian **kata kunci** di Commons berisik (pernah 40 hasil → banyak mesin aspal,
angkasa/bandara, bahkan jalan rusak); **kategori jauh lebih baik**.

**Jebakan:**
- **Lisensi** tiap dataset berbeda (CC BY 4.0, CC BY-NC, atau restricted). **Catat lisensi &
  sumber** untuk atribusi di skripsi; jangan pakai yang melarang penggunaan komersial bila
  skripsi dianggap demikian.
- **Domain gap**: mayoritas dataset luar negeri. Negatif "jalan aspal negara lain" tetap
  berguna menekan false alarm umum, tapi **bukan pengganti** data lokal.
- Kualitas anotasi bervariasi → jangan campur ke kelas positif tanpa memeriksa.

---

## B. Data sintetis / video AI sebagai "dataset lokal" — HATI-HATI

### Yang TIDAK boleh
- Menyebut gambar/video **hasil AI** sebagai **"foto lokal Bandung"**. Itu **klaim palsu**
  dan masalah integritas akademik. Harus dilabeli eksplisit **sintetis**.
- Menguji pada data sintetis lalu melaporkannya sebagai performa nyata.

### Masalah teknis
- Video/gambar AI generatif (Sora, Veo, Kling, dsb.) umumnya **berbayar**; yang gratis/open
  (**CogVideoX, LTX-Video, Wan2.1, AnimateDiff**, atau gambar **SDXL/Flux** via `diffusers`)
  butuh **GPU** (bisa di Kaggle) tapi kualitas jalan realistisnya belum tentu cukup.
- Artefak khas (retak tak wajar, tekstur aneh, perspektif salah) → model bisa belajar **fitur
  palsu**, dan **gagal di data nyata** (synthetic→real gap).
- Retak/kerusakan hasil AI sering **tidak realistis secara dimensi** → mengganggu asumsi
  severity & kalibrasi.

### Cara pakai yang SAH (dan tetap berguna)
1. **Negatif sintetis**: generate "aspal baik" → risikonya lebih kecil karena hanya perlu
   tampak seperti aspal wajar.
2. **Augmentasi terkontrol**: pakai **img2img / inpainting** pada foto nyata untuk
   menambah/menghapus kerusakan — bukan mengganti data.
3. **Jadikan ablasi**: eksperimen "efek data sintetis" yang dilaporkan apa adanya
   (menarik untuk pembahasan skripsi), **bukan** sebagai data utama.

### Rekomendasi
- **Untuk domain adaptation, 50 foto nyata dari HP-mu jauh lebih bernilai daripada 500 gambar
  sintetis.** Jangan tunda demi sintetis.
- Kalau butuh "lokal" cepat tanpa merekam: pakai **Mapillary / Wikimedia Commons** (nyata,
  gratis, ada liputan Indonesia) sebagai **proksi**, dan sebutkan batasannya.
- **Set uji wajib nyata** (mis. BPID Bandung) supaya klaim performa valid.

---

## C. Alur yang disarankan

1. Kumpulkan **negatif nyata**: rekam sendiri + Roboflow (filter label kosong) + Mapillary.
2. Saring/tinjau: `scripts/kandidat_negatif.py` (frame tanpa deteksi → kandidat), lalu **review manual**.
3. Untuk unlabeled: frame dari rekaman sendiri (tanpa label) — bukan sintetis.
4. (Opsional) Data sintetis **hanya sebagai augmentasi**, dilabeli jelas + dilaporkan sebagai ablasi.
5. Evaluasi akhir: **data uji nyata** (BPID Bandung / lokal nyata).

Alat pendukung di repo:
- `scripts/ekstrak_frame.py` — video → frame.
- `scripts/kandidat_negatif.py` — saring kandidat negatif via model.
- `docs/Panduan-Tuning-Model.md` — cara pakai negatif untuk hard-negative mining.
- `docs/Cara-Training-Kaggle.md` — alur training.
