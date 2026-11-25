"""
=====================================================================
 BACKEND CHATBOT AI  (FastAPI + Ollama lokal)
=====================================================================
File ini adalah satu-satunya file Python yang dibutuhkan untuk server.

Cara menjalankan:
    1. pip install -r requirements.txt
    2. pastikan Ollama sudah jalan dan modelnya sudah diunduh
       (ollama pull deepseek-r1:7b)
    3. uvicorn main:app --reload --port 8000

Dokumentasi API otomatis tersedia di:
    http://localhost:8000/docs
=====================================================================
"""

# ---------------------------------------------------------------------
# 1. IMPORT LIBRARY
# ---------------------------------------------------------------------
import os                 # untuk membaca environment variable (.env)
import json               # untuk menyusun payload SSE (streaming)
import logging            # untuk menulis log ke terminal
from typing import List, Optional, Sequence   # tipe data untuk daftar riwayat pesan

# load_dotenv() bertugas membaca file .env dan memasukkannya ke os.environ.
# Dipakai untuk memuat file .env (opsional).
from dotenv import load_dotenv

# FastAPI = kerangka kerja web, HTTPException = untuk mengembalikan error HTTP.
# CORSMiddleware = izin agar frontend (port 5173) boleh memanggil backend ini.
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# Client (bukan modul ollama global) supaya kita bisa menentukan host + headers
# sendiri, yaitu Ollama LOKAL di http://localhost:11434.
from ollama import Client, ResponseError

# ---------------------------------------------------------------------
# 2. KONFIGURASI DASAR
# ---------------------------------------------------------------------
# (Opsional) Baca file .env bila ada. Host & model kini ditulis langsung
# di kode (Ollama lokal tanpa API Key), jadi file .env TIDAK wajib ada.
# override=True: nilai di .env selalu menang atas sisa variabel lama
# di terminal, supaya tidak "nyangkut" ke pengaturan sebelumnya.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=_ENV_PATH, override=True)

# Nama model lokal yang dipakai: deepseek-r1:7b
# (unduh sekali dengan: ollama pull deepseek-r1:7b)
MODEL_NAME = "deepseek-r1:7b"

# Alamat server Ollama lokal. Tidak ada API Key karena hanya bisa
# diakses dari komputer ini. Jalankan aplikasi Ollama / "ollama serve".
OLLAMA_HOST = "http://localhost:11434"

# Batas waktu (detik) untuk satu permintaan ke Ollama.
# Model lokal di CPU bisa butuh waktu lama, jadi beri ruang lebih.
REQUEST_TIMEOUT = 300

# Setup logging supaya pesan error terlihat rapi di terminal.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("chatbot-backend")


# ---------------------------------------------------------------------
# 3. INISIALISASI KLIEN OLLAMA LOKAL
# ---------------------------------------------------------------------
# Karena memakai Ollama lokal, TIDAK ada API Key dan TIDAK ada header
# Authorization. Server Ollama hanya mendengarkan di komputer ini
# (http://localhost:11434) sehingga tidak perlu autentikasi.
client = Client(host="http://localhost:11434", timeout=REQUEST_TIMEOUT)

logger.info("Terhubung ke Ollama lokal http://localhost:11434 memakai model %s", MODEL_NAME)


# ---------------------------------------------------------------------
# 4. SKEMA DATA (validasi request & response)
# ---------------------------------------------------------------------
class ChatRequest(BaseModel):
    """
    Bentuk body JSON yang diterima endpoint POST /chat:
        {"message": "Halo!"}

    Field(...) artinya wajib diisi. min_length=1 memastikan tidak kosong.
    history (opsional) = riwayat percakapan sebelumnya agar AI ingat konteks.
    """
    message: str = Field(..., min_length=1, max_length=8000, description="Pesan dari user")
    history: List[dict] = Field(
        default_factory=list,
        description="Riwayat percakapan lama, format: [{role, content}, ...]",
    )
    # Semua field opsional di bawah ini agar kontrak lama tetap kompatibel:
    # {"message": "..."} saja tetap valid dan memakai nilai default.
    system_prompt: Optional[str] = Field(None, description="Instruksi kustom pengguna")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Kreativitas jawaban")
    max_tokens: Optional[int] = Field(None, ge=16, le=8192, description="Panjang maksimum jawaban")


class ChatResponse(BaseModel):
    """Bentuk JSON yang dikembalikan: {"reply": "..."}"""
    reply: str


# ---------------------------------------------------------------------
# 5. INSTANCE APLIKASI FASTAPI
# ---------------------------------------------------------------------
app = FastAPI(
    title="Chatbot AI Backend",
    description=f"Backend chatbot berbasis FastAPI + Ollama lokal ({MODEL_NAME}).",
    version="1.0.0",
)

