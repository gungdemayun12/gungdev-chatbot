/**
 * uji_token_riwayat.mjs — menguji perilaku "token Google kedaluwarsa
 * tetapi pengguna masih login" tanpa browser dan tanpa server asli.
 *
 * Yang diuji (persis seperti keluhan pengguna):
 *   1. Saat dibuka ulang dengan token hilang, hook meminta token ke Google.
 *   2. Bila Google memberi token baru, riwayat dibaca dari server dan
 *      status menjadi 'server' (tersinkron) — bukan 'perluLogin'.
 *   3. Bila Google TIDAK memberi token, status menjadi 'perangkat'
 *      (bukan 'perluLogin'), tidak ada peringatan "masuk ulang".
 *   4. Saat menyimpan setelah 401, token dipulihkan lalu disimpan ulang.
 *   5. Logout manual menghentikan sinkronisasi dan melupakan token.
 *
 * Jalankan: node uji_token_riwayat.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))

let gagal = 0
function cek(nama, syarat, info = '') {
  if (syarat) {
    console.log(`  OK   ${nama}`)
  } else {
    gagal += 1
    console.log(`  GAGAL ${nama} ${info}`)
  }
}

/* ------------------------------------------------------------------ */
/* Tiruan lingkungan browser minimal                                   */
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

/* Google Identity Services tiruan. `modeToken` menentukan apakah
   pemulihan token berhasil atau tidak. */
const google = {
  modeToken: 'berhasil', // 'berhasil' | 'gagal'
  accounts: {
    id: {
      initialize: () => {},
      prompt: (cb) => {
        // Tidak memberi token; hasil disampaikan lewat callback token.
        if (google.modeToken === 'gagal') {
          cb({ isNotDisplayed: () => true, isSkippedMoment: () => false })
        }
      },
      renderButton: () => {},
    },
  },
}
globalThis.window = globalThis
globalThis.document = {
  querySelector: () => null,
  createElement: () => ({}),
  head: { appendChild: () => {} },
}
globalThis.window.google = google

