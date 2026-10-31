# Panduan Deploy JalanPantau ke Oracle Cloud Always Free

Target akhir: JalanPantau bisa dibuka dari internet lewat IP publik (dan
nanti domain + HTTPS) di instance **Oracle Cloud Always Free** — gratis
selamanya, tanpa sleep, spek **Ampere A1 (ARM) 2 OCPU / 12 GB RAM** yang
jauh di atas kebutuhan aplikasi ini.

Arsitektur di server (semua dari paket di folder ini):

```
internet ──► Caddy (port 80/443, container, HTTPS otomatis bila domain)
                │ reverse proxy
                ▼
          Flask `python web/app.py` (container, 127.0.0.1:5000 saja)
                │
                ▼
          SQLite riwayat.db di named volume Docker (awet antar-build)
```

Kenapa begitu: `web/app.py` memang bind `127.0.0.1:5000` secara hardcoded
dan **kode aplikasi tidak diubah sama sekali** untuk deploy ini. Kedua
container memakai `network_mode: host`; Caddy meneruskan trafik ke
localhost, dan port 5000 tidak pernah terekspos ke internet.

Isi paket (`deploy/oracle/`):

| Berkas | Fungsi |
|---|---|
| `Dockerfile` | Image aplikasi multi-stage, Python 3.11 slim, siap ARM64 & x86_64 |
| `docker-compose.yml` | Service `app` + `caddy`, volume data, restart otomatis |
| `requirements-deploy.txt` | Dependensi varian server (opencv headless; torch CPU dari PyPI) |
| `Caddyfile` | Reverse proxy; mode IP (`:80`) dan mode domain (HTTPS) |
| `.env.example` | Template rahasia & konfigurasi runtime |
| `.dockerignore` | Disalin ke root repo sebelum build pertama |

---

## Langkah 1 — Daftar Oracle Cloud Free Tier

1. Buka halaman Oracle Cloud Free Tier, daftar dengan email aktif.
2. **Home Region: pilih `Singapore (Singapore)`.** Pilihan ini **permanen**
   dan tidak bisa diubah sesudah akun jadi; Always Free hanya bisa dibuat
   di home region. Singapore = latensi terkecil dari Indonesia.
3. Verifikasi identitas memakai kartu debit/kredit. Ini hanya verifikasi
   (ada penahanan dana kecil yang dikembalikan); resource berlabel
   **Always Free Eligible** tidak ditagih. Jangan klik "Upgrade" ke
   Pay As You Go kecuali kamu sadar konsekuensinya.
4. Akun baru juga diberi kredit trial berbatas waktu — **abaikan** untuk
   proyek ini; kita hanya memakai resource Always Free.

## Langkah 2 — Buat instance

Console → **Compute → Instances → Create instance**:

- **Name**: `jalanpantau`
- **Image**: `Canonical Ubuntu 24.04` — pastikan varian **aarch64 (ARM)**.
- **Shape**: ubah ke **Ampere**, `VM.Standard.A1.Flex`, set **2 OCPU /
  12 GB RAM**. (Kuota Always Free total 4 OCPU / 24 GB — memakai 2/12
  menyisakan separuh untuk instance lain. Bila nanti kurang, shape bisa
  dinaikkan selama total tidak melewati 4/24.)
- **Networking**: VCN default, **pastikan "Assign a public IPv4 address" aktif**.
- **SSH keys**: pilih *Generate a key pair for me* lalu **unduh private
  key dan simpan baik-baik** (kunci ini satu-satunya jalan masuk SSH;
  kehilangan = terkunci).
- **Boot volume**: 50 GB cukup (total kuota penyimpanan Always Free
  200 GB).
- Create. Tunggu status **RUNNING**, catat **Public IPv4 address**.

**Bila muncul `Out of host capacity`**: itu soal ketersediaan ARM di
region, bukan kesalahanmu. Coba lagi di jam lain, pilih Availability
Domain lain, atau turunkan dulu ke 1 OCPU / 6 GB lalu naikkan shape
belakangan. Ini alasan deploy disiapkan jauh sebelum hari presentasi.

## Langkah 3 — Buka port di Security List

