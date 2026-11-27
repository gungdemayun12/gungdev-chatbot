"""
uji_diagnostik.py — memastikan /diagnostik melaporkan SEMUA penyedia
dengan jujur, dan tidak pernah membocorkan isi kunci.

MENGAPA UJI INI ADA
-------------------
Pernah terjadi: NVIDIA_API_KEY sudah dipasang di Vercel dan deploy ulang
dilakukan, tetapi GET /diagnostik tetap TIDAK menampilkan "NVIDIA_API_KEY".
Penyebabnya bukan Vercel, melainkan daftar awalan nama variabel di
/diagnostik yang hanya memuat OPENROUTER/GROQ/AI_/UPSTASH/GOOGLE.

Akibatnya berbahaya: pemilik situs mengira key belum terpasang, lalu
memeriksa hal-hal yang tidak salah, atau menempel key berulang kali.
Lebih buruk lagi, ia bisa menyimpulkan "NVIDIA tidak berfungsi" padahal
key-nya baik-baik saja.

Uji ini mengunci dua hal:
  1. Setiap penyedia punya entri di /diagnostik, terpasang atau tidak.
  2. Bila sebuah kunci penyedia terpasang, NAMANYA muncul di env_terpasang.
  3. Tidak ada nilai kunci yang ikut keluar.

Jalankan: python uji_diagnostik.py
"""

import asyncio
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
print("=== 1. SEMUA PENYEDIA DILAPORKAN ===")
# ---------------------------------------------------------------------
# env_terpasang dibaca dari os.environ, jadi uji harus mengisi os.environ
# juga — bukan hanya atribut modul. Kalau tidak, uji tidak meniru produksi.
KUNCI_TIRUAN = {
    "GROQ_API_KEY": "RAHASIA-groq-uji-111",
    "OPENROUTER_API_KEY": "RAHASIA-openrouter-uji-222",
    "GEMINI_API_KEY": "RAHASIA-gemini-uji-333",
    "NVIDIA_API_KEY": "RAHASIA-nvidia-uji-444",
}
for nama, nilai in KUNCI_TIRUAN.items():
    os.environ[nama] = nilai

main.GROQ_API_KEY = KUNCI_TIRUAN["GROQ_API_KEY"]
main.OPENROUTER_API_KEY = KUNCI_TIRUAN["OPENROUTER_API_KEY"]
main.GEMINI_API_KEY = KUNCI_TIRUAN["GEMINI_API_KEY"]
main.NVIDIA_API_KEY = KUNCI_TIRUAN["NVIDIA_API_KEY"]

hasil = asyncio.run(main.diagnostik())

penyedia = hasil.get("penyedia") or {}
for nama in ("groq", "openrouter", "gemini", "nvidia"):
    cek(
        f"/diagnostik melaporkan penyedia '{nama}'",
        nama in penyedia,
        str(penyedia.get(nama)),
    )
    cek(
        f"penyedia '{nama}' melaporkan kunci terpasang = True",
        (penyedia.get(nama) or {}).get("ada_kunci") is True,
    )

terpasang = hasil.get("env_terpasang") or []
for nama_var in (
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_API_KEY",
    "NVIDIA_API_KEY",
):
    cek(
        f"'{nama_var}' muncul di env_terpasang",
        nama_var in terpasang,
        "tidak muncul" if nama_var not in terpasang else "",
    )

# ---------------------------------------------------------------------
print("\n=== 2. TIDAK ADA NILAI KUNCI YANG BOCOR ===")
# ---------------------------------------------------------------------
teks = repr(hasil)
for bocor in (
    "RAHASIA-groq-uji-111",
    "RAHASIA-openrouter-uji-222",
    "RAHASIA-gemini-uji-333",
    "RAHASIA-nvidia-uji-444",
):
    cek(
        f"nilai '{bocor[:22]}...' TIDAK muncul di /diagnostik",
        bocor not in teks,
    )

# ---------------------------------------------------------------------
print("\n=== 3. KUNCI KOSONG DILAPORKAN JUJUR ===")
# ---------------------------------------------------------------------
main.NVIDIA_API_KEY = ""
main.GEMINI_API_KEY = ""
os.environ.pop("NVIDIA_API_KEY", None)
os.environ.pop("GEMINI_API_KEY", None)
hasil2 = asyncio.run(main.diagnostik())
penyedia2 = hasil2.get("penyedia") or {}
cek(
    "nvidia tanpa kunci -> ada_kunci False",
    (penyedia2.get("nvidia") or {}).get("ada_kunci") is False,
)
cek(
    "gemini tanpa kunci -> ada_kunci False",
    (penyedia2.get("gemini") or {}).get("ada_kunci") is False,
)
cek(
    "groq yang masih terpasang tetap True",
    (penyedia2.get("groq") or {}).get("ada_kunci") is True,
)
cek(
    "NVIDIA_API_KEY yang dikosongkan tidak muncul di env_terpasang",
    "NVIDIA_API_KEY" not in (hasil2.get("env_terpasang") or []),
    str(hasil2.get("env_terpasang")),
)

# ---------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"HASIL: {LULUS}/{LULUS + GAGAL} lulus")
print("=" * 62)
sys.exit(0 if GAGAL == 0 else 1)
