/**
 * uji_hook_sesi.mjs — menguji hook `useSessions` SECARA NYATA (logika
 * hook dijalankan, bukan sekadar cek string) untuk kasus yang dikeluhkan:
 *
 *   "sudah login, balik beberapa jam, disuruh masuk ulang untuk
 *    menyinkronkan riwayat"
 *
 * Caranya: sumber proyek ditulis ulang di memori (client id uji,
 * impor 'react' diarahkan ke React tiruan yang menjalankan hook asli),
 * lalu `fetch` diganti tiruan yang membalas 401 sebelum token dipulihkan.
 *
 * Jalankan: node uji_hook_sesi.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { buatReactTiruan, waitFor } from './uji_render_hook.mjs'

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
/* Lingkungan tiruan                                                   */
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
/* CATATAN: setTimeout/clearTimeout milik Node DIPERTAHANKAN apa adanya.
   Sempat diganti dengan fungsi lain dan itu membuat batas waktu 8 detik
   di auth.js tidak pernah berbunyi — hasil uji jadi menyesatkan. */

const CLIENT_ID_UJI = 'client-uji.apps.googleusercontent.com'

const google = {
  tokenBaru: 'token-segar',
  accounts: {
    id: {
      initialize: (cfg) => {
        google._cb = cfg.callback
      },
      prompt: (cb) => {
        // Tiruan Google yang sesungguhnya: memberi notifikasi MOMENT
        // (isNotDisplayed), lalu tidak pernah memanggil callback token.
        if (google.tokenBaru) {
          setTimeout(() => google._cb({ credential: google.tokenBaru }), 0)
        } else if (typeof cb === 'function') {
          setTimeout(() => cb({ isNotDisplayed: () => true }), 0)
        }
      },
      renderButton: () => {},
    },
  },
}
globalThis.window.google = google
globalThis.document = {
  querySelector: () => null,
  createElement: () => ({}),
  head: { appendChild: () => {} },
}

/* ------------------------------------------------------------------ */
/* Server riwayat tiruan                                               */
/* ------------------------------------------------------------------ */
const SESI_SERVER = [
  {
    id: 's_server_1',
    title: 'Pesan lama dari server',
    titleLocked: false,
    messages: [
      { id: 'm1', role: 'user', content: 'halo', createdAt: 1 },
      { id: 'm2', role: 'assistant', content: 'hai', createdAt: 2 },
    ],
    createdAt: 1,
    updatedAt: 2,
    pinned: false,
  },
]

const server = { tokenSah: 'token-segar', s401: 0, s200: 0, post: 0 }

globalThis.fetch = async (url, opsi = {}) => {
  const teks = String(url)
  if (!teks.includes('/api/sessions')) {
    return { status: 404, ok: false, json: async () => ({}) }
  }
  const auth = (opsi.headers && (opsi.headers.Authorization || opsi.headers.authorization)) || ''
  const token = auth.replace(/^Bearer\s+/i, '')

  if (!token || token !== server.tokenSah) {
    server.s401 += 1
    return { status: 401, ok: false, json: async () => ({}) }
  }
  server.s200 += 1
  const metode = (opsi.method || 'GET').toUpperCase()
  if (metode === 'GET') {
    return {
      status: 200,
      ok: true,
      json: async () => ({ tersedia: true, sesi: SESI_SERVER, activeId: 's_server_1' }),
    }
  }
  server.post += 1
  return { status: 200, ok: true, json: async () => ({ tersimpan: true }) }
}

