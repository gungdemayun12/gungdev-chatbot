@echo off
REM ==========================================================
REM  Menjalankan backend Chatbot Saya (Windows)
REM  Klik dua kali file ini, atau jalankan dari terminal.
REM ==========================================================
setlocal

REM Lokasi Python yang dipakai (instalasi lokal, tanpa mengubah PATH global)
set PYTHON=%LOCALAPPDATA%\ChatbotSaya-Python\python.exe

REM Kalau Python di atas tidak ada, coba pakai "python" dari PATH
if not exist "%PYTHON%" set PYTHON=python

REM Selalu jalankan dari folder tempat file .bat ini berada,
REM supaya file .env di folder backend/ pasti terbaca.
cd /d "%~dp0"

REM Bersihkan variabel lama dari sesi terminal sebelumnya, agar nilai
REM dari file .env (localhost + deepseek-r1:7b) yang dipakai.
set OLLAMA_HOST=
set MODEL_NAME=
set OLLAMA_API_KEY=

echo ==========================================================
echo  Backend Chatbot Saya  -  Ollama LOKAL
echo  http://localhost:8000   (cek: /health, dokumen: /docs)
echo  Tekan Ctrl+C untuk menghentikan.
echo ==========================================================
echo.

"%PYTHON%" -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
