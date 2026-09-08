# Dataset Roma (Lorenzo Arcioni) — khusus prototipe + manhole

URL: https://www.kaggle.com/datasets/lorenzoarcioni/road-damage-dataset-potholes-cracks-and-manholes
Cek: 2026-09-03. Lisensi MIT. Usability 8,75. Ukuran 194,79 MB (AMAN untuk disk).

## Fakta
- 2.009 gambar 640x360, Roma/Sacrofano Italia (GoPro HERO7 + Samsung A14)
- Kelas (3): 0 Pothole, 1 Crack, 2 Manhole
- Anotasi: polygon quadrilateral + labels-YOLO (box) + COCO + script konversi
- Nilai jual: manhole eksplisit (menekan false positive), dokumentasi rapi

## Putusan: JANGAN jadi dataset utama. Peran = prototipe + suplemen manhole.
Alasan:
1. Kecil (2rb vs 38rb RDD2022 vs 9rb RDDC-ID) dan Italia saja (domain gap ke Indonesia).
2. Kelas kasar (crack tidak dipecah) dan TIDAK kompatibel dengan skema 5 kelas
   (tidak bisa asal gabung — pothole cocok, crack ambigu, manhole tidak ada padanannya).
3. Resolusi 640x360 lebih rendah dari dataset lain.

## Cara pakai yang benar
- Smoke-test pipeline: latih YOLOv11n 20-30 epoch di dataset ini (±30 menit di T4) untuk
  memastikan kode train/val/export/Streamlit beres SEBELUM bakar kuota di dataset besar.
- Eksperimen manhole: uji apakah model utama salah mendeteksi manhole sebagai pothole;
  bila ya, tambah sampel manhole ini sebagai hard negative (kelas `other_corruption`/abaikan).
- Mapping FINAL 2026-09-03 (dipakai prototipe + gabung train): pothole->4, crack->1 (kasar: crack tak dipecah — catat sebagai keterbatasan), manhole->3 (other_corruption).

## Urutan dataset final (revisi 2026-09-03)
1. Prototipe: Roma 195 MB (cepat, murah kuota)
2. Train utama: RDD2022 subset 8k (India dkk) + Roma 2k-remap ≈ 10k
3. Test OOD: BPID Bandung 161 foto (jangan dilatih) + foto lokal
