"""
uji_gambar.py — pengujian pembuatan gambar oleh AI.

Yang diuji (semua TANPA memanggil layanan gambar sungguhan kecuali
bagian yang memang perlu, dan bagian itu diberi penanda jelas):

  1. Pengenalan niat: permintaan gambar dikenali, PERTANYAAN TENTANG
     gambar TIDAK dikenali (agar jatah gambar tidak terbuang).
  2. Deskripsi gambar: kata perintah dibuang, gaya tidak ditimpa.
  3. Jatah gambar TERPISAH dari jatah chat (inti permintaan pemilik
     situs: "jangan boros di gambar saja").
  4. Gambar gagal TIDAK memakan jatah dan TIDAK menggagalkan chat.
  5. Gambar berhasil dicatat sebagai jatah gambar, bukan jatah chat.
  6. Tamu tidak mendapat gambar, tetapi tetap bisa mengobrol.
  7. Kontrak lama tidak berubah: chat biasa tetap {"reply": "..."}.

Jalankan: python uji_gambar.py
"""
import asyncio
import io
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HASIL = []


def cek(nama, lulus, info=""):
    HASIL.append({"nama": nama, "lulus": bool(lulus)})
    print(("LULUS  " if lulus else "GAGAL  ") + nama + (f" — {info}" if info else ""))


def baca(nama):
    """Membaca modul sebagai teks (main.py berawalan BOM)."""
    return io.open(nama, encoding="utf-8-sig").read()


# =====================================================================
print("=== 1. PENGENALAN NIAT: PERMINTAAN GAMBAR ===")
# =====================================================================
import gambar

PERMINTAAN = [
    "buatkan gambar kucing oranye sedang tidur di sofa",
    "gambarkan pemandangan pantai saat matahari terbenam",
    "tolong buat ilustrasi logo warung kopi",
    "bikinin gambar poster konser musik",
    "buatkan foto sunset di Bali",
    "desain logo kucing minimalis",
    "buatkan gambar rumah gaya minimalis",
    "bikin gambar kartun anak sekolah",
    "generate gambar naga terbang",
    "lukiskan pemandangan sawah",
]
for t in PERMINTAAN:
    h = gambar.niat_gambar(t)
    cek(f"dikenali: {t[:46]}", h["buat"] is True, h["alasan"])

# Menyunting gambar lampiran.
for t in [
    "edit gambar ini jadi gaya anime",
    "hapus latar belakang fotonya",
    "ubah gambar ini jadi hitam putih",
]:
    h = gambar.niat_gambar(t, ada_lampiran_gambar=True)
    cek(f"dikenali (sunting): {t[:44]}", h["buat"] and h["sunting"], h["alasan"])

# =====================================================================
print("\n=== 2. TIDAK SALAH KIRA: PERTANYAAN TENTANG GAMBAR ===")
# =====================================================================
# Ini yang paling penting: bila salah kira, jatah gambar pengguna
# terbuang hanya karena ia bertanya.
BUKAN_PERMINTAAN = [
    "apa itu gambar vektor?",
    "jelaskan cara membuat gambar dengan AI",
    "berapa harga gambar digital?",
    "gambaran umum ekonomi Indonesia",
    "sebutkan contoh gambar ilustrasi",
    "bagaimana cara buat logo yang bagus?",
    "apa perbedaan gambar dan foto?",
    "tips membuat gambar yang menarik",
    "pengertian ilustrasi dalam desain",
    "belajar desain grafis untuk pemula",
    "halo apa kabar",
    "buat ringkasan artikel ini",
    "tolong jelaskan apa itu poster",
    "kenapa gambar saya blur?",
    "mengapa foto saya gelap?",
]
for t in BUKAN_PERMINTAAN:
    h = gambar.niat_gambar(t)
    cek(f"bukan gambar: {t[:46]}", h["buat"] is False, h["alasan"])

