"""
penyimpanan.py — penyimpanan riwayat percakapan di server (Upstash Redis).

KENAPA MODUL INI ADA
--------------------
Sebelumnya riwayat chat hanya tersimpan di localStorage perangkat. Artinya
membuka situs di HP dan di laptop menghasilkan dua riwayat berbeda. Supaya
satu akun Google punya riwayat yang sama di semua perangkat, datanya harus
tinggal di tempat yang bisa diakses keduanya: server.

Vercel Serverless tidak punya disk permanen, jadi datanya dititipkan ke
Upstash Redis (REST API, gratis, tanpa kartu kredit). Modul ini memakai
REST yang sama dengan `usage.py`, jadi tidak perlu pustaka Redis tambahan.

PRINSIP PENTING
---------------
1. TIDAK PERNAH membuat chat gagal.
   Semua operasi dibungkus try/except. Bila Redis tidak dikonfigurasi,
   sedang penuh, atau kuotanya habis, fungsi mengembalikan `False`/None
   dan percakapan tetap berjalan seperti biasa. Riwayat akan tersimpan
   lagi otomatis saat penyimpanan pulih.

2. TIDAK PERNAH menyimpan data tanpa identitas.
   Semua kunci memakai `sub` Google yang SUDAH diverifikasi di server,
   sehingga satu pengguna tidak mungkin membaca riwayat pengguna lain.
   `sub` juga dibatasi pola karakter supaya tidak bisa dipakai untuk
   menyusup ke kunci lain ("..", "/", spasi, dsb.).

3. Data disimpan per SESI, bukan satu blob besar.
   Menyimpan seluruh riwayat sebagai satu nilai akan membuat setiap
   pesan menulis ulang semuanya (mahal & berisiko kehilangan data saat
   dua perangkat menulis bersamaan). Di sini satu sesi = satu kunci,
   dan indeks sesi disimpan terpisah.

STRUKTUR KUNCI
--------------
    gungdev:chat:idx:<sub>            -> ZSET {sessionId: updatedAt}
    gungdev:chat:s:<sub>:<sid>        -> STRING (JSON sesi)
    gungdev:chat:aktif:<sub>          -> STRING (sessionId terakhir dibuka)

ZSET dipakai untuk indeks agar urutan "terbaru di atas" konsisten dan
bisa dipotong tanpa membaca seluruh data.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("chatbot.penyimpanan")

# ---------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------
_UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip()
_UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip()

_PREFIX = "gungdev:chat"

# Batas jumlah sesi per akun. Tanpa batas, satu akun yang sangat aktif
# bisa menghabiskan kuota gratis untuk semua orang. 200 sesi sudah jauh
# lebih banyak daripada yang bisa digulir pengguna di sidebar.
MAKS_SESI = 200

# Umur data (detik). Satu tahun: riwayat dianggap milik pengguna dan
# hanya boleh hilang bila ia sendiri menghapusnya. Angka ini hanya
# jaring pengaman agar Redis tidak penuh oleh akun yang ditinggalkan.
UMUR_DATA = 365 * 24 * 3600

# Batas ukuran agar body permintaan tidak menembus batas Vercel (4,5 MB).
MAKS_PESAN_SESI = 900_000  # ~900 KB per sesi (cukup untuk ratusan pesan)

# Pola `sub` Google: deretan angka panjang. Selain itu, kunci rahasia
# perangkat (untuk pengguna login tanpa backend lama) berbentuk hex.
_POLA_SUB = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

# Pola ID sesi. Frontend membuat ID seperti "s_mf3k9_a1b2c3", tetapi versi
# lama bisa lebih pendek. Batasnya sengaja longgar (1 karakter) supaya
# riwayat pengguna tidak ditolak hanya karena ID-nya pendek — yang penting
# adalah tidak ada karakter berbahaya ("/", ":", spasi, "..").
_POLA_SESI = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class PenyimpananPenuh(Exception):
    """Dilempar bila penyimpanan menolak data (mis. kuota habis)."""


def tersedia() -> bool:
    """
    Apakah penyimpanan server sudah dikonfigurasi?

    Dipakai endpoint untuk membalas "tersimpan di server: tidak" dengan
    jujur, sehingga frontend bisa memberi tahu pengguna bahwa riwayat
    sementara hanya ada di perangkat ini.
    """
    return bool(_UPSTASH_URL and _UPSTASH_TOKEN)


def sub_sah(sub: Optional[str]) -> Optional[str]:
    """
    Memvalidasi `sub` sebelum dipakai sebagai bagian kunci Redis.

    Mengembalikan nilai yang sudah dibersihkan, atau None bila tidak sah.
    Ini pertahanan berlapis: walaupun pemanggil lupa memeriksa identitas,
    kunci Redis tidak bisa dibelokkan ke akun lain.
    """
    if not sub:
        return None
    bersih = str(sub).strip()
    if not _POLA_SUB.match(bersih):
        return None
    return bersih


# ---------------------------------------------------------------------
# Perintah Redis (REST Upstash)
# ---------------------------------------------------------------------
async def _perintah(*perintah: Any, timeout: float = 6.0) -> Optional[Any]:
    """
    Menjalankan satu perintah Redis lewat REST Upstash.

    Mengembalikan None bila penyimpanan tidak tersedia atau gagal.
    Sengaja TIDAK melempar exception: penyimpanan riwayat tidak boleh
    menggagalkan percakapan.
    """
    if not tersedia():
        return None

    hasil = await perintah_aman(*perintah, timeout=timeout)
    return hasil


async def perintah_aman(*perintah: Any, timeout: float = 6.0) -> Optional[Any]:
    """
    Seperti `_perintah`, tetapi membedakan "gagal" dari "data kosong".

    Dipakai operasi tulis agar pemanggil tahu kapan harus memberi tahu
    frontend bahwa riwayat TIDAK tersimpan di server (sehingga salinan
    di perangkat harus dipertahankan).
    """
    if not tersedia():
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            res = await http.post(
                _UPSTASH_URL,
                headers={
                    "Authorization": f"Bearer {_UPSTASH_TOKEN}",
                    "Content-Type": "application/json",
                },
                json=[str(p) for p in perintah],
            )
            if res.status_code >= 400:
                logger.warning("Upstash menolak perintah: %s", res.text[:200])
                return None
            data = res.json()
            if isinstance(data, dict) and data.get("error"):
                logger.warning("Upstash error: %s", str(data.get("error"))[:200])
                return None
            return data.get("result")
    except Exception as exc:  # noqa: BLE001
        logger.warning("Upstash tidak dapat dihubungi: %s", exc)
        return None


def _kunci_indeks(sub: str) -> str:
    return f"{_PREFIX}:idx:{sub}"


def _kunci_sesi(sub: str, sid: str) -> str:
    return f"{_PREFIX}:s:{sub}:{sid}"


def _kunci_aktif(sub: str) -> str:
    return f"{_PREFIX}:aktif:{sub}"


# ---------------------------------------------------------------------
# Membaca
# ---------------------------------------------------------------------
async def daftar_sesi(sub: str, batas: int = MAKS_SESI) -> Dict[str, Any]:
    """
    Mengambil seluruh riwayat milik satu akun.

    Mengembalikan:
        {"tersedia": bool, "sessions": [...], "activeId": str|None}

    `tersedia=False` berarti penyimpanan sedang tidak bisa dipakai —
    frontend memakai ini untuk memutuskan apakah salinan di perangkat
    perlu dipertahankan sebagai cadangan.
    """
    sub = sub_sah(sub)
    if not sub:
        return {"tersedia": False, "sessions": [], "activeId": None}

    if not tersedia():
        return {"tersedia": False, "sessions": [], "activeId": None}

    # 1. Indeks: sesi terbaru lebih dulu.
    ids = await _perintah("ZRANGE", _kunci_indeks(sub), 0, max(0, batas - 1), "REV")
    if not isinstance(ids, list):
        return {"tersedia": False, "sessions": [], "activeId": None}

    ids = [str(i) for i in ids if i]
    if not ids:
        return {"tersedia": True, "sessions": [], "activeId": None}

    # 2. Isi setiap sesi dalam SATU perjalanan (pipeline).
    mentah = await _perintah("MGET", *[_kunci_sesi(sub, sid) for sid in ids])
    if not isinstance(mentah, list):
        return {"tersedia": False, "sessions": [], "activeId": None}

    sessions: List[dict] = []
    hilang: List[str] = []
    for sid, isi in zip(ids, mentah):
        if not isi:
            hilang.append(sid)  # indeks menunjuk data yang sudah kedaluwarsa
            continue
        try:
            obj = json.loads(isi)
        except (TypeError, ValueError):
            hilang.append(sid)
            continue
        if isinstance(obj, dict) and obj.get("id"):
            sessions.append(obj)
        else:
            hilang.append(sid)

    # 3. Bersihkan sisa indeks yang datanya sudah tidak ada.
    if hilang:
        await _perintah("ZREM", _kunci_indeks(sub), *hilang)

    aktif = await _perintah("GET", _kunci_aktif(sub))
    active_id = str(aktif) if aktif else None
    if active_id and not any(s.get("id") == active_id for s in sessions):
        active_id = None

    return {"tersedia": True, "sessions": sessions, "activeId": active_id}


# ---------------------------------------------------------------------
# Menulis
# ---------------------------------------------------------------------
def bersihkan_sesi(sesi: Any) -> Optional[dict]:
    """
    Menyaring satu sesi dari field yang tidak dikenal / berbahaya.

    Frontend mengirim objek yang bentuknya bisa berubah sewaktu-waktu,
    jadi server hanya menyimpan field yang memang dikenal. Ini mencegah
    isi localStorage lama yang aneh ikut tersimpan selamanya.
    """
    if not isinstance(sesi, dict):
        return None

    sid = str(sesi.get("id") or "").strip()
    if not _POLA_SESI.match(sid):
        return None

    pesan_masuk = sesi.get("messages")
    if not isinstance(pesan_masuk, list):
        pesan_masuk = []

    pesan: List[dict] = []
    for m in pesan_masuk[-400:]:
        if not isinstance(m, dict):
            continue
        peran = m.get("role")
        if peran not in ("user", "assistant"):
            continue
        isi = m.get("content")
        if not isinstance(isi, str):
            isi = "" if isi is None else str(isi)
        pesan.append(
            {
                "id": str(m.get("id") or ""),
                "role": peran,
                "content": isi[:20000],
                "createdAt": int(m.get("createdAt") or 0),
                "feedback": (
                    m.get("feedback") if m.get("feedback") in ("like", "dislike") else None
                ),
            }
        )

    try:
        dibuat = int(sesi.get("createdAt") or 0)
    except (TypeError, ValueError):
        dibuat = 0
    try:
        diperbarui = int(sesi.get("updatedAt") or 0)
    except (TypeError, ValueError):
        diperbarui = 0

    judul = str(sesi.get("title") or "Percakapan baru")[:160]

    hasil = {
        "id": sid,
        "title": judul,
        "titleLocked": bool(sesi.get("titleLocked")),
        "messages": pesan,
        "createdAt": dibuat,
        "updatedAt": diperbarui or dibuat,
        "pinned": bool(sesi.get("pinned")),
    }

    if len(json.dumps(hasil, ensure_ascii=False)) > MAKS_PESAN_SESI:
        return None

    return hasil


async def simpan_sesi(sub: str, sesi: Any) -> bool:
    """
    Menyimpan SATU sesi (tambah baru atau perbarui).

    Mengembalikan True bila benar-benar tersimpan di server. `False`
    berarti frontend harus mempertahankan salinan di perangkat.
    """
    sub = sub_sah(sub)
    if not sub:
        return False

    bersih = bersihkan_sesi(sesi)
    if not bersih:
        return False

    if not tersedia():
        return False

    sid = bersih["id"]
    waktu = bersih.get("updatedAt") or int(
        datetime.now(timezone.utc).timestamp() * 1000
    )
    isi = json.dumps(bersih, ensure_ascii=False, separators=(",", ":"))

    # Tulis isi lebih dulu. Kalau ini gagal, indeks tidak boleh berubah —
    # supaya tidak ada baris riwayat yang menunjuk ke data yang tidak ada.
    hasil = await perintah_aman(
        "SET", _kunci_sesi(sub, sid), isi, "EX", UMUR_DATA, timeout=12.0
    )
    if hasil is None:
        return False

    # Perbarui indeks. Dipisah karena kegagalan di sini tidak menghilangkan
    # data; sesi tetap bisa dibaca lewat daftar berikutnya.
    #
    # Skor ZSET = waktu "diperbarui" sesi, dan HARUS unik antar-sesi.
    # Dua masalah yang diatasi di sini:
    #
    # 1. `updatedAt` bisa sama persis (dua sesi disimpan pada milidetik
    #    yang sama). Bila skornya seri, Redis mengurutkan berdasarkan
    #    nama anggota, sehingga riwayat bisa "melompat" posisi. Pecahan
    #    di bawah 1 milidetik yang diturunkan dari ID sesi membuat skor
    #    selalu unik tanpa mengubah urutan berdasarkan waktu.
    #
    # 2. Jam perangkat bisa ngawur (tahun 1970, atau tahun depan). Nilai
    #    yang terlalu jauh digeser ke "sekarang" — tetapi pergeseran
    #    hanya dilakukan bila memang perlu, dan pecahan jitter tetap
    #    dipertahankan agar sesi-sesi yang sama-sama ngawur tidak
    #    bertabrakan skornya.
    jitter = (abs(hash(sid)) % 900) / 1000.0
    waktu_ms = int(waktu)

    sekarang_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    batas_bawah = sekarang_ms - UMUR_DATA * 1000
    # Toleransi jam perangkat yang sedikit maju (mis. beda zona / NTP).
    batas_atas = sekarang_ms + 24 * 3600 * 1000

    if waktu_ms < batas_bawah or waktu_ms > batas_atas:
        logger.info(
            "Waktu sesi %s di luar rentang wajar (%s); memakai waktu server.",
            sid,
            waktu_ms,
        )
        waktu_ms = sekarang_ms

    skor = waktu_ms + jitter

    ditambah = await perintah_aman(
        "ZADD", _kunci_indeks(sub), skor, sid, timeout=10.0
    )
    if ditambah is None:
        return False

    await perintah_aman("EXPIRE", _kunci_indeks(sub), UMUR_DATA, timeout=8.0)

    # Potong sesi terlama bila melebihi batas. Tidak fatal bila gagal.
    jumlah = await perintah_aman("ZCARD", _kunci_indeks(sub), timeout=8.0)
    try:
        total = int(jumlah or 0)
    except (TypeError, ValueError):
        total = 0
    if total > MAKS_SESI:
        lebih = total - MAKS_SESI
        buang = await perintah_aman(
            "ZRANGE", _kunci_indeks(sub), 0, lebih - 1, timeout=8.0
        )
        if isinstance(buang, list) and buang:
            nama = [str(x) for x in buang if x]
            if nama:
                await perintah_aman("DEL", *[_kunci_sesi(sub, x) for x in nama], timeout=10.0)
                await perintah_aman("ZREM", _kunci_indeks(sub), *nama, timeout=8.0)

    return True


async def simpan_banyak(sub: str, daftar: Any) -> Dict[str, Any]:
    """
    Menyimpan beberapa sesi sekaligus (dipakai saat menyinkronkan salinan
    dari perangkat ke server).

    Mengembalikan ringkasan: {"tersimpan": n, "gagal": n}.
    """
    if not isinstance(daftar, list):
        return {"tersimpan": 0, "gagal": 0}

    tersimpan = 0
    gagal = 0
    for sesi in daftar[:MAKS_SESI]:
        if await simpan_sesi(sub, sesi):
            tersimpan += 1
        else:
            gagal += 1
    return {"tersimpan": tersimpan, "gagal": gagal}


async def hapus_sesi(sub: str, sid: str) -> bool:
    """Menghapus satu sesi milik akun. Mengembalikan True bila berhasil."""
    sub = sub_sah(sub)
    sid = str(sid or "").strip()
    if not sub or not _POLA_SESI.match(sid):
        return False
    if not tersedia():
        return False

    await _perintah("DEL", _kunci_sesi(sub, sid))
    hasil = await perintah_aman("ZREM", _kunci_indeks(sub), sid)
    return hasil is not None


async def hapus_semua(sub: str) -> bool:
    """Menghapus SELURUH riwayat akun (tombol "Hapus semua")."""
    sub = sub_sah(sub)
    if not sub or not tersedia():
        return False

    ids = await _perintah("ZRANGE", _kunci_indeks(sub), 0, -1)
    if isinstance(ids, list) and ids:
        nama = [str(x) for x in ids if x]
        if nama:
            await perintah_aman(
                "DEL", *[_kunci_sesi(sub, x) for x in nama], timeout=20.0
            )
    await _perintah("DEL", _kunci_indeks(sub))
    await _perintah("DEL", _kunci_aktif(sub))
    return True


async def simpan_aktif(sub: str, sid: Optional[str]) -> bool:
    """Menyimpan sesi yang sedang dibuka (agar refresh & perangkat lain sepakat)."""
    sub = sub_sah(sub)
    if not sub or not tersedia():
        return False

    if not sid:
        await perintah_aman("DEL", _kunci_aktif(sub))
        return True

    sid = str(sid).strip()
    if not _POLA_SESI.match(sid):
        return False

    hasil = await perintah_aman(
        "SET", _kunci_aktif(sub), sid, "EX", UMUR_DATA, timeout=8.0
    )
    return hasil is not None
