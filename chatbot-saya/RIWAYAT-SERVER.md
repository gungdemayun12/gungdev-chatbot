# Riwayat di Server + Pemakaian per Akun

Dokumen ini menjelaskan cara mengaktifkan fitur **riwayat yang sama di semua
perangkat** dan **pemakaian (usage) per akun**.

Tanpa dua langkah di bawah, aplikasi tetap berjalan normal — hanya riwayatnya
masih tersimpan di perangkat masing-masing.

---

## Ringkasan yang berubah

| Sebelum | Sesudah |
|---|---|
| Riwayat hanya di browser | Riwayat di server, **sama di semua perangkat** |
| Hapus data browser = riwayat hilang | Riwayat aman di server |
| Semua pengunjung berbagi satu angka usage | Tiap akun punya **jatah 60 pesan/24 jam** sendiri |
| Tidak ada pembatas per akun | Satu akun habis jatah **tidak** memengaruhi akun lain |
| — | Bila server tak bisa dipakai, salinan perangkat dipakai otomatis |
| Satu penyedia AI habis kuota = situs berhenti | **Failover otomatis** ke penyedia lain saat kuota habis (429/402) |

Kontrak API lama **tidak berubah**: `/chat`, `/chat/stream`, `/health`,
`/capabilities` tetap sama persis.

---

## Jatah chat per akun

| Hal | Nilai |
|---|---|
| Jatah pesan per akun | **60 pesan per jendela 24 jam** |
| Saat layanan ramai | Sementara 8 pesan (otomatis, kembali normal sendiri) |
| Jatah tamu | 3 pesan/hari (per IP, tidak berubah) |
| Akun baru per hari | Maksimal 25 (agar akun baru tidak melampaui kapasitas 566/hari) |
| Kapan jendela dimulai | **Saat pesan pertama akun itu** |
| Kapan reset | Saat jendela 24 jamnya berakhir — **berbeda tiap akun** |
| Token | **Dicatat & ditampilkan**, tetapi **tidak membatasi** |
| Yang dilihat pengguna | **Hanya jatahnya sendiri** — kapasitas layanan hanya untuk pemilik situs |

### Dari mana angka 52 berasal

Kuota gratis dipakai bergantian menurut model yang dipilih, dan
**otomatis saling menyelamatkan** saat salah satu kehabisan kuota:

| Sumber | Batas request/hari | Batas token/hari |
|---|---|---|
| Groq (tiga model gratis) | 3 × 1.000 = 3.000 | 3 × 200.000 = 600.000 |
| Gemini (penyedia cadangan) | 200 | 250.000 |
| OpenRouter (model `:free`) | 50 | tanpa batas |

Kunci perubahannya: **batas Groq dihitung per model**, bukan per
penyedia. Tiga model gratis yang dipakai punya jatah masing-masing, jadi
kapasitas gabungannya tiga kali lipat dari hitungan lama:

```
kendala request : 3.000 + 200 + 50      = 3.250 request/hari
kendala token   : 600.000 + 250.000     = 850.000 token/hari
                  850.000 / 1.500       = 566 pesan/hari  <- yang lebih dulu habis
                  566 / 10 akun aktif   = 56 pesan per akun (dipakai 52)
```

Angka 1.500 token/pesan adalah rata-rata nyata (pesan pendek ±700 token,
pesan panjang/riset ±3.000 token). Kendala yang menentukan adalah **token**,
bukan request — request masih sangat longgar (3.250 untuk 566 pesan).

Jatah dipakai **52** (bukan 56) karena angka Gemini di atas sengaja dibuat
konservatif: Google tidak lagi mempublikasikan RPD pasti untuk free tier.
Bila kuota Gemini ternyata lebih besar, tidak ada yang rusak — kita hanya
tidak memanfaatkannya. Yang berbahaya adalah sebaliknya: menetapkan jatah
lebih tinggi dari kuota nyata.

**Catatan revisi (48 → 52).** Sebelumnya jatah 48 diambil dari 56
dikurangi bantalan ±15%. Bantalan itu diperkecil menjadi ±7% setelah
pemakaian nyata di produksi diperiksa: saat jatah 48 dipakai, sisa kuota
harian masih cukup, sehingga 4 pesan tambahan masih tertutup. Dengan 52,
kapasitas 566 pesan/hari masih menampung **10 akun aktif penuh**
(566 / 52 = 10,9). Penjaga otomatis tetap bekerja: bila sisa kuota situs
< 15%, jatah sementara dipangkas ke 8 pesan supaya situs tidak mati.

Kenaikan ini **bukan** karena NVIDIA. NVIDIA berupa trial credit yang bisa
habis, jadi tidak dihitung sebagai kapasitas (lihat `trial_nvidia_dihitung`
di `usage.py`). Kenaikan besar (mis. 48 → 70-an) baru mungkin bila ada
kuota harian **tetap** yang benar-benar baru — misalnya project Google
Gemini tambahan atau model Groq baru yang terbukti hidup saat diuji
**langsung ke penyedianya**, bukan lewat server sendiri.

### Jawaban tidak lagi terpotong

Keluhan nyata: jawaban berhenti di tengah, pengguna harus mengetik
"lanjut" — dan itu **memakan satu jatah pesan lagi** padahal satu
pertanyaan belum selesai dijawab.

Tiga penyebab, semuanya diperbaiki:

| Penyebab | Perbaikan |
|---|---|
| `DEFAULT_MAX_TOKENS` hanya 2.048 — terlalu pendek untuk riset | Dinaikkan ke **4.096** (bawaan & riset) |
| `httpx` timeout 60 dtk berlaku juga untuk **membaca** stream, jadi jawaban panjang diputus di detik ke-60 | `TIMEOUT_STREAM`: connect 15 dtk, **read 120 dtk** (jeda antar-potongan, bukan total durasi) |
| Model kehabisan token → jawaban berhenti, pengguna harus "lanjut" | **Sambung otomatis**: server meminta lanjutan ke model yang sama dan menyambungkannya ke jawaban yang sama |

Sambung otomatis (`MAKS_SAMBUNG = 3`) berjalan **di dalam satu
permintaan**, jadi pemakaian dicatat **sekali** — satu pertanyaan tetap
satu jatah. Bila setelah tiga sambungan masih terpotong, server mengirim
sinyal `{"terpotong": true}` sebelum `{"done": true}` agar UI memberi
tahu dengan tenang.

### Menu model diringkas

Daftar 12 model dulu ditampilkan sekaligus; di ponsel menu itu mendorong
kotak ketik keluar layar. Sekarang:

- **Tampil lebih dulu** (`MODEL_UTAMA` di `frontend/src/lib/models.js`):
  GPT-OSS 120B, Qwen3.8 27B, DeepSeek V4.1 Flash, Gemini 4 Argon,
  Gemini 3.5 Lite.
- **Sisanya** di balik tombol **"Model lainnya"** (dengan jumlahnya).
- Model yang sedang aktif **selalu ditampilkan** walau ia bukan model
  utama, supaya pengguna tidak kehilangan jejak pilihannya.
- Tidak ada model yang dihapus — semua tetap bisa dipilih.

Kenapa 52 dan bukan angka lain:

- **16** (hitungan lama) terlalu pesimis: hanya memakai satu model Sumber B.
- **80** aman hanya bila ≤ 7 akun aktif/hari; satu pengguna yang suka riset
  web memakai ±3.000 token/pesan (2× rata-rata), sehingga kuota bisa habis
  sebelum hari berakhir.
