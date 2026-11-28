# Fitur "Buat Gambar" Ã¢â‚¬â€ Panduan Lengkap

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
menggambar"** Ã¢â‚¬â€ kisi titik yang terisi bertahap dengan lonceng persen Ã¢â‚¬â€
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
   mendapat penjelasan yang tenang Ã¢â‚¬â€ bukan halaman error.

---

## 3. Mengapa jatah gambar DIPISAH dari jatah chat

Ini permintaan langsung pemilik situs: *"jatah gambar dipisah dengan
jatah chat harian agar tidak boros di gambar saja"*.

| Jatah | Batas bawaan | Kunci penyimpanan |
|---|---|---|
| Chat (akun) | 52 pesan / 24 jam | `gungdev:usage:u:<sub>:<jendela>` |
| **Gambar (akun)** | **3 gambar / 24 jam** | `gungdev:usage:gambar:<sub>:<jendela>` |
| Gambar (tamu) | 0 | Ã¢â‚¬â€ |

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
Diperbarui dalam 5 jam 12 menit Ã‚Â· 48 dari 52
Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“Ë†Ã¢â€“â€˜Ã¢â€“â€˜Ã¢â€“â€˜
```

Alasannya sederhana: *"sisa 47 pesan"* tidak berarti apa-apa bagi
pengguna baru Ã¢â‚¬â€ ia tidak tahu 47 itu banyak atau sedikit. **"92% sisa"
langsung terbaca.** Angka pastinya tetap ada di baris keterangan kecil
(`48 dari 52`), jadi pengguna yang ingin hitungan tepat tidak
kehilangan apa pun.

Aturan tampilannya:

| Hal | Aturan |
|---|---|
| Yang ditonjolkan | **Sisa**, bukan terpakai (100% = masih penuh) |
| Bilah mengisi | Sesuai sisa (bilah panjang = jatah banyak) |
| Warna | Aksen biasa Ã¢â€ â€™ `is-rendah` (Ã¢â€°Â¤30%) Ã¢â€ â€™ `is-kritis` (Ã¢â€°Â¤10%) |
| Buta warna | Persen selalu **tertulis**, warna hanya penegas |
| Saat bilah kecil | Isi minimal 2% agar tidak terlihat kosong padahal ada |
| `prefers-reduced-motion` | Transisi dimatikan |

Ada **dua bilah terpisah** Ã¢â‚¬â€ obrolan dan gambar Ã¢â‚¬â€ karena keduanya
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
**sendiri tiap detik** Ã¢â‚¬â€ tanpa permintaan tambahan ke server. Bila
waktu reset tercapai, panel mengambil data sekali lagi supaya jatah yang
pulih langsung terlihat.

Bila pembacaan jatah gambar gagal (penyimpanan bermasalah), panel
**tetap** menampilkan jatah obrolan Ã¢â‚¬â€ kegagalan itu tidak boleh
menggagalkan seluruh panel.

---

## 4. Bagaimana server mengenali permintaan gambar

Ini bagian yang paling rawan. Bila salah kira, jatah gambar pengguna
terbuang hanya karena ia **bertanya**.

Aturannya sengaja **konservatif**: lebih baik melewatkan satu permintaan
gambar daripada membuat gambar padahal pengguna hanya bertanya.

**Dikenali sebagai permintaan gambar:**

- "buatkan gambar kucing oranyeÃ¢â‚¬Â¦"
- "gambarkan pemandangan pantaiÃ¢â‚¬Â¦"
- "tolong buat ilustrasi logoÃ¢â‚¬Â¦"
- "bikin gambar poster konser"
- "edit gambar ini jadi gaya anime" (ada lampiran gambar)

**TIDAK dikenali (hanya bertanya):**

- "apa itu gambar vektor?"
- "jelaskan cara membuat gambar dengan AI"
- "berapa harga gambar digital?"
- "gambaran umum ekonomi Indonesia" Ã¢â€ Â "gambaran", bukan "gambar"

### Jebakan yang sudah diperbaiki

Pencocokan frasa sempat memakai **substring biasa**. Akibatnya
"membuat gambar" cocok dengan "buat gambar", sehingga kalimat
*"jelaskan cara membuat gambar dengan AI"* **salah dikira** perintah
menggambar dan memakan jatah gambar.

Perbaikannya: semua pencocokan memakai **batas kata**
(`(?<![\w-])Ã¢â‚¬Â¦(?![\w-])`). Diuji oleh `uji_gambar.py` bagian 2.

---

## 5. Bagaimana gambar sampai ke layar

```
Pengguna mengetik "buatkan gambar kucing tidur di sofa"
        Ã¢â€â€š
        Ã¢â€“Â¼
