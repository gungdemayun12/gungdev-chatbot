"""
uji_riset_semua_model.py — memastikan SEMUA model bisa melakukan riset,
baca gambar, dan baca file dengan kemampuan yang sama.

Inti permintaan pemilik situs: "kalau user sudah minta, AI langsung
lakukan tugasnya" — pengguna TIDAK perlu berganti model.

Yang diuji:
  1. Model apa pun tetap dipakai saat riset (tidak dilempar ke model lain).
  2. Riset benar-benar menyisipkan konteks sumber ke prompt.
  3. Riset tetap jalan walau riset GAGAL (chat tidak ikut gagal).
  4. Gambar tetap dialihkan ke model vision (batasan nyata penyedia).
  5. Semua model di allowlist punya kemampuan yang sama di /capabilities.
  6. Model OpenRouter berbayar -> cadangan :free saat kredit habis (402).
  7. OpenRouter error 401/429 diberi pesan yang jelas.

Jalankan: python uji_riset_semua_model.py
(memakai backend tiruan; tidak menyentuh penyedia AI sungguhan)
"""

import asyncio
import os
import sys

# Konfigurasi tiruan SEBELUM main diimpor.
os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://upstash-tiruan.local")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "tiruan")
os.environ.setdefault("GOOGLE_CLIENT_ID", "uji.apps.googleusercontent.com")

import server_uji  # noqa: E402  (memasang tiruan httpx, redis, tokeninfo)
import main  # noqa: E402
import riset  # noqa: E402

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
# 1. Model TIDAK diganti saat riset
# ---------------------------------------------------------------------
print("=== 1. MODEL TIDAK DIGANTI SAAT RISET ===")
for model in main.MODEL_DIIZINKAN:
    dipakai, catatan = main.model_untuk_permintaan(model, ada_gambar=False, penelitian=True)
    cek(
        f"riset memakai model pilihan apa adanya: {model}",
        dipakai == model and catatan is None,
        f"dipakai={dipakai}",
    )


# ---------------------------------------------------------------------
# 2. Gambar TETAP dialihkan ke model vision (batasan penyedia)
# ---------------------------------------------------------------------
print("\n=== 2. GAMBAR DIALIHKAN KE MODEL VISION ===")
dipakai, catatan = main.model_untuk_permintaan(
    "deepseek/deepseek-v4.1-flash", ada_gambar=True, penelitian=False
)
cek(
    "model teks + gambar -> dialihkan ke model vision",
    dipakai in main.MODEL_VISION,
    f"dipakai={dipakai}",
)
cek("pengguna diberi tahu alasannya", bool(catatan), (catatan or "")[:80])

# Model yang MEMANG mendukung gambar tidak boleh dialihkan.
for m in ["google/gemini-3.1-flash-lite", "google/gemma-4-31b-it:free"]:
    if m in main.MODEL_DIIZINKAN:
        dipakai2, catatan2 = main.model_untuk_permintaan(m, ada_gambar=True)
        cek(f"model vision tidak dialihkan: {m}", dipakai2 == m and catatan2 is None, dipakai2)


# ---------------------------------------------------------------------
# 3. Semua model punya kemampuan yang sama di /capabilities
# ---------------------------------------------------------------------
print("\n=== 3. KEMAMPUAN SAMA UNTUK SEMUA MODEL ===")
caps = asyncio.run(main.capabilities())
cek("fitur riset aktif", caps["fitur"]["riset"] is True)
cek("fitur gambar aktif", caps["fitur"]["gambar"] is True)
cek("fitur file aktif", caps["fitur"]["file"] is True)
jumlah = len(caps["models"])
cek("semua model terdaftar", jumlah == len(main.MODEL_DIIZINKAN), f"{jumlah} model")

# Riset dianggap kemampuan SERVER, jadi tidak ada satu pun model yang
# ditandai "tidak bisa riset".
semua_browser = all(m.get("browser") for m in caps["models"])
cek(
    "SEMUA model bisa riset (riset dikerjakan server)",
    semua_browser,
    f"{len(caps['models'])} model",
)


