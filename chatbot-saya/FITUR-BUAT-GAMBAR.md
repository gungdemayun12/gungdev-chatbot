# Fitur "Buat Gambar" — Panduan Lengkap

Dokumen ini menjelaskan cara kerja fitur pembuatan gambar di GungDev:
apa yang terjadi saat pengguna meminta gambar, mengapa jatahnya
terpisah dari jatah chat, dan cara mengaturnya.

---

## 1. Ringkasan singkat

Pengguna **tidak perlu memilih model** dan **tidak perlu menekan tombol
apa pun**. Ia cukup menulis permintaannya:

> "buatkan gambar kucing oranye sedang tidur di sofa"

Lalu gambarnya muncul di percakapan, bisa diklik untuk diperbesar dan
diunduh.

Ini pola yang sama dengan **riset web otomatis**: server yang menentukan
kapan fitur dipakai, bukan pengguna.

Yang **tidak** berubah:

- Model chat tetap sama (`gpt-oss-20b` dan lainnya) untuk obrolan biasa.
- Kontrak `/chat` dan `/chat/stream` tetap sama. `gambar` hanyalah
  field **tambahan** yang hanya muncul bila gambar memang dibuat.
- Jatah chat (52 pesan/24 jam) tidak tersentuh oleh gambar.

---

## 2. Apakah perlu mengambil API key?

**Tidak.** Fitur ini sengaja memakai layanan gambar yang benar-benar
gratis:

| Hal | Nilai |
|---|---|
| API key | **Tidak perlu** |
| Kartu kredit | **Tidak perlu** |
| Pendaftaran | **Tidak perlu** |
| Biaya | **Nol** |

### Yang harus Anda tahu (jujur)

Karena gratis dan tanpa pendaftaran, tidak ada jaminan layanan:

- Kadang **lambat** (antre).
- Kadang **gagal sesaat** saat sedang ramai (server menjawab 402/503).
- **Kualitas** di bawah layanan berbayar. Teks di dalam gambar sering
  kurang rapi.
- Kebijakan layanan bisa berubah sewaktu-waktu.

Karena itu ada tiga pengaman di kode:

1. **Percobaan ulang otomatis** (3 kali, dengan jeda makin panjang).
   Satu kegagalan sesaat tidak langsung membuat pengguna kehilangan
   kesempatan.
2. **Kegagalan tidak memakan jatah.** Percobaan yang gagal bukan salah
   pengguna, jadi jatahnya tidak berkurang.
3. **Kegagalan tidak menggagalkan chat.** Bila gambar gagal, pengguna
   mendapat penjelasan yang tenang — bukan halaman error.

---

## 3. Mengapa jatah gambar DIPISAH dari jatah chat

Ini permintaan langsung pemilik situs: *"jatah gambar dipisah dengan
jatah chat harian agar tidak boros di gambar saja"*.

| Jatah | Batas bawaan | Kunci penyimpanan |
|---|---|---|
| Chat (akun) | 52 pesan / 24 jam | `gungdev:usage:u:<sub>:<jendela>` |
| **Gambar (akun)** | **3 gambar / 24 jam** | `gungdev:usage:gambar:<sub>:<jendela>` |
| Gambar (tamu) | 0 | — |

Karena kuncinya **berbeda**, keduanya tidak mungkin saling
memengaruhi. Yang terjadi:

- Membuat 3 gambar **tidak** mengurangi 52 pesan chat.
- Jatah gambar habis **tidak** menghalangi obrolan.
- Chat sebanyak apa pun **tidak** menambah jatah gambar.

Dibuktikan oleh `uji_gambar.py` (bagian 4) dan `uji_gambar_browser.mjs`
(bagian 2): jatah chat tetap `0 -> 0` sementara jatah gambar `0 -> 1`.

### Mengapa tamu tidak mendapat gambar

Untuk mencegah penyalahgunaan layanan gratis oleh pengunjung anonim.
Tamu tetap bisa mengobrol seperti biasa; ia hanya diberi tahu bahwa
membuat gambar perlu login.

Bila suatu saat Anda ingin tamu mendapat 1 gambar, cukup set
environment variable `JATAH_GAMBAR_TAMU=1`. Tidak perlu mengubah kode.

---

## 4. Bagaimana server mengenali permintaan gambar

Ini bagian yang paling rawan. Bila salah kira, jatah gambar pengguna
terbuang hanya karena ia **bertanya**.