/* ------------------------------------------------------------------ */
/* Pemuat modul bertulis-ulang                                        */
/* ------------------------------------------------------------------ */
const tiruan = buatReactTiruan()
const urlReact = `data:text/javascript;base64,${Buffer.from(
  `export const useState=globalThis.__REACT_TIRUAN__.useState;
   export const useEffect=globalThis.__REACT_TIRUAN__.useEffect;
   export const useRef=globalThis.__REACT_TIRUAN__.useRef;
   export const useMemo=globalThis.__REACT_TIRUAN__.useMemo;
   export const useCallback=globalThis.__REACT_TIRUAN__.useCallback;
   export const useReducer=globalThis.__REACT_TIRUAN__.useReducer;
   export const useLayoutEffect=globalThis.__REACT_TIRUAN__.useLayoutEffect;
   export default { };`,
).toString('base64')}`
globalThis.__REACT_TIRUAN__ = tiruan.React

let cacheModul = new Map()
let generasi = 0

function urlModul(nama, folder = 'src/lib') {
  const kunci = `${folder}/${nama}`
  if (cacheModul.has(kunci)) return cacheModul.get(kunci)
  let isi = readFileSync(join(__dirname, folder, nama), 'utf8')
  isi = isi
    .replace(/import\.meta\.env\?\.VITE_GOOGLE_CLIENT_ID \|\| ''/, `'${CLIENT_ID_UJI}'`)
    .replace(/from 'react'/g, `from '${urlReact}'`)
    .replace(/from '\.\/([a-z]+)\.js'/g, (_, n) => `from '${urlModul(`${n}.js`)}'`)
    .replace(/from '\.\.\/lib\/([a-z]+)\.js'/g, (_, n) => `from '${urlModul(`${n}.js`)}'`)
  const url = `data:text/javascript;base64,${Buffer.from(
    `${isi}\n// gen-${generasi}-${nama}\n`,
    'utf8',
  ).toString('base64')}`
  cacheModul.set(kunci, url)
  return url
}

/** Memuat useSessions + auth dengan state perangkat & modul yang bersih. */
async function muatUlang() {
  generasi += 1
  cacheModul = new Map()
  tiruan.reset()
  const auth = await import(urlModul('auth.js'))
  const sesi = await import(urlModul('useSessions.js', 'src/hooks'))
  return { auth, useSessions: sesi.useSessions }
}

async function pasangHook(useSessions, setelan, sub) {
  const r = tiruan.render(() => useSessions(setelan, sub, 'http://uji'))
  await r.jalankan()
  return r
}

/* ------------------------------------------------------------------ */
/* Kasus A: token hilang, Google memberi token baru                   */
/* ------------------------------------------------------------------ */
console.log('Kasus A: token hilang, Google memberi token baru')

store.set(
  'gungdev:auth',
  JSON.stringify({
    sub: 'akun-uji',
    name: 'Akun Uji',
    email: 'uji@example.com',
    picture: '',
    loginPada: Date.now() - 5 * 60 * 60 * 1000,
  }),
)
store.set(
  'gungdev:sessions:akun-uji',
  JSON.stringify([
    {
      id: 's_lokal_1',
      title: 'Dari perangkat',
      titleLocked: false,
      messages: [{ id: 'm9', role: 'user', content: 'lokal', createdAt: 5 }],
      createdAt: 5,
      updatedAt: 5,
      pinned: false,
    },
  ]),
)

server.tokenSah = 'token-segar'
google.tokenBaru = 'token-segar'
server.s401 = 0

let { auth, useSessions } = await muatUlang()
const login = auth.bacaSesiTersimpan()
cek('sesi login masih terbaca setelah 5 jam', login?.sub === 'akun-uji')

const A = await pasangHook(useSessions, { saveHistory: true }, login.sub)
await waitFor(() => A.hasil.current.statusSimpan !== 'memuat', { timeout: 8000 })

cek(
  'statusSimpan BUKAN perluLogin',
  A.hasil.current.statusSimpan !== 'perluLogin',
  `status=${A.hasil.current.statusSimpan}`,
)
cek(
  'statusSimpan = server (tersinkron)',
  A.hasil.current.statusSimpan === 'server',
  `status=${A.hasil.current.statusSimpan}`,
)
cek(
  'riwayat dari server terpakai',
  A.hasil.current.sessions.some((s) => s.id === 's_server_1'),
  JSON.stringify(A.hasil.current.sessions.map((s) => s.id)),
)
A.unmount()

/* ------------------------------------------------------------------ */
/* Kasus B: Google tidak memberi token -> tetap login, pakai perangkat */
/* ------------------------------------------------------------------ */
console.log('\nKasus B: Google tidak memberi token (butuh interaksi)')

google.tokenBaru = null
store.set(
  'gungdev:auth',
  JSON.stringify({
    sub: 'akun-uji',
    name: 'Akun Uji',
    email: 'uji@example.com',
    picture: '',
    loginPada: Date.now() - 5 * 60 * 60 * 1000,
  }),
)
;({ auth, useSessions } = await muatUlang())
const B = await pasangHook(useSessions, { saveHistory: true }, 'akun-uji')
// Pemulihan token punya batas waktu 8 detik saat Google tidak menjawab,
// jadi tunggu lebih lama dari itu.
await waitFor(() => B.hasil.current.statusSimpan !== 'memuat', { timeout: 20000 })

cek(
  'statusSimpan BUKAN perluLogin',
  B.hasil.current.statusSimpan !== 'perluLogin',
  `status=${B.hasil.current.statusSimpan}`,
)
cek(
  'statusSimpan = perangkat',
  B.hasil.current.statusSimpan === 'perangkat',
  `status=${B.hasil.current.statusSimpan}`,
)
cek(
  'riwayat perangkat tetap tampil',
  B.hasil.current.sessions.length > 0,
  `jumlah=${B.hasil.current.sessions.length}`,
)
B.unmount()

/* ------------------------------------------------------------------ */
/* Kasus C: token kedaluwarsa saat menyimpan -> dipulihkan otomatis    */
/* ------------------------------------------------------------------ */
console.log('\nKasus C: menyimpan saat token kedaluwarsa')

store.set(
  'gungdev:auth',
  JSON.stringify({
    sub: 'akun-uji',
    name: 'Akun Uji',
    email: 'uji@example.com',
    picture: '',
    loginPada: Date.now() - 5 * 60 * 60 * 1000,
  }),
)
google.tokenBaru = 'token-baru-simpan'
server.tokenSah = 'token-baru-simpan'
server.s401 = 0
server.post = 0
;({ auth, useSessions } = await muatUlang())
const C = await pasangHook(useSessions, { saveHistory: true }, 'akun-uji')
await waitFor(() => C.hasil.current.statusSimpan !== 'memuat', { timeout: 8000 })

const sesiBaru = C.hasil.current.ensureSession()
C.hasil.current.addMessage(sesiBaru.id, { role: 'user', content: 'pesan baru' })
// Beri jeda melewati debounce 900 ms.
await new Promise((r) => setTimeout(r, 1600))
await waitFor(() => server.post > 0, { timeout: 5000 })

cek('simpan berhasil setelah token dipulihkan', server.post > 0, `POST=${server.post}`)
cek(
  'statusSimpan = server setelah simpan',
  C.hasil.current.statusSimpan === 'server',
  `status=${C.hasil.current.statusSimpan}`,
)
C.unmount()

/* ------------------------------------------------------------------ */
/* Kasus D: logout manual menghentikan sinkronisasi                    */
/* ------------------------------------------------------------------ */
console.log('\nKasus D: logout manual')
;({ auth, useSessions } = await muatUlang())
const D = await pasangHook(useSessions, { saveHistory: true }, null)
await waitFor(() => D.hasil.current.statusSimpan === 'lokal', { timeout: 4000 })
cek(
  'tamu tidak menyinkronkan (status lokal)',
  D.hasil.current.statusSimpan === 'lokal',
  `status=${D.hasil.current.statusSimpan}`,
)
D.unmount()

console.log('\nselesai. gagal =', gagal)
process.exit(gagal === 0 ? 0 : 1)
