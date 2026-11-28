"""
uji_server_riwayat.py — menguji penyimpanan riwayat & usage per akun
TANPA membutuhkan Upstash asli.

Cara kerja: `httpx.AsyncClient` dipalsukan, sehingga:
  - panggilan ke Google tokeninfo  -> dijawab token tiruan
  - panggilan ke Upstash REST      -> dijawab Redis mini di memori

Jadi seluruh alur (verifikasi identitas, kunci per akun, isolasi antar
akun, usage terpisah) benar-benar dijalankan oleh kode produksi.
"""

import asyncio
import json
import os
import sys
import time

# Upstash tiruan harus aktif SEBELUM modul backend diimpor, karena
# penyimpanan.py membaca env saat modul dimuat.
os.environ["UPSTASH_REDIS_REST_URL"] = "https://upstash-tiruan.local"
os.environ["UPSTASH_REDIS_REST_TOKEN"] = "tiruan"
os.environ["GOOGLE_CLIENT_ID"] = "klien-uji.apps.googleusercontent.com"

import httpx  # noqa: E402

# ---------------------------------------------------------------------
# Redis mini di memori
# ---------------------------------------------------------------------
DB = {}


def redis(perintah):
    op = str(perintah[0]).upper()
    a = [str(x) for x in perintah[1:]]

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
        urut = sorted(cur.items(), key=lambda x: x[1], reverse="REV" in [s.upper() for s in a[3:]])
        awal, akhir = int(a[1]), int(a[2])
        items = [k for k, _ in urut]
        if akhir == -1:
            return items[awal:]
        return items[awal : akhir + 1]
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
    raise AssertionError(f"perintah Redis tidak dikenal: {op}")


# Token tiruan: token -> payload yang "diverifikasi Google"
TOKEN_VALID = {
    "token-budi": {
        "aud": os.environ["GOOGLE_CLIENT_ID"],
        "sub": "111122223333444455",
        "email": "budi@gmail.com",
        "name": "Budi Santoso",
        "email_verified": "true",
    },
    "token-sari": {
        "aud": os.environ["GOOGLE_CLIENT_ID"],
        "sub": "999988887777666655",
        "email": "sari@gmail.com",
        "name": "Sari Dewi",
        "email_verified": "true",
    },
}


class ResTiruan:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
        self.text = json.dumps(data)

    def json(self):
        return self._data


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
        return ResTiruan(404, {})

    async def get(self, url, params=None, **kw):
        if "tokeninfo" in url:
            token = (params or {}).get("id_token", "")
            data = TOKEN_VALID.get(token)
            if data:
                return ResTiruan(200, data)
            return ResTiruan(400, {"error": "invalid_token"})
        return ResTiruan(404, {})


httpx.AsyncClient = ClientTiruan  # type: ignore[misc]

import main  # noqa: E402
import penyimpanan  # noqa: E402

# Konfigurasi modul dibaca saat impor -> paksa agar memakai tiruan.
penyimpanan._UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]
penyimpanan._UPSTASH_TOKEN = "tiruan"
import identitas  # noqa: E402

identitas.GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]
import usage  # noqa: E402

usage._UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]
usage._UPSTASH_TOKEN = "tiruan"

HASIL = []


def cek(nama, lulus, info=""):
    HASIL.append((nama, lulus, info))
    print(f"{'LULUS' if lulus else 'GAGAL'}  {nama}{(' — ' + str(info)) if info else ''}")


def sesi(sid, judul, pesan_teks, updated=None):
    """
    Membuat objek sesi untuk pengujian.

    `updated` sengaja default ke waktu sekarang (bukan angka tetap):
    server menolak waktu yang terlalu jauh dari jam sebenarnya, jadi
    angka tetap seperti 2000 hanya akan menguji jalur "jam ngawur".
    """
    if updated is None:
        updated = int(time.time() * 1000)
    return {
        "id": sid,
        "title": judul,
        "titleLocked": False,
        "messages": [
            {"id": sid + "m1", "role": "user", "content": pesan_teks, "createdAt": 1},
            {"id": sid + "m2", "role": "assistant", "content": "Jawaban.", "createdAt": 2},
        ],
        "createdAt": 1000,
        "updatedAt": updated,
        "pinned": False,
    }


