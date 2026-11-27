"""
riset.py — riset web NYATA yang bekerja untuk SEMUA model & penyedia.

KENAPA MODUL INI ADA
--------------------
Sebelumnya riset web hanya bisa dilakukan model yang didukung tool
`browser_search` milik Groq (keluarga GPT-OSS). Akibatnya, memilih
model lain membuat permintaan riset "dilempar" ke model berbeda, dan
model OpenRouter sama sekali tidak bisa riset.

Pemilik situs ingin SEMUA model punya kemampuan yang sama, tanpa
pengguna perlu berganti model. Jadi riset dikerjakan DI SINI, di
server, dengan alur yang sama untuk semua penyedia:

    1. Model merumuskan kata kunci pencarian dari permintaan pengguna.
    2. Server mencari sumber dan membaca isinya.
    3. Isi sumber dikirim balik ke model sebagai konteks.
    4. Model menulis jawaban sambil menyebut sumbernya.

SUMBER YANG DIPAKAI (semua terbuka, tanpa API key, tanpa biaya)
---------------------------------------------------------------
1. Wikipedia (id + en) lewat API resmi — paling andal & stabil, karena
   memang disediakan untuk pemakaian program. Terbukti bekerja.
2. Bing (HTML) sebagai pelengkap berita/opini yang mungkin belum ada
   di Wikipedia.
3. Pembacaan langsung URL yang muncul pada hasil pencarian.

CATATAN PENTING TENTANG MESIN PENCARI
-------------------------------------
DuckDuckGo, SearXNG publik, dan Mojeek TERBUKTI gagal/diblokir saat
diuji (sertifikat tidak valid, HTTP 429, atau halaman kosong). Bing
pun bisa menyajikan halaman sampah bila mendeteksi bot. Karena itu
Wikipedia dijadikan sumber UTAMA, dan mesin pencari hanya pelengkap.
Modul ini dirancang agar tetap berguna walau mesin pencari memblokir:
lebih baik riset dari sumber ensiklopedia daripada tidak sama sekali.

PRINSIP
-------
1. TIDAK PERNAH menggagalkan chat. Semua kegagalan ditelan dan dicatat
   di log; chat tetap jalan dengan jawaban jujur dari model.
2. TIDAK butuh rahasia baru (tanpa API key pencarian).
3. Selalu menyebut sumber (URL) agar pengguna bisa memeriksa sendiri.
4. Anti-SSRF: hanya http/https dan alamat publik.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import logging
import re
import socket
from typing import List, Optional
from urllib.parse import quote, quote_plus, urlparse

import httpx

logger = logging.getLogger("gungdev-riset")

# Batas waktu & ukuran: serverless punya batas waktu, dan konteks yang
# terlalu panjang justru mengaburkan jawaban.
MAKS_SUMBER = 4
MAKS_KARAKTER_SUMBER = 1800
MAKS_KARAKTER_TOTAL = 7000
TIMEOUT_CARI = 10.0
TIMEOUT_BACA = 9.0
BAHASA_WIKI = ("id", "en")

# Wikimedia MENOLAK User-Agent generik tanpa info kontak (kebijakan
# robot resmi mereka). UA ini sengaja memuat nama aplikasi + kontak
# situs, sebagaimana diminta: https://w.wiki/4wJS
UA_WIKI = (
    "GungDev/2.0 (https://gungdev-chatbot-ai.vercel.app; admin@gungdev.ai) "
    "httpx/0.27"
)
UA_BROWSER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


# ---------------------------------------------------------------------
# KEAMANAN: hanya alamat publik (anti-SSRF)
# ---------------------------------------------------------------------
def _alamat_privat(host: str) -> bool:
    """
    True bila host menunjuk ke jaringan lokal/privat.

    Mencegah pengguna memaksa server membaca `http://localhost:8000`
    atau `http://169.254.169.254` (metadata cloud).
    """
    if not host:
        return True
    nama = host.strip("[]").lower()
    if nama in ("localhost", "localhost.localdomain") or nama.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(nama)
        return (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        )
    except ValueError:
        pass
    try:
        for info in socket.getaddrinfo(nama, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
    except (socket.gaierror, ValueError, OSError):
        return False
    return False


def _url_aman(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    if p.scheme not in ("http", "https"):
        return False
    return not _alamat_privat(p.hostname or "")


# ---------------------------------------------------------------------
# BERSIH-BERSIH TEKS
# ---------------------------------------------------------------------
_RE_SKRIP = re.compile(r"<(script|style|noscript|svg|iframe)[^>]*>.*?</\1>", re.S | re.I)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_SPASI = re.compile(r"[ \t\r\f\v]+")
_RE_BARIS_KOSONG = re.compile(r"\n{3,}")


def _teks_dari_html(isi: str) -> str:
    """Mengubah HTML menjadi teks biasa yang ringkas."""
    isi = _RE_SKRIP.sub(" ", isi)
    isi = _RE_TAG.sub(" ", isi)
    isi = html.unescape(isi)
    isi = _RE_SPASI.sub(" ", isi)
    isi = _RE_BARIS_KOSONG.sub("\n\n", isi)
    return isi.strip()


# ---------------------------------------------------------------------
# SUMBER 1: WIKIPEDIA (utama, resmi, stabil)
# ---------------------------------------------------------------------
async def _wiki_cari(http: httpx.AsyncClient, kueri: str, bahasa: str) -> List[dict]:
    """Mencari judul artikel relevan lewat API resmi Wikipedia."""
    try:
        res = await http.get(
            f"https://{bahasa}.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": kueri,
                "format": "json",
                "srlimit": 5,
                "srprop": "snippet|wordcount",
            },
            headers={"User-Agent": UA_WIKI},
            timeout=TIMEOUT_CARI,
        )
        if res.status_code >= 400:
            return []
        data = res.json()
    except (httpx.HTTPError, ValueError):
        return []

    kunci = _kunci_relevan(kueri)
    hasil = []
    for item in (data.get("query") or {}).get("search") or []:
        judul = (item.get("title") or "").strip()
        if not judul:
            continue
        cuplikan = _teks_dari_html(item.get("snippet") or "")[:300]
        # Saring hasil tidak relevan. Pencarian Wikipedia kadang
        # mengembalikan artikel "mirip secara kata" tetapi bukan
        # jawabannya (mis. query "ibu kota Australia" -> "Jakarta").
        # Artikel yang cocok hampir selalu memuat kata kunci utama
        # pada JUDUL atau CUPLIKANNYA.
        gabungan = f"{judul} {cuplikan}".lower()
        utama = kunci[0] if kunci else ""
        cocok_utama = (utama in gabungan) if utama else True
        jumlah_cocok = sum(1 for k in kunci if k in gabungan)
        if not cocok_utama and jumlah_cocok < max(2, len(kunci)):
            continue
        hasil.append(
            {
                "judul": judul,
                "bahasa": bahasa,
                "cuplikan": cuplikan,
                "peringkat": jumlah_cocok,
                "url": f"https://{bahasa}.wikipedia.org/wiki/{quote(judul.replace(' ', '_'))}",
            }
        )
    # Artikel yang memuat lebih banyak kata kunci dianggap lebih tepat.
    hasil.sort(key=lambda s: s.get("peringkat", 0), reverse=True)
    return hasil[:2]


async def _wiki_ringkas(http: httpx.AsyncClient, bahasa: str, judul: str) -> str:
    """Mengambil ringkasan artikel (REST API resmi)."""
    try:
        res = await http.get(
            f"https://{bahasa}.wikipedia.org/api/rest_v1/page/summary/{quote(judul.replace(' ', '_'), safe='')}",
            headers={"User-Agent": UA_WIKI},
            timeout=TIMEOUT_BACA,
        )
        if res.status_code >= 400:
            return ""
        data = res.json()
    except (httpx.HTTPError, ValueError):
        return ""
    return (data.get("extract") or "").strip()


# ---------------------------------------------------------------------
# SUMBER 2: BING (pelengkap berita/opini terkini)
# ---------------------------------------------------------------------
_RE_BLOK_BING = re.compile(r'<li class="b_algo".*?</li>', re.S)
_RE_JUDUL_BING = re.compile(r"<h2>.*?<a[^>]*>(.*?)</a>", re.S)
_RE_CITE_BING = re.compile(r"<cite[^>]*>(.*?)</cite>", re.S)
_RE_KUTIP_BING = re.compile(r"<p[^>]*>(.*?)</p>", re.S)


def _kunci_relevan(kueri: str) -> List[str]:
    """Kata kunci bermakna dari query, untuk menyaring hasil sampah."""
    kata = [k.lower() for k in re.split(r"[^\w]+", kueri or "") if len(k) > 2]
    # Buang kata tanya yang tidak membedakan hasil.
    buang = {
        "apa", "siapa", "kapan", "dimana", "mana", "bagaimana", "mengapa",
        "yang", "dan", "atau", "untuk", "dengan", "dari", "adalah", "itu",
        "the", "and", "what", "who", "when", "where", "how", "why", "is",
    }
    return [k for k in kata if k not in buang][:6]


async def _bing_cari(http: httpx.AsyncClient, kueri: str) -> List[dict]:
    """
    Mencari lewat Bing. Hasil disaring ketat karena Bing kadang
    menyajikan halaman sampah bila mendeteksi akses otomatis.
    """
    try:
        res = await http.get(
            "https://www.bing.com/search",
            params={"q": kueri, "setlang": "id", "cc": "ID"},
            headers={"User-Agent": UA_BROWSER, "Accept-Language": "id,en;q=0.8"},
            timeout=TIMEOUT_CARI,
        )
        if res.status_code >= 400:
            return []
        isi = res.text
    except httpx.HTTPError:
        return []

    kunci = _kunci_relevan(kueri)
    hasil: List[dict] = []
    for blok in _RE_BLOK_BING.findall(isi):
        j = _RE_JUDUL_BING.search(blok)
        c = _RE_CITE_BING.search(blok)
        p = _RE_KUTIP_BING.search(blok)
        judul = _teks_dari_html(j.group(1)) if j else ""
        url = _teks_dari_html(c.group(1)) if c else ""
        kutip = _teks_dari_html(p.group(1)) if p else ""
        if not url.startswith("http") or not _url_aman(url):
            continue
        # Saring hasil sampah: harus memuat sebagian kata kunci.
        gabungan = f"{judul} {kutip} {url}".lower()
        cocok = sum(1 for k in kunci if k in gabungan)
        if kunci and cocok < max(1, len(kunci) // 2):
            continue
        hasil.append({"judul": judul[:160] or url, "url": url, "cuplikan": kutip[:300]})
        if len(hasil) >= 2:
            break
    return hasil


# ---------------------------------------------------------------------
# MEMBACA HALAMAN LANGSUNG
# ---------------------------------------------------------------------
async def _baca(http: httpx.AsyncClient, url: str) -> str:
    """Mengambil inti teks satu halaman. Gagal -> string kosong."""
    if not _url_aman(url):
        return ""
    try:
        res = await http.get(
            url,
            headers={
                "User-Agent": UA_BROWSER,
                "Accept": "text/html,application/xhtml+xml,text/plain",
                "Accept-Language": "id,en;q=0.8",
            },
            follow_redirects=True,
            timeout=TIMEOUT_BACA,
        )
    except (httpx.HTTPError, ValueError):
        return ""
    if res.status_code >= 400:
        return ""
    jenis = (res.headers.get("content-type") or "").lower()
    if "html" not in jenis and "text/plain" not in jenis:
        return ""
    return _teks_dari_html(res.text)[:MAKS_KARAKTER_SUMBER]


# ---------------------------------------------------------------------
# API PUBLIK
# ---------------------------------------------------------------------
async def cari_dan_baca(kueri: str) -> dict:
    """
    Satu putaran riset: cari di Wikipedia + Bing, lalu baca isinya.

    Selalu mengembalikan dict (tidak pernah melempar exception):

        {
          "kueri": "...",
          "sumber": [{"judul","url","cuplikan","isi"}...],
          "teks": "..."    # konteks siap-pakai untuk model ("" = kosong)
        }
    """
    kueri = (kueri or "").strip()
    hasil: dict = {"kueri": kueri, "sumber": [], "teks": ""}
    if not kueri:
        return hasil

    batas = httpx.Timeout(TIMEOUT_CARI, connect=6.0)
    async with httpx.AsyncClient(timeout=batas, follow_redirects=True) as http:
        # Wikipedia id & en + Bing, dijalankan BERSAMAAN agar cepat.
        tugas = [
            asyncio.create_task(_wiki_cari(http, kueri, "id")),
            asyncio.create_task(_wiki_cari(http, kueri, "en")),
            asyncio.create_task(_bing_cari(http, kueri)),
        ]
        kumpulan: List[dict] = []
        for selesai in asyncio.as_completed(tugas):
            try:
                kumpulan.extend(await selesai)
            except Exception as exc:  # noqa: BLE001
                logger.info("Sumber pencarian gagal: %s", exc)

        # Buang duplikat (judul+url), pertahankan urutan prioritas:
        # Wikipedia ID lebih dulu karena bahasanya sama dengan pengguna.
        terlihat: set = set()
        unik: List[dict] = []
        for s in kumpulan:
            kunci = (s.get("judul", "").lower(), s.get("url", ""))
            if kunci in terlihat:
                continue
            terlihat.add(kunci)
            unik.append(s)
            if len(unik) >= MAKS_SUMBER:
                break

        # Isi tiap sumber: artikel Wikipedia diambil lewat REST resmi
        # (bersih & cepat), sisanya dibaca langsung dari halaman.
        async def isi_dari(s: dict) -> str:
            if s.get("bahasa"):
                teks = await _wiki_ringkas(http, s["bahasa"], s["judul"])
                if teks:
                    return teks[:MAKS_KARAKTER_SUMBER]
            return await _baca(http, s["url"])

        if unik:
            isi_semua = await asyncio.gather(
                *[isi_dari(s) for s in unik], return_exceptions=True
            )
            for s, isi in zip(unik, isi_semua):
                s["isi"] = isi if isinstance(isi, str) else ""
            hasil["sumber"] = unik

    # Susun konteks untuk model. Bila isi halaman kosong, cuplikan
    # pencarian tetap dipakai agar riset tidak sia-sia.
    potongan: List[str] = []
    total = 0
    for i, s in enumerate(hasil["sumber"], start=1):
        badan = (s.get("isi") or "").strip() or (s.get("cuplikan") or "").strip()
        if not badan:
            continue
        blok = f"[Sumber {i}] {s.get('judul') or s['url']}\nURL: {s['url']}\n{badan}"
        if total + len(blok) > MAKS_KARAKTER_TOTAL:
            blok = blok[: max(0, MAKS_KARAKTER_TOTAL - total)]
        if not blok:
            break
        potongan.append(blok)
        total += len(blok)

    hasil["teks"] = "\n\n".join(potongan)
    logger.info(
        "Riset '%s': %d sumber, %d karakter konteks",
        kueri[:60],
        len(hasil["sumber"]),
        len(hasil["teks"]),
    )
    return hasil


def konteks_untuk_model(hasil: dict) -> Optional[str]:
    """
    Membungkus hasil riset menjadi pesan sistem siap kirim.

    None bila kosong, agar pemanggil tidak mengirim blok kosong yang
    justru membuat model bingung.
    """
    teks = (hasil or {}).get("teks") or ""
    if not teks.strip():
        return None
    return (
        "Berikut hasil pencarian web terbaru yang HARUS menjadi dasar "
        "jawabanmu. Gunakan isinya; jangan mengarang di luar itu.\n\n"
        f"{teks}\n\n"
        "ATURAN MENJAWAB:\n"
        "1. Jawab langsung ke inti pertanyaan pengguna.\n"
        "2. Sebutkan sumber dengan penanda [1], [2] sesuai nomor di atas, "
        "dan tuliskan tautannya di akhir bila relevan.\n"
        "3. Bila sumber saling bertentangan, sebutkan perbedaannya.\n"
        "4. Bila sumber tidak memuat jawabannya, katakan terus terang, lalu "
        "jawab sebisamu dari pengetahuan sendiri dan tandai bagian itu.\n"
        "5. Jangan menyebut kata 'konteks', 'sistem', atau 'prompt'."
    )


def instruksi_query() -> str:
    """
    Instruksi agar model merumuskan kata kunci pencarian yang tajam.

    Query buruk menghasilkan riset buruk, jadi langkah ini dipisah:
    model berpikir "apa yang perlu dicari" dulu, baru dicari.
    """
    return (
        "Kamu adalah perumus kata kunci pencarian. Dari permintaan pengguna, "
        "tulis SATU kalimat pencarian yang paling tepat: singkat (maksimal 12 "
        "kata), tanpa tanda kutip, tanpa nomor, tanpa penjelasan, tanpa kata "
        "'tolong'. Bila pertanyaannya tentang hal terkini, sebutkan topiknya "
        "secara spesifik. Balas HANYA kalimat pencarian itu."
    )


def bersihkan_query(teks: Optional[str], cadangan: str) -> str:
    """
    Merapikan keluaran model menjadi query yang wajar.

    Model kadang menambahkan tanda kutip, label "Query:", atau kalimat
    panjang. Semua itu dibuang di sini agar pencarian tetap tepat.
    """
    q = (teks or "").strip()
    if not q:
        return (cadangan or "").strip()[:200]
    # Ambil baris pertama yang berisi.
    for baris in q.splitlines():
        baris = baris.strip()
        if baris:
            q = baris
            break
    q = re.sub(r"^(query|pencarian|search)\s*[:：]\s*", "", q, flags=re.I)
    q = q.strip("\"'`“”‘’ ").strip()
    # Buang kalimat penjelas setelah tanda titik dua di ujung.
    if len(q) > 160:
        q = q[:160]
    return q or (cadangan or "").strip()[:200]
