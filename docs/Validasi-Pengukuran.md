# Validasi Pengukuran & Severity — Panduan

Dua eksperimen ini menutup kelemahan metodologi paling rawan ditanya penguji:
**seberapa akurat pengukuran (cm) dan klasifikasi severity**, bukan sekadar mAP
deteksi. Keduanya memakai skrip yang sudah ada di `scripts/`.

---

## 1. Validasi kalibrasi (`pixels_per_cm`)

**Tujuan:** mengukur galat ukuran nyata vs terukur (cm) setelah kalibrasi.

**Cara mengumpulkan data:**
1. Siapkan objek acuan berukuran diketahui (mis. keramik 30×30 cm, penggaris 10 cm).
2. Foto objek itu dengan kamera + jarak yang dipakai saat inspeksi.
3. Catat berapa piksel panjang objek pada foto (bisa lewat tool kalibrasi/klik 2 titik).
4. Isi baris ke `docs/contoh-validasi/kalibrasi.csv`:
   `nama,panjang_px,panjang_cm_nyata,ppc` (kolom `ppc` boleh kosong ⇒ pakai default).

**Jalankan:**
```bash
.\.venv\Scripts\python scripts\validasi_kalibrasi.py --csv docs/contoh-validasi/kalibrasi.csv
```

**Luaran:** galat per objek + **MAE (cm)**, **MAPE (%)**, galat maksimum, dan bias.
Interpretasi: MAPE < ±10 % wajar untuk kamera monokular tanpa referensi; laporkan
apa adanya. Ulangi minimal 5–10 objek agar bermakna.

---

## 2. Validasi severity

**Tujuan:** confusion matrix Ringan/Sedang/Berat (prediksi sistem vs label manual).

**Cara mengumpulkan data:**
1. Deteksi sejumlah temuan (mis. 30–100 titik dari foto beragam).
2. Untuk tiap temuan, ketik label severity manual (penilaian orang) sebagai `aktual`
   dan biarkan `prediksi` = keluaran sistem.
3. Isi `docs/contoh-validasi/severity.csv` dengan kolom `prediksi,aktual`.

**Jalankan:**
```bash
.\.venv\Scripts\python scripts\validasi_severity.py --csv docs/contoh-validasi/severity.csv
```

**Luaran:** akurasi keseluruhan, matriks aktual×prediksi, recall & precision per kelas.
Interpretasi: kelas yang paling sering salah menandakan ambang di `config/severity.yaml`
perlu disesuaikan.

---

## Catatan kejujuran
- Ini **estimasi**, bukan pengukuran presisi (kamera monokular tak mengukur kedalaman).
- Jangan mengklaim RAB; nilai rupiah = indeks prioritas dari tabel harga acuan.
- Selalu laporkan jumlah sampel (n) dan sebaran kelas.

---

## 3. Hukum jarak: `pixels_per_cm` bergantung pada jarak (temuan)

Diukur dari foto keramik **30×30 cm** (Poco M6 Pro, zoom 1×) dengan
`scripts/ukur_kalibrasi_foto.py` (deteksi garis nat otomatis + overlay verifikasi):

| Jarak | jarak nat (px) | ppc terukur | ppc × jarak |
|---|---|---|---|
| 49–53 cm | 2148,5 | **71,62** | 3581 |
| 98–102 cm | 1140,8 | **38,03** | 3803 |

Cek silang meteran (foto 50 cm): rentang pita ≈ 4410 px ≈ 61,6 cm pada 71,6 px/cm,
cocok dengan label pita sampai **"24"** (inci) ≈ 61 cm → referensi valid.

**Kesimpulan:** `ppc × jarak ≈ konstan ≈ 3600–3800 px·cm` (≈ **3700 ± 5%**), jadi
`ppc ≈ 3700 / jarak_cm`.

**Bukti pentingnya kalibrasi per jarak.** Bila satu `ppc` saja dipakai untuk semua jarak
(nilai aplikasi **11,4342**, setara ± 3,1 m):

| Foto | nyata | terukur | galat |
|---|---|---|---|
| keramik @ 50 cm | 30 cm | 187,9 cm | **+526%** |
| keramik @ 100 cm | 30 cm | 99,8 cm | **+233%** |

(MAE 113,8 cm · MAPE 379% · bias +113,8 cm → cenderung **over-estimasi**.)
Reproduksi: `.\.venv\Scripts\python scripts\validasi_kalibrasi.py --csv docs/contoh-validasi/kalibrasi-jarak.csv --ppc 11.4342`

**Implikasi skripsi:** satu `ppc` global hanya sah di dekat jarak kalibrasinya; estimasi
ukuran (dan biaya) akan membengkak bila jarak foto berbeda. Mitigasi: kalibrasi per jarak
(atau catat jarak saat memotret) — nilai praktis `ppc ≈ 3700 / jarak_cm`.

**Belum selesai — perlu foto ulang ± 2 m.** Dua percobaan belum bisa dipakai:

- `jarak foto 198 - 203 cm.jpg` — lantai penuh barang/kabel → garis nat terputus, deteksi gagal.
- `jarak foto 185 - 192 cm.jpg` — **resolusi 1444×2560 (setengah dari foto lain)** → indikasi
  **zoom/crop berbeda**, sehingga skalanya tidak sebanding dengan seri 50/100 cm; deteksi grid
  juga tidak konsisten.

**Syarat foto ulang:** setelan kamera **sama persis** dengan foto 50 & 100 cm (resolusi penuh
± 2608×4624 / 4624×2608, zoom 1×, tanpa crop), **lantai bersih**, kamera **menghadap lurus ke
bawah**, dan **pita meteran dibentangkan lurus**. Lalu:
`.\.venv\Scripts\python scripts\ukur_kalibrasi_foto.py --gambar "<foto 2m>" --cm 30`

Catatan metodologi: untuk seri jarak, **jangan mengubah zoom/resolusi kamera** — kalau berubah,
`ppc` berubah bukan karena jarak, sehingga serinya tidak sahih.


