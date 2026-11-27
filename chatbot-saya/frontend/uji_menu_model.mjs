/**
 * uji_menu_model.mjs — memastikan menu model RAPI dan RINGKAS.
 *
 * Yang diuji:
 *   1. Model utama tampil lebih dulu (GPT, Qwen, DeepSeek, Gemini 4
 *      Argon, Gemini 3.5).
 *   2. Model lain TIDAK langsung tampil; ada di balik "Model lainnya".
 *   3. Tombol "Model lainnya" membuka sisanya, dan semua bisa dipilih.
 *   4. Menu tidak memanjang melebihi batas layar (di ponsel).
 */
import { chromium } from 'playwright'

const UI = process.env.UI_URL || 'http://127.0.0.1:5173/'
const LULUS = []
const GAGAL = []

function cek(nama, ok, info = '') {
  if (ok) {
    LULUS.push(nama)
    console.log(`LULUS  ${nama}${info ? ` — ${info}` : ''}`)
  } else {
    GAGAL.push(nama)
    console.log(`GAGAL  ${nama}${info ? ` — ${info}` : ''}`)
  }
}

const UTAMA = [
  'GPT-OSS 120B',
  'Qwen3.8 27B',
  'DeepSeek V4.1 Flash',
  'Gemini 4 Argon',
  'Gemini 3.5 Lite',
]

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 420, height: 780 } })
const page = await ctx.newPage()
await page.goto(UI, { waitUntil: 'domcontentloaded' })
await page.waitForSelector('.mpicker__btn', { timeout: 20000 })

/* --- 1. Buka menu --- */
await page.click('.mpicker__btn')
await page.waitForSelector('.mpicker__menu', { timeout: 10000 })

const labelTampil = await page.$$eval(
  '.mpicker__menu .mpicker__item-label',
  (els) => els.map((e) => e.textContent.trim()),
)
console.log('\nLabel tampil awal:', JSON.stringify(labelTampil))

for (const nama of UTAMA) {
  cek(
    `Model utama tampil: ${nama}`,
    labelTampil.includes(nama),
    labelTampil.includes(nama) ? '' : `tidak ada di ${JSON.stringify(labelTampil)}`,
  )
}

/* --- 2. Jumlah baris awal harus ringkas --- */
cek(
  'Jumlah baris awal <= 7 (tidak memanjang)',
  labelTampil.length <= 7,
  `${labelTampil.length} baris`,
)

/* --- 3. Tombol "Model lainnya" ada --- */
const tombolLain = await page.$('.mpicker__more')
cek('Tombol "Model lainnya" tersedia', Boolean(tombolLain))

/* --- 4. Tinggi menu tidak melebihi layar --- */
const kotakMenu = await page.$eval('.mpicker__menu', (el) => {
  const r = el.getBoundingClientRect()
  return { atas: r.top, bawah: r.bottom, tinggi: r.height }
})
cek(
  'Menu tidak melebihi tinggi layar',
  kotakMenu.tinggi <= 780,
  `tinggi ${Math.round(kotakMenu.tinggi)}px, atas ${Math.round(kotakMenu.atas)}px`,
)
cek(
  'Menu masih di dalam layar (tidak terpotong tepi atas/bawah)',
  kotakMenu.atas >= -1 && kotakMenu.bawah <= 781,
  `atas ${Math.round(kotakMenu.atas)}, bawah ${Math.round(kotakMenu.bawah)}`,
)

/* --- 5. Buka "Model lainnya" --- */
if (tombolLain) {
  await tombolLain.click()
  await page.waitForSelector('.mpicker__lainnya', { timeout: 10000 })
  const labelLain = await page.$$eval(
    '.mpicker__lainnya .mpicker__item-label',
    (els) => els.map((e) => e.textContent.trim()),
  )
  console.log('Label di "Model lainnya":', JSON.stringify(labelLain))
  cek('Bagian "Model lainnya" berisi model sisanya', labelLain.length > 0, `${labelLain.length} model`)

  const totalSemua = labelTampil.length + labelLain.length
  cek(
    'Semua 12 model tetap bisa dipilih (tidak ada yang hilang)',
    totalSemua >= 12,
    `${totalSemua} baris total`,
  )
}

