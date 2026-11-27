"""
uji_unik_model.py — memastikan seluruh daftar model konsisten dan TIDAK
ada id yang dipakai dua penyedia sekaligus.

MENGAPA UJI INI PENTING
-----------------------
NVIDIA juga punya model "openai/gpt-oss-120b", id yang SAMA PERSIS
dengan model Groq. Kalau id itu dimasukkan apa adanya:
  - router menganggap model tersebut milik NVIDIA,
  - padahal selama ini dilayani Groq,
  - sehingga pengguna yang memilih GPT-OSS 120B diam-diam pindah
    penyedia, dan kuota Groq tidak terpakai sementara kuota NVIDIA
    (yang hanya berupa trial credit) ikut terbakar.

Uji ini mengunci agar hal itu tidak terjadi lagi: setiap id harus
menunjuk tepat SATU penyedia.

Jalankan: python uji_unik_model.py
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


# ---------------------------------------------------------------------
print("=== 1. SETIAP ID HANYA MILIK SATU PENYEDIA ===")
# ---------------------------------------------------------------------
daftar = {
    "groq": main.MODEL_GROQ_DIIZINKAN,
    "openrouter": main.OPENROUTER_MODELS,
    "gemini": main.GEMINI_MODELS,
    "nvidia": main.NVIDIA_MODELS,
}

pemilik = {}
bentrok = []
for penyedia, model_list in daftar.items():
    for m in model_list:
        if m in pemilik:
            bentrok.append(f"{m} ({pemilik[m]} & {penyedia})")
        else:
            pemilik[m] = penyedia

cek(
    "Tidak ada id model yang dipakai dua penyedia",
    not bentrok,
    "; ".join(bentrok) if bentrok else f"{len(pemilik)} id unik",
)

# ---------------------------------------------------------------------
print("\n=== 2. ROUTING SESUAI PEMILIKNYA ===")
# ---------------------------------------------------------------------
kunci = (main.GROQ_API_KEY, main.GEMINI_API_KEY, main.OPENROUTER_API_KEY, main.NVIDIA_API_KEY)
main.GROQ_API_KEY = "ada"
main.GEMINI_API_KEY = "ada"
main.OPENROUTER_API_KEY = "ada"
main.NVIDIA_API_KEY = "ada"
try:
    salah = []
    for penyedia, model_list in daftar.items():
        for m in model_list:
            tujuan = main._penyedia_untuk_model(m)
            if tujuan != penyedia:
                salah.append(f"{m} -> {tujuan} (harusnya {penyedia})")
    cek(
        "Semua model dirutekan ke penyedia yang benar",
        not salah,
        "; ".join(salah[:4]) if salah else f"{len(pemilik)} model diperiksa",
    )
finally:
    (main.GROQ_API_KEY, main.GEMINI_API_KEY, main.OPENROUTER_API_KEY, main.NVIDIA_API_KEY) = kunci

# ---------------------------------------------------------------------
print("\n=== 3. SEMUA MODEL BISA DIPILIH ===")
# ---------------------------------------------------------------------
hilang = [m for m in pemilik if m not in main.MODEL_DIIZINKAN]
cek(
    "Semua model penyedia masuk MODEL_DIIZINKAN",
    not hilang,
    "; ".join(hilang[:4]) if hilang else f"{len(pemilik)} model",
)
cek(
    "MODEL_DIIZINKAN tidak punya id kembar",
    len(main.MODEL_DIIZINKAN) == len(set(main.MODEL_DIIZINKAN)),
    f"{len(set(main.MODEL_DIIZINKAN))} unik dari {len(main.MODEL_DIIZINKAN)}",
)
cek(
    "Tidak ada model 'hantu' di MODEL_DIIZINKAN",
    set(main.MODEL_DIIZINKAN) == set(pemilik),
    f"selisih: {set(main.MODEL_DIIZINKAN) ^ set(pemilik)}",
)

# ---------------------------------------------------------------------
print("\n=== 4. JUMLAH MODEL PER PENYEDIA ===")
# ---------------------------------------------------------------------
for penyedia, model_list in daftar.items():
    print(f"       {penyedia:<12} {len(model_list)} model")
cek(
    "Keempat penyedia punya model",
    all(len(v) > 0 for v in daftar.values()),
)

# ---------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"HASIL: {LULUS}/{LULUS + GAGAL} lulus")
print("=" * 62)
sys.exit(0 if GAGAL == 0 else 1)
