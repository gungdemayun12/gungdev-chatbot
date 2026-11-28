# Fitur "Buat Gambar" ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Panduan Lengkap

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
- Kontrak `/chat` dan `/chat/stream` tetap sama. `gambar` dan
  `gambar_dimulai` hanyalah field **tambahan** yang hanya muncul bila
  gambar memang dibuat.
- Jatah chat (52 pesan/24 jam) tidak tersentuh oleh gambar.

Selama gambarnya dibuat, pengguna melihat animasi **"Sedang
menggambar"** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â kisi titik yang terisi bertahap dengan lonceng persen ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â
bukan animasi "Berpikir".

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
   mendapat penjelasan yang tenang ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â bukan halaman error.

---

## 3. Mesin gambar: Gemini dulu, layanan gratis sebagai cadangan

Gambar dibuat oleh **dua mesin berurutan**, bukan satu:

| Urutan | Mesin | Kapan dipakai | Ciri hasil |
|---|---|---|---|
| 1 | Gemini (model gambar) | selalu dicoba lebih dulu bila kuncinya ada | paling patuh pada deskripsi, tanpa logo penyedia |
| 2 | Layanan gratis | bila Gemini gagal / kuota habis | tanda air penyedia dipangkas, diganti `gungdev` |

MENGAPA BEGINI Ã¢â‚¬â€ hasil uji nyata pada permintaan pemilik situs:

> "buatkan gambar kucing sedang tidur di sofa"

| Mesin | Hasil |
|---|---|
| Layanan gratis | kucing **duduk**, tanda air penyedia masih menempel |
| Gemini (mesin utama) | kucing **tidur**, latar sofa, tanpa logo penyedia |

Tetapi kuota gambar gratis Gemini terbatas. Kalau hanya Gemini yang
dipakai, fitur gambar akan **mati total** begitu kuotanya habis. Karena
itu cadangan gratis selalu tersedia: pengguna selalu mendapat gambar,
kualitas terbaik saat kuota ada, tetap ada gambar saat kuota habis.

### Kunci yang dipakai

`GEMINI_API_KEY` yang **sudah ada** untuk penyedia teks. Pemilik situs
tidak perlu mendaftar layanan baru. Perbedaannya hanya nama model:

| Keperluan | Model | Endpoint |
|---|---|---|
| Obrolan (teks) | `gemini-3.5-flash-lite` | `chat/completions` (kompatibel OpenAI) |
| **Membuat gambar** | `gemini-3.1-flash-image` | `generateContent` (bentuk berbeda) |

Model teks di atas **tidak bisa** membuat gambar Ã¢â‚¬â€ itu bukan kerusakan,
memang bukan mesin gambar.

### Yang sengaja diperiksa ketat

**HTTP 200 tidak menjamin ada gambar.** Gemini bisa membalas 200 dengan
bagian teks saja (mis. menolak permintaan). Bila itu dianggap berhasil,
pengguna menerima pesan "gambar berhasil" tanpa gambar. Karena itu
`_ambil_gambar_gemini()` hanya menerima bagian yang benar-benar berisi
berkas gambar (`inlineData` dengan tanda awal JPEG/PNG).

### Pemangkasan hanya untuk cadangan

| Mesin | Pangkas 6% bawah? | Alasan |
|---|---|---|
| Gemini | **tidak** | tidak menempelkan logo; memangkas justru memotong isi sah |
| Layanan gratis | ya | logo penyedia menyatu di piksel, harus dibuang |

### Menandai gambar lama

Gambar di riwayat yang dibuat **sebelum** perbaikan ini masih membawa
tanda air penyedia Ã¢â‚¬â€ gambarnya tersimpan permanen dan tidak berubah
sendiri. Server kini menyimpan `mesin` bersama setiap gambar baru, dan UI
memakai penanda itu untuk menampilkan keterangan:

> Gambar ini dibuat sebelum kualitas gambar ditingkatkan, jadi tanda
> airnya mungkin masih terlihat. Minta gambar yang sama lagi untuk
> mendapat versi baru yang bersih.

**Tidak menebak dari ukuran berkas.** Percobaan pertama memakai ukuran
berkas dan itu salah: gambar baru dari cadangan juga kecil, sehingga
gambar baru diberi peringatan palsu. Peringatan palsu lebih buruk
daripada tidak ada peringatan.

---

## 4. Mengapa jatah gambar DIPISAH dari jatah chat