Frontend  POST /chat/stream  (kontrak lama, tidak berubah)
        Ã¢â€â€š
        Ã¢â€“Â¼
Backend   perlu_gambar()  Ã¢â€ â€™ ya
        Ã¢â€â€š
        Ã¢â€“Â¼
SSE   data: {"meta": {"gambar_dimulai": {...}}}   Ã¢â€ Â DIKIRIM DULU
        Ã¢â€â€š                                          (animasi mulai di sini)
        Ã¢â€“Â¼
Backend   siapkan_gambar()
        Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ usage.periksa_jatah_gambar()  Ã¢â€ â€™ habis? Ã¢â€ â€™ pesan tenang, chat tetap jalan
        Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ gambar.deskripsi_gambar() Ã¢â€ â€™ terjemahkan IDÃ¢â€ â€™EN (lihat bagian 6)
        Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ gambar.buat_gambar()      Ã¢â€ â€™ ambil dari layanan gratis (enhance=true)
        Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ gambar._pangkas_bawah()   Ã¢â€ â€™ buang tanda air layanan
        Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ gambar._gambar_watermark()Ã¢â€ â€™ gambar tanda air "gungdev" sendiri
        Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ usage.catat_gambar()      Ã¢â€ â€™ catat HANYA bila berhasil
        Ã¢â€â€š
        Ã¢â€“Â¼
SSE   data: {"meta": {"gambar": {...}}}    Ã¢â€ Â gambar utuh (tidak bisa streaming)
      data: {"delta": "Ini gambar yang Anda minta..."}
      data: {"done": true}
        Ã¢â€â€š
        Ã¢â€“Â¼
