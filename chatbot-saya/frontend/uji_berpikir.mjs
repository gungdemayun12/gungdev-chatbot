/**
 * uji_berpikir.mjs — memastikan animasi "berpikir" benar-benar tampil,
 * beranimasi, dan jujur mengikuti tahapnya.
 *
 * Yang diuji:
 *   1. Saat AI lambat, animasi berpikir TAMPIL (bukan layar diam).
 *   2. Titik-titiknya BERANIMASI (punya animation, bukan gambar statis).
 *   3. Label tahapnya sesuai fase ('Berpikir' / 'Menelusuri').
 *   4. Ada penghitung detik setelah beberapa saat (bukti masih hidup).
 *   5. Muncul kalimat penenang saat menunggu lama.
 *   6. Saat jawaban mulai mengalir, animasi HILANG dan teks muncul.
 *   7. Saat riset web, label berubah menjadi 'Menelusuri'.
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const SUB_A = '100000000000000001'
const TOKEN_A = 'token-akun-a'

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

async function aturJeda(detik) {
  await fetch(`${API}/__uji/jeda`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ detik }),
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
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.evaluate(async (t) => {
    const mod = await import('/src/lib/riwayat.js')
    mod.setTokenRiwayat(t)
  }, TOKEN_A)
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  return { ctx, page }
}

async function kirim(page, teks) {
  await page.fill('.composer__input', teks)
  await page.click('.composer__send')
}

async function jalankan() {
  const browser = await chromium.launch()
  await resetAkun(SUB_A)
  // Jawaban ditahan 14 detik agar animasi & kalimat penenang (muncul
  // setelah 8 detik) sempat diamati.
  await aturJeda(14)

  const { ctx, page } = await bukaMasuk(browser)
  await page.waitForTimeout(1200)

  /* ============ 1. ANIMASI TAMPIL SAAT AI LAMBAT ============ */
  console.log('\n=== 1. ANIMASI BERPIKIR TAMPIL ===')
  await kirim(page, 'Tolong jelaskan sesuatu yang butuh waktu lama')

  const animasi = await page
    .waitForSelector('[data-uji="berpikir"]:not(.berpikir--ringkas)', { timeout: 10000 })
    .catch(() => null)
  cek('Animasi berpikir muncul selama menunggu', Boolean(animasi))

  const teksAnimasi = animasi ? (await animasi.textContent()) || '' : ''
  cek(
    'Menampilkan label tahap (Berpikir)',
    /Berpikir/i.test(teksAnimasi),
    teksAnimasi.slice(0, 80).replace(/\n/g, ' | '),
  )
  cek(
    'Menampilkan keterangan tahap',
    /Menimbang jawaban/i.test(teksAnimasi),
    teksAnimasi.slice(0, 120).replace(/\n/g, ' | '),
  )

  /* ---- Titik-titiknya benar-benar beranimasi ---- */
  const anim = await page.$$eval(
    '[data-uji="berpikir"]:not(.berpikir--ringkas) .berpikir__titik i',
    (els) =>
      els.map((el) => {
        const s = getComputedStyle(el)
        return {
          nama: s.animationName,
          durasi: s.animationDuration,
          lebar: s.width,
        }
      }),
  )
  cek('Ada 3 titik animasi', anim.length === 3, `${anim.length} titik`)
  cek(
    'Titik memakai animasi CSS (bukan statis)',
    anim.length > 0 && anim.every((a) => a.nama && a.nama !== 'none'),
    anim.map((a) => a.nama).join(','),
  )
  cek(
    'Animasi punya durasi berjalan',
    anim.every((a) => parseFloat(a.durasi) > 0),
    anim.map((a) => a.durasi).join(','),
  )

  /* ---- Label berkilau (menandakan "hidup") ---- */
  const kilau = await page.$eval(
    '[data-uji="berpikir"] .berpikir__label',
    (el) => getComputedStyle(el).animationName,
  )
  cek('Label tahap berkilau (beranimasi)', kilau && kilau !== 'none', String(kilau))

  /* ============ 2. PENGHITUNG DETIK & KALIMAT TENANG ============ */
  console.log('\n=== 2. PENANDA MASIH BERJALAN ===')
  await page.waitForTimeout(6000)
  const teksSetelah6 =
    (await page.textContent('[data-uji="berpikir"]:not(.berpikir--ringkas)').catch(() => '')) || ''
  cek(
    'Muncul penghitung detik setelah beberapa saat',
    /\d+\s*dtk/.test(teksSetelah6),
    teksSetelah6.slice(0, 120).replace(/\n/g, ' | '),
  )

  // Kalimat penenang muncul setelah 8 detik menunggu.
  const adaTenang = await page
    .waitForSelector(
      '[data-uji="berpikir"]:not(.berpikir--ringkas) [data-uji="berpikir-tenang"]',
      { timeout: 8000 },
    )
    .catch(() => null)
  cek('Muncul kalimat penenang saat menunggu lama', Boolean(adaTenang))
  if (adaTenang) {
    const teksTenang = (await adaTenang.textContent()) || ''
    cek(
      'Kalimat penenang tidak menakut-nakuti',
      !/gagal|error|macet|berhenti paksa/i.test(teksTenang),
      teksTenang.slice(0, 80),
    )
  }
  /* ============ 3. ANIMASI HILANG SAAT JAWABAN MENGALIR ============ */
  console.log('\n=== 3. ANIMASI HILANG SAAT JAWABAN MUNCUL ===')
  await page.waitForSelector('.msg--assistant .msg__content', { timeout: 25000 })
  await page.waitForTimeout(600)

  const masihAdaAnimasi = await page.$('.msg--assistant [data-uji="berpikir"]')
  cek('Animasi hilang setelah jawaban mulai mengalir', !masihAdaAnimasi)

  const teksJawaban = (await page.textContent('.msg--assistant .msg__content')) || ''
  cek(
    'Jawaban benar-benar tampil',
    /Jawaban untuk/i.test(teksJawaban),
    teksJawaban.slice(0, 60),
  )

  /* Hint bawah juga harus hilang saat selesai. */
  await page.waitForTimeout(2500)
  const hintTersisa = await page.$('.chat__streaming-hint')
  cek('Hint bawah hilang setelah selesai', !hintTersisa)

  /* ============ 3b. PESAN KEDUA (REGRESI) ============
     Bug nyata: setelah jawaban pertama selesai, mengirim pesan lagi TIDAK
     memunculkan animasi di area chat — layar terlihat kosong/diam.
     Penyebabnya `streamingId` masih menyimpan ID jawaban lama sehingga
     dianggap "sudah ada jawaban". Uji ini mengunci perilakunya. */
  console.log('\n=== 3b. ANIMASI MUNCUL LAGI SAAT PESAN KEDUA ===')
  await aturJeda(8)
  await kirim(page, 'Pertanyaan kedua yang juga butuh waktu')
  await page.waitForTimeout(1500)

  const animasiKedua = await page.$('[data-uji="berpikir"]:not(.berpikir--ringkas)')
  cek('Animasi tampil lagi saat pesan kedua dikirim', Boolean(animasiKedua))
  if (animasiKedua) {
    const teksKedua = (await animasiKedua.textContent()) || ''
    cek(
      'Label tahap tetap terbaca di pesan kedua',
      /Berpikir|Menelusuri|Menyusun/.test(teksKedua),
      teksKedua.slice(0, 60).replace(/\n/g, ' | '),
    )
  }

  // Tunggu sampai balon asisten TERAKHIR berisi jawaban DAN animasi hilang
  // dari DOM (bukan sekadar "sudah ada teks"), agar tidak balapan waktu.
  await page
    .waitForFunction(
      () => {
        const balon = Array.from(document.querySelectorAll('.msg--assistant'))
        const last = balon[balon.length - 1]
        const adaIsi = Boolean(last && last.querySelector('.msg__content'))
        const masihAnimasi = Boolean(
          document.querySelector('[data-uji="berpikir"]:not(.berpikir--ringkas)'),
        )
        return adaIsi && !masihAnimasi
      },
      { timeout: 25000 },
    )
    .catch(() => {})
  const setelahKedua = await page.$('[data-uji="berpikir"]:not(.berpikir--ringkas)')
  cek('Animasi hilang lagi setelah jawaban kedua muncul', !setelahKedua)

  // Tombol riset baru muncul setelah streaming selesai; tunggu sebentar.
  await page.waitForSelector('.composer__tool--research', { timeout: 10000 }).catch(() => {})
  await aturJeda(6)

  /* ============ 4. RISET WEB: LABEL BERUBAH ============ */
  console.log('\n=== 4. LABEL RISET WEB ===')
  await aturJeda(6)
  // Aktifkan mode riset web lalu kirim pesan.
  const tombolRiset = await page.$(
    '.composer__tool--research, [aria-label="Aktifkan riset web"]',
  )
  cek('Tombol riset web tersedia', Boolean(tombolRiset))
  if (tombolRiset) {
    await tombolRiset.click()
    await page.waitForTimeout(300)
    await kirim(page, 'Cari informasi terbaru di web')

    const animasiRiset = await page
      .waitForSelector('[data-uji="berpikir"]:not(.berpikir--ringkas)', { timeout: 10000 })
      .catch(() => null)
    const teksRiset = animasiRiset ? (await animasiRiset.textContent()) : ''
    cek(
      'Saat riset, label menjadi "Menelusuri"',
      /Menelusuri/i.test(teksRiset),
      teksRiset.slice(0, 90).replace(/\n/g, ' | '),
    )
    cek(
      'Menjelaskan sedang mencari di web',
      /Mencari di web/i.test(teksRiset),
      teksRiset.slice(0, 120).replace(/\n/g, ' | '),
    )
    const kelasRiset = animasiRiset
      ? await animasiRiset.evaluate((el) => el.className)
      : ''
    cek('Memakai gaya riset (is-research)', /is-research/.test(kelasRiset), kelasRiset)
  }

  await page.waitForTimeout(9000)
  await aturJeda(0)
  await resetAkun(SUB_A)
  await ctx.close()
  await browser.close()

  console.log('\n' + '='.repeat(62))
  const lulus = HASIL.filter((h) => h.lulus).length
  console.log(`HASIL: ${lulus}/${HASIL.length} lulus`)
  console.log('='.repeat(62))
  HASIL.filter((h) => !h.lulus).forEach((h) => console.log(`  GAGAL: ${h.nama}`))
  process.exit(lulus === HASIL.length ? 0 : 1)
}

jalankan().catch(async (e) => {
  console.error('Uji gagal dijalankan:', e)
  await aturJeda(0).catch(() => {})
  process.exit(2)
})
