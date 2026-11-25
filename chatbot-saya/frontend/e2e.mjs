/**
 * E2E test GungDev — verifikasi runtime di browser sungguhan.
 * Jalankan: node e2e.mjs
 */
import { chromium } from 'playwright'

const URL = 'http://localhost:5173'
const results = []
const check = (name, ok, extra = '') => {
  results.push({ name, ok, extra })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? ' — ' + extra : ''}`)
}

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })

const errors = []
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(m.text())
})
page.on('pageerror', (e) => errors.push('PAGEERROR: ' + e.message))

await page.goto(URL, { waitUntil: 'networkidle' })

// 1. Judul & brand
check('Title halaman = GungDev', (await page.title()) === 'GungDev')
check('Sidebar menampilkan "GungDev"', await page.locator('.sb-brand__name').isVisible())

// 2. Tanpa nama model di header
const headerText = await page.locator('.chat__header').innerText()
check('Header TIDAK menyebut nama model/teknologi',
  !/deepseek|ollama|ditenagai/i.test(headerText), JSON.stringify(headerText))
check('Header ada indikator status', /Online|Offline/.test(headerText))

// 3. Empty state + sapaan serif
check('Empty state: sapaan waktu',
  await page.locator('.empty__greeting').isVisible(),
  await page.locator('.empty__greeting').innerText())
check('Empty state: 4 kartu saran',
  (await page.locator('.suggestion').count()) === 4)

// 4. Tema terang default + token warna
const theme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
check('data-theme terpasang (anti-flash)', theme === 'light' || theme === 'dark', theme)
const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
check('Background krem hangat (#FAF9F5)', bg === 'rgb(250, 249, 245)', bg)

// 5. Kirim pesan + streaming
await page.locator('.composer__input').fill('Balas dengan: **Halo** dunia')
await page.locator('.composer__send').click()

// selama loading tombol stop muncul
await page.waitForSelector('.chat__streaming-hint', { timeout: 15000 }).catch(() => {})
check('Tombol Stop tampil saat streaming', await page.locator('.composer__send--stop').isVisible())

await page.waitForSelector('.msg--assistant .msg__content', { timeout: 180000 })
await page.waitForSelector('.msg__actions', { timeout: 180000 })
await page.waitForTimeout(1200) // beri waktu penyimpanan localStorage

// 5b. PERSISTENSI: reload => riwayat & pesan tetap ada
//     (dilakukan SEBELUM uji markdown yang menimpa localStorage)
await page.reload({ waitUntil: 'networkidle' })
await page.waitForTimeout(800)
check('Riwayat persist setelah reload', (await page.locator('.sb-item').count()) >= 1)
check('Pesan tetap ada setelah reload',
  (await page.locator('.msg--assistant').count()) >= 1)
check('Sidebar: 1 sesi = 1 item riwayat',
  (await page.locator('.sb-item').count()) === 1,
  String(await page.locator('.sb-item').count()))
const title = await page.locator('.sb-item__title').first().innerText()
check('Judul sesi otomatis dari pesan pertama',
  title.length > 0 && title !== 'Percakapan baru', title)
const actions = await page.locator('.msg--assistant .msg-action').count()
check('Aksi AI (Salin/Regen/Suka/Tidak suka) minimal 4', actions >= 4, String(actions))

// 6. Markdown ter-render (bukan ** mentah) — uji deterministik via data injeksi
const mdCheck = await page.evaluate(() => {
  const sessions = [{
    id: 's_md', title: 'Tes Markdown', titleLocked: true, pinned: false,
    createdAt: Date.now(), updatedAt: Date.now(),
    messages: [
      { id: 'm1', role: 'user', content: 'tes', createdAt: Date.now() },
      { id: 'm2', role: 'assistant', createdAt: Date.now(),
        content: 'Ini **tebal** dan *miring*.\n\n```js\nconst a = 1;\n```\n\n<think>rahasia</think>' },
    ],
  }]
  localStorage.removeItem('gungdev:sessions')
  localStorage.setItem('gungdev:sessions', JSON.stringify(sessions))
  localStorage.setItem('gungdev:active-session', 's_md')
  return true
})
await page.reload({ waitUntil: 'networkidle' })
await page.waitForSelector('.msg--assistant .markdown')
const mdHtml = await page.locator('.msg--assistant .markdown').first().innerHTML()
const rawText = await page.locator('.msg--assistant .markdown').first().innerText()
check('Markdown **bold** TIDAK tampil mentah', !rawText.includes('**') && mdCheck, rawText.slice(0, 50))
check('Markdown menghasilkan <strong> & <em>', mdHtml.includes('<strong>') && mdHtml.includes('<em>'))
check('Code block: nama bahasa tampil', (await page.locator('.code-block__lang').innerText()) === 'js')
check('Code block: tombol Salin tampil', await page.locator('.code-copy').isVisible())
check('<think> disembunyikan di panel Proses berpikir',
  !rawText.includes('rahasia') && (await page.locator('.thinking').count()) === 1)

// 6b. Bersihkan injeksi markdown supaya uji berikutnya netral
await page.evaluate(() => localStorage.removeItem('gungdev:sessions'))
await page.evaluate(() => localStorage.removeItem('gungdev:active-session'))

// 7. Dark mode
await page.evaluate(() => localStorage.setItem('gungdev:theme', 'dark'))
await page.reload({ waitUntil: 'networkidle' })
const dtheme = await page.evaluate(() => document.documentElement.getAttribute('data-theme'))
const dbg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor)
check('Dark mode aktif', dtheme === 'dark', dtheme)
check('Background gelap (#1F1E1D)', dbg === 'rgb(31, 30, 29)', dbg)

// 11. Pengaturan: 6 tab
await page.evaluate(() => localStorage.setItem('gungdev:theme', 'light'))
await page.reload({ waitUntil: 'networkidle' })
await page.locator('.sb-footer .icon-btn').click()
await page.waitForSelector('.settings', { timeout: 5000 })
check('Modal Pengaturan terbuka', await page.locator('.modal').isVisible())
check('Pengaturan punya 6 tab', (await page.locator('.settings__tab').count()) === 6)
const tabsText = await page.locator('.settings__tabs').innerText()
check('Tab Lanjutan berisi URL backend',
  /Lanjutan/.test(tabsText))
await page.locator('.settings__tab', { hasText: 'Lanjutan' }).click()
check('Tab Lanjutan: field URL backend tampil',
  await page.locator('#set-api').isVisible())

// Esc menutup modal
await page.keyboard.press('Escape')
await page.waitForSelector('.modal', { state: 'detached', timeout: 5000 })
check('Esc menutup modal', (await page.locator('.modal').count()) === 0)

// 12. Mobile: drawer
await page.setViewportSize({ width: 390, height: 844 })
await page.waitForTimeout(300)
const sidebarVisibleBefore = await page.locator('.sidebar').evaluate(
  (el) => getComputedStyle(el).transform !== 'none' && !el.classList.contains('is-open'),
)
check('Mobile: sidebar tersembunyi (drawer tertutup)', sidebarVisibleBefore)
check('Mobile: hamburger tampil', await page.locator('.chat__menu').isVisible())
await page.locator('.chat__menu').click()
await page.waitForTimeout(350)
check('Mobile: drawer terbuka setelah klik hamburger',
  await page.locator('.sidebar.is-open').isVisible())
check('Mobile: overlay gelap tampil',
  await page.locator('.sb-overlay.is-visible').isVisible())
await page.locator('.sb-overlay').click({ position: { x: 300, y: 400 } })
await page.waitForTimeout(350)
check('Mobile: overlay menutup drawer',
  (await page.locator('.sidebar.is-open').count()) === 0)

// 13. Font input >= 16px (anti zoom iOS)
const fs = await page.locator('.composer__input').evaluate((el) => getComputedStyle(el).fontSize)
check('Font input >= 16px (anti-zoom iOS)', parseFloat(fs) >= 16, fs)

// 14. Tidak ada error konsol
const realErrors = errors.filter((e) => !/favicon|404 \(Not Found\)/i.test(e))
check('Tidak ada error konsol', realErrors.length === 0, realErrors.slice(0, 2).join(' | '))

await page.screenshot({ path: 'e2e-mobile.png', fullPage: false })
await page.setViewportSize({ width: 1280, height: 900 })
await page.waitForTimeout(400)
await page.screenshot({ path: 'e2e-desktop.png', fullPage: false })

await browser.close()

const failed = results.filter((r) => !r.ok)
console.log(`\n=== ${results.length - failed.length}/${results.length} lulus ===`)
if (failed.length) {
  console.log('GAGAL:', failed.map((f) => f.name).join(', '))
  process.exit(1)
}
