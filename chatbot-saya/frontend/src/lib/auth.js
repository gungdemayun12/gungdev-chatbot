/**
 * auth.js — login dengan Google (Google Identity Services).
 *
 * Cara kerjanya (tanpa backend, tanpa database):
 *   1. Google Identity Services (GIS) membuka jendela pilih akun.
 *   2. Setelah pengguna memilih akun, Google mengembalikan ID token
 *      (JWT) yang ditandatangani Google.
 *   3. ID token itu DIBACA di browser untuk mengambil nama, email, dan
 *      `sub` (ID unik akun), lalu disimpan di perangkat ini.
 *
 * Kenapa aman untuk kebutuhan kita:
 *   - Tidak ada yang dirahasiakan di sini. Client ID Google memang
 *     dirancang publik (terlihat di setiap situs yang memakai login
 *     Google). Tidak ada Client Secret di frontend.
 *   - `sub` dipakai sebagai kunci riwayat supaya dua akun berbeda di
 *     satu perangkat tidak saling menimpa.
 *
 * Batasan yang perlu diketahui (jujur):
 *   Status login di sini dipakai untuk pengalaman pengguna (menyimpan
 *   riwayat, membuka batas tamu). Verifikasi kriptografis penuh atas
 *   tanda tangan token idealnya dilakukan di server. Karena riwayat
 *   hanya tersimpan di perangkat pengguna sendiri, tidak ada data
 *   milik orang lain yang bisa diakses lewat cara ini.
 */
import { KEYS, readJSON, writeJSON, removeKey } from './storage.js'

/** Client ID dibaca dari build (VITE_GOOGLE_CLIENT_ID di Vercel). */
export const GOOGLE_CLIENT_ID = (import.meta.env?.VITE_GOOGLE_CLIENT_ID || '').trim()

/** Apakah login Google sudah dikonfigurasi untuk situs ini? */
export const LOGIN_TERSEDIA = Boolean(GOOGLE_CLIENT_ID)

const SKRIP_GIS = 'https://accounts.google.com/gsi/client'

/** Masa berlaku sesi login di perangkat ini (30 hari). */
const UMUR_SESI_MS = 30 * 24 * 60 * 60 * 1000

/* ------------------------------------------------------------------ */
/* 1. Memuat skrip Google sekali saja                                  */
/* ------------------------------------------------------------------ */
let janjiSkrip = null

/** Memuat https://accounts.google.com/gsi/client (sekali, lalu cache). */
export function muatSkripGoogle() {
  if (typeof window === 'undefined') return Promise.reject(new Error('Tidak ada browser.'))
  if (window.google?.accounts?.id) return Promise.resolve()
  if (janjiSkrip) return janjiSkrip

  janjiSkrip = new Promise((resolve, reject) => {
    const sudahAda = document.querySelector(`script[src="${SKRIP_GIS}"]`)
    if (sudahAda) {
      sudahAda.addEventListener('load', () => resolve())
      sudahAda.addEventListener('error', () => reject(new Error('Gagal memuat Google.')))
      return
    }

    const el = document.createElement('script')
    el.src = SKRIP_GIS
    el.async = true
    el.defer = true
    el.onload = () => resolve()
    el.onerror = () => {
      janjiSkrip = null // boleh dicoba lagi nanti
      reject(new Error('Gagal memuat layanan login Google.'))
    }
    document.head.appendChild(el)
  })

  return janjiSkrip
}

/* ------------------------------------------------------------------ */
/* 2. Membaca ID token (JWT)                                           */
/* ------------------------------------------------------------------ */
/** Mengurai payload JWT tanpa memverifikasi tanda tangan. */
function bacaPayload(jwt) {
  try {
    const bagian = String(jwt).split('.')
    if (bagian.length !== 3) return null
    const base64 = bagian[1].replace(/-/g, '+').replace(/_/g, '/')
    const padding = '='.repeat((4 - (base64.length % 4)) % 4)
    const json = decodeURIComponent(
      atob(base64 + padding)
        .split('')
        .map((c) => `%${c.charCodeAt(0).toString(16).padStart(2, '0')}`)
        .join(''),
    )
    return JSON.parse(json)
  } catch {
    return null
  }
}

/**
 * Mengubah ID token Google menjadi objek akun yang kita pakai.
 * Mengembalikan null bila token tidak sah / bukan untuk situs ini.
 */
export function akunDariToken(idToken) {
  const payload = bacaPayload(idToken)
  if (!payload) return null

  // Token harus memang ditujukan untuk aplikasi kita.
  if (GOOGLE_CLIENT_ID && payload.aud && payload.aud !== GOOGLE_CLIENT_ID) return null
  // Token kedaluwarsa (exp dalam detik).
  if (payload.exp && Date.now() >= payload.exp * 1000) return null
  if (!payload.sub) return null

  return {
    sub: String(payload.sub),
    name: (payload.name || payload.given_name || 'Pengguna').toString().slice(0, 80),
    email: (payload.email || '').toString().slice(0, 160),
    picture: (payload.picture || '').toString(),
    loginPada: Date.now(),
  }
}