Ini permintaan langsung pemilik situs: *"jatah gambar dipisah dengan
jatah chat harian agar tidak boros di gambar saja"*.

| Jatah | Batas bawaan | Kunci penyimpanan |
|---|---|---|
| Chat (akun) | 52 pesan / 24 jam | `gungdev:usage:u:<sub>:<jendela>` |
| **Gambar (akun)** | **3 gambar / 24 jam** | `gungdev:usage:gambar:<sub>:<jendela>` |
| Gambar (tamu) | 0 | ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â |

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

### Bagaimana jatah ditampilkan: bilah persen, bukan angka

Panel **Jatah Saya** menampilkan jatah sebagai **bilah persen**, bukan
angka mentah:

```
Batas obrolan                            92% sisa
Diperbarui dalam 5 jam 12 menit ÃƒÆ’Ã¢â‚¬Å¡Ãƒâ€šÃ‚Â· 48 dari 52
ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€¹Ã¢â‚¬Â ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“ÃƒÂ¢Ã¢â€šÂ¬Ã‹Å“
```

Alasannya sederhana: *"sisa 47 pesan"* tidak berarti apa-apa bagi
pengguna baru ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ia tidak tahu 47 itu banyak atau sedikit. **"92% sisa"
langsung terbaca.** Angka pastinya tetap ada di baris keterangan kecil
(`48 dari 52`), jadi pengguna yang ingin hitungan tepat tidak
kehilangan apa pun.

Aturan tampilannya:

| Hal | Aturan |
|---|---|
| Yang ditonjolkan | **Sisa**, bukan terpakai (100% = masih penuh) |
| Bilah mengisi | Sesuai sisa (bilah panjang = jatah banyak) |
| Warna | Aksen biasa ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ `is-rendah` (ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°Ãƒâ€šÃ‚Â¤30%) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ `is-kritis` (ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â°Ãƒâ€šÃ‚Â¤10%) |
| Buta warna | Persen selalu **tertulis**, warna hanya penegas |
| Saat bilah kecil | Isi minimal 2% agar tidak terlihat kosong padahal ada |
| `prefers-reduced-motion` | Transisi dimatikan |

Ada **dua bilah terpisah** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â obrolan dan gambar ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â karena keduanya
memang tidak saling mengurangi. Digabung menjadi satu bilah, pengguna
akan mengira membuat gambar memotong jatah chat.

Data bilah berasal dari `/usage`:

```json
"akun": {
  "requests": { "terpakai": 4, "batas": 52, "sisa": 48, "persen": 8 },
  "gambar":   { "terpakai": 1, "batas": 3,  "sisa": 2,  "persen": 34,
                "habis": false,
                "reset": { "detik": 82000, "jam": 22.8, "pada": 1764...,
                           "bergulir": true, "jendela_jam": 24.0 } }
}
```

`reset.pada` (detik epoch) dipakai browser untuk menghitung mundur
**sendiri tiap detik** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â tanpa permintaan tambahan ke server. Bila
waktu reset tercapai, panel mengambil data sekali lagi supaya jatah yang
pulih langsung terlihat.

Bila pembacaan jatah gambar gagal (penyimpanan bermasalah), panel
**tetap** menampilkan jatah obrolan ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â kegagalan itu tidak boleh
menggagalkan seluruh panel.

---

## 5. Bagaimana server mengenali permintaan gambar

Ini bagian yang paling rawan. Bila salah kira, jatah gambar pengguna
terbuang hanya karena ia **bertanya**.

Aturannya sengaja **konservatif**: lebih baik melewatkan satu permintaan
gambar daripada membuat gambar padahal pengguna hanya bertanya.

**Dikenali sebagai permintaan gambar:**

- "buatkan gambar kucing oranyeÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦"
- "gambarkan pemandangan pantaiÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦"
- "tolong buat ilustrasi logoÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦"
- "bikin gambar poster konser"
- "edit gambar ini jadi gaya anime" (ada lampiran gambar)

**TIDAK dikenali (hanya bertanya):**

- "apa itu gambar vektor?"
- "jelaskan cara membuat gambar dengan AI"
- "berapa harga gambar digital?"
- "gambaran umum ekonomi Indonesia" ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Ãƒâ€šÃ‚Â "gambaran", bukan "gambar"

### Jebakan yang sudah diperbaiki

