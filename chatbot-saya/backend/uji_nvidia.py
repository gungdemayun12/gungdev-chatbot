"""
uji_nvidia.py — memastikan penyedia keempat (NVIDIA NIM) tersambung
benar dan TIDAK diam-diam merusak perilaku lama.

Yang dikunci uji ini:

  1. Model NVIDIA terdaftar di MODEL_DIIZINKAN sehingga bisa dipilih.
  2. Router mengarahkan model NVIDIA ke penyedia "nvidia" (bukan ke Groq).
  3. Bila kunci NVIDIA tidak ada, model NVIDIA TIDAK membuat chat gagal —
     permintaan dialihkan ke penyedia yang punya kunci.
  4. NVIDIA ikut dalam rantai failover (bukan hanya tempelan).
  5. NVIDIA TIDAK dipakai sebagai dasar menaikkan jatah harian, karena
     kuotanya berupa trial credit yang bisa habis.
  6. Payload NVIDIA memakai bentuk OpenAI (max_tokens, bukan
     max_completion_tokens) dan tidak mengirim temperature 0.
  7. Streaming NVIDIA mengirim delta dan mengenali finish_reason.
  8. Model lama tetap utuh: tidak ada model yang hilang dari daftar.

Jalankan: python uji_nvidia.py
"""

import asyncio
import json
import os
import sys

os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://upstash-tiruan.local")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "tiruan")
os.environ.setdefault("GOOGLE_CLIENT_ID", "uji.apps.googleusercontent.com")

import main  # noqa: E402
import usage  # noqa: E402

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
print("=== 1. MODEL NVIDIA TERDAFTAR ===")
# ---------------------------------------------------------------------
cek(
    "NVIDIA_MODELS tidak kosong",
    len(main.NVIDIA_MODELS) > 0,
    f"{len(main.NVIDIA_MODELS)} model",
)
for m in main.NVIDIA_MODELS:
    cek(
        f"'{m}' masuk MODEL_DIIZINKAN",
        m in main.MODEL_DIIZINKAN,
    )

cek(
    "Model lama tetap ada (tidak ada yang hilang)",
    all(
        m in main.MODEL_DIIZINKAN
        for m in (
            "openai/gpt-oss-120b",
            "qwen/qwen3.8-27b",
            "gemini-4-argon",
            "gemini-3.5-flash-lite",
            "deepseek/deepseek-v4.1-flash",
        )
    ),
    f"total {len(main.MODEL_DIIZINKAN)} model",
)

cek(
    "Tidak ada id model kembar di MODEL_DIIZINKAN",
    len(main.MODEL_DIIZINKAN) == len(set(main.MODEL_DIIZINKAN)),
    f"{len(set(main.MODEL_DIIZINKAN))} unik dari {len(main.MODEL_DIIZINKAN)}",
)

# NVIDIA mematikan model lama tanpa pemberitahuan panjang: saat daftar
# pertama dibuat, kelima model yang dipakai ternyata SUDAH MATI (HTTP 410
# "end of life"). Dua uji di bawah mengunci agar kesalahan seperti itu
# tidak lolos lagi.
cek(
    "Model default NVIDIA ada di dalam daftar yang boleh dipilih",
    main.NVIDIA_MODEL_DEFAULT in main.NVIDIA_MODELS,
    main.NVIDIA_MODEL_DEFAULT,
)
cek(
    "Tidak ada model NVIDIA yang sudah dimatikan masih terdaftar",
    not (
        set(main.NVIDIA_MODELS)
        & {
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "deepseek-ai/deepseek-v4.1-flash",
            "moonshotai/kimi-2.5",
            "zai-org/glm-5",
            "meta/llama-3.3-70b-instruct",
        }
    ),
    "semua model mati sudah dibuang",
)

# ---------------------------------------------------------------------
print("\n=== 2. ROUTING MODEL -> PENYEDIA ===")
# ---------------------------------------------------------------------
kunci_asli = (main.GROQ_API_KEY, main.GEMINI_API_KEY, main.OPENROUTER_API_KEY, main.NVIDIA_API_KEY)

# Keadaan A: semua kunci tersedia.
main.GROQ_API_KEY = "ada"
main.GEMINI_API_KEY = "ada"
main.OPENROUTER_API_KEY = "ada"
main.NVIDIA_API_KEY = "ada"

for m in main.NVIDIA_MODELS:
    cek(
        f"'{m}' dirutekan ke nvidia",
        main._penyedia_untuk_model(m) == "nvidia",
        main._penyedia_untuk_model(m),
    )

cek(
    "Model Groq tetap ke groq",
    main._penyedia_untuk_model("openai/gpt-oss-120b") == "groq",
    main._penyedia_untuk_model("openai/gpt-oss-120b"),
)
cek(
    "Model Gemini tetap ke gemini",
    main._penyedia_untuk_model("gemini-4-argon") == "gemini",
    main._penyedia_untuk_model("gemini-4-argon"),
)
cek(
    "Model OpenRouter tetap ke openrouter",
    main._penyedia_untuk_model("deepseek/deepseek-v4.1-flash") == "openrouter",
    main._penyedia_untuk_model("deepseek/deepseek-v4.1-flash"),
)

