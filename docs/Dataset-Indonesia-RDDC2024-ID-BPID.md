# Dataset Indonesia: RDDC2024-ID + BPID Bandung

Temuan 2026-09-03. Menjawab isu domain gap (RDD2022 bukan jalan Indonesia).

## 1. RDDC2024-ID — DROP 2026-09-03 (dataset tidak tersedia)
- Repo: https://github.com/endurancechallengeindonesia/RDDC2024-ID (lisensi MIT)
- Isi: 9.000+ foto beranotasi dari jalan Indonesia, format YOLO, dilabeli 44 kontributor (crowdsourced + cross-validasi)
- Download: Google Drive (link di README repo), isi zip: Images + Labels
- KLARIFIKASI 2026-09-03 (cek manual): folder `images/` di GitHub HANYA berisi ilustrasi dokumentasi (P1-P6 severity + readme), BUKAN dataset. Dataset tetap via GDrive.
- STATUS 2026-09-03: user cek manual — dataset tidak ada (GitHub hanya ilustrasi P1-P6, GDrive tidak berisi dataset). DROP dari train, digantikan Roma-remap. Catatan remap di bawah disimpan sebagai arsip bila link hidup lagi.
- BONUS yang tetap dipakai: README repo mendokumentasikan standar severity retak (Low <10mm, Moderate 10-75mm, High >75mm). Dipakai sebagai acuan modul severity (bukan ambang karangan) — sitasi di jurnal.
- Kelas: 0 Longitudinal, 1 Lateral (=transverse), 2 Alligator, 3 Pothole, 4 Other
- PERHATIAN: urutan kelas 3/4 TERTUKAR vs RDD2022 mirror (di sana 3=other, 4=pothole).
  Wajib remap saat gabung (script di bawah). Jangan asal copy folder.

## 2. BPID Bandung (uji independen / OOD test)
- Mendeley Data DOI 10.17632/rgymy6dwdd.1, publikasi 12 Juni 2026, lisensi CC BY 4.0, Binus University
- Isi: foto lubang jalan Kota Bandung, 4 kondisi (cerah / mendung / basah-hujan / malam) + bayangan pohon (hard negative)
- TERVERIFIKASI 2026-09-03 (file sudah di `data/publik/bpid/`): 161 images + 161 labels YOLO,
  pairing 100% (tanpa label 0, tanpa gambar 0), single class id 0 = Pothole, total 263 box (~1,6/gambar).
  Catatan: klaim deskripsi "50 gambar" kedaluwarsa — versi terdownload 161 gambar, lebih baik.
- PERHATIAN: id 0 di sini = Pothole, sedangkan standar repo id 4 = pothole. Untuk evaluasi
  dengan model 5 kelas, remap 0->4 pada SALINAN eval (jangan ubah file asli). Script di Sel 6 template.
- Peran: JANGAN dipakai latih. Pakai sebagai test set OOD + bahan grafik jurnal
  ("model diuji di jalan Bandung yang tidak pernah dilihat saat training").

## 3. Strategi gabungan final
- Train: RDD2022 subset (India + China_MotorBike + Japan, exclude Norway) + RDDC2024-ID + 150 foto lokal sendiri
- Val: campuran proporsional
- Test: split test RDD2022 + BPID Bandung + foto lokal (3 test set = bahan analisis generalisasi)
- Sitasi wajib: Arya et al. 2024 (RDD2022) + repo RDDC2024-ID + DOI BPID

## 4. Remap kelas RDDC2024-ID -> standar repo (ikut RDD2022 mirror)
- RDDC 0 -> 0 longitudinal_crack (tetap)
- RDDC 1 -> 1 transverse_crack (lateral = transverse, tetap)
- RDDC 2 -> 2 alligator_crack (tetap)
- RDDC 3 (pothole) -> 4
- RDDC 4 (other) -> 3
```python
from pathlib import Path
REMAP = {"0":"0", "1":"1", "2":"2", "3":"4", "4":"3"}
for t in Path("labels_rddc_id").glob("*.txt"):
    out = []
    for l in t.read_text().strip().splitlines():
        p = l.split()
        p[0] = REMAP[p[0]]
        out.append(" ".join(p))
    (Path("labels_std")/t.name).write_text("\n".join(out))
```
