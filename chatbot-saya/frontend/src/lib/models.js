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
    singkat: 'Gemini 3.1 Lite (OpenRouter)',
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
  // --- Gemini (penyedia cadangan, gratis tanpa kartu kredit) ---
  // Ketiganya TERBUKTI menjawab saat diuji langsung ke produksi.
  // Model 2.0 sudah dimatikan Google (1 Juni 2026) dan 2.5 sudah
  // deprecated, jadi tidak dicantumkan. Model 4-hydrogen & 3.6-flash
  // juga tidak dicantumkan karena timeout di Vercel (>60 dtk).
  {
    id: 'gemini-3.5-flash-lite',
    singkat: 'Gemini 3.5 Lite',
    ket: 'Cepat, konteks panjang, bisa gambar',
    Icon: 'Zap',
    vision: true,
    browser: true,
  },
  {
    id: 'gemini-4-argon',
    singkat: 'Gemini 4 Argon',
    ket: 'Paling baru, cepat dan teliti',
    Icon: 'Sparkles',
    vision: true,
    browser: true,
  },
  {
    id: 'gemini-3.1-flash-lite',
    singkat: 'Gemini 3.1 Lite (Gemini)',
    ket: 'Cadangan hemat kuota',
    Icon: 'Brain',
    vision: true,
    browser: true,
  },
]

/** Pilihan bawaan (juga dipakai bila pilihan tersimpan tidak dikenal). */
export const MODEL_DEFAULT = 'openai/gpt-oss-120b'

/**
 * MODEL UTAMA — yang ditampilkan lebih dulu di menu.
 *
 * MENGAPA DIBATASI
 * ----------------
 * Daftar lengkap berisi 12 model. Di ponsel, menu itu jadi sangat panjang
 * dan mendorong kotak ketik keluar layar. Padahal sebagian besar pengguna
 * hanya perlu beberapa pilihan yang jelas.
 *
 * Yang ditampilkan lengkap dengan keterangan hanyalah model yang
 * mewakili tiap keluarga: GPT, Qwen, DeepSeek, Gemini 4 Argon, dan
 * Gemini 3.5. Sisanya tetap BISA DIPILIH — hanya diletakkan di balik
 * tombol "Model lainnya" agar tampilan tetap ringkas.
 *
 * Ini murni soal tampilan: SEMUA model di MODEL_PILIHAN tetap bisa
 * dipakai, dan tidak ada kemampuan yang hilang.
 */
export const MODEL_UTAMA = [
  'openai/gpt-oss-120b',
  'qwen/qwen3.8-27b',
  'deepseek/deepseek-v4.1-flash',
  'gemini-4-argon',
  'gemini-3.5-flash-lite',
]

/** True bila model ini ditampilkan di bagian utama menu. */
export function apakahModelUtama(id) {
  return MODEL_UTAMA.includes(id)
}

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
 * Nama pendek untuk model yang BELUM terdaftar di MODEL_PILIHAN.
 *
 * Tanpa ini, model baru tampil sebagai id mentah (mis.
 * "gemini-3.1-flash-lite") dan bisa TERLIHAT SAMA dengan model lain
 * yang namanya kebetulan mirip. Itu membingungkan: dua baris berbeda
 * dengan tulisan hampir identik.
 *
 * Kunci peta ini adalah id persis seperti yang dikirim server.
 */
const NAMA_CADANGAN = {
  'gemini-3.1-flash-lite': { singkat: 'Gemini 3.1 Lite (Gemini)', ket: 'Cadangan hemat kuota', Icon: 'Brain' },
  'google/gemini-3.1-flash-lite': {
    singkat: 'Gemini 3.1 Lite (OpenRouter)',
    ket: 'Ringan untuk chat cepat',
    Icon: 'Zap',
  },
}

/**
 * Menggabungkan kemampuan dari server ke daftar model.
 *
 * `capabilities` berasal dari GET /capabilities. Bila null (backend lama
 * atau offline), nilai cadangan di MODEL_PILIHAN yang dipakai — UI tetap
 * berfungsi, hanya penandaannya mengikuti data bawaan.
 *
 * PENTING: fungsi ini juga MENAMBAH model yang ada di server tetapi belum
 * ada di MODEL_PILIHAN. Dulu fungsi ini hanya menimpa nilai vision, jadi
 * model yang baru ditambahkan di backend TIDAK PERNAH muncul di menu —
 * pengguna melihat daftar lama padahal server sudah punya model baru.
 * Sekarang server yang menentukan isi menu; MODEL_PILIHAN hanya
 * menyediakan nama pendek & keterangan (model tak dikenal tetap tampil
 * dengan nama id-nya).
 */
export function gabungKemampuan(capabilities) {
  if (!capabilities?.models?.length) return MODEL_PILIHAN

  const peta = new Map(capabilities.models.map((m) => [m.id, m]))

  // 1. Model bawaan: urutan & tampilan dipertahankan, kemampuan diperbarui.
  const hasil = MODEL_PILIHAN.map((m) => {
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

  // 2. Model yang ADA di server tetapi belum dikenal di sini -> tambahkan.
  const sudahAda = new Set(MODEL_PILIHAN.map((m) => m.id))
  for (const dari of capabilities.models) {
    if (sudahAda.has(dari.id)) continue
    const cadangan = NAMA_CADANGAN[dari.id]
    hasil.push({
      id: dari.id,
      // Nama yang jelas lebih baik daripada id mentah; model tanpa nama
      // pendek tetap bisa dipilih memakai id-nya.
      singkat: cadangan?.singkat || dari.id,
      ket: cadangan?.ket || 'Tersedia',
      Icon: cadangan?.Icon || 'Sparkles',
      vision: Boolean(dari.vision),
      browser: dari.browser === undefined ? true : Boolean(dari.browser),
    })
  }

  return hasil
}

/**
 * Model yang dipakai otomatis bila pengguna melampirkan gambar tetapi
 * model pilihannya bukan model vision.
 */
export function modelUntukGambar(capabilities) {
  return capabilities?.vision_default || MODEL_PILIHAN.find((m) => m.vision)?.id || MODEL_DEFAULT
}