Frontend  Message.jsx Ã¢â€ â€™ GambarHasil.jsx
```

### Mengapa `gambar_dimulai` dikirim lebih dulu

Membuat gambar butuh 10Ã¢â‚¬â€œ40 detik. Kalau penanda "proses dimulai" baru
dikirim bersama hasilnya, pengguna melihat animasi "Berpikir" (atau layar
diam) selama puluhan detik, lalu animasi gambar muncul sesaat sebelum
gambarnya Ã¢â‚¬â€ animasi yang tidak berguna.

Karena itu niatnya dideteksi lebih dulu (`perlu_gambar()`), penanda
dikirim, **baru** gambarnya dibuat. Frontend memakai penanda ini untuk
menampilkan `Menggambar.jsx` alih-alih `Berpikir.jsx`, dan melepasnya
lagi setelah selesai/gagal.

### Animasi "Sedang menggambar"

`Menggambar.jsx` menampilkan judul kecil, kisi 15Ãƒâ€”9 titik yang terisi
bertahap, dan lonceng persen.

**Soal persentase Ã¢â‚¬â€ penting:** server tidak bisa melaporkan kemajuan
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

## 6. Deskripsi diterjemahkan ke bahasa Inggris

**Ini bukan hiasan Ã¢â‚¬â€ inilah perbaikan kualitas yang paling berpengaruh.**

Kasus nyata yang melatarbelakanginya:

> "buatkan gambar kucing sedang tidur di sofa" Ã¢â€ â€™ kucing **berdiri** di sofa.

Penyebabnya bukan modelnya "bodoh". Model gambar dilatih dengan bahasa
Inggris, dan frasa "sedang tidur" tidak dikenali. Model hanya menangkap
"kucing" dan "sofa", lalu memakai pose bawaannya: duduk atau berdiri.

Perbaikannya, di `deskripsi_gambar()`:

1. Kalimat perintah dibuang ("tolong buatkan gambar ...").
2. Kata kunci diterjemahkan lewat kamus kecil: pose, warna, objek, latar,
   gaya, dan kata sambung.
3. Frasa **terpanjang menang**, supaya "anak kucing" Ã¢â€ â€™ `kitten` (bukan
   `child` + `cat`).
4. Kata yang tidak ada di kamus **dibiarkan** Ã¢â‚¬â€ permintaan tidak pernah
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
Ã¢â€ â€™ "a cat lying down asleep, eyes closed on sofa, highly detailed,
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
permintaan "poster pricelist" berubah menjadi foto semangkuk mie Ã¢â‚¬â€ kata
"mie goreng" satu-satunya kata benda yang dikenali model.

`_bersihkan_kata_sampah()` bekerja konservatif:

- **membuang** basa-basi ("dll nya yaa", "berikan", "terbaik"),
- **memperbaiki** salah ketik umum lewat `_SALAH_KETIK`
  (`pioster` Ã¢â€ â€™ poster, `bgfaus` Ã¢â€ â€™ bagus, `sayaa` Ã¢â€ â€™ saya),
- **membawa** kata asing/bahasa daerah yang ejaannya wajar
  (`tipat`, `rujak`, `warung`) Ã¢â‚¬â€ lebih baik membawa kata yang tidak
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
menulis apa pun Ã¢â‚¬â€ padahal teks adalah isi utama poster. Karena itu
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

## 7. Tanda air: milik gungdev sendiri

Dua langkah terpisah Ã¢â‚¬â€ sengaja, supaya kalau satu gagal yang lain tetap
jalan:

| Langkah | Fungsi | Tujuan |
|---|---|---|
| 1. Pangkas | `_pangkas_bawah()` | Buang tanda air penyedia |
| 2. Watermark | `_gambar_watermark()` | Tambah tanda air "gungdev" |

### Langkah 1 Ã¢â‚¬â€ kenapa memangkas, bukan sekadar menimpa

Layanan gambar gratis yang dipakai **selalu** menempelkan tanda air
("pollinations.ai") di pojok kanan bawah. Parameter `nologo=true` yang
dulu menghilangkannya **sudah tidak berpengaruh**.

Tanda air itu sudah menyatu di piksel, jadi satu-satunya cara
menghilangkannya adalah memotong strip bawahnya. Dipotong **6%**
(`PANGKAS_BAWAH`) Ã¢â‚¬â€ pada gambar 1024 px hanya ~61 px, biasanya area
lantai/latar, bukan objek utama.

Kalau pemangkasan ini dimatikan, tanda air penyedia akan tetap terlihat
dan bertumpuk dengan watermark gungdev.

### Langkah 2 Ã¢â‚¬â€ watermark gungdev

Setelah dipangkas, aplikasi menggambar tanda airnya sendiri di pojok
kanan bawah:

- teks kecil putih dengan bayangan gelap tipis Ã¢â‚¬â€ tetap terbaca di latar
  terang (mis. sofa putih) maupun gelap;
- satu titik aksen kecil di kiri teks sebagai penanda merek;
- ukuran dan jarak tepi mengikuti tinggi gambar, jadi proporsional di
  512 px maupun 1024 px;
- teksnya `gungdev` (bisa diganti lewat `GAMBAR_WATERMARK`).

Nama penyedia **tidak pernah** muncul di sini.

### Kalau ada yang gagal

Kedua fungsi mengembalikan **gambar asli apa adanya** bila gagal
(Pillow tidak terpasang, format tak dikenal). Tanda air lebih baik
daripada gambar rusak atau hilang Ã¢â‚¬â€ dan kegagalan tidak pernah
menggagalkan chat.

Catatan: JPEG bersifat *lossy*, jadi menyimpan ulang mengubah setiap
piksel sedikit. Itu sebabnya uji watermark memeriksa "perubahannya kecil
di luar area watermark", bukan "identik".

---

## 8. Batas waktu dan `maxDuration` Vercel

`GAMBAR_TIMEOUT` bawaan **52 detik**. Ini bukan angka sembarangan:
`maxDuration` fungsi serverless Vercel adalah **60 detik** (lihat
`vercel.json`), dan tidak bisa dinaikkan di paket gratis.

Kalau batas waktu di server lebih besar dari `maxDuration`, Vercel
memutus koneksi lebih dulu dan pengguna melihat galat koneksi Ã¢â‚¬â€ bukan
pesan yang jelas. Karena itu selalu **di bawah** 60, dengan sisa waktu
untuk menyiapkan jawaban.

---

## 9. Batas ukuran gambar di riwayat

| Batas | Nilai | Alasan |
|---|---|---|
| Satu gambar | 400 KB (base64) | Cukup untuk gambar 1024Ãƒâ€”1024 |
| Satu sesi | 900 KB (`MAKS_PESAN_SESI`) | Batas lama, tidak diubah |

Gambar yang lebih besar dari 400 KB **dibuang diam-diam** dari riwayat
server. Ini disengaja: lebih baik kehilangan satu gambar daripada
**gagal menyimpan seluruh riwayat** percakapan itu.

Gambar tetap terlihat selama sesi berjalan; yang hilang hanya
salinannya di server setelah halaman dimuat ulang.

---

## 10. Pengaturan lewat environment variable

Semua opsional. Tanpa diisi, semuanya memakai nilai bawaan yang wajar.

| Variabel | Bawaan | Arti |
|---|---|---|
| `JATAH_GAMBAR_PER_AKUN` | `3` | Gambar per akun per 24 jam |
| `JATAH_GAMBAR_TAMU` | `0` | Gambar untuk tamu (0 = perlu login) |
| `GAMBAR_UKURAN` | `1024` | Ukuran gambar (piksel, persegi) |
| `GAMBAR_TIMEOUT` | `52` | Batas waktu permintaan (detik) Ã¢â‚¬â€ harus < 60 |
| `GAMBAR_PERCOBAAN` | `3` | Berapa kali dicoba bila gagal |
| `GAMBAR_JEDA` | `1.5` | Jeda antar percobaan (detik) |
| `GAMBAR_PANGKAS_BAWAH` | `0.06` | Porsi bawah yang dipotong (0 = jangan) |
| `GAMBAR_WATERMARK` | `gungdev` | Teks tanda air milik aplikasi |
| `GAMBAR_WATERMARK_AKTIF` | `1` | `0` = jangan gambar tanda air gungdev |
| `GAMBAR_WATERMARK_UKURAN` | `0.032` | Tinggi huruf watermark (porsi tinggi gambar) |
| `GAMBAR_MODEL` | `flux` | Model gambar layanan |
| `GAMBAR_BASE_URL` | *(layanan bawaan)* | Ganti penyedia tanpa ubah kode |
| `GAMBAR_MAKS_BYTE` | `6000000` | Batas ukuran berkas gambar diterima |

Untuk pindah penyedia gambar nanti, cukup ubah `GAMBAR_BASE_URL` Ã¢â‚¬â€
logika niat, jatah, dan tampilan tidak perlu disentuh.

---

## 11. Kalau ingin pindah ke layanan berbayar nanti

Yang perlu diubah **hanya** `gambar.buat_gambar()`:

1. Tambahkan API key lewat environment variable.
2. Ganti cara memanggil layanan di dalam `buat_gambar()`.
3. Kalau layanan baru tidak menempelkan tanda air, set
   `GAMBAR_PANGKAS_BAWAH=0` (tanda air gungdev tetap digambar).

Niat, jatah, penyimpanan, dan tampilan **tidak perlu diubah**.

---

## 12. Menjalankan uji

```bash
cd chatbot-saya/backend
python uji_gambar.py          # 143 pemeriksaan (backend, tanpa jaringan)
```

```bash
cd chatbot-saya/frontend
node uji_gambar_browser.mjs   # 41 pemeriksaan (browser + UI)
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