- **56** adalah batas teoretis (566 pesan/hari ÷ 10 akun aktif).
- **52** = 56 dikurangi bantalan ±7%. Aman untuk ±10 akun aktif/hari dan
  masih menyisakan ruang untuk pesan panjang/riset.

Bantalan itu penting karena 1.500 token/pesan adalah **rata-rata**: pesan
riset bisa dua kali lipat. Bila jatah dipasang 56 dan kuota Gemini ternyata
lebih kecil dari perkiraan, kuota situs habis sebelum hari berakhir dan
**semua** pengunjung kena.

Dua penjaga supaya kuota tidak habis di tengah hari:

1. **Jatah dipangkas otomatis** — bila sisa pesan situs < 15% dari kapasitas
   harian (795), akun mendapat 8 pesan/24 jam. Akun yang datang belakangan
   tetap kebagian.
2. **Batas akun baru per hari** — maksimal 25 akun baru. Tanpa ini, 25 akun
   baru x 60 pesan sehari sudah melampaui kapasitas 795 pesan/hari.

### Jendela bergulir, bukan jam dinding

Jatah **tidak** direset serentak untuk semua akun. Tiap akun punya
jendela 24 jam miliknya sendiri:

| Akun mulai chat | Jendelanya | Saat habis, pulih |
|---|---|---|
| GungDe jam 20:00 | 20:00 → 20:00 besok | 20:00 besok (bukan 07:00 pagi) |
| Indah jam 09:00 | 09:00 → 09:00 besok | 09:00 besok |

Akun yang **tidak** menghabiskan jatah tidak pernah dibatasi sama
sekali; hitung mundur hanya ditampilkan sebagai informasi.

Jendela yang dipakai bersama: `JENDELA_JATAH_JAM` (bawaan 24).

### Panel jatah & hitung mundur reset

Panel **"Jatah saya"** bisa dibuka dari tombol jatah di header chat. Tombol
itu **selalu tampil** — juga untuk tamu dan saat data belum termuat — supaya
panel tidak pernah "hilang" bagi pengguna.

Di dalam panel ada **hitung mundur reset** dalam format `jam:menit:detik`
(mis. `23:59:52`) yang **berdetak setiap detik**. Cara kerjanya:

- Server mengirim waktu pulih **absolut** (`akun.reset.pada`, epoch detik).
- Browser menghitung selisihnya sendiri tiap detik, jadi hitung mundur tetap
  real time **tanpa** menambah permintaan ke server (hemat kuota).
- Saat hitung mundur mencapai nol, panel mengambil data terbaru sekali
  sehingga jatah yang baru pulih langsung terlihat.
- Angka juga disegarkan saat tab kembali aktif (pindah tab → kembali).

### Bahasa: tenang, seperti uang bekal

Jatah dibahas seperti **bekal** yang cukup untuk 24 jam ke depan, bukan
seperti peringatan. Panduannya:

- Tidak ada kata yang menakut-nakuti ("segera habis", "hati-hati",
  "kritis", "jangan"). Warna peringatan hanya muncul bila benar-benar
  hampir habis, dan kalimatnya tetap menenangkan.
- Kata "pulih" diganti **"diperbarui"**, supaya terasa seperti bekal yang
  diisi ulang, bukan hukuman yang berakhir.
- Saat jatah habis: "Jatah Anda sudah terpakai semua. Bisa chat lagi dalam
  …" — plus pengingat bahwa percakapan lama tetap bisa dibaca.

### Animasi "berpikir" saat AI bekerja

Jawaban panjang atau riset web bisa memakan puluhan detik. Selama itu UI
menampilkan indikator berbentuk kotak kecil di area chat, plus versi
ringkas di bawah kotak pesan:

```
┌─────────────────────────────────────────────┐
│ • • •   Menelusuri...                10 dtk │
│         Mencari di web · Masih bekerja…     │
└─────────────────────────────────────────────┘
```

- **Tiga titik** berdenyut bergantian (CSS `berpikirDenyut`), labelnya
  berkilau lembut — menandakan aplikasi masih hidup, bukan macet.
- **Label jujur mengikuti tahap nyata**: `Berpikir` → `Menelusuri`
  (saat riset web) → `Menyusun` (saat teks mulai mengalir).
- **Penghitung detik** muncul setelah 3 detik: bukti proses berjalan.
  Tidak ada progress bar yang mengarang persentase.
- **Kalimat penenang** muncul bertahap saat menunggu lama (8, 20, 40, 75
  detik) — mis. "Masih bekerja, terima kasih sudah menunggu."
- Animasi **hilang sendiri** begitu jawaban mulai mengalir.
- Menghormati `prefers-reduced-motion`: pengguna yang mematikan animasi
  tetap melihat titik statis.

Tahapnya diatur dari `generationPhase` di `App.jsx` (`thinking`,
`research`, `writing`), jadi label tidak pernah menampilkan proses yang
tidak benar-benar terjadi.

**Kapan indikator tampil?** Selama balon asisten terakhir belum berisi
teks untuk permintaan yang sedang berjalan. Ada dua bug yang pernah terjadi
di sini dan keduanya sudah ditutup oleh uji regresi:

1. Kondisi memakai `messages.some((m) => m.id === streamingId)`, padahal
   `streamingId` bisa masih menyimpan ID jawaban lama → indikator tidak
   pernah muncul.
2. Saat mengirim pesan kedua, balon asisten terakhir adalah jawaban
   pertama yang sudah berisi → dianggap "sudah selesai" sehingga layar
   terlihat kosong. Perbaikannya: bandingkan **urutan** — balon asisten
   terakhir harus berada setelah pesan pengguna terakhir.
3. Percakapan masih kosong (pengguna pertama kali) juga menampilkan
   indikator, karena pesan pengguna belum ikut dirender pada detik-detik
   awal.

### Konfirmasi sebelum keluar

Klik **Keluar** (dari header chat, menu akun di sidebar, atau Pengaturan →
Akun) tidak langsung mengeluarkan pengguna. Muncul dialog:

> **Keluar dari akun?**
> Percakapan Anda **tetap tersimpan** dan akan muncul lagi saat Anda masuk
> dengan akun yang sama.
> Setelah keluar Anda memakai mode tamu: riwayat tidak tersimpan dan jatah
> pesan lebih sedikit.
>
> [Batal] [Ya, keluar]

"Membatalkan" bisa lewat tombol **Batal**, tombol silang, klik latar, atau
**Esc** — pengguna tetap masuk.

### Pengaturan

Tujuh tab, semua tersimpan otomatis di perangkat:

| Tab | Isi |
|---|---|
| **Umum** | Tema (terang/gelap/sistem), bahasa menu, ukuran font, nama panggilan |
| **Personalisasi** | Instruksi khusus, gaya jawaban, nada, **bahasa jawaban AI**, **panjang jawaban** |
| **Percakapan** | Status akun, simpan riwayat, **kirim dengan Enter**, **gulir otomatis**, **tampilkan jam pesan**, **konfirmasi sebelum menghapus**, ekspor, hapus semua |
| **Akun** | Status login, panel jatah, penjelasan privasi, tombol keluar |
| **Lanjutan** | Pilihan model, temperature, panjang maksimum jawaban, kembalikan setelan awal |
| **Pintasan** | Daftar pintasan keyboard |
| **Tentang** | Versi dan keterangan singkat |

### Mengapa hanya jumlah pesan yang membatasi?

Panjang jawaban AI sangat bervariasi: jawaban singkat ~100 token,
jawaban panjang ~3.000 token. Bila token dijadikan pembatas, pengguna
yang bertanya hal rumit akan kehabisan jatah jauh lebih cepat padahal
sama-sama satu pesan. Jumlah pesan lebih adil dan lebih mudah dipahami.

