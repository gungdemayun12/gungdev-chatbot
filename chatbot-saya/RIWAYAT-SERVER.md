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
| Semua pengunjung berbagi satu angka usage | Tiap akun punya **jatah 100 pesan/hari** sendiri |
| Tidak ada pembatas per akun | Satu akun habis jatah **tidak** memengaruhi akun lain |
| — | Bila server tak bisa dipakai, salinan perangkat dipakai otomatis |

Kontrak API lama **tidak berubah**: `/chat`, `/chat/stream`, `/health`,
`/capabilities` tetap sama persis.

---

## Jatah chat per akun (baru)

| Hal | Nilai |
|---|---|
| Jatah pesan per akun | **100 pesan per jendela 24 jam** |
| Jatah tamu | 3 pesan/hari (per IP, tidak berubah) |
| Kapan jendela dimulai | **Saat pesan pertama akun itu** |
| Kapan reset | Saat jendela 24 jamnya berakhir — **berbeda tiap akun** |
| Token | **Dicatat & ditampilkan**, tetapi **tidak membatasi** |
| Kuota bersama situs | 1.000 permintaan/hari (dari penyedia, dipakai bersama) |

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
| `frontend/src/components/UsagePanel.jsx` | Panel pemakaian + jatah akun |

## Menjalankan uji

```powershell
# Backend (tanpa perlu Upstash asli — Redis & Google dipalsukan)
cd chatbot-saya/backend
python uji_server_riwayat.py      # 54 pemeriksaan penyimpanan riwayat
python uji_jatah.py               # 51 pemeriksaan jatah & reset bergulir
python server_uji.py              # jalankan server uji di port 8000
python uji_api.py                 # 24 pemeriksaan endpoint lama
python uji_jatah_api.py           # 37 pemeriksaan jatah/reset via HTTP

# Frontend (butuh server_uji.py + npm run dev berjalan)
cd chatbot-saya/frontend
node uji_browser.mjs              # 16 pemeriksaan riwayat lintas "perangkat"
node uji_jatah_browser.mjs        # 13 pemeriksaan jatah/reset di UI
```

> **Penting:** `server_uji.py` menyimpan state di memori proses. Restart
> server sebelum menjalankan rangkaian uji agar hasil tidak tercemar sisa
> uji sebelumnya.