## 13. Daftar berkas yang terlibat

| Berkas | Perannya |
|---|---|
| `backend/gambar.py` | Deteksi niat, penerjemah IDÃ¢â€ â€™EN, ambil gambar, pangkas + watermark |
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
| `backend/uji_gambar.py` | 143 pemeriksaan backend |
| `frontend/uji_gambar_browser.mjs` | 41 pemeriksaan browser |

---

## 14. Catatan penting untuk pengembangan berikutnya

- **Nama penyedia gambar tidak boleh muncul di UI.** Jangan pernah
  menampilkan `meta.gambar.label` (isinya hanya "gungdev") atau URL
  layanan. Uji browser memeriksanya.
- **Jangan mencatat jatah sebelum gambar berhasil.** Kalau dicatat di
  awal, pengguna kehilangan jatah hanya karena layanan sedang ramai.
- **Jangan memakai kunci jatah chat untuk gambar.** Itu yang membuat
  jatah bercampur Ã¢â‚¬â€ persis yang ingin dihindari.
- **Tanda fase gambar harus dilepas lagi.** `setMessageImagePhase(id, null)`
  dipanggil setelah selesai/gagal. Kalau lupa, animasi "Sedang
  menggambar" tertinggal di layar meskipun gambarnya sudah tampil.
- **Jatah tampil sebagai bilah persen, bukan angka mentah.** Judul bilah
  + "N% sisa" + keterangan reset + bilah tipis; angka pastinya hanya di
  baris keterangan kecil. Bilah menonjolkan **sisa**, bukan terpakai.
- **Jangan menampilkan dua animasi untuk satu proses.** Saat membuat
  gambar, `Berpikir` di dalam pesan, petunjuk bawah composer, dan
  indikator kosong harus diam Ã¢â‚¬â€ semuanya dikendalikan `membuatGambar`.
- **`server_uji.py` mengganti endpoint `/chat`.** Bila menambah logika
  di `/chat` produksi, tambahkan juga di stub `chat_uji` dan
  `chat_stream_uji`; kalau tidak, uji browser tidak menguji apa pun
  yang berarti. Ini sempat terjadi pada fitur gambar.