Pencocokan frasa sempat memakai **substring biasa**. Akibatnya
"membuat gambar" cocok dengan "buat gambar", sehingga kalimat
*"jelaskan cara membuat gambar dengan AI"* **salah dikira** perintah
menggambar dan memakan jatah gambar.

Perbaikannya: semua pencocokan memakai **batas kata**
(`(?<![\w-])ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬Ãƒâ€šÃ‚Â¦(?![\w-])`). Diuji oleh `uji_gambar.py` bagian 2.

---

## 6. Bagaimana gambar sampai ke layar

```
Pengguna mengetik "buatkan gambar kucing tidur di sofa"
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼
Frontend  POST /chat/stream  (kontrak lama, tidak berubah)
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼
Backend   perlu_gambar()  ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ ya
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼
SSE   data: {"meta": {"gambar_dimulai": {...}}}   ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Ãƒâ€šÃ‚Â DIKIRIM DULU
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡                                          (animasi mulai di sini)
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼
Backend   siapkan_gambar()
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ usage.periksa_jatah_gambar()  ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ habis? ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ pesan tenang, chat tetap jalan
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ gambar.deskripsi_gambar() ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ terjemahkan IDÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢EN (lihat bagian 6)
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ gambar.buat_gambar()      ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ ambil dari layanan gratis (enhance=true)
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ gambar._pangkas_bawah()   ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ buang tanda air layanan
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒâ€¦Ã¢â‚¬Å“ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ gambar._gambar_watermark()ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ gambar tanda air "gungdev" sendiri
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ usage.catat_gambar()      ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ catat HANYA bila berhasil
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼
SSE   data: {"meta": {"gambar": {...}}}    ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â Ãƒâ€šÃ‚Â gambar utuh (tidak bisa streaming)
      data: {"delta": "Ini gambar yang Anda minta..."}
      data: {"done": true}
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚ÂÃƒÂ¢Ã¢â€šÂ¬Ã…Â¡
        ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Å“Ãƒâ€šÃ‚Â¼
Frontend  Message.jsx ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ GambarHasil.jsx
```

### Mengapa `gambar_dimulai` dikirim lebih dulu

Membuat gambar butuh 10ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã…â€œ40 detik. Kalau penanda "proses dimulai" baru
dikirim bersama hasilnya, pengguna melihat animasi "Berpikir" (atau layar
diam) selama puluhan detik, lalu animasi gambar muncul sesaat sebelum
gambarnya ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â animasi yang tidak berguna.

Karena itu niatnya dideteksi lebih dulu (`perlu_gambar()`), penanda
dikirim, **baru** gambarnya dibuat. Frontend memakai penanda ini untuk
menampilkan `Menggambar.jsx` alih-alih `Berpikir.jsx`, dan melepasnya
lagi setelah selesai/gagal.

### Animasi "Sedang menggambar"

`Menggambar.jsx` menampilkan judul kecil, kisi 15ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â9 titik yang terisi
bertahap, dan lonceng persen.

**Soal persentase ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â penting:** server tidak bisa melaporkan kemajuan
sungguhan, karena layanan gambar baru mengirim hasilnya sekali di akhir.
Persen di sini adalah **perkiraan waktu**, bukan kemajuan nyata. Supaya
tidak menipu:

- angkanya berhenti di **97%** dan tidak pernah 100% sebelum gambar tiba;
- ia naik cepat di awal lalu melambat (`sqrt`), bukan garis lurus;
- setelah melewati perkiraan, teksnya berubah menjadi "hampir selesai".

### Mengapa gambar dikirim sebagai data URL

Kalau UI hanya menyimpan **tautan**, gambar bisa hilang saat halaman
dimuat ulang (layanan gratis tidak menyimpan gambar selamanya). Data
URL membuat gambar ikut tersimpan bersama riwayat, jadi tetap terlihat
kapan pun.

Konsekuensinya: gambar ikut dikirim ke penyimpanan riwayat. Karena itu
ada batas ukuran (lihat bagian 7).

---

## 7. Deskripsi diterjemahkan ke bahasa Inggris

**Ini bukan hiasan ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â inilah perbaikan kualitas yang paling berpengaruh.**

Kasus nyata yang melatarbelakanginya:

> "buatkan gambar kucing sedang tidur di sofa" ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ kucing **berdiri** di sofa.

Penyebabnya bukan modelnya "bodoh". Model gambar dilatih dengan bahasa
Inggris, dan frasa "sedang tidur" tidak dikenali. Model hanya menangkap
"kucing" dan "sofa", lalu memakai pose bawaannya: duduk atau berdiri.

