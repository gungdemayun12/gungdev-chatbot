# GungDev — Asisten AI 💬

Aplikasi chatbot AI premium bergaya **Claude.ai / ChatGPT**, berjalan sepenuhnya di
komputer sendiri. Terdiri dari dua bagian:

| Bagian | Teknologi | Fungsi |
|---|---|---|
| **Frontend** | React 19 + Vite 8 | Antarmuka chat premium (tema krem hangat + terracotta) |
| **Backend** | Python FastAPI | Meneruskan pertanyaan ke **Ollama lokal** (`http://localhost:11434`) |

> **Tanpa API Key, tanpa internet.** Semua proses berjalan lokal dengan model
> `deepseek-r1:7b` melalui Ollama.

---

## ✨ Fitur

### Tampilan & Desain
- **Design system** berbasis CSS variables: palet hangat ala Claude (terracotta
  `#D97757` di atas krem `#FAF9F5`), heading serif (Newsreader), body Inter.
- **Tema Terang / Gelap / Ikuti Sistem** — tersimpan di `localStorage`, tanpa
  kedipan warna saat load (skrip anti-flash di `index.html`).
- **Responsif mobile-first**: sidebar menjadi drawer dengan overlay gelap di
  bawah 1024px, tutup via tap overlay atau swipe ke kiri.
- Radius besar, shadow berlapis, transisi 150–250ms, scrollbar tipis,
  fokus keyboard jelas, `prefers-reduced-motion` dihormati, target sentuh ≥44px.
- Ikon konsisten dari **lucide-react** (tanpa emoji sebagai ikon UI).

### Percakapan
- **Streaming token per token** (SSE) + animasi typing tiga titik.
- **Markdown penuh** dirender rapi (**bold**, *italic*, heading, list, tabel,
  blockquote, link) — tidak ada lagi tanda `**` mentah.
- **Code block** dengan syntax highlighting, nama bahasa, dan tombol
  **Salin → "Tersalin ✓"**.
- Blok penalaran `<think>...</think>` (DeepSeek-R1) disembunyikan dalam panel
  lipat **"Proses berpikir"** (tertutup secara default).
- Aksi pesan: **Salin, Regenerasi, Suka/Tidak suka** (AI) dan **Edit, Salin**
  (pengguna). Tombol **Stop generating** saat AI menjawab.
- Timestamp halus saat hover, tombol **gulir ke bawah** mengambang.

### Riwayat & Sesi
- **Satu sesi = satu item riwayat**, judul otomatis dari pesan pertama
  (dipotong rapi dengan ellipsis).
- Dikelompokkan otomatis: **Disematkan, Hari ini, Kemarin, 7 Hari Terakhir,
  Lebih Lama**.
- Menu `...` per item: Ganti nama, Sematkan, Ekspor (.md / .txt), Hapus
  (dengan dialog konfirmasi).
- Pencarian riwayat, skeleton loading, penyimpanan persisten di `localStorage`.
- Ekspor seluruh riwayat ke **JSON** atau **Markdown**.

### Pengaturan (6 tab)
- **Umum** — tema, bahasa, ukuran font, nama panggilan
- **Personalisasi** — instruksi kustom, gaya jawaban (singkat/seimbang/detail),
  nada (santai/formal)
- **Percakapan** — simpan riwayat on/off, ekspor semua, hapus semua
- **Lanjutan** — URL backend, model, temperature, maksimum token, system prompt
- **Pintasan** — daftar keyboard shortcut
- **Tentang** — versi & info aplikasi

### Kualitas Jawaban
- **System prompt default** yang membuat GungDev ramah, akurat, jujur (tidak
  mengarang), dan langsung ke inti.
- **Temperature default 0.4** untuk jawaban faktual yang stabil.

### Pintasan Keyboard
| Pintasan | Fungsi |
|---|---|
| `Ctrl/⌘ + K` | Cari percakapan |
| `Ctrl/⌘ + Shift + O` | Percakapan baru |
| `Ctrl/⌘ + B` | Tampilkan / sembunyikan sidebar |
| `Esc` | Tutup dialog |
| `Enter` | Kirim pesan |
| `Shift + Enter` | Baris baru |

---

## 📁 Struktur Folder

