# Audit UX — JalanPantau

- **Tanggal**: 2026-10-26
- **Objek**: aplikasi web JalanPantau (Flask + Jinja + vanilla JS)
- **Halaman diaudit**: `/`, `/peta`, `/riwayat`, `/segmen`, `/kalibrasi`, `/tentang`, `/login`, `/laporan/preview`
- **Mode**: walkthrough langsung via browser (desktop 1440×900 dan mobile 390×~844), plus pemindaian axe-core WCAG A/AA
- **Kerangka**: Nielsen 10 + responsive + performance

## Ringkasan eksekutif

Aplikasi sudah **fungsional, konsisten secara visual, dan bersih secara aksesibilitas** (axe-core: 0 violation di `/`, `/peta`, `/riwayat`). Masalah utamanya bukan tampilan rusak, melainkan **umpan balik alur, kejelasan aksi simpan/lokasi, dan keterbacaan di layar sempit**.

Temuan terbesar:

1. Setelah deteksi selesai, hasil muncul jauh di bawah tanpa auto-scroll atau toast; pada kegagalan, overlay "Menganalisis…" justru tertinggal.
2. Aksi simpan membutuhkan login, tetapi gerbang itu baru muncul di akhir alur — operator bisa menyelesaikan seluruh deteksi sebelum tahu ia butuh akun admin.
3. Tabel Riwayat/Segmen tidak bisa dipakai di 390 px: kolom aksi berada di luar layar tanpa petunjuk geser.
4. Beberapa label menyesatkan: "TINGKAT TERPARAH" menampilkan "Berat (0)" walau semua temuan Sedang; "Unduh Log" mengunduh PDF.
5. Hasil deteksi hanya bertahan 10 detik, padahal penyimpanannya sekarang ringan (token gambar).

### Sebaran temuan

| Severity | Jumlah |
|---|---:|
| Blocker | 0 |
| Major | 12 |
| Minor | 11 |
| **Total** | **23** |

| Dimensi | Temuan |
|---|---:|
| visibility | 3 |
| real-world-match | 5 |
| user-control | 3 |
| consistency | 2 |
| error-prevention | 2 |
| recognition | 1 |
| flexibility | 1 |
| aesthetic | 1 |
| error-recovery | 1 |
| help-docs | 1 |
| responsive | 3 |
| performance | 0 |

### Yang sudah bagus (jangan dirusak)

- Konfirmasi hapus riwayat memakai modal kustom, bukan `confirm()` bawaan.
- Simpan riwayat idempoten (`client_ref`) dan punya deteksi duplikat koordinat 10 menit.
- Empty state peta dan peringatan "tidak ada temuan" jujur, tidak mengklaim jalan aman.
- Tabel bisa difokus keyboard (`tabindex="0"`, `role="region"`), dialog memakai `<dialog>` native.
- Kontras dan struktur heading lolos axe; tidak ada emoji sebagai ikon.
- Live preview tetap halus karena arsitektur capture/infer/render terpisah.

---

## Peluang perbaikan (prioritas)

### 1. Hasil deteksi & live langsung terlihat, dan tidak hilang — **tinggi**

**Menjawab**: audit-1, audit-2, audit-3, audit-9, audit-19

**Alasan**: ini titik putus alur utama. Pengguna menyelesaikan aksi paling mahal (inferensi) lalu tidak tahu hasilnya sudah siap; bila gagal, layar tetap terlihat "Menganalisis…". Hasil juga lenyap setelah 10 detik sehingga koreksi operator hilang saat pindah halaman.

**Arah perbaikan**:
- Saat selesai: scroll/highlight ke `#hasil`, tampilkan toast "N temuan", dan ringkas status di dekat hasil.
- Saat gagal: hentikan spinner, kembalikan placeholder viewer, tampilkan error inline + tombol "Coba lagi".
- Live: saat video selesai, buka dialog tabel temuan atau arahkan ke panel "Simpan Sesi" dengan status "N titik siap disimpan".
- Perpanjang masa pemulihan hasil (sessionStorage atau 24 jam) karena payload sudah berupa token, bukan base64.

**Layar**: Deteksi (Gambar & Live).

---

