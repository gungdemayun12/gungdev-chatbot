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
#
# CATATAN PENTING (Vercel): batas `maxDuration` fungsi serverless adalah
# 60 detik (lihat vercel.json). Nilai di sini HARUS lebih kecil dari itu,
# kalau tidak Vercel memutus koneksi lebih dulu dan pengguna melihat
# galat alih-alih pesan yang jelas. Karena itu 52 detik, bukan 75.
GAMBAR_TIMEOUT_DETIK = float(os.environ.get("GAMBAR_TIMEOUT", "52") or 52)

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
# TANDA AIR: MILIK GUNGDEV SENDIRI
# ---------------------------------------------------------------------
# Layanan gambar gratis yang dipakai SELALU menempelkan tanda air
# layanannya ("pollinations.ai") di pojok kanan bawah, dan parameter
# `nologo` sudah tidak berpengaruh. Karena aplikasi ini tidak boleh
# menampilkan nama penyedia, tanda air itu harus dibuang.
#
# Dua langkah, sengaja dipisah supaya kalau satu gagal yang lain tetap
# jalan:
#
#   1. PANGKAS — potong strip bawah. Inilah satu-satunya cara
#      MENGHILANGKAN tanda air layanan yang sudah menyatu di piksel.
#   2. WATERMARK — gambar tanda air "gungdev" sendiri di pojok kanan
#      bawah, supaya hasilnya tetap terasa milik aplikasi ini.
#
# Kalau pemangkasan dihilangkan, tanda air penyedia akan tetap terlihat
# dan menimpa area yang sama dengan watermark gungdev. Jadi jangan
# matikan pemangkasan kecuali penyedia gambarnya sudah berganti.

# Porsi tinggi gambar yang dipotong dari bawah (0.06 = 6%).
# 6% cukup untuk membuang tanda air layanan tanpa memotong objek utama:
# pada gambar 1024 px itu hanya ~61 px, biasanya area lantai/latar.
PANGKAS_BAWAH = float(os.environ.get("GAMBAR_PANGKAS_BAWAH", "0.06") or 0.06)

# Teks tanda air milik aplikasi. Nama penyedia TIDAK boleh muncul di sini.
WATERMARK_TEKS = os.environ.get("GAMBAR_WATERMARK", "").strip() or LABEL_PUBLIK

# Porsi tinggi gambar yang dipakai sebagai tinggi huruf watermark.
WATERMARK_UKURAN = float(os.environ.get("GAMBAR_WATERMARK_UKURAN", "0.032") or 0.032)

# 0 = matikan watermark gungdev (tanda air layanan tetap dibuang).
WATERMARK_AKTIF = (os.environ.get("GAMBAR_WATERMARK_AKTIF", "1") or "1") not in (
    "0",
    "false",
    "no",
)

# Huruf TrueType yang dicoba berurutan. Di Vercel (Linux) biasanya tidak
# ada berkas font sama sekali, jadi daftar ini kemungkinan besar gagal
# semua di produksi — karena itu ada cadangan huruf bawaan Pillow.
_FONT_CALON = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "C:/Windows/Fonts/segoeuib.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/segoeui.ttf",
    "C:/Windows/Fonts/arial.ttf",
)


def _font_watermark(ukuran_px: int):
    """
    Membuka huruf untuk watermark; None bila tidak ada font TrueType.

    Pemanggil harus siap menerima None: Pillow punya huruf bawaan yang
    bisa dipakai, hanya bentuknya lebih kecil dan kurang rapi.
    """
    try:
        from PIL import ImageFont
    except Exception:  # noqa: BLE001
        return None

    for jalur in _FONT_CALON:
        try:
            if os.path.exists(jalur):
                return ImageFont.truetype(jalur, ukuran_px)
        except Exception:  # noqa: BLE001
            continue

    # Cadangan: huruf bawaan Pillow. Ukurannya tidak bisa diatur, jadi
    # hasilnya lebih kecil — masih lebih baik daripada tanpa watermark.
    try:
        return ImageFont.load_default()
    except Exception:  # noqa: BLE001
        return None