# =====================================================================
print("\n=== 3. DESKRIPSI GAMBAR ===")
# =====================================================================
# Deskripsi kini DITERJEMAHKAN ke bahasa Inggris. Ini bukan hiasan: model
# gambar memahami Inggris jauh lebih tepat, dan tanpa terjemahan kata
# "sedang tidur" diabaikan sehingga kucing digambar BERDIRI.
d = gambar.deskripsi_gambar("tolong buatkan gambar kucing oranye sedang tidur di sofa")
cek("kata perintah dibuang", "tolong" not in d and "buatkan" not in d, d)
cek("objek diterjemahkan ke Inggris", "cat" in d, d)
cek("warna diterjemahkan ke Inggris", "orange" in d, d)
# INTI PERBAIKAN: pose "tidur" harus muncul eksplisit.
cek("pose 'tidur' menjadi kata Inggris", "asleep" in d, d)
cek("pose dipertegas berbaring", "lying down" in d, d)
cek("mata tertutup disebut", "eyes closed" in d, d)
cek("latar 'di sofa' ikut terbawa", "sofa" in d, d)
cek("gaya foto bawaan ditambahkan", "photography" in d, d)
cek("minta negatif (tanpa teks acak)", "no text" in d, d)
cek("tidak ada kata Indonesia yang tertinggal", "sedang" not in d and " di " not in d, d)

d2 = gambar.deskripsi_gambar("buatkan gambar pemandangan pantai gaya anime")
cek("gaya pengguna tidak ditimpa", "anime" in d2, d2)
cek("gaya anime tidak diberi gaya foto", "professional photography" not in d2, d2)

d3 = gambar.deskripsi_gambar("gambarkan matahari")
cek("deskripsi tidak kosong", bool(d3.strip()), d3)
cek("deskripsi dibatasi panjangnya", len(d3) <= 900)
cek("deskripsi tetap deskripsi matahari", "sun" in d3, d3)

# Frasa terpanjang harus menang: "anak kucing" -> "kitten", bukan
# "child" + "cat".
d4 = gambar.deskripsi_gambar("buatkan gambar anak kucing")
cek("frasa terpanjang menang (anak kucing)", "kitten" in d4, d4)

# Kata yang tidak dikenal TIDAK boleh hilang begitu saja.
d5 = gambar.deskripsi_gambar("buatkan gambar zebra ungu berjalan")
cek("kata tak dikenal tetap dibawa", "zebra" in d5, d5)
cek("warna 'ungu' diterjemahkan", "purple" in d5, d5)
cek("pose 'berjalan' diterjemahkan", "walking" in d5 or "jalan" in d5, d5)

# Menyunting gambar: kata "edit" harus menonjol, gaya foto tidak perlu.
d6 = gambar.deskripsi_gambar("ubah gambar ini jadi hitam putih", sunting=True)
cek("suntingan menyebut edit", "edit" in d6.lower(), d6)
cek("suntingan menyebut hitam putih", "black and white" in d6, d6)

# ---------------------------------------------------------------------
# KARYA DESAIN (poster / pricelist / logo)
# ---------------------------------------------------------------------
# Kasus nyata yang gagal sebelum ini: permintaan "poster pricelist"
# menghasilkan foto semangkuk mie. Penyebabnya: deskripsi diberi gaya
# "professional photography" dan negatif "no text", padahal poster
# justru butuh tata letak dan teks.
POSTER = (
    "buatkan saya sebuah poster untuk pricelist warung sayaa, yang dimana "
    "ada tipat cantok, es gula, mie goreng, rujak bali, minuman, jajan, "
    "dll nya yaa, buatkan pioster pricelist yang bgfaus yaa"
)
dp = gambar.deskripsi_gambar(POSTER)
cek("poster TIDAK diberi gaya foto", "professional photography" not in dp, dp)
cek("poster diberi gaya desain", "graphic design" in dp or "layout" in dp, dp)
cek("poster TIDAK dilarang berteks", "no text" not in dp, dp)
cek("poster tetap memuat judul poster", "poster" in dp, dp)
cek("poster tetap memuat isi warung", "warung" in dp, dp)
cek("poster tetap memuat nama makanan", "tipat" in dp and "rujak" in dp, dp)
# Salah ketik dibersihkan supaya tidak mengaburkan isi permintaan.
cek("salah ketik 'pioster' diperbaiki", "pioster" not in dp, dp)
cek("salah ketik 'bgfaus' diperbaiki", "bgfaus" not in dp, dp)
cek("salah ketik 'sayaa' diperbaiki", "sayaa" not in dp, dp)
cek("basa-basi 'yaaa' dibuang", "yaaa" not in dp, dp)
cek("kata 'dll nya yaa' dibuang", "dll" not in dp, dp)
# Daftar harga harus dapat arahan STRUKTUR, bukan hanya "poster".
cek("daftar harga diberi arahan baris harga", "price list" in dp or "leader lines" in dp, dp)

