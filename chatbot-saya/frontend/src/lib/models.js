/**
 * models.js — daftar model yang bisa dipilih pengguna.
 *
 * =====================================================================
 *  HANYA MODEL YANG BENAR-BENAR TERSEDIA
 * =====================================================================
 *
 * Isi daftar ini SENGAJA dibuat sama persis dengan MODEL_DIIZINKAN di
 * backend/main.py. Server menolak (dan mengganti ke default) model yang
 * tidak ada di daftar itu, jadi jangan menambah di sini tanpa menambah
 * di sana juga.
 *
 * CATATAN PENTING (per 16 Agustus 2026):
 *   "llama-3.3-70b-versatile" dan "llama-3.1-8b-instant" TIDAK ada di
 *   daftar ini karena Groq sudah mematikannya untuk akun gratis
 *   (kini Enterprise / berbayar kontrak). Banyak tutorial lama masih
 *   menampilkannya; kalau dipasang di sini, memilih model tersebut akan
 *   selalu gagal. Penggantinya: openai/gpt-oss-120b.
 *   Rujukan: console.groq.com/docs/deprecations
 */

export const MODEL_PILIHAN = [
  {
    // Nama asli model — ditampilkan di menu.
    id: 'openai/gpt-oss-120b',
    // Nama pendek untuk tombol di kotak pesan (ruangnya sempit).
    singkat: 'GPT-OSS 120B',
    ket: 'Paling teliti, cocok untuk soal rumit',
    Icon: 'Sparkles',
  },
  {
    id: 'openai/gpt-oss-20b',
    singkat: 'GPT-OSS 20B',
    ket: 'Paling cepat, ringan untuk chat harian',
    Icon: 'Zap',
  },
  {
    id: 'qwen/qwen3.8-27b',
    singkat: 'Qwen3.8 27B',
    ket: 'Alternatif — pilihan berbeda gaya jawaban',
    Icon: 'Brain',
  },
]

/** Pilihan bawaan (juga dipakai bila pilihan tersimpan tidak dikenal). */
export const MODEL_DEFAULT = 'openai/gpt-oss-120b'

/** Mencari definisi model dari id; selalu mengembalikan objek yang valid. */
export function cariModel(id) {
  return (
    MODEL_PILIHAN.find((m) => m.id === id) ||
    MODEL_PILIHAN.find((m) => m.id === MODEL_DEFAULT) ||
    MODEL_PILIHAN[0]
  )
}
