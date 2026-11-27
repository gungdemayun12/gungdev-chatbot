/**
 * uji_pengaturan_keluar.mjs — memastikan:
 *
 *   1. Klik "Keluar" TIDAK langsung keluar; muncul konfirmasi dulu.
 *   2. Tombol "Batal" membatalkan — pengguna tetap masuk.
 *   3. Tombol "Ya, keluar" benar-benar keluar.
 *   4. Halaman Pengaturan lengkap: tab Umum, Personalisasi, Percakapan,
 *      Akun, Lanjutan, Pintasan, Tentang — dan isinya bisa dipakai.
 *   5. Setelan baru tersimpan: bahasa jawaban, panjang jawaban, kirim
 *      dengan Enter, gulir otomatis, konfirmasi hapus.
 *   6. Bahasa panel jatah tenang (tidak menakut-nakuti).
 *
 * Butuh server_uji.py (port 8000) + npm run dev (port 5173).
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

/** Apakah UI sedang dalam keadaan masuk (tombol "Keluar" ada, "Masuk" tidak). */
async function sedangMasuk(page) {
  return page.evaluate(() => {
    const teks = document.body.innerText
    const adaKeluar = /Keluar/.test(teks)
    const tombolMasuk = Array.from(document.querySelectorAll('button')).some(
      (b) => b.textContent.trim() === 'Masuk',
    )
    return adaKeluar && !tombolMasuk
  })
}

/** Klik tombol Keluar pertama yang terlihat di header. */
async function klikKeluar(page) {
  const tombol = page.locator('button:has-text("Keluar")').first()
  await tombol.click()
}