Instance → **Virtual cloud network → Subnet → Security List** (yang
terpasang) → tambahkan **Ingress rules**:

| Source | Protokol | Port tujuan | Keterangan |
|---|---|---|---|
| `0.0.0.0/0` | TCP | 80 | HTTP |
| `0.0.0.0/0` | TCP | 443 | HTTPS |
| `0.0.0.0/0` | UDP | 443 | HTTP/3 (opsional) |
| `0.0.0.0/0` | TCP | 22 | SSH (ideal: batasi ke IP kamu bila IP rumahmu statis) |

Port 5000 **jangan** dibuka — aplikasi hanya untuk Caddy di localhost.

## Langkah 4 — SSH masuk & pasang Docker

Dari PC kamu (ganti IP & path kunci):

```bash
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<IP-PUBLIK>
```

Di dalam instance:

```bash
sudo apt update && sudo apt upgrade -y
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
```

Keluar (`exit`) lalu SSH masuk lagi agar grup `docker` aktif; cek
`docker run hello-world` harus jalan tanpa `sudo`.

**Gotcha khas Oracle (penting):** image Ubuntu Oracle memasang aturan
iptables bawaan yang menolak sebagian besar trafik masuk selain SSH,
di luar Security List. Bila nanti situs tidak bisa dibuka padahal
Security List sudah benar, ini penyebabnya. Buka port di iptables VM:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo apt install -y iptables-persistent   # jawab Yes saat ditanya simpan rules
```

## Langkah 5 — Ambil kode & siapkan konfigurasi

```bash
git clone -b scope-baru https://github.com/rachmatx/jalan-pantau.git
cd jalan-pantau/deploy/oracle
cp .env.example .env
cp .dockerignore ../../.dockerignore
nano .env
```

Isi dua nilai wajib di `.env`:

- `JP_SECRET_KEY` — hasilkan dengan `openssl rand -hex 32`, tempel.
- `JP_DEMO_PASS` — sandi admin yang kuat dan baru. **Jangan dikosongkan:**
  kosong berarti sandi default `jalanpantau2026` yang diketahui publik
  dari repo. Mengganti ini sebelum aplikasi online itu wajib, bukan saran.

`JP_HTTPS` biarkan `0` selama masih memakai HTTP via IP (lihat catatan
di `.env.example` — salah nilai di sini membuat login gagal berputar).

## Langkah 6 — Build & jalankan

```bash
docker compose build      # pertama kali 10–25 menit: unduh torch ARM dsb.
docker compose up -d
docker compose ps         # app harus menuju (healthy)
docker compose logs -f app   # Ctrl-C untuk berhenti mengikuti log
```

Build pertama memang lama — itu normal (torch + ultralytics versi ARM).
Build berikutnya jauh lebih cepat karena layer cache.

## Langkah 7 — Uji dari browser

Buka `http://<IP-PUBLIK>/`:

1. Halaman Deteksi tampil.
2. Unggah satu foto uji dari `test_foto/` (atau foto jalan apa pun) →
   deteksi jalan, hasil tampil. Inferensi pertama bisa lebih lambat
   (model dimuat) — berikutnya normal.
3. Login dengan `admin` + sandi dari `JP_DEMO_PASS`, simpan sesi,
   cek Riwayat & unduh PDF.
4. Cek Peta.

Bila 1–4 mulus, deploy selesai. Sisanya (domain) adalah peningkatan,
bukan syarat.

## Langkah 8 (disarankan) — Domain + HTTPS untuk presentasi

URL angka-IP itu fungsional tapi kurang enak ditampilkan di slide/QR.
Jalur murahnya: klaim domain **.tech gratis 1 tahun** dari GitHub
Student Developer Pack (Namecheap) yang sudah kamu punya, lalu:

1. Di Namecheap: tambahkan **A record** `@` (dan `www` bila mau) →
   IP publik instance. Tunggu propagasi (cek `nslookup namadomain.tech`).
2. Edit `Caddyfile`: nonaktifkan blok `:80`, aktifkan blok domain,
   ganti dengan domainmu.
3. Edit `.env`: `JP_HTTPS=1`.
4. `docker compose up -d` ulang kedua service. Caddy otomatis meminta
   sertifikat Let's Encrypt — situs langsung HTTPS.