Token tetap dicatat (diambil dari **angka resmi penyedia**, bukan
perkiraan) dan ditampilkan di panel supaya pengguna tahu pemakaiannya.

### Apa yang terjadi saat jatah habis?

- Pesan ditolak dengan penjelasan jelas: berapa lama lagi pulih.
- **Akun lain tidak terpengaruh** — masing-masing punya jatah sendiri.
- Riwayat percakapan lama **tetap bisa dibaca**.
- Kuota penyedia tidak terpakai oleh permintaan yang ditolak.

### Bila penyimpanan bermasalah

Chat **tidak pernah** diblokir karena penyimpanan mati. Bila angka
pemakaian tidak bisa dibaca, server memilih meloloskan chat — lebih baik
kehilangan penegakan jatah sesaat daripada mematikan situs bagi semua
orang. Jatah kembali berlaku otomatis saat penyimpanan pulih.

---

## Tentang penyimpanan riwayat (Redis)

| Hal | Nilai |
|---|---|
| Maksimal percakapan per akun | 200 sesi (yang terlama otomatis dibuang) |
| Maksimal pesan per percakapan | 400 pesan |
| Ukuran maksimal per percakapan | ~900 KB |
| Umur data | 1 tahun sejak terakhir disentuh |

Kuota gratis Upstash: **10.000 perintah/hari**, **500.000/bulan**,
**256 MB**. Reset harian 00:00 UTC, bulanan tiap tanggal 1.

Bila kuota habis: chat tetap jalan, riwayat berhenti ke server, salinan
perangkat dipakai, dan sidebar memberi tahu dengan jujur.


---

## Langkah 1 — Buat database gratis di Upstash

1. Buka <https://upstash.com> lalu daftar (bisa pakai akun Google).
2. Pilih **Redis** → **Create Database**.
3. Isi:
   - **Name**: `gungdev-riwayat` (bebas)
   - **Type**: Regional
   - **Region**: pilih yang paling dekat, mis. `Singapore`
   - **TLS**: aktifkan (bawaan)
4. Setelah dibuat, buka tab **REST API** dan salin dua nilai:
   - `UPSTASH_REDIS_REST_URL`
   - `UPSTASH_REDIS_REST_TOKEN`

> Kedua nilai ini **rahasia**. Jangan ditempel di chat, jangan di-commit ke
> GitHub. Cukup dipasang di Vercel.

Kuota gratis: **500.000 perintah/bulan** (10.000/hari). Satu percakapan
memakai sekitar 5 perintah, jadi kira-kira **2.000 pesan/hari**.

Bila kuota habis: chat **tetap jalan**, riwayat berhenti tersimpan ke server,
dan salinan di perangkat tetap dipakai. Tidak ada data yang hilang.

---

## Langkah 2 — Pasang tiga Environment Variable di Vercel

Buka project backend **`gungdev-chatbot-rq5l`** →
**Settings** → **Environment Variables**, lalu tambahkan:

| Nama | Nilai | Type |
|---|---|---|
| `UPSTASH_REDIS_REST_URL` | URL dari Upstash | **Plain Text** |
| `UPSTASH_REDIS_REST_TOKEN` | Token dari Upstash | **Plain Text** |
| `GOOGLE_CLIENT_ID` | `521751493364-ffh8r1urf1aqvac0mbgop034gi2igmq0.apps.googleusercontent.com` | **Plain Text** |

### Kenapa harus "Plain Text"?

Tipe **Sensitive** tidak bisa dibaca saat proses build/debug, sehingga nilainya
bisa tidak sampai ke fungsi serverless. Untuk tiga nilai ini, **Plain Text**
lebih aman dari kesalahan konfigurasi.

`GOOGLE_CLIENT_ID` bukan rahasia — nilai ini memang terlihat di browser setiap
situs yang memakai login Google. Server memerlukannya untuk memastikan token
benar milik situs ini, bukan situs lain.

Setelah menambah ketiganya: **Deployments → Redeploy** (tanpa ubah kode).

---

## Cara memastikan berhasil

1. Buka situs, login dengan Google.
2. Kirim satu pesan.
3. Buka situs di **perangkat lain** (HP/laptop), login dengan akun **yang sama**.
4. Percakapan tadi harus muncul di sidebar.
5. Buka panel Usage → harus ada baris **"Pemakaian saya"**.

Bila belum muncul, buka panel Usage dan lihat pesan di sidebar:

| Pesan di sidebar | Artinya |
|---|---|
| *(tidak ada)* | Normal, riwayat tersimpan di server |
| Riwayat sementara hanya di perangkat ini | Env Upstash belum terbaca / kuota habis |
| Masuk ulang untuk menyinkronkan riwayat | Token Google tidak terbaca (coba login ulang) |

---

## Yang perlu diketahui (jujur)

- **Riwayat tamu tetap tidak disimpan** di mana pun, dan tamu dibatasi 3
  pesan/hari. Ini tidak berubah.
- **Gambar & file asli tidak disimpan** di server — hanya nama dan teksnya,
  sama seperti sebelumnya.
- **Pengaturan** (tema, model, nama panggilan) tetap per perangkat, bukan per
  akun. Ini disengaja: pilihan model di laptop belum tentu cocok di HP.
- Saklar **"Simpan riwayat"** tetap bisa dimatikan kapan saja. Saat mati,
  tidak ada yang dikirim ke server — termasuk saat tab ditutup.

---

## Berkas terkait

| Berkas | Isi |
|---|---|
| `backend/penyimpanan.py` | Penyimpanan riwayat di Upstash (per akun, per sesi) |
| `backend/identitas.py` | Verifikasi ID token Google ke `oauth2.googleapis.com` |
| `backend/usage.py` | Pencatatan usage + **jatah bergulir per akun** |
| `backend/main.py` | Endpoint `/api/sessions`, penegakan jatah di `/chat` |
| `frontend/src/lib/riwayat.js` | Semua permintaan riwayat + token |
| `frontend/src/hooks/useSessions.js` | Server sebagai sumber kebenaran, perangkat sebagai cadangan |
| `frontend/src/hooks/useSettings.js` | Semua preferensi pengguna (tema, bahasa, perilaku chat) |
| `frontend/src/components/Settings.jsx` | Halaman Pengaturan 7 tab |
| `frontend/src/components/Berpikir.jsx` | Animasi "berpikir" (titik + label tahap) |
| `frontend/src/components/UsagePanel.jsx` | Panel pemakaian + jatah akun |
| `frontend/src/components/Logo.jsx` | Lambang rubah (sidebar, avatar jawaban, layar kosong, Tentang) |
| `frontend/_buat_ikon.py` | Membuat semua ukuran logo/ikon dari `public/White-Chested Fox Logo.png` |
| `frontend/index.html` | Pemasangan favicon, apple-touch-icon, manifest, pratinjau tautan |

## Logo & ikon situs

Logo yang dipakai adalah berkas milik pemilik situs:
`frontend/public/White-Chested Fox Logo.png` (1448×1086, rubah oranye
dengan garis hampir hitam di latar putih).

**Bentuknya tidak digambar ulang.** Semua ukuran dibuat dengan memotong
gambar aslinya (`frontend/_buat_ikon.py`), supaya garis rubahnya persis
seperti aslinya. Percobaan membuat ulang sebagai vektor (SVG) sempat
dilakukan dan **dibuang**: hasil vektorisasi otomatis tidak setia pada
garis aslinya, sementara gambar tangan menghasilkan bentuk yang berbeda
dari logo pemilik situs.