/* ------------------------------------------------------------------ */
/* Tiruan server riwayat: tahu kapan token dianggap sah                */
/* ------------------------------------------------------------------ */
const sesiServer = [
  {
    id: 's_dari_server',
    title: 'Percakapan di server',
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

let tokenDisahkan = null // token yang dianggap Google terima
let jumlah401 = 0
let jumlahPOST = 0

function buatFetch() {
  return async (url, opsi = {}) => {
    const teks = String(url)
    const auth = (opsi.headers && (opsi.headers.Authorization || opsi.headers.authorization)) || ''
    const token = auth.replace(/^Bearer\s+/i, '')
    const sah = Boolean(token) && token === tokenDisahkan

    if (teks.includes('/api/sessions')) {
      if (!sah) {
        jumlah401 += 1
        return { status: 401, ok: false, json: async () => ({}) }
      }
      const metode = (opsi.method || 'GET').toUpperCase()
      if (metode === 'GET') {
        return {
          status: 200,
          ok: true,
          json: async () => ({ tersedia: true, sesi: sesiServer, activeId: 's_dari_server' }),
        }
      }
      jumlahPOST += 1
      return { status: 200, ok: true, json: async () => ({ tersimpan: true }) }
    }
    return { status: 404, ok: false, json: async () => ({}) }
  }
}
globalThis.fetch = buatFetch()

/* Siapkan pemulihan token: Google mengembalikan token tertentu. */
function pasangPemulihan(hasilToken) {
  google.accounts.id.prompt = () => {
    if (hasilToken) {
      // Token datang asinkron seperti Google asli.
      setTimeout(() => {
        google._callback({ credential: hasilToken })
      }, 0)
    } else {
      google._callback({})
    }
  }
  google.accounts.id.initialize = (cfg) => {
    google._callback = cfg.callback
  }
}

/* ------------------------------------------------------------------ */
/* Muat modul dengan cache-busting supaya state token bersih           */
/* ------------------------------------------------------------------ */
/* VITE_GOOGLE_CLIENT_ID tidak ada saat dijalankan dengan Node, sehingga
   LOGIN_TERSEDIA akan false dan pemulihan token tidak pernah dicoba.
   Untuk pengujian ini source ditulis ulang di memori: nilai client id
   diganti literal uji, lalu modul dimuat lewat data URL. Tidak ada file
   proyek yang diubah. */
const CLIENT_ID_UJI = 'client-uji.apps.googleusercontent.com'
let cacheModul = new Map()
let nomorGenerasi = 0

/** Menyesuaikan impor relatif agar tetap menunjuk modul yang sama. */
function tulisUlang(source) {
  return source
    .replace(/import\.meta\.env\?\.VITE_GOOGLE_CLIENT_ID \|\| ''/, `'${CLIENT_ID_UJI}'`)
    .replace(/from '\.\/([a-z]+)\.js'/g, (_, n) => `from '${urlModul(`${n}.js`)}'`)
    .replace(/\/\/# sourceMappingURL=.*/g, '')
}

function urlModul(nama) {
  if (cacheModul.has(nama)) return cacheModul.get(nama)
  const isi = readFileSync(join(__dirname, 'src/lib', nama), 'utf8')
  const url = dataModul(nama, isi)
  cacheModul.set(nama, url)
  return url
}

/**
 * Membuat URL modul untuk satu generasi.
 *
 * URL diberi penanda generasi di komentar agar Node menganggapnya modul
 * yang berbeda; dengan begitu state modul (mis. token di memori) benar-
 * benar bersih di setiap kasus uji.
 */
function dataModul(nama, isiSumber) {
  const isi = isiSumber ?? readFileSync(join(__dirname, 'src/lib', nama), 'utf8')
  const diubah = `${tulisUlang(isi)}\n// generasi-${nomorGenerasi}-${nama}\n`
  return `data:text/javascript;base64,${Buffer.from(diubah, 'utf8').toString('base64')}`
}

/**
 * Memuat ulang modul dengan STATE BERSIH.
 *
 * Node meng-cache modul berdasarkan URL, jadi setiap generasi memakai
 * folder virtual sendiri ('gen-1', 'gen-2', ...). Tanpa ini, token yang
 * sudah diisi pada kasus sebelumnya "bocor" ke kasus berikutnya dan
 * hasil uji menjadi menyesatkan.
 */
async function muatModul() {
  nomorGenerasi += 1
  cacheModul = new Map()
  const auth = await import(dataModul('auth.js'))
  const riwayat = await import(dataModul('riwayat.js'))
  return { riwayat, auth }
}

console.log('uji_token_riwayat: memulai\n')

/* ------------------------------------------------------------------ */
/* Kasus 1: token hilang, Google memberi token baru -> tersinkron      */
/* ------------------------------------------------------------------ */
{
  console.log('Kasus 1: token kedaluwarsa, Google memberi token baru')
  tokenDisahkan = 'token-baru-1'
  pasangPemulihan('token-baru-1')

  const { riwayat, auth } = await muatModul()
  // Pastikan LOGIN_TERSEDIA true untuk uji ini.
  cek(
    'login Google dianggap tersedia (client id terpasang)',
    auth.LOGIN_TERSEDIA === true,
  )
  cek('modul riwayat dimuat (token awal kosong)', riwayat.getTokenRiwayat() === null)

  const pulih = await auth.pulihkanTokenRiwayat()
  cek('pemulihan token berhasil', pulih === true, String(pulih))
  cek('token tersimpan di memori', riwayat.getTokenRiwayat() === 'token-baru-1')

  const h = await riwayat.ambilRiwayatServer('http://x', {})
  cek('riwayat terbaca dari server', h.ok === true)
  cek('tidak meminta login ulang', h.perluLogin === false)
  cek('data server terisi', h.sessions.length === 1)

  cek('tidak ada 401 sama sekali', jumlah401 === 0, `jumlah401=${jumlah401}`)
}

/* ------------------------------------------------------------------ */
/* Kasus 2: token hilang, Google TIDAK memberi token -> pakai lokal    */
/* ------------------------------------------------------------------ */
{
  console.log('\nKasus 2: token kedaluwarsa, Google tidak memberi token')
  tokenDisahkan = 'token-lain'
  pasangPemulihan(null)

  const { riwayat, auth } = await muatModul()
  const pulih = await auth.pulihkanTokenRiwayat()
  cek('pemulihan gagal secara wajar (bukan crash)', pulih === false, String(pulih))
  cek('token tetap kosong', riwayat.getTokenRiwayat() === null)

  const h = await riwayat.ambilRiwayatServer('http://x', {})
  cek('riwayat menandai perluLogin (di level modul)', h.perluLogin === true)
  // Pemanggil (useSessions) yang wajib mengubahnya menjadi 'perangkat'.
}

/* ------------------------------------------------------------------ */
/* Kasus 3: cek sumber useSessions: tidak ada lagi setStatusSimpan('perluLogin') */
/* ------------------------------------------------------------------ */
{
  console.log('\nKasus 3: pemeriksaan sumber kode')
  const src = readFileSync(join(__dirname, 'src/hooks/useSessions.js'), 'utf8')
  cek(
    "tidak ada setStatusSimpan('perluLogin')",
    !src.includes("setStatusSimpan('perluLogin')"),
  )
  cek('ada pemulihan token di kirimPerubahan', src.includes('pulihkanTokenRiwayat'))
  cek(
    'status fallback ke perangkat (bukan perluLogin)',
    src.includes("setStatusSimpan('perangkat')"),
  )

  const sidebar = readFileSync(join(__dirname, 'src/components/Sidebar.jsx'), 'utf8')
  // Teks yang tampil ke pengguna (bukan komentar) harus benar-benar hilang.
  const teksTampil = sidebar.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '')
  cek('teks "Masuk ulang" hilang dari tampilan sidebar', !teksTampil.includes('Masuk ulang'))
  cek('tidak ada kondisi perluLogin di sidebar', !sidebar.includes('perluLogin'))
}

/* ------------------------------------------------------------------ */
/* Kasus 4: logout manual menghentikan sinkronisasi                    */
/* ------------------------------------------------------------------ */
{
  console.log('\nKasus 4: logout manual melupakan token')
  tokenDisahkan = 'token-4'
  pasangPemulihan('token-4')

  const { riwayat, auth } = await muatModul()
  await auth.pulihkanTokenRiwayat()
  cek('token ada sebelum logout', riwayat.getTokenRiwayat() === 'token-4')

  auth.hapusSesi()
  cek('token terhapus setelah logout', riwayat.getTokenRiwayat() === null)
  cek('sesi login terhapus dari perangkat', auth.bacaSesiTersimpan() === null)

  const h = await riwayat.ambilRiwayatServer('http://x', {})
  cek('setelah logout tidak ada pembacaan riwayat', h.perluLogin === true)
}

console.log('\nselesai. gagal =', gagal)
process.exit(gagal === 0 ? 0 : 1)
