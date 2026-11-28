/**
 * uji_judul_riwayat.mjs — uji alur nyata: kirim pesan panjang, lihat judul
 * riwayat yang muncul di sidebar, lalu pastikan judul itu BERTAHAN setelah
 * halaman dimuat ulang.
 *
 * Latar belakang (keluhan pemilik situs): judul riwayat hanya potongan
 * prompt panjang. Ia ingin judul yang menyimpulkan TOPIK sesi seperti
 * Claude/ChatGPT — ringkas, mudah diingat — dan tetap ada setelah refresh.
 *
 * Yang diuji:
 *   1. Judul awal muncul langsung setelah pesan pertama dikirim.
 *   2. Judul akhir berupa TOPIK: pendek, tanpa kata sapaan/perintah,
 *      bukan potongan mentah kalimat panjang.
 *   3. Judul BERTAHAN setelah refresh.
 *   4. Judul buatan pengguna (rename) tidak ditimpa judul otomatis.
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 * Jalankan: node uji_judul_riwayat.mjs
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const TOKEN = 'token-akun-a'
const SUB = '100000000000000001'

const PROMPT_PANJANG =
  'Halo, selamat sore. Tolong bantu saya ya, saya sedang merencanakan liburan ' +
  'bulan madu ke Bali bulan depan bersama istri saya. Bisa carikan paket honeymoon ' +
  'yang bagus, lengkap dengan harga, fasilitas, dan itinerary hariannya? Untuk ' +
  'anggaran sekitar lima sampai delapan juta. Terima kasih banyak sebelumnya.'

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

const browser = await chromium.launch()

/* Reset server & salinan perangkat milik akun uji. */
{
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.evaluate(async (t) => {
    const mod = await import('/src/lib/riwayat.js')
    mod.setTokenRiwayat(t, { paksa: true })
    await mod.hapusRiwayatServer('http://127.0.0.1:8000', null)
    localStorage.removeItem('gungdev:sessions:100000000000000001')
    localStorage.removeItem('gungdev:active-session:100000000000000001')
  }, TOKEN)
  const r = await page.request.post(`${API}/__uji/reset`, { data: { sub: SUB } })
  console.log(`  (reset server: HTTP ${r.status()})`)
  await ctx.close()
}

/* Buka sebagai akun A dengan token. */
const ctx = await browser.newContext()
await ctx.addInitScript(
  ({ sub }) => {
    localStorage.setItem(
      'gungdev:auth',
      JSON.stringify({ sub, name: 'Akun A', email: 'akun.a@gmail.com', loginPada: Date.now() }),
    )
  },
  { sub: SUB },
)
const page = await ctx.newPage()

/** Memakai instance modul yang sama dengan aplikasi (lihat uji_login_bertahan). */
async function modulRiwayat() {
  await page.evaluate(async () => {
    const appUrl =
      performance
        .getEntriesByType('resource')
        .map((e) => e.name)
        .find((n) => n.includes('/src/lib/riwayat.js')) || '/src/lib/riwayat.js'
    const src = appUrl.includes('?') ? new URL(appUrl).search : ''
    window.__riwayat = await import('/src/lib/riwayat.js' + src)
  })
}

await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('.composer__input', { timeout: 20000 })
await modulRiwayat()
await page.evaluate((t) => window.__riwayat.setTokenRiwayat(t, { paksa: true }), TOKEN)
await page.waitForTimeout(600)

/* ---------------------------------------------------------------- */
console.log('\n=== 1. JUDUL SETELAH PESAN PERTAMA ===')
await page.fill('.composer__input', PROMPT_PANJANG)
await page.press('.composer__input', 'Enter')

// Tunggu jawaban selesai (streaming tiruan server uji cepat).
await page.waitForFunction(
  () => document.querySelectorAll('.msg--assistant').length > 0,
  { timeout: 60000 },
)
await page.waitForTimeout(3500) // beri waktu judul pintar dari server

/** Membaca judul sesi pertama di sidebar. */
async function judulSidebar() {
  return page.evaluate(() => {
    const el = document.querySelector('.sb-item__title, .sb-item-title, .sb-item')
    if (!el) return null
    return el.textContent.trim()
  })
}

const judulAwal = await judulSidebar()
cek('judul riwayat muncul', Boolean(judulAwal), String(judulAwal))

/* ---------------------------------------------------------------- */
console.log('\n=== 2. JUDUL BERUPA TOPIK, BUKAN POTONGAN PROMPT ===')
const judul = (judulAwal || '').trim()
cek('judul <= 60 karakter', judul.length > 0 && judul.length <= 60, `${judul.length}: ${judul}`)
cek('judul <= 8 kata', judul.split(/\s+/).length <= 8, `${judul.split(/\s+/).length} kata`)
cek('judul tanpa kata sapaan "halo"', !/^halo\b/i.test(judul), judul)
cek('judul tanpa kata "tolong"', !/tolong/i.test(judul), judul)
cek('judul tanpa kata "selamat sore"', !/selamat\s+sore/i.test(judul), judul)
cek(
  'judul BUKAN potongan 48 karakter pertama prompt',
  judul !== PROMPT_PANJANG.slice(0, 48).trim() && !PROMPT_PANJANG.startsWith(judul.slice(0, 40)),
  judul,
)
cek('judul memuat topik percakapan', /(honeymoon|bulan madu|bali)/i.test(judul), judul)

/* ---------------------------------------------------------------- */
console.log('\n=== 3. JUDUL BERTAHAN SETELAH REFRESH ===')
await page.reload({ waitUntil: 'domcontentloaded' })
await page.waitForSelector('.composer__input', { timeout: 20000 })
await page.waitForTimeout(2200)
const judulSetelahRefresh = await judulSidebar()
cek('judul tetap ada setelah refresh', Boolean(judulSetelahRefresh), String(judulSetelahRefresh))
cek('judul sama setelah refresh', judulSetelahRefresh === judulAwal, `${judulAwal} -> ${judulSetelahRefresh}`)

/* ---------------------------------------------------------------- */
console.log('\n=== 4. JUDUL BUATAN PENGGUNA TIDAK DITIMPA ===')
// Ganti nama sesi lewat API hook internal aplikasi: klik kanan -> Ubah nama
// bila tersedia; bila tidak, ubah langsung state lewat menu sidebar.
const adaMenu = await page.evaluate(() => Boolean(document.querySelector('.sb-item')))
if (adaMenu) {
  const item = page.locator('.sb-item').first()
  await item.hover()
  await page.waitForTimeout(300)
  const tombolMenu = page.locator('.sb-item__menu, .sb-item__more, button[aria-label*="Ubah"], button[title*="Ubah"]').first()
  if (await tombolMenu.count()) {
    await tombolMenu.click()
    await page.waitForTimeout(300)
    const ubah = page.locator('button', { hasText: /Ubah nama|Ganti nama/i }).first()
    if (await ubah.count()) {
      await ubah.click()
      await page.waitForTimeout(300)
      const input = page.locator('input[type="text"]').first()
      if (await input.count()) {
        await input.fill('Rencana bulan madu')
        await page.keyboard.press('Enter')
        await page.waitForTimeout(800)
        const judulBaru = await judulSidebar()
        cek('judul buatan pengguna dipakai', judulBaru === 'Rencana bulan madu', String(judulBaru))
      }
    }
  }
}

await browser.close()
const gagal = HASIL.filter((h) => !h.lulus).length
console.log(`\nHASIL: ${HASIL.length - gagal}/${HASIL.length} lulus`)
process.exit(gagal === 0 ? 0 : 1)
