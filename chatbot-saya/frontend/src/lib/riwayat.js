/**
 * riwayat.js — komunikasi riwayat percakapan dengan server.
 *
 * KENAPA ADA
 * ----------
 * Dulu riwayat hanya ada di localStorage, jadi membuka situs di HP dan di
 * laptop menghasilkan dua riwayat berbeda. Sekarang riwayat disimpan di
 * server sehingga satu akun Google = riwayat yang sama di semua perangkat.
 *
 * ATURAN PENTING
 * --------------
 * 1. Modul ini TIDAK PERNAH melempar error ke UI. Semua fungsi
 *    mengembalikan status supaya pemanggil bisa memutuskan: pakai data
 *    server, atau tetap pakai salinan di perangkat. Chat tidak boleh
 *    ikut gagal hanya karena penyimpanan bermasalah.
 *
 * 2. Setiap permintaan membawa ID token Google. Server memverifikasinya
 *    ke Google, jadi permintaan tanpa token sah ditolak (401).
 *
 * 3. Token yang ditolak (kedaluwarsa) TIDAK dianggap bencana: fungsi
 *    mengembalikan `perluLogin`, dan pemanggil membiarkan pengguna
 *    memakai salinan perangkat sampai ia masuk lagi.
 */
import { normalizeUrl } from './api.js'

/**
 * Menyimpan token terakhir yang diberikan Google Identity Services.
 *
 * ID token Google berlaku sekitar 1 jam. Aplikasi bisa dipakai lebih
 * lama dari itu (tab dibiarkan terbuka), jadi token disimpan di memori
 * dan diperbarui setiap kali Google memberi kredensial baru. Token tidak
 * ditulis ke localStorage karena tidak perlu bertahan setelah tab ditutup
 * — pengguna cukup masuk sekali lagi keesokan harinya.
 */
let tokenAktif = null

/** Menyimpan token baru dari Google. */
export function setTokenRiwayat(token) {
  const bersih = (token || '').trim()
  tokenAktif = bersih || null
}

/** Mengambil token yang sedang aktif (null bila belum login). */
export function getTokenRiwayat() {
  return tokenAktif
}

/** Melupakan token (dipakai saat keluar). */
export function lupakanToken() {
  tokenAktif = null
}

function headerOtorisasi() {
  return tokenAktif ? { Authorization: `Bearer ${tokenAktif}` } : {}
}

/**
 * Membaca riwayat milik akun dari server.
 *
 * @returns {Promise<{
 *   ok: boolean,            // permintaan berhasil dijawab server
 *   tersedia: boolean,      // server benar-benar menyimpan riwayat
 *   perluLogin: boolean,    // token tidak ada / ditolak (401)
 *   sessions: Array,
 *   activeId: string|null,
 * }>}
 */
export async function ambilRiwayatServer(baseUrl, { signal } = {}) {
  const kosong = { ok: false, tersedia: false, perluLogin: false, sessions: [], activeId: null }

  if (!tokenAktif) return { ...kosong, perluLogin: true }

  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/api/sessions`, {
      method: 'GET',
      headers: { ...headerOtorisasi() },
      signal,
    })

    if (res.status === 401) return { ...kosong, perluLogin: true }
    if (!res.ok) return kosong

    const data = await res.json()
    if (!Array.isArray(data?.sesi)) return kosong

    return {
      ok: true,
      tersedia: Boolean(data?.tersedia),
      perluLogin: false,
      sessions: data.sesi,
      activeId: data?.activeId || null,
    }
  } catch {
    return kosong
  }
}

/**
 * Menyimpan satu sesi ke server.
 *
 * @returns {Promise<{ok: boolean, tersimpan: boolean, perluLogin: boolean}>}
 */
export async function simpanSesiServer(baseUrl, sesi, { signal } = {}) {
  if (!tokenAktif) return { ok: false, tersimpan: false, perluLogin: true }

  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/api/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headerOtorisasi() },
      body: JSON.stringify({ session: sesi }),
      signal,
    })

    if (res.status === 401) return { ok: false, tersimpan: false, perluLogin: true }
    if (!res.ok) return { ok: false, tersimpan: false, perluLogin: false }

    const data = await res.json()
    return { ok: true, tersimpan: Boolean(data?.tersimpan), perluLogin: false }
  } catch {
    return { ok: false, tersimpan: false, perluLogin: false }
  }
}

/**
 * Mengirim beberapa sesi sekaligus (migrasi riwayat perangkat ke server).
 *
 * Dipakai sekali setelah pengguna login: riwayat yang sudah ada di
 * perangkat dikirim ke server supaya tidak hilang dan langsung bisa
 * dibuka dari perangkat lain.
 *
 * @returns {Promise<{ok: boolean, tersimpan: number, gagal: number}>}
 */
export async function sinkronSesiServer(baseUrl, daftarSesi, { signal } = {}) {
  if (!tokenAktif || !Array.isArray(daftarSesi) || daftarSesi.length === 0) {
    return { ok: false, tersimpan: 0, gagal: 0 }
  }

  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/api/sessions/sync`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headerOtorisasi() },
      body: JSON.stringify({ sessions: daftarSesi }),
      signal,
    })
    if (!res.ok) return { ok: false, tersimpan: 0, gagal: daftarSesi.length }

    const data = await res.json()
    return {
      ok: true,
      tersimpan: Number(data?.tersimpan) || 0,
      gagal: Number(data?.gagal) || 0,
    }
  } catch {
    return { ok: false, tersimpan: 0, gagal: daftarSesi.length }
  }
}

/** Menyimpan sesi yang sedang dibuka. */
export async function simpanAktifServer(baseUrl, activeId, { signal } = {}) {
  if (!tokenAktif) return { ok: false }

  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/api/sessions/active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...headerOtorisasi() },
      body: JSON.stringify({ activeId: activeId || null }),
      signal,
    })
    return { ok: res.ok }
  } catch {
    return { ok: false }
  }
}

/**
 * Menghapus riwayat di server.
 *
 * @param {string|null} id  ID sesi, atau null untuk menghapus SEMUA.
 */
export async function hapusRiwayatServer(baseUrl, id, { signal } = {}) {
  if (!tokenAktif) return { ok: false, perluLogin: true }

  try {
    const url = new URL(`${normalizeUrl(baseUrl)}/api/sessions`)
    if (id) url.searchParams.set('id', id)

    const res = await fetch(url.toString(), {
      method: 'DELETE',
      headers: { ...headerOtorisasi() },
      signal,
    })
    if (res.status === 401) return { ok: false, perluLogin: true }
    return { ok: res.ok, perluLogin: false }
  } catch {
    return { ok: false, perluLogin: false }
  }
}