Perbaikannya, di `deskripsi_gambar()`:

1. Kalimat perintah dibuang ("tolong buatkan gambar ...").
2. Kata kunci diterjemahkan lewat kamus kecil: pose, warna, objek, latar,
   gaya, dan kata sambung.
3. Frasa **terpanjang menang**, supaya "anak kucing" ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ `kitten` (bukan
   `child` + `cat`).
4. Kata yang tidak ada di kamus **dibiarkan** ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â permintaan tidak pernah
   hilang hanya karena tidak dikenali.
5. Gaya foto bawaan ditambahkan bila pengguna tidak memilih gaya sendiri:

   ```
   highly detailed, sharp focus, professional photography,
   natural soft lighting, shallow depth of field, 8k
   ```

6. Penegasan negatif selalu ditambahkan untuk mengurangi hasil aneh:
   `no text, no watermark, no distorted anatomy, no extra limbs`.

Contoh hasil:

```
"buatkan saya sebuah gambar kucing sedang tidur di sofa"
ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ "a cat lying down asleep, eyes closed on sofa, highly detailed,
   sharp focus, professional photography, natural soft lighting,
   shallow depth of field, 8k, no text, no watermark, ..."
```

Kata posenya sekarang tidak bisa disalahtafsirkan: `lying down`,
`asleep`, `eyes closed`. Hasilnya kucing benar-benar tidur meringkuk.

Bila pengguna menyebut gayanya sendiri ("gaya anime", "kartun"), gaya
itulah yang dipakai dan gaya foto tidak ditambahkan.

### Membuang kata sampah

Permintaan nyata sering penuh basa-basi dan salah ketik:

> "buatkan pioster pricelist yang **bgfaus** yaa, beriakan saya gambar
> terbaik **nya yaaa**"

Kata seperti ini **tidak bisa ditafsirkan** model gambar, dan yang lebih
buruk: ia **mengaburkan** kata yang penting. Inilah penyebab nyata
permintaan "poster pricelist" berubah menjadi foto semangkuk mie ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â kata
"mie goreng" satu-satunya kata benda yang dikenali model.

`_bersihkan_kata_sampah()` bekerja konservatif:

- **membuang** basa-basi ("dll nya yaa", "berikan", "terbaik"),
- **memperbaiki** salah ketik umum lewat `_SALAH_KETIK`
  (`pioster` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ poster, `bgfaus` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ bagus, `sayaa` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢ saya),
- **membawa** kata asing/bahasa daerah yang ejaannya wajar
  (`tipat`, `rujak`, `warung`) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â lebih baik membawa kata yang tidak
  dikenal daripada membuang kata yang penting.

Bila pembersihan menghabiskan seluruh deskripsi, teks asli dipakai
kembali. Deskripsi kotor lebih baik daripada deskripsi kosong.

### Karya desain: poster, pricelist, logo

Permintaan desain **tidak** memakai gaya foto. Alasannya nyata:

| | Foto | Karya desain |
|---|---|---|
| Gaya | `professional photography` | `flat graphic design layout` |
| Negatif | `no text, ...` | **tanpa** `no text` |

Foto tidak punya tata letak, dan `no text` justru **melarang** model
menulis apa pun ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â padahal teks adalah isi utama poster. Karena itu
`_KRIA_DESAIN` memisahkan keduanya.

Untuk **pricelist/daftar harga/menu**, arahan gayanya lebih spesifik
lagi (`_GAYA_DAFTAR_HARGA`): baris menu dengan garis titik-titik ke
harga, kolom rata, grid foto kecil, judul besar di atas. Tanpa ini
model menumpuk semua makanan di tengah dan hasilnya poster makanan,
bukan daftar harga.

**Batas jujur:** model gambar gratis bisa meniru *tata letak* poster,
tetapi **belum bisa menulis huruf yang benar-benar terbaca**. Karena itu
`pesan_berhasil()` menambahkan satu kalimat jujur untuk karya desain,
dan menawarkan menyusun daftar harga sebagai teks. Tanpa penjelasan ini
pengguna mengira aplikasinya rusak.

---

## 8. Tanda air: milik gungdev sendiri

Dua langkah terpisah ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â sengaja, supaya kalau satu gagal yang lain tetap
jalan:

