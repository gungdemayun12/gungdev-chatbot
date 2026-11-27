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
# KUOTA PENYEDIA YANG DIPAKAI BERSAMA (dasar perhitungan jatah)
# ---------------------------------------------------------------------
# Dua penyedia dipakai bergantian menurut model yang dipilih pengguna:
#
#   Penyedia A (model :free) : 50 request/hari, tanpa batas token
#   Penyedia B (Groq)        : 3 model gratis, masing-masing
#                              1.000 request/hari DAN 200.000 token/hari
#
# PENTING — kuota Groq dihitung PER MODEL, bukan per penyedia. Tiga model
# gratis yang kita pakai (gpt-oss-120b, gpt-oss-20b, qwen3.8-27b) punya
# jatah masing-masing, jadi kapasitas gabungan penyedia B adalah
# 3 x 1.000 = 3.000 request dan 3 x 200.000 = 600.000 token per hari.
#
# Hitungan sebelumnya hanya memakai SATU model Groq + OpenRouter
# (50 request, 200.000 token), sehingga jatah per akun jadi jauh lebih
# kecil dari yang sebenarnya bisa diberikan.
KUOTA_BERSAMA = {
    # Request penyedia langka (OpenRouter :free). Tetap dicatat karena
    # inilah penyedia yang paling cepat habis bila semua orang memilih
    # model :free.
    "rpd_penyedia_langka": 50,
    # Model Groq gratis yang kuotanya terpisah satu sama lain.
    "model_groq": 3,
    # ------------------------------------------------------------------
    # NVIDIA NIM: SENGAJA TIDAK DIHITUNG
    # ------------------------------------------------------------------
    # NVIDIA memberi "trial credits" (~1.000 panggilan) untuk akun
    # Developer gratis — BUKAN kuota harian permanen seperti Groq.
    # Kreditnya terbatas dan berlaku ±90 hari.
    #
    # Kalau kredit itu dihitung sebagai kapasitas harian, jatah per akun
    # akan naik berdasarkan kuota yang bisa hilang tanpa peringatan, dan
    # begitu kredit habis SEMUA pengunjung kehilangan jatah itu sekaligus.
    # Karena itu NVIDIA dipakai sebagai:
    #   - jalur cadangan keempat saat Groq/Gemini/OpenRouter habis, dan
    #   - sumber model tambahan yang bisa dipilih pengguna,
    # tetapi TIDAK dipakai sebagai dasar menaikkan jatah.
    #
    # Artinya: menambah NVIDIA memperbanyak PILIHAN MODEL, bukan
    # menambah jatah harian. Menambah jatah butuh penyedia dengan kuota
    # harian tetap (lihat catatan di RIWAYAT-SERVER.md).
    "trial_nvidia_dihitung": 0,
    "rpd_per_model_groq": 1_000,
    "tpd_per_model_groq": 200_000,
    # Gemini (penyedia cadangan). Google TIDAK lagi mempublikasikan angka
    # RPD pasti untuk free tier, jadi angka di bawah adalah perkiraan
    # KONSERVATIF yang sengaja dibuat kecil: bila ternyata kuota aslinya
    # lebih besar, tidak ada yang rusak — hanya saja perhitungan kita
    # tidak memanfaatkannya. Yang penting jangan sampai terlalu besar,
    # karena itu akan membuat jatah per akun melebihi kuota nyata.
    #
    # Rujukan: free tier Gemini 2.5 Flash sekitar 250 request/hari dan
    # 250.000 token/menit. Kita pakai 200 request/hari dan 250.000 token
    # per hari (bukan per menit) agar aman.
    "rpd_gemini": 200,
    "tpd_gemini": 250_000,
    # Rata-rata token per pesan (prompt + riwayat + jawaban). Diukur dari
    # pemakaian nyata: pesan pendek ~700 token, pesan panjang/riset
    # ~3.000 token, sehingga rata-ratanya ~1.500.
    "token_per_pesan": 1_500,
}

