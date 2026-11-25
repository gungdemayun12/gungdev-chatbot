import { chromium } from 'playwright'

const URL = 'https://gungdev-chatbot-ai.vercel.app'
const hasil = []
const cek = (nama, ok, extra = '') => {
  hasil.push({ nama, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${nama}${extra ? ' — ' + extra : ''}`)
}

const TERLARANG = [
  /gpt-oss/i, /openai/i, /groq/i, /ollama/i, /deepseek/i, /llama/i, /qwen/i,
  /fastapi/i, /uvicorn/i, /react-markdown/i, /system prompt/i, /localhost/i,
  /127\.0\.0\.1/i, /gungdev-chatbot-rq5l/i, /GROQ_MODEL/i, /OLLAMA_MODEL/i,
]
const periksaBocor = (teks, diMana) => {
  const kena = TERLARANG.filter((r) => r.test(teks)).map((r) => r.source)
  cek(`Bebas info sensitif: ${diMana}`, kena.length === 0, kena.join(', '))
}

const browser = await chromium.launch()

/* ---------- DESKTOP ---------- */
console.log('--- DESKTOP LIVE ---')
const desk = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const d = await desk.newPage()
const errs = []
d.on('console', (m) => {
  if (m.type() === 'error') errs.push(m.text().slice(0, 150))
})

await d.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })
await d.evaluate(() => localStorage.clear())
await d.reload({ waitUntil: 'networkidle' })
await d.waitForTimeout(4000)

cek('Situs live tampil', (await d.locator('.chat__header').count()) > 0)
cek('Status Online', /Online/i.test(await d.locator('.chat__header').innerText()))

const picker = d.locator('.mpicker__btn')
cek('Pemilih model ada di composer', (await picker.count()) === 1)

const bP = await picker.boundingBox()
const bS = await d.locator('.composer__send').boundingBox()
cek('Pemilih model di KIRI tombol kirim', bP && bS && bP.x + bP.width <= bS.x + 2,
  bP && bS ? `${Math.round(bP.x + bP.width)} <= ${Math.round(bS.x)}` : '')

await picker.click()
await d.waitForTimeout(600)
cek('Menu terbuka, 2 pilihan', (await d.locator('.mpicker__item').count()) === 2)
const menuTxt = await d.locator('.mpicker__menu').innerText()
periksaBocor(menuTxt, 'menu model')
await d.screenshot({ path: 'l-menu.png' })

/* pilih Cepat lalu kirim */
await d.locator('.mpicker__item').filter({ hasText: 'Cepat' }).first().click()
await d.waitForTimeout(900)
cek('Tombol jadi "Cepat"', (await picker.innerText()).includes('Cepat'))

let body = null
d.on('request', (req) => {
  if (req.url().includes('/chat/stream')) {
    try {
      body = JSON.parse(req.postData() || '{}')
    } catch { /* abaikan */ }
  }
})

await d.locator('.composer__input').fill('Balas hanya: oke')
await d.locator('.composer__send').click()
let chatOk = false
try {
  await d.waitForFunction(() => {
    const el = document.querySelectorAll('.msg--assistant')
    return el.length > 0 && el[el.length - 1].innerText.trim().length > 0
  }, { timeout: 90000 })
  chatOk = true
} catch { /* gagal */ }
cek('Chat berfungsi dengan model pilihan', chatOk)
cek('Request mengirim model "cepat"', body?.model === 'cepat', String(body?.model))
cek('Request tanpa nama model teknis', !/gpt-oss|openai|groq/i.test(JSON.stringify(body)))

await d.waitForTimeout(800)
await d.screenshot({ path: 'l-chat.png' })

/* /health & /usage produksi */
const health = await d.evaluate(async () => {
  const r = await fetch('/health')
  return r.json()
})
cek('/health produksi = gungdev', health.provider === 'gungdev' && health.model === 'gungdev',
  JSON.stringify(health))

const usage = await d.evaluate(async () => {
  const r = await fetch('/usage')
  return r.json()
})
cek('/usage produksi = gungdev', usage.provider === 'gungdev' && usage.model === 'gungdev',
  `${usage.provider}/${usage.model}`)

/* Pengaturan bersih */
await d.locator('[aria-label="Menu pengaturan"]').first().click()
await d.waitForTimeout(1300)
await d.locator('.settings__tab').filter({ hasText: 'Lanjutan' }).first().click()
await d.waitForTimeout(2800)
const lanjutan = await d.locator('.modal__body').innerText()
periksaBocor(lanjutan, 'tab Lanjutan live')
cek('Pemilih model publik ada di Pengaturan', /Model AI/i.test(lanjutan))
cek('Panel kuota ada', (await d.locator('.settings-usage .usage-bar').count()) === 2)
await d.screenshot({ path: 'l-settings.png' })

await d.locator('.settings__tab').filter({ hasText: 'Tentang' }).first().click()
await d.waitForTimeout(900)
const tentang = await d.locator('.about').innerText()
periksaBocor(tentang, 'tab Tentang live')
await d.screenshot({ path: 'l-tentang.png' })

await d.locator('[aria-label="Tutup dialog"]').first().click()
await d.waitForTimeout(700)
periksaBocor(await d.locator('body').innerText(), 'seluruh halaman live')

const fatal = errs.filter((e) => !/favicon|Failed to fetch|ERR_|net::/i.test(e))
cek('Tanpa error konsol (desktop)', fatal.length === 0, fatal.slice(0, 2).join(' | '))
await desk.close()

/* ---------- MOBILE ---------- */
console.log('\n--- MOBILE LIVE ---')
const mob = await browser.newContext({
  viewport: { width: 390, height: 844 },
  deviceScaleFactor: 3,
  isMobile: true,
  hasTouch: true,
})
const p = await mob.newPage()
await p.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })
await p.evaluate(() => localStorage.clear())
await p.reload({ waitUntil: 'networkidle' })
await p.waitForTimeout(4000)

const pm = p.locator('.mpicker__btn')
cek('Mobile: pemilih model ada', (await pm.count()) === 1)
const bm = await pm.boundingBox()
const sm = await p.locator('.composer__send').boundingBox()
cek('Mobile: di kiri tombol kirim', bm && sm && bm.x + bm.width <= sm.x + 2)
cek('Mobile: tombol >=36px', bm && bm.height >= 36, bm ? Math.round(bm.height) + 'px' : '')

await pm.click()
await p.waitForTimeout(800)
cek('Mobile: menu terbuka', (await p.locator('.mpicker__menu').count()) === 1)
const menuBox = await p.locator('.mpicker__menu').boundingBox()
cek('Mobile: menu pas di layar', menuBox && menuBox.width <= 390, menuBox ? Math.round(menuBox.width) + 'px' : '')
const itemBox = await p.locator('.mpicker__item').first().boundingBox()
cek('Mobile: item >=44px (mudah disentuh)', itemBox && itemBox.height >= 44,
  itemBox ? Math.round(itemBox.height) + 'px' : '')
cek('Mobile: tanpa scroll horizontal',
  !(await p.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2)))

await p.screenshot({ path: 'l-m-menu.png' })
await p.locator('.mpicker__item').filter({ hasText: 'Cepat' }).first().click()
await p.waitForTimeout(900)
cek('Mobile: pilihan tersimpan', (await pm.getAttribute('aria-label'))?.includes('Cepat'))
await p.screenshot({ path: 'l-m-composer.png' })

await mob.close()
await browser.close()

const gagal = hasil.filter((r) => !r.ok)
console.log(`\n=== ${hasil.length - gagal.length}/${hasil.length} lulus ===`)
if (gagal.length) console.log('GAGAL:\n - ' + gagal.map((g) => g.nama).join('\n - '))
