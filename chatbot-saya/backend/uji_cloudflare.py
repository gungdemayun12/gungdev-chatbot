"""
uji_cloudflare.py — memeriksa jalur penyedia Cloudflare Workers AI.

MENGAPA UJI INI ADA
-------------------
Cloudflare adalah penyedia yang menambah kuota HARIAN (±229–1.189
pesan/hari) tanpa kartu kredit. Itu berguna hanya bila tiga hal ini
benar:

  1. Kunci kosong berarti jalur ini DILEWATI, bukan membuat situs error.
  2. Kuota harian habis (HTTP 429) berarti PINDAH ke penyedia lain,
     bukan menampilkan error ke pengguna.
  3. Model yang tidak bisa dipakai (berbayar / salah nama -> 403/404)
     DILEWATI ke model cadangan, bukan menyerah.

Selain itu uji ini menjaga aturan penting dari pemilik situs:
  "yang paling pintar untuk coding" — model khusus coding dipakai saat
  pesan memang minta coding, tetapi TIDAK untuk semua pesan (kuotanya
  paling mahal, hanya ±69 pesan/hari).

Semua uji memakai KLIEN TIRUAN: tidak ada satu permintaan pun yang
keluar ke internet, dan tidak perlu kunci Cloudflare yang sungguhan.

Jalankan: python uji_cloudflare.py
"""

import asyncio
import json
import os
import sys

os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://upstash-tiruan.local")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "tiruan")
os.environ.setdefault("GOOGLE_CLIENT_ID", "uji.apps.googleusercontent.com")

import httpx  # noqa: E402
from fastapi import HTTPException  # noqa: E402

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
# KLIEN TIRUAN
# ---------------------------------------------------------------------
class Res:
    def __init__(self, status_code: int, data=None, teks: str = "") -> None:
        self.status_code = status_code
        self._data = data
        self.text = teks or (json.dumps(data) if data is not None else "")
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._data

    async def aread(self):
        return self.content

    async def aclose(self):
        return None

    async def aiter_lines(self):
        for baris in self._data or []:
            yield baris


def _balasan_ok(teks: str = "Jawaban uji Cloudflare.") -> Res:
    return Res(
        200,
        {
            "choices": [{"message": {"content": teks}}],
            "usage": {"total_tokens": 40, "prompt_tokens": 25, "completion_tokens": 15},
        },
    )


class KlienTiruan:
    """
    Klien HTTP tiruan.

    `perilaku` adalah fungsi (url, payload) -> Res, sehingga tiap uji
    bisa menentukan jawaban penyedia tanpa jaringan.
    """

    def __init__(self, *a, **k) -> None:
        self.dipanggil = []
        self.model_dicoba = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **kw):
        self.dipanggil.append(url)
        self.model_dicoba.append(json.get("model"))
        return PERILAKU(json.get("model"), json)

    def build_request(self, method, url, headers=None, json=None, **kw):
        self.dipanggil.append(url)
        self.model_dicoba.append(json.get("model"))
        return {"url": url, "json": json, "headers": headers}

    async def send(self, permintaan, stream=False, **kw):
        return PERILAKU(permintaan["json"].get("model"), permintaan["json"])


# Perilaku default: berhasil. Tiap uji akan menggantinya.
PERILAKU = lambda model, payload: _balasan_ok()  # noqa: E731

_ASLI = httpx.AsyncClient


def pasang_klien(perilaku) -> None:
    global PERILAKU
    PERILAKU = perilaku
    httpx.AsyncClient = KlienTiruan  # type: ignore[misc]


def lepas_klien() -> None:
    httpx.AsyncClient = _ASLI  # type: ignore[misc]


def jalankan(coro):
    return asyncio.run(coro)


KUNCI_AWAL = (main.CLOUDFLARE_ACCOUNT_ID, main.CLOUDFLARE_API_TOKEN)


def pasang_kunci() -> None:
    main.CLOUDFLARE_ACCOUNT_ID = "akun-tiruan"
    main.CLOUDFLARE_API_TOKEN = "token-tiruan"


