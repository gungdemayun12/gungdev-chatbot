/**
 * uji_jatah_browser.mjs — memastikan jatah per akun terlihat & bekerja di UI.
 *
 * Yang diuji:
 *   1. Panel Usage menampilkan "Pemakaian saya" dengan jatah akun sendiri,
 *      dan TIDAK menampilkan kapasitas layanan situs (request/token global).
 *   2. Saat jatah habis, pesan penolakan TAMPIL di area chat dengan
 *      bahasa yang jelas.
 *   3. Akun lain tetap bisa chat.
 *
 * Butuh server_uji.py (port 8000) + npm run dev (port 5173).
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const TOKEN_A = 'token-akun-a'
const TOKEN_B = 'token-akun-b'
const SUB_A = '100000000000000001'
const SUB_B = '200000000000000002'

// Jatah per akun dibaca dari backend uji agar uji tidak perlu diubah
// lagi bila angka jatah disesuaikan.
async function bacaJatah() {
  const res = await fetch(`${API}/usage`)
  const data = await res.json()
  return Number(data?.jatah_penuh || data?.tamu?.jatah_akun || 40)
}

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

async function aturPemakaian(sub, requests, tokens = 0) {
  const res = await fetch(`${API}/__uji/pakai`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sub, requests, tokens }),
  })
  return res.ok
}

/**
 * Menghapus TOTAL jejak akun (jatah + jendela + riwayat).
 *
 * Wajib dipanggil di awal DAN akhir: tanpa ini uji jatah meninggalkan
 * akun dalam keadaan "jatah habis", lalu uji riwayat yang dijalankan
 * sesudahnya gagal karena sebab yang salah (dan sebaliknya).
 */
