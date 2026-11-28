"""
uji_judul.py — memastikan judul riwayat dibuat dari TOPIK percakapan,
bukan potongan mentah prompt panjang.

Latar belakang (keluhan pemilik situs): judul riwayat dulu hanya 48
karakter pertama prompt, sehingga prompt panjang menghasilkan judul
terpotong yang tidak menggambarkan isi sesi. Ia ingin judul seperti
Claude/ChatGPT: ringkas, menyimpulkan topik, mudah diingat.

Yang diuji:
  1. Kata sapaan & kata perintah dibuang dari judul.
  2. Judul dibatasi jumlah kata & panjang karakter.
  3. Judul memakai kata dari SELURUH percakapan, bukan satu kalimat.
  4. Keluaran model dibersihkan ("Judul: \"...\"." -> judul bersih).
  5. Keluaran model yang menyalin kalimat panjang DITOLAK.
  6. Endpoint /judul menjawab dan tidak pernah gagal.
  7. Bahan percakapan memuat pertanyaan + jawaban asisten.

Jalankan: python uji_judul.py
"""

import asyncio
import os
import sys

os.environ.setdefault("UPSTASH_REDIS_REST_URL", "https://upstash-tiruan.local")
os.environ.setdefault("UPSTASH_REDIS_REST_TOKEN", "tiruan")
os.environ.setdefault("GOOGLE_CLIENT_ID", "uji.apps.googleusercontent.com")

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import judul  # noqa: E402

LULUS = 0
GAGAL = 0


def cek(nama: str, ok: bool, info: str = "") -> None:
    global LULUS, GAGAL
    if ok:
        LULUS += 1
        print(f"LULUS  {nama}" + (f" — {info}" if info else ""))
    else:
        GAGAL += 1
        print(f"GAGAL  {nama}" + (f" — {info}" if info else ""))


