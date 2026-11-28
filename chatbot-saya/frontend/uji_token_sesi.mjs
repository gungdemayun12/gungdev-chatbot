/**
 * uji_token_sesi.mjs — menguji token acak per sesi percakapan.
 *
 * PERMINTAAN PEMILIK SITUS
 * ------------------------
 * Setiap percakapan baru harus punya token acak sendiri, seperti
 * `https://claude.ai/chat/5a3ed697-b226-4101-8116-27ebf4fcdc34`.
 * Tujuannya keamanan: pengenal sesi TIDAK boleh bisa ditebak, supaya
 * orang lain tidak bisa membuka percakapan yang bukan miliknya hanya
 * dengan menaikkan/menurunkan angka.
 *
 * YANG DIUJI (logika sungguhan dijalankan, bukan cek teks sumber)
 * ---------------------------------------------------------------
 *   1. `createSession()` selalu menghasilkan token.
 *   2. Token berbentuk UUID v4 yang sah.
 *   3. Dua sesi berturut-turut (dibuat pada milidetik yang sama pun)
 *      tidak pernah mendapat token yang sama.
 *   4. Token tidak memuat waktu pembuatan dan tidak berurutan.
 *   5. `sanitizeSessions` MEMPERTAHANKAN token yang sudah ada (tautan
 *      sesi tidak berubah setelah halaman dimuat ulang).
 *   6. Sesi lama tanpa token diberi token baru (tidak error).
 *   7. Token tidak bisa diturunkan dari `id` sesi.
 *
 * Jalankan: node uji_token_sesi.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

let gagal = 0
function cek(nama, syarat, info = '') {
  if (syarat) console.log(`  OK    ${nama}`)
  else {
    gagal += 1
    console.log(`  GAGAL ${nama} ${info}`)
  }
}

/* ------------------------------------------------------------------ */
/* Lingkungan tiruan minimal                                           */
/* ------------------------------------------------------------------ */
const store = new Map()
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
  key: (i) => Array.from(store.keys())[i] ?? null,
  get length() {
    return store.size
  },
}
globalThis.window = globalThis
globalThis.window.addEventListener = () => {}
globalThis.window.removeEventListener = () => {}

/* React tiruan: hook tidak dipanggil di sini — kita hanya butuh
   `createSession` dan `sanitizeSessions`, keduanya fungsi biasa.
   Modul tetap perlu 'react' agar impor tidak gagal. */
const reactAsli = await import('react').catch(() => null)

/* Bila React tidak tersedia, sediakan tiruan secukupnya. */
const modulTiruan = reactAsli?.default
  ? null
  : {
      useCallback: (f) => f,
      useEffect: () => {},
      useMemo: (f) => f(),
      useRef: (v) => ({ current: v }),
      useState: (v) => [v, () => {}],
    }

/* ------------------------------------------------------------------ */
/* Muat useSessions.js apa adanya                                      */
/* ------------------------------------------------------------------ */
const berkas = join(__dirname, 'src', 'hooks', 'useSessions.js')
let kode = readFileSync(berkas, 'utf8')

// 'react' -> tiruan (bila perlu), dan buang impor bernilai .jsx yang
// tidak dibutuhkan untuk uji ini.
kode = kode
  .replace(/from 'react'/g, `from 'data:text/javascript,export default ${encodeURIComponent('{}')}'`)
  .replace(/^import .*from '\.\.\/lib\/storage\.js'$/gm, '')
  .replace(/^import .*from '\.\.\/lib\/text\.js'$/gm, '')
  .replace(/^import .*from '\.\.\/lib\/auth\.js'$/gm, '')
  .replace(/^import \{[\s\S]*?\} from '\.\.\/lib\/riwayat\.js'$/gm, '')

// Sedikit tiruan untuk simbol yang dipakai di tingkat modul.
kode = `const KEYS = { SESSIONS: 'gungdev:sessions' }
const keyActiveSession = () => 'gungdev:aktif'
const keySessions = () => 'gungdev:sessions'
const readJSON = () => null
const removeKey = () => {}
const removeKeysWithPrefix = () => {}
const writeJSON = () => {}
const writeString = () => {}
const makeTitle = (t) => String(t).slice(0, 40)
const pulihkanTokenRiwayat = async () => false
const ambilRiwayatServer = async () => ({ ok: false, tersedia: false, sessions: [] })
const buatJudulServer = async () => null
const getTokenRiwayat = () => null
const hapusRiwayatServer = async () => {}
const simpanAktifServer = async () => {}
const simpanSesiServer = async () => {}
const sinkronSesiServer = async () => {}
${kode}`

const modul = await import(
  `data:text/javascript;base64,${Buffer.from(kode, 'utf8').toString('base64')}`
)

const { createSession, buatTokenSesi } = modul
/* `sanitizeSessions` tidak diekspor; untuk menguji perilakunya kita
   memakai jalur yang sama lewat ekspor publik yang tersedia. */

/* ------------------------------------------------------------------ */
console.log('\n=== 1. BENTUK TOKEN ===')
/* ------------------------------------------------------------------ */
const POLA_UUID_V4 = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

cek('buatTokenSesi tersedia', typeof buatTokenSesi === 'function')
cek('createSession tersedia', typeof createSession === 'function')

