/**
 * translate.js — terjemahan antarmuka lewat MyMemory.
 *
 * PEMILIHAN LAYANAN
 * -----------------
 * MyMemory dipilih karena bisa dipakai langsung tanpa akun, API key, atau
 * kartu kredit. Bahasa Indonesia tetap menjadi sumber teks di kode; layanan
 * ini hanya dipakai saat pengguna memilih English.
 *
 * BATAS GRATIS
 * ------------
 * Tanpa email: 5.000 karakter per hari.
 * Dengan email: 50.000 karakter per hari.
 * Hasil disimpan di localStorage supaya teks yang sama tidak diterjemahkan
 * berulang dan kuota harian tidak cepat habis.
 */
import { readJSON, writeJSON } from './storage.js'

const KUNCI_CACHE = 'gungdev:translate-cache'
const ENDPOINT = 'https://api.mymemory.translated.net/get'
const MAKS_PER_PERMINTAAN = 450

const cache = new Map()
const antrean = []
let sedangBerjalan = false

function muatCache() {
  const tersimpan = readJSON(KUNCI_CACHE, {})
  if (tersimpan && typeof tersimpan === 'object') {
    for (const [kunci, nilai] of Object.entries(tersimpan)) {
      if (typeof nilai === 'string' && nilai) cache.set(kunci, nilai)
    }
  }
}

function simpanCache() {
  writeJSON(KUNCI_CACHE, Object.fromEntries(cache))
}

muatCache()

function kunciCache(teks, dari, ke) {
  return `${dari}|${ke}|${teks}`
}

function pecah(teks) {
  if (teks.length <= MAKS_PER_PERMINTAAN) return [teks]
  const potongan = []
  let sisa = teks
  while (sisa.length > MAKS_PER_PERMINTAAN) {
    const batas = sisa.lastIndexOf(' ', MAKS_PER_PERMINTAAN)
    const potong = batas > 100 ? batas : MAKS_PER_PERMINTAAN
    potongan.push(sisa.slice(0, potong))
    sisa = sisa.slice(potong).trimStart()
  }
  if (sisa) potongan.push(sisa)
  return potongan
}

async function terjemahkanLangsung(teks, dari, ke) {
  const params = new URLSearchParams({
    q: teks,
    langpair: `${dari}|${ke}`,
  })
  const email = import.meta.env.VITE_TRANSLATE_EMAIL
  if (typeof email === 'string' && email.includes('@')) params.set('de', email)

  const respons = await fetch(`${ENDPOINT}?${params}`, {
    signal: AbortSignal.timeout(12000),
  })
  if (!respons.ok) throw new Error(`translate ${respons.status}`)
  const data = await respons.json()
  if (data?.quotaFinished) throw new Error('kuota translate habis')
  const hasil = data?.responseData?.translatedText
  if (typeof hasil !== 'string' || !hasil.trim()) throw new Error('translate kosong')
  return hasil
}

async function prosesAntrean() {
  if (sedangBerjalan) return
  sedangBerjalan = true
  try {
    while (antrean.length) {
      const pekerjaan = antrean.shift()
      try {
        const hasil = (
          await Promise.all(
            pecah(pekerjaan.teks).map((bagian) =>
              terjemahkanLangsung(bagian, pekerjaan.dari, pekerjaan.ke),
            ),
          )
        ).join(' ')
        cache.set(pekerjaan.kunci, hasil)
        simpanCache()
        pekerjaan.selesai(hasil)
      } catch (err) {
        pekerjaan.gagal(err)
      }
    }
  } finally {
    sedangBerjalan = false
  }
}

/**
 * Menerjemahkan satu teks. Bahasa sumber dan tujuan yang sama dikembalikan
 * langsung tanpa permintaan jaringan.
 */
export function translateText(teks, dari = 'id', ke = 'en') {
  if (!teks || dari === ke) return Promise.resolve(teks)
  const kunci = kunciCache(teks, dari, ke)
  if (cache.has(kunci)) return Promise.resolve(cache.get(kunci))

  return new Promise((selesai, gagal) => {
    antrean.push({ teks, dari, ke, kunci, selesai, gagal })
    prosesAntrean()
  })
}
