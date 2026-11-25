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
 *
 * =====================================================================
 *  KEMAMPUAN (vision / browser)
 * =====================================================================
 * Tidak semua model bisa membaca gambar atau melakukan riset web.
 * Nilai di bawah adalah CADANGAN untuk tampilan. Sumber kebenaran tetap
 * server (GET /capabilities), karena server yang benar-benar memproses.
 * Bila backend dan file ini berbeda, yang dipakai adalah data server.
 *
 *   vision  : bisa "melihat" gambar (JPG/PNG/WEBP)
 *   browser : bisa riset di web memakai browser bawaan penyedia
 *
 * Per dokumentasi Groq, dari model gratis di atas hanya
 * qwen/qwen3.8-27b yang multimodal, dan hanya keluarga GPT-OSS yang
 * mendukung browser_search.
 */

export const MODEL_PILIHAN = [
  {
    // Nama asli model — ditampilkan di menu.
    id: 'openai/gpt-oss-120b',
    // Nama pendek untuk tombol di kotak pesan (ruangnya sempit).
    singkat: 'GPT-OSS 120B',
    ket: 'Paling teliti, cocok untuk soal rumit',
    Icon: 'Sparkles',
    vision: false,
    browser: true,
  },
  {
    id: 'openai/gpt-oss-20b',
    singkat: 'GPT-OSS 20B',
    ket: 'Paling cepat, ringan untuk chat harian',
    Icon: 'Zap',
    vision: false,
    browser: true,
  },
  {
    id: 'qwen/qwen3.8-27b',
    singkat: 'Qwen3.8 27B',
    ket: 'Bisa membaca gambar, gaya jawaban berbeda',
    Icon: 'Brain',
    vision: true,
    browser: false,
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

/** Daftar id semua model yang bisa dipilih (untuk validasi pengaturan). */
export const MODEL_ID = MODEL_PILIHAN.map((m) => m.id)

/**
 * Menggabungkan kemampuan dari server ke daftar model.
 *
 * `capabilities` berasal dari GET /capabilities. Bila null (backend lama
 * atau offline), nilai cadangan di MODEL_PILIHAN yang dipakai — UI tetap
 * berfungsi, hanya penandaannya mengikuti data bawaan.
 */
export function gabungKemampuan(capabilities) {
  if (!capabilities?.models?.length) return MODEL_PILIHAN

  const peta = new Map(capabilities.models.map((m) => [m.id, m]))
  return MODEL_PILIHAN.map((m) => {
    const dari = peta.get(m.id)
    if (!dari) return m
    return {
      ...m,
      vision: Boolean(dari.vision),
      browser: Boolean(dari.browser),
    }
  })
}

/**
 * Model yang dipakai otomatis bila pengguna melampirkan gambar tetapi
 * model pilihannya bukan model vision.
 */
export function modelUntukGambar(capabilities) {
  return capabilities?.vision_default || MODEL_PILIHAN.find((m) => m.vision)?.id || MODEL_DEFAULT
}

/**
 * Model yang dipakai otomatis bila pengguna meminta riset web tetapi
 * model pilihannya tidak mendukung browser.
 */
export function modelUntukRiset(capabilities) {
  return capabilities?.browser_default || MODEL_PILIHAN.find((m) => m.browser)?.id || MODEL_DEFAULT
}