# ---------------------------------------------------------------------
# 4. Riset menyisipkan konteks ke prompt
# ---------------------------------------------------------------------
print("\n=== 4. RISET MENYISIPKAN KONTEKS SUMBER ===")


class PermintaanUji:
    """Meniru ChatRequest minimal untuk siapkan_permintaan."""

    message = "Siapa presiden Indonesia sekarang?"
    history = []
    system_prompt = None
    temperature = None
    max_tokens = None
    model = "deepseek/deepseek-v4.1-flash"
    images = []
    files = []
    file_base64 = []
    research = True


permintaan = PermintaanUji()
messages, opsi = asyncio.run(main.siapkan_permintaan(permintaan))

system_isi = "\n".join(m.get("content", "") for m in messages if m.get("role") == "system")
cek(
    "prompt memuat hasil riset",
    "Sumber 1" in system_isi or "wikipedia" in system_isi.lower(),
    system_isi[:100].replace("\n", " "),
)
cek(
    "prompt memuat aturan menyebut sumber",
    "[1]" in system_isi,
    "",
)
cek("model tetap model pilihan saat riset", opsi["model"] == "deepseek/deepseek-v4.1-flash", opsi["model"])
cek("opsi riset aktif", opsi["penelitian"] is True)


# ---------------------------------------------------------------------
# 5. Riset gagal -> chat tetap jalan
# ---------------------------------------------------------------------
print("\n=== 5. RISET GAGAL TIDAK MENGGAGALKAN CHAT ===")


async def _riset_meledak(*a, **k):
    raise RuntimeError("jaringan mati (uji)")


asli = riset.cari_dan_baca
riset.cari_dan_baca = _riset_meledak
try:
    messages2, opsi2 = asyncio.run(main.siapkan_permintaan(permintaan))
    cek("chat tetap siap walau riset gagal", len(messages2) > 0 and opsi2["penelitian"] is True)
finally:
    riset.cari_dan_baca = asli


# ---------------------------------------------------------------------
# 6. OpenRouter: cadangan :free saat kredit habis (402)
# ---------------------------------------------------------------------
print("\n=== 6. OPENROUTER CADANGAN MODEL GRATIS ===")

kandidat = main._kandidat_openrouter("deepseek/deepseek-v4.1-flash", ada_gambar=False)
cek("model utama dicoba lebih dulu", kandidat[0] == "deepseek/deepseek-v4.1-flash", str(kandidat))
cek("ada cadangan model :free", any(":free" in m for m in kandidat[1:]), str(kandidat[1:]))

kandidat_gambar = main._kandidat_openrouter("deepseek/deepseek-v4.1-flash", ada_gambar=True)
cek(
    "cadangan gambar hanya model vision",
    all(m in main.MODEL_VISION for m in kandidat_gambar[1:]) if len(kandidat_gambar) > 1 else True,
    str(kandidat_gambar),
)

pesan402 = main._pesan_openrouter_error(402, "insufficient credits", "x")
cek("pesan 402 jelas & ramah", pesan402.status_code == 503 and "kredit" in pesan402.detail.lower(), pesan402.detail)
pesan401 = main._pesan_openrouter_error(401, "invalid key", "x")
cek("pesan 401 tidak membocorkan detail", "kunci" in pesan401.detail.lower(), pesan401.detail)
pesan429 = main._pesan_openrouter_error(429, "rate limit", "x")
cek("pesan 429 meminta tunggu", pesan429.status_code == 429, pesan429.detail)


# ---------------------------------------------------------------------
# 7. Semua model yang terdaftar punya rincian kemampuan
# ---------------------------------------------------------------------
print("\n=== 7. RINCIAN KEMAMPUAN PER MODEL ===")
for m in caps["models"]:
    id_model = m["id"]
    cek(
        f"vision terdaftar benar: {id_model}",
        m["vision"] == (id_model in main.MODEL_VISION),
        f"vision={m['vision']}",
    )
    cek(f"model bisa riset: {id_model}", m["browser"] is True, "")

print(f"\nHASIL: {LULUS}/{LULUS + GAGAL} lulus")
sys.exit(0 if GAGAL == 0 else 1)
