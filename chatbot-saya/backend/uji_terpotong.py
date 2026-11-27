"""
uji_terpotong.py — memastikan jawaban yang berhenti di tengah DIKENALI,
dan jatah 52 tetap aman terhadap kapasitas harian.

MENGAPA PENTING
---------------
Dulu, bila model kehabisan token, server tetap mengirim `done: true`
seolah jawaban sudah lengkap. Pengguna mengira AI-nya berhenti, lalu
mengetik "lanjut" — dan itu MEMAKAN SATU JATAH PESAN LAGI padahal
jawabannya belum selesai. Jadi batas token yang terlalu kecil bukan
penghematan, tapi pemborosan jatah.

Uji ini mengunci:

  1. finish_reason "length" dikenali sebagai terpotong.
  2. finish_reason normal ("stop") TIDAK dianggap terpotong.
  3. Penanda terpotong bersifat PER-PERMINTAAN (tidak bocor antar
     permintaan yang berjalan bersamaan).
  4. Streaming sungguhan mengirim sinyal `terpotong` saat model
     kehabisan token.
  5. Jawaban yang selesai normal TIDAK mengirim sinyal `terpotong`.
  6. Batas token bawaan cukup besar (>= 4096).
  7. Jatah 52 masih di bawah kapasitas harian.

Jalankan: python uji_terpotong.py
"""

import asyncio
import contextvars
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
print("=== 1. PENGENALAN finish_reason ===")
# ---------------------------------------------------------------------
cek(
    "'length' dikenali terpotong",
    main._terpotong_dari_finish("length") is True,
)
cek(
    "'max_tokens' dikenali terpotong",
    main._terpotong_dari_finish("max_tokens") is True,
)
cek(
    "'stop' TIDAK dianggap terpotong",
    main._terpotong_dari_finish("stop") is False,
)
cek(
    "None/kosong TIDAK dianggap terpotong",
    main._terpotong_dari_finish(None) is False
    and main._terpotong_dari_finish("") is False,
)
cek(
    "huruf besar/kecil tidak berpengaruh",
    main._terpotong_dari_finish("LENGTH") is True,
)

# ---------------------------------------------------------------------
print("\n=== 2. PENANDA TIDAK BOCOR ANTAR PERMINTAAN ===")
# ---------------------------------------------------------------------
main._mulai_pantau_terpotong()
cek("Penanda baru diawali 'tidak terpotong'", main._apakah_terpotong() is False)

# Simulasi dua permintaan berjalan bersamaan dengan contextvars.copy_context.
ctx_a = contextvars.copy_context()
ctx_b = contextvars.copy_context()


def jalankan_terpotong():
    main._mulai_pantau_terpotong()
    main._tandai_terpotong()
    return main._apakah_terpotong()


def jalankan_normal():
    main._mulai_pantau_terpotong()
    return main._apakah_terpotong()


hasil_a = ctx_a.run(jalankan_terpotong)
hasil_b = ctx_b.run(jalankan_normal)
cek("Permintaan A terpotong", hasil_a is True)
cek("Permintaan B TIDAK ikut terpotong (tidak bocor)", hasil_b is False)

# ---------------------------------------------------------------------
print("\n=== 3. BATAS TOKEN CUKUP PANJANG ===")
# ---------------------------------------------------------------------
cek(
    "DEFAULT_MAX_TOKENS >= 4096 (jawaban panjang tidak kepotong)",
    main.DEFAULT_MAX_TOKENS >= 4096,
    str(main.DEFAULT_MAX_TOKENS),
)
cek(
    "Batas riset >= 4096",
    main.MAX_TOKENS_RISET >= 4096,
    str(main.MAX_TOKENS_RISET),
)
cek(
    "Batas bawaan tetap di bawah batas request (8192)",
    main.DEFAULT_MAX_TOKENS <= 8192,
)

# ---------------------------------------------------------------------
print("\n=== 4. STREAMING MENGIRIM SINYAL terpotong SAAT KEPOTONG ===")
# ---------------------------------------------------------------------


async def _stream_kepotong(messages, opsi):
    """Tiruan penyedia: mengirim teks lalu berhenti karena kehabisan token."""
    yield "Jawaban yang"
    yield " belum selesai"
    main._tandai_terpotong()


async def _stream_normal(messages, opsi):
    yield "Jawaban lengkap."


