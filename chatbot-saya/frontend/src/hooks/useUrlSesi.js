/**
 * useUrlSesi.js — alamat unik per percakapan (token acak di URL).
 *
 * PERMINTAAN PEMILIK SITUS
 * ------------------------
 * Setiap sesi percakapan harus punya alamat sendiri yang memuat token
 * acak, seperti `https://claude.ai/chat/5a3ed697-b226-4101-8116-27ebf4fcdc34`.
 * Tujuannya: alamat bisa disalin, disimpan sebagai penanda, dibuka lagi,
 * dan dibagikan — bukan sekadar tersembunyi di localStorage.
 *
 * BENTUK ALAMAT
 * -------------
 *   /c/<token>          contoh: /c/5a3ed697-b226-4101-8116-27ebf4fcdc34
 *
 * Kenapa `/c/` dan bukan `/chat/`:
 *   - `/chat` sudah dipakai backend sebagai rute API, jadi halaman tidak
 *     boleh memakainya agar tidak tertukar.
 *   - Satu huruf lebih pendek, tetap jelas sebagai "percakapan".
 *
 * KENAPA SEBELUMNYA TIDAK ADA
 * ---------------------------
 * Token acak sudah dibuat dan disimpan (lihat `buatTokenSesi` di
 * useSessions.js), tetapi belum pernah dipasang ke URL — sehingga token
 * itu tidak terlihat dan tidak berguna. Hook ini yang menyambungkannya.
 *
 * PRINSIP PENTING: URL hanya MENCERMINkan keadaan, bukan sumber
 * kebenaran. Bila token tidak dikenal (mis. dibuka di perangkat lain
 * yang riwayatnya belum tersinkron), aplikasi tidak boleh error — ia
 * hanya membersihkan URL dan pengguna tetap mendapat halaman yang bisa
 * dipakai. Riwayat tetap datang dari server/akun.
 */
import { useCallback, useEffect, useRef } from 'react'

/** Awalan alamat sesi. Satu tempat agar mudah diubah. */
export const AWALAN_SESI = '/c/'

/** Pola token yang diterima: UUID v4 (sama dengan yang dibuat frontend). */
const POLA_TOKEN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/

/**
 * Membaca token sesi dari URL saat ini.
 *
 * @returns {string|null} token, atau null bila alamat bukan alamat sesi.
 */
export function tokenDariUrl(lokasi = window.location) {
  const jalur = String(lokasi.pathname || '')
  if (!jalur.startsWith(AWALAN_SESI)) return null
  const kandidat = jalur
    .slice(AWALAN_SESI.length)
    .replace(/\/+$/, '')
    .toLowerCase()
  return POLA_TOKEN.test(kandidat) ? kandidat : null
}

/**
 * Mengganti alamat di bilah browser TANPA memuat ulang halaman.
 *
 * `replaceState` dipakai, bukan `pushState`: berpindah sesi bukan
 * "halaman baru" dalam riwayat browser. Kalau memakai pushState, tombol
 * Kembali akan membawa pengguna ke sesi sebelumnya satu per satu —
 * melelahkan bila ia membuka sepuluh percakapan.
 */
function tulisUrl(token) {
  const tujuan = token ? `${AWALAN_SESI}${token}` : '/'
  if (window.location.pathname === tujuan) return
  try {
    window.history.replaceState({ sesi: token || null }, '', tujuan)
  } catch {
    // Sebagian lingkungan (mis. iframe ketat) menolak history API.
    // URL saja yang gagal diperbarui — aplikasi tetap jalan.
  }
}

/**
 * Menjaga URL tetap sejalan dengan sesi yang sedang dibuka.
 *
 * Logikanya satu arah pada satu waktu, dan HANYA satu efek yang menulis
 * URL — sehingga tidak ada dua efek yang saling menimpa:
 *
 *   1. Saat data sesi pertama kali termuat: bila URL memuat /c/<token>,
 *      cari sesi bertoken itu lalu buka (`selectSession`).
 *   2. Saat sesi aktif berganti: tulis tokennya ke URL.
 *
 * @param {object} argumen
 * @param {{id:string, token?:string}|null} argumen.activeSession  sesi aktif
 * @param {Array} argumen.sessions   semua sesi (untuk mencari token dari URL)
 * @param {Function} argumen.selectSession  dipanggil bila URL menunjuk sesi lain
 * @param {boolean} argumen.loaded   data sesi sudah termuat
 * @param {boolean} argumen.tamu    pengguna belum login (riwayat tidak disimpan)
 */
