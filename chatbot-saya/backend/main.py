"""
=====================================================================
 BACKEND GUNGDEV â€” FastAPI, multi-provider
=====================================================================
Satu server, dua mode penyedia AI:

  1. GROQ (dipakai saat deploy / publik)
       - API cloud OpenAI-compatible, sangat cepat (~280-500 token/detik)
       - Butuh GROQ_API_KEY (gratis di console.groq.com)
       - Cocok untuk Vercel Serverless, Render, Railway, Fly.io

  2. OLLAMA (dipakai saat pengembangan lokal)
       - Model berjalan di komputer sendiri, tanpa API key
       - Butuh aplikasi Ollama + model sudah diunduh

Mode dipilih otomatis:
   - Jika GROQ_API_KEY di-set  -> Groq
   - Jika tidak                -> Ollama lokal
  Bisa dipaksa lewat AI_PROVIDER=groq atau AI_PROVIDER=ollama.

Kontrak API TIDAK berubah:
   POST /chat         { message, history?, ... } -> { reply }
   POST /chat/stream  { message, history?, ... } -> text/event-stream
   GET  /health       -> { status, provider, model }

Cara menjalankan lokal:
     pip install -r requirements.txt
     uvicorn main:app --reload --port 8000

Dokumentasi otomatis:
     http://localhost:8000/docs

CATATAN DEPLOY VERCEL:
     File api/index.py HANYA mengimpor `app` dari modul ini.
     Jadi semua logika tetap di sini (satu sumber kebenaran) dan
     berjalan baik di server biasa maupun di Vercel Serverless.
=====================================================================
"""

# ---------------------------------------------------------------------
# 1. IMPORT LIBRARY
# ---------------------------------------------------------------------
import base64               # decode file biner yang dikirim klien
import contextvars         # penanda jawaban terpotong per-permintaan
import json                 # payload SSE (streaming)
import logging              # log rapi di terminal
import os                   # membaca environment variable
from typing import AsyncIterator, List, Optional, Sequence

import httpx                # HTTP client async (dipakai Groq & cek kesehatan)
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import lampiran             # ekstraksi teks file & validasi gambar
import penyimpanan          # riwayat percakapan di server (Upstash Redis)
import identitas            # verifikasi ID token Google di server
import usage                # pencatat & penyedia data kuota (usage)
import riset                # riset web nyata untuk SEMUA model

# python-dotenv hanya dipakai saat pengembangan lokal.
# Di Vercel/Render variabel masuk lewat environment, bukan file .env.
try:
    from dotenv import load_dotenv
except ImportError:          # pragma: no cover - dependensi opsional
    load_dotenv = None

# ---------------------------------------------------------------------
# 2. KONFIGURASI DASAR
# ---------------------------------------------------------------------
if load_dotenv is not None:
    _ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    load_dotenv(dotenv_path=_ENV_PATH, override=False)


def _env(nama: str, default: str = "") -> str:
    """Membaca env var dan membuang spasi di ujung."""
    return (os.environ.get(nama) or default).strip()


def _env_int(nama: str, default: int) -> int:
    """Membaca env var bertipe int dengan fallback aman."""
    try:
        return int(_env(nama) or default)
    except ValueError:
        return default


def _env_float(nama: str, default: float) -> float:
    """Membaca env var bertipe float dengan fallback aman."""
    try:
        return float(_env(nama) or default)
    except ValueError:
        return default


# ---- Groq (cloud) ----
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_BASE_URL = _env("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")

# ---- OpenRouter (OpenAI-compatible cloud) ----
OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_BASE_URL = _env(
    "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
).rstrip("/")
OPENROUTER_SITE_URL = _env("OPENROUTER_SITE_URL", "https://gungdevchatbot.vercel.app")
OPENROUTER_APP_NAME = _env("OPENROUTER_APP_NAME", "GungDev")
OPENROUTER_MODEL_DEFAULT = _env("OPENROUTER_MODEL", "openai/gpt-oss-20b")
# Daftar model OpenRouter yang boleh dipilih. Semua di sini mendukung
# tool calling sehingga bisa riset (riset tetap dikerjakan di server).
OPENROUTER_MODELS = [
    "google/gemini-2.5-flash-tts",
    "google/gemini-3.1-flash-lite",
    "deepseek/deepseek-v4.1-flash",
    # Model :free — bisa dipakai tanpa kredit OpenRouter.
    # Dipakai sebagai cadangan bila model berbayar menolak karena kredit
    # habis, sehingga situs tetap bisa dipakai.
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "inclusionai/ling-3.2-flash:free",
]

# Model OpenRouter GRATIS yang dipakai otomatis bila model berbayar
# menolak karena kredit/tagihan (HTTP 402). Tujuannya: pengguna tetap
# mendapat jawaban, bukan pesan error.
OPENROUTER_CADANGAN = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "inclusionai/ling-3.2-flash:free",
    "nvidia/nemotron-3.5-lightning:free",
]

# ---------------------------------------------------------------------
# PENYEDIA CADANGAN: GOOGLE GEMINI
# ---------------------------------------------------------------------
# Mengapa Gemini ditambahkan:
#   Groq membatasi 200.000 token/hari PER MODEL. Bila kuota itu habis,
#   seluruh situs berhenti melayani. Gemini memberi jalur tambahan yang
#   GRATIS (tanpa kartu kredit) dengan konteks 1 juta token, sehingga
#   kuota situs tidak lagi bergantung pada satu penyedia saja.
#
# Kenapa aman ditambahkan:
#   Gemini menyediakan endpoint yang KOMPATIBEL OpenAI di
#   https://generativelanguage.googleapis.com/v1beta/openai/ , jadi
#   format pesan, streaming SSE, dan gambar (image_url) sama persis
#   dengan yang sudah dipakai OpenRouter/Groq. Tidak ada kontrak API
#   yang berubah.
#
# Bila GEMINI_API_KEY kosong, penyedia ini otomatis TIDAK dipakai dan
# perilaku situs kembali seperti semula (Groq/OpenRouter saja).
GEMINI_API_KEY = _env("GEMINI_API_KEY")
GEMINI_BASE_URL = _env(
    "GEMINI_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta/openai",
).rstrip("/")

# Model Gemini yang dipakai.
#
# MENGAPA BUKAN gemini-2.5-flash LAGI
# ------------------------------------
# Per dokumentasi resmi Google (ai.google.dev/gemini-api/docs/deprecations):
#   - gemini-2.0-flash / gemini-2.0-flash-lite : DIMATIKAN 1 Juni 2026
#   - gemini-2.5-flash                         : deprecated, 1 Des 2026
#                                                dialihkan paksa ke
#                                                gemini-3.5-flash-lite
#   - gemini-2.5-flash-lite                    : hanya untuk pengguna lama
#
# Karena itu default dipindah ke generasi yang masih hidup dan TIDAK punya
# jadwal mati: gemini-3.5-flash-lite (pengganti resmi 2.5-flash, cepat dan
# hemat). Bisa diubah lewat GEMINI_MODEL tanpa mengubah kode.
GEMINI_MODEL_DEFAULT = _env("GEMINI_MODEL", "gemini-3.5-flash-lite")

# Urutan model yang dicoba, dari yang paling diinginkan.
#
# URUTAN INI DIPILIH DARI HASIL UJI NYATA, BUKAN DARI TEORI.
# Diuji langsung ke produksi (Vercel Hobby) dengan key gratis:
#
#   gemini-3.5-flash-lite  -> 200 OK, cepat          <- default
#   gemini-4-argon         -> 200 OK, 2,8 dtk
#   gemini-3.1-flash-lite  -> 200 OK, 15 dtk
#   gemini-3.6-flash       -> 502 jawaban kosong (35,6 dtk)  <- TIDAK DIPAKAI
#   gemini-4-hydrogen      -> 504 timeout Vercel (>60 dtk)   <- TIDAK DIPAKAI
#
# MENGAPA gemini-4-hydrogen DIBUANG
# ---------------------------------
# Model Gemini 4 adalah model "reasoning" yang berpikir panjang sebelum
# menjawab. Vercel Hobby menghentikan fungsi sekitar 60 detik, sehingga
# permintaan berakhir 504 dan pengguna TIDAK mendapat jawaban sama sekali.
# Model yang lebih lambat dari batas waktu itu lebih buruk daripada tidak
# ada: pengguna menunggu lama lalu gagal.
#
# gemini-4-argon tetap dipakai karena terbukti menjawab dalam 2,8 detik.
#
# Catatan jujur: TIDAK semua model di sini dijamin bisa dipakai dengan key
# gratis. Google membatasi sebagian model hanya untuk akun lama. Karena itu
# daftar ini berfungsi sebagai RANTAI CADANGAN: model yang ditolak
# (404/403) dilewati otomatis. Untuk melihatnya dengan key Anda sendiri,
# jalankan `python uji_model_gemini.py`.
#
# Model yang sudah dimatikan (2.0-flash, 2.0-flash-lite) SENGAJA tidak
# dimasukkan lagi: hanya memperlambat setiap permintaan.
GEMINI_MODELS = [
    GEMINI_MODEL_DEFAULT,
    # Terbukti cepat (2,8 dtk) saat model default kena batas kuota.
    "gemini-4-argon",
    # Cadangan terakhir yang juga terbukti menjawab (15 dtk).
    "gemini-3.1-flash-lite",
]

# ---------------------------------------------------------------------
# PENYEDIA KEEMPAT: NVIDIA NIM (build.nvidia.com)
# ---------------------------------------------------------------------
# MENGAPA DITAMBAHKAN
# -------------------
# Kapasitas harian situs dibatasi oleh TOTAL TOKEN dari semua penyedia.
# Setiap penyedia baru yang punya kuota sendiri menambah kapasitas itu,
# dan kapasitas itulah yang menentukan seberapa besar jatah per akun
# boleh dinaikkan. Menambah penyedia = menambah jatah, bukan sekadar
# menambah pilihan model.
#
# KEADAAN GRATISNYA (dicek Nov 2026, jujur apa adanya)
# ---------------------------------------------------
# NVIDIA memberi "trial credits" (~1.000 panggilan) untuk akun Developer
# Program gratis, tanpa kartu kredit. Ini BUKAN kuota harian permanen
# seperti Groq — kreditnya terbatas dan berlaku ±90 hari. Artinya NVIDIA
# cocok sebagai:
#   - jalur cadangan keempat saat Groq + Gemini + OpenRouter habis, dan
#   - sumber model tambahan (GLM, Kimi, DeepSeek, Nemotron) yang bisa
#     dipilih pengguna.
# NVIDIA TIDAK dihitung sebagai kapasitas harian permanen di usage.py,
# karena kreditnya akan habis. Menghitungnya sebagai kapasitas tetap
# akan membuat jatah per akun terlalu tinggi lalu kuota habis mendadak.
#
# Bentuk API-nya kompatibel OpenAI, jadi tidak ada kontrak yang berubah.
# Bila NVIDIA_API_KEY kosong, seluruh bagian ini dilewati.
NVIDIA_API_KEY = _env("NVIDIA_API_KEY")
NVIDIA_BASE_URL = _env(
    "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
).rstrip("/")
NVIDIA_MODEL_DEFAULT = _env("NVIDIA_MODEL", "nvidia/nemotron-3.5-lightning-30b-a3b")

# Model NVIDIA yang boleh dipilih.
#
# CARA DAFTAR INI DISUSUN (penting, jangan dikira tebakan)
# -------------------------------------------------------
# NVIDIA mematikan model lama tanpa pemberitahuan panjang. Saat daftar ini
# pertama dibuat, lima model yang dipakai ternyata SUDAH MATI:
#
#   openai/gpt-oss-120b          -> 410, end of life 3 Sep 2026
#   openai/gpt-oss-20b           -> 410, end of life Nov 2026
#   deepseek-ai/deepseek-v4.1-flash -> 410
#   moonshotai/kimi-2.5          -> 404 (tidak ada)
#   zai-org/glm-5                -> 404 (sudah diganti z-ai/glm-5.3-flash)
#
# Karena itu daftar sekarang diambil dari GET /v1/models milik NVIDIA
# (bisa dilihat tanpa key), lalu tiap kandidat diuji satu per satu:
# 403/401 = model hidup dan bisa dipanggil, 410 = mati, 404 = bukan chat.
# Hasilnya 8 model di bawah, semuanya hidup per 27 Nov 2026.
#
# Bila suatu saat ada yang 410 lagi, server otomatis melewatinya ke
# cadangan (lihat _kandidat_nvidia). Untuk memeriksa ulang daftar model
# yang masih hidup: python cek_key.py nvidia
#
# CATATAN: id di sini sudah unik terhadap penyedia lain. NVIDIA dulu punya
# "openai/gpt-oss-120b" yang sama persis dengan id Groq, dan itu berbahaya
# karena router akan menganggap model Groq milik NVIDIA. Model seperti itu
# kini tidak dipakai lagi (sudah mati), tetapi aturannya tetap: SETIAP id
# harus menunjuk tepat satu penyedia. Dijaga oleh uji_unik_model.py.
NVIDIA_MODELS = [
    # Model penalaran besar; kualitas terbaik, paling lambat.
    "nvidia/nemotron-3-ultra-550b-a55b",
    # Cepat & ringan: cocok jadi default dan cadangan.
    "nvidia/nemotron-3.5-lightning-30b-a3b",
    "nvidia/nemotron-3.5-bolt-e4b",
    # Penalaran + bisa membaca gambar.
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning",
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    # Model pihak ketiga yang tersedia di katalog NVIDIA.
    "moonshotai/kimi-k3.1-pro",
    "z-ai/glm-5.3-flash",
    "minimaxai/minimax-m3.1-flash",
]

# Pemetaan id pilihan-pengguna -> nama model asli di katalog NVIDIA.
#
# Saat ini SEMUA id di atas sudah memakai nama katalog yang benar, jadi
# peta ini kosong. Dibiarkan ada karena masih diperlukan bila nanti ada
# model NVIDIA yang id-nya bentrok dengan penyedia lain: masukkan id
# berawalan "nvidia/" di NVIDIA_MODELS, lalu petakan di sini.
_NVIDIA_NAMA_ASLI: dict = {}


def _nvidia_nama_asli(model: str) -> str:
    """Menerjemahkan id pilihan pengguna menjadi nama model katalog NVIDIA."""
    return _NVIDIA_NAMA_ASLI.get(model, model)

# Model default.
#
# CATATAN PENTING (diperbarui):
#   Model "llama-3.3-70b-versatile" dan "llama-3.1-8b-instant" kini
#   berstatus ENTERPRISE di Groq (harga ContactSales), sehingga TIDAK
#   bisa dipakai dengan API key gratis -> Groq membalas HTTP 404.
#
#   Model yang tersedia untuk key gratis: keluarga OpenAI GPT-OSS.
#   "openai/gpt-oss-120b" -> kualitas terbaik, ~500 token/detik.
MODEL_GROQ_DEFAULT = "openai/gpt-oss-120b"

# Model lama yang sudah tidak bisa dipakai key gratis. Bila nilainya
# masih terpasang di environment (mis. dari deploy sebelumnya), otomatis
# dialihkan ke default baru agar situs tidak mati.
_MODEL_GROQ_USANG = {
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "llama3-70b-8192",
    "llama3-8b-8192",
}


def _model_groq_terpilih() -> str:
    """Menentukan model Groq yang dipakai, dengan pengaman model usang."""
    diminta = _env("GROQ_MODEL")
    if diminta and diminta not in _MODEL_GROQ_USANG:
        return diminta
    return MODEL_GROQ_DEFAULT


GROQ_MODEL = _model_groq_terpilih()

# Daftar model cadangan (semuanya tersedia untuk API key gratis).
# Dipakai otomatis bila model utama dibalas HTTP 404 oleh Groq.
_MODEL_GROQ_CADANGAN = [
    MODEL_GROQ_DEFAULT,        # openai/gpt-oss-120b -> kualitas terbaik
    "openai/gpt-oss-20b",      # lebih cepat, ringan
    "qwen/qwen3.8-27b",        # preview, alternatif
]

# ---------------------------------------------------------------------
# DAFTAR MODEL YANG BOLEH DIPILIH (allowlist)
# ---------------------------------------------------------------------
# Pemilihan model dikirim klien memakai NAMA MODEL ASLI (sesuai permintaan
# pemilik situs). Yang dijaga di sini bukan kerahasiaan nama, melainkan
# BATASAN: klien tidak bisa memaksa server memakai model di luar daftar.
#
# CATATAN PENTING (per 16 Agustus 2026):
#   "llama-3.3-70b-versatile" dan "llama-3.1-8b-instant" sudah DIMATIKAN
#   Groq untuk akun gratis/developer - kini Enterprise (berbayar kontrak).
#   Karena itu keduanya TIDAK dimasukkan: memakainya hanya menghasilkan
#   error. Penggantinya: openai/gpt-oss-120b / -20b.
#   Lihat console.groq.com/docs/deprecations
#
# Menambah/mengganti model: cukup ubah list di bawah.
MODEL_GROQ_DIIZINKAN = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
]
MODEL_DIIZINKAN = (
    MODEL_GROQ_DIIZINKAN + OPENROUTER_MODELS + GEMINI_MODELS + NVIDIA_MODELS
)

