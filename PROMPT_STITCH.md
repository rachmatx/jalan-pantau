# PROMPT STITCH — copy-paste seluruh isi ke Google Stitch (satu halaman per sesi)

> Bahasa UI: **Indonesia**. Gaya: aplikasi civic-tech yang bersih dan profesional
> (alat kerja petugas, bukan landing marketing). Tema terang, kontras teks ≥ 4,5,
> ikon SVG, tanpa emoji. Mobile + desktop responsif. **Dilarang keras**: teks
> lorem, testimoni, paket harga, atau angka buatan — hanya konten di bawah.

## Konteks aplikasi

**JalanPantau** — web app Tugas Akhir. Alur: foto jalan difoto → AI YOLOv11n
mendeteksi 5 kerusakan (retak memanjang, retak melintang, retak kulit buaya,
kerusakan lain, lubang) → tiap temuan diberi severity Ringan/Sedang/Berat +
estimasi biaya → laporan PDF → tersimpan di riwayat → terpetakan GPS.
Navigasi: Deteksi, Peta, Riwayat, Tentang. Angka resmi yang boleh tampil:
mAP validasi 0,59 · mAP test 0,47 · OOD Bandung 0,55 · bobot model 5,2 MB.

---

## LAYAR 1 — Deteksi (layar utama, paling penting)

Workbench 2 kolom (desktop; HP menumpuk vertikal):
- **Kiri: viewer foto besar** dengan toolbar zoom melayang (−/+/1:1/Pas/Layar-penuh
  + indikator %) — untuk memeriksa foto hasil anotasi AI (kotak + label tiap temuan).
- **Kanan: panel kontrol** berisi: upload foto (JPG/PNG), slider confidence
  (0,05–0,8), checkbox "foto malam", kolom lokasi + lintang + bujur (terisi otomatis),
  tombol primer "Deteksi".
- **Bawah (full-width): panel hasil** — baris judul + tombol "Unduh PDF" dan
  "Simpan ke riwayat"; 3 kartu KPI (Jumlah temuan, Prioritas berat, Estimasi total
  biaya Rp); tabel temuan (No, Kelas, Ukuran, Severity badge warna, Estimasi Rp).
- Tab "Gambar | Live" di atas workbench. Tab Live berisi kontrol sumber
  (webcam / kamera HP / file video), kartu KPI kecil (FPS, Titik unik, Deteksi,
  Frame), tombol Mulai/Berhenti.
- State yang didesain: sebelum upload (placeholder ramah), loading "Mendeteksi…",
  hasil ada, hasil kosong ("tidak terdeteksi, turunkan confidence…"), error.

## LAYAR 2 — Peta

Peta besar (Leaflet) default Bandung, panel filter severity
(Ringan/Sedang/Berat + penghitung titik) di atasnya, marker dot berwarna per
severity, popup berisi lokasi + severity + jumlah temuan + total + link foto.
Saat data kosong: peta tetap tampil + kartu pesan kecil melayang di atas peta
("Belum ada titik… isi koordinat saat menyimpan", tombol Tutup). Peta tidak boleh
tertutup navigasi saat scroll.

## LAYAR 3 — Riwayat

Bar filter (Dari tanggal, Sampai tanggal, Severity, pencarian, tombol Tampilkan),
tabel (Waktu, Sumber, Lokasi, Severity, Temuan, Total Rp). Klik waktu → **modal
detail**: judul, foto bukti, tabel temuan, tombol Unduh PDF / Hapus (konfirmasi) /
Tutup / X. State kosong yang ramah + mengarahkan ke halaman Deteksi.

## LAYAR 4 — Tentang

 Blok alur 3 langkah (Deteksi → Ukur → Laporkan), blok metrik model (4 kartu angka
resmi di atas), daftar batasan yang jujur (kamera mono tak ukur kedalaman; siang
hari saja; harga = estimasi bukan RAB; wajib kalibrasi kamera), tabel harga acuan
(Severity, Bahan, Harga Rp, Satuan).

---

Setelah 4 layar jadi: samakan radius, spacing, dan gaya tombol di semua layar,
lalu export HTML/CSS per layar.