| Langkah | Fungsi | Tujuan |
|---|---|---|
| 1. Pangkas | `_pangkas_bawah()` | Buang tanda air penyedia |
| 2. Watermark | `_gambar_watermark()` | Tambah tanda air "gungdev" |

### Langkah 1 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â kenapa memangkas, bukan sekadar menimpa

Layanan gambar gratis yang dipakai **selalu** menempelkan tanda air
("pollinations.ai") di pojok kanan bawah. Parameter `nologo=true` yang
dulu menghilangkannya **sudah tidak berpengaruh**.

Tanda air itu sudah menyatu di piksel, jadi satu-satunya cara
menghilangkannya adalah memotong strip bawahnya. Dipotong **6%**
(`PANGKAS_BAWAH`) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â pada gambar 1024 px hanya ~61 px, biasanya area
lantai/latar, bukan objek utama.

Kalau pemangkasan ini dimatikan, tanda air penyedia akan tetap terlihat
dan bertumpuk dengan watermark gungdev.

### Langkah 2 ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â watermark gungdev

Setelah dipangkas, aplikasi menggambar tanda airnya sendiri di pojok
kanan bawah:

- teks kecil putih dengan bayangan gelap tipis ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â tetap terbaca di latar
  terang (mis. sofa putih) maupun gelap;
- satu titik aksen kecil di kiri teks sebagai penanda merek;
- ukuran dan jarak tepi mengikuti tinggi gambar, jadi proporsional di
  512 px maupun 1024 px;
- teksnya `gungdev` (bisa diganti lewat `GAMBAR_WATERMARK`).

Nama penyedia **tidak pernah** muncul di sini.

### Kalau ada yang gagal

Kedua fungsi mengembalikan **gambar asli apa adanya** bila gagal
(Pillow tidak terpasang, format tak dikenal). Tanda air lebih baik
daripada gambar rusak atau hilang ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â dan kegagalan tidak pernah
menggagalkan chat.

Catatan: JPEG bersifat *lossy*, jadi menyimpan ulang mengubah setiap
piksel sedikit. Itu sebabnya uji watermark memeriksa "perubahannya kecil
di luar area watermark", bukan "identik".

---

## 9. Batas waktu dan `maxDuration` Vercel

`GAMBAR_TIMEOUT` bawaan **52 detik**. Ini bukan angka sembarangan:
`maxDuration` fungsi serverless Vercel adalah **60 detik** (lihat
`vercel.json`), dan tidak bisa dinaikkan di paket gratis.

Kalau batas waktu di server lebih besar dari `maxDuration`, Vercel
memutus koneksi lebih dulu dan pengguna melihat galat koneksi ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â bukan
pesan yang jelas. Karena itu selalu **di bawah** 60, dengan sisa waktu
untuk menyiapkan jawaban.

---

## 10. Batas ukuran gambar di riwayat

| Batas | Nilai | Alasan |
|---|---|---|
| Satu gambar | 400 KB (base64) | Cukup untuk gambar 1024ÃƒÆ’Ã†â€™ÃƒÂ¢Ã¢â€šÂ¬Ã¢â‚¬Â1024 |
| Satu sesi | 900 KB (`MAKS_PESAN_SESI`) | Batas lama, tidak diubah |

Gambar yang lebih besar dari 400 KB **dibuang diam-diam** dari riwayat
server. Ini disengaja: lebih baik kehilangan satu gambar daripada
**gagal menyimpan seluruh riwayat** percakapan itu.

Gambar tetap terlihat selama sesi berjalan; yang hilang hanya
salinannya di server setelah halaman dimuat ulang.

---

## 11. Pengaturan lewat environment variable

Semua opsional. Tanpa diisi, semuanya memakai nilai bawaan yang wajar.

