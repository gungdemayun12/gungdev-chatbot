@echo off
REM ==========================================================
REM  Menjalankan backend GungDev (Windows)
REM  Klik dua kali file ini, atau jalankan dari terminal.
REM
REM  Mode dipilih otomatis:
REM    - ada GROQ_API_KEY di .env  -> Groq (cloud)
REM    - tidak ada                 -> Ollama lokal
REM ==========================================================
setlocal

REM Lokasi Python (instalasi lokal, tanpa mengubah PATH global)
set PYTHON=%LOCALAPPDATA%\ChatbotSaya-Python\python.exe

REM Kalau tidak ada, pakai "python" dari PATH
if not exist "%PYTHON%" set PYTHON=python

REM Selalu jalankan dari folder file .bat ini agar .env terbaca
cd /d "%~dp0"

REM Bersihkan variabel lama dari sesi terminal sebelumnya
set OLLAMA_HOST=
set OLLAMA_MODEL=
set MODEL_NAME=
set OLLAMA_API_KEY=
set AI_PROVIDER=

REM Pastikan dependensi terpasang
"%PYTHON%" -c "import fastapi, httpx, uvicorn" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  Dependensi belum terpasang. Memasang sekarang...
    "%PYTHON%" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo  GAGAL memasang dependensi. Periksa koneksi internet.
        pause
        exit /b 1
    )
)

echo ==========================================================
echo  Backend GungDev
echo  http://localhost:8000    (cek: /health, dokumen: /docs)
echo  Tekan Ctrl+C untuk menghentikan.
echo ==========================================================
echo.

"%PYTHON%" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