Aturannya sengaja **konservatif**: lebih baik melewatkan satu permintaan
gambar daripada membuat gambar padahal pengguna hanya bertanya.

**Dikenali sebagai permintaan gambar:**

- "buatkan gambar kucing oranye…"
- "gambarkan pemandangan pantai…"
- "tolong buat ilustrasi logo…"
- "bikin gambar poster konser"
- "edit gambar ini jadi gaya anime" (ada lampiran gambar)

**TIDAK dikenali (hanya bertanya):**

- "apa itu gambar vektor?"
- "jelaskan cara membuat gambar dengan AI"
- "berapa harga gambar digital?"
- "gambaran umum ekonomi Indonesia" ← "gambaran", bukan "gambar"

### Jebakan yang sudah diperbaiki

Pencocokan frasa sempat memakai **substring biasa**. Akibatnya
"membuat gambar" cocok dengan "buat gambar", sehingga kalimat
*"jelaskan cara membuat gambar dengan AI"* **salah dikira** perintah
menggambar dan memakan jatah gambar.

Perbaikannya: semua pencocokan memakai **batas kata**
(`(?<![\w-])…(?![\w-])`). Diuji oleh `uji_gambar.py` bagian 2.

---

## 5. Bagaimana gambar sampai ke layar

```
Pengguna mengetik "buatkan gambar kucing"
        │
        ▼
Frontend  POST /chat/stream  (kontrak lama, tidak berubah)
        │
        ▼
Backend   siapkan_gambar()
        ├── gambar.niat_gambar()      → perlu gambar? tidak → chat biasa
        ├── usage.periksa_jatah_gambar()  → habis? → pesan tenang, chat tetap jalan
        ├── gambar.buat_gambar()      → ambil dari layanan gratis
        ├── gambar._pangkas_bawah()   → buang tanda air layanan
        └── usage.catat_gambar()      → catat HANYA bila berhasil
        │
        ▼
SSE   data: {"meta": {"gambar": {...}}}    ← gambar utuh (tidak bisa streaming)
      data: {"delta": "Ini gambar yang Anda minta..."}
      data: {"done": true}
        │
        ▼
Frontend  Message.jsx → GambarHasil.jsx
```

### Mengapa gambar dikirim sebagai data URL

Kalau UI hanya menyimpan **tautan**, gambar bisa hilang saat halaman
dimuat ulang (layanan gratis tidak menyimpan gambar selamanya). Data
URL membuat gambar ikut tersimpan bersama riwayat, jadi tetap terlihat
kapan pun.

Konsekuensinya: gambar ikut dikirim ke penyimpanan riwayat. Karena itu
ada batas ukuran (lihat bagian 7).

---

## 6. Tanda air layanan gambar dibuang

Layanan gambar gratis yang dipakai **selalu** menempelkan tanda air
("pollinations.ai") di pojok kanan bawah. Parameter `nologo=true` yang
dulu menghilangkannya **sudah tidak berpengaruh**.

Karena aplikasi ini tidak boleh menampilkan nama penyedia apa pun,
strip bawah gambar dipotong **6%** (`PANGKAS_BAWAH`). Bagian bawah
gambar biasanya lantai/latar, bukan objek utama, jadi komposisinya
tidak rusak.

Bila pemangkasan gagal (Pillow tidak terpasang, format tak dikenal),
**gambar asli dipakai apa adanya** — tanda air lebih baik daripada
gambar rusak atau hilang. Diuji oleh `uji_gambar.py` bagian 5.

---

## 7. Batas ukuran gambar di riwayat

| Batas | Nilai | Alasan |
|---|---|---|
| Satu gambar | 400 KB (base64) | Cukup untuk gambar 1024×1024 |
| Satu sesi | 900 KB (`MAKS_PESAN_SESI`) | Batas lama, tidak diubah |

Gambar yang lebih besar dari 400 KB **dibuang diam-diam** dari riwayat
server. Ini disengaja: lebih baik kehilangan satu gambar daripada
**gagal menyimpan seluruh riwayat** percakapan itu.

Gambar tetap terlihat selama sesi berjalan; yang hilang hanya
salinannya di server setelah halaman dimuat ulang.

---

## 8. Pengaturan lewat environment variable

Semua opsional. Tanpa diisi, semuanya memakai nilai bawaan yang wajar.