def _pangkas_bawah(isi: bytes) -> bytes:
    """
    Memotong sebagian kecil bagian bawah gambar untuk membuang tanda air
    layanan gambar.

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


def _gambar_watermark(isi: bytes) -> bytes:
    """
    Menambahkan tanda air "gungdev" di pojok kanan bawah gambar.

    Bentuknya sengaja tenang, bukan mencolok:
      - teks kecil berwarna putih dengan bayangan gelap tipis, supaya
        tetap terbaca di latar terang maupun gelap;
      - ada satu titik aksen kecil di kiri teks sebagai penanda merek;
      - letaknya di pojok bawah, tidak menutupi objek utama.

    Mengembalikan bytes gambar. Bila gagal (Pillow tidak ada, format tak
    dikenal), gambar ASLI dikembalikan apa adanya — watermark tidak
    boleh membuat gambar hilang.
    """
    if not WATERMARK_AKTIF or not WATERMARK_TEKS:
        return isi
    try:
        from io import BytesIO

        from PIL import Image, ImageDraw

        with Image.open(BytesIO(isi)) as im:
            gambar = im.convert("RGB")
            lebar, tinggi = gambar.size

            ukuran = max(11, int(tinggi * WATERMARK_UKURAN))
            font = _font_watermark(ukuran)

            # Lapisan transparan supaya teks bisa semi-transparan tanpa
            # mengubah warna gambar di sekitarnya.
            lapisan = Image.new("RGBA", gambar.size, (0, 0, 0, 0))
            pena = ImageDraw.Draw(lapisan)

            teks = WATERMARK_TEKS
            try:
                kotak = pena.textbbox((0, 0), teks, font=font)
                lebar_teks = kotak[2] - kotak[0]
                tinggi_teks = kotak[3] - kotak[1]
            except Exception:  # noqa: BLE001
                lebar_teks = len(teks) * ukuran // 2
                tinggi_teks = ukuran

            # Jarak tepi mengikuti ukuran gambar, jadi proporsional di
            # gambar 512 px maupun 1024 px.
            tepi = max(10, int(tinggi * 0.022))
            # Titik merek + jarak, lalu teks.
            diameter_titik = max(4, int(tinggi_teks * 0.34))
            jarak_titik = max(6, int(tinggi_teks * 0.42))
            lebar_total = diameter_titik + jarak_titik + lebar_teks

            x_kanan = lebar - tepi
            x_awal = x_kanan - lebar_total
            y_teks = tinggi - tepi - tinggi_teks - max(1, int(tinggi * 0.004))

            # Bayangan gelap tipis: digambar 1 px bergeser, membuat teks
            # tetap terbaca di latar terang (mis. sofa putih).
            geser = max(1, ukuran // 12)
            pena.text(
                (x_awal + diameter_titik + jarak_titik + geser, y_teks + geser),
                teks,
                font=font,
                fill=(0, 0, 0, 120),
            )
            pena.text(
                (x_awal + diameter_titik + jarak_titik, y_teks),
                teks,
                font=font,
                fill=(255, 255, 255, 235),
            )

            # Titik aksen merek, sejajar garis dasar teks.
            tengah_titik_y = y_teks + tinggi_teks // 2
            pena.ellipse(
                (
                    x_awal,
                    tengah_titik_y - diameter_titik // 2,
                    x_awal + diameter_titik,
                    tengah_titik_y + diameter_titik // 2,
                ),
                fill=(255, 255, 255, 235),
            )

            hasil = Image.alpha_composite(gambar.convert("RGBA"), lapisan).convert("RGB")
            keluaran = BytesIO()
            hasil.save(keluaran, format="JPEG", quality=92, optimize=True)
            keluaran_bytes = keluaran.getvalue()

            # Jangan biarkan watermark membuat gambar membengkak.
            if len(keluaran_bytes) > len(isi) * 3:
                return isi
            return keluaran_bytes
    except Exception as exc:  # noqa: BLE001
        logger.warning("Gagal menambahkan watermark (gambar dipakai apa adanya): %s", exc)
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

# ---------------------------------------------------------------------
# MENERJEMAHKAN PERMINTAAN KE BAHASA INGGRIS
# ---------------------------------------------------------------------
# MENGAPA INI PERLU — kasus nyata:
#   "buatkan gambar kucing sedang tidur di sofa"
#   model gambar menghasilkan kucing BERDIRI di sofa.
#
# Penyebabnya bukan modelnya "bodoh", tetapi deskripsi bahasa Indonesia
# terlalu samar bagi model gambar (yang dilatih dengan bahasa Inggris).
# Kata "sedang tidur" sebagai frasa tidak dikenali; model hanya menangkap
# "kucing" dan "sofa", lalu memakai pose bawaannya: duduk/berdiri.
#
# Perbaikannya: kata POSE (dan warna, jenis objek, latar) diterjemahkan
# ke istilah Inggris yang tegas. Contoh hasil:
#   "an orange tabby cat lying down asleep on a sofa, curled up,
#    eyes closed, relaxed pose, photo, realistic, natural lighting"
#
# Model lalu punya kata kunci yang tidak bisa disalahtafsirkan: "lying
# down", "asleep", "curled up", "eyes closed".
#
# Kamus ini SENGAJA sederhana dan tidak lengkap — ia hanya menangani kata
# yang sering muncul dalam permintaan gambar sehari-hari. Kata yang tidak
# ada di kamus dibiarkan apa adanya (tidak dihapus), jadi permintaan
# tetap utuh meskipun sebagian tidak diterjemahkan.

# Pose/keadaan. Daftar ini yang paling menentukan hasil benar atau tidak.
_KAMUS_POSE = {
    "sedang tidur": "lying down asleep, eyes closed",
    "sedang tertidur": "lying down asleep, eyes closed",
    "tertidur": "lying down asleep, eyes closed",
    "tidur": "lying down asleep, eyes closed",
    "tidur nyenyak": "sleeping deeply, eyes closed, relaxed",
    "berbaring": "lying down",
    "terbaring": "lying down",
    "duduk": "sitting",
    "berdiri": "standing",
    "jongkok": "squatting, crouching",
    "berlari": "running, motion",
    "berjalan": "walking",
    "berdiri diam": "standing still",
    "berlari kencang": "running fast, dynamic motion",
    "melompat": "jumping, mid air",
    "terbang": "flying",
    "berenang": "swimming",
    "makan": "eating",
    "minum": "drinking",
    "tersenyum": "smiling",
    "tersenyum lebar": "smiling broadly, happy expression",
    "tertawa": "laughing, joyous expression",
    "menangis": "crying, tears",
    "melihat kamera": "looking at camera",
    "menatap kamera": "looking directly at camera",
    "menghadap kamera": "facing camera",
    "berpelukan": "hugging",
    "memegang": "holding",
    "membaca": "reading",
    "menulis": "writing",
    "bermain": "playing",
    "berdoa": "praying",
    "berdiri tegak": "standing upright",
    "membelakangi": "seen from behind",
    "dari samping": "side view",
    "dari atas": "top view, overhead angle",
    "close up": "close up shot",
    "potret": "portrait",
}

# Warna.
_KAMUS_WARNA = {
    "oranye": "orange",
    "jingga": "orange",
    "merah": "red",
    "merah muda": "pink",
    "biru": "blue",
    "biru muda": "light blue",
    "biru tua": "dark blue",
    "hijau": "green",
    "hijau muda": "light green",
    "kuning": "yellow",
    "emas": "golden",
    "keemasan": "golden",
    "ungu": "purple",
    "coklat": "brown",
    "cokelat": "brown",
    "hitam": "black",
    "putih": "white",
    "abu abu": "grey",
    "abu-abu": "grey",
    "kelabu": "grey",
    "pink": "pink",
    "toska": "turquoise",
    "krem": "cream",
    "perak": "silver",
    "transparan": "transparent",
}

# Hewan & objek yang sering diminta.
_KAMUS_OBJEK = {
    "kucing": "cat",
    "anak kucing": "kitten",
    "anjing": "dog",
    "anak anjing": "puppy",
    "burung": "bird",
    "ikan": "fish",
    "kuda": "horse",
    "sapi": "cow",
    "kambing": "goat",
    "ayam": "chicken",
    "bebek": "duck",
    "kelinci": "rabbit",
    "harimau": "tiger",
    "singa": "lion",
    "gajah": "elephant",
    "monyet": "monkey",
    "panda": "panda",
    "serigala": "wolf",
    "rusa": "deer",
    "kupu kupu": "butterfly",
    "kupu-kupu": "butterfly",
    "lebah": "bee",
    "naga": "dragon",
    "dinosaurus": "dinosaur",
    "manusia": "human",
    "orang": "person",
    "anak": "child",
    "anak anak": "children",
    "perempuan": "woman",
    "wanita": "woman",
    "laki laki": "man",
    "pria": "man",
    "keluarga": "family",
    "sepasang kekasih": "couple in love",
    "rumah": "house",
    "mobil": "car",
    "motor": "motorcycle",
    "sepeda": "bicycle",
    "pesawat": "airplane",
    "kapal": "ship",
    "kereta": "train",
    "pohon": "tree",
    "bunga": "flower",
    "bunga matahari": "sunflower",
    "gunung": "mountain",
    "pantai": "beach",
    "laut": "sea",
    "danau": "lake",
    "sungai": "river",
    "hutan": "forest",
    "sawah": "rice field",
    "sawah hijau": "green rice terrace",
    "kota": "city",
    "desa": "village",
    "kamar": "bedroom",
    "dapur": "kitchen",
    "ruang tamu": "living room",
    "sofa": "sofa",
    "kursi": "chair",
    "meja": "table",
    "tempat tidur": "bed",
    "kasur": "bed",
    "bantal": "pillow",
    "selimut": "blanket",
    "jendela": "window",
    "pintu": "door",
    "buku": "book",
    "kopi": "coffee",
    "kue": "cake",
    "roti": "bread",
    "nasi": "rice",
    "buah": "fruit",
    "apel": "apple",
    "pisang": "banana",
    "makanan": "food",
    "minuman": "drink",
    "botol": "bottle",
    "gelas": "glass",
    "cangkir": "cup",
    "tas": "bag",
    "sepatu": "shoes",
    "baju": "shirt",
    "gaun": "dress",
    "topi": "hat",
    "kacamata": "glasses",
    "jam tangan": "wristwatch",
    "ponsel": "smartphone",
    "laptop": "laptop",
    "komputer": "computer",
    "robot": "robot",
    "roket": "rocket",
    "bintang": "stars",
    "bulan": "moon",
    "matahari": "sun",
    "matahari terbenam": "sunset",
    "matahari terbit": "sunrise",
    "awan": "clouds",
    "hujan": "rain",
    "salju": "snow",
    "pelangi": "rainbow",
    "api": "fire",
    "air": "water",
    "air terjun": "waterfall",
    "logo": "logo",
    "poster": "poster",
    "banner": "banner",
    "sampul": "book cover",
    "stiker": "sticker",
    "ikon": "icon",
    "maskot": "mascot",
    "karakter": "character",
    "desain": "design",
    "pemandangan": "landscape scenery",
    "pemandangan alam": "natural landscape",
    "konser": "concert",
    "musik": "music",
    "gedung": "building",
    "sekolah": "school",
    "masjid": "mosque",
    "gereja": "church",
    "pura": "temple",
    "jembatan": "bridge",
    "lapangan": "field",
    "kota besar": "big city skyline",
    "malam": "night",
    "siang": "day",
    "pagi": "morning",
    "sore": "afternoon",
    "cangkir kopi": "cup of coffee",
    "secangkir kopi": "cup of coffee",
    "es krim": "ice cream",
    "pizza": "pizza",
    "burger": "burger",
    "sate": "satay skewers",
    "rendang": "rendang dish",
    "nasi goreng": "fried rice",
    "bakso": "meatball soup",
    "keripik": "chips",
    "sayur": "vegetables",
}

# Latar & suasana.
_KAMUS_LATAR = {
    "di dalam": "indoors",
    "di luar": "outdoors",
    "di kamar": "in a bedroom",
    "di taman": "in a garden",
    "di jalan": "on a street",
    "di pantai": "at the beach",
    "saat matahari terbenam": "at sunset, golden hour",
    "saat matahari terbit": "at sunrise",
    "malam hari": "at night",
    "siang hari": "during the day",
    "pagi hari": "in the morning",
    "sore hari": "in the afternoon",
    "suasana hujan": "in the rain",
    "latar belakang putih": "plain white background",
    "latar putih": "plain white background",
    "latar hitam": "plain black background",
    "latar polos": "plain background",
}

# Gaya visual. Bila pengguna menyebut gaya, gaya itulah yang dipakai
# dan gaya bawaan TIDAK ditambahkan.
_KAMUS_GAYA = {
    "realistis": "photorealistic, realistic photo",
    "fotorealistis": "photorealistic, realistic photo",
    "kartun": "cartoon style, cel shaded",
    "kartun lucu": "cute cartoon style",
    "anime": "anime style, japanese animation",
    "manga": "manga style, black and white ink",
    "ilustrasi": "illustration",
    "lukisan": "painting, painterly",
    "cat air": "watercolor painting",
    "cat minyak": "oil painting",
    "sketsa": "pencil sketch, hand drawn",
    "pensil": "pencil drawing",
    "3d": "3d render, octane render",
    "3d render": "3d render, octane render",
    "pixel": "pixel art, 8-bit",
    "pixel art": "pixel art, 8-bit",
    "minimalis": "minimalist, clean design",
    "vintage": "vintage, retro film look",
    "retro": "retro style",
    "cyberpunk": "cyberpunk, neon lights",
    "fantasi": "fantasy art, epic",
    "kartun 2d": "2d cartoon animation",
    "hitam putih": "black and white, monochrome",
    "monokrom": "monochrome",
    "grafis": "graphic design",
    "vektor": "vector illustration, flat design",
    "flat": "flat design, vector",
    "cinematic": "cinematic lighting, movie still",
    "sinematik": "cinematic lighting, movie still",
}

# Gaya bawaan untuk FOTO. Ditambahkan HANYA bila pengguna tidak memilih
# gaya sendiri. Kata-kata ini menaikkan mutu hasil secara nyata:
# pencahayaan disebut, detail disebut, dan "no text" mencegah model
# menuliskan huruf acak di dalam gambar.
_GAYA_FOTO = (
    "highly detailed, sharp focus, professional photography, "
    "natural soft lighting, shallow depth of field, 8k"
)

# Penegasan negatif. Banyak model gambar gratis memahaminya sebagai
# bagian kalimat; ini mengurangi hasil aneh (anatomi salah, teks acak).
_NEGATIF = "no text, no watermark, no distorted anatomy, no extra limbs"

# Kata sambung & kata umum yang tidak perlu diterjemahkan (sudah berupa
# kata Inggris atau memang dibiarkan).
_LEWATI = {
    "di",
    "ke",
    "dari",
    "yang",
    "dan",
    "atau",
    "dengan",
    "untuk",
    "pada",
    "dalam",
    "sebuah",
    "seekor",
    "satu",
    "para",
    "itu",
    "ini",
    "sedang",
    "sambil",
    "bersama",
    "lucu",
    "imut",
    "cantik",
    "indah",
    "bagus",
    "keren",
    "besar",
    "kecil",
    "tinggi",
    "panjang",
    "pendek",
    "baru",
    "tua",
    "muda",
    "gemuk",
    "kurus",
    "sangat",
    "sekali",
    "agak",
    "paling",
    "lebih",
    "mirip",
    "seperti",
    "gaya",
    "bertema",
    "nuansa",
    "suasana",
    "alas",
    "bentuk",
    "ukuran",
    "warna",
    "tema",
    "aksen",
    "latar",
    "a",
    "an",
    "the",
    "of",
    "in",
    "on",
    "at",
    "with",
    "and",
}

# Kata sambung Indonesia yang diterjemahkan ke padanan Inggris yang
# sederhana. Tanpa ini, "kucing tidur di sofa" menjadi
# "cat lying down asleep di sofa" — kata "di" menggantung dan model
# gambar bisa mengabaikan seluruh bagian "di sofa".
_SAMBUNG = {
    "di": "on",
    "ke": "to",
    "dari": "from",
    "dan": "and",
    "atau": "or",
    "dengan": "with",
    "untuk": "for",
    "pada": "on",
    "dalam": "in",
    "sambil": "while",
    "bersama": "together",
    "lucu": "cute",
    "imut": "adorable",
    "cantik": "beautiful",
    "indah": "scenic",
    "bagus": "beautiful",
    "keren": "cool",
    "besar": "large",
    "kecil": "small",
    "tinggi": "tall",
    "panjang": "long",
    "pendek": "short",
    "baru": "new",
    "tua": "old",
    "muda": "young",
    "gemuk": "chubby",
    "kurus": "slim",
    "sangat": "very",
    "agak": "slightly",
    "lebih": "more",
    "mirip": "similar to",
    "seperti": "like",
    "gaya": "style",
    "bertema": "themed",
    "nuansa": "mood",
    "suasana": "atmosphere",
    "bentuk": "shape",
    "warna": "color",
    "tema": "theme",
    "latar": "background",
    "sebuah": "",
    "seekor": "",
    "satu": "",
    "para": "",
    "itu": "",
    "ini": "",
    "sedang": "",
    "yang": "",
    "sekali": "",
}


def _terjemah_kamus(teks: str, kamus: Dict[str, str]) -> Tuple[str, List[str]]:
    """
    Mengganti frasa Indonesia dengan padanan Inggrisnya.

    Frasa TERPANJANG dicoba lebih dulu, supaya "anak kucing" menjadi
    "kitten" (bukan "child" + "cat"), dan "matahari terbenam" menjadi
    "sunset" (bukan "sun" + sesuatu).

    Mengembalikan (teks_hasil, daftar_padanan_unik).
    """
    hasil = teks
    dipakai: List[str] = []
    for indo in sorted(kamus, key=len, reverse=True):
        inggris = kamus[indo]
        pola = r"(?<![\w-])" + re.escape(indo) + r"(?![\w-])"
        if re.search(pola, hasil):
            hasil = re.sub(pola, inggris, hasil)
            dipakai.append(inggris)
    return hasil, dipakai


def _beri_awalan(kerja: str) -> str:
    """
    Memberi awalan yang membuat deskripsi terbaca sebagai frasa benda.

    Model gambar dilatih dengan deskripsi seperti "a photo of an orange
    cat sleeping on a sofa". Daftar kata lepas ("cat orange lying down
    asleep on sofa") masih bekerja, tetapi hasilnya kurang tepat.

    Fungsi ini SENGAJA sederhana: ia hanya menambah "a photo of" dan
    artikel "a"/"an" di depan kata benda pertama, tidak menyusun ulang
    kalimat. Bila tidak yakin, teks dibiarkan apa adanya — deskripsi yang
    kurang rapi tetap jauh lebih baik daripada deskripsi yang salah.
    """
    if not kerja:
        return kerja

    teks = kerja.strip()
    awal = teks.lower()

    # Sudah berupa frasa yang utuh? Jangan diubah.
    if re.match(r"^(a|an|the|photo|picture|portrait|illustration|design|logo)\b", awal):
        return teks
    if awal.startswith(("edit", "close up", "side view", "top view")):
        return teks

    # Kata pertama harus kata benda yang dikenal. Kalau tidak, biarkan:
    # menambahkan "a" di depan kata yang salah justru merusak.
    kata_pertama = re.split(r"[\s,]", teks, maxsplit=1)[0].lower()
    benda = set(_KAMUS_OBJEK.values())

    # Kata sifat warna di depan kata benda ("orange cat") diperbolehkan:
    # cari kata benda pertama dalam dua kata awal.
    dua_awal = re.split(r"[\s,]+", teks)[:2]
    ada_benda = any(k.lower() in benda for k in dua_awal)

    if kata_pertama in benda:
        artikel = "an" if kata_pertama[0] in "aeiou" else "a"
        return f"{artikel} {teks}"
    if ada_benda:
        # Contoh: "orange cat ..." -> "an orange cat ..."
        return f"a photo of {teks}"
    return teks


def deskripsi_gambar(pesan: str, sunting: bool = False) -> str:
    """
    Mengubah pesan pengguna menjadi deskripsi gambar yang layak dipakai.

    Contoh:
        "tolong buatkan gambar kucing sedang tidur di sofa"
        -> "orange tabby cat lying down asleep, eyes closed on a sofa,
            highly detailed, sharp focus, professional photography..."

    MENGAPA DITERJEMAHKAN — ini perbaikan penting, bukan hiasan:
    model gambar memahami bahasa Inggris jauh lebih tepat. Tanpa
    terjemahan, "sedang tidur" tidak dikenali dan model memakai pose
    bawaannya (duduk/berdiri), sehingga permintaan "kucing tidur"
    menghasilkan kucing berdiri.

    Gaya: bila pengguna menyebut gaya sendiri ("gaya anime", "kartun"),
    gaya itulah yang dipakai dan gaya foto bawaan tidak ditambahkan.
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

    # --- Terjemahkan ke Inggris (frasa pose paling menentukan) ---
    asli = bersih.lower()
    kerja = asli

    kerja, _ = _terjemah_kamus(kerja, _KAMUS_GAYA)
    kerja, _ = _terjemah_kamus(kerja, _KAMUS_POSE)
    kerja, _ = _terjemah_kamus(kerja, _KAMUS_LATAR)
    kerja, _ = _terjemah_kamus(kerja, _KAMUS_OBJEK)
    kerja, _ = _terjemah_kamus(kerja, _KAMUS_WARNA)
    # Kata sambung & kata sifat diterjemahkan SETELAH kata benda, supaya
    # "di sofa" tidak berubah sebelum "sofa" sempat dikenali.
    kerja, _ = _terjemah_kamus(kerja, _SAMBUNG)

    # Rapikan: buang kata sambung yang menggantung, spasi ganda, dan koma
    # berlebih. Kata yang tidak dikenal TETAP dibiarkan, supaya permintaan
    # tidak pernah "hilang" hanya karena tidak ada di kamus.
    potongan: List[str] = []
    for bagian in re.split(r"\s*,\s*", kerja):
        if not bagian.strip():
            continue
        kata = bagian.strip()
        if kata.lower() in _LEWATI:
            continue
        potongan.append(kata)
    kerja = ", ".join(potongan).strip(" ,")
    kerja = re.sub(r"\s{2,}", " ", kerja).strip()

    if not kerja:
        kerja = bersih

    # Awalan "a"/"an" membuat deskripsi terbaca sebagai frasa benda yang
    # wajar — model gambar menanggapinya lebih baik daripada daftar kata
    # lepas ("cat orange lying down" lebih lemah daripada
    # "a photo of an orange cat lying down").
    kerja = _beri_awalan(kerja)

    # --- Apakah pengguna memilih gaya sendiri? ---
    pilihan_gaya = re.search(
        r"(gaya|style|realistis|realistic|kartun|cartoon|anime|manga|3d|pixel|"
        r"watercolor|cat air|lukisan|sketsa|hitam putih|monochrome|minimalis|"
        r"minimalist|vintage|retro|cyberpunk|fantasi|vektor|vector|ilustrasi|"
        r"illustration|cinematic|sinematik)",
        asli,
    )

    if sunting:
        # Untuk menyunting gambar, hasil "foto" bawaan tidak perlu:
        # yang penting perubahannya jelas dan gambar aslinya dihormati.
        inti = f"edit this image: {kerja}" if not kerja.lower().startswith("edit") else kerja
        return f"{inti}, keep composition, {_NEGATIF}"[:900]

    if pilihan_gaya:
        # Gaya pilihan pengguna dihormati; jangan ditimpa gaya foto.
        return f"{kerja}, {_NEGATIF}"[:900]

    return f"{kerja}, {_GAYA_FOTO}, {_NEGATIF}"[:900]


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
        # `enhance` menyuruh layanan memperbaiki prompt dan menambah
        # detail. Hasilnya lebih bagus untuk deskripsi panjang, dengan
        # biaya waktu tunggu sedikit lebih lama — itu wajar.
        "enhance": "true",
        # Catatan: parameter "nologo" sudah TIDAK berpengaruh — layanan
        # selalu menempelkan tanda air. Karena itu tanda air dibuang
        # dengan memangkas strip bawah (_pangkas_bawah), lalu diganti
        # tanda air milik aplikasi (_gambar_watermark).
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

            # Buang tanda air layanan gambar, lalu ganti dengan tanda air
            # milik aplikasi ini ("gungdev"). Dua langkah terpisah:
            # pemangkasan membuang milik penyedia, watermark menambahkan
            # milik kita.
            isi = _pangkas_bawah(isi)
            isi = _gambar_watermark(isi)
            # Kedua langkah menghasilkan JPEG, jadi tipenya ikut menyesuaikan.
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
