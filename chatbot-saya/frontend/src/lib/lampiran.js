/**
 * lampiran.js — membaca file & gambar di BROWSER sebelum dikirim ke AI.
 *
 * Kenapa diekstrak di browser:
 *   1. File biner tidak perlu diunggah ke serverless function, sehingga
 *      tidak menabrak batas ukuran body (Vercel ±4,5 MB).
 *   2. Tidak menambah beban CPU/memori backend gratis.
 *   3. Pengguna langsung melihat hasilnya (mis. "PDF 12 halaman dibaca").
 *
 * Hasil ekstraksi dikirim sebagai TEKS biasa, jadi SEMUA model bisa
 * membacanya — tidak perlu model khusus.
 *
 * Untuk GAMBAR: tidak mungkin diubah jadi teks tanpa model vision.
 * Gambar dikirim sebagai data URL base64 ke model yang multimodal
 * (server yang memilih otomatis).
 */

/* ------------------------------------------------------------------ */
/* BATAS                                                              */
/* ------------------------------------------------------------------ */
export const MAKS_FILE_BYTES = 4 * 1024 * 1024 // 4 MB per file
export const MAKS_FILE = 5 // jumlah file per pesan
export const MAKS_GAMBAR = 3 // batas penyedia untuk gambar
export const MAKS_GAMBAR_BYTES = 4 * 1024 * 1024
export const MAKS_KARAKTER = 24000 // per file (sama dengan backend)

export const EKSTENSI_TEKS = [
  'txt', 'md', 'markdown', 'csv', 'tsv', 'json', 'yaml', 'yml', 'xml',
  'html', 'htm', 'css', 'js', 'jsx', 'ts', 'tsx', 'py', 'java', 'c', 'h',
  'cpp', 'cs', 'go', 'rs', 'rb', 'php', 'sql', 'sh', 'bash', 'ini', 'toml',
  'conf', 'log', 'srt', 'tex',
]

export const EKSTENSI_DIDUKUNG = [
  'pdf', 'docx', 'xlsx', 'pptx',
  ...EKSTENSI_TEKS,
  'png', 'jpg', 'jpeg', 'webp',
]

const EKSTENSI_GAMBAR = ['png', 'jpg', 'jpeg', 'webp']

/** Ekstensi huruf kecil dari sebuah nama file. */
export function ekstensiFile(nama) {
  const n = (nama || '').toLowerCase()
  const i = n.lastIndexOf('.')
  return i === -1 ? '' : n.slice(i + 1)
}

/** Apakah file ini gambar yang bisa dilihat model vision? */
export function adalahGambar(file) {
  const tipe = (file?.type || '').toLowerCase()
  if (tipe.startsWith('image/')) return EKSTENSI_GAMBAR.includes(ekstensiFile(file.name))
  return EKSTENSI_GAMBAR.includes(ekstensiFile(file.name))
}

/** Ukuran dalam bentuk mudah dibaca. */
export function formatUkuran(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/* ------------------------------------------------------------------ */
/* PEMBACAAN TEKS                                                     */
/* ------------------------------------------------------------------ */
function bersihkan(teks) {
  return (teks || '')
    .replace(/\r\n/g, '\n')
    .replace(/\r/g, '\n')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

function potong(teks) {
  if (teks.length <= MAKS_KARAKTER) return { teks, terpotong: false }
  return { teks: teks.slice(0, MAKS_KARAKTER), terpotong: true }
}

/**
 * Membaca teks dari file polos (txt, md, csv, json, kode, dst).
 * File dari Windows sering ber-encoding cp1252; UTF-8 dicoba lebih dulu.
 */
async function bacaTeksPolos(file) {
  const buffer = await file.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buffer)
  } catch {
    // Bukan UTF-8 valid -> pakai windows-1252 (Latin-1).
    return new TextDecoder('windows-1252').decode(buffer)
  }
}

/* ------------------------------------------------------------------ */
/* PDF                                                                */
/* ------------------------------------------------------------------ */
/**
 * Mengekstrak teks PDF memakai pdf.js yang dimuat malas (lazy).
 *
 * Dimuat dari CDN saat pertama kali dibutuhkan. Bila gagal (offline /
 * CDN diblokir), pengguna mendapat pesan jelas, bukan error misterius.
 */
let pdfjsCache = null

async function muatPdfjs() {
  if (pdfjsCache) return pdfjsCache
  const VERSI = '4.8.69'
  const base = `https://cdn.jsdelivr.net/npm/pdfjs-dist@${VERSI}/build/`
  const mod = await import(/* @vite-ignore */ `${base}pdf.min.mjs`)
  mod.GlobalWorkerOptions.workerSrc = `${base}pdf.worker.min.mjs`
  pdfjsCache = mod
  return mod
}