### 2. Tabel dan aksi bisa dipakai di layar sempit — **tinggi**

**Menjawab**: audit-21, audit-23

**Alasan**: di 390 px, tabel Riwayat memiliki lebar isi 783 px di dalam area 366 px. Kolom Severity/Temuan/Segmen/Aksi berada di luar layar, dan tidak ada petunjuk bahwa tabel bisa digeser. Tombol aksi baris juga hanya sekitar 26 px.

**Arah perbaikan**:
- Ubah tabel Riwayat/Segmen menjadi kartu bertumpuk di bawah 640 px, atau kunci kolom aksi di kanan.
- Tambahkan petunjuk "geser untuk melihat kolom lain" + bayangan tepi saat masih ada kolom tersembunyi.
- Naikkan target sentuh aksi baris ke minimal 44 px.
- Panel Live di layar pendek: buat tombol Mulai/Simpan lengket di bawah atau ringkas parameter ke accordion.

**Layar**: Riwayat, Segmen, hasil Deteksi, panel Live.

---

### 3. Lokasi & simpan tanpa kejutan — **tinggi**

**Menjawab**: audit-8, audit-14, audit-15, audit-16

**Alasan**: GPS diminta otomatis saat halaman dibuka, sebelum pengguna memilih foto. Bila ditolak, riwayat tetap tersimpan tanpa titik peta dan peringatan baru muncul setelah record dibuat. Placeholder "-6,9"/"107,6" juga mudah disangka nilai terisi, dan koordinat parsial diterima.

**Arah perbaikan**:
- Tampilkan status eksplisit: "Titik peta: belum ada / dari GPS / dari EXIF".
- Jika koordinat kosong, minta konfirmasi "Simpan tanpa titik peta?" sebelum menulis riwayat.
- Validasi pasangan lintang+bujur secara inline; jangan biarkan hanya satu terisi.
- Pindahkan permintaan izin GPS ke momen bermakna (tombol "Ambil GPS" atau saat simpan), bukan saat page load.

**Layar**: Deteksi, Live, Riwayat, Peta.

---

### 4. Istilah & KPI yang tidak menyesatkan — **tinggi (quick wins)**

**Menjawab**: audit-4, audit-5, audit-6, audit-12, audit-20

**Alasan**: beberapa label salah arti atau mencampur bahasa, dan biaya perbaikannya kecil dibanding dampaknya.

**Arah perbaikan**:
- `TINGKAT TERPARAH`: tampilkan badge level sebenarnya ("Sedang"), bukan `Berat (0)`.
- `Unduh Log` pada Live: ganti menjadi `Unduh Laporan PDF` (atau benar-benar sediakan log).
- Hapus subteks "· kelas ukuran" dari kolom severity; jelaskan di tooltip bila perlu.
- Seragamkan: "Login" → "Masuk"; "Simpan Sesi" vs "Simpan ke Riwayat" → satu istilah untuk satu konsep.
- Tambahkan definisi singkat severity/indeks prioritas di dekat hasil, dengan tautan ke Tentang.

**Layar**: Deteksi, Live, Login, Tentang.

---

### 5. Peta mobile: filter tidak menutupi peta — **sedang**

**Menjawab**: audit-7, audit-22

**Alasan**: di 390 px kartu filter memakan sekitar sepertiga atas peta dan tidak bisa diciutkan. Header daftar prioritas juga mengatakan "URUT TERTINGGI", tetapi nilai di kanan baris adalah nama segmen atau "-", bukan peringkat/skor.

**Arah perbaikan**:
- Ringkas filter menjadi chip "Filter (2)" yang membuka sheet; peta tetap jadi fokus.
- Tampilkan peringkat/skor di baris prioritas, pindahkan nama segmen ke subteks.

**Layar**: Peta.

---

### 6. Panel Live lebih ringkas & mengingat pengaturan — **sedang**

**Menjawab**: audit-17, audit-18

**Alasan**: panel Live memuat tips FPS, benchmark F1, dan tiga paragraf troubleshooting kamera sebelum kontrol utama. Pengaturan (sumber, conf, performa, mode malam, nama ruas) juga hilang setiap reload.