| Variabel | Bawaan | Arti |
|---|---|---|
| `JATAH_GAMBAR_PER_AKUN` | `3` | Gambar per akun per 24 jam |
| `JATAH_GAMBAR_TAMU` | `0` | Gambar untuk tamu (0 = perlu login) |
| `GAMBAR_UKURAN` | `1024` | Ukuran gambar (piksel, persegi) |
| `GAMBAR_TIMEOUT` | `52` | Batas waktu permintaan (detik) ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â harus < 60 |
| `GAMBAR_PERCOBAAN` | `3` | Berapa kali dicoba bila gagal |
| `GAMBAR_JEDA` | `1.5` | Jeda antar percobaan (detik) |
| `GAMBAR_PANGKAS_BAWAH` | `0.06` | Porsi bawah yang dipotong (0 = jangan) |
| `GAMBAR_WATERMARK` | `gungdev` | Teks tanda air milik aplikasi |
| `GAMBAR_WATERMARK_AKTIF` | `1` | `0` = jangan gambar tanda air gungdev |
| `GAMBAR_WATERMARK_UKURAN` | `0.032` | Tinggi huruf watermark (porsi tinggi gambar) |
| `GAMBAR_MODEL` | `flux` | Model gambar layanan |
| `GAMBAR_BASE_URL` | *(layanan bawaan)* | Ganti penyedia tanpa ubah kode |
| `GAMBAR_MAKS_BYTE` | `6000000` | Batas ukuran berkas gambar diterima |
| `GEMINI_GAMBAR_MODEL` | `gemini-3.1-flash-image` | Model **gambar** Gemini (kosongkan = matikan mesin utama) |
| `GEMINI_GAMBAR_UKURAN` | `1K` | Ukuran keluaran Gemini: `512`/`1K`/`2K`/`4K` |
| `GEMINI_GAMBAR_TIMEOUT` | `40` | Batas waktu satu permintaan Gemini (detik) |
| `GAMBAR_CADANGAN_TIMEOUT` | `45` | Batas waktu cadangan gratis setelah Gemini gagal |

Untuk pindah penyedia gambar nanti, cukup ubah `GAMBAR_BASE_URL` ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â
logika niat, jatah, dan tampilan tidak perlu disentuh.

---

## 11b. Penyedia chat kelima: kuota HARIAN, tanpa kartu kredit

Situs punya beberapa penyedia chat. Yang menentukan **jatah harian** adalah
seberapa besar kuota gratis masing-masing penyedia, jadi menambah penyedia
berarti menambah jatah obrolan untuk semua pengguna.

**Syarat yang diminta pemilik situs: kuota reset HARIAN, bukan bulanan, dan
tanpa kartu kredit.** Hasil riset halaman resmi penyedia (Nov 2026):

