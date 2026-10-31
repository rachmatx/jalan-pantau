# JalanPantau di GitHub Codespaces (cloud gratis kuota student)

> **Posisi jalur ini:** pendaftaran Oracle & Azure sama-sama kena
> gerbang verifikasi. Codespaces tidak punya gerbang itu — akun
> GitHub-mu sudah terverifikasi student. Ini cloud beneran (mesin
> GitHub/Azure di belakangnya), gratis dari kuota student, dan RAM-nya
> cukup untuk aplikasi ini. Sifatnya **sesi** (bukan server 24/7) —
> cocok untuk demo terjadwal, pengujian jarak jauh, dan cadangan
> presentasi. Jalur utama hari-H tetap Cloudflare Tunnel dari
> desktop (`deploy/cloudflare/`).

## Anggarannya (dari kuota GitHub Student-mu)

- Kuota Codespaces student: **180 core-hour/bulan**. Mesin 2-core
  membakar 2 core-hour per jam → **±90 jam nyala per bulan**. Lebih
  dari cukup untuk semua sesi demo & uji; bukan untuk nyala terus.
- Mesin 2-core = **8 GB RAM** (cukup: kebutuhan terukur aplikasi
  ±0,5 GB saat inferensi, lihat catatan uji deploy 31 Okt 2026).
- **Jangan pilih mesin lebih besar** — 4-core membakar kuota 2×
  lebih cepat tanpa manfaat berarti untuk aplikasi ini.
- Storage kuota 20 GB — venv + repo hanya ±3 GB. Hapus codespace
  lama yang tidak dipakai.

## Prasyarat

Konfigurasi di repo ini (`.devcontainer/` + folder ini) harus sudah
**ter-push ke branch `scope-baru`** — Codespaces membaca konfigurasi
dari branch yang dipilih saat pembuatan. Tanpa itu, codespace akan
terbuka sebagai environment generik tanpa setup otomatis.

## Langkah 1 — Buat codespace

1. Buka `github.com/rachmatx/jalan-pantau`.
2. Tombol hijau **Code → tab Codespaces → ⋯ (titik tiga) →
   "New with options…"** — jangan langsung "Create", karena kita
   harus memilih branch.
3. **Branch: `scope-baru`**, **Machine: 2-core** → **Create codespace**.
4. VS Code web terbuka dan setup berjalan otomatis (terminal
   "Setting up your codespace"): membuat `.venv`, memasang torch
   CPU + semua dependensi. **±5–10 menit** pertama kali — torch itu
   besar, ini normal. Selesai bila muncul tulisan
   "Setup Codespaces selesai".

## Langkah 2 — Atur batas idle (sekali saja, penting untuk demo)

Codespace berhenti sendiri setelah **30 menit idle** secara bawaan.
Untuk hari presentasi, longgarkan dulu:

`github.com/settings/codespaces` → **Default idle timeout** → naikkan
ke nilai terbesar (240 menit).

Ingat turunkan lagi setelahnya bila tidak dipakai — codespace yang
nyala membakar kuota jam.

## Langkah 3 — Jalankan aplikasi

Di terminal codespace (sudah berada di root repo):

```bash
JP_SECRET_KEY=$(.venv/bin/python -c "import secrets; print(secrets.token_hex(32))") JP_DEMO_PASS='SANDI_ADMIN_BARU' .venv/bin/python web/app.py
```

- Ganti `SANDI_ADMIN_BARU` dengan sandi kuat pilihanmu. **Wajib:**
  sandi bawaan aplikasi (`jalanpantau2026`) tercantum di repo
  publik — URL codespace-mu nanti publik, jadi sandi bawaan =
  siapa pun bisa login admin.
- `JP_HTTPS` sudah diset `1` oleh devcontainer (aksesmu lewat
  HTTPS-nya GitHub) — jangan diubah, salah nilai membuat login
  berputar.
- `JP_SECRET_KEY` acak per sesi membuat sesi login lama tidak
  berlaku lagi setiap codespace dijalankan ulang; untuk demo itu
  tidak masalah. Bila mau tetap, ganti perintahnya dengan nilai
  hex tetap buatanmu sendiri.

## Langkah 4 — Jadikan port publik & ambil URL

1. Di VS Code web: tab **PORTS** (di panel bawah).
2. Port **5000** muncul otomatis saat aplikasi jalan.
3. **Klik kanan port 5000 → Port Visibility → Public.**
4. Salin URL-nya (bentuknya
   `https://<nama-codespace>-5000.app.github.dev`) — itu alamat
   publik aplikasimu selama codespace nyala.
5. Uji dari HP (data seluler): Deteksi → unggah foto → hasil tampil
   → login admin → simpan sesi → Riwayat/PDF → Peta.

## Langkah 5 — Selesai pakai: STOP, jangan biarkan nyala

`github.com/codespaces` → codespace-mu → **⋯ → Stop codespace**.
Kuota jam berhenti berjalan; isi workspace (termasuk `.venv` dan
database riwayat di dalam repo) tersimpan untuk sesi berikutnya.
**Delete** hanya bila sudah tidak akan dipakai lagi (menghapus
semuanya, termasuk riwayat di dalamnya — backup dulu bila perlu).

## Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| Setup gagal / tidak jalan otomatis | Jalankan manual di terminal: `bash deploy/codespaces/setup.sh` — baca baris error pertamanya |
| Port 5000 tidak muncul | Aplikasi belum jalan atau crash — baca terminal tempat `web/app.py` dijalankan |
| URL publik dibuka → 502 / error GitHub | Aplikasi mati di codespace (cek terminal), atau port belum Public |
| Login berputar terus | `JP_HTTPS` harus `1` (sudah dari devcontainer — pastikan tidak kamu timpa ke 0) |
| Codespace mati sendiri di tengah demo | Idle timeout — atur 240 menit (Langkah 2) sebelum hari-H, dan codespace memang punya batas durasi sesi maksimum; untuk sesi panjang, Tunnel desktop tetap lebih aman |
| Kuota menipis | `github.com/settings/billing` → Codespaces — matikan codespace yang tidak dipakai; jangan buat mesin >2-core |

## Checklist menjelang presentasi (bila Codespaces jadi jalur demo)

- [ ] Codespace dibuat dari branch `scope-baru`, mesin 2-core
- [ ] Idle timeout sudah 240 menit untuk hari itu
- [ ] Aplikasi jalan, port 5000 Public, URL tersalin ke slide/QR
- [ ] Satu foto uji terdeteksi benar end-to-end dari HP
- [ ] Sandi admin sudah diganti (bukan bawaan)
- [ ] Cadangan tetap siap: Cloudflare Tunnel dari desktop
