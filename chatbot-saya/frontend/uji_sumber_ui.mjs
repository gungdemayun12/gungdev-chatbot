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

async function aturSumber(sumber, bentuk = 'ringkas') {
  await fetch(`${API}/__uji/sumber`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sumber, bentuk }),
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
cek('penanda [1] sudah jadi chip (bukan teks mentah)', !/\[1\]/.test(isiJawaban), isiJawaban.slice(0, 80))

/* ---------- 4b. Chip sitasi sebaris (gaya ChatGPT) ---------- */
console.log('\n=== 4b. CHIP SITASI SEBARIS ===')
const chip = page.locator('.msg--assistant .sitasi')
const jumlahChip = await chip.count()
cek('chip sumber muncul di dalam jawaban', jumlahChip >= 2, `${jumlahChip} chip`)

if (jumlahChip > 0) {
  const chip1 = chip.first()
  const label1 = (await chip1.locator('.sitasi__label').innerText()).trim()
  const hrefChip1 = await chip1.getAttribute('href')
  const targetChip1 = await chip1.getAttribute('target')
  const relChip1 = await chip1.getAttribute('rel')
  cek('chip menampilkan NAMA SITUS (bukan angka)', label1 === 'contoh.com', label1)
  cek('chip bisa diklik ke situs asli', hrefChip1 === 'https://contoh.com/private-tour', String(hrefChip1))
  cek('chip membuka tab baru', targetChip1 === '_blank', String(targetChip1))
  cek('chip aman (noopener)', /noopener/.test(relChip1 || ''), String(relChip1))

  const judulChip = await chip1.getAttribute('title')
  cek('chip menyimpan judul sumber', /Private Tours Bali/.test(judulChip || ''), String(judulChip).slice(0, 50))

  // Chip duduk di ujung kalimat: teks sesudahnya tidak memuat angka mentah,
  // dan kalimat sebelum chip sudah berakhir (ada koma/titik/awal baris).
  const posisiChip = await page.evaluate(() => {
    const el = document.querySelector('.msg--assistant .sitasi')
    if (!el) return null
    const sebelum = (el.previousSibling?.textContent || '').trim().slice(-40)
    return { sebelum }
  })
  cek(
    'chip menempel setelah kalimat (bukan di awal)',
    Boolean(posisiChip && posisiChip.sebelum.length > 3),
    posisiChip ? posisiChip.sebelum : 'null',
  )
}

/* ---------- 4c. DAFTAR BERBUTIR tidak boleh rusak (kasus nyata) ---------- */
/* Ini kasus yang lolos dari uji sebelumnya: penanda [2] di akhir setiap
   butir sempat memutus daftar sehingga angkanya tampil mentah. */
console.log('\n=== 4c. DAFTAR BERBUTIR TETAP RAPI ===')
await aturSumber(SUMBER_UJI, 'daftar')
await kirim(page, 'carikan paket tour bali beserta harganya')
await page.waitForFunction(
  () => document.querySelectorAll('.msg--assistant').length >= 2,
  null,
  { timeout: 20000 },
)
await page.waitForTimeout(1000)

const butir = await page.evaluate(() => {
  const semua = document.querySelectorAll('.msg--assistant .msg__content')
  const isi = semua[semua.length - 1]
  if (!isi) return null
  const li = isi.querySelectorAll('li')
  return {
    jumlahLi: li.length,
    teksMentah: (isi.innerText || '').includes('[2]'),
    berChip: Array.from(li).filter((n) => n.querySelector('.sitasi')).length,
    adaUl: isi.querySelectorAll('ul, ol').length,
  }
})
cek('daftar dirender sebagai <li> (bukan paragraf terpotong)', Boolean(butir && butir.jumlahLi === 4), JSON.stringify(butir && butir.jumlahLi))
cek('daftar memakai <ul>/<ol> asli', Boolean(butir && butir.adaUl >= 1), JSON.stringify(butir && butir.adaUl))
cek('tidak ada angka mentah [2] di layar', Boolean(butir && !butir.teksMentah), String(butir && butir.teksMentah))
cek('setiap butir membawa chip sumbernya', Boolean(butir && butir.berChip === butir.jumlahLi), `${butir && butir.berChip}/${butir && butir.jumlahLi}`)

await aturSumber(SUMBER_UJI, 'ringkas')

/* ---------- 5. Kartu sumber tetap ada setelah refresh ---------- */
console.log('\n=== 5. SETELAH REFRESH ===')
await page.waitForTimeout(600)
await page.reload({ waitUntil: 'networkidle' })
await page.waitForSelector('.msg--assistant .sumber', { timeout: 15000 })
const masihAda = await page.locator('.sumber__ringkas').first().isVisible()
cek('kartu sumber tersimpan bersama riwayat', masihAda)
const chipSetelahRefresh = await page.locator('.msg--assistant .sitasi').count()
cek('chip sitasi tetap tampil setelah refresh', chipSetelahRefresh >= 2, `${chipSetelahRefresh} chip`)

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
const cekChatBiasa = await page.evaluate(() => {
  const pesan = document.querySelectorAll('.msg--assistant')
  const terakhir = pesan[pesan.length - 1]
  if (!terakhir) return null
  return {
    kartu: terakhir.querySelectorAll('.sumber').length,
    chip: terakhir.querySelectorAll('.sitasi').length,
  }
})
cek('chat biasa tidak menampilkan kartu sumber', Boolean(cekChatBiasa && cekChatBiasa.kartu === 0), JSON.stringify(cekChatBiasa && cekChatBiasa.kartu))
cek('chat biasa tidak menampilkan chip sitasi', Boolean(cekChatBiasa && cekChatBiasa.chip === 0), JSON.stringify(cekChatBiasa && cekChatBiasa.chip))

/* ---------- 7. Tidak ada error JS ---------- */
console.log('\n=== 7. TIDAK ADA ERROR JS ===')
cek('tidak ada error JS di halaman', errorJs.length === 0, errorJs.join(' | ').slice(0, 120))

await browser.close()

const lulus = HASIL.filter((h) => h.lulus).length
console.log('\n' + '='.repeat(60))
console.log(`HASIL: ${lulus}/${HASIL.length} lulus`)
console.log('='.repeat(60))
process.exit(lulus === HASIL.length ? 0 : 1)
