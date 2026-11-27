/**
 * text.js — utilitas teks: judul sesi, ekstraksi <think>, ekspor, salin.
 */

/**
 * Memisahkan blok penalaran DeepSeek-R1 (<think>...</think>) dari jawaban.
 * Model kadang membuka tag tapi belum menutupnya saat streaming, jadi
 * bagian "thinking" dikenali juga ketika tag penutup belum muncul.
 */
export function splitThinking(raw = '') {
  // Blok lengkap (boleh lebih dari satu)
  const complete = /<think[^>]*>([\s\S]*?)<\/think>/gi
  let thinking = Array.from(raw.matchAll(complete))
    .map((m) => m[1])
    .join('\n\n')
    .trim()
  let answer = raw.replace(complete, '')

  // Blok yang belum ditutup (sedang streaming)
  const openIdx = answer.search(/<think[^>]*>/i)
  if (openIdx !== -1) {
    const after = answer.slice(openIdx)
    const tagEnd = after.indexOf('>') + 1
    thinking = (thinking ? thinking + '\n\n' : '') + after.slice(tagEnd).trim()
    answer = answer.slice(0, openIdx)
  }

  // Sisa tag penutup tanpa pembuka
  answer = answer.replace(/<\/think>/gi, '')

  return { thinking: thinking.trim(), answer: answer.replace(/\n{3,}/g, '\n\n').trim() }
}

/**
 * Membuat judul sesi otomatis dari pesan pertama.
 * Dipotong rapi di batas kata + ellipsis.
 */
export function makeTitle(text = '', maxLength = 48) {
  const clean = text
    .replace(/```[\s\S]*?```/g, ' ') // buang blok kode
    .replace(/[#*_>`~[\]()]/g, ' ') // buang karakter markdown
    .replace(/\s+/g, ' ')
    .trim()

  if (!clean) return 'Percakapan baru'
  if (clean.length <= maxLength) return clean

  const cut = clean.slice(0, maxLength)
  const lastSpace = cut.lastIndexOf(' ')
  const base = lastSpace > maxLength * 0.6 ? cut.slice(0, lastSpace) : cut
  return base.trimEnd() + '…'
}

/** Format waktu singkat "14:05". */
export function formatTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString('id-ID', {
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

/** Awal hari (00:00) untuk pengelompokan riwayat. */
function startOfDay(date) {
  const d = new Date(date)
  d.setHours(0, 0, 0, 0)
  return d.getTime()
}

/**
 * Mengelompokkan sesi ke: Disematkan, Hari ini, Kemarin,
 * 7 Hari Terakhir, Lebih Lama.
 */
export function groupSessions(sessions) {
  const now = Date.now()
  const today = startOfDay(now)
  const dayMs = 86400000

  const groups = {
    pinned: [],
    today: [],
    yesterday: [],
    week: [],
    older: [],
  }

  const sorted = [...sessions].sort(
    (a, b) => (b.pinned === true) - (a.pinned === true) || b.updatedAt - a.updatedAt,
  )

  for (const s of sorted) {
    if (s.pinned) {
      groups.pinned.push(s)
      continue
    }
    const t = s.updatedAt || s.createdAt || now
    const day = startOfDay(t)
    if (day === today) groups.today.push(s)
    else if (day === today - dayMs) groups.yesterday.push(s)
    else if (day > today - 7 * dayMs) groups.week.push(s)
    else groups.older.push(s)
  }

  return [
    { key: 'pinned', label: 'Disematkan', items: groups.pinned },
    { key: 'today', label: 'Hari ini', items: groups.today },
    { key: 'yesterday', label: 'Kemarin', items: groups.yesterday },
    { key: 'week', label: '7 Hari Terakhir', items: groups.week },
    { key: 'older', label: 'Lebih Lama', items: groups.older },
  ].filter((g) => g.items.length > 0)
}

/** Menyalin teks ke clipboard dengan fallback untuk browser lama. */
export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* lanjut ke fallback */
  }

  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

/** Memicu unduhan file di browser. */
export function downloadFile(filename, content, mime = 'text/plain;charset=utf-8') {
  const blob = new Blob([content], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** Nama file aman dari karakter terlarang. */
export function safeFilename(name, fallback = 'percakapan') {
  const clean = (name || '').replace(/[\\/:*?"<>|]+/g, '-').replace(/\s+/g, ' ').trim()
  return (clean || fallback).slice(0, 80)
}

/** Satu sesi -> Markdown. */
export function sessionToMarkdown(session) {
  const lines = [`# ${session.title || 'Percakapan'}`, '']
  lines.push(`_Diekspor dari GungDev — ${new Date().toLocaleString('id-ID')}_`, '')
  for (const m of session.messages || []) {
    if (m.role === 'user') {
      lines.push('## Pengguna', '', m.content, '')
    } else if (m.role === 'assistant') {
      const { thinking, answer } = splitThinking(m.content || '')
      if (thinking) lines.push('<details><summary>Proses berpikir</summary>', '', thinking, '', '</details>', '')
      lines.push('## GungDev', '', answer || m.content || '', '')
      // Sumber riset ikut diekspor, supaya catatan yang dibagikan tetap
      // bisa diperiksa asalnya (nomornya sama dengan penanda [1], [2]).
      if (Array.isArray(m.sumber) && m.sumber.length) {
        lines.push('**Sumber:**', '')
        for (const s of m.sumber) {
          lines.push(`${s.nomor}. [${s.judul || s.url}](${s.url})${s.situs ? ` — ${s.situs}` : ''}`)
        }
        lines.push('')
      }
    }
  }
  return lines.join('\n')
}

/** Satu sesi -> teks polos. */
export function sessionToText(session) {
  const lines = [session.title || 'Percakapan', '='.repeat(40), '']
  for (const m of session.messages || []) {
    const who = m.role === 'user' ? 'Pengguna' : 'GungDev'
    const { answer } = splitThinking(m.content || '')
    lines.push(`[${who}]`, answer || m.content || '', '')
    if (m.role === 'assistant' && Array.isArray(m.sumber) && m.sumber.length) {
      lines.push('Sumber:')
      for (const s of m.sumber) lines.push(`  ${s.nomor}. ${s.judul || s.url} (${s.url})`)
      lines.push('')
    }
  }
  return lines.join('\n')
}
