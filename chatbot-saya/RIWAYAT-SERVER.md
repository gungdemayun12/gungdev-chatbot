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
| Semua pengunjung berbagi satu angka usage | Tiap akun punya angka **Pemakaian saya** |
| — | Bila server tak bisa dipakai, salinan perangkat dipakai otomatis |

Kontrak API lama **tidak berubah**: `/chat`, `/chat/stream`, `/health`,
`/capabilities` tetap sama persis.

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
| `backend/usage.py` | Pencatatan usage global + per akun |
| `backend/main.py` | Endpoint `/api/sessions` (GET/POST/sync/active/DELETE) |
| `frontend/src/lib/riwayat.js` | Semua permintaan riwayat + token |
| `frontend/src/hooks/useSessions.js` | Server sebagai sumber kebenaran, perangkat sebagai cadangan |

## Menjalankan uji

```powershell
# Backend (tanpa perlu Upstash asli — Redis & Google dipalsukan)
cd chatbot-saya/backend
python uji_server_riwayat.py      # 54 pemeriksaan
python server_uji.py              # jalankan server uji di port 8000
python uji_api.py                 # 24 pemeriksaan endpoint

# Frontend (butuh server_uji.py + npm run dev berjalan)
cd chatbot-saya/frontend
node uji_browser.mjs              # 16 pemeriksaan lintas "perangkat"
```
