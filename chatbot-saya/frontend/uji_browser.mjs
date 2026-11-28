/**
 * uji_browser.mjs — uji alur riwayat server lintas "perangkat".
 *
 * Dua context browser terpisah = dua perangkat berbeda (localStorage
 * masing-masing tidak berbagi). Yang diuji:
 *
 *   1. Akun A buat percakapan di perangkat 1
 *   2. Perangkat 2 (context baru, akun sama) -> riwayat SAMA muncul
 *   3. Perangkat 2 hapus -> hilang di perangkat 1
 *   4. Akun B -> TIDAK melihat riwayat akun A
 *   5. Saklar "Simpan riwayat" mati -> tidak menulis ke server
 *   6. Tamu -> tidak ada riwayat
 *
 * CATATAN PENTING TENTANG TOKEN
 * -----------------------------
 * Di produksi, ID token datang dari Google Identity Services. Di uji
 * lokal GIS tidak bisa dipakai (localhost belum terdaftar di Google),
 * jadi token dipasang lewat jalur yang SAMA dengan produksi: memanggil
 * setTokenRiwayat() pada modul riwayat, sebelum React sempat membaca
 * riwayat. Dengan begitu alur nyata (header Authorization, verifikasi
 * token di backend, kunci per akun) tetap benar-benar diuji.
 */
import { chromium } from 'playwright'

const URL_APP = 'http://127.0.0.1:5173/'
const API = 'http://127.0.0.1:8000'
const TOKEN_A = 'token-akun-a'
const TOKEN_B = 'token-akun-b'

const HASIL = []
function cek(nama, lulus, info = '') {
  HASIL.push({ nama, lulus })
  console.log(`${lulus ? 'LULUS' : 'GAGAL'}  ${nama}${info ? ' — ' + info : ''}`)
}

/**
 * Membuka halaman sebagai akun tertentu.
 *
 * Urutan penting: status login & token sudah terpasang SEBELUM React
 * menjalankan efek pembacaan riwayat. `addInitScript` menyuntikkan kode
 * yang jalan sebelum skrip aplikasi, jadi permintaan pertama ke
 * /api/sessions sudah membawa token — persis seperti produksi.
 */
/**
 * Menyimpan token riwayat di perangkat SEBELUM aplikasi dimuat.
 *
 * Dijalankan di dalam `addInitScript`, jadi token sudah ada saat React
 * pertama kali membaca riwayat — persis seperti pengguna yang sudah
 * login lalu membuka kembali situsnya (token memang tersimpan).
 */
export const SIMPAN_TOKEN_SEBELUM_MUAT = ({ token }) => {
  localStorage.setItem(
    'gungdev:token-riwayat',
    JSON.stringify({ token, pada: Date.now() }),
  )
}

async function bukaSebagai(browser, { sub, name, email, token }, { saveHistory = true } = {}) {
  const ctx = await browser.newContext()

  await ctx.addInitScript(
    ({ sub, name, email, token, saveHistoryFlag }) => {
      localStorage.setItem(
        'gungdev:auth',
        JSON.stringify({ sub, name, email, loginPada: Date.now() }),
      )
      // Token dipasang SEBELUM aplikasi dimuat: inilah keadaan nyata
      // pengguna yang sudah login lalu membuka situsnya lagi.
      if (token) {
        localStorage.setItem(
          'gungdev:token-riwayat',
          JSON.stringify({ token, pada: Date.now() }),
        )
      }
      if (!saveHistoryFlag) {
        const s = JSON.parse(localStorage.getItem('gungdev:settings') || '{}')
        s.saveHistory = false
        localStorage.setItem('gungdev:settings', JSON.stringify(s))
      }
      // Token dipasang lewat modul resmi, sama seperti callback GIS.
      window.__siapkanToken = async () => {
        const mod = await import('/src/lib/riwayat.js')
        mod.setTokenRiwayat(token, { paksa: true })
      }
    },
    { sub, name, email, token, saveHistoryFlag: saveHistory },
  )

  const page = await ctx.newPage()
  await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('.composer__input', { timeout: 20000 })
  return { ctx, page }
}

