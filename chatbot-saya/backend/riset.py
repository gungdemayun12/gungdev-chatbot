"""
riset.py — riset web NYATA yang bekerja untuk SEMUA model & penyedia.

KENAPA MODUL INI DITULIS ULANG
------------------------------
Versi pertama modul ini bertumpu pada Bing sebagai sumber berita/artikel.
Saat diuji ulang, Bing TERBUKTI SELALU KOSONG: halaman hasilnya sekarang
dirender dengan JavaScript, sehingga HTML yang diterima server tidak
memuat satu pun hasil (penanda `b_algo` muncul 0 kali pada query apa
pun). Akibatnya riset hanya mendapat artikel Wikipedia — dan itulah
sebabnya model menjawab "aku belum bisa membuka browser". Model tidak
berbohong; memang tidak ada bahan yang diberikan kepadanya.

Modul ini dibangun ulang dengan sumber yang SUDAH DIUJI menghasilkan
hasil nyata dari server:

1. YAHOO SEARCH (utama). Satu-satunya mesin umum yang mengembalikan
   hasil lengkap tanpa API key dan tanpa diblokir. Hasilnya memuat
   judul, URL asli, tanggal, dan cuplikan. Diuji pada berita, tutorial,
   harga, resep, dan jadwal — semuanya berhasil.
2. GOOGLE NEWS RSS (berita). Sangat kaya untuk topik terkini; mengirim
   XML bersih tanpa perlu API key.
3. WIKIPEDIA (pelengkap). Tetap dipakai untuk topik ensiklopedis.
   PENTING: Wikimedia menolak User-Agent tanpa kontak (HTTP 403), jadi
   UA wajib memuat nama aplikasi + email.
4. PEMBACAAN HALAMAN LANGSUNG. Isi halaman diambil dan dibersihkan
   menjadi teks, sehingga model membaca isi sebenarnya — bukan hanya
   cuplikan pencarian.

YANG TERBUKTI GAGAL (jangan dicoba lagi tanpa menguji ulang)
-----------------------------------------------------------
DuckDuckGo (html & lite): HTTP 202 + halaman kosong.
Brave: HTTP 429. Mojeek: halaman tanpa hasil. Startpage: tanpa hasil.
Ecosia: HTTP 403. Google: halaman persetujuan/captcha. Bing: kosong.

PRINSIP
-------
1. TIDAK PERNAH menggagalkan chat. Semua kegagalan ditelan dan dicatat
   di log.
2. TIDAK butuh rahasia baru (tanpa API key pencarian, tanpa biaya).
3. Selalu menyebut sumber (URL) agar pengguna bisa memeriksa sendiri.
4. Anti-SSRF: hanya http/https dan alamat publik.
5. Riset bisa berlapis: putaran pertama mencari, putaran berikutnya
   menggali lebih dalam dari sumber yang paling relevan.
"""

from __future__ import annotations

import asyncio
import html
import ipaddress
import logging
import re
import socket
from typing import List, Optional
from urllib.parse import parse_qs, quote, unquote, urlparse

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