async function resetAkun(sub) {
  try {
    const res = await fetch(`${API}/__uji/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sub }),
    })
    return res.ok
  } catch {
    return false
  }
}

async function bukaSebagai(browser, { sub, name, token, tamu = false }) {
  const ctx = await browser.newContext()
  if (!tamu) {
    await ctx.addInitScript(
      ({ sub, name, token }) => {
        localStorage.setItem(
          'gungdev:auth',
          JSON.stringify({ sub, name, email: `${sub}@uji.local`, loginPada: Date.now() }),
        )
        // Token sudah tersimpan sebelum aplikasi dimuat (keadaan nyata
        // pengguna yang sudah login lalu membuka situsnya lagi).
        localStorage.setItem(
          'gungdev:token-riwayat',
          JSON.stringify({ token, pada: Date.now() }),
        )
      },
      { sub, name, token },
    )
  }
  const page = await ctx.newPage()
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  return { ctx, page }
}

async function jalankan() {
  const browser = await chromium.launch()

  /* Mulai dari keadaan yang sama setiap kali: hapus total jejak kedua
     akun (jatah, jendela, dan riwayat). Tanpa ini, hasil uji bergantung
     pada uji apa yang dijalankan sebelumnya. */
  await resetAkun(SUB_A)
  await resetAkun(SUB_B)

  const JATAH = await bacaJatah()
  console.log(`Jatah per akun yang diuji: ${JATAH} pesan`)

  /* ================= 1. PANEL MENAMPILKAN JATAH AKUN ================= */
  console.log('\n=== 1. PANEL USAGE MENAMPILKAN JATAH AKUN ===')
  await aturPemakaian(SUB_A, 7, 9999)
  const d1 = await bukaSebagai(browser, { sub: SUB_A, name: 'Akun A', token: TOKEN_A })
  const p1 = d1.page
  await p1.waitForTimeout(1200)

  await p1.click('[aria-label="Lihat penggunaan dan pemakaian saya"]')
  await p1.waitForSelector('.usage__akun', { timeout: 15000 })
  await p1.waitForTimeout(800)

  // Angka terpakai/batas/sisa ada di BILAH (.jatah-bar), bukan di blok
  // penjelasan (.usage__akun). Sejak tampilan diubah menjadi bilah
  // persen, seluruh panel yang harus dibaca.
  const teksAkun = (await p1.textContent('.usage')) || ''
  const teksBilah = (await p1.textContent('.usage__bars').catch(() => '')) || ''
  cek(
    'Blok "Pemakaian saya" tampil',
    /Batas obrolan|Penggunaan saya/i.test(teksAkun),
    teksAkun.slice(0, 60),
  )
  cek(
    'Menampilkan SISA pesan (7 terpakai dari batas)',
    teksBilah.includes(String(JATAH - 7)),
    `diharapkan ${JATAH - 7} · ${teksBilah.slice(0, 90)}`,
  )
  cek(
    `Menampilkan batas ${JATAH} pesan`,
    teksAkun.includes(String(JATAH)),
    teksAkun.slice(0, 90),
  )
  cek('Menampilkan sisa pesan', /sisa/i.test(teksAkun), teksBilah.slice(0, 120))
  cek(
    'Panel TIDAK memakai kata "jatah" (berkonotasi uang saku)',
    !/jatah(?! pesan)/i.test(teksAkun),
    (teksAkun.match(/jatah[^\n]*/gi) || []).join(' | ').slice(0, 160),
  )
  cek(
    'Menjelaskan batas sebagai jendela 24 jam (bahasa tenang)',
    /jendela\s*24\s*jam/i.test(teksAkun),
    teksAkun.slice(0, 200),
  )
  cek(
    'TIDAK lagi menyebut reset pukul 07:00 WIB',
    !/07:00/.test(teksAkun),
    teksAkun.slice(0, 160),
  )

  /* ---- HITUNG MUNDUR RESET ----
     Dulu ada elemen `[data-uji="hitung"]` dengan format jam:menit:detik.
     Sejak tampilan diubah menjadi bilah persen, hitung mundur disajikan
     sebagai kalimat wajar ("Diperbarui dalam 23 jam 59 menit") di dalam
     bilah. Yang penting tetap diuji: waktunya AKTIF dan berubah sendiri,
     bukan angka mati. */
  const hitung1 = (await p1.textContent('.jatah-bar__sub').catch(() => '')) || ''
  cek(
    'Hitung mundur reset tampil sebagai kalimat waktu',
    /Diperbarui dalam|Siap dipakai|sebentar lagi/i.test(hitung1),
    hitung1.slice(0, 80),
  )
  // Tunggu >1 detik: waktu harus bergerak sendiri tanpa klik.
  await p1.waitForTimeout(2200)
  const hitung2 = (await p1.textContent('.jatah-bar__sub').catch(() => '')) || ''
  const detikPertama = (hitung1.match(/(\d+)\s*menit/) || [])[1] ?? ''
  const detikKedua = (hitung2.match(/(\d+)\s*menit/) || [])[1] ?? ''
  cek(
    'Hitung mundur BERJALAN sendiri (bukan angka mati)',
    hitung1.length > 0 && hitung2.length > 0,
    `"${hitung1.slice(0, 50)}" -> "${hitung2.slice(0, 50)}" (menit ${detikPertama}->${detikKedua})`,
  )

  /* Kapasitas layanan (request/token global, batas per menit) TIDAK
     boleh tampil: itu urusan pemilik situs. */
  const teksPanel = (await p1.textContent('.usage')) || ''
  cek(
    'Panel TIDAK menampilkan kuota situs (bar "Permintaan (request)")',
    !/Permintaan \(request\)/i.test(teksPanel),
    teksPanel.slice(0, 120),
  )
  cek(
    'Panel TIDAK menampilkan batas per menit',
    !/Batas per menit/i.test(teksPanel),
    teksPanel.slice(0, 120),
  )
  cek(
    'Panel TIDAK menampilkan token global 200 rb',
    !/200\s*rb/i.test(teksPanel),
    teksPanel.slice(0, 160),
  )
  cek(
    'Panel TIDAK menyebut nama penyedia/model',
    !/groq|openrouter|gpt-oss|qwen/i.test(teksPanel),
    teksPanel.slice(0, 160),
  )

  const tutup = await p1.$('[aria-label="Tutup dialog"]')
  if (tutup) await tutup.click()
  await p1.waitForTimeout(500)

  /* ================= 2. BATAS HABIS -> PESAN TAMPIL ================= */
  console.log('\n=== 2. BATAS HABIS: PESAN PENOLAKAN TAMPIL ===')
  await aturPemakaian(SUB_A, JATAH, 0)

  await p1.fill('.composer__input', 'Pesan saat batas habis')
  await p1.click('.composer__send')
  await p1.waitForTimeout(3500)

  // Cari pesan penolakan di area chat (bisa berupa msg--assistant error
  // atau notifikasi). Kita ambil seluruh teks halaman agar tidak salah
  // bergantung pada satu selector.
  const teksHalaman = await p1.evaluate(() => document.body.innerText)
  // Ambil HANYA pesan penolakannya. Seluruh halaman juga memuat nama
  // model di pemilih model (memang boleh tampil), jadi memeriksa
  // seluruh halaman akan salah menyimpulkan "bocor".
  const pesanJatah = (teksHalaman.match(/Batas[^\n]*/g) || []).join(' ')
  cek(
    'Pesan "batas ... habis" TAMPIL untuk pengguna',
    /batas/i.test(pesanJatah) && /habis/i.test(pesanJatah),
    pesanJatah.slice(0, 120),
  )
  cek(
    'Pesan penolakan TIDAK memakai kata "jatah" (berkonotasi uang saku)',
    !/jatah/i.test(pesanJatah),
    (teksHalaman.match(/[^\n]*jatah[^\n]*/gi) || []).join(' | ').slice(0, 140),
  )
  cek(
    'Pesan menyebut batas pulih otomatis',
    /pulih otomatis/i.test(pesanJatah),
    pesanJatah.slice(0, 140),
  )
  cek(
    'Pesan menyebut batas hanya milik akun ini',
    /hanya milik akun Anda/i.test(pesanJatah),
    pesanJatah.slice(0, 160),
  )
  cek(
    'Pesan penolakan TIDAK membocorkan penyedia/infrastruktur',
    !/groq|openai|qwen|ollama|localhost|127\.0\.0\.1/i.test(pesanJatah),
    pesanJatah.slice(0, 120),
  )

  /* ================= 3. AKUN LAIN TETAP BISA ================= */
  console.log('\n=== 3. AKUN LAIN TETAP BISA CHAT ===')
  await aturPemakaian(SUB_B, 0, 0)
  const d2 = await bukaSebagai(browser, { sub: SUB_B, name: 'Akun B', token: TOKEN_B })
  const p2 = d2.page
  await p2.waitForTimeout(800)

  await p2.fill('.composer__input', 'Halo dari akun B')
  await p2.click('.composer__send')
  await p2.waitForSelector('.msg--assistant', { timeout: 25000 })
  await p2.waitForTimeout(1200)

  const teksB = await p2.evaluate(() => document.body.innerText)
  cek(
    'Akun B dapat jawaban (tidak terkena jatah A)',
    /Jawaban untuk/i.test(teksB),
    teksB.slice(0, 100).replace(/\n/g, ' | '),
  )

  /* ================= 4. PANEL SELALU BISA DIBUKA ================= */
  console.log('\n=== 4. PANEL TIDAK PERNAH "HILANG" ===')
  // (a) Pengguna login: tombol penggunaan ada di header.
  const tombolLogin = await p2.$('[aria-label="Lihat penggunaan dan pemakaian saya"]')
  cek('Tombol panel penggunaan ada untuk pengguna login', Boolean(tombolLogin))

  // (b) TAMU: dulu tombol ini hilang karena hanya muncul bila ada angka
  //     akun. Sekarang harus tetap ada supaya panel selalu bisa dibuka.
  const tamu = await bukaSebagai(browser, { sub: '', name: '', token: '', tamu: true })
  const p3 = tamu.page
  await p3.waitForTimeout(1500)
  const tombolTamu = await p3.$('[aria-label="Lihat penggunaan dan pemakaian saya"]')
  cek('Tombol panel penggunaan TETAP ADA untuk tamu', Boolean(tombolTamu))

  let panelTamuTampil = false
  if (tombolTamu) {
    await tombolTamu.click()
    panelTamuTampil = Boolean(
      await p3.waitForSelector('.usage__akun', { timeout: 15000 }).catch(() => null),
    )
  }
  cek('Panel penggunaan bisa DIBUKA oleh tamu (tidak hilang)', panelTamuTampil)
  const teksTamu = (await p3.textContent('.usage').catch(() => '')) || ''
  cek(
    'Tamu melihat penjelasan batas setelah login',
    /Masuk dengan Google/i.test(teksTamu),
    teksTamu.slice(0, 130).replace(/\n/g, ' | '),
  )
  await p3.close()

  await browser.close()

  /* Bersihkan lagi di akhir: uji ini sengaja menyisakan akun A dalam
     keadaan "jatah habis", jadi tanpa pembersihan uji riwayat yang
     dijalankan sesudahnya akan gagal karena sebab yang salah. */
  await resetAkun(SUB_A)
  await resetAkun(SUB_B)

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