# Logo juga karya desain, tetapi bukan daftar harga.
dl = gambar.deskripsi_gambar("desain logo kopi hitam putih")
cek("logo diberi gaya desain", "graphic design" in dl or "layout" in dl, dl)
cek("logo TIDAK diberi arahan daftar harga", "leader lines" not in dl, dl)

# FOTO tetap memakai gaya foto seperti sebelumnya (tidak ikut berubah).
df = gambar.deskripsi_gambar("buatkan gambar kucing sedang tidur di sofa")
cek("foto tetap memakai gaya foto", "professional photography" in df, df)
cek("foto tetap memakai negatif 'no text'", "no text" in df, df)

# Pesan pendamping harus JUJUR soal teks di poster, dan TIDAK
# menyebutkannya untuk foto biasa.
pp = gambar.pesan_berhasil(dp)
cek("pesan poster jujur soal tulisan", "hiasan" in pp or "terbaca" in pp, pp)
cek("pesan poster menawarkan versi teks", "teks" in pp, pp)
pf = gambar.pesan_berhasil(df)
cek("pesan foto tidak menyebut poster", "pricelist" not in pf and "hiasan" not in pf, pf)
cek("pesan tidak membocorkan nama penyedia", "pollinations" not in pp.lower())

# Pembersih kata tidak boleh membuang kata yang penting.
for kata in ("tipat", "rujak", "warung", "kucing", "goreng", "mie"):
    cek(f"kata '{kata}' dianggap berarti", gambar._kata_berarti(kata), kata)
cek("kata acak 'bgfaus' tidak dianggap berarti (sebelum koreksi)", gambar._SALAH_KETIK.get("bgfaus") == "bagus")
cek("deskripsi kosong tidak membuat sampah", gambar._bersihkan_kata_sampah("") == "")


# =====================================================================
print("\n=== 4. JATAH GAMBAR TERPISAH DARI JATAH CHAT ===")
# =====================================================================
# server_uji mengganti httpx global, jadi modul dieksekusi dalam konteks
# tiruan. Untuk jatah, cukup uji modul usage dengan Redis tiruan.
import server_uji  # noqa: E402  (menyiapkan tiruan lebih dulu)

usage = server_uji.main.usage

# Akun uji KHUSUS modul ini. Sengaja berbeda dari akun uji lain
# (uji_api/uji_browser memakai ...001 dan ...002) agar pengujian jatah
# di sini tidak mengotori hitungan pengujian lain.
SUB = "900000000000000009"


