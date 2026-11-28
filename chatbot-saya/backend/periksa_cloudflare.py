"""
periksa_cloudflare.py — memeriksa kunci Cloudflare TANPA mengetik perintah
panjang di PowerShell.

MENGAPA ADA SKRIP INI
---------------------
Mengetik perintah berisi kunci (yang panjang, penuh angka dan huruf) di
PowerShell gampang gagal: tanda kutip hilang, baris terpotong saat
disalin, atau Enter tertekan terlalu cepat. Gejalanya membingungkan —
layar hanya kembali ke prompt tanpa pesan apa pun.

Skrip ini menghapus semua kerumitan itu: cukup jalankan, lalu TEMPEL
kuncinya saat diminta. Kuncinya hanya disimpan di memori untuk pemeriksaan
ini saja — TIDAK ditulis ke berkas dan TIDAK dicetak utuh.

CARA PAKAI
----------
    cd chatbot-saya\\backend
    & $env:LOCALAPPDATA\\ChatbotSaya-Python\\python.exe periksa_cloudflare.py

Lalu tempel Account ID dan token saat ditanya (klik kanan = tempel di
PowerShell, tidak perlu Ctrl+V).
"""

from __future__ import annotations

import sys

import httpx

BATAS_DETIK = 40.0
MODEL_UJI = "@cf/openai/gpt-oss-120b"


def _samar(kunci: str) -> str:
    if not kunci:
        return "(kosong)"
    return f"panjang {len(kunci)}, awal '{kunci[:6]}...'"


def main() -> int:
    print("=" * 60)
    print("PERIKSA KUNCI CLOUDFLARE")
    print("=" * 60)
    print("Tempel nilainya lalu tekan Enter. (Klik kanan = tempel)")
    print()

    try:
        akun = input("Account ID : ").strip()
        token = input("API Token  : ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nDibatalkan.")
        return 2

    # Kunci yang tersalin dari web kadang membawa spasi atau baris baru.
    akun = akun.strip().strip('"').strip("'")
    token = token.strip().strip('"').strip("'")

    print()
    print(f"  Account ID : {akun if akun else '(kosong)'}")
    print(f"  Token      : {_samar(token)}")

    if not akun or not token:
        print()
        print("GAGAL: dua-duanya harus diisi.")
        if not akun:
            print("  -> Account ID belum diisi.")
        if not token:
            print("  -> Token belum diisi.")
        return 2

    if not akun.isalnum():
        print()
        print("PERINGATAN: Account ID biasanya hanya huruf dan angka.")
        print("            Periksa apakah ada karakter aneh yang ikut tersalin.")

    url = (
        f"https://api.cloudflare.com/client/v4/accounts/{akun}"
        "/ai/v1/chat/completions"
    )

    print()
    print("Menghubungi Cloudflare...")

    try:
        res = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL_UJI,
                "messages": [{"role": "user", "content": "Balas tepat satu kata: SIAP"}],
                "max_tokens": 40,
            },
            timeout=BATAS_DETIK,
        )
    except httpx.TimeoutException:
        print(f"GAGAL: tidak menjawab dalam {BATAS_DETIK:.0f} detik. Coba lagi.")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"GAGAL: tidak bisa menghubungi server — {str(exc)[:100]}")
        return 1

    print(f"HTTP {res.status_code}")
    print()

    if res.status_code == 200:
        try:
            isi = (res.json().get("choices") or [{}])[0].get("message", {})
            teks = (isi.get("content") or "").strip().replace("\n", " ")[:60]
        except Exception:  # noqa: BLE001
            teks = ""
        print("=" * 60)
        print("BERHASIL — kunci Cloudflare Anda HIDUP.")
        print("=" * 60)
        if teks:
            print(f'Model menjawab: "{teks}"')
        print()
        print("Langkah berikutnya: tempel DUA nilai ini di Vercel")
        print("  Settings -> Environment Variables ->")
        print("    CLOUDFLARE_ACCOUNT_ID  = Account ID di atas")
        print("    CLOUDFLARE_API_TOKEN   = token Anda")
        print("lalu Redeploy.")
        return 0

    print("=" * 60)
    print("GAGAL — kunci belum bisa dipakai.")
    print("=" * 60)
    print(f"Jawaban Cloudflare: {res.text[:250]}")
    print()

    if res.status_code in (401, 403):
        print("Penyebab paling mungkin:")
        print("  1. Token kurang/lebih satu huruf saat disalin.")
        print("  2. Token tidak punya izin 'Workers AI - Edit'.")
        print("     Saat membuat token, pilih template 'Workers AI', atau")
        print("     centang DUA izin: 'Workers AI - Read' DAN 'Workers AI - Edit'.")
        print("  3. Token sudah dihapus / kedaluwarsa -> buat baru.")
        print("  4. Account ID salah (milik akun lain).")
    elif res.status_code == 404:
        print("Penyebab: Account ID tidak ditemukan, atau model uji tidak ada.")
        print("  -> Periksa lagi Account ID di halaman 'Use REST API'.")
    elif res.status_code == 429:
        print("Kunci BENAR, tetapi kuota harian sedang habis. Ini bukan masalah")
        print("kunci — coba lagi setelah 00:00 UTC (07:00 WIB).")
        return 0
    else:
        print("Periksa kembali kedua nilai, lalu coba lagi.")

    return 1


if __name__ == "__main__":
    sys.exit(main())
