# Cakupan Mockup Stitch vs Implementasi

Sumber mockup: `stitch_aplikasi_deteksi_kerusakan_jalan/` (19 folder).
Status: ✅ sesuai · ⚠️ sebagian/disederhanakan · ❌ belum.

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
| `layar_disposisi_kirim_laporan_ke_instansi_pemerintahan` | `disposisi_kirim.html` | ✅ |
| `layar_disposisi_detail_pelacakan_log_penanganan_lapangan` | `disposisi_detail.html` | ✅ |
| `jalanpantau_mode_mobile_petugas_lapangan` | `mobile.html` | ⚠️ mockup (banner DEMO; telemetri simulasi) |
| `dashboard_eksekutif_verifikasi_kedinasan_..._dsdabm` | `dashboard/verifikasi.html` | ✅ (baru) |
| `dashboard_eksekutif_dialog_penerbitan_spk_elektronik_alokasi_material` | `dashboard/verifikasi.html` (terbitkan SPK) | ⚠️ sebagian (dialog alokasi material belum) |
| `dashboard_eksekutif_analitik_heatmap_indeks_kemantapan_jalan_ikj` | `dashboard/analitik.html` | ⚠️ sebagian (peta kerapatan internal; **bukan IKJ resmi**) |
| `dashboard_eksekutif_manajemen_armada_trc_monitoring_lapangan` | — | ❌ belum |

## Catatan penyimpangan yang disengaja
- **Tanpa data fiktif.** Layar `dashboard/verifikasi.html` mengikat data **nyata**
  dari `/api/disposisi`, bukan nomor tiket/angka contoh dari mockup
  (mis. `#DISP-BM-2025-084`, `88.42%`, `Node: bdg-dsdabm-prd-01`).
- **Tanpa IKJ.** Mockup menampilkan "Indeks Kemantapan Jalan (IKJ) 88.42%", tetapi
  sistem ini belum menghitung IKJ → sengaja tidak ditampilkan (jangan diklaim).
- **Tanpa telemetri palsu.** Latensi/SHA-256/webhook dari mockup tidak dipakai.

## Sisa pekerjaan (bila ingin melengkapi)
- Heatmap IKJ (butuh definisi & data IKJ).
- Manajemen armada TRC (butuh data armada).
- Dialog alokasi material SPK (butuh master material/AHSP).
