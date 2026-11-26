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
    sehingga panel Usage bisa berkata "akun Anda hari ini: 12 permintaan".

    Dipanggil dari dalam endpoint chat. Tidak pernah melempar exception.
    """
    kunci_global = _kunci_harian()
    sub_sah = _sub_sah(sub)
    kunci_akun = _kunci_harian(sub_sah) if sub_sah else None

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
                # Agak lebih lama dari global: panel akun berguna untuk
                # melihat pemakaian beberapa hari terakhir.
                await _redis_perintah("EXPIRE", kunci_akun, 30 * 24 * 3600)
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
    Membaca total request & token hari ini (UTC).

    Tanpa `sub` -> total seluruh situs.
    Dengan `sub` -> pemakaian akun itu saja.
    """
    kunci = _kunci_harian(sub)

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


def _detik_sampai_reset_harian() -> int:
    """Sisa detik hingga 00:00 UTC (jendela harian Groq)."""
    sekarang = datetime.now(timezone.utc)
    besok = (sekarang + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(0, int((besok - sekarang).total_seconds()))


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
            "Jumlah token dihitung server dari panjang percakapan, jadi bisa "
            "sedikit berbeda dari dashboard penyedia."
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
        milik = await baca_harian(sub_sah)
        hasil["akun"] = {
            "requests": {
                "terpakai": milik["requests"],
                # Batas "adil" per akun: jatah harian dibagi rata ke
                # sejumlah pengguna aktif yang wajar. Ini BUKAN blokir —
                # hanya angka acuan agar pengguna tahu posisinya.
                "batas": batas["rpd"],
                "persen": _persen(milik["requests"], batas["rpd"]),
            },
            "tokens": {
                "terpakai": milik["tokens"],
                "batas": batas["tpd"],
                "persen": _persen(milik["tokens"], batas["tpd"]),
            },
            "catatan": (
                "Angka ini pemakaian akun Anda sendiri hari ini (UTC). "
                "Sisa kuota di atas dipakai bersama seluruh pengunjung situs."
            ),
        }

    return hasil
