/**
 * prompt.js — system prompt dasar GungDev.
 *
 * =====================================================================
 *  FILE INI HANYA UNTUK PENGEMBANG. JANGAN ditampilkan atau diedit
 *  dari UI publik.
 * =====================================================================
 *
 * Kenapa dipisah ke sini:
 *   Sebelumnya system prompt disimpan di localStorage sebagai bagian
 *   dari "settings", lalu ditampilkan di Pengaturan. Artinya siapa pun
 *   yang membuka situs bisa melihat isi instruksi internal (dan
 *   mengubahnya). Itu tidak perlu diketahui pengunjung umum.
 *
 *   Sekarang teksnya hanya ada di dalam build frontend dan tidak punya
 *   kontrol di UI. Untuk mengubahnya, edit konstanta di bawah lalu
 *   deploy ulang.
 *
 * Catatan: nilai di frontend ini hanya lapisan pertama. Backend juga
 * punya DEFAULT_SYSTEM_PROMPT sendiri (di main.py) yang dipakai bila
 * field system_prompt tidak dikirim — jadi mengubah salah satu saja
 * sudah berpengaruh.
 */
export const SYSTEM_PROMPT_DASAR =
  'Kamu adalah GungDev, asisten AI berbahasa Indonesia yang ramah, akurat, dan ' +
  'jelas. Jawab dalam bahasa yang digunakan pengguna. Jika tidak yakin dengan ' +
  'sebuah fakta, katakan terus terang, jangan mengarang. Gunakan format Markdown ' +
  'seperlunya. Jawab langsung ke inti tanpa basa-basi berlebihan.'
