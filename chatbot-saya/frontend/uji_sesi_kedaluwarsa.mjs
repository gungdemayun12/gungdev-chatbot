/**
 * uji_sesi_kedaluwarsa.mjs — memastikan pengguna yang SUDAH login tidak
 * pernah diperlakukan sebagai tamu, bahkan ketika ID token Google sudah
 * kedaluwarsa (~1 jam).
 *
 * KELUHAN PEMILIK SITUS (dengan tangkapan layar)
 * ---------------------------------------------
 * "Saya sudah login, profil akun tampil di kiri bawah. Saya refresh lalu
 *  buka lagi setelah beberapa jam. Kenapa muncul 'Signing you in…' seolah
 *  saya belum login? Dan selama itu saya jadi mode tamu — jatah saya
 *  jadi 3. Kecuali saya tunggu verifikasi selesai."
 *
 * AKAR MASALAH
 * ------------
 * ID token Google hanya berumur ~1 jam. Handler lama MENGHAPUS token yang
 * kedaluwarsa, sehingga aplikasi tidak bisa membedakan:
 *   - "belum pernah login"  -> wajar jadi tamu
 *   - "login, token basi"   -> TIDAK boleh jadi tamu
 * Lalu status penyimpanan jatuh ke 'perangkat', dan UI menampilkan
 * peringatan seolah akunnya bermasalah.
 *
 * Yang diuji:
 *   1. Token kedaluwarsa TIDAK dihapus; dikenali sebagai "perlu diperbarui".
 *   2. Setelah halaman dimuat: profil tetap tampil, TIDAK ada ajakan masuk,
 *      TIDAK ada dialog login sendiri.
 *   3. Pengguna TIDAK dianggap tamu: tidak ada "Sisa N pesan tamu".
 *   4. Tidak ada peringatan "Riwayat sementara hanya di perangkat ini".
 *   5. Jatah tetap jatah AKUN (bukan 3 pesan tamu).
 *   6. Kirim pesan dengan token basi tetap dicatat sebagai akun (bukan tamu).
 *   7. Setelah "Keluar", token benar-benar dilupakan (perilaku lama tetap).
 *
 * Butuh server_uji.py (port 8000) + vite (port 5173).
 * Jalankan: node uji_sesi_kedaluwarsa.mjs
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const SUB_A = '100000000000000001'

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

/** JWT tiruan dengan `exp` tertentu (tidak diverifikasi di sisi klien). */
function jwtTiruan(sub, expDetik) {
  const b64 = (o) => Buffer.from(JSON.stringify(o)).toString('base64url')
  return `${b64({ alg: 'none', typ: 'JWT' })}.${b64({ sub, exp: expDetik })}.x`
}

const browser = await chromium.launch()

/** Konteks "pengguna sudah login lalu kembali setelah beberapa jam". */
async function bukaKedaluwarsa(jamLalu) {
  const ctx = await browser.newContext()
  const exp = Math.floor(Date.now() / 1000) - jamLalu * 3600
  await ctx.addInitScript(
    ({ sub, token, pada }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({
          sub,
          name: 'Gungde Mayun',
          email: 'gungdemayun@gmail.com',
          loginPada: pada,
        }),
      )
      localStorage.setItem('gungdev:token-riwayat', JSON.stringify({ token, pada }))
    },
    {
      sub: SUB_A,
      token: jwtTiruan(SUB_A, exp),
      pada: Date.now() - jamLalu * 3600 * 1000,
    },
  )
  const page = await ctx.newPage()
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  return { ctx, page }
}

/** Keadaan UI dari sudut pandang pengguna. */
async function keadaan(page) {
  return page.evaluate(() => {
    const t = document.body.innerText
    return {
      profilTampil: /Gungde Mayun/.test(t),
      tombolMasuk: Array.from(document.querySelectorAll('button')).some((b) =>
        /^Masuk/.test(b.textContent.trim()),
      ),
      ajakanMasuk: /Masuk dengan Google/.test(t),
      statusTamu: /Belum masuk/.test(t),
      sisaTamu: (t.match(/Sisa \d+ pesan tamu hari ini/) || [null])[0],
      peringatanPerangkat: /Riwayat sementara hanya di perangkat ini/.test(t),
      dialogLogin: Boolean(document.querySelector('.modal, [role="dialog"]')),
      jatah3: /3 pesan\/hari/.test(t),
    }
  })
}

await resetAkun(SUB_A)

/* ---------------------------------------------------------------- */
console.log('=== 1. TOKEN KEDALUWARSA TIDAK DIHAPUS ===')
{
  const { ctx, page } = await bukaKedaluwarsa(3)
  await page.waitForTimeout(2500)

  const tokenInfo = await page.evaluate(async () => {
    const appUrl =
      performance
        .getEntriesByType('resource')
        .map((e) => e.name)
        .find((n) => n.includes('/src/lib/riwayat.js')) || '/src/lib/riwayat.js'
    const src = appUrl.includes('?') ? new URL(appUrl).search : ''
    const mod = await import('/src/lib/riwayat.js' + src)
    return {
      aktif: mod.getTokenRiwayat(),
      perluDiperbarui: mod.tokenPerluDiperbarui(),
      tersimpanDiPerangkat: localStorage.getItem('gungdev:token-riwayat') !== null,
    }
  })
  cek('token basi tidak dipakai sebagai token aktif', tokenInfo.aktif === null)
  cek('token basi dikenali "perlu diperbarui"', tokenInfo.perluDiperbarui === true)
  cek('salinan token tidak dibuang dari perangkat', tokenInfo.tersimpanDiPerangkat)
  await ctx.close()
}

