/**
 * storage.js — pembungkus localStorage yang aman.
 *
 * Semua data aplikasi memakai prefix "gungdev:" agar tidak bentrok dengan
 * key lain. Setiap fungsi dibungkus try/catch supaya aplikasi tetap jalan
 * walau localStorage diblokir (mode privat) atau penuh.
 */
const PREFIX = 'gungdev:'

export const KEYS = {
  SESSIONS: PREFIX + 'sessions',
  ACTIVE_SESSION: PREFIX + 'active-session',
  SETTINGS: PREFIX + 'settings',
  THEME: PREFIX + 'theme',
  PROFILE: PREFIX + 'profile',
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
