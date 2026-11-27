"""
uji_model_gemini.py — memeriksa model Gemini mana yang BENAR-BENAR bisa
dipakai dengan API key Anda, lalu melaporkan mana yang layak ditambahkan
ke aplikasi.

MENGAPA PERLU DIUJI, BUKAN DIPERCAYA
------------------------------------
Dokumentasi Google mencantumkan banyak model, tetapi tidak semua bisa
dipakai dengan API key gratis:
  - sebagian model hanya untuk akun yang sudah memakainya sejak dulu,
  - sebagian sudah dimatikan total (mis. gemini-2.0-flash per 1 Juni 2026),
  - sebagian butuh billing / bukan untuk chat teks.

Karena itu setiap model diuji langsung: dikirimi pesan pendek, diminta
jawaban streaming, dan dikirimi gambar kecil. Yang gagal tidak dimasukkan.

CARA PAKAI (PowerShell, di folder chatbot-saya/backend):

    $env:GEMINI_API_KEY="AIza...(key dari https://aistudio.google.com/apikey)"
    python uji_model_gemini.py

Key TIDAK ditulis di file ini dan TIDAK disimpan — hanya dibaca dari
environment sesi terminal itu.

Yang diperiksa per model:
  1. Apakah menjawab satu pesan teks (bukan 404/429/401).
  2. Apakah streaming SSE bekerja (dipakai /chat/stream).
  3. Apakah bisa membaca gambar (dipakai fitur lampiran gambar).
  4. Kecepatan jawaban.
"""

import base64
import os
import sys
import time

import httpx

BASE = os.environ.get("GEMINI_BASE_URL", "").strip() or (
    "https://generativelanguage.googleapis.com/v1beta/openai"
)

# Gambar PNG 1x1 piksel (untuk menguji kemampuan baca gambar).
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)
GAMBAR_URL = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()

# Kandidat model, diurutkan dari yang paling diinginkan.
#
# Kelompok 1 (generasi terbaru, tanpa jadwal mati):
#   pilihan utama — paling pintar, konteks 1 juta token.
# Kelompok 2 (untuk kecepatan / kuota lebih lega):
#   dipakai sebagai cadangan saat model utama kena limit.
# Kelompok 3 (generasi lama, hanya untuk pembanding):
#   kemungkinan besar mati; diuji supaya jelas, bukan ditebak.
KANDIDAT = [
    # --- Gemini 4 (terbaru) ---
    "gemini-4-hydrogen",
    "gemini-4-argon",
    "gemini-4-neon",
    "gemini-4-carbon",
    # --- Gemini 3 ---
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    # --- Gemini 2.5 (pembanding; kemungkinan dibatasi) ---
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    # --- Gemini 2.0 (diharapkan mati; untuk membuktikan) ---
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
]

PESAN = [
    {"role": "user", "content": "Jawab satu kata saja: halo"},
]


def headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def uji_teks(http: httpx.Client, key: str, model: str) -> dict:
    """Uji satu jawaban biasa (non-streaming)."""
    mulai = time.perf_counter()
    try:
        r = http.post(
            f"{BASE}/chat/completions",
            headers=headers(key),
            json={
                "model": model,
                "messages": PESAN,
                "temperature": 0.2,
                "max_tokens": 32,
                "stream": False,
            },
            timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "kode": "jaringan", "sebab": str(e)[:90], "detik": 0}

    detik = time.perf_counter() - mulai
    if r.status_code >= 400:
        return {
            "ok": False,
            "kode": r.status_code,
            "sebab": r.text[:110].replace("\n", " "),
            "detik": detik,
        }

    try:
        isi = (r.json()["choices"][0]["message"].get("content") or "").strip()
    except Exception:  # noqa: BLE001
        isi = ""

    if not isi:
        return {"ok": False, "kode": "kosong", "sebab": "jawaban kosong", "detik": detik}
    return {"ok": True, "kode": 200, "sebab": isi[:40], "detik": detik}


