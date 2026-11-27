"""
server_uji.py — backend dengan penyimpanan & identitas TIRUAN.

Dipakai pengujian browser (Playwright): menjalankan kode backend yang
SAMA PERSIS dengan produksi, tetapi:
  - Upstash dipalsukan (Redis di memori) -> tidak perlu akun Upstash
  - tokeninfo Google dipalsukan          -> tidak perlu token asli
  - penyedia AI dipalsukan               -> kuota Groq tidak terbakar

Dengan begitu alur nyata (verifikasi token, kunci per akun, isolasi antar
akun, usage per akun, sinkron lintas perangkat) tetap diuji.
"""
import os

os.environ["UPSTASH_REDIS_REST_URL"] = "https://upstash-tiruan.local"
os.environ["UPSTASH_REDIS_REST_TOKEN"] = "tiruan"
os.environ["GOOGLE_CLIENT_ID"] = "uji.apps.googleusercontent.com"
os.environ["AI_PROVIDER"] = "ollama"

import asyncio
import json
import sys
from datetime import datetime, timezone

import httpx

# ---------------------------------------------------------------------
# Redis mini
# ---------------------------------------------------------------------
DB = {}
JEJAK = []


def redis(perintah):
    op = str(perintah[0]).upper()
    a = [str(x) for x in perintah[1:]]
    JEJAK.append({"op": op, "kunci": a[0] if a else "", "nilai": a[1][:60] if len(a) > 1 else ""})

    if op == "SET":
        DB[a[0]] = a[1]
        return "OK"
    if op == "GET":
        return DB.get(a[0])
    if op == "DEL":
        n = 0
        for k in a:
            if k in DB:
                del DB[k]
                n += 1
        return n
    if op == "MGET":
        return [DB.get(k) for k in a]
    if op == "HINCRBY":
        cur = DB.get(a[0])
        if not isinstance(cur, dict):
            cur = {}
        cur[a[1]] = int(cur.get(a[1], 0)) + int(a[2])
        DB[a[0]] = cur
        return cur[a[1]]
    if op == "HMGET":
        cur = DB.get(a[0]) or {}
        return [str(cur.get(f, "0")) if f in cur else None for f in a[1:]]
    if op == "EXPIRE":
        return 1
    if op == "ZADD":
        cur = DB.get(a[0])
        if not isinstance(cur, dict):
            cur = {}
        cur[a[2]] = float(a[1])
        DB[a[0]] = cur
        return 1
    if op == "ZRANGE":
        cur = DB.get(a[0]) or {}
        rev = "REV" in [s.upper() for s in a[3:]]
        urut = sorted(cur.items(), key=lambda x: x[1], reverse=rev)
        items = [k for k, _ in urut]
        awal, akhir = int(a[1]), int(a[2])
        return items[awal:] if akhir == -1 else items[awal : akhir + 1]
    if op == "ZREM":
        cur = DB.get(a[0]) or {}
        n = 0
        for k in a[1:]:
            if k in cur:
                del cur[k]
                n += 1
        DB[a[0]] = cur
        return n
    if op == "ZCARD":
        return len(DB.get(a[0]) or {})
    if op == "LREM":
        return 0
    raise AssertionError("perintah Redis tidak dikenal: " + op)


# Token uji: dua akun berbeda
TOKEN_VALID = {
    "token-akun-a": {
        "aud": os.environ["GOOGLE_CLIENT_ID"],
        "sub": "100000000000000001",
        "email": "akun.a@gmail.com",
        "name": "Akun A",
        "email_verified": "true",
    },
    "token-akun-b": {
        "aud": os.environ["GOOGLE_CLIENT_ID"],
        "sub": "200000000000000002",
        "email": "akun.b@gmail.com",
        "name": "Akun B",
        "email_verified": "true",
    },
}


