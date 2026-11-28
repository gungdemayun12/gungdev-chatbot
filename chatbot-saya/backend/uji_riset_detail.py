"""
uji_riset_detail.py — memastikan riset MENELUSURI HALAMAN DALAM (paket/post),
bukan berhenti di domain utama.

Latar belakang (keluhan pemilik situs): saat menanyakan paket tour, jawaban
hanya menyebut "beetrip.co.id" berulang kali, padahal informasi paketnya ada
di halaman /view/paket-honeymoon-4h3m-private-pool-villa. Riset hanya membaca
teks halaman depan dan membuang seluruh tautan.

Yang diuji:
  1. Tautan detail (/view, /category, /article) benar-benar ditemukan.
  2. Tautan sampah (tag, kontak, css, domain lain) dibuang.
  3. Pemilihan tautan: kata pembeda menang atas kata umum.
  4. Halaman kategori dipakai sebagai perantara bila perlu.
  5. RISET NYATA: sumber menunjuk halaman dalam, bukan domain utama.
  6. Judul kartu sumber memakai judul halaman, bukan domain.
  7. Aturan prompt: model diminta memakai nomor halaman detail.

Jalankan: python uji_riset_detail.py
"""

import asyncio
import sys
from urllib.parse import urlparse

import riset

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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


def kedalaman(url: str) -> int:
    """Jumlah bagian alamat. '/' -> 0, '/view/paket' -> 2."""
    return len([x for x in (urlparse(url).path or "").split("/") if x])


