"""
uji_gemini.py — memastikan Google Gemini terpasang sebagai penyedia
cadangan dengan benar, dan failover antar penyedia bekerja.

MENGAPA PENTING
---------------
Groq membatasi 200.000 token/hari per model. Dulu, begitu kuota itu
habis, SELURUH situs berhenti melayani padahal penyedia lain masih punya
sisa kuota. Gemini ditambahkan supaya ada jalur kedua yang gratis.

Yang diuji di sini:
  1. Konfigurasi Gemini terbaca dari environment.
  2. Model Gemini dirutekan ke penyedia "gemini" (bukan Groq).
  3. Bila kunci Gemini kosong, model Gemini TIDAK membuat situs error
     (dialihkan ke penyedia yang kuncinya ada).
  4. Urutan failover benar: penyedia pilihan lebih dulu, lalu yang lain.
  5. Failover HANYA terjadi pada status kuota habis (429/402), BUKAN
     pada 401/403 (masalah kunci) atau 500 (masalah server).
  6. Streaming tidak berpindah penyedia setelah teks mulai terkirim.
  7. Endpoint OpenAI-compatible Gemini dipakai (bukan API native).

Jalankan: python uji_gemini.py
"""

import asyncio
import os
import sys

os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://upstash-tiruan.local")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "tiruan")
os.environ.setdefault("GOOGLE_CLIENT_ID", "uji.apps.googleusercontent.com")

import main  # noqa: E402
from fastapi import HTTPException  # noqa: E402

LULUS = 0
GAGAL = 0


def cek(nama: str, ok: bool, info: str = "") -> None:
    global LULUS, GAGAL
    if ok:
        LULUS += 1
        print(f"LULUS  {nama}" + (f" — {info}" if info else ""))
    else:
        GAGAL += 1
        print(f"GAGAL  {nama}" + (f" — {info}" if info else ""))


def dengan_kunci(gemini: str, groq: str, openrouter: str):
    """Konteks: pasang kunci tertentu lalu kembalikan seperti semula."""

    class _Ctx:
        def __enter__(self):
            self.lama = (
                main.GEMINI_API_KEY,
                main.GROQ_API_KEY,
                main.OPENROUTER_API_KEY,
            )
            main.GEMINI_API_KEY = gemini
            main.GROQ_API_KEY = groq
            main.OPENROUTER_API_KEY = openrouter

        def __exit__(self, *a):
            (
                main.GEMINI_API_KEY,
                main.GROQ_API_KEY,
                main.OPENROUTER_API_KEY,
            ) = self.lama

    return _Ctx()


# ---------------------------------------------------------------------
print("=== 1. KONFIGURASI GEMINI ===")
# ---------------------------------------------------------------------
cek(
    "Base URL memakai endpoint OpenAI-compatible",
    main.GEMINI_BASE_URL.endswith("/openai"),
    main.GEMINI_BASE_URL,
)
cek(
    "Base URL bukan API native (tidak ada v1beta saja)",
    "/v1beta/openai" in main.GEMINI_BASE_URL,
    main.GEMINI_BASE_URL,
)
cek(
    "Model default terisi",
    bool(main.GEMINI_MODEL_DEFAULT),
    main.GEMINI_MODEL_DEFAULT,
)
cek(
    "Ada daftar model cadangan (minimal 2)",
    len(main.GEMINI_MODELS) >= 2,
    ", ".join(main.GEMINI_MODELS),
)
cek(
    "Timeout Gemini masuk akal (10-300 detik)",
    10 <= main.TIMEOUT_GEMINI <= 300,
    f"{main.TIMEOUT_GEMINI} dtk",
)

# ---------------------------------------------------------------------
print("\n=== 2. MODEL GEMINI DIKENALI SISTEM ===")
# ---------------------------------------------------------------------
for m in main.GEMINI_MODELS:
    cek(f"'{m}' masuk allowlist MODEL_DIIZINKAN", m in main.MODEL_DIIZINKAN)
    cek(f"'{m}' terdaftar bisa membaca gambar", m in main.MODEL_VISION)

# ---------------------------------------------------------------------
print("\n=== 3. ROUTING: MODEL GEMINI -> PENYEDIA GEMINI ===")
# ---------------------------------------------------------------------
with dengan_kunci("kunci-gemini", "kunci-groq", "kunci-openrouter"):
    for m in main.GEMINI_MODELS:
        tujuan = main._penyedia_untuk_model(m)
        cek(f"'{m}' dirutekan ke gemini", tujuan == "gemini", tujuan)

    # Pilihan lama tidak boleh berubah perilakunya.
    cek(
        "Model Groq tetap ke groq",
        main._penyedia_untuk_model("openai/gpt-oss-120b") == "groq",
    )
    cek(
        "Model OpenRouter tetap ke openrouter",
        main._penyedia_untuk_model("google/gemma-4-31b-it:free") == "openrouter",
    )

# ---------------------------------------------------------------------
print("\n=== 4. TANPA KUNCI GEMINI (kondisi sebelum key dipasang) ===")
# ---------------------------------------------------------------------
with dengan_kunci("", "kunci-groq", "kunci-openrouter"):
    cek(
        "Model Gemini dialihkan ke groq (situs tetap hidup)",
        main._penyedia_untuk_model("gemini-2.5-flash") == "groq",
        main._penyedia_untuk_model("gemini-2.5-flash"),
    )
    urutan = main._urutan_penyedia("groq")
    cek(
        "Gemini TIDAK muncul di urutan failover",
        "gemini" not in urutan,
        ",".join(urutan) or "(kosong)",
    )

with dengan_kunci("", "", ""):
    cek(
        "Semua kunci kosong -> tidak crash",
        isinstance(main._penyedia_untuk_model("gemini-2.5-flash"), str),
    )
    cek("Urutan failover kosong bila tak ada kunci", main._urutan_penyedia("groq") == [])

