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
import json                 # payload SSE (streaming)
import logging              # log rapi di terminal
import os                   # membaca environment variable
from typing import AsyncIterator, List, Optional, Sequence

import httpx                # HTTP client async (dipakai Groq & cek kesehatan)
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

import usage                # pencatat & penyedia data kuota (usage)

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
]

# ---------------------------------------------------------------------
# KATALOG MODEL PUBLIK  (peta: ID publik -> nama model sebenarnya)
# ---------------------------------------------------------------------
# PENTING — alasan keamanan:
#   Frontend hanya pernah mengirim ID publik ("pintar", "cepat").
#   Pemetaan ke nama model asli HANYA ada di server ini. Dengan begitu
#   pengunjung tidak bisa melihat/menyalahgunakan nama model teknis,
#   dan tidak bisa memaksa server memakai model lain di luar daftar.
#
# Menambah/mengganti model: cukup ubah dict di bawah. Tidak perlu
# menyentuh frontend sama sekali.
KATALOG_MODEL = {
    "pintar": MODEL_GROQ_DEFAULT,   # -> "openai/gpt-oss-120b" (lebih teliti)
    "cepat": "openai/gpt-oss-20b",  # -> lebih ringan & cepat
}

# Model yang dipakai bila klien tidak mengirim pilihan / mengirim nilai
# yang tidak dikenal. Dipilih "pintar" agar kualitas jawaban terjaga.
MODEL_PUBLIK_DEFAULT = "pintar"


def model_dari_pilihan(pilihan: Optional[str]) -> str:
    """
    Menerjemahkan ID publik dari UI menjadi nama model sebenarnya.

    Nilai apa pun yang tidak ada di KATALOG_MODEL (termasuk None, string
    kosong, atau percobaan menyisipkan nama model lain) akan DIABAIKAN
    dan diganti model default. Ini mencegah klien memilih model di luar
    daftar gratis yang diizinkan.
    """
    kunci = (pilihan or "").strip().lower()
    if kunci in KATALOG_MODEL:
        return KATALOG_MODEL[kunci]
    if pilihan:
        logger.warning(
            "Pilihan model tidak dikenal (%r) — memakai model default.", pilihan
        )
    return KATALOG_MODEL[MODEL_PUBLIK_DEFAULT]


def label_publik_model(nama_model: str) -> str:
    """
    Kebalikannya: nama model asli -> ID publik, untuk keperluan log /
    panel usage agar nama teknis tidak ikut terekspos.
    """
    for kunci, nilai in KATALOG_MODEL.items():
        if nilai == nama_model:
            return kunci
    return MODEL_PUBLIK_DEFAULT