def jalankan_event_stream(stream_fn, stream_awal=None):
    """Menjalankan event_stream() milik /chat/stream dengan stream tiruan."""
    lama_stream = main.stream
    lama_catat = usage.catat_request
    main.stream = stream_fn

    async def catat_tiruan(*a, **k):
        return True

    usage.catat_request = catat_tiruan

    async def jatah_tiruan(sub):
        return {"boleh": True, "sisa": 99, "batas": 48, "sub": "uji"}

    lama_jatah = usage.periksa_jatah
    lama_daftar = usage.daftarkan_akun
    usage.periksa_jatah = jatah_tiruan

    async def daftar_tiruan(sub):
        return {"diterima": True}

    usage.daftarkan_akun = daftar_tiruan
    try:
        # body_iterator adalah ASYNC generator -> harus di-iterate async.
        async def kumpulkan():
            hasil = []
            async for potong in stream_awal():
                hasil.append(potong)
            return "".join(hasil)

        return asyncio.run(kumpulkan())
    finally:
        main.stream = lama_stream
        usage.catat_request = lama_catat
        usage.periksa_jatah = lama_jatah
        usage.daftarkan_akun = lama_daftar


# Susun permintaan tiruan minimal.
from main import ChatRequest  # noqa: E402

req = ChatRequest(message="Halo")


async def siapkan_tiruan(request):
    return (
        [{"role": "user", "content": "Halo"}],
        {
            "model": "gemini-3.5-flash-lite",
            "temperature": 0.4,
            "max_tokens": 4096,
            "penyesuaian": None,
        },
    )


lama_siapkan = main.siapkan_permintaan
lama_identitas = main.identitas_pemanggil
main.siapkan_permintaan = siapkan_tiruan


async def identitas_tiruan(auth):
    return {"sub": "uji-terpotong"}


main.identitas_pemanggil = identitas_tiruan

try:
    # Kasus A: model kehabisan token.
    resp = asyncio.run(main.chat_stream(req, authorization=None))
    keluaran = jalankan_event_stream(
        _stream_kepotong, stream_awal=lambda: resp.body_iterator
    )
    cek(
        "Saat kepotong, klien menerima sinyal 'terpotong'",
        '"terpotong": true' in keluaran,
        keluaran[:150].replace("\n", " "),
    )
    cek("Saat kepotong, 'done' tetap dikirim", '"done": true' in keluaran)

    # Kasus B: jawaban selesai normal.
    resp2 = asyncio.run(main.chat_stream(req, authorization=None))
    keluaran2 = jalankan_event_stream(
        _stream_normal, stream_awal=lambda: resp2.body_iterator
    )
    cek(
        "Jawaban normal TIDAK mengirim 'terpotong'",
        '"terpotong"' not in keluaran2,
        keluaran2[:150].replace("\n", " "),
    )
    cek("Jawaban normal tetap mengirim 'done'", '"done": true' in keluaran2)
finally:
    main.siapkan_permintaan = lama_siapkan
    main.identitas_pemanggil = lama_identitas

# ---------------------------------------------------------------------
print("\n=== 4b. SAMBUNG OTOMATIS (TANPA MEMAKAN JATAH LAGI) ===")
# ---------------------------------------------------------------------
# Inti keluhan pengguna: jawaban berhenti di tengah, lalu harus mengetik
# "lanjut" — dan itu memakan satu jatah pesan lagi. Server sekarang
# menyambungnya sendiri dalam satu permintaan yang sama.


def sambung_otomatis():
    """Menjalankan /chat/stream dengan model yang terpotong di putaran 1."""
    lama_siapkan2 = main.siapkan_permintaan
    lama_identitas2 = main.identitas_pemanggil
    lama_stream2 = main.stream
    lama_catat2 = usage.catat_request
    lama_jatah2 = usage.periksa_jatah
    lama_daftar2 = usage.daftarkan_akun

    jumlah_catat = {"n": 0}
    pesan_terkirim = []

    async def catat_tiruan(*a, **k):
        jumlah_catat["n"] += 1
        return True

    async def jatah_tiruan(sub):
        return {"boleh": True, "sisa": 99, "batas": 48, "sub": "uji"}

    async def daftar_tiruan(sub):
        return {"diterima": True}

    async def siapkan2(request):
        return (
            [{"role": "user", "content": "Jelaskan panjang"}],
            {
                "model": "gemini-3.5-flash-lite",
                "temperature": 0.4,
                "max_tokens": 4096,
                "penyesuaian": None,
            },
        )

    async def identitas2(auth):
        return {"sub": "uji-sambung"}

    async def stream_bersambung(pesan, opsi):
        """Putaran 1 terpotong; putaran 2 selesai."""
        pesan_terkirim.append(pesan)
        if len(pesan_terkirim) == 1:
            yield "Bagian pertama jawaban"
            main._tandai_terpotong()
        else:
            yield ", bagian kedua yang merampungkan."

    main.siapkan_permintaan = siapkan2
    main.identitas_pemanggil = identitas2
    main.stream = stream_bersambung
    usage.catat_request = catat_tiruan
    usage.periksa_jatah = jatah_tiruan
    usage.daftarkan_akun = daftar_tiruan

    try:
        r = asyncio.run(main.chat_stream(req, authorization=None))

        async def kumpulkan():
            potongan = []
            async for p in r.body_iterator:
                potongan.append(p)
            return "".join(potongan)

        keluaran = asyncio.run(kumpulkan())
    finally:
        main.siapkan_permintaan = lama_siapkan2
        main.identitas_pemanggil = lama_identitas2
        main.stream = lama_stream2
        usage.catat_request = lama_catat2
        usage.periksa_jatah = lama_jatah2
        usage.daftarkan_akun = lama_daftar2

    return keluaran, jumlah_catat["n"], pesan_terkirim


