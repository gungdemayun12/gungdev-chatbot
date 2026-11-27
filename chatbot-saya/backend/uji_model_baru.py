"""
uji_model_baru.py — mencari model TAMBAHAN yang benar-benar hidup untuk
key Gemini Anda, tanpa tertipu oleh pengalihan otomatis.

MENGAPA UJI INI PERLU
---------------------
Server GungDev mengalihkan model yang tidak dikenal ke model default.
Akibatnya, memanggil /chat dengan nama model sembarang tetap dibalas
200 "SIAP" — padahal model itu belum tentu ada. Kalau kita menambah
model ke daftar hanya berdasarkan respons 200, daftar akan penuh nama
model yang sebenarnya tidak pernah dipakai.

Jadi uji ini memanggil Gemini LANGSUNG (bukan lewat server kita) dan
memeriksa dua hal:
  1. HTTP 200 dengan isi jawaban yang tidak kosong.
  2. Balasan menyebut nama model yang diminta (bila model bisa menurut),
     sebagai bukti model itu memang menjawab.

Karena model belum tentu mau menyebut namanya, bukti utama tetap:
HTTP 200 + isi jawaban wajar + tidak ada pesan "model not found".

CARA PAKAI
----------
    # PowerShell
    $env:GEMINI_API_KEY="AIza..."
    python uji_model_baru.py

Hasilnya: daftar kandidat yang layak ditambahkan, plus baris
`GEMINI_MODELS = [...]` siap salin ke main.py.
"""

import os
import sys
import time

import httpx

BASE = "https://generativelanguage.googleapis.com/v1beta/openai"

# Kandidat model yang BELUM ada di GEMINI_MODELS. Semuanya nama Gemini
# generasi 3.5 ke atas — generasi 2.x sudah dimatikan/deprecated Google,
# jadi tidak diuji lagi.
KANDIDAT = [
    # Varian "flash" yang lebih besar: biasanya lebih pintar, lebih lambat.
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-4-hydrogen",
    "gemini-4-argon",
    # Varian "lite": cepat & hemat, cocok jadi cadangan.
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-4-argon-lite",
    "gemini-3.8-flash-lite",
    # Varian "pro" (bila tersedia untuk free tier).
    "gemini-3.5-pro",
    "gemini-4-pro",
]

# Batas waktu satu panggilan (detik). Model reasoning bisa lambat; yang
# lebih lambat dari ini juga tidak layak dipakai di Vercel Hobby karena
# fungsi Vercel diputus sekitar 60 detik.
BATAS_DETIK = 25.0

PERTANYAAN = "Sebutkan nama model AI yang sedang menjawab ini, satu baris saja."


def _headers(key: str) -> dict:
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def uji(http: httpx.Client, key: str, model: str) -> dict:
    """Memanggil model dan menilai apakah jawabannya sungguh berasal darinya."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Jawab sangat singkat."},
            {"role": "user", "content": PERTANYAAN},
        ],
        "temperature": 0.1,
        "max_tokens": 60,
    }

    mulai = time.time()
    try:
        res = http.post(
            f"{BASE}/chat/completions",
            headers=_headers(key),
            json=payload,
            timeout=BATAS_DETIK,
        )
    except httpx.TimeoutException:
        return {"ok": False, "kode": "timeout", "sebab": f"lebih dari {BATAS_DETIK:.0f} dtk"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "kode": "error", "sebab": str(exc)[:70]}

    detik = time.time() - mulai

    if res.status_code != 200:
        badan = res.text[:160].replace("\n", " ")
        return {"ok": False, "kode": res.status_code, "sebab": badan}

    try:
        data = res.json()
        isi = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except Exception:  # noqa: BLE001
        return {"ok": False, "kode": 200, "sebab": "balasan bukan JSON"}

    isi = isi.strip()
    if not isi:
        return {"ok": False, "kode": 200, "sebab": "jawaban kosong"}

    # Bukti tambahan: bila model menyebut namanya sendiri, cocokkan.
    menyebut = model.lower() in isi.lower()

    return {
        "ok": True,
        "kode": 200,
        "detik": detik,
        "sebab": isi[:72].replace("\n", " "),
        "menyebut": menyebut,
    }


def uji_stream(http: httpx.Client, key: str, model: str) -> bool:
    """Memastikan model juga bisa streaming — syarat utama UI chat."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Hitung 1 sampai 3."}],
        "temperature": 0.1,
        "max_tokens": 40,
        "stream": True,
    }
    try:
        with http.stream(
            "POST",
            f"{BASE}/chat/completions",
            headers=_headers(key),
            json=payload,
            timeout=BATAS_DETIK,
        ) as res:
            if res.status_code != 200:
                return False
            ada = False
            for baris in res.iter_lines():
                if baris.startswith("data:") and '"delta"' in baris:
                    ada = True
                    break
            return ada
    except Exception:  # noqa: BLE001
        return False


def main() -> int:
    key = (os.environ.get("GEMINI_API_KEY") or "").strip()
    if not key:
        print("GEMINI_API_KEY belum diisi.")
        print('PowerShell:  $env:GEMINI_API_KEY="AIza..."')
        print("Ambil gratis di https://aistudio.google.com/apikey")
        return 2

    print(f"Endpoint : {BASE}")
    print(f"Kandidat : {len(KANDIDAT)} model")
    print(f"Batas    : {BATAS_DETIK:.0f} detik per panggilan\n")
    print(f"{'model':<26} {'teks':<9} {'stream':<8} {'detik':<7} catatan")
    print("-" * 100)

    hidup = []
    with httpx.Client() as http:
        for model in KANDIDAT:
            hasil = uji(http, key, model)
            if not hasil["ok"]:
                print(
                    f"{model:<26} {str(hasil['kode']):<9} {'-':<8} {'-':<7} {hasil['sebab']}"
                )
                continue

            stream_ok = uji_stream(http, key, model)
            tanda = "ya" if hasil["menyebut"] else "-"
            print(
                f"{model:<26} {'OK':<9} "
                f"{('OK' if stream_ok else 'GAGAL'):<8} "
                f"{hasil['detik']:<7.2f} disebut={tanda} | {hasil['sebab']}"
            )
            hidup.append(
                {
                    "model": model,
                    "stream": stream_ok,
                    "detik": round(hasil["detik"], 2),
                    "menyebut": hasil["menyebut"],
                }
            )

    print("-" * 100)
    if not hidup:
        print("\nTidak ada kandidat yang hidup untuk key ini.")
        return 1

    # Hanya yang cepat & bisa streaming yang layak jadi default/cadangan.
    layak = [h for h in hidup if h["stream"] and h["detik"] <= BATAS_DETIK]
    layak.sort(key=lambda h: h["detik"])

    print(f"\nHidup: {len(hidup)} model. Layak dipakai: {len(layak)}.\n")
    print("Urutan usulan (tercepat lebih dulu):")
    for h in layak:
        print(f"  {h['model']:<26} {h['detik']:>6.2f} dtk")

    print("\nSalin bila setuju:\n")
    print("GEMINI_MODELS = [")
    for h in layak:
        print(f'    "{h["model"]}",')
    print("]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
