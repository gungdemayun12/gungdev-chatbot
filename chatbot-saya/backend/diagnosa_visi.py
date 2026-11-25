"""
Diagnosa visi Groq: menguji kombinasi parameter untuk menemukan mana yang
menyebabkan HTTP 400. Dijalankan dari komputer lokal memakai GROQ_API_KEY
di environment (JANGAN hardcode key di sini).
"""
import asyncio
import base64
import json
import os

import httpx

KEY = os.environ.get("GROQ_API_KEY", "").strip()
BASE = "https://api.groq.com/openai/v1"

# PNG 8x8 merah solid
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAJUlEQVR42mP8z8BQz0AEYBxVSF+F"
    "jP9RUQAAxWgHBQAAAABJRU5ErkJggg=="
)


def pesan(gambar=True):
    isi = [{"type": "text", "text": "Warna apa yang dominan? Satu kata."}]
    if gambar:
        isi.append(
            {
                "type": "image_url",
                "image_url": {"url": "data:image/png;base64," + base64.b64encode(PNG).decode()},
            }
        )
    return [{"role": "user", "content": isi}]


async def coba(nama, body):
    async with httpx.AsyncClient(timeout=90) as http:
        try:
            r = await http.post(
                f"{BASE}/chat/completions",
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                json=body,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"{nama:52s} -> EXC {type(exc).__name__}: {exc}")
            return

        if r.status_code == 200:
            data = r.json()
            try:
                isi = data["choices"][0]["message"]["content"] or ""
            except Exception:  # noqa: BLE001
                isi = ""
            print(f"{nama:52s} -> 200 OK  {isi.strip()[:70]!r}")
        else:
            print(f"{nama:52s} -> {r.status_code}  {r.text[:220]}")


async def main():
    if not KEY:
        print("GROQ_API_KEY tidak ada di environment. Set dulu.")
        print("Contoh (PowerShell): $env:GROQ_API_KEY='...'")
        return

    dasar = {"model": "qwen/qwen3.8-27b", "messages": pesan(), "max_completion_tokens": 100}

    # A. Persis seperti kode produksi (temperature 0.4)
    await coba("A. temperature=0.4 (seperti kode)", {**dasar, "temperature": 0.4})
    # B. Sesuai dokumentasi (temperature=1)
    await coba("B. temperature=1 (dokumentasi)", {**dasar, "temperature": 1})
    # C. tanpa temperature
    await coba("C. tanpa temperature", dasar)
    # D. tanpa max_completion_tokens
    await coba(
        "D. temperature=1, tanpa max_tokens",
        {"model": "qwen/qwen3.8-27b", "messages": pesan(), "temperature": 1},
    )
    # E. teks saja (kontrol: apakah modelnya sendiri yang bermasalah?)
    await coba(
        "E. kontrol teks saja",
        {
            "model": "qwen/qwen3.8-27b",
            "messages": [{"role": "user", "content": "Balas: ok"}],
            "temperature": 1,
            "max_completion_tokens": 50,
        },
    )
    # F. JPEG (bukan PNG) untuk melihat apakah tipe gambar berpengaruh
    try:
        from PIL import Image
        import io as _io

        buf = _io.BytesIO()
        Image.new("RGB", (32, 32), (200, 30, 30)).save(buf, format="JPEG")
        jpg = base64.b64encode(buf.getvalue()).decode()
        await coba(
            "F. JPEG 32x32",
            {
                "model": "qwen/qwen3.8-27b",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": "Warna dominan? Satu kata."},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpg}"}},
                        ],
                    }
                ],
                "temperature": 1,
                "max_completion_tokens": 100,
            },
        )
    except ImportError:
        print("(Pillow tidak ada, uji JPEG dilewati)")


asyncio.run(main())