async function itemRiwayat(page) {
  return page.$$eval('.sb-item', (els) => els.map((e) => e.textContent.trim()))
}

/**
 * Membaca riwayat akun langsung dari server, memakai pg.REQUEST (bukan
 * fetch di dalam halaman).
 *
 * Mengapa tidak lewat `page.evaluate(fetch(...))` seperti sebelumnya:
 * permintaan itu berjalan di dalam halaman aplikasi, sehingga ikut
 * memakai keadaan halaman (token modul, urutan render, hook React).
 * Bila pemeriksaan kebetulan berjalan saat halaman sedang menulis, hasil
 * bacaan bisa kosong walaupun server sebenarnya sudah menerima data —
 * uji lalu gagal karena sebab yang salah, dan hanya kadang-kadang.
 * Permintaan lewat pg.REQUEST tidak menyentuh halaman sama sekali.
 */
async function riwayatDiServer(page, token) {
  const res = await page.request.get(`${API}/api/sessions`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  const j = await res.json()
  return (j.sesi || []).map((s) => s.title)
}

async function jalankan() {
  const browser = await chromium.launch()

  /* Bersihkan penyimpanan server lebih dulu supaya hasil uji tidak
     bergantung pada sisa uji sebelumnya. */
  {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
    await page.evaluate(
      async ({ api, toks }) => {
        const mod = await import('/src/lib/riwayat.js')
        for (const t of toks) {
          mod.setTokenRiwayat(t, { paksa: true })
          await mod.hapusRiwayatServer(api, null)
        }
        mod.lupakanToken()
      },
      { api: API, toks: [TOKEN_A, TOKEN_B] },
    )
    await ctx.close()
  }

  /* Bersihkan JATAH kedua akun. Uji sebelumnya (mis. uji jatah) bisa
     meninggalkan akun di 100/100 sehingga chat ditolak — itu perilaku
     yang benar, tetapi membuat uji riwayat ini gagal karena sebab yang
     salah. Uji riwayat tidak sedang menguji jatah.

     Reset TOTAL (jatah + jendela + riwayat), bukan hanya angka
     pemakaian: bila hanya angkanya dinolkan, jendela lama bisa saja
     sudah berakhir sehingga akun memakai jendela baru — hasil uji
     menjadi bergantung urutan. Reset total membuat uji ini selalu
     mulai dari keadaan yang sama. */
  {
    const ctxBersih = await browser.newContext()
    const pBersih = await ctxBersih.newPage()
    try {
      for (const sub of ['100000000000000001', '200000000000000002']) {
        const res = await pBersih.request.post(`${API}/__uji/reset`, {
          data: { sub },
        })
        if (!res.ok()) {
          throw new Error(`reset ${sub} gagal: HTTP ${res.status()}`)
        }
      }
    } catch (e) {
      console.warn(`  (pembersihan uji: ${e.message})`)
    }
    await ctxBersih.close()
  }

  /* BERSIHKAN ULANG RIWAYAT SESUDAH reset jatah, lalu PASTIKAN kosong.
     Mengapa perlu: langkah `hapusRiwayatServer` di atas dijalankan
     sebelum reset, dan reset sengaja tidak menyentuh riwayat akun lain.
     Bila uji lain (mis. uji_login_bertahan) baru saja menulis riwayat
     untuk akun yang sama, sisa itu akan muncul di perangkat 2 dan
     membuat hasil uji bergantung urutan — persis kegagalan palsu yang
     pernah terjadi. Pemeriksaan di bawah menegaskan server benar-benar
     bersih, sehingga bila nanti gagal lagi, penyebabnya BUKAN sisa
     data. */
  {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
    const sisa = await page.evaluate(
      async ({ api, toks }) => {
        const mod = await import('/src/lib/riwayat.js')
        const hasil = []
        for (const t of toks) {
          mod.setTokenRiwayat(t, { paksa: true })
          /* Hapus berulang: hapusRiwayatServer mengembalikan hasil
             penghapusan, dan satu putaran sudah cukup untuk server uji. */
          for (let i = 0; i < 2; i += 1) await mod.hapusRiwayatServer(api, null)
          const res = await fetch(api + '/api/sessions', {
            headers: { Authorization: `Bearer ${t}` },
          })
          const j = await res.json()
          hasil.push((j.sesi || []).length)
        }
        mod.lupakanToken()
        return hasil
      },
      { api: API, toks: [TOKEN_A, TOKEN_B] },
    )
    await ctx.close()
    cek(
      'Server benar-benar bersih SEBELUM uji dimulai (tidak ada sisa uji lain)',
      sisa.every((n) => n === 0),
      `sesi tersisa per akun = ${JSON.stringify(sisa)}`,
    )
  }

  /* Tunggu sampai server SUNGGUH-SUNGGUH kosong, lalu hapus sekali lagi.
     Mengapa perlu: saat sebuah konteks browser ditutup, hook
     `useSessions` mengirim sisa perubahan lewat `pagehide`. Kalau uji
     lain (mis. uji_login_bertahan) baru saja menutup halamannya, kiriman
     itu bisa MENDARAT SESUDAH pembersihan di atas — sehingga perangkat 2
     melihat sisa data dan uji gagal karena sebab yang salah.

     Jadi: beri jeda agar kiriman `pagehide` selesai, lalu bersihkan dan
     PASTIKAN kosong. Bila masih ada sisa, ulangi (maks. 5 putaran). */
  {
    const ctx = await browser.newContext()
    const page = await ctx.newPage()
    await page.goto(URL_APP, { waitUntil: 'domcontentloaded' })
    const akhir = await page.evaluate(
      async ({ api, toks }) => {
        const mod = await import('/src/lib/riwayat.js')
        const hitung = async (t) => {
          mod.setTokenRiwayat(t, { paksa: true })
          const res = await fetch(api + '/api/sessions', {
            headers: { Authorization: `Bearer ${t}` },
          })
          return ((await res.json()).sesi || []).length
        }
        const tunggu = (ms) => new Promise((r) => setTimeout(r, ms))
        let hasil = []
        for (let putaran = 0; putaran < 5; putaran += 1) {
          await tunggu(1200) // biarkan kiriman pagehide mendarat
          hasil = []
          for (const t of toks) {
            mod.setTokenRiwayat(t, { paksa: true })
            await mod.hapusRiwayatServer(api, null)
            hasil.push(await hitung(t))
          }
          if (hasil.every((n) => n === 0)) break
        }
        mod.lupakanToken()
        return hasil
      },
      { api: API, toks: [TOKEN_A, TOKEN_B] },
    )
    await ctx.close()
    cek(
      'Server tetap kosong setelah menunggu kiriman pagehide',
      akhir.every((n) => n === 0),
      `sesi tersisa = ${JSON.stringify(akhir)}`,
    )
  }

  /* Bersihkan JATAH kedua akun. Uji sebelumnya (mis. uji jatah) bisa
     meninggalkan akun di 100/100 sehingga chat ditolak — itu perilaku
     yang benar, tetapi membuat uji riwayat ini gagal karena sebab yang
     salah. Uji riwayat tidak sedang menguji jatah.

     Reset TOTAL (jatah + jendela + riwayat), bukan hanya angka
     pemakaian: bila hanya angkanya dinolkan, jendela lama bisa saja
     sudah berakhir sehingga akun memakai jendela baru — hasil uji
     menjadi bergantung urutan. Reset total membuat uji ini selalu
     mulai dari keadaan yang sama. */
  {
    const ctxBersih = await browser.newContext()
    const pBersih = await ctxBersih.newPage()
    try {
      for (const sub of ['100000000000000001', '200000000000000002']) {
        const res = await pBersih.request.post(`${API}/__uji/reset`, {
          data: { sub },
        })
        if (!res.ok()) {
          throw new Error(`reset ${sub} gagal: HTTP ${res.status()}`)
        }
      }
    } catch (e) {
      console.warn(`  (pembersihan uji: ${e.message})`)
    }
    await ctxBersih.close()
  }

  /* Jeda singkat setelah reset jatah.
     Endpoint /__uji/reset juga MENGHAPUS riwayat akun. Bila perangkat 1
     mulai menyimpan tepat saat reset masih berjalan, simpanan itu bisa
     terhapus lagi, lalu pemeriksaan "data sudah sampai di server" membaca
     kosong dan uji gagal karena sebab yang salah. Jeda ini membuat
     urutannya pasti, tanpa mengubah apa pun pada aplikasi. */
  await new Promise((r) => setTimeout(r, 800))

  /* ================= PERANGKAT 1 — AKUN A ================= */
  console.log('\n=== PERANGKAT 1 (akun A) ===')
  const d1 = await bukaSebagai(browser, {
    sub: '100000000000000001',
    name: 'Akun A',
    email: 'akun.a@gmail.com',
    token: TOKEN_A,
  })
  const p1 = d1.page

  await p1.fill('.composer__input', 'Halo dari perangkat satu')
  await p1.click('.composer__send')
  await p1.waitForSelector('.msg--assistant', { timeout: 25000 })
  await p1.waitForTimeout(2600) // debounce simpan 900 ms + perjalanan

  const judul1 = await itemRiwayat(p1)
  cek('Perangkat 1 punya 1 item riwayat', judul1.length === 1, JSON.stringify(judul1))

  /* Pastikan server BENAR-BENAR sudah menerima data sebelum perangkat 2
     dibuka. Tanpa pemeriksaan ini, uji bisa gagal hanya karena balapan
     waktu (perangkat 2 membaca sebelum debounce 900 ms selesai).

     Dibaca lewat pg.REQUEST, bukan fetch di dalam halaman: pengguna yang
     sedang mengetik dapat memicu tulis ulang dan membuat bacaan kosong.
     Bila belum sampai, tunggu sebentar lalu ulangi (maks. 4 detik). */
  let tersimpanDiServer = await riwayatDiServer(p1, TOKEN_A)
  for (let i = 0; i < 4 && tersimpanDiServer.length === 0; i += 1) {
    await p1.waitForTimeout(1000)
    tersimpanDiServer = await riwayatDiServer(p1, TOKEN_A)
  }
  cek(
    'Data perangkat 1 benar-benar sudah sampai di server',
    tersimpanDiServer.length === 1,
    JSON.stringify(tersimpanDiServer),
  )

  const status1 = await p1.evaluate(() => {
    const el = document.querySelector('.sb-simpan')
    return el ? el.textContent.trim() : ''
  })
  cek('Perangkat 1 tidak menampilkan peringatan simpan', status1 === '', status1)

  /* ================= PERANGKAT 2 — AKUN A (context BARU) ================= */
  console.log('\n=== PERANGKAT 2 (akun A, localStorage kosong) ===')
  const d2 = await bukaSebagai(browser, {
    sub: '100000000000000001',
    name: 'Akun A',
    email: 'akun.a@gmail.com',
    token: TOKEN_A,
  })
  const p2 = d2.page

  /* Tunggu sampai perangkat 2 benar-benar menampilkan riwayat.
     Sebelumnya hanya diberi jeda tetap 3 detik; bila pembacaan server
     sedikit lebih lambat (server uji memakai Redis tiruan di memori),
     daftar belum terisi saat diperiksa. Sekarang: tunggu sampai muncul,
     dengan batas 12 detik, lalu periksa. */
  await p2
    .waitForFunction(() => document.querySelectorAll('.sb-item').length > 0, null, {
      timeout: 12000,
    })
    .catch(() => {})
  const judul2 = await itemRiwayat(p2)
  cek(
    'PERANGKAT 2 MELIHAT RIWAYAT PERANGKAT 1 (inti permintaan)',
    judul2.length === 1 && judul2[0] === judul1[0],
    `${JSON.stringify(judul2)} vs ${JSON.stringify(judul1)}`,
  )

  if (judul2.length > 0) {
    await p2.click('.sb-item')
    await p2.waitForTimeout(1000)
    const isi2 = await p2.$$eval('.msg--user', (els) => els.map((e) => e.textContent.trim()))
    cek(
      'Isi pesan ikut tersinkron',
      isi2.some((t) => t.includes('Halo dari perangkat satu')),
      JSON.stringify(isi2).slice(0, 90),
    )
  }

  /* ================= AKUN B ================= */
  console.log('\n=== PERANGKAT 3 (akun B) ===')
  const d3 = await bukaSebagai(browser, {
    sub: '200000000000000002',
    name: 'Akun B',
    email: 'akun.b@gmail.com',
    token: TOKEN_B,
  })
  const p3 = d3.page
  await p3.waitForTimeout(3000)
  const judul3 = await itemRiwayat(p3)
  cek('Akun B TIDAK melihat riwayat akun A', judul3.length === 0, JSON.stringify(judul3))

  /* ================= TAMU ================= */
  console.log('\n=== PERANGKAT 4 (tamu) ===')
  const ctx4 = await browser.newContext()
  const p4 = await ctx4.newPage()
  await p4.goto(URL_APP, { waitUntil: 'domcontentloaded' })
  await p4.waitForSelector('.composer__input', { timeout: 20000 })
  await p4.waitForTimeout(1500)
  const judul4 = await itemRiwayat(p4)
  cek('Tamu: riwayat kosong', judul4.length === 0, JSON.stringify(judul4))

  const kunciTamu = await p4.evaluate(() =>
    Object.keys(localStorage).filter((k) => k.includes('session')),
  )
  cek('Tamu: tidak ada kunci riwayat di perangkat', kunciTamu.length === 0, JSON.stringify(kunciTamu))

  /* ================= PANEL USAGE PER AKUN ================= */
  console.log('\n=== USAGE PER AKUN ===')
  const usageA = await p1.evaluate(async (api) => {
    const res = await fetch(api + '/usage', {
      headers: { Authorization: 'Bearer token-akun-a' },
    })
    return res.json()
  }, API)
  const usageB = await p3.evaluate(async (api) => {
    const res = await fetch(api + '/usage', {
      headers: { Authorization: 'Bearer token-akun-b' },
    })
    return res.json()
  }, API)
  const usageTamu = await p4.evaluate(async (api) => (await fetch(api + '/usage')).json(), API)

  cek(
    'Usage akun A tercatat sendiri',
    (usageA?.akun?.requests?.terpakai || 0) >= 1,
    JSON.stringify(usageA?.akun?.requests),
  )
  cek(
    'Usage akun B angka berbeda dari A',
    usageB?.akun?.requests?.terpakai !== usageA?.akun?.requests?.terpakai,
    `A=${usageA?.akun?.requests?.terpakai} B=${usageB?.akun?.requests?.terpakai}`,
  )
  cek('Tamu tidak punya bagian akun', !usageTamu?.akun)
  cek('Nama penyedia tetap disamarkan', usageA?.provider === 'gungdev')

  /* ================= PANEL USAGE DI UI ================= */
  await p1.reload({ waitUntil: 'domcontentloaded' })
  await p1.evaluate(async (t) => {
    const mod = await import('/src/lib/riwayat.js')
    mod.setTokenRiwayat(t, { paksa: true })
  }, TOKEN_A)
  await p1.waitForSelector('.composer__input', { timeout: 20000 })
  await p1.waitForTimeout(1200)

  // Buka panel usage lewat tombol di header.
  const tombolUsage = await p1.$('[aria-label="Lihat jatah dan pemakaian saya"]')
  if (tombolUsage) {
    await tombolUsage.click()
    await p1.waitForTimeout(1800)
    const adaAkun = await p1.$('.usage__akun')
    const teksAkun = adaAkun ? (await adaAkun.textContent()).trim() : ''
    cek('Panel Usage menampilkan "Pemakaian saya"', Boolean(adaAkun), teksAkun.slice(0, 70))
    const tutup = await p1.$('[aria-label="Tutup dialog"]')
    if (tutup) await tutup.click()
  } else {
    cek('Panel Usage bisa dibuka', false, 'tombol tidak ditemukan')
  }

  /* ================= HAPUS DI PERANGKAT 2 ================= */
  console.log('\n=== HAPUS DI PERANGKAT 2, CEK DI PERANGKAT 1 ===')
  const hapus = await p2.evaluate(
    async ({ api, t }) => {
      const mod = await import('/src/lib/riwayat.js')
      mod.setTokenRiwayat(t, { paksa: true })
      return mod.hapusRiwayatServer(api, null)
    },
    { api: API, t: TOKEN_A },
  )
  cek('Perangkat 2 menghapus semua riwayat akun', hapus?.ok === true, JSON.stringify(hapus))

  const sisaServer = await p1.evaluate(async (api) => {
    const res = await fetch(api + '/api/sessions', {
      headers: { Authorization: 'Bearer token-akun-a' },
    })
    return (await res.json()).sesi.length
  }, API)
  cek('Server benar-benar kosong setelah dihapus', sisaServer === 0, `${sisaServer} sesi`)

  /* ================= SAKLAR SIMPAN RIWAYAT MATI ================= */
  console.log('\n=== SAKLAR "SIMPAN RIWAYAT" MATI ===')

  /* Perangkat lain dengan akun SAMA harus ditutup dulu: perangkat 1
     masih terbuka dengan saklar nyala, jadi saat ditutup ia memang akan
     mengirim ulang isi terakhirnya (pagehide). Itu perilaku yang benar,
     tetapi membuat uji ini mengukur hal yang salah. Karena itu server
     dibersihkan SESUDAH semua perangkat lain ditutup. */
  await d1.ctx.close()
  await d2.ctx.close()
  await d3.ctx.close()
  await ctx4.close()

  /* Bersihkan server setelah semua perangkat lain tertutup, supaya
     hanya perangkat 5 (saklar mati) yang mungkin menulis. */
  {
    const ctxBersih = await browser.newContext()
    const pBersih = await ctxBersih.newPage()
    await pBersih.goto(URL_APP, { waitUntil: 'domcontentloaded' })
    await pBersih.evaluate(
      async ({ api, t }) => {
        const mod = await import('/src/lib/riwayat.js')
        mod.setTokenRiwayat(t, { paksa: true })
        await mod.hapusRiwayatServer(api, null)
      },
      { api: API, t: TOKEN_A },
    )
    await ctxBersih.close()
  }

  const d5 = await bukaSebagai(
    browser,
    {
      sub: '100000000000000001',
      name: 'Akun A',
      email: 'akun.a@gmail.com',
      token: TOKEN_A,
    },
    { saveHistory: false },
  )
  const p5 = d5.page
  await p5.waitForTimeout(1200)

  await p5.fill('.composer__input', 'Pesan saat saklar mati')
  await p5.click('.composer__send')
  await p5.waitForSelector('.msg--assistant', { timeout: 25000 })
  await p5.waitForTimeout(2600)

  const serverSetelahSaklarMati = await p5.evaluate(async (api) => {
    const res = await fetch(api + '/api/sessions', {
      headers: { Authorization: 'Bearer token-akun-a' },
    })
    const d = await res.json()
    return { jumlah: d.sesi.length, judul: d.sesi.map((s) => s.title) }
  }, API)
  cek(
    'Saklar mati -> server TIDAK ditulisi',
    serverSetelahSaklarMati.jumlah === 0,
    `${serverSetelahSaklarMati.jumlah} sesi: ${JSON.stringify(serverSetelahSaklarMati.judul)}`,
  )

  await browser.close()

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