# Keadaan B: kunci NVIDIA tidak ada -> harus dialihkan, bukan gagal.
main.NVIDIA_API_KEY = ""
tujuan = main._penyedia_untuk_model(main.NVIDIA_MODELS[0])
cek(
    "Tanpa kunci NVIDIA, model NVIDIA dialihkan ke penyedia lain",
    tujuan != "nvidia" and tujuan in ("groq", "gemini", "openrouter"),
    tujuan,
)

# Keadaan C: hanya NVIDIA yang punya kunci.
main.GROQ_API_KEY = ""
main.GEMINI_API_KEY = ""
main.OPENROUTER_API_KEY = ""
main.NVIDIA_API_KEY = "ada"
cek(
    "Bila hanya NVIDIA tersedia, model Groq dialihkan ke nvidia",
    main._penyedia_untuk_model("openai/gpt-oss-120b") == "nvidia",
    main._penyedia_untuk_model("openai/gpt-oss-120b"),
)

# ---------------------------------------------------------------------
print("\n=== 3. NVIDIA IKUT RANTAI FAILOVER ===")
# ---------------------------------------------------------------------
main.GROQ_API_KEY = "ada"
main.GEMINI_API_KEY = "ada"
main.OPENROUTER_API_KEY = "ada"
main.NVIDIA_API_KEY = "ada"

urutan = main._urutan_penyedia("groq")
cek(
    "nvidia ada di rantai failover",
    "nvidia" in urutan,
    str(urutan),
)
cek(
    "Penyedia utama tetap di urutan pertama",
    urutan[0] == "groq",
    str(urutan[:2]),
)
cek(
    "Tidak ada penyedia dobel di rantai",
    len(urutan) == len(set(urutan)),
    str(urutan),
)

main.NVIDIA_API_KEY = ""
cek(
    "Tanpa kunci, nvidia keluar dari rantai",
    "nvidia" not in main._urutan_penyedia("groq"),
    str(main._urutan_penyedia("groq")),
)

# ---------------------------------------------------------------------
print("\n=== 4. NVIDIA TIDAK MENAIKKAN JATAH (JUJUR SOAL KUOTA) ===")
# ---------------------------------------------------------------------
cek(
    "Trial NVIDIA tidak dihitung sebagai kapasitas harian",
    usage.KUOTA_BERSAMA.get("trial_nvidia_dihitung") == 0,
    str(usage.KUOTA_BERSAMA.get("trial_nvidia_dihitung")),
)
cek(
    "Jatah tetap 52 (NVIDIA tidak menaikkan jatah; kenaikan 48->52 dari bantalan)",
    usage.JATAH_AKUN_DASAR == 52,
    str(usage.JATAH_AKUN_DASAR),
)
cek(
    "Kapasitas token tidak ikut bertambah oleh NVIDIA",
    usage.KAPASITAS_HARIAN["token"] == 850_000,
    str(usage.KAPASITAS_HARIAN["token"]),
)

# ---------------------------------------------------------------------
print("\n=== 5. BENTUK PAYLOAD SESUAI STANDAR OPENAI ===")
# ---------------------------------------------------------------------
opsi = {"temperature": 0.4, "max_tokens": 4096}
MODEL_UJI = main.NVIDIA_MODELS[0]
payload = main._nvidia_payload(MODEL_UJI, [{"role": "user", "content": "hai"}], opsi, False)

cek("Payload memakai 'max_tokens'", "max_tokens" in payload)
cek(
    "Payload TIDAK memakai 'max_completion_tokens' (khusus Groq)",
    "max_completion_tokens" not in payload,
)
cek(
    "Payload memuat nama model ASLI katalog NVIDIA",
    payload.get("model") == MODEL_UJI,
    str(payload.get("model")),
)
cek(
    "Model tanpa pemetaan dikirim apa adanya (tidak diubah)",
    main._nvidia_nama_asli(MODEL_UJI) == MODEL_UJI,
)
cek(
    "_NVIDIA_NAMA_ASLI masih berupa dict yang bisa diisi",
    isinstance(main._NVIDIA_NAMA_ASLI, dict),
)
cek("Payload tidak streaming saat complete", payload.get("stream") is False)

# temperature 0 digeser: sebagian model NIM menolaknya.
payload0 = main._nvidia_payload(MODEL_UJI, [], {"temperature": 0, "max_tokens": 100}, False)
cek(
    "temperature 0 digeser (tidak dikirim sebagai 0)",
    payload0["temperature"] > 0,
    str(payload0["temperature"]),
)

payload_stream = main._nvidia_payload(MODEL_UJI, [], opsi, True)
cek("Payload streaming memakai stream=True", payload_stream.get("stream") is True)

# Kandidat cadangan: model tak dikenal -> jatuh ke default.
kandidat = main._kandidat_nvidia("model-yang-tidak-ada", False)
cek(
    "Model tak dikenal jatuh ke default NVIDIA",
    kandidat[0] == main.NVIDIA_MODEL_DEFAULT,
    kandidat[0],
)
cek(
    "Daftar kandidat tidak berisi model dobel",
    len(kandidat) == len(set(kandidat)),
    str(kandidat),
)

