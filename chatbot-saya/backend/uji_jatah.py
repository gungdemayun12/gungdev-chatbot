"""
uji_jatah.py — uji jatah (kuota) chat per akun.

Yang diuji:
  1. Akun baru mulai dengan jatah penuh (0 terpakai, 40 tersisa).
  2. Setelah chat, angka TURUN hanya untuk akun itu.
  3. Akun LAIN tidak terpengaruh (inti permintaan pengguna).
  4. Saat jatah habis, akun itu DITOLAK — akun lain tetap bisa chat.
  5. Token dihitung dari angka ASLI penyedia, bukan perkiraan.
  6. Reset: jendela 24 jam bergulir milik tiap akun.
  7. Penyimpanan mati TIDAK memblokir chat (jangan pernah mematikan situs).
  8. Jatah otomatis dipangkas saat kuota bersama menipis.
  9. /usage hanya menampilkan jatah akun — rincian kuota penyedia tidak
     pernah dikirim ke klien.

Uji ini memalsukan Redis (lewat penyimpanan) sehingga tidak memakai
kuota Upstash maupun penyedia AI sama sekali.

Jalankan:  python uji_jatah.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import usage

HASIL = []


def cek(nama: str, lulus: bool, info: str = "") -> None:
    HASIL.append((nama, lulus))
    tanda = "LULUS" if lulus else "GAGAL"
    print(f"{tanda}  {nama}" + (f" — {info}" if info else ""))


# ---------------------------------------------------------------------
# Penyimpanan palsu: cukup meniru yang dipakai usage.py
# ---------------------------------------------------------------------
DB: dict = {}


class RedisPalsu:
    """Meniru Upstash REST untuk perintah yang dipakai usage.py."""

    def __init__(self) -> None:
        self.tersedia = True

    async def perintah(self, *args):
        if not self.tersedia:
            return None
        op = str(args[0]).upper()
        if op == "SET":
            kunci = str(args[1])
            nilai = args[2]
            DB[kunci] = str(nilai)
            return "OK"
        if op == "HINCRBY":
            kunci, field, n = str(args[1]), str(args[2]), int(args[3])
            isi = DB.setdefault(kunci, {})
            if not isinstance(isi, dict):
                isi = {}
                DB[kunci] = isi
            isi[field] = int(isi.get(field, 0)) + n
            return isi[field]
        if op == "EXPIRE":
            return 1
        if op == "HMGET":
            kunci = str(args[1])
            isi = DB.get(kunci, {})
            if not isinstance(isi, dict):
                isi = {}
            return [isi.get(str(f)) for f in args[2:]]
        if op == "GET":
            nilai = DB.get(str(args[1]))
            return None if nilai is None else str(nilai)
        if op == "DEL":
            for k in args[1:]:
                DB.pop(str(k), None)
            return 1
        if op == "SADD":
            kunci = str(args[1])
            isi = DB.setdefault(kunci, set())
            if not isinstance(isi, set):
                isi = set()
                DB[kunci] = isi
            sebelum = len(isi)
            for anggota in args[2:]:
                isi.add(str(anggota))
            return len(isi) - sebelum
        if op == "SCARD":
            isi = DB.get(str(args[1]), set())
            return len(isi) if isinstance(isi, set) else 0
        if op == "SISMEMBER":
            isi = DB.get(str(args[1]), set())
            return 1 if isinstance(isi, set) and str(args[2]) in isi else 0
        return None


palsu = RedisPalsu()


async def perintah_palsu(*args, **kwargs):
    return await palsu.perintah(*args)


# Pasang palsu ke usage.py
usage._redis_perintah = perintah_palsu  # type: ignore[assignment]
usage._UPSTASH_URL = "http://palsu"  # agar dianggap tersedia
usage._UPSTASH_TOKEN = "token-palsu"
usage._memori.clear()


def hari(delta: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=delta)).strftime("%Y-%m-%d")


def isi_catatan(
    sub: str, req: int, tok: int = 0, delta: int = 0, mulai: float | None = None
) -> str:
    """
    Menaruh angka pemakaian langsung di 'Redis' untuk akun tertentu.

    Sejak jatah memakai JENDELA 24 JAM BERGULIR, kuncinya bukan tanggal
    lagi melainkan penanda jendela. Nilai jendela dibaca dari DB (Redis
    tiruan) — BUKAN dari usage._memori — supaya uji mengikuti sumber
    kebenaran yang sama dengan produksi.
    """
    if mulai is None:
        nilai = DB.get(f"gungdev:usage:jendela:{sub}")
        if nilai is not None:
            mulai = float(nilai)
        else:
            mulai = datetime.now(timezone.utc).timestamp()
            DB[f"gungdev:usage:jendela:{sub}"] = str(int(mulai))
    kunci = f"gungdev:usage:u:{sub}:w{int(mulai)}"
    DB[kunci] = {"requests": req, "tokens": tok}
    return kunci


def mulai_jendela(sub: str, mundur_detik: int = 0) -> float:
    """
    Menetapkan (dan memundurkan) awal jendela jatah sebuah akun.

    Salinan di `usage._memori` juga dibersihkan/diperbarui, karena modul
    menyimpan cadangan di sana. Bila tidak disamakan, uji bisa membaca
    jendela lama dan menyimpulkan hal yang salah.
    """
    mulai = datetime.now(timezone.utc).timestamp() - mundur_detik
    DB[f"gungdev:usage:jendela:{sub}"] = str(int(mulai))
    usage._memori[f"gungdev:usage:jendela:{sub}"] = mulai
    return mulai


def bersihkan() -> None:
    DB.clear()
    usage._memori.clear()
    usage._token_terakhir.clear()
    palsu.tersedia = True


# ---------------------------------------------------------------------
async def jalankan() -> None:
    A = "100000000000000001"
    B = "200000000000000002"

    # ================= 1. JATAH AWAL =================
    print("\n=== 1. AKUN BARU MULAI DENGAN JATAH PENUH ===")
    bersihkan()
    JATAH = usage.JATAH_AKUN_DASAR
    j = await usage.periksa_jatah(A)
    cek("Akun baru boleh chat", j["boleh"] is True)
    cek("Terpakai 0", j["terpakai"] == 0, str(j["terpakai"]))
    cek(f"Jatah {JATAH} request", j["batas"] == JATAH, str(j["batas"]))
    cek(f"Sisa {JATAH}", j["sisa"] == JATAH, str(j["sisa"]))
    cek("Reset harian ada hitung mundurnya", 0 < j["reset_detik"] <= 86400,
        f"{j['reset_detik']} dtk")

    # ================= 2. PEMAKAIAN AKUN A =================
    print("\n=== 2. PEMAKAIAN HANYA MENGURANGI JATAH AKUN ITU ===")
    for _ in range(5):
        await usage.catat_request(tokens=500, model="m", sub=A)

    jA = await usage.periksa_jatah(A)
    jB = await usage.periksa_jatah(B)
    cek("Akun A terpakai 5", jA["terpakai"] == 5, str(jA["terpakai"]))
    cek("Akun A sisa 11", jA["sisa"] == JATAH - 5, str(jA["sisa"]))
    cek("Akun B TETAP 0 (tidak terpengaruh)", jB["terpakai"] == 0, str(jB["terpakai"]))
    cek(f"Akun B sisa {JATAH}", jB["sisa"] == JATAH, str(jB["sisa"]))

    token_A = (await usage.baca_harian(A))["tokens"]
    cek("Token akun A 2.500", token_A == 2500, str(token_A))
    cek("Token akun B tetap 0", (await usage.baca_harian(B))["tokens"] == 0)

    # ================= 3. JATAH HABIS -> DITOLAK =================
    print("\n=== 3. JATAH HABIS: AKUN ITU DITOLAK, AKUN LAIN TETAP BISA ===")
    isi_catatan(A, req=JATAH, tok=0)  # A sudah pas di batas
    jA = await usage.periksa_jatah(A)
    jB = await usage.periksa_jatah(B)
    cek("Akun A DITOLAK", jA["boleh"] is False)
    cek("Alasan = request", jA["alasan"] == "request", str(jA["alasan"]))
    cek("Sisa akun A 0", jA["sisa"] == 0, str(jA["sisa"]))
    cek("Akun B TETAP BOLEH chat", jB["boleh"] is True)

    # Lewat batas sedikit pun tetap ditolak (tidak boleh jadi celah).
    isi_catatan(A, req=JATAH + 1, tok=0)
    cek("Akun A di atas batas juga ditolak",
        (await usage.periksa_jatah(A))["boleh"] is False)

    # ================= 4. TOKEN BUKAN PEMBATAS =================
    print("\n=== 4. TOKEN TIDAK MEMBATASI CHAT (hanya dicatat) ===")
    bersihkan()
    isi_catatan(A, req=1, tok=999_999)
    jA = await usage.periksa_jatah(A)
    cek("Token sangat besar TIDAK menolak chat", jA["boleh"] is True)
    cek("Token tetap tercatat sebagai informasi",
        jA["token_terpakai"] == 999_999, str(jA["token_terpakai"]))
    cek(f"Sisa pesan tetap {JATAH - 1}", jA["sisa"] == JATAH - 1, str(jA["sisa"]))

    # ================= 5. RESET: JENDELA 24 JAM BERGULIR =================
    print("\n=== 5. RESET = JENDELA 24 JAM BERGULIR MILIK AKUN ITU ===")
    bersihkan()
    mulai_jendela(A, mundur_detik=0)
    isi_catatan(A, req=JATAH, tok=20_000)        # A sudah habis di jendela ini
    sekarang = await usage.periksa_jatah(A)
    cek("A ditolak dalam jendela berjalan", sekarang["boleh"] is False)
    cek("Hitung mundur mendekati 24 jam",
        86000 < sekarang["reset_detik"] <= 86400,
        f"{sekarang['reset_detik']} dtk")

    # BUKTI BERGULIR: akun B baru mulai -> jendelanya sendiri, penuh,
    # dan reset-nya ~24 jam lagi (berbeda dari A yang sudah berjalan).
    jB = await usage.periksa_jatah(B)
    cek("Akun B tetap penuh walau A habis",
        jB["boleh"] is True and jB["sisa"] == JATAH)

    # Jendela A dipundurkan 25 jam -> sudah lewat -> jatah harus pulih.
    # Catatan: pemakaian lama tercatat pada kunci jendela LAMA. Setelah
    # jendela lewat, akun memakai kunci jendela BARU yang masih kosong.
    mulai_jendela(A, mundur_detik=25 * 3600)
    pulih = await usage.periksa_jatah(A)
    cek("Setelah jendela lewat, A boleh lagi (reset)", pulih["boleh"] is True)
    cek("Setelah reset terpakai kembali 0", pulih["terpakai"] == 0,
        str(pulih["terpakai"]))
    cek(f"Setelah reset sisa penuh {JATAH}", pulih["sisa"] == JATAH,
        str(pulih["sisa"]))
    cek("Hitung mundur kembali ~24 jam",
        86000 < pulih["reset_detik"] <= 86400, f"{pulih['reset_detik']} dtk")

    # BUKTI BUKAN JAM DINDING: jendela yang dimulai 20 jam lalu punya
    # sisa ~4 jam, bukan menunggu 07:00 WIB.
    bersihkan()
    mulai_jendela(A, mundur_detik=20 * 3600)
    isi_catatan(A, req=5)
    j20 = await usage.periksa_jatah(A)
    cek("Jendela mulai 20 jam lalu -> sisa ~4 jam",
        3.5 * 3600 < j20["reset_detik"] < 4.5 * 3600,
        f"{round(j20['reset_detik'] / 3600, 1)} jam")
    cek("Pemakaian 5 tetap terbaca", j20["terpakai"] == 5, str(j20["terpakai"]))

    # Akun yang TIDAK menghabiskan jatah tidak pernah ditolak.
    cek("Akun hemat (5 pesan) tetap boleh chat", j20["boleh"] is True)

    # Dua akun dengan jendela berbeda punya waktu reset berbeda.
    bersihkan()
    mulai_jendela(A, mundur_detik=20 * 3600)
    mulai_jendela(B, mundur_detik=2 * 3600)
    rA = await usage.periksa_jatah(A)
    rB = await usage.periksa_jatah(B)
    cek("Reset akun A dan B BERBEDA (bukan jam dinding)",
        abs(rA["reset_detik"] - rB["reset_detik"]) > 3600,
        f"A={round(rA['reset_detik']/3600,1)}j B={round(rB['reset_detik']/3600,1)}j")

    # ================= 6. TOKEN ASLI PENYEDIA =================
    print("\n=== 6. TOKEN DIPAKAI DARI ANGKA ASLI PENYEDIA ===")
    bersihkan()
    cek("Belum ada angka -> None", usage.ambil_token_asli() is None)

    usage.simpan_token_asli(1234, prompt=1000, completion=234)
    cek("Angka asli tersimpan", usage.ambil_token_asli() == 1234,
        str(usage.ambil_token_asli()))

    # Angka lama harus diabaikan agar tidak terpakai permintaan lain.
    usage._token_terakhir["waktu"] -= 10_000
    cek("Angka basi diabaikan", usage.ambil_token_asli() is None)

    # Tanpa total tapi ada prompt+completion: tetap dijumlahkan.
    usage.simpan_token_asli(0, prompt=300, completion=200)
    cek("Dijumlahkan bila total kosong", usage.ambil_token_asli() == 500,
        str(usage.ambil_token_asli()))

    # ================= 7. PENYIMPANAN MATI TIDAK MEMBLOKIR =================
    print("\n=== 7. PENYIMPANAN MATI TIDAK BOLEH MEMBLOKIR CHAT ===")
    bersihkan()
    isi_catatan(A, req=JATAH, tok=20_000)  # seolah habis
    palsu.tersedia = False               # Redis mati
    jA = await usage.periksa_jatah(A)
    cek("Redis mati -> chat TETAP BOLEH (lebih baik longgar daripada mati)",
        jA["boleh"] is True)

    usage._UPSTASH_URL = ""              # tidak dikonfigurasi sama sekali
    cek("Tanpa Upstash -> tetap boleh", (await usage.periksa_jatah(A))["boleh"] is True)
    usage._UPSTASH_URL = "http://palsu"
    palsu.tersedia = True

    # ================= 8. TAMU =================
    print("\n=== 8. TAMU TIDAK PUNYA JATAH AKUN ===")
    bersihkan()
    jTamu = await usage.periksa_jatah(None)
    cek("Tamu boleh (batas per-IP di main.py)", jTamu["boleh"] is True)
    cek("Batas tamu 3", jTamu["batas"] == 3, str(jTamu["batas"]))
    cek("Tamu tanpa sub", jTamu["sub"] is None)

    # ================= 9. RINGKASAN /usage =================
    print("\n=== 9. PANEL /usage MENAMPILKAN JATAH AKUN ===")
    bersihkan()
    for _ in range(7):
        await usage.catat_request(tokens=1000, model="m", sub=A)
    r = await usage.ringkasan("groq", "openai/gpt-oss-120b", sub=A)
    akun = r.get("akun") or {}
    cek("Bagian akun ada", bool(akun))
    cek("Terpakai 7", akun.get("requests", {}).get("terpakai") == 7,
        str(akun.get("requests")))
    cek(f"Batas akun {JATAH} (jatah akun, bukan kuota situs)",
        akun.get("requests", {}).get("batas") == JATAH,
        str(akun.get("requests", {}).get("batas")))
    cek(f"Sisa akun {JATAH - 7}",
        akun.get("requests", {}).get("sisa") == JATAH - 7,
        str(akun.get("requests", {}).get("sisa")))
    cek("Token tercatat sebagai informasi (bukan batas)",
        akun.get("tokens", {}).get("terpakai") == 7000,
        str(akun.get("tokens")))
    cek("Token tanpa batas (None)",
        akun.get("tokens", {}).get("batas") is None,
        str(akun.get("tokens", {}).get("batas")))
    cek("Belum habis", akun.get("habis") is False)
    cek("Ada jadwal reset akun", bool(akun.get("reset", {}).get("waktu_utc")))
    # `pada` = waktu absolut (epoch detik). Frontend memakainya untuk
    # menghitung mundur sendiri tiap detik -> panel terasa real time
    # tanpa perlu bertanya ulang ke server.
    pada = (akun.get("reset") or {}).get("pada")
    cek("Reset menyertakan waktu absolut 'pada' (untuk hitung mundur lokal)",
        isinstance(pada, int) and pada > 0, str(pada))
    sekarang_epoch = int(datetime.now(timezone.utc).timestamp())
    cek("'pada' berada dalam jendela 24 jam ke depan",
        isinstance(pada, int) and 0 < pada - sekarang_epoch <= 86400,
        f"{(pada or 0) - sekarang_epoch} dtk")
    cek("Nama penyedia tetap disamarkan", r.get("provider") == "gungdev")
    cek("Nama model tetap disamarkan", r.get("model") == "gungdev")

    # ---------------------------------------------------------------
    # RAHASIA: /usage TIDAK boleh membuka kapasitas layanan.
    # ---------------------------------------------------------------
    print("\n=== 9b. /usage HANYA MENAMPILKAN JATAH AKUN (TANPA KAPASITAS SITUS) ===")
    teks = json.dumps(r)
    for kunci_terlarang in ("requests", "tokens", "per_menit", "sumber"):
        # `requests`/`tokens` boleh muncul DI DALAM "akun"; yang dilarang
        # adalah versi tingkat-atas (kapasitas situs).
        cek(f"Tidak ada '{kunci_terlarang}' tingkat situs di respons",
            kunci_terlarang not in r, str(list(r.keys())))
    cek("Tidak membocorkan angka kuota penyedia (1.000 / 200.000)",
        "1000" not in teks.replace(" ", "").replace("1.000", "1000")
        and "200000" not in teks.replace(" ", ""),
        teks[:120])
    cek("Tidak menyebut nama penyedia/model",
        not any(x in teks.lower() for x in ("groq", "openrouter", "gpt-oss")),
        teks[:120])
    cek("Ada indikator layanan (kata, bukan angka kuota)",
        (r.get("layanan") or {}).get("status") in ("lancar", "ramai", "dikurangi"),
        str(r.get("layanan")))

    # Tamu: tidak ada bagian akun, ada penjelasan jatah tamu.
    rTamu = await usage.ringkasan("groq", "openai/gpt-oss-120b")
    cek("Tamu tanpa bagian akun", not rTamu.get("akun"))
    cek("Tamu diberi tahu jatah login", bool(rTamu.get("tamu")))
    cek("Jatah akun untuk tamu disebut angka yang benar",
        (rTamu.get("tamu") or {}).get("jatah_akun") == JATAH,
        str((rTamu.get("tamu") or {}).get("jatah_akun")))

    # ================= 10. JATAH DIPANGKAS SAAT KUOTA TIPIS =================
    print("\n=== 10. JATAH OTOMATIS DIPANGKAS SAAT KUOTA BERSAMA MENIPIS ===")
    bersihkan()
    cek(f"Kuota lega -> jatah penuh {JATAH}",
        (await usage.jatah_berjalan()) == JATAH,
        str(await usage.jatah_berjalan()))
    cek("Kapasitas harian = 3 Groq + OpenRouter + Gemini (3.250 request)",
        usage.KAPASITAS_HARIAN["request"] == 3250,
        str(usage.KAPASITAS_HARIAN["request"]))
    cek("Kapasitas token harian = 850.000 (600rb Groq + 250rb Gemini)",
        usage.KAPASITAS_HARIAN["token"] == 850_000,
        str(usage.KAPASITAS_HARIAN["token"]))
    cek("Kapasitas 566 pesan/hari (kendala token)",
        usage.PESAN_PER_HARI == 566, str(usage.PESAN_PER_HARI))
    cek("Jatah 40 x 10 akun aktif = 400 -> masih di bawah kapasitas",
        JATAH * 10 <= usage.PESAN_PER_HARI, f"{JATAH} x 10")

    # Situs sudah memakai hampir seluruh kapasitas token harian.
    kunci_global = usage._kunci_harian()
    hampir_habis = usage.KAPASITAS_HARIAN["token"] - (
        usage.KUOTA_BERSAMA["token_per_pesan"] * 3
    )
    DB[kunci_global] = {"requests": 100, "tokens": hampir_habis}
    cek("Sisa pesan situs terbaca sedikit",
        (await usage.sisa_pesan_situs()) <= usage.PESAN_PER_HARI * 0.15,
        str(await usage.sisa_pesan_situs()))
    jatah_baru = await usage.jatah_berjalan()
    cek(f"Kuota tipis -> jatah turun ke {usage.JATAH_SAAT_KUOTA_TIPIS}",
        jatah_baru == usage.JATAH_SAAT_KUOTA_TIPIS, str(jatah_baru))

    jA = await usage.periksa_jatah(A)
    cek("Pemeriksaan jatah memakai angka yang sudah dipangkas",
        jA["batas"] == usage.JATAH_SAAT_KUOTA_TIPIS, str(jA["batas"]))

    r = await usage.ringkasan("groq", "openai/gpt-oss-120b", sub=A)
    akun = r.get("akun") or {}
    cek("Panel menandai jatah sedang dikurangi",
        (akun.get("requests") or {}).get("dikurangi") is True,
        str(akun.get("requests")))
    cek("Status layanan menjadi 'dikurangi'",
        (r.get("layanan") or {}).get("status") == "dikurangi",
        str(r.get("layanan")))
    cek("Panel tetap menyebut jatah penuh sebagai pembanding",
        (akun.get("requests") or {}).get("jatah_penuh") == JATAH,
        str((akun.get("requests") or {}).get("jatah_penuh")))

    # Request yang menipis juga memangkas jatah.
    DB[kunci_global] = {"requests": usage.KAPASITAS_HARIAN["request"] - 10,
                        "tokens": 0}
    cek("Kuota request menipis -> jatah juga dipangkas",
        (await usage.jatah_berjalan()) == usage.JATAH_SAAT_KUOTA_TIPIS,
        str(await usage.jatah_berjalan()))

    # ================= 11. BATAS AKUN BARU PER HARI =================
    print("\n=== 11. JUMLAH AKUN BARU PER HARI DIBATASI ===")
    bersihkan()
    d1 = await usage.daftarkan_akun("300000000000000003")
    cek("Akun baru pertama diterima", d1["baru"] is True and d1["diterima"] is True,
        str(d1))
    d2 = await usage.daftarkan_akun("300000000000000003")
    cek("Akun yang sama tidak dihitung dua kali",
        d2["baru"] is False and d2["akun_hari_ini"] == 1, str(d2))

    # Penuhi kuota akun baru, lalu akun berikutnya ditolak.
    for i in range(usage.MAX_AKUN_BARU_PER_HARI - 1):
        await usage.daftarkan_akun(f"4000000000000{i:05d}")
    dPenuh = await usage.daftarkan_akun("500000000000000005")
    cek("Akun baru melebihi batas DITOLAK", dPenuh["diterima"] is False, str(dPenuh))

    # Akun LAMA tetap boleh walau kuota akun baru habis.
    dLama = await usage.daftarkan_akun("300000000000000003")
    cek("Akun lama TETAP diterima walau kuota akun baru habis",
        dLama["diterima"] is True, str(dLama))

    # Penyimpanan mati -> semua diterima (jangan memblokir pengguna sah).
    palsu.tersedia = False
    dMati = await usage.daftarkan_akun("600000000000000006")
    cek("Penyimpanan mati -> akun tetap diterima", dMati["diterima"] is True,
        str(dMati))
    palsu.tersedia = True

    # ================= HASIL =================
    print("\n" + "=" * 62)
    lulus = sum(1 for _, ok in HASIL if ok)
    print(f"HASIL: {lulus}/{len(HASIL)} lulus")
    print("=" * 62)
    for nama, ok in HASIL:
        if not ok:
            print(f"  GAGAL: {nama}")


if __name__ == "__main__":
    asyncio.run(jalankan())
    raise SystemExit(0 if all(ok for _, ok in HASIL) else 1)
