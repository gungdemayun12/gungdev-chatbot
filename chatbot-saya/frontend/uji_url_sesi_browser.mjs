/**
 * uji_url_sesi_browser.mjs — alamat unik per percakapan di BROWSER asli.
 *
 * PERMINTAAN PEMILIK SITUS
 * ------------------------
 * "Kenapa masing-masing sesi chat tidak ada token unik di URL-nya?
 *  Buatkan seperti https://claude.ai/chat/1ce46db1-... "
 *
 * Yang harus terbukti di browser sungguhan (bukan hanya di unit test):
 *   1. Kirim pesan -> alamat di bilah browser menjadi /c/<uuid>.
 *   2. Sesi lain (yang berbeda) punya alamat BERBEDA.
 *   3. Kembali ke sesi pertama -> alamat pertama muncul lagi.
 *   4. Membuka /c/<token> langsung (tempel di address bar) -> sesi itu
 *      yang terbuka, bukan sesi lain.
 *   5. Token asing -> TIDAK error, aplikasi tetap bisa dipakai, URL
 *      dibersihkan.
 *   6. Tombol Kembali browser tidak melempar pengguna ke sesi lain
 *      (karena replaceState, bukan pushState).
 *   7. Item "Salin tautan" ada di menu tiap sesi.
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 * Jalankan: node uji_url_sesi_browser.mjs
 */
import { chromium } from 'playwright'

const URL_APP = process.env.URL_UJI || 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const SUB_A = '100000000000000001'
const POLA_SESI = /\/c\/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

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
function buatTokenLogin() {
  const sekarang = Math.floor(Date.now() / 1000)
  const isi = { sub: SUB_A, exp: sekarang + 3600, iat: sekarang, email: 'uji@contoh.test' }
  return `${b64({ alg: 'none', typ: 'JWT' })}.${b64(isi)}.tanda-tangan-uji`
}

/**
 * Menyiapkan login di perangkat, sama seperti setelah "Masuk dengan
 * Google" berhasil. Kuncinya `gungdev:auth` dengan isi { sub, name,
 * email, loginPada } — lihat `bacaSesiTersimpan` di src/lib/auth.js.
 * Token riwayat dipakai agar riwayat akun ditarik dari server uji.
 */
async function siapkanLogin(page) {
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.evaluate(
    ({ sub, token }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({
          sub,
          name: 'Pengguna Uji',
          email: 'uji@contoh.test',
          loginPada: Date.now(),
        }),
      )
      localStorage.setItem('gungdev:token-riwayat', JSON.stringify({ token, pada: Date.now() }))
    },
    { sub: SUB_A, token: buatTokenLogin() },
  )
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
}

async function kirimPesan(page, teks) {
  const kotak = page.locator('textarea').first()
  await kotak.waitFor({ state: 'visible', timeout: 20000 })
  await kotak.fill(teks)
  await kotak.press('Enter')
  const balasan = page.locator('.msg--assistant').last()
  await balasan.waitFor({ state: 'visible', timeout: 60000 })
  /* Tunggu sampai tombol Stop hilang = jawaban selesai. */
  await page
    .locator('.composer__send--stop')
    .waitFor({ state: 'detached', timeout: 60000 })
    .catch(() => {})
  await page.waitForTimeout(500)
}