# Model yang dipakai bila klien tidak mengirim pilihan / mengirim nilai
# di luar daftar.
MODEL_DEFAULT_PILIHAN = "openai/gpt-oss-120b"

# ---------------------------------------------------------------------
# KEMAMPUAN KHUSUS PER MODEL
# ---------------------------------------------------------------------
# Tidak semua model bisa melakukan semua hal. Dua daftar di bawah adalah
# SATU-SATUNYA sumber kebenaran, dan sengaja di sisi server supaya
# perilakunya tetap benar walau frontend diubah orang lain.
#
# 1. MODEL_VISION — bisa "melihat" gambar.
#    Per dokumentasi Groq (console.groq.com/docs/vision), dari model
#    gratis hanya qwen/qwen3.8-27b yang multimodal. Model GPT-OSS
#    TIDAK bisa menerima gambar: bila dikirimi gambar, Groq membalas
#    error 400. Karena itu server otomatis memindahkan permintaan
#    bergambar ke model vision, bukan membiarkannya gagal.
MODEL_VISION = {
    "qwen/qwen3.8-27b",
    "google/gemini-2.5-flash-tts",
    "google/gemini-3.1-flash-lite",
    # Model Gemini asli (penyedia cadangan). Semua Gemini multimodal.
    # Daftar ini harus selaras dengan GEMINI_MODELS di atas.
    "gemini-3.5-flash-lite",
    "gemini-4-argon",
    "gemini-3.1-flash-lite",
    # Model OpenRouter :free yang multimodal (bisa membaca gambar).
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "inclusionai/ling-3.2-flash:free",
    "particle-ai/particle-1:free",
    # Model NVIDIA NIM yang multimodal (varian VL = vision-language).
    "nvidia/nemotron-3.5-super-vl-120b-a12b",
    "zai-org/glm-5",
}

# Model yang dipakai bila pesan berisi gambar tetapi pilihan pengguna
# bukan model vision.
MODEL_VISION_DEFAULT = "qwen/qwen3.8-27b"

# 2. MODEL_BROWSER — model yang SECARA TEKNIS punya tool `browser_search`
#    bawaan Groq. Dulu daftar ini menentukan siapa yang bisa riset,
#    sehingga model lain sama sekali tidak bisa. Sekarang riset dikerjakan
#    di server (riset.py) untuk SEMUA model, jadi daftar ini hanya
#    dipertahankan sebagai catatan/dokumentasi dan tidak dipakai untuk
#    mengganti model lagi.
MODEL_BROWSER = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
}

# Tidak dipakai lagi (riset tidak memaksa ganti model). Dipertahankan agar
# impor/uji lama yang menyebut nama ini tidak error.
MODEL_BROWSER_DEFAULT = "openai/gpt-oss-120b"


def model_dari_pilihan(pilihan: Optional[str]) -> str:
    """
    Memvalidasi pilihan model dari klien.

    Nilai yang TIDAK ada di MODEL_DIIZINKAN (termasuk None, string kosong,
    atau model berbayar seperti llama-3.3-70b-versatile yang sudah mati
    untuk akun gratis) akan DIABAIKAN dan diganti model default. Ini
    mencegah klien memakai model di luar daftar yang diizinkan - baik
    karena tidak tersedia maupun karena berbayar.
    """
    kunci = (pilihan or "").strip()
    if kunci in MODEL_DIIZINKAN:
        return kunci

    # Nama lama yang sudah mati: beri peringatan jelas di log agar tidak
    # membingungkan saat menelusuri masalah.
    if kunci in _MODEL_GROQ_USANG:
        logger.warning(
            "Model %r sudah tidak tersedia untuk akun gratis (Enterprise). "
            "Memakai %s.",
            kunci,
            MODEL_DEFAULT_PILIHAN,
        )
    elif pilihan:
        logger.warning(
            "Pilihan model tidak dikenal (%r) - memakai %s.",
            pilihan,
            MODEL_DEFAULT_PILIHAN,
        )
    return MODEL_DEFAULT_PILIHAN


def model_untuk_permintaan(
    pilihan: Optional[str],
    ada_gambar: bool = False,
    penelitian: bool = False,
) -> tuple[str, Optional[str]]:
    """
    Memilih model yang BENAR-BENAR dipakai, sesuai kebutuhan permintaan.

    Aturan:
      - Ada gambar  -> model harus multimodal (MODEL_VISION).
      - Riset       -> TIDAK memengaruhi pilihan model (dikerjakan server).
      - Selain itu  -> hormati pilihan pengguna apa adanya.

    Bila pilihan pengguna tidak memenuhi syarat, model diganti otomatis
    dan dikembalikan catatan penyesuaian, sehingga UI bisa memberi tahu
    pengguna dengan jujur alih-alih membiarkan permintaan gagal dengan
    error 400 dari penyedia.

    Parameter `penelitian` masih diterima demi kompatibilitas pemanggil
    lama, tetapi tidak lagi dipakai untuk berpindah model.

    Mengembalikan: (nama_model, catatan_penyesuaian_atau_None)
    """
    dipilih = model_dari_pilihan(pilihan)
    model = dipilih

    # CATATAN PENTING (diperbarui):
    #   Riset TIDAK lagi memaksa ganti model. Riset dikerjakan di server
    #   (lihat riset.py) sehingga SEMUA model bisa riset dengan kualitas
    #   yang sama. Pengguna tidak perlu berpindah model hanya untuk
    #   mencari informasi di web.
    #
    #   Model tetap hanya diganti bila ada GAMBAR dan modelnya tidak
    #   multimodal — karena itu keterbatasan nyata penyedia (mengirim
    #   gambar ke model teks akan ditolak dengan error 400).
    if ada_gambar and model not in MODEL_VISION:
        logger.info(
            "Gambar dilampirkan tetapi model %s bukan model vision. "
            "Beralih ke %s.",
            model,
            MODEL_VISION_DEFAULT,
        )
        model = MODEL_VISION_DEFAULT

    return model, _catatan_penyesuaian(model, dipilih, ada_gambar, penelitian)


def _catatan_penyesuaian(
    model_final: str,
    dipilih: str,
    ada_gambar: bool,
    penelitian: bool,  # dipertahankan agar pemanggil lama tetap jalan
) -> Optional[str]:
    """
    Menjelaskan ke pengguna mengapa modelnya diganti (bahasa awam).

    Catatan: riset web TIDAK lagi menjadi alasan penggantian model. Riset
    dikerjakan di server (riset.py) untuk semua model, jadi pesan lama
    "belum mendukung riset web" tidak boleh muncul lagi.
    """
    if model_final == dipilih:
        return None

    if model_final in MODEL_VISION:
        return (
            f"Model {dipilih} belum bisa membaca gambar, jadi permintaan ini "
            f"otomatis diproses oleh {model_final}."
        )

    return (
        f"Model {dipilih} belum mendukung permintaan ini, jadi diproses "
        f"oleh {model_final}."
    )


def opsi_model_aktif() -> str:
    """
    panel Usage.

    Panel Usage bersifat global (bukan per pengguna), jadi dipakai model
    yang terakhir tercatat - atau model default bila belum ada. Batas
    kuota model gratis saat ini identik, sehingga angkanya tetap benar
    walau dua pengguna memilih model berbeda.
    """
    terakhir = usage.model_terakhir()
    if terakhir:
        return terakhir
    if PROVIDER == "groq":
        return MODEL_DEFAULT_PILIHAN
    return OLLAMA_MODEL


# ---- Ollama (lokal) ----
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "deepseek-r1:7b")

# ---- Timeout ----
# Groq cepat; Ollama lokal di CPU bisa sangat lambat.
# Vercel Hobby membatasi total eksekusi ~10-60 detik, jadi default
# Groq diturunkan agar tidak menggantung melewati batas fungsi.
TIMEOUT_GROQ = _env_float("TIMEOUT_GROQ", 60)
TIMEOUT_OLLAMA = _env_float("TIMEOUT_OLLAMA", 300)
# Gemini bisa lebih lambat saat "thinking"; beri ruang lebih lega, tetapi
# tetap di bawah batas fungsi Vercel agar tidak menggantung.
TIMEOUT_GEMINI = _env_float("TIMEOUT_GEMINI", 90)

# ---------------------------------------------------------------------
# TIMEOUT KHUSUS STREAMING (PENTING: PENYEBAB JAWABAN TERPOTONG)
# ---------------------------------------------------------------------
# `httpx.AsyncClient(timeout=60)` memberi batas 60 detik untuk SETIAP
# operasi baca. Pada respons streaming, itu berarti: bila model butuh
# lebih dari 60 detik untuk menyelesaikan jawaban, koneksi DIPUTUS di
# tengah kalimat — padahal teks sudah mulai mengalir ke pengguna.
#
# Jawaban panjang (riset, penjelasan rinci) sangat mudah melewati 60
# detik. Akibatnya pengguna melihat jawaban "setengah" lalu harus
# mengetik "lanjut", yang memakan satu jatah pesan lagi. Inilah sumber
# keluhan "jawaban kepotong" selain batas max_tokens.
#
# Perbaikannya: saat streaming, batas WAKTUNGGU (connect/pool) tetap
# ketat, tetapi batas BACA dibuat longgar. Yang penting bukan "seluruh
# jawaban selesai dalam N detik", melainkan "tidak ada jeda mati lebih
# dari N detik". Jawaban boleh berjalan selama tokennya masih mengalir.
TIMEOUT_STREAM = httpx.Timeout(
    connect=15.0,      # menyambung ke penyedia
    read=120.0,        # jeda maksimum antar-potongan (BUKAN total durasi)
    write=30.0,        # mengirim permintaan
    pool=15.0,         # menunggu koneksi bebas
)

# ---- CORS ----
# Daftar origin tambahan dipisah koma, mis:
#   ALLOWED_ORIGINS=https://gungdev.vercel.app,https://gungdev.com
# Nilai "*" berarti izinkan semua origin (dipakai bila API dan UI
# berada di domain berbeda dan Anda tidak mau mengurus daftar).
_extra_origins = [
    o.strip() for o in _env("ALLOWED_ORIGINS").split(",") if o.strip()
]
_allow_all = "*" in _extra_origins
if _allow_all:
    _extra_origins = [o for o in _extra_origins if o != "*"]

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("gungdev-backend")


# ---------------------------------------------------------------------
# 3. PEMILIHAN PROVIDER
# ---------------------------------------------------------------------
def pilih_provider() -> str:
    """
    Menentukan provider aktif dari environment atau ketersediaan key.

    AI_PROVIDER (bila diisi) MENANG atas segalanya — ini disengaja agar
    pemilik situs bisa mengunci pilihan. Tetapi kalau nilai itu menunjuk
    penyedia yang kuncinya tidak ada, situs akan mati. Karena itu nilai
    yang tidak mungkin dijalankan DIABAIKAN, dan penyedia yang kuncinya
    benar-benar tersedia yang dipakai.
    """
    dipaksa = _env("AI_PROVIDER").lower()
    if dipaksa == "groq" and not GROQ_API_KEY:
        logger.warning(
            "AI_PROVIDER=groq tetapi GROQ_API_KEY kosong; pilihan diabaikan."
        )
        dipaksa = ""
    elif dipaksa == "openrouter" and not OPENROUTER_API_KEY:
        logger.warning(
            "AI_PROVIDER=openrouter tetapi OPENROUTER_API_KEY kosong; "
            "pilihan diabaikan."
        )
        dipaksa = ""
    elif dipaksa == "gemini" and not GEMINI_API_KEY:
        logger.warning(
            "AI_PROVIDER=gemini tetapi GEMINI_API_KEY kosong; pilihan diabaikan."
        )
        dipaksa = ""

    if dipaksa in ("groq", "openrouter", "gemini", "ollama"):
        return dipaksa
    if GROQ_API_KEY:
        return "groq"
    if GEMINI_API_KEY:
        return "gemini"
    if OPENROUTER_API_KEY:
        return "openrouter"
    return "ollama"


PROVIDER = pilih_provider()
MODEL_NAME = (
    GROQ_MODEL if PROVIDER == "groq" else
    OPENROUTER_MODEL_DEFAULT if PROVIDER == "openrouter" else OLLAMA_MODEL
)

if PROVIDER == "groq":

    logger.info("Provider aktif: GROQ (%s) model %s", GROQ_BASE_URL, MODEL_NAME)
    if not GROQ_API_KEY:
        logger.warning(
            "AI_PROVIDER=groq tetapi GROQ_API_KEY kosong. "
            "Permintaan akan gagal dengan HTTP 401."
        )
elif PROVIDER == "openrouter":
    logger.info("Provider aktif: OpenRouter model %s", MODEL_NAME)
    if not OPENROUTER_API_KEY:
        logger.warning("AI_PROVIDER=openrouter tetapi OPENROUTER_API_KEY kosong.")
else:
    logger.info("Provider aktif: OLLAMA lokal (%s) model %s", OLLAMA_HOST, MODEL_NAME)


# ---------------------------------------------------------------------
# 4. SKEMA DATA
# ---------------------------------------------------------------------
class ChatRequest(BaseModel):
    """
    Body JSON untuk /chat dan /chat/stream.

    Field lama tetap sama persis (kompatibel):
        {"message": "Halo!"}
    """
    message: str = Field(..., min_length=1, max_length=8000, description="Pesan dari user")
    history: List[dict] = Field(
        default_factory=list,
        description="Riwayat percakapan lama, format: [{role, content}, ...]",
    )
    system_prompt: Optional[str] = Field(None, description="Instruksi kustom pengguna")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Kreativitas jawaban")
    max_tokens: Optional[int] = Field(None, ge=16, le=8192, description="Panjang maksimum jawaban")
    # Pilihan model dari UI, berisi NAMA MODEL ASLI (mis.
    # "openai/gpt-oss-120b"). Server memvalidasinya terhadap
    # MODEL_DIIZINKAN; nilai di luar daftar diganti model default.
    model: Optional[str] = Field(None, max_length=64, description="Pilihan model dari UI")

    # --- Lampiran (semua opsional; body lama tetap sah) ---

    # Gambar sebagai data URL base64: "data:image/png;base64,...".
    # Maks 3 gambar (batas Groq). Hanya diproses model vision; bila model
    # yang dipilih bukan model vision, server otomatis mengalihkannya.
    images: List[str] = Field(
        default_factory=list,
        description="Gambar dalam format data URL base64 (maks 3)",
    )

    # File yang isinya SUDAH diekstrak jadi teks di browser, format:
    #   [{"name": "laporan.pdf", "text": "..."}]
    #
    # Kenapa diekstrak di browser: agar tidak perlu mengunggah file biner
    # besar ke serverless function (batas body Vercel 4,5 MB), dan agar
    # PDF/gambar-scan bisa dibaca memakai pustaka yang sudah ada di
    # browser. Backend tetap mengekstrak sendiri bila klien hanya
    # mengirim base64 mentah (lihat `file_base64`).
    files: List[dict] = Field(
        default_factory=list,
        description="File berupa teks hasil ekstraksi: [{name, text}]",
    )

    # Jalur cadangan: file biner base64 yang diekstrak di SERVER.
    # Format: [{"name": "laporan.pdf", "data": "<base64>"}]
    # Berguna untuk klien non-browser / API langsung.
    file_base64: List[dict] = Field(
        default_factory=list,
        description="File biner base64 untuk diekstrak di server: [{name, data}]",
    )

    # Paksa riset web LEBIH DALAM. Riset biasa sudah berjalan otomatis
    # untuk semua model; flag ini hanya menambah kedalaman (lebih banyak
    # sumber + putaran lanjutan).
    research: bool = Field(
        False,
        description="True = paksa riset web lebih dalam sebelum menjawab",
    )


class ChatResponse(BaseModel):
    """
    Response /chat (kontrak lama, tidak berubah): {"reply": "..."}

    `sumber` adalah field TAMBAHAN yang hanya muncul bila AI melakukan
    riset web. Isinya daftar sumber ringkas untuk kartu sumber di UI.
    Klien lama yang hanya membaca `reply` tidak terpengaruh.
    """
    reply: str
    sumber: Optional[List[dict]] = None


class HealthResponse(BaseModel):
    """Response /health â€” menambah info provider tanpa merusak field 'status'."""
    status: str
    provider: str
    model: str