---

## Operasional sehari-hari

```bash
cd ~/jalan-pantau/deploy/oracle

docker compose logs -f app        # pantau log
docker compose restart app        # restart aplikasi saja
docker compose down               # matikan semua (data volume aman)
docker compose up -d              # nyalakan lagi
```

**Update kode** (setelah push perubahan ke `scope-baru`):

```bash
cd ~/jalan-pantau && git pull
cd deploy/oracle && docker compose build && docker compose up -d
```

**Backup database riwayat** (named volume `jp-instance`; nama lengkapnya
di mesinmu diawali nama proyek compose — cek dulu dengan
`docker volume ls | grep jp-instance`, lalu pakai nama persis itu):

```bash
docker run --rm -v <nama-volume-dari-docker-volume-ls>:/data -v "$PWD":/backup \
  alpine tar czf /backup/backup-riwayat-$(date +%F).tar.gz -C /data .
```

## Hal yang perlu diketahui (jujur, bukan menakut-nakuti)

- **Kebijakan idle Oracle**: instance Always Free yang sangat idle
  (CPU/jaringan/memori rendah terus selama ±7 hari) dapat dihentikan
  Oracle. Untuk pemakaian aktif menjelang presentasi risikonya kecil;
  bila instance tiba-tiba berhenti, cukup Start lagi dari Console —
  data di boot volume & Docker volume tidak hilang.
- **Filesystem container selain volume bersifat sementara.** Hanya
  `web/instance` (DB + thumbnail) yang dipetakan ke volume. Jangan
  menyimpan berkas penting di lokasi lain di dalam container.
- **Performa inferensi di ARM**: CPU Ampere kencang untuk kelasnya,
  tapi tetap CPU — mode foto adalah andalan demo; live streaming akan
  berjalan pada FPS CPU (backend `.onnx` dipilih otomatis), bukan
  40+ FPS seperti desktop GPU kamu. Untuk demo live yang mulus,
  Cloudflare Tunnel dari desktop tetap rencana cadangan terbaik.
- **Kuota Always Free**: total 4 OCPU / 24 GB RAM / 200 GB storage
  untuk semua instance A1 di akun. Jangan membuat instance A1 lain
  berukuran penuh bila instance ini masih dipakai.

## Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| Situs tidak bisa dibuka sama sekali | Security List (80/443) **dan** iptables VM (Langkah 4) — dua-duanya, bukan salah satu |
| `502 Bad Gateway` dari Caddy | `docker compose logs app` — aplikasi belum siap (model sedang dimuat) atau crash; tunggu healthcheck hijau |
| Build gagal di paket Python (kompilasi ARM) | Pastikan build memakai Dockerfile paket ini (build-essential ada di tahap builder); salin potongan log error persisnya untuk didiagnosis |
| Login gagal terus / berputar ke halaman login | `JP_HTTPS` tidak cocok dengan skema akses: HTTP via IP → `0`; HTTPS domain → `1` |
| Container app restart terus | `docker compose logs app` — paling sering: `.env` belum dibuat, atau volume lama berisi DB dari versi tak cocok (uji: ganti nama volume di compose untuk DB bersih) |
| Inferensi sangat lambat | Wajar untuk request pertama (muat model). Bila terus lambat: naikkan shape ke 4 OCPU/24 GB dari Console (instance berhenti sebentar) |
| SSH tidak bisa masuk | Kunci privat salah file/longgar permission (`chmod 600`), atau IP publik berubah setelah instance dibuat ulang |

## Checklist menjelang presentasi

- [ ] Situs terbuka dari jaringan luar (uji dari HP, bukan Wi-Fi rumah saja)
- [ ] Login admin dengan sandi baru berhasil; sesi tersimpan
- [ ] Satu foto uji terdeteksi benar end-to-end (deteksi → simpan → PDF)
- [ ] Domain + HTTPS aktif (bila memakai Langkah 8)
- [ ] Backup DB terakhir sudah diambil
- [ ] Rencana cadangan siap: aplikasi lokal di desktop/laptop +
      Cloudflare Tunnel, berjaga bila cloud bermasalah di hari-H