**Arah perbaikan**:
- Pindahkan tips/benchmark ke accordion "Bantuan performa" atau halaman Tentang.
- Simpan pengaturan terakhir di localStorage dengan tombol "Reset ke bawaan".
- Pertahankan tombol Mulai sebagai aksi paling menonjol.

**Layar**: Deteksi tab Live.

---

## Temuan lengkap

### visibility — sistem status terlihat

#### audit-1 · major — Hasil deteksi muncul di luar area pandang
- **Bukti**: `web/templates/deteksi.html:33` (status di bar atas) dan `:144` (`#hasil`); `web/static/js/deteksi.js` tidak memanggil `scrollIntoView`/toast saat sukses. Saat diuji, `#hasil` berada di posisi ~812 px pada viewport 900 px, sementara pengguna berada di ~222 px.
- **Dampak**: pengguna mengira deteksi belum selesai atau tidak menemukan apa pun.
- **Saran**: auto-scroll + highlight hasil, toast ringkasan, dan status hasil di dekat tombol aksi.
- **Effort**: medium.

#### audit-2 · major — Selesai live tidak memberi tahu bahwa hasil siap disimpan
- **Bukti**: `web/static/js/live.js:180` hanya mengubah status menjadi "Video selesai diputar."; snapshot diambil diam-diam di `live.js:263-294`; panel `#hasil-live` + "Simpan Sesi" ada di `web/templates/deteksi.html:379-394`, jauh di bawah.
- **Dampak**: sesi live berakhir tanpa tindak lanjut; pengguna menutup halaman dan kehilangan hasil.
- **Saran**: saat selesai, tampilkan "N titik siap disimpan", buka dialog tabel, dan arahkan fokus ke tombol Simpan Sesi.
- **Effort**: medium.

#### audit-3 · minor — Umpan balik PDF hanya di status bar atas
- **Bukti**: `web/static/js/deteksi.js:560-585` menulis "PDF terunduh." ke `#status`; `web/static/js/live.js:420-441` tidak memberi konfirmasi sukses sama sekali.
- **Dampak**: di mobile status tidak terlihat; pengguna tidak yakin unduhan berhasil.
- **Saran**: toast sukses untuk PDF gambar & live, plus status proses saat membuat laporan.
- **Effort**: quick-win.

---

### real-world-match — bahasa dan model mental pengguna

#### audit-4 · major — "TINGKAT TERPARAH" menampilkan jumlah, bukan tingkat
- **Bukti**: `web/static/js/deteksi.js:211` dan `:648` mengisi `#berat-nilai` dengan `` `Berat (${nBerat})` ``. Saat diuji dengan 3 temuan yang semuanya "Sedang", kartu menampilkan "Berat (0)".
- **Dampak**: informasi keselamatan paling penting justru bertentangan dengan data.
- **Saran**: tampilkan badge severity terburuk yang benar; jumlah Berat menjadi subteks opsional.
- **Effort**: quick-win.

#### audit-5 · major — "Unduh Log" mengunduh PDF
- **Bukti**: label `web/templates/deteksi.html:386` "Unduh Log"; handler `web/static/js/live.js:420-441` memanggil `/api/laporan` dan mengunduh `laporan_jalan_live.pdf`.
- **Dampak**: pengguna mengharapkan log teknis, mendapat berita acara; kepercayaan pada label menurun.
- **Saran**: ganti label menjadi "Unduh Laporan PDF", atau implementasikan ekspor log terpisah.
- **Effort**: quick-win.

#### audit-6 · minor — Jargon "kelas ukuran" di kolom severity
- **Bukti**: `web/static/js/deteksi.js:41` menambahkan `· ${r.makna}`; untuk pothole server mengirim `"kelas ukuran"` (`app/severity.py:34`, `:110`).
- **Dampak**: pengguna melihat "Sedang · kelas ukuran" dan harus menebak artinya.
- **Saran**: sembunyikan dari tabel; jelaskan lewat tooltip atau halaman bantuan.
- **Effort**: quick-win.