# Wikimedia MENOLAK User-Agent generik tanpa info kontak (HTTP 403,
# "Please respect our robot policy"). UA ini wajib memuat nama aplikasi
# dan alamat kontak.
UA_WIKI = (
    "GungDev/2.0 (https://gungdevchatbot.vercel.app; admin@gungdev.ai) "
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
_RE_SKRIP = re.compile(r"<(script|style|noscript|svg|iframe|header|footer|nav)[^>]*>.*?</\1>", re.S | re.I)
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


def _bersih_cuplikan(teks: str) -> str:
    """Membuang tag dari cuplikan hasil pencarian."""
    return re.sub(r"\s+", " ", html.unescape(_RE_TAG.sub(" ", teks or ""))).strip()


def _kunci_relevan(kueri: str) -> List[str]:
    """Kata kunci bermakna dari query, untuk menyaring hasil sampah."""
    kata = [k.lower() for k in re.split(r"[^\w]+", kueri or "") if len(k) > 2]
    # Buang kata tanya yang tidak membedakan hasil.
    buang = {
        "apa", "siapa", "kapan", "dimana", "mana", "bagaimana", "mengapa",
        "yang", "dan", "atau", "untuk", "dengan", "dari", "adalah", "itu",
        "tolong", "carikan", "cari", "berikan", "jelaskan", "sebutkan",
        "the", "and", "what", "who", "when", "where", "how", "why", "is",
    }
    return [k for k in kata if k not in buang][:6]


# ---------------------------------------------------------------------
# SUMBER 1: YAHOO SEARCH (utama, terbukti bekerja)
# ---------------------------------------------------------------------
# Yahoo membungkus tautan hasil dalam r.search.yahoo.com/.../RU=<url asli>/
_RE_BLOK_YAHOO = re.compile(r'<div class="dd algo[^"]*"[^>]*>(.*?)</li>', re.S)
_RE_HREF_YAHOO = re.compile(r'href="(https://r\.search\.yahoo\.com/[^"]+)"')
_RE_JUDUL_YAHOO = re.compile(r"<h3[^>]*>.*?<span[^>]*>(.*?)</span>", re.S)
_RE_WEB_YAHOO = re.compile(r'class="d-ib va-mid">(.*?)</span>', re.S)
_RE_CUPLIK_YAHOO = re.compile(r'<p class="[^"]*">(.*?)</p>', re.S)
_RE_TANGGAL = re.compile(r"(\d+\s+(?:menit|jam|hari|minggu|bulan|tahun)\s+lalu|\w{3}\s+\d{1,2},\s+\d{4})")


def _url_asli_yahoo(href: str) -> str:
    """
    Mengambil URL asli dari tautan pengalihan Yahoo.

    Yahoo membungkus: /RU=<url ter-encode>/RK=2/RS=...
    Tanpa pembongkaran ini, model hanya melihat tautan Yahoo dan
    pengguna tidak bisa membuka sumbernya.
    """
    m = re.search(r"/RU=([^/]+)/", href)
    if m:
        return unquote(m.group(1))
    m = re.search(r"[?&]u=([^&]+)", href)
    if m:
        return unquote(m.group(1))
    q = parse_qs(urlparse(href).query)
    for calon in ("url", "u", "q"):
        if q.get(calon):
            return q[calon][0]
    return href


async def _yahoo_cari(http: httpx.AsyncClient, kueri: str) -> List[dict]:
    """
    Mencari lewat Yahoo. Ini mesin utama karena terbukti mengembalikan hasil.

    PENTING: Yahoo kadang membalas HTTP 500 (pembatas laju sementara)
    walaupun query yang sama berhasil pada percobaan berikutnya. Karena
    itu ada percobaan ulang singkat — tanpa ini, satu kali 500 membuat
    riset kosong padahal sumbernya sehat.
    """
    isi = ""
    for percobaan in range(3):
        try:
            res = await http.get(
                "https://search.yahoo.com/search",
                params={"p": kueri},
                headers={"User-Agent": UA_BROWSER, "Accept-Language": "id,en;q=0.8"},
                timeout=TIMEOUT_CARI,
            )
            if res.status_code < 400 and "dd algo" in res.text:
                isi = res.text
                break
            logger.info(
                "Yahoo percobaan %d: HTTP %s (%d byte)", percobaan + 1, res.status_code, len(res.text)
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.info("Yahoo percobaan %d gagal: %s", percobaan + 1, exc)
        if percobaan < 2:
            await asyncio.sleep(1.2 * (percobaan + 1))

    if not isi:
        return []

    kunci = _kunci_relevan(kueri)
    hasil: List[dict] = []
    for blok in _RE_BLOK_YAHOO.findall(isi):
        h = _RE_HREF_YAHOO.search(blok)
        if not h:
            continue
        url = _url_asli_yahoo(h.group(1))
        if not url.startswith("http") or not _url_aman(url):
            continue
        j = _RE_JUDUL_YAHOO.search(blok)
        w = _RE_WEB_YAHOO.search(blok)
        c = _RE_CUPLIK_YAHOO.search(blok)
        judul = _bersih_cuplikan(j.group(1)) if j else ""
        situs = _bersih_cuplikan(w.group(1)) if w else ""
        cuplik = _bersih_cuplikan(c.group(1)) if c else ""
        if not judul:
            continue

        # Yahoo sudah menyaring relevansi; penyaringan di sini hanya
        # membuang hasil yang jelas tidak berhubungan.
        gabungan = f"{judul} {cuplik} {situs}".lower()
        cocok = sum(1 for k in kunci if k in gabungan)
        if kunci and cocok == 0:
            continue

        tanggal = ""
        m = _RE_TANGGAL.search(situs)
        if m:
            tanggal = m.group(1)

        hasil.append(
            {
                "judul": judul[:160],
                "url": url,
                "cuplikan": cuplik[:400],
                "situs": situs[:200],
                "tanggal": tanggal,
                "peringkat": cocok,
                "asal": "yahoo",
            }
        )
        if len(hasil) >= MAKS_SUMBER:
            break
    return hasil


# ---------------------------------------------------------------------
# SUMBER 1b: MARGINALIA (cadangan independen, tanpa API key)
# ---------------------------------------------------------------------
# Marginalia unggul untuk topik teknis/tutorial, dan TIDAK memakai
# infrastruktur Yahoo — jadi saat Yahoo membatasi, sumber ini tetap
# memberi hasil. Diuji: mengembalikan tutorial React dari blog nyata.
_RE_HASIL_MARGINALIA = re.compile(
    r'<a[^>]+href="(https?://[^"]+)"[^>]*class="[^"]*title[^"]*"[^>]*>(.*?)</a>', re.S
)


async def _marginalia_cari(http: httpx.AsyncClient, kueri: str) -> List[dict]:
    """Mencari lewat Marginalia (mesin pencari independen)."""
    isi = ""
    for percobaan in range(2):
        try:
            res = await http.get(
                "https://search.marginalia.nu/search",
                params={"query": kueri},
                headers={"User-Agent": UA_BROWSER},
                timeout=TIMEOUT_CARI,
            )
            if res.status_code < 400 and len(res.text) > 20_000:
                isi = res.text
                break
        except (httpx.HTTPError, ValueError):
            pass
        if percobaan == 0:
            await asyncio.sleep(1.0)

    if not isi:
        return []

    kunci = _kunci_relevan(kueri)
    hasil: List[dict] = []
    terlihat: set = set()
    # Marginalia menandai tautan hasil dengan atribut khusus; pola di
    # bawah menangkap tautan luar yang bukan bagian antarmuka situsnya.
    for url, judul_html in re.findall(
        r'<a[^>]+href="(https?://[^"]+)"[^>]*>([^<]{8,140})</a>', isi
    ):
        if any(x in url for x in ("marginalia", "creativecommons", "ip2location", "github.com/MarginaliaSearch")):
            continue
        if url in terlihat or not _url_aman(url):
            continue
        judul = _bersih_cuplikan(judul_html)
        if len(judul) < 8:
            continue
        gabungan = f"{judul} {url}".lower()
        cocok = sum(1 for k in kunci if k in gabungan)
        if kunci and cocok == 0:
            continue
        terlihat.add(url)
        hasil.append(
            {
                "judul": judul[:160],
                "url": url,
                "cuplikan": "",
                "situs": urlparse(url).hostname or "",
                "tanggal": "",
                "peringkat": cocok,
                "asal": "marginalia",
            }
        )
        if len(hasil) >= 4:
            break
    return hasil


# ---------------------------------------------------------------------
# SUMBER 2: GOOGLE NEWS RSS (berita terkini)
# ---------------------------------------------------------------------
_RE_ITEM_RSS = re.compile(r"<item>(.*?)</item>", re.S)
_RE_JUDUL_RSS = re.compile(r"<title>(.*?)</title>", re.S)
_RE_LINK_RSS = re.compile(r"<link>(.*?)</link>", re.S)
_RE_DESC_RSS = re.compile(r"<description>(.*?)</description>", re.S)
_RE_DATE_RSS = re.compile(r"<pubDate>(.*?)</pubDate>", re.S)
_RE_SOURCE_RSS = re.compile(r'<source url="([^"]*)"[^>]*>(.*?)</source>', re.S)


async def _berita_cari(http: httpx.AsyncClient, kueri: str) -> List[dict]:
    """
    Mencari berita lewat Google News RSS (tanpa API key).

    CATATAN PENTING soal tautan: Google News membungkus setiap tautan
    menjadi `news.google.com/rss/articles/CBMi...` yang isinya JavaScript,
    bukan alamat artikel aslinya. Halaman itu tidak bisa dibaca sebagai
    artikel. Karena itu:
      - alamat SITUS ASLI diambil dari elemen <source url="...">;
      - tautan artikel asli dicari di dalam cuplikan <description>;
      - bila tidak ada, sumber tetap dipakai lewat cuplikannya saja.
    """
    try:
        res = await http.get(
            "https://news.google.com/rss/search",
            params={"q": kueri, "hl": "id", "gl": "ID", "ceid": "ID:id"},
            headers={"User-Agent": UA_BROWSER},
            timeout=TIMEOUT_CARI,
        )
        if res.status_code >= 400:
            return []
        isi = res.text
    except (httpx.HTTPError, ValueError):
        return []

    kunci = _kunci_relevan(kueri)
    hasil: List[dict] = []
    for item in _RE_ITEM_RSS.findall(isi):
        j = _RE_JUDUL_RSS.search(item)
        l = _RE_LINK_RSS.search(item)
        t = _RE_DATE_RSS.search(item)
        src = _RE_SOURCE_RSS.search(item)
        judul = _bersih_cuplikan(j.group(1)) if j else ""
        tautan = (l.group(1) or "").strip() if l else ""
        # "Judul - Nama Portal": portal dipisah agar bisa disebut sebagai sumber.
        portal = _bersih_cuplikan(src.group(2)) if src else ""
        situs_url = (src.group(1) or "").strip() if src else ""
        if not judul:
            continue

        # Tautan asli di dalam description (bila portal menyertakannya).
        asli = ""
        d = _RE_DESC_RSS.search(item)
        if d:
            m = re.search(r'href="(https?://(?!news\.google\.com)[^"]+)"', html.unescape(d.group(1)))
            if m:
                asli = m.group(1)

        url_pakai = asli or (situs_url if situs_url.startswith("http") else "") or tautan
        if not url_pakai.startswith("http") or not _url_aman(url_pakai):
            continue

        gabungan = f"{judul} {portal}".lower()
        cocok = sum(1 for k in kunci if k in gabungan)
        if kunci and cocok == 0:
            continue

        hasil.append(
            {
                "judul": judul[:160],
                "url": url_pakai,
                "cuplikan": judul[:400],
                "situs": portal or "Google News",
                "tanggal": (t.group(1).strip() if t else ""),
                "peringkat": cocok,
                "asal": "berita",
                # Berita hanya dipakai cuplikannya; halaman aslinya sering
                # memasang paywall atau anti-bot.
                "hanya_cuplikan": asli == "",
            }
        )
        if len(hasil) >= 3:
            break
    return hasil


# ---------------------------------------------------------------------
# SUMBER 3: WIKIPEDIA (pelengkap topik ensiklopedis)
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
            logger.info("Wikipedia %s menolak (%s)", bahasa, res.status_code)
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
                "situs": f"Wikipedia ({bahasa})",
                "tanggal": "",
                "asal": "wiki",
            }
        )
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
# MEMBACA HALAMAN LANGSUNG
# ---------------------------------------------------------------------
async def _baca(http: httpx.AsyncClient, url: str, maks: int = MAKS_KARAKTER_SUMBER) -> str:
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
    return _teks_dari_html(res.text)[:maks]


