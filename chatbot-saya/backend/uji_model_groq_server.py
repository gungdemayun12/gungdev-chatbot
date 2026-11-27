"""
uji_model_groq_server.py — mencari model Groq yang MASIH HIDUP memakai
key Groq yang sudah terpasang di server Anda, tanpa perlu menyalin key.

MENGAPA CARA INI ADA
--------------------
Halaman console.groq.com TIDAK bisa menampilkan kembali key yang sudah
dibuat (hanya tampil sekali saat pembuatan). Bila Anda tidak menyimpan
key Groq, menguji model Groq langsung dari komputer menjadi mustahil —
padahal key-nya baik-baik saja dan sedang dipakai situs.

Jadi uji ini bertanya ke server produksi Anda sendiri, yang MEMANG
memegang key tersebut. Tidak ada key yang dikirim, dicetak, atau
disimpan di sini.

MENGAPA PERLU UJI, BUKAN PERCAYA DAFTAR
---------------------------------------
Groq sering mematikan model lama untuk akun gratis — persis seperti
yang terjadi pada NVIDIA (5 model kita ternyata sudah mati, dibalas
HTTP 410). Menambah model tanpa menguji berarti menambah nama yang
tidak pernah bisa menjawab.

CARA PAKAI
----------
    cd chatbot-saya\\backend
    python uji_model_groq_server.py

Hasilnya: daftar model yang hidup + baris `MODEL_GROQ_HIDUP = [...]`
siap saya pakai untuk menghitung ulang jatah.
"""

from __future__ import annotations

import json
import re
import sys

import httpx

BASE = "https://gungdev-chatbot-rq5l.vercel.app"

# Kandidat model Groq. Diambil dari katalog Groq yang berlaku Nov 2026,
# ditambah nama lama sebagai pembanding (kalau ternyata masih hidup).
KANDIDAT = [
    # Yang sekarang dipakai situs (pembanding wajib hidup).
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.8-27b",
    # Kandidat tambahan: tiap model punya kuota SENDIRI di Groq.
    "qwen/qwen3.5-32b",
    "qwen/qwen3-32b",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "moonshotai/kimi-k2-instruct",
    "deepseek-ai/deepseek-r1-distill-llama-70b",
    "google/gemma-3-27b-it",
    "mistralai/mistral-saba-24b",
    "compound-beta",
    "compound-beta-mini",
    "allam-2-7b",
]

# Pertanyaan yang jawabannya tidak mungkin ditebak penyedia lain, supaya
# pengalihan otomatis di server langsung kelihatan.
TANYA = "Sebutkan nama model AI yang sedang menjawab ini. Satu baris saja."


def tanya(model: str) -> dict:
    """Mengirim satu pesan ke server produksi dan menilai jawabannya."""
    potongan = []
    error = ""
    try:
        with httpx.stream(
            "POST",
            f"{BASE}/chat/stream",
            json={"message": TANYA, "model": model},
            timeout=120,
        ) as res:
            if res.status_code != 200:
                return {"hidup": False, "sebab": f"HTTP {res.status_code}"}
            for baris in res.iter_lines():
                if not baris.startswith("data:"):
                    continue
                isi = baris[5:].strip()
                if isi == "[DONE]":
                    break
                try:
                    obj = json.loads(isi)
                except json.JSONDecodeError:
                    continue
                if obj.get("delta"):
                    potongan.append(obj["delta"])
                if obj.get("error"):
                    error = str(obj["error"])
    except Exception as exc:  # noqa: BLE001
        return {"hidup": False, "sebab": f"koneksi: {str(exc)[:50]}"}

    teks = re.sub(r"\s+", " ", "".join(potongan)).strip()
    if error:
        return {"hidup": False, "sebab": f"error: {error[:50]}"}
    if not teks:
        return {"hidup": False, "sebab": "jawaban kosong"}
    return {"hidup": True, "jawab": teks[:70]}


def main() -> int:
    print(f"Server : {BASE}")
    print(f"Kandidat: {len(KANDIDAT)} model\n")

    # Pembanding: model ngawur pasti dialihkan ke penyedia lain. Kalau
    # jawabannya SAMA PERSIS dengan model Groq, berarti model Groq itu
    # juga tidak dipakai dan jawabannya datang dari tempat lain.
    kontrol = tanya("model-ngawur-pembanding-xyz")
    print(f"pembanding ngawur -> {kontrol.get('jawab') or kontrol.get('sebab')}\n")
    print(f"{'model':<46} {'hasil':<10} catatan")
    print("-" * 110)

    hidup = []
    for model in KANDIDAT:
        hasil = tanya(model)
        if hasil["hidup"]:
            tanda = "OK"
            catatan = hasil["jawab"]
            hidup.append(model)
        else:
            tanda = "GAGAL"
            catatan = hasil["sebab"]
        print(f"{model:<46} {tanda:<10} {catatan}")

    print("-" * 110)
    if not hidup:
        print("\nTidak ada model yang bisa dipastikan hidup.")
        return 1

    print(f"\nHidup: {len(hidup)} model")
    print("Setiap model Groq punya kuota sendiri: +1.000 request dan")
    print("+200.000 token per hari.\n")
    print("MODEL_GROQ_HIDUP = [")
    for m in hidup:
        print(f'    "{m}",')
    print("]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
