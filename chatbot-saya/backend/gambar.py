"""
gambar.py — pembuatan & penyuntingan gambar (tanpa API key, tanpa biaya).

KENAPA MODUL INI ADA
--------------------
Pemilik situs ingin GungDev bisa MEMBUAT gambar bila pengguna memintanya,
tanpa harus memilih model sendiri: "kalau user pengen generate gambar,
AI otomatis memakai model yang cocok". Sama seperti riset web yang juga
berjalan otomatis untuk semua model.

Modul ini hanya menangani SATU hal: dari pesan pengguna, tentukan
apakah ia minta gambar dibuat/disunting, ubah pesannya menjadi
deskripsi gambar yang baik, lalu ambil gambarnya dari layanan gambar.

BIAYA & JATAH
-------------
Layanan gambar yang dipakai GRATIS: tanpa API key, tanpa kartu kredit,
tanpa pendaftaran. Konsekuensinya (jujur): kualitas di bawah layanan
berbayar, kadang lambat, dan bisa gagal saat ramai. Karena itu:

  - Jatah gambar DIPISAH dari jatah chat (lihat usage.jatah_gambar).
    Membuat gambar tidak pernah mengurangi 52 pesan chat.
  - Kegagalan membuat gambar TIDAK boleh menggagalkan chat: pemanggil
    harus tetap menjawab dengan teks biasa.

MENGAPA GAMBAR DIAMBIL DI SERVER (bukan di browser)
---------------------------------------------------
1. Kalau browser memanggil langsung, gambarnya bisa terhalang aturan
   keamanan browser (CORS) sehingga gagal tanpa penjelasan.
2. Jatah gambar hanya bisa ditegakkan di server; dari browser, siapa pun
   bisa memanggil layanan gambar berkali-kali.
3. Hasilnya dikirim sebagai data URL, jadi gambar TETAP TAMPIL di
   percakapan (tidak perlu hosting gambar terpisah).

CATATAN PRIVASI: deskripsi gambar dikirim ke layanan gambar publik.
Karena itu pesan pengguna TIDAK dikirim mentah-mentah bila tidak perlu.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx

logger = logging.getLogger("chatbot.gambar")

# ---------------------------------------------------------------------
# KONFIGURASI
# ---------------------------------------------------------------------
# Layanan gambar gratis. Bisa diganti lewat env tanpa mengubah kode,
# sehingga pindah penyedia nanti tidak perlu menulis ulang logika.
GAMBAR_BASE_URL = (
    os.environ.get("GAMBAR_BASE_URL") or "https://image.pollinations.ai/prompt"
).rstrip("/")

# Ukuran default. 1024x1024 cukup tajam untuk dilihat di ponsel tanpa
# membuat pengiriman data terlalu besar.
GAMBAR_UKURAN_DEFAULT = int(os.environ.get("GAMBAR_UKURAN", "1024") or 1024)

# Batas waktu. Layanan gratis bisa antre, jadi diberi waktu cukup —
# tetapi tidak tanpa batas, supaya chat tidak menggantung selamanya.
GAMBAR_TIMEOUT_DETIK = float(os.environ.get("GAMBAR_TIMEOUT", "75") or 75)

# Batas ukuran gambar yang diterima (byte). Menjaga respons tidak
# membengkak: data URL base64 membuat ukuran naik ~33%.
GAMBAR_MAKS_BYTE = int(os.environ.get("GAMBAR_MAKS_BYTE", "6000000") or 6000000)

# Model gambar. "flux" adalah yang paling baik untuk deskripsi panjang.
GAMBAR_MODEL = os.environ.get("GAMBAR_MODEL", "flux").strip() or "flux"

# Berapa kali dicoba bila layanan gagal (ramai / timeout).
# Layanan gratis sering menolak sesaat dengan status 402/429 ketika
# sedang ramai. Karena itu percobaan dibuat beberapa kali dengan jeda
# singkat: satu gambar gagal padahal layanan hanya "penuh sebentar"
# akan terasa seperti fitur yang rusak.
GAMBAR_PERCOBAAN = max(1, int(os.environ.get("GAMBAR_PERCOBAAN", "3") or 3))

# Jeda antar percobaan (detik), dikali nomor percobaan.
GAMBAR_JEDA_DETIK = float(os.environ.get("GAMBAR_JEDA", "1.5") or 1.5)

# Penanda publik produk. Nama penyedia gambar TIDAK boleh tampil di UI.
LABEL_PUBLIK = "gungdev"

# ---------------------------------------------------------------------
# MEMOTONG TANDA AIR LAYANAN GAMBAR
# ---------------------------------------------------------------------
# Layanan gambar gratis yang dipakai SELALU menempelkan tanda air
# ("pollinations.ai") di pojok kanan bawah gambar. Parameter `nologo`
# yang dulu menghilangkannya sekarang tidak berpengaruh.
#
# Karena aplikasi ini tidak boleh menampilkan nama penyedia apa pun,
# strip bawah gambar dipotong sedikit. Nilai 6% cukup untuk membuang
# tanda air tanpa merusak komposisi gambar (bagian bawah biasanya
# lantai/latar, bukan objek utama).
PANGKAS_BAWAH = float(os.environ.get("GAMBAR_PANGKAS_BAWAH", "0.06") or 0.06)


def _pangkas_bawah(isi: bytes) -> bytes:
    """
    Memotong sebagian kecil bagian bawah gambar untuk membuang tanda air.

    Mengembalikan bytes gambar baru. Bila apa pun gagal (Pillow tidak
    terpasang, format tak dikenal), gambar ASLI dikembalikan apa adanya
    — tanda air lebih baik daripada gambar rusak atau hilang.
    """
    if PANGKAS_BAWAH <= 0:
        return isi
    try:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(isi)) as im:
            lebar, tinggi = im.size
            tinggi_baru = int(tinggi * (1 - PANGKAS_BAWAH))
            if tinggi_baru < 32 or tinggi_baru >= tinggi:
                return isi
            potong = im.crop((0, 0, lebar, tinggi_baru))
            keluaran = BytesIO()
            # JPEG kualitas 92: hampir tidak terlihat bedanya dengan asli,
            # tetapi ukurannya jauh lebih kecil daripada PNG.
            potong.convert("RGB").save(keluaran, format="JPEG", quality=92, optimize=True)
            return keluaran.getvalue()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal memangkas tanda air (gambar dipakai apa adanya): %s", exc)
        return isi

# ---------------------------------------------------------------------
# MENGENALI PERMINTAAN GAMBAR
# ---------------------------------------------------------------------
# Pendekatan: aturan kata kunci yang cukup ketat. Tujuannya bukan
# menebak sempurna, tetapi MENGHINDARI salah kira — lebih baik tidak
# membuat gambar daripada membuat gambar padahal pengguna hanya bertanya.
#
# Contoh yang HARUS dikenali:
#   "buatkan gambar kucing oranye"
#   "gambarkan pemandangan pantai"
#   "tolong buat ilustrasi logo kopi"
#   "edit gambar ini jadi gaya anime"   (dengan lampiran gambar)
#   "hapus latar belakang fotonya"
#
# Contoh yang TIDAK boleh dikenali (hanya bertanya):
#   "apa itu gambar vektor?"
#   "jelaskan cara membuat gambar dengan AI"
#   "berapa harga gambar digital?"
#   "gambaran umum ekonomi Indonesia"   <- "gambaran", bukan perintah

# Kata kerja yang menandakan PERINTAH membuat gambar.
_KATA_PERINTAH = (
    "buatkan",
    "buat",
    "bikin",
    "bikinkan",
    "gambarkan",
    "gambarin",
    "gambar",
    "ilustrasikan",
    "lukiskan",
    "desainkan",
    "desain",
    "generate",
    "hasilkan",
    "cetak",
    "render",
    "edit",
    "ubah",
    "ganti",
    "hapus",
    "hilangkan",
    "tambahkan",
)

# Kata benda objek gambar. Perintah gambar HARUS diikuti salah satunya
# (kecuali ada lampiran gambar, karena "edit jadi anime" sudah jelas).
_KATA_OBJEK = (
    "gambar",
    "foto",
    "ilustrasi",
    "lukisan",
    "poster",
    "logo",
    "banner",
    "sampul",
    "cover",
    "avatar",
    "wallpaper",
    "sketsa",
    "karikatur",
    "kartun",
    "animasi",
    "meme",
    "stiker",
    "ikon",
    "icon",
    "desain",
    "visual",
    "thumbnail",
    "pemandangan",
    "potret",
    "selfie",
    "kolase",
    "infografis",
    "3d",
)

# Frasa yang menandakan PERTANYAAN, bukan perintah. Bila ada, permintaan
# gambar dibatalkan walau mengandung kata kerja di atas.
_FRASA_TANYA = (
    "apa itu",
    "apakah",
    "jelaskan",
    "cara membuat",
    "cara buat",
    "bagaimana cara",
    "berapa",
    "kenapa",
    "mengapa",
    "perbedaan",
    "pengertian",
    "contoh gambar",
    "sebutkan",
    "definisi",
    "arti",
    "fungsi",
    "manfaat",
    "tips",
    "tutorial",
    "belajar",
    "maksud",
    "gambaran umum",
)

# Kata yang menandakan permintaan SUNGGUHAN untuk menggambar, bahkan
# tanpa kata benda objek: "gambarkan kucing", "lukiskan matahari".
_KATA_GAMBAR_KUAT = (
    "gambarkan",
    "gambarin",
    "ilustrasikan",
    "lukiskan",
    "buatkan gambar",
    "buat gambar",
    "bikin gambar",
    "bikinkan gambar",
    "generate gambar",
    "generate image",
    "buatkan ilustrasi",
    "buat ilustrasi",
    "buatkan foto",
    "buatkan poster",
    "buatkan logo",
    "desain logo",
    "buatkan desain",
)

# Permintaan menyunting gambar yang sudah ada (butuh lampiran gambar).
_KATA_SUNTING = (
    "edit",
    "ubah",
    "ganti",
    "hapus",
    "hilangkan",
    "tambahkan",
    "jadikan",
    "jadii",
    "jadikanlah",
    "beri",
    "kasih",
)


def _normalisasi(teks: str) -> str:
    """Huruf kecil, spasi dirapikan, tanda baca disederhanakan."""
    t = (teks or "").lower()
    t = re.sub(r"[^\w\s\-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _ada_kata(teks: str, daftar: Tuple[str, ...]) -> bool:
    """
    True bila salah satu frasa ada sebagai KATA UTUH.

    Penting: "gambaran" tidak boleh cocok dengan "gambar", dan "buatan"
    tidak boleh cocok dengan "buat". Karena itu dicek batas kata.
    """
    for frasa in daftar:
        pola = r"(?<![\w-])" + re.escape(frasa) + r"(?![\w-])"
        if re.search(pola, teks):
            return True
    return False


def _ada_frasa(teks: str, daftar: Tuple[str, ...]) -> bool:
    """
    True bila salah satu frasa ada, dengan BATAS KATA di kedua ujung.

    Penting: pencocokan substring biasa berbahaya. "membuat gambar"
    mengandung "buat gambar", sehingga kalimat seperti
    "jelaskan cara membuat gambar dengan AI" (hanya bertanya) akan
    salah dikira perintah menggambar lalu memakan jatah gambar.
    """
    for frasa in daftar:
        pola = r"(?<![\w-])" + re.escape(frasa) + r"(?![\w-])"
        if re.search(pola, teks):
            return True
    return False


def niat_gambar(pesan: str, ada_lampiran_gambar: bool = False) -> Dict[str, Any]:
    """
    Menentukan apakah pengguna MEMINTA gambar dibuat/disunting.

    Mengembalikan:
        {
          "buat": bool,       # True = perlu membuat gambar
          "sunting": bool,    # True = menyunting gambar yang dilampirkan
          "alasan": str,      # penjelasan singkat (untuk log/uji)
        }

    Fungsi ini SENGAJA konservatif: lebih baik melewatkan satu permintaan
    gambar daripada membuat gambar padahal pengguna hanya bertanya.
    """
    t = _normalisasi(pesan)
    hasil = {"buat": False, "sunting": False, "alasan": ""}

    if not t:
        hasil["alasan"] = "pesan kosong"
        return hasil

    # --- 1. Pertanyaan lebih dulu: jangan pernah membuat gambar ---
    if _ada_frasa(t, _FRASA_TANYA):
        # Pengecualian: "buatkan gambar X, jelaskan juga" tetap minta gambar
        # bila ada kata gambar KUAT di awal kalimat.
        if not _ada_frasa(t, _KATA_GAMBAR_KUAT):
            hasil["alasan"] = "terdeteksi pertanyaan"
            return hasil

    # --- 2. Menyunting gambar lampiran ---
    if ada_lampiran_gambar and _ada_kata(t, _KATA_SUNTING):
        hasil["sunting"] = True
        hasil["buat"] = True
        hasil["alasan"] = "menyunting gambar lampiran"
        return hasil

    # --- 3. Permintaan gambar yang jelas ---
    if _ada_frasa(t, _KATA_GAMBAR_KUAT):
        hasil["buat"] = True
        hasil["alasan"] = "frasa permintaan gambar"
        return hasil

    # --- 4. Kata perintah + kata objek gambar ---
    if _ada_kata(t, _KATA_PERINTAH) and _ada_kata(t, _KATA_OBJEK):
        hasil["buat"] = True
        hasil["alasan"] = "perintah + objek gambar"
        return hasil

    # --- 5. Lampiran gambar + permintaan sunting tanpa kata objek ---
    # Contoh: "edit gambar ini jadi hitam putih" — kata "gambar" ada,
    # tetapi bila tidak ada, tetap dikenali lewat lampiran.
    if ada_lampiran_gambar and _ada_kata(t, _KATA_SUNTING):
        hasil["sunting"] = True
        hasil["buat"] = True
        hasil["alasan"] = "suntingan pada lampiran"
        return hasil

    hasil["alasan"] = "bukan permintaan gambar"
    return hasil


# ---------------------------------------------------------------------
# MEMBUAT DESKRIPSI GAMBAR (PROMPT)
# ---------------------------------------------------------------------
# Kata-kata pembuka yang bukan bagian dari deskripsi gambar. Dibuang agar
# layanan gambar tidak "menggambar" kata "tolong buatkan".
_AWALAN_DIBUANG = (
    "tolong",
    "coba",
    "bisa",
    "bisakah",
    "minta",
    "aku",
    "saya",
    "gua",
    "gue",
    "kami",
    "buatkan",
    "bikinkan",
    "buat",
    "bikin",
    "gambarkan",
    "gambarin",
    "ilustrasikan",
    "lukiskan",
    "desainkan",
    "generate",
    "hasilkan",
    "render",
    "sebuah",
    "satu",
    "suatu",
    "dong",
    "ya",
    "yah",
    "nih",
    "gambar",
    "gambarannya",
    "foto",
    "ilustrasi",
    "lukisan",
    "sebuah gambar",
    "gambar dari",
    "gambar tentang",
    "dengan",
)

# Tambahan gaya supaya hasilnya lebih layak, tanpa mengubah permintaan.
_GAYA_BAWAAN = "high quality, detailed, sharp focus, good lighting"


def deskripsi_gambar(pesan: str, sunting: bool = False) -> str:
    """
    Mengubah pesan pengguna menjadi deskripsi gambar yang layak dipakai.

    Contoh:
        "tolong buatkan gambar kucing oranye sedang tidur di sofa"
        -> "a cat orange sleeping on a sofa, high quality, detailed"

    Catatan: deskripsi sengaja TIDAK diterjemahkan ke bahasa Inggris oleh
    model (itu akan memakan jatah chat). Layanan gambar memahami bahasa
    Indonesia dengan cukup baik, dan menerjemahkan sendiri lebih mahal
    daripada manfaatnya.
    """
    t = (pesan or "").strip()

    # Buang kalimat perintah pembuka ("tolong buatkan gambar ...").
    pola_awal = re.compile(
        r"^\s*(?:(?:" + "|".join(re.escape(k) for k in _AWALAN_DIBUANG) + r")\b[\s,]*)+",
        re.IGNORECASE,
    )
    bersih = pola_awal.sub("", t).strip(" ,.:;-\n\t")

    # Buang sisa kata yang menggantung di ujung.
    bersih = re.sub(r"\s+(?:ya|yah|dong|nih|deh)$", "", bersih, flags=re.IGNORECASE)

    if not bersih:
        bersih = t.strip() or "ilustrasi"

    # Jangan menambahkan gaya bila pengguna sudah menyebut gaya sendiri.
    sudah_ada_gaya = re.search(
        r"(gaya|style|realistis|realistic|kartun|cartoon|anime|3d|pixel|watercolor|"
        r"hitam putih|monochrome|minimalis|minimalist)",
        bersih,
        re.IGNORECASE,
    )
    if sudah_ada_gaya:
        return bersih[:900]
    return f"{bersih}, {_GAYA_BAWAAN}"[:900]


# ---------------------------------------------------------------------
# MENGAMBIL GAMBAR
# ---------------------------------------------------------------------
def _bangun_url(deskripsi: str, ukuran: int, seed: int) -> str:
    """Menyusun URL permintaan gambar."""
    prompt = urllib.parse.quote(deskripsi, safe="")
    params = {
        "width": str(ukuran),
        "height": str(ukuran),
        "seed": str(seed),
        "model": GAMBAR_MODEL,
        # Catatan: parameter "nologo" sudah TIDAK berpengaruh — layanan
        # selalu menempelkan tanda air. Karena itu tanda air dibuang
        # dengan memangkas strip bawah gambar (_pangkas_bawah).
    }
    kueri = urllib.parse.urlencode(params)
    return f"{GAMBAR_BASE_URL}/{prompt}?{kueri}"


def _tipe_gambar(content_type: str, isi: bytes) -> str:
    """Menentukan MIME gambar dari header atau tanda awal berkas."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
        return "image/jpeg" if ct == "image/jpg" else ct
    if isi[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if isi[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if isi[:4] == b"RIFF" and isi[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


async def buat_gambar(
    deskripsi: str,
    ukuran: Optional[int] = None,
    seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Mengambil satu gambar dari layanan gambar gratis.

    Mengembalikan (TIDAK PERNAH melempar exception):
        {"ok": True,  "data_url": "data:image/jpeg;base64,...", "deskripsi": "..."}
        {"ok": False, "pesan": "alasan singkat untuk pengguna", "galat": "..."}

    Penting: kegagalan di sini TIDAK boleh menggagalkan chat. Pemanggil
    tetap menjawab dengan teks biasa bila `ok` bernilai False.
    """
    bersih = (deskripsi or "").strip()
    if not bersih:
        return {"ok": False, "pesan": "Deskripsi gambarnya belum jelas.", "galat": "kosong"}

    ukuran = ukuran or GAMBAR_UKURAN_DEFAULT
    # Seed tetap membuat hasil bisa diulang (mis. saat regenerasi),
    # tetapi berbeda untuk setiap deskripsi.
    if seed is None:
        seed = abs(hash(bersih)) % 2_000_000

    galat_terakhir = ""
    for percobaan in range(GAMBAR_PERCOBAAN):
        # Jeda makin panjang tiap percobaan, memberi waktu layanan reda.
        if percobaan > 0:
            await asyncio.sleep(GAMBAR_JEDA_DETIK * percobaan)

        url = _bangun_url(bersih, ukuran, seed + percobaan)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(GAMBAR_TIMEOUT_DETIK, connect=15.0),
                follow_redirects=True,
            ) as klien:
                resp = await klien.get(url)

            if resp.status_code != 200:
                galat_terakhir = f"status {resp.status_code}"
                logger.warning(
                    "Gambar gagal (percobaan %s/%s): %s",
                    percobaan + 1,
                    GAMBAR_PERCOBAAN,
                    galat_terakhir,
                )
                continue

            isi = resp.content or b""
            if not isi:
                galat_terakhir = "isi kosong"
                continue
            if len(isi) > GAMBAR_MAKS_BYTE:
                galat_terakhir = "gambar terlalu besar"
                continue

            tipe = _tipe_gambar(resp.headers.get("content-type", ""), isi)
            # Pastikan yang diterima benar-benar gambar, bukan halaman galat.
            if tipe == "image/jpeg" and isi[:3] != b"\xff\xd8\xff":
                galat_terakhir = "bukan berkas gambar"
                continue

            # Buang tanda air layanan gambar (lihat _pangkas_bawah).
            isi = _pangkas_bawah(isi)
            # Pemangkasan menghasilkan JPEG, jadi tipenya ikut menyesuaikan.
            tipe = _tipe_gambar("", isi)

            b64 = base64.b64encode(isi).decode("ascii")
            return {
                "ok": True,
                "data_url": f"data:{tipe};base64,{b64}",
                "deskripsi": bersih,
            }

        except httpx.TimeoutException:
            galat_terakhir = "waktu habis"
        except Exception as exc:  # noqa: BLE001
            galat_terakhir = type(exc).__name__
            logger.warning("Gambar gagal (percobaan %s): %s", percobaan + 1, exc)

    return {
        "ok": False,
        "pesan": (
            "Gambar belum berhasil dibuat karena layanan gambar sedang ramai. "
            "Coba lagi sebentar lagi ya."
        ),
        "galat": galat_terakhir,
    }


# ---------------------------------------------------------------------
# PESAN UNTUK PENGGUNA
# ---------------------------------------------------------------------
def pesan_berhasil(deskripsi: str) -> str:
    """
    Teks pendamping gambar.

    Sengaja singkat dan tenang: pengguna sudah melihat gambarnya, jadi
    tidak perlu penjelasan panjang. Nama penyedia gambar TIDAK disebut.
    """
    return (
        "Ini gambar yang Anda minta. Klik gambarnya bila ingin melihat "
        "lebih besar atau menyimpannya.\n\n"
        f"Deskripsi: {deskripsi}"
    )


def pesan_tidak_tersedia() -> str:
    """Dipakai bila layanan gambar tidak bisa dipakai sama sekali."""
    return (
        "Gambar belum bisa dibuat saat ini. Anda tetap bisa memakai obrolan "
        "seperti biasa, dan bisa mencoba membuat gambar lagi nanti."
    )


def ringkas_untuk_meta(hasil: Dict[str, Any]) -> Dict[str, Any]:
    """
    Bentuk ringkas untuk dikirim ke UI (tanpa data gambar).

    `url` sengaja diisi penanda internal: UI hanya memakai ini untuk
    tombol unduh, bukan untuk memuat gambar (gambarnya sudah ada di
    `data_url`). Nama penyedia tidak pernah ikut terkirim.
    """
    return {
        "deskripsi": hasil.get("deskripsi", ""),
        "label": LABEL_PUBLIK,
    }


def daftar_kemampuan() -> Dict[str, Any]:
    """Info kemampuan gambar untuk /capabilities (aman ditampilkan)."""
    return {
        # Kemampuan MEMBUAT gambar (berbeda dari `vision` = membaca gambar).
        "buat_gambar": True,
        "ukuran": GAMBAR_UKURAN_DEFAULT,
        "gratis": True,
    }