| Berkas | Ukuran | Dipakai di |
|---|---|---|
| `logo-512.png` | 512px, latar transparan | Sumber logo untuk layar beresolusi tinggi |
| `logo-192.png` | 192px, latar transparan | Sidebar, avatar jawaban, layar kosong, Tentang |
| `icon-192.png` | 192px, ubin gelap membulat | Favicon tab browser |
| `icon-512.png` | 512px, ubin gelap membulat | Manifest (dipasang ke layar utama) |
| `icon-maskable-512.png` | 512px, latar penuh | Android (ikon dipotong sesuai bentuk launcher) |
| `apple-touch-icon.png` | 180px, persegi tanpa transparan | iOS/iPadOS (iOS membulatkan sendiri) |
| `og-image.png` | 1200×630 | Pratinjau saat tautan dibagikan |

Bila logo sumber diganti, cukup jalankan sekali dari folder `frontend`:

```
python _buat_ikon.py
```

lalu `git add -A`, commit, push. Tidak ada yang perlu diubah di kode.

**Kenapa logo selalu diberi bidang terang.** Sebagian garis logo hampir
hitam. Di tema gelap, garis itu akan menyatu dengan latar bila ditempel
langsung. Karena itu di tempat kecil (sidebar, avatar) logo diletakkan di
atas bidang putih keabu-abuan bergaris tepi tipis — terlihat sama jelas
di tema terang maupun gelap.

**Posisi logo saat ini:**

| Tempat | Ukuran |
|---|---|
| Sidebar, kiri atas | kotak 34px, logo 26px |
| Avatar setiap jawaban AI | kotak 30px, logo 24px |
| Layar kosong (atas sapaan) | kotak 72px, logo 64px |
| Pengaturan → Tentang | kotak 60px, logo 52px |

Ukuran gambar dikunci (`object-fit: contain`) agar tidak gepeng, karena
bentuk logonya tinggi dan sempit.


## Failover antar penyedia (Gemini & NVIDIA sebagai cadangan)

### Masalahnya

Setiap penyedia gratis punya batas harian. Groq membatasi **200.000
token per hari per model**, OpenRouter `:free` hanya **50 request/hari**.
Sebelumnya, begitu salah satu penyedia habis kuota, **seluruh situs**
berhenti melayani — padahal penyedia lain masih punya sisa kuota. Pengguna
melihat pesan error, padahal masalahnya hanya di satu jalur.

### Solusinya

Google Gemini ditambahkan sebagai **jalur ketiga yang gratis** (tanpa kartu
kredit, konteks 1 juta token), lalu NVIDIA NIM sebagai **jalur keempat**.
Permintaan otomatis dialihkan ke penyedia lain bila penyedia utama
kehabisan kuota.

Urutan percobaan:

| Kondisi | Urutan |
|---|---|
| Pengguna memilih model Groq | Groq → Gemini → OpenRouter → NVIDIA |
| Pengguna memilih model Gemini | Gemini → Groq → OpenRouter → NVIDIA |
| Pengguna memilih model `:free` OpenRouter | OpenRouter → Groq → Gemini → NVIDIA |
| Pengguna memilih model NVIDIA | NVIDIA → Groq → Gemini → OpenRouter |

Penyedia pilihan pengguna **selalu dicoba lebih dulu**, jadi pilihannya
tetap dihormati. Penyedia lain hanya menjadi penyelamat. Bila kunci sebuah
penyedia kosong, penyedia itu otomatis keluar dari urutan — tidak ada
permintaan yang dikirim ke tempat tanpa kunci.

### Kapan failover terjadi (dan kapan TIDAK)

Failover **hanya** pada status yang berarti kuota habis:

| Status | Arti | Dialihkan? |
|---|---|---|
| `429` | kuota/rate limit habis | ✅ ya |
| `402` | kredit/tagihan habis | ✅ ya |
| `401` / `403` | kunci salah atau tidak berhak | ❌ tidak |
| `500` | penyedia sedang bermasalah | ❌ tidak |

Alasannya: `401`/`403` adalah **kesalahan konfigurasi**, bukan kuota.
Kalau dialihkan, kunci yang salah akan tersembunyi dan kita tidak pernah
tahu ada yang perlu diperbaiki. Error seperti ini diteruskan apa adanya.

### Streaming: tidak pindah setelah teks terkirim

Di `/chat/stream`, failover hanya dilakukan **sebelum potongan pertama
dikirim** ke pengguna. Setelah satu huruf sampai di layar, berpindah
penyedia akan membuat jawaban **terulang dari awal** dan terasa rusak.
Karena itu, bila koneksi putus di tengah jawaban, pengguna mendapat pesan
error yang wajar — bukan jawaban kedua yang menimpa jawaban pertama.

### Cadangan model di dalam satu penyedia

Selain failover antar penyedia, tiap penyedia juga punya cadangan model.
Bila sebuah model ditutup penyedianya (HTTP `404`, umumnya karena model
berubah statusnya), model berikutnya dicoba otomatis:

```
Gemini : gemini-3.5-flash-lite → gemini-4-hydrogen → gemini-4-argon
         → gemini-3.6-flash → gemini-3.1-flash-lite
Groq   : lihat _MODEL_GROQ_CADANGAN di main.py
```

Bila permintaan berisi **gambar**, cadangan model dinonaktifkan — berganti
ke model yang tidak bisa membaca gambar hanya menghasilkan error `400` yang
membingungkan.

### Model mati sengaja tidak dipakai

Google mematikan model lama secara berkala. Per dokumentasi resmi
(`ai.google.dev/gemini-api/docs/deprecations`):

| Model | Status |
|---|---|
| `gemini-2.0-flash` | **dimatikan 1 Juni 2026** |
| `gemini-2.0-flash-lite` | **dimatikan 1 Juni 2026** |
| `gemini-2.5-flash` | deprecated; 1 Des 2026 dialihkan ke `gemini-3.5-flash-lite` |
| `gemini-2.5-flash-lite` | hanya untuk pengguna lama |

Karena itu daftar model di kode memakai generasi **3.5 ke atas**. Memasukkan
model yang sudah mati hanya memperlambat setiap permintaan: model itu pasti
gagal lebih dulu sebelum cadangan berikutnya dicoba.

### Memeriksa model mana yang hidup untuk key Anda

Dokumentasi tidak menjamin sebuah model bisa dipakai dengan key gratis —
Google membatasi sebagian model untuk akun lama. Untuk melihat kenyataannya:

```powershell
cd chatbot-saya/backend
$env:GEMINI_API_KEY="AIza..."
python uji_model_gemini.py
```

Skrip itu menguji setiap model (teks, streaming, gambar), lalu mencetak
daftar model yang lolos beserta kecepatannya — lengkap dengan usulan isi
`GEMINI_MODELS`. Key hanya dibaca dari environment sesi, tidak disimpan.

### Mengaktifkan

Cukup pasang **satu** Environment Variable di Vercel:

```
GEMINI_API_KEY = (ambil gratis di https://aistudio.google.com/apikey)
```

Bila variabel ini **kosong**, Gemini otomatis tidak dipakai dan situs
kembali ke perilaku lama (Groq + OpenRouter saja). Tidak ada yang rusak —
hanya tidak ada jalur cadangan.

Untuk memeriksa apakah cadangan sudah aktif, buka `/capabilities` dan
lihat field `cadangan_aktif` (`true` = siap dipakai). Field ini **tidak**
ditampilkan di UI — nama penyedia tidak pernah muncul ke pengguna.

## Penyedia keempat: NVIDIA NIM

Cukup pasang **satu** Environment Variable tambahan di Vercel:

```
NVIDIA_API_KEY = (ambil gratis di https://build.nvidia.com/settings/api-keys)
```

Butuh akun NVIDIA Developer Program (gratis, tanpa kartu kredit). Key
berbentuk `nvapi-...` dan **hanya ditampilkan sekali** saat dibuat.

Sebelum dipasang ke Vercel, periksa dulu di komputer sendiri:

```powershell
cd chatbot-saya\backend
$env:NVIDIA_API_KEY="nvapi-..."
python cek_key.py nvidia
```

Muncul `OK` berarti key hidup. Muncul `GAGAL : HTTP 401` berarti salah
salin. Skrip ini memanggil NVIDIA langsung dan **tidak mencetak key utuh**
(hanya panjang dan 6 huruf awal), jadi aman bila layar Anda terlihat orang
lain atau Anda bertanya di forum.

Endpoint `https://integrate.api.nvidia.com/v1` kompatibel OpenAI, jadi
format pesan, streaming, dan gambar sama persis dengan penyedia lain —
**tidak ada kontrak API yang berubah**. Bila variabel ini kosong, seluruh
bagian NVIDIA dilewati dan model NVIDIA otomatis dialihkan ke penyedia
lain (pengguna melihat chat tetap berjalan, bukan error).

### Model tambahan yang dibuka

Model NVIDIA berubah cukup sering: NVIDIA **mematikan model lama tanpa
pemberitahuan panjang**, dibalas `HTTP 410 "end of life"`. Saat daftar ini
pertama dibuat, kelima model yang dipakai ternyata sudah mati
(`openai/gpt-oss-120b`, `openai/gpt-oss-20b`,
`deepseek-ai/deepseek-v4.1-flash`, `moonshotai/kimi-2.5`, `zai-org/glm-5`).

Sekarang daftar diambil dari `GET https://integrate.api.nvidia.com/v1/models`
(bisa dilihat tanpa key) lalu diuji satu per satu: `403`/`401` = hidup,
`410` = mati, `404` = bukan model chat. Hasil per 27 Nov 2026 — 8 model,
semuanya hidup:

| Id model | Keterangan |
|---|---|
| `nvidia/nemotron-3.5-lightning-30b-a3b` | default, cepat & ringan |
| `nvidia/nemotron-3-ultra-550b-a55b` | paling kuat, paling lambat |
| `nvidia/nemotron-3.5-bolt-e4b` | sangat cepat |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | penalaran, bisa gambar |
| `nvidia/nemotron-3.5-super-vl-120b-a12b` | bisa gambar & dokumen |
| `moonshotai/kimi-k3.1-pro` | konteks sangat panjang |
| `z-ai/glm-5.3-flash` | cepat untuk analisis |
| `minimaxai/minimax-m3.1-flash` | ringan & responsif |

Bila suatu saat ada yang dibalas `410`, server **otomatis melewatinya ke
model cadangan** — pengguna tidak melihat error. Untuk memeriksa ulang
daftar yang masih hidup: `python cek_key.py nvidia`.

### Mengapa id model dijaga unik

NVIDIA dulu punya model bernama **persis** `openai/gpt-oss-120b` — sama
dengan id Groq. Kalau dimasukkan apa adanya, router akan menganggap model
itu milik NVIDIA, padahal selama ini dilayani Groq: pengguna GPT-OSS 120B
diam-diam pindah penyedia, kuota Groq tidak terpakai, dan trial credit
NVIDIA ikut terbakar. Model itu sekarang sudah mati dan tidak dipakai lagi,
tetapi aturannya tetap: **setiap id harus menunjuk tepat satu penyedia**
(dijaga `uji_unik_model.py`). Bila nanti ada id yang bentrok, beri awalan
`nvidia/` di `NVIDIA_MODELS` lalu petakan di `_NVIDIA_NAMA_ASLI`.

### Jujur: NVIDIA TIDAK menaikkan jatah harian

Ini penting agar tidak ada harapan yang keliru.

| Penyedia | Bentuk gratisnya | Menambah jatah? |
|---|---|---|
| Groq | kuota **harian tetap** per model (1.000 req, 200.000 token) | ✅ ya |
| Gemini | kuota harian per project Google | ✅ ya |
| OpenRouter `:free` | 50 request/hari | ✅ ya (kecil) |
| **NVIDIA NIM** | **trial credit** ±1.000 panggilan, berlaku ±90 hari | ❌ **tidak** |

Kredit NVIDIA terbatas dan bisa habis. Kalau dihitung sebagai kapasitas
harian, jatah per akun akan naik berdasarkan kuota yang bisa lenyap tanpa
peringatan — dan begitu kredit habis, semua pengunjung kehilangan jatah itu
sekaligus. Karena itu di `usage.py` ada `trial_nvidia_dihitung: 0` dan
jatah **tidak** dihitung dari NVIDIA. NVIDIA dipakai sebagai **pilihan
model tambahan** dan **jalur cadangan keempat**, bukan sebagai dasar
menaikkan jatah. (Kenaikan 48 → 52 dahulu berasal dari bantalan yang
diperkecil setelah pemakaian nyata diperiksa, bukan dari NVIDIA. Kenaikan
52 → 60 berasal dari **Cloudflare Workers AI**, yang BERBEDA dari NVIDIA
karena kuotanya harian tetap dan reset setiap hari — lihat bagian
"Cloudflare Workers AI" di bawah.)

### Penyedia yang TIDAK dipakai (dan alasannya)

| Penyedia | Alasan tidak dipakai |
|---|---|
| Cerebras | tanpa free tier; hanya $5 credit 30 hari |
| Mistral | dokumentasi resmi: Free mode **tidak** termasuk akses API |
| GitHub Models | layanan ditutup 30 Juli 2026 |
| Cloudflare Workers AI | 10.000 Neuron/hari terlalu kecil |
| SambaNova | 20 request/hari per model, perlu payment method |

Cara menaikkan jatah yang **benar-benar** bekerja: menambah project Google
Gemini (kuota dihitung per project, bukan per key), menambah model Groq
yang kuotanya terpisah, atau berlangganan Groq berbayar.

## Riset web: otomatis, untuk SEMUA model

### Masalahnya

Dulu riset web hanya dikerjakan bila pengguna menekan tombol globe, dan
hanya model yang punya tool `browser_search` milik Groq (keluarga
GPT-OSS) yang bisa melakukannya. Model lain — Claude, Gemini, DeepSeek,
Kimi, GLM — sama sekali tidak bisa riset. Kalau pengguna tetap meminta,
jawabannya dikarang dari ingatan, atau model menjawab jujur:

> "di percakapan ini aku belum bisa benar-benar membuka browser…"

Itu bukan halusinasi model. Memang tidak ada bahan yang diberikan
kepadanya.

### Akar masalah yang ditemukan lewat pengujian

Waktu sumber pencarian diuji satu per satu dari server, hasilnya:

| Sumber | Hasil uji nyata |
|---|---|
| **Bing** | **selalu kosong** — penanda `b_algo` muncul **0 kali** pada query apa pun, karena halaman hasilnya kini dirender JavaScript |
| DuckDuckGo (html & lite) | HTTP 202 + halaman kosong |
| Brave | HTTP 429 |
| Mojeek | halaman tanpa hasil |
| Startpage | tanpa hasil |
| Ecosia | HTTP 403 |
| Google | halaman persetujuan/captcha |
| SearXNG publik (`searx.be` dll.) | captcha / 429 / bukan JSON |
| Qwant | koneksi mati |
| Reddit | HTTP 403 |
| Wikipedia dengan UA tanpa kontak | HTTP 403 |