# ---------------------------------------------------------------------
print("\n=== 5. URUTAN FAILOVER ===")
# ---------------------------------------------------------------------
with dengan_kunci("kunci-gemini", "kunci-groq", "kunci-openrouter"):
    u = main._urutan_penyedia("groq")
    cek(
        "Groq lebih dulu, lalu Gemini, lalu OpenRouter",
        u == ["groq", "gemini", "openrouter"],
        "->".join(u),
    )
    u2 = main._urutan_penyedia("gemini")
    cek(
        "Pilihan pengguna dihormati (gemini dulu)",
        u2[0] == "gemini",
        "->".join(u2),
    )
    cek("Semua penyedia muncul sekali", len(u2) == len(set(u2)) == 3)

# ---------------------------------------------------------------------
print("\n=== 6. FAILOVER HANYA SAAT KUOTA HABIS ===")
# ---------------------------------------------------------------------
_dipanggil = {"gemini": 0, "groq": 0}


async def _groq_habis(messages, opsi):
    _dipanggil["groq"] += 1
    raise HTTPException(status_code=429, detail="kuota habis")


async def _gemini_ok(messages, opsi):
    _dipanggil["gemini"] += 1
    return "jawaban dari gemini"


async def _groq_kunci_salah(messages, opsi):
    _dipanggil["groq"] += 1
    raise HTTPException(status_code=401, detail="kunci salah")


async def _groq_server_error(messages, opsi):
    _dipanggil["groq"] += 1
    raise HTTPException(status_code=500, detail="server error")


def jalankan_failover(groq_fn, model="openai/gpt-oss-120b"):
    """Panggil main.complete() dengan groq diganti fungsi tiruan."""
    _dipanggil["gemini"] = 0
    _dipanggil["groq"] = 0
    lama_groq, lama_gemini = main.groq_complete, main.gemini_complete
    main.groq_complete = groq_fn
    main.gemini_complete = _gemini_ok
    try:
        hasil = asyncio.run(
            main.complete(
                [{"role": "user", "content": "halo"}],
                {
                    "model": model,
                    "temperature": 0.4,
                    "max_tokens": 512,
                    "ada_gambar": False,
                },
            )
        )
        return hasil, None
    except HTTPException as exc:
        return None, exc
    finally:
        main.groq_complete, main.gemini_complete = lama_groq, lama_gemini


with dengan_kunci("kunci-gemini", "kunci-groq", ""):
    hasil, err = jalankan_failover(_groq_habis)
    cek(
        "429 dari Groq -> dialihkan ke Gemini, jawaban tetap datang",
        hasil == "jawaban dari gemini" and err is None,
        str(hasil or err),
    )
    cek("Gemini benar-benar dipanggil", _dipanggil["gemini"] == 1)

    hasil, err = jalankan_failover(_groq_kunci_salah)
    cek(
        "401 (kunci salah) TIDAK dialihkan — error apa adanya",
        err is not None and err.status_code == 401,
        f"status={getattr(err, 'status_code', None)}",
    )
    cek("Gemini tidak dipanggil untuk 401", _dipanggil["gemini"] == 0)

    hasil, err = jalankan_failover(_groq_server_error)
    cek(
        "500 (masalah server) TIDAK dialihkan",
        err is not None and err.status_code == 500,
        f"status={getattr(err, 'status_code', None)}",
    )

# ---------------------------------------------------------------------
print("\n=== 7. STREAMING: TIDAK PINDAH SETELAH TEKS TERKIRIM ===")
# ---------------------------------------------------------------------


async def _groq_stream_putus(messages, opsi):
    """Kirim satu potongan, lalu 'kuota habis' di tengah jalan."""
    yield "Halo"
    raise HTTPException(status_code=429, detail="kuota habis")


async def _gemini_stream_ok(messages, opsi):
    yield "SEHARUSNYA-TIDAK-DIPAKAI"


async def jalankan_stream(groq_fn):
    _dipanggil["gemini"] = 0
    lama_groq, lama_gemini = main.groq_stream, main.gemini_stream
    main.groq_stream = groq_fn
    main.gemini_stream = _gemini_stream_ok
    potongan = []
    error = None
    try:
        async for d in main.stream(
            [{"role": "user", "content": "halo"}],
            {"model": "openai/gpt-oss-120b", "temperature": 0.4, "max_tokens": 512},
        ):
            potongan.append(d)
    except HTTPException as exc:
        error = exc
    finally:
        main.groq_stream, main.gemini_stream = lama_groq, lama_gemini
    return potongan, error


with dengan_kunci("kunci-gemini", "kunci-groq", ""):
    potongan, err = asyncio.run(jalankan_stream(_groq_stream_putus))
    cek(
        "Teks yang sudah terkirim TIDAK diulang dari Gemini",
        potongan == ["Halo"],
        str(potongan),
    )
    cek("Error diteruskan setelah teks terkirim", err is not None)

# ---------------------------------------------------------------------
print("\n=== 8. PESAN ERROR TIDAK MEMBOCORKAN NAMA PENYEDIA ===")
# ---------------------------------------------------------------------
pesan = main.pesan_jatah_habis({"boleh": False, "sisa": 0, "batas": 40, "reset_pada": 0})
for kata in ("gemini", "groq", "openrouter"):
    cek(
        f"Pesan jatah tidak menyebut '{kata}'",
        kata not in pesan.lower(),
        pesan[:60].replace("\n", " "),
    )

# ---------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"HASIL: {LULUS}/{LULUS + GAGAL} lulus")
print("=" * 62)
sys.exit(0 if GAGAL == 0 else 1)