# ---------------------------------------------------------------------
# 6. CORS MIDDLEWARE
# ---------------------------------------------------------------------
# Browser memblokir request dari domain berbeda (frontend 5173 -> backend 8000)
# kecuali backend mengizinkannya lewat header CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",   # frontend Vite saat development
        "http://127.0.0.1:5173",   # alternatif alamat lokal
    ],
    # allow_origin_regex dipakai untuk domain Vercel (preview & production),
    # karena wildcard seperti "https://*.vercel.app" tidak didukung
    # langsung oleh spesifikasi CORS di browser.
    allow_origin_regex=r"https://([a-zA-Z0-9-]+\.)*vercel\.app",
    allow_methods=["*"],   # izinkan GET, POST, OPTIONS, dll.
    allow_headers=["*"],   # izinkan semua header (Content-Type, Authorization, ...)
    allow_credentials=False,
)


# ---------------------------------------------------------------------
# 7. FUNGSI PEMBANTU: MENERJEMAHKAN ERROR OLLAMA -> HTTPException
# ---------------------------------------------------------------------
def raise_informative_error(exc: Exception) -> None:
    """
    Mengubah error mentah dari library ollama menjadi pesan HTTP yang
    ramah dibaca oleh pengguna maupun developer frontend.
    """

    # --- Error dari server Ollama (status code 4xx/5xx) ---
    if isinstance(exc, ResponseError):
        status = getattr(exc, "status_code", None)
        # beberapa versi library menyimpan kode di error.error / error dict
        detail_asli = getattr(exc, "error", None) or str(exc)

        if status == 401:
            raise HTTPException(
                status_code=401,
                detail=(
                    "Ollama menolak permintaan (401). Backend ini memakai Ollama lokal "
                    "di http://localhost:11434 tanpa API Key."
                ),
            )
        if status == 402:
            raise HTTPException(
                status_code=402,
                detail=(
                    "Ollama meminta pembayaran (HTTP 402). Backend ini seharusnya memakai "
                    "Ollama lokal di http://localhost:11434 yang tidak butuh kredit."
                ),
            )
        if status == 403:
            raise HTTPException(
                status_code=403,
                detail="Akses ditolak oleh server Ollama (HTTP 403).",
            )
        if status == 404:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Model '{MODEL_NAME}' tidak ditemukan di Ollama lokal. "
                    f"Unduh dulu dengan: ollama pull {MODEL_NAME}"
                ),
            )
        if status == 410:
            raise HTTPException(
                status_code=410,
                detail=(
                    f"Model '{MODEL_NAME}' sudah tidak tersedia (HTTP 410). "
                    "Ganti MODEL_NAME di file .env dengan model yang sudah diunduh."
                ),
            )
        if status == 429:
            raise HTTPException(
                status_code=429,
                detail="Kuota habis atau terlalu banyak permintaan. Coba lagi beberapa saat lagi.",
            )
        if status and 500 <= status < 600:
            raise HTTPException(
                status_code=502,
                detail=f"Server Ollama sedang bermasalah (HTTP {status}). Coba lagi nanti.",
            )
        # Status lain yang tidak disebutkan di atas
        raise HTTPException(
            status_code=502,
            detail=f"Ollama mengembalikan error (HTTP {status}): {detail_asli}",
        )

    # --- Timeout (server terlalu lama menjawab) ---
    if isinstance(exc, TimeoutError) or "timeout" in str(exc).lower():
        raise HTTPException(
            status_code=504,
            detail="Permintaan ke Ollama timeout. Model lokal mungkin masih memproses — silakan coba lagi.",
        )

    # --- Gagal konek (internet mati / host salah) ---
    pesan = str(exc).lower()
    if "connection" in pesan or "connect" in pesan or "getaddrinfo" in pesan:
        raise HTTPException(
            status_code=503,
            detail=(
                "Tidak dapat terhubung ke Ollama lokal di "
                f"{OLLAMA_HOST}. Pastikan aplikasi Ollama sudah berjalan "
                "(buka aplikasi Ollama atau jalankan 'ollama serve')."
            ),
        )

    # --- Fallback: error tak terduga ---
    logger.exception("Error tidak terduga saat memanggil Ollama")
    raise HTTPException(
        status_code=500,
        detail=f"Terjadi kesalahan internal: {exc}",
    )


# ---------------------------------------------------------------------
# 8. ENDPOINT GET /health
# ---------------------------------------------------------------------
@app.get("/health")
def health_check():
    """
    Endpoint sederhana untuk memastikan server hidup.
    Berguna untuk monitoring / cek cepat di browser.
    """
    return {"status": "ok"}


# ---------------------------------------------------------------------
# 9. SYSTEM PROMPT & OPSI MODEL (dipakai /chat dan /chat/stream)
# ---------------------------------------------------------------------
# Instruksi bawaan agar jawaban GungDev rapi, jujur, dan tidak bertele-tele.
DEFAULT_SYSTEM_PROMPT = (
    "Kamu adalah GungDev, asisten AI berbahasa Indonesia yang ramah, akurat, dan "
    "jelas. Jawab dalam bahasa yang digunakan pengguna. Jika tidak yakin dengan "
    "sebuah fakta, katakan terus terang, jangan mengarang. Gunakan format Markdown "
    "seperlunya. Jawab langsung ke inti tanpa basa-basi berlebihan."
)