| Variabel | Bawaan | Arti |
|---|---|---|
| `JATAH_GAMBAR_PER_AKUN` | `3` | Gambar per akun per 24 jam |
| `JATAH_GAMBAR_TAMU` | `0` | Gambar untuk tamu (0 = perlu login) |
| `GAMBAR_UKURAN` | `1024` | Ukuran gambar (piksel, persegi) |
| `GAMBAR_TIMEOUT` | `75` | Batas waktu permintaan (detik) |
| `GAMBAR_PERCOBAAN` | `3` | Berapa kali dicoba bila gagal |
| `GAMBAR_JEDA` | `1.5` | Jeda antar percobaan (detik) |
| `GAMBAR_PANGKAS_BAWAH` | `0.06` | Porsi bawah yang dipotong (0 = jangan) |
| `GAMBAR_MODEL` | `flux` | Model gambar layanan |
| `GAMBAR_BASE_URL` | *(layanan bawaan)* | Ganti penyedia tanpa ubah kode |
| `GAMBAR_MAKS_BYTE` | `6000000` | Batas ukuran berkas gambar diterima |

Untuk pindah penyedia gambar nanti, cukup ubah `GAMBAR_BASE_URL` —
logika niat, jatah, dan tampilan tidak perlu disentuh.

---

## 9. Kalau ingin pindah ke layanan berbayar nanti

Yang perlu diubah **hanya** `gambar.buat_gambar()`:

1. Tambahkan API key lewat environment variable.
2. Ganti cara memanggil layanan di dalam `buat_gambar()`.
3. Kalau layanan baru tidak menempelkan tanda air, set
   `GAMBAR_PANGKAS_BAWAH=0`.

Niat, jatah, penyimpanan, dan tampilan **tidak perlu diubah**.

---

## 10. Menjalankan uji

```bash
cd chatbot-saya/backend
python uji_gambar.py          # 79 pemeriksaan (backend, tanpa jaringan)
```

```bash
cd chatbot-saya/frontend
node uji_gambar_browser.mjs   # 15 pemeriksaan (browser + UI)
```

`uji_gambar_browser.mjs` memakai gambar tiruan dari `server_uji.py`,
jadi **tidak butuh internet** dan tidak memanggil layanan sungguhan.

Uji backend memakai akun khusus (`...009`) agar tidak mengotori akun
uji lain. Bila menjalankan `uji_api.py`, reset akun dulu:

```bash
curl -X POST http://127.0.0.1:8000/__uji/reset \
  -H "Content-Type: application/json" -d "{\"sub\":\"100000000000000001\"}"
```

---

## 11. Daftar berkas yang terlibat

| Berkas | Perannya |
|---|---|
| `backend/gambar.py` | Deteksi niat, deskripsi, ambil gambar, pangkas tanda air |
| `backend/usage.py` | Jatah gambar (terpisah dari jatah chat) |
| `backend/main.py` | `siapkan_gambar()`, sambungan ke `/chat` & `/chat/stream` |
| `backend/penyimpanan.py` | Menyimpan gambar di riwayat (+ batas ukuran) |
| `frontend/src/components/GambarHasil.jsx` | Menampilkan, memperbesar, mengunduh |
| `frontend/src/components/Message.jsx` | Menempatkan gambar di bawah teks |
| `frontend/src/App.jsx` | Menangkap `meta.gambar` dari SSE |
| `frontend/src/hooks/useSessions.js` | Menyimpan gambar bersama pesan |
| `frontend/src/App.css` | Tampilan gambar |
| `backend/uji_gambar.py` | 79 pemeriksaan backend |
| `frontend/uji_gambar_browser.mjs` | 15 pemeriksaan browser |

---

## 12. Catatan penting untuk pengembangan berikutnya

- **Nama penyedia gambar tidak boleh muncul di UI.** Jangan pernah
  menampilkan `meta.gambar.label` (isinya hanya "gungdev") atau URL
  layanan. Uji browser memeriksanya.
- **Jangan mencatat jatah sebelum gambar berhasil.** Kalau dicatat di
  awal, pengguna kehilangan jatah hanya karena layanan sedang ramai.
- **Jangan memakai kunci jatah chat untuk gambar.** Itu yang membuat
  jatah bercampur — persis yang ingin dihindari.
- **`server_uji.py` mengganti endpoint `/chat`.** Bila menambah logika
  di `/chat` produksi, tambahkan juga di stub `chat_uji` dan
  `chat_stream_uji`; kalau tidak, uji browser tidak menguji apa pun
  yang berarti. Ini sempat terjadi pada fitur gambar.
