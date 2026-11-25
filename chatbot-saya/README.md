# GungDev — Asisten AI 💬

Aplikasi chatbot AI premium bergaya **Claude.ai / ChatGPT**, siap dipakai banyak orang.

| Bagian | Teknologi | Hosting |
|---|---|---|
| **Frontend** | React 19 + Vite 8 | **Vercel** (gratis) |
| **Backend** | FastAPI (Python) | **Render** / Railway (gratis) |
| **Model AI** | Groq Cloud (produksi) atau Ollama (lokal) | API / komputer sendiri |

---

## 🏗 Arsitektur

```
Pengguna ──► Vercel (React) ──HTTPS──► Render (FastAPI) ──► Groq Cloud (LLM)
               frontend/                 backend/            gratis, ~280 tps

Saat development lokal:
Pengguna ──► localhost:5173 ──► localhost:8000 ──► Ollama lokal (deepseek-r1:7b)
```

Backend memilih provider otomatis:

| Kondisi | Provider |
|---|---|
| `GROQ_API_KEY` terisi | **Groq** (cloud, cepat) |
| `GROQ_API_KEY` kosong | **Ollama** (lokal, gratis offline) |
| `AI_PROVIDER=groq` / `ollama` | Dipaksa manual |

> **Mengapa bukan Ollama di server?** Model 7B butuh ~6–8 GB RAM dan GPU.
> Hosting gratis hanya memberi 512 MB–1 GB tanpa GPU, jadi Ollama tidak mungkin
> jalan di sana. Karena itu produksi memakai Groq, sementara Ollama tetap
> tersedia untuk development lokal.

---

## ✨ Fitur

### Tampilan & Desain
- **Design system** CSS variables: palet hangat terracotta `#D97757` di atas krem
  `#FAF9F5`, heading serif (Newsreader), body Inter.
- **Tema Terang / Gelap / Ikuti Sistem**, tersimpan di `localStorage`, tanpa
  kedipan warna saat load.
- **Responsif mobile-first**: sidebar jadi drawer + overlay di bawah 1024px.
- Radius besar, shadow berlapis, transisi 150–250ms, scrollbar tipis, fokus
  keyboard jelas, `prefers-reduced-motion` dihormati, target sentuh ≥44px.
- Ikon konsisten dari **lucide-react** (tanpa emoji sebagai ikon UI).

### Percakapan
- **Streaming token per token** (SSE) + animasi typing tiga titik.
- **Markdown penuh** (**bold**, *italic*, heading, list, tabel, blockquote, link).
- **Code block** dengan syntax highlighting, nama bahasa, tombol **Salin**.
- Blok `<think>...</think>` disembunyikan dalam panel **"Proses berpikir"**.
- Aksi pesan: **Salin, Regenerasi, Suka/Tidak suka** (AI); **Edit, Salin** (user).
- Tombol **Stop generating**, timestamp saat hover, tombol gulir ke bawah.

### Riwayat & Sesi
- **Satu sesi = satu item riwayat**, judul otomatis dari pesan pertama.
- Dikelompokkan: **Disematkan, Hari ini, Kemarin, 7 Hari Terakhir, Lebih Lama**.
- Menu `...`: Ganti nama, Sematkan, Ekspor (.md/.txt), Hapus (dengan konfirmasi).
- Pencarian, skeleton loading, persistensi `localStorage`.
- Ekspor semua riwayat ke **JSON** atau **Markdown**.

### Pengaturan (6 tab)
Umum · Personalisasi · Percakapan · **Lanjutan** (URL backend, model, temperature,
max token, system prompt) · Pintasan · Tentang.

### Pintasan Keyboard
| Pintasan | Fungsi |
|---|---|
| `Ctrl/⌘ + K` | Cari percakapan |
| `Ctrl/⌘ + Shift + O` | Percakapan baru |
| `Ctrl/⌘ + B` | Toggle sidebar |
| `Esc` | Tutup dialog |
| `Enter` / `Shift+Enter` | Kirim / baris baru |

---

## 📁 Struktur Folder

```
chatbot-saya/
├── frontend/                        # React + Vite  ->  Vercel
│   ├── vercel.json                  # konfigurasi deploy Vercel
│   ├── index.html                   # anti-flash tema, viewport, favicon
│   ├── .env.example                 # VITE_API_URL
│   ├── e2e.mjs                      # uji end-to-end (Playwright)
│   └── src/
│       ├── App.jsx / App.css / index.css / main.jsx
│       ├── components/              # ChatArea, Composer, EmptyState, Markdown,
│       │                            # Message, Sidebar, Settings, Modal, Toast, icons
│       ├── hooks/                   # useSessions, useSettings, useToasts
│       └── lib/                     # api, storage, text, theme
│
└── backend/                         # FastAPI  ->  Render / Railway
    ├── main.py                      # seluruh logika server (multi-provider)
    ├── requirements.txt
    ├── Dockerfile                   # untuk Render/Railway/Fly.io
    ├── render.yaml                  # blueprint deploy Render
    ├── run.bat                      # peluncur cepat Windows
    └── .env.example
```

---

## 🚀 Deploy (Ringkas)

### Langkah 1 — Ambil API key Groq (gratis)
1. Buka <https://console.groq.com/keys>
2. Login → **Create API Key** → salin (diawali `gsk_...`)
3. Simpan, akan dipakai di langkah 2

### Langkah 2 — Deploy Backend ke Render
1. Buka <https://dashboard.render.com> → **New** → **Web Service**
2. Hubungkan repo `gungdev-chatbot`
3. Isi:
   - **Root Directory**: `chatbot-saya/backend`
   - **Runtime**: **Docker** (otomatis terbaca dari `Dockerfile`)
   - **Instance Type**: **Free**
   - **Health Check Path**: `/health`
