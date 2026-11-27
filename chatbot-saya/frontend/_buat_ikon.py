"""_buat_ikon.py — membuat semua ukuran logo dari logo asli pengguna.

Prinsip: logo TIDAK digambar ulang. Semua berkas di bawah ini adalah
crop langsung dari "White-Chested Fox Logo.png", supaya bentuk rubahnya
persis seperti aslinya.

Yang dihasilkan (semua masuk ke public/):
  logo-512.png          rubah polos, latar transparan (dipakai di UI)
  logo-192.png          versi kecil untuk layar biasa/1x
  icon-192.png          ubin gelap membulat -> favicon PNG
  icon-512.png          ubin gelap membulat -> manifest
  icon-maskable-512.png ubin penuh (Android memotong tepi sendiri)
  apple-touch-icon.png  180px, tanpa sudut membulat (iOS membulatkan)
  og-image.png          1200x630 pratinjau saat tautan dibagikan

Jalankan sekali saja bila logo sumber berubah (dari folder frontend):
  python _buat_ikon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).parent / "public"
SUMBER = PUBLIC / "White-Chested Fox Logo.png"

GELAP = (28, 27, 26)
GELAP_TERANG = (42, 40, 38)

# Kotak potong diambil dari logo asli (1448x1086). Rubahnya berada di
# tengah dengan ruang kosong lebar di kiri-kanan; kotak ini memuat
# telinga sampai ekor dengan sedikit napas di tepi.
KOTAK = (556, 210, 900, 885)

AMBANG_PUTIH = 242


def _rubah_transparan() -> Image.Image:
    """Crop rubah + jadikan latar putih transparan (bukan dipotong)."""
    asli = Image.open(SUMBER).convert("RGBA").crop(KOTAK)
    piksel = asli.load()
    lebar, tinggi = asli.size
    for y in range(tinggi):
        for x in range(lebar):
            r, g, b, _ = piksel[x, y]
            if r >= AMBANG_PUTIH and g >= AMBANG_PUTIH and b >= AMBANG_PUTIH:
                piksel[x, y] = (r, g, b, 0)
    return asli


def _latar_gradasi(ukuran: tuple[int, int]) -> Image.Image:
    lebar, tinggi = ukuran
    gambar = Image.new("RGB", ukuran, GELAP)
    garis = ImageDraw.Draw(gambar)
    for i in range(tinggi):
        t = i / max(1, tinggi - 1)
        warna = tuple(
            int(GELAP[k] + (GELAP_TERANG[k] - GELAP[k]) * (1 - t)) for k in range(3)
        )
        garis.line([(0, i), (lebar, i)], fill=warna)
    return gambar


def _tempel_dengan_bingkai(
    latar: Image.Image, rubah: Image.Image, skala: float, tebal: int
) -> None:
    """
    Menempelkan rubah dengan "cincin" putih tipis di belakangnya.

    Perlu karena sebagian garis logo berwarna hampir hitam; di atas ubin
    gelap garis itu bisa menyatu dengan latar.
    """
    lebar, tinggi = latar.size
    sisi = int(min(lebar, tinggi) * skala)
    kecil = rubah.resize((sisi, sisi), Image.LANCZOS)
    posisi = ((lebar - sisi) // 2, (tinggi - sisi) // 2)

    cincin = Image.new("RGBA", kecil.size, (255, 255, 255, 0))
    cincin.putalpha(kecil.getchannel("A"))
    for dx in range(-tebal, tebal + 1):
        for dy in range(-tebal, tebal + 1):
            if dx or dy:
                latar.paste(
                    (255, 255, 255),
                    (posisi[0] + dx, posisi[1] + dy),
                    cincin,
                )
    latar.paste(kecil, posisi, kecil)


def _ubin(ukuran: int, rubah: Image.Image, skala: float, radius_persen: float) -> Image.Image:
    dasar = _latar_gradasi((ukuran, ukuran))
    if radius_persen > 0:
        topeng = Image.new("L", (ukuran, ukuran), 0)
        ImageDraw.Draw(topeng).rounded_rectangle(
            [0, 0, ukuran - 1, ukuran - 1],
            radius=int(ukuran * radius_persen),
            fill=255,
        )
        dasar.putalpha(topeng)
    hasil = dasar.convert("RGBA")
    _tempel_dengan_bingkai(hasil, rubah, skala, max(1, ukuran // 120))
    return hasil


def main() -> None:
    rubah = _rubah_transparan()
    print("rubah dipotong:", rubah.size)

    # A. Logo polos berlatar transparan, untuk dipakai di antarmuka.
    for sisi, nama in ((512, "logo-512.png"), (192, "logo-192.png")):
        kotak = Image.new("RGBA", (sisi, sisi), (0, 0, 0, 0))
        isi = rubah.copy()
        isi.thumbnail((sisi, sisi), Image.LANCZOS)
        kotak.paste(isi, ((sisi - isi.width) // 2, (sisi - isi.height) // 2), isi)
        kotak.save(PUBLIC / nama, optimize=True)
        print("dibuat:", nama, kotak.size, f"{kotak.size[0]}px")

    # B. Ikon bersudut membulat (tab browser, manifest).
    for sisi, nama in ((192, "icon-192.png"), (512, "icon-512.png")):
        hasil = _ubin(sisi, rubah, skala=0.74, radius_persen=0.23)
        hasil.save(PUBLIC / nama, optimize=True)
        print("dibuat:", nama)

    # C. Maskable (Android): latar sampai tepi, rubah lebih kecil.
    hasil = _ubin(512, rubah, skala=0.55, radius_persen=0.0)
    hasil.save(PUBLIC / "icon-maskable-512.png", optimize=True)
    print("dibuat: icon-maskable-512.png")

    # D. Apple touch icon: persegi penuh, tanpa transparan.
    sisi = 180
    hasil = _latar_gradasi((sisi, sisi)).convert("RGBA")
    _tempel_dengan_bingkai(hasil, rubah, 0.76, max(1, sisi // 120))
    hasil.convert("RGB").save(PUBLIC / "apple-touch-icon.png", optimize=True)
    print("dibuat: apple-touch-icon.png")

    # E. Pratinjau tautan (1200x630).
    lebar, tinggi = 1200, 630
    og = _latar_gradasi((lebar, tinggi)).convert("RGBA")
    _tempel_dengan_bingkai(og, rubah, 0.52, 3)
    og.convert("RGB").save(PUBLIC / "og-image.png", optimize=True)
    print("dibuat: og-image.png")


if __name__ == "__main__":
    main()
