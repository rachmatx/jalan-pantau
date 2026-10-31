# Panduan Deploy JalanPantau ke Azure for Students

> **Kenapa Azure:** pendaftaran Oracle Cloud gagal di verifikasi kartu
> (kartu virtual ditolak filter mereka). User memutuskan pivot ke
> **Azure for Students** — kredit **$100 / 12 bulan, TANPA kartu sama
> sekali** (verifikasi via status mahasiswa), dan sudah diklaim lewat
> GitHub Student Developer Pack.

Target akhir: JalanPantau online dari VM Azure, memakai **paket Docker
yang sama persis** dengan paket di `deploy/oracle/` (Dockerfile,
docker-compose, Caddyfile, `.env` — semuanya dipakai apa adanya; nama
folder "oracle" itu historis, isinya netral platform). Yang berbeda
hanya cara membuat VM-nya.

Kenapa paketnya langsung cocok: base image `python:3.11-slim` itu
multi-arch dan semua wheel ARM64 maupun x86_64 di
`requirements-deploy.txt` sudah diaudit + diuji jalan (31 Okt 2026).

## Gambaran biaya (jujur, dari penawaran resmi Azure for Students)

- Azure for Students memberi **kuota gratis 12 bulan: 750 jam/bulan**
  untuk VM ukuran **B1s, B2pts v2 (ARM), dan B2ats v2 (AMD)** — 750 jam
  itu cukup untuk satu VM nyala 24/7 sebulan penuh. Jadi komputasi VM
  di panduan ini **Rp0 dari kuota**, bukan dari kredit.
- Yang tetap memakan kredit $100: **disk OS** (Standard SSD 32 GB,
  sekitar $2–3/bulan) dan biaya kecil lain. Kredit $100 untuk setahun
  itu longgar sekali untuk kebutuhan ini.
- Karena **tidak ada kartu terdaftar**, bila kredit habis layanan
  berhenti — **tidak mungkin ada tagihan kejutan**.
- Kredit bisa dipakai untuk naik kelas VM sementara menjelang
  presentasi (mis. B2ms 8 GB RAM) lalu turun lagi.

## Langkah 1 — Aktivasi Azure for Students

1. Buka halaman **Azure for Students** (`azure.microsoft.com/free/students`)
   atau klaim dari halaman benefit GitHub Student Pack-mu (offer Azure).
2. Masuk dengan akun Microsoft, lalu verifikasi status mahasiswa
   (email kampus `bsi.ac.id` atau verifikasi GitHub Student yang sudah
   kamu punya). **Tidak ada langkah kartu.**
3. Pastikan subscription yang aktif bernama **Azure for Students**
   dengan kredit $100 terlihat di Portal (`portal.azure.com`).

Satu orang hanya boleh punya satu subscription student — jangan buat
dobel.

## Langkah 2 — Buat VM

Portal → **Virtual machines → Create → Azure virtual machine**:

- **Subscription**: Azure for Students
- **Resource group**: buat baru, nama `jalanpantau-rg`
- **Virtual machine name**: `jalanpantau`
- **Region**: `Southeast Asia` (Singapore — latensi terkecil dari sini)
- **Availability options**: No infrastructure redundancy required
- **Security type**: Standard
- **Image**: `Ubuntu Server 24.04 LTS - ARM64` (untuk jalur ARM di bawah)
- **VM architecture**: Arm64
- **Size**: **`Standard_B2pts_v2`** — 2 vCPU / 4 GB RAM (ARM Ampere).
  Ukuran ini yang masuk kuota gratis 750 jam/bulan.
  - **Bila size ini tidak muncul / tidak tersedia di region**:
    ganti arsitektur ke **x64**, image `Ubuntu Server 24.04 LTS - x64`,
    size **`Standard_B2ats_v2`** (2 vCPU / 4 GB, AMD) — juga masuk
    kuota gratis yang sama, dan paket Docker kita jalan tanpa diubah
    sama sekali (sudah teruji di x86_64).