/* --- 6. Memilih model dari bagian "lainnya" tetap bekerja --- */
if (tombolLain) {
  const target = await page.$('.mpicker__lainnya .mpicker__item')
  if (target) {
    const namaTarget = await target.$eval('.mpicker__item-label', (e) =>
      e.textContent.trim(),
    )
    await target.click()
    await page.waitForTimeout(500)
    const menuTertutup = (await page.$('.mpicker__menu')) === null
    cek('Menu tertutup setelah memilih model', menuTertutup)
    const labelAktif = await page.$eval('.mpicker__label', (e) => e.textContent.trim())
    cek(
      `Model "${namaTarget}" benar-benar terpilih`,
      labelAktif === namaTarget,
      `tombol kini: ${labelAktif}`,
    )
  }
}

/* --- 7. Buka ulang: bagian "lainnya" kembali ringkas --- */
await page.click('.mpicker__btn')
await page.waitForSelector('.mpicker__menu', { timeout: 10000 })
const adaAgain = await page.$('.mpicker__lainnya')
cek('Menu terbuka lagi dalam keadaan ringkas', adaAgain === null)

/* Model aktif harus tetap terlihat walau ia dari bagian "lainnya" */
const labelUlang = await page.$$eval('.mpicker__menu .mpicker__item-label', (els) =>
  els.map((e) => e.textContent.trim()),
)
const adaCentang = await page.$$eval('.mpicker__menu .mpicker__item-check', (e) => e.length)
cek(
  'Model aktif tetap ditampilkan (ada tanda centang)',
  adaCentang >= 1,
  `${adaCentang} centang di ${JSON.stringify(labelUlang)}`,
)

/* --- 8. Nama model tidak boleh kembar (membingungkan pengguna) --- */
await page.click('.mpicker__more').catch(() => {})
await page.waitForSelector('.mpicker__lainnya', { timeout: 10000 }).catch(() => {})

/* Baca id asli dari atribut title: itulah pembeda yang sesungguhnya.
   Satu id boleh muncul dua kali HANYA bila salah satunya baris aktif
   yang sengaja diulang di atas (agar pilihan pengguna tetap terlihat). */
const semuaId = await page.$$eval('.mpicker__menu .mpicker__item', (els) =>
  els.map((e) => e.getAttribute('title') || ''),
)
const hitung = new Map()
for (const id of semuaId) hitung.set(id, (hitung.get(id) || 0) + 1)
const dobel = [...hitung.entries()].filter(([, n]) => n > 1)

/* Hitung berapa id yang memang sedang aktif (punya tanda centang). */
const idAktif = await page.$$eval(
  '.mpicker__menu .mpicker__item.is-active',
  (els) => els.map((e) => e.getAttribute('title') || ''),
)
cek(
  'Tidak ada model yang tampil dua kali tanpa alasan',
  dobel.every(([id, n]) => n === 2 && idAktif.includes(id)),
  dobel.length
    ? `dobel: ${JSON.stringify(dobel)} (aktif: ${JSON.stringify(idAktif)})`
    : `${semuaId.length} baris, semua unik`,
)

/* Nama pendek harus berbeda untuk id yang berbeda — dua model berbeda
   tidak boleh tertulis sama persis di layar. */
const pasangan = await page.$$eval('.mpicker__menu .mpicker__item', (els) =>
  els.map((e) => ({
    id: e.getAttribute('title') || '',
    label: (e.querySelector('.mpicker__item-label')?.textContent || '').trim(),
  })),
)
const labelUnikPerId = new Map()
for (const { id, label } of pasangan) {
  if (!idAktif.includes(id)) labelUnikPerId.set(id, label)
}
const labelKembar = []
const terlihat = new Map()
for (const [id, label] of labelUnikPerId) {
  if (terlihat.has(label) && terlihat.get(label) !== id) {
    labelKembar.push(`${label} (${terlihat.get(label)} vs ${id})`)
  }
  terlihat.set(label, id)
}
cek(
  'Dua model berbeda tidak memakai nama tampilan yang sama',
  labelKembar.length === 0,
  labelKembar.length ? labelKembar.join('; ') : `${terlihat.size} nama berbeda`,
)

await ctx.close()
await browser.close()

console.log('\n' + '='.repeat(60))
console.log(`HASIL: ${LULUS.length}/${LULUS.length + GAGAL.length} lulus`)
console.log('='.repeat(60))
if (GAGAL.length) {
  for (const g of GAGAL) console.log('  GAGAL:', g)
  process.exit(1)
}
