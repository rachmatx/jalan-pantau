# Cakupan Mockup Stitch vs Implementasi

Sumber mockup: `stitch_aplikasi_deteksi_kerusakan_jalan/` (19 folder).
Status: ✅ sesuai · ⚠️ sebagian/disederhanakan · ❌ belum/dihapus.

> **Catatan scope (Okt 2026):** aplikasi dipangkas ke satu peran (**admin**).
> Layar disposisi/SPK/kontraktor/portal dinas dan mode mobile sudah **dihapus**
> dari kode; entri di bawah ditandai ❌ agar tidak jadi klaim palsu. Scope aktif:
> deteksi → severity → indeks prioritas → peta GIS → riwayat → PDF.

| Layar Stitch | Implementasi | Status |
|---|---|---|
| `civic_precision/` | Design system (`civic.css`) | ✅ |
| `layar_1_deteksi_jalanpantau` | `deteksi.html` (tab Gambar) | ✅ |
| `layar_1_deteksi_live_streaming_jalanpantau` | `deteksi.html` (tab Live) | ✅ |
| `layar_1_deteksi_state_gangguan_kamera_panduan_solusi` | state galat kamera `deteksi.html` | ✅ |
| `layar_1_deteksi_state_hasil_kosong_jalan_mulus` | empty state deteksi | ✅ |
| `layar_2_peta_jalanpantau` | `peta.html` | ✅ |
| `layar_2_viewer_foto_inspeksi_jalanpantau` | modal foto di `peta.js` | ✅ |
| `layar_3_riwayat_jalanpantau` | `riwayat.html` | ✅ |
| `layar_3_riwayat_modal_detail_berita_acara` | modal detail `riwayat.html` | ✅ |
| `layar_4_tentang_jalanpantau` | `tentang.html` | ✅ |
| `layar_pengaturan_kalibrasi_sensor_kamera_ai` | `kalibrasi.html` | ✅ |
| `jalanpantau_pratinjau_berita_acara_laporan_audit_pdf` | `laporan_preview.html` | ✅ |
| `layar_disposisi_kirim_laporan_ke_instansi_pemerintahan` | — | ❌ dihapus (di luar scope) |
| `layar_disposisi_detail_pelacakan_log_penanganan_lapangan` | — | ❌ dihapus (di luar scope) |
| `jalanpantau_mode_mobile_petugas_lapangan` | — | ❌ dihapus (di luar scope) |
| `dashboard_eksekutif_verifikasi_kedinasan_...` (SPK) | — | ❌ dihapus (di luar scope) |
| `dashboard_eksekutif_dialog_penerbitan_spk_...` | — | ❌ dihapus (di luar scope) |
| `dashboard_eksekutif_analitik_heatmap_indeks_kemantapan_jalan_ikj` | — | ❌ dihapus (IKJ tidak dihitung) |
| `dashboard_eksekutif_manajemen_armada_trc_monitoring_lapangan` | — | ❌ belum |

## Catatan penyimpangan yang disengaja
- **Tanpa data fiktif.** Tidak ada nomor tiket/angka contoh dari mockup
  (mis. `#DISP-BM-2025-084`, `88.42%`, `Node: bdg-dsdabm-prd-01`).
- **Tanpa IKJ.** Sistem ini tidak menghitung Indeks Kemantapan Jalan (IKJ) →
  sengaja tidak ditampilkan (jangan diklaim).
- **Tanpa telemetri palsu.** Latensi/SHA-256/webhook dari mockup tidak dipakai.
- **Tanpa biaya rupiah.** Estimasi biaya diganti indeks prioritas 0–100
  (lihat `app/prioritas.py`); ini jawaban atas kritik double-counting.