# Kapasitas gabungan per hari (dihitung dari KUOTA_BERSAMA di atas).
KAPASITAS_HARIAN = {
    "request": (
        KUOTA_BERSAMA["model_groq"] * KUOTA_BERSAMA["rpd_per_model_groq"]
        + KUOTA_BERSAMA["rpd_penyedia_langka"]
        + KUOTA_BERSAMA["rpd_gemini"]
    ),
    "token": (
        KUOTA_BERSAMA["model_groq"] * KUOTA_BERSAMA["tpd_per_model_groq"]
        + KUOTA_BERSAMA["tpd_gemini"]
    ),
}

# Berapa PESAN yang muat per hari bila seluruh token dipakai bertanya.
# Inilah kendala sebenarnya (request jauh lebih longgar).
PESAN_PER_HARI = KAPASITAS_HARIAN["token"] // max(
    1, KUOTA_BERSAMA["token_per_pesan"]
)

# ---------------------------------------------------------------------
# JATAH HARIAN PER AKUN
# ---------------------------------------------------------------------
# Kuota penyedia dipakai BERSAMA semua pengunjung dan tidak bisa dibagi
# oleh kita. Tanpa batas per akun, satu pengguna yang sangat aktif bisa
# menghabiskan kuota seluruh situs sehingga pengunjung lain tiba-tiba
# tidak bisa chat. Karena itu tiap akun mendapat jatah sendiri yang
# ditegakkan di server.
#
# PERHITUNGAN ANGKA (dipakai JATAH_AKUN_DASAR di bawah):
#   Kapasitas gabungan per hari (lihat KAPASITAS_HARIAN):
#     request : 3 x 1.000 (Groq) + 200 (Gemini) + 50 (OpenRouter)
#               = 3.250 request
#     token   : 3 x 200.000 (Groq) + 250.000 (Gemini) = 850.000 token
#   Kendala yang lebih dulu habis adalah TOKEN:
#     850.000 token / 1.500 token per pesan = 566 pesan/hari
#   Dibagi ke ~10 akun aktif:
#     566 / 10 = 56 pesan per akun
#   => jatah TEORITIS 56, dipakai 52 (JATAH_AKUN_DASAR).
#
# KENAPA 52, BUKAN 56
# -------------------
# 52 diambil dari 56 dikurangi ±7% sebagai bantalan, dan merupakan
# kenaikan 48 -> 52 (+4 pesan, +8,3%).
#
# Catatan revisi: sebelumnya angkanya 48 (bantalan ±15%). Bantalan
# diperkecil karena pemakaian nyata di produksi menunjukkan kuota masih
# tersisa cukup saat angka 48 dipakai, sehingga 4 pesan tambahan masih
# tertutup. Bantalan tetap ada karena:
#   - Angka Gemini sengaja konservatif (Google tidak lagi mempublikasikan
#     RPD pasti; sebagian model dibatasi untuk akun lama).
#   - Rata-rata 1.500 token/pesan adalah RATA-RATA. Pesan riset/file bisa
#     3.000 token (2x lipat).
#   - Bila kuota ternyata lebih kecil dari perkiraan, jatah 56 membuat
#     kuota situs habis sebelum hari berakhir dan SEMUA pengunjung kena.
#
# MENGAPA TIDAK LEBIH TINGGI
# --------------------------
# 56 adalah batas aman teoretis kalau kita menganggap SEMUA 10 akun
# aktif menghabiskan jatahnya. Di atas 56, kuota situs bisa habis di
# tengah hari. Itu sebabnya NVIDIA (trial credit) tidak dihitung, dan
# kenaikan besar baru mungkin bila ada kuota harian TETAP yang baru.
#
# CATATAN PEMAKAIAN NYATA
# -----------------------
# Batas ini hanya mengikat bila jumlah akun aktif x jatah melebihi
# kapasitas 566 pesan/hari. Dengan 52: 566/52 = 10 akun aktif penuh.
# Bila akun aktif lebih dari itu, penjaga otomatis di bawah
# (JATAH_SAAT_KUOTA_TIPIS) yang menurunkan jatah sementara — jadi situs
# tidak mati, hanya lebih ketat saat ramai.
#
# Kenapa 52 dan bukan 16 atau 80:
#   - 16  : hanya memakai 1 model Groq + OpenRouter (terlalu pesimis,
#           kapasitas sebenarnya 3x lebih besar karena kuota per model).
#   - 80  : hanya aman bila <= 7 akun aktif/hari; satu pengguna yang suka
#           riset web memakai ~3.000 token/pesan (2x rata-rata), jadi
#           kuota bisa habis sebelum hari berakhir.
#   - 52  : aman untuk ~10 akun aktif/hari dan masih menyisakan ruang
#           untuk pesan panjang/riset.
#
# Bila pemakaian nyata menunjukkan kuota masih lega (cek panel
# "Layanan" di /usage), angka ini boleh dinaikkan tanpa mengubah kode:
# cukup pasang Environment Variable JATAH_REQUEST_PER_AKUN di Vercel.
#
# Penjaga agar kuota tidak habis:
#   - Bila kuota situs tersisa < 15%, tiap akun yang masih punya jatah
#     dipangkas ke 8 pesan/24 jam (JATAH_SAAT_KUOTA_TIPIS). Akun yang
#     datang belakangan tetap bisa memakai layanan.
#   - Total akun baru per hari dibatasi MAX_AKUN_BARU_PER_HARI. Tanpa
#     ini, 25 akun baru sehari (x 52 pesan) langsung menghabiskan kuota.
JATAH_AKUN_DASAR = int(os.getenv("JATAH_REQUEST_PER_AKUN", "52") or 52)
JATAH_SAAT_KUOTA_TIPIS = int(os.getenv("JATAH_KUOTA_TIPIS", "8") or 8)
# Akun baru per hari: 25 akun x 52 pesan = 1.300 pesan, jauh di atas
# kapasitas 566 pesan/hari. Karena itu batasnya tetap 25 agar jumlah
# akun baru tidak melampaui kapasitas token harian.
MAX_AKUN_BARU_PER_HARI = int(os.getenv("MAKS_AKUN_BARU", "25") or 25)