- **Authentication type**: SSH public key
  - **Username**: `azureuser`
  - **SSH public key source**: *Generate new key pair*, nama mis.
    `jalanpantau_key`. Saat diminta, **unduh private key (.pem) dan
    simpan baik-baik** — sama seperti Oracle, ini satu-satunya kunci
    masuk; kehilangan = terkunci.
- **OS disk type**: Standard SSD, 32 GB cukup.
- **Public inbound ports**: Allow selected ports → **SSH (22)** dulu;
  port 80/443 dibuka di Langkah 3.

Create → tunggu deployment selesai → catat **Public IP address** VM.

**Soal RAM 4 GB:** cukup untuk mode foto (jalur utama demo) dan mode
live `.onnx` dasar. Sebagai bantalan, tambahkan swap 2 GB sekali saja
setelah SSH masuk (Langkah 4) — murah dan menghilangkan risiko
kehabisan memori saat model dimuat.

## Langkah 3 — Buka port 80/443 (NSG)

VM → **Networking → Network settings → Create port rule → Inbound
port rule**, tambahkan dua rule:

| Destination port | Protocol | Source | Action |
|---|---|---|---|
| 80 | TCP | Any | Allow |
| 443 | TCP | Any | Allow |

(UDP 443 untuk HTTP/3 opsional.) Port 5000 **jangan** dibuka —
aplikasi hanya untuk Caddy di localhost, sama seperti desain awal.

## Langkah 4 — SSH masuk & pasang Docker

Dari PC kamu (Windows: file `.pem` biasanya perlu dibatasi izinnya —
di PowerShell: `icacls jalanpantau_key.pem /inheritance:r /grant:r "$($env:USERNAME):R"`):

```bash
ssh -i jalanpantau_key.pem azureuser@<IP-PUBLIK>
```

Di dalam VM:

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER

# bantalan RAM 4 GB: swap 2 GB (sekali saja)
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

Keluar (`exit`) lalu SSH lagi agar grup `docker` aktif; cek
`docker run hello-world` harus jalan tanpa `sudo`.

Catatan: image Ubuntu Azure **tidak** punya gotcha iptables bawaan
seperti Oracle — NSG di Langkah 3 itu satu-satunya gerbang, tidak ada
langkah iptables tambahan.

## Langkah 5 — Ambil kode & siapkan konfigurasi

Persis seperti paket awal (folder `deploy/oracle` dipakai apa adanya):

```bash
git clone -b scope-baru https://github.com/rachmatx/jalan-pantau.git
cd jalan-pantau/deploy/oracle
cp .env.example .env
cp .dockerignore ../../.dockerignore
nano .env
```

Isi dua nilai wajib di `.env`:

- `JP_SECRET_KEY` — hasilkan dengan `openssl rand -hex 32`, tempel.
- `JP_DEMO_PASS` — sandi admin yang kuat dan baru. **Jangan
  dikosongkan:** kosong berarti sandi default `jalanpantau2026` yang
  diketahui publik dari repo.

`JP_HTTPS` biarkan `0` selama masih memakai HTTP via IP.

## Langkah 6 — Build & jalankan

```bash
docker compose build      # pertama kali 10–25 menit: unduh torch dsb.
docker compose up -d
docker compose ps         # app harus menuju (healthy)
docker compose logs -f app   # Ctrl-C untuk berhenti mengikuti log
```

## Langkah 7 — Uji dari browser

Buka `http://<IP-PUBLIK>/`:

1. Halaman Deteksi tampil.
2. Unggah satu foto uji dari `test_foto/` → deteksi jalan, hasil
   tampil. Inferensi pertama lebih lambat (model dimuat).
3. Login `admin` + sandi `JP_DEMO_PASS`, simpan sesi, cek Riwayat &
   unduh PDF.
4. Cek Peta.

## Langkah 8 (disarankan) — Domain + HTTPS

Sama seperti rencana awal: klaim domain **.tech gratis 1 tahun** dari
GitHub Student Pack (Namecheap), arahkan A record `@` ke IP publik VM,
aktifkan blok domain di `Caddyfile` (di folder `deploy/oracle`),
set `JP_HTTPS=1` di `.env`, lalu `docker compose up -d` ulang.
Caddy mengurus sertifikat Let's Encrypt otomatis.

