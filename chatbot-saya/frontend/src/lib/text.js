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

/* ---------------------------------------------------------------------
   SITASI SEBARIS
   ---------------------------------------------------------------------
   Model menulis penanda [1], [2] persis setelah kalimat yang memakai
   sumber itu. Penanda itu diubah di sini menjadi chip kecil berisi NAMA
   SITUS yang bisa diklik — seperti ChatGPT ("Batur Tours +1").

   Kenapa diubah di sisi tampilan, bukan meminta model menulis format
   khusus: model kadang lupa/salah menulis format panjang, sedangkan
   angka [1] adalah hal paling sederhana dan paling sering benar. Dengan
   cara ini tampilan tetap rapi walau model menulisnya berbeda-beda.
   --------------------------------------------------------------------- */

/** Host tanpa "www." — dipakai sebagai nama pengganti bila situs kosong. */
function hostDari(url) {
  try {
    return new URL(url).hostname.replace(/^www\./i, '')
  } catch {
    return ''
  }
}

/** Nama pendek untuk chip: nama situs, atau host, dipotong wajar. */
function namaSumber(s) {
  const mentah = (s?.situs || '').trim() || hostDari(s?.url || '')
  // "Advertorial Kompas.id" -> tetap dibaca enak; potong yang kepanjangan.
  return mentah.length > 28 ? `${mentah.slice(0, 27)}…` : mentah
}

/**
 * Menyisipkan penanda sitasi ke dalam teks Markdown sebagai tautan khusus.
 *
 * MASALAH YANG DIPERBAIKI: sebelumnya jawaban dipecah menjadi beberapa
 * blok Markdown terpisah, lalu chip diletakkan di antaranya. Itu merusak
 * struktur daftar berbutir — satu butir yang penandanya berada di tengah
 * akan terbelah menjadi dua blok, sehingga penanda bullet-nya hilang dan
 * penanda `[2]` tampil sebagai angka mentah.
 *
 * SEKARANG: teks TIDAK dipecah. Penanda `[2]` diganti di tempatnya menjadi
 * tautan Markdown biasa dengan skema khusus `sitasi:<nomor>`, sehingga
 * react-markdown tetap memproses seluruh jawaban sebagai SATU dokumen utuh
 * (daftar, tabel, dan blok kode tetap rapi). Tautan itu kemudian ditangkap
 * oleh renderer `a` dan digambar sebagai chip.
 *
 * Skema `sitasi:` sengaja dipakai agar tidak bisa dijadikan tautan jahat:
 * tidak ada URL luar yang ikut terbentuk, dan renderer hanya menerima angka.
 *
 * @param {string} teks    jawaban model (Markdown)
 * @param {Array}  daftar  daftar sumber dari server ({nomor, judul, url, situs})
 * @returns {string} Markdown dengan penanda sitasi berbentuk `[label](sitasi:1,2)`
 */
export function sisipkanSitasi(teks, daftar) {
  const isi = String(teks || '')
  if (!isi) return ''

  const peta = new Map(
    (Array.isArray(daftar) ? daftar : []).map((s) => [Number(s?.nomor), s]),
  )
  if (peta.size === 0) return isi

  // Satu grup kurung berisi angka & pemisah, mis. "[1]", "[1][2]", "[1, 3]", "[2-4]".
  const pola = /\[(\d+(?:\s*[,–-]\s*\d+)*)\](?:\[(\d+(?:\s*[,–-]\s*\d+)*)\])*/g

  const nomorDari = (teksAngka) => {
    const hasil = []
    for (const bagian of teksAngka.split(',')) {
      const rentang = bagian.trim().match(/^(\d+)\s*[–-]\s*(\d+)$/)
      if (rentang) {
        const a = Number(rentang[1])
        const b = Number(rentang[2])
        for (let n = a; n <= b && n - a < 20; n += 1) hasil.push(n)
      } else if (/^\d+$/.test(bagian.trim())) {
        hasil.push(Number(bagian.trim()))
      }
    }
    return hasil
  }

  return isi.replace(pola, (mentah) => {
    // Kumpulkan SEMUA grup angka pada kecocokan ini ([1][2] -> 1 dan 2).
    const semua = []
    for (const grup of mentah.matchAll(/\[([^\]]+)\]/g)) {
      semua.push(...nomorDari(grup[1]))
    }
    const valid = [...new Set(semua.filter((n) => peta.has(n)))]
    // Nomor yang tidak dikenal DIBIARKAN apa adanya (informasi tidak hilang).
    if (valid.length === 0) return mentah

    const utama = peta.get(valid[0])
    const label = namaSumber(utama).replace(/[[\]]/g, '')
    const sisa = valid.length > 1 ? ` +${valid.length - 1}` : ''
    // Skema khusus (`sitasi:1`) TIDAK dipakai: react-markdown mengosongkan
    // href untuk skema yang tidak dikenal, sehingga chip gagal dikenali.
    // Karena itu dipakai URL sah berdomain .invalid (dijamin tidak nyata),
    // lalu ditangkap renderer dan TIDAK pernah dibuka sebagai tautan.
    return `[${label}${sisa}](https://sumber.gungdev.invalid/sitasi/${valid.join(',')})`
  })
}