Jadi mesin "utama" yang dipakai selama ini memang tidak pernah memberi
hasil. Yang tersisa hanya artikel Wikipedia — sering salah topik. Itulah
sebab riset terasa tidak nyata.

### Sumber yang dipakai sekarang (semua terbukti bekerja)

1. **Yahoo Search** — mesin utama. Mengembalikan judul, URL asli, tanggal,
   dan cuplikan. Diuji pada berita, tutorial, harga, resep, dan jadwal:
   semuanya berhasil.
2. **Google News RSS** — berita terkini, XML bersih, tanpa API key.
3. **Marginalia** — mesin independen, cadangan saat Yahoo membatasi;
   bagus untuk tutorial/topik teknis.
4. **Wikipedia** (id + en) — pelengkap topik ensiklopedis. UA **wajib**
   memuat kontak (`admin@gungdev.ai`), kalau tidak ditolak 403.

Catatan teknis:

- Yahoo kadang membalas **HTTP 500** (pembatas laju sementara) walau query
  yang sama berhasil beberapa detik kemudian. Karena itu ada **3 percobaan
  ulang** dengan jeda 1,2 s dan 2,4 s. Marginalia 2 percobaan.
- Tautan Google News (`news.google.com/rss/articles/…`) tidak bisa dibaca
  sebagai artikel. Yang dipakai adalah alamat situs asli dari atribut
  `<source url>` dan tautan di dalam `<description>`; bila tidak ada,
  cuplikannya tetap dipakai sebagai bahan.

### Cara kerjanya sekarang

1. Pengguna mengirim pesan — **tanpa perlu menekan apa pun**.
2. Server menilai apakah pesan itu wajar diriset (`riset.perlu_riset`).
   Sapaan singkat seperti "halo" atau "terima kasih" dilewati agar tidak
   memperlambat.
3. Model merumuskan kata kunci pencarian dari permintaan pengguna.
4. Server mencari di empat sumber di atas **secara bersamaan**, membuang
   duplikat, lalu **membaca isi halaman** yang paling relevan.
5. Isi sumber dikirim ke model sebagai konteks, dengan aturan menjawab:
   sebut sumber `[1]`, `[2]`, dan **dilarang** berkata tidak bisa membuka
   web.
6. Model menulis jawaban berdasarkan sumber itu.

Karena seluruh proses ada di server, **semua model** — Groq, OpenRouter,
Gemini, NVIDIA — mendapat kualitas riset yang sama. Model **tidak lagi
diganti** hanya karena pengguna minta riset.

### Tombol globe sekarang: paksa riset LEBIH DALAM

Riset biasa sudah otomatis. Tombol globe (dan kata "riset", "research",
"teliti", "mendalam") memicu **riset berlapis**:

- putaran pertama: 6 sumber;
- model diminta menyebut bagian yang **belum terjawab**;
- putaran kedua mencari celah itu dengan kata kunci berbeda;
- hasil kedua putaran digabung, maksimal 8 sumber.

### Yang perlu diketahui (jujur)

- Tambahan waktu sekitar 5–12 detik pada pesan yang diriset. Ini harga
  dari membaca halaman sungguhan, bukan sekadar menempelkan judul.
- Sumber gratis bisa berubah perilaku kapan saja (seperti Bing). Bila
  suatu saat riset terasa menurun, jalankan `uji_riset.py` lebih dulu —
  uji itu mencari sumber nyata, bukan menebak.
- Bila seluruh sumber gagal, chat **tetap** berjalan: model menjawab dari
  pengetahuannya, dan prompt kejujuran membuatnya tidak mengaku-ngaku
  sudah menelusuri web.

### Kartu sumber di bawah jawaban (gaya ChatGPT)

Setiap jawaban riset menampilkan baris ringkas **"Sumber: contoh.com +2"**
di bawahnya. Bila diklik, terbuka daftar sumber bernomor — judul, nama
situs, dan tautan yang bisa diklik. Nomornya **sama** dengan penanda
`[1]`, `[2]` di dalam jawaban, jadi pengguna bisa mencocokkan kalimat
dengan sumbernya.

Yang dikirim ke browser hanya ringkasan sumber (nomor, judul, URL, situs,
tanggal) — **isi halaman tidak ikut dikirim**, karena sudah dipakai model
dan akan membuat respons membengkak. Ukurannya sekitar 60 byte per sumber.

Kartu sumber **ikut tersimpan bersama riwayat**, jadi tetap terlihat
setelah halaman dimuat ulang atau dibuka di perangkat lain.

Bila model lupa menulis penanda, kartu sumber tetap ditampilkan —
pengguna tetap tahu dari mana jawaban itu diambil.

### Membaca sampai halaman DETAIL (paket / post), bukan domain utama

Dulu hasil riset sering menyebut satu domain berulang kali, misalnya
"beetrip.co.id", padahal informasi paketnya ada di halaman
`/view/paket-honeymoon-4h3m-private-pool-villa`. Penyebabnya: `_teks_dari_html`
membuang SEMUA tag, termasuk `<a href>`, sehingga tautan halaman detail tidak
pernah terlihat dan tidak pernah dibuka.

Sekarang riset menelusuri tautan:

1. **Tingkat 1** — dari halaman yang sudah dibaca, kumpulkan tautan halaman
   dalam (`/view/`, `/tour/`, `/article/`, `/blog/`, `/produk/`, ...).
   Tautan sampah dibuang: css/js/gambar, `/tag/`, `/kontak`, `/login`,
   dan tautan ke domain lain.
2. **Tingkat 2** — bila halaman depan hanya memuat tautan kategori
   (umum di situs katalog seperti beetrip.co.id), halaman `/category/...`
   yang paling relevan dibuka dulu, lalu tautan paket di dalamnya diambil.
   Tingkat ini hanya dijalankan bila tingkat 1 belum menemukan apa pun,
   supaya riset tetap cepat.
3. Halaman detail yang terpilih **dibaca isinya** (maks 3 halaman) dan
   dijadikan **sumber tersendiri**, ditaruh di depan agar `[1]` menunjuk
   halaman paketnya.

Pemilihan tautan memakai TF-IDF sederhana: kata yang muncul di banyak tautan
(mis. "bali", "paket") berbobot kecil, kata pembeda (mis. "honeymoon")
berbobot besar. Tanpa ini, tautan yang kebetulan memuat kata umum selalu
menang dan halaman yang benar tidak pernah dibaca.

Judul kartu sumber diambil dari `<h1>` halaman (lalu `<title>`), bukan teks
anchor yang sering generik seperti "Selengkapnya" atau "Promo".

Aturan ke model juga dipertegas: bila sebuah bagian jawaban bersumber dari
halaman detail, nomor halaman detail itulah yang dipakai — bukan nomor
halaman depan situsnya.

Bukti nyata (diuji langsung ke beetrip.co.id):

```
[2] Paket Tour Bali Komplit 3H2M  -> beetrip.co.id/view/paket-tour-bali-komplit-3h2m
[3] Paket Tour Bali Hemat 3H2M    -> beetrip.co.id/view/paket-tour-bali-hemat-3h2m
[4] Paket Honeymoon 3H2M Private Pool Villa
                                  -> beetrip.co.id/view/paket-honeymoon-3h2m-private-pool-villa
```

Halaman `/view/paket-honeymoon-4h3m-private-pool-villa` terbaca 9.429
karakter berisi itinerari, harga, dan ulasan — bukan sekadar nama domain.

### Chip sumber sebaris (menempel di ujung kalimat)