# ---------------------------------------------------------------------
print("\n=== 6. STREAMING NVIDIA MENGIRIM DELTA & MENDETEKSI TERPOTONG ===")
# ---------------------------------------------------------------------
from unittest.mock import patch  # noqa: E402

ALIRAN_SSE = (
    'data: {"choices":[{"delta":{"content":"Halo"}}]}\n'
    'data: {"choices":[{"delta":{"content":" dunia"}}]}\n'
    'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n'
    "data: [DONE]\n"
)


class _ResTiruan:
    status_code = 200
    headers = {}

    def __init__(self, teks):
        self._teks = teks

    async def aiter_lines(self):
        for baris in self._teks.splitlines():
            yield baris

    async def aread(self):
        return b""

    async def aclose(self):
        return None


class _HTTPTiruan:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def build_request(self, *a, **k):
        return object()

    async def send(self, *a, **k):
        return _ResTiruan(ALIRAN_SSE)


async def _jalankan_stream():
    with patch.object(main.httpx, "AsyncClient", lambda **k: _HTTPTiruan()):
        main._mulai_pantau_terpotong()
        potongan = []
        async for d in main.nvidia_stream(
            [{"role": "user", "content": "halo"}], opsi
        ):
            potongan.append(d)
        return "".join(potongan), main._apakah_terpotong()


teks, terpotong = asyncio.run(_jalankan_stream())
cek(
    "Streaming NVIDIA menggabungkan delta",
    teks == "Halo dunia",
    repr(teks),
)
cek(
    "finish_reason 'length' dikenali sebagai terpotong",
    terpotong is True,
)

# ---------------------------------------------------------------------
print("\n=== 7. MODEL YANG SUDAH DIMATIKAN (HTTP 410) DILEWATI ===")
# ---------------------------------------------------------------------
# NVIDIA membalas 410 "end of life" untuk model yang sudah dimatikan.
# Ini pernah terjadi pada SEMUA model yang kita daftarkan pertama kali.
# Perilaku yang benar: lewati ke model berikutnya, JANGAN tampilkan error
# kepada pengguna yang tidak melakukan kesalahan apa pun.
class _ResGone:
    status_code = 410
    headers = {}

    def __init__(self):
        self.text = '{"detail":"model has reached its end of life"}'

    async def aread(self):
        return self.text.encode()

    async def aclose(self):
        return None

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"dari cadangan"}}]}'


class _HTTPGoneLaluHidup:
    """Model pertama dibalas 410, model kedua berhasil."""

    def __init__(self):
        self.dipanggil = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def build_request(self, *a, **k):
        return object()

    async def send(self, *a, **k):
        if not self.dipanggil:
            self.dipanggil.append("mati")
            return _ResGone()
        self.dipanggil.append("hidup")
        return _ResTiruan(ALIRAN_SSE)


async def _jalankan_410():
    tiruan = _HTTPGoneLaluHidup()
    with patch.object(main.httpx, "AsyncClient", lambda **k: tiruan):
        potongan = []
        async for d in main.nvidia_stream(
            [{"role": "user", "content": "halo"}], opsi
        ):
            potongan.append(d)
    return "".join(potongan), tiruan.dipanggil


teks410, urutan_panggil = asyncio.run(_jalankan_410())
cek(
    "Model 410 dilewati, bukan menggagalkan permintaan",
    teks410 == "Halo dunia",
    repr(teks410),
)
cek(
    "Setelah 410 server benar-benar mencoba model lain",
    len(urutan_panggil) == 2,
    str(urutan_panggil),
)

cek(
    "Pesan untuk 410 tidak menyalahkan pengguna dan tanpa bocoran",
    "rahasia-internal-xyz" not in main._pesan_nvidia_error(410, "rahasia-internal-xyz")
    and "tidak dipakai lagi" in main._pesan_nvidia_error(410, "x"),
    main._pesan_nvidia_error(410, "x")[:70],
)

# ---------------------------------------------------------------------
print("\n=== 8. PESAN KESALAHAN TIDAK MEMBOCORKAN DETAIL TEKNIS ===")
# ---------------------------------------------------------------------
for kode in (401, 403, 404, 410, 429, 500):
    pesan = main._pesan_nvidia_error(kode, "rahasia-internal-xyz")
    cek(
        f"Kode {kode} memberi pesan Bahasa Indonesia tanpa bocoran",
        "nvidia" in pesan.lower() or "ai" in pesan.lower(),
        pesan[:60],
    )
    cek(
        f"Kode {kode} tidak meneruskan badan respons mentah",
        "rahasia-internal-xyz" not in pesan,
    )

# Kembalikan kunci asli.
(
    main.GROQ_API_KEY,
    main.GEMINI_API_KEY,
    main.OPENROUTER_API_KEY,
    main.NVIDIA_API_KEY,
) = kunci_asli

# ---------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"HASIL: {LULUS}/{LULUS + GAGAL} lulus")
print("=" * 62)
sys.exit(0 if GAGAL == 0 else 1)
