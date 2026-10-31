@echo off
REM ============================================================
REM  JalanPantau - Reset akun admin (Windows, jalankan SEKALI)
REM
REM  Kenapa perlu: aplikasi hanya menanam akun admin saat tabel
REM  admin KOSONG (database.init_admin). Di PC ini aplikasi sudah
REM  pernah jalan, jadi admin lama sudah tersimpan di database —
REM  kemungkinan besar masih bersandi bawaan publik
REM  "jalanpantau2026". Mengganti JP_DEMO_PASS di mulai-tunnel.bat
REM  TIDAK mengubah sandi yang sudah tertanam itu.
REM
REM  Script ini menghapus BARIS AKUN ADMIN SAJA. Data riwayat,
REM  sesi deteksi, dan peta TIDAK ikut terhapus. Pada start
REM  aplikasi berikutnya (lewat mulai-tunnel.bat), akun admin
REM  ditanam ulang memakai JP_DEMO_PASS dari .bat tersebut.
REM
REM  Jalankan script ini SEBELUM mulai-tunnel.bat, dan pastikan
REM  JP_DEMO_PASS di mulai-tunnel.bat sudah diganti nilainya.
REM ============================================================

cd /d "%~dp0..\.."

echo Folder repo: %CD%
echo.
echo Script ini akan menghapus akun admin dari database lokal.
echo Data riwayat TIDAK ikut terhapus.
echo Pastikan aplikasi sedang TIDAK berjalan.
echo.
pause

python -c "import sqlite3; c=sqlite3.connect(r'web\instance\riwayat.db'); n=c.execute('DELETE FROM admin').rowcount; c.commit(); print('Baris admin terhapus:', n)"
if errorlevel 1 (
  echo.
  echo GAGAL menjalankan reset. Cek: python terbaca di PATH,
  echo dan berkas web\instance\riwayat.db ada di folder repo ini.
  echo.
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  Selesai. Sekarang jalankan mulai-tunnel.bat seperti biasa:
echo  akun admin akan ditanam ulang dengan sandi dari .bat itu.
echo  Uji setelahnya: login pakai sandi BARU harus bisa, dan
echo  sandi lama "jalanpantau2026" harus DITOLAK.
echo ============================================================
echo.
pause
