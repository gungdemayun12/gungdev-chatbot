/**
 * storage.js — pembungkus localStorage yang aman.
 *
 * Semua data aplikasi memakai prefix "gungdev:" agar tidak bentrok dengan
 * key lain. Setiap fungsi dibungkus try/catch supaya aplikasi tetap jalan
 * walau localStorage diblokir (mode privat) atau penuh.
 */
const PREFIX = 'gungdev:'

export const KEYS = {
  /* Riwayat TAMU (sebelum login). Sekarang hanya dipakai untuk
     membersihkan sisa data versi lama — riwayat tamu tidak disimpan. */
  SESSIONS: PREFIX + 'sessions',
  ACTIVE_SESSION: PREFIX + 'active-session',
  SETTINGS: PREFIX + 'settings',
  THEME: PREFIX + 'theme',
  PROFILE: PREFIX + 'profile',

  // --- Login Google (semua di perangkat ini) ---
  AUTH: PREFIX + 'auth', // sesi login { sub, name, email, exp }
  GUEST: PREFIX + 'guest', // hitungan pemakaian tamu { hari, terpakai }

  /* Awalan kunci riwayat PER AKUN Google:
       gungdev:sessions:<sub>
       gungdev:active-session:<sub>
     Dipisah per `sub` (ID unik Google, tidak berubah walau ganti nama
     atau email) supaya dua akun di satu perangkat tidak saling
     mencampur riwayat. */
  SESSIONS_PREFIX: PREFIX + 'sessions:',
  ACTIVE_SESSION_PREFIX: PREFIX + 'active-session:',
}

/** Kunci riwayat milik satu akun Google. */
export function keySessions(sub) {
  return KEYS.SESSIONS_PREFIX + sub
}

/** Kunci sesi aktif milik satu akun Google. */
export function keyActiveSession(sub) {
  return KEYS.ACTIVE_SESSION_PREFIX + sub
}

/**
 * Menghapus seluruh kunci berawalan tertentu.
 * Dipakai untuk membersihkan data sensitif versi lama.
 */
export function removeKeysWithPrefix(prefix) {
  try {
    const buang = []
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      if (k && k.startsWith(prefix)) buang.push(k)
    }
    buang.forEach((k) => localStorage.removeItem(k))
  } catch {
    /* localStorage diblokir: tidak ada yang perlu dibersihkan */
  }
}

/** Membaca nilai JSON. Mengembalikan `fallback` jika tidak ada / rusak. */
export function readJSON(key, fallback) {
  try {
    const raw = localStorage.getItem(key)
    if (raw === null) return fallback
    const parsed = JSON.parse(raw)
    return parsed === null || parsed === undefined ? fallback : parsed
  } catch {
    return fallback
  }
}

/** Menulis nilai JSON. Mengembalikan true bila berhasil. */
export function writeJSON(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
    return true
  } catch {
    return false
  }
}

/** Membaca string biasa. */
export function readString(key, fallback = null) {
  try {
    const v = localStorage.getItem(key)
    return v === null ? fallback : v
  } catch {
    return fallback
  }
}

/** Menulis string biasa (dipakai untuk preferensi tema). */
export function writeString(key, value) {
  try {
    localStorage.setItem(key, value)
    return true
  } catch {
    return false
  }
}

/** Menghapus satu key. */
export function removeKey(key) {
  try {
    localStorage.removeItem(key)
  } catch {
    /* abaikan */
  }
}