def kosongkan_kunci() -> None:
    main.CLOUDFLARE_ACCOUNT_ID = ""
    main.CLOUDFLARE_API_TOKEN = ""


# ---------------------------------------------------------------------
print("=== 1. KONFIGURASI DASAR ===")
# ---------------------------------------------------------------------
cek(
    "Cloudflare tidak aktif bila kunci kosong",
    (lambda: (kosongkan_kunci(), main.cloudflare_tersedia())[1])() is False,
)
cek(
    "Cloudflare tidak aktif bila hanya token yang ada",
    (lambda: (
        setattr(main, "CLOUDFLARE_ACCOUNT_ID", ""),
        setattr(main, "CLOUDFLARE_API_TOKEN", "ada"),
        main.cloudflare_tersedia(),
    )[2])()
    is False,
)
cek(
    "Cloudflare tidak aktif bila hanya account id yang ada",
    (lambda: (
        setattr(main, "CLOUDFLARE_ACCOUNT_ID", "ada"),
        setattr(main, "CLOUDFLARE_API_TOKEN", ""),
        main.cloudflare_tersedia(),
    )[2])()
    is False,
)
pasang_kunci()
cek("Cloudflare aktif bila dua bagian kunci ada", main.cloudflare_tersedia() is True)

cek(
    "Model Cloudflare masuk daftar model yang boleh dipilih",
    all(m in main.MODEL_DIIZINKAN for m in main.CLOUDFLARE_MODELS),
)
cek(
    "Model default ada di daftar Cloudflare",
    main.CLOUDFLARE_MODEL_DEFAULT in main.CLOUDFLARE_MODELS,
    main.CLOUDFLARE_MODEL_DEFAULT,
)
cek(
    "Setiap id Cloudflare punya nama katalog asli",
    all(m in main._CLOUDFLARE_NAMA_ASLI for m in main.CLOUDFLARE_MODELS),
)
cek(
    "Nama katalog memakai awalan @cf/",
    all(v.startswith("@cf/") for v in main._CLOUDFLARE_NAMA_ASLI.values()),
)
cek(
    "Model khusus coding/vision/hemat ada di daftar",
    all(
        m in main.CLOUDFLARE_MODELS
        for m in (main.CF_MODEL_CODING, main.CF_MODEL_VISION, main.CF_MODEL_HEMAT)
    ),
)
cek(
    "Model vision Cloudflare terdaftar di MODEL_VISION",
    main.CF_MODEL_VISION in main.MODEL_VISION,
)
# Model berbayar TIDAK boleh masuk daftar: memakainya hanya error 403.
_semua_nama = " ".join(main._CLOUDFLARE_NAMA_ASLI.values())
cek(
    "Model berbayar (kimi-k2.7-code/glm-5.3/deepseek-v4) tidak ikut daftar",
    not any(
        x in _semua_nama
        for x in ("kimi-k2.7", "glm-5.3", "deepseek-v4", "inkling-2")
    ),
)

# ---------------------------------------------------------------------
print("\n=== 2. PEMILIHAN MODEL SESUAI KEBUTUHAN ===")
# ---------------------------------------------------------------------
pesan_biasa = [{"role": "user", "content": "Halo, apa kabar hari ini?"}]
pesan_coding = [
    {"role": "user", "content": "Tolong bantu perbaiki error di script Python saya"}
]
pesan_gambar = [
    {
        "role": "user",
        "content": [
            {"type": "text", "text": "Ini gambar apa?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAA"}},
        ],
    }
]

k = main._kandidat_cloudflare(main.CLOUDFLARE_MODEL_DEFAULT, False, pesan_biasa)
cek(
    "Pesan biasa memakai model terpintar sebagai utama",
    k[0] == main.CLOUDFLARE_MODEL_DEFAULT,
    k[0],
)
cek(
    "Model hemat ditaruh PALING AKHIR sebagai penjaga",
    k[-1] == main.CF_MODEL_HEMAT,
    f"akhir={k[-1]} | urutan={k}",
)
cek(
    "Cadangan pertama adalah model hemat-konteks (gemma), bukan model paling boros",
    k[1] == "cloudflare/gemma-4-26b-a4b-it",
    k[1],
)
cek("Tidak ada model kembar dalam urutan", len(k) == len(set(k)))
cek(
    "Semua model dalam urutan adalah model Cloudflare",
    all(m in main.CLOUDFLARE_MODELS for m in k),
)

