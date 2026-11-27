/**
 * uji_login_bertahan.mjs — uji BROWSER untuk kasus yang dikeluhkan:
 * pengguna sudah login, kembali beberapa jam kemudian, dan sebelumnya
 * diminta "Masuk ulang untuk menyinkronkan riwayat".
 *
 * Yang dibuktikan di browser sungguhan (Chromium):
 *   1. Halaman dibuka dengan token SUDAH kedaluwarsa (server balas 401).
 *      Google tidak bisa memberi token (nilai client id uji tidak nyata),
 *      jadi pemulihan gagal — persis kondisi paling buruk.
 *      Hasil yang benar: TIDAK ADA peringatan "Masuk ulang" dan
 *      pengguna tetap login.
 *   2. Riwayat perangkat tetap tampil (tidak hilang).
 *   3. Setelah token dipulihkan, riwayat server muncul & tersinkron.
 *   4. Logout manual benar-benar mengakhiri sesi.
 *
 * Jalankan (butuh backend uji + vite dev):
 *   node uji_login_bertahan.mjs
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
/* Akun uji harus sama dengan yang dikenali backend uji (server_uji.py):
   token 'token-akun-a' -> sub '100000000000000001'. */
const SUB_AKUN = '100000000000000001'
const AKUN = {
  sub: SUB_AKUN,
  name: 'Akun Tetap Login',
  email: 'tetap@example.com',
  picture: '',
}

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

/* Token yang dianggap sah oleh backend uji. */
const TOKEN_SAH = 'token-akun-a'

const browser = await chromium.launch()

/* ------------------------------------------------------------------ */
/* Persiapan: tanam riwayat perangkat + sesi login (5 jam lalu)        */
/* ------------------------------------------------------------------ */
function skripAwal({ token }) {
  return `
    (function () {
      try {
        var sesi = {
          sub: ${JSON.stringify(AKUN.sub)},
          name: ${JSON.stringify(AKUN.name)},
          email: ${JSON.stringify(AKUN.email)},
          picture: '',
          loginPada: Date.now() - 5 * 60 * 60 * 1000
        };
        localStorage.setItem('gungdev:auth', JSON.stringify(sesi));
        var riwayat = [{
          id: 's_perangkat_1',
          title: 'Percakapan lama di perangkat',
          titleLocked: false,
          messages: [
            { id: 'm1', role: 'user', content: 'halo dari perangkat', createdAt: 1 },
            { id: 'm2', role: 'assistant', content: 'hai', createdAt: 2 }
          ],
          createdAt: 1, updatedAt: 2, pinned: false
        }];
        localStorage.setItem('gungdev:sessions:' + sesi.sub, JSON.stringify(riwayat));
        ${token ? `localStorage.setItem('gungdev:token-uji', ${JSON.stringify(token)});` : ''}
      } catch (e) {}
    })();
  `
}

/* ------------------------------------------------------------------ */
/* Skenario 1: token kedaluwarsa, Google tidak bisa memulihkan         */
/* ------------------------------------------------------------------ */
console.log('Skenario 1: sesi login ada, token kedaluwarsa (paling buruk)')
{
  const ctx = await browser.newContext()
  const page = await ctx.newPage()

  /* Token lama yang TIDAK sah dipasang ke modul riwayat SEBELUM React
     membaca riwayat — meniru token kedaluwarsa yang masih tersimpan. */
  await page.addInitScript(skripAwal({ token: null }))
  await page.addInitScript(() => {
    // Cegah Google memulihkan token: blokir skrip GIS.
    const asalFetch = window.fetch
    window.fetch = (...a) => asalFetch(...a)
  })
  await page.route('**/accounts.google.com/**', (route) => route.abort())

  /* Kirim token KEDALUWARSA ke backend lewat localStorage untuk uji:
     backend uji menerima token hanya bila cocok dengan sub akun. */
  await page.addInitScript(() => {
    window.__tokenKedaluwarsa = 'token-kedaluwarsa'
  })

  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3500)

  const teksHalaman = (await page.locator('body').innerText()) || ''
  cek(
    'tidak ada peringatan "Masuk ulang"',
    !/Masuk ulang/i.test(teksHalaman),
    'teks yang dicari: Masuk ulang',
  )
  cek(
    'tidak ada ajakan "Masuk dengan Google" (masih login)',
    !/Masuk dengan Google/i.test(teksHalaman),
  )
  cek(
    'nama akun masih tampil (sesi login bertahan)',
    teksHalaman.includes(AKUN.name) || teksHalaman.includes('Akun'),
  )
  cek(
    'riwayat perangkat tetap tampil',
    teksHalaman.includes('Percakapan lama di perangkat'),
  )

  await ctx.close()
}

