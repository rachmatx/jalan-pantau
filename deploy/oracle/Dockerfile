# JalanPantau — image aplikasi untuk Oracle Cloud Always Free (ARM64)
# =====================================================================
# Target: instance VM.Standard.A1.Flex (Ampere, aarch64), Ubuntu, Docker.
# Base image python:3.11-slim-bookworm bersifat multi-arch, jadi Dockerfile
# yang sama juga jalan di x86_64 (mis. buat uji build di PC).
#
# Strategi:
# - Multi-stage: tahap builder memasang semua dependensi ke /opt/venv
#   (build-essential ikut di tahap ini saja, untuk paket yang sesekali
#   perlu kompilasi di ARM seperti `lap`); tahap runtime hanya membawa
#   venv + pustaka sistem minimum -> image akhir lebih kecil & bersih.
# - Aplikasi TIDAK diubah sama sekali: tetap `python web/app.py`.
#   app.py memang bind 127.0.0.1:5000 secara hardcoded; di compose, app
#   memakai network_mode: host sehingga Caddy (juga host) me-reverse-proxy
#   ke 127.0.0.1:5000, dan port 5000 TIDAK pernah terekspos ke internet.
# =====================================================================

# ---------- Tahap 1: builder ----------
FROM python:3.11-slim-bookworm AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY deploy/oracle/requirements-deploy.txt /tmp/requirements-deploy.txt
RUN pip install --upgrade pip \
 && pip install -r /tmp/requirements-deploy.txt

# ---------- Tahap 2: runtime ----------
FROM python:3.11-slim-bookworm

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Jakarta \
    JP_DEBUG=0

# libglib2.0-0: dibutuhkan opencv-headless; libgomp1: OpenMP untuk
# torch/onnxruntime; tzdata: zona waktu Asia/Jakarta untuk log & sesi.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libglib2.0-0 libgomp1 tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --create-home --uid 10001 jp

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . /app

# web/instance = lokasi SQLite (riwayat.db) + thumbnail hasil.
# Di compose, folder ini ditimpa named volume agar data awet antar-build.
RUN mkdir -p /app/web/instance/hasil \
 && chown -R jp:jp /app

USER jp

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/', timeout=4)" || exit 1

CMD ["python", "web/app.py"]
