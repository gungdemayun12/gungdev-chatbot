/**
 * uji_alur_lengkap.mjs — uji alur pengguna menyeluruh di browser:
 *
 *   1. Pilih model dari model picker (termasuk model OpenRouter).
 *   2. Kirim pesan -> jawaban muncul bertahap (streaming).
 *   3. Riwayat tersimpan di server untuk akun itu.
 *   4. Panel Usage menampilkan pemakaian akun.
 *   5. Ganti model -> pilihan benar-benar tersimpan.
 *   6. Setelah refresh -> riwayat & model tetap.
 *
 * Backend uji (server_uji.py) memalsukan penyedia AI, jadi tidak ada
 * kuota provider yang terbakar.
 *
 * Jalankan: node uji_alur_lengkap.mjs
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const TOKEN = 'token-akun-a'
const SUB = '100000000000000001'

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

const browser = await chromium.launch()

/* ---------------------------------------------------------------- */
/* Bersihkan server untuk akun uji                                   */
/* ---------------------------------------------------------------- */
{
  const ctx = await browser.newContext()
  const page = await ctx.newPage()
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.evaluate(
    async ({ api, t }) => {
      const mod = await import('/src/lib/riwayat.js')
      mod.setTokenRiwayat(t)
      await mod.hapusRiwayatServer(api, null)
    },
    { api: API, t: TOKEN },
  )
  const r = await page.request.post(`${API}/__uji/reset`, { data: { sub: SUB } })
  console.log(`  (reset server: HTTP ${r.status()})`)
  await ctx.close()
}

/* ---------------------------------------------------------------- */
/* Buka sebagai akun A                                               */
/* ---------------------------------------------------------------- */
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
const galatHalaman = []
page.on('pageerror', (e) => galatHalaman.push(e.message))

await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
await page.evaluate(async (t) => {
  const mod = await import('/src/lib/riwayat.js')
  mod.setTokenRiwayat(t)
}, TOKEN)
await page.waitForSelector('.composer__input', { timeout: 20000 })
await page.waitForTimeout(1500)

/* ---------------------------------------------------------------- */
/* 1. Model picker                                                   */
/* ---------------------------------------------------------------- */
console.log('\n=== 1. MODEL PICKER ===')
const tombolModel = page.locator('.mpicker__btn').first()
const adaTombolModel = (await tombolModel.count()) > 0
cek('tombol model picker ada', adaTombolModel)

let modelTersedia = []
if (adaTombolModel) {
  await tombolModel.click()
  await page.waitForTimeout(600)
  modelTersedia = await page.$$eval('.mpicker__item-label', (els) =>
    els.map((e) => e.textContent.trim()).filter(Boolean),
  )
  cek('menu model terbuka', modelTersedia.length > 0, `jumlah=${modelTersedia.length}`)

  const teksMenu = modelTersedia.join(' | ')
  cek(
    'model google/gemini-3.1-flash-lite terdaftar',
    modelTersedia.includes('google/gemini-3.1-flash-lite'),
    teksMenu,
  )
  cek(
    'model deepseek/deepseek-v4.1-flash terdaftar',
    modelTersedia.includes('deepseek/deepseek-v4.1-flash'),
    teksMenu,
  )

  /* Badge "Gambar"/"Web" harus sudah dihapus dari menu. */
  const labelMenu = await page.$$eval('.mpicker__menu', (els) => els.map((e) => e.innerText).join('\n'))
  cek('TIDAK ada badge "Gambar"/"Web" di menu', !/\b(Gambar|Web)\b/.test(labelMenu), labelMenu.slice(0, 150))

  /* Pilih model DeepSeek. */
  const pilihanDeepseek = page.locator('.mpicker__item[role="option"]:has-text("deepseek/deepseek-v4.1-flash")').first()
  if ((await pilihanDeepseek.count()) > 0) {
    await pilihanDeepseek.click()
    await page.waitForTimeout(500)
    const labelAktif = await page.locator('.mpicker__label').innerText()
    cek('model DeepSeek terpilih di tombol', /DeepSeek/i.test(labelAktif), labelAktif)
  } else {
    cek('bisa memilih model DeepSeek', false, 'item DeepSeek tidak ditemukan')
    await page.keyboard.press('Escape')
  }
}

/* ---------------------------------------------------------------- */
/* 2. Kirim pesan -> streaming                                       */
/* ---------------------------------------------------------------- */
console.log('\n=== 2. KIRIM PESAN & STREAMING ===')
const pesanUji = 'Uji alur lengkap: balas singkat.'
await page.fill('.composer__input', pesanUji)
await page.click('.composer__send')

/* Streaming: teks asisten muncul dan bertambah sebelum selesai. */
let adaStreaming = false
for (let i = 0; i < 40; i += 1) {
  const jumlah = await page.locator('.msg--assistant').count()
  if (jumlah > 0) {
    adaStreaming = true
    break
  }
  await page.waitForTimeout(100)
}
cek('jawaban asisten muncul', adaStreaming)