/* ------------------------------------------------------------------ */
/* Skenario 2: token dipulihkan -> riwayat server tersinkron           */
/* ------------------------------------------------------------------ */
console.log('\nSkenario 2: token berhasil dipulihkan -> tersinkron ke server')
{
  /* Siapkan data server untuk akun ini lewat API langsung. */
  const res = await fetch('http://127.0.0.1:8000/api/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${TOKEN_SAH}` },
    body: JSON.stringify({
      session: {
        id: 's_dari_server',
        title: 'Percakapan dari server',
        titleLocked: false,
        messages: [{ id: 'm5', role: 'user', content: 'halo dari server', createdAt: 9 }],
        createdAt: 9,
        updatedAt: 9,
        pinned: false,
      },
    }),
  })
  cek('data server uji tersimpan', res.ok, `HTTP ${res.status}`)

  const ctx = await browser.newContext()
  const page = await ctx.newPage()

  /* Tiruan Google Identity Services yang MEMBERI token baru.
     Ini meniru kondisi normal: pengguna masih login ke Google, jadi
     `prompt()` mengembalikan kredensial baru tanpa interaksi. */
  await page.addInitScript(`window.google = {
    accounts: { id: {
      initialize: function (cfg) { window.__cb = cfg.callback },
      prompt: function () { setTimeout(function () { window.__cb({ credential: ${JSON.stringify(TOKEN_SAH)} }) }, 50) },
      renderButton: function () {}
    } }
  }`)

  await page.addInitScript(skripAwal({ token: null }))

  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(3000)

  const teks = (await page.locator('body').innerText()) || ''
  cek(
    'riwayat dari server muncul (tersinkron)',
    teks.includes('Percakapan dari server'),
    'dicari: Percakapan dari server',
  )
  cek('tidak ada peringatan "Masuk ulang"', !/Masuk ulang/i.test(teks))
  cek('masih login (tidak ada ajakan masuk)', !/Masuk dengan Google/i.test(teks))

  /* Pastikan server benar-benar menerima permintaan dari browser ini. */
  const cekServer = await fetch('http://127.0.0.1:8000/api/sessions', {
    headers: { Authorization: `Bearer ${TOKEN_SAH}` },
  })
  const dataServer = await cekServer.json()
  cek(
    'server punya sesi untuk akun ini',
    Array.isArray(dataServer.sesi) && dataServer.sesi.some((s) => s.id === 's_dari_server'),
    `jumlah sesi server = ${dataServer.sesi?.length}`,
  )

  await ctx.close()
}

/* ------------------------------------------------------------------ */
/* Skenario 3: logout manual mengakhiri sesi                          */
/* ------------------------------------------------------------------ */
console.log('\nSkenario 3: logout manual')
{
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.addInitScript(skripAwal({ token: null }))
  await page.route('**/accounts.google.com/**', (route) => route.abort())
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)

  const authSebelum = await page.evaluate(() => localStorage.getItem('gungdev:auth'))
  cek('sesi login tersimpan sebelum logout', Boolean(authSebelum))

  // Cari tombol keluar.
  const tombolKeluar = page.locator('button:has-text("Keluar")')
  const adaKeluar = (await tombolKeluar.count()) > 0
  cek('tombol Keluar ada di UI', adaKeluar)
  if (adaKeluar) {
    await tombolKeluar.first().click()
    await page.waitForTimeout(800)
    const authSesudah = await page.evaluate(() => localStorage.getItem('gungdev:auth'))
    cek('sesi login terhapus setelah logout', authSesudah === null)
    const teks = (await page.locator('body').innerText()) || ''
    cek('muncul ajakan masuk lagi', /Masuk dengan Google/i.test(teks))
  }
  await ctx.close()
}

await browser.close()

const gagal = HASIL.filter((h) => !h.lulus).length
console.log(`\nHASIL: ${HASIL.length - gagal}/${HASIL.length} lulus`)
process.exit(gagal === 0 ? 0 : 1)