#### audit-7 · minor — Header daftar prioritas tidak cocok dengan isi baris
- **Bukti**: `web/templates/peta.html:93` "URUT TERTINGGI"; `web/static/js/peta.js:213` menaruh `segmen_nama || "-"` di sel kanan.
- **Dampak**: pengguna mengira sel kanan adalah skor/peringkat, padahal nama segmen; baris "-" terlihat seperti data hilang.
- **Saran**: tampilkan peringkat/skor di sel kanan, nama segmen di subteks, atau ubah header.
- **Effort**: quick-win.

#### audit-8 · minor — Placeholder koordinat tampak seperti nilai
- **Bukti**: `web/templates/deteksi.html:113-114` dan `:357-358` memakai placeholder `-6,9` / `107,6`.
- **Dampak**: pengguna mengira titik sudah terisi (terutama setelah GPS ditolak), lalu menyimpan tanpa titik.
- **Saran**: placeholder contoh yang jelas ("mis. -6,917500") + status "belum ada titik peta".
- **Effort**: quick-win.

---

### user-control — kendali pengguna

#### audit-9 · major — Hasil deteksi hilang setelah 10 detik
- **Bukti**: `web/static/js/deteksi.js:619-632` menghapus hasil bila `jp_deteksi_time` lebih tua dari 10.000 ms; komentar lama menyebut alasan base64, tetapi payload kini hanya token. Restore juga mereset `verHapus`/`verSev` (`deteksi.js:655-670`).
- **Dampak**: pengguna tidak bisa membandingkan hasil dengan peta/riwayat lalu kembali; koreksi yang belum disimpan lenyap.
- **Saran**: gunakan sessionStorage atau TTL 24 jam; tampilkan "hasil terakhir" + waktu.
- **Effort**: medium.

#### audit-10 · minor — Inferensi gambar tidak bisa dibatalkan
- **Bukti**: `web/static/js/deteksi.js:382-413` menonaktifkan tombol dan menunggu `fetch` tanpa `AbortController`; hanya mode teliti yang diberi estimasi waktu.
- **Dampak**: pada CPU lambat, pengguna terkunci menunggu tanpa jalan keluar.
- **Saran**: tombol "Batalkan" + AbortController, atau izinkan berpindah tab sambil proses berjalan.
- **Effort**: medium.

#### audit-11 · minor — Menu mobile tidak punya jalan tutup yang wajar
- **Bukti**: `web/templates/base.html:76-85` hanya mengganti `hidden`; tidak ada handler Esc/tap luar. `t.classList.toggle("terbuka")` tidak punya aturan CSS, jadi ikon tidak berubah menjadi X.
- **Dampak**: pengguna harus menebak bahwa hamburger harus ditekan lagi; keyboard user tidak bisa menutup dengan Esc.
- **Saran**: tutup saat Esc/tap luar, ubah ikon ke X, dan kembalikan fokus ke tombol.
- **Effort**: quick-win.

---

### consistency — konsistensi

#### audit-12 · minor — Satu konsep, beberapa label
- **Bukti**: "Simpan ke Riwayat" (`web/templates/deteksi.html:158`) vs "Simpan Sesi" (`:394`); "Unduh Laporan PDF" (`:154`) vs "Unduh PDF" (`web/templates/segmen.html:105`) vs "Unduh Log" (`deteksi.html:386`); "Login" (`web/templates/login.html:64`) vs tombol "Masuk" (`:80`).
- **Dampak**: pengguna ragu apakah aksi yang berbeda benar-benar berbeda.
- **Saran**: tetapkan glossary aksi dan gunakan satu istilah per konsep.
- **Effort**: quick-win.

#### audit-13 · minor — Upload di Kalibrasi memakai kontrol native
- **Bukti**: `web/templates/kalibrasi.html:45` memakai `<input type="file">` native, sehingga muncul teks Inggris "Choose File / No file chosen"; Deteksi memakai dropzone kustom (`web/static/css/civic.css:383`).
- **Dampak**: halaman terasa berbeda dan kurang dapat diprediksi.
- **Saran**: pakai komponen dropzone yang sama.
- **Effort**: quick-win.

---

### error-prevention — mencegah kesalahan