keluaran_s, jumlah_catat_s, pesan_s = sambung_otomatis()

cek(
    "Server memanggil penyedia DUA kali (putaran awal + sambungan)",
    len(pesan_s) == 2,
    f"{len(pesan_s)} panggilan",
)
cek(
    "Kedua bagian jawaban tergabung dalam satu aliran",
    "Bagian pertama jawaban" in keluaran_s
    and "bagian kedua yang merampungkan." in keluaran_s,
    keluaran_s[:160].replace("\n", " "),
)
cek(
    "Pengguna TIDAK menerima sinyal 'terpotong' (jawaban sudah utuh)",
    '"terpotong"' not in keluaran_s,
    keluaran_s[:160].replace("\n", " "),
)
cek(
    "Pemakaian dicatat SEKALI saja (satu jatah untuk satu pertanyaan)",
    jumlah_catat_s == 1,
    f"tercatat {jumlah_catat_s}x",
)
cek(
    "'done' tetap dikirim di akhir",
    '"done": true' in keluaran_s,
)

# Pesan sambungan harus memuat jawaban sebelumnya + instruksi melanjutkan.
if len(pesan_s) > 1:
    pesan_lanjut = pesan_s[1]
    peran = [m.get("role") for m in pesan_lanjut]
    cek(
        "Pesan sambungan berbentuk [.. user, assistant, user]",
        peran[-2:] == ["assistant", "user"],
        str(peran),
    )
    cek(
        "Jawaban sebelumnya ikut dikirim agar model tidak mengulang",
        "Bagian pertama jawaban" in str(pesan_lanjut[-2].get("content", "")),
    )
    cek(
        "Instruksi melarang mengulang dari awal",
        "jangan mengulang" in str(pesan_lanjut[-1].get("content", "")).lower(),
    )
else:
    cek("Pesan sambungan terbentuk", False, "sambungan tidak terjadi")

cek(
    "Batas sambungan wajar (tidak berputar tanpa akhir)",
    1 <= main.MAKS_SAMBUNG <= 5,
    str(main.MAKS_SAMBUNG),
)

# ---------------------------------------------------------------------
print("\n=== 5. JATAH 52 AMAN TERHADAP KAPASITAS ===")
# ---------------------------------------------------------------------
cek(
    "Jatah per akun = 52",
    usage.JATAH_AKUN_DASAR == 52,
    str(usage.JATAH_AKUN_DASAR),
)
cek(
    "Jatah naik 4 pesan dari 48 sebelumnya",
    usage.JATAH_AKUN_DASAR == 48 + 4,
    f"48 -> {usage.JATAH_AKUN_DASAR}",
)
cek(
    "Total 10 akun aktif x jatah masih di bawah kapasitas",
    usage.JATAH_AKUN_DASAR * 10 <= usage.PESAN_PER_HARI,
    f"{usage.JATAH_AKUN_DASAR} x 10 = {usage.JATAH_AKUN_DASAR * 10} <= {usage.PESAN_PER_HARI}",
)
cek(
    "Kapasitas token menampung minimal 10 akun penuh",
    usage.PESAN_PER_HARI // usage.JATAH_AKUN_DASAR >= 10,
    f"{usage.PESAN_PER_HARI} // {usage.JATAH_AKUN_DASAR}",
)
cek(
    "Jatah TIDAK melebihi 10% dari pesan/hari (bantalan tetap ada)",
    usage.JATAH_AKUN_DASAR <= int(usage.PESAN_PER_HARI * 0.10),
    f"{usage.JATAH_AKUN_DASAR} <= {int(usage.PESAN_PER_HARI * 0.10)}",
)
cek(
    "Jatah tidak melebihi angka teoritis 56",
    usage.JATAH_AKUN_DASAR <= 56,
    str(usage.JATAH_AKUN_DASAR),
)

# ---------------------------------------------------------------------
print("\n" + "=" * 62)
print(f"HASIL: {LULUS}/{LULUS + GAGAL} lulus")
print("=" * 62)
sys.exit(0 if GAGAL == 0 else 1)
