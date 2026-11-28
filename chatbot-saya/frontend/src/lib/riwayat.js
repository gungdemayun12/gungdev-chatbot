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
 * 3. Token disimpan di perangkat supaya sesi login BERTAHAN setelah
 *    halaman dimuat ulang (lihat penjelasan di `tokenAktif`).
 */
import { normalizeUrl } from './api.js'
import { KEYS, readJSON, writeJSON, removeKey } from './storage.js'

/**
 * Kunci penyimpanan token di perangkat.
 *
 * MENGAPA TOKEN DISIMPAN (dulu hanya di memori)
 * ---------------------------------------------
 * ID token Google hanya hidup di memori, jadi setiap kali halaman
 * dimuat ulang token itu hilang. Akibatnya pengguna yang SUDAH login
 * terlihat seperti belum login: sidebar menampilkan "Masuk dengan
 * Google", riwayat tidak bisa dibaca, dan muncul ajakan masuk lagi —
 * padahal ia tidak pernah keluar. Itu tidak seperti Claude/ChatGPT.
 *
 * Sekarang token disimpan bersama sesi login (kunci terpisah), sehingga
 * membuka situs besok lupa/lewat beberapa hari tetap login.
 *
 * Yang menentukan masa berlaku BUKAN penyimpanan ini, melainkan Google:
 * ID token membawa `exp` (biasanya ~1 jam). Token yang sudah lewat
 * `exp` dianggap tidak ada, dan aplikasi meminta token segar tanpa
 * popup (lihat `pulihkanTokenRiwayat` di auth.js).
 *
 * Keamanan: token adalah kredensial; karena itu ia dihapus setiap
 * pengguna menekan "Keluar" (`lupakanToken`) dan otomatis dibuang bila
 * kedaluwarsa. Server tetap memverifikasi tanda tangannya ke Google
 * pada setiap permintaan, jadi token palsu tidak bisa dipakai.
 */
const KUNCI_TOKEN = KEYS.TOKEN_RIWAYAT || 'gungdev:token-riwayat'

/** Cadangan kedaluwarsa: jangan pakai token yang hampir habis. */
const JEDA_KEDALUWARSA_MS = 60 * 1000

/** Membaca `exp` dari JWT tanpa memverifikasi tanda tangan. */
function expDariJwt(jwt) {
  try {
    const bagian = String(jwt).split('.')
    if (bagian.length !== 3) return 0
    const base64 = bagian[1].replace(/-/g, '+').replace(/_/g, '/')
    const padding = '='.repeat((4 - (base64.length % 4)) % 4)
    const json = JSON.parse(atob(base64 + padding))
    return Number(json?.exp) || 0
  } catch {
    return 0
  }
}

/** True bila token masih berlaku (dengan jeda aman 1 menit). */
function tokenMasihBerlaku(token) {
  if (!token) return false
  const exp = expDariJwt(token)
  // Token tanpa `exp` tetap dipakai; server yang memutuskan sah/tidak.
  if (!exp) return true
  return Date.now() + JEDA_KEDALUWARSA_MS < exp * 1000
}

/** Token aktif di memori (diisi sekali saat halaman dimuat). */
let tokenAktif = null
let sudahMuatToken = false

/* Penanda "pengguna sudah menekan Keluar".
   Selama penanda ini aktif, token yang datang dari pemulihan diam-diam
   DITOLAK — sesi yang sudah diakhiri tidak boleh hidup kembali sendiri.
   Penanda direset hanya saat pengguna menekan tombol login lagi. */
let dibatalkanPengguna = false

/** Mengisi `tokenAktif` dari perangkat SEKALI (lazy). */
function muatTokenSekali() {
  if (sudahMuatToken) return
  sudahMuatToken = true
  // Dibatalkan pengguna = token tidak boleh dihidupkan lagi sama sekali.
  if (dibatalkanPengguna) return
  const tersimpan = readJSON(KUNCI_TOKEN, null)
  const token = (tersimpan?.token || '').trim()
  if (token && tokenMasihBerlaku(token)) {
    tokenAktif = token
  } else if (tersimpan) {
    removeKey(KUNCI_TOKEN)
  }
}