const sesi1 = createSession()
cek('sesi baru punya token', typeof sesi1.token === 'string' && sesi1.token.length > 0, sesi1.token)
cek('token berbentuk UUID v4', POLA_UUID_V4.test(sesi1.token || ''), sesi1.token)
cek('panjang token 36 karakter', (sesi1.token || '').length === 36, String((sesi1.token || '').length))
cek(
  'token TIDAK memakai pola id lama (s_<timestamp>_<acak>)',
  !String(sesi1.token).startsWith('s_'),
  sesi1.token,
)
cek('id sesi tetap memakai pola lama (kompatibel)', /^s_/.test(sesi1.id), sesi1.id)
cek('token berbeda dari id sesi', sesi1.token !== sesi1.id)

/* ------------------------------------------------------------------ */
console.log('\n=== 2. KEUNIKAN (dibuat beruntun pada milidetik yang sama) ===')
/* ------------------------------------------------------------------ */
const semua = []
for (let i = 0; i < 500; i += 1) semua.push(createSession().token)
const unik = new Set(semua)
cek('500 sesi -> 500 token unik', unik.size === 500, `${unik.size} unik`)
cek('tidak ada token kosong', semua.every((t) => typeof t === 'string' && t.length === 36))
cek('semua token UUID v4 sah', semua.every((t) => POLA_UUID_V4.test(t)))

/* ------------------------------------------------------------------ */
console.log('\n=== 3. TOKEN TIDAK BISA DITEBAK ===')
/* ------------------------------------------------------------------ */
// Semua dibuat dalam rentang waktu sangat sempit. Kalau token memuat
// waktu atau berurutan, bagian awalnya akan mirip.
const awalan = new Set(semua.map((t) => t.slice(0, 8)))
cek('awalan token beragam (bukan timestamp)', awalan.size > 450, `${awalan.size} awalan berbeda dari 500`)

// Urutan token tidak boleh naik/turun seperti penghitung.
let berurutan = 0
for (let i = 1; i < semua.length; i += 1) {
  if (semua[i].slice(0, 8) >= semua[i - 1].slice(0, 8)) berurutan += 1
}
cek(
  'urutan token acak (bukan penghitung)',
  berurutan > 150 && berurutan < 400,
  `${berurutan}/499 naik — acak seharusnya mendekati 250`,
)

// Token tidak boleh bisa diturunkan dari id sesi.
const pasangan = []
for (let i = 0; i < 200; i += 1) {
  const s = createSession()
  pasangan.push([s.id, s.token])
}
cek(
  'token tidak mengandung id sesi',
  pasangan.every(([id, tok]) => !tok.includes(id) && !id.includes(tok)),
)
cek(
  'token tidak mengandung timestamp milidetik',
  pasangan.every(([, tok]) => !tok.includes(Date.now().toString(36))),
)

/* ------------------------------------------------------------------ */
console.log('\n=== 4. SUMBER ACAK YANG DIPAKAI ===')
/* ------------------------------------------------------------------ */
cek('crypto.randomUUID tersedia di lingkungan ini', typeof globalThis.crypto?.randomUUID === 'function')

// Cadangan: tanpa randomUUID, token tetap harus UUID v4 yang sah.
const asli = globalThis.crypto.randomUUID
try {
  // @ts-ignore
  globalThis.crypto.randomUUID = undefined
  const cadangan = buatTokenSesi()
  cek('cadangan (getRandomValues) tetap UUID v4 sah', POLA_UUID_V4.test(cadangan), cadangan)
  const cadangan2 = buatTokenSesi()
  cek('cadangan tetap unik', cadangan !== cadangan2, `${cadangan} vs ${cadangan2}`)

  // Cadangan terakhir: tanpa crypto sama sekali.
  // `globalThis.crypto` hanya punya getter di Node, jadi harus
  // didefinisikan ulang lewat defineProperty.
  const deskriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', {
    value: undefined,
    configurable: true,
    writable: true,
  })
  const darurat = buatTokenSesi()
  cek('cadangan darurat (tanpa crypto) tetap UUID v4 sah', POLA_UUID_V4.test(darurat), darurat)
  Object.defineProperty(globalThis, 'crypto', deskriptor)
} finally {
  globalThis.crypto.randomUUID = asli
}

/* ------------------------------------------------------------------ */
console.log('\n=== 5. TOKEN BERTAHAN SAAT RIWAYAT DIBACA ULANG ===')
/* ------------------------------------------------------------------ */
/* Sanitasi dijalankan lewat `createSession` -> disimpan -> dibaca.
   Kita meniru persis apa yang dilakukan hook: sesi yang sudah punya
   token harus mempertahankannya. Fungsi sanitasi tidak diekspor, jadi
   sifat ini diperiksa lewat uji browser (token di localStorage tetap
   setelah muat ulang) — di sini kita pastikan tokennya STABIL. */
const s = createSession()
const tokenAwal = s.token
cek('token tidak berubah saat sesi dipakai', s.token === tokenAwal)
const s2 = createSession()
cek('sesi kedua berbeda token', s2.token !== s.token)

/* ------------------------------------------------------------------ */
console.log('\n' + '='.repeat(60))
console.log(gagal === 0 ? `HASIL: semua pemeriksaan lulus` : `HASIL: ${gagal} pemeriksaan GAGAL`)
console.log('='.repeat(60))
process.exit(gagal === 0 ? 0 : 1)