async def uji_jatah():
    await usage.catat_request(tokens=100, model="uji", sub=SUB)
    await usage.catat_request(tokens=100, model="uji", sub=SUB)

    j_chat = await usage.periksa_jatah(SUB)
    cek("pemakaian chat tercatat", j_chat["terpakai"] == 2, str(j_chat["terpakai"]))

    j_gambar_awal = await usage.periksa_jatah_gambar(SUB)
    cek(
        "gambar mulai dari 0 walau chat sudah 2",
        j_gambar_awal["terpakai"] == 0,
        str(j_gambar_awal["terpakai"]),
    )
    cek(
        "batas gambar lebih kecil dari batas chat",
        j_gambar_awal["batas"] < j_chat["batas"],
        f"gambar={j_gambar_awal['batas']} chat={j_chat['batas']}",
    )
    cek("boleh membuat gambar", j_gambar_awal["boleh"] is True)

    # Buat 3 gambar -> jatah gambar penuh terpakai.
    for _ in range(3):
        await usage.catat_gambar(SUB)

    j_gambar = await usage.periksa_jatah_gambar(SUB)
    cek("3 gambar tercatat", j_gambar["terpakai"] == 3, str(j_gambar["terpakai"]))
    cek("jatah gambar habis -> ditolak", j_gambar["boleh"] is False)
    cek("alasan = gambar", j_gambar["alasan"] == "gambar", str(j_gambar["alasan"]))

    # INTI: chat TIDAK terpengaruh oleh habisnya jatah gambar.
    j_chat_lagi = await usage.periksa_jatah(SUB)
    cek(
        "chat tetap boleh walau jatah gambar habis",
        j_chat_lagi["boleh"] is True,
    )
    cek(
        "jatah chat TIDAK berkurang oleh gambar",
        j_chat_lagi["terpakai"] == 2,
        f"chat terpakai={j_chat_lagi['terpakai']} (harus tetap 2)",
    )

    # Sebaliknya: chat banyak tidak mengurangi jatah gambar.
    for _ in range(5):
        await usage.catat_request(tokens=100, model="uji", sub=SUB)
    j_gambar_lagi = await usage.periksa_jatah_gambar(SUB)
    cek(
        "jatah gambar tidak pulih/berubah karena chat",
        j_gambar_lagi["terpakai"] == 3,
        str(j_gambar_lagi["terpakai"]),
    )


asyncio.run(uji_jatah())

# =====================================================================
print("\n=== 5. TANDA AIR LAYANAN GAMBAR DIBUANG ===")
# =====================================================================
# Layanan gambar gratis selalu menempelkan tanda air di pojok kanan
# bawah, dan nama penyedia TIDAK boleh tampil di UI. Karena itu strip
# bawah dipotong. Uji ini memastikan pemangkasan bekerja DAN bahwa
# kegagalan pemangkasan tidak merusak gambar.
from io import BytesIO  # noqa: E402

from PIL import Image  # noqa: E402

_png = BytesIO()
Image.new("RGB", (200, 200), (120, 90, 60)).save(_png, format="PNG")
_png_asli = _png.getvalue()

_potong = gambar._pangkas_bawah(_png_asli)
cek("gambar dipangkas (byte berbeda)", _potong != _png_asli)
with Image.open(BytesIO(_png_asli)) as _a, Image.open(BytesIO(_potong)) as _b:
    cek("lebar tetap sama", _b.size[0] == _a.size[0], f"{_a.size} -> {_b.size}")
    cek("tinggi berkurang", _b.size[1] < _a.size[1], f"{_a.size} -> {_b.size}")
    cek(
        "tinggi tidak terpotong berlebihan",
        _b.size[1] >= int(_a.size[1] * 0.9),
        f"{_a.size[1]} -> {_b.size[1]}",
    )
cek("hasil pemangkasan masih gambar sah", _potong[:3] == b"\xff\xd8\xff" or _potong[:8] == b"\x89PNG\r\n\x1a\n")
cek("data rusak dikembalikan apa adanya", gambar._pangkas_bawah(b"bukan gambar") == b"bukan gambar")
cek("gambar kosong tidak melempar exception", gambar._pangkas_bawah(b"") == b"")

