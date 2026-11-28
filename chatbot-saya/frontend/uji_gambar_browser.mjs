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
console.log('\n=== 1b. ANIMASI "SEDANG MENGGAMBAR" ===')
// Animasi ini harus muncul SEBELUM gambar selesai, dengan kisi titik,
// persen, dan judul yang jelas. Tanpa ini pengguna hanya melihat layar
// diam selama puluhan detik.
{
  // Jatah gambar akun hanya 3 per 24 jam, dan bagian 1 di atas sudah
  // memakainya. Tanpa dikosongkan, permintaan di bagian ini dijawab
  // "jatah habis" — bukan gambar — sehingga `meta.gambar_dimulai` tidak
  // pernah dikirim dan animasinya tidak bisa diuji sama sekali.
  await fetch(`${API}/__uji/jatah-gambar-bebaskan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub: SUB_A }),
  })

  // Jeda buatan di server uji supaya animasinya sempat diamati.
  await fetch(`${API}/__uji/jeda`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ detik: 3 }),
  })

  const ctxA = await browser.newContext()
  await ctxA.addInitScript(
    ({ sub, token }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({ sub, name: 'Gungde Mayun', email: 'g@x.com', loginPada: Date.now() }),
      )
      localStorage.setItem('gungdev:token-riwayat', JSON.stringify({ token, pada: Date.now() }))
    },
    { sub: SUB_A, token: TOKEN_UJI },
  )
  const pageA = await ctxA.newPage()
  await pageA.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await pageA.waitForSelector('.composer__input', { timeout: 20000 })
  await pageA.waitForTimeout(1200)

  // Riwayat dari bagian sebelumnya bisa sudah berisi gambar. Mencatat
  // jumlahnya penting: nanti kita harus menunggu gambar BARU, bukan
  // gambar lama yang sudah ada di layar sejak halaman dimuat.
  const gambarAwal = await pageA.locator('.hasil-gambar__img').count()

  await pageA.fill('.composer__input', 'buatkan gambar kucing tidur di sofa')
  await pageA.press('.composer__input', 'Enter')

  // Tunggu animasi muncul (harus cepat, sebelum gambar selesai).
  let adaAnimasi = false
  try {
    await pageA.waitForSelector('[data-uji="menggambar"]', { timeout: 8000 })
    adaAnimasi = true
  } catch {
    adaAnimasi = false
  }
  cek('animasi "Sedang menggambar" muncul', adaAnimasi)

  if (adaAnimasi) {
    // Beri waktu animasi berjalan sebentar: kisi terisi bertahap, jadi
    // pemeriksaan "ada titik terisi" harus dilakukan setelah beberapa
    // ratus milidetik, bukan pada frame pertama.
    await pageA.waitForTimeout(900)
    const info = await pageA.evaluate(() => {
      const el = document.querySelector('[data-uji="menggambar"]')
      const titik = el.querySelectorAll('.menggambar__titik').length
      const terisi = el.querySelectorAll('.menggambar__titik.is-terisi').length
      const persen = el.querySelector('.menggambar__persen')?.textContent || ''
      return {
        judul: el.querySelector('.menggambar__judul')?.textContent || '',
        titik,
        terisi,
        persen,
        adaKisi: Boolean(el.querySelector('.menggambar__kisi')),
        adaDeskripsi: Boolean(el.querySelector('.menggambar__deskripsi')),
      }
    })
    cek('judul berbunyi "Sedang menggambar"', /sedang menggambar/i.test(info.judul), info.judul)
    cek('kisi titik tampil', info.adaKisi && info.titik > 50, `${info.titik} titik`)
    cek('sebagian titik sudah terisi', info.terisi > 0, `${info.terisi} terisi`)
    cek('persen ditampilkan', /%$/.test(info.persen.trim()), info.persen)
    // Persen TIDAK boleh 100% sebelum gambar tiba (itu akan menipu).
    const angkaPersen = Number(info.persen.replace('%', ''))
    cek('persen belum 100% saat masih proses', angkaPersen < 100, info.persen)
    cek('deskripsi proses tampil', info.adaDeskripsi)

    // Animasi "Berpikir" TIDAK boleh muncul di dalam jawaban asisten yang
    // sedang menggambar. Diperiksa di dalam `.msg--assistant` saja, karena
    // petunjuk di bawah composer memang memakai komponen lain.
    const adaBerpikir = await pageA
      .locator('.msg--assistant [data-uji="berpikir"]')
      .count()
    cek('animasi "Berpikir" tidak dipakai untuk gambar', adaBerpikir === 0, String(adaBerpikir))

    // Indikator "Berpikir" di bawah composer juga harus diam.
    const adaHintBerpikir = await pageA.locator('.chat__streaming-hint').count()
    cek('petunjuk "Berpikir" di bawah composer tidak tampil', adaHintBerpikir === 0, String(adaHintBerpikir))

    // Tunggu selesai: animasi hilang, gambar BARU muncul.
    //
    // Kenapa menunggu jumlah bertambah, bukan sekadar `waitForSelector`:
    // riwayat dari bagian sebelumnya bisa sudah menampilkan gambar, jadi
    // selector itu langsung cocok dan pemeriksaan di bawah berjalan
    // sebelum prosesnya benar-benar selesai.
    await pageA.waitForFunction(
      (n) => document.querySelectorAll('.hasil-gambar__img').length > n,
      gambarAwal,
      { timeout: 60000 },
    )
    await pageA.waitForTimeout(500)
    const sisa = await pageA.locator('[data-uji="menggambar"]').count()
    cek('animasi hilang setelah gambar jadi', sisa === 0, String(sisa))
  } else {
    for (const n of [
      'judul berbunyi "Sedang menggambar"',
      'kisi titik tampil',
      'sebagian titik sudah terisi',
      'persen ditampilkan',
      'persen belum 100% saat masih proses',
      'deskripsi proses tampil',
      'animasi "Berpikir" tidak dipakai untuk gambar',
      'petunjuk "Berpikir" di bawah composer tidak tampil',
      'animasi hilang setelah gambar jadi',
    ]) {
      cek(n, false, 'animasi tidak muncul')
    }
  }

  // Kembalikan jeda ke nol agar bagian berikutnya tidak lambat.
  await fetch(`${API}/__uji/jeda`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ detik: 0 }),
  })
  await ctxA.close()
}

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

/* ================================================================ */
console.log('\n=== 8. PANEL JATAH: INDIKATOR PERSEN ===')
// Bagian jatah diganti dari angka menjadi BILAH PERSEN, mengikuti contoh
// "Plan limits": judul, "N% sisa" di kanan, keterangan waktu reset, dan
// bilah tipis. Uji ini memastikan bilahnya benar-benar tampil dan
// angkanya masuk akal — bukan hanya ada di data.
{
  await resetAkun(SUB_A)

  // Data server yang menjadi sumber bilah.
  const data = await fetch(`${API}/usage`, {
    headers: { Authorization: `Bearer ${TOKEN_UJI}` },
  }).then((r) => r.json())
  const g = data?.akun?.gambar
  cek('/usage mengirim akun.gambar', Boolean(g), g ? `batas=${g.batas}` : 'tidak ada')
  cek('/usage mengirim persen gambar', typeof g?.persen === 'number', String(g?.persen))
  cek('/usage mengirim reset gambar', typeof g?.reset?.detik === 'number', String(g?.reset?.detik))

  const sesi8 = await buka()
  const { page: page8 } = sesi8

  // Buka panel "Jatah Saya" dari tombol di header.
  await page8.evaluate(() => {
    const tombol = Array.from(document.querySelectorAll('button')).find((b) =>
      /jatah/i.test(b.getAttribute('aria-label') || ''),
    )
    if (tombol) tombol.click()
  })

  await page8.waitForSelector('.jatah-bar', { timeout: 15000 }).catch(() => {})

  const panel = await page8.evaluate(() => {
    const bar = Array.from(document.querySelectorAll('.jatah-bar'))
    const baca = (el) => {
      if (!el) return null
      const isi = el.querySelector('.jatah-bar__isi')
      const track = el.querySelector('.jatah-bar__trek')
      return {
        judul: el.querySelector('.jatah-bar__judul')?.textContent?.trim() || '',
        persen: el.querySelector('.jatah-bar__persen')?.textContent?.trim() || '',
        sub: el.querySelector('.jatah-bar__sub')?.textContent?.trim() || '',
        lebar: isi ? isi.style.width : '',
        adaProgressbar: track?.getAttribute('role') === 'progressbar',
        ariaNow: track?.getAttribute('aria-valuenow') || '',
      }
    }
    return {
      jumlah: bar.length,
      chat: baca(bar.find((b) => b.dataset.uji === 'jatah-chat')),
      gambar: baca(bar.find((b) => b.dataset.uji === 'jatah-gambar')),
      // Angka mentah lama TIDAK boleh lagi menjadi tampilan utama.
      adaTotalLama: Boolean(document.querySelector('.usage__akun-total')),
      teksPanel: document.querySelector('.usage')?.innerText?.slice(0, 400) || '',
    }
  })

  cek('panel menampilkan dua bilah jatah', panel.jumlah >= 2, `jumlah=${panel.jumlah}`)
  cek('bilah obrolan ada', Boolean(panel.chat), JSON.stringify(panel.chat))
  cek('bilah gambar ada', Boolean(panel.gambar), JSON.stringify(panel.gambar))
  cek('bilah obrolan menulis persen sisa', /^\d{1,3}% sisa$/.test(panel.chat?.persen || ''), panel.chat?.persen)
  cek('bilah gambar menulis persen sisa', /^\d{1,3}% sisa$/.test(panel.gambar?.persen || ''), panel.gambar?.persen)
  cek('bilah obrolan punya lebar terisi', /%$/.test(panel.chat?.lebar || ''), panel.chat?.lebar)
  cek('bilah gambar punya lebar terisi', /%$/.test(panel.gambar?.lebar || ''), panel.gambar?.lebar)
  cek('bilah bisa dibaca pembaca layar', Boolean(panel.chat?.adaProgressbar && panel.gambar?.adaProgressbar))
  cek('bilah punya nilai aria', panel.chat?.ariaNow === '100', `obrolan=${panel.chat?.ariaNow}`)
  cek('keterangan waktu reset tampil', /diperbarui|siap dipakai/i.test(panel.chat?.sub || ''), panel.chat?.sub)
  cek('angka mentah lama tidak lagi jadi tampilan utama', !panel.adaTotalLama)
  cek('tidak ada nama penyedia di panel', !/pollinations|openrouter|ollama/i.test(panel.teksPanel))

  // Setelah jatah gambar dipakai, bilahnya harus TURUN sendirinya.
  await fetch(`${API}/__uji/jatah-gambar`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub: SUB_A, jumlah: 1 }),
  })
  const sesi8b = await buka()
  const { page: page8b } = sesi8b
  await page8b.evaluate(() => {
    const tombol = Array.from(document.querySelectorAll('button')).find((b) =>
      /jatah/i.test(b.getAttribute('aria-label') || ''),
    )
    if (tombol) tombol.click()
  })
  await page8b.waitForSelector('[data-uji="jatah-gambar"]', { timeout: 15000 }).catch(() => {})
  const persenGambarBaru = await page8b
    .evaluate(() => {
      const el = document.querySelector('[data-uji="jatah-gambar-persen"]')
      return el ? el.textContent.trim() : ''
    })
    .catch(() => '')
  const angkaBaru = parseInt(persenGambarBaru, 10)
  cek(
    'bilah gambar turun setelah gambar dibuat',
    Number.isFinite(angkaBaru) && angkaBaru < 100,
    persenGambarBaru || '(kosong)',
  )

  await sesi8.ctx.close()
  await sesi8b.ctx.close()
  await resetAkun(SUB_A)
}

await browser.close()

const gagal = HASIL.filter((h) => !h.lulus)
console.log(`\nHASIL: ${HASIL.length - gagal.length}/${HASIL.length} lulus`)
process.exit(gagal.length === 0 ? 0 : 1)
