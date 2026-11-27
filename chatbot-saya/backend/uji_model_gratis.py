"""
uji_model_gratis.py — memeriksa model OpenRouter mana yang BENAR-BENAR
bisa dipakai dengan API key Anda (khusus model :free / tanpa kredit).

CARA PAKAI (PowerShell, di folder chatbot-saya/backend):

    $env:OPENROUTER_API_KEY="sk-or-v1-...(key baru Anda)"
    python uji_model_gratis.py

Key TIDAK ditulis di file ini dan TIDAK disimpan — hanya dibaca dari
environment sesi terminal itu.

Yang diperiksa per model:
  - apakah menjawab (bukan error 402/429/404)
  - apakah mendukung gambar (dikirim gambar 1x1 piksel)
  - kecepatan jawaban

Hasilnya dipakai untuk memilih daftar model di main.py.
"""

import asyncio
import base64
import os
import sys
import time

import httpx

BASE = "https://openrouter.ai/api/v1"

# Gambar PNG 1x1 piksel warna merah (untuk menguji kemampuan baca gambar).
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFAAH/"
    "q842iQAAAABJRU5ErkJggg=="
)
GAMBAR_URL = "data:image/png;base64," + base64.b64encode(PNG_1PX).decode()

# Semua model :free yang saat ini terdaftar di OpenRouter.
KANDIDAT = [
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "inclusionai/ling-3.2-flash:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "particle-ai/particle-1:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "baidu/ernie-5.5-flash-preview:free",
    "recursive/flint-v1.0:free",
    "liquid/lfm-3-1.7b:free",
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
]


def headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://gungdev-chatbot-ai.vercel.app",
        "X-Title": "GungDev",
    }


async def tanya(http: httpx.AsyncClient, key: str, model: str, pesan: list) -> dict:
    """Satu permintaan; mengembalikan hasil yang mudah dibaca."""
    t0 = time.time()
    try:
        res = await http.post(
            f"{BASE}/chat/completions",
            headers=headers(key),
            json={"model": model, "messages": pesan, "max_tokens": 80},
        )
    except httpx.HTTPError as exc:
        return {"ok": False, "ms": int((time.time() - t0) * 1000), "sebab": f"jaringan: {exc}"}

    ms = int((time.time() - t0) * 1000)
    if res.status_code >= 400:
        try:
            j = res.json()
            pesan_err = (j.get("error") or {}).get("message") or res.text[:160]
        except ValueError:
            pesan_err = res.text[:160]
        return {"ok": False, "ms": ms, "sebab": f"HTTP {res.status_code}: {pesan_err}"}

    try:
        j = res.json()
    except ValueError:
        return {"ok": False, "ms": ms, "sebab": "balasan bukan JSON"}

    if j.get("error"):
        return {"ok": False, "ms": ms, "sebab": str(j["error"])[:160]}

    pilihan = j.get("choices") or []
    if not pilihan:
        return {"ok": False, "ms": ms, "sebab": "tidak ada pilihan jawaban"}
    isi = (pilihan[0].get("message") or {}).get("content") or ""
    return {"ok": bool(isi.strip()), "ms": ms, "isi": isi.strip()[:100]}


async def main() -> int:
    key = (os.environ.get("OPENROUTER_API_KEY") or "").strip()
    if not key:
        print("OPENROUTER_API_KEY belum diisi.")
        print('PowerShell:  $env:OPENROUTER_API_KEY="sk-or-v1-..."')
        return 1

    print(f"Key terbaca (panjang {len(key)}, awalan {key[:8]}…)\n")

    async with httpx.AsyncClient(timeout=90) as http:
        print("=== STATUS KEY & KREDIT ===")
        try:
            r = await http.get(f"{BASE}/key", headers=headers(key))
            if r.status_code == 200:
                d = r.json().get("data") or {}
                print(f"  label   : {d.get('label')}")
                print(f"  terpakai: {d.get('usage')}")
                print(f"  batas   : {d.get('limit')}  (None = tanpa batas)")
                print(f"  gratis  : {d.get('is_free_tier')}")
            else:
                print(f"  HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as exc:
            print(f"  GAGAL: {exc}")

        print("\n=== TEKS ===")
        bisa_teks = []
        for m in KANDIDAT:
            h = await tanya(http, key, m, [{"role": "user", "content": "Berapa 2+2? Jawab angkanya."}])
            tanda = "OK  " if h["ok"] else "GAGAL"
            info = h.get("isi", "").replace("\n", " ") if h["ok"] else h.get("sebab", "")
            print(f"  {tanda} {h['ms']:>6}ms  {m:<50} {info[:70]}")
            if h["ok"]:
                bisa_teks.append(m)
            await asyncio.sleep(1)

        print("\n=== GAMBAR (hanya untuk yang lolos teks) ===")
        bisa_gambar = []
        for m in bisa_teks:
            h = await tanya(
                http,
                key,
                m,
                [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Gambar ini berwarna apa? Sebut satu kata."},
                            {"type": "image_url", "image_url": {"url": GAMBAR_URL}},
                        ],
                    }
                ],
            )
            tanda = "OK  " if h["ok"] else "TIDAK"
            info = h.get("isi", "") if h["ok"] else h.get("sebab", "")[:60]
            print(f"  {tanda} {m:<50} {info[:60]}")
            if h["ok"]:
                bisa_gambar.append(m)
            await asyncio.sleep(1)

    print("\n" + "=" * 70)
    print("MODEL TEKS YANG BISA DIPAKAI ({}):".format(len(bisa_teks)))
    for m in bisa_teks:
        print("   ", m)
    print("\nMODEL YANG BISA BACA GAMBAR ({}):".format(len(bisa_gambar)))
    for m in bisa_gambar:
        print("   ", m)
    print("=" * 70)
    print("\nKirimkan daftar di atas ke saya, atau langsung tempel ke")
    print("OPENROUTER_MODELS / MODEL_VISION di chatbot-saya/backend/main.py")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