Selain kartu di bawah, setiap kalimat yang memakai sumber diberi **chip
kecil berisi NAMA SITUS** yang bisa diklik, misalnya:

```
Harga awal: Rp200.000–Rp250.000/orang. [Batur Tours +1]
```

- Chip dibangun dari penanda `[1]`, `[2]` yang ditulis model, lalu diubah
  di sisi tampilan (`sisipkanSitasi` di `lib/text.js`, komponen
  `Sitasi.jsx`). Model **tidak** diminta menghafal format khusus, karena
  angka `[1]` adalah hal paling sederhana dan paling sering benar.
- **Penanda diganti DI TEMPAT, bukan dengan memecah jawaban.** Ini penting:
  versi pertama memecah jawaban menjadi beberapa blok Markdown, dan itu
  merusak daftar berbutir — satu butir yang penandanya di tengah terbelah,
  penanda bullet-nya hilang, dan `[2]` tampil sebagai angka mentah. Sekarang
  seluruh jawaban tetap dirender sebagai SATU dokumen, sehingga daftar,
  tabel, dan blok kode tetap rapi.
- Penanda diubah menjadi tautan `https://sumber.gungdev.invalid/sitasi/2`,
  lalu ditangkap renderer dan digambar sebagai chip. Domain `.invalid`
  dipakai karena skema buatan (`sitasi:2`) **dikosongkan** oleh
  react-markdown, sehingga chip gagal dikenali. URL ini tidak pernah dibuka.
- Nomor pertama menjadi nama chip; sisanya diringkas menjadi `+N`, dengan
  daftar judul lengkap saat kursor diarahkan (`title`).
- Chip membuka **situs asli** di tab baru (`target="_blank"`,
  `rel="noopener noreferrer"`).
- Yang dikenali: `[1]`, `[1][3]`, `[1, 3]`, dan rentang `[1-3]`. Nomor yang
  tidak ada di daftar sumber dibiarkan apa adanya agar informasi tidak
  hilang.
- Bila tidak ada sumber (chat biasa), penanda tidak diubah dan tidak ada
  chip yang muncul.

Agar chip duduk di ujung kalimat, aturan ke model diperketat: penanda
wajib ditulis **tepat sebelum titik** pada kalimat yang memakainya, dan
untuk jawaban berbentuk daftar setiap butir diberi penandanya sendiri.

### Jatah: satu permintaan riset = SATU pesan

Ini perlu ditegaskan karena riset memanggil model beberapa kali:

| Jenis pesan | Panggilan ke AI | Jatah terpakai |
|---|---|---|
| Sapaan singkat ("halo") | 1 | **1 pesan** |
| Pertanyaan biasa | 1 | **1 pesan** |
| Riset otomatis | 2 (rumuskan kata kunci + jawab) | **1 pesan** |
| Riset mendalam / tombol globe | 3 (dua kata kunci + jawab) | **1 pesan** |

Yang bertambah hanyalah **token** yang tercatat di panel Usage (karena
konteks sumber ikut dibaca model), **bukan jumlah pesan**. Pencatatan
jatah dilakukan sekali di akhir, setelah seluruh proses selesai.

## Sesi login yang bertahan (tidak minta masuk ulang)

### Masalahnya

Keluhan pemilik situs: setiap kali halaman dimuat ulang, ia diminta
"Sign in with Google" lagi — tidak seperti Claude/ChatGPT, yang sekali
masuk lalu tetap tersimpan sampai ia sendiri keluar.

### Akar masalah

ID token Google dulu **hanya disimpan di memori** (`let tokenAktif` di
`riwayat.js`). Memori hilang setiap halaman dimuat ulang, sedangkan
identitas login (`sub`, nama) disimpan 30 hari. Akibatnya setelah
refresh aplikasi terlihat seperti "setengah login": sidebar masih
menampilkan akun, tetapi token tidak ada, riwayat server tidak terbaca,
dan aplikasi berusaha memulihkan token lewat Google `prompt()` yang bisa
gagal (diblokir, FedCM, akun tunggal) → UI jatuh ke "riwayat hanya di
perangkat" dan muncul ajakan masuk.

### Perbaikannya

1. **Token disimpan di perangkat** (`gungdev:token-riwayat`), terpisah
   dari identitas akun. Saat halaman dibuka, token itu langsung dipakai —
   tanpa memanggil Google, tanpa jeda, tanpa ajakan masuk.
2. **Token kedaluwarsa diperbarui diam-diam.** ID token Google berumur
   ~1 jam. Bila `exp` sudah lewat, `pulihkanTokenRiwayat` meminta token
   segar lewat One Tap **tanpa popup**. Bila Google meminta interaksi,
   aplikasi tetap memakai salinan perangkat dan pengguna **tidak**
   dipaksa masuk.
3. **Hanya "Keluar" yang mengakhiri sesi.** `lupakanToken` menghapus
   token dari memori dan perangkat dan memasang penanda
   `dibatalkanPengguna`, sehingga pemulihan diam-diam (maupun jawaban
   Google yang datang terlambat) **tidak bisa menghidupkan sesi yang
   sudah diakhiri**. Penanda dilepas hanya saat pengguna menekan tombol
   login lagi (`setTokenRiwayat(token, { paksa: true })`).
4. **Tidak ada "verifying" berulang.** Bila token tersimpan masih
   berlaku, tidak ada satu pun permintaan ke Google saat memuat halaman.

Keamanan: server tetap memverifikasi tanda tangan token ke Google pada
setiap permintaan riwayat, jadi token palsu tidak bisa dipakai. Token
dihapus otomatis bila kedaluwarsa dan dihapus saat pengguna keluar.

### Kasus "sudah login tapi diperlakukan sebagai tamu"

Ini keluhan lanjutan yang ditemukan dari tangkapan layar pemilik situs:

> "Saya sudah login, profil akun tampil di kiri bawah. Saya refresh lalu
> buka lagi setelah beberapa jam. Kenapa muncul 'Signing you in…' seolah
> saya belum login? Selama itu saya jadi mode tamu, jatah saya jadi 3."

Akar masalahnya: ID token Google hanya berumur **~1 jam**. Kode lama
**menghapus** token yang sudah kedaluwarsa, sehingga aplikasi kehilangan
cara membedakan dua keadaan yang sangat berbeda:

| Keadaan | Perlakuan yang benar |
|---|---|
| Belum pernah login | Tamu — jatah 3 pesan |
| **Login, token basi** | **Tetap akun** — hanya token perlu diperbarui |

Karena tidak bisa membedakan, aplikasi jatuh ke mode tamu dan menampilkan
peringatan "riwayat sementara hanya di perangkat ini" padahal profilnya
masih tampil. Itu yang membingungkan dan membuat jatah terasa "hilang".

Perbaikannya:

1. **Token basi tidak lagi dibuang.** Ia disimpan sebagai
   `tokenKedaluwarsa` dan dikenali lewat `tokenPerluDiperbarui()`.
   Fungsinya: *bukti bahwa perangkat ini memang sudah login*. Ia tidak
   pernah dikirim ke server (server akan menolaknya), jadi keamanannya
   tidak berubah.
2. **Pemulihan token memakai bukti itu.** `pulihkanTokenRiwayat` tidak
   lagi menganggap "token kosong" sama dengan "belum pernah login".
3. **Status penyimpanan baru `'sesi'`, bukan `'perangkat'`.** Artinya
   "login, riwayat menyusul". Status ini **tidak ditampilkan** sebagai
   peringatan — pengguna memang sudah login dan tidak perlu berbuat apa
   pun.