# Temperature rendah agar jawaban faktual lebih stabil/tidak mengarang.
DEFAULT_TEMPERATURE = 0.4

# Batas panjang jawaban (token).
DEFAULT_MAX_TOKENS = 2048


def build_messages(
    message: str,
    history: Optional[Sequence[dict]] = None,
    system_prompt: Optional[str] = None,
) -> List[dict]:
    """
    Menyusun daftar pesan untuk Ollama:
    [pesan sistem] + [riwayat percakapan] + [pesan user terbaru].
    """
    messages: List[dict] = [
        {"role": "system", "content": (system_prompt or DEFAULT_SYSTEM_PROMPT).strip()}
    ]

    # Ambil maksimal 20 pesan terakhir agar konteks tidak membengkak.
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


# ---------------------------------------------------------------------
# 9. ENDPOINT GET /health
# ---------------------------------------------------------------------
@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    """
    Menerima {"message": "..."} lalu mengembalikan {"reply": "..."}.

    Kontrak lama TETAP SAMA (dipakai klien lama). Field tambahan
    (history, system_prompt, temperature, max_tokens) bersifat opsional.
    """

    # 9a. Ambil dan bersihkan pesan user.
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Pesan tidak boleh kosong.")

    # 9b. Susun percakapan (system + history + pesan baru).
    messages = build_messages(
        user_message,
        history=request.history,
        system_prompt=request.system_prompt,
    )

    # Opsi model: temperature rendah & batas token.
    options = {
        "temperature": (
            request.temperature if request.temperature is not None else DEFAULT_TEMPERATURE
        ),
        "num_predict": (
            request.max_tokens if request.max_tokens is not None else DEFAULT_MAX_TOKENS
        ),
    }

    # 9c. Kirim ke Ollama lokal dengan try/except.
    try:
        response = client.chat(
            model="deepseek-r1:7b",  # <--- model lokal yang sudah diunduh
            messages=messages,
            options=options,
        )

        # Respons library ollama berbentuk objek; teks jawaban ada di
        # response["message"]["content"] (atau response.message.content).
        content = ""
        try:
            content = response["message"]["content"]
        except (KeyError, TypeError):
            content = getattr(getattr(response, "message", None), "content", "") or ""

        if not content or not str(content).strip():
            raise HTTPException(
                status_code=502,
                detail="Ollama mengembalikan balasan kosong. Silakan coba lagi.",
            )

        return {"reply": str(content).strip()}

    except HTTPException:
        # Jangan dibungkus ulang - teruskan apa adanya.
        raise
    except Exception as exc:  # noqa: BLE001 - semua error diterjemahkan di helper
        logger.error("Gagal memanggil Ollama: %s", exc)
        raise_informative_error(exc)


# ---------------------------------------------------------------------
# 10. ENDPOINT POST /chat/stream  (Server-Sent Events)
# ---------------------------------------------------------------------
@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """
    Versi STREAMING dari /chat. Jawaban dikirim potongan demi potongan
    (token per token) memakai protokol SSE agar UI bisa mengetik bertahap.

    Format yang dikirim ke browser (satu objek JSON per baris "data:"):
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

    options = {
        "temperature": (
            request.temperature if request.temperature is not None else DEFAULT_TEMPERATURE
        ),
        "num_predict": (
            request.max_tokens if request.max_tokens is not None else DEFAULT_MAX_TOKENS
        ),
    }

    def event_stream():
        """Generator: menghasilkan event SSE sampai jawaban selesai."""
        try:
            for chunk in client.chat(
                model="deepseek-r1:7b",
                messages=messages,
                options=options,
                stream=True,
            ):
                # Ambil potongan teks dari tiap chunk.
                try:
                    token = chunk["message"]["content"]
                except (KeyError, TypeError):
                    token = getattr(getattr(chunk, "message", None), "content", "") or ""

                if token:
                    yield f"data: {json.dumps({'delta': token}, ensure_ascii=False)}\n\n"

            yield f"data: {json.dumps({'done': True})}\n\n"

        except GeneratorExit:
            # Klien menutup koneksi (tombol Stop) — hentikan dengan tenang.
            logger.info("Klien menghentikan streaming.")
        except Exception as exc:  # noqa: BLE001
            logger.error("Gagal streaming dari Ollama: %s", exc)
            # Terjemahkan error menjadi pesan ramah, kirim sebagai event error.
            try:
                raise_informative_error(exc)
            except HTTPException as http_exc:
                pesan = http_exc.detail
            except Exception:  # noqa: BLE001
                pesan = "Terjadi kesalahan saat menghubungi Ollama."
            yield f"data: {json.dumps({'error': pesan}, ensure_ascii=False)}\n\n"

    # Header SSE: no-cache + X-Accel-Buffering agar tidak di-buffer proxy.
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------
# 10. MENJALANKAN SERVER (opsional)
# ---------------------------------------------------------------------
# Cara utama tetap: uvicorn main:app --reload --port 8000
# Blok di bawah bisa dipakai dengan: python main.py
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