async function bacaPdf(file) {
  let pdfjs
  try {
    pdfjs = await muatPdfjs()
  } catch {
    throw new Error(
      'Pembaca PDF tidak dapat dimuat (periksa koneksi internet). Coba lagi, atau salin isi PDF ke kotak pesan.',
    )
  }

  const data = new Uint8Array(await file.arrayBuffer())
  let pdf
  try {
    pdf = await pdfjs.getDocument({ data }).promise
  } catch (err) {
    if (String(err?.name || '').includes('Password')) {
      throw new Error('PDF ini terkunci kata sandi sehingga tidak bisa dibaca.', {
        cause: err,
      })
    }
    throw new Error('PDF tidak dapat dibuka. Pastikan file tidak rusak.', {
      cause: err,
    })
  }

  const batasHalaman = Math.min(pdf.numPages, 60)
  const bagian = []
  let total = 0

  for (let i = 1; i <= batasHalaman; i++) {
    try {
      const halaman = await pdf.getPage(i)
      const isi = await halaman.getTextContent()
      const teks = isi.items
        .map((it) => (typeof it.str === 'string' ? it.str : ''))
        .join(' ')
        .replace(/\s+/g, ' ')
        .trim()
      if (teks) {
        bagian.push(`[Halaman ${i}]\n${teks}`)
        total += teks.length
      }
    } catch {
      /* halaman rusak -> lewati */
    }
    if (total >= MAKS_KARAKTER) break
  }

  const hasil = bersihkan(bagian.join('\n\n'))
  if (!hasil) {
    throw new Error(
      'PDF ini tidak berisi teks (kemungkinan hasil pindai/foto). Lampirkan foto halamannya sebagai gambar agar AI bisa membacanya.',
    )
  }
  return `${hasil}\n\n(${pdf.numPages} halaman total, dibaca ${batasHalaman})`
}

/* ------------------------------------------------------------------ */
/* DOCX / XLSX / PPTX  (arsip ZIP berisi XML)                         */
/* ------------------------------------------------------------------ */
/**
 * Membaca file Office tanpa pustaka tambahan.
 *
 * DOCX/XLSX/PPTX adalah arsip ZIP. Browser modern bisa membacanya lewat
 * DecompressionStream, tetapi itu hanya untuk gzip/deflate mentah — bukan
 * arsip ZIP. Karena itu kita urai ZIP secara manual: baca "central
 * directory" di akhir file, ambil entri XML yang dicari, lalu dekompres
 * isinya dengan DecompressionStream('deflate-raw').
 *
 * Ukurannya kecil dan hanya berjalan saat pengguna melampirkan file
 * Office, jadi tidak membebani pemuatan situs.
 */

/** Membaca seluruh isi ZIP (minimal, cukup untuk file Office). */
async function bacaEntriZip(buffer) {
  const view = new DataView(buffer)
  const bytes = new Uint8Array(buffer)

  // Cari End of Central Directory (EOCD): tanda 0x06054b50.
  let eocd = -1
  const mulai = Math.max(0, bytes.length - 66000)
  for (let i = bytes.length - 22; i >= mulai; i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i
      break
    }
  }
  if (eocd === -1) throw new Error('Bukan file Office yang valid.')

  const jumlah = view.getUint16(eocd + 10, true)
  let ptr = view.getUint32(eocd + 16, true)

  const entri = []
  for (let i = 0; i < jumlah; i++) {
    if (ptr + 46 > bytes.length) break
    if (view.getUint32(ptr, true) !== 0x02014b50) break

    const metode = view.getUint16(ptr + 10, true)
    const ukuranPadat = view.getUint32(ptr + 20, true)
    const panjangNama = view.getUint16(ptr + 28, true)
    const panjangExtra = view.getUint16(ptr + 30, true)
    const panjangKomentar = view.getUint16(ptr + 32, true)
    const offsetLokal = view.getUint32(ptr + 42, true)
    const nama = new TextDecoder().decode(
      bytes.subarray(ptr + 46, ptr + 46 + panjangNama),
    )

    entri.push({ nama, metode, ukuranPadat, offsetLokal })
    ptr += 46 + panjangNama + panjangExtra + panjangKomentar
  }
  return entri
}

/** Mengambil isi satu entri ZIP (didekompres bila perlu). */
async function isiEntriZip(buffer, entri) {
  const view = new DataView(buffer)
  const bytes = new Uint8Array(buffer)
  const p = entri.offsetLokal

  if (view.getUint32(p, true) !== 0x04034b50) return ''
  const namaLen = view.getUint16(p + 26, true)
  const extraLen = view.getUint16(p + 28, true)
  const mulaiData = p + 30 + namaLen + extraLen
  const padat = bytes.subarray(mulaiData, mulaiData + entri.ukuranPadat)

  let mentah
  if (entri.metode === 0) {
    mentah = padat
  } else if (entri.metode === 8) {
    mentah = await new Response(
      new Blob([padat]).stream().pipeThrough(new DecompressionStream('deflate-raw')),
    ).arrayBuffer()
  } else {
    return ''
  }

  return new TextDecoder('utf-8', { fatal: false }).decode(mentah)
}

