"""
uji_riset_kualitas.py — apakah riset memberi sumber yang BENAR, bukan
sekadar "ada hasil". Ini yang menentukan kualitas jawaban model.
"""

import asyncio
import sys

import riset

# (pertanyaan, kata yang HARUS muncul di sumber)
KASUS = [
    ("ibu kota Australia", ["australia", "canberra"]),
    ("presiden Indonesia saat ini", ["presiden", "indonesia"]),
    ("apa itu fotosintesis", ["fotosintesis"]),
    ("Cristiano Ronaldo klub sekarang", ["ronaldo"]),
    ("sejarah candi borobudur", ["borobudur"]),
]


async def main() -> int:
    lulus = 0
    for pertanyaan, wajib in KASUS:
        hasil = await riset.cari_dan_baca(pertanyaan)
        gab = (
            " ".join(s["judul"] for s in hasil["sumber"])
            + " "
            + hasil["teks"]
        ).lower()
        ada = all(k in gab for k in wajib)
        judul = ", ".join(s["judul"][:24] for s in hasil["sumber"]) or "(kosong)"
        status = "LULUS" if ada else "GAGAL"
        if ada:
            lulus += 1
        print(f"{status}  {pertanyaan}")
        print(f"        sumber: {judul}")
        print(f"        konteks: {len(hasil['teks'])} karakter")
        if not ada:
            print(f"        kata wajib tidak ditemukan: {wajib}")
        print()

    print(f"HASIL: {lulus}/{len(KASUS)} lulus")
    return 0 if lulus == len(KASUS) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
