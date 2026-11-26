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
import { setTokenRiwayat, getTokenRiwayat, lupakanToken } from './riwayat.js'

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
  // Token riwayat ikut dilupakan: setelah keluar, perangkat ini tidak
  // boleh lagi bisa membaca riwayat akun di server.
  lupakanToken()
}

/* ------------------------------------------------------------------ */
/* 4. Meminta login ke Google                                          */
/* ------------------------------------------------------------------ */
let siapGIS = false

/** Menyiapkan GIS sekali (initialize cukup dipanggil sekali). */
/**
 * Callback aktif. HANYA SATU yang boleh terpasang di Google.
 *
 * Google hanya memakai `initialize()` terakhir, jadi kalau tiap tombol
 * memanggil initialize() dengan callback sendiri-sendiri, hasil login
 * bisa nyasar ke callback yang salah (dan login tampak "tidak terjadi").
 * Solusinya: initialize() dipanggil SEKALI, lalu semua pemanggil
 * didaftarkan di sini dan dijawab bersamaan.
 */
let pendengar = new Set()

/**
 * Menyiapkan GIS. Hanya benar-benar memanggil initialize() satu kali
 * sepanjang umur halaman.
 */
async function siapkanGIS() {
  await muatSkripGoogle()
  if (siapGIS) return
  window.google.accounts.id.initialize({
    client_id: GOOGLE_CLIENT_ID,
    auto_select: false,
    cancel_on_tap_outside: true,
    callback: (res) => {
      // Teruskan hasil ke semua pemanggil yang sedang menunggu.
      const akun = akunDariToken(res?.credential)
      // ID token disimpan untuk dikirim ke backend riwayat. Backend
      // memverifikasinya ke Google; tanpa token ini riwayat akun tidak
      // bisa dibaca/ditulis (dan tidak ada akun lain yang bisa diakses).
      setTokenRiwayat(res?.credential)
      const daftar = Array.from(pendengar)
      pendengar.clear()
      daftar.forEach(({ onAkun, onError }) => {
        if (akun) onAkun(akun)
        else onError('Login Google gagal dibaca. Silakan coba lagi.')
      })
    },
  })
  siapGIS = true
}

/**
 * Memulihkan ID token SETELAH halaman dimuat ulang.
 *
 * MASALAH YANG DIPECAHKAN
 * -----------------------
 * ID token Google hanya hidup di memori (aman, tetapi hilang saat
 * refresh). Status login (`sub`, nama) justru disimpan 30 hari. Akibatnya
 * setelah refresh pengguna masih terlihat "login" tetapi riwayatnya tidak
 * bisa dibaca dari server — dan UI menyuruhnya "masuk ulang", padahal ia
 * tidak pernah keluar. Itu membingungkan.
 *
 * SOLUSI
 * ------
 * Google menyediakan `prompt()` untuk meminta kredensial baru TANPA
 * jendela popup, bila pengguna sebelumnya sudah menyetujui aplikasi ini.
 * Bila Google masih mengingat pilihannya, token baru datang sendiri
 * dalam hitungan detik.
 *
 * Bila Google memutuskan perlu interaksi (mis. pengguna logout dari
 * Google, atau memakai mode Incognito), fungsi ini selesai tanpa token
 * dan aplikasi memakai salinan perangkat — pengguna tidak dipaksa apa pun.
 *
 * Token TIDAK disimpan di localStorage: token adalah kredensial hidup,
 * bukan data tampilan, dan menyimpannya berarti memperpanjang masa
 * berlakunya jauh melebihi yang seharusnya.
 *
 * @returns {Promise<boolean>} true bila token berhasil dipulihkan
 */
export function pulihkanTokenRiwayat() {
  if (!LOGIN_TERSEDIA) return Promise.resolve(false)
  if (getTokenRiwayat()) return Promise.resolve(true)

  return new Promise((resolve) => {
    let selesai = false

    /* Batas waktu: bila Google tidak menjawab (diblokir ekstensi,
       internet lambat, dsb.), jangan biarkan halaman menunggu. */
    const batas = setTimeout(() => {
      if (selesai) return
      selesai = true
      resolve(false)
    }, 8000)

    const beres = (ok) => {
      if (selesai) return
      selesai = true
      clearTimeout(batas)
      resolve(ok)
    }

    muatSkripGoogle()
      .then(() => {
        if (!window.google?.accounts?.id?.prompt) {
          beres(false)
          return
        }

        /* Callback sementara HANYA untuk pemulihan ini. Login biasa
           memakai callback di siapkanGIS(). */
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          auto_select: true,
          cancel_on_tap_outside: true,
          callback: (res) => {
            const token = (res?.credential || '').trim()
            if (!token) {
              beres(false)
              return
            }
            setTokenRiwayat(token)
            beres(true)
          },
        })

        window.google.accounts.id.prompt((notifikasi) => {
          /* `isNotDisplayed` / `isSkippedMoment` = Google tidak memberi
             token tanpa interaksi. Itu bukan error. */
          if (
            notifikasi?.isNotDisplayed?.() ||
            notifikasi?.isSkippedMoment?.() ||
            notifikasi?.isDismissedMoment?.()
          ) {
            beres(false)
          }
        })
      })
      .catch(() => beres(false))
  })
}

/**
 * Menampilkan jendela pilih akun Google.
 *
 * Memakai renderButton resmi Google di dalam elemen tersembunyi lalu
 * mengkliknya secara terprogram. Ini cara yang didukung Google dan
 * jauh lebih andal daripada prompt()/One Tap yang sering diblokir.
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

  /* Wadah WAJIB masih ada di halaman. Tanpa ini, Google tidak bisa
     merender tombol dan popup tidak akan pernah terbuka. */
  if (!wadah || !wadah.isConnected) {
    onError('Komponen login belum siap. Tutup lalu buka lagi dialog login.')
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

  const pendaftar = { onAkun, onError }
  pendengar.add(pendaftar)

  /* Google menaruh tombol aslinya di wadah tersembunyi. Kita klik
     tombol itu secara terprogram agar tampilan GungDev tetap dipakai. */
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

  /* renderButton bekerja sinkron, jadi tombol sudah ada di sini.
     Kalau belum (mis. peramban lambat), tunggu satu putaran frame. */
  const cariTombol = () => wadah.querySelector('div[role="button"], button')
  let tombol = cariTombol()
  if (!tombol) {
    await new Promise((r) => requestAnimationFrame(() => r()))
    tombol = cariTombol()
  }

  if (!tombol) {
    pendengar.delete(pendaftar)
    onError('Tombol Google gagal disiapkan. Coba muat ulang halaman ini.')
    return () => {}
  }

  tombol.click()

  // Fungsi pembatalan: lepaskan pendengar agar tidak menumpuk.
  return () => {
    pendengar.delete(pendaftar)
    if (wadah) wadah.innerHTML = ''
  }
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
