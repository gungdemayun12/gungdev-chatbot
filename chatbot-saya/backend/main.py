"""
=====================================================================
 BACKEND GUNGDEV — FastAPI, multi-provider
=====================================================================
Satu server, dua mode penyedia AI:

  1. GROQ (dipakai saat deploy / publik)
       - API cloud OpenAI-compatible, sangat cepat (~280-500 token/detik)
       - Butuh GROQ_API_KEY (gratis di console.groq.com)
       - Cocok untuk Render / Railway / Fly.io (RAM kecil, tanpa GPU)

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
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------
# 2. KONFIGURASI DASAR
# ---------------------------------------------------------------------
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
GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")

# ---- Ollama (lokal) ----
OLLAMA_HOST = _env("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = _env("OLLAMA_MODEL", "deepseek-r1:7b")

# ---- Timeout ----
# Groq cepat; Ollama lokal di CPU bisa sangat lambat.
TIMEOUT_GROQ = _env_float("TIMEOUT_GROQ", 120)
TIMEOUT_OLLAMA = _env_float("TIMEOUT_OLLAMA", 300)

# ---- CORS ----
# Daftar origin tambahan dipisah koma, mis:
#   ALLOWED_ORIGINS=https://gungdev.vercel.app,https://gungdev.com
_extra_origins = [
    o.strip() for o in _env("ALLOWED_ORIGINS").split(",") if o.strip()
]

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


class ChatResponse(BaseModel):
    """Response /chat (kontrak lama, tidak berubah): {"reply": "..."}"""
    reply: str


class HealthResponse(BaseModel):
    """Response /health — menambah info provider tanpa merusak field 'status'."""
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
    """Menentukan temperature & batas token final."""
    return {
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
    description=f"Backend GungDev (provider: {PROVIDER}, model: {MODEL_NAME}).",
    version="2.0.0",
)


# ---------------------------------------------------------------------
# 7. CORS MIDDLEWARE
# ---------------------------------------------------------------------
# allow_origins_exact  = untuk development & domain yang didaftarkan manual
# allow_origin_regex   = menangani SEMUA subdomain Vercel (preview & production),
#                        karena browser tidak mendukung wildcard "https://*.vercel.app".
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",   # vite preview
        "http://127.0.0.1:4173",
        *_extra_origins,
    ],
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
        return "Waktu tunggu habis. Model mungkin masih memproses — coba lagi."
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
    """Meminta jawaban lengkap (non-streaming) ke Groq."""
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": opsi["temperature"],
        "max_completion_tokens": opsi["max_tokens"],
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
        res = await http.post(
            f"{GROQ_BASE_URL}/chat/completions",
            headers=_groq_headers(),
            json=payload,
        )
        res.raise_for_status()
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


async def groq_stream(messages: List[dict], opsi: dict) -> AsyncIterator[str]:
    """Menghasilkan potongan teks (delta) dari Groq secara bertahap."""
    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": opsi["temperature"],
        "max_completion_tokens": opsi["max_tokens"],
        "stream": True,
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
        async with http.stream(
            "POST",
            f"{GROQ_BASE_URL}/chat/completions",
            headers=_groq_headers(),
            json=payload,
        ) as res:
            if res.status_code >= 400:
                # Baca body error supaya pesannya informatif.
                body = await res.aread()
                logger.error("Groq menolak streaming: %s %s", res.status_code, body[:200])
                raise HTTPException(
                    status_code=502,
                    detail=pesan_error_http(res.status_code),
                )

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
# 12. ENDPOINT GET /health
# ---------------------------------------------------------------------
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Untuk indikator Online/Offline di frontend.

    Selalu membalas 'ok' bila server hidup; frontend lalu memastikan
    provider benar-benar bisa dipanggil saat pesan pertama dikirim.
    """
    return {"status": "ok", "provider": PROVIDER, "model": MODEL_NAME}


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
            async for delta in stream(messages, opsi):
                ada_isi = True
                yield sse({"delta": delta})

            if not ada_isi:
                yield sse(
                    {"error": "Layanan AI tidak mengirim jawaban. Silakan coba lagi."}
                )
                return

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
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",   # cegah buffering di proxy (Render/Nginx)
        },
    )


# ---------------------------------------------------------------------
# 15. ENTRY POINT (python main.py)
# ---------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    port = _env_int("PORT", 8000)
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