# ---------------------------------------------------------------------
# 4b. SKEMA DATA: RIWAYAT PERCAKAPAN DI SERVER
# ---------------------------------------------------------------------
class SesiSimpan(BaseModel):
    """Body POST /api/sessions — menyimpan satu sesi percakapan."""
    session: dict = Field(..., description="Satu objek sesi lengkap")


class SesiBanyak(BaseModel):
    """
    Body POST /api/sessions/sync — menyimpan beberapa sesi sekaligus.

    Dipakai sekali saat pengguna login pertama kali di perangkat yang
    sudah punya riwayat lokal: salinan perangkat dikirim ke server agar
    tidak hilang.
    """
    sessions: List[dict] = Field(default_factory=list, description="Daftar sesi")


class SesiAktif(BaseModel):
    """Body POST /api/sessions/active — sesi yang sedang dibuka."""
    activeId: Optional[str] = Field(None, description="ID sesi aktif, atau null")


async def identitas_pemanggil(authorization: Optional[str]) -> Optional[dict]:
    """
    Membaca header `Authorization: Bearer <ID token Google>` dan
    memverifikasinya ke Google.

    Mengembalikan payload akun (berisi `sub`) atau None bila header
    tidak ada / token tidak sah.

    PENTING: `sub` yang dipakai sebagai kunci penyimpanan SELALU berasal
    dari jawaban Google yang sudah diverifikasi, bukan dari isi body
    permintaan. Dengan begitu tidak ada cara bagi pengguna untuk mengaku
    sebagai akun orang lain.
    """
    if not authorization:
        return None

    teks = authorization.strip()
    if teks.lower().startswith("bearer "):
        teks = teks[7:].strip()

    return await identitas.verifikasi_token(teks)


# ---------------------------------------------------------------------
# 5. SYSTEM PROMPT & DEFAULT MODEL PARAMETER
# ---------------------------------------------------------------------
DEFAULT_SYSTEM_PROMPT = (
    "Kamu adalah GungDev, asisten AI berbahasa Indonesia yang ramah, akurat, dan "
    "jelas. Jawab dalam bahasa yang digunakan pengguna. Jika tidak yakin dengan "
    "sebuah fakta, katakan terus terang, jangan mengarang. Gunakan format Markdown "
    "seperlunya. Jawab langsung ke inti tanpa basa-basi berlebihan."
)

DEFAULT_TEMPERATURE = 0.4

# Batas panjang jawaban.
#
# MENGAPA DINAIKKAN DARI 2048
# ---------------------------
# 2048 token terlalu pendek untuk permintaan riset / penjelasan panjang.
# Model berhenti di tengah kalimat ("kepotong"), dan pengguna harus
# mengirim prompt "lanjut" — yang MEMAKAN SATU JATAH PESAN LAGI padahal
# jawabannya belum selesai. Jadi batas kecil bukan penghematan, justru
# pemborosan jatah.
#
# 4096 cukup untuk jawaban panjang tanpa menabrak batas penyedia:
#   - Groq gratis : 8.000 token/menit. Jawaban 4096 masih muat.
#   - Gemini      : output maksimum jauh di atas 4096.
#   - OpenRouter  : menyesuaikan modelnya sendiri.
# Masih di bawah batas `le=8192` di ChatRequest, jadi UI tetap sah.
DEFAULT_MAX_TOKENS = 4096

# Saat riset web, jawaban biasanya lebih panjang (rangkuman + sumber).
# Beri ruang lebih lega supaya tidak terpotong.
MAX_TOKENS_RISET = 4096


def build_messages(
    message: str,
    history: Optional[Sequence[dict]] = None,
    system_prompt: Optional[str] = None,
    images: Optional[Sequence[str]] = None,
    blok_lampiran: str = "",
) -> List[dict]:
    """
    Menyusun [system] + [riwayat 20 terakhir] + [pesan baru].

    Pesan baru berisi `message` + blok isi file (bila ada). Bila ada
    gambar, isi pesan diubah menjadi format multimodal OpenAI:

        {"role": "user", "content": [
            {"type": "text", "text": "..."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
        ]}

    Riwayat lama TIDAK ikut membawa gambar (hanya teks). Ini disengaja:
    gambar berukuran besar per pesan akan cepat menghabiskan kuota token,
    dan model hanya perlu melihat gambar pada giliran pertanyaannya.
    """
    messages: List[dict] = [
        {"role": "system", "content": (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()}
    ]

    for item in list(history or [])[-20:]:
        try:
            role = item.get("role")
            content = item.get("content")
        except AttributeError:
            continue
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content})

    teks_final = f"{message}{blok_lampiran}"
    daftar_gambar = [g for g in (images or []) if isinstance(g, str) and g.strip()]

    if not daftar_gambar:
        messages.append({"role": "user", "content": teks_final})
        return messages

    isi: List[dict] = [{"type": "text", "text": teks_final}]
    for url in daftar_gambar:
        isi.append({"type": "image_url", "image_url": {"url": url}})
    messages.append({"role": "user", "content": isi})
    return messages


def resolve_options(request: ChatRequest) -> dict:
    """
    Menentukan model, temperature, & batas token final.

    Model dipilih dengan mempertimbangkan isi permintaan: gambar butuh
    model vision. Riset web TIDAK lagi mengubah pilihan model, karena
    riset dikerjakan di server dan berlaku untuk semua model. Bila
    pilihan pengguna tidak memenuhi syarat (mis. gambar), model diganti
    otomatis dan `penyesuaian` berisi penjelasan untuk pengguna.
    """
    ada_gambar = bool(request.images)
    model, penyesuaian = model_untuk_permintaan(
        request.model,
        ada_gambar=ada_gambar,
        penelitian=bool(request.research),
    )
    return {
        "model": model,
        "penyesuaian": penyesuaian,
        "temperature": (
            request.temperature
            if request.temperature is not None
            else DEFAULT_TEMPERATURE
        ),
        "max_tokens": (
            request.max_tokens
            if request.max_tokens is not None
            else DEFAULT_MAX_TOKENS
        ),
    }


def siapkan_lampiran(request: ChatRequest) -> tuple[str, List[str]]:
    """
    Mengubah lampiran pada request menjadi (blok_teks, daftar_gambar).

    Tiga sumber digabung:
      1. `files`       -> teks yang sudah diekstrak di browser (paling umum)
      2. `file_base64` -> file biner yang diekstrak di server (klien API)
      3. `images`      -> data URL gambar, diteruskan ke model vision

    Semua kesalahan dilaporkan sebagai HTTP 400 dengan pesan Bahasa
    Indonesia yang jelas, supaya pengguna tahu file mana yang bermasalah.
    """
    hasil: List[dict] = []

    # --- 1. Teks yang sudah diekstrak klien ---
    for item in request.files[: lampiran.MAKS_JUMLAH_FILE]:
        if not isinstance(item, dict):
            continue
        nama = str(item.get("name") or "lampiran").strip()[:120]
        teks = item.get("text")

        # Klien bisa mengirim string mentah; samakan bentuknya.
        if isinstance(teks, (list, dict)):
            teks = json.dumps(teks, ensure_ascii=False)
        teks = "" if teks is None else str(teks)

        if not teks.strip():
            continue

        teks = teks.replace("\r\n", "\n").strip()
        terpotong = len(teks) > lampiran.MAKS_KARAKTER_PER_FILE
        if terpotong:
            teks = teks[: lampiran.MAKS_KARAKTER_PER_FILE]

        hasil.append(
            {
                "nama": nama,
                "teks": teks,
                "terpotong": terpotong,
                "jenis": str(item.get("type") or "teks")[:40],
            }
        )

    # --- 2. File biner yang diekstrak server ---
    for item in request.file_base64[: lampiran.MAKS_JUMLAH_FILE]:
        if not isinstance(item, dict):
            continue
        nama = str(item.get("name") or "lampiran").strip()[:120]
        data_b64 = item.get("data")
        if not isinstance(data_b64, str) or not data_b64.strip():
            continue
        try:
            mentah = base64.b64decode(data_b64, validate=False)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=400,
                detail=f"File '{nama}' tidak dapat dibaca (base64 tidak valid).",
            ) from exc

        try:
            hasil.append(lampiran.ekstrak_file(nama, mentah))
        except lampiran.LampiranError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # --- 3. Gambar ---
    try:
        gambar = lampiran.validasi_gambar(request.images)
    except lampiran.LampiranError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if hasil:
        logger.info("Lampiran diproses: %s", lampiran.ringkas_untuk_log(hasil))
    if gambar:
        logger.info("%d gambar dilampirkan.", len(gambar))

    return lampiran.susun_blok_lampiran(hasil), gambar


# ---------------------------------------------------------------------
# 6. INSTANCE APLIKASI FASTAPI
# ---------------------------------------------------------------------
app = FastAPI(
    title="GungDev Backend",
    description="Backend GungDev.",
    version="2.1.0",
)


# ---------------------------------------------------------------------
# 7. CORS MIDDLEWARE
# ---------------------------------------------------------------------
# allow_origins       = development & domain yang didaftarkan manual
# allow_origin_regex  = SEMUA subdomain Vercel (preview & production),
#                       karena browser tidak mendukung wildcard "https://*.vercel.app".
app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        ["*"]
        if _allow_all
        else [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:4173",   # vite preview
            "http://127.0.0.1:4173",
            *_extra_origins,
        ]
    ),
    allow_origin_regex=r"https://([a-zA-Z0-9-]+\.)*vercel\.app",
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
    max_age=86400,   # cache preflight 24 jam -> lebih cepat
)


# ---------------------------------------------------------------------
# 8. FUNGSI PEMBANTU: ERROR -> HTTPException YANG RAMAH
# ---------------------------------------------------------------------
def pesan_error_http(status: int, detail_asli: str = "") -> str:
    """Menerjemahkan status HTTP provider menjadi pesan Bahasa Indonesia."""
    if status == 400:
        # Alasan asli dari penyedia sangat penting untuk menelusuri
        # masalah format (mis. gambar ditolak). Tercatat di log server;
        # pengguna tetap menerima pesan yang mudah dimengerti.
        if detail_asli:
            logger.error("HTTP 400 dari provider: %s", detail_asli)
            # Bila masalahnya soal gambar/media, beri pesan yang lebih
            # spesifik agar pengguna tahu apa yang harus dilakukan.
            rendah = detail_asli.lower()
            if any(k in rendah for k in ("image", "media", "vision", "modal")):
                return (
                    "Gambar tidak dapat diproses. Coba gunakan JPG/PNG "
                    "berukuran lebih kecil, atau pilih model yang bisa "
                    "membaca gambar."
                )
        return "Permintaan tidak valid. Coba ubah atau pendekkan pesan Anda."
    if status in (401, 403):
        if PROVIDER == "groq":
            return (
                "API key Groq tidak valid atau sudah dicabut. Periksa variabel "
                "GROQ_API_KEY di server."
            )
        return (
            "Ollama menolak permintaan. Pastikan backend memakai Ollama lokal "
            f"di {OLLAMA_HOST} (tanpa API key)."
        )
    if status == 404:
        if PROVIDER == "groq":
            return f"Model '{MODEL_NAME}' tidak tersedia di Groq. Ganti GROQ_MODEL."
        return (
            f"Model '{MODEL_NAME}' tidak ditemukan di Ollama. "
            f"Unduh dulu dengan: ollama pull {MODEL_NAME}"
        )
    if status == 413:
        return "Pesan terlalu panjang. Coba persingkat."
    if status == 422:
        return "Format permintaan tidak sesuai."
    if status == 429:
        if PROVIDER == "groq":
            return (
                "Kuota gratis Groq sedang tercapai. Ini biasanya pulih dalam "
                "beberapa detik sampai satu menit. Tunggu sebentar lalu coba lagi."
            )
        return "Terlalu banyak permintaan. Coba lagi beberapa saat lagi."
    if status == 503:
        if PROVIDER == "groq":
            return "Layanan Groq sedang sibuk. Coba lagi sebentar lagi."
        return (
            f"Tidak dapat terhubung ke Ollama di {OLLAMA_HOST}. "
            "Pastikan aplikasi Ollama berjalan ('ollama serve')."
        )
    if status == 504:
        return "Waktu tunggu habis. Model mungkin masih memproses ΓÇö coba lagi."
    if 500 <= status < 600:
        return f"Layanan AI sedang bermasalah (HTTP {status}). Coba lagi nanti."
    return detail_asli or f"Terjadi kesalahan pada layanan AI (HTTP {status})."


def ke_http_exception(exc: Exception) -> HTTPException:
    """Mengubah exception apa pun menjadi HTTPException yang informatif."""
    # Error HTTP dari httpx (Groq membalas 4xx/5xx)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail_asli = ""
        try:
            body = exc.response.json()
            detail_asli = (
                body.get("error", {}).get("message")
                if isinstance(body.get("error"), dict)
                else str(body.get("error") or "")
            )
        except Exception:  # noqa: BLE001
            detail_asli = exc.response.text[:200]
        logger.error("Provider membalas HTTP %s: %s", status, detail_asli)
        return HTTPException(status_code=502, detail=pesan_error_http(status, detail_asli))

    if isinstance(exc, httpx.TimeoutException) or isinstance(exc, TimeoutError):
        return HTTPException(
            status_code=504,
            detail="Waktu tunggu habis saat menghubungi layanan AI. Coba lagi.",
        )

    if isinstance(exc, httpx.RequestError):
        pesan = str(exc).lower()
        if PROVIDER == "groq":
            return HTTPException(
                status_code=503,
                detail="Tidak dapat menghubungi Groq. Periksa koneksi internet server.",
            )
        if "connection" in pesan or "connect" in pesan or "getaddrinfo" in pesan:
            return HTTPException(
                status_code=503,
                detail=(
                    f"Tidak dapat terhubung ke Ollama di {OLLAMA_HOST}. "
                    "Pastikan aplikasi Ollama sudah berjalan ('ollama serve')."
                ),
            )
        return HTTPException(status_code=503, detail=f"Gagal menghubungi layanan AI: {exc}")

    logger.error("Kesalahan tak terduga: %s", exc)
    return HTTPException(
        status_code=502,
        detail="Terjadi kesalahan saat memproses jawaban. Silakan coba lagi.",
    )


# ---------------------------------------------------------------------
# 9. PEMANGGILAN KE GROQ (OpenAI-compatible)
# ---------------------------------------------------------------------
def _groq_headers() -> dict:
    return {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }


def _groq_payload(model: str, messages: List[dict], opsi: dict, streaming: bool) -> dict:
    """
    Menyusun body permintaan ke Groq.

    Riset web TIDAK lagi memakai tool bawaan Groq `browser_search`.
    Alasan: tool itu hanya tersedia untuk keluarga GPT-OSS, sehingga
    model lain tidak bisa riset sama sekali — dan itulah yang membuat
    riset terasa "tidak nyata". Sekarang riset dikerjakan di server
    (lihat riset.py + lakukan_riset_server), sehingga SEMUA model di
    semua penyedia mendapat kualitas riset yang sama.

    Yang tetap dipakai dari pengaturan riset: batas token lebih besar,
    karena jawaban riset biasanya panjang dan rinci. Tanpa ini jawaban
    terpotong di tengah.

    Catatan: dokumentasi Groq selalu memakai `temperature=1, top_p=1`
    pada contoh vision. Nilai itu dipakai untuk permintaan bergambar
    agar sesuai anjuran resmi.
    """
    payload = {
        "model": model,
        "messages": messages,
        "temperature": opsi["temperature"],
        "max_completion_tokens": opsi["max_tokens"],
        "stream": streaming,
    }

    # Saat streaming, Groq tidak mengirim angka token kecuali diminta.
    # Tanpa ini pencatatan jatah token hanya bisa menebak dari panjang
    # teks, sehingga angka di panel Usage tidak akurat.
    if streaming:
        payload["stream_options"] = {"include_usage": True}

    if opsi.get("penelitian") or opsi.get("perlu_riset"):
        # Jawaban riset panjang dan rinci; beri ruang token lebih besar
        # agar tidak terpotong di tengah.
        payload["max_completion_tokens"] = max(
            opsi["max_tokens"], MAX_TOKENS_RISET
        )

    return payload


def _teks_dari_pesan(pesan: dict) -> str:
    """
    Mengambil teks jawaban dari satu objek message Groq.

    Model dengan tool kadang mengembalikan `content` kosong dan
    menaruh hasilnya di `reasoning`/`annotations`. Kita tetap
    mengutamakan `content`, lalu memakai cadangan bila kosong.
    """
    isi = pesan.get("content")
    if isinstance(isi, str) and isi.strip():
        return isi.strip()

    # Sebagian respons membungkus konten dalam list (format multimodal).
    if isinstance(isi, list):
        bagian = [
            b.get("text", "")
            for b in isi
            if isinstance(b, dict) and isinstance(b.get("text"), str)
        ]
        gabung = "".join(bagian).strip()
        if gabung:
            return gabung

    cadangan = pesan.get("reasoning")
    if isinstance(cadangan, str) and cadangan.strip():
        return cadangan.strip()

    return ""