```
chatbot-saya/
├── frontend/                      # React + Vite
│   ├── index.html                 # skrip anti-flash tema, meta viewport, favicon
│   ├── public/
│   │   └── favicon.svg
│   ├── e2e.mjs                    # uji end-to-end (Playwright, opsional)
│   ├── package.json
│   └── src/
│       ├── main.jsx
│       ├── App.jsx                # orkestrasi state, streaming, pintasan, ekspor
│       ├── App.css                # seluruh styling komponen + breakpoint
│       ├── index.css              # design tokens (terang/gelap), tipografi, reset
│       ├── components/
│       │   ├── ChatArea.jsx       # header, daftar pesan, error banner, composer
│       │   ├── Composer.jsx       # textarea auto-grow, kirim/stop, lampiran
│       │   ├── EmptyState.jsx     # sapaan serif + 4 kartu saran
│       │   ├── Markdown.jsx       # react-markdown + highlight.js + DOMPurify
│       │   ├── Message.jsx        # pesan user/AI, panel "Proses berpikir", aksi
│       │   ├── Sidebar.jsx        # riwayat terkelompok, pencarian, menu konteks
│       │   ├── Settings.jsx       # 6 tab pengaturan
│       │   ├── Modal.jsx          # dialog dasar (fokus terkunci, Esc)
│       │   ├── Toast.jsx          # notifikasi
│       │   └── icons.jsx          # re-export ikon lucide-react
│       ├── hooks/
│       │   ├── useSessions.js     # state sesi + persistensi localStorage
│       │   ├── useSettings.js     # preferensi + system prompt gabungan
│       │   └── useToasts.js
│       └── lib/
│           ├── api.js             # streamChat (SSE), sendChat, checkHealth
│           ├── storage.js         # pembungkus localStorage yang aman
│           ├── text.js            # splitThinking, makeTitle, groupSessions, ekspor
│           └── theme.js           # tema terang/gelap/sistem
└── backend/                       # Python FastAPI
    ├── main.py                    # seluruh logika server
    ├── requirements.txt
    ├── run.bat                    # peluncur cepat (Windows)
    └── .env.example
```

---

## 1. Prasyarat

1. **Ollama** terpasang dan berjalan — unduh di <https://ollama.com/download>.
2. **Model sudah diunduh**:
   ```bash
   ollama pull deepseek-r1:7b
   ```
3. Cek keduanya siap:
   ```bash
   ollama list                    # harus muncul deepseek-r1:7b
   curl http://localhost:11434/api/tags
   ```

---

## 2. Menjalankan Backend

```bash
cd chatbot-saya/backend

# Windows (paling mudah)
run.bat

# Atau manual
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend siap di **http://localhost:8000** — dokumentasi interaktif di
<http://localhost:8000/docs>.

---

## 3. Menjalankan Frontend

```bash
cd chatbot-saya/frontend
npm install
npm run dev
```

Buka **http://localhost:5173**.

### Library yang di-install

```bash
npm install react-markdown remark-gfm rehype-highlight highlight.js dompurify lucide-react
```

| Library | Kegunaan |
|---|---|
| `react-markdown` | Render Markdown pada jawaban AI |
| `remark-gfm` | Dukungan tabel, strikethrough, task list |
| `rehype-highlight` + `highlight.js` | Syntax highlighting code block |
| `dompurify` | Sanitasi HTML (anti-XSS) |
| `lucide-react` | Ikon UI yang konsisten |

### Build produksi

```bash
npm run build      # hasil di dist/
npm run preview    # pratinjau hasil build
```

---

## 4. API Backend

Kontrak lama **tetap utuh**, ditambah satu endpoint streaming.

### `POST /chat` — cara lama (non-streaming)

```json
// Request (field bertanda * wajib)
{
  "message": "Halo GungDev",          // *
  "history": [{ "role": "user", "content": "..." }],
  "system_prompt": "instruksi kustom", // opsional
  "temperature": 0.4,                  // opsional, 0.0–2.0
  "max_tokens": 2048                   // opsional, 16–8192
}

// Response
{ "reply": "Halo! Ada yang bisa saya bantu?" }
```

### `POST /chat/stream` — streaming (SSE)

Request sama persis dengan `/chat`. Response `text/event-stream`, satu objek
JSON per baris `data:`:

```
data: {"delta": "Halo"}
data: {"delta": "! Ada"}
data: {"done": true}
```

Jika terjadi masalah:

```
data: {"error": "Ollama tidak berjalan. Buka aplikasi Ollama lalu coba lagi."}
```

### `GET /health`

```json
{ "status": "ok" }
```

Dipakai frontend untuk indikator **Online/Offline** di header.

---

## 5. Catatan

- **Indikator status**: header hanya menampilkan titik hijau + "Online". Nama
  model dan teknologi tidak ditampilkan di UI utama, melainkan di
  **Pengaturan → Lanjutan**.
- **Riwayat** disimpan di `localStorage` browser (`gungdev:sessions`). Matikan
  lewat **Pengaturan → Percakapan → Simpan riwayat** bila tidak ingin menyimpan.
- **Error ramah**: bila backend mati, muncul banner jelas + tombol
  **"Coba lagi"** (bukan crash).
- **Port bentrok?** Hentikan proses yang menahan port 8000:
  ```powershell
  Get-NetTCPConnection -State Listen -LocalPort 8000 |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
  ```
- **Uji E2E (opsional)** — butuh Playwright:
  ```bash
  npm install --no-save playwright
  npx playwright install chromium
  node e2e.mjs
  ```

---

## 6. Lisensi

Proyek pribadi untuk pembelajaran. Bebas dimodifikasi sesuai kebutuhan.