/* ------------------------------------------------------------------ */
/* 3. Menyimpan & membaca sesi login di perangkat                      */
/* ------------------------------------------------------------------ */
export function bacaSesiTersimpan() {
  const raw = readJSON(KEYS.AUTH, null)
  if (!raw || typeof raw !== 'object' || !raw.sub) return null
  if (!raw.loginPada || Date.now() - raw.loginPada > UMUR_SESI_MS) {
    removeKey(KEYS.AUTH)
    return null
  }
  return {
    sub: String(raw.sub),
    name: (raw.name || 'Pengguna').toString(),
    email: (raw.email || '').toString(),
    picture: (raw.picture || '').toString(),
    loginPada: raw.loginPada,
  }
}

export function simpanSesi(akun) {
  writeJSON(KEYS.AUTH, akun)
}

export function hapusSesi() {
  removeKey(KEYS.AUTH)
}

/* ------------------------------------------------------------------ */
/* 4. Meminta login ke Google                                          */
/* ------------------------------------------------------------------ */
let siapGIS = false

/** Menyiapkan GIS sekali (initialize cukup dipanggil sekali). */
async function siapkanGIS() {
  await muatSkripGoogle()
  if (siapGIS) return
  window.google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    // Tombol resmi Google langsung dipakai; tidak perlu One Tap popup.
    auto_select: false,
    cancel_on_tap_outside: true,
    use_fedcm_for_prompt: true,
    // Tidak mengirim kredensial ke server mana pun — kita hanya butuh
    // identitas di browser.
    callback: () => {},
  })
  siapGIS = true
}

/**
 * Menampilkan jendela pilih akun Google.
 *
 * Memakai renderButton resmi Google di dalam elemen tersembunyi lalu
 * mengkliknya secara terprogram. Ini cara yang didukung Google dan
 * lebih andal daripada prompt() yang sering diblokir peramban.
 *
 * @param {{ onAkun: (akun:object)=>void, onError: (pesan:string)=>void, wadah: HTMLElement }} params
 * @returns {Promise<() => void>} fungsi pembatalan
 */
export async function mulaiLoginGoogle({ onAkun, onError, wadah }) {
  if (!LOGIN_TERSEDIA) {
    onError(
      'Login Google belum diaktifkan di situs ini. Pemilik situs perlu mengisi Client ID Google.',
    )
    return () => {}
  }

  try {
    await siapkanGIS()
  } catch {
    onError('Tidak dapat menghubungi layanan login Google. Periksa koneksi internet Anda.')
    return () => {}
  }

  const g = window.google?.accounts?.id
  if (!g) {
    onError('Layanan login Google tidak tersedia di peramban ini.')
    return () => {}
  }

  let sudahJalan = false
  const bereskan = () => {
    if (wadah) wadah.innerHTML = ''
  }

  g.initialize({
    client_id: GOOGLE_CLIENT_ID,
    auto_select: false,
    cancel_on_tap_outside: true,
    use_fedcm_for_prompt: true,
    callback: (res) => {
      sudahJalan = true
      bereskan()
      const akun = akunDariToken(res?.credential)
      if (!akun) {
        onError('Login Google gagal dibaca. Silakan coba lagi.')
        return
      }
      onAkun(akun)
    },
  })

  if (wadah) {
    wadah.innerHTML = ''
    g.renderButton(wadah, {
      type: 'standard',
      theme: 'outline',
      size: 'large',
      text: 'signin_with',
      shape: 'pill',
      logo_alignment: 'left',
      width: 260,
    })
  }

  g.disableAutoSelect()
  g.prompt((notifikasi) => {
    // "not_displayed" = jendela tidak muncul (mis. diblokir). Beri tahu
    // pengguna untuk mencoba lagi, jangan diam saja.
    if (!sudahJalan && notifikasi?.isNotDisplayed?.()) {
      bereskan()
      onError(
        'Jendela login Google tidak bisa dibuka. Coba lagi, atau izinkan pop-up untuk situs ini.',
      )
    }
  })

  return bereskan
}

/* ------------------------------------------------------------------ */
/* 5. Utilitas tampilan                                                */
/* ------------------------------------------------------------------ */

/**
 * Inisial untuk avatar: "Ni Luh Ayu" -> "NL".
 * Nama satu kata -> satu huruf. Nama kosong -> "G".
 */
export function inisial(nama) {
  const bersih = (nama || '').trim()
  if (!bersih) return 'G'
  const kata = bersih.split(/\s+/).filter(Boolean)
  if (kata.length === 1) return kata[0].charAt(0).toUpperCase()
  return (kata[0].charAt(0) + kata[kata.length - 1].charAt(0)).toUpperCase()
}