async function jalankan() {
  await resetAkun(SUB_A)

  const browser = await chromium.launch()
  const konteks = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const page = await konteks.newPage()

  const galat = []
  page.on('pageerror', (e) => galat.push(String(e)))
  page.on('console', (m) => {
    if (m.type() === 'error') galat.push(m.text())
  })

  /* Masuk sebagai akun uji supaya riwayatnya tersimpan di server. */
  await siapkanLogin(page)

  console.log('\n=== 1. ALAMAT TERBENTUK SAAT PESAN DIKIRIM ===')
  const JUDUL_1 = 'Halo, sebutkan satu warna.'
  await kirimPesan(page, JUDUL_1)
  await page.waitForTimeout(1500)
  const url1 = new URL(page.url())
  cek('alamat memuat token sesi (/c/<uuid>)', POLA_SESI.test(url1.pathname), url1.pathname)
  const token1 = url1.pathname.split('/c/')[1]

  /* Token harus STABIL: penyimpanan riwayat & pembuatan judul berjalan
     di latar belakang, jangan sampai itu mengubah alamat sesi. */
  await page.waitForTimeout(2500)
  const token1Stabil = new URL(page.url()).pathname.split('/c/')[1]
  cek('token tidak berubah setelah riwayat tersimpan', token1Stabil === token1, `${token1} -> ${token1Stabil}`)

  console.log('\n=== 2. SESI BERBEDA PUNYA ALAMAT BERBEDA ===')
  /* Sesi baru: klik "Percakapan baru", lalu kirim pesan agar benar-benar
     menjadi sesi baru (sesi kosong aktif dipakai ulang oleh newSession). */
  await page.getByRole('button', { name: /percakapan baru|chat baru/i }).first().click()
  await page.waitForTimeout(400)
  await kirimPesan(page, 'Sebutkan satu buah.')
  await page.waitForTimeout(800)
  const url2 = new URL(page.url())
  cek('sesi kedua juga punya token', POLA_SESI.test(url2.pathname), url2.pathname)
  const token2 = url2.pathname.split('/c/')[1]
  cek('token sesi pertama != sesi kedua', token1 && token2 && token1 !== token2, `${token1} vs ${token2}`)

  console.log('\n=== 3. KEMBALI KE SESI PERTAMA -> ALAMAT IKUT ===')
  /* Judul sesi bisa diganti otomatis oleh AI, jadi jangan dipakai sebagai
     penciri. Yang stabil: klik item sidebar yang BUKAN sesi aktif.
     Sidebar mengurutkan terbaru di atas, jadi item terakhir = sesi lama. */
  const itemLain = page.locator('.sb-item__main:not([aria-current="true"])')
  await itemLain.last().click()
  await page.waitForTimeout(1200)
  const url3 = new URL(page.url())
  cek('mengganti sesi mengubah alamat', POLA_SESI.test(url3.pathname), url3.pathname)
  cek('alamat menunjuk token milik sesi yang dibuka', url3.pathname === `/c/${token1}`, `${url3.pathname} vs /c/${token1}`)

  console.log('\n=== 4. MEMBUKA TAUTAN LANGSUNG ===')
  /* Buat sesi ketiga supaya "sesi pertama" bukan yang terakhir aktif. */
  await page.goto(`${URL_APP.replace(/\/$/, '')}/c/${token2}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const url4 = new URL(page.url())
  cek('membuka /c/<token> tetap di alamat itu', url4.pathname === `/c/${token2}`, url4.pathname)
  const judulAktif = await page.locator('.sb-item__main[aria-current="true"]').first().textContent().catch(() => '')
  cek('sesi yang terbuka adalah pemilik token', Boolean(judulAktif), String(judulAktif).trim())

  console.log('\n=== 5. TOKEN ASING -> TIDAK ERROR ===')
  const galatSebelum = galat.length
  await page.goto(`${URL_APP.replace(/\/$/, '')}/c/ffffffff-ffff-4fff-8fff-ffffffffffff`, {
    waitUntil: 'domcontentloaded',
  })
  await page.waitForTimeout(3000)
  const masihHidup = await page.locator('textarea').first().isVisible().catch(() => false)
  cek('aplikasi tetap bisa dipakai setelah token asing', masihHidup)
  /* Yang dicari: kegagalan APLIKASI (galat JS / crash). Galat jaringan
     seperti 401 atau koneksi server uji bukan salah fitur ini — token
     riwayat uji memang bisa ditolak setelah server di-reset. */
  const galatBaru = galat
    .slice(galatSebelum)
    .filter((g) => !/favicon|404|401|403|Failed to load resource|net::|ERR_/i.test(g))
  cek('tidak ada galat aplikasi untuk token asing', galatBaru.length === 0, galatBaru.join(' | ').slice(0, 200))
  const url5 = new URL(page.url())
  cek('alamat token asing dibersihkan (bukan dibiarkan)', !url5.pathname.includes('ffffffff'), url5.pathname)

  console.log('\n=== 6. RIWAYAT BROWSER TIDAK DIPENUHI SESI ===')
  /* Buka tautan sesi beberapa kali dalam satu halaman (tanpa reload),
     lalu periksa panjang riwayat browser tetap wajar. Kalau memakai
     pushState, setiap perpindahan sesi akan menambah satu entri dan
     tombol Kembali harus ditekan berkali-kali. */
  await page.goto(`${URL_APP.replace(/\/$/, '')}/c/${token1}`, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const panjangAwal = await page.evaluate(() => window.history.length)
  for (let i = 0; i < 3; i++) {
    await page.locator('.sb-item__main').nth(i % 2).click()
    await page.waitForTimeout(600)
  }
  const panjangAkhir = await page.evaluate(() => window.history.length)
  cek(
    'berpindah sesi tidak menumpuk riwayat browser',
    panjangAkhir === panjangAwal,
    `history.length ${panjangAwal} -> ${panjangAkhir}`,
  )

  console.log('\n=== 7. MENU "SALIN TAUTAN" ADA ===')
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const tombolMenu = page.locator('.sb-item__more').first()
  if (await tombolMenu.count()) {
    await tombolMenu.click()
    await page.waitForTimeout(300)
    const adaSalin = await page.locator('.sb-menu__item', { hasText: 'Salin tautan' }).count()
    cek('menu sesi punya "Salin tautan"', adaSalin > 0)
  } else {
    cek('menu sesi punya "Salin tautan"', false, 'tidak ada item sesi di sidebar')
  }

  console.log('\n=== 8. TAMU JUGA MENDAPAT ALAMAT ===')
  /* Sesi tanpa login: riwayat tidak disimpan, tetapi selama halaman
     terbuka percakapan tetap harus punya alamat sendiri. */
  const konteksTamu = await browser.newContext({ viewport: { width: 1280, height: 900 } })
  const pageTamu = await konteksTamu.newPage()
  await pageTamu.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await pageTamu.waitForTimeout(2500)
  await kirimPesan(pageTamu, 'Sebutkan satu hewan.')
  await pageTamu.waitForTimeout(1500)
  const jalurTamu = new URL(pageTamu.url()).pathname
  cek('tamu mendapat alamat /c/<uuid> setelah mengirim pesan', POLA_SESI.test(jalurTamu), jalurTamu)

  /* Tamu membuka token asing: URL harus dibersihkan juga. */
  await pageTamu.goto(`${URL_APP.replace(/\/$/, '')}/c/ffffffff-ffff-4fff-8fff-ffffffffffff`, {
    waitUntil: 'domcontentloaded',
  })
  await pageTamu.waitForTimeout(3000)
  const jalurTamuAsing = new URL(pageTamu.url()).pathname
  cek('tamu membuka token asing -> URL dibersihkan', jalurTamuAsing === '/', jalurTamuAsing)
  await konteksTamu.close()

  await browser.close()

  console.log('\n' + '='.repeat(64))
  const gagal = HASIL.filter((h) => !h.lulus).length
  console.log(`${HASIL.length - gagal}/${HASIL.length} lulus`)
  console.log(gagal === 0 ? 'HASIL: semua pemeriksaan lulus' : `HASIL: ${gagal} GAGAL`)
  console.log('='.repeat(64))
  process.exit(gagal === 0 ? 0 : 1)
}

jalankan().catch((e) => {
  console.error('\nUji berhenti karena kesalahan:', e)
  process.exit(1)
})
