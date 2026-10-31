# JalanPantau via Cloudflare Tunnel (jalur darurat / hari-H)

> **Status jalur cloud:** pendaftaran Oracle gagal di verifikasi kartu
> (kartu virtual), aktivasi Azure for Students kena blokir validasi
> otomatis. Keduanya diparkir dulu. Jalur ini adalah rencana yang
> **jalan hari ini juga tanpa pendaftaran apa pun**: aplikasi tetap
> berjalan di desktop kamu (GPU, model `.pt`, 40+ FPS — performa
> terbaik dari semua opsi), Cloudflare hanya meneruskan aksesnya ke
> internet lewat HTTPS.

## Sifat jalur ini (jujur)

- **Tanpa akun, tanpa kartu, tanpa biaya.** Quick Tunnel tidak butuh
  login Cloudflare sama sekali.
- **URL acak** (`https://<acak>.trycloudflare.com`) dan **berubah
  setiap tunnel dijalankan ulang**. Untuk presentasi: jalankan pagi
  hari-H, salin URL-nya ke slide/QR saat itu juga.
- **PC harus tetap nyala** dan kedua jendela (aplikasi + tunnel)
  tidak boleh ditutup selama dipakai. Internet rumah jadi jalurnya.
- Ini jembatan sementara, bukan hosting permanen — target akhirnya
  tetap VM cloud (Azure/Oracle) begitu gerbang pendaftarannya lolos.

## Persiapan (sekali saja)

1. Di desktop, perbarui repo: masuk folder `jalan-pantau`, lalu
   `git pull` (pastikan di branch `scope-baru`) supaya versi terbaru
   (slider 0,25, paket deploy) ikut terbawa.
2. Pasang `cloudflared` — pilih salah satu:
   - PowerShell: `winget install --id Cloudflare.cloudflared`
   - Manual: unduh `cloudflared-windows-amd64.exe` dari rilis GitHub
     Cloudflare (cloudflare/cloudflared), ganti nama jadi
     `cloudflared.exe`, taruh di folder yang masuk PATH (mis.
     `C:\Windows` atau folder khusus yang kamu daftarkan ke PATH).
   Cek: buka CMD baru, `cloudflared --version` harus menjawab.
3. **Reset akun admin di database PC ini (SEKALI, wajib).** Aplikasi
   hanya menanam akun admin saat tabel admin kosong
   (`database.init_admin`), dan di PC ini aplikasi sudah pernah
   jalan — jadi admin lama sudah tertanam, kemungkinan besar masih
   bersandi bawaan `jalanpantau2026`. Mengganti `JP_DEMO_PASS` di
   .bat TIDAK mengubah sandi yang sudah tertanam itu. Obatnya:
   dobel-klik **`reset-admin.bat`** di folder ini (menghapus baris
   akun admin saja; data riwayat aman). Pada start berikutnya lewat
   `mulai-tunnel.bat`, admin ditanam ulang memakai sandi dari .bat.
4. Buka `mulai-tunnel.bat` (di folder ini) dengan Notepad, edit dua
   baris di bagian atas:
   - `JP_SECRET_KEY` — isi string acak panjang apa saja (sekali ini,
     seterusnya jangan diganti-ganti supaya sesi login tidak rusak).
   - `JP_DEMO_PASS` — **sandi admin BARU yang kuat.** Ini wajib, bukan
     saran: sandi bawaan aplikasi adalah `jalanpantau2026` dan itu
     tercantum di repo publik. Selama tunnel aktif, siapa pun yang
     memegang URL bisa login admin dengan sandi bawaan itu bila kamu
     tidak menggantinya. Script menolak jalan selama nilai ini belum
     diganti.
   Simpan.

## Menjalankan (setiap kali mau online)

1. Dobel-klik `mulai-tunnel.bat`.
2. Jendela aplikasi terbuka (biarkan), lalu jendela tunnel mencetak
   URL `https://....trycloudflare.com`.
3. Uji dari HP (data seluler, bukan Wi-Fi rumah): buka URL → halaman
   Deteksi tampil → unggah foto uji → deteksi jalan → login admin
   dengan sandi barumu → simpan sesi → cek Riwayat/PDF.
4. Bagikan URL itu ke slide/QR/audiens.

## Mematikan

Tutup jendela tunnel (atau Ctrl-C) dan jendela aplikasi. URL langsung
mati; tidak ada sisa yang terekspos.

## Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| `cloudflared` tidak dikenal | CMD-nya dibuka sebelum install selesai (buka CMD baru), atau exe belum masuk PATH |
| `ModuleNotFoundError: No module named 'flask'` | Python yang terpanggil bukan venv proyek. .bat sekarang memilih `.venv`/`venv` di repo secara otomatis + preflight cek dependensi; bila venv-mu bernama lain/conda, arahkan `PY` di .bat ke python.exe yang benar |
| Script berhenti di peringatan sandi | Memang begitu — `JP_DEMO_PASS` di .bat belum diganti dari placeholder |
| URL dibuka → 502 / tidak tersambung | Aplikasi belum siap (tunggu ±15 dtk lagi) atau jendela aplikasi error — baca pesan di jendela aplikasi |
| Login berputar terus | `JP_HTTPS` di .bat harus `1` untuk akses lewat tunnel HTTPS; jangan diubah ke 0 |
| Tunnel putus di tengah | Internet rumah putus / PC tidur — matikan screen sleep selama presentasi; jalankan ulang .bat (URL baru!) |

