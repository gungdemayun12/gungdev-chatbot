"""
uji_jatah.py — uji jatah (kuota) chat per akun.

Yang diuji:
  1. Akun baru mulai dengan jatah penuh (0 terpakai, 100 tersisa).
  2. Setelah chat, angka TURUN hanya untuk akun itu.
  3. Akun LAIN tidak terpengaruh (inti permintaan pengguna).
  4. Saat jatah habis, akun itu DITOLAK — akun lain tetap bisa chat.
  5. Token dihitung dari angka ASLI penyedia, bukan perkiraan.
  6. Reset harian: besok (tanggal UTC baru) jatah kembali penuh.
  7. Penyimpanan mati TIDAK memblokir chat (jangan pernah mematikan situs).

Uji ini memalsukan Redis (lewat penyimpanan) sehingga tidak memakai
kuota Upstash maupun Groq sama sekali.

Jalankan:  python uji_jatah.py
"""

from __future__ import annotations

import asyncio
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
        if op == "HINCRBY":
            kunci, field, n = str(args[1]), str(args[2]), int(args[3])
            isi = DB.setdefault(kunci, {})
            isi[field] = int(isi.get(field, 0)) + n
            return isi[field]
        if op == "EXPIRE":
            return 1
        if op == "HMGET":
            kunci = str(args[1])
            isi = DB.get(kunci, {})
            return [isi.get(str(f)) for f in args[2:]]
        if op == "GET":
            nilai = DB.get(str(args[1]))
            return None if nilai is None else str(nilai)
        if op == "DEL":
            for k in args[1:]:
                DB.pop(str(k), None)
            return 1
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


def isi_catatan(sub: str, req: int, tok: int = 0, delta: int = 0) -> None:
    """Menaruh angka pemakaian langsung di 'Redis' untuk akun tertentu."""
    kunci = f"gungdev:usage:u:{sub}:{hari(delta)}"
    DB[kunci] = {"requests": req, "tokens": tok}


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
    j = await usage.periksa_jatah(A)
    cek("Akun baru boleh chat", j["boleh"] is True)
    cek("Terpakai 0", j["terpakai"] == 0, str(j["terpakai"]))
    cek("Jatah 100 request", j["batas"] == 100, str(j["batas"]))
    cek("Sisa 100", j["sisa"] == 100, str(j["sisa"]))
    cek("Reset harian ada hitung mundurnya", 0 < j["reset_detik"] <= 86400,
        f"{j['reset_detik']} dtk")

    # ================= 2. PEMAKAIAN AKUN A =================
    print("\n=== 2. PEMAKAIAN HANYA MENGURANGI JATAH AKUN ITU ===")
    for _ in range(5):
        await usage.catat_request(tokens=500, model="m", sub=A)

    jA = await usage.periksa_jatah(A)
    jB = await usage.periksa_jatah(B)
    cek("Akun A terpakai 5", jA["terpakai"] == 5, str(jA["terpakai"]))
    cek("Akun A sisa 95", jA["sisa"] == 95, str(jA["sisa"]))
    cek("Akun B TETAP 0 (tidak terpengaruh)", jB["terpakai"] == 0, str(jB["terpakai"]))
    cek("Akun B sisa 100", jB["sisa"] == 100, str(jB["sisa"]))

    token_A = (await usage.baca_harian(A))["tokens"]
    cek("Token akun A 2.500", token_A == 2500, str(token_A))
    cek("Token akun B tetap 0", (await usage.baca_harian(B))["tokens"] == 0)

    # ================= 3. JATAH HABIS -> DITOLAK =================
    print("\n=== 3. JATAH HABIS: AKUN ITU DITOLAK, AKUN LAIN TETAP BISA ===")
    isi_catatan(A, req=100, tok=0)  # A sudah 100/100
    jA = await usage.periksa_jatah(A)
    jB = await usage.periksa_jatah(B)
    cek("Akun A DITOLAK", jA["boleh"] is False)
    cek("Alasan = request", jA["alasan"] == "request", str(jA["alasan"]))
    cek("Sisa akun A 0", jA["sisa"] == 0, str(jA["sisa"]))
    cek("Akun B TETAP BOLEH chat", jB["boleh"] is True)

    # Lewat batas sedikit pun tetap ditolak (tidak boleh jadi celah).
    isi_catatan(A, req=101, tok=0)
    cek("Akun A di 101 juga ditolak", (await usage.periksa_jatah(A))["boleh"] is False)

    # ================= 4. TOKEN BUKAN PEMBATAS =================
    print("\n=== 4. TOKEN TIDAK MEMBATASI CHAT (hanya dicatat) ===")
    bersihkan()
    isi_catatan(A, req=1, tok=999_999)
    jA = await usage.periksa_jatah(A)
    cek("Token sangat besar TIDAK menolak chat", jA["boleh"] is True)
    cek("Token tetap tercatat sebagai informasi",
        jA["token_terpakai"] == 999_999, str(jA["token_terpakai"]))
    cek("Sisa pesan tetap 99", jA["sisa"] == 99, str(jA["sisa"]))

    # ================= 5. RESET HARIAN =================
    print("\n=== 5. RESET HARIAN: BESOK JATAH KEMBALI PENUH ===")
    bersihkan()
    isi_catatan(A, req=100, tok=20_000)          # hari ini: habis
    isi_catatan(A, req=0, tok=0, delta=1)        # besok: kosong
    hari_ini = await usage.periksa_jatah(A)
    cek("Hari ini A ditolak", hari_ini["boleh"] is False)

    # Majukan "hari ini" ke tanggal besok -> harusnya penuh lagi.
    asli = usage._hari_ini
    usage._hari_ini = lambda: hari(1)            # type: ignore[assignment]
    try:
        besok = await usage.periksa_jatah(A)
    finally:
        usage._hari_ini = asli                   # type: ignore[assignment]
    cek("Besok A boleh lagi (reset)", besok["boleh"] is True)
    cek("Besok terpakai 0", besok["terpakai"] == 0, str(besok["terpakai"]))

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
    isi_catatan(A, req=100, tok=20_000)  # seolah habis
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
    cek("Batas akun 100 (BUKAN 1000 global)",
        akun.get("requests", {}).get("batas") == 100,
        str(akun.get("requests", {}).get("batas")))
    cek("Sisa akun 93", akun.get("requests", {}).get("sisa") == 93,
        str(akun.get("requests", {}).get("sisa")))
    cek("Token tercatat sebagai informasi (bukan batas)",
        akun.get("tokens", {}).get("terpakai") == 7000,
        str(akun.get("tokens")))
    cek("Token tanpa batas (None)",
        akun.get("tokens", {}).get("batas") is None,
        str(akun.get("tokens", {}).get("batas")))
    cek("Belum habis", akun.get("habis") is False)
    cek("Ada jadwal reset akun", bool(akun.get("reset", {}).get("waktu_utc")))
    cek("Nama penyedia tetap disamarkan", r.get("provider") == "gungdev")
    cek("Nama model tetap disamarkan", r.get("model") == "gungdev")

    # Tamu: tidak ada bagian akun, ada penjelasan jatah tamu.
    rTamu = await usage.ringkasan("groq", "openai/gpt-oss-120b")
    cek("Tamu tanpa bagian akun", not rTamu.get("akun"))
    cek("Tamu diberi tahu jatah login", bool(rTamu.get("tamu")))

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
