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
# Gambar tiruan untuk pengujian (JPEG 1x1 piksel yang sah).
# Dipakai agar jalur pembuatan gambar bisa diuji tanpa internet.
# ---------------------------------------------------------------------
JPEG_UJI = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n"
    b"\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d"
    b"\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\xff\xc0\x00"
    b"\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00"
    b"\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00"
    b"\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00\xb5\x10\x00"
    b"\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00\x01}\x01\x02"
    b"\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81\x91\xa1\x08"
    b"\x23B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19\x1a%&'()*456"
    b"789:CDEFGHIJSTUVWXYZcdefghijstuvwxyz\x83\x84\x85\x86\x87\x88\x89\x8a"
    b"\x92\x93\x94\x95\x96\x97\x98\x99\x9a\xa2\xa3\xa4\xa5\xa6\xa7\xa8\xa9"
    b"\xaa\xb2\xb3\xb4\xb5\xb6\xb7\xb8\xb9\xba\xc2\xc3\xc4\xc5\xc6\xc7\xc8"
    b"\xc9\xca\xd2\xd3\xd4\xd5\xd6\xd7\xd8\xd9\xda\xe1\xe2\xe3\xe4\xe5\xe6"
    b"\xe7\xe8\xe9\xea\xf1\xf2\xf3\xf4\xf5\xf6\xf7\xf8\xf9\xfa\xff\xda\x00"
    b"\x08\x01\x01\x00\x00?\x00\xd2\xcf \xff\xd9"
)

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
        # Layanan gambar (uji): kembalikan JPEG kecil yang sah, sehingga
        # jalur gambar bisa diuji di browser tanpa mengambil gambar
        # sungguhan. Isinya bukan gambar bermakna — hanya JPEG 1x1.
        if "image.pollinations.ai" in url or "/prompt" in url:
            kelas = type("R", (), {})()
            kelas.status_code = 200
            kelas.content = JPEG_UJI
            kelas.headers = {"content-type": "image/jpeg"}
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

    Hal yang sama berlaku untuk PEMBUATAN GAMBAR: stub memanggil
    `main.siapkan_gambar` yang SAMA dengan produksi (jatah gambar
    terpisah, deteksi niat, dsb.). Tanpa ini, uji browser tidak
    menguji apa pun yang berarti untuk fitur gambar.
    """
    akun = await main.identitas_pemanggil(authorization)

    hasil_gambar = await main.siapkan_gambar(request, (akun or {}).get("sub"))
    if hasil_gambar and hasil_gambar["jenis"] == "berhasil":
        return {
            "reply": hasil_gambar["pesan"],
            "gambar": {
                "data_url": hasil_gambar["data_url"],
                "deskripsi": hasil_gambar["deskripsi"],
                "sunting": hasil_gambar["sunting"],
                # Sama seperti produksi (lihat main.py): penanda mesin
                # dipakai UI untuk membedakan gambar baru dari gambar lama.
                "mesin": hasil_gambar.get("mesin"),
            },
        }
    if hasil_gambar and hasil_gambar["jenis"] in ("jatah_habis", "gagal"):
        # Sama seperti produksi: pesan jelas, TANPA memakai jatah chat.
        return {"reply": hasil_gambar["pesan"]}

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

    def sse(obj):
        return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"

    # Jalur gambar SAMA dengan produksi (lihat chat_uji di atas).
    #
    # URUTANNYA JUGA HARUS SAMA: `meta.gambar_dimulai` dikirim LEBIH DULU
    # sebelum gambar dibuat. Tanpa ini, uji browser tidak akan pernah
    # melihat animasi "Sedang menggambar" padahal produksinya memakai
    # urutan itu — uji akan lulus sambil tidak menguji apa pun.
    if main.perlu_gambar(request):
        async def aliran_gambar():
            jatah_gambar = await usage.periksa_jatah_gambar((akun or {}).get("sub"))
            if not jatah_gambar["boleh"]:
                yield sse({"delta": usage.pesan_jatah_gambar_habis(jatah_gambar)})
                yield sse({"done": True})
                return

            yield sse({"meta": {"gambar_dimulai": {
                "deskripsi": main.deskripsi_untuk_ui(request),
            }}})

            # Jeda tiruan: meniru layanan gambar yang butuh waktu, supaya
            # animasi "Sedang menggambar" sempat terlihat dan bisa diuji.
            if _JEDA_UJI["detik"] > 0:
                await asyncio.sleep(_JEDA_UJI["detik"])

            hasil_gambar = await main.siapkan_gambar(request, (akun or {}).get("sub"))
            if hasil_gambar and hasil_gambar["jenis"] == "berhasil":
                yield sse({"meta": {"gambar": {
                    "data_url": hasil_gambar["data_url"],
                    "deskripsi": hasil_gambar["deskripsi"],
                    "sunting": hasil_gambar["sunting"],
                    "mesin": hasil_gambar.get("mesin"),
                }}})
                yield sse({"delta": hasil_gambar["pesan"]})
            elif hasil_gambar:
                yield sse({"delta": hasil_gambar["pesan"]})
            else:
                yield sse({"delta": main.gambar_mod.pesan_tidak_tersedia()})
            yield sse({"done": True})

        return StreamingResponse(aliran_gambar(), media_type="text/event-stream")

    # Jatah diperiksa SEBELUM stream dimulai, sama seperti produksi.
    jatah = await usage.periksa_jatah((akun or {}).get("sub"))
    if not jatah["boleh"]:
        raise main.HTTPException(status_code=429, detail=main.pesan_jatah_habis(jatah))

    async def aliran():
        teks = f"Jawaban untuk: {request.message[:40]}"
        # Sumber riset tiruan: dikirim lewat event `meta` persis seperti
        # produksi, supaya kartu sumber di UI bisa diuji tanpa jaringan.
        if _SUMBER_UJI["sumber"]:
            yield sse({"meta": {"model": "openai/gpt-oss-120b", "sumber": _SUMBER_UJI["sumber"]}})
            # Bentuk jawaban bisa dipilih agar daftar berbutir ikut teruji
            # (penanda [2] di akhir setiap butir pernah memutus daftar).
            if _SUMBER_UJI["bentuk"] == "daftar":
                teks = (
                    "**2. Bali Top Holiday**\n\n"
                    "- Paket Ekonomis 3H2M: start Rp 1.440.000/pax [2]\n"
                    "- Paket Simple Group 3H2M: start Rp 1.490.000/pax [2]\n"
                    "- Paket Ekonomis 4H3M: start Rp 2.070.000/pax [2]\n"
                    "- Bulan Madu 3H2M: Rp 5.400.000/couple [2]\n"
                )
            else:
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
_SUMBER_UJI = {"sumber": [], "bentuk": "ringkas"}


@main.app.post("/__uji/jatah-gambar")
async def jatah_gambar_uji(payload: dict):
    """
    Melaporkan pemakaian jatah GAMBAR satu akun (untuk pengujian).

    Hanya ada di server uji. Dipakai uji browser untuk membuktikan bahwa
    jatah gambar benar-benar bertambah sementara jatah chat tetap.
    """
    sub = str(payload.get("sub") or "")
    j = await usage.periksa_jatah_gambar(sub or None)
    # `jumlah` opsional: dipakai uji panel untuk membuat pemakaian tanpa
    # harus membuat gambar sungguhan (yang memakan waktu & kuota).
    for _ in range(int(payload.get("jumlah") or 0)):
        await usage.catat_gambar(sub)
    if payload.get("jumlah"):
        j = await usage.periksa_jatah_gambar(sub or None)
    return {"terpakai": j["terpakai"], "batas": j["batas"], "boleh": j["boleh"]}


@main.app.post("/__uji/jatah-gambar-bebaskan")
async def bebaskan_jatah_gambar_uji(payload: dict):
    """
    Mengosongkan jatah GAMBAR satu akun (HANYA untuk pengujian).

    MENGAPA PERLU: jatah gambar akun hanya 3 per 24 jam. Satu berkas uji
    menjalankan beberapa skenario berurutan, sehingga tanpa ini skenario
    berikutnya sudah kehabisan jatah — tidak mendapat gambar, tidak
    mendapat `meta.gambar_dimulai`, dan uji animasi gagal bukan karena
    ada bug.

    Sengaja memakai jalur yang sama dengan `catat_gambar` (kunci yang
    sama), supaya yang dibersihkan benar-benar data yang dipakai
    produksi. Endpoint ini tidak ada di produksi.
    """
    sub = str(payload.get("sub") or "")
    if not sub:
        return {"ok": False, "alasan": "sub kosong"}

    try:
        jendela = await usage._jendela_akun(sub)
        kunci = usage._kunci_gambar(sub, jendela["mulai"])
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "alasan": str(exc)}

    if usage._UPSTASH_URL and usage._UPSTASH_TOKEN:
        try:
            await usage._redis_perintah("DEL", kunci)
            return {"ok": True, "kunci": kunci}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "alasan": str(exc)}

    usage._memori.pop(kunci, None)
    return {"ok": True, "kunci": kunci}


@main.app.post("/__uji/sumber")
async def atur_sumber(payload: dict):
    """Mengisi/mengosongkan daftar sumber tiruan untuk uji UI."""
    _SUMBER_UJI["sumber"] = payload.get("sumber") or []
    _SUMBER_UJI["bentuk"] = payload.get("bentuk") or "ringkas"
    return {"ok": True, "jumlah": len(_SUMBER_UJI["sumber"]), "bentuk": _SUMBER_UJI["bentuk"]}


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