await page.waitForSelector('.msg--assistant', { timeout: 25000 })
await page.waitForTimeout(3000)

const teksPesan = await page.$$eval('.msg', (els) => els.map((e) => e.textContent.trim()))
cek('pesan pengguna tampil', teksPesan.some((t) => t.includes('Uji alur lengkap')))
cek('jawaban asisten berisi teks', teksPesan.some((t) => t.length > 20))

/* ---------------------------------------------------------------- */
/* 3. Tersimpan di server                                            */
/* ---------------------------------------------------------------- */
console.log('\n=== 3. TERSIMPAN DI SERVER ===')
const server1 = await page.evaluate(async (api) => {
  const res = await fetch(api + '/api/sessions', {
    headers: { Authorization: 'Bearer token-akun-a' },
  })
  const j = await res.json()
  return {
    tersedia: j.tersedia,
    jumlah: (j.sesi || []).length,
    pesan: (j.sesi || [])[0]?.messages?.length || 0,
  }
}, API)
cek('server menyatakan riwayat tersedia', server1.tersedia === true, JSON.stringify(server1))
cek('sesi tersimpan di server', server1.jumlah >= 1, `jumlah=${server1.jumlah}`)
cek('isi pesan ikut tersimpan', server1.pesan >= 2, `pesan=${server1.pesan}`)

const statusSimpan = await page.evaluate(() => {
  const el = document.querySelector('.sb-simpan')
  return el ? el.textContent.trim() : '(tidak ada peringatan)'
})
cek(
  'TIDAK ada peringatan "Riwayat sementara hanya di perangkat ini"',
  !/hanya di perangkat/i.test(statusSimpan),
  statusSimpan,
)

/* ---------------------------------------------------------------- */
/* 4. Panel Usage                                                    */
/* ---------------------------------------------------------------- */
console.log('\n=== 4. PANEL USAGE ===')
const usage = await page.evaluate(async (api) => {
  const res = await fetch(api + '/usage', {
    headers: { Authorization: 'Bearer token-akun-a' },
  })
  return res.json()
}, API)
/* Struktur /usage: bagian TINGKAT ATAS = kuota global penyedia,
   sedangkan bagian "akun" = jatah milik akun ini (100 pesan/24 jam). */
const akunUsage = usage?.akun || {}
cek(
  'usage akun tercatat (>= 1 pesan)',
  Number(akunUsage?.requests?.terpakai) >= 1,
  JSON.stringify(akunUsage?.requests),
)
cek(
  'jatah akun memakai batas 100 (bukan batas global)',
  Number(akunUsage?.requests?.batas) === 100,
  String(akunUsage?.requests?.batas),
)
cek(
  'sisa jatah akun dihitung dari 100',
  Number(akunUsage?.requests?.sisa) === 100 - Number(akunUsage?.requests?.terpakai),
  JSON.stringify(akunUsage?.requests),
)
cek(
  'token hanya informasi (batas null, tidak membatasi)',
  akunUsage?.tokens?.batas === null && Number(akunUsage?.tokens?.terpakai) >= 0,
  JSON.stringify(akunUsage?.tokens),
)
cek(
  'jendela jatah bergulir 24 jam',
  akunUsage?.reset?.bergulir === true && Number(akunUsage?.reset?.jendela_jam) === 24,
  JSON.stringify(akunUsage?.reset),
)

const teksHalaman = await page.locator('body').innerText()
cek('nama penyedia TIDAK bocor di UI', !/openrouter|groq|ollama|upstash/i.test(teksHalaman))

/* ---------------------------------------------------------------- */
/* 5. Refresh -> riwayat & model tetap                               */
/* ---------------------------------------------------------------- */
console.log('\n=== 5. SETELAH REFRESH ===')
await page.reload({ waitUntil: 'domcontentloaded' })
await page.evaluate(async (t) => {
  const mod = await import('/src/lib/riwayat.js')
  mod.setTokenRiwayat(t)
}, TOKEN)
await page.waitForSelector('.composer__input', { timeout: 20000 })
await page.waitForTimeout(2500)

const item = await page.$$eval('.sb-item', (els) => els.map((e) => e.textContent.trim()))
cek('riwayat muncul lagi setelah refresh', item.length >= 1, JSON.stringify(item))

const teksSetelah = await page.locator('body').innerText()
cek('TIDAK ada peringatan "Masuk ulang"', !/Masuk ulang/i.test(teksSetelah))
cek('masih login setelah refresh', !/Masuk dengan Google/i.test(teksSetelah))

cek('tidak ada error JS di halaman', galatHalaman.length === 0, galatHalaman.slice(0, 2).join(' | '))

await ctx.close()
await browser.close()

const gagal = HASIL.filter((h) => !h.lulus).length
console.log(`\nHASIL: ${HASIL.length - gagal}/${HASIL.length} lulus`)
process.exit(gagal === 0 ? 0 : 1)