| Penyedia | Kuota | Reset | Kartu | Lolos? |
|---|---|---|---|---|
| Groq | 1.000 permintaan + 200.000 token per model/hari | harian | tidak | sudah dipakai |
| OpenRouter | 50/hari (1.000 bila beli 10 kredit) | harian | tidak | sudah dipakai |
| Gemini (teks) | ~1.000/hari/model | harian (tengah malam Pasifik) | tidak | sudah dipakai |
| NVIDIA NIM | kredit trial ~1.000 panggilan | sekali, ±90 hari | tidak | sudah dipakai |
| **Cloudflare Workers AI** | **10.000 Neuron/hari** | **00:00 UTC** | **tidak** | **dipakai** |
| Mistral | ~1 miliar token/**bulan** | bulanan | verifikasi HP | gugur |
| Cerebras | kredit $5 habis 30 hari | sekali | **wajib** | gugur |
| Together AI | tidak ada free tier permanen | — | ya | gugur |

### Berapa pesan tambahannya?

10.000 Neuron per hari, dengan perkiraan satu pesan ±1.500 token masuk +
600 token keluar:

| Model | Neuron/pesan | Pesan/hari |
|---|---|---|
| `granite-4.0-h-micro` | 8 | **1.189** |
| `qwen3-30b-a3b` | 25 | **396** |
| `gemma-4-26b-a4b-it` | 30 | **333** |
| `gpt-oss-120b` | 44 | **229** |
| `qwen2.5-coder-32b` | 145 | **69** |

### Model mana yang dipakai, dan kapan

Pemilik situs meminta "yang paling pintar", khususnya untuk coding. Yang
**paling pintar tetapi masih gratis** di Cloudflare adalah `gpt-oss-120b`,
jadi itu default-nya. Model lain dipakai otomatis sesuai kebutuhan:

| Kebutuhan | Model | Alasan |
|---|---|---|
| Obrolan biasa | `gpt-oss-120b` | paling pintar yang gratis |
| Pesan minta **coding** | `qwen2.5-coder-32b` | khusus coding; hanya dipakai saat relevan karena paling mahal |
| Ada **gambar** | `llama-4-scout` | satu-satunya model gratis Cloudflare yang bisa membaca gambar |
| Kuota hampir habis | `granite-4.0-h-micro` | paling hemat; selalu ditaruh paling akhir agar chat tidak mati |

**Penting — jangan berharap ke model berbayar.** Model coding TERBAIK
Cloudflare (`kimi-k2.7-code`, `glm-5.3`, `deepseek-v4`, `inkling-2-small`)
**wajib metode pembayaran berbayar**. Dokumentasi resmi menyebutnya
demikian, dan memakainya di akun gratis hanya menghasilkan HTTP 403. Karena
itu model-model itu **sengaja tidak dimasukkan** ke daftar.

### Pengaturan

| Variabel | Bawaan | Arti |
|---|---|---|
| `CLOUDFLARE_ACCOUNT_ID` | *(kosong)* | Account ID dari dashboard Cloudflare |
| `CLOUDFLARE_API_TOKEN` | *(kosong)* | API token Workers AI (Read + Edit) |
| `CLOUDFLARE_MODEL` | `cloudflare/gpt-oss-120b` | Model default |
| `CLOUDFLARE_BASE_URL` | `https://api.cloudflare.com/client/v4` | Jarang perlu diubah |

Bila `CLOUDFLARE_ACCOUNT_ID` **atau** `CLOUDFLARE_API_TOKEN` kosong, seluruh
bagian Cloudflare dilewati — situs kembali memakai penyedia lain seperti
biasa, tanpa error. Periksa kunci sebelum deploy dengan:

```bash
cd chatbot-saya/backend
python cek_key.py cloudflare
```

### Apa yang terjadi saat kuota habis

Cloudflare membalas HTTP 429 ketika 10.000 Neuron harian terpakai. Server
**tidak menampilkan error** kepada pengguna: permintaan otomatis dialihkan ke
penyedia lain yang masih punya sisa kuota (`complete()` / `stream()` di
`main.py`). Ini perilaku yang sama dengan penyedia lain, dan dijaga oleh
`uji_cloudflare.py`.

---

## 12. Kalau ingin pindah ke layanan berbayar nanti

Yang perlu diubah **hanya** `gambar.buat_gambar()`:

1. Tambahkan API key lewat environment variable.
2. Ganti cara memanggil layanan di dalam `buat_gambar()`.
3. Kalau layanan baru tidak menempelkan tanda air, set
   `GAMBAR_PANGKAS_BAWAH=0` (tanda air gungdev tetap digambar).

Niat, jatah, penyimpanan, dan tampilan **tidak perlu diubah**.

---

## 13. Menjalankan uji

```bash
cd chatbot-saya/backend
python uji_gambar.py          # 171 pemeriksaan (backend, tanpa jaringan)
python uji_cloudflare.py       # 41 pemeriksaan (penyedia Cloudflare, tanpa jaringan)
```

```bash
cd chatbot-saya/frontend
node uji_gambar_browser.mjs   # 52 pemeriksaan (browser + UI)
```

`uji_gambar_browser.mjs` memakai gambar tiruan dari `server_uji.py`,
jadi **tidak butuh internet** dan tidak memanggil layanan sungguhan.

Uji backend memakai akun khusus (`...009`) agar tidak mengotori akun
uji lain. Bila menjalankan `uji_api.py`, reset akun dulu:

```bash
curl -X POST http://127.0.0.1:8000/__uji/reset \
  -H "Content-Type: application/json" -d "{\"sub\":\"100000000000000001\"}"
```

Jatah gambar akun hanya 3 per 24 jam, sedangkan satu berkas uji browser
menjalankan beberapa skenario berurutan. Untuk itu ada endpoint khusus
uji yang mengosongkan jatah gambar di tengah uji:

```bash
curl -X POST http://127.0.0.1:8000/__uji/jatah-gambar-bebaskan \
  -H "Content-Type: application/json" -d "{\"sub\":\"100000000000000001\"}"
```

Endpoint ini **hanya ada di `server_uji.py`**, tidak di produksi.

---

## 14. Daftar berkas yang terlibat

| Berkas | Perannya |
|---|---|
| `backend/gambar.py` | Deteksi niat, penerjemah IDÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â ÃƒÂ¢Ã¢â€šÂ¬Ã¢â€žÂ¢EN, ambil gambar, pangkas + watermark |
| `backend/usage.py` | Jatah gambar (terpisah dari jatah chat) |
| `backend/main.py` | `perlu_gambar()`, `siapkan_gambar()`, `/chat` & `/chat/stream` |
| `backend/penyimpanan.py` | Menyimpan gambar di riwayat (+ batas ukuran) |
| `frontend/src/components/Menggambar.jsx` | Animasi kisi titik + persen |
| `frontend/src/components/JatahBar.jsx` | Satu bilah jatah bergaya "Plan limits" (persen sisa) |
| `frontend/src/components/UsagePanel.jsx` | Panel Jatah Saya: dua bilah (obrolan & gambar) |
| `frontend/src/components/Berpikir.jsx` | Animasi untuk chat biasa (bukan gambar) |
| `frontend/src/components/GambarHasil.jsx` | Menampilkan, memperbesar, mengunduh |
| `frontend/src/components/Message.jsx` | Memilih animasi & menempatkan gambar |
| `frontend/src/components/ChatArea.jsx` | Meneruskan `faseGambar`, mematikan hint ganda |
| `frontend/src/App.jsx` | Menangkap `meta.gambar_dimulai` & `meta.gambar` |
| `frontend/src/hooks/useSessions.js` | Menyimpan gambar & tanda fase gambar |
| `frontend/src/App.css` | Tampilan gambar, animasi `.menggambar*`, bilah `.jatah-bar*` |
| `backend/uji_gambar.py` | 160 pemeriksaan backend |
| `backend/uji_cloudflare.py` | 41 pemeriksaan jalur penyedia Cloudflare (tanpa jaringan) |
| `frontend/uji_gambar_browser.mjs` | 52 pemeriksaan browser |

---

## 15. Catatan penting untuk pengembangan berikutnya

- **Nama penyedia gambar tidak boleh muncul di UI.** Jangan pernah
  menampilkan `meta.gambar.label` (isinya hanya "gungdev") atau URL
  layanan. Uji browser memeriksanya.
- **Jangan mencatat jatah sebelum gambar berhasil.** Kalau dicatat di
  awal, pengguna kehilangan jatah hanya karena layanan sedang ramai.
- **Jangan memakai kunci jatah chat untuk gambar.** Itu yang membuat
  jatah bercampur ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â persis yang ingin dihindari.
- **Tanda fase gambar harus dilepas lagi.** `setMessageImagePhase(id, null)`
  dipanggil setelah selesai/gagal. Kalau lupa, animasi "Sedang
  menggambar" tertinggal di layar meskipun gambarnya sudah tampil.
- **Jatah tampil sebagai bilah persen, bukan angka mentah.** Judul bilah
  + "N% sisa" + keterangan reset + bilah tipis; angka pastinya hanya di
  baris keterangan kecil. Bilah menonjolkan **sisa**, bukan terpakai.
- **Jangan memakai model teks Gemini untuk membuat gambar.** Itu mesin
  obrolan; gambar butuh model gambar (`gemini-3.1-flash-image`) dan
  endpoint `generateContent`.
- **Cadangan gratis jangan dihapus.** Tanpanya, fitur gambar mati total
  saat kuota Gemini habis. Selalu uji jalur "Gemini gagal → cadangan".
- **Pemangkasan 6% hanya untuk mesin cadangan.** Gemini tidak menempelkan
  logo, jadi memangkasnya justru memotong isi gambar yang sah.
- **Field `mesin` harus ikut tersimpan** di `useSessions.js` dan
  `penyimpanan.py`. Bila tertinggal, gambar baru kehilangan penandanya
  dan UI menampilkan peringatan "gambar lama" yang palsu.
- **Penanda gambar lama tidak boleh ditebak dari ukuran berkas.** Gambar
  baru dari cadangan juga kecil; itulah sebabnya percobaan pertama
  memberi peringatan palsu. Pakai `mesin`.
- **Jangan menampilkan dua animasi untuk satu proses.** Saat membuat
  gambar, `Berpikir` di dalam pesan, petunjuk bawah composer, dan
  indikator kosong harus diam ÃƒÆ’Ã‚Â¢ÃƒÂ¢Ã¢â‚¬Å¡Ã‚Â¬ÃƒÂ¢Ã¢â€šÂ¬Ã‚Â semuanya dikendalikan `membuatGambar`.
- **`server_uji.py` mengganti endpoint `/chat`.** Bila menambah logika
  di `/chat` produksi, tambahkan juga di stub `chat_uji` dan
  `chat_stream_uji`; kalau tidak, uji browser tidak menguji apa pun
  yang berarti. Ini sempat terjadi pada fitur gambar.