/**
 * Menyimpan token baru dari Google (ke memori + perangkat).
 *
 * @param {string} token
 * @param {{paksa?: boolean}} opsi `paksa` = abaikan penanda "sudah keluar".
 *   Dipakai HANYA setelah pengguna benar-benar menekan tombol login lagi.
 *   Pemulihan diam-diam tidak boleh memakai `paksa`, supaya sesi yang
 *   sudah diakhiri tidak hidup kembali sendiri.
 */
export function setTokenRiwayat(token, { paksa = false } = {}) {
  const bersih = (token || '').trim()
  if (bersih && dibatalkanPengguna && !paksa) return
  if (paksa) dibatalkanPengguna = false
  tokenAktif = bersih || null
  sudahMuatToken = true
  if (tokenAktif) {
    writeJSON(KUNCI_TOKEN, { token: tokenAktif, pada: Date.now() })
  } else {
    removeKey(KUNCI_TOKEN)
  }
}

/** Mengambil token yang sedang aktif (null bila belum login / kedaluwarsa). */
export function getTokenRiwayat() {
  muatTokenSekali()
  if (tokenAktif && !tokenMasihBerlaku(tokenAktif)) {
    tokenAktif = null
    removeKey(KUNCI_TOKEN)
  }
  return tokenAktif
}

/** Melupakan token (dipakai saat pengguna benar-benar keluar). */
export function lupakanToken() {
  tokenAktif = null
  sudahMuatToken = true
  dibatalkanPengguna = true
  removeKey(KUNCI_TOKEN)
}

/**
 * Dipakai HANYA saat pengguna menekan tombol login: membuka izin agar
 * token berikutnya diterima kembali.
 */
export function izinkanTokenLagi() {
  dibatalkanPengguna = false
}

function headerOtorisasi() {
  const token = getTokenRiwayat()
  return token ? { Authorization: `Bearer ${token}` } : {}
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

  if (!getTokenRiwayat()) return { ...kosong, perluLogin: true }

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
  if (!getTokenRiwayat()) return { ok: false, tersimpan: false, perluLogin: true }

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
  if (!getTokenRiwayat() || !Array.isArray(daftarSesi) || daftarSesi.length === 0) {
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

/**
 * Meminta server membuat JUDUL RIWAYAT dari topik percakapan.
 *
 * Kenapa perlu server: judul yang baik menyimpulkan isi sesi, bukan
 * memotong kalimat pertama. Model bahasa bisa melakukannya; pemotongan
 * teks di browser tidak.
 *
 * Tidak pernah melempar error: bila server tidak bisa dihubungi, hasilnya
 * `null` dan pemanggil memakai judul lokal (`makeTitle`).
 *
 * @param {Array<{role: string, content: string}>} pesan
 * @returns {Promise<string|null>}
 */
export async function buatJudulServer(baseUrl, pesan, { signal, model } = {}) {
  if (!Array.isArray(pesan) || pesan.length === 0) return null

  try {
    const res = await fetch(`${normalizeUrl(baseUrl)}/judul`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pesan: pesan.map((m) => ({
          role: m.role === 'assistant' ? 'assistant' : 'user',
          content: String(m.content || '').slice(0, 1200),
        })),
        model: model || undefined,
      }),
      signal,
    })
    if (!res.ok) return null

    const data = await res.json()
    const judul = String(data?.judul || '').trim()
    return judul || null
  } catch {
    return null
  }
}

/** Menyimpan sesi yang sedang dibuka. */
export async function simpanAktifServer(baseUrl, activeId, { signal } = {}) {
  if (!getTokenRiwayat()) return { ok: false }

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
  if (!getTokenRiwayat()) return { ok: false, perluLogin: true }

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
