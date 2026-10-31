# Hosting JalanPantau dari Laptop Fedora + Cloudflare Tunnel

> **Kenapa jalur ini:** aplikasi SUDAH terpasang dan jalan di laptop
> ini — tidak ada pendaftaran cloud, tidak ada kartu, tidak ada
> plafon RAM. Cloudflare Tunnel meneruskan aplikasi lokal ke
> internet lewat HTTPS. Dengan **named tunnel**, alamatnya adalah
> **domain .tech kamu sendiri** (tetap, tidak acak) — menjawab
> kebutuhan domain yang tidak bisa dipenuhi Codespaces.

## Batasnya, jujur dari awal

- Laptop harus **nyala, tercolok listrik, dan tidak tidur** selama
  hosting dipakai. Laptop mati/tidur = situs mati.
- CPU laptop ini (i5-3210M) tua: **mode foto bisa dipakai** tapi
  deteksi per foto lambat (orde detik sampai belasan detik — termasuk
  memuat model di permintaan pertama). **Mode live JANGAN di sini**
  (FPS kecil + panas, sudah terukur sebelumnya); live tetap dari
  desktop GPU atau Codespaces.
- Koneksi internet rumah adalah jalurnya; kecepatan unggah rumah
  membatasi respons ke pengunjung.
- Ini hosting masa presentasi/pengujian, bukan server produksi
  24/7 — target akhirnya tetap VM cloud bila gerbangnya kebuka.

## Langkah 0 — Pastikan aplikasi sehat secara lokal

Jalankan aplikasi seperti biasanya di laptop ini, buka
`http://127.0.0.1:5000` — halaman Deteksi harus tampil dan satu foto
uji terdeteksi. Semua langkah berikutnya mengandaikan ini beres.

Jangan lupa perbarui kode: `git pull` di branch `scope-baru` (setelah
commit perbaikan tile peta & libgl1 ter-push) — sumber tile peta kini
CARTO, tidak lagi bergantung pada tile.openstreetmap.org yang
memblokir domain publik.

## Langkah 1 — Amankan sandi admin (WAJIB sebelum terekspos)

Database laptop ini kemungkinan besar sudah berisi akun admin dari
pertama kali aplikasi jalan — dan `init_admin()` hanya menanam akun
**saat tabel admin kosong**, jadi mengganti env `JP_DEMO_PASS` saja
TIDAK mengubah sandi yang sudah tersimpan (kemungkinan masih
`jalanpantau2026`, sandi publik dari repo).

Reset khusus akun admin (data riwayat TIDAK ikut terhapus — yang
dihapus hanya baris akun admin, lalu aplikasi menanam ulang dengan
sandi dari env pada start berikutnya):

```bash
cd ~/jalan-pantau
sqlite3 web/instance/riwayat.db "DELETE FROM admin;"
```

Lalu pastikan setiap start aplikasi sesudah ini membawa env:

```bash
export JP_DEMO_PASS='SANDI_BARU_YANG_KUAT'
export JP_SECRET_KEY='STRING_ACAK_PANJANG'
export JP_HTTPS=1
```

Uji: login `admin` + sandi barumu harus bisa; sandi lama harus
ditolak.

## Langkah 2 — Pasang cloudflared

Sudah pernah memasang untuk proyek lain? Cek dulu: `cloudflared
--version`. Bila ada, lewati langkah ini.

```bash
sudo dnf install -y https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.rpm
cloudflared --version
```

## Langkah 3 — Tes cepat (quick tunnel, URL acak)

Terminal 1 (aplikasi, dengan env dari Langkah 1):

```bash
cd ~/jalan-pantau && python web/app.py   # sesuaikan python-mu
```

Terminal 2:

```bash
cloudflared tunnel --url http://127.0.0.1:5000
```

Salin URL `https://....trycloudflare.com`, uji dari HP (data
seluler): halaman tampil, peta CARTO tampil, deteksi jalan, login
bisa. Bila ini mulus, fondasinya terbukti — tinggal dibuat tetap.

## Langkah 4 — Named tunnel + domain sendiri

1. Daftar **Cloudflare** (gratis, cukup email — tanpa kartu) →
   **Add a site** → masukkan domain `.tech` kamu (dari GitHub
   Student Pack / Namecheap) → pilih plan **Free**.
2. Di Namecheap: ganti **nameserver** domain ke dua nameserver yang
   diberikan Cloudflare. Tunggu status domain di Cloudflare jadi
   **Active** (menit sampai beberapa jam).
3. Di Fedora:

```bash
cloudflared tunnel login
cloudflared tunnel create jalanpantau
cloudflared tunnel route dns jalanpantau app
```

   `route dns` di atas membuat subdomain `app.domainmu.tech`.
4. Salin `cloudflared-config-contoh.yml` dari folder ini ke
   `~/.cloudflared/config.yml`, isi UUID tunnel, path credentials,
   user, dan hostname dari langkahmu.
5. Jalankan: `cloudflared tunnel run jalanpantau` — buka
   `https://app.domainmu.tech` dari HP. HTTPS-nya otomatis dari
   Cloudflare.

## Langkah 5 — Biar nyala sendiri (systemd)

Aplikasi — pakai unit di folder ini (`jalanpantau.service`):
sesuaikan path & python, isi env sandi, lalu:

```bash
mkdir -p ~/.config/systemd/user
cp deploy/fedora/jalanpantau.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now jalanpantau
loginctl enable-linger $USER
journalctl --user -u jalanpantau -f   # pantau log
```

Tunnel sebagai service (cloudflared memasang unit sistemnya
sendiri):

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Matikan suspend selama masa hosting (GNOME):

```bash
gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing'
gsettings set org.gnome.desktop.session idle-delay 0
```

Dan biarkan laptop tercolok; tutup layar boleh selama suspend mati
— bila menutup lid memicu tidur di mesinmu, tambahkan
`HandleLidSwitch=ignore` di `/etc/systemd/logind.conf` lalu
`sudo systemctl restart systemd-logind`.

## Troubleshooting cepat

| Gejala | Cek pertama |
|---|---|
| Domain tidak terbuka | Nameserver belum pindah (cek status Active di Cloudflare) atau tunnel belum `run` |
| 502 dari Cloudflare | Aplikasi lokal mati — `systemctl --user status jalanpantau` / buka 127.0.0.1:5000 |
| Login ditolak terus | Sandi admin belum tereset (Langkah 1) — env saja tidak cukup bila admin lama sudah tertanam |
| Login berputar | `JP_HTTPS` harus `1` (akses publik selalu HTTPS dari Cloudflare) |
| Situs mati setelah laptop ditinggal | Suspend/lid — cek Langkah 5 (gsettings + linger) |
| Deteksi sangat lambat | Wajar di CPU ini untuk foto pertama (muat model); foto berikutnya lebih cepat. Live jangan di sini |

## Checklist menjelang presentasi

- [ ] Aplikasi lokal sehat (deteksi foto uji OK di 127.0.0.1:5000)
- [ ] Sandi admin sudah BARU (sandi bawaan ditolak saat diuji)
- [ ] `https://app.domainmu.tech` terbuka dari HP (data seluler)
- [ ] Peta tampil (tile CARTO), satu foto terdeteksi end-to-end
- [ ] Service aplikasi + tunnel aktif & auto-start (systemd)
- [ ] Suspend mati, laptop tercolok
- [ ] Cadangan: Codespace "scary spooky monster" siap dinyalakan,
      dan/atau quick tunnel desktop
