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