# --- Watermark milik aplikasi ---
# Tanda air penyedia dibuang (pangkas), lalu diganti tanda air "gungdev".
_wm = gambar._gambar_watermark(_png_asli)
cek("watermark mengubah gambar", _wm != _png_asli)
with Image.open(BytesIO(_wm)) as _w:
    cek("watermark tidak mengubah ukuran", _w.size == (200, 200), str(_w.size))
    # Pojok kanan bawah harus berbeda dari gambar polos: di situlah teks
    # dan titik merek digambar.
    _polos = Image.open(BytesIO(_png_asli)).convert("RGB")
    _kanan_bawah = _w.convert("RGB").crop((130, 160, 200, 200))
    _kanan_bawah_polos = _polos.crop((130, 160, 200, 200))
    cek(
        "ada jejak watermark di pojok kanan bawah",
        list(_kanan_bawah.getdata()) != list(_kanan_bawah_polos.getdata()),
    )
    # Pojok kiri atas harus TETAP: watermark tidak boleh menutupi gambar.
    #
    # Catatan: JPEG bersifat "lossy", jadi menyimpan ulang mengubah
    # SETIAP piksel sedikit. Karena itu yang diuji bukan "identik", tetapi
    # "perubahannya kecil" — jauh lebih kecil daripada jejak teks di
    # pojok kanan bawah.
    _kiri_atas = list(_w.convert("RGB").crop((0, 0, 60, 40)).getdata())
    _kiri_atas_polos = list(_polos.crop((0, 0, 60, 40)).getdata())
    _selisih_kiri = sum(
        abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2])
        for a, b in zip(_kiri_atas, _kiri_atas_polos)
    )
    cek(
        "watermark tidak menutupi bagian lain gambar",
        _selisih_kiri < 60 * 40 * 12,
        f"selisih={_selisih_kiri}",
    )
cek("watermark data rusak aman", gambar._gambar_watermark(b"bukan gambar") == b"bukan gambar")
cek("watermark kosong aman", gambar._gambar_watermark(b"") == b"")
cek("teks watermark = nama aplikasi", gambar.WATERMARK_TEKS == "gungdev", gambar.WATERMARK_TEKS)
cek(
    "teks watermark bukan nama penyedia",
    "pollinations" not in gambar.WATERMARK_TEKS.lower(),
)

# =====================================================================
print("\n=== 6. TAMU TIDAK MENDAPAT GAMBAR ===")
# =====================================================================


async def uji_tamu():
    jt = await usage.periksa_jatah_gambar(None)
    cek("tamu tidak boleh membuat gambar", jt["boleh"] is False)
    cek("batas gambar tamu = 0", jt["batas"] == 0, str(jt["batas"]))
    pesan = usage.pesan_jatah_gambar_habis(jt)
    cek("pesan tamu menyebut perlu login", "login" in pesan.lower(), pesan[:90])

    j_chat_tamu = await usage.periksa_jatah(None)
    cek("tamu TETAP boleh mengobrol", j_chat_tamu["boleh"] is True)


asyncio.run(uji_tamu())

# =====================================================================
print("\n=== 7. PESAN JATAH GAMBAR HABIS (nada & isi) ===")
# =====================================================================
pesan = usage.pesan_jatah_gambar_habis(
    {"sub": SUB, "batas": 3, "reset_detik": 7200, "alasan": "gambar"}
)
cek("menyebut jumlah gambar", "3 gambar" in pesan, pesan[:80])
cek("menyebut kapan pulih", "jam" in pesan, pesan[:120])
cek("menegaskan obrolan tidak terpengaruh", "tetap" in pesan.lower(), pesan[-90:])
cek(
    "tidak menyebut nama penyedia",
    not any(x in pesan.lower() for x in ("groq", "openrouter", "pollinations", "nvidia")),
)

# =====================================================================
print("\n=== 8. GAGAL MEMBUAT GAMBAR: JATAH TIDAK TERPAKAI ===")
# =====================================================================


async def uji_gagal():
    modul = server_uji.main.gambar_mod

    asli = modul.buat_gambar

    async def gagal_selalu(deskripsi, **kw):
        return {"ok": False, "pesan": "Layanan sedang ramai.", "galat": "status 402"}

    modul.buat_gambar = gagal_selalu
    # Akun baru: jatah gambar SUB sudah habis di bagian sebelumnya,
    # dan bagian ini menguji kegagalan layanan, bukan jatah habis.
    sub = "300000000000000003"
    try:
        sebelum = await usage.periksa_jatah_gambar(sub)
        hasil = await server_uji.main.siapkan_gambar(
            server_uji.main.ChatRequest(message="buatkan gambar kucing lucu"), sub
        )
        sesudah = await usage.periksa_jatah_gambar(sub)
        cek("hasil jenis 'gagal'", hasil and hasil["jenis"] == "gagal", str(hasil and hasil["jenis"]))
        cek(
            "jatah gambar TIDAK terpakai saat gagal",
            sesudah["terpakai"] == sebelum["terpakai"],
            f"{sebelum['terpakai']} -> {sesudah['terpakai']}",
        )
        cek("tidak melempar exception", True)
    finally:
        modul.buat_gambar = asli


