/**
 * uji_jatah_browser.mjs — memastikan jatah per akun terlihat & bekerja di UI.
 *
 * Yang diuji:
 *   1. Panel Usage menampilkan "Pemakaian saya" dengan jatah 100 pesan
 *      (bukan 1000 kuota bersama).
 *   2. Saat jatah habis, pesan penolakan TAMPIL di area chat dengan
 *      bahasa yang jelas.
 *   3. Akun lain tetap bisa chat.
 *
 * Butuh server_uji.py (port 8000) + npm run dev (port 5173).
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const TOKEN_A = 'token-akun-a'
const TOKEN_B = 'token-akun-b'
const SUB_A = '100000000000000001'
const SUB_B = '200000000000000002'

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

async function aturPemakaian(sub, requests, tokens = 0) {
  const res = await fetch(`${API}/__uji/pakai`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub, requests, tokens }),
  })
  return res.ok
}

async function bukaSebagai(browser, { sub, name, token }) {
  const ctx = await browser.newContext()
  await ctx.addInitScript(
    ({ sub, name }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({ sub, name, email: `${sub}@uji.local`, loginPada: Date.now() }),
      )
    },
    { sub, name },
  )
  const page = await ctx.newPage()
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.evaluate(async (t) => {
    const mod = await import('/src/lib/riwayat.js')
    mod.setTokenRiwayat(t)
  }, token)
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  return { ctx, page }
}

async function jalankan() {
  const browser = await chromium.launch()

  /* ================= 1. PANEL MENAMPILKAN JATAH AKUN ================= */
  console.log('\n=== 1. PANEL USAGE MENAMPILKAN JATAH AKUN ===')
  await aturPemakaian(SUB_A, 37, 9999)
  const d1 = await bukaSebagai(browser, { sub: SUB_A, name: 'Akun A', token: TOKEN_A })
  const p1 = d1.page
  await p1.waitForTimeout(1200)

  await p1.click('[aria-label="Lihat pemakaian dan kuota AI"]')
  await p1.waitForSelector('.usage__akun', { timeout: 15000 })
  await p1.waitForTimeout(800)

  const teksAkun = (await p1.textContent('.usage__akun')) || ''
  cek('Blok "Pemakaian saya" tampil', /Pemakaian saya/i.test(teksAkun), teksAkun.slice(0, 60))
  cek('Menampilkan 37 pesan terpakai', teksAkun.includes('37'), teksAkun.slice(0, 90))
  cek('Menampilkan jatah 100 pesan', teksAkun.includes('100'), teksAkun.slice(0, 90))
  cek('Menampilkan sisa pesan', /Sisa/i.test(teksAkun), teksAkun.slice(0, 120))
  cek('Menampilkan token terpakai', /token/i.test(teksAkun), teksAkun.slice(0, 140))
  cek(
    'TIDAK menyebut batas global 1.000 di blok akun',
    !teksAkun.includes('1.000'),
    teksAkun.slice(0, 100),
  )

  const tutup = await p1.$('[aria-label="Tutup dialog"]')
  if (tutup) await tutup.click()
  await p1.waitForTimeout(500)

  /* ================= 2. JATAH HABIS -> PESAN TAMPIL ================= */
  console.log('\n=== 2. JATAH HABIS: PESAN PENOLAKAN TAMPIL ===')
  await aturPemakaian(SUB_A, 100, 0)

  await p1.fill('.composer__input', 'Pesan saat jatah habis')
  await p1.click('.composer__send')
  await p1.waitForTimeout(3500)

  // Cari pesan penolakan di area chat (bisa berupa msg--assistant error
  // atau notifikasi). Kita ambil seluruh teks halaman agar tidak salah
  // bergantung pada satu selector.
  const teksHalaman = await p1.evaluate(() => document.body.innerText)
  // Ambil HANYA pesan penolakannya. Seluruh halaman juga memuat nama
  // model di pemilih model (memang boleh tampil), jadi memeriksa
  // seluruh halaman akan salah menyimpulkan "bocor".
  const pesanJatah = (teksHalaman.match(/Jatah[^\n]*/g) || []).join(' ')
  cek(
    'Pesan "jatah ... habis" TAMPIL untuk pengguna',
    /jatah/i.test(pesanJatah) && /habis/i.test(pesanJatah),
    pesanJatah.slice(0, 120),
  )
  cek(
    'Pesan menyebut jatah pulih otomatis',
    /pulih otomatis/i.test(pesanJatah),
    pesanJatah.slice(0, 140),
  )
  cek(
    'Pesan menyebut jatah hanya milik akun ini',
    /hanya milik akun Anda/i.test(pesanJatah),
    pesanJatah.slice(0, 160),
  )
  cek(
    'Pesan penolakan TIDAK membocorkan penyedia/infrastruktur',
    !/groq|openai|qwen|ollama|localhost|127\.0\.0\.1/i.test(pesanJatah),
    pesanJatah.slice(0, 120),
  )

  /* ================= 3. AKUN LAIN TETAP BISA ================= */
  console.log('\n=== 3. AKUN LAIN TETAP BISA CHAT ===')
  await aturPemakaian(SUB_B, 0, 0)
  const d2 = await bukaSebagai(browser, { sub: SUB_B, name: 'Akun B', token: TOKEN_B })
  const p2 = d2.page
  await p2.waitForTimeout(800)

  await p2.fill('.composer__input', 'Halo dari akun B')
  await p2.click('.composer__send')
  await p2.waitForSelector('.msg--assistant', { timeout: 25000 })
  await p2.waitForTimeout(1200)

  const teksB = await p2.evaluate(() => document.body.innerText)
  cek(
    'Akun B dapat jawaban (tidak terkena jatah A)',
    /Jawaban untuk/i.test(teksB),
    teksB.slice(0, 100).replace(/\n/g, ' | '),
  )

  await browser.close()

  console.log('\n' + '='.repeat(62))
  const lulus = HASIL.filter((h) => h.lulus).length
  console.log(`HASIL: ${lulus}/${HASIL.length} lulus`)
  console.log('='.repeat(62))
  HASIL.filter((h) => !h.lulus).forEach((h) => console.log(`  GAGAL: ${h.nama}`))
  process.exit(lulus === HASIL.length ? 0 : 1)
}

jalankan().catch((e) => {
  console.error('Uji gagal dijalankan:', e)
  process.exit(2)
})
