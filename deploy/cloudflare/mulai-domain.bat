@echo off
REM ============================================================
REM  JalanPantau - Peluncur NAMED Tunnel (domain sendiri)
REM  Menjalankan aplikasi lokal lalu membukanya ke internet di
REM  alamat tetap app.rachmatx.me lewat tunnel "jalanpantau".
REM
REM  Syarat satu kali (SUDAH dikerjakan 31 Okt 2026, JANGAN
REM  diulang): cloudflared terpasang, tunnel login/create/route
REM  dns selesai, dan %USERPROFILE%\.cloudflared\config.yml ada.
REM  Lihat PANDUAN.md folder ini bila config itu hilang.
REM
REM  SEBELUM PERTAMA KALI JALAN: edit DUA nilai di bawah ini,
REM  samakan dengan isianmu di mulai-tunnel.bat.
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

if not exist "%USERPROFILE%\.cloudflared\config.yml" (
  echo.
  echo  ==========================================================
  echo   BERHENTI: config named tunnel tidak ditemukan di
  echo   %USERPROFILE%\.cloudflared\config.yml
  echo   Tanpa berkas itu tunnel "jalanpantau" tidak bisa jalan.
  echo   Ikuti bagian "Mode domain sendiri" di PANDUAN.md.
  echo  ==========================================================
  echo.
  pause
  exit /b 1
)

where cloudflared >nul 2>nul
if errorlevel 1 (
  echo.
  echo  cloudflared belum terpasang / tidak terbaca di PATH.
  echo  Buka jendela CMD BARU setelah install, atau pasang:
  echo     winget install --id Cloudflare.cloudflared
  echo.
  pause
  exit /b 1
)

REM --- Pilih interpreter: utamakan venv di dalam repo ---
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if exist "venv\Scripts\python.exe" set "PY=venv\Scripts\python.exe"

echo Memeriksa lingkungan Python: %PY%
"%PY%" -c "import flask, ultralytics, torch; print('  Dependensi OK - CUDA tersedia:', torch.cuda.is_available())"
if errorlevel 1 (
  echo.
  echo  ==========================================================
  echo   BERHENTI: python di atas TIDAK punya dependensi proyek
  echo   ^(flask/ultralytics/torch^). Arahkan variabel PY di berkas
  echo   .bat ini ke python.exe yang benar, lalu jalankan lagi.
  echo  ==========================================================
  echo.
  pause
  exit /b 1
)

echo Menyalakan aplikasi JalanPantau di jendela baru...
start "JalanPantau App - JANGAN DITUTUP" cmd /k "%PY% web\app.py"

echo Menunggu aplikasi siap (20 detik)...
timeout /t 20 /nobreak >nul

echo.
echo ============================================================
echo  Named tunnel "jalanpantau" dibuka.
echo  Alamat publikmu: https://app.rachmatx.me
echo  Jendela ini JANGAN ditutup selama situs dipakai.
echo  Ctrl-C untuk mematikan tunnel.
echo ============================================================
echo.
cloudflared tunnel run jalanpantau
pause
