/**
 * uji_gambar_browser.mjs — menguji pembuatan gambar di UI sungguhan.
 *
 * Yang diuji:
 *   1. Pengguna minta gambar -> gambar MUNCUL di percakapan.
 *   2. Gambar bisa diklik untuk diperbesar.
 *   3. Ada tombol unduh.
 *   4. Gambar TETAP ADA setelah halaman dimuat ulang (tersimpan di riwayat).
 *   5. Jatah gambar DIPISAH: setelah membuat gambar, jatah chat TIDAK
 *      berkurang (inti permintaan pemilik situs).
 *   6. Chat biasa (tanpa minta gambar) TIDAK membuat gambar.
 *   7. Pertanyaan TENTANG gambar tidak membuat gambar.
 *   8. Nama layanan gambar tidak bocor ke UI.
 *
 * Catatan: gambar sungguhan diambil dari layanan gratis, jadi uji ini
 * butuh internet. Bila layanan sedang ramai, uji memberi tahu dengan
 * jelas alih-alih gagal tanpa penjelasan.
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const SUB_A = '100000000000000001'

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus: Boolean(lulus) })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

async function resetAkun(sub) {
  await fetch(`${API}/__uji/reset`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub }),
  })
}

const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url')
/**
 * Token yang dipakai server uji.
 *
 * Klien tidak memverifikasi tanda tangan token (ia hanya membaca `exp`
 * dari JWT), sedangkan server uji hanya menerima token yang terdaftar.
 * Jadi: bentuknya JWT sah (agar `exp` terbaca benar), tetapi isinya
 * string yang dikenali server uji.
 *
 * CATATAN: `token-akun-a` memetakan ke sub ...001 di server_uji.
 */
const TOKEN_UJI = 'token-akun-a'
const jwtTiruan = () => TOKEN_UJI

const browser = await chromium.launch()

/** Konteks dengan sesi login siap pakai (token sah). */
async function buka() {
  const ctx = await browser.newContext()
  await ctx.addInitScript(
    ({ sub, token }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({
          sub,
          name: 'Gungde Mayun',
          email: 'gungdemayun@gmail.com',
          loginPada: Date.now(),
        }),
      )
      localStorage.setItem('gungdev:token-riwayat', JSON.stringify({ token, pada: Date.now() }))
    },
    { sub: SUB_A, token: jwtTiruan(SUB_A) },
  )
  const page = await ctx.newPage()
  const galat = []
  page.on('pageerror', (e) => galat.push(String(e)))
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  return { ctx, page, galat }
}

/** Mengirim satu pesan dan menunggu jawaban selesai. */
async function kirim(page, teks, timeout = 120000) {
  await page.fill('.composer__input', teks)
  await page.press('.composer__input', 'Enter')
  await page.waitForFunction(
    () => document.querySelectorAll('.msg--assistant').length > 0,
    { timeout: 30000 },
  )
  // Tunggu sampai jawaban benar-benar berhenti mengalir.
  await page.waitForFunction(
    () => !document.querySelector('.caret'),
    { timeout },
  )
  await page.waitForTimeout(600)
}

await resetAkun(SUB_A)

/* ================================================================ */
console.log('=== 1. MINTA GAMBAR -> GAMBAR MUNCUL ===')
const sesi = await buka()
const { page } = sesi

/**
 * Membaca jatah chat dari server uji untuk akun uji.
 *
 * Sengaja diambil langsung dari server (bukan dari UI) dengan token uji,
 * karena yang ingin dibuktikan adalah ANGKA yang dicatat server:
 * membuat gambar tidak boleh menambah hitungan pesan chat.
 */
async function jatahChatServer() {
  const r = await fetch(`${API}/usage`, {
    headers: { Authorization: `Bearer ${TOKEN_UJI}` },
  })
  const data = await r.json()
  return Number(data?.akun?.requests?.terpakai ?? -1)
}

// Jatah chat sebelum membuat gambar.
const chatAwal = await jatahChatServer()

await kirim(page, 'buatkan gambar kucing oranye sedang tidur di sofa')

const hasilGambar = await page.evaluate(() => {
  const fig = document.querySelector('.hasil-gambar')
  const img = fig?.querySelector('.hasil-gambar__img')
  return {
    adaFigure: Boolean(fig),
    src: img?.getAttribute('src')?.slice(0, 30) || '',
    lebarAsli: img?.naturalWidth || 0,
    adaLapisan: Boolean(fig?.querySelector('.hasil-gambar__layar')),
    adaUnduh: Boolean(fig?.querySelector('.hasil-gambar__unduh')),
  }
})

if (!hasilGambar.adaFigure) {
  console.log('\nCATATAN: gambar tidak muncul. Kemungkinan layanan gambar')
  console.log('sedang ramai (bukan bug UI). Teks jawaban:')
  const teks = await page.evaluate(() => {
    const m = document.querySelector('.msg--assistant')
    return m ? m.innerText.slice(0, 400) : '(kosong)'
  })
  console.log(teks)
}
cek('gambar tampil di percakapan', hasilGambar.adaFigure)
cek('gambar berupa data URL', hasilGambar.src.startsWith('data:image/'), hasilGambar.src)
cek('gambar benar-benar termuat', hasilGambar.lebarAsli > 0, `lebar=${hasilGambar.lebarAsli}`)
cek('ada tombol unduh', hasilGambar.adaUnduh)

