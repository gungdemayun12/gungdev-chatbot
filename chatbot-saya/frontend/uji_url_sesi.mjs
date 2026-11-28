/**
 * uji_url_sesi.mjs — menguji alamat unik per percakapan (/c/<token>).
 *
 * PERMINTAAN PEMILIK SITUS
 * ------------------------
 * Setiap sesi chat harus punya token unik DI URL-nya, seperti
 * `https://claude.ai/chat/1ce46db1-d6cf-4194-9e4c-92c9f3ed5fdb`.
 *
 * Sebelumnya token sudah dibuat dan disimpan, tetapi TIDAK dipasang ke
 * URL — sehingga tidak terlihat dan tidak berguna. Uji ini memastikan
 * penyambungannya benar, dua arah:
 *
 *   STATE -> URL : buka sesi A -> URL jadi /c/<token A>
 *   URL -> STATE : buka /c/<token A> -> sesi A yang terbuka
 *                  buka /c/<token asing> -> tidak error, URL dibersihkan
 *
 * CARA KERJA
 * ----------
 * Ditulis React tiruan kecil yang meniru cara React menjalankan hook:
 *   - useRef  : disimpan per posisi, sama seperti React
 *   - useState: state disimpan per posisi, setter memicu render ulang
 *   - useEffect: dependency dibandingkan, efek yang berubah dijalankan
 *     SETELAH render selesai, berurutan sesuai urutan penulisan
 * Jadi logika hook diuji apa adanya, tanpa browser dan tanpa React asli.
 *
 * Jalankan: node uji_url_sesi.mjs
 */
import { readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { fileURLToPath, pathToFileURL } from 'node:url'
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
/* Tiruan `window`                                                     */
/* ------------------------------------------------------------------ */
const TOKEN_A = '1ce46db1-d6cf-4194-9e4c-92c9f3ed5fdb'
const TOKEN_B = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'

const lokasi = { pathname: '/', origin: 'https://gungdevchatbot.vercel.app' }
const riwayatPanggilan = []
const pendengar = new Map()

globalThis.window = {
  location: lokasi,
  origin: lokasi.origin,
  history: {
    replaceState: (_s, _j, url) => {
      riwayatPanggilan.push({ metode: 'replaceState', url })
      lokasi.pathname = url
    },
    pushState: (_s, _j, url) => {
      riwayatPanggilan.push({ metode: 'pushState', url })
      lokasi.pathname = url
    },
  },
  addEventListener: (nama, fn) => pendengar.set(nama, fn),
  removeEventListener: (nama) => pendengar.delete(nama),
}

/* ------------------------------------------------------------------ */
/* React tiruan: useRef / useCallback / useEffect dengan dependency    */
/* ------------------------------------------------------------------ */
const berkasReact = join(__dirname, '_react_tiruan_uji.mjs')
writeFileSync(
  berkasReact,
  `/* React tiruan untuk uji: cukup useRef & useCallback. useEffect
   dicatat dan dijalankan oleh mesin render di uji_url_sesi.mjs. */
export const useRef = (awal) => {
  const slot = globalThis.__slot
  const i = globalThis.__pos++
  if (!(i in slot.refs)) slot.refs[i] = { current: awal }
  return slot.refs[i]
}
export const useCallback = (fn) => fn
export const useEffect = (fn, deps) => {
  globalThis.__slot.efek.push({ fn, deps })
}
`,
  'utf8',
)

/* ------------------------------------------------------------------ */
/* Muat useUrlSesi.js dengan impor react diganti                      */
/* ------------------------------------------------------------------ */
const berkasAsli = join(__dirname, 'src', 'hooks', 'useUrlSesi.js')
const berkasUji = join(__dirname, '_useUrlSesi_uji.mjs')

writeFileSync(
  berkasUji,
  readFileSync(berkasAsli, 'utf8').replace(/from 'react'/, `from './_react_tiruan_uji.mjs'`),
  'utf8',
)

let modul
try {
  modul = await import(pathToFileURL(berkasUji).href)
} finally {
  for (const f of [berkasReact, berkasUji]) {
    try {
      unlinkSync(f)
    } catch {
      /* tidak apa-apa */
    }
  }
}

const { tokenDariUrl, AWALAN_SESI, useUrlSesi } = modul

/* ------------------------------------------------------------------ */
/* Mesin render tiruan                                                 */
/* ------------------------------------------------------------------ */
/**
 * Menjalankan `useUrlSesi` seperti React: satu "komponen" yang bisa
 * dirender berulang kali dengan props berbeda, memakai slot ref yang
 * sama dan menjalankan efek hanya bila dependency-nya berubah.
 *
 * @returns {{ dipilih: string[], render: Function }}
 */
function buatKomponen(awal) {
  const slot = { refs: {} }
  let efekTerpasang = [] // pasangan [deps, fn] dari render sebelumnya
  let props = awal
  const dipilih = []

  function render(propsBaru) {
    props = { ...props, ...propsBaru }
    const efekBaru = []

    globalThis.__slot = { refs: slot.refs, efek: efekBaru }
    globalThis.__pos = 0

    useUrlSesi({
      ...props,
      selectSession: (id) => {
        dipilih.push(id)
        if (props.onSelect) props.onSelect(id)
      },
    })

    /* Bandingkan dependency tiap efek dengan render sebelumnya. */
    const akanJalan = []
    efekBaru.forEach((fn, i) => {
      const lama = efekTerpasang[i]
      if (!lama || !samaDeps(lama.deps, fn.deps)) akanJalan.push(fn)
    })

    /* React memasang efek berurutan sesuai urutan penulisan. */
    for (const fn of akanJalan) fn.fn()

    efekTerpasang = efekBaru.map((fn) => ({ deps: fn.deps, fn }))
    return { dipilih: [...dipilih] }
  }

  return { render, dipilih }
}

function samaDeps(a, b) {
  if (!a || !b) return false
  return a.length === b.length && a.every((v, i) => Object.is(v, b[i]))
}

/* ------------------------------------------------------------------ */
console.log('\n=== 1. MEMBACA TOKEN DARI URL ===')
/* ------------------------------------------------------------------ */
cek('awalan alamat adalah /c/', AWALAN_SESI === '/c/', AWALAN_SESI)

lokasi.pathname = `/c/${TOKEN_A}`
cek('token dibaca dari /c/<uuid>', tokenDariUrl(lokasi) === TOKEN_A, String(tokenDariUrl(lokasi)))

lokasi.pathname = `/c/${TOKEN_A}/`
cek('garis miring di akhir tetap diterima', tokenDariUrl(lokasi) === TOKEN_A, String(tokenDariUrl(lokasi)))

lokasi.pathname = `/c/${TOKEN_A.toUpperCase()}`
cek('huruf besar dinormalkan ke kecil', tokenDariUrl(lokasi) === TOKEN_A, String(tokenDariUrl(lokasi)))

for (const [nama, jalur] of [
  ['halaman utama tidak dianggap sesi', '/'],
  ['alamat kosong tidak dianggap sesi', '/c/'],
  ['token ngawur ditolak', '/c/bukan-token-sama-sekali'],
  ['percobaan path traversal ditolak', '/c/../rahasia'],
  ['rute API /chat TIDAK dianggap halaman sesi', `/chat/${TOKEN_A}`],
  ['rute /c/<token>/lain ditolak', `/c/${TOKEN_A}/lain`],
]) {
  lokasi.pathname = jalur
  cek(nama, tokenDariUrl(lokasi) === null, String(tokenDariUrl(lokasi)))
}

/* ------------------------------------------------------------------ */
console.log('\n=== 2. STATE -> URL ===')
/* ------------------------------------------------------------------ */
const sesiA = { id: 's_a', token: TOKEN_A, messages: [{ role: 'user', content: 'a' }] }
const sesiB = { id: 's_b', token: TOKEN_B, messages: [{ role: 'user', content: 'b' }] }
const semua = [sesiA, sesiB]

lokasi.pathname = '/'
riwayatPanggilan.length = 0

const komp = buatKomponen({ activeSession: sesiA, sessions: semua, loaded: true })
komp.render()

cek('URL diisi token sesi aktif', lokasi.pathname === `/c/${TOKEN_A}`, lokasi.pathname)
cek(
  'memakai replaceState (bukan pushState)',
  riwayatPanggilan.length > 0 && riwayatPanggilan.every((p) => p.metode === 'replaceState'),
  JSON.stringify(riwayatPanggilan),
)

riwayatPanggilan.length = 0
komp.render({ activeSession: sesiB })
cek('ganti ke sesi B -> URL jadi token B', lokasi.pathname === `/c/${TOKEN_B}`, lokasi.pathname)
cek(
  'ganti sesi tidak menumpuk riwayat browser',
  riwayatPanggilan.every((p) => p.metode === 'replaceState'),
  JSON.stringify(riwayatPanggilan),
)

/* Sesi baru yang belum punya pesan tetap punya alamat. */
const sesiKosong = { id: 's_kosong', token: TOKEN_A, messages: [] }
lokasi.pathname = '/'
const kompKosong = buatKomponen({ activeSession: sesiKosong, sessions: [sesiKosong], loaded: true })
kompKosong.render()
cek('sesi baru (belum ada pesan) juga punya alamat', lokasi.pathname === `/c/${TOKEN_A}`, lokasi.pathname)

/* ------------------------------------------------------------------ */
console.log('\n=== 3. URL -> STATE (membuka tautan) ===')
/* ------------------------------------------------------------------ */
lokasi.pathname = `/c/${TOKEN_B}`
const k1 = buatKomponen({ activeSession: sesiA, sessions: semua, loaded: true })
k1.render()
cek('membuka /c/<token B> membuka sesi B', k1.dipilih.includes('s_b'), JSON.stringify(k1.dipilih))
cek('URL tetap di token B (tidak ditimpa sesi lama)', lokasi.pathname === `/c/${TOKEN_B}`, lokasi.pathname)

lokasi.pathname = `/c/${TOKEN_A}`
const k2 = buatKomponen({ activeSession: sesiB, sessions: semua, loaded: true })
k2.render()
cek('membuka /c/<token A> membuka sesi A', k2.dipilih.includes('s_a'), JSON.stringify(k2.dipilih))

lokasi.pathname = `/c/${TOKEN_A}`
const k3 = buatKomponen({ activeSession: sesiA, sessions: semua, loaded: true })
k3.render()
cek('sesi yang sudah aktif tidak dipilih ulang', k3.dipilih.length === 0, JSON.stringify(k3.dipilih))

/* ------------------------------------------------------------------ */
console.log('\n=== 4. TOKEN ASING -> TIDAK ERROR, URL DIBERSIHKAN ===')
/* ------------------------------------------------------------------ */
lokasi.pathname = '/c/ffffffff-ffff-4fff-8fff-ffffffffffff'
riwayatPanggilan.length = 0
const k4 = buatKomponen({ activeSession: sesiA, sessions: semua, loaded: true })
let errorAsing = null
try {
  k4.render()
} catch (e) {
  errorAsing = e
}
cek('token tidak dikenal tidak menyebabkan error', errorAsing === null, String(errorAsing))
cek('URL dibersihkan saat token tidak dikenal', lokasi.pathname === '/', lokasi.pathname)
cek('tidak ada sesi yang dipilih untuk token asing', k4.dipilih.length === 0, JSON.stringify(k4.dipilih))

/* TAMU: riwayatnya memang tidak pernah ada, jadi sesi kosong adalah
   keadaan final. Token di URL harus dibersihkan juga (temuan dari uji
   produksi: di produksi pengguna tamu, URL asing tertinggal selamanya). */
lokasi.pathname = '/c/ffffffff-ffff-4fff-8fff-ffffffffffff'
const k4t = buatKomponen({ activeSession: sesiA, sessions: [], loaded: true, tamu: true })
k4t.render()
cek('tamu dengan token asing -> URL dibersihkan', lokasi.pathname === '/', lokasi.pathname)

/* ------------------------------------------------------------------ */
console.log('\n=== 4b. TAMU: saat pesan dikirim, alamat tetap terbentuk ===')
/* ------------------------------------------------------------------ */
const sesiTamu = { id: 's_tamu', token: TOKEN_A, messages: [] }
lokasi.pathname = '/'
const kt = buatKomponen({ activeSession: sesiTamu, sessions: [sesiTamu], loaded: true, tamu: true })
kt.render()
cek('tamu juga mendapat alamat /c/<token>', lokasi.pathname === `/c/${TOKEN_A}`, lokasi.pathname)

/* ------------------------------------------------------------------ */
console.log('\n=== 5. SESI LAMA TANPA TOKEN ===')
/* ------------------------------------------------------------------ */
const sesiLama = { id: 's_lama', token: undefined, messages: [] }
lokasi.pathname = '/'
const k5 = buatKomponen({ activeSession: sesiLama, sessions: [sesiLama], loaded: true })
let errorLama = null
try {
  k5.render()
} catch (e) {
  errorLama = e
}
cek('sesi lama tanpa token tidak error', errorLama === null, String(errorLama))
cek('sesi lama tanpa token -> URL bersih', lokasi.pathname === '/', lokasi.pathname)

/* ------------------------------------------------------------------ */
console.log('\n=== 6. SEBELUM DATA TERMUAT ===')
/* ------------------------------------------------------------------ */
lokasi.pathname = `/c/${TOKEN_A}`
riwayatPanggilan.length = 0
const k6 = buatKomponen({ activeSession: null, sessions: [], loaded: false })
k6.render()
cek('URL tidak diubah sebelum data termuat', riwayatPanggilan.length === 0, JSON.stringify(riwayatPanggilan))
cek('tidak memilih sesi sebelum data termuat', k6.dipilih.length === 0)
cek('token di URL tidak hilang saat menunggu', lokasi.pathname === `/c/${TOKEN_A}`, lokasi.pathname)

/* Setelah data termuat, token yang sama dibuka. */
k6.render({ activeSession: sesiA, sessions: semua, loaded: true })
cek('setelah data termuat, tautan tetap terbuka', lokasi.pathname === `/c/${TOKEN_A}`, lokasi.pathname)

/* ------------------------------------------------------------------ */
console.log('\n=== 7. TAUTAN DIBUKA SAAT RIWAYAT MASIH KOSONG ===')
/* ------------------------------------------------------------------ */
lokasi.pathname = `/c/${TOKEN_B}`
riwayatPanggilan.length = 0
const k7 = buatKomponen({ activeSession: null, sessions: [], loaded: true })
k7.render()
cek(
  'token tidak dihapus saat daftar sesi masih kosong (data belum turun)',
  lokasi.pathname === `/c/${TOKEN_B}`,
  lokasi.pathname,
)

/* ------------------------------------------------------------------ */
console.log('\n=== 8. TOMBOL KEMBALI / MAJU BROWSER ===')
/* ------------------------------------------------------------------ */
lokasi.pathname = `/c/${TOKEN_A}`
const k8 = buatKomponen({ activeSession: sesiA, sessions: semua, loaded: true })
k8.render()
const popstate = pendengar.get('popstate')
cek('pendengar popstate terpasang', typeof popstate === 'function')

if (typeof popstate === 'function') {
  lokasi.pathname = `/c/${TOKEN_B}`
  popstate()
  cek('popstate ke token B membuka sesi B', k8.dipilih.includes('s_b'), JSON.stringify(k8.dipilih))

  const sebelum = k8.dipilih.length
  lokasi.pathname = `/c/${TOKEN_A}`
  k8.render({ activeSession: sesiA })
  cek(
    'tidak terjadi gelung saat URL menunjuk sesi yang sudah aktif',
    k8.dipilih.length === sebelum,
    JSON.stringify(k8.dipilih),
  )
}

/* ------------------------------------------------------------------ */
console.log('\n' + '='.repeat(60))
console.log(gagal === 0 ? 'HASIL: semua pemeriksaan lulus' : `HASIL: ${gagal} pemeriksaan GAGAL`)
console.log('='.repeat(60))
process.exit(gagal === 0 ? 0 : 1)
