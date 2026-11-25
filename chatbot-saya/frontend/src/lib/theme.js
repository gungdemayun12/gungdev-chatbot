/**
 * theme.js — pengelolaan tema Terang / Gelap / Ikuti Sistem.
 *
 * Tema diterapkan dengan atribut data-theme pada <html>, sehingga semua
 * CSS variable di index.css otomatis berganti. Pilihan disimpan di
 * localStorage dengan key "gungdev:theme".
 */
import { KEYS, readString, writeString } from './storage.js'

export const THEME_FALLBACK = 'system'

/** Apakah sistem operasi sedang memakai mode gelap? */
export function systemPrefersDark() {
  return (
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-color-scheme: dark)').matches
  )
}

/** Mengubah preferensi ('light' | 'dark' | 'system') menjadi tema efektif. */
export function resolveTheme(pref) {
  if (pref === 'light' || pref === 'dark') return pref
  return systemPrefersDark() ? 'dark' : 'light'
}

/** Membaca preferensi tema yang tersimpan. */
export function getThemePref() {
  const v = readString(KEYS.THEME, THEME_FALLBACK)
  return v === 'light' || v === 'dark' || v === 'system' ? v : THEME_FALLBACK
}

/**
 * Menerapkan tema ke <html> dan (opsional) menyimpannya.
 * Juga menyesuaikan meta theme-color agar bilah browser ikut berubah.
 */
export function applyTheme(pref, { persist = true } = {}) {
  const effective = resolveTheme(pref)
  const root = document.documentElement
  root.setAttribute('data-theme', effective)

  if (persist) writeString(KEYS.THEME, pref)

  // Sesuaikan warna bilah browser di perangkat mobile.
  const meta = document.querySelector('meta[name="theme-color"]:not([media])')
  const color = effective === 'dark' ? '#1f1e1d' : '#faf9f5'
  if (meta) {
    meta.setAttribute('content', color)
  } else {
    const tag = document.createElement('meta')
    tag.name = 'theme-color'
    tag.content = color
    document.head.appendChild(tag)
  }

  return effective
}
