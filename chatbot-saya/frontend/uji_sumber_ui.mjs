/**
 * uji_sumber_ui.mjs — memastikan kartu sumber riset tampil seperti ChatGPT.
 *
 * Yang diuji:
 *   1. Setelah jawaban riset, muncul baris ringkas "Sumber:".
 *   2. Baris itu bisa dibuka dan menampilkan SEMUA sumber bernomor.
 *   3. Setiap sumber punya tautan yang bisa diklik (target _blank).
 *   4. Nomornya berurutan 1..N dan cocok dengan penanda [1] di jawaban.
 *   5. Chat biasa (tanpa riset) TIDAK menampilkan kartu sumber.
 *   6. Kartu sumber tetap ada setelah halaman dimuat ulang (ikut riwayat).
 *   7. Tidak ada error JS.
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const SUB_A = '100000000000000001'

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

async function resetAkun(sub) {
  await fetch(`${API}/__uji/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub }),
  })
}

async function aturSumber(sumber) {
  await fetch(`${API}/__uji/sumber`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sumber }),
  })
}

async function bukaMasuk(browser) {
  const ctx = await browser.newContext()
  await ctx.addInitScript(
    ({ sub }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({
          sub,
          name: 'Akun A',
          email: `${sub}@uji.local`,
          loginPada: Date.now(),
        }),
      )
    },
    { sub: SUB_A },
  )
  const page = await ctx.newPage()
  const errorJs = []
  page.on('pageerror', (e) => errorJs.push(String(e)))
  await page.goto(URL_APP, { waitUntil: 'networkidle' })
  return { ctx, page, errorJs }
}

async function kirim(page, teks) {
  const box = page.locator('textarea').first()
  await box.fill(teks)
  await box.press('Enter')
}

const SUMBER_UJI = [
  { nomor: 1, judul: 'Private Tours Bali', url: 'https://contoh.com/private-tour', situs: 'contoh.com', tanggal: '' },
  { nomor: 2, judul: 'Bali Driver Tour', url: 'https://contoh.com/driver', situs: 'contoh.com', tanggal: '' },
  { nomor: 3, judul: 'Bali OK Tour', url: 'https://contoh.com/oktour', situs: 'contoh.com', tanggal: '' },
]

const browser = await chromium.launch()

/* ---------- 1. Kartu sumber tampil setelah jawaban riset ---------- */
console.log('=== 1. KARTU SUMBER TAMPIL ===')
await resetAkun(SUB_A)
await aturSumber(SUMBER_UJI)
const { page, errorJs } = await bukaMasuk(browser)

await kirim(page, 'carikan website private tour bali murah')
await page.waitForSelector('.msg--assistant .sumber', { timeout: 20000 })

const ringkas = page.locator('.sumber__ringkas').first()
cek('baris ringkas "Sumber:" muncul', await ringkas.isVisible())
const teksRingkas = (await ringkas.innerText()).replace(/\s+/g, ' ')
cek('menyebut "Sumber"', /Sumber/.test(teksRingkas), teksRingkas.slice(0, 60))
cek('menampilkan jumlah sisanya (+2)', /\+2/.test(teksRingkas), teksRingkas.slice(0, 60))

/* ---------- 2. Membuka daftar menampilkan semua sumber ---------- */
console.log('\n=== 2. DAFTAR SUMBER LENGKAP ===')
const daftar = page.locator('.sumber__daftar')
cek('daftar masih tertutup sebelum diklik', (await daftar.count()) === 0)

await ringkas.click()
await page.waitForSelector('.sumber__daftar', { timeout: 5000 })
const item = page.locator('.sumber__item')
const jumlahItem = await item.count()
cek('semua sumber tampil setelah dibuka', jumlahItem === 3, `${jumlahItem} item`)

/* ---------- 3. Tautan bisa diklik ---------- */
console.log('\n=== 3. TAUTAN SUMBER ===')
const tautan = page.locator('.sumber__link')
const href1 = await tautan.first().getAttribute('href')
const target1 = await tautan.first().getAttribute('target')
const rel1 = await tautan.first().getAttribute('rel')
cek('tautan mengarah ke URL asli', href1 === 'https://contoh.com/private-tour', href1)
cek('tautan membuka tab baru', target1 === '_blank', String(target1))
cek('tautan aman (noopener)', /noopener/.test(rel1 || ''), String(rel1))

const judul1 = (await page.locator('.sumber__judul').first().innerText()).trim()
cek('judul sumber tampil', judul1 === 'Private Tours Bali', judul1)

/* ---------- 4. Nomor berurutan & cocok dengan penanda ---------- */
console.log('\n=== 4. NOMOR SUMBER ===')
const nomor = await page.locator('.sumber__nomor').allInnerTexts()
cek('nomor berurutan 1,2,3', nomor.join(',') === '1,2,3', nomor.join(','))
const isiJawaban = await page.locator('.msg--assistant .msg__content').first().innerText()
cek('jawaban memakai penanda [1]', /\[1\]/.test(isiJawaban), isiJawaban.slice(0, 60))
cek('jawaban memakai penanda [2]', /\[2\]/.test(isiJawaban), isiJawaban.slice(0, 60))

/* ---------- 5. Kartu sumber tetap ada setelah refresh ---------- */
console.log('\n=== 5. SETELAH REFRESH ===')
await page.waitForTimeout(600)
await page.reload({ waitUntil: 'networkidle' })
await page.waitForSelector('.msg--assistant .sumber', { timeout: 15000 })
const masihAda = await page.locator('.sumber__ringkas').first().isVisible()
cek('kartu sumber tersimpan bersama riwayat', masihAda)

/* ---------- 6. Chat biasa TANPA riset tidak menampilkan sumber ---------- */
console.log('\n=== 6. CHAT BIASA TANPA SUMBER ===')
await aturSumber([])
await kirim(page, 'halo')
await page.waitForFunction(
  () => document.querySelectorAll('.msg--assistant').length >= 2,
  null,
  { timeout: 20000 },
)
await page.waitForTimeout(900)
const jumlahKartu = await page.locator('.msg--assistant .sumber').count()
cek('chat biasa tidak menampilkan kartu sumber', jumlahKartu <= 1, `${jumlahKartu} kartu (hanya dari pesan riset)`)

/* ---------- 7. Tidak ada error JS ---------- */
console.log('\n=== 7. TIDAK ADA ERROR JS ===')
cek('tidak ada error JS di halaman', errorJs.length === 0, errorJs.join(' | ').slice(0, 120))

await browser.close()

const lulus = HASIL.filter((h) => h.lulus).length
console.log('\n' + '='.repeat(60))
console.log(`HASIL: ${lulus}/${HASIL.length} lulus`)
console.log('='.repeat(60))
process.exit(lulus === HASIL.length ? 0 : 1)
