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
MODEL_DIIZINKAN = [
    "openai/gpt-oss-120b",   # paling teliti
    "openai/gpt-oss-20b",    # paling cepat
    "qwen/qwen3.8-27b",      # alternatif (status preview di Groq)
]

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
}

# Model yang dipakai bila pesan berisi gambar tetapi pilihan pengguna
# bukan model vision.
MODEL_VISION_DEFAULT = "qwen/qwen3.8-27b"

# 2. MODEL_BROWSER — bisa melakukan riset web memakai tool bawaan Groq
#    "browser_search" (dijalankan di sisi Groq, tanpa API key tambahan).
#    Per dokumentasi Groq, hanya keluarga GPT-OSS yang mendukungnya.
MODEL_BROWSER = {
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
}

# Model pengganti bila pengguna meminta riset web dengan model yang
# tidak mendukung browser_search.
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
      - Minta riset -> model harus bisa browser_search (MODEL_BROWSER).
      - Selain itu  -> hormati pilihan pengguna apa adanya.

    Bila pilihan pengguna tidak memenuhi syarat, model diganti otomatis
    dan dikembalikan catatan penyesuaian, sehingga UI bisa memberi tahu
    pengguna dengan jujur alih-alih membiarkan permintaan gagal dengan
    error 400 dari penyedia.

    Bila gambar DAN riset diminta sekaligus, riset diutamakan: model
    vision tidak punya browser_search, dan jawaban riset yang dikarang
    lebih berbahaya daripada gambar yang diabaikan (pengguna tetap
    mendapat pemberitahuan lewat `catatan`).

    Mengembalikan: (nama_model, catatan_penyesuaian_atau_None)
    """
    dipilih = model_dari_pilihan(pilihan)
    model = dipilih

    if penelitian and model not in MODEL_BROWSER:
        logger.info(
            "Riset web diminta dengan model %s yang tidak mendukung "
            "browser_search. Beralih ke %s.",
            model,
            MODEL_BROWSER_DEFAULT,
        )
        model = MODEL_BROWSER_DEFAULT
    elif ada_gambar and model not in MODEL_VISION:
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
    penelitian: bool,
) -> Optional[str]:
    """Menjelaskan ke pengguna mengapa modelnya diganti (bahasa awam)."""
    if model_final == dipilih:
        return None

    if penelitian and model_final in MODEL_BROWSER:
        alasan = "belum mendukung riset web"
        if ada_gambar:
            alasan = "belum bisa riset web sekaligus membaca gambar"
        return (
            f"Model {dipilih} {alasan}, jadi permintaan ini diproses oleh "
            f"{model_final}."
        )

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

    # Minta AI melakukan riset di web (memakai browser_search bawaan Groq).
    research: bool = Field(
        False,
        description="True = lakukan riset web sebelum menjawab",
    )


class ChatResponse(BaseModel):
    """Response /chat (kontrak lama, tidak berubah): {"reply": "..."}"""
    reply: str


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
DEFAULT_MAX_TOKENS = 2048


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
    model vision, riset web butuh model dengan browser_search. Bila
    pilihan pengguna tidak memenuhi syarat, model diganti otomatis dan
    `penyesuaian` berisi penjelasan untuk pengguna.
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

    Riset web memakai tool bawaan Groq `browser_search`, yang berjalan
    di sisi server Groq — tidak perlu API key pencarian tambahan dan
    tidak perlu layanan pihak ketiga.

    Catatan penting dari dokumentasi Groq:
      - browser_search hanya untuk keluarga GPT-OSS.
      - `tool_choice: "required"` membuat model WAJIB mencari dulu,
        bukan menjawab dari ingatan. Itu yang membuat risetnya nyata.
      - reasoning rendah disarankan agar sesi browsing tidak terlalu
        panjang (hemat token kuota gratis).
      - browser_search tidak kompatibel dengan structured outputs; kita
        tidak memakainya, jadi aman.

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

    if opsi.get("penelitian"):
        payload["tools"] = [{"type": "browser_search"}]
        payload["tool_choice"] = "required"
        # Riset butuh waktu; beri ruang token lebih besar agar jawaban
        # tidak terpotong di tengah. Tetap di bawah batas 8.000 TPM.
        payload["max_completion_tokens"] = max(opsi["max_tokens"], 2048)

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

    async with httpx.AsyncClient(timeout=TIMEOUT_GROQ) as http:
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

                try:
                    delta = obj["choices"][0]["delta"].get("content") or ""
                except (KeyError, IndexError, TypeError):
                    delta = ""
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
async def usage_check(authorization: Optional[str] = Header(None)):
    """
    Menampilkan pemakaian kuota AI hari ini.

        {
          "provider": "gungdev",
          "model": "gungdev",
          "requests": { "terpakai": 40, "batas": 1000, "sisa": 960, "persen": 4.0 },
          "tokens":   { "terpakai": 17500, "batas": 200000, "sisa": 182500, "persen": 8.8 },
          "per_menit": { "request_batas": 30, "token_batas": 8000, "reset_detik": 37 },
          "reset": { "detik": 25200, "jam": 7.0, "waktu_utc": "...", "zona": "UTC" },
          "sumber": "penyedia" | "perkiraan",
          "akun": { ... }      // HANYA bila pemanggil login (terverifikasi)
        }

    Bagian "akun" berisi pemakaian MILIK AKUN ITU SENDIRI, sehingga tiap
    pengguna punya angka masing-masing seperti layanan AI pada umumnya.
    Angka kuota utama tetap global karena kuota penyedia memang dipakai
    bersama.

    Endpoint ini TIDAK memanggil penyedia AI, jadi tidak menghabiskan
    kuota sama sekali. Token yang tidak sah hanya membuat bagian "akun"
    tidak dikirim — tidak membuat permintaan gagal, karena tamu pun
    berhak melihat sisa kuota.
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
    "Pengguna meminta RISET WEB. Kamu punya akses penjelajah web. "
    "Aturan: (1) Selalu cari informasi terbaru di web sebelum menjawab, "
    "jangan mengandalkan ingatan. (2) Utamakan sumber yang kredibel dan "
    "terbaru. (3) Sebutkan sumbernya secara ringkas (nama situs + tanggal "
    "bila ada) agar pengguna bisa memeriksa sendiri. (4) Bila informasi "
    "tidak ditemukan atau sumber saling bertentangan, katakan terus "
    "terang. (5) Jangan mengarang kutipan, angka, atau tautan."
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
) -> str:
    """
    Menggabungkan system prompt dasar dengan instruksi tambahan yang
    relevan. Tambahan ditaruh di AKHIR agar mudah dibaca model dan tidak
    menimpa kepribadian dasar GungDev.
    """
    bagian = [(dasar or DEFAULT_SYSTEM_PROMPT).strip()]
    if penelitian:
        bagian.append(PROMPT_RISET)
    if ada_lampiran:
        bagian.append(PROMPT_LAMPIRAN)
    if ada_gambar:
        bagian.append(PROMPT_GAMBAR)
    return "\n\n".join(b for b in bagian if b)