4. **Environment Variables**:
   | Key | Value |
   |---|---|
   | `AI_PROVIDER` | `groq` |
   | `GROQ_API_KEY` | `gsk_...` (dari langkah 1) |
   | `GROQ_MODEL` | `llama-3.3-70b-versatile` |
5. **Create Web Service** → tunggu build (~3 menit)
6. Salin URL backend, mis. `https://gungdev-api.onrender.com`
7. Tes: buka `https://gungdev-api.onrender.com/health` → harus muncul
   `{"status":"ok","provider":"groq","model":"..."}`

> Render free **tidur setelah 15 menit idle**. Permintaan pertama setelah tidur
> butuh ~30–60 detik untuk bangun. Ini normal.

### Langkah 3 — Deploy Frontend ke Vercel
1. Buka <https://vercel.com/new> → import repo `gungdev-chatbot`
2. Isi:
   - **Root Directory**: `chatbot-saya/frontend`
   - **Framework Preset**: `Vite` (terdeteksi otomatis)
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
3. **Environment Variables**:
   | Key | Value |
   |---|---|
   | `VITE_API_URL` | `https://gungdev-api.onrender.com` (URL langkah 2) |
4. **Deploy** → selesai, dapat URL `https://gungdev-chatbot.vercel.app`

> `VITE_API_URL` dibaca saat **build**. Kalau diubah, wajib **Redeploy**.

### Langkah 4 — Verifikasi
Buka URL Vercel, ketik pesan. Bila muncul error:
- **"Backend tidak terhubung"** → cek `VITE_API_URL` sudah benar & backend hidup
- **"API key Groq tidak valid"** → cek `GROQ_API_KEY` di Render
- **CORS error** → domain `*.vercel.app` sudah diizinkan otomatis; untuk domain
  sendiri tambahkan ke `ALLOWED_ORIGINS` di Render

---

## 💻 Menjalankan Lokal

### Backend
```bash
cd chatbot-saya/backend
run.bat                    # Windows (auto-install dependensi)
# atau:
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Tanpa `GROQ_API_KEY`, backend otomatis memakai **Ollama lokal**:
```bash
ollama pull deepseek-r1:7b
ollama serve
```

Ingin mencoba Groq di lokal? Isi `.env`:
```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

### Frontend
```bash
cd chatbot-saya/frontend
npm install
npm run dev          # http://localhost:5173
```

Buka **http://localhost:5173**. URL backend diatur di `.env`:
```env
VITE_API_URL=http://localhost:8000
```

---

## 🔌 API Backend

Kontrak lama tetap utuh.

### `GET /health`
```json
{ "status": "ok", "provider": "groq", "model": "llama-3.3-70b-versatile" }
```

### `POST /chat` — non-streaming
```json
// Request (field * wajib)
{
  "message": "Halo GungDev",           // *
  "history": [{ "role": "user", "content": "..." }],
  "system_prompt": "instruksi kustom", // opsional
  "temperature": 0.4,                  // opsional, 0.0–2.0
  "max_tokens": 2048                   // opsional, 16–8192
}

// Response
{ "reply": "Halo! Ada yang bisa saya bantu?" }
```

### `POST /chat/stream` — streaming SSE
Request sama. Response `text/event-stream`:
```
data: {"delta": "Halo"}
data: {"delta": "! Ada"}
data: {"done": true}
```
Bila gagal:
```
data: {"error": "Kuota gratis Groq tercapai. Tunggu sebentar lalu coba lagi."}
```

---

## ⚙️ Variabel Environment

### Backend
| Variabel | Default | Keterangan |
|---|---|---|
| `AI_PROVIDER` | otomatis | `groq` atau `ollama` |
| `GROQ_API_KEY` | — | API key dari console.groq.com |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Model Groq |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | Endpoint Groq |
| `OLLAMA_HOST` | `http://localhost:11434` | Alamat Ollama lokal |
| `OLLAMA_MODEL` | `deepseek-r1:7b` | Model Ollama |
| `ALLOWED_ORIGINS` | — | Domain tambahan, pisah koma |
| `TIMEOUT_GROQ` | `120` | Timeout detik |
| `TIMEOUT_OLLAMA` | `300` | Timeout detik |
| `PORT` | `8000` | Port (diisi otomatis oleh Render) |

### Frontend
| Variabel | Default | Keterangan |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | URL backend |

---

## 📌 Batas Kuota Gratis

| Layanan | Batas |
|---|---|
| **Groq** | Rate limit per menit/hari; cek di console.groq.com |
| **Render free** | 512 MB RAM, tidur setelah 15 menit idle |
| **Vercel Hobby** | 100 GB bandwidth/bulan |

Bila pengguna bertambah banyak, pertimbangkan:
- Upgrade Render ke Starter (~$7/bln) agar selalu bangun
- Upgrade Groq ke Developer plan
- Tambahkan rate-limit per IP di backend (`slowapi`)

---

## 🧪 Uji E2E (opsional)

```bash
cd chatbot-saya/frontend
npm install --no-save playwright
npx playwright install chromium
node e2e.mjs
```

---

## 🔧 Troubleshooting

**Port 8000 dipakai proses lain**
```powershell
Get-NetTCPConnection -State Listen -LocalPort 8000 |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

**Tidak ada nama model di UI?**
Disengaja — nama model hanya tampil di **Pengaturan → Lanjutan**.

**Riwayat hilang setelah ganti browser?**
Riwayat disimpan di `localStorage` per-browser, bukan di server. Gunakan
**Pengaturan → Percakapan → Ekspor** untuk mencadangkan.

---

## Lisensi

Proyek pribadi untuk pembelajaran. Bebas dimodifikasi.
