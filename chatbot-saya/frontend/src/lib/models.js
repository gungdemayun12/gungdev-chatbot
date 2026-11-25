/**
 * models.js — daftar model yang boleh dipilih pengguna.
 *
 * =====================================================================
 *  HANYA LABEL PUBLIK.
 * =====================================================================
 *
 * File ini sengaja TIDAK memuat nama model teknis, nama penyedia, atau
 * alamat layanan apa pun. Yang dikirim ke server hanyalah `id` pendek
 * ("pintar" / "cepat"); server yang tahu model sebenarnya.
 *
 * Konsekuensi keamanan:
 *   - Pengunjung tidak bisa melihat model apa yang dipakai di baliknya.
 *   - Pengunjung tidak bisa menyisipkan nama model lain; server
 *     mengabaikan nilai di luar daftar dan memakai default.
 *
 * Menambah pilihan: tambahkan objek di sini DAN di KATALOG_MODEL pada
 * backend/main.py dengan `id` yang sama.
 */
export const MODEL_PILIHAN = [
  {
    id: 'pintar',
    label: 'Pintar',
    hint: 'Lebih teliti untuk soal rumit',
    Icon: 'Sparkles',
  },
  {
    id: 'cepat',
    label: 'Cepat',
    hint: 'Jawaban lebih gesit, lebih ringan',
    Icon: 'Zap',
  },
]

/** Pilihan bawaan (juga dipakai bila pilihan tersimpan tidak dikenal). */
export const MODEL_DEFAULT = 'pintar'

/** Mencari definisi model dari id; selalu mengembalikan objek yang valid. */
export function cariModel(id) {
  return (
    MODEL_PILIHAN.find((m) => m.id === id) ||
    MODEL_PILIHAN.find((m) => m.id === MODEL_DEFAULT) ||
    MODEL_PILIHAN[0]
  )
}
