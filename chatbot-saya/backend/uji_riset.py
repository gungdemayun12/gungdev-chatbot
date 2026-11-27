"""
uji_riset.py — memastikan modul riset BENAR-BENAR mengambil data dari web.

Yang diuji:
  1. Pencarian menghasilkan sumber (bukan kosong).
  2. Halaman benar-benar dibaca (ada isi, bukan cuma judul).
  3. Konteks untuk model terbentuk.
  4. Anti-SSRF: alamat lokal/privat DITOLAK.
  5. Tidak pernah melempar exception walau query aneh/kosong.

Jalankan: python uji_riset.py
"""

import asyncio
import sys

import riset

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


async def main() -> int:
    print("=== 1. PENCARIAN NYATA ===")
    hasil = await riset.cari_dan_baca("ibu kota Australia populasi 2026")
    cek("ada sumber ditemukan", len(hasil["sumber"]) > 0, f"{len(hasil['sumber'])} sumber")
    for s in hasil["sumber"]:
        print(f"   - {s['judul'][:60]}  ({s['url'][:70]})")

    ada_isi = [s for s in hasil["sumber"] if (s.get("isi") or "").strip()]
    cek("minimal satu halaman benar-benar terbaca", len(ada_isi) > 0, f"{len(ada_isi)} halaman berisi")
    cek("konteks untuk model terbentuk", len(hasil["teks"]) > 100, f"{len(hasil['teks'])} karakter")
    cek(
        "konteks memuat URL sumber",
        "http" in hasil["teks"],
        hasil["teks"][:80].replace("\n", " "),
    )

    print("\n=== 2. PERTANYAAN BERBAHASA INDONESIA ===")
    hasil2 = await riset.cari_dan_baca("resep rendang padang asli")
    cek("pencarian Indonesia berhasil", len(hasil2["sumber"]) > 0, f"{len(hasil2['sumber'])} sumber")

    print("\n=== 3. ANTI-SSRF ===")
    for url in [
        "http://localhost:8000/health",
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ]:
        cek(f"tolak {url}", not riset._url_aman(url))

    cek("izinkan URL publik", riset._url_aman("https://id.wikipedia.org/wiki/Australia"))

    print("\n=== 4. KETAHANAN (tidak boleh melempar) ===")
    for q in ["", "   ", "!!!", "a" * 500]:
        try:
            r = await riset.cari_dan_baca(q)
            cek(f"query aneh {q[:10]!r} tidak melempar", isinstance(r, dict))
        except Exception as exc:  # noqa: BLE001
            cek(f"query aneh {q[:10]!r} tidak melempar", False, str(exc))

    print("\n=== 5. KONTEKS UNTUK MODEL ===")
    k = riset.konteks_untuk_model(hasil)
    cek("konteks terbentuk", isinstance(k, str) and len(k) > 100)
    cek("instruksi menyebut sumber", "[1]" in k and "sumber" in k.lower())
    cek("konteks kosong -> None", riset.konteks_untuk_model({"teks": ""}) is None)

    print(f"\nHASIL: {LULUS}/{LULUS + GAGAL} lulus")
    return 0 if GAGAL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
