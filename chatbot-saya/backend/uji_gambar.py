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
d = gambar.deskripsi_gambar("tolong buatkan gambar kucing oranye sedang tidur di sofa")
cek("kata perintah dibuang", "tolong" not in d and "buatkan" not in d, d)
cek("isi permintaan tetap ada", "kucing oranye" in d, d)
cek("gaya bawaan ditambahkan", "high quality" in d, d)

d2 = gambar.deskripsi_gambar("buatkan gambar pemandangan pantai gaya anime")
cek("gaya pengguna tidak ditimpa", "anime" in d2 and "high quality" not in d2, d2)

d3 = gambar.deskripsi_gambar("gambarkan matahari")
cek("deskripsi tidak kosong", bool(d3.strip()), d3)
cek("deskripsi dibatasi panjangnya", len(d3) <= 900)


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