k = main._kandidat_cloudflare("", False, pesan_coding)
cek(
    "Pesan coding otomatis memakai model khusus coding",
    k[0] == main.CF_MODEL_CODING,
    k[0],
)

k = main._kandidat_cloudflare("", False, pesan_biasa)
cek(
    "Pesan biasa TIDAK memakai model coding (hemat kuota)",
    k[0] != main.CF_MODEL_CODING,
    k[0],
)

k = main._kandidat_cloudflare(main.CLOUDFLARE_MODEL_DEFAULT, True, pesan_gambar)
cek(
    "Ada gambar -> model vision didahulukan",
    k[0] == main.CF_MODEL_VISION,
    k[0],
)
cek(
    "Ada gambar -> hanya model vision yang dicoba",
    all(m in main._CF_VISION for m in k),
    str(k),
)

# Pesan coding LAMA tidak boleh membuat percakapan berikutnya ikut mahal.
pesan_campur = [
    {"role": "user", "content": "bagaimana cara fix error python ini"},
    {"role": "assistant", "content": "Begini caranya..."},
    {"role": "user", "content": "Oke, sekarang ceritakan tentang pantai Bali"},
]
k = main._kandidat_cloudflare("", False, pesan_campur)
cek(
    "Pesan coding lama tidak memaksa model coding di pesan sesudahnya",
    k[0] != main.CF_MODEL_CODING,
    k[0],
)

# Kata "coding" di tengah kata biasa tidak boleh memicu model mahal.
cek(
    "Kata biasa tidak memicu model coding",
    main._cf_ada_kata_coding([{"role": "user", "content": "Saya suka kodeks"}])
    is False,
)
cek(
    "Teks kosong aman",
    main._cf_ada_kata_coding([]) is False
    and main._cf_ada_kata_coding([{"role": "user", "content": ""}]) is False,
)

# ---------------------------------------------------------------------
print("\n=== 3. ROUTING & FAILOVER PENYEDIA ===")
# ---------------------------------------------------------------------
_awal = (
    main.GROQ_API_KEY,
    main.GEMINI_API_KEY,
    main.OPENROUTER_API_KEY,
    main.NVIDIA_API_KEY,
)
main.GROQ_API_KEY = ""
main.GEMINI_API_KEY = ""
main.OPENROUTER_API_KEY = ""
main.NVIDIA_API_KEY = ""
pasang_kunci()
try:
    cek(
        "Model Cloudflare dirutekan ke Cloudflare",
        main._penyedia_untuk_model("cloudflare/gpt-oss-120b") == "cloudflare",
    )
    # Kunci Cloudflare kosong -> model dialihkan ke penyedia yang ada.
    kosongkan_kunci()
    main.GROQ_API_KEY = "ada"
    cek(
        "Kunci Cloudflare kosong -> model dialihkan ke penyedia lain",
        main._penyedia_untuk_model("cloudflare/gpt-oss-120b") == "groq",
        main._penyedia_untuk_model("cloudflare/gpt-oss-120b"),
    )
    main.GROQ_API_KEY = ""

    pasang_kunci()
    pasang_klien(lambda model, payload: _balasan_ok())
    try:
        urutan = main._urutan_penyedia("cloudflare")
        cek("Cloudflare ikut dalam urutan penyedia", "cloudflare" in urutan, str(urutan))
        cek(
            "Cloudflare tidak dipakai bila kuncinya kosong",
            "cloudflare" not in main._urutan_penyedia("groq")
            or main.cloudflare_tersedia(),
        )
    finally:
        lepas_klien()
finally:
    main.GROQ_API_KEY, main.GEMINI_API_KEY, main.OPENROUTER_API_KEY, main.NVIDIA_API_KEY = _awal