def siapkan_permintaan(request: ChatRequest) -> tuple[List[dict], dict]:
    """
    Mengerjakan semua persiapan yang sama untuk /chat dan /chat/stream:

      - memvalidasi pesan
      - mengekstrak lampiran (file -> teks, gambar -> divalidasi)
      - memilih model yang tepat (vision / browser / biasa)
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

    prompt = susun_system_prompt(
        request.system_prompt,
        penelitian=opsi["penelitian"],
        ada_lampiran=bool(blok_lampiran),
        ada_gambar=bool(gambar),
    )

    messages = build_messages(
        user_message,
        history=request.history,
        system_prompt=prompt,
        images=gambar,
        blok_lampiran=blok_lampiran,
    )
    return messages, opsi


# ---------------------------------------------------------------------
# 12c. ENDPOINT GET /capabilities — kemampuan tiap model
# ---------------------------------------------------------------------
@app.get("/capabilities")
async def capabilities():
    """
    Memberi tahu UI model mana yang bisa membaca gambar dan mana yang
    bisa riset web, supaya pilihan bisa ditandai di menu dan pengguna
    tidak kaget ketika modelnya berganti otomatis.

    Yang dikirim hanya hal yang MEMANG terlihat pengguna (nama model
    sudah tampil di UI sejak awal): tidak ada URL, key, atau detail
    infrastruktur.
    """
    return {
        "models": [
            {
                "id": m,
                "vision": m in MODEL_VISION,
                "browser": m in MODEL_BROWSER,
            }
            for m in MODEL_DIIZINKAN
        ],
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
    messages, opsi = siapkan_permintaan(request)

    try:
        isi = await complete(messages, opsi)
        # Catat pemakaian (tidak pernah menggagalkan percakapan).
        akun = await identitas_pemanggil(authorization)
        await usage.catat_request(
            tokens=_perkiraan_token(messages, isi),
            model=opsi["model"],
            sub=(akun or {}).get("sub"),
        )
        return {"reply": isi}
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
    messages, opsi = siapkan_permintaan(request)

    # Identitas diverifikasi SEKALI di awal (bukan di dalam generator)
    # agar hasil cache Google dipakai bersama oleh pencatatan usage.
    akun = await identitas_pemanggil(authorization)
    sub_akun = (akun or {}).get("sub")

    def sse(obj: dict) -> str:
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def event_stream() -> AsyncIterator[str]:
        try:
            # Beri tahu lebih dulu bila model berbeda dari pilihan
            # pengguna, supaya UI bisa menjelaskannya dengan jujur.
            if opsi.get("penyesuaian"):
                yield sse(
                    {
                        "meta": {
                            "model": opsi["model"],
                            "penyesuaian": opsi["penyesuaian"],
                        }
                    }
                )

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
                sub=sub_akun,
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