# Persentase sisa kuota bersama yang dianggap "tipis".
AMBANG_KUOTA_TIPIS = 0.15

# PENTING — kenapa HANYA jumlah pesan yang membatasi:
# Token tetap DICATAT dan DITAMPILKAN agar pengguna (dan pemilik situs)
# tahu pemakaiannya, tetapi sengaja TIDAK dipakai sebagai pembatas per
# akun. Panjang jawaban AI sangat bervariasi (jawaban singkat 100 token,
# jawaban panjang 3.000 token), sehingga membatasi token akan membuat
# pengguna yang bertanya hal sederhana mendapat jatah jauh lebih banyak
# daripada yang bertanya hal rumit — padahal keduanya satu pesan.
# Jumlah pesan lebih adil dan lebih mudah dipahami.
JATAH_AKUN = {"rpd": JATAH_AKUN_DASAR}

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
# JATAH BERJALAN: dasar per akun, dipangkas bila kuota bersama menipis
# ---------------------------------------------------------------------
async def sisa_pesan_situs() -> int:
    """
    Berapa pesan lagi yang muat di kuota gabungan HARI INI.

    Dipakai hanya di dalam server (indikator layanan & pemangkasan
    jatah). Angka ini TIDAK pernah dikirim ke pengguna — pengguna hanya
    melihat jatahnya sendiri.

    Kendala diambil dari yang lebih dulu habis:
      - request : 3.250/hari (3 model Groq + OpenRouter + Gemini)
      - token   : 850.000/hari -> 566 pesan
    """
    try:
        harian = await baca_harian()
    except Exception:  # noqa: BLE001
        return KAPASITAS_HARIAN["request"]

    terpakai_request = max(0, int(harian.get("requests", 0)))
    terpakai_token = max(0, int(harian.get("tokens", 0)))

    sisa_request = KAPASITAS_HARIAN["request"] - terpakai_request
    sisa_token = KAPASITAS_HARIAN["token"] - terpakai_token
    sisa_dari_token = sisa_token // max(1, KUOTA_BERSAMA["token_per_pesan"])

    return max(0, min(sisa_request, sisa_dari_token))


