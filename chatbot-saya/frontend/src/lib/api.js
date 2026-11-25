/**
 * api.js — semua komunikasi ke backend AI.
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
 *   GET  /health      -> { status: "ok", provider, model }
 */

/**
 * URL backend default.
 *
 * Prioritas:
 *   1. VITE_API_URL dari Environment Variables (dipakai saat deploy)
 *   2. Otomatis:
 *        - di localhost -> http://localhost:8000 (backend terpisah saat dev)
 *        - di domain publik -> "/api" (backend satu domain, mis. Vercel)
 *
 * Karena backend kini bisa ikut di-deploy ke Vercel (folder /api),
 * frontend yang di-hosting di domain yang sama TIDAK WAJIB mengisi
 * VITE_API_URL sama sekali.
 */
function tebakDefault() {
  const dariEnv = (import.meta.env?.VITE_API_URL || '').trim().replace(/\/+$/, '')
  if (dariEnv) return dariEnv

  if (typeof window !== 'undefined' && window.location) {
    const { hostname, origin } = window.location
    const lokal =
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '[::1]' ||
      hostname === ''
    if (lokal) return 'http://localhost:8000'
    return `${origin}/api`
  }

  return 'http://localhost:8000'
}

export const DEFAULT_API_URL = tebakDefault()

/** Membersihkan base URL (buang garis miring di akhir). */
export function normalizeUrl(url) {
  return (url || DEFAULT_API_URL).trim().replace(/\/+$/, '')
}

/** Membuat pesan error yang ramah untuk pengguna. */
function friendlyError(status, detail) {
  if (detail) return detail
  const map = {
    400: 'Pesan tidak boleh kosong.',
    401: 'Layanan AI menolak permintaan. Hubungi pemilik situs.',
    402: 'Kuota layanan AI memerlukan pembayaran. Hubungi pemilik situs.',
    404: 'Model AI tidak tersedia saat ini. Hubungi pemilik situs.',
    413: 'Pesan terlalu panjang. Coba persingkat atau mulai percakapan baru.',
    429: 'Terlalu banyak permintaan. Tunggu sebentar lalu coba lagi.',
    502: 'Layanan AI sedang bermasalah. Silakan coba lagi sebentar lagi.',
    503: 'Server sedang tidak dapat dihubungi. Coba lagi beberapa saat.',
    504: 'Waktu tunggu habis. Coba lagi dengan pertanyaan yang lebih singkat.',
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
 * Mengambil pemakaian & sisa kuota AI.
 *
 * Endpoint ini tidak memanggil penyedia AI, jadi TIDAK menghabiskan
 * kuota. Mengembalikan null bila backend lama belum punya /usage
 * (agar UI bisa menyembunyikan panel tanpa error).
 */
export async function fetchUsage(baseUrl, { signal } = {}) {
  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/usage`, { signal })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
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
 * @param {string} params.model        ID publik model ("pintar" / "cepat").
 *                                     Server yang menerjemahkan ke model asli.
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
  model,
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
      model: model || undefined,
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