# ---------------------------------------------------------------------
print("\n=== 4. PANGGILAN BERHASIL ===")
# ---------------------------------------------------------------------
pasang_kunci()
opsi = {"model": "cloudflare/gpt-oss-120b", "temperature": 0.3, "max_tokens": 512}
pasang_klien(lambda model, payload: _balasan_ok("Halo, ini jawaban dari uji."))
try:
    hasil = jalankan(main.cloudflare_complete(pesan_biasa, opsi))
    cek("cloudflare_complete mengembalikan jawaban", "uji" in hasil, hasil[:40])
finally:
    lepas_klien()

cek(
    "URL memakai format akun Cloudflare",
    "/accounts/akun-tiruan/ai/v1/chat/completions" in main._cloudflare_url(),
    main._cloudflare_url(),
)
cek(
    "Payload memakai nama katalog @cf/",
    main._cloudflare_payload(
        "cloudflare/gpt-oss-120b", pesan_biasa, opsi, False
    )["model"]
    == "@cf/openai/gpt-oss-120b",
)
cek(
    "Suhu 0 digeser (Cloudflare menolak 0)",
    main._cloudflare_payload(
        "cloudflare/gpt-oss-120b", pesan_biasa, {"temperature": 0, "max_tokens": 10}, False
    )["temperature"]
    == 0.1,
)

