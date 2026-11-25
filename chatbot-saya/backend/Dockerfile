# ==========================================================
# Dockerfile backend GungDev
# ==========================================================
# Image kecil (python-slim) + user non-root.
# Render/Railway/Fly.io bisa langsung memakai file ini.
# ==========================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependensi lebih dulu agar layer cache efisien.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin kode aplikasi.
COPY main.py .

# Jalankan sebagai user biasa (praktik keamanan standar).
RUN useradd --create-home --uid 1000 appuser
USER appuser

# Render/Railway menyuntikkan PORT; default 8000 untuk lokal.
ENV PORT=8000
EXPOSE 8000

# Satu worker: cukup untuk free tier & menjaga memori rendah.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --timeout-keep-alive 75"]