Catatan IP: IP publik VM Azure bisa berubah bila VM dibuat ulang;
untuk kestabilan jangka panjang, di halaman Public IP VM ada opsi
mengubah SKU/assignment menjadi **Static** (biaya kecil dari kredit).
Untuk masa presentasi, IP dinamis bawaan pun cukup selama VM tidak
dibuat ulang.

## Operasional & biaya sehari-hari

```bash
cd ~/jalan-pantau/deploy/oracle

docker compose logs -f app        # pantau log
docker compose restart app        # restart aplikasi saja
docker compose down               # matikan container (data volume aman)
docker compose up -d              # nyalakan lagi
```

**Update kode** (setelah push ke `scope-baru`):

```bash
cd ~/jalan-pantau && git pull
cd deploy/oracle && docker compose build && docker compose up -d
```

**Pantau kredit**: Portal → Cost Management — pastikan pemakaian
bulanan hanya disk + sisa kecil; VM B2pts_v2/B2ats_v2 harus tertagih
$0 selama kuota 750 jam belum terlampaui (jangan menjalankan dua VM
berukuran sama sekaligus — kuota per ukuran dipakai bersama).

**Backup database riwayat**:

```bash
docker run --rm -v <nama-volume-dari-docker-volume-ls | grep jp-instance>:/data -v "$PWD":/backup \
  alpine tar czf /backup/backup-riwayat-$(date +%F).tar.gz -C /data .
```

## Hal yang perlu diketahui

- **Kredit habis = layanan berhenti, bukan ditagih.** Tanpa kartu,
  risikomu mentok di "situs mati", tidak pernah "tagihan datang".
  Subscription student bisa diperbarui tiap 12 bulan selama status
  mahasiswa aktif.
- **Kuota gratis VM hanya untuk ukuran B1s / B2pts v2 / B2ats v2.**
  Naik ke ukuran lain (mis. B2ms) selalu memakan kredit — hitung
  jamnya bila dipakai menjelang presentasi.
- **Subscription student kadang membatasi region/ukuran.** Bila
  Southeast Asia menolak B2pts_v2, urutan fallback: B2ats_v2 di region
  sama → B2pts_v2 di East Asia → kabari asisten, kita nilai ulang.
- **Performa**: 2 vCPU CPU-only — mode foto adalah andalan demo; live
  berjalan di backend `.onnx` otomatis pada FPS CPU. Cadangan hari-H
  tetap Cloudflare Tunnel dari desktop (`.pt` 40+ FPS).

## Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| Situs tidak bisa dibuka | NSG rule 80/443 sudah dibuat? VM status Running? `docker compose ps` |
| `502 Bad Gateway` dari Caddy | `docker compose logs app` — aplikasi belum siap (model dimuat) atau crash |
| Login gagal terus / berputar | `JP_HTTPS` tidak cocok: HTTP via IP → `0`; HTTPS domain → `1` |
| Container app restart terus / OOM | Cek `free -h` (swap sudah aktif?) & log; pertimbangkan naik sementara ke B2ms dari kredit |
| Mode live gagal mulai / tracker error | Pastikan image ter-build dari `requirements-deploy.txt` terbaru (butuh `scipy` + `lap` eksplisit) |
| SSH tidak bisa masuk | File `.pem` salah / izin file terlalu terbuka (Windows: perintah `icacls` di Langkah 4) |
| Size VM tidak tersedia | Ikuti urutan fallback ukuran/region di "Hal yang perlu diketahui" |

## Checklist menjelang presentasi

- [ ] Situs terbuka dari jaringan luar (uji dari HP, bukan Wi-Fi rumah saja)
- [ ] Login admin dengan sandi baru berhasil; sesi tersimpan
- [ ] Satu foto uji terdeteksi benar end-to-end (deteksi → simpan → PDF)
- [ ] Domain + HTTPS aktif (bila memakai Langkah 8)
- [ ] Backup DB terakhir sudah diambil
- [ ] Rencana cadangan siap: aplikasi lokal di desktop/laptop +
      Cloudflare Tunnel, berjaga bila cloud bermasalah di hari-H
