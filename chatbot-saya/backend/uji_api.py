"""
uji_api.py — menguji endpoint riwayat pada server uji yang sedang jalan.

Menguji hal yang paling penting bagi pengguna:
  1. Tanpa token   -> ditolak
  2. Akun A simpan -> terbaca lagi (seperti buka di perangkat lain)
  3. Akun B        -> TIDAK bisa melihat riwayat A
  4. Usage terpisah per akun
  5. Hapus hanya milik sendiri
  6. Chat tanpa login tetap berjalan (kontrak lama tidak berubah)
"""
import time

import httpx

BASE = "http://127.0.0.1:8000"
HASIL = []


def cek(nama, lulus, info=""):
    HASIL.append((nama, lulus))
    tanda = "LULUS" if lulus else "GAGAL"
    print(f"{tanda}  {nama}{(' — ' + str(info)) if info else ''}")


def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def sekarang_ms():
    return int(time.time() * 1000)


def sesi(sid, judul, teks):
    return {
        "id": sid,
        "title": judul,
        "titleLocked": False,
        "messages": [
            {"id": "m1", "role": "user", "content": teks, "createdAt": 1},
            {"id": "m2", "role": "assistant", "content": "Jawaban.", "createdAt": 2},
        ],
        "createdAt": 1000,
        "updatedAt": sekarang_ms(),
        "pinned": False,
    }


with httpx.Client(base_url=BASE, timeout=20) as c:
    print("=" * 62)
    print("1. KEAMANAN IDENTITAS")
    print("=" * 62)

    r = c.get("/api/sessions")
    cek("Tanpa token ditolak (401)", r.status_code == 401, r.status_code)

    r = c.get("/api/sessions", headers=hdr("token-palsu"))
    cek("Token palsu ditolak (401)", r.status_code == 401, r.status_code)

    print()
    print("=" * 62)
    print("2. AKUN A MENYIMPAN & MEMBACA KEMBALI")
    print("=" * 62)

    r = c.post(
        "/api/sessions",
        headers=hdr("token-akun-a"),
        json={"session": sesi("s_uji_a1", "Percakapan Akun A", "Rahasia milik akun A")},
    )
    cek("Akun A bisa menyimpan", r.status_code == 200 and r.json().get("tersimpan") is True, r.text[:60])

    baca_a = c.get("/api/sessions", headers=hdr("token-akun-a")).json()
    cek("Akun A membaca riwayatnya lagi", len(baca_a["sesi"]) == 1, f"{len(baca_a['sesi'])} sesi")
    cek("Penyimpanan server aktif", baca_a["tersedia"] is True)
    cek(
        "Isi pesan utuh setelah bolak-balik",
        baca_a["sesi"][0]["messages"][0]["content"] == "Rahasia milik akun A",
    )

    print()
    print("=" * 62)
    print("3. ISOLASI ANTAR AKUN (paling penting)")
    print("=" * 62)

    baca_b = c.get("/api/sessions", headers=hdr("token-akun-b")).json()
    cek("Akun B TIDAK melihat riwayat A", len(baca_b["sesi"]) == 0, f"{len(baca_b['sesi'])} sesi")
    cek("Isi rahasia A tidak bocor ke B", "Rahasia milik akun A" not in str(baca_b))

    # Akun B menyimpan miliknya sendiri
    c.post(
        "/api/sessions",
        headers=hdr("token-akun-b"),
        json={"session": sesi("s_uji_b1", "Punya B", "Rahasia milik akun B")},
    )
    a2 = c.get("/api/sessions", headers=hdr("token-akun-a")).json()
    b2 = c.get("/api/sessions", headers=hdr("token-akun-b")).json()
    cek("A tetap 1 sesi, B 1 sesi (tidak tercampur)", len(a2["sesi"]) == 1 and len(b2["sesi"]) == 1, f"A={len(a2['sesi'])} B={len(b2['sesi'])}")
    cek("Rahasia B tidak terlihat A", "Rahasia milik akun B" not in str(a2))

    print()
    print("=" * 62)
    print("4. USAGE TERPISAH PER AKUN")
    print("=" * 62)

    for pesan in ("halo dari A", "halo lagi dari A"):
        c.post("/chat/stream", headers=hdr("token-akun-a"), json={"message": pesan})
    c.post("/chat/stream", headers=hdr("token-akun-b"), json={"message": "halo dari B"})

    ua = c.get("/usage", headers=hdr("token-akun-a")).json()
    ub = c.get("/usage", headers=hdr("token-akun-b")).json()
    ut = c.get("/usage").json()

    cek("Usage akun A = 2 permintaan", ua.get("akun", {}).get("requests", {}).get("terpakai") == 2, ua.get("akun", {}).get("requests"))
    cek("Usage akun B = 1 permintaan", ub.get("akun", {}).get("requests", {}).get("terpakai") == 1, ub.get("akun", {}).get("requests"))
    cek("Tamu tidak punya bagian akun", "akun" not in ut)
    cek("Total situs = 3 permintaan", ut["requests"]["terpakai"] >= 3, ut["requests"]["terpakai"])
    cek("Nama penyedia tetap disamarkan", ua["provider"] == "gungdev")
    cek("Nama model tetap disamarkan", ua["model"] == "gungdev")

    print()
    print("=" * 62)
    print("5. HAPUS HANYA MILIK SENDIRI")
    print("=" * 62)

    r = c.delete("/api/sessions", headers=hdr("token-akun-a"))
    cek("Hapus semua milik A berhasil", r.status_code == 200, r.text[:40])

    sa = c.get("/api/sessions", headers=hdr("token-akun-a")).json()
    sb = c.get("/api/sessions", headers=hdr("token-akun-b")).json()
    cek("Riwayat A benar-benar kosong", len(sa["sesi"]) == 0, len(sa["sesi"]))
    cek("Riwayat B TIDAK ikut terhapus", len(sb["sesi"]) == 1, len(sb["sesi"]))

    # Hapus satu sesi saja
    c.post("/api/sessions", headers=hdr("token-akun-b"), json={"session": sesi("s_uji_b2", "Kedua B", "x")})
    c.delete("/api/sessions", params={"id": "s_uji_b2"}, headers=hdr("token-akun-b"))
    sb2 = c.get("/api/sessions", headers=hdr("token-akun-b")).json()
    cek("Hapus satu sesi menyisakan yang lain", len(sb2["sesi"]) == 1, len(sb2["sesi"]))

    print()
    print("=" * 62)
    print("6. KONTRAK LAMA TIDAK BERUBAH")
    print("=" * 62)

    with c.stream("POST", "/chat/stream", json={"message": "tanpa login"}) as res:
        isi = "".join(res.iter_text())
    cek("Chat tanpa login tetap jalan (SSE)", res.status_code == 200 and "delta" in isi, isi[:50].replace("\n", " "))

    r = c.post("/chat", json={"message": "halo non-stream"})
    cek("/chat tetap membalas 200", r.status_code == 200, r.text[:50])

    r = c.get("/health")
    cek("/health tetap sama", r.json() == {"status": "ok", "provider": "gungdev", "model": "gungdev"}, r.text[:60])

    r = c.get("/capabilities")
    cek("/capabilities tetap ada", r.status_code == 200 and "models" in r.json())

print()
lulus = sum(1 for _, l in HASIL if l)
print("=" * 62)
print(f"HASIL: {lulus}/{len(HASIL)} lulus")
print("=" * 62)
for nama, l in HASIL:
    if not l:
        print(f"  GAGAL: {nama}")
raise SystemExit(0 if lulus == len(HASIL) else 1)