class ResTiruan:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)
        self.headers = {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("tiruan", request=None, response=None)


class SelisihTiruan:
    """Meniru httpx.HTTPStatusError dengan respons tiruan."""

    class _Res:
        status_code = 500
        text = "penyedia palsu"

        def json(self):
            return {"error": {"message": "penyedia palsu"}}

    response = _Res()


class ClientTiruan:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None, **kw):
        if "upstash" in url:
            return ResTiruan(200, {"result": redis(json)})
        # Panggilan ke penyedia AI -> balasan palsu.
        if "chat/completions" in url:
            return ResTiruan(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": "Jawaban uji dari server.",
                                "reasoning": None,
                            }
                        }
                    ]
                },
            )
        return ResTiruan(404, {})

    async def get(self, url, params=None, **kw):
        if "tokeninfo" in url:
            data = TOKEN_VALID.get((params or {}).get("id_token", ""))
            return ResTiruan(200, data) if data else ResTiruan(400, {"error": "invalid_token"})
        # Wikipedia (riset web tiruan) -> hasil palsu tapi berbentuk sama.
        # Judul sengaja memuat kata kunci query, karena riset.py menyaring
        # hasil yang tidak relevan (perilaku nyata yang harus diuji apa
        # adanya, bukan dilewati).
        if "wikipedia.org" in url:
            kueri = (params or {}).get("srsearch") or "topik"
            judul = str(kueri)[:60]
            if "rest_v1/page/summary" in url:
                return ResTiruan(
                    200,
                    {
                        "title": judul,
                        "extract": (
                            f"Ini ringkasan artikel uji tentang {judul} dari "
                            "ensiklopedia yang dipakai untuk memastikan riset web "
                            "benar-benar menyertakan sumber."
                        ),
                    },
                )
            return ResTiruan(
                200,
                {
                    "query": {
                        "search": [
                            {
                                "title": judul,
                                "snippet": f"Ringkasan uji tentang <b>{judul}</b>.",
                            },
                            {
                                "title": f"{judul} lanjutan",
                                "snippet": f"Keterangan tambahan tentang {judul}.",
                            },
                        ]
                    }
                },
            )
        if "bing.com" in url:
            kelas = type("R", (), {})()
            kelas.status_code = 200
            kelas.text = "<html><body></body></html>"
            kelas.headers = {}
            return kelas
        return ResTiruan(404, {})

    def build_request(self, *a, **k):
        raise AssertionError("tidak dipakai dalam uji")

    async def send(self, *a, **k):
        raise AssertionError("tidak dipakai dalam uji")


httpx.AsyncClient = ClientTiruan  # type: ignore[misc]

import main  # noqa: E402
import penyimpanan  # noqa: E402
import identitas  # noqa: E402
import usage  # noqa: E402

penyimpanan._UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]
penyimpanan._UPSTASH_TOKEN = "tiruan"
identitas.GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
usage._UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]
usage._UPSTASH_TOKEN = "tiruan"


# ---------------------------------------------------------------------
# /chat/stream palsu: SSE bertahap (tanpa menyentuh penyedia AI)
# ---------------------------------------------------------------------
from fastapi.responses import StreamingResponse  # noqa: E402

# PENTING: FastAPI memakai ROUTE PERTAMA yang cocok. Stub di bawah harus
# didaftarkan SEBELUM route produksi, jadi route lama dibuang lebih dulu.
main.app.router.routes = [
    r for r in main.app.router.routes if getattr(r, "path", "") not in ("/chat", "/chat/stream")
]

# ---------------------------------------------------------------------
# PERLAMBATAN BUATAN (hanya untuk uji animasi "berpikir").
#
# Jawaban stub biasanya selesai dalam ~0,1 detik, sehingga animasi
# berpikir tidak sempat terlihat (dan tidak bisa diuji). Nilai ini
# mengatur berapa detik stub MENAHAN jawaban sebelum mengirim teks.
# Bawaannya 0 (perilaku lama, semua uji lain tidak terpengaruh).
# ---------------------------------------------------------------------
_JEDA_UJI = {"detik": 0.0}