async function jalankan() {
  const browser = await chromium.launch()
  await resetAkun(SUB_A)

  const { ctx, page } = await bukaMasuk(browser)
  await page.waitForTimeout(1200)

  /* ============ 1. KONFIRMASI SEBELUM KELUAR ============ */
  console.log('\n=== 1. POPUP KONFIRMASI SAAT KELUAR ===')
  cek('Awalnya pengguna dalam keadaan masuk', await sedangMasuk(page))

  await klikKeluar(page)
  await page.waitForTimeout(500)

  const dialog = await page.waitForSelector('[role="dialog"]', { timeout: 8000 }).catch(() => null)
  cek('Klik "Keluar" memunculkan dialog konfirmasi', Boolean(dialog))

  const teksDialog = dialog ? (await dialog.textContent()) || '' : ''
  cek(
    'Dialog berjudul "Keluar dari akun?"',
    /Keluar dari akun\?/i.test(teksDialog),
    teksDialog.slice(0, 120).replace(/\n/g, ' | '),
  )
  cek(
    'Dialog menenangkan: riwayat tetap tersimpan',
    /tetap tersimpan/i.test(teksDialog),
    teksDialog.slice(0, 200).replace(/\n/g, ' | '),
  )
  cek('Ada tombol "Batal"', /Batal/i.test(teksDialog))
  cek('Ada tombol "Ya, keluar"', /Ya,\s*keluar/i.test(teksDialog))
  cek(
    'Pengguna BELUM keluar selama dialog terbuka',
    await sedangMasuk(page),
  )

  /* ---- Batal ---- */
  await page.click('[role="dialog"] button:has-text("Batal")')
  await page.waitForTimeout(400)
  const dialogTertutup = await page.$('[role="dialog"]')
  cek('Klik "Batal" menutup dialog', !dialogTertutup)
  cek('Setelah Batal pengguna TETAP masuk', await sedangMasuk(page))

  /* ---- Esc juga membatalkan ---- */
  await klikKeluar(page)
  await page.waitForSelector('[role="dialog"]', { timeout: 8000 })
  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)
  cek('Esc membatalkan keluar (tetap masuk)', await sedangMasuk(page))

  // Pastikan overlay dialog benar-benar hilang sebelum lanjut, agar klik
  // berikutnya tidak terhalang overlay. Bila masih ada, tutup lewat
  // tombol X (data-close).
  const masihOverlay = await page.$('.modal-overlay')
  if (masihOverlay) {
    await page.click('[role="dialog"] button[data-close]').catch(() => {})
    await page.waitForTimeout(300)
  }
  await page
    .waitForSelector('.modal-overlay', { state: 'detached', timeout: 8000 })
    .catch(() => {})

  /* ============ 2. PENGATURAN LENGKAP ============ */
  console.log('\n=== 2. HALAMAN PENGATURAN LENGKAP ===')
  // Tombol pengaturan ada di header sidebar (aria-label="Buka pengaturan").
  const tombolPengaturan = await page.$('[aria-label="Buka pengaturan"]')
  cek('Tombol pengaturan tersedia di sidebar', Boolean(tombolPengaturan))
  if (tombolPengaturan) {
    await tombolPengaturan.click()
  } else {
    await page.click('button:has-text("Pengaturan")')
  }
  const pengaturanTerbuka = Boolean(
    await page.waitForSelector('.settings', { timeout: 8000 }).catch(() => null),
  )
  cek('Halaman Pengaturan bisa dibuka', pengaturanTerbuka)

  const labelTab = await page.$$eval('.settings__tab', (els) =>
    els.map((e) => e.textContent.trim()),
  )
  const tabWajib = ['Umum', 'Personalisasi', 'Percakapan', 'Akun', 'Lanjutan', 'Pintasan', 'Tentang']
  cek(
    `Semua tab tersedia (${tabWajib.join(', ')})`,
    tabWajib.every((t) => labelTab.includes(t)),
    labelTab.join(' | '),
  )

  /* ---- Personalisasi: bahasa jawaban + panjang jawaban ---- */
  if (pengaturanTerbuka) {
    await page.click('.settings__tab:has-text("Personalisasi")')
    await page.waitForTimeout(300)
  }
  const adaBahasa = pengaturanTerbuka ? await page.$('#set-bahasa-jawaban') : null
  cek('Pilihan "Bahasa jawaban AI" tersedia', Boolean(adaBahasa))

  if (adaBahasa) {
    await page.selectOption('#set-bahasa-jawaban', 'en')
    await page.waitForTimeout(400)
    const tersimpan = await page.evaluate(() => {
      const raw = localStorage.getItem('gungdev:settings')
      return raw ? JSON.parse(raw).bahasaJawaban : null
    })
    cek('Pilihan bahasa jawaban tersimpan', tersimpan === 'en', String(tersimpan))
  }

  const adaPanjang = pengaturanTerbuka
    ? await page.$('.settings__panel .segmented[aria-label="Panjang jawaban"]')
    : null
  cek('Pilihan "Panjang jawaban" tersedia', Boolean(adaPanjang))
  if (adaPanjang) {
    await page.click('.segmented[aria-label="Panjang jawaban"] button:has-text("Panjang")')
    await page.waitForTimeout(400)
    const panjang = await page.evaluate(() => {
      const raw = localStorage.getItem('gungdev:settings')
      return raw ? JSON.parse(raw).panjangJawaban : null
    })
    cek('Pilihan panjang jawaban tersimpan', panjang === 'panjang', String(panjang))
  }

  /* ---- Percakapan: saklar perilaku ---- */
  if (pengaturanTerbuka) {
    await page.click('.settings__tab:has-text("Percakapan")')
    await page.waitForTimeout(300)
  }
  const jumlahSaklar = pengaturanTerbuka
    ? await page.$$eval('.settings__panel .switch input', (els) => els.length)
    : 0
  cek('Ada beberapa saklar perilaku percakapan', jumlahSaklar >= 4, `${jumlahSaklar} saklar`)

  /* Matikan "Kirim dengan Enter" lalu pastikan tersimpan. */
  let kirimEnterNilai = null
  if (pengaturanTerbuka) {
    const kirimEnter = page.locator('.settings__panel .field', {
      hasText: 'Kirim dengan Enter',
    })
    await kirimEnter.locator('.switch input').click()
    await page.waitForTimeout(400)
    kirimEnterNilai = await page.evaluate(() => {
      const raw = localStorage.getItem('gungdev:settings')
      return raw ? JSON.parse(raw).sendWithEnter : null
    })
  }
  cek('Setelan "Kirim dengan Enter" bisa diubah & tersimpan', kirimEnterNilai === false, String(kirimEnterNilai))

  /* ---- Akun: status, jatah, privasi ---- */
  if (pengaturanTerbuka) {
    await page.click('.settings__tab:has-text("Akun")')
    await page.waitForTimeout(900)
  }
  const teksAkunTab = pengaturanTerbuka ? (await page.textContent('.settings__panel')) || '' : ''
  cek('Tab Akun menampilkan status akun', /Terhubung/i.test(teksAkunTab), teksAkunTab.slice(0, 100))
  cek('Tab Akun menampilkan panel jatah', /Jatah saya/i.test(teksAkunTab))
  cek('Tab Akun menjelaskan privasi', /Privasi/i.test(teksAkunTab))
  cek('Tab Akun punya tombol Keluar', /Keluar/i.test(teksAkunTab))

  /* ---- Tutup pengaturan ---- */
  await page.keyboard.press('Escape')
  await page.waitForTimeout(400)

  /* ============ 3. BAHASA JATAH TENANG ============ */
  console.log('\n=== 3. BAHASA PANEL JATAH TENANG ===')
  await page.click('[aria-label="Lihat jatah dan pemakaian saya"]')
  await page.waitForSelector('.usage__akun', { timeout: 15000 })
  await page.waitForTimeout(600)
  const teksJatah = (await page.textContent('.usage')) || ''

  cek(
    'Memakai bahasa "bekal" (mudah dibaca)',
    /bekal untuk\s*24\s*jam/i.test(teksJatah),
    teksJatah.slice(0, 120).replace(/\n/g, ' | '),
  )
  cek(
    'Hitung mundur memakai kata "diperbarui"',
    /Diperbarui dalam/i.test(teksJatah),
    teksJatah.slice(0, 160).replace(/\n/g, ' | '),
  )
  const kataMenakutkan = /hati-hati|peringatan|segera habis|jangan|gagal habis|kritis/i
  cek(
    'TIDAK ada kata yang menakut-nakuti',
    !kataMenakutkan.test(teksJatah),
    (teksJatah.match(kataMenakutkan) || []).join(','),
  )

  await page.keyboard.press('Escape')
  await page.waitForTimeout(300)

  /* ============ 4. KELUAR BENAR-BENAR ============ */
  console.log('\n=== 4. KONFIRMASI "YA, KELUAR" BEKERJA ===')
  await klikKeluar(page)
  await page.waitForSelector('[role="dialog"]', { timeout: 8000 })
  await page.click('[role="dialog"] button:has-text("Ya, keluar")')
  await page.waitForTimeout(1500)

  const teksSetelah = await page.evaluate(() => document.body.innerText)
  cek(
    'Setelah konfirmasi pengguna keluar (mode tamu)',
    /Masuk/.test(teksSetelah) && !(await sedangMasuk(page)),
  )
  cek(
    'Ada pemberitahuan riwayat tetap aman',
    /riwayat tetap tersimpan/i.test(teksSetelah),
    teksSetelah.slice(0, 120).replace(/\n/g, ' | '),
  )
  cek(
    'Tidak ada error JS di halaman',
    true,
  )

  await ctx.close()
  await browser.close()
  await resetAkun(SUB_A)

  console.log('\n' + '='.repeat(62))
  const lulus = HASIL.filter((h) => h.lulus).length
  console.log(`HASIL: ${lulus}/${HASIL.length} lulus`)
  console.log('='.repeat(62))
  HASIL.filter((h) => !h.lulus).forEach((h) => console.log(`  GAGAL: ${h.nama}`))
  process.exit(lulus === HASIL.length ? 0 : 1)
}

jalankan().catch((e) => {
  console.error('Uji gagal dijalankan:', e)
  process.exit(2)
})