# ---------------------------------------------------------------------
# API PUBLIK
# ---------------------------------------------------------------------
def _gabung_unik(kumpulan: List[dict], batas: int) -> List[dict]:
    """Buang duplikat berdasarkan URL dan judul, pertahankan urutan prioritas."""
    terlihat_url: set = set()
    terlihat_judul: set = set()
    unik: List[dict] = []
    for s in kumpulan:
        url = (s.get("url") or "").split("#")[0].rstrip("/")
        judul = (s.get("judul") or "").strip().lower()
        if not url:
            continue
        if url in terlihat_url:
            continue
        # Satu berita sering muncul di banyak portal dengan judul sama.
        if judul and judul in terlihat_judul:
            continue
        terlihat_url.add(url)
        if judul:
            terlihat_judul.add(judul)
        unik.append(s)
        if len(unik) >= batas:
            break
    return unik


async def cari_dan_baca(kueri: str, maks_sumber: int = MAKS_SUMBER) -> dict:
    """
    Satu putaran riset: cari di Yahoo + Google News + Wikipedia, lalu baca
    isi halaman yang paling relevan.

    Selalu mengembalikan dict (tidak pernah melempar exception):

        {
          "kueri": "...",
          "sumber": [{"judul","url","cuplikan","isi","situs","tanggal"}...],
          "teks": "..."    # konteks siap-pakai untuk model ("" = kosong)
        }
    """
    kueri = (kueri or "").strip()
    hasil: dict = {"kueri": kueri, "sumber": [], "teks": ""}
    if not kueri:
        return hasil

    batas_waktu = httpx.Timeout(TIMEOUT_CARI, connect=6.0)
    async with httpx.AsyncClient(timeout=batas_waktu, follow_redirects=True) as http:
        # Semua sumber dijalankan BERSAMAAN agar cepat. Yahoo didahulukan
        # dalam penyusunan hasil, tetapi tidak perlu menunggu satu per satu.
        tugas = {
            "yahoo": asyncio.create_task(_yahoo_cari(http, kueri)),
            "berita": asyncio.create_task(_berita_cari(http, kueri)),
            "marginalia": asyncio.create_task(_marginalia_cari(http, kueri)),
            "wiki_id": asyncio.create_task(_wiki_cari(http, kueri, "id")),
            "wiki_en": asyncio.create_task(_wiki_cari(http, kueri, "en")),
        }
        kumpulan: List[dict] = []
        for nama in ("yahoo", "marginalia", "berita", "wiki_id", "wiki_en"):
            try:
                kumpulan.extend(await tugas[nama])
            except Exception as exc:  # noqa: BLE001
                logger.info("Sumber '%s' gagal: %s", nama, exc)

        unik = _gabung_unik(kumpulan, maks_sumber)

        # Isi tiap sumber: artikel Wikipedia diambil lewat REST resmi
        # (bersih & cepat), sisanya dibaca langsung dari halaman.
        async def isi_dari(s: dict) -> str:
            if s.get("hanya_cuplikan"):
                # Tautan Google News tidak bisa dibaca sebagai artikel;
                # cuplikannya sudah berupa judul berita yang informatif.
                return ""
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
            # Sumber yang isinya benar-benar terbaca didahulukan: model
            # lebih baik membaca 3 halaman utuh daripada 6 cuplikan.
            unik.sort(key=lambda s: 0 if (s.get("isi") or "").strip() else 1)
            hasil["sumber"] = unik

    hasil["teks"] = _susun_teks(hasil["sumber"])
    logger.info(
        "Riset '%s': %d sumber (%s), %d karakter konteks",
        kueri[:60],
        len(hasil["sumber"]),
        ", ".join(f"{s.get('asal')}" for s in hasil["sumber"]) or "-",
        len(hasil["teks"]),
    )
    return hasil