4. **Pembaruan token dilakukan sebelum mengirim pesan.** Tanpa ini, satu
   pesan bisa tercatat sebagai tamu hanya karena token sedang basi.
5. **Percobaan ulang otomatis tiap 45 detik** sampai token berhasil
   diperbarui. Pengguna tidak perlu menekan apa pun.
6. `use_fedcm_for_prompt: true` pada Google Identity Services, supaya
   pembaruan token tidak menampilkan jendela pilih akun bila browser
   masih mengingat pilihan pengguna.

Yang tetap berlaku: **hanya "Keluar" yang mengakhiri sesi.** `lupakanToken`
menghapus token aktif *dan* `tokenKedaluwarsa`.

Diuji oleh `uji_sesi_kedaluwarsa.mjs` (27 pemeriksaan): token basi 2, 12,
dan 72 jam — profil tetap tampil, tidak ada ajakan masuk, tidak ada jatah
tamu, dan pemakaian tamu tidak bertambah saat mengirim pesan.

## Judul riwayat dari TOPIK percakapan

### Masalahnya

Judul riwayat dulu diambil dengan memotong ±48 karakter pertama prompt.
Prompt panjang menghasilkan judul seperti
"Halo, saya mau tanya dong soal paket honeymoon di Bali untuk…" — tidak
menggambarkan isi sesi dan sulit diingat. Claude/ChatGPT memberi judul
ringkas yang menyimpulkan topik.

### Cara kerjanya sekarang

Judul dibuat **dua tahap**:

1. **Langsung saat pesan pertama dikirim** — `makeTitle` (cadangan lokal
   di browser) membuang kata sapaan dan kata perintah ("halo", "tolong",
   "carikan", "bisa"), lalu menyusun kata topik. Sidebar tidak pernah
   kosong walau server lambat.
2. **Setelah jawaban pertama tiba** — `POST /judul` meminta model
   menuliskan 3–6 kata topik dari pertanyaan **dan** inti jawaban
   asisten. Inilah yang membuat judulnya seperti "Paket honeymoon Bali
   dan harga", bukan salinan kalimat pengguna.

`judul.py` menjaga kualitasnya:

| Aturan | Alasan |
|---|---|
| Maks 60 karakter, 3–6 kata | Judul harus bisa dipindai mata |
| Tanpa tanda kutip, emoji, titik akhir | Gaya judul riwayat yang tenang |
| Keluaran model >42 karakter / >8 kata DITOLAK | Model kadang menyalin kalimat pengguna apa adanya |
| Bila model gagal → `judul_lokal` | Endpoint tidak pernah gagal |
| Judul buatan pengguna (`titleLocked`) tidak disentuh | Pilihan pengguna selalu menang |

Endpoint ini **tidak memakai jatah chat**: biayanya beberapa puluh token
dan dipanggil sekali per sesi baru.

### Dua jebakan yang sempat membuat judul pintar tidak terpakai

1. **`/judul` belum dirutekan di `vercel.json`.** Endpoint sudah ada di
   `main.py`, tetapi Vercel tidak punya aturan `rewrites` untuk `/judul`,
   jadi permintaan tidak pernah sampai ke fungsi dan dijawab 404. Setiap
   rewrite baru di FastAPI **wajib** ditambahkan juga di `vercel.json`.
2. **Jawaban model terpotong di tengah penalaran.** Model `gpt-oss`
   (model penalar) menulis rencananya dulu — dalam bahasa Inggris — baru
   judulnya. Dengan `max_tokens: 32` jawabannya berhenti di
   `'We need to output a title ... So title: "Paket'`, lalu
   `bersihkan_judul` menolak seluruh keluaran itu. Sekarang:

   - jatah token judul dinaikkan ke 200 (tetap sangat murah), dan
     prompt melarang model menjelaskan rencananya;
   - `bersihkan_judul` **menyelamatkan** judul yang sudah disebut setelah
     kata "judul:"/"title:" — termasuk bila keluarannya terpotong;
   - narasi bahasa Inggris tetap **ditolak** agar judul memakai bahasa
     pengguna.

Respons `/judul` menyertakan `sumber`: `"model"` (judul dirumuskan model)
atau `"lokal"` (cadangan tanpa jaringan). Keduanya judul yang wajar.

Contoh nyata (diuji di browser): prompt 400+ karakter

> "Halo, selamat sore. Tolong bantu saya ya, saya sedang merencanakan
> liburan bulan madu ke Bali bulan depan bersama istri saya..."

menjadi judul:

> **Sedang merencanakan liburan bulan madu Bali**

## Menjalankan uji

```powershell
# Backend (tanpa perlu Upstash asli — Redis & Google dipalsukan)
cd chatbot-saya/backend
python uji_server_riwayat.py      # 55 pemeriksaan penyimpanan riwayat
python uji_jatah.py               # 78 pemeriksaan jatah, reset & kerahasiaan
python uji_routing_penyedia.py    # 14 pemeriksaan routing model -> penyedia
python uji_gemini.py              # 40 pemeriksaan Gemini & failover antar penyedia
python uji_nvidia.py              # 60 pemeriksaan penyedia keempat (NVIDIA NIM)
python uji_riset_detail.py        # 26 pemeriksaan riset menelusuri halaman paket/post
python uji_unik_model.py          # 6 pemeriksaan id model tidak bentrok antar penyedia
python uji_terpotong.py           # 29 pemeriksaan deteksi & sambung jawaban terpotong
python uji_riset.py               # 20 pemeriksaan riset web NYATA (mencari di internet sungguhan)
python uji_riset_semua_model.py   # 80 pemeriksaan: semua model bisa riset, model tidak diganti
python uji_model_gemini.py        # cek model Gemini mana yang hidup untuk key Anda
python uji_model_baru.py          # cari model Gemini TAMBAHAN yang hidup (jujur, tanpa pengalihan)
python cek_key.py nvidia          # cek API key baru hidup atau tidak, sebelum ke Vercel
python cek_key.py gemini          # idem untuk Gemini
python server_uji.py              # jalankan server uji di port 8000
python uji_api.py                 # 25 pemeriksaan endpoint lama
python uji_jatah_api.py           # 44 pemeriksaan jatah/reset via HTTP
python uji_judul.py               # 31 pemeriksaan judul dari TOPIK (bukan potongan prompt)

# Frontend (butuh server_uji.py + npm run dev berjalan)
cd chatbot-saya/frontend
node uji_browser.mjs              # 18 pemeriksaan riwayat lintas "perangkat"
node uji_jatah_browser.mjs        # 23 pemeriksaan jatah/hitung mundur di UI
node uji_pengaturan_keluar.mjs    # 29 pemeriksaan konfirmasi keluar & pengaturan
node uji_berpikir.mjs             # 20 pemeriksaan animasi "berpikir"
node uji_alur_lengkap.mjs         # 26 pemeriksaan alur ujung-ke-ujung
node uji_menu_model.mjs           # 17 pemeriksaan menu model ringkas & rapi
node uji_sumber_ui.mjs            # 27 pemeriksaan kartu + chip sumber riset (gaya ChatGPT)
node uji_login_bertahan.mjs       # 22 pemeriksaan sesi login tetap masuk setelah refresh
node uji_sesi_kedaluwarsa.mjs     # 27 pemeriksaan: token basi TIDAK dianggap tamu
node uji_judul_riwayat.mjs        # 10 pemeriksaan judul riwayat = topik, bertahan setelah refresh
```

> **Penting:** `server_uji.py` menyimpan state di memori proses. Restart
> server sebelum menjalankan rangkaian uji agar hasil tidak tercemar sisa
> uji sebelumnya.
