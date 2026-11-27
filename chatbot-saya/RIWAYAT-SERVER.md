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
| Semua pengunjung berbagi satu angka usage | Tiap akun punya **jatah 40 pesan/24 jam** sendiri |
| Tidak ada pembatas per akun | Satu akun habis jatah **tidak** memengaruhi akun lain |
| — | Bila server tak bisa dipakai, salinan perangkat dipakai otomatis |

Kontrak API lama **tidak berubah**: `/chat`, `/chat/stream`, `/health`,
`/capabilities` tetap sama persis.

---

## Jatah chat per akun

| Hal | Nilai |
|---|---|
| Jatah pesan per akun | **40 pesan per jendela 24 jam** |
| Saat layanan ramai | Sementara 8 pesan (otomatis, kembali normal sendiri) |
| Jatah tamu | 3 pesan/hari (per IP, tidak berubah) |
| Akun baru per hari | Maksimal 25 (agar 25 × 40 tidak melampaui kapasitas 400/hari) |
| Kapan jendela dimulai | **Saat pesan pertama akun itu** |
| Kapan reset | Saat jendela 24 jamnya berakhir — **berbeda tiap akun** |
| Token | **Dicatat & ditampilkan**, tetapi **tidak membatasi** |
| Yang dilihat pengguna | **Hanya jatahnya sendiri** — kapasitas layanan hanya untuk pemilik situs |

### Dari mana angka 40 berasal

Dua sumber kuota dipakai bergantian menurut model yang dipilih:

| Sumber | Batas request/hari | Batas token/hari |
|---|---|---|
| Sumber A (model `:free`) | 50 | tanpa batas |
| Sumber B (tiga model gratis) | 3 × 1.000 = 3.000 | 3 × 200.000 = 600.000 |

Kunci perubahannya: **batas Sumber B dihitung per model**, bukan per
sumber. Tiga model gratis yang dipakai punya jatah masing-masing, jadi
kapasitas gabungannya tiga kali lipat dari hitungan lama:

```
kendala request : 3.000 + 50          = 3.050 request/hari
kendala token   : 3 x 200.000 = 600.000 token/hari
                  600.000 / 1.500      = 400 pesan/hari  <- yang lebih dulu habis
                  400 / 10 akun aktif  = 40 pesan per akun
```

Angka 1.500 token/pesan adalah rata-rata nyata (pesan pendek ±700 token,
pesan panjang/riset ±3.000 token). Kendala yang menentukan adalah **token**,
bukan request — request masih sangat longgar (3.050 untuk 400 pesan).

Kenapa 40 dan bukan angka lain:

- **16** (hitungan lama) terlalu pesimis: hanya memakai satu model Sumber B.
- **80** aman hanya bila ≤ 5 akun aktif/hari; satu pengguna yang suka riset
  web memakai ±3.000 token/pesan (2× rata-rata), sehingga kuota bisa habis
  sebelum hari berakhir.
- **40** aman untuk ±10 akun aktif/hari dan masih menyisakan ruang untuk
  pesan panjang/riset.

Dua penjaga supaya kuota tidak habis di tengah hari:

1. **Jatah dipangkas otomatis** — bila sisa pesan situs < 15% dari kapasitas
   harian (400), akun mendapat 8 pesan/24 jam. Akun yang datang belakangan
   tetap kebagian.
2. **Batas akun baru per hari** — maksimal 25 akun baru. Tanpa ini, 25 akun
   baru x 40 pesan sehari sudah melampaui kapasitas 400 pesan/hari.

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
## Menjalankan uji

```powershell
# Backend (tanpa perlu Upstash asli — Redis & Google dipalsukan)
cd chatbot-saya/backend
python uji_server_riwayat.py      # 55 pemeriksaan penyimpanan riwayat
python uji_jatah.py               # 78 pemeriksaan jatah, reset & kerahasiaan
python server_uji.py              # jalankan server uji di port 8000
python uji_api.py                 # 25 pemeriksaan endpoint lama
python uji_jatah_api.py           # 44 pemeriksaan jatah/reset via HTTP

# Frontend (butuh server_uji.py + npm run dev berjalan)
cd chatbot-saya/frontend
node uji_browser.mjs              # 18 pemeriksaan riwayat lintas "perangkat"
node uji_jatah_browser.mjs        # 23 pemeriksaan jatah/hitung mundur di UI
node uji_pengaturan_keluar.mjs    # 29 pemeriksaan konfirmasi keluar & pengaturan
node uji_berpikir.mjs             # 20 pemeriksaan animasi "berpikir"
node uji_alur_lengkap.mjs         # 26 pemeriksaan alur ujung-ke-ujung
```

> **Penting:** `server_uji.py` menyimpan state di memori proses. Restart
> server sebelum menjalankan rangkaian uji agar hasil tidak tercemar sisa
> uji sebelumnya.