asyncio.run(uji_gagal())

# =====================================================================
print("\n=== 9. BERHASIL: JATAH GAMBAR NAIK, JATAH CHAT TETAP ===")
# =====================================================================


async def uji_berhasil():
    modul = server_uji.main.gambar_mod
    asli = modul.buat_gambar

    async def berhasil_palsu(deskripsi, **kw):
        return {
            "ok": True,
            "data_url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQ==",
            "deskripsi": deskripsi,
        }

    modul.buat_gambar = berhasil_palsu
    sub = "200000000000000002"
    try:
        chat_awal = await usage.periksa_jatah(sub)
        hasil = await server_uji.main.siapkan_gambar(
            server_uji.main.ChatRequest(message="buatkan gambar kucing lucu"), sub
        )
        chat_akhir = await usage.periksa_jatah(sub)
        gambar_akhir = await usage.periksa_jatah_gambar(sub)

        cek("hasil jenis 'berhasil'", hasil and hasil["jenis"] == "berhasil")
        cek("ada data_url gambar", (hasil or {}).get("data_url", "").startswith("data:image/"))
        cek("jatah gambar bertambah", gambar_akhir["terpakai"] == 1, str(gambar_akhir["terpakai"]))
        cek(
            "jatah CHAT tidak bertambah oleh gambar",
            chat_akhir["terpakai"] == chat_awal["terpakai"],
            f"{chat_awal['terpakai']} -> {chat_akhir['terpakai']}",
        )
        cek("pesan pendamping tidak kosong", bool((hasil or {}).get("pesan", "").strip()))
    finally:
        modul.buat_gambar = asli


asyncio.run(uji_berhasil())

# =====================================================================
print("\n=== 10. CHAT BIASA TIDAK MEMBUAT GAMBAR ===")
# =====================================================================


async def uji_chat_biasa():
    hasil = await server_uji.main.siapkan_gambar(
        server_uji.main.ChatRequest(message="halo, apa kabar?"), SUB
    )
    cek("chat biasa -> None (tanpa gambar)", hasil is None, str(hasil))


asyncio.run(uji_chat_biasa())

# =====================================================================
print("\n=== 11. KONTRAK API TIDAK BERUBAH ===")
# =====================================================================
main_src = baca("main.py")
cek("ChatResponse masih punya reply", "reply: str" in main_src)
cek("ChatResponse punya field gambar opsional", "gambar: Optional[dict] = None" in main_src)
cek("ChatRequest punya buat_gambar opsional", "buat_gambar: bool = Field(" in main_src)
cek("endpoint /chat tidak diubah namanya", '@app.post("/chat"' in main_src)
cek("endpoint /chat/stream tetap ada", '@app.post("/chat/stream"' in main_src)
cek("endpoint /judul tetap ada", '@app.post("/judul"' in main_src)
cek("gambar tidak memakai jatah chat", "catat_request" not in main_src.split("siapkan_gambar")[1].split("@app.post")[0])

# Nama penyedia gambar tidak boleh muncul di kode yang mengirim ke UI.
cek("nama layanan gambar tidak ada di main.py", "pollinations" not in main_src.lower())
gambar_src = baca("gambar.py")
cek("nama layanan hanya di modul internal", "pollinations" in gambar_src.lower())

# =====================================================================
print("\n=== 12. CAPABILITIES MENGAKUI KEMAMPUAN GAMBAR ===")
# =====================================================================
cek("capabilities menyebut buat_gambar", '"buat_gambar": True' in main_src)
cek("capabilities menyebut jatah gambar", '"jatah_gambar"' in main_src)

# =====================================================================
gagal = [h for h in HASIL if not h["lulus"]]
print(f"\nHASIL: {len(HASIL) - len(gagal)}/{len(HASIL)} lulus")
if gagal:
    print("GAGAL:")
    for h in gagal:
        print("  -", h["nama"])
sys.exit(0 if not gagal else 1)
