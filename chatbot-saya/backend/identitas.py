"""
identitas.py — memastikan pemanggil BENAR pemilik akun Google yang diklaim.

KENAPA MODUL INI ADA
--------------------
Begitu riwayat disimpan di server, backend menerima permintaan seperti
"Hapus semua riwayat milik akun 1234567890". Tanpa pemeriksaan, siapa pun
bisa mengirim angka itu dan menghapus riwayat orang lain. Karena itu
SETIAP permintaan ke /api/sessions harus membawa ID token Google, dan
server memverifikasinya lebih dulu.

CARA VERIFIKASI (tanpa pustaka tambahan)
----------------------------------------
Kita TIDAK memeriksa tanda tangan JWT sendiri (itu butuh pyjwt +
cryptography, dua dependensi yang memperbesar fungsi serverless).
Sebagai gantinya, token dikirim ke endpoint resmi Google:

    GET https://oauth2.googleapis.com/tokeninfo?id_token=<token>

Google yang memeriksa tanda tangan, masa berlaku, dan audiens. Jawaban
yang berguna hanya datang bila token memang asli. Hasilnya di-cache
singkat di memori proses agar tidak memanggil Google untuk setiap pesan
(hemat latensi & kuota).

Endpoint tokeninfo didokumentasikan Google di:
https://developers.google.com/identity/sign-in/web/backend-auth

CATATAN KEAMANAN
----------------
- `sub` yang dipakai sebagai kunci riwayat SELALU berasal dari jawaban
  Google, tidak pernah dari nilai yang dikirim klien.
- `aud` (audiens) wajib sama dengan GOOGLE_CLIENT_ID milik situs ini,
  supaya token dari aplikasi lain tidak bisa dipakai di sini.
- Token yang gagal diverifikasi dianggap tidak ada identitas sama sekali;
  permintaan riwayat ditolak, chat biasa tetap dilayani.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger("chatbot.identitas")

# Client ID situs. BUKAN rahasia (memang tampil di bundel frontend),
# tetapi wajib diketahui server untuk memeriksa `aud`.
GOOGLE_CLIENT_ID = (os.getenv("GOOGLE_CLIENT_ID") or "").strip()

_TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"

# Cache hasil verifikasi: token -> (payload, kedaluwarsa_unix_detik).
# Ukuran kecil dan umur singkat: cukup untuk menghindari panggilan
# berulang saat pengguna mengirim beberapa pesan berturut-turut, tanpa
# membuat token yang sudah dicabut tetap dianggap sah terlalu lama.
_cache: Dict[str, Tuple[Dict[str, Any], float]] = {}
_CACHE_UMUR = 300.0      # 5 menit
_CACHE_MAKS = 500        # batasi memori


def tersedia() -> bool:
    """
    Apakah verifikasi bisa dilakukan?

    Butuh GOOGLE_CLIENT_ID di environment backend. Bila kosong, endpoint
    riwayat menolak dengan pesan yang jelas alih-alih menerima identitas
    apa pun (lebih baik tidak menyimpan riwayat daripada menyimpannya
    tanpa perlindungan).
    """
    return bool(GOOGLE_CLIENT_ID)


def _bersihkan_cache() -> None:
    """Membuang entri kedaluwarsa agar memori proses tidak tumbuh."""
    sekarang = time.time()
    mati = [k for k, (_, exp) in _cache.items() if exp <= sekarang]
    for k in mati:
        _cache.pop(k, None)
    if len(_cache) > _CACHE_MAKS:
        # Buang yang paling cepat kedaluwarsa.
        for k, _ in sorted(_cache.items(), key=lambda x: x[1][1])[: len(_cache) - _CACHE_MAKS]:
            _cache.pop(k, None)


async def verifikasi_token(
    token: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Memverifikasi ID token Google.

    Mengembalikan payload Google bila sah:
        {"sub": "...", "email": "...", "name": "...", "picture": "..."}
    atau None bila token tidak ada / tidak sah / gagal diverifikasi.
    """
    token = (token or "").strip()
    if not token or len(token) > 4096:
        return None

    if not tersedia():
        logger.warning(
            "GOOGLE_CLIENT_ID belum diisi di environment backend; "
            "identitas akun tidak dapat diverifikasi."
        )
        return None

    # 1. Cache.
    kini = time.time()
    cache = _cache.get(token)
    if cache and cache[1] > kini:
        return cache[0]

    # 2. Tanya Google.
    try:
        async with httpx.AsyncClient(timeout=8.0) as http:
            res = await http.get(_TOKENINFO, params={"id_token": token})
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tidak dapat menghubungi Google tokeninfo: %s", exc)
        return None

    if res.status_code != 200:
        # 400 = token tidak sah / kedaluwarsa. Ini hal biasa (mis. token
        # lama di perangkat), bukan masalah server -> tidak perlu error.
        logger.info("Token Google ditolak (HTTP %s).", res.status_code)
        return None

    try:
        data = res.json()
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    # 3. Periksa audiens & identitas.
    aud = str(data.get("aud") or "")
    if aud != GOOGLE_CLIENT_ID:
        logger.warning("Token Google dengan audiens lain ditolak: %s", aud[:40])
        return None

    sub = str(data.get("sub") or "").strip()
    if not sub:
        return None

    # `email_verified` bisa berupa string "true" dari tokeninfo.
    terverifikasi = str(data.get("email_verified", "")).lower() in ("true", "1")

    payload = {
        "sub": sub,
        "email": str(data.get("email") or "")[:160],
        "name": str(data.get("name") or "Pengguna")[:80],
        "picture": str(data.get("picture") or "")[:400],
        "email_verified": terverifikasi,
    }

    _bersihkan_cache()
    _cache[token] = (payload, kini + _CACHE_UMUR)
    return payload