#### audit-14 · major — Simpan tanpa titik peta terjadi tanpa konfirmasi
- **Bukti**: `web/static/js/gps.js:22-42` meminta GPS saat page load; `web/static/js/deteksi.js:545-557` dan `live.js:405-415` tetap menyimpan lalu memberi peringatan setelah record dibuat.
- **Dampak**: riwayat tanpa koordinat masuk tanpa persetujuan eksplisit; peta jadi tidak lengkap.
- **Saran**: konfirmasi "Simpan tanpa titik peta?" sebelum POST; tawarkan "Ambil GPS" di dialog yang sama.
- **Effort**: medium.

#### audit-15 · minor — Koordinat parsial diterima
- **Bukti**: `web/static/js/deteksi.js:474-483` membaca lat/lon terpisah; `web/app.py:920-932` memvalidasi masing-masing dan mengembalikan `None` untuk yang kosong.
- **Dampak**: hanya lintang terisi → record tersimpan tetapi tidak muncul di peta; pesan setelah simpan membingungkan.
- **Saran**: validasi pasangan; jika salah satu kosong, kosongkan keduanya atau minta lengkapi.
- **Effort**: quick-win.

---

### recognition — mengenali, bukan mengingat

#### audit-16 · major — Syarat login baru terlihat di akhir alur
- **Bukti**: `web/app.py:935-936` menaruh `@login_wajib` pada `POST /api/riwayat`; UI publik menampilkan "Simpan ke Riwayat"/"Simpan Sesi" tanpa penanda. `tests/test_auth_deferred.py:41-45` menegaskan 401 tanpa login, sementara `docs/User-Flow.md:85` masih menyebut operator publik bisa "simpan riwayat".
- **Dampak**: operator menyelesaikan deteksi lalu tertahan di langkah terakhir; ekspektasi dari dokumentasi tidak cocok dengan aplikasi.
- **Saran**: tampilkan sejak awal bahwa simpan butuh admin (badge/link Masuk), atau buka simpan untuk publik; perbarui dokumentasi.
- **Effort**: medium.

---

### flexibility — efisiensi penggunaan

#### audit-17 · minor — Pengaturan live tidak diingat
- **Bukti**: `web/static/js/live.js` tidak memakai `localStorage`/`sessionStorage`; sumber, conf, interval, performa, mode malam, dan nama ruas kembali ke default setiap reload.
- **Dampak**: pengulangan inspeksi di ruas yang sama harus mengisi ulang.
- **Saran**: simpan setelan terakhir + tombol reset.
- **Effort**: quick-win.

---

### aesthetic — kepadatan dan hierarki

#### audit-18 · major — Informasi teknis memenuhi panel live
- **Bukti**: `web/templates/deteksi.html:205-220` (tiga langkah troubleshooting kamera), `:330-335` (benchmark F1 @640 vs @960), dan `:193-194` (FPS tampil vs inferensi) berada di alur utama sebelum tombol Mulai.
- **Dampak**: aksi utama tenggelam; pengguna baru harus membaca istilah teknis sebelum bisa mencoba.
- **Saran**: pindahkan ke disclosure "Bantuan performa" atau Tentang; sisakan satu kalimat ringkas.
- **Effort**: medium.

---

### error-recovery — pulih dari kesalahan

#### audit-19 · major — Deteksi gagal meninggalkan layar seolah masih memproses
- **Bukti**: `web/static/js/deteksi.js:391` memasang overlay "Menganalisis…"; blok `catch` di `:455-460` hanya mengubah status di atas dan tidak mengembalikan `slot`; error tidak memunculkan toast dan tidak ada tombol coba lagi.
- **Dampak**: pengguna menunggu selamanya atau mengira aplikasi hang; penyebab gagal tidak terlihat di area aksi.
- **Saran**: di `catch`, hentikan overlay, kembalikan placeholder, tampilkan error inline + "Coba lagi", dan toast.
- **Effort**: medium.

---

### help-docs — bantuan di konteks