def opsi_model_aktif() -> str:
    """
    Nama model yang dianggap aktif untuk menghitung batas kuota di
    panel Usage.

    Panel Usage bersifat global (bukan per pengguna), jadi dipakai model
    yang terakhir tercatat — atau model default bila belum ada. Batas
    kuota kedua model gratis saat ini identik, sehingga angkanya tetap
    benar walau dua pengguna memilih model berbeda.
    """
    terakhir = usage.model_terakhir()
    if terakhir:
        return terakhir
    if PROVIDER == "groq":
        return KATALOG_MODEL[MODEL_PUBLIK_DEFAULT]
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
    Menentukan provider aktif.

    Urutan prioritas:
      1. AI_PROVIDER=groq / ollama  (dipaksa manual)
      2. GROQ_API_KEY ada           -> groq
      3. selain itu                 -> ollama
    """
    dipaksa = _env("AI_PROVIDER").lower()
    if dipaksa in ("groq", "ollama"):
        return dipaksa
    return "groq" if GROQ_API_KEY else "ollama"


PROVIDER = pilih_provider()
MODEL_NAME = GROQ_MODEL if PROVIDER == "groq" else OLLAMA_MODEL

if PROVIDER == "groq":
    logger.info("Provider aktif: GROQ (%s) model %s", GROQ_BASE_URL, MODEL_NAME)
    if not GROQ_API_KEY:
        logger.warning(
            "AI_PROVIDER=groq tetapi GROQ_API_KEY kosong. "
            "Permintaan akan gagal dengan HTTP 401."
        )
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
    # Pilihan model dari UI. Nilainya adalah ID publik (mis. "pintar"),
    # BUKAN nama model asli — supaya detail penyedia tidak terekspos.
    model: Optional[str] = Field(None, max_length=32, description="Pilihan model dari UI")


class ChatResponse(BaseModel):
    """Response /chat (kontrak lama, tidak berubah): {"reply": "..."}"""
    reply: str


class HealthResponse(BaseModel):
    """Response /health â€” menambah info provider tanpa merusak field 'status'."""
    status: str
    provider: str
    model: str


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
DEFAULT_MAX_TOKENS = 2048


def build_messages(
    message: str,
    history: Optional[Sequence[dict]] = None,
    system_prompt: Optional[str] = None,
) -> List[dict]:
    """Menyusun [system] + [riwayat 20 terakhir] + [pesan baru]."""
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

    messages.append({"role": "user", "content": message})
    return messages


def resolve_options(request: ChatRequest) -> dict:
    """
    Menentukan model, temperature, & batas token final.

    `model` di sini adalah NAMA MODEL ASLI hasil terjemahan dari ID
    publik yang dikirim UI — bukan nilai mentah dari klien.
    """
    model = model_dari_pilihan(request.model)
    return {
        "model": model,
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
                "Kuota gratis Groq tercapai atau terlalu banyak permintaan. "
                "Tunggu sebentar lalu coba lagi."
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


async def groq_complete(messages: List[dict], opsi: dict) -> str:
    """
    Meminta jawaban lengkap (non-streaming) ke Groq.

    Bila model yang dipasang ternyata sudah tidak tersedia (HTTP 404 —
    umumnya karena model berubah jadi Enterprise), otomatis dicoba
    model gratis lain sebelum menyerah. Dengan begitu situs tetap
    hidup meski GROQ_MODEL di environment sudah usang.
    """
    kandidat = [opsi.get("model") or GROQ_MODEL] + [
        m for m in _MODEL_GROQ_CADANGAN if m != (opsi.get("model") or GROQ_MODEL)
    ]
    error_terakhir: Optional[HTTPException] = None

    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
        for model in kandidat:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": opsi["temperature"],
                "max_completion_tokens": opsi["max_tokens"],
                "stream": False,
            }
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
                isi = data["choices"][0]["message"]["content"] or ""
            except (KeyError, IndexError, TypeError):
                isi = ""

            if not isi.strip():
                raise HTTPException(
                    status_code=502,
                    detail="Layanan AI mengembalikan jawaban kosong. Silakan coba lagi.",
                )
            return isi.strip()

    raise error_terakhir or HTTPException(
        status_code=502, detail=pesan_error_http(404)
    )


async def groq_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """
    Menghasilkan potongan teks (delta) dari Groq secara bertahap.

    Punya mekanisme cadangan model yang sama dengan groq_complete():
    bila model utama 404, coba model gratis berikutnya. Penentuan model
    dilakukan SEBELUM data dikirim ke pengguna, jadi aman untuk dialihkan.
    """
    kandidat = [opsi.get("model") or GROQ_MODEL] + [
        m for m in _MODEL_GROQ_CADANGAN if m != (opsi.get("model") or GROQ_MODEL)
    ]

    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
        res = None
        for model in kandidat:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": opsi["temperature"],
                "max_completion_tokens": opsi["max_tokens"],
                "stream": True,
            }
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

                try:
                    delta = obj["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, TypeError):
                    delta = ""
                if delta:
                    yield delta
        finally:
            # Tutup koneksi HTTP ke Groq, termasuk bila pengguna
            # menekan tombol "Stop" di tengah jawaban.
            await res.aclose()


# ---------------------------------------------------------------------
# 10. PEMANGGILAN KE OLLAMA (lokal)
# ---------------------------------------------------------------------
async def ollama_complete(messages: List[dict], opsi: dict) -> str:
    """Meminta jawaban lengkap ke Ollama lokal via HTTP API."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
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
        "messages": messages,
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
# 11. DISPATCHER: satu pintu untuk kedua provider
# ---------------------------------------------------------------------
async def complete(messages: List[dict], opsi: dict) -> str:
    """Menghasilkan jawaban lengkap dari provider aktif."""
    if PROVIDER == "groq":
        return await groq_complete(messages, opsi)
    return await ollama_complete(messages, opsi)


