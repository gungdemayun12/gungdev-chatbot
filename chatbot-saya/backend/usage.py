"""
usage.py — pencatat & penyedia data pemakaian (usage) kuota AI.

KENAPA MODUL INI ADA
--------------------
Penyedia AI gratis (Groq) membatasi pemakaian per menit dan per hari.
Tanpa pencatatan, pengguna hanya tahu kuota habis KETIKA chat tiba-tiba
gagal — pengalaman yang buruk. Modul ini membuat aplikasi bisa berkata
jujur: "kuota hari ini terpakai 40 dari 1.000, reset dalam 7 jam".

CARA KERJA (dua lapis, saling melengkapi)
-----------------------------------------
1. LAPIS UTAMA — header dari Groq.
   Setiap respons Groq menyertakan x-ratelimit-remaining-requests dan
   x-ratelimit-remaining-tokens. Ini SUMBER KEBENARAN karena berasal
   langsung dari penyedia. Kita hanya meneruskannya ke frontend.

2. LAPIS CADANGAN — penghitung lokal.
   Bila backend dipanggil ke penyedia lain (Ollama lokal) atau header
   tidak tersedia, kita tetap punya hitungan sendiri agar panel tidak
   kosong.

PENYIMPANAN
-----------
Vercel Serverless bersifat stateless: memori hilang saat fungsi tidur.
Karena itu penghitung lokal disimpan ke Upstash Redis bila tersedia
(env UPSTASH_REDIS_REST_URL + UPSTASH_REDIS_REST_TOKEN). Bila tidak
tersedia, modul tetap berfungsi dengan memori proses — angkanya kurang
akurat antar-instan, tetapi tidak pernah membuat aplikasi error.

Modul ini SENGAJA tidak pernah membuat permintaan gagal. Semua operasi
penyimpanan dibungkus try/except: kegagalan mencatat tidak boleh
menggagalkan percakapan pengguna.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

try:
    # Dipakai hanya untuk memvalidasi `sub` akun sebelum dipakai di kunci
    # Redis. Diimpor dengan pengaman agar usage.py tetap bisa dipakai
    # sendiri (mis. dalam pengujian) tanpa modul lain.
    import penyimpanan
except ImportError:  # pragma: no cover
    penyimpanan = None  # type: ignore[assignment]

logger = logging.getLogger("chatbot.usage")

# ---------------------------------------------------------------------
# Batas kuota penyedia (bukan tebakan — dari halaman Rate Limits Groq).
# Nilai ini dipakai untuk MENGHITUNG PERSENTASE, bukan untuk memblokir.
# Blokir tetap dilakukan Groq sendiri (HTTP 429).
# ---------------------------------------------------------------------
BATAS_KUOTA: Dict[str, Dict[str, int]] = {
    "openai/gpt-oss-120b": {
        "rpm": 30,          # request per menit
        "rpd": 1000,        # request per hari
        "tpm": 8000,        # token per menit
        "tpd": 200000,      # token per hari
    },
    "openai/gpt-oss-20b": {
        "rpm": 30,
        "rpd": 1000,
        "tpm": 8000,
        "tpd": 200000,
    },
    "qwen/qwen3.8-27b": {
        "rpm": 30,
        "rpd": 1000,
        "tpm": 8000,
        "tpd": 200000,
    },
}

# Kuota cadangan bila model tidak dikenal (mis. model baru dari Groq).
BATAS_DEFAULT = {"rpm": 30, "rpd": 1000, "tpm": 8000, "tpd": 200000}

# ---------------------------------------------------------------------
# JATAH HARIAN PER AKUN
# ---------------------------------------------------------------------
# Kuota penyedia (1000 request/hari) dipakai BERSAMA semua pengunjung dan
# tidak bisa dibagi oleh kita — Groq yang memegangnya. Tanpa batas per
# akun, satu pengguna yang sangat aktif bisa menghabiskan kuota seluruh
# situs sehingga pengunjung lain tiba-tiba tidak bisa chat.
#
# Karena itu tiap akun mendapat jatah sendiri yang ditegakkan di server.
# Angka dipilih agar kuota gratis cukup untuk sekitar 10 akun aktif:
#     10 akun x 100 request = 1000 request/hari  (pas dengan batas Groq)
#
# PENTING — kenapa HANYA jumlah pesan yang membatasi:
# Token tetap DICATAT dan DITAMPILKAN agar pengguna tahu pemakaiannya,
# tetapi sengaja TIDAK dipakai sebagai pembatas. Panjang jawaban AI
# sangat bervariasi (jawaban singkat 100 token, jawaban panjang 3.000
# token), sehingga membatasi token akan membuat pengguna yang bertanya
# hal sederhana mendapat jatah jauh lebih banyak daripada yang bertanya
# hal rumit — padahal keduanya satu pesan. Jumlah pesan lebih adil dan
# lebih mudah dipahami.
JATAH_AKUN = {
    "rpd": int(os.getenv("JATAH_REQUEST_PER_AKUN", "100") or 100),
}

# ---------------------------------------------------------------------
# JENDELA JATAH: 24 JAM BERGULIR PER AKUN (bukan jam dinding)
# ---------------------------------------------------------------------
# Jatah TIDAK direset serentak pukul 07:00 WIB untuk semua orang. Tiap
# akun punya jendela 24 jam MILIKNYA SENDIRI yang dimulai saat pesan
# pertama akun itu — sama seperti layanan AI pada umumnya.
#
# Contoh:
#   Akun GungDe mulai chat 20:00 -> jendelanya 20:00 s/d 20:00 besok.
#   Kalau jatahnya habis 22:00, ia pulih 20:00 besok (22 jam lagi),
#   BUKAN jam 07:00 pagi.
#   Akun Indah mulai chat 09:00 -> jendelanya 09:00 s/d 09:00 besok.
#
# Akun yang jatahnya TIDAK habis tidak pernah dibatasi sama sekali;
# hitung mundur hanya ditampilkan sebagai informasi.
#
# Biayanya: Redis menyimpan satu angka "jendela mulai" per akun, dan
# kedaluwarsa otomatis 2 x durasi jendela agar tidak menumpuk.
JENDELA_JATAH_DETIK = int(os.getenv("JENDELA_JATAH_JAM", "24") or 24) * 3600

# Jatah tamu. Nilai sebenarnya ditegakkan di main.py (3 pesan/hari lewat
# penghitung per-IP); angka ini hanya untuk ditampilkan di panel.
JATAH_TAMU = {"rpd": 3}

# Toleransi token tak terduga. Bila pencatat token gagal total, server
# tetap perlu menghitung sesuatu yang wajar agar angka di panel tidak
# tiba-tiba nol. Nilai ini hanya memengaruhi pencatatan, bukan pembatas.
TOKEN_MIN_PER_REQUEST = 200

# ---------------------------------------------------------------------
# Penyimpanan ringan: Upstash Redis (REST) bila tersedia, memori bila tidak.
# ---------------------------------------------------------------------
_UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
_UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

# Cadangan memori proses (dipakai bila Upstash tidak dikonfigurasi).
_memori: Dict[str, Any] = {}

# Kunci Redis. Memakai tanggal UTC agar reset harian konsisten dengan
# cara Groq menghitung (Groq memakai jendela UTC).
_PREFIX = "gungdev:usage"


def _hari_ini() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _sub_sah(sub: Optional[str]) -> Optional[str]:
    """Validasi `sub` lewat modul penyimpanan bila tersedia."""
    if not sub:
        return None
    if penyimpanan is not None:
        return penyimpanan.sub_sah(sub)
    teks = str(sub).strip()
    return teks if teks.isalnum() or "-" in teks or "_" in teks else None


def _kunci_harian(sub: Optional[str] = None) -> str:
    """
    Kunci Redis untuk pencatatan usage.

    Tanpa `sub`  -> gungdev:usage:<tanggal>          (total seluruh situs)
    Dengan `sub` -> gungdev:usage:u:<sub>:<tanggal>  (milik satu akun)

    Dua-duanya tetap dicatat: angka global dipakai untuk menghitung sisa
    kuota penyedia (yang memang dipakai bersama), sedangkan angka per
    akun dipakai panel "pemakaian saya".
    """
    sub = _sub_sah(sub)
    if sub:
        return f"{_PREFIX}:u:{sub}:{_hari_ini()}"
    return f"{_PREFIX}:{_hari_ini()}"


async def _redis_perintah(*perintah: Any) -> Optional[Any]:
    """
    Menjalankan satu perintah Redis lewat REST Upstash.

    Mengembalikan None bila Upstash tidak dikonfigurasi atau gagal.
    Sengaja tidak melempar exception: pencatatan usage tidak boleh
    menggagalkan percakapan pengguna.
    """
    if not (_UPSTASH_URL and _UPSTASH_TOKEN):
        return None

    try:
        async with httpx.AsyncClient(timeout=5.0) as http:
            res = await http.post(
                _UPSTASH_URL,
                headers={
                    "Authorization": f"Bearer {_UPSTASH_TOKEN}",
                    "Content-Type": "application/json",
                },
                json=list(perintah),
            )
            if res.status_code >= 400:
                logger.warning("Upstash menolak perintah: %s", res.text[:160])
                return None
            data = res.json()
            return data.get("result")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Upstash tidak dapat dihubungi: %s", exc)
        return None


async def catat_request(
    tokens: int = 0,
    model: str = "",
    sub: Optional[str] = None,
) -> None:
    """
    Mencatat satu request yang berhasil dijawab.

    Selalu mencatat TOTAL SITUS (dipakai menghitung sisa kuota penyedia),
    dan — bila `sub` diberikan — juga mencatat PEMAKAIAN AKUN itu sendiri
    pada JENDELA 24 JAM yang sedang berjalan, sehingga panel Usage bisa
    berkata "akun Anda: 12 dari 100 pesan".

    Dipanggil dari dalam endpoint chat. Tidak pernah melempar exception.
    """
    kunci_global = _kunci_harian()
    sub_sah = _sub_sah(sub)
    kunci_akun = None
    if sub_sah:
        try:
            kunci_akun = (await _jendela_akun(sub_sah))["kunci"]
        except Exception:  # noqa: BLE001
            kunci_akun = None

    # --- Upstash (akurat lintas instan) ---
    if _UPSTASH_URL and _UPSTASH_TOKEN:
        try:
            await _redis_perintah("HINCRBY", kunci_global, "requests", 1)
            if tokens > 0:
                await _redis_perintah("HINCRBY", kunci_global, "tokens", int(tokens))
            # Kedaluwarsa 7 hari agar Redis tidak penuh oleh data lama.
            await _redis_perintah("EXPIRE", kunci_global, 7 * 24 * 3600)

            if kunci_akun:
                await _redis_perintah("HINCRBY", kunci_akun, "requests", 1)
                if tokens > 0:
                    await _redis_perintah("HINCRBY", kunci_akun, "tokens", int(tokens))
                # Data jendela hanya berguna selama jendelanya hidup.
                # Dua kali durasi jendela cukup, lalu terhapus sendiri.
                await _redis_perintah("EXPIRE", kunci_akun, JENDELA_JATAH_DETIK * 2)
            return
        except Exception:  # noqa: BLE001
            pass  # lanjut ke cadangan memori

    # --- Cadangan memori proses ---
    for kunci in [k for k in (kunci_global, kunci_akun) if k]:
        catatan = _memori.setdefault(kunci, {"requests": 0, "tokens": 0})
        catatan["requests"] += 1
        if tokens > 0:
            catatan["tokens"] += int(tokens)
    _memori["__terakhir__"] = {
        "waktu": datetime.now(timezone.utc).isoformat(),
        "model": model,
    }


def simpan_header_kuota(headers: Any, model: str = "") -> None:
    """
    Menyimpan nilai x-ratelimit-* dari respons penyedia.

    Ini sumber angka paling akurat: penyedia tahu persis sisa kuota
    organisasi, sedangkan hitungan lokal hanya perkiraan.

    `headers` boleh berupa httpx.Headers maupun dict biasa. Fungsi ini
    tidak pernah melempar exception.
    """
    try:
        def ambil(nama: str) -> Optional[int]:
            nilai = None
            try:
                nilai = headers.get(nama)
            except Exception:  # noqa: BLE001
                nilai = None
            if nilai is None:
                return None
            # Groq memakai format "1000" atau "1m30s" untuk reset.
            teks = str(nilai).strip()
            if not teks:
                return None
            try:
                return int(float(teks))
            except ValueError:
                return None

        rekam = {
            "remaining_requests": ambil("x-ratelimit-remaining-requests"),
            "remaining_tokens": ambil("x-ratelimit-remaining-tokens"),
            "limit_requests": ambil("x-ratelimit-limit-requests"),
            "limit_tokens": ambil("x-ratelimit-limit-tokens"),
            "waktu": datetime.now(timezone.utc).isoformat(),
            "model": model,
        }

        # Hanya simpan bila ada minimal satu angka bermakna.
        if rekam["remaining_requests"] is None and rekam["remaining_tokens"] is None:
            return

        _memori["__kuota_terakhir__"] = rekam
        _memori["__kuota_terakhir__:" + _hari_ini()] = rekam
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal menyimpan header kuota: %s", exc)


def ambil_header_kuota() -> Optional[Dict[str, Any]]:
    """Mengambil header kuota terakhir untuk hari ini (bila ada)."""
    return _memori.get("__kuota_terakhir__:" + _hari_ini()) or _memori.get(
        "__kuota_terakhir__"
    )


def model_terakhir() -> Optional[str]:
    """
    Nama model yang terakhir menjawab, dipakai untuk menentukan batas
    kuota mana yang ditampilkan di panel Usage.

    Hanya untuk perhitungan internal — nilai ini TIDAK pernah dikirim
    ke frontend (respons /usage memakai label publik).
    """
    try:
        kuota = ambil_header_kuota() or {}
        model = kuota.get("model")
        if model:
            return str(model)
        terakhir = _memori.get("__terakhir__") or {}
        model = terakhir.get("model")
        return str(model) if model else None
    except Exception:  # noqa: BLE001
        return None


async def baca_harian(sub: Optional[str] = None) -> Dict[str, int]:
    """
    Membaca total request & token.

    Tanpa `sub` -> total seluruh situs pada hari UTC ini.
    Dengan `sub` -> pemakaian akun itu pada JENDELA 24 JAM berjalannya
    (bukan lagi per tanggal kalender), sesuai cara jatah dihitung.
    """
    sub_sah = _sub_sah(sub)
    if sub_sah:
        try:
            return await _baca_jendela(sub_sah)
        except Exception:  # noqa: BLE001
            return {"requests": 0, "tokens": 0}

    kunci = _kunci_harian()

    if _UPSTASH_URL and _UPSTASH_TOKEN:
        hasil = await _redis_perintah("HMGET", kunci, "requests", "tokens")
        if isinstance(hasil, list) and len(hasil) == 2:
            return {
                "requests": int(hasil[0] or 0),
                "tokens": int(hasil[1] or 0),
            }

    catatan = _memori.get(kunci, {})
    return {
        "requests": int(catatan.get("requests", 0)),
        "tokens": int(catatan.get("tokens", 0)),
    }


# ---------------------------------------------------------------------
# Token ASLI dari penyedia
# ---------------------------------------------------------------------
# Groq mengirim angka token sebenarnya di setiap respons (prompt_tokens +
# completion_tokens). Angka itu jauh lebih akurat daripada menebak dari
# panjang teks, jadi disimpan di sini lalu dibaca oleh endpoint chat
# untuk dicatat. Nilainya per-instans (memori proses) karena hanya
# dipakai sesaat setelah respons diterima, dalam permintaan yang sama.
_token_terakhir: Dict[str, int] = {}


def simpan_token_asli(total: int, prompt: int = 0, completion: int = 0) -> None:
    """
    Menyimpan angka token sebenarnya dari respons penyedia.

    Dipanggil tepat setelah respons Groq diterima, lalu dibaca oleh
    endpoint /chat untuk mencatat ke Redis. Tidak pernah melempar
    exception.
    """
    try:
        nilai = int(total or 0)
        if nilai <= 0:
            nilai = int(prompt or 0) + int(completion or 0)
        if nilai <= 0:
            return
        _token_terakhir["total"] = nilai
        _token_terakhir["prompt"] = int(prompt or 0)
        _token_terakhir["completion"] = int(completion or 0)
        _token_terakhir["waktu"] = datetime.now(timezone.utc).timestamp()
    except Exception:  # noqa: BLE001
        return


def ambil_token_asli(umur_maks: float = 120.0) -> Optional[int]:
    """
    Mengambil angka token asli yang terakhir disimpan.

    `umur_maks` (detik) mencegah angka basi dari permintaan lain
    terpakai — pada serverless tiap permintaan punya proses sendiri,
    tetapi pada server biasa (lokal) prosesnya dipakai bersama.
    Mengembalikan None bila tidak ada atau sudah terlalu lama.
    """
    try:
        total = _token_terakhir.get("total")
        waktu = _token_terakhir.get("waktu")
        if not total or not waktu:
            return None
        if datetime.now(timezone.utc).timestamp() - float(waktu) > umur_maks:
            return None
        return int(total)
    except Exception:  # noqa: BLE001
        return None


def _detik_sampai_reset_harian() -> int:
    """Sisa detik hingga 00:00 UTC (jendela kuota PENYEDIA, bukan akun)."""
    sekarang = datetime.now(timezone.utc)
    besok = (sekarang + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(0, int((besok - sekarang).total_seconds()))


# ---------------------------------------------------------------------
# JENDELA JATAH PER AKUN (24 jam bergulir)
# ---------------------------------------------------------------------
# Kunci Redis yang menyimpan KAPAN jendela akun itu dimulai:
#     gungdev:jendela:<sub>  ->  "<epoch detik>"
#
# Jendela dimulai saat pesan pertama akun itu setelah jendela lamanya
# berakhir. Selama jendela masih berjalan, angka pemakaian terus
# bertambah di kunci harian biasa — hanya nama kuncinya memakai
# penanda jendela, bukan tanggal kalender.
#
# MENGAPA TIDAK MEMAKAI TANGGAL: tanggal membuat semua akun reset
# serentak pukul 00:00 UTC. Pengguna yang chat jam 06:50 hanya menikmati
# jatahnya 10 menit. Jendela bergulir membuat tiap akun mendapat 24 jam
# penuh sejak pemakaian pertamanya.
async def _jendela_akun(sub: str) -> Dict[str, Any]:
    """
    Membaca (atau memulai) jendela jatah milik satu akun.

    Mengembalikan:
        {
          "kunci": str,      # kunci Redis untuk pemakaian jendela ini
          "mulai": float,    # epoch detik jendela dimulai
          "akhir": float,    # epoch detik jendela berakhir (reset)
          "sisa_detik": int,
        }

    Bila penyimpanan tidak tersedia, dipakai jendela berdasarkan
    memori proses supaya perilakunya tetap masuk akal saat lokal.

    PENTING — Redis adalah SUMBER KEBENARAN, memori hanya cadangan:
    membaca memori lebih dulu membuat proses yang sudah lama hidup
    (mis. server biasa atau instance serverless yang hangat) terus
    memakai jendela lama meski Redis sudah menyimpan jendela baru.
    Akibatnya jatah tidak pernah pulih. Karena itu memori hanya dipakai
    bila Redis benar-benar tidak tersedia.
    """
    sekarang = datetime.now(timezone.utc).timestamp()
    kunci_jendela = f"{_PREFIX}:jendela:{sub}"

    mulai: float = 0.0
    redis_terbaca = False
    if _UPSTASH_URL and _UPSTASH_TOKEN:
        try:
            nilai = await _redis_perintah("GET", kunci_jendela)
            if nilai is not None:
                mulai = float(nilai)
                redis_terbaca = True
            else:
                # Redis hidup tapi kunci belum ada -> memang belum pernah
                # mulai. Jangan pakai memori yang mungkin sudah basi.
                redis_terbaca = True
        except Exception:  # noqa: BLE001
            redis_terbaca = False

    if not redis_terbaca:
        mulai = float(_memori.get(kunci_jendela, 0) or 0)
        # Angka tanggal lama (kunci berbasis tanggal) tidak relevan lagi;
        # anggap belum pernah mulai agar tidak salah hitung.
        if mulai <= 0:
            mulai = 0.0

    # Jendela baru dimulai bila belum pernah ada, atau sudah lewat.
    if mulai <= 0 or sekarang >= mulai + JENDELA_JATAH_DETIK:
        mulai_baru = sekarang
        # Jaga-jaga: kunci pemakaian memakai int(detik). Bila jendela baru
        # dimulai pada detik yang SAMA dengan jendela mana pun yang masih
        # tersimpan, angka pemakaian lama bisa ikut terbaca sehingga akun
        # yang sudah lewat jendelanya tetap ditolak. Karena itu penanda
        # jendela baru dipastikan belum pernah dipakai: cari detik terkecil
        # (mulai dari sekarang) yang kuncinya benar-benar kosong.
        #
        # Hanya berlaku bila pemakaian disimpan di Redis; pada cadangan
        # memori, kunci kosong selalu berarti 0.
        percobaan = 0
        while percobaan < 5:
            calon = f"{_PREFIX}:u:{sub}:w{int(mulai_baru)}"
            if not (_UPSTASH_URL and _UPSTASH_TOKEN):
                break
            try:
                isi = await _redis_perintah("HMGET", calon, "requests")
            except Exception:  # noqa: BLE001
                break
            # HMGET mengembalikan [None] bila kunci belum ada.
            if not isinstance(isi, list) or not isi or isi[0] in (None, ""):
                break
            # Sudah terpakai -> mundurkan penanda satu detik lalu coba lagi.
            mulai_baru = float(int(mulai_baru) + 1)
            percobaan += 1
        mulai = mulai_baru
        if _UPSTASH_URL and _UPSTASH_TOKEN:
            try:
                await _redis_perintah(
                    "SET", kunci_jendela, int(mulai), "EX", JENDELA_JATAH_DETIK * 2
                )
            except Exception:  # noqa: BLE001
                pass
        _memori[kunci_jendela] = mulai
    else:
        # Simpan salinan agar tetap jalan bila Redis mati sesaat.
        _memori[kunci_jendela] = mulai

    akhir = mulai + JENDELA_JATAH_DETIK
    return {
        "kunci": f"{_PREFIX}:u:{sub}:w{int(mulai)}",
        "mulai": mulai,
        "akhir": akhir,
        "sisa_detik": max(0, int(akhir - sekarang)),
    }


async def _baca_jendela(sub: str) -> Dict[str, int]:
    """Membaca pemakaian akun pada jendela yang sedang berjalan."""
    jendela = await _jendela_akun(sub)
    kunci = jendela["kunci"]

    if _UPSTASH_URL and _UPSTASH_TOKEN:
        hasil = await _redis_perintah("HMGET", kunci, "requests", "tokens")
        if isinstance(hasil, list) and len(hasil) == 2:
            return {
                "requests": int(hasil[0] or 0),
                "tokens": int(hasil[1] or 0),
            }

    catatan = _memori.get(kunci, {})
    return {
        "requests": int(catatan.get("requests", 0)),
        "tokens": int(catatan.get("tokens", 0)),
    }


# ---------------------------------------------------------------------
# JATAH: memeriksa apakah akun masih boleh chat
# ---------------------------------------------------------------------
async def periksa_jatah(sub: Optional[str]) -> Dict[str, Any]:
    """
    Memeriksa jatah harian akun SEBELUM chat dikerjakan.

    Mengembalikan:
        {
          "boleh": bool,        # False = tolak, jatah pesan habis
          "sub": str|None,      # akun yang diperiksa (None = tamu)
          "terpakai": int,      # request akun pada jendela berjalan
          "batas": int,         # jatah request akun per jendela
          "sisa": int,
          "token_terpakai": int,   # hanya informasi, BUKAN pembatas
          "reset_detik": int,   # hitung mundur ke akhir JENDELA AKUN
          "alasan": str|None,   # 'request' bila ditolak
        }

    ATURAN PENTING:
    - Penyimpanan mati TIDAK boleh memblokir chat. Bila angka tidak bisa
      dibaca, fungsi ini mengembalikan `boleh=True` — lebih baik
      kehilangan penegakan jatah daripada mematikan situs.
    - Penolakan hanya terjadi bila angka BENAR-BENAR terbaca dan sudah
      melewati batas. Tidak ada penolakan berdasarkan perkiraan.
    - Hanya JUMLAH PESAN yang membatasi. Token dicatat sebagai informasi
      untuk pengguna, tidak pernah menolak (alasannya lihat JATAH_AKUN).
    - Reset memakai JENDELA 24 JAM BERGULIR milik akun itu sendiri
      (lihat _jendela_akun), bukan jam dinding yang sama untuk semua.
    """
    sub_sah = _sub_sah(sub)
    hasil: Dict[str, Any] = {
        "boleh": True,
        "sub": sub_sah,
        "terpakai": 0,
        "batas": JATAH_AKUN["rpd"],
        "sisa": JATAH_AKUN["rpd"],
        "token_terpakai": 0,
        "reset_detik": _detik_sampai_reset_harian(),
        "alasan": None,
    }

    # Tamu tidak punya akun -> jatah per-IP ditangani main.py.
    if not sub_sah:
        hasil["batas"] = JATAH_TAMU["rpd"]
        hasil["sisa"] = JATAH_TAMU["rpd"]
        return hasil

    # Penyimpanan tidak tersedia: jangan memblokir siapa pun.
    if not (_UPSTASH_URL and _UPSTASH_TOKEN):
        return hasil

    try:
        jendela = await _jendela_akun(sub_sah)
        catatan = await _baca_jendela(sub_sah)
    except Exception:  # noqa: BLE001
        return hasil

    terpakai = max(0, int(catatan.get("requests", 0)))
    token_terpakai = max(0, int(catatan.get("tokens", 0)))

    hasil["terpakai"] = terpakai
    hasil["token_terpakai"] = token_terpakai
    hasil["sisa"] = max(0, JATAH_AKUN["rpd"] - terpakai)
    hasil["reset_detik"] = jendela["sisa_detik"]

    # Hanya jumlah pesan yang menentukan boleh/tidak.
    if terpakai >= JATAH_AKUN["rpd"]:
        hasil["boleh"] = False
        hasil["alasan"] = "request"

    return hasil


def _detik_sampai_reset_menit() -> int:
    """Sisa detik hingga menit berikutnya (jendela per menit Groq)."""
    sekarang = datetime.now(timezone.utc)
    return 60 - sekarang.second


def batas_model(model: str) -> Dict[str, int]:
    """Batas kuota untuk sebuah model; default bila tidak dikenal."""
    return BATAS_KUOTA.get(model, BATAS_DEFAULT)


def _persen(terpakai: int, batas: int) -> float:
    if batas <= 0:
        return 0.0
    nilai = (terpakai / batas) * 100
    return round(min(100.0, max(0.0, nilai)), 1)


async def ringkasan(
    provider: str,
    model: str,
    sisa_header: Optional[Dict[str, Any]] = None,
    sub: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Menyusun data untuk panel Usage di frontend.

    `sisa_header` berisi nilai x-ratelimit-* dari respons Groq terakhir
    (bila ada). Nilai dari penyedia SELALU diprioritaskan di atas
    hitungan lokal, karena penyedia yang menentukan kebenaran.

    `sub` (opsional) = akun Google yang sudah Diverifikasi server. Bila
    diisi, respons mendapat bagian "akun" berisi pemakaian MILIK AKUN ITU
    SENDIRI. Bagian kuota penyedia tetap global karena memang dipakai
    bersama semua pengguna — menampilkannya seolah milik satu akun akan
    menyesatkan.

    CATATAN KEAMANAN: parameter `provider` & `model` tetap dipakai untuk
    menghitung batas kuota, tetapi NILAINYA TIDAK dikembalikan ke klien.
    Respons hanya berisi label publik "gungdev".
    """
    batas = batas_model(model)
    harian = await baca_harian()

    # Bila pemanggil tidak memberi header, pakai yang tersimpan dari
    # respons penyedia terakhir. Ini membuat /usage akurat tanpa perlu
    # memanggil Groq lagi (hemat kuota!).
    if sisa_header is None:
        sisa_header = ambil_header_kuota()

    # PENTING — semantik header Groq (sudah diverifikasi lewat pengujian):
    #   x-ratelimit-remaining-requests -> sisa REQUEST PER HARI (RPD)
    #   x-ratelimit-remaining-tokens   -> sisa TOKEN PER MENIT (TPM)
    #
    # Header token TIDAK mewakili kuota harian. Memakainya sebagai
    # kuota harian membuat panel melaporkan "96% habis" padahal itu
    # hanya jendela 60 detik yang pulih segera. Karena itu:
    #   - request : pakai header (benar-benar harian)
    #   - token   : pakai hitungan server terhadap batas harian (TPD)
    sisa_request_penyedia = (sisa_header or {}).get("remaining_requests")

    if isinstance(sisa_request_penyedia, int):
        sisa_request = sisa_request_penyedia
    else:
        sisa_request = max(0, batas["rpd"] - harian["requests"])

    # Token harian selalu dari pencatatan server (perkiraan jujur).
    sisa_token = max(0, batas["tpd"] - harian["tokens"])

    terpakai_request = batas["rpd"] - sisa_request
    terpakai_token = batas["tpd"] - sisa_token

    reset_harian = _detik_sampai_reset_harian()

    hasil: Dict[str, Any] = {
        # Nama penyedia & model SENGAJA diganti label publik: panel ini
        # dapat dibaca siapa saja, jadi detail teknis tidak boleh bocor.
        "provider": "gungdev",
        "model": "gungdev",
        # Request (RPD) — angka penyedia bila tersedia
        "requests": {
            "terpakai": max(0, terpakai_request),
            "batas": batas["rpd"],
            "sisa": max(0, sisa_request),
            "persen": _persen(terpakai_request, batas["rpd"]),
            "akurat": isinstance(sisa_request_penyedia, int),
        },
        # Token (TPD) — dari pencatatan server
        "tokens": {
            "terpakai": max(0, terpakai_token),
            "batas": batas["tpd"],
            "sisa": max(0, sisa_token),
            "persen": _persen(terpakai_token, batas["tpd"]),
            "akurat": False,
        },
        # Kuota per menit (dipakai untuk peringatan "terlalu cepat")
        "per_menit": {
            "request_batas": batas["rpm"],
            "token_batas": batas["tpm"],
            "reset_detik": _detik_sampai_reset_menit(),
        },
        # Reset harian
        "reset": {
            "detik": reset_harian,
            "jam": round(reset_harian / 3600, 1),
            "waktu_utc": (
                datetime.now(timezone.utc) + timedelta(seconds=reset_harian)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zona": "UTC",
        },
        # Transparansi sumber angka, agar tidak menyesatkan pengguna.
        "sumber": (
            "penyedia" if isinstance(sisa_request_penyedia, int) else "perkiraan"
        ),
        "catatan": (
            "Jumlah permintaan dibaca langsung dari penyedia AI sehingga akurat. "
            "Jumlah token dicatat dari angka resmi penyedia; bila penyedia tidak "
            "mengirimkannya, server memakai perkiraan sehingga angkanya bisa "
            "sedikit berbeda."
        ),
        "token_per_menit_sisa": (sisa_header or {}).get("remaining_tokens"),
    }

    # ------------------------------------------------------------------
    # Pemakaian MILIK AKUN INI SENDIRI.
    #
    # Penting dibedakan dari angka di atas: kuota penyedia dipakai
    # bersama semua pengunjung, sedangkan angka di bawah ini benar-benar
    # milik satu akun. Bila `sub` kosong (tamu), bagian ini tidak
    # dikirim sama sekali — tamu memang tidak punya akun.
    # ------------------------------------------------------------------
    sub_sah = _sub_sah(sub)
    if sub_sah:
        try:
            jendela = await _jendela_akun(sub_sah)
            milik = await _baca_jendela(sub_sah)
        except Exception:  # noqa: BLE001
            jendela = {
                "sisa_detik": reset_harian,
                "akhir": datetime.now(timezone.utc).timestamp() + reset_harian,
            }
            milik = {"requests": 0, "tokens": 0}

        jatah_req = JATAH_AKUN["rpd"]
        terpakai_req = max(0, int(milik["requests"]))
        terpakai_token = max(0, int(milik["tokens"]))
        sisa_akun = jendela["sisa_detik"]

        hasil["akun"] = {
            "requests": {
                "terpakai": terpakai_req,
                # Ini JATAH SUNGGUHAN milik akun ini — bukan angka
                # tampilan. Bila terpakai mencapai batas, /chat menolak
                # sampai jendela akun ini berakhir (lihat periksa_jatah).
                "batas": jatah_req,
                "sisa": max(0, jatah_req - terpakai_req),
                "persen": _persen(terpakai_req, jatah_req),
            },
            # Token hanya INFORMASI: dicatat dan ditampilkan agar
            # pengguna tahu pemakaiannya, tetapi tidak membatasi chat.
            "tokens": {
                "terpakai": terpakai_token,
                "batas": None,
                "sisa": None,
                "persen": None,
            },
            "habis": terpakai_req >= jatah_req,
            # Reset memakai JENDELA AKUN INI SENDIRI (24 jam bergulir
            # sejak pesan pertamanya), bukan jam dinding bersama.
            "reset": {
                "detik": sisa_akun,
                "jam": round(sisa_akun / 3600, 1),
                "waktu_utc": datetime.fromtimestamp(
                    jendela["akhir"], tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "zona": "UTC",
                "bergulir": True,
                "jendela_jam": round(JENDELA_JATAH_DETIK / 3600, 1),
            },
            "catatan": (
                "Jatah ini milik akun Anda sendiri dan terpisah dari akun lain. "
                f"Jendela {round(JENDELA_JATAH_DETIK / 3600)} jam dimulai saat "
                "pesan pertama Anda, dan jatah kembali penuh saat jendela itu "
                "berakhir. Akun yang tidak menghabiskan jatah tidak pernah "
                "dibatasi."
            ),
        }
    else:
        # Tamu: tidak punya akun, jadi tidak ada jatah per akun.
        # Batas 3 pesan/hari per IP ditegakkan di main.py.
        hasil["tamu"] = {
            "batas_pesan": JATAH_TAMU["rpd"],
            "catatan": "Masuk dengan Google untuk mendapat jatah 100 pesan/hari.",
        }

    return hasil