/**
 * Memecah teks menjadi potongan biasa dan potongan sitasi.
 *
 * @deprecated Dipertahankan untuk kompatibilitas dan pengujian logika
 *   pengenalan nomor. TAMPILAN memakai `sisipkanSitasi` karena cara itu
 *   tidak merusak struktur Markdown (daftar/tabel) — lihat catatan di
 *   fungsi tersebut.
 *
 * @param {string} teks      jawaban model (Markdown)
 * @param {Array}  daftar    daftar sumber dari server ({nomor, judul, url, situs})
 * @returns {Array<{jenis:'teks',isi:string}|{jenis:'sitasi',nomor:number[]}>}
 *
 * Yang dikenali:
 *   [1]        -> satu sumber
 *   [1][3]     -> dua sumber berurutan
 *   [1, 3]     -> dua sumber dalam satu kurung
 *   [1-3]      -> rentang
 *
 * Penanda yang nomornya tidak ada di daftar sumber DIBIARKAN apa adanya,
 * supaya tidak ada informasi yang hilang.
 */
export function pecahSitasi(teks, daftar) {
  const isi = String(teks || '')
  if (!isi) return []

  const sah = new Set(
    (Array.isArray(daftar) ? daftar : []).map((s) => Number(s?.nomor)).filter((n) => n > 0),
  )
  if (sah.size === 0) return [{ jenis: 'teks', isi }]

  const potongan = []
  // Satu grup kurung berisi angka & pemisah, mis. "[1]", "[1][2]", "[1, 3]", "[2-4]".
  const pola = /\[(\d+(?:\s*[,–-]\s*\d+)*)\](?:\[(\d+(?:\s*[,–-]\s*\d+)*)\])*/g

  const nomorDari = (teksAngka) => {
    const hasil = []
    for (const bagian of teksAngka.split(',')) {
      const rentang = bagian.trim().match(/^(\d+)\s*[–-]\s*(\d+)$/)
      if (rentang) {
        const a = Number(rentang[1])
        const b = Number(rentang[2])
        for (let n = a; n <= b && n - a < 20; n += 1) hasil.push(n)
      } else if (/^\d+$/.test(bagian.trim())) {
        hasil.push(Number(bagian.trim()))
      }
    }
    return hasil
  }

  let akhir = 0
  let cocok
  while ((cocok = pola.exec(isi)) !== null) {
    // Kumpulkan SEMUA grup angka pada kecocokan ini ([1][2] -> 1 dan 2).
    const semua = []
    const mentah = cocok[0]
    for (const grup of mentah.matchAll(/\[([^\]]+)\]/g)) {
      semua.push(...nomorDari(grup[1]))
    }
    const valid = semua.filter((n) => sah.has(n))

    if (valid.length === 0) continue // bukan sitasi -> biarkan apa adanya

    if (cocok.index > akhir) {
      potongan.push({ jenis: 'teks', isi: isi.slice(akhir, cocok.index) })
    }
    potongan.push({ jenis: 'sitasi', nomor: [...new Set(valid)] })
    akhir = cocok.index + mentah.length
  }

  if (akhir < isi.length) potongan.push({ jenis: 'teks', isi: isi.slice(akhir) })
  return potongan
}

/**
 * Mengenali URL penanda sitasi hasil `sisipkanSitasi`.
 *
 * @param {string} href
 * @returns {number[]|null} daftar nomor sumber, atau null bila bukan sitasi
 */
export function nomorSitasi(href) {
  const cocok = String(href || '').match(/sumber\.gungdev\.invalid\/sitasi\/([\d,]+)/i)
  if (!cocok) return null
  const nomor = cocok[1]
    .split(',')
    .map((n) => Number(n))
    .filter((n) => Number.isFinite(n) && n > 0)
  return nomor.length ? nomor : null
}

/**
 * Menyiapkan data tampilan untuk satu kelompok sitasi.
 *
 * @returns {{label:string, url:string, lainnya:Array}|null}
 *   `label`  = nama situs sumber pertama (mis. "Batur Tours")
 *   `url`    = tautan yang dibuka saat chip diklik
 *   `lainnya`= sumber tambahan (untuk "+1" dan daftar kecil saat diklik)
 */
export function ringkasSitasi(nomor, daftar) {
  const peta = new Map(
    (Array.isArray(daftar) ? daftar : []).map((s) => [Number(s?.nomor), s]),
  )
  const sumber = nomor.map((n) => peta.get(n)).filter(Boolean)
  if (sumber.length === 0) return null

  const utama = sumber[0]
  return {
    label: namaSumber(utama),
    url: utama.url,
    judul: utama.judul || utama.url,
    lainnya: sumber.slice(1),
    jumlah: sumber.length,
  }
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