export function useUrlSesi({ activeSession, sessions, selectSession, loaded, tamu = false }) {
  /* Token yang URL-nya sudah kita tulis sendiri. Dipakai agar efek
     berikutnya tidak menulis alamat yang sama berulang kali. */
  const terakhirDitulis = useRef(undefined)
  /* Apakah token dari URL sudah dicoba dicocokkan (cukup sekali). */
  const sudahCocokkan = useRef(false)
  /* Diisi oleh langkah 1 saat render ini untuk memberi tahu langkah 2
     bahwa URL sudah final — jangan ditimpa dengan sesi lama. */
  const urlFinal = useRef(false)

  /* ------------------------------------------------------------------
     LANGKAH 1 (hanya sekali): URL -> STATE
     ------------------------------------------------------------------ */
  useEffect(() => {
    if (!loaded || sudahCocokkan.current) return

    const tokenUrl = tokenDariUrl()
    if (!tokenUrl) {
      sudahCocokkan.current = true
      return
    }

    /* Bila daftar sesi masih kosong, putuskan berdasarkan SIAPA pengguna:
       - Tamu: riwayatnya memang tidak pernah ada, jadi sesi kosong adalah
         keadaan FINAL. Token di URL tidak akan pernah cocok, jadi bersihkan
         (jangan biarkan alamat yang tidak menunjuk apa pun).
       - Login: sesi kosong bisa berarti riwayatnya belum turun dari server.
         Jangan putuskan apa pun dulu, nanti dicoba lagi. */
    if (sessions.length === 0 && !tamu) return
    sudahCocokkan.current = true

    const cocok = sessions.find((s) => s.token === tokenUrl)
    if (cocok) {
      terakhirDitulis.current = cocok.token
      urlFinal.current = true
      if (activeSession?.id !== cocok.id) selectSession(cocok.id)
      /* URL sudah benar — jangan sentuh. Ini penting: `selectSession`
         baru berlaku pada render berikutnya, jadi pada render ini
         `activeSession` masih sesi lama. Tanpa penjagaan ini efek di
         bawah akan menimpa alamat yang baru saja dibuka dengan token
         sesi lama. */
      return
    }

    /* Token tidak dikenal: bukan error. Bersihkan URL supaya tidak
       menyisakan alamat yang tidak menunjuk apa pun. */
    tulisUrl(null)
    terakhirDitulis.current = null
    urlFinal.current = true
  }, [loaded, sessions, activeSession, selectSession, tamu])

  /* ------------------------------------------------------------------
     LANGKAH 2 (setiap kali sesi aktif berganti): STATE -> URL
     Dijalankan setelah langkah 1.
     ------------------------------------------------------------------ */
  useEffect(() => {
    if (!loaded) return

    /* Langkah 1 sudah memutuskan URL pada render ini (tautan dibuka atau
       token asing dibersihkan) — jangan ditimpa. */
    if (urlFinal.current) {
      urlFinal.current = false
      return
    }

    /* Sebelum pencocokan selesai, jangan menulis apa pun: URL yang dibuka
       pengguna belum sempat dibaca, dan menimpanya lebih dulu akan
       menghapus tautan yang sedang ia buka. */
    if (!sudahCocokkan.current && tokenDariUrl()) return

    const token = activeSession?.token || null
    if (token === terakhirDitulis.current) return
    terakhirDitulis.current = token
    tulisUrl(token)
  }, [loaded, activeSession?.token, activeSession?.id, sessions.length, tamu])

  /* ------------------------------------------------------------------
     LANGKAH 3: tombol Kembali / Maju browser.
     Karena kita memakai replaceState, ini praktis tidak terpicu. Tetap
     ditangani supaya alamat yang ditempel manual lalu Enter ikut
     membuka sesi yang benar.
     ------------------------------------------------------------------ */
  const cocokkan = useCallback(() => {
    const tokenUrl = tokenDariUrl()
    if (!tokenUrl) return
    const cocok = sessions.find((s) => s.token === tokenUrl)
    if (cocok && cocok.id !== activeSession?.id) {
      terakhirDitulis.current = cocok.token
      sudahCocokkan.current = true
      selectSession(cocok.id)
    }
  }, [sessions, activeSession, selectSession])

  useEffect(() => {
    window.addEventListener('popstate', cocokkan)
    return () => window.removeEventListener('popstate', cocokkan)
  }, [cocokkan])
}

export default useUrlSesi
