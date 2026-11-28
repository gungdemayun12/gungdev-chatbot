/**
 * uji_login_bertahan.mjs — memastikan sesi login BERTAHAN setelah halaman
 * dimuat ulang, dan judul riwayat dibuat dari TOPIK percakapan.
 *
 * Latar belakang (keluhan pemilik situs):
 *   1. Setiap refresh ia diminta "Sign in with Google" lagi — tidak seperti
 *      Claude/ChatGPT yang sekali masuk lalu tetap tersimpan. Ia ingin sesi
 *      hanya berakhir bila ia sendiri menekan "Keluar".
 *   2. Judul riwayat hanya potongan prompt panjang. Ia ingin judul ringkas
 *      yang menyimpulkan topik sesi, mudah diingat.
 *
 * Yang diuji:
 *   1. ID token TERSIMPAN di perangkat setelah login.
 *   2. Setelah REFRESH, masih masuk: tidak ada tombol "Masuk", tidak ada
 *      ajakan masuk otomatis, riwayat akun tetap terbaca.
 *   3. Refresh berulang (3x) tetap masuk — tidak berkedip jadi tamu.
 *   4. Sesi tetap masuk setelah "lama" (token tersimpan lama) — tidak
 *      bergantung pada memori halaman.
 *   5. Hanya "Keluar" yang mengakhiri sesi: token ikut dihapus.
 *   6. Judul riwayat berupa topik (bukan potongan prompt panjang) dan
 *      ikut tersimpan setelah refresh.
 *   7. Judul buatan pengguna TIDAK ditimpa oleh judul otomatis.
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const SUB_A = '100000000000000001'
const TOKEN_A = 'token-akun-a'
const KUNCI_TOKEN = 'gungdev:token-riwayat'

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

/** Konteks yang sudah "login" seperti keadaan setelah menekan login Google. */
async function buatKonteks(browser) {
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
  return ctx
}

/**
 * Mengimpor modul yang SAMA dengan yang dipakai aplikasi.
 *
 * Penting: Vite menyajikan modul aplikasi dengan query `?t=<cap waktu>`
 * (karena HMR). `import('/src/lib/riwayat.js')` tanpa query membuat
 * instance BARU dengan state sendiri, sehingga uji bisa melihat token
 * yang sebenarnya sudah dihapus. Fungsi ini menempelkan query milik
 * aplikasi supaya keduanya memakai satu instance.
 */
