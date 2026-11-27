"""
cek_key.py — memeriksa apakah API key yang baru Anda ambil BENAR-BENAR
hidup, sebelum dipasang ke Vercel.

MENGAPA PERLU DIPERIKSA DULU
----------------------------
Key yang salah baru ketahuan setelah dipasang di Vercel, lalu situs
mengalami error dan penyebabnya sulit dilacak. Uji ini memanggil
penyedia LANGSUNG, jadi Anda tahu hasilnya dalam hitungan detik.

Key TIDAK disimpan dan TIDAK dicetak utuh — hanya panjang dan awalnya,
supaya aman bila Anda merekam layar atau bertanya di forum.

CARA PAKAI
----------
PowerShell (Windows):

    cd chatbot-saya\\backend

    $env:NVIDIA_API_KEY="nvapi-..."
    python cek_key.py nvidia

    $env:GEMINI_API_KEY="AIza..."
    python cek_key.py gemini

Bisa juga tanpa menyebut nama (semua yang punya key akan diuji):

    python cek_key.py

Hasil yang bagus ditandai OK. Bila GAGAL, sebabnya ditulis apa adanya
dan ada saran perbaikan di bawahnya.
"""

from __future__ import annotations

import os
import sys
import time

import httpx

BATAS_DETIK = 40.0


def _samar(kunci: str) -> str:
    """Menampilkan key dalam bentuk aman: panjang + 6 huruf awal saja."""
    if not kunci:
        return "(kosong)"
    return f"panjang {len(kunci)}, awal '{kunci[:6]}...'"


def _payload(model: str, teks: str) -> dict:
    return {
        "model": model,
        "messages": [{"role": "user", "content": teks}],
        "temperature": 0.1,
        "max_tokens": 40,
    }


def _uji_satu(
    nama: str,
    url: str,
    kunci: str,
    model: str,
    teks: str = "Balas tepat satu kata: SIAP",
) -> bool:
    """Memanggil satu model dan melaporkan hasilnya. True bila hidup."""
    print(f"\n[{nama}] model: {model}")
    print(f"  key   : {_samar(kunci)}")
    print(f"  url   : {url}")

    mulai = time.time()
    try:
        res = httpx.post(
            url,
            headers={
                "Authorization": f"Bearer {kunci}",
                "Content-Type": "application/json",
            },
            json=_payload(model, teks),
            timeout=BATAS_DETIK,
        )
    except httpx.TimeoutException:
        print(f"  GAGAL : tidak menjawab dalam {BATAS_DETIK:.0f} detik.")
        print("          Coba lagi; bila tetap, jaringan Anda yang lambat.")
        return False
    except Exception as exc:  # noqa: BLE001
        print(f"  GAGAL : tidak bisa menghubungi server — {str(exc)[:80]}")
        return False

    detik = time.time() - mulai

    if res.status_code == 200:
        try:
            data = res.json()
            isi = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
        except Exception:  # noqa: BLE001
            isi = ""
        isi = isi.strip().replace("\n", " ")[:70]
        if not isi:
            print(f"  GAGAL : HTTP 200 tetapi jawaban kosong ({detik:.1f} dtk).")
            print("          Model ini kemungkinan tidak tersedia untuk akun Anda.")
            return False
        print(f"  OK    : {detik:.1f} detik — jawab: \"{isi}\"")
        return True

    print(f"  GAGAL : HTTP {res.status_code} ({detik:.1f} dtk)")
    print(f"          pesan: {res.text[:180].replace(chr(10), ' ')}")

    if res.status_code in (401, 403):
        print("          -> Key ditolak. Biasanya salah salin (kurang/lebih")
        print("             satu huruf) atau key sudah dihapus.")
    elif res.status_code == 402:
        print("          -> Kredit akun habis.")
    elif res.status_code == 404:
        print("          -> Nama model tidak ada untuk key ini, bukan salah key.")
    elif res.status_code == 429:
        print("          -> Key BENAR, tetapi kuota sedang penuh. Coba lagi nanti.")
        return True
    return False


def main() -> int:
    pilihan = (sys.argv[1] if len(sys.argv) > 1 else "semua").lower()

    nvidia = (os.environ.get("NVIDIA_API_KEY") or "").strip()
    gemini = (os.environ.get("GEMINI_API_KEY") or "").strip()

    dikerjakan = 0
    hidup = 0

    if pilihan in ("nvidia", "semua"):
        if not nvidia:
            if pilihan == "nvidia":
                print("NVIDIA_API_KEY belum diisi di terminal ini.")
                print('PowerShell:  $env:NVIDIA_API_KEY="nvapi-..."')
                return 2
        else:
            dikerjakan += 1
            hidup += _uji_satu(
                "NVIDIA",
                "https://integrate.api.nvidia.com/v1/chat/completions",
                nvidia,
                os.environ.get("NVIDIA_MODEL", "openai/gpt-oss-120b"),
            )

    if pilihan in ("gemini", "semua"):
        if not gemini:
            if pilihan == "gemini":
                print("GEMINI_API_KEY belum diisi di terminal ini.")
                print('PowerShell:  $env:GEMINI_API_KEY="AIza..."')
                return 2
        else:
            dikerjakan += 1
            hidup += _uji_satu(
                "Gemini",
                "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
                gemini,
                os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
            )

    if dikerjakan == 0:
        print("Tidak ada key yang bisa diuji.")
        print("Isi salah satu dulu, misalnya:")
        print('  $env:NVIDIA_API_KEY="nvapi-..."')
        print('  $env:GEMINI_API_KEY="AIza..."')
        return 2

    print("\n" + "=" * 60)
    print(f"HASIL: {hidup}/{dikerjakan} key hidup")
    print("=" * 60)
    if hidup:
        print("\nLangkah berikutnya: pasang key ini di Vercel (lihat panduan).")
    return 0 if hidup == dikerjakan else 1


if __name__ == "__main__":
    sys.exit(main())
