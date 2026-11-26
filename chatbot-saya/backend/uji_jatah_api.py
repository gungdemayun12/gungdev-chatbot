"""
uji_jatah_api.py — uji penegakan jatah lewat HTTP sungguhan.

Uji ini memastikan penolakan benar-benar terjadi di endpoint, bukan hanya
di dalam modul:

  1. Akun dengan jatah tersisa -> /chat dan /chat/stream BERHASIL
  2. Akun yang jatahnya habis -> /chat ditolak HTTP 429 dengan pesan jelas
  3. /chat/stream ditolak SEBELUM streaming (bukan 200 kosong)
  4. Akun LAIN tetap bisa chat (isolasi jatah)
  5. /usage menampilkan jatah akun yang benar
  6. Tamu tidak terkena jatah akun
  7. Kontrak lama tidak berubah: /chat tetap {"reply": ...},
     /chat/stream tetap SSE, /health tetap {"status":"ok"}

Butuh server_uji.py berjalan di port 8000 (state bersih).

Jalankan:  python server_uji.py   (di terminal lain)
           python uji_jatah_api.py
"""

from __future__ import annotations

import json
import sys

import httpx

BASE = "http://127.0.0.1:8000"
AKUN_A = "100000000000000001"
AKUN_B = "200000000000000002"
TOKEN_A = "token-akun-a"
TOKEN_B = "token-akun-b"

HASIL = []


def cek(nama: str, lulus: bool, info: str = "") -> None:
    HASIL.append((nama, lulus))
    print(("LULUS" if lulus else "GAGAL") + f"  {nama}" + (f" — {info}" if info else ""))


def atur_pemakaian(sub: str, requests: int, tokens: int = 0) -> None:
    httpx.post(
        f"{BASE}/__uji/pakai",
        json={"sub": sub, "requests": requests, "tokens": tokens},
        timeout=10,
    )


def mundurkan_jendela(sub: str, jam: int) -> None:
    """Memundurkan awal jendela jatah akun (untuk menguji reset)."""
    httpx.post(
        f"{BASE}/__uji/jendela",
        json={"sub": sub, "mundur_detik": jam * 3600},
        timeout=10,
    )


def info_jendela(sub: str) -> dict:
    try:
        return httpx.get(f"{BASE}/__uji/jendela/{sub}", timeout=10).json()
    except Exception:  # noqa: BLE001
        return {}


def chat(pesan: str, token: str | None, stream: bool = False):
    url = f"{BASE}/chat/stream" if stream else f"{BASE}/chat"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.post(url, json={"message": pesan}, headers=headers, timeout=60)