#### audit-20 · minor — Severity & indeks prioritas tidak dijelaskan di tempat
- **Bukti**: hasil menampilkan badge Ringan/Sedang/Berat (`web/static/js/deteksi.js` `badge()`), sedangkan definisi baru ada di Tentang (`web/templates/tentang.html:26`) tanpa tautan dari hasil.
- **Dampak**: pengguna tidak tahu dasar penilaian dan arti "indeks prioritas" saat mengambil keputusan.
- **Saran**: tambahkan info-tooltip singkat di dekat tabel + tautan "Pelajari penilaian".
- **Effort**: quick-win.

---

### responsive — layar sempit

#### audit-21 · major — Tabel lebar tidak terpakai di 390 px
- **Bukti**: `web/templates/riwayat.html:58`, `web/templates/segmen.html:67-86`; `web/static/css/civic.css:574` hanya memberi `overflow-x:auto`. Pada audit, `#daftar` memiliki `clientWidth` 366 px dan `scrollWidth` 783 px; tombol aksi baris ~26 px (`civic.css:1340-1351`).
- **Dampak**: detail/PDF/hapus tidak terjangkau tanpa gestur geser yang tidak diketahui.
- **Saran**: kartu mobile atau kolom aksi lengket; petunjuk geser; target sentuh ≥44 px.
- **Effort**: major-rework.

#### audit-22 · major — Kartu filter peta menutupi peta di mobile
- **Bukti**: `web/static/css/civic.css:1369-1374` membuat kartu filter selebar layar di atas peta; tidak ada kontrol ciut. Peringatan GPS juga ditambahkan ke kartu yang sama (`web/static/js/peta.js:110-124`).
- **Dampak**: area peta yang terlihat menyusut; pengguna harus menutup/menggeser untuk melihat titik.
- **Saran**: chip ringkasan filter yang membuka sheet, atau kartu bisa diciutkan.
- **Effort**: medium.

#### audit-23 · major — Aksi utama Live di bawah fold
- **Bukti**: `web/templates/deteksi.html:361-394` menempatkan "Mulai Stream Live", "Hentikan", "Putar Demo", dan panel hasil setelah belasan field parameter; pada viewport 720 px dan 390 px tombol utama tidak terlihat tanpa scroll.
- **Dampak**: pengguna demo tidak menemukan cara memulai; setelah sesi selesai, tombol simpan juga jauh.
- **Saran**: action bar lengket (Mulai/Demo/Simpan) atau accordion parameter.
- **Effort**: medium.

---

### performance — persepsi kinerja

Tidak ada temuan yang layak diperbaiki di dimensi ini pada audit kali ini:
- Preview live tetap halus karena decoupling 3-thread; FPS tampil tidak turun saat inferensi lambat.
- Tidak ada layout shift besar yang teramati pada pemuatan halaman.
- Catatan: FPS inferensi live memang jauh lebih rendah daripada FPS tampil; ini batasan model/CPU, bukan regresi UI. Jelaskan di UI agar tidak disalahartikan (lihat audit-18).

---

## Metode & batasan

- Walkthrough langsung di browser dengan sesi publik dan sesi admin.
- Viewport: desktop 1440×900 CSS dan mobile 390×844 CSS (devicePixelRatio 0.8).
- Pemindaian axe-core (WCAG A/AA) pada `/`, `/peta`, `/riwayat`: 0 violation.
- Interaksi diuji: unggah gambar, deteksi, koreksi, simpan, PDF, live demo, snapshot, simpan live, filter riwayat, detail modal, hapus, login salah/benar, peta popup, empty state.
- Belum diuji: kamera fisik/IP-cam nyata (hanya demo video), pembacaan layar nyata, dan pengguna non-teknis.
- Audit ini berbasis expert review; temuan bertingkat sedang sebaiknya diverifikasi dengan 5–10 pengguna nyata sebelum refactor besar.

---

## Urutan kerja yang disarankan

1. **Quick wins istilah & KPI** (peluang 4): murah, langsung menghilangkan kesan "aplikasi salah".
2. **Umpan balik & pemulihan hasil** (peluang 1): dampak terbesar ke alur utama.
3. **Lokasi & simpan** (peluang 3): mencegah data riwayat tanpa titik dan kejutan login.
4. **Tabel mobile** (peluang 2): perbaikan struktur, butuh waktu lebih lama.
5. **Peta mobile & panel live** (peluang 5–6): polish setelah alur inti beres.
