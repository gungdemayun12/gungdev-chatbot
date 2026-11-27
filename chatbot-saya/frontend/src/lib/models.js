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
 *  SEMUA MODEL PUNYA KEMAMPUAN YANG SAMA
 * =====================================================================
 * Setiap model di sini bisa melakukan hal yang sama tanpa pengguna perlu
 * berganti model:
 *
 *   - riset web   -> dikerjakan SERVER (lihat backend/riset.py), jadi
 *                    berlaku untuk semua model & penyedia.
 *   - baca file   -> file diekstrak menjadi teks sebelum dikirim.
 *   - baca gambar -> bergantung pada modelnya sendiri.
 *
 * Karena itu TIDAK ADA penanda khusus "bisa riset" per model: semua bisa.
 * Satu-satunya perbedaan nyata adalah `vision` (membaca gambar), karena
 * itu batasan modelnya sendiri. Bila gambar dikirim ke model non-vision,
 * backend otomatis mengalihkan ke model vision dan memberi tahu pengguna.
 *
 * Backend tetap sumber kebenaran: `gabungKemampuan()` menimpa nilai di
 * bawah dengan data dari GET /capabilities bila tersedia.
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
    ket: 'Seimbang untuk chat dan gambar',
    Icon: 'Brain',
    vision: true,
    browser: true,
  },
  {
    id: 'google/gemini-2.5-flash-tts',
    singkat: 'Gemini Flash TTS',
    ket: 'Cepat untuk percakapan multimodal',
    Icon: 'Sparkles',
    vision: true,
    browser: true,
  },
  {
    id: 'google/gemini-3.1-flash-lite',
    singkat: 'Gemini 3.1 Lite',
    ket: 'Ringan untuk chat cepat',
    Icon: 'Zap',
    vision: true,
    browser: true,
  },
  {
    id: 'deepseek/deepseek-v4.1-flash',
    singkat: 'DeepSeek V4.1 Flash',
    ket: 'Cepat untuk analisis dan chat',
    Icon: 'Brain',
    vision: false,
    browser: true,
  },
  // --- Model gratis: tetap bisa dipakai bila kredit utama habis ---
  {
    id: 'google/gemma-4-31b-it:free',
    singkat: 'Gemma 4 31B',
    ket: 'Gratis, bisa membaca gambar',
    Icon: 'Sparkles',
    vision: true,
    browser: true,
  },
  {
    id: 'nvidia/nemotron-3.5-super-vl:free',
    singkat: 'Nemotron 3.5 VL',
    ket: 'Gratis, konteks sangat panjang',
    Icon: 'Brain',
    vision: true,
    browser: true,
  },
  {
    id: 'inclusionai/ling-3.2-flash:free',
    singkat: 'Ling 3.2 Flash',
    ket: 'Gratis dan cepat',
    Icon: 'Zap',
    vision: true,
    browser: true,
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
      // Riset kini kemampuan server, jadi selalu tersedia. Nilai dari
      // server dipakai apa adanya agar tetap sinkron bila berubah.
      browser: dari.browser === undefined ? true : Boolean(dari.browser),
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