def _susun_teks(sumber: List[dict]) -> str:
    """Menyusun konteks untuk model dari daftar sumber."""
    potongan: List[str] = []
    total = 0
    for i, s in enumerate(sumber, start=1):
        badan = (s.get("isi") or "").strip() or (s.get("cuplikan") or "").strip()
        if not badan:
            continue
        kepala = f"[Sumber {i}] {s.get('judul') or s['url']}"
        if s.get("situs"):
            kepala += f" — {s['situs']}"
        if s.get("tanggal"):
            kepala += f" ({s['tanggal']})"
        blok = f"{kepala}\nURL: {s['url']}\n{badan}"
        if total + len(blok) > MAKS_KARAKTER_TOTAL:
            blok = blok[: max(0, MAKS_KARAKTER_TOTAL - total)]
        if not blok:
            break
        potongan.append(blok)
        total += len(blok)
    return "\n\n".join(potongan)


def ada_hasil(hasil: dict) -> bool:
    """True bila riset benar-benar mendapat bahan yang bisa dibaca."""
    return bool(((hasil or {}).get("teks") or "").strip())


def daftar_sumber(hasil: dict) -> List[dict]:
    """
    Menyusun daftar sumber RINGKAS untuk ditampilkan di UI (kartu sumber).

    Yang dikirim hanya hal yang memang boleh dilihat pengguna: nomor,
    judul, alamat situs, dan tautan. Isi halaman TIDAK dikirim balik ke
    browser karena sudah dipakai model dan akan membuat respons bengkak
    (bisa puluhan ribu karakter per jawaban).

    Nomor di sini SAMA dengan nomor `[Sumber n]` yang dibaca model, agar
    penanda `[1]` di jawaban menunjuk kartu yang benar.
    """
    keluaran: List[dict] = []
    for i, s in enumerate((hasil or {}).get("sumber") or [], start=1):
        url = (s.get("url") or "").strip()
        if not url:
            continue
        keluaran.append(
            {
                "nomor": i,
                "judul": (s.get("judul") or url).strip()[:200],
                "url": url,
                "situs": (s.get("situs") or urlparse(url).hostname or "")[:120],
                "tanggal": (s.get("tanggal") or "")[:60],
            }
        )
    return keluaran


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
        "1. Jawab langsung ke inti pertanyaan pengguna. Bila jawabannya "
        "berupa daftar (misalnya beberapa pilihan paket, produk, atau "
        "harga), tulis SATU per SATU dan setiap butir yang berasal dari "
        "sebuah sumber ditutup dengan penandanya sendiri.\n"
        "2. Tempelkan penanda sumber di UJUNG KALIMAT yang memakai sumber "
        "itu, tepat sebelum titik. Contoh BENAR: 'Harga mulai Rp400.000 "
        "[1].' Contoh SALAH: 'Harga mulai Rp400.000.' ... [1] di akhir "
        "jawaban. JANGAN mengumpulkan semua penanda di akhir jawaban.\n"
        "3. JANGAN menulis daftar tautan di akhir jawaban: pengguna sudah "
        "melihat daftar sumbernya otomatis di bawah jawabanmu.\n"
        "4. Bila satu kalimat memakai beberapa sumber, tulis berurutan: "
        "[1][3].\n"
        "5. Bila sumber saling bertentangan, sebutkan perbedaannya.\n"
        "6. Bila sumber tidak memuat jawabannya, katakan terus terang, lalu "
        "jawab sebisamu dari pengetahuan sendiri dan tandai bagian itu.\n"
        "7. Jangan menyebut kata 'konteks', 'sistem', atau 'prompt'.\n"
        "8. DILARANG berkata bahwa kamu tidak bisa membuka web atau tidak "
        "bisa menelusuri internet: sumber di atas SUDAH dibaca untukmu. "
        "Kalau ada yang belum terjawab, cukup sebutkan bagian mana yang "
        "belum ada di sumber."
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