def _openrouter_headers() -> dict:
    return {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": OPENROUTER_SITE_URL,
        "X-Title": OPENROUTER_APP_NAME,
    }


def _openrouter_payload(model: str, messages: List[dict], opsi: dict, streaming: bool) -> dict:
    payload = {
        "model": model,
        "messages": messages,
        "temperature": opsi["temperature"],
        "max_tokens": opsi["max_tokens"],
        "stream": streaming,
    }
    # Meminta usage pada chunk terakhir agar panel token mendapat angka resmi
    # OpenRouter bila endpoint/model menyediakannya.
    if streaming:
        payload["stream_options"] = {"include_usage": True}
    if opsi.get("perlu_riset") or opsi.get("penelitian"):
        # Riset dikerjakan di server untuk semua penyedia, jadi tidak ada
        # tool yang perlu dikirim ke OpenRouter. Jawaban riset panjang,
        # jadi ruang tokennya diperbesar.
        payload["max_tokens"] = max(opsi["max_tokens"], MAX_TOKENS_RISET)
    return payload


def _kandidat_openrouter(model: str, ada_gambar: bool) -> List[str]:
    """
    Daftar model yang dicoba berurutan untuk OpenRouter.

    Mengapa perlu cadangan: model berbayar (Gemini/DeepSeek) akan
    ditolak dengan HTTP 402 bila kredit key habis. Tanpa cadangan,
    pengguna hanya melihat error dan Activity OpenRouter tetap nol
    karena tidak ada permintaan yang berhasil. Dengan cadangan ini,
    permintaan otomatis dialihkan ke model :free sehingga chat tetap
    jalan tanpa biaya.

    Bila permintaan memuat GAMBAR, hanya model vision yang dicoba —
    mengirim gambar ke model teks hanya menghasilkan error 400.
    """
    utama = model or OPENROUTER_MODEL_DEFAULT
    kandidat = [utama]
    for m in OPENROUTER_CADANGAN:
        if m == utama:
            continue
        if ada_gambar and m not in MODEL_VISION:
            continue
        kandidat.append(m)
    return kandidat


def _pesan_openrouter_error(status: int, teks: str, model: str) -> HTTPException:
    """Menerjemahkan error OpenRouter menjadi pesan yang berguna."""
    rendah = (teks or "").lower()
    if status == 402 or "insufficient" in rendah or "credit" in rendah:
        return HTTPException(
            status_code=503,
            detail=(
                "Kredit layanan AI sedang tidak tersedia. Coba lagi nanti, "
                "atau pilih model lain dari menu model."
            ),
        )
    if status == 401:
        return HTTPException(
            status_code=502,
            detail="Layanan AI menolak kunci akses. Hubungi pemilik situs.",
        )
    if status == 404:
        return HTTPException(
            status_code=502,
            detail=f"Model '{model}' tidak tersedia. Pilih model lain dari menu.",
        )
    if status == 429:
        return HTTPException(
            status_code=429,
            detail="Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.",
        )
    return HTTPException(
        status_code=502,
        detail="Layanan AI sedang sibuk. Silakan coba lagi sebentar lagi.",
    )


async def openrouter_complete(messages: List[dict], opsi: dict) -> str:
    """
    Meminta jawaban lengkap ke OpenRouter, dengan cadangan model gratis.

    Bila model utama menolak karena kredit habis (402) atau model tidak
    ada (404), permintaan dicoba dengan model :free berikutnya. Ini yang
    membuat GungDev tetap bisa dipakai tanpa biaya.
    """
    utama = opsi.get("model") or OPENROUTER_MODEL_DEFAULT
    kandidat = _kandidat_openrouter(utama, bool(opsi.get("ada_gambar")))
    error_terakhir: Optional[HTTPException] = None

    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
        for model in kandidat:
            res = await http.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=_openrouter_headers(),
                json=_openrouter_payload(model, messages, opsi, False),
            )

            if res.status_code >= 400:
                sebab = res.text[:300]
                logger.warning(
                    "OpenRouter menolak %s: HTTP %s %s", model, res.status_code, sebab
                )
                error_terakhir = _pesan_openrouter_error(res.status_code, sebab, model)
                # Hanya masalah model/kredit yang layak dicoba ulang.
                if res.status_code in (402, 404, 429) and model != kandidat[-1]:
                    continue
                raise error_terakhir

            data = res.json()
            pakai = data.get("usage") or {}
            usage.simpan_token_asli(
                pakai.get("total_tokens") or 0,
                pakai.get("prompt_tokens") or 0,
                pakai.get("completion_tokens") or 0,
            )
            isi = _teks_dari_pesan((data.get("choices") or [{}])[0].get("message") or {})
            if not isi:
                logger.warning("OpenRouter %s memberi jawaban kosong.", model)
                error_terakhir = HTTPException(
                    status_code=502,
                    detail="Layanan AI mengembalikan jawaban kosong. Silakan coba lagi.",
                )
                if model != kandidat[-1]:
                    continue
                raise error_terakhir

            if model != utama:
                logger.info("OpenRouter memakai model cadangan %s (bukan %s).", model, utama)
            return isi

    raise error_terakhir or HTTPException(
        status_code=502, detail="Layanan AI sedang sibuk. Silakan coba lagi."
    )


async def openrouter_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """
    Streaming dari OpenRouter, dengan cadangan model gratis.

    Penentuan model dilakukan SEBELUM byte pertama dikirim, sehingga
    bila model utama ditolak (kredit habis / tidak ada) kita masih bisa
    mengalihkan ke model :free tanpa merusak stream yang sudah berjalan.
    """
    utama = opsi.get("model") or OPENROUTER_MODEL_DEFAULT
    kandidat = _kandidat_openrouter(utama, bool(opsi.get("ada_gambar")))
    error_terakhir: Optional[HTTPException] = None

    async with httpx.AsyncClient(timeout=TIMEOUT_STREAM) as http:
        res = None
        model_terpakai = utama
        for model in kandidat:
            req = http.build_request(
                "POST",
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=_openrouter_headers(),
                json=_openrouter_payload(model, messages, opsi, True),
            )
            kandidat_res = await http.send(req, stream=True)

            if kandidat_res.status_code >= 400:
                body = await kandidat_res.aread()
                await kandidat_res.aclose()
                sebab = body.decode("utf-8", "replace")[:300]
                logger.warning(
                    "OpenRouter menolak streaming %s: HTTP %s %s",
                    model,
                    kandidat_res.status_code,
                    sebab,
                )
                error_terakhir = _pesan_openrouter_error(
                    kandidat_res.status_code, sebab, model
                )
                if kandidat_res.status_code in (402, 404, 429) and model != kandidat[-1]:
                    continue
                raise error_terakhir

            res = kandidat_res
            model_terpakai = model
            break

        if res is None:
            raise error_terakhir or HTTPException(
                status_code=502, detail="Layanan AI sedang sibuk. Silakan coba lagi."
            )

        if model_terpakai != utama:
            logger.info(
                "OpenRouter streaming memakai model cadangan %s (bukan %s).",
                model_terpakai,
                utama,
            )

        try:
            async for baris in res.aiter_lines():
                if not baris.startswith("data:"):
                    continue
                data = baris[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                pakai = obj.get("usage") or {}
                if pakai:
                    usage.simpan_token_asli(
                        pakai.get("total_tokens") or 0,
                        pakai.get("prompt_tokens") or 0,
                        pakai.get("completion_tokens") or 0,
                    )
                try:
                    pilihan = obj["choices"][0]
                except (KeyError, IndexError, TypeError):
                    pilihan = {}
                try:
                    delta = (pilihan.get("delta") or {}).get("content") or ""
                except AttributeError:
                    delta = ""
                if _terpotong_dari_finish(pilihan.get("finish_reason")):
                    _tandai_terpotong()
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            await res.aclose()


async def groq_complete(messages: List[dict], opsi: dict) -> str:
    """
    Meminta jawaban lengkap (non-streaming) ke Groq.

    Bila model yang dipasang ternyata sudah tidak tersedia (HTTP 404 —
    umumnya karena model berubah jadi Enterprise), otomatis dicoba
    model gratis lain sebelum menyerah. Dengan begitu situs tetap
    hidup meski GROQ_MODEL di environment sudah usang.

    PENTING: cadangan model DINONAKTIFKAN bila ada gambar. Mengganti ke
    model yang tidak multimodal hanya akan menghasilkan error 400 dan
    pesan yang membingungkan pengguna.
    """
    utama = opsi.get("model") or GROQ_MODEL
    if opsi.get("ada_gambar"):
        kandidat = [utama]
    else:
        kandidat = [utama] + [m for m in _MODEL_GROQ_CADANGAN if m != utama]
    error_terakhir: Optional[HTTPException] = None

    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
        for model in kandidat:
            payload = _groq_payload(model, messages, opsi, streaming=False)
            res = await http.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers=_groq_headers(),
                json=payload,
            )

            # Hanya 404 (model tidak ada) yang layak dicoba ulang
            # dengan model lain. 401/429/500 langsung dilaporkan.
            if res.status_code == 404 and model != kandidat[-1]:
                logger.warning(
                    "Model Groq '%s' tidak tersedia, mencoba model cadangan.", model
                )
                error_terakhir = HTTPException(
                    status_code=502, detail=pesan_error_http(404)
                )
                continue

            res.raise_for_status()

            # Simpan header kuota dari Groq agar panel Usage bisa
            # menampilkan SISA KUOTA SEBENARNYA (bukan perkiraan).
            usage.simpan_header_kuota(res.headers, model)

            data = res.json()
            try:
                pesan = data["choices"][0]["message"] or {}
            except (KeyError, IndexError, TypeError):
                pesan = {}

            # Simpan angka token SEBENARNYA dari penyedia. Ini membuat
            # pencatatan jatah akurat, bukan perkiraan dari panjang teks.
            try:
                pakai = data.get("usage") or {}
                usage.simpan_token_asli(
                    pakai.get("total_tokens") or 0,
                    pakai.get("prompt_tokens") or 0,
                    pakai.get("completion_tokens") or 0,
                )
            except Exception:  # noqa: BLE001
                pass

            isi = _teks_dari_pesan(pesan)

            if not isi:
                raise HTTPException(
                    status_code=502,
                    detail="Layanan AI mengembalikan jawaban kosong. Silakan coba lagi.",
                )
            return isi

    raise error_terakhir or HTTPException(
        status_code=502, detail=pesan_error_http(404)
    )