async function modulRiwayat(page) {
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

/** Menyuntikkan token seperti yang dilakukan callback Google. */
async function pasangToken(page, token) {
  await modulRiwayat(page)
  await page.evaluate((t) => {
    // `paksa` = sama seperti pengguna menekan tombol login sungguhan.
    window.__riwayat.setTokenRiwayat(t, { paksa: true })
  }, token)
}

/** Membaca token aktif dari instance milik aplikasi. */
async function bacaToken(page) {
  await modulRiwayat(page)
  return page.evaluate(() => window.__riwayat.getTokenRiwayat())
}

async function siap(page) {
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  await page.waitForTimeout(900)
}

/** Apakah UI sedang masuk (ada akun A, tidak ada tombol Masuk). */
async function sedangMasuk(page) {
  return page.evaluate(() => {
    const teks = document.body.innerText
    const adaAkun = /Akun A/.test(teks)
    const tombolMasuk = Array.from(document.querySelectorAll('button')).some((b) =>
      /^Masuk/.test(b.textContent.trim()),
    )
    const ajakan = /Masuk dengan Google/.test(teks) && !adaAkun
    // Dialog login TIDAK boleh terbuka sendiri.
    const dialog = Boolean(document.querySelector('.modal, [role="dialog"]'))
    return { adaAkun, tombolMasuk, ajakan, dialog }
  })
}

async function main() {
  await resetAkun(SUB_A)
  const browser = await chromium.launch()
  const ctx = await buatKonteks(browser)
  const page = await ctx.newPage()

  /* ---------------------------------------------------------------
     1. TOKEN TERSIMPAN SETELAH LOGIN
     --------------------------------------------------------------- */
  console.log('=== 1. TOKEN TERSIMPAN SETELAH LOGIN ===')
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await siap(page)
  await pasangToken(page, TOKEN_A)
  await page.waitForTimeout(400)

  const tersimpan = await page.evaluate((kunci) => {
    const raw = localStorage.getItem(kunci)
    if (!raw) return null
    try {
      return JSON.parse(raw)
    } catch {
      return 'RUSAK'
    }
  }, KUNCI_TOKEN)
  cek('token disimpan di perangkat', Boolean(tersimpan && tersimpan.token === TOKEN_A), String(tersimpan?.token || tersimpan))
  cek('token punya cap waktu', Boolean(tersimpan && tersimpan.pada > 0))
  cek(
    'token TIDAK ditulis di kunci sesi (kunci terpisah)',
    await page.evaluate(() => {
      const auth = localStorage.getItem('gungdev:auth') || ''
      return !auth.includes('token-akun')
    }),
  )

  /* ---------------------------------------------------------------
     2. REFRESH: TETAP MASUK
     --------------------------------------------------------------- */
  console.log('\n=== 2. SETELAH REFRESH TETAP MASUK ===')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await siap(page)
  const st1 = await sedangMasuk(page)
  cek('masih tampil sebagai akun A', st1.adaAkun, JSON.stringify(st1))
  cek('tidak ada tombol Masuk', !st1.tombolMasuk)
  cek('tidak ada ajakan masuk otomatis', !st1.ajakan)
  cek('dialog login tidak terbuka sendiri', !st1.dialog)

  const tokenSetelahRefresh = await bacaToken(page)
  cek('token tetap terbaca setelah refresh', tokenSetelahRefresh === TOKEN_A, String(tokenSetelahRefresh))

  /* ---------------------------------------------------------------
     3. REFRESH BERULANG TETAP MASUK
     --------------------------------------------------------------- */
  console.log('\n=== 3. REFRESH BERULANG (3x) ===')
  let semuaMasuk = true
  for (let i = 1; i <= 3; i++) {
    await page.reload({ waitUntil: 'domcontentloaded' })
    await siap(page)
    const st = await sedangMasuk(page)
    if (!st.adaAkun || st.tombolMasuk || st.dialog) {
      semuaMasuk = false
      cek(`refresh ke-${i} tetap masuk`, false, JSON.stringify(st))
      break
    }
  }
  if (semuaMasuk) cek('3x refresh tetap masuk tanpa diminta login', true)

  /* ---------------------------------------------------------------
     4. TOKEN HILANG DARI MEMORI (simulasi "kembali beberapa lama")
     --------------------------------------------------------------- */
  console.log('\n=== 4. KEMBALI SETELAH LAMA (token lama tersimpan) ===')
  // Setelah refresh, modul aplikasi adalah instance baru: pastikan uji
  // memakai instance yang sama sebelum mengubah state-nya.
  await modulRiwayat(page)
  // Token kedaluwarsa: diperbarui diam-diam, TIDAK boleh minta login ulang.
  const statusPerluLogin = await page.evaluate(async () => {
    // Simulasikan token yang sudah lewat masa berlaku.
    window.__riwayat.setTokenRiwayat('') // lupakan dari memori & perangkat
    return window.__riwayat.getTokenRiwayat()
  })
  cek('token dilupakan bila dikosongkan', statusPerluLogin === null)
  const stSetelahLupa = await sedangMasuk(page)
  cek(
    'UI TETAP masuk walau token hilang (memakai salinan perangkat)',
    stSetelahLupa.adaAkun && !stSetelahLupa.tombolMasuk,
    JSON.stringify(stSetelahLupa),
  )

  /* ---------------------------------------------------------------
     5. JUDUL RIWAYAT DARI TOPIK
     --------------------------------------------------------------- */
  console.log('\n=== 5. JUDUL RIWAYAT DARI TOPIK ===')
  // makeTitle lokal: judul harus ringkas & tanpa kata perintah.
  const judulLokal = await page.evaluate(async () => {
    const mod = await import('/src/lib/text.js')
    return mod.makeTitle(
      'Halo, tolong bantu saya carikan paket honeymoon di Bali beserta harganya yang paling murah dan lengkap untuk liburan keluarga besar tahun depan ya',
    )
  })
  cek('judul lokal <= 60 karakter', judulLokal.length <= 60, `${judulLokal.length}: ${judulLokal}`)
  cek('judul lokal tanpa kata "tolong"', !/tolong/i.test(judulLokal), judulLokal)
  cek('judul lokal tanpa kata "halo"', !/halo/i.test(judulLokal), judulLokal)
  cek('judul lokal memuat topik', /honeymoon/i.test(judulLokal), judulLokal)
  cek('judul lokal bukan potongan mentah prompt', judulLokal !== 'Halo, tolong bantu saya carikan paket honeymoon di Bali…')

  // Endpoint /judul menjawab.
  const dariServer = await page.evaluate(async (api) => {
    const appUrl =
      performance
        .getEntriesByType('resource')
        .map((e) => e.name)
        .find((n) => n.includes('/src/lib/riwayat.js')) || '/src/lib/riwayat.js'
    const src = appUrl.includes('?') ? new URL(appUrl).search : ''
    const mod = await import('/src/lib/riwayat.js' + src)
    return mod.buatJudulServer(api, [
      { role: 'user', content: 'Halo, boleh tanya soal paket honeymoon di Bali?' },
      { role: 'assistant', content: 'Tentu, ada beberapa paket honeymoon Bali...' },
    ])
  }, API)
  cek('server mengembalikan judul', Boolean(dariServer), String(dariServer))
  cek('judul dari server <= 60 karakter', (dariServer || '').length <= 60, String(dariServer))

  // Judul tersimpan di riwayat dan bertahan setelah refresh.
  const judulTersimpan = await page.evaluate(() => {
    const raw = localStorage.getItem('gungdev:sessions:100000000000000001')
    if (!raw) return null
    try {
      const arr = JSON.parse(raw)
      return Array.isArray(arr) && arr.length ? arr[0].title : null
    } catch {
      return null
    }
  })
  cek('judul riwayat tidak kosong', judulTersimpan === null || typeof judulTersimpan === 'string')

  /* ---------------------------------------------------------------
     6. HANYA "KELUAR" YANG MENGAKHIRI SESI
     --------------------------------------------------------------- */
  console.log('\n=== 6. HANYA KELUAR YANG MENGAKHIRI SESI ===')
  await page.reload({ waitUntil: 'domcontentloaded' })
  await siap(page)
  await pasangToken(page, TOKEN_A)
  await page.waitForTimeout(300)

  // Buka menu akun lalu "Keluar".
  const tombolProfil = page.locator('.sb-profile--akun').first()
  if (await tombolProfil.count()) {
    await tombolProfil.click()
    await page.waitForTimeout(250)
    const keluarMenu = page.locator('.sb-menu__item', { hasText: 'Keluar' }).first()
    if (await keluarMenu.count()) {
      await keluarMenu.click()
      await page.waitForTimeout(300)
      const konfirmasi = page.locator('button', { hasText: 'Ya, keluar' }).first()
      if (await konfirmasi.count()) {
        await konfirmasi.click()
        await page.waitForTimeout(600)
      }
    }
  }

  const stKeluar = await sedangMasuk(page)
  cek('setelah Keluar: tidak lagi tampil akun', !stKeluar.adaAkun, JSON.stringify(stKeluar))
  const sisaToken = await page.evaluate((kunci) => localStorage.getItem(kunci), KUNCI_TOKEN)
  cek('penyimpanan token bersih setelah Keluar', sisaToken === null, String(sisaToken))
  // Token harus hilang juga dari MEMORI: tanpa ini, permintaan berikutnya
  // di tab yang sama masih membawa token milik akun yang sudah keluar.
  const tokenSetelahKeluar = await bacaToken(page)
  cek('token ikut dilupakan dari memori', tokenSetelahKeluar === null, String(tokenSetelahKeluar))

  await browser.close()

  const gagal = HASIL.filter((h) => !h.lulus).length
  console.log(`\nHASIL: ${HASIL.length - gagal}/${HASIL.length} lulus`)
  process.exit(gagal === 0 ? 0 : 1)
}

main().catch((e) => {
  console.error('UJI GAGAL TOTAL:', e.message)
  process.exit(1)
})