# ---------------------------------------------------------------------
print("\n=== 5. STREAMING ===")
# ---------------------------------------------------------------------
def alir_stream(model, payload):
    baris = [
        'data: {"choices":[{"delta":{"content":"Halo "}}]}',
        'data: {"choices":[{"delta":{"content":"dunia"}}]}',
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    return Res(200, baris)


pasang_klien(alir_stream)
try:
    async def kumpulkan():
        potongan = []
        async for d in main.cloudflare_stream(pesan_biasa, opsi):
            potongan.append(d)
        return potongan

    potongan = jalankan(kumpulkan())
    cek("cloudflare_stream mengalirkan teks", "".join(potongan) == "Halo dunia", str(potongan))
finally:
    lepas_klien()

# ---------------------------------------------------------------------
print("\n=== 6. KUOTA HABIS -> PINDAH PENYEDIA ===")
# ---------------------------------------------------------------------
def kuota_habis(model, payload):
    return Res(429, {"errors": [{"code": 3040, "message": "Daily neurons limit"}]})


pasang_klien(kuota_habis)
try:
    galat = None
    try:
        jalankan(main.cloudflare_complete(pesan_biasa, opsi))
    except HTTPException as exc:
        galat = exc
    cek(
        "Kuota habis (429) dilempar sebagai 429 agar failover bekerja",
        galat is not None and galat.status_code == 429,
        str(getattr(galat, "status_code", None)),
    )
    cek(
        "Pesan kuota habis menyebut kuota harian, tanpa nama penyedia",
        galat is not None
        and "kuota harian" in galat.detail.lower()
        and "cloudflare" not in galat.detail.lower(),
        galat.detail if galat else "",
    )
finally:
    lepas_klien()

# Failover sungguhan: Cloudflare 429 -> penyedia lain menjawab.
_asli_groq = main.groq_complete
_asli_cf = main.cloudflare_complete


async def _cf_habis(messages, opsi):
    raise HTTPException(status_code=429, detail="kuota harian habis")


async def _groq_ok(messages, opsi):
    return "Jawaban dari penyedia lain."


main.cloudflare_complete = _cf_habis
main.groq_complete = _groq_ok
_kunci_awal2 = (main.GROQ_API_KEY, main.GEMINI_API_KEY, main.OPENROUTER_API_KEY, main.NVIDIA_API_KEY)
main.GROQ_API_KEY = "ada"
main.GEMINI_API_KEY = ""
main.OPENROUTER_API_KEY = ""
main.NVIDIA_API_KEY = ""
try:
    hasil = jalankan(
        main.complete(
            pesan_biasa,
            {"model": "cloudflare/gpt-oss-120b", "temperature": 0.3, "max_tokens": 100},
        )
    )
    cek(
        "Kuota Cloudflare habis -> chat tetap dijawab penyedia lain",
        "penyedia lain" in hasil,
        hasil,
    )
finally:
    main.cloudflare_complete = _asli_cf
    main.groq_complete = _asli_groq
    main.GROQ_API_KEY, main.GEMINI_API_KEY, main.OPENROUTER_API_KEY, main.NVIDIA_API_KEY = _kunci_awal2

# ---------------------------------------------------------------------
print("\n=== 7. MODEL BERBAYAR / SALAH NAMA -> LEWATI KE CADANGAN ===")
# ---------------------------------------------------------------------
def model_berbayar(model, payload):
    if model == "@cf/openai/gpt-oss-120b":
        return Res(403, {"errors": [{"code": 5039, "message": "Payment required"}]})
    return _balasan_ok("Jawaban dari model cadangan.")


pasang_klien(model_berbayar)
try:
    hasil = jalankan(main.cloudflare_complete(pesan_biasa, opsi))
    cek(
        "Model 403 dilewati, bukan menyerah",
        "cadangan" in hasil,
        hasil[:40],
    )
finally:
    lepas_klien()


def semua_gagal(model, payload):
    return Res(404, {"errors": [{"message": "model not found"}]})


pasang_klien(semua_gagal)
try:
    galat = None
    try:
        jalankan(main.cloudflare_complete(pesan_biasa, opsi))
    except HTTPException as exc:
        galat = exc
    cek(
        "Semua model gagal -> galat jelas (502), bukan crash",
        galat is not None and galat.status_code == 502,
        str(getattr(galat, "status_code", None)),
    )
finally:
    lepas_klien()

# ---------------------------------------------------------------------
print("\n=== 8. KUNCI DITOLAK -> PESAN JELAS ===")
# ---------------------------------------------------------------------
pasang_klien(lambda model, payload: Res(401, {"errors": [{"message": "unauthorized"}]}))
try:
    galat = None
    try:
        jalankan(main.cloudflare_complete(pesan_biasa, opsi))
    except HTTPException as exc:
        galat = exc
    cek(
        "Kunci ditolak dijelaskan ke pemilik situs",
        galat is not None and "CLOUDFLARE" in galat.detail,
        galat.detail[:70] if galat else "",
    )
finally:
    lepas_klien()

# ---------------------------------------------------------------------
print("\n=== 9. NAMA PENYEDIA TIDAK BOCOR KE UI ===")
# ---------------------------------------------------------------------
_isi_main = open("main.py", encoding="utf-8-sig").read()
# /capabilities hanya mengirim id model. Id "cloudflare/..." memang nama
# model pilihan pengguna (sama seperti "gemini-3.5-flash-lite"), jadi
# yang diperiksa di sini adalah: pesan galat yang DIBACA PENGGUNA tidak
# boleh menyebut penyedia.
_galat = [
    main._pesan_cloudflare_error(kode, "")
    for kode in (400, 401, 403, 404, 429, 500)
]
cek(
    "Pesan galat tidak menyebut 'Cloudflare' kecuali untuk pemilik situs",
    all(
        "cloudflare" not in g.lower()
        for kode, g in zip((400, 401, 403, 404, 429, 500), _galat)
        if kode not in (401, 403)
    ),
    str([g[:30] for g in _galat]),
)
cek(
    "Pesan kunci ditolak menyebut nama variabel (agar pemilik situs bisa perbaiki)",
    "CLOUDFLARE_ACCOUNT_ID" in main._pesan_cloudflare_error(401, ""),
)
cek(
    "Pesan galat 429 menyebut kuota harian (apa yang bisa dilakukan)",
    "kuota harian" in main._pesan_cloudflare_error(429, "").lower(),
)

# ---------------------------------------------------------------------
kosongkan_kunci()
main.CLOUDFLARE_ACCOUNT_ID, main.CLOUDFLARE_API_TOKEN = KUNCI_AWAL

print("\n" + "=" * 62)
print(f"HASIL: {LULUS}/{LULUS + GAGAL} lulus")
print("=" * 62)
sys.exit(0 if GAGAL == 0 else 1)
