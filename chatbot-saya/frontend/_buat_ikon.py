"""_buat_ikon.py — membuat semua ukuran logo dari logo asli pengguna.

Prinsip:
  1. Logo TIDAK digambar ulang. Semua berkas adalah crop langsung dari
     "White-Chested Fox Logo.png", jadi bentuk rubahnya persis aslinya.
  2. Latar dibuat putih OTOMATIS dari kanal ALPHA gambar itu sendiri,
     bukan dengan menghapus piksel yang berwarna putih. Ini penting:
     dada dan rongga badan rubah memang berwarna putih, sehingga cara
     "hapus semua yang putih" akan melubangi bagian dalam logo.
     (Kesalahan itu pernah terjadi dan membuat badan kiri rubah tampak
     berlubang tembus -- lihat catatan di bawah.)
  3. Rongga badan kiri yang berwarna putih asli dipertahankan (memang
     begitu desainnya), tetapi diberi latar putih sehingga terbaca
     sebagai bagian dari gambar, bukan lubang.

Jalankan sekali saja bila logo sumber berubah (dari folder frontend):
  python _buat_ikon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

PUBLIC = Path(__file__).parent / "public"
SUMBER = PUBLIC / "White-Chested Fox Logo.png"

PUTIH = (255, 255, 255)

# Kotak potong: hanya memuat rubahnya, dengan sedikit napas di tepi.
# Nilai diambil dari batas tinta gambar asli.
KOTAK = (556, 210, 900, 885)


def _rubah_transparan() -> Image.Image:
    """
    Crop rubah dan siapkan versi berlatar transparan.

    Transparansi diambil dari KANAL ALPHA gambar asli. Piksel yang opak
    (termasuk dada putih) dibiarkan apa adanya.
    """
    asli = Image.open(SUMBER).convert("RGBA").crop(KOTAK)

    # Bersihkan sisa hampir-transparan di tepi agar tidak ada bingkai
    # samar ketika gambar diperkecil.
    data = asli.load()
    lebar, tinggi = asli.size
    for y in range(tinggi):
        for x in range(lebar):
            r, g, b, a = data[x, y]
            if a == 0:
                continue
            # Tepi anti-alias: samakan warna ke putih agar tidak muncul
            # garis gelap saat diletakkan di atas latar terang.
            if a < 255:
                t = a / 255
                data[x, y] = (
                    int(r * t + 255 * (1 - t)),
                    int(g * t + 255 * (1 - t)),
                    int(b * t + 255 * (1 - t)),
                    a,
                )
    return asli


def _latar(ukuran: tuple[int, int], warna=PUTIH) -> Image.Image:
    return Image.new("RGBA", ukuran, warna + (255,))


def _tempel_tengah(latar: Image.Image, rubah: Image.Image, skala: float) -> None:
    lebar, tinggi = latar.size
    sisi = int(min(lebar, tinggi) * skala)
    kecil = rubah.copy()
    kecil.thumbnail((sisi, sisi), Image.LANCZOS)
    posisi = ((lebar - kecil.width) // 2, (tinggi - kecil.height) // 2)
    # Latar PUTIH di belakang logo, supaya rongga badan yang memang putih
    # terbaca sebagai bagian gambar -- bukan lubang yang menembus latar.
    latar.paste(kecil, posisi, kecil)


def main() -> None:
    rubah = _rubah_transparan()
    print("rubah dipotong:", rubah.size)

    # A. Logo polos: latar PUTIH penuh (bukan transparan).
    #
    #    Kenapa tidak transparan: rongga badan rubah berwarna putih asli.
    #    Bila latarnya transparan, rongga itu menjadi lubang tembus dan
    #    rubah terlihat "terpotong". Dengan latar putih, bentuknya utuh
    #    persis seperti gambar aslinya.
    for sisi, nama in ((512, "logo-512.png"), (192, "logo-192.png")):
        kanvas = _latar((sisi, sisi), PUTIH)
        _tempel_tengah(kanvas, rubah, skala=1.0)
        kanvas.convert("RGB").save(PUBLIC / nama, optimize=True)
        print("dibuat:", nama, kanvas.size)

    # B. Favicon & ikon aplikasi: LOGO YANG SAMA, hanya diberi sudut
    #    membulat. Tidak ada desain baru.
    for sisi, nama in ((192, "icon-192.png"), (512, "icon-512.png")):
        kanvas = Image.new("RGBA", (sisi, sisi), PUTIH + (0,))
        isi = _latar((sisi, sisi), PUTIH)
        _tempel_tengah(isi, rubah, skala=0.94)

        topeng = Image.new("L", (sisi, sisi), 0)
        ImageDraw.Draw(topeng).rounded_rectangle(
            [0, 0, sisi - 1, sisi - 1],
            radius=int(sisi * 0.21),
            fill=255,
        )
        kanvas.paste(isi, (0, 0), topeng)
        kanvas.save(PUBLIC / nama, optimize=True)
        print("dibuat:", nama)

    # C. Maskable (Android): latar penuh sampai tepi, logo lebih kecil.
    sisi = 512
    kanvas = _latar((sisi, sisi), PUTIH)
    _tempel_tengah(kanvas, rubah, skala=0.72)
    kanvas.convert("RGB").save(PUBLIC / "icon-maskable-512.png", optimize=True)
    print("dibuat: icon-maskable-512.png")

    # D. Apple touch icon: persegi penuh, tanpa sudut membulat
    #    (iOS membulatkan sendiri).
    sisi = 180
    kanvas = _latar((sisi, sisi), PUTIH)
    _tempel_tengah(kanvas, rubah, skala=0.94)
    kanvas.convert("RGB").save(PUBLIC / "apple-touch-icon.png", optimize=True)
    print("dibuat: apple-touch-icon.png")

    # E. Pratinjau tautan 1200x630: logo di tengah latar putih.
    lebar, tinggi = 1200, 630
    kanvas = _latar((lebar, tinggi), PUTIH)
    sisi_logo = 420
    kecil = rubah.copy()
    kecil.thumbnail((sisi_logo, sisi_logo), Image.LANCZOS)
    kanvas.paste(
        kecil,
        ((lebar - kecil.width) // 2, (tinggi - kecil.height) // 2),
        kecil,
    )
    kanvas.convert("RGB").save(PUBLIC / "og-image.png", optimize=True)
    print("dibuat: og-image.png")


if __name__ == "__main__":
    main()
