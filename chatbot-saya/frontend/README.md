# GungDev — Frontend (React + Vite)

Antarmuka chat premium untuk asisten AI **GungDev**. Bagian ini hanya berisi
tampilan; seluruh pemrosesan AI ada di `../backend` (FastAPI + Ollama).

## Menjalankan lokal

```bash
npm install
npm run dev          # http://localhost:5173
```

Pastikan backend berjalan di `http://localhost:8000`:

```bash
cd ../backend
run.bat
```

## Perintah

| Perintah | Kegunaan |
|---|---|
| `npm run dev` | Server pengembangan (HMR) |
| `npm run build` | Build produksi ke `dist/` |
| `npm run preview` | Pratinjau hasil build |
| `npm run lint` | Periksa kode dengan ESLint |

## Konfigurasi backend

URL backend dibaca dari `VITE_API_URL` (lihat `.env.example`).
Tanpa variabel tersebut, aplikasi memakai `http://localhost:8000`.

```env
VITE_API_URL=http://localhost:8000
```

Nilai ini juga bisa diubah langsung oleh pengguna lewat
**Pengaturan → Lanjutan → URL backend**, dan tersimpan di `localStorage`.

> **Penting:** `VITE_API_URL` dibaca saat **build**. Setelah mengubahnya di
> Vercel (Settings → Environment Variables), lakukan **Redeploy**.

## Deploy ke Vercel

`vercel.json` sudah disiapkan (SPA rewrite + cache aset).

**Cara 1 — dashboard:**
1. Import repo GitHub di <https://vercel.com/new>.
2. **Root Directory** → `chatbot-saya/frontend`
3. Framework Preset → **Vite** (terdeteksi otomatis)
4. Build Command `npm run build`, Output Directory `dist`
5. Tambahkan Environment Variable `VITE_API_URL` = URL backend publik (HTTPS)
6. **Deploy**

**Cara 2 — CLI:**
```bash
npm i -g vercel
cd chatbot-saya/frontend
vercel
vercel --prod
```

## Library utama

- `react` + `react-dom` — UI
- `react-markdown` + `remark-gfm` — render Markdown jawaban AI
- `rehype-highlight` + `highlight.js` — syntax highlighting
- `dompurify` — sanitasi HTML
- `lucide-react` — ikon

## Uji E2E (opsional)

```bash
npm install --no-save playwright
npx playwright install chromium
node e2e.mjs
```