async def stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """Menghasilkan jawaban bertahap dari provider aktif."""
    if PROVIDER == "groq":
        async for delta in groq_stream(messages, opsi):
            yield delta
        return
    async for delta in ollama_stream(messages, opsi):
        yield delta


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
    """
    try:
        panjang = sum(len(str(m.get("content", ""))) for m in messages)
        panjang += len(jawaban or "")
        return max(1, panjang // 4)
    except Exception:  # noqa: BLE001
        return 0


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
# 12b. ENDPOINT GET /usage — pemakaian & sisa kuota AI
# ---------------------------------------------------------------------
@app.get("/usage")
async def usage_check():
    """
    Menampilkan pemakaian kuota AI hari ini.

        {
          "provider": "groq",
          "model": "openai/gpt-oss-120b",
          "requests": { "terpakai": 40, "batas": 1000, "sisa": 960, "persen": 4.0 },
          "tokens":   { "terpakai": 17500, "batas": 200000, "sisa": 182500, "persen": 8.8 },
          "per_menit": { "request_batas": 30, "token_batas": 8000, "reset_detik": 37 },
          "reset": { "detik": 25200, "jam": 7.0, "waktu_utc": "...", "zona": "UTC" },
          "sumber": "penyedia" | "perkiraan"
        }

    Endpoint ini TIDAK memanggil penyedia AI, jadi tidak menghabiskan
    kuota sama sekali. Angkanya berasal dari header respons terakhir
    atau dari pencatatan server sendiri.
    """
    return await usage.ringkasan(PROVIDER, opsi_model_aktif())


# ---------------------------------------------------------------------
# 13. ENDPOINT POST /chat  (non-streaming, kontrak lama)
# ---------------------------------------------------------------------
@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Menerima {"message": "..."} lalu mengembalikan {"reply": "..."}.

    Kontrak lama TETAP SAMA. Field tambahan (history, system_prompt,
    temperature, max_tokens) bersifat opsional.
    """
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    messages = build_messages(
        user_message,
        history=request.history,
        system_prompt=request.system_prompt,
    )
    opsi = resolve_options(request)

    try:
        isi = await complete(messages, opsi)
        # Catat pemakaian (tidak pernah menggagalkan percakapan).
        await usage.catat_request(tokens=_perkiraan_token(messages, isi), model=opsi["model"])
        return {"reply": isi}
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ke_http_exception(exc) from exc


# ---------------------------------------------------------------------
# 14. ENDPOINT POST /chat/stream  (Server-Sent Events)
# ---------------------------------------------------------------------
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Versi streaming dari /chat. Format SSE (satu JSON per baris data:):

        data: {"delta": "Halo"}          <- potongan teks baru
        data: {"done": true}             <- selesai
        data: {"error": "pesan error"}   <- terjadi masalah
    """
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    messages = build_messages(
        user_message,
        history=request.history,
        system_prompt=request.system_prompt,
    )
    opsi = resolve_options(request)

    def sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def event_stream() -> AsyncIterator[str]:
        try:
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

            # Catat pemakaian setelah jawaban selesai terkumpul.
            await usage.catat_request(
                tokens=_perkiraan_token(messages, "".join(jawaban)),
                model=opsi["model"],
            )

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