@main.app.post("/__uji/jeda")
async def atur_jeda(payload: dict):
    """Atur jeda buatan sebelum jawaban dikirim (detik)."""
    _JEDA_UJI["detik"] = max(0.0, float(payload.get("detik", 0)))
    return {"ok": True, "detik": _JEDA_UJI["detik"]}


@main.app.post("/chat")
async def chat_uji(request: main.ChatRequest, authorization: str | None = main.Header(None)):
    """
    Versi /chat untuk uji: membalas {reply} tanpa menyentuh penyedia AI.

    PENTING: stub ini WAJIB memakai jalur jatah yang sama dengan produksi
    (periksa_jatah + pesan_jatah_habis). Sempat terjadi: stub tidak
    memeriksa jatah sehingga uji jatah "lulus" padahal endpoint
    produksinya bisa saja salah. Yang diuji harus jalur yang sama.
    """
    akun = await main.identitas_pemanggil(authorization)
    jatah = await usage.periksa_jatah((akun or {}).get("sub"))
    if not jatah["boleh"]:
        raise main.HTTPException(status_code=429, detail=main.pesan_jatah_habis(jatah))

    await usage.catat_request(
        tokens=usage.TOKEN_MIN_PER_REQUEST, model="openai/gpt-oss-120b", sub=jatah.get("sub")
    )
    return {"reply": f"Jawaban untuk: {request.message[:40]}"}


