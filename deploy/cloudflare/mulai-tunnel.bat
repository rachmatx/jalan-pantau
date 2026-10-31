@echo off
REM ============================================================
REM  JalanPantau - Peluncur Cloudflare Quick Tunnel (Windows)
REM  Menjalankan aplikasi lokal lalu membukanya ke internet
REM  lewat tunnel HTTPS sementara (URL acak trycloudflare.com).
REM
REM  SEBELUM PERTAMA KALI JALAN: edit DUA nilai di bawah ini.
REM  JP_DEMO_PASS adalah sandi login admin aplikasi. Nilai
REM  bawaan publiknya "jalanpantau2026" (dari repo terbuka) -
REM  selama tunnel aktif, SIAPA PUN yang tahu URL bisa masuk
REM  sebagai admin bila sandi ini tidak diganti.
REM ============================================================

set JP_SECRET_KEY=GANTI_DENGAN_STRING_ACAK_PANJANG
set JP_DEMO_PASS=GANTI_DENGAN_SANDI_KUAT_BARU
set JP_HTTPS=1
set JP_SESSION_HOURS=8

cd /d "%~dp0..\.."

if "%JP_DEMO_PASS%"=="GANTI_DENGAN_SANDI_KUAT_BARU" (
  echo.
  echo  ==========================================================
  echo   BERHENTI: JP_DEMO_PASS belum diganti!
  echo   Buka berkas .bat ini dengan Notepad, edit baris
  echo   JP_DEMO_PASS dan JP_SECRET_KEY di bagian atas,
  echo   simpan, lalu jalankan lagi.
  echo  ==========================================================
  echo.
  pause
  exit /b 1
)

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo.
  echo  cloudflared belum terpasang. Pasang dulu lewat PowerShell:
  echo     winget install --id Cloudflare.cloudflared
  echo  atau unduh cloudflared-windows-amd64.exe dari GitHub
  echo  Cloudflare, ganti namanya jadi cloudflared.exe, dan taruh
  echo  di folder yang masuk PATH. Lihat PANDUAN.md di folder ini.
  echo.
  pause
  exit /b 1
)

echo Menyalakan aplikasi JalanPantau di jendela baru...
start "JalanPantau App - JANGAN DITUTUP" cmd /k python web\app.py

echo Menunggu aplikasi siap (15 detik)...
timeout /t 15 /nobreak >nul

echo.
echo ============================================================
echo  Tunnel dibuka. Cari baris berisi:
echo     https://....trycloudflare.com
echo  Itu alamat publik aplikasimu. Jendela ini JANGAN ditutup
echo  selama tunnel dipakai. Ctrl-C untuk mematikan tunnel.
echo ============================================================
echo.
cloudflared tunnel --url http://127.0.0.1:5000
pause