/** Mengambil teks dari XML Office, mempertahankan pemisah baris. */
function teksDariXml(xml, tag) {
  // <w:p> / </w:p> = paragraf -> jadikan baris baru agar rapi terbaca.
  const denganBaris = xml.replace(/<\/(w:p|a:p|row)>/g, '\n')
  const cocok = denganBaris.match(new RegExp(`<${tag}[^>]*>([^<]*)</${tag}>`, 'g')) || []
  return cocok
    .map((m) => m.replace(/<[^>]+>/g, ' '))
    .join(' ')
    .replace(/[ \t]{2,}/g, ' ')
}

async function bacaOffice(file, ext) {
  if (typeof DecompressionStream === 'undefined') {
    throw new Error(
      'Peramban ini terlalu lama untuk membaca file Office. Coba peramban terbaru, atau salin-tempel isinya ke kotak pesan.',
    )
  }

  const buffer = await file.arrayBuffer()
  const entri = await bacaEntriZip(buffer)

  const pola =
    ext === 'docx'
      ? /^word\/(document|header\d*|footer\d*)\.xml$/
      : ext === 'xlsx'
        ? /^xl\/(worksheets\/sheet\d+|sharedStrings)\.xml$/
        : /^ppt\/slides\/slide\d+\.xml$/
  const tag = ext === 'pptx' ? 'a:t' : 't'

  const terpilih = entri.filter((e) => pola.test(e.nama)).slice(0, 40)
  if (!terpilih.length) throw new Error('File tidak berisi teks yang bisa dibaca.')

  const bagian = []
  for (const e of terpilih) {
    try {
      const xml = await isiEntriZip(buffer, e)
      const teks = ext === 'docx' ? teksDariXml(xml, 'w:t') : teksDariXml(xml, tag)
      const rapi = bersihkan(teks)
      if (rapi) bagian.push(rapi)
    } catch {
      /* entri rusak -> lewati */
    }
  }

  const hasil = bersihkan(bagian.join('\n\n'))
  if (!hasil) throw new Error('File ini tidak memuat teks (mungkin hanya gambar).')
  return hasil
}

/* ------------------------------------------------------------------ */
/* GAMBAR                                                             */
/* ------------------------------------------------------------------ */
/** Membaca gambar jadi data URL, sekaligus memperkecil bila terlalu besar. */
export async function bacaGambar(file) {
  if (!adalahGambar(file)) {
    throw new Error(`Format gambar "${ekstensiFile(file.name)}" tidak didukung. Gunakan JPG, PNG, atau WEBP.`)
  }
  if (file.size > MAKS_GAMBAR_BYTES) {
    throw new Error(`Gambar terlalu besar (maksimal ${formatUkuran(MAKS_GAMBAR_BYTES)}).`)
  }

  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ''))
    reader.onerror = () => reject(new Error('Gambar tidak dapat dibaca.'))
    reader.readAsDataURL(file)
  })

  if (!dataUrl.startsWith('data:image/')) {
    throw new Error('File ini bukan gambar yang valid.')
  }

  return {
    nama: file.name,
    ukuran: file.size,
    dataUrl,
    pratinjau: dataUrl,
  }
}

/* ------------------------------------------------------------------ */
/* API UTAMA                                                          */
/* ------------------------------------------------------------------ */
/**
 * Membaca satu file dan mengembalikan hasil siap kirim.
 *
 * Mengembalikan salah satu dari:
 *   { jenis: 'gambar', nama, ukuran, dataUrl, pratinjau }
 *   { jenis: 'teks',   nama, teks, terpotong, tipe }
 *
 * Melempar Error dengan pesan Bahasa Indonesia yang bisa langsung
 * ditampilkan ke pengguna.
 */
export async function bacaLampiran(file) {
  const ext = ekstensiFile(file.name)

  if (adalahGambar(file)) {
    const g = await bacaGambar(file)
    return { jenis: 'gambar', ...g }
  }

  if (!EKSTENSI_DIDUKUNG.includes(ext)) {
    throw new Error(
      `Jenis file .${ext || '?'} belum didukung. Yang bisa dibaca: PDF, DOCX, XLSX, PPTX, TXT, MD, CSV, JSON, kode teks, dan gambar (JPG/PNG/WEBP).`,
    )
  }

  if (file.size > MAKS_FILE_BYTES) {
    throw new Error(`File "${file.name}" terlalu besar (maksimal ${formatUkuran(MAKS_FILE_BYTES)}).`)
  }

  let teks
  if (ext === 'pdf') teks = await bacaPdf(file)
  else if (ext === 'docx' || ext === 'xlsx' || ext === 'pptx') teks = await bacaOffice(file, ext)
  else teks = await bacaTeksPolos(file)

  const { teks: dipotong, terpotong } = potong(bersihkan(teks))
  if (!dipotong) throw new Error(`Tidak ada teks yang bisa dibaca di "${file.name}".`)

  return {
    jenis: 'teks',
    nama: file.name,
    ukuran: file.size,
    teks: dipotong,
    terpotong,
    tipe: ext.toUpperCase(),
  }
}