@main.app.post("/chat/stream")
async def chat_stream_uji(request: main.ChatRequest, authorization: str | None = main.Header(None)):
    akun = await main.identitas_pemanggil(authorization)

    # Jatah diperiksa SEBELUM stream dimulai, sama seperti produksi.
    jatah = await usage.periksa_jatah((akun or {}).get("sub"))
    if not jatah["boleh"]:
        raise main.HTTPException(status_code=429, detail=main.pesan_jatah_habis(jatah))

    def sse(obj):
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    async def aliran():
        teks = f"Jawaban untuk: {request.message[:40]}"
        # Sumber riset tiruan: dikirim lewat event `meta` persis seperti
        # produksi, supaya kartu sumber di UI bisa diuji tanpa jaringan.
        if _SUMBER_UJI["sumber"]:
            yield sse({"meta": {"model": "openai/gpt-oss-120b", "sumber": _SUMBER_UJI["sumber"]}})
            teks = "Harga mulai Rp400.000 [1] dan Rp350.000 [2]."
        # Jeda buatan agar animasi "berpikir" bisa diamati/diuji.
        if _JEDA_UJI["detik"] > 0:
            await asyncio.sleep(_JEDA_UJI["detik"])
        for potong in [teks[: len(teks) // 2], teks[len(teks) // 2 :]]:
            await asyncio.sleep(0.05)
            yield sse({"delta": potong})
        await usage.catat_request(
            tokens=usage.TOKEN_MIN_PER_REQUEST, model="openai/gpt-oss-120b", sub=jatah.get("sub")
        )
        yield sse({"done": True})

    return StreamingResponse(aliran(), media_type="text/event-stream")


# ---------------------------------------------------------------------
# Sumber riset tiruan untuk uji kartu sumber di UI.
# Bawaannya kosong, jadi semua uji lain tidak terpengaruh.
# ---------------------------------------------------------------------
_SUMBER_UJI = {"sumber": []}


@main.app.post("/__uji/sumber")
async def atur_sumber(payload: dict):
    """Mengisi/mengosongkan daftar sumber tiruan untuk uji UI."""
    _SUMBER_UJI["sumber"] = payload.get("sumber") or []
    return {"ok": True, "jumlah": len(_SUMBER_UJI["sumber"])}


@main.app.get("/__uji/db")
async def lihat_db():
    """Untuk memeriksa isi penyimpanan dari dalam tes (hanya saat uji)."""
    return {"kunci": sorted(DB.keys())}


@main.app.get("/__uji/log")
async def lihat_log():
    """Jejak semua perintah Redis (untuk menelusuri siapa menulis apa)."""
    return {"log": JEJAK[-80:]}


@main.app.post("/__uji/pakai")
async def isi_pemakaian(data: dict):
    """
    Mengisi angka pemakaian akun untuk menguji penegakan jatah.

    Dipakai uji_api.py agar bisa mensimulasikan "akun sudah memakai 100
    pesan" tanpa harus benar-benar mengirim 100 pesan.

    Pemakaian kini disimpan pada JENDELA 24 JAM milik akun, jadi kuncinya
    berasal dari _jendela_akun (bukan tanggal kalender lagi).
    """
    import usage as _usage

    sub = str(data.get("sub") or "")
    req = int(data.get("requests") or 0)
    tok = int(data.get("tokens") or 0)

    if sub:
        jendela = await _usage._jendela_akun(sub)
        kunci = jendela["kunci"]
    else:
        kunci = _usage._kunci_harian()

    DB[kunci] = {"requests": req, "tokens": tok}
    return {"ok": True, "kunci": kunci}


@main.app.post("/__uji/jendela")
async def atur_jendela(data: dict):
    """
    Memundurkan awal jendela jatah akun, untuk menguji RESET.

    Dengan memundurkan `mulai` lebih dari durasi jendela, jendela akun itu
    dianggap sudah berakhir — sehingga pemakaian harus kembali 0 dan akun
    boleh chat lagi. Ini cara menguji reset tanpa menunggu 24 jam.
    """
    import usage as _usage

    sub = str(data.get("sub") or "")
    mundur = int(data.get("mundur_detik") or 0)
    if not sub or mundur <= 0:
        return {"ok": False}

    kunci_jendela = f"{_usage._PREFIX}:jendela:{sub}"
    DB[kunci_jendela] = str(
        int(datetime.now(timezone.utc).timestamp()) - mundur
    )
    return {"ok": True, "kunci": kunci_jendela}


@main.app.get("/__uji/jendela/{sub}")
async def lihat_jendela(sub: str):
    """Melihat jendela jatah akun (untuk verifikasi uji)."""
    import usage as _usage

    jendela = await _usage._jendela_akun(sub)
    return {
        "kunci": jendela["kunci"],
        "sisa_detik": jendela["sisa_detik"],
        "akhir": jendela["akhir"],
    }


@main.app.post("/__uji/reset")
async def reset_uji(data: dict):
    """
    Menghapus TOTAL jejak uji untuk satu akun: pemakaian jatah dan riwayat.

    Mengapa perlu: tiap rangkaian uji mengubah state server. Bila satu uji
    menyisakan akun dalam keadaan "jatah habis", uji berikutnya gagal
    karena sebab yang salah — dan hasilnya jadi bergantung urutan.
    Endpoint ini membuat tiap rangkaian uji mulai dari keadaan yang sama.
    """
    import usage as _usage
    import penyimpanan as _penyimpanan

    sub = str(data.get("sub") or "")
    if not sub:
        return {"ok": False}

    dihapus = []

    # 1. Jendela + pemakaian jatah.
    kunci_jendela = f"{_usage._PREFIX}:jendela:{sub}"
    DB.pop(kunci_jendela, None)
    _usage._memori.pop(kunci_jendela, None)
    for k in list(DB.keys()):
        if k.startswith(f"{_usage._PREFIX}:u:{sub}:"):
            DB.pop(k, None)
            dihapus.append(k)
    for k in list(_usage._memori.keys()):
        if str(k).startswith(f"{_usage._PREFIX}:u:{sub}:"):
            _usage._memori.pop(k, None)

    # 2. Riwayat percakapan akun itu.
    try:
        await _penyimpanan.hapus_semua(sub)
        dihapus.append("riwayat")
    except Exception:  # noqa: BLE001
        pass

    return {"ok": True, "dihapus": dihapus}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    print("Server uji siap di http://127.0.0.1:%s" % port, flush=True)
    uvicorn.run(main.app, host="127.0.0.1", port=port, log_level="warning")
