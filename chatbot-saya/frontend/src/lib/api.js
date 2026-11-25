/**
 * api.js — semua komunikasi ke backend FastAPI (localhost:8000).
 *
 * Ada dua cara memanggil:
 *   1. streamChat()  -> jawaban dikirim token per token (SSE) => dipakai UI
 *   2. sendChat()    -> cara lama: tunggu jawaban lengkap => cadangan bila
 *                       browser/proksi tidak mendukung streaming
 *
 * Kontrak backend (tidak diubah):
 *   POST /chat        { message, history?, system_prompt?, temperature?, max_tokens? }
 *                     -> { reply: "..." }
 *   POST /chat/stream sama, tetapi membalas text/event-stream:
 *                     data: {"delta":"..."} ... data: {"done":true}
 *   GET  /health      -> { status: "ok" }
 */

/**
 * URL backend default.
 *
 * Prioritas:
 *   1. VITE_API_URL dari file .env (dipakai saat deploy, mis. Vercel)
 *   2. http://localhost:8000 (pengembangan lokal)
 */
export const DEFAULT_API_URL =
  (import.meta.env?.VITE_API_URL || '').trim().replace(/\/+$/, '') ||
  'http://localhost:8000'

/** Membersihkan base URL (buang garis miring di akhir). */
export function normalizeUrl(url) {
  return (url || DEFAULT_API_URL).trim().replace(/\/+$/, '')
}

/** Membuat pesan error yang ramah untuk pengguna. */
function friendlyError(status, detail) {
  if (detail) return detail
  const map = {
    400: 'Pesan tidak boleh kosong.',
    401: 'Ollama menolak permintaan. Pastikan Ollama berjalan di komputer ini.',
    402: 'Ollama meminta pembayaran. Backend seharusnya memakai model lokal.',
    404: 'Model tidak ditemukan di Ollama. Jalankan: ollama pull deepseek-r1:7b',
    429: 'Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.',
    502: 'Ollama bermasalah atau mengembalikan balasan kosong.',
    503: 'Ollama tidak berjalan. Buka aplikasi Ollama lalu coba lagi.',
    504: 'Waktu tunggu habis. Model mungkin masih memuat — coba lagi.',
  }
  return map[status] || `Terjadi kesalahan pada server (HTTP ${status}).`
}

/** Mengecek apakah backend hidup. Dipakai untuk indikator "Online". */
export async function checkHealth(baseUrl, { signal } = {}) {
  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/health`, { signal })
    if (!res.ok) return false
    const data = await res.json()
    return data?.status === 'ok'
  } catch {
    return false
  }
}

/**
 * Memanggil /chat/stream dan memanggil callback untuk tiap potongan teks.
 *
 * @param {object} params
 * @param {string} params.baseUrl     URL backend
 * @param {string} params.message     Pesan pengguna
 * @param {Array}  params.history     Riwayat pesan sebelumnya
 * @param {string} params.systemPrompt Instruksi kustom (opsional)
 * @param {number} params.temperature
 * @param {number} params.maxTokens
 * @param {AbortSignal} params.signal  Untuk tombol "Stop"
 * @param {(delta: string) => void} params.onDelta
 * @param {() => void} params.onDone
 */
export async function streamChat({
  baseUrl,
  message,
  history = [],
  systemPrompt,
  temperature,
  maxTokens,
  signal,
  onDelta,
  onDone,
}) {
  const res = await fetch(`${normalizeUrl(baseUrl)}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      history,
      system_prompt: systemPrompt || undefined,
      temperature: typeof temperature === 'number' ? temperature : undefined,
      max_tokens: typeof maxTokens === 'number' ? maxTokens : undefined,
    }),
    signal,
  })

  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = typeof data?.detail === 'string' ? data.detail : ''
    } catch {
      /* body bukan JSON */
    }
    throw new Error(friendlyError(res.status, detail))
  }

  // Browser modern: body adalah ReadableStream.
  if (!res.body || !res.body.getReader) {
    // Fallback: pakai teks utuh (hindari crash di browser lama).
    const text = await res.text()
    const parsed = parseSSEText(text)
    if (parsed.error) throw new Error(parsed.error)
    if (parsed.text) onDelta(parsed.text)
    onDone()
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      // Event SSE dipisahkan oleh baris kosong ganda.
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''

      for (const part of parts) {
        for (const line of part.split('\n')) {
          if (!line.startsWith('data:')) continue
          const payload = line.slice(5).trim()
          if (!payload) continue

          let obj
          try {
            obj = JSON.parse(payload)
          } catch {
            continue
          }

          if (obj.error) throw new Error(obj.error)
          if (typeof obj.delta === 'string' && obj.delta.length > 0) onDelta(obj.delta)
          if (obj.done) {
            onDone()
            return
          }
        }
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* abaikan */
    }
  }

  onDone()
}

/** Mengurai seluruh teks SSE (dipakai fallback). */
function parseSSEText(text) {
  let out = ''
  let error = null
  for (const line of text.split('\n')) {
    if (!line.startsWith('data:')) continue
    try {
      const obj = JSON.parse(line.slice(5).trim())
      if (obj.error) error = obj.error
      if (typeof obj.delta === 'string') out += obj.delta
    } catch {
      /* lewati baris rusak */
    }
  }
  return { text: out, error }
}

/** Cara non-streaming (cadangan). Mengembalikan teks jawaban. */
export async function sendChat({
  baseUrl,
  message,
  history = [],
  systemPrompt,
  temperature,
  maxTokens,
  signal,
}) {
  const res = await fetch(`${normalizeUrl(baseUrl)}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      history,
      system_prompt: systemPrompt || undefined,
      temperature: typeof temperature === 'number' ? temperature : undefined,
      max_tokens: typeof maxTokens === 'number' ? maxTokens : undefined,
    }),
    signal,
  })

  if (!res.ok) {
    let detail = ''
    try {
      const data = await res.json()
      detail = typeof data?.detail === 'string' ? data.detail : ''
    } catch {
      /* body bukan JSON */
    }
    throw new Error(friendlyError(res.status, detail))
  }

  const data = await res.json()
  return (data?.reply || '').toString()
}