async def groq_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """
    Menghasilkan potongan teks (delta) dari Groq secara bertahap.

    Punya mekanisme cadangan model yang sama dengan groq_complete():
    bila model utama 404, coba model gratis berikutnya. Penentuan model
    dilakukan SEBELUM data dikirim ke pengguna, jadi aman untuk dialihkan.
    Cadangan dinonaktifkan bila ada gambar (lihat groq_complete).
    """
    utama = opsi.get("model") or GROQ_MODEL
    if opsi.get("ada_gambar"):
        kandidat = [utama]
    else:
        kandidat = [utama] + [m for m in _MODEL_GROQ_CADANGAN if m != utama]

    async with httpx.AsyncClient(timeout=TIMEOUT_STREAM) as http:
        res = None
        for model in kandidat:
            payload = _groq_payload(model, messages, opsi, streaming=True)
            permintaan = http.build_request(
                "POST",
                f"{GROQ_BASE_URL}/chat/completions",
                headers=_groq_headers(),
                json=payload,
            )
            kandidat_res = await http.send(permintaan, stream=True)

            if kandidat_res.status_code == 404 and model != kandidat[-1]:
                body = await kandidat_res.aread()
                logger.warning(
                    "Model Groq '%s' tidak tersedia saat streaming: %s. "
                    "Mencoba model cadangan.",
                    model,
                    body[:120],
                )
                await kandidat_res.aclose()
                continue

            if kandidat_res.status_code >= 400:
                body = await kandidat_res.aread()
                logger.error(
                    "Groq menolak streaming: %s %s",
                    kandidat_res.status_code,
                    body[:200],
                )
                kode = kandidat_res.status_code
                await kandidat_res.aclose()
                raise HTTPException(
                    status_code=502,
                    detail=pesan_error_http(kode),
                )

            res = kandidat_res

            # Header kuota juga tersedia pada respons streaming.
            usage.simpan_header_kuota(kandidat_res.headers, model)

            break

        if res is None:
            raise HTTPException(status_code=502, detail=pesan_error_http(404))

        try:
            async for baris in res.aiter_lines():
                if not baris or not baris.startswith("data:"):
                    continue
                data = baris[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                # Potongan terakhir (dengan stream_options.include_usage)
                # membawa angka token sebenarnya. Disimpan agar jatah
                # akun dihitung dari angka asli, bukan perkiraan.
                pakai = obj.get("usage")
                if isinstance(pakai, dict) and pakai:
                    try:
                        usage.simpan_token_asli(
                            pakai.get("total_tokens") or 0,
                            pakai.get("prompt_tokens") or 0,
                            pakai.get("completion_tokens") or 0,
                        )
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    pilihan = obj["choices"][0]
                except (KeyError, IndexError, TypeError):
                    pilihan = {}
                try:
                    delta = (pilihan.get("delta") or {}).get("content") or ""
                except AttributeError:
                    delta = ""
                # Catat bila model berhenti karena kehabisan token.
                if _terpotong_dari_finish(pilihan.get("finish_reason")):
                    _tandai_terpotong()
                # Sebagian respons mengirim content berupa list bagian.
                if isinstance(delta, list):
                    delta = "".join(
                        b.get("text", "")
                        for b in delta
                        if isinstance(b, dict) and isinstance(b.get("text"), str)
                    )
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            # Tutup koneksi HTTP ke Groq, termasuk bila pengguna
            # menekan tombol "Stop" di tengah jawaban.
            await res.aclose()


# ---------------------------------------------------------------------
# 10b. PEMANGGILAN KE GOOGLE GEMINI (penyedia cadangan)
# ---------------------------------------------------------------------
def _gemini_headers() -> dict:
    return {
        "Authorization": f"Bearer {GEMINI_API_KEY}",
        "Content-Type": "application/json",
    }


def _gemini_payload(model: str, messages: List[dict], opsi: dict, streaming: bool) -> dict:
    """
    Menyusun body permintaan untuk endpoint OpenAI-compatible Gemini.

    Bentuknya sengaja sama dengan Groq/OpenRouter karena Gemini meniru
    standar OpenAI. Yang TIDAK dikirim: `tools` milik Groq — riset web
    sudah dikerjakan di server (lihat riset.py), jadi tidak diperlukan.
    """
    payload = {
        "model": model,
        "messages": messages,
        "temperature": opsi["temperature"],
        "max_tokens": opsi["max_tokens"],
        "stream": streaming,
    }
    return payload


def _kandidat_gemini(model: str, ada_gambar: bool) -> List[str]:
    """
    Daftar model Gemini yang dicoba berurutan.

    Google kadang menutup model lama untuk API key baru (mis. 404 "model
    not found"). Tanpa cadangan, situs akan mati padahal hanya perlu
    ganti nama model. Bila ada gambar, hanya model vision yang dicoba.
    """
    utama = model if model in GEMINI_MODELS else GEMINI_MODEL_DEFAULT
    kandidat = [utama]
    for m in GEMINI_MODELS:
        if m == utama:
            continue
        if ada_gambar and m not in MODEL_VISION:
            continue
        kandidat.append(m)
    return kandidat


async def gemini_complete(messages: List[dict], opsi: dict) -> str:
    """Meminta jawaban lengkap (non-streaming) ke Gemini."""
    kandidat = _kandidat_gemini(
        opsi.get("model") or GEMINI_MODEL_DEFAULT, bool(opsi.get("ada_gambar"))
    )
    error_terakhir: Optional[HTTPException] = None

    async with httpx.AsyncClient(timeout=TIMEOUT_GEMINI) as http:
        for model in kandidat:
            payload = _gemini_payload(model, messages, opsi, streaming=False)
            res = await http.post(
                f"{GEMINI_BASE_URL}/chat/completions",
                headers=_gemini_headers(),
                json=payload,
            )

            # 404 = model tidak tersedia untuk key ini -> coba berikutnya.
            if res.status_code == 404 and model != kandidat[-1]:
                logger.warning(
                    "Model Gemini '%s' tidak tersedia, mencoba model cadangan.", model
                )
                error_terakhir = HTTPException(
                    status_code=502, detail=pesan_error_http(404)
                )
                continue

            if res.status_code >= 400:
                body = await res.aread() if hasattr(res, "aread") else b""
                logger.error(
                    "Gemini menolak permintaan: %s %s",
                    res.status_code,
                    (body or res.text.encode())[:200],
                )
                error_terakhir = ke_http_exception(
                    httpx.HTTPStatusError(
                        f"Gemini {res.status_code}",
                        request=res.request,
                        response=res,
                    )
                )
                # 429 = kuota habis. Tidak ada gunanya mencoba model lain
                # bila kuotanya memang habis untuk seluruh akun; tetapi
                # kuota Gemini dihitung per model, jadi tetap dicoba.
                if res.status_code == 429 and model != kandidat[-1]:
                    continue
                raise error_terakhir

            data = res.json()
            try:
                pesan = data["choices"][0]["message"] or {}
            except (KeyError, IndexError, TypeError):
                pesan = {}

            # Simpan angka token sebenarnya agar pencatatan jatah akurat.
            try:
                pakai = data.get("usage") or {}
                usage.simpan_token_asli(
                    pakai.get("total_tokens") or 0,
                    pakai.get("prompt_tokens") or 0,
                    pakai.get("completion_tokens") or 0,
                )
            except Exception:  # noqa: BLE001
                pass

            isi = _teks_dari_pesan(pesan)
            if not isi:
                raise HTTPException(
                    status_code=502,
                    detail="Layanan AI mengembalikan jawaban kosong. Silakan coba lagi.",
                )
            return isi

    raise error_terakhir or HTTPException(
        status_code=502, detail=pesan_error_http(404)
    )


async def gemini_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """
    Menghasilkan potongan teks (delta) dari Gemini secara bertahap.

    Mekanisme cadangan model sama dengan gemini_complete(). Penentuan
    model dilakukan SEBELUM ada data dikirim ke pengguna, jadi aman
    untuk dialihkan di tengah jalan.
    """
    kandidat = _kandidat_gemini(
        opsi.get("model") or GEMINI_MODEL_DEFAULT, bool(opsi.get("ada_gambar"))
    )

    async with httpx.AsyncClient(timeout=TIMEOUT_STREAM) as http:
        res = None
        for model in kandidat:
            payload = _gemini_payload(model, messages, opsi, streaming=True)
            permintaan = http.build_request(
                "POST",
                f"{GEMINI_BASE_URL}/chat/completions",
                headers=_gemini_headers(),
                json=payload,
            )
            kandidat_res = await http.send(permintaan, stream=True)

            if kandidat_res.status_code == 404 and model != kandidat[-1]:
                body = await kandidat_res.aread()
                logger.warning(
                    "Model Gemini '%s' tidak tersedia saat streaming: %s. "
                    "Mencoba model cadangan.",
                    model,
                    body[:120],
                )
                await kandidat_res.aclose()
                continue

            if kandidat_res.status_code == 429 and model != kandidat[-1]:
                await kandidat_res.aread()
                logger.warning(
                    "Kuota Gemini untuk '%s' habis; mencoba model berikutnya.", model
                )
                await kandidat_res.aclose()
                continue

            if kandidat_res.status_code >= 400:
                body = await kandidat_res.aread()
                logger.error(
                    "Gemini menolak streaming: %s %s",
                    kandidat_res.status_code,
                    body[:200],
                )
                kode = kandidat_res.status_code
                await kandidat_res.aclose()
                raise ke_http_exception(
                    httpx.HTTPStatusError(
                        f"Gemini {kode}",
                        request=kandidat_res.request,
                        response=kandidat_res,
                    )
                )

            res = kandidat_res
            break

        if res is None:
            raise HTTPException(status_code=502, detail=pesan_error_http(404))

        try:
            async for baris in res.aiter_lines():
                if not baris or not baris.startswith("data:"):
                    continue
                data = baris[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                pakai = obj.get("usage")
                if isinstance(pakai, dict) and pakai:
                    try:
                        usage.simpan_token_asli(
                            pakai.get("total_tokens") or 0,
                            pakai.get("prompt_tokens") or 0,
                            pakai.get("completion_tokens") or 0,
                        )
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    pilihan = obj["choices"][0]
                except (KeyError, IndexError, TypeError):
                    pilihan = {}
                try:
                    delta = (pilihan.get("delta") or {}).get("content") or ""
                except AttributeError:
                    delta = ""
                if _terpotong_dari_finish(pilihan.get("finish_reason")):
                    _tandai_terpotong()
                if isinstance(delta, list):
                    delta = "".join(
                        b.get("text", "")
                        for b in delta
                        if isinstance(b, dict) and isinstance(b.get("text"), str)
                    )
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            # Tutup koneksi juga saat pengguna menekan "Stop".
            await res.aclose()


# ---------------------------------------------------------------------
# 9b. PEMANGGILAN KE NVIDIA NIM (penyedia keempat, kompatibel OpenAI)
# ---------------------------------------------------------------------
def _nvidia_headers() -> dict:
    return {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _nvidia_payload(model: str, messages: List[dict], opsi: dict, streaming: bool) -> dict:
    """
    Body permintaan untuk NVIDIA NIM.

    NIM memakai standar OpenAI, tetapi beberapa modelnya menolak
    `temperature` 0 (dianggap tidak valid), jadi nilai itu digeser
    sedikit. Selain itu `max_tokens` dikirim sebagai `max_tokens` biasa —
    NIM tidak mengenal `max_completion_tokens` milik Groq.
    """
    suhu = opsi["temperature"]
    if not isinstance(suhu, (int, float)) or suhu <= 0:
        suhu = 0.1

    return {
        "model": _nvidia_nama_asli(model),
        "messages": messages,
        "temperature": suhu,
        "max_tokens": opsi["max_tokens"],
        "stream": streaming,
    }


def _kandidat_nvidia(model: str, ada_gambar: bool) -> List[str]:
    """Model NVIDIA yang dicoba berurutan; nama salah dibalas 404."""
    utama = model if model in NVIDIA_MODELS else NVIDIA_MODEL_DEFAULT
    kandidat = [utama]
    for m in NVIDIA_MODELS:
        if m == utama:
            continue
        if ada_gambar and m not in MODEL_VISION:
            continue
        kandidat.append(m)
    return kandidat


def _pesan_nvidia_error(kode: int, badan: str) -> str:
    """Pesan kesalahan NVIDIA dalam Bahasa Indonesia yang tenang."""
    if kode in (401, 403):
        return (
            "Layanan AI menolak kunci akses NVIDIA. Periksa kembali "
            "NVIDIA_API_KEY di pengaturan server."
        )
    if kode == 404:
        return "Model NVIDIA yang dipilih tidak tersedia. Silakan pilih model lain."
    if kode == 410:
        return (
            "Model NVIDIA yang dipilih sudah tidak dipakai lagi. "
            "Silakan pilih model lain."
        )
    if kode in (402, 429):
        return (
            "Kuota layanan AI sedang penuh. Silakan coba lagi beberapa saat lagi."
        )
    logger.warning("NVIDIA menolak permintaan: HTTP %s %s", kode, badan[:200])
    return "Layanan AI sedang bermasalah. Silakan coba lagi."


async def nvidia_complete(messages: List[dict], opsi: dict) -> str:
    """Jawaban lengkap (non-streaming) dari NVIDIA NIM."""
    kandidat = _kandidat_nvidia(
        opsi.get("model") or NVIDIA_MODEL_DEFAULT, bool(opsi.get("ada_gambar"))
    )
    error_terakhir: Optional[HTTPException] = None

    async with httpx.AsyncClient(timeout=TIMEOUT_GEMINI) as http:
        for model in kandidat:
            res = await http.post(
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers=_nvidia_headers(),
                json=_nvidia_payload(model, messages, opsi, False),
            )

            if res.status_code >= 400:
                sebab = res.text[:300]
                logger.warning(
                    "NVIDIA menolak %s: HTTP %s %s", model, res.status_code, sebab
                )
                error_terakhir = HTTPException(
                    status_code=502,
                    detail=_pesan_nvidia_error(res.status_code, sebab),
                )
                # Naikkan status asli agar failover kuota tetap bekerja.
                if res.status_code in _STATUS_KUOTA:
                    error_terakhir = HTTPException(
                        status_code=res.status_code,
                        detail=_pesan_nvidia_error(res.status_code, sebab),
                    )
                # 410 = model sudah dimatikan NVIDIA ("end of life").
                # Ini bukan salah pengguna dan bukan salah kunci, jadi
                # jangan tampilkan error: lewati ke model cadangan.
                if (
                    res.status_code in (402, 404, 410, 429)
                    and model != kandidat[-1]
                ):
                    continue
                raise error_terakhir

            data = res.json()
            pakai = data.get("usage") or {}
            if pakai:
                try:
                    usage.simpan_token_asli(
                        pakai.get("total_tokens") or 0,
                        pakai.get("prompt_tokens") or 0,
                        pakai.get("completion_tokens") or 0,
                    )
                except Exception:  # noqa: BLE001
                    pass

            isi = _teks_dari_pesan((data.get("choices") or [{}])[0].get("message") or {})
            if not isi:
                logger.warning("NVIDIA %s memberi jawaban kosong.", model)
                error_terakhir = HTTPException(
                    status_code=502,
                    detail="Layanan AI mengembalikan jawaban kosong. Silakan coba lagi.",
                )
                if model != kandidat[-1]:
                    continue
                raise error_terakhir

            if model != kandidat[0]:
                logger.info("NVIDIA memakai model cadangan %s.", model)
            return isi

    raise error_terakhir or HTTPException(
        status_code=502, detail="Layanan AI sedang bermasalah. Silakan coba lagi."
    )


async def nvidia_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """Mengalirkan jawaban dari NVIDIA NIM (SSE, format OpenAI)."""
    kandidat = _kandidat_nvidia(
        opsi.get("model") or NVIDIA_MODEL_DEFAULT, bool(opsi.get("ada_gambar"))
    )

    async with httpx.AsyncClient(timeout=TIMEOUT_STREAM) as http:
        res = None
        for model in kandidat:
            payload = _nvidia_payload(model, messages, opsi, streaming=True)
            permintaan = http.build_request(
                "POST",
                f"{NVIDIA_BASE_URL}/chat/completions",
                headers=_nvidia_headers(),
                json=payload,
            )
            kandidat_res = await http.send(permintaan, stream=True)

            if (
                kandidat_res.status_code in (404, 410)
                and model != kandidat[-1]
            ):
                await kandidat_res.aread()
                logger.warning(
                    "Model NVIDIA '%s' tidak tersedia/dimatikan (HTTP %s); "
                    "mencoba cadangan.",
                    model,
                    kandidat_res.status_code,
                )
                await kandidat_res.aclose()
                continue

            if kandidat_res.status_code >= 400:
                badan = await kandidat_res.aread()
                kode = kandidat_res.status_code
                await kandidat_res.aclose()
                logger.error("NVIDIA menolak streaming: %s %s", kode, badan[:200])
                # Kode asli dipertahankan agar failover kuota bisa bekerja.
                raise HTTPException(
                    status_code=kode if kode in _STATUS_KUOTA else 502,
                    detail=_pesan_nvidia_error(kode, badan.decode("utf-8", "replace")),
                )

            res = kandidat_res
            break

        if res is None:
            raise HTTPException(
                status_code=502,
                detail="Model NVIDIA tidak tersedia. Silakan pilih model lain.",
            )

        try:
            async for baris in res.aiter_lines():
                if not baris or not baris.startswith("data:"):
                    continue
                data = baris[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue

                pakai = obj.get("usage")
                if isinstance(pakai, dict) and pakai:
                    try:
                        usage.simpan_token_asli(
                            pakai.get("total_tokens") or 0,
                            pakai.get("prompt_tokens") or 0,
                            pakai.get("completion_tokens") or 0,
                        )
                    except Exception:  # noqa: BLE001
                        pass

                try:
                    pilihan = obj["choices"][0]
                except (KeyError, IndexError, TypeError):
                    pilihan = {}
                try:
                    delta = (pilihan.get("delta") or {}).get("content") or ""
                except AttributeError:
                    delta = ""
                if _terpotong_dari_finish(pilihan.get("finish_reason")):
                    _tandai_terpotong()
                if isinstance(delta, list):
                    delta = "".join(
                        b.get("text", "")
                        for b in delta
                        if isinstance(b, dict) and isinstance(b.get("text"), str)
                    )
                if isinstance(delta, str) and delta:
                    yield delta
        finally:
            await res.aclose()


# ---------------------------------------------------------------------
# 10. PEMANGGILAN KE OLLAMA (lokal)
# ---------------------------------------------------------------------
def _pesan_untuk_ollama(messages: List[dict]) -> List[dict]:
    """
    Mengubah pesan format OpenAI (dipakai Groq) ke format Ollama.

    Bedanya: Ollama menerima `content` sebagai STRING dan gambar
    diletakkan di field terpisah `images` berisi base64 MURNI (tanpa
    awalan "data:image/png;base64,").

    Tanpa konversi ini, permintaan bergambar akan ditolak Ollama dengan
    error "cannot unmarshal array into ... field content of type string"
    — persis yang terjadi saat pengembangan lokal.
    """
    hasil: List[dict] = []

    for pesan in messages:
        isi = pesan.get("content")

        # Sudah string biasa (mayoritas riwayat & system prompt).
        if isinstance(isi, str):
            hasil.append({"role": pesan.get("role", "user"), "content": isi})
            continue

        # Format multimodal OpenAI: list berisi teks + image_url.
        if isinstance(isi, list):
            bagian_teks: List[str] = []
            gambar: List[str] = []
            for bagian in isi:
                if not isinstance(bagian, dict):
                    continue
                if bagian.get("type") == "text" and isinstance(bagian.get("text"), str):
                    bagian_teks.append(bagian["text"])
                elif bagian.get("type") == "image_url":
                    url = (bagian.get("image_url") or {}).get("url") or ""
                    # Ollama mau base64 tanpa header data URL.
                    if url.startswith("data:"):
                        url = url.split(",", 1)[-1]
                    if url:
                        gambar.append(url)

            baru = {
                "role": pesan.get("role", "user"),
                "content": "\n".join(bagian_teks),
            }
            if gambar:
                baru["images"] = gambar
            hasil.append(baru)
            continue

        hasil.append({"role": pesan.get("role", "user"), "content": str(isi or "")})

    return hasil


async def ollama_complete(messages: List[dict], opsi: dict) -> str:
    """Meminta jawaban lengkap ke Ollama lokal via HTTP API."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": _pesan_untuk_ollama(messages),
        "stream": False,
        "options": {
            "temperature": opsi["temperature"],
            "num_predict": opsi["max_tokens"],
        },
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_OLLAMA) as http:
        res = await http.post(f"{OLLAMA_HOST}/api/chat", json=payload)
        res.raise_for_status()
        data = res.json()

    isi = (data.get("message") or {}).get("content") or ""
    if not isi.strip():
        raise HTTPException(
            status_code=502,
            detail="Ollama mengembalikan balasan kosong. Silakan coba lagi.",
        )
    return isi.strip()


async def ollama_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """Menghasilkan potongan teks dari Ollama secara bertahap."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": _pesan_untuk_ollama(messages),
        "stream": True,
        "options": {
            "temperature": opsi["temperature"],
            "num_predict": opsi["max_tokens"],
        },
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_OLLAMA) as http:
        async with http.stream("POST", f"{OLLAMA_HOST}/api/chat", json=payload) as res:
            if res.status_code >= 400:
                body = await res.aread()
                logger.error("Ollama menolak: %s %s", res.status_code, body[:200])
                raise HTTPException(
                    status_code=502,
                    detail=pesan_error_http(res.status_code),
                )

            async for baris in res.aiter_lines():
                if not baris.strip():
                    continue
                try:
                    obj = json.loads(baris)
                except json.JSONDecodeError:
                    continue
                if obj.get("error"):
                    raise HTTPException(status_code=502, detail=str(obj["error"]))
                delta = (obj.get("message") or {}).get("content") or ""
                if delta:
                    yield delta
                if obj.get("done"):
                    break


# ---------------------------------------------------------------------
# 11. DISPATCHER: satu pintu untuk semua penyedia
# ---------------------------------------------------------------------
def _penyedia_untuk_model(model: str) -> str:
    """
    Menentukan penyedia yang tepat untuk satu model.

    MENGAPA INI PERLU
    -----------------
    Dulu penyedia dipilih SEKALI saat server mulai (dari AI_PROVIDER),
    lalu semua model dikirim ke penyedia itu. Akibatnya memilih model
    OpenRouter tetap dijawab Groq — nama model hanya menjadi label,
    penggunaan OpenRouter tetap nol, dan kuota gratis Groq cepat habis
    walau pengguna memilih model lain.

    Sekarang setiap model dirutekan ke penyedia yang MEMANG punya model
    itu:
      - model terdaftar di OPENROUTER_MODELS -> OpenRouter
      - selain itu                            -> penyedia utama

    Bila penyedia tujuan tidak punya kunci, model dialihkan ke penyedia
    yang kuncinya tersedia, supaya chat tetap berjalan (bukan error).
    """
    di_openrouter = model in OPENROUTER_MODELS
    di_groq = model in MODEL_GROQ_DIIZINKAN
    di_gemini = model in GEMINI_MODELS
    di_nvidia = model in NVIDIA_MODELS

    # Daftar penyedia penyelamat, dipakai berurutan bila penyedia yang
    # dituju tidak punya kunci. Disusun sekali agar tidak berulang.
    def penyelamat(kecuali: str) -> Optional[str]:
        for nama, ada in (
            ("groq", GROQ_API_KEY),
            ("gemini", GEMINI_API_KEY),
            ("openrouter", OPENROUTER_API_KEY),
            ("nvidia", NVIDIA_API_KEY),
        ):
            if nama != kecuali and ada:
                return nama
        return None

    if di_openrouter:
        if OPENROUTER_API_KEY:
            return "openrouter"
        return penyelamat("openrouter") or PROVIDER
    if di_nvidia:
        if NVIDIA_API_KEY:
            return "nvidia"
        return penyelamat("nvidia") or PROVIDER
    if di_gemini:
        if GEMINI_API_KEY:
            return "gemini"
        return penyelamat("gemini") or PROVIDER
    if di_groq:
        if GROQ_API_KEY:
            return "groq"
        return penyelamat("groq") or PROVIDER
    # Model tidak dikenali penyedianya: pakai penyedia aktif.
    return PROVIDER


def _urutan_penyedia(penyedia_utama: str) -> List[str]:
    """
    Urutan penyedia yang dicoba saat penyedia utama gagal karena kuota.

    MENGAPA PERLU FAILOVER
    ----------------------
    Setiap penyedia gratis punya batas harian (Groq 200.000 token/hari
    per model, OpenRouter 50 request/hari, Gemini kuota harian). Dahulu
    bila satu penyedia habis, SEMUA pengguna langsung melihat error
    padahal penyedia lain masih punya sisa kuota.

    Dengan urutan ini, permintaan otomatis dialihkan ke penyedia lain
    yang kuncinya tersedia. Pengguna tidak perlu tahu — jawaban tetap
    datang.

    Urutannya: penyedia pilihan pengguna lebih dulu (agar pilihannya
    dihormati), lalu penyedia lain sebagai penyelamat.
    """
    semua = ["groq", "gemini", "openrouter", "nvidia"]

    def tersedia(nama: str) -> bool:
        if nama == "groq":
            return bool(GROQ_API_KEY)
        if nama == "gemini":
            return bool(GEMINI_API_KEY)
        if nama == "openrouter":
            return bool(OPENROUTER_API_KEY)
        if nama == "nvidia":
            return bool(NVIDIA_API_KEY)
        return False

    urutan = [penyedia_utama] if tersedia(penyedia_utama) else []
    urutan += [p for p in semua if p != penyedia_utama and tersedia(p)]
    return urutan


# Status yang menandakan "kuota penyedia ini habis" dan layak dicoba ke
# penyedia lain. 401/403 TIDAK termasuk: itu masalah kunci, bukan kuota,
# dan berpindah penyedia justru menyembunyikan kesalahan konfigurasi.
_STATUS_KUOTA = {429, 402}

# ---------------------------------------------------------------------
# DETEKSI JAWABAN TERPOTONG
# ---------------------------------------------------------------------
# Penyebab jawaban berhenti di tengah ("kepotong"):
#   1. Model mencapai batas `max_tokens`          -> finish_reason = "length"
#   2. Batas token per menit penyedia tercapai    -> finish_reason berhenti
#      mendadak / koneksi ditutup
#   3. Waktu habis (timeout)                      -> tidak ada finish_reason
#
# Dulu hal ini tidak terdeteksi: server mengirim `done: true` seolah
# jawaban sudah lengkap. Pengguna pun harus mengetik "lanjut" — dan itu
# MEMAKAN SATU JATAH PESAN LAGI. Sekarang server mengirim sinyal
# `terpotong` supaya UI bisa memberi tahu dan menawarkan melanjutkan
# tanpa memotong jatah lagi.
def _terpotong_dari_finish(finish_reason: Optional[str]) -> bool:
    """True bila model berhenti karena kehabisan jatah token sendiri."""
    if not finish_reason:
        return False
    return str(finish_reason).lower() in {"length", "max_tokens", "max_output_tokens"}


# Berapa kali jawaban boleh disambung otomatis dalam SATU kirim pesan.
#
# 3 dipilih dengan sengaja: dengan max_tokens 4096, tiga sambungan
# berarti hingga ±16.000 token — jauh lebih panjang daripada jawaban
# paling panjang yang wajar. Bila masih terpotong setelah itu, biasanya
# penyebabnya bukan panjang jawaban melainkan model yang berhenti
# aneh, dan mengulang terus hanya membuang kuota.
MAKS_SAMBUNG = 3


def _pesan_untuk_sambungan(messages: List[dict], sudah_ditulis: str) -> List[dict]:
    """
    Menyusun pesan untuk meminta LANJUTAN jawaban yang terpotong.

    Riwayat asli + jawaban yang sudah terkirim + instruksi melanjutkan.
    Instruksi dibuat tegas supaya model tidak mengulang dari awal
    (mengulang berarti pengguna membaca hal yang sama dua kali) dan
    tidak membuka dengan basa-basi seperti "Tentu, lanjut:".
    """
    return list(messages) + [
        {"role": "assistant", "content": sudah_ditulis},
        {
            "role": "user",
            "content": (
                "Jawabanmu di atas terputus di tengah. Lanjutkan TEPAT dari "
                "kata terakhir — jangan mengulang dari awal, jangan "
                "mengulang kalimat yang sudah tertulis, dan tanpa pembuka "
                "seperti 'lanjut' atau 'tentu'. Tulis sisanya sampai selesai."
            ),
        },
    ]


# Penanda jawaban terpotong. Disimpan per-task (contextvars) supaya
# permintaan yang berjalan bersamaan tidak saling menimpa — satu pengguna
# yang jawabannya terpotong tidak boleh membuat pengguna lain ikut
# ditandai terpotong.
_TERPOTONG: "contextvars.ContextVar[List[str]]" = contextvars.ContextVar(
    "gungdev_terpotong", default=None
)


def _mulai_pantau_terpotong() -> None:
    """Menyiapkan penanda baru untuk satu permintaan."""
    _TERPOTONG.set([])


def _tandai_terpotong(alasan: str = "") -> None:
    """Menandai bahwa jawaban berhenti sebelum selesai."""
    daftar = _TERPOTONG.get()
    if daftar is not None:
        daftar.append(alasan or "token")


def _apakah_terpotong() -> bool:
    """True bila jawaban pada permintaan ini berhenti di tengah."""
    daftar = _TERPOTONG.get()
    return bool(daftar)



async def complete(messages: List[dict], opsi: dict) -> str:
    """Menghasilkan jawaban lengkap, dengan failover antar penyedia."""
    model = opsi.get("model") or MODEL_NAME
    penyedia_utama = _penyedia_untuk_model(model)
    urutan = _urutan_penyedia(penyedia_utama) or [penyedia_utama]
    error_terakhir: Optional[Exception] = None

    for i, penyedia in enumerate(urutan):
        try:
            if penyedia == "gemini":
                return await gemini_complete(messages, opsi)
            if penyedia == "openrouter":
                return await openrouter_complete(messages, opsi)
            if penyedia == "nvidia":
                return await nvidia_complete(messages, opsi)
            if penyedia == "groq":
                return await groq_complete(messages, opsi)
            return await ollama_complete(messages, opsi)
        except HTTPException as exc:
            error_terakhir = exc
            # Hanya kuota habis yang layak dialihkan ke penyedia lain.
            if exc.status_code not in _STATUS_KUOTA or i == len(urutan) - 1:
                raise
            logger.warning(
                "Penyedia '%s' kehabisan kuota (%s); mengalihkan ke '%s'.",
                penyedia,
                exc.status_code,
                urutan[i + 1],
            )

    raise error_terakhir or HTTPException(status_code=502, detail=pesan_error_http(429))


async def stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """
    Menghasilkan jawaban bertahap, dengan failover antar penyedia.

    PENTING: failover hanya dilakukan SEBELUM potongan pertama dikirim.
    Setelah satu karakter sampai ke pengguna, berpindah penyedia akan
    membuat jawaban terasa terulang dari awal, jadi itu tidak dilakukan.
    """
    model = opsi.get("model") or MODEL_NAME
    penyedia_utama = _penyedia_untuk_model(model)
    urutan = _urutan_penyedia(penyedia_utama) or [penyedia_utama]

    for i in range(len(urutan)):
        penyedia = urutan[i]
        mulai = False
        try:
            if penyedia == "gemini":
                aliran = gemini_stream(messages, opsi)
            elif penyedia == "openrouter":
                aliran = openrouter_stream(messages, opsi)
            elif penyedia == "nvidia":
                aliran = nvidia_stream(messages, opsi)
            elif penyedia == "groq":
                aliran = groq_stream(messages, opsi)
            else:
                aliran = ollama_stream(messages, opsi)

            async for delta in aliran:
                mulai = True
                yield delta
            return
        except HTTPException as exc:
            # Sudah ada teks terkirim -> tidak boleh pindah penyedia.
            if mulai or exc.status_code not in _STATUS_KUOTA or i == len(urutan) - 1:
                raise
            logger.warning(
                "Penyedia '%s' kehabisan kuota saat streaming (%s); "
                "mengalihkan ke '%s'.",
                penyedia,
                exc.status_code,
                urutan[i + 1],
            )

# ---------------------------------------------------------------------
# 11b. PERKIRAAN TOKEN (untuk pencatatan usage)
# ---------------------------------------------------------------------
def _perkiraan_token(messages: List[dict], jawaban: str) -> int:
    """
    Memperkirakan jumlah token yang dipakai satu percakapan.

    Groq mengembalikan angka pasti di field usage, tetapi angka itu
    tidak selalu tersedia (mis. saat streaming). Perkiraan kasar
    ~4 karakter per token sudah cukup untuk indikator pemakaian —
    dan angka PASTI tetap datang dari header kuota penyedia.

    `content` bisa berupa string (biasa) atau list bagian (multimodal),
    jadi keduanya dihitung dengan aman.
    """
    def panjang_isi(isi) -> int:
        if isinstance(isi, str):
            return len(isi)
        if isinstance(isi, list):
            total = 0
            for bagian in isi:
                if isinstance(bagian, dict):
                    total += len(str(bagian.get("text", "")))
                    # Gambar memakan token jauh lebih besar; beri
                    # perkiraan tetap agar angka tidak menyesatkan.
                    if bagian.get("type") == "image_url":
                        total += 1000
            return total
        return len(str(isi or ""))

    try:
        panjang = sum(panjang_isi(m.get("content")) for m in messages)
        panjang += len(jawaban or "")
        return max(1, panjang // 4)
    except Exception:  # noqa: BLE001
        return 0


def _token_untuk_catatan(messages: List[dict], jawaban: str) -> int:
    """
    Menentukan jumlah token yang dicatat untuk satu permintaan.

    Urutan prioritas:
      1. Angka ASLI dari penyedia (Groq mengirim usage di setiap
         respons). Ini yang dipakai kapan pun tersedia.
      2. Perkiraan dari panjang teks — hanya bila penyedia tidak
         mengirim angka (mis. Ollama lokal).

    Batas minimum selalu dipakai agar jatah tidak bisa diakali dengan
    membuat pencatatan token gagal (biaya 0 token = jatah tak terbatas).
    """
    asli = usage.ambil_token_asli()
    if asli and asli > 0:
        return int(asli)
    try:
        perkiraan = _perkiraan_token(messages, jawaban)
    except Exception:  # noqa: BLE001
        perkiraan = 0
    return max(usage.TOKEN_MIN_PER_REQUEST, int(perkiraan or 0))


def pesan_jatah_habis(jatah: dict) -> str:
    """
    Pesan yang dilihat pengguna saat jatah hariannya habis.

    Ditulis jelas dan menenangkan: apa yang terjadi, kapan pulih, dan
    apa yang bisa dilakukan sekarang. Tanpa menyebut nama penyedia AI
    atau detail infrastruktur.
    """
    jam = jatah.get("reset_detik") or 0
    if jam >= 3600:
        sisa = jam % 3600
        waktu = f"{int(jam // 3600)} jam"
        if sisa >= 60:
            waktu += f" {int(sisa // 60)} menit"
        waktu += " lagi"
    elif jam >= 60:
        waktu = f"{int(jam // 60)} menit lagi"
    else:
        waktu = f"{int(jam)} detik lagi"

    batas = jatah.get("batas")
    jatah_teks = f" Jatah Anda {batas} pesan per jendela 24 jam." if batas else ""

    if jatah.get("alasan") == "token":
        # Tidak dipakai lagi (token bukan pembatas), tetapi dipertahankan
        # agar kode lama/pemanggil lain tidak menghasilkan pesan kosong.
        inti = "Pemakaian token Anda sudah mencapai batas."
    else:
        inti = "Jatah pesan Anda sudah habis."

    return (
        f"{inti}{jatah_teks} Jatah pulih otomatis dalam {waktu} — yaitu saat "
        f"jendela 24 jam akun Anda berakhir (dihitung sejak pesan pertama "
        f"Anda). Jatah ini hanya milik akun Anda, akun lain tidak terpengaruh. "
        f"Anda masih bisa membaca riwayat percakapan yang sudah ada."
    )


def pesan_akun_baru_penuh(daftar: dict) -> str:
    """
    Pesan saat kuota harian untuk AKUN BARU sudah habis.

    Kenapa perlu dibatasi: kuota layanan dibagi rata ke sejumlah akun yang
    wajar per hari. Tanpa aturan ini, puluhan akun baru dalam sehari bisa
    menghabiskan seluruh kuota sehingga pengguna lain (dan pengguna setia
    yang besok kembali) tidak kebagian.

    Pesan sengaja tidak menyebut angka kuota internal, hanya menjelaskan
    apa yang terjadi dan apa yang bisa dilakukan.
    """
    return (
        "Layanan hari ini sudah menerima banyak akun baru, jadi akun baru "
        "belum bisa dipakai sekarang. Akun yang sudah pernah memakai layanan "
        "tetap bisa chat seperti biasa. Silakan coba lagi besok — jatah "
        "akun baru dibuka kembali otomatis."
    )


# ---------------------------------------------------------------------
# 12. ENDPOINT GET /health
# ---------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Untuk indikator Online/Offline di frontend.

    Selalu membalas 'ok' bila server hidup; frontend lalu memastikan
    provider benar-benar bisa dipanggil saat pesan pertama dikirim.

    PENTING — hanya label publik yang dikirim. Nama penyedia, nama model,
    dan base URL sengaja TIDAK disertakan: itu informasi internal yang
    tidak perlu diketahui pengunjung. Untuk kebutuhan operasional,
    detail sebenarnya tetap tercatat di log server.
    """
    return {"status": "ok", "provider": "gungdev", "model": "gungdev"}


# ---------------------------------------------------------------------
# 12a. ENDPOINT GET /diagnostik — status konfigurasi (AMAN, tanpa rahasia)
# ---------------------------------------------------------------------
def _format_key(kunci: str) -> str:
    """
    Menjelaskan BENTUK sebuah kunci tanpa membocorkan isinya.

    Hanya untuk membantu diagnosa saat kunci "tidak terbaca":
      - "kosong"            -> variabel tidak terpasang / tidak terbaca
      - "awalan-salah"      -> terisi, tetapi bukan format OpenRouter
      - "terlalu-pendek"    -> kemungkinan terpotong saat menempel
      - "ok"                -> bentuknya wajar

    Panjang dalam puluhan karakter tidak dapat dipakai menebak kunci.
    """
    if not kunci:
        return "kosong"
    if len(kunci) < 30:
        return "terlalu-pendek"
    if not kunci.startswith("sk-or-"):
        return "awalan-salah"
    return "ok"


@app.get("/diagnostik")
async def diagnostik():
    """
    Menjawab pertanyaan "kenapa riwayat hanya tersimpan di perangkat?"

    Yang dikirim HANYA status terpasang/belum terpasang (boolean).
    Tidak ada API key, token, URL, atau nama penyedia — sehingga endpoint
    ini aman dibuka walau situsnya publik. Nilai rahasia tetap tidak
    pernah keluar dari server.
    """
    return {
        # Penyimpanan riwayat per akun (Redis). Bila false, frontend
        # menampilkan "Riwayat sementara hanya di perangkat ini".
        "penyimpanan_riwayat": penyimpanan.tersedia(),
        # Verifikasi ID token Google. Bila false, SEMUA permintaan riwayat
        # ditolak (401) walau pengguna sudah login.
        "verifikasi_login": identitas.tersedia(),
        # Status AI (hanya boolean).
        "ai_siap": bool(
            GROQ_API_KEY if PROVIDER == "groq"
            else OPENROUTER_API_KEY if PROVIDER == "openrouter"
            else True
        ),
        # Provider AKTIF. Hanya nama jenisnya ("groq"/"openrouter"/
        # "ollama"), bukan URL atau key: ini yang menentukan pemakaian
        # benar-benar sampai ke penyedia atau tidak.
        "provider_aktif": PROVIDER,
        # Petunjuk panjang API key OpenRouter (0 = kosong). Membantu
        # memastikan key benar-benar terbaca, tanpa menampilkan isinya.
        "panjang_key_openrouter": len(OPENROUTER_API_KEY),
        "panjang_key_groq": len(GROQ_API_KEY),
        # Model default yang dipakai provider aktif.
        "model_default": MODEL_NAME,
        # Daftar NAMA environment variable yang terpasang (TANPA nilai).
        # Berguna saat rahasia "tidak terbaca": langsung terlihat apakah
        # variabelnya tidak ada, salah nama, atau terpasang di tempat lain.
        # Nama variabel bukan rahasia; nilainya tetap tidak pernah keluar.
        #
        # Daftar awalan ini WAJIB memuat SEMUA penyedia. Dulu hanya ada
        # OPENROUTER/GROQ/AI_/UPSTASH/GOOGLE, sehingga NVIDIA_API_KEY dan
        # GEMINI_API_KEY yang SUDAH terpasang tampak seolah tidak ada —
        # dan orang bisa menghabiskan waktu memeriksa Vercel padahal
        # masalahnya di daftar ini.
        "env_terpasang": sorted(
            nama
            for nama in os.environ
            if nama.startswith(
                (
                    "OPENROUTER",
                    "GROQ",
                    "GEMINI",
                    "NVIDIA",
                    "AI_",
                    "UPSTASH",
                    "GOOGLE",
                )
            )
        ),
        # Status tiap penyedia: terpasang atau tidak, dan dipakai atau
        # tidak. Hanya benar/salah — nilainya tidak pernah keluar.
        "penyedia": {
            "groq": {"ada_kunci": bool(GROQ_API_KEY)},
            "openrouter": {"ada_kunci": bool(OPENROUTER_API_KEY)},
            "gemini": {"ada_kunci": bool(GEMINI_API_KEY)},
            "nvidia": {"ada_kunci": bool(NVIDIA_API_KEY)},
        },
        # Penanda aman: apakah kunci OpenRouter memakai awalan yang benar.
        # Ini membedakan "variabel tidak ada" dari "variabel ada tapi salah
        # isi" (mis. terpotong saat menempel). Tidak membocorkan key.
        "format_key_openrouter": _format_key(OPENROUTER_API_KEY),
        # Petunjuk aman: kunci OpenRouter terpasang tetapi TIDAK dipakai,
        # biasanya karena AI_PROVIDER mengunci penyedia lain. Tanpa
        # petunjuk ini, pemilik situs bisa bingung kenapa penggunaan
        # OpenRouter tetap nol walau kuncinya sudah diisi.
        "key_openrouter_dipakai": PROVIDER == "openrouter",
        # -------------------------------------------------------------
        # KAPASITAS & JATAH — HANYA untuk pemilik situs.
        # Tidak ada satupun dari angka ini yang tampil ke pengguna;
        # /usage hanya mengirim jatah akun masing-masing.
        # -------------------------------------------------------------
        "jatah": {
            "per_akun_penuh": usage.JATAH_AKUN_DASAR,
            "per_akun_saat_ramai": usage.JATAH_SAAT_KUOTA_TIPIS,
            "jendela_jam": round(usage.JENDELA_JATAH_DETIK / 3600, 1),
            "maks_akun_baru_per_hari": usage.MAX_AKUN_BARU_PER_HARI,
            "tamu_pesan_per_hari": usage.JATAH_TAMU["rpd"],
        },
        "kuota_bersama": {
            "request_per_hari_penyedia_langka": usage.KUOTA_BERSAMA[
                "rpd_penyedia_langka"
            ],
            "model_groq": usage.KUOTA_BERSAMA["model_groq"],
            "request_per_hari_per_model_groq": usage.KUOTA_BERSAMA[
                "rpd_per_model_groq"
            ],
            "token_per_hari_per_model_groq": usage.KUOTA_BERSAMA[
                "tpd_per_model_groq"
            ],
            "token_per_pesan_rata2": usage.KUOTA_BERSAMA["token_per_pesan"],
        },
        # Kapasitas gabungan kedua penyedia per hari (hanya pemilik situs).
        "kapasitas_harian": {
            "request": usage.KAPASITAS_HARIAN["request"],
            "token": usage.KAPASITAS_HARIAN["token"],
            "pesan": usage.PESAN_PER_HARI,
            "sisa_pesan_hari_ini": await usage.sisa_pesan_situs(),
        },
    }


# ---------------------------------------------------------------------
# 12b. ENDPOINT GET /usage — pemakaian & sisa kuota AI
# ---------------------------------------------------------------------
@app.get("/usage")
async def usage_check(authorization: Optional[str] = Header(None)):
    """
    Menampilkan JATAH pemakaian milik akun yang sedang login.

        {
          "provider": "gungdev",
          "model": "gungdev",
          "layanan": { "status": "lancar|ramai|dikurangi", ... },
          "reset":  { "detik": 25200, "jam": 7.0, "waktu_utc": "...", "zona": "UTC" },
          "akun": {
             "requests": { "terpakai": 4, "batas": 16, "sisa": 12, "persen": 25 },
             "tokens":   { "terpakai": 6200, "batas": null },   // hanya info
             "habis": false,
             "reset":    { "detik": 70000, "bergulir": true, ... }
          },
          "tamu": { "batas_pesan": 3 }   // HANYA bila tidak login
        }

    PENTING: rincian kuota penyedia (request/hari, token/hari, batas per
    menit) sengaja TIDAK dikirim. Pengguna hanya perlu tahu bagiannya
    sendiri; detail kapasitas layanan adalah urusan pemilik situs dan
    sudah tersedia di /diagnostik (dibatasi kunci).

    Endpoint ini TIDAK memanggil penyedia AI, jadi tidak menghabiskan
    kuota sama sekali. Token yang tidak sah hanya membuat bagian "akun"
    tidak dikirim — tidak membuat permintaan gagal, karena tamu pun
    berhak melihat jatah tamu.
    """
    akun = await identitas_pemanggil(authorization)
    return await usage.ringkasan(
        PROVIDER,
        opsi_model_aktif(),
        sub=(akun or {}).get("sub"),
    )


# ---------------------------------------------------------------------
# 12d. ENDPOINT RIWAYAT PERCAKAPAN DI SERVER (/api/sessions)
# ---------------------------------------------------------------------
# Empat endpoint di bawah membuat riwayat sama di semua perangkat:
#
#   GET    /api/sessions          -> { tersedia, sessions, activeId }
#   POST   /api/sessions          -> simpan SATU sesi
#   POST   /api/sessions/sync     -> simpan BANYAK sesi (migrasi perangkat)
#   POST   /api/sessions/active   -> simpan sesi yang sedang dibuka
#   DELETE /api/sessions          -> hapus semua (atau ?id=... satu sesi)
#
# Semua WAJIB membawa `Authorization: Bearer <ID token Google>` yang sah.
# Endpoint /chat & /chat/stream TIDAK berubah sama sekali.
@app.get("/api/sessions")
async def sessions_daftar(authorization: Optional[str] = Header(None)):
    """
    Mengambil seluruh riwayat milik akun yang sedang login.

    `tersedia: false` berarti penyimpanan server sedang tidak bisa
    dipakai (belum dikonfigurasi / kuota habis). Frontend memakai tanda
    ini untuk memberi tahu pengguna bahwa riwayat sementara hanya ada di
    perangkat ini — bukan untuk menampilkan error.
    """
    akun = await identitas_pemanggil(authorization)
    if not akun:
        raise HTTPException(
            status_code=401,
            detail="Sesi login tidak valid. Silakan masuk ulang dengan Google.",
        )

    data = await penyimpanan.daftar_sesi(akun["sub"])
    return {
        "tersedia": data["tersedia"] and penyimpanan.tersedia(),
        "sesi": data["sessions"],
        "activeId": data["activeId"],
        "akun": {"name": akun.get("name", ""), "email": akun.get("email", "")},
    }


@app.post("/api/sessions")
async def sessions_simpan(
    body: SesiSimpan,
    authorization: Optional[str] = Header(None),
):
    """Menyimpan satu sesi (tambah baru atau perbarui)."""
    akun = await identitas_pemanggil(authorization)
    if not akun:
        raise HTTPException(
            status_code=401,
            detail="Sesi login tidak valid. Silakan masuk ulang dengan Google.",
        )

    tersimpan = await penyimpanan.simpan_sesi(akun["sub"], body.session)
    return {"tersimpan": tersimpan}


@app.post("/api/sessions/sync")
async def sessions_sinkron(
    body: SesiBanyak,
    authorization: Optional[str] = Header(None),
):
    """
    Menyimpan beberapa sesi sekaligus.

    Dipakai sekali saat pengguna login di perangkat yang sudah punya
    riwayat lokal, agar riwayat lama tidak hilang. Sesi yang sudah ada
    di server akan DIPERBARUI (bukan diduplikasi) karena kuncinya ID sesi.
    """
    akun = await identitas_pemanggil(authorization)
    if not akun:
        raise HTTPException(
            status_code=401,
            detail="Sesi login tidak valid. Silakan masuk ulang dengan Google.",
        )

    hasil = await penyimpanan.simpan_banyak(akun["sub"], body.sessions)
    return {
        "tersimpan": hasil["tersimpan"],
        "gagal": hasil["gagal"],
        "total": len(body.sessions),
    }


@app.post("/api/sessions/active")
async def sessions_aktif(
    body: SesiAktif,
    authorization: Optional[str] = Header(None),
):
    """Mencatat sesi yang sedang dibuka agar perangkat lain ikut sepakat."""
    akun = await identitas_pemanggil(authorization)
    if not akun:
        raise HTTPException(
            status_code=401,
            detail="Sesi login tidak valid. Silakan masuk ulang dengan Google.",
        )

    ok = await penyimpanan.simpan_aktif(akun["sub"], body.activeId)
    return {"tersimpan": ok}


@app.delete("/api/sessions")
async def sessions_hapus(
    id: Optional[str] = None,
    authorization: Optional[str] = Header(None),
):
    """
    Menghapus riwayat milik akun.

    ?id=<sesiId>  -> hapus satu sesi
    tanpa id      -> hapus SEMUA sesi akun itu

    Ini satu-satunya cara riwayat hilang dari server — sesuai permintaan
    pemilik situs: "tersimpan selama pengguna tidak menghapusnya".
    """
    akun = await identitas_pemanggil(authorization)
    if not akun:
        raise HTTPException(
            status_code=401,
            detail="Sesi login tidak valid. Silakan masuk ulang dengan Google.",
        )

    if id:
        ok = await penyimpanan.hapus_sesi(akun["sub"], id)
        return {"terhapus": 1 if ok else 0}

    ok = await penyimpanan.hapus_semua(akun["sub"])
    return {"terhapus": "semua" if ok else 1}


# ---------------------------------------------------------------------
# 11d. SYSTEM PROMPT TAMBAHAN: RISET WEB & LAMPIRAN
# ---------------------------------------------------------------------
# Instruksi ini ditambahkan HANYA bila fiturnya dipakai, sehingga
# percakapan biasa tetap memakai prompt dasar yang ringkas (hemat token).
PROMPT_RISET = (
    "Pengguna meminta RISET WEB. Sumber web SUDAH dibaca untukmu oleh "
    "sistem dan disertakan di bawah. Aturan: (1) Jawab berdasarkan isi "
    "sumber itu, jangan mengandalkan ingatan. (2) Utamakan informasi "
    "terbaru; bila sumber mencantumkan tanggal, sebutkan. (3) Sebutkan "
    "sumbernya (nama situs + nomor [1], [2]) agar pengguna bisa memeriksa "
    "sendiri. (4) Bila informasi tidak ditemukan atau sumber saling "
    "bertentangan, katakan terus terang. (5) Jangan mengarang kutipan, "
    "angka, atau tautan. (6) JANGAN mengatakan bahwa kamu tidak bisa "
    "membuka web — sumber sudah dibacakan untukmu."
)

PROMPT_LAMPIRAN = (
    "Pengguna melampirkan berkas. Baca seluruh isinya dengan teliti lalu "
    "jawab berdasarkan ISI BERKAS itu, bukan dugaan. Bila pertanyaan tidak "
    "bisa dijawab dari berkas, katakan bagian mana yang tidak ada. Jangan "
    "mengarang isi berkas."
)

PROMPT_GAMBAR = (
    "Pengguna melampirkan gambar. Amati isinya secara rinci (teks, objek, "
    "tata letak, angka) lalu jawab berdasarkan apa yang benar-benar "
    "terlihat. Bila ada bagian yang buram atau tidak terbaca, katakan "
    "demikian alih-alih menebak."
)


def susun_system_prompt(
    dasar: Optional[str],
    penelitian: bool = False,
    ada_lampiran: bool = False,
    ada_gambar: bool = False,
    konteks_riset: Optional[str] = None,
) -> str:
    """
    Menggabungkan system prompt dasar dengan instruksi tambahan yang
    relevan. Tambahan ditaruh di AKHIR agar mudah dibaca model dan tidak
    menimpa kepribadian dasar GungDev.

    `konteks_riset` adalah hasil pencarian web yang sudah dibaca server.
    Bila ada, konteks itu yang menjadi dasar jawaban (lihat riset.py).
    """
    bagian = [(dasar or DEFAULT_SYSTEM_PROMPT).strip()]
    if penelitian:
        bagian.append(PROMPT_RISET)
    if konteks_riset:
        bagian.append(konteks_riset)
    if ada_lampiran:
        bagian.append(PROMPT_LAMPIRAN)
    if ada_gambar:
        bagian.append(PROMPT_GAMBAR)
    return "\n\n".join(b for b in bagian if b)


async def lakukan_riset_server(
    permintaan: str,
    opsi: dict,
    messages: List[dict],
) -> tuple[Optional[str], List[dict]]:
    """
    Menjalankan riset web DI SERVER, berlaku untuk semua model/penyedia.

    Mengapa di server: model tidak punya akses internet sendiri. Sebelumnya
    riset hanya dikerjakan bila pengguna menekan tombol globe, dan hasilnya
    tipis karena bertumpu pada Bing yang ternyata selalu kosong. Sekarang:

      1. Riset berjalan OTOMATIS untuk semua model — pengguna tidak perlu
         menekan apa pun. `opsi["perlu_riset"]` sudah dinilai oleh
         pemanggil (lihat riset.perlu_riset), sedangkan tombol globe
         (request.research) hanya MEMAKSA riset lebih dalam.
      2. Model merumuskan kata kunci; server mencari di Yahoo + Google News
         + Marginalia + Wikipedia, lalu membaca isi halaman.
      3. Bila pengguna meminta "riset"/"research"/"teliti", riset
         dilanjutkan satu putaran lagi untuk menutup bagian yang belum
         terjawab (riset berlapis).

    Mengembalikan (teks_konteks, daftar_sumber):

      - `teks_konteks` None bila tidak ada hasil;
      - `daftar_sumber` berupa list ringkas ({nomor, judul, url, situs,
        tanggal}) untuk kartu sumber di UI. Nomornya sama dengan penanda
        `[1]`, `[2]` yang ditulis model.

    TIDAK pernah melempar exception: kegagalan riset tidak boleh
    menggagalkan chat — model tetap menjawab dari pengetahuannya sendiri,
    dan instruksi kejujuran di prompt membuatnya tidak mengaku-ngaku sudah
    menelusuri web.
    """
    if not opsi.get("perlu_riset"):
        return None, []

    dalam = bool(opsi.get("riset_dalam"))
    maunya_banyak = dalam or bool(opsi.get("penelitian"))

    try:
        # Langkah 1: minta model merumuskan query. Kalau gagal (mis.
        # model tidak tersedia), pakai pesan pengguna apa adanya.
        query = None
        try:
            pesan_query = [{"role": "system", "content": riset.instruksi_query()}]
            pesan_query += [
                m for m in messages if m.get("role") in ("user", "assistant")
            ][-4:]
            mentah = await complete(pesan_query, {**opsi, "penelitian": False, "max_tokens": 64})
            query = riset.bersihkan_query(mentah, permintaan)
        except Exception as exc:  # noqa: BLE001
            logger.info("Perumusan query riset gagal (%s); memakai pesan asli.", exc)
            query = riset.bersihkan_query(None, permintaan)

        query = query or permintaan

        # Langkah 2: putaran pertama. Saat riset mendalam, ambil lebih
        # banyak sumber sekaligus.
        hasil = await riset.cari_dan_baca(query, maks_sumber=6 if maunya_banyak else 4)
        semua_sumber = list(hasil.get("sumber") or [])
        kueri_dipakai = [query]

        # Langkah 3: putaran lanjutan HANYA bila diminta mendalam. Model
        # diminta menyebut celah yang belum terjawab, lalu dicari lagi.
        if dalam and riset.ada_hasil(hasil):
            try:
                pesan_lanjut = [
                    {
                        "role": "system",
                        "content": riset.instruksi_query_lanjutan(
                            permintaan, " | ".join(kueri_dipakai)
                        ),
                    }
                ]
                mentah2 = await complete(
                    pesan_lanjut, {**opsi, "penelitian": False, "max_tokens": 64}
                )
                query2 = riset.bersihkan_query(mentah2, "")
                if query2 and query2.upper() != "CUKUP" and len(query2) > 3:
                    kueri_dipakai.append(query2)
                    hasil2 = await riset.cari_dan_baca(query2, maks_sumber=4)
                    # Gabungkan, jangan buang putaran pertama.
                    semua_sumber.extend(hasil2.get("sumber") or [])
            except Exception as exc:  # noqa: BLE001
                logger.info("Putaran riset lanjutan dilewati (%s).", exc)

        if semua_sumber:
            hasil["sumber"] = semua_sumber[:8]
            hasil["teks"] = riset._susun_teks(hasil["sumber"])

        logger.info(
            "Riset '%s': %d sumber, %d putaran, dalam=%s",
            (query or "")[:50],
            len(hasil.get("sumber") or []),
            len(kueri_dipakai),
            dalam,
        )
        # Sumber ikut dikembalikan agar UI bisa menampilkan kartu sumber
        # bernomor (seperti ChatGPT). Hanya ringkasannya yang dikirim ke
        # browser, bukan isi halaman.
        return riset.konteks_untuk_model(hasil), riset.daftar_sumber(hasil)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Riset web gagal, chat tetap dilanjutkan: %s", exc)
        return None, []


async def siapkan_permintaan(request: ChatRequest) -> tuple[List[dict], dict]:
    """
    Mengerjakan semua persiapan yang sama untuk /chat dan /chat/stream:

      - memvalidasi pesan
      - mengekstrak lampiran (file -> teks, gambar -> divalidasi)
      - memilih model yang tepat (vision / browser / biasa)
      - melakukan riset web bila diminta (untuk SEMUA model)
      - menyusun messages + opsi

    Dikumpulkan di satu tempat agar kedua endpoint tidak mungkin
    berperilaku berbeda.
    """
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    blok_lampiran, gambar = siapkan_lampiran(request)
    opsi = resolve_options(request)
    opsi["penelitian"] = bool(request.research)
    opsi["ada_gambar"] = bool(gambar)

    # Riset web OTOMATIS untuk semua model.
    #
    # Dulu riset hanya jalan bila pengguna menekan tombol globe. Akibatnya
    # permintaan seperti "carikan artikel tentang X" dijawab dari ingatan,
    # dan model lalu mengaku tidak bisa menelusuri internet. Sekarang:
    #   - pesan yang wajar diriset -> riset jalan sendiri;
    #   - tombol globe (request.research) -> MEMAKSA riset lebih dalam;
    #   - permintaan yang mengandung "riset/research/teliti" -> berlapis.
    #
    # Pesan yang tidak wajar diriset (sapaan, basa-basi singkat) dilewati
    # agar tidak memperlambat jawaban tanpa menambah mutu.
    opsi["riset_dalam"] = bool(request.research) or riset.perlu_riset_dalam(user_message)
    opsi["perlu_riset"] = bool(opsi["riset_dalam"]) or riset.perlu_riset(user_message)

    # Susun messages dasar dulu: dipakai untuk merumuskan query riset.
    prompt_awal = susun_system_prompt(
        request.system_prompt,
        penelitian=opsi["perlu_riset"],
        ada_lampiran=bool(blok_lampiran),
        ada_gambar=bool(gambar),
    )
    messages_awal = build_messages(
        user_message,
        history=request.history,
        system_prompt=prompt_awal,
        images=gambar,
        blok_lampiran=blok_lampiran,
    )

    # Riset dijalankan SETELAH model dipilih: query dirumuskan model
    # yang sama dengan yang akan menjawab, agar relevan.
    konteks_riset, sumber = await lakukan_riset_server(
        user_message, opsi, messages_awal
    )

    # Sumber disimpan di `opsi` agar endpoint bisa mengirimnya ke UI
    # (kartu sumber). Ini TIDAK mengubah kontrak lama: field baru hanya
    # ditambahkan pada objek meta/done di SSE, dan klien lama mengabaikannya.
    opsi["sumber"] = sumber

    if konteks_riset:
        # penelitian=True di sini WAJIB: instruksi "jangan mengaku tidak
        # bisa membuka web" harus ikut terkirim, meski pengguna tidak
        # menekan tombol globe (riset otomatis).
        prompt = susun_system_prompt(
            request.system_prompt,
            penelitian=True,
            ada_lampiran=bool(blok_lampiran),
            ada_gambar=bool(gambar),
            konteks_riset=konteks_riset,
        )
        messages = build_messages(
            user_message,
            history=request.history,
            system_prompt=prompt,
            images=gambar,
            blok_lampiran=blok_lampiran,
        )
    else:
        messages = messages_awal

    return messages, opsi


# ---------------------------------------------------------------------
# 12c. ENDPOINT GET /capabilities — kemampuan tiap model
# ---------------------------------------------------------------------
@app.get("/capabilities")
async def capabilities():
    """
    Memberi tahu UI kemampuan tiap model.

    CATATAN PENTING: riset web TIDAK lagi ditandai per model, karena
    riset kini dikerjakan di server (lihat riset.py). Artinya SEMUA model
    bisa riset dengan kualitas yang sama — pengguna tidak perlu berganti
    model. Yang masih benar-benar berbeda per model hanyalah kemampuan
    membaca gambar (`vision`), karena itu batasan nyata dari modelnya
    sendiri.

    Yang dikirim hanya hal yang MEMANG terlihat pengguna (nama model
    sudah tampil di UI sejak awal): tidak ada URL, key, atau detail
    infrastruktur.
    """
    return {
        "models": [
            {
                "id": m,
                "vision": m in MODEL_VISION,
                # Riset selalu tersedia untuk semua model (dikerjakan
                # server), jadi nilainya selalu true.
                "browser": True,
            }
            for m in MODEL_DIIZINKAN
        ],
        # Penyedia cadangan aktif? Dipakai diagnostik/uji, bukan untuk
        # menampilkan nama backend ke pengguna.
        "cadangan_aktif": bool(GEMINI_API_KEY),
        "vision_default": MODEL_VISION_DEFAULT,
        "browser_default": MODEL_BROWSER_DEFAULT,
        # Kemampuan tingkat fitur (bukan per model).
        "fitur": {
            "gambar": True,
            "file": True,
            "riset": True,
            "maks_gambar": lampiran.MAKS_JUMLAH_GAMBAR,
            "maks_file": lampiran.MAKS_JUMLAH_FILE,
            "maks_file_mb": lampiran.MAKS_FILE_BYTES // (1024 * 1024),
        },
    }


# ---------------------------------------------------------------------
# 13. ENDPOINT POST /chat  (non-streaming, kontrak lama)
# ---------------------------------------------------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, authorization: Optional[str] = Header(None)):
    """
    Menerima {"message": "..."} lalu mengembalikan {"reply": "..."}.

    Kontrak lama TETAP SAMA. Field tambahan (history, system_prompt,
    temperature, max_tokens, model, images, files, research) opsional.

    Header `Authorization` juga OPSIONAL: bila berisi ID token Google
    yang sah, pemakaian dicatat atas nama akun itu sehingga panel Usage
    menampilkan angka miliknya sendiri. Tanpa header, chat tetap jalan
    seperti biasa (mode tamu) — kontrak tidak berubah.
    """
    messages, opsi = await siapkan_permintaan(request)

    # Identitas diverifikasi SEBELUM memanggil AI, agar jatah harian akun
    # bisa ditegakkan. Bila jatah habis, permintaan ditolak dengan pesan
    # yang jelas — kuota penyedia tidak ikut terpakai.
    akun = await identitas_pemanggil(authorization)
    jatah = await usage.periksa_jatah((akun or {}).get("sub"))
    if not jatah["boleh"]:
        raise HTTPException(status_code=429, detail=pesan_jatah_habis(jatah))

    # Batasi jumlah AKUN BARU per hari (lihat usage.daftarkan_akun).
    daftar = await usage.daftarkan_akun(jatah.get("sub"))
    if not daftar.get("diterima", True):
        raise HTTPException(status_code=429, detail=pesan_akun_baru_penuh(daftar))

    try:
        isi = await complete(messages, opsi)
        # Catat pemakaian (tidak pernah menggagalkan percakapan).
        await usage.catat_request(
            tokens=_token_untuk_catatan(messages, isi),
            model=opsi["model"],
            sub=jatah.get("sub"),
        )
        # `sumber` hanya ditambahkan bila riset benar-benar dipakai, agar
        # kontrak lama {reply} tetap utuh untuk chat biasa.
        hasil: dict = {"reply": isi}
        if opsi.get("sumber"):
            hasil["sumber"] = opsi["sumber"]
        return hasil
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ke_http_exception(exc) from exc


# ---------------------------------------------------------------------
# 14. ENDPOINT POST /chat/stream  (Server-Sent Events)
# ---------------------------------------------------------------------
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest, authorization: Optional[str] = Header(None)):
    """
    Versi streaming dari /chat. Format SSE (satu JSON per baris data:):

        data: {"delta": "Halo"}          <- potongan teks baru
        data: {"meta": {...}}            <- info model yang dipakai (opsional)
        data: {"done": true}             <- selesai
        data: {"error": "pesan error"}   <- terjadi masalah

    `meta` dikirim paling awal dan hanya muncul bila model diganti
    otomatis (mis. gambar diproses model vision). Klien lama yang tidak
    mengenal field ini akan mengabaikannya, jadi kontrak tetap aman.

    Header `Authorization` opsional seperti pada /chat: bila sah,
    pemakaian dicatat atas nama akun itu.
    """
    messages, opsi = await siapkan_permintaan(request)

    # Identitas diverifikasi SEKALI di awal (bukan di dalam generator)
    # agar hasil cache Google dipakai bersama oleh pencatatan usage.
    akun = await identitas_pemanggil(authorization)
    sub_akun = (akun or {}).get("sub")

    # Jatah diperiksa SEBELUM streaming dimulai. Bila diperiksa di dalam
    # generator, status HTTP sudah terkirim sebagai 200 dan pengguna
    # hanya melihat jawaban kosong — pesannya harus jelas.
    jatah = await usage.periksa_jatah(sub_akun)
    if not jatah["boleh"]:
        raise HTTPException(status_code=429, detail=pesan_jatah_habis(jatah))
    sub_akun = jatah.get("sub")

    # Batasi jumlah AKUN BARU per hari agar kuota situs tidak dihabiskan
    # akun-akun baru (lihat usage.daftarkan_akun). Akun yang sudah
    # terdaftar tidak pernah terkena aturan ini.
    daftar = await usage.daftarkan_akun(sub_akun)
    if not daftar.get("diterima", True):
        raise HTTPException(
            status_code=429,
            detail=pesan_akun_baru_penuh(daftar),
        )

    def sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def event_stream() -> AsyncIterator[str]:
        try:
            # Siapkan penanda baru: setiap permintaan punya status
            # "terpotong" sendiri.
            _mulai_pantau_terpotong()

            # Beri tahu lebih dulu bila model berbeda dari pilihan
            # pengguna, supaya UI bisa menjelaskannya dengan jujur.
            # Sumber riset ikut dikirim di sini agar UI bisa menyiapkan
            # kartu sumber sejak awal (nomornya sama dengan [1], [2] yang
            # ditulis model). Klien lama mengabaikan field tambahan ini.
            meta: dict = {"model": opsi["model"]}
            if opsi.get("penyesuaian"):
                meta["penyesuaian"] = opsi["penyesuaian"]
            if opsi.get("sumber"):
                meta["sumber"] = opsi["sumber"]
            if opsi.get("penyesuaian") or opsi.get("sumber"):
                yield sse({"meta": meta})

            ada_isi = False
            jawaban = []
            async for delta in stream(messages, opsi):
                ada_isi = True
                jawaban.append(delta)
                yield sse({"delta": delta})

            if not ada_isi:
                yield sse(
                    {"error": "Layanan AI tidak mengirim jawaban. Silakan coba lagi."}
                )
                return

            # ---------------------------------------------------------
            # SAMBUNG OTOMATIS (PENTING: MENGHEMAT JATAH PENGGUNA)
            # ---------------------------------------------------------
            # Bila model berhenti karena kehabisan token, jawabannya
            # belum selesai. Dulu pengguna harus mengetik "lanjut" —
            # dan itu MEMAKAN SATU JATAH PESAN LAGI padahal satu
            # pertanyaan belum selesai dijawab.
            #
            # Sekarang server melanjutkannya sendiri: minta lanjutan ke
            # model yang sama, lalu sambungkan hasilnya ke jawaban yang
            # sudah terkirim. Pengguna melihat satu jawaban utuh dari
            # satu kali kirim pesan, dan hanya dihitung satu jatah.
            #
            # Batasnya `MAKS_SAMBUNG`: cukup untuk merampungkan jawaban
            # panjang, tetapi tidak berputar tanpa akhir bila model
            # ternyata selalu kehabisan token.
            for putaran in range(MAKS_SAMBUNG):
                if not _apakah_terpotong():
                    break

                logger.info(
                    "Jawaban terpotong; menyambung otomatis (%s/%s).",
                    putaran + 1,
                    MAKS_SAMBUNG,
                )
                # Penanda direset supaya sambungan ini dinilai sendiri:
                # bila lanjutannya juga terpotong, kita sambung lagi.
                _mulai_pantau_terpotong()

                lanjutan_messages = _pesan_untuk_sambungan(
                    messages, "".join(jawaban)
                )
                dapat_lanjutan = False
                try:
                    async for delta in stream(lanjutan_messages, opsi):
                        dapat_lanjutan = True
                        jawaban.append(delta)
                        yield sse({"delta": delta})
                except Exception as exc:  # noqa: BLE001
                    # Sambungan gagal (mis. kuota penyedia habis di
                    # tengah). Yang sudah terkirim tetap utuh; hentikan
                    # saja sambungannya daripada menampilkan error.
                    logger.warning("Sambungan otomatis gagal: %s", exc)
                    break

                # Tidak ada tambahan teks -> tidak ada gunanya
                # menyambung lagi; hentikan agar tidak mengulang.
                if not dapat_lanjutan:
                    break

            # Catat pemakaian SEKALI setelah seluruh jawaban (termasuk
            # sambungannya) selesai terkumpul. Satu pertanyaan = satu
            # jatah, meskipun butuh beberapa putaran penyedia.
            await usage.catat_request(
                tokens=_token_untuk_catatan(messages, "".join(jawaban)),
                model=opsi["model"],
                sub=sub_akun,
            )

            # Bila setelah semua sambungan masih terpotong, beri tahu UI
            # supaya pengguna tidak perlu menebak. `done` tetap dikirim
            # agar klien lama tidak menunggu selamanya.
            if _apakah_terpotong():
                yield sse({"terpotong": True})

            yield sse({"done": True})

        except HTTPException as exc:
            yield sse({"error": exc.detail})
        except Exception as exc:  # noqa: BLE001
            logger.error("Streaming gagal: %s", exc)
            hasil = ke_http_exception(exc)
            yield sse({"error": hasil.detail})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            # "Connection: keep-alive" sengaja TIDAK dipakai: Vercel
            # (HTTP/2) mengabaikannya, dan di sebagian proxy justru
            # memicu buffering. Header di bawah ini yang penting.
            "X-Accel-Buffering": "no",   # cegah buffering di proxy (Nginx dsb.)
            "Content-Encoding": "identity",  # jangan kompres -> SSE tetap instan
        },
    )


# ---------------------------------------------------------------------
# 15. ENTRY POINT (python main.py)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = _env_int("PORT", 8000)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