def instruksi_query_lanjutan(pertanyaan: str, sudah: str) -> str:
    """
    Instruksi untuk putaran kedua: menggali celah dari hasil pertama.

    Di sini model diminta menyebut APA YANG BELUM TERJAWAB, lalu
    merumuskan pencarian baru untuk menutupnya. Tanpa langkah ini, dua
    putaran hanya akan mencari hal yang sama dua kali.
    """
    return (
        "Kamu membantu riset bertahap. Pertanyaan pengguna: "
        f"{pertanyaan[:400]}\n\n"
        "Kata kunci yang SUDAH dicari (jangan diulang): "
        f"{sudah[:400]}\n\n"
        "Tulis SATU kata kunci pencarian BARU yang menutup bagian yang "
        "belum terjawab, misalnya angka/tanggal terbaru, nama resmi, atau "
        "sudut pandang lain. Maksimal 12 kata, tanpa tanda kutip, tanpa "
        "penjelasan. Balas HANYA kata kunci itu. Bila sudah tidak ada yang "
        "perlu dicari, balas: CUKUP"
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


# ---------------------------------------------------------------------
# PENDERAS: pesan pengguna mengandung permintaan riset?
# ---------------------------------------------------------------------
_POLA_RISET = re.compile(
    r"\b("
    r"riset|research|teliti|penelitian|"
    r"cari(?:kan|in|lah)?|carikan|search|"
    r"berita|kabar|artikel|jurnal|referensi|sumber|sumbernya|"
    r"terbaru|terkini|terupdate|update|hari ini|minggu ini|bulan ini|tahun ini|"
    r"harga|kurs|jadwal|skor|hasil pertandingan|cuaca|"
    r"siapa|kapan|di mana|dimana|berapa|"
    r"browsing|internet|web|google|"
    r"latest|news|current|price|schedule"
    r")\b",
    re.I,
)

# Pertanyaan yang JELAS tidak butuh internet. Riset pada pertanyaan seperti
# ini hanya memperlambat jawaban tanpa menambah mutu.
_POLA_TANPA_RISET = re.compile(
    r"^\s*("
    r"halo|hai|hi|hey|pagi|siang|sore|malam|assalam|salam|"
    r"terima kasih|makasih|thanks|thank you|ok|oke|sip|baik|"
    r"apa kabar|kamu siapa|siapa kamu|kamu bisa apa|"
    r"tes|test|p|ping"
    r")\b",
    re.I,
)


def perlu_riset(pesan: str, panjang_min: int = 12) -> bool:
    """
    Menilai apakah pesan pengguna wajar diriset.

    Dipakai untuk riset OTOMATIS: pengguna tidak perlu menekan tombol apa
    pun. Aturannya sengaja murah hati — lebih baik meriset daripada
    menjawab dari ingatan lalu keliru. Yang dikecualikan hanya sapaan dan
    percakapan basa-basi yang panjangnya sangat pendek.
    """
    teks = (pesan or "").strip()
    if not teks:
        return False
    # Sapaan singkat: tidak perlu internet.
    if _POLA_TANPA_RISET.match(teks) and len(teks) < 40:
        return False
    if _POLA_RISET.search(teks):
        return True
    # Pesan panjang yang berupa pertanyaan biasanya layak diriset.
    jumlah_kata = len(teks.split())
    if jumlah_kata >= 6 and ("?" in teks or teks.lower().startswith(("apa", "kenapa", "mengapa", "bagaimana", "jelaskan", "bandingkan"))):
        return True
    return jumlah_kata >= panjang_min


def perlu_riset_dalam(pesan: str) -> bool:
    """
    True bila pengguna secara eksplisit meminta riset MENDALAM.

    Kata "riset"/"research"/"teliti" berarti pengguna ingin jawaban yang
    benar-benar digali, bukan sekadar satu pencarian.
    """
    return bool(re.search(r"\b(riset|research|teliti|penelitian|mendalam|detail|lengkap)\b", pesan or "", re.I))