async def main() -> int:
    # --- 1. Pengumpulan tautan detail ---------------------------------
    print("=== 1. PENGUMPULAN TAUTAN DETAIL ===")
    html = """
    <html><body>
    <a href="/category/paket-honeymoon/">Paket Honeymoon</a>
    <a href="/view/paket-honeymoon-4h3m-private-pool-villa">Paket Honeymoon 4H3M</a>
    <a href="/tag/promo">Promo</a>
    <a href="/kontak">Kontak</a>
    <a href="/assets/css/style.css">CSS</a>
    <a href="https://situslain.com/view/paket">Situs lain</a>
    <a href="/view/paket-honeymoon-4h3m-private-pool-villa">Dobel</a>
    </body></html>
    """
    tautan = riset._tautan_detail(html, "https://contoh.co.id/")
    daftar_url = [t["url"] for t in tautan]
    cek("tautan halaman dalam ditemukan", len(tautan) >= 2, f"{len(tautan)} tautan")
    cek("tautan /view/ ikut terkumpul", any("/view/" in u for u in daftar_url))
    cek("tautan /category/ ikut terkumpul", any("/category/" in u for u in daftar_url))
    cek(
        "tag/kontak/css dibuang",
        not any(x in " ".join(daftar_url) for x in ("/tag/", "/kontak", ".css")),
    )
    cek("domain lain diabaikan", not any("situslain" in u for u in daftar_url))
    cek("tidak ada duplikat", len(daftar_url) == len(set(daftar_url)), str(len(daftar_url)))

    # --- 2. Tautan kategori sebagai perantara -------------------------
    print("\n=== 2. TAUTAN KATEGORI (PERANTARA) ===")
    kategori = riset._tautan_kategori(html, "https://contoh.co.id/")
    cek("tautan kategori ditemukan", any("/category/" in k["url"] for k in kategori), str(len(kategori)))

    # --- 3. Pemilihan tautan relevan ---------------------------------
    print("\n=== 3. PEMILIHAN TAUTAN RELEVAN ===")
    kandidat = [
        {"url": "https://contoh.co.id/view/paket-tour-bali-hemat", "judul": "Paket Tour Bali Hemat"},
        {"url": "https://contoh.co.id/view/paket-honeymoon-4h3m", "judul": "Paket Honeymoon 4H3M"},
        {"url": "https://contoh.co.id/view/paket-tour-bali-keluarga", "judul": "Paket Bali Keluarga"},
    ]
    pilih = riset._pilih_tautan_detail(kandidat, "paket bali honeymoon", 1)
    cek("kata pembeda menang atas kata umum", "honeymoon" in pilih[0]["url"], pilih[0]["url"])
    cek("jumlah pilihan dibatasi", len(riset._pilih_tautan_detail(kandidat, "paket", 2)) == 2)

    # --- 4. Judul halaman asli ----------------------------------------
    print("\n=== 4. JUDUL HALAMAN ===")
    html_judul = "<html><head><title>Promo - Contoh</title></head><body><h1>Paket Honeymoon 4H3M</h1></body></html>"
    cek(
        "judul diambil dari <h1>, bukan <title> generik",
        riset._judul_halaman(html_judul) == "Paket Honeymoon 4H3M",
        riset._judul_halaman(html_judul),
    )

    # --- 5. RISET NYATA ------------------------------------------------
    print("\n=== 5. RISET NYATA: SUMBER MENUNJUK HALAMAN DALAM ===")
    hasil = await riset.cari_dan_baca("paket honeymoon bali private pool villa", maks_sumber=5)
    sumber = hasil.get("sumber") or []
    detail = [s for s in sumber if s.get("detail")]
    print(f"   sumber total {len(sumber)} | halaman detail {len(detail)}")
    for i, s in enumerate(sumber[:6], start=1):
        tanda = "[DETAIL]" if s.get("detail") else "        "
        print(f"   [{i}] {tanda} {s['url'][:78]}")

    cek("ada halaman detail yang dibaca", len(detail) >= 1, f"{len(detail)} halaman")
    cek(
        "sumber detail berupa halaman DALAM (bukan domain utama)",
        any(kedalaman(s["url"]) >= 2 for s in detail),
        detail[0]["url"][:70] if detail else "-",
    )
    cek(
        "halaman detail benar-benar berisi",
        bool(detail and (detail[0].get("isi") or "").strip()),
        f"{len(detail[0].get('isi') or '')} karakter" if detail else "-",
    )

    # --- 6. Daftar sumber untuk UI ------------------------------------
    print("\n=== 6. KARTU SUMBER UNTUK PENGGUNA ===")
    kartu = riset.daftar_sumber(hasil)
    cek("kartu sumber tersusun", len(kartu) > 0, f"{len(kartu)} kartu")
    cek(
        "nomor berurutan dari 1",
        [k["nomor"] for k in kartu] == list(range(1, len(kartu) + 1)),
    )
    cek(
        "ada kartu berURL halaman dalam",
        any(kedalaman(k["url"]) >= 2 for k in kartu),
        next((k["url"][:70] for k in kartu if kedalaman(k["url"]) >= 2), "-"),
    )
    cek(
        "kartu memakai JUDUL halaman, bukan nama domain saja",
        any(len((k.get("judul") or "")) > 12 and k.get("judul") != k.get("situs") for k in kartu),
        (kartu[0].get("judul") or "")[:60],
    )
    cek("isi halaman TIDAK dikirim ke browser", all("isi" not in k for k in kartu))

    # --- 7. Aturan untuk model ----------------------------------------
    print("\n=== 7. ATURAN UNTUK MODEL ===")
    konteks = riset.konteks_untuk_model(hasil) or ""
    cek("aturan memakai nomor halaman detail", "pakai nomor halaman detail" in konteks)
    cek("aturan melarang menyebut domain utama", "Jangan menyebut alamat domain utama" in konteks)
    cek("penanda HALAMAN DETAIL ada", "HALAMAN DETAIL" in konteks)
    cek("tetap melarang mengaku tidak bisa web", "DILARANG berkata" in konteks)

    # --- 8. Tidak pernah melempar exception ---------------------------
    print("\n=== 8. KETAHANAN ===")
    for q in ("", "   ", "!!!", "a" * 500):
        try:
            h = await riset.cari_dan_baca(q, maks_sumber=2)
            cek(f"query {q[:12]!r} tidak melempar exception", isinstance(h, dict))
        except Exception as exc:  # noqa: BLE001
            cek(f"query {q[:12]!r} tidak melempar exception", False, str(exc))

    print(f"\nHASIL: {LULUS}/{LULUS + GAGAL} lulus")
    return 0 if GAGAL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