async def jatah_berjalan() -> int:
    """
    Jatah pesan per akun yang BERLAKU SEKARANG (24 jam bergulir).

    Kenapa tidak hanya memakai angka tetap?

    Jatah dihitung untuk ~10 akun aktif. Bila kenyataannya datang 40 akun
    sekaligus, kuota bersama akan habis di tengah hari dan semua orang
    (termasuk yang baru masuk) ikut kecewa. Karena itu:

      - kuota masih lega  -> jatah penuh (JATAH_AKUN_DASAR, 52)
      - kuota < 15% sisa  -> jatah dipangkas (JATAH_SAAT_KUOTA_TIPIS, 8)

    Pemangkasan hanya MEMBATASI lebih awal, tidak pernah menambah dan
    tidak pernah menghapus pemakaian yang sudah tercatat. Pengguna yang
    sudah memakai lebih dari angka baru tetap melihat sisa 0 dan
    mendapat pesan reset yang jelas — bukan error.

    Angkanya tetap per akun; pengguna tidak pernah melihat kuota situs.
    """
    try:
        sisa = await sisa_pesan_situs()
    except Exception:  # noqa: BLE001
        return JATAH_AKUN_DASAR

    # Pesan yang muat per hari = kapasitas token. Dianggap "tipis" bila
    # sisa pesan situs tinggal < 15% dari kapasitas harian.
    batas_tipis = int(PESAN_PER_HARI * AMBANG_KUOTA_TIPIS)
    if sisa <= batas_tipis:
        return min(JATAH_AKUN_DASAR, JATAH_SAAT_KUOTA_TIPIS)
    return JATAH_AKUN_DASAR


