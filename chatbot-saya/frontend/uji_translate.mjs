/**
 * uji_translate.mjs — layanan MyMemory untuk bahasa antarmuka.
 *
 * Tidak memanggil internet: fetch ditiru agar hasilnya stabil dan kuota
 * harian tidak terpakai hanya karena pengujian.
 */
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'

const dir = dirname(fileURLToPath(import.meta.url))
const simpanan = new Map()
globalThis.localStorage = {
  getItem: (k) => (simpanan.has(k) ? simpanan.get(k) : null),
  setItem: (k, v) => simpanan.set(k, String(v)),
  removeItem: (k) => simpanan.delete(k),
}
globalThis.import = { meta: { env: {} } }

const berkas = join(dir, '_translate_uji.mjs')
writeFileSync(
  berkas,
  readFileSync(join(dir, 'src', 'lib', 'translate.js'), 'utf8')
    .replace("from './storage.js'", "from './_storage_uji_translate.mjs'")
    .replaceAll('import.meta.env.VITE_TRANSLATE_EMAIL', 'globalThis.__EMAIL_TRANSLATE'),
  'utf8',
)
writeFileSync(
  join(dir, '_storage_uji_translate.mjs'),
  `export function readJSON(k, fallback){try{const r=localStorage.getItem(k);return r==null?fallback:JSON.parse(r)}catch{return fallback}}
export function writeJSON(k,v){localStorage.setItem(k,JSON.stringify(v));return true}\n`,
  'utf8',
)

let gagal = 0
const cek = (nama, syarat, info = '') => {
  console.log(`${syarat ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
  if (!syarat) gagal += 1
}

const panggilan = []
globalThis.fetch = async (url) => {
  panggilan.push(String(url))
  const q = decodeURIComponent(new URL(url).searchParams.get('q'))
  const hasil = q
    .split('\n⟦GD⟧\n')
    .map((bagian) => (bagian === 'Pengaturan' ? 'Settings' : `EN:${bagian}`))
    .join('\n⟦GD⟧\n')
  return { ok: true, json: async () => ({ responseData: { translatedText: hasil } }) }
}
globalThis.AbortSignal = { timeout: () => undefined }

const { translateMany, translateText } = await import(pathToFileURL(berkas).href)
unlinkSync(berkas)
unlinkSync(join(dir, '_storage_uji_translate.mjs'))

const hasil = await translateText('Pengaturan', 'id', 'en')
cek('Indonesia ke Inggris memakai MyMemory', hasil === 'Settings', hasil)
cek('permintaan memuat pasangan bahasa id|en', panggilan[0].includes('langpair=id%7Cen'))

const ulang = await translateText('Pengaturan', 'id', 'en')
cek('teks yang sama diambil dari cache', ulang === 'Settings' && panggilan.length === 1)

cek('bahasa sama tidak memanggil jaringan', (await translateText('Halo', 'id', 'id')) === 'Halo')
cek('teks kosong tidak memanggil jaringan', (await translateText('', 'id', 'en')) === '')

const sebelum = panggilan.length
const banyak = await translateMany(['Pengaturan', 'Percakapan Baru', 'Pengaturan'], 'id', 'en')
cek('banyak teks dikembalikan bersamaan', banyak.get('Pengaturan') === 'Settings')
cek('teks baru ikut dalam hasil yang sama', banyak.get('Percakapan Baru') === 'EN:Percakapan Baru')
cek('kelompok teks cukup satu permintaan, bukan satu per teks', panggilan.length === sebelum + 1, `${panggilan.length - sebelum}`)

console.log(gagal ? `\nHASIL: ${gagal} GAGAL` : '\nHASIL: semua pemeriksaan lulus')
process.exit(gagal ? 1 : 0)