## Langkah lanjutan (kapan-kapan, bukan sekarang)

URL tetap bisa didapat lewat **Named Tunnel**: akun Cloudflare gratis
(cukup email, tanpa kartu) + domain `.tech` dari GitHub Student Pack
dipindah nameserver-nya ke Cloudflare, lalu tunnel diikat ke
subdomain tetap (mis. `app.namadomain.tech`). Kerjakan setelah
presentasi, saat tidak ada tekanan deadline.

## Rutinitas menyalakan dari PC mati (named tunnel, alamat tetap)

Semua persiapan satu kali (install cloudflared, reset admin,
tunnel login/create/route dns, config.yml) SUDAH selesai 31 Okt
2026 — **jangan diulang**. Setiap kali PC baru dinyalakan dan
situs mau dipakai, hanya ini:

**Cara satu-klik:** dobel-klik `mulai-domain.bat` di folder ini
(isi dulu JP_SECRET_KEY & JP_DEMO_PASS di bagian atasnya, samakan
dengan .bat quick tunnel). Sisanya otomatis: cek lingkungan →
aplikasi menyala di jendela baru → tunnel `jalanpantau` jalan.

**Cara manual (setara persis):**

1. Nyalakan PC, tunggu desktop siap, pastikan internet jalan.
2. Buka CMD, masuk folder repo:
   `cd "C:\Users\R\Documents\@Semester 5\Proyek akhir matkul AI ML PIK\jalan-pantau"`
3. Di jendela itu, set env lalu nyalakan aplikasi (blok ini
   disalin utuh; nilai env samakan dengan isian .bat-mu):
   ```
   set JP_SECRET_KEY=ISIANMU
   set JP_DEMO_PASS=SANDI_BARUMU
   set JP_HTTPS=1
   .venv\Scripts\python.exe web\app.py
   ```
   Tunggu log preload selesai (model gambar, live, scene
   classifier, inferensi live siap). Jendela JANGAN ditutup.
4. Buka CMD **baru** (folder bebas), jalanin tunnel:
   `cloudflared tunnel run jalanpantau`
   Jendela ini juga JANGAN ditutup.
5. Buka `https://app.rachmatx.me` — situs online. Untuk sesi
   panjang (presentasi), matikan sleep PC lebih dulu.

Mematikan: Ctrl+C di jendela tunnel, lalu Ctrl+C di jendela
aplikasi — atau matikan PC sekalian; tidak ada yang rusak,
data riwayat tersimpan di SQLite lokal.

## Mode domain sendiri (Named Tunnel) — langkah penuh Windows

Quick Tunnel memang TIDAK bisa memakai domain sendiri; URL acak
adalah harga dari "tanpa akun". Named Tunnel bisa, dari PC yang
sama, tanpa biaya dan tanpa kartu. Waktu aktif pengerjaannya
±15–30 menit; satu-satunya bagian yang tidak bisa dijanjikan
waktunya adalah propagasi nameserver (menit s.d. beberapa jam).

1. **Akun + daftarkan domain di Cloudflare.** Daftar di
   cloudflare.com (email saja) → **Add a site** → masukkan domain
   `.tech` kamu → plan **Free** → Cloudflare memberi DUA nameserver.
   Catat keduanya persis.
2. **Pindah nameserver di Namecheap.** Namecheap → Domain List →
   Manage (domainmu) → Nameservers → **Custom DNS** → isi dua
   nameserver Cloudflare → simpan. Balik ke dashboard Cloudflare
   dan tunggu status domain jadi **Active** (ada email konfirmasi).
   Selama belum Active, langkah berikutnya belum bisa jalan.
3. **Ikat cloudflared ke akunmu** (CMD biasa, bukan PowerShell
   juga boleh):

   ```
   cloudflared tunnel login
   ```

   Browser terbuka → pilih domainmu → **Authorize**. Berkas
   `cert.pem` tersimpan di `%USERPROFILE%\.cloudflared\`.
4. **Buat tunnel-nya:**

   ```
   cloudflared tunnel create jalanpantau
   ```

   Catat UUID yang dicetak + berkas `<UUID>.json` yang dibuat di
   folder `.cloudflared` yang sama.
5. **Arahkan subdomain ke tunnel:**

   ```
   cloudflared tunnel route dns jalanpantau app
   ```

   Ini membuat `app.domainmu.tech`. (Ganti `app` bila mau nama
   subdomain lain.)
6. **Tulis config.** Salin `config-contoh.yml` dari folder ini ke
   `%USERPROFILE%\.cloudflared\config.yml`, lalu isi UUID, path
   credentials (ingat: user Windows-mu, mis. `C:\Users\R\...`),
   dan hostname dari langkahmu.
7. **Jalankan.** Matikan quick tunnel dulu (Ctrl+C di jendelanya),
   aplikasi biarkan tetap jalan, lalu:

   ```
   cloudflared tunnel run jalanpantau
   ```

8. **Uji** `https://app.domainmu.tech` dari HP (data seluler):
   halaman, deteksi, login, peta — sama seperti uji quick tunnel.

Bila mau tunnel-nya menyala otomatis sebagai service Windows:
jalankan `cloudflared service install` dari CMD **Run as
administrator** (sekali saja); aplikasinya tetap dinyalakan lewat
`mulai-tunnel.bat` tanpa bagian tunnel, atau jadwalkan .bat itu di
Task Scheduler. Untuk masa presentasi, menjalankan manual seperti
langkah 7 sudah cukup dan lebih mudah diawasi.
