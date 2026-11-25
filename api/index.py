"""
=====================================================================
 TITIK MASUK VERCEL SERVERLESS FUNCTION
=====================================================================
File ini SANGAT kecil dengan sengaja.

Tugasnya hanya satu: mengekspor objek `app` (FastAPI) dari
`chatbot-saya/backend/main.py` agar Vercel bisa menjalankannya
sebagai serverless function.

Semua logika tetap berada di backend/main.py  ->  satu sumber
kebenaran. Jadi:

  - Menjalankan lokal  : uvicorn main:app --reload --port 8000
  - Deploy ke Vercel   : otomatis lewat file ini
  - Deploy ke Render   : lewat Dockerfile

Tidak ada duplikasi kode sama sekali.

URL setelah deploy (Vercel):
    https://<project>.vercel.app/api/health
    https://<project>.vercel.app/api/chat
    https://<project>.vercel.app/api/chat/stream
=====================================================================
"""

import os
import sys

# Vercel menjalankan file ini dari folder /var/task.
# Tambahkan folder backend ke sys.path supaya `import main` berhasil
# tanpa perlu menginstal paket apa pun.
_BACKEND_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "chatbot-saya",
    "backend",
)

if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from main import app  # noqa: E402  (import setelah sys.path diatur)

# Vercel mencari variabel bernama `app` (ASGI).
__all__ = ["app"]