def jalankan() -> None:
    # Pastikan server hidup.
    try:
        httpx.get(f"{BASE}/health", timeout=5)
    except Exception as exc:  # noqa: BLE001
        print(f"Server uji belum berjalan di {BASE}: {exc}")
        print("Jalankan dulu:  python server_uji.py")
        sys.exit(2)

    # ================= 1. JATAH TERSISA -> BERHASIL =================
    print("\n=== 1. JATAH TERSISA: CHAT BERHASIL ===")
    atur_pemakaian(AKUN_A, 0)
    r = chat("Halo, satu pesan", TOKEN_A)
    cek("POST /chat berhasil (200)", r.status_code == 200, str(r.status_code))
    cek("Kontrak lama tetap: ada field 'reply'", "reply" in (r.json() or {}),
        str(list((r.json() or {}).keys())))

    r = chat("Halo lewat stream", TOKEN_A, stream=True)
    cek("POST /chat/stream berhasil (200)", r.status_code == 200, str(r.status_code))
    cek("Stream tetap berformat SSE", r.text.startswith("data:"),
        r.text[:40].replace("\n", " "))
    cek("Stream diakhiri done", '"done"' in r.text)

    # ================= 2. JATAH HABIS -> DITOLAK =================
    print("\n=== 2. JATAH HABIS: /chat DITOLAK ===")
    atur_pemakaian(AKUN_A, 100)  # tepat di batas
    r = chat("Pesan saat jatah habis", TOKEN_A)
    cek("POST /chat ditolak 429", r.status_code == 429, str(r.status_code))
    detail = ""
    try:
        detail = (r.json() or {}).get("detail", "")
    except Exception:  # noqa: BLE001
        detail = r.text
    cek("Pesan penolakan jelas bagi pengguna", "jatah" in detail.lower(),
        detail[:90])
    cek("Pesan menyebut jatah pulih otomatis", "pulih" in detail.lower())
    cek("Pesan TIDAK membocorkan nama penyedia/model",
        "groq" not in detail.lower() and "gpt" not in detail.lower(),
        detail[:60])

    # Di atas batas juga ditolak (tidak ada celah).
    atur_pemakaian(AKUN_A, 150)
    cek("Di atas batas tetap ditolak",
        chat("Pesan lagi", TOKEN_A).status_code == 429)

    # ================= 3. STREAM DITOLAK SEBELUM MULAI =================
    print("\n=== 3. /chat/stream DITOLAK SEBELUM STREAMING ===")
    atur_pemakaian(AKUN_A, 100)
    r = chat("Stream saat habis", TOKEN_A, stream=True)
    cek("Stream ditolak 429 (bukan 200 kosong)", r.status_code == 429,
        str(r.status_code))
    cek("Tidak mengirim data SSE apa pun", not r.text.strip().startswith("data:"),
        r.text[:40].replace("\n", " "))

    # ================= 4. ISOLASI: AKUN LAIN TETAP BISA =================
    print("\n=== 4. AKUN LAIN TIDAK TERPENGARUH (inti permintaan) ===")
    atur_pemakaian(AKUN_B, 0)
    r = chat("Halo dari akun B", TOKEN_B)
    cek("Akun B tetap bisa chat meski A habis", r.status_code == 200,
        str(r.status_code))
    cek("Akun B dapat jawaban", bool((r.json() or {}).get("reply")))

    # ================= 5. /usage MENAMPILKAN JATAH AKUN =================
    print("\n=== 5. /usage MENAMPILKAN JATAH AKUN SENDIRI ===")
    atur_pemakaian(AKUN_A, 37, tokens=9999)
    atur_pemakaian(AKUN_B, 2, tokens=500)

    uA = httpx.get(f"{BASE}/usage", headers={"Authorization": f"Bearer {TOKEN_A}"},
                   timeout=15).json()
    uB = httpx.get(f"{BASE}/usage", headers={"Authorization": f"Bearer {TOKEN_B}"},
                   timeout=15).json()

    akunA = uA.get("akun") or {}
    akunB = uB.get("akun") or {}
    cek("Akun A terpakai 37", akunA.get("requests", {}).get("terpakai") == 37,
        str(akunA.get("requests")))
    cek("Akun A batas 100 (bukan 1000 global)",
        akunA.get("requests", {}).get("batas") == 100,
        str(akunA.get("requests", {}).get("batas")))
    cek("Akun A sisa 63", akunA.get("requests", {}).get("sisa") == 63,
        str(akunA.get("requests", {}).get("sisa")))
    cek("Akun B terpakai 2 (terpisah)", akunB.get("requests", {}).get("terpakai") == 2,
        str(akunB.get("requests")))
    cek("Token A tercatat 9999 (informasi)",
        akunA.get("tokens", {}).get("terpakai") == 9999,
        str(akunA.get("tokens")))
    cek("Token tanpa batas", akunA.get("tokens", {}).get("batas") is None)
    cek("Ada jadwal reset akun", bool(akunA.get("reset", {}).get("waktu_utc")),
        str(akunA.get("reset", {}).get("waktu_utc")))
    cek("Nama penyedia tetap disamarkan", uA.get("provider") == "gungdev")

    # ================= 6. RESET: JENDELA 24 JAM BERGULIR =================
    print("\n=== 6. RESET = JENDELA 24 JAM BERGULIR PER AKUN ===")
    atur_pemakaian(AKUN_A, 100)          # A habis
    atur_pemakaian(AKUN_B, 100)          # B juga habis
    r = chat("A saat habis", TOKEN_A)
    cek("A ditolak saat habis", r.status_code == 429, str(r.status_code))

    detail = ""
    try:
        detail = (r.json() or {}).get("detail", "")
    except Exception:  # noqa: BLE001
        detail = r.text
    cek("Pesan menyebut jendela 24 jam",
        "24 jam" in detail.lower(), detail[:110])
    cek("Pesan TIDAK lagi menyebut '07:00 WIB'",
        "07:00" not in detail, detail[:80])

    # Jendela A dilewatkan -> A boleh lagi. Jendela B TETAP berjalan.
    mundurkan_jendela(AKUN_A, 25)
    rA = chat("A setelah jendela lewat", TOKEN_A)
    cek("Setelah jendelanya lewat, A boleh lagi", rA.status_code == 200,
        str(rA.status_code))

    rB = chat("B masih di jendelanya", TOKEN_B)
    cek("Akun B TETAP ditolak (jendelanya belum lewat)", rB.status_code == 429,
        str(rB.status_code))

    # /usage akun A sudah pulih.
    uA2 = httpx.get(f"{BASE}/usage", headers={"Authorization": f"Bearer {TOKEN_A}"},
                    timeout=15).json()
    akunA2 = uA2.get("akun") or {}
    cek("Setelah reset, A terpakai 1 (bukan 100)",
        akunA2.get("requests", {}).get("terpakai") == 1,
        str(akunA2.get("requests")))
    cek("Setelah reset, A sisa 99",
        akunA2.get("requests", {}).get("sisa") == 99,
        str(akunA2.get("requests")))
    cek("Reset akun ditandai bergulir",
        akunA2.get("reset", {}).get("bergulir") is True,
        str(akunA2.get("reset")))

    # Dua akun dengan jendela berbeda -> waktu reset berbeda (bukan jam dinding).
    # Jendela B sengaja dimundurkan 5 jam agar perbedaannya nyata; tanpa
    # itu A dan B baru dibuat pada detik yang hampir sama sehingga
    # selisihnya hanya beberapa detik dan uji jadi menyesatkan.
    mundurkan_jendela(AKUN_B, 5)
    wA = info_jendela(AKUN_A)
    wB = info_jendela(AKUN_B)
    cek("Waktu reset A dan B berbeda (bukan jam dinding)",
        abs(wA.get("sisa_detik", 0) - wB.get("sisa_detik", 0)) > 3 * 3600,
        f"A={round(wA.get('sisa_detik', 0) / 3600, 1)}j "
        f"B={round(wB.get('sisa_detik', 0) / 3600, 1)}j")

    # ================= 7. TAMU =================
    print("\n=== 7. TAMU TIDAK KENA JATAH AKUN ===")
    uTamu = httpx.get(f"{BASE}/usage", timeout=15).json()
    cek("Tamu tanpa bagian akun", not uTamu.get("akun"))
    cek("Tamu diberi keterangan jatah login", bool(uTamu.get("tamu")))

    # ================= 8. KONTRAK LAMA UTUH =================
    print("\n=== 8. KONTRAK LAMA TETAP UTUH ===")
    h = httpx.get(f"{BASE}/health", timeout=10).json()
    cek("/health tetap {status:ok}", h.get("status") == "ok", str(h))
    cek("/health tanpa detail infrastruktur",
        h.get("provider") == "gungdev" and "localhost" not in json.dumps(h).lower())
    c = httpx.get(f"{BASE}/capabilities", timeout=10)
    cek("/capabilities tetap ada", c.status_code == 200, str(c.status_code))

    # Chat tanpa token (tamu) tetap berjalan seperti dulu.
    r = chat("Halo sebagai tamu", None)
    cek("Tamu bisa chat (kontrak tidak berubah)", r.status_code in (200, 429),
        str(r.status_code))

    # ================= HASIL =================
    print("\n" + "=" * 62)
    lulus = sum(1 for _, ok in HASIL if ok)
    print(f"HASIL: {lulus}/{len(HASIL)} lulus")
    print("=" * 62)
    for nama, ok in HASIL:
        if not ok:
            print(f"  GAGAL: {nama}")
    sys.exit(0 if lulus == len(HASIL) else 1)


if __name__ == "__main__":
    jalankan()