/* ---------------------------------------------------------------- */
console.log('\n=== 2. TETAP LOGIN SETELAH BEBERAPA JAM ===')
for (const jam of [2, 12, 72]) {
  const { ctx, page } = await bukaKedaluwarsa(jam)
  await page.waitForTimeout(2500)
  const st = await keadaan(page)
  cek(`kembali setelah ${jam} jam: profil akun tampil`, st.profilTampil, JSON.stringify(st))
  cek(`kembali setelah ${jam} jam: tidak ada tombol Masuk`, !st.tombolMasuk)
  cek(`kembali setelah ${jam} jam: tidak ada ajakan masuk`, !st.ajakanMasuk)
  cek(`kembali setelah ${jam} jam: bukan mode tamu`, !st.statusTamu)
  cek(`kembali setelah ${jam} jam: dialog login tidak terbuka`, !st.dialogLogin)
  await ctx.close()
}

/* ---------------------------------------------------------------- */
console.log('\n=== 3. TIDAK DIANGGAP TAMU (JATAH TETAP AKUN) ===')
{
  const { ctx, page } = await bukaKedaluwarsa(5)
  await page.waitForTimeout(2500)
  const st = await keadaan(page)
  cek('tidak ada "Sisa N pesan tamu"', st.sisaTamu === null, String(st.sisaTamu))
  cek('tidak ada jatah "3 pesan/hari"', !st.jatah3)
  cek('tidak ada peringatan "riwayat sementara"', !st.peringatanPerangkat)
  await ctx.close()
}

/* ---------------------------------------------------------------- */
console.log('\n=== 4. KIRIM PESAN TETAP DIHITUNG SEBAGAI AKUN ===')
{
  const { ctx, page } = await bukaKedaluwarsa(4)
  await page.waitForTimeout(2000)

  await page.fill('.composer__input', 'Sebut satu kata saja: uji')
  await page.press('.composer__input', 'Enter')
  await page.waitForFunction(
    () => document.querySelectorAll('.msg--assistant').length > 0,
    { timeout: 60000 },
  )
  await page.waitForTimeout(2500)

  // Pemakaian tamu di perangkat TIDAK boleh bertambah.
  const tamu = await page.evaluate(() => localStorage.getItem('gungdev:guest'))
  const terpakaiTamu = tamu ? Number(JSON.parse(tamu).terpakai) || 0 : 0
  cek('pemakaian TAMU tidak bertambah', terpakaiTamu === 0, String(terpakaiTamu))

  // Jatah akun tercatat di server.
  const usage = await page.evaluate(async (api) => {
    const r = await fetch(`${api}/usage`)
    return r.json()
  }, API)
  cek(
    'jatah yang berlaku adalah jatah akun (bukan 3)',
    Number(usage?.jatah_penuh || 0) > 3,
    `jatah_penuh=${usage?.jatah_penuh}`,
  )
  await ctx.close()
}

/* ---------------------------------------------------------------- */
console.log('\n=== 5. "KELUAR" TETAP MENGAKHIRI SESI ===')
{
  const { ctx, page } = await bukaKedaluwarsa(3)
  await page.waitForTimeout(2000)
  // Pasang token segar dulu supaya tombol akun aktif seperti biasa.
  await page.evaluate(async () => {
    const appUrl =
      performance
        .getEntriesByType('resource')
        .map((e) => e.name)
        .find((n) => n.includes('/src/lib/riwayat.js')) || '/src/lib/riwayat.js'
    const src = appUrl.includes('?') ? new URL(appUrl).search : ''
    const mod = await import('/src/lib/riwayat.js' + src)
    mod.setTokenRiwayat('token-akun-a', { paksa: true })
  })
  await page.waitForTimeout(400)

  await page.locator('.sb-profile--akun').first().click()
  await page.waitForTimeout(300)
  await page.locator('.sb-menu__item', { hasText: 'Keluar' }).first().click()
  await page.waitForTimeout(300)
  const ya = page.locator('button', { hasText: 'Ya, keluar' }).first()
  if (await ya.count()) {
    await ya.click()
    await page.waitForTimeout(800)
  }

  const st = await keadaan(page)
  cek('setelah Keluar: profil akun hilang', !st.profilTampil)
  const token = await page.evaluate(async () => {
    const appUrl =
      performance
        .getEntriesByType('resource')
        .map((e) => e.name)
        .find((n) => n.includes('/src/lib/riwayat.js')) || '/src/lib/riwayat.js'
    const src = appUrl.includes('?') ? new URL(appUrl).search : ''
    const mod = await import('/src/lib/riwayat.js' + src)
    return {
      aktif: mod.getTokenRiwayat(),
      perlu: mod.tokenPerluDiperbarui(),
      ls: localStorage.getItem('gungdev:token-riwayat'),
    }
  })
  cek('setelah Keluar: token aktif kosong', token.aktif === null, String(token.aktif))
  cek('setelah Keluar: tidak ada lagi token tersimpan', token.ls === null, String(token.ls))
  cek('setelah Keluar: tidak dianggap "perlu diperbarui"', token.perlu === false)
  await ctx.close()
}

await browser.close()

const gagal = HASIL.filter((h) => !h.lulus).length
console.log(`\nHASIL: ${HASIL.length - gagal}/${HASIL.length} lulus`)
process.exit(gagal === 0 ? 0 : 1)
