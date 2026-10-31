#!/usr/bin/env bash
# JalanPantau — setup otomatis GitHub Codespaces.
# Dijalankan sekali oleh devcontainer (postCreateCommand) saat
# codespace pertama kali dibuat. Membuat venv .venv di root repo
# lalu memasang dependensi varian server (deploy/oracle/
# requirements-deploy.txt — berkas yang sama yang sudah teruji
# untuk deploy cloud).
set -e
cd "$(dirname "$0")/../.."

if [ ! -x .venv/bin/python ]; then
  echo "== Membuat virtualenv .venv =="
  python -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip

# torch CPU dulu dari index resmi PyTorch. Langkah ini penting di
# x86_64: tanpa ini, ultralytics menarik torch dari PyPI yang
# membundel CUDA (±2,5 GB, lambat & boros kuota storage codespace).
# Di ARM wheel PyPI memang CPU-only, tapi Codespaces memakai x86_64.
echo "== Memasang torch CPU =="
.venv/bin/python -m pip install torch torchvision \
  --index-url https://download.pytorch.org/whl/cpu

echo "== Memasang dependensi aplikasi =="
.venv/bin/python -m pip install -r deploy/oracle/requirements-deploy.txt

echo ""
echo "=============================================================="
echo " Setup Codespaces selesai."
echo " Jalankan aplikasi dengan (ganti SANDI_ADMIN_BARU):"
echo ""
echo "   JP_SECRET_KEY=\$(.venv/bin/python -c \"import secrets; print(secrets.token_hex(32))\") JP_DEMO_PASS='SANDI_ADMIN_BARU' .venv/bin/python web/app.py"
echo ""
echo " Lalu buka tab PORTS, klik kanan port 5000,"
echo " Port Visibility -> Public, dan salin URL-nya."
echo " Panduan lengkap: deploy/codespaces/PANDUAN.md"
echo "=============================================================="