def uji_stream(http: httpx.Client, key: str, model: str) -> dict:
    """Uji streaming SSE — dipakai oleh /chat/stream di aplikasi."""
    potongan = 0
    try:
        with http.stream(
            "POST",
            f"{BASE}/chat/completions",
            headers=headers(key),
            json={
                "model": model,
                "messages": PESAN,
                "temperature": 0.2,
                "max_tokens": 32,
                "stream": True,
            },
            timeout=60,
        ) as r:
            if r.status_code >= 400:
                r.read()
                return {"ok": False, "sebab": f"HTTP {r.status_code}"}
            for baris in r.iter_lines():
                if not baris:
                    continue
                if not baris.startswith("data:"):
                    continue
                data = baris[5:].strip()
                if data == "[DONE]":
                    break
                if data:
                    potongan += 1
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "sebab": str(e)[:90]}

    return {
        "ok": potongan > 0,
        "sebab": f"{potongan} potongan" if potongan else "tidak ada data",
    }


def uji_gambar(http: httpx.Client, key: str, model: str) -> dict:
    """Uji kemampuan membaca gambar (dipakai fitur lampiran gambar)."""
    try:
        r = http.post(
            f"{BASE}/chat/completions",
            headers=headers(key),
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Apa warna gambar ini? Satu kata."},
                            {"type": "image_url", "image_url": {"url": GAMBAR_URL}},
                        ],
                    }
                ],
                "temperature": 0.2,
                "max_tokens": 32,
            },
            timeout=60,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "sebab": str(e)[:90]}

    if r.status_code >= 400:
        return {"ok": False, "sebab": f"HTTP {r.status_code}"}
    return {"ok": True, "sebab": "bisa membaca gambar"}


def main() -> int:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("GEMINI_API_KEY belum diisi.")
        print('PowerShell:  $env:GEMINI_API_KEY="AIza..."')
        print("Ambil gratis di https://aistudio.google.com/apikey")
        return 2

    print(f"Endpoint : {BASE}")
    print(f"Kandidat : {len(KANDIDAT)} model\n")
    print(f"{'model':<30} {'teks':<8} {'stream':<8} {'gambar':<8} {'detik':<7} catatan")
    print("-" * 96)

    hidup = []
    with httpx.Client() as http:
        for model in KANDIDAT:
            hasil = uji_teks(http, key, model)
            if not hasil["ok"]:
                status = str(hasil["kode"])
                print(
                    f"{model:<30} {status:<8} {'-':<8} {'-':<8} {'-':<7} {hasil['sebab']}"
                )
                continue

            stream = uji_stream(http, key, model)
            gambar = uji_gambar(http, key, model)
            print(
                f"{model:<30} {'OK':<8} "
                f"{('OK' if stream['ok'] else 'GAGAL'):<8} "
                f"{('OK' if gambar['ok'] else 'TIDAK'):<8} "
                f"{hasil['detik']:<7.2f} {hasil['sebab']}"
            )
            hidup.append(
                {
                    "model": model,
                    "stream": stream["ok"],
                    "gambar": gambar["ok"],
                    "detik": hasil["detik"],
                }
            )

    print("-" * 96)
    print(f"\nLULUS: {len(hidup)} dari {len(KANDIDAT)} model\n")

    if not hidup:
        print("Tidak ada model yang bisa dipakai. Periksa key Anda.")
        return 1

    # Yang layak dipakai aplikasi: bisa teks DAN stream DAN gambar.
    layak = [m for m in hidup if m["stream"] and m["gambar"]]
    if layak:
        print("LAYAK DIPASANG (teks + stream + gambar semua jalan):")
        for m in sorted(layak, key=lambda x: x["detik"]):
            print(f"  - {m['model']:<30} {m['detik']:.2f} dtk")
        print("\nUsulan urutan di main.py (tercepat dulu sebagai cadangan):")
        print("GEMINI_MODELS = [")
        for m in sorted(layak, key=lambda x: x["detik"]):
            print(f'    "{m["model"]}",')
        print("]")
    else:
        print("Ada model yang hidup, tetapi tidak ada yang memenuhi ketiga syarat.")

    gagal_stream = [m for m in hidup if not m["stream"]]
    if gagal_stream:
        print("\nHidup tapi streaming gagal (jangan dipakai sebagai utama):")
        for m in gagal_stream:
            print(f"  - {m['model']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
