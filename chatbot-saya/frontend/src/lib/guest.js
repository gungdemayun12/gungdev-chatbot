/**
 * guest.js — batas pemakaian untuk pengunjung yang BELUM login.
 *
 * Aturan (sama seperti semangat ChatGPT):
 *   - Tamu tetap boleh mencoba, tapi sangat dibatasi: 3 pesan per hari.
 *   - Hitungan disimpan di perangkat ini saja (localStorage), direset
 *     otomatis saat tanggal berganti.
 *   - Riwayat percakapan tamu TIDAK disimpan. Setelah login, riwayat
 *     baru disimpan.
 *
 * Catatan jujur: batas di browser bisa diakali (orang bisa menghapus
 * data situs). Ini memang pilihan yang disepakati: gratis, tanpa
 * database, dan cukup untuk pengunjung biasa.
 */
import { KEYS, readJSON, writeJSON } from './storage.js'

/** Jumlah pesan yang boleh dikirim tamu per hari. */
export const BATAS_TAMU = 3

/**
 * Penanda tanggal lokal (format YYYY-MM-DD).
 *
 * Sengaja memakai tanggal LOKAL pengguna, bukan UTC: orang Indonesia
 * akan merasa "besok" mulai tengah malam WIB, bukan jam 07.00 pagi.
 */
export function hariIni(date = new Date()) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** Membaca hitungan tamu hari ini (diperbaiki bila data rusak/basi). */
export function bacaPemakaianTamu() {
  const hari = hariIni()
  const raw = readJSON(KEYS.GUEST, null)

  /** Bentuk aman saat data belum ada atau sudah lewat hari. */
  const kosong = { hari, terpakai: 0 }

  if (!raw || typeof raw !== 'object') return kosong
  if (raw.hari !== hari) return kosong

  const terpakai = Number(raw.terpakai)
  if (!Number.isFinite(terpakai) || terpakai < 0) return kosong

  return { hari, terpakai: Math.min(BATAS_TAMU, Math.floor(terpakai)) }
}

/**
 * Mencatat satu pesan tamu.
 * Mengembalikan keadaan SETELAH pencatatan.
 */
export function catatPesanTamu() {
  const sekarang = bacaPemakaianTamu()
  const baru = {
    hari: sekarang.hari,
    terpakai: Math.min(BATAS_TAMU, sekarang.terpakai + 1),
  }
  writeJSON(KEYS.GUEST, baru)
  return baru
}

/** Menghapus hitungan tamu (dipakai saat logout / setelah login). */
export function resetPemakaianTamu() {
  writeJSON(KEYS.GUEST, { hari: hariIni(), terpakai: 0 })
}

/**
 * Ringkasan untuk UI: sisa pesan, apakah sudah habis, dan apakah
 * pengunjung hampir kehabisan (untuk ajakan login yang halus).
 */
export function ringkasTamu(pemakaian = bacaPemakaianTamu()) {
  const terpakai = Math.min(BATAS_TAMU, pemakaian.terpakai || 0)
  const sisa = Math.max(0, BATAS_TAMU - terpakai)
  return {
    batas: BATAS_TAMU,
    terpakai,
    sisa,
    habis: sisa === 0,
    // Muncul setelah pesan pertama: pengingat lembut, bukan menghalangi.
    perluIngat: sisa > 0 && sisa <= 1,
  }
}