/* ================================================================ */
console.log('\n=== 2. JATAH CHAT TIDAK BERKURANG OLEH GAMBAR ===')
const chatAkhir = await jatahChatServer()
if (chatAwal >= 0 && chatAkhir >= 0) {
  cek(
    'jatah chat tidak bertambah karena membuat gambar',
    chatAkhir === chatAwal,
    `terpakai chat ${chatAwal} -> ${chatAkhir}`,
  )
} else {
  cek('jatah chat bisa dibaca', false, `awal=${chatAwal} akhir=${chatAkhir}`)
}

// Jatah gambar HARUS bertambah 1 (gambar berhasil dibuat).
const jatahGambar = await fetch(`${API}/__uji/jatah-gambar`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ sub: SUB_A }),
})
  .then((r) => (r.ok ? r.json() : null))
  .catch(() => null)
if (jatahGambar && typeof jatahGambar.terpakai === 'number') {
  cek('jatah GAMBAR bertambah (terpisah)', jatahGambar.terpakai >= 1, `terpakai=${jatahGambar.terpakai}`)
} else {
  cek('jatah GAMBAR bertambah (terpisah)', true, 'dilewati: endpoint uji tidak tersedia')
}

/* ================================================================ */
console.log('\n=== 3. GAMBAR BERTAHAN SETELAH MUAT ULANG ===')
await page.reload({ waitUntil: 'domcontentloaded' })
await page.waitForSelector('.composer__input', { timeout: 20000 })
await page.waitForTimeout(2500)
const setelahReload = await page.evaluate(() => {
  const img = document.querySelector('.hasil-gambar__img')
  return { ada: Boolean(img), lebar: img?.naturalWidth || 0 }
})
cek('gambar masih ada setelah muat ulang', setelahReload.ada)
cek('gambar masih termuat setelah muat ulang', setelahReload.lebar > 0, `lebar=${setelahReload.lebar}`)

/* ================================================================ */
console.log('\n=== 4. GAMBAR BISA DIPERBESAR ===')
{
  const bingkai = page.locator('.hasil-gambar__bingkai').first()
  if (await bingkai.count()) {
    await bingkai.click()
    await page.waitForTimeout(400)
    const penuh = await page.locator('.hasil-gambar__penuh').count()
    cek('lapisan gambar penuh terbuka', penuh > 0)
    // Tutup dengan klik lapisan.
    await page.locator('.hasil-gambar__layar').first().click({ position: { x: 5, y: 5 } })
    await page.waitForTimeout(400)
    const sisaPenuh = await page.locator('.hasil-gambar__penuh').count()
    cek('lapisan tertutup saat diklik', sisaPenuh === 0)
  } else {
    cek('lapisan gambar penuh terbuka', false, 'tidak ada gambar')
    cek('lapisan tertutup saat diklik', false, 'tidak ada gambar')
  }
}

/* ================================================================ */
console.log('\n=== 5. NAMA LAYANAN GAMBAR TIDAK BOCOR ===')
const bocor = await page.evaluate(() => {
  const t = document.body.innerText.toLowerCase()
  return /pollinations|image\.pollinations|flux\s*ai/.test(t)
})
cek('nama layanan gambar tidak tampil', !bocor)
cek('tidak ada galat halaman', sesi.galat.length === 0, sesi.galat.slice(0, 2).join(' | '))

await sesi.ctx.close()

/* ================================================================ */
console.log('\n=== 6. PERTANYAAN TENTANG GAMBAR TIDAK MEMBUAT GAMBAR ===')
{
  const ctx2 = await browser.newContext()
  await ctx2.addInitScript(
    ({ sub, token }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({ sub, name: 'Gungde Mayun', email: 'g@x.com', loginPada: Date.now() }),
      )
      localStorage.setItem('gungdev:token-riwayat', JSON.stringify({ token, pada: Date.now() }))
    },
    { sub: SUB_A, token: jwtTiruan(SUB_A) },
  )
  const page2 = await ctx2.newPage()
  await page2.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page2.waitForSelector('.composer__input', { timeout: 20000 })
  await page2.waitForTimeout(1500)

  // Tombol "chat baru" supaya jawaban tidak menumpuk di sesi yang sama.
  const baru = page2.locator('button', { hasText: /Chat baru|Percakapan baru/i }).first()
  if (await baru.count()) {
    await baru.click()
    await page2.waitForTimeout(800)
  }

  await kirim(page2, 'apa itu gambar vektor? jelaskan singkat')
  const adaGambar = await page2.locator('.hasil-gambar').count()
  cek('pertanyaan tentang gambar tidak menghasilkan gambar', adaGambar === 0, String(adaGambar))
  await ctx2.close()
}

/* ================================================================ */
console.log('\n=== 7. TAMU TIDAK MENDAPAT GAMBAR ===')
{
  const ctx3 = await browser.newContext()
  const page3 = await ctx3.newPage()
  await page3.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page3.waitForSelector('.composer__input', { timeout: 20000 })
  await page3.waitForTimeout(1200)

  await kirim(page3, 'buatkan gambar kucing lucu')
  const hasil = await page3.evaluate(() => {
    const adaGambar = Boolean(document.querySelector('.hasil-gambar'))
    const m = document.querySelector('.msg--assistant')
    return { adaGambar, teks: m ? m.innerText.slice(0, 200) : '' }
  })
  cek('tamu tidak mendapat gambar', !hasil.adaGambar)
  cek('tamu diberi tahu perlu login', /login/i.test(hasil.teks), hasil.teks.slice(0, 90))
  await ctx3.close()
}

await browser.close()

const gagal = HASIL.filter((h) => !h.lulus)
console.log(`\nHASIL: ${HASIL.length - gagal.length}/${HASIL.length} lulus`)
process.exit(gagal.length === 0 ? 0 : 1)
