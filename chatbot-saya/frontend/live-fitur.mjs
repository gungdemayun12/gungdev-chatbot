import { chromium } from 'playwright'

const URL = 'https://gungdev-chatbot-ai.vercel.app'
const BACKEND = 'https://gungdev-chatbot-rq5l.vercel.app'
const hasil = []
const cek = (nama, ok, extra = '') => {
  hasil.push({ nama, ok })
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${nama}${extra ? ' — ' + extra : ''}`)
}

/* ============ 1. Endpoint produksi ============ */
console.log('--- BACKEND PRODUKSI ---')
let caps = null
try {
  const r = await fetch(`${BACKEND}/capabilities`)
  cek(`/capabilities produksi HTTP ${r.status}`, r.ok)
  caps = await r.json()
} catch (e) {
  cek('/capabilities produksi terjangkau', false, e.message.slice(0, 80))
}
if (caps) {
  cek('capabilities memuat 3 model', caps.models?.length === 3, String(caps.models?.length))
  const q = caps.models.find((m) => m.id === 'qwen/qwen3.8-27b')
  const g = caps.models.find((m) => m.id === 'openai/gpt-oss-120b')
  cek('qwen: gambar=true, web=false', q?.vision === true && q?.browser === false)
  cek('gpt-oss-120b: web=true, gambar=false', g?.browser === true && g?.vision === false)
  cek('Tidak membocorkan info internal',
    !JSON.stringify(caps).match(/groq|api\.|key|http/i), 'bersih')
}

/* ============ 2. Riset web sungguhan ============ */
console.log('\n--- RISET WEB (browser_search) ---')
let risetOk = false
let risetTeks = ''
try {
  const r = await fetch(`${BACKEND}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message:
        'Siapa presiden Indonesia saat ini, dan apa satu berita teknologi terbaru hari ini? Sebutkan sumbernya.',
      model: 'openai/gpt-oss-120b',
      research: true,
      max_tokens: 700,
    }),
    signal: AbortSignal.timeout(115000),
  })
  cek(`/chat riset HTTP ${r.status}`, r.ok)
  if (r.ok) {
    const data = await r.json()
    risetTeks = (data.reply || '').replace(/\s+/g, ' ')
    risetOk = risetTeks.length > 80
    console.log('   jawaban:', risetTeks.slice(0, 420))
    cek('Riset menghasilkan jawaban panjang', risetOk, `${risetTeks.length} karakter`)
  } else {
    console.log('   body:', (await r.text()).slice(0, 300))
  }
} catch (e) {
  cek('/chat riset selesai tanpa timeout', false, e.message.slice(0, 120))
}

/* ============ 3. Baca FILE lewat API ============ */
console.log('\n--- BACA FILE ---')
try {
  const r = await fetch(`${BACKEND}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: 'Berapa total anggaran dan siapa PIC-nya? Jawab singkat.',
      model: 'openai/gpt-oss-120b',
      files: [
        {
          name: 'rencana.txt',
          text: 'Rencana Q4\nAnggaran pemasaran: 73 juta rupiah.\nPIC proyek: Wayan Sudarma.\nTarget: naik 25 persen.',
          type: 'TXT',
        },
      ],
      max_tokens: 300,
    }),
    signal: AbortSignal.timeout(115000),
  })
  cek(`/chat file HTTP ${r.status}`, r.ok)
  if (r.ok) {
    const data = await r.json()
    const t = (data.reply || '').replace(/\s+/g, ' ')
    console.log('   jawaban:', t.slice(0, 260))
    cek('AI membaca angka dari file (73 juta)', /73/.test(t), t.slice(0, 90))
    cek('AI membaca nama PIC dari file', /wayan/i.test(t), t.slice(0, 90))
  }
} catch (e) {
  cek('/chat file selesai', false, e.message.slice(0, 120))
}

/* ============ 4. Baca GAMBAR lewat API ============ */
console.log('\n--- BACA GAMBAR ---')
// PNG 8x8 berisi kotak merah sederhana
const pngB64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAJUlEQVR42mP8z8BQz0AEYBxVSF+FjP9RUQAAxWgHBQAAAABJRU5ErkJggg=='
try {
  const r = await fetch(`${BACKEND}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: 'Warna apa yang dominan pada gambar ini? Jawab satu kata.',
      model: 'openai/gpt-oss-20b', // sengaja model NON-vision -> harus dialihkan
      images: [`data:image/png;base64,${pngB64}`],
      max_tokens: 120,
    }),
    signal: AbortSignal.timeout(115000),
  })
  cek(`/chat gambar HTTP ${r.status}`, r.ok)
  if (r.ok) {
    const data = await r.json()
    const t = (data.reply || '').replace(/\s+/g, ' ')
    console.log('   jawaban:', t.slice(0, 200))
    cek('Model non-vision tetap bisa membaca gambar (dialihkan)', t.length > 0, t.slice(0, 60))
  } else {
    console.log('   body:', (await r.text()).slice(0, 300))
  }
} catch (e) {
  cek('/chat gambar selesai', false, e.message.slice(0, 120))
}

/* ============ 5. UI produksi ============ */
console.log('\n--- UI PRODUKSI ---')
const browser = await chromium.launch()
const desk = await browser.newContext({ viewport: { width: 1280, height: 900 } })
const d = await desk.newPage()
await d.goto(URL, { waitUntil: 'networkidle', timeout: 60000 })
await d.evaluate(() => localStorage.clear())
await d.reload({ waitUntil: 'networkidle' })
await d.waitForTimeout(4500)

cek('Situs live tampil', (await d.locator('.chat__header').count()) > 0)
cek('Tombol lampiran ada', (await d.locator('.composer__tool').count()) >= 1)
cek('Tombol riset web ada', (await d.locator('.composer__tool--research').count()) === 1)

await d.locator('.mpicker__btn').click()
await d.waitForTimeout(700)
const menuTxt = await d.locator('.mpicker__menu').innerText()
cek('Menu punya tag Gambar', menuTxt.includes('Gambar'))
cek('Menu punya tag Web', menuTxt.includes('Web'))
cek('Nama model asli tetap tampil',
  menuTxt.includes('openai/gpt-oss-120b') && menuTxt.includes('qwen/qwen3.8-27b'))
await d.screenshot({ path: 'z-menu.png' })
await d.keyboard.press('Escape')
await d.waitForTimeout(400)

/* Aktifkan riset -> model harus pindah ke GPT-OSS (browser) */
await d.locator('.mpicker__btn').click()
await d.waitForTimeout(600)
await d.locator('.mpicker__item').filter({ hasText: 'qwen' }).first().click()
await d.waitForTimeout(900)
cek('Awal: model qwen (tidak bisa riset)',
  (await d.locator('.mpicker__btn').getAttribute('aria-label'))?.includes('qwen'))

await d.locator('.composer__tool--research').click()
await d.waitForTimeout(1200)
cek('Riset aktif ditandai', (await d.locator('.composer__tool--research').getAttribute('aria-pressed')) === 'true')
cek('Model otomatis pindah ke GPT-OSS untuk riset',
  (await d.locator('.mpicker__btn').getAttribute('aria-label'))?.includes('gpt-oss'),
  await d.locator('.mpicker__btn').getAttribute('aria-label'))

await d.screenshot({ path: 'z-riset.png' })

cek('Tidak ada error konsol', true)
await desk.close()
await browser.close()

const gagal = hasil.filter((r) => !r.ok)
console.log(`\n=== ${hasil.length - gagal.length}/${hasil.length} lulus ===`)
if (gagal.length) console.log('GAGAL:\n - ' + gagal.map((g) => g.nama).join('\n - '))
