"""
uji_routing_penyedia.py — memastikan setiap model dikirim ke penyedia
yang MEMANG punya model itu.

MENGAPA PENTING
---------------
Sebelumnya penyedia dipilih sekali saat server mulai. Akibatnya:
  - memilih model OpenRouter tetap dijawab Groq (usage OpenRouter 0),
  - kuota gratis Groq cepat habis walau pengguna memilih model lain,
  - tidak ada saling cadangan antar penyedia.

Uji ini mengunci perilaku yang benar: model OpenRouter -> OpenRouter,
model Groq -> Groq, dan tetap aman bila salah satu kunci tidak ada.

Jalankan: python uji_routing_penyedia.py
"""

import os
import sys

os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://upstash-tiruan.local")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "tiruan")
os.environ.setdefault("GOOGLE_CLIENT_ID", "uji.apps.googleusercontent.com")

import main  # noqa: E402

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


def dengan_kunci(openrouter: str, groq: str):
    """Memasang kunci sementara lalu mengembalikan pemulihnya."""
    lama_or, lama_groq = main.OPENROUTER_API_KEY, main.GROQ_API_KEY
    main.OPENROUTER_API_KEY = openrouter
    main.GROQ_API_KEY = groq

    def pulihkan():
        main.OPENROUTER_API_KEY = lama_or
        main.GROQ_API_KEY = lama_groq

    return pulihkan


print("=== 1. KEDUA KUNCI TERSEDIA (kondisi ideal) ===")
pulih = dengan_kunci("sk-or-v1-" + "x" * 50, "gsk_" + "y" * 50)
try:
    for m in main.OPENROUTER_MODELS:
        cek(
            f"model OpenRouter -> openrouter: {m}",
            main._penyedia_untuk_model(m) == "openrouter",
            main._penyedia_untuk_model(m),
        )
    for m in main.MODEL_GROQ_DIIZINKAN:
        cek(
            f"model Groq -> groq: {m}",
            main._penyedia_untuk_model(m) == "groq",
            main._penyedia_untuk_model(m),
        )
finally:
    pulih()

print("\n=== 2. KUNCI OPENROUTER KOSONG (kondisi produksi sekarang) ===")
pulih = dengan_kunci("", "gsk_" + "y" * 50)
try:
    # Model OpenRouter tidak boleh membuat chat mati: dialihkan ke Groq.
    tujuan = main._penyedia_untuk_model("deepseek/deepseek-v4.1-flash")
    cek("model OpenRouter tanpa kunci tidak error (dialihkan)", tujuan == "groq", tujuan)
    cek(
        "model Groq tetap ke groq",
        main._penyedia_untuk_model("openai/gpt-oss-120b") == "groq",
    )
finally:
    pulih()

print("\n=== 3. KEDUA KUNCI KOSONG (lokal/ollama) ===")
pulih = dengan_kunci("", "")
lama_provider = main.PROVIDER
main.PROVIDER = "ollama"
try:
    cek(
        "tanpa kunci sama sekali -> ollama",
        main._penyedia_untuk_model("deepseek/deepseek-v4.1-flash") == "ollama",
        main._penyedia_untuk_model("deepseek/deepseek-v4.1-flash"),
    )
finally:
    main.PROVIDER = lama_provider
    pulih()

print("\n=== 4. MODEL TIDAK DIKENAL TIDAK MEMBUAT CRASH ===")
pulih = dengan_kunci("sk-or-v1-" + "x" * 50, "gsk_" + "y" * 50)
try:
    tujuan = main._penyedia_untuk_model("model/asing-tidak-dikenal")
    cek("model asing tetap punya tujuan", tujuan in ("groq", "openrouter", "ollama"), tujuan)
finally:
    pulih()

print("\n=== 5. KEDUA DAFTAR MODEL TIDAK TUMPANG TINDIH ===")
tumpang = set(main.MODEL_GROQ_DIIZINKAN) & set(main.OPENROUTER_MODELS)
cek("tidak ada model di dua penyedia sekaligus", len(tumpang) == 0, str(tumpang))

print(f"\nHASIL: {LULUS}/{LULUS + GAGAL} lulus")
sys.exit(0 if GAGAL == 0 else 1)
