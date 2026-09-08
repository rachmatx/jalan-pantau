# Strategi subset 8k + 2k (keputusan 2026-09-03, revisi: RDDC drop)

Alasan: hemat kuota T4 gratis + waktu latih. 5k terstratifikasi jauh lebih baik dari 26k asal-amburadul.

## Komposisi final (revisi 2026-09-03: RDDC tidak tersedia, diganti Roma)
- Train: RDD2022 8.000 (stratified India/MotorBike/Japan) + Roma 2.009 (full, remap 0→4, 1→1, 2→3) = ~10k
- Val: 10–15% dari train (~1,2k), proporsional per sumber
- Test: TIDAK perlu dibatasi (evaluasi murah, tanpa gradien) — pakai full test split RDD2022
  + full BPID Bandung (161) + semua foto lokal. Test besar = grafik generalisasi makin kuat.

## Aturan sampling (wajib ditulis di jurnal)
1. Stratified: pertahankan distribusi kelas asli tiap dataset (jangan random murni —
   kelas pothole/alligator yang minoritas bisa hilang).
2. Minority floor: tiap kelas ≤ pastikan ≥800 gambar di train gabungan; bila kurang, top-up dari sisa.
3. Fixed seed (mis. 42) + simpan daftar file terpilih (`subset_files.txt`) untuk reproduksibilitas.
4. Urutan: remap Roma dulu (0→4, 1→1, 2→3 — crack kasar, catat di keterbatasan) BARU gabung dengan subset RDD.
5. Untuk RDD2022: sampling di dalam subset relevan (India + China_MotorBike + Japan, exclude Norway),
   bukan dari full 38k (supaya subset tidak tercemar salju Norwegia).

## Estimasi T4 (YOLOv11n, imgsz 640, batch 16, ~10k gambar)
- ±625 iterasi/epoch × ±0,4 dtk ≈ 4–5 menit/epoch → 100 epoch ≈ 7–8 jam.
- Muat dalam 1 sesi (limit ~12 jam). Pakai early stopping patience 20 + simpan best.pt.
- Val/test evaluasi hanya hitungan menit.

## Yang ditulis di jurnal
- "Keterbatasan komputasi (GPU T4 gratis), digunakan stratified subset 5k+5k dengan seed 42..."
- Tabel distribusi kelas sebelum vs sesudah sampling (bukti tidak bias).
- Daftar file subset dilampirkan sebagai supplementary / repo.
