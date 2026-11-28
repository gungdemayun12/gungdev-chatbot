"""
judul.py — membuat JUDUL RIWAYAT dari TOPIK percakapan, bukan potongan prompt.

MASALAH YANG DIPECAHKAN
-----------------------
Dulu judul diambil dengan memotong ±48 karakter pertama pesan pengguna.
Untuk prompt panjang hasilnya tidak enak dibaca dan tidak menggambarkan
isi sesi:

    "Halo, saya mau tanya dong soal paket honeymoon di Bali untuk..."

Padahal Claude/ChatGPT memberi judul ringkas yang menyimpulkan topik:

    "Paket honeymoon Bali & harga"

JUDUL DIBUAT DUA TAHAP
----------------------
1. **Model** (bila tersedia): diberi beberapa pesan pertama sesi — pertanyaan
   pengguna DAN inti jawaban asisten — lalu diminta menulis 3–6 kata topik.
   Model bisa menyimpulkan ("rencana liburan ke Bali") dari percakapan yang
   tidak menyebut topiknya secara harfiah.
2. **Cadangan lokal** (`judul_lokal`): tanpa jaringan, tanpa model. Membuang
   kata sapaan ("halo", "tolong", "bisa"), membuang kalimat perintah
   ("carikan", "jelaskan"), lalu mengambil kata paling khas dari SELURUH
   percakapan — bukan hanya kalimat pertama. Hasilnya tetap judul topik yang
   wajar, bukan potongan prompt.

ATURAN JUDUL
------------
- 3–6 kata, maksimal 60 karakter, tanpa tanda kutip/emoji/penutup titik.
- Ditulis dengan huruf kapital di awal, sisanya huruf kecil — gaya judul
  riwayat yang tenang dan mudah dipindai mata.
- Tidak pernah kosong: bila semua gagal, dipakai "Percakapan baru".
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

MAKS_PANJANG = 60
MAKS_KATA = 6

# Kata yang hanya berfungsi sebagai pembuka/penyambung. Dibuang dari judul
# karena tidak menerangkan topik apa pun.
_KATA_ABAIKAN = {
    # sapaan & pengisi
    "halo", "hai", "hi", "hello", "hey", "selamat", "pagi", "siang", "sore",
    "malam", "gan", "bro", "sis", "kak", "bang", "min", "admin", "semuanya",
    "oke", "ok", "oh", "ya", "yaa", "nih", "sih", "dong", "deh", "kok", "kan",
    "lah", "pun", "aja", "saja", "gitu", "begitu", "gimana", "bagaimana",
    # permintaan / perintah
    "tolong", "mohon", "bantu", "bantuin", "bisa", "bisakah", "dapat",
    "carikan", "cari", "carinya", "temukan", "kasih", "berikan", "beri",
    "buatkan", "buat", "jelaskan", "terangkan", "sebutkan", "tuliskan",
    "tulis", "uraikan", "rekomendasikan", "rekomendasi", "sarankan",
    "ingin", "mau", "pengen", "pengin", "butuh", "perlu", "inginnya",
    "saya", "aku", "gue", "guee", "kami", "kita", "kamu", "anda", "mereka",
    "ada", "adakah", "apakah", "apa", "itu", "ini", "yang", "untuk", "buat",
    "dengan", "dan", "atau", "di", "ke", "dari", "pada", "dalam", "tentang",
    "soal", "mengenai", "seputar", "kalau", "bila", "jika", "supaya", "agar",
    "juga", "lagi", "masih", "sudah", "belum", "banyak", "beberapa",
    "sekali", "banget", "sangat", "paling", "lebih", "agak", "cukup",
    "sekarang", "nanti", "tadi", "besok", "kemarin",
    # kata kerja tanya yang terlalu umum untuk jadi judul
    "bagus", "baik", "cocok", "bagaimanakah", "seperti", "contoh", "contohnya",
    "minta", "sertakan", "sertakanlah", "beserta", "termasuk", "lengkap",
    "detail", "rinci", "jelas", "terbaru", "terkini", "terbaik", "murah",
    "penting", "utama", "umum", "secara", "beserta", "yaitu", "ialah",
}

# Kata yang menandakan judul sudah bagus bila muncul.
_BOBOT_PENTING = ("harga", "biaya", "cara", "perbandingan", "vs", "jadwal",
                  "tips", "contoh", "resep", "sejarah", "pengertian")

_RE_KODE = re.compile(r"```[\s\S]*?```", re.S)
_RE_MARKDOWN = re.compile(r"[#*_>`~\[\](){}|\\/]")
_RE_LAMPIRAN = re.compile(r"^\s*(_[^_]+_)\s*$", re.M)
_RE_KATA = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*", re.UNICODE)


def _bersihkan(teks: str) -> str:
    """Membuang markdown, blok kode, dan penanda lampiran."""
    teks = _RE_KODE.sub(" ", teks or "")
    teks = _RE_LAMPIRAN.sub(" ", teks)
    teks = _RE_MARKDOWN.sub(" ", teks)
    teks = teks.replace("—", " ").replace("–", " ")
    return re.sub(r"\s+", " ", teks).strip()


def _kata(teks: str) -> List[str]:
    """Kata bermakna (huruf/angka), tanpa kata pembuka/penyambung."""
    hasil = []
    for k in _RE_KATA.findall(_bersihkan(teks).lower()):
        if len(k) < 3:
            continue
        if k in _KATA_ABAIKAN:
            continue
        hasil.append(k)
    return hasil


def _rapikan(kata: Iterable[str]) -> str:
    """Menyusun kata menjadi judul rapi: kapital di awal, tanpa titik."""
    daftar: List[str] = []
    for k in kata:
        if k not in daftar:  # hindari kata dobel
            daftar.append(k)
    teks = " ".join(daftar).strip(" .:,;!?-\"'")
    if not teks:
        return ""
    if len(teks) > MAKS_PANJANG:
        potong = teks[:MAKS_PANJANG]
        spasi = potong.rfind(" ")
        teks = (potong[:spasi] if spasi > MAKS_PANJANG * 0.5 else potong).strip()
    return teks[:1].upper() + teks[1:]


def judul_lokal(teks: Iterable[str], maks_kata: int = MAKS_KATA) -> str:
    """
    Membuat judul dari TOPIK dengan cara lokal (tanpa model, tanpa jaringan).

    `teks` boleh berupa beberapa potongan. Urutan pemilihan kata:

      1. Kata KANDIDAT yang muncul di potongan terakhir (biasanya inti
         pertanyaan sesudah sapaan pembuka seperti "Halo, boleh tanya?").
      2. Kata dari potongan lain, urut kemunculan.

    Mengapa potongan terakhir didahulukan: pengguna sering membuka sesi
    dengan sapaan, lalu baru menyebut topiknya di pesan berikutnya. Tanpa
    ini, judulnya menjadi "Boleh tanya tentu silakan" — tidak menerangkan
    apa pun.

    Kata yang muncul berulang di percakapan diberi prioritas, karena
    pengulangan menandakan topik utama.
    """
    potongan = [t for t in (teks or []) if isinstance(t, str) and t.strip()]
    if not potongan:
        return "Percakapan baru"

    daftar_kata = [_kata(p) for p in potongan]
    semua = [k for bagian in daftar_kata for k in bagian]
    if not semua:
        return "Percakapan baru"

    # Hitung kemunculan untuk memberi prioritas pada topik utama.
    hitung: dict = {}
    for k in semua:
        hitung[k] = hitung.get(k, 0) + 1

    # Urutan pencarian: potongan terakhir dulu, lalu sisanya.
    urutan = list(reversed(daftar_kata))

    terpilih: List[str] = []
    terlihat: set = set()

    def tambah(kata_list: Iterable[str]) -> None:
        for k in kata_list:
            if len(terpilih) >= maks_kata:
                return
            if k in terlihat:
                continue
            terlihat.add(k)
            terpilih.append(k)

    # 1) Potongan terakhir (inti pertanyaan) lebih dulu.
    if urutan:
        tambah(urutan[0])
    # 2) Kata yang berulang di percakapan (topik utama).
    tambah([k for k in semua if hitung.get(k, 0) > 1])
    # 3) Sisanya, urut asli percakapan.
    tambah(semua)

    judul = _rapikan(terpilih)
    return judul or "Percakapan baru"


# ---------------------------------------------------------------------
# TAHAP 1: judul dari model
# ---------------------------------------------------------------------
def instruksi_judul() -> str:
    """Prompt sistem untuk model: minta judul topik, bukan ringkasan."""
    return (
        "Tugasmu HANYA menuliskan judul percakapan.\n"
        "Baca percakapan berikut, lalu tulis 3-6 kata yang menyimpulkan "
        "TOPIK yang dibahas — seperti judul riwayat chat.\n\n"
        "Aturan:\n"
        "1. Balas HANYA judulnya. Tanpa tanda kutip, tanpa penjelasan, "
        "tanpa titik di akhir, tanpa emoji.\n"
        "2. Maksimal 60 karakter. Pakai bahasa yang sama dengan pengguna.\n"
        "3. Sebut inti topiknya (objek + hal yang dibahas). Jangan menyalin "
        "kalimat pengguna apa adanya.\n"
        "4. Jangan memakai kata sapaan atau kata perintah seperti 'tolong', "
        "'carikan', 'bisa', 'halo'.\n"
        "5. Jangan mengarang isi di luar percakapan.\n"
        "6. JANGAN menjelaskan rencanamu dan jangan berpikir panjang. "
        "Langsung tulis judulnya di baris pertama, karena jawaban yang "
        "terlalu panjang akan terpotong.\n\n"
        "Contoh:\n"
        "- Pengguna tanya paket honeymoon Bali beserta harga -> "
        "Paket honeymoon Bali\n"
        "- Pengguna minta cara membuat kue bolu kukus yang lembut -> "
        "Cara membuat bolu kukus lembut\n"
        "- Pengguna tanya beda IndexedDB dan localStorage -> "
        "IndexedDB vs localStorage\n\n"
        "Sekarang tulis judulnya."
    )


def bahan_percakapan(pesan: Iterable[dict], maks_pesan: int = 4, maks_karakter: int = 700) -> str:
    """
    Menyusun potongan percakapan untuk model: pertanyaan pengguna dan
    inti jawaban asisten. Jawaban dipotong pendek karena yang dibutuhkan
    hanya topiknya.
    """
    baris: List[str] = []
    diambil = 0
    for m in pesan or []:
        if not isinstance(m, dict):
            continue
        peran = m.get("role")
        isi = _bersihkan(str(m.get("content") or ""))
        if not isi:
            continue
        if peran == "user":
            isi = isi[: maks_karakter // 2]
            label = "Pengguna"
        elif peran == "assistant":
            isi = isi[: maks_karakter // 3]
            label = "Asisten"
        else:
            continue
        baris.append(f"{label}: {isi}")
        diambil += 1
        if diambil >= maks_pesan:
            break
    return "\n".join(baris)


def bersihkan_judul(mentah: Optional[str]) -> str:
    """
    Membersihkan keluaran model menjadi judul yang layak.

    Model kadang menulis "Judul: \"Paket Honeymoon Bali\"." atau
    menambahkan penjelasan. Fungsi ini membuang semua itu. Bila hasilnya
    tidak masuk akal (terlalu pendek/panjang), dikembalikan string kosong
    supaya pemanggil memakai cadangan lokal.
    """
    teks = (mentah or "").strip()
    if not teks:
        return ""

    # 1) Bila model menyebut judulnya secara eksplisit, ambil yang itu.
    #    Ditelusuri SEBELUM memotong baris, karena penalaran model
    #    biasanya satu paragraf panjang.
    pola = re.search(
        r"(?:judul|title)\s*(?:percakapan|chat|nya)?\s*(?:adalah|is|:|=)\s*[\"“']?\s*"
        r"([^\"“”'\n]{4,80})",
        teks,
        flags=re.I,
    )
    if pola:
        teks = pola.group(1).strip()

    # 2) Ambil baris pertama yang berisi (bila model menulis per baris).
    elif "\n" in teks:
        for baris in teks.splitlines():
            baris = baris.strip()
            if baris:
                teks = baris
                break

    # 3) Buang awalan label.
    teks = re.sub(r"^(judul|title)\s*[:：-]\s*", "", teks, flags=re.I)
    # 4) Buang tanda kutip/penutup.
    teks = teks.strip(" \"'`“”‘’*_#.!,;:")
    teks = re.sub(r"\s+", " ", teks).strip()
    # 5) Buang emoji & simbol yang bukan huruf/angka. Judul riwayat harus
    #    tenang dan mudah dipindai; emoji dari model tidak diinginkan.
    teks = "".join(
        c for c in teks
        if c.isprintable() and (c.isalnum() or c in " -&+/.',:")
    ).strip()
    teks = re.sub(r"\s+", " ", teks).strip()

    # 6) Model penalar kadang berpikir dalam bahasa Inggris. Judul yang
    #    baik memakai bahasa pengguna, jadi narasi Inggris ditolak.
    if _tampak_bahasa_inggris(teks):
        return ""

    if len(teks) < 4:
        return ""
    if len(teks) > MAKS_PANJANG:
        potong = teks[:MAKS_PANJANG]
        spasi = potong.rfind(" ")
        teks = (potong[:spasi] if spasi > MAKS_PANJANG * 0.5 else potong).strip()
    # Terlalu panjang = kemungkinan model menyalin kalimat pengguna apa
    # adanya, bukan menyimpulkan topik. Judul yang baik ringkas.
    if len(teks.split()) > 8:
        return ""
    if len(teks) > 42:
        return ""
    # Judul harus benar-benar punya huruf, bukan sisa tanda baca.
    if not re.search(r"[^\W\d_]", teks, re.UNICODE):
        return ""
    return teks[:1].upper() + teks[1:]


# Kata fungsi bahasa Inggris yang praktis tidak muncul di judul Indonesia.
_KATA_INGGRIS = {
    "the", "we", "need", "to", "output", "title", "summarizing", "topic",
    "conversation", "user", "asks", "and", "price", "so", "is", "that",
    "this", "should", "be", "let", "me", "write", "of", "about",
    "here", "then", "final", "answer", "summarize", "must", "only",
}


def _tampak_bahasa_inggris(teks: str) -> bool:
    """
    True bila teks jelas narasi bahasa Inggris, bukan judul singkat.

    Judul Indonesia yang kebetulan memuat kata Inggris (mis. "IndexedDB
    vs localStorage") tetap lolos karena tidak memuat kata fungsi narasi
    dalam jumlah berarti.
    """
    kata = [k for k in _RE_KATA.findall((teks or "").lower()) if len(k) > 1]
    if len(kata) < 3:
        return False
    inggris = sum(1 for k in kata if k in _KATA_INGGRIS)
    return inggris >= 3 and inggris / len(kata) > 0.4