async def jalankan():
    print("=" * 60)
    print("BAGIAN 1 — Keamanan identitas")
    print("=" * 60)

    # Tanpa token
    try:
        await main.sessions_daftar(authorization=None)
        cek("Tanpa token ditolak", False, "tidak menolak")
    except main.HTTPException as e:
        cek("Tanpa token ditolak (401)", e.status_code == 401, e.detail[:50])

    # Token palsu
    try:
        await main.sessions_daftar(authorization="Bearer token-palsu")
        cek("Token palsu ditolak", False)
    except main.HTTPException as e:
        cek("Token palsu ditolak (401)", e.status_code == 401)

    # Token sah
    akun = await main.identitas_pemanggil("Bearer token-budi")
    cek("Token sah diterima", akun is not None and akun["sub"] == "111122223333444455", (akun or {}).get("name"))

    # Clien ID lain. Cache dibersihkan dulu karena modul verifikasi
    # sengaja menyimpan hasil baik selama 5 menit (agar tidak memanggil
    # Google untuk setiap pesan). Dalam uji kita ingin memaksa
    # pemeriksaan ulang.
    identitas._cache.clear()
    identitas.GOOGLE_CLIENT_ID = "klien-lain.apps.googleusercontent.com"
    akun_salah = await main.identitas_pemanggil("Bearer token-budi")
    cek("Token dengan audiens lain ditolak", akun_salah is None)
    identitas._cache.clear()
    identitas.GOOGLE_CLIENT_ID = os.environ["GOOGLE_CLIENT_ID"]

    print()
    print("=" * 60)
    print("BAGIAN 2 — Menyimpan & membaca riwayat")
    print("=" * 60)

    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Akun baru: riwayat kosong", hasil["sessions"] == [], f"{len(hasil['sessions'])} sesi")

    sekarang = int(time.time() * 1000)

    ok = await penyimpanan.simpan_sesi(
        "111122223333444455",
        sesi("s_abc123", "Belajar Python", "Apa itu list?", updated=sekarang - 60000),
    )
    cek("Simpan sesi pertama", ok is True)

    ok2 = await penyimpanan.simpan_sesi(
        "111122223333444455",
        sesi("s_def456", "Resep Rendang", "Cara masak rendang?", updated=sekarang),
    )
    cek("Simpan sesi kedua", ok2 is True)

    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Dua sesi terbaca kembali", len(hasil["sessions"]) == 2, len(hasil["sessions"]))
    cek(
        "Urutan terbaru di atas",
        hasil["sessions"][0]["id"] == "s_def456",
        hasil["sessions"][0]["title"],
    )
    cek(
        "Isi pesan utuh",
        hasil["sessions"][0]["messages"][0]["content"] == "Cara masak rendang?",
    )

    # Kasus yang sempat menimbulkan bug: dua sesi dengan updatedAt SAMA
    # (tersimpan pada milidetik yang sama). Urutan harus stabil, bukan
    # berubah-ubah setiap kali dimuat.
    await penyimpanan.simpan_sesi(
        "111122223333444455", sesi("s_seri1", "Seri A", "a", updated=sekarang - 1000)
    )
    await penyimpanan.simpan_sesi(
        "111122223333444455", sesi("s_seri2", "Seri B", "b", updated=sekarang - 1000)
    )
    urutan1 = [s["id"] for s in (await penyimpanan.daftar_sesi("111122223333444455"))["sessions"]]
    urutan2 = [s["id"] for s in (await penyimpanan.daftar_sesi("111122223333444455"))["sessions"]]
    cek("Dua sesi dengan waktu sama -> urutan STABIL", urutan1 == urutan2, f"{urutan1} vs {urutan2}")
    cek("Keduanya tetap ada", {"s_seri1", "s_seri2"}.issubset(set(urutan1)))

    # Jam perangkat yang salah (tahun 1970) tidak boleh menahan sesi
    # di posisi tertentu selamanya.
    await penyimpanan.simpan_sesi(
        "111122223333444455", sesi("s_lama", "Jam 1970", "x", updated=1000)
    )
    urutan3 = [s["id"] for s in (await penyimpanan.daftar_sesi("111122223333444455"))["sessions"]]
    cek("Jam perangkat salah tidak merusak daftar", len(urutan3) == 5, len(urutan3))
    cek(
        "Sesi berjam salah tetap bisa dibuka",
        "s_lama" in urutan3,
        urutan3,
    )
    cek(
        "Semua sesi unik (tidak ada yang tertimpa)",
        len(set(urutan3)) == len(urutan3) == 5,
        urutan3,
    )

    # Bersihkan untuk bagian berikutnya.
    await penyimpanan.hapus_sesi("111122223333444455", "s_seri1")
    await penyimpanan.hapus_sesi("111122223333444455", "s_seri2")
    await penyimpanan.hapus_sesi("111122223333444455", "s_lama")
    await penyimpanan.simpan_sesi(
        "111122223333444455",
        sesi("s_abc123", "Belajar Python", "Apa itu list?", updated=sekarang - 60000),
    )
    await penyimpanan.simpan_sesi(
        "111122223333444455",
        sesi("s_def456", "Resep Rendang", "Cara masak rendang?", updated=sekarang),
    )

    print()
    print("=" * 60)
    print("BAGIAN 3 — Isolasi antar akun (yang paling penting)")
    print("=" * 60)

    hasil_sari = await penyimpanan.daftar_sesi("999988887777666655")
    cek("Akun Sari TIDAK melihat riwayat Budi", hasil_sari["sessions"] == [], f"{len(hasil_sari['sessions'])} sesi")

    await penyimpanan.simpan_sesi("999988887777666655", sesi("s_sari01", "Catatan Sari", "Rahasia Sari"))
    hasil_sari = await penyimpanan.daftar_sesi("999988887777666655")
    hasil_budi = await penyimpanan.daftar_sesi("111122223333444455")

    cek("Sari melihat riwayatnya sendiri", len(hasil_sari["sessions"]) == 1, hasil_sari["sessions"][0]["title"])
    cek("Budi tetap 2 sesi (tidak tercampur)", len(hasil_budi["sessions"]) == 2, len(hasil_budi["sessions"]))
    cek(
        "Isi rahasia Sari tidak terlihat Budi",
        all("Rahasia Sari" not in json.dumps(s) for s in hasil_budi["sessions"]),
    )

    # Percobaan menyusup lewat sub aneh
    cek("sub dengan pola aneh ditolak", penyimpanan.sub_sah("../rahasia") is None)
    cek("sub kosong ditolak", penyimpanan.sub_sah("") is None)
    cek("sub sah diterima", penyimpanan.sub_sah("111122223333444455") == "111122223333444455")

    print()
    print("=" * 60)
    print("BAGIAN 4 — Menghapus")
    print("=" * 60)

    await penyimpanan.simpan_aktif("111122223333444455", "s_def456")
    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Sesi aktif tersimpan", hasil["activeId"] == "s_def456", hasil["activeId"])

    await penyimpanan.hapus_sesi("111122223333444455", "s_def456")
    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Hapus satu sesi berhasil", len(hasil["sessions"]) == 1, len(hasil["sessions"]))
    cek("Sesi aktif ikut dibersihkan", hasil["activeId"] is None, hasil["activeId"])

    await penyimpanan.hapus_semua("111122223333444455")
    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Hapus semua berhasil", hasil["sessions"] == [])

    hasil_sari = await penyimpanan.daftar_sesi("999988887777666655")
    cek("Hapus semua Budi tidak menyentuh Sari", len(hasil_sari["sessions"]) == 1)

    print()
    print("=" * 60)
    print("BAGIAN 5 — Usage per akun")
    print("=" * 60)

    await usage.catat_request(tokens=100, model="openai/gpt-oss-120b", sub="111122223333444455")
    await usage.catat_request(tokens=150, model="openai/gpt-oss-120b", sub="111122223333444455")
    await usage.catat_request(tokens=999, model="openai/gpt-oss-120b", sub="999988887777666655")

    milik_budi = await usage.baca_harian("111122223333444455")
    milik_sari = await usage.baca_harian("999988887777666655")
    global_semua = await usage.baca_harian()

    cek("Pemakaian Budi = 2 permintaan", milik_budi["requests"] == 2, milik_budi)
    cek("Token Budi = 250", milik_budi["tokens"] == 250, milik_budi["tokens"])
    cek("Pemakaian Sari = 1 permintaan", milik_sari["requests"] == 1, milik_sari)
    cek("Token Sari = 999 (terpisah)", milik_sari["tokens"] == 999, milik_sari["tokens"])
    cek("Total situs = 3 permintaan", global_semua["requests"] == 3, global_semua)

    ringkas = await usage.ringkasan("groq", "openai/gpt-oss-120b", sub="111122223333444455")
    cek("Panel usage memuat bagian akun", "akun" in ringkas)
    cek("Angka akun benar di panel", ringkas.get("akun", {}).get("requests", {}).get("terpakai") == 2, ringkas.get("akun", {}).get("requests"))
    cek("Nama penyedia tetap disamarkan", ringkas["provider"] == "gungdev")
    cek("Nama model tetap disamarkan", ringkas["model"] == "gungdev")
    # Jatah per akun: kapasitas situs tidak lagi dikirim ke klien.
    cek("Kapasitas situs TIDAK ikut ke klien",
        "requests" not in ringkas and "tokens" not in ringkas,
        str(list(ringkas.keys())))

    ringkas_tamu = await usage.ringkasan("groq", "openai/gpt-oss-120b")
    cek("Tamu tidak mendapat bagian akun", "akun" not in ringkas_tamu)

    print()
    print("=" * 60)
    print("BAGIAN 6 — Ketahanan (penyimpanan mati)")
    print("=" * 60)

    penyimpanan._UPSTASH_URL = ""
    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Penyimpanan mati -> tersedia=False", hasil["tersedia"] is False)
    ok = await penyimpanan.simpan_sesi("111122223333444455", sesi("s_x1", "X", "y"))
    cek("Penyimpanan mati -> simpan mengembalikan False (tidak error)", ok is False)

    # Kode produksi tetap jalan tanpa exception.
    data = await main.sessions_daftar(authorization="Bearer token-budi")
    cek("Endpoint tetap membalas tanpa error", data["tersedia"] is False)

    # Kembalikan agar tidak mengganggu
    penyimpanan._UPSTASH_URL = os.environ["UPSTASH_REDIS_REST_URL"]

    print()
    print("=" * 60)
    print("BAGIAN 7 — Data rusak tidak merusak segalanya")
    print("=" * 60)

    penyimpanan.DB = DB
    DB["gungdev:chat:idx:111122223333444455"] = {"s_rusak": 1.0, "s_baik": 2.0}
    DB["gungdev:chat:s:111122223333444455:s_rusak"] = "{bukan json}"
    DB["gungdev:chat:s:111122223333444455:s_baik"] = json.dumps(sesi("s_baik", "Sehat", "halo"))
    hasil = await penyimpanan.daftar_sesi("111122223333444455")
    cek("Sesi rusak dilewati, sesi sehat tetap terbaca", len(hasil["sessions"]) == 1 and hasil["sessions"][0]["id"] == "s_baik", len(hasil["sessions"]))

    # Field aneh dari klien disaring
    bersih = penyimpanan.bersihkan_sesi(
        {
            "id": "s_uji_aman",
            "title": "X" * 400,
            "messages": [{"role": "hacker", "content": "x"}, {"role": "user", "content": "ok"}],
            "fieldAsing": {"apa": "ini"},
        }
    )
    cek("Peran asing dibuang", len(bersih["messages"]) == 1, len(bersih["messages"]))
    cek("Field asing tidak disimpan", "fieldAsing" not in bersih)
    cek("Judul dipotong", len(bersih["title"]) <= 160, len(bersih["title"]))

    # Bug yang pernah terjadi: ID sesi pendek (mis. "s_now") ditolak oleh
    # pola yang terlalu ketat, sehingga sesi hilang tanpa peringatan.
    for sid in ("s_a", "s_1", "s_now", "s_mf3k9_a1b2c3", "s_" + "x" * 60):
        hasil_sid = penyimpanan.bersihkan_sesi({"id": sid, "title": "t", "messages": []})
        cek(f"ID sesi '{sid[:14]}…' diterima", hasil_sid is not None and hasil_sid["id"] == sid)

    # Karakter berbahaya tetap ditolak.
    for sid in ("../rahasia", "a:b", "a b", "a/b", ""):
        cek(f"ID sesi berbahaya '{sid}' ditolak", penyimpanan.bersihkan_sesi({"id": sid, "messages": []}) is None)

    # -----------------------------------------------------------------
    # TOKEN SESI (UUID v4 dari frontend)
    # -----------------------------------------------------------------
    # Token disimpan agar tautan/pengenal sesi tetap sama di semua
    # perangkat. Karena datang dari klien, bentuknya diperiksa ketat.
    token_sah = "5a3ed697-b226-4101-8116-27ebf4fcdc34"
    bersih_token = penyimpanan.bersihkan_sesi(
        {"id": "s_token", "title": "T", "messages": [], "token": token_sah}
    )
    cek("Token sesi sah ikut tersimpan", bersih_token.get("token") == token_sah, bersih_token.get("token"))

    bersih_up = penyimpanan.bersihkan_sesi(
        {"id": "s_token2", "messages": [], "token": token_sah.upper()}
    )
    cek("Token disimpan dalam huruf kecil", bersih_up.get("token") == token_sah, bersih_up.get("token"))

    for buruk in (
        "<script>alert(1)</script>",
        "bukan-uuid-sama-sekali",
        "5a3ed697-b226-4101-8116-27ebf4fcdc3",  # kurang 1 karakter
        "5a3ed697-b226-4101-8116-27ebf4fcdc345",  # lebih 1 karakter
        "5a3ed697-b226-4101-8116-27ebf4fcdcg4",  # bukan heksadesimal
        "a" * 500,
    ):
        hasil_buruk = penyimpanan.bersihkan_sesi(
            {"id": "s_token3", "messages": [], "token": buruk}
        )
        cek(
            f"Token tidak sah '{buruk[:18]}…' dibuang",
            "token" not in hasil_buruk,
            str(hasil_buruk.get("token")),
        )

    # Tanpa token sama sekali: sesi tetap sah (sesi lama belum punya token).
    tanpa_token = penyimpanan.bersihkan_sesi({"id": "s_lama", "messages": []})
    cek("Sesi lama tanpa token tetap diterima", tanpa_token is not None and "token" not in tanpa_token)

    print()
    lulus = sum(1 for _, l, _ in HASIL if l)
    print("=" * 60)
    print(f"HASIL: {lulus}/{len(HASIL)} lulus")
    print("=" * 60)
    for nama, l, info in HASIL:
        if not l:
            print(f"  GAGAL: {nama} ({info})")

    return 0 if lulus == len(HASIL) else 1


sys.exit(asyncio.run(jalankan()))
