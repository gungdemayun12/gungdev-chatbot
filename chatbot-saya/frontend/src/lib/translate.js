/**
 * translate.js — terjemahan antarmuka lewat MyMemory.
 *
 * Semua teks dikirim bersamaan, tetapi pemanggil baru menerima hasil
 * setelah seluruh kelompok selesai. Dengan begitu antarmuka bisa berpindah
 * bahasa dalam satu langkah, bukan satu teks demi satu teks.
 */
import { readJSON, writeJSON } from './storage.js'

const KUNCI_CACHE = 'gungdev:translate-cache'
const ENDPOINT = 'https://api.mymemory.translated.net/get'
const MAKS_KARAKTER = 450
const PEMISAH = '\n⟦GD⟧\n'

const cache = new Map()

function muatCache() {
  const tersimpan = readJSON(KUNCI_CACHE, {})
  if (!tersimpan || typeof tersimpan !== 'object') return
  for (const [kunci, nilai] of Object.entries(tersimpan)) {
    if (typeof nilai === 'string' && nilai) cache.set(kunci, nilai)
  }
}

function simpanCache() {
  writeJSON(KUNCI_CACHE, Object.fromEntries(cache))
}

muatCache()

function kunci(teks, dari, ke) {
  return `${dari}|${ke}|${teks}`
}

function kelompok(daftar) {
  const hasil = []
  let sekarang = []
  let panjang = 0
  for (const teks of daftar) {
    const tambahan = teks.length + PEMISAH.length
    if (sekarang.length && panjang + tambahan > MAKS_KARAKTER) {
      hasil.push(sekarang)
      sekarang = []
      panjang = 0
    }
    sekarang.push(teks)
    panjang += tambahan
  }
  if (sekarang.length) hasil.push(sekarang)
  return hasil
}

async function terjemahkanKelompok(daftar, dari, ke) {
  const params = new URLSearchParams({
    q: daftar.join(PEMISAH),
    langpair: `${dari}|${ke}`,
  })
  const email = import.meta.env.VITE_TRANSLATE_EMAIL
  if (typeof email === 'string' && email.includes('@')) params.set('de', email)

  const respons = await fetch(`${ENDPOINT}?${params}`, {
    signal: AbortSignal.timeout(15000),
  })
  if (!respons.ok) throw new Error(`translate ${respons.status}`)
  const data = await respons.json()
  if (data?.quotaFinished) throw new Error('kuota translate habis')
  const mentah = data?.responseData?.translatedText
  if (typeof mentah !== 'string' || !mentah.trim()) throw new Error('translate kosong')

  const bagian = mentah.split(/\s*⟦\s*GD\s*⟧\s*/i)
  return daftar.map((teks, i) => bagian[i]?.trim() || teks)
}

/**
 * Menerjemahkan banyak teks sekaligus.
 * Hasilnya baru dikembalikan setelah semua permintaan selesai.
 */
export async function translateMany(daftar, dari = 'id', ke = 'en') {
  const unik = [...new Set(daftar.filter((teks) => typeof teks === 'string' && teks.trim()))]
  if (!unik.length || dari === ke) return new Map(unik.map((teks) => [teks, teks]))

  const hasil = new Map()
  const belum = []
  for (const teks of unik) {
    const ada = cache.get(kunci(teks, dari, ke))
    if (ada) hasil.set(teks, ada)
    else belum.push(teks)
  }

  await Promise.all(
    kelompok(belum).map(async (bagian) => {
      try {
        const terjemahan = await terjemahkanKelompok(bagian, dari, ke)
        bagian.forEach((teks, i) => {
          cache.set(kunci(teks, dari, ke), terjemahan[i])
          hasil.set(teks, terjemahan[i])
        })
      } catch {
        bagian.forEach((teks) => hasil.set(teks, teks))
      }
    }),
  )
  if (belum.length) simpanCache()
  return hasil
}

export function translateText(teks, dari = 'id', ke = 'en') {
  return translateMany([teks], dari, ke).then((hasil) => hasil.get(teks) || teks)
}