async def daftarkan_akun(sub: Optional[str]) -> Dict[str, Any]:
    """
    Mencatat akun BARU yang pertama kali memakai layanan hari ini.

    Tujuan: kuota penyedia dibagi ke sejumlah akun yang wajar. Tanpa
    pendaftaran, siapa pun bisa membuat puluhan akun Google dalam sehari
    dan menghabiskan kuota situs (kenyataannya sudah terjadi: 40 akun
    baru sehari = 37% dari 1.000 request/hari).

    Mengembalikan:
        {"baru": bool, "diterima": bool, "akun_hari_ini": int, "batas": int}

    ATURAN PENTING: bila penyimpanan tidak tersedia atau angkanya tidak
    bisa dibaca, akun SELALU diterima. Lebih baik melonggar daripada
    menolak pengguna sah karena masalah penyimpanan.
    """
    hasil = {
        "baru": False,
        "diterima": True,
        "akun_hari_ini": 0,
        "batas": MAX_AKUN_BARU_PER_HARI,
    }
    sub_sah = _sub_sah(sub)
    if not sub_sah:
        return hasil
    if not (_UPSTASH_URL and _UPSTASH_TOKEN):
        return hasil

    kunci_daftar = f"{_PREFIX}:akun-baru:{_hari_ini()}"
    kunci_anggota = f"{_PREFIX}:akun-terdaftar"

    try:
        sudah = await _redis_perintah("SISMEMBER", kunci_anggota, sub_sah)
        if sudah in (1, "1", True):
            # Akun lama: tidak menambah hitungan, tidak pernah ditolak.
            jumlah = await _redis_perintah("SCARD", kunci_daftar)
            hasil["akun_hari_ini"] = int(jumlah or 0)
            return hasil

        # Akun baru: catat keanggotaan dulu agar dua permintaan bersamaan
        # tidak menghitung dua kali.
        await _redis_perintah("SADD", kunci_anggota, sub_sah)
        await _redis_perintah("EXPIRE", kunci_anggota, 90 * 24 * 3600)
        await _redis_perintah("SADD", kunci_daftar, sub_sah)
        await _redis_perintah("EXPIRE", kunci_daftar, 3 * 24 * 3600)

        total = int(await _redis_perintah("SCARD", kunci_daftar) or 0)
        hasil.update(
            {
                "baru": True,
                # Akun ini ikut terhitung, jadi batasnya inklusif: kuota
                # 40 berarti akun ke-40 masih diterima, ke-41 ditolak.
                "diterima": total <= MAX_AKUN_BARU_PER_HARI,
                "akun_hari_ini": total,
            }
        )
        return hasil
    except Exception:  # noqa: BLE001
        return hasil


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
    batas = JATAH_AKUN_DASAR
    hasil: Dict[str, Any] = {
        "boleh": True,
        "sub": sub_sah,
        "terpakai": 0,
        "batas": batas,
        "sisa": batas,
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

    # Jatah berjalan bisa lebih kecil dari dasar bila kuota situs menipis.
    try:
        batas = await jatah_berjalan()
    except Exception:  # noqa: BLE001
        batas = JATAH_AKUN_DASAR
    hasil["batas"] = batas

    try:
        jendela = await _jendela_akun(sub_sah)
        catatan = await _baca_jendela(sub_sah)
    except Exception:  # noqa: BLE001
        return hasil

    terpakai = max(0, int(catatan.get("requests", 0)))
    token_terpakai = max(0, int(catatan.get("tokens", 0)))

    hasil["terpakai"] = terpakai
    hasil["token_terpakai"] = token_terpakai
    hasil["sisa"] = max(0, batas - terpakai)
    hasil["reset_detik"] = jendela["sisa_detik"]

    # Hanya jumlah pesan yang menentukan boleh/tidak.
    if terpakai >= batas:
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

    ATURAN UTAMA (permintaan pemilik situs): pengguna HANYA melihat jatah
    milik akunnya sendiri. Rincian kuota penyedia — berapa request/hari,
    token/hari, dan batas per menit — adalah urusan pemilik situs dan
    TIDAK dikirim ke klien. Yang dikirim hanyalah:

      - bagian "akun"  : jatah akun itu (terpakai, batas, sisa, reset)
      - indikator layanan: sehat / ramai / jatah dikurangi

    Indikator dibuat dari perbandingan INTERNAL terhadap kuota penyedia,
    lalu diringkas menjadi satu kata. Angka mentahnya tidak pernah ikut.

    `sisa_header` berisi nilai x-ratelimit-* dari respons penyedia
    terakhir (bila ada) dan hanya dipakai untuk indikator itu.

    CATATAN KEAMANAN: parameter `provider` & `model` tetap dipakai untuk
    menghitung batas kuota, tetapi NILAINYA TIDAK dikembalikan ke klien.
    Respons hanya berisi label publik "gungdev".
    """
    batas = batas_model(model)
    harian = await baca_harian()

    # Bila pemanggil tidak memberi header, pakai yang tersimpan dari
    # respons penyedia terakhir. Ini membuat /usage akurat tanpa perlu
    # memanggil penyedia lagi (hemat kuota!).
    if sisa_header is None:
        sisa_header = ambil_header_kuota()

    # PENTING — semantik header Groq (sudah diverifikasi lewat pengujian):
    #   x-ratelimit-remaining-requests -> sisa REQUEST PER HARI (RPD)
    #   x-ratelimit-remaining-tokens   -> sisa TOKEN PER MENIT (TPM)
    #
    # Header token TIDAK mewakili kuota harian. Memakainya sebagai
    # kuota harian membuat panel melaporkan "96% habis" padahal itu
    # hanya jendela 60 detik yang pulih segera.
    sisa_request_penyedia = (sisa_header or {}).get("remaining_requests")

    if isinstance(sisa_request_penyedia, int):
        sisa_request = sisa_request_penyedia
    else:
        sisa_request = max(0, batas["rpd"] - harian["requests"])

    # Token harian selalu dari pencatatan server (perkiraan jujur).
    sisa_token = max(0, batas["tpd"] - harian["tokens"])

    reset_harian = _detik_sampai_reset_harian()

    # ------------------------------------------------------------------
    # Indikator layanan — RINGKASAN, bukan angka kuota penyedia.
    #
    # Perbandingan dilakukan di dalam server (memakai kuota yang lebih
    # dulu habis), lalu hasilnya dipadatkan menjadi satu status. Tidak
    # ada angka request/token penyedia yang keluar dari server.
    # ------------------------------------------------------------------
    jatah_kini = await jatah_berjalan()
    sisa_pesan_kini = await sisa_pesan_situs()
    porsi_sisa = sisa_pesan_kini / max(1, PESAN_PER_HARI)
    if porsi_sisa <= AMBANG_KUOTA_TIPIS:
        status_layanan = "dikurangi"
    elif porsi_sisa <= 0.4:
        status_layanan = "ramai"
    else:
        status_layanan = "lancar"

    hasil: Dict[str, Any] = {
        # Nama penyedia & model SENGAJA diganti label publik: panel ini
        # dapat dibaca siapa saja, jadi detail teknis tidak boleh bocor.
        "provider": "gungdev",
        "model": "gungdev",
        # Indikator (kata, bukan angka) agar pengguna tahu kondisi
        # layanan tanpa perlu melihat kuota internal.
        "layanan": {
            "status": status_layanan,
            "jatah_dikurangi": jatah_kini < JATAH_AKUN_DASAR,
            "catatan": (
                "Layanan sedang lancar."
                if status_layanan == "lancar"
                else (
                    "Layanan sedang ramai, jadi jatah harian sementara "
                    "dikurangi sedikit agar semua pengguna tetap dapat "
                    "bagian. Jatah kembali normal otomatis."
                    if status_layanan == "dikurangi"
                    else "Layanan cukup ramai hari ini."
                )
            ),
        },
        # Reset harian layanan (00:00 UTC) — info umum, bukan kuota.
        "reset": {
            "detik": reset_harian,
            "jam": round(reset_harian / 3600, 1),
            "waktu_utc": (
                datetime.now(timezone.utc) + timedelta(seconds=reset_harian)
            ).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "zona": "UTC",
        },
        # Jatah yang berlaku sekarang (dipakai panel untuk menjelaskan
        # bila jatah sedang dikurangi).
        "jatah_penuh": JATAH_AKUN_DASAR,
    }

    # ------------------------------------------------------------------
    # Pemakaian MILIK AKUN INI SENDIRI.
    #
    # Ini satu-satunya angka jatah yang boleh dilihat pengguna. Bila
    # `sub` kosong (tamu), bagian ini tidak dikirim sama sekali — tamu
    # memang tidak punya akun.
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

        jatah_req = jatah_kini
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
                # True bila jatah hari ini lebih kecil dari biasanya,
                # agar panel bisa menjelaskan tanpa membuka kuota situs.
                "dikurangi": jatah_req < JATAH_AKUN_DASAR,
                "jatah_penuh": JATAH_AKUN_DASAR,
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
            #
            # `pada` adalah waktu absolut (detik epoch, UTC) saat jatah
            # pulih. Frontend memakai angka ini untuk menghitung mundur
            # SENDIRI setiap detik, sehingga hitung mundur tetap berjalan
            # tanpa perlu bertanya ulang ke server (hemat kuota, dan tetap
            # real time).
            "reset": {
                "detik": sisa_akun,
                "jam": round(sisa_akun / 3600, 1),
                "pada": int(jendela["akhir"]),
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
        if hasil["akun"]["requests"]["dikurangi"]:
            hasil["akun"]["catatan"] += (
                " Hari ini layanan sedang ramai, sehingga jatah harian "
                "sementara dikurangi — jatah kembali normal otomatis."
            )
    else:
        # Tamu: tidak punya akun, jadi tidak ada jatah per akun.
        # Batas 3 pesan/hari per IP ditegakkan di main.py.
        hasil["tamu"] = {
            "batas_pesan": JATAH_TAMU["rpd"],
            "jatah_akun": JATAH_AKUN_DASAR,
            "catatan": (
                "Masuk dengan Google untuk mendapat jatah "
                f"{JATAH_AKUN_DASAR} pesan per jendela 24 jam."
            ),
        }

    return hasil