def main() -> int:
    # --- 1. Kata pembuka dibuang -------------------------------------
    print("=== 1. KATA SAPAAN & PERINTAH DIBUANG ===")
    j = judul.judul_lokal(["Halo, tolong carikan paket honeymoon di Bali beserta harganya ya"])
    cek("kata sapaan 'halo' hilang", "halo" not in j.lower(), j)
    cek("kata perintah 'tolong' hilang", "tolong" not in j.lower(), j)
    cek("kata perintah 'carikan' hilang", "carikan" not in j.lower(), j)
    cek("topik tetap ada", "honeymoon" in j.lower(), j)

    # --- 2. Batas panjang --------------------------------------------
    print("\n=== 2. BATAS PANJANG & JUMLAH KATA ===")
    panjang = (
        "Halo tolong bantu saya carikan dan jelaskan paket tour honeymoon bali "
        "beserta harga terbaru yang paling murah dan lengkap sekali untuk keluarga besar"
    )
    j2 = judul.judul_lokal([panjang])
    cek("maksimal 60 karakter", len(j2) <= judul.MAKS_PANJANG, f"{len(j2)} karakter: {j2}")
    cek("maksimal 6 kata", len(j2.split()) <= judul.MAKS_KATA, j2)
    cek("tidak ada titik di akhir", not j2.endswith("."), j2)

    # --- 3. Topik dari SELURUH percakapan ----------------------------
    print("\n=== 3. TOPIK DARI SELURUH PERCAKAPAN ===")
    j3 = judul.judul_lokal(
        [
            "Halo, boleh tanya?",
            "Tentu, silakan.",
            "Saya mau tahu paket honeymoon Bali",
        ]
    )
    cek("kata topik dari pesan belakang ikut terbawa", "honeymoon" in j3.lower(), j3)

    # --- 4. Keluaran model dibersihkan -------------------------------
    print("\n=== 4. KELUARAN MODEL DIBERSIHKAN ===")
    cek(
        'label "Judul:" dibuang',
        judul.bersihkan_judul('Judul: "Paket Honeymoon Bali"') == "Paket Honeymoon Bali",
        judul.bersihkan_judul('Judul: "Paket Honeymoon Bali"'),
    )
    cek(
        "tanda kutip & titik dibuang",
        judul.bersihkan_judul('"Paket Tour Bali."') == "Paket Tour Bali",
        judul.bersihkan_judul('"Paket Tour Bali."'),
    )
    cek("baris penjelasan diabaikan", judul.bersihkan_judul("Paket Bali\n(karena itu topiknya)") == "Paket Bali")
    cek("emoji dibuang", "😀" not in judul.bersihkan_judul("Paket Bali 😀"))
    cek("judul kosong -> kosong", judul.bersihkan_judul("   ") == "")

    # --- 5. Penyalinan kalimat panjang ditolak -----------------------
    print("\n=== 5. PENYALINAN KALIMAT PANJANG DITOLAK ===")
    salinan = (
        "Halo tolong carikan paket honeymoon di bali beserta harganya yang paling "
        "murah dan lengkap sekali untuk liburan keluarga besar tahun depan ya"
    )
    cek("kalimat panjang ditolak", judul.bersihkan_judul(salinan) == "")
    cek(
        "judul wajar diterima",
        judul.bersihkan_judul("Paket honeymoon Bali & harga") == "Paket honeymoon Bali & harga",
    )

    # --- 6. Bahan percakapan -----------------------------------------
    print("\n=== 6. BAHAN UNTUK MODEL ===")
    bahan = judul.bahan_percakapan(
        [
            {"role": "user", "content": "carikan paket honeymoon bali"},
            {"role": "assistant", "content": "Berikut tiga paket honeymoon Bali..."},
            {"role": "system", "content": "abaikan saya"},
        ]
    )
    cek("pertanyaan pengguna ikut", "honeymoon" in bahan)
    cek("jawaban asisten ikut", "Berikut tiga paket" in bahan)
    cek("pesan sistem tidak ikut", "abaikan" not in bahan)

    # --- 7. Endpoint /judul ------------------------------------------
    print("\n=== 7. ENDPOINT /judul ===")
    import server_uji  # noqa: F401  (menyiapkan tiruan Upstash & Google)
    import main

    async def endpoint() -> None:
        # Tanpa pesan: tetap menjawab wajar, tidak error.
        kosong = await main.buat_judul(main.JudulRequest(pesan=[]))
        cek("pesan kosong tetap menjawab", bool(kosong.get("judul")), str(kosong))

        # Model gagal -> cadangan lokal, tetap ada judul.
        asli = main.complete

        async def gagal(messages, opsi):
            raise RuntimeError("model mati")

        main.complete = gagal
        try:
            hasil = await main.buat_judul(
                main.JudulRequest(
                    pesan=[
                        main.PesanJudul(role="user", content="Halo tolong carikan paket honeymoon bali"),
                        main.PesanJudul(role="assistant", content="Berikut paketnya..."),
                    ]
                )
            )
        finally:
            main.complete = asli
        cek("model gagal -> tetap ada judul", bool(hasil.get("judul")), str(hasil))
        cek("sumber ditandai lokal", hasil.get("sumber") == "lokal", str(hasil.get("sumber")))
        cek("judul cadangan berisi topik", "honeymoon" in (hasil.get("judul") or "").lower(), hasil.get("judul"))

        # Model menjawab: judul dari model dipakai.
        async def pintar(messages, opsi):
            return 'Judul: "Paket honeymoon Bali dan harga"'

        main.complete = pintar
        try:
            hasil2 = await main.buat_judul(
                main.JudulRequest(
                    pesan=[
                        main.PesanJudul(role="user", content="paket honeymoon bali berapa harganya"),
                        main.PesanJudul(role="assistant", content="Mulai 3 juta..."),
                    ]
                )
            )
        finally:
            main.complete = asli
        cek("judul dari model dipakai", hasil2.get("judul") == "Paket honeymoon Bali dan harga", str(hasil2))
        cek("sumber ditandai model", hasil2.get("sumber") == "model", str(hasil2.get("sumber")))

    asyncio.run(endpoint())

    print(f"\nHASIL: {LULUS}/{LULUS + GAGAL} lulus")
    return 0 if GAGAL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
