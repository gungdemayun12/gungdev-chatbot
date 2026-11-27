/**
 * useSettings.js — semua preferensi pengguna, tersimpan di localStorage.
 *
 * Setiap perubahan langsung diterapkan ke UI (ukuran font lewat atribut
 * data-fontsize di <html>, tema lewat data-theme).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { KEYS, readJSON, writeJSON } from '../lib/storage.js'
import { DEFAULT_API_URL } from '../lib/api.js'
import { SYSTEM_PROMPT_DASAR } from '../lib/prompt.js'
import { MODEL_DEFAULT, MODEL_ID } from '../lib/models.js'
import { getThemePref, applyTheme } from '../lib/theme.js'

export const DEFAULT_SETTINGS = {
  // Umum
  theme: 'system', // 'light' | 'dark' | 'system'
  language: 'id',
  fontSize: 'medium', // 'small' | 'medium' | 'large'
  nickname: 'Kamu',

  // Personalisasi
  customInstructions: '',
  responseStyle: 'balanced', // 'concise' | 'balanced' | 'detailed'
  tone: 'casual', // 'casual' | 'formal'

  // Percakapan
  saveHistory: true,
  sendWithEnter: true, // Enter kirim, Shift+Enter baris baru
  autoScroll: true, // gulir otomatis ke pesan terbaru
  showTimestamps: false, // tampilkan jam pada pesan
  confirmBeforeDelete: true, // tanya dulu sebelum menghapus percakapan

  // Personalisasi tambahan
  bahasaJawaban: 'id', // 'id' | 'en' — bahasa jawaban AI (bukan antarmuka)
  panjangJawaban: 'sedang', // 'pendek' | 'sedang' | 'panjang'

  // Lanjutan
  //
  // apiUrl SENGAJA dibiarkan kosong ('').
  // Artinya: "ikuti nilai bawaan aplikasi" (VITE_API_URL saat produksi,
  // atau http://localhost:8000 saat dev).
  //
  // Ini mencegah masalah lama: bila pengguna pernah mengisi
  // http://localhost:8000 lalu menyimpannya, nilai itu akan terus
  // menang atas URL backend produksi dan chat selalu gagal.
  apiUrl: '',
  // Pilihan model dari UI. Nilainya NAMA MODEL ASLI, sama dengan
  // MODEL_DIIZINKAN di backend. Server yang memvalidasi.
  model: MODEL_DEFAULT,
  temperature: 0.4,
  maxTokens: 2048,
}

/** Alamat lokal yang TIDAK mungkin dijangkau pengunjung situs publik. */
const POLA_LOKAL = /^(https?:\/\/)?(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:\d+)?(\/|$)/i

/** Apakah aplikasi sedang dibuka dari domain publik (bukan komputer sendiri)? */
function sedangDiPublik() {
  if (typeof window === 'undefined' || !window.location) return false
  const h = window.location.hostname
  return !(h === 'localhost' || h === '127.0.0.1' || h === '[::1]' || h === '')
}

/** Menggabungkan nilai tersimpan dengan default (tahan data lama/rusak). */
function mergeSettings(raw) {
  if (!raw || typeof raw !== 'object') return { ...DEFAULT_SETTINGS }
  const merged = { ...DEFAULT_SETTINGS, ...raw }

  // Jaga tipe data agar tidak merusak komponen.
  merged.temperature = Number.isFinite(Number(merged.temperature))
    ? Math.min(2, Math.max(0, Number(merged.temperature)))
    : DEFAULT_SETTINGS.temperature
  merged.maxTokens = Number.isFinite(Number(merged.maxTokens))
    ? Math.min(8192, Math.max(16, Number(merged.maxTokens)))
    : DEFAULT_SETTINGS.maxTokens
  merged.saveHistory = Boolean(merged.saveHistory)
  merged.sendWithEnter = merged.sendWithEnter !== false
  merged.autoScroll = merged.autoScroll !== false
  merged.showTimestamps = Boolean(merged.showTimestamps)
  merged.confirmBeforeDelete = merged.confirmBeforeDelete !== false
  if (!['small', 'medium', 'large'].includes(merged.fontSize)) merged.fontSize = 'medium'
  if (!['light', 'dark', 'system'].includes(merged.theme)) merged.theme = 'system'
  if (!['concise', 'balanced', 'detailed'].includes(merged.responseStyle))
    merged.responseStyle = 'balanced'
  if (!['casual', 'formal'].includes(merged.tone)) merged.tone = 'casual'
  if (!['id', 'en'].includes(merged.bahasaJawaban)) merged.bahasaJawaban = 'id'
  if (!['pendek', 'sedang', 'panjang'].includes(merged.panjangJawaban))
    merged.panjangJawaban = 'sedang'

  // --- apiUrl ---
  // Selalu berupa string.
  if (typeof merged.apiUrl !== 'string') merged.apiUrl = ''
  merged.apiUrl = merged.apiUrl.trim()

  // PENYEMBUHAN OTOMATIS:
  // Bila situs dibuka dari domain publik tetapi tersimpan alamat lokal
  // (mis. http://localhost:8000 dari masa pengembangan), buang nilainya
  // agar kembali memakai URL backend dari build (VITE_API_URL).
  // Tanpa ini, pengguna akan terus melihat "Backend tidak terhubung".
  if (merged.apiUrl && POLA_LOKAL.test(merged.apiUrl) && sedangDiPublik()) {
    merged.apiUrl = ''
  }

  // --- model ---
  // Hanya nama model yang benar-benar tersedia yang diizinkan. Nilai
  // lain diganti default, termasuk:
  //   - "pintar"/"cepat" (ID publik dari versi sebelumnya), dan
  //   - "llama-3.3-70b-versatile" / "llama-3.1-8b-instant" yang sudah
  //     dimatikan Groq untuk akun gratis (kini Enterprise).
  if (!MODEL_ID.includes(merged.model)) {
    merged.model = MODEL_DEFAULT
  }

  // --- bersihkan sisa data sensitif versi lama ---
  // Versi sebelumnya menyimpan system prompt di localStorage. Kunci itu
  // tidak dipakai lagi dan TIDAK boleh ikut tersimpan, karena siapa pun
  // yang membuka peramban bisa membacanya. Dibuang permanen di sini.
  if ('systemPrompt' in merged) delete merged.systemPrompt

  return merged
}

/**
 * URL backend yang benar-benar dipakai.
 * Kosong -> pakai bawaan build (VITE_API_URL / localhost saat dev).
 */
export function resolveApiUrl(settings) {
  const manual = (settings?.apiUrl || '').trim()
  return manual || DEFAULT_API_URL
}

/**
 * Menyusun system prompt final dari pengaturan.
 *
 * PENTING — system prompt TIDAK lagi bisa diubah dari UI. Teks dasarnya
 * kini tinggal di lib/prompt.js (khusus pengembang) supaya pengunjung
 * tidak bisa melihat maupun mengubahnya.
 */
export function composeSystemPrompt(settings) {
  const parts = [SYSTEM_PROMPT_DASAR]

  const styleMap = {
    concise: 'Jawab sesingkat mungkin, langsung ke inti, maksimal beberapa kalimat.',
    balanced: 'Berikan jawaban seimbang: cukup detail namun tidak bertele-tele.',
    detailed: 'Berikan jawaban yang detail dan menyeluruh, sertakan contoh bila relevan.',
  }
  parts.push(styleMap[settings.responseStyle] || styleMap.balanced)

  // Panjang jawaban dari Pengaturan → Personalisasi. Dipisah dari
  // responseStyle agar pengguna bisa memilih "Nada santai + panjang".
  const panjangMap = {
    pendek: 'Usahakan jawaban pendek: inti saja, tanpa basa-basi.',
    sedang: 'Panjang jawaban secukupnya: cukup untuk menjawab dengan tuntas.',
    panjang: 'Beri penjelasan yang panjang dan menyeluruh bila memang membantu.',
  }
  if (panjangMap[settings.panjangJawaban]) parts.push(panjangMap[settings.panjangJawaban])

  const toneMap = {
    casual: 'Gunakan nada santai, hangat, dan akrab seperti teman yang membantu.',
    formal: 'Gunakan nada formal, sopan, dan profesional.',
  }
  parts.push(toneMap[settings.tone] || toneMap.casual)

  // Bahasa jawaban (terpisah dari bahasa antarmuka). Dipilih pengguna di
  // Pengaturan → Personalisasi: kadang orang ingin jawaban Inggris walau
  // menunya berbahasa Indonesia.
  parts.push(
    settings.bahasaJawaban === 'en'
      ? 'Selalu jawab dalam bahasa Inggris, kecuali pengguna meminta bahasa lain secara eksplisit.'
      : 'Selalu jawab dalam bahasa Indonesia yang baik dan mudah dipahami, kecuali pengguna meminta bahasa lain secara eksplisit.',
  )

  if (settings.customInstructions?.trim()) {
    parts.push(`Preferensi pengguna yang perlu diperhatikan:\n${settings.customInstructions.trim()}`)
  }

  return parts.join('\n\n')
}

export function useSettings() {
  const [settings, setSettings] = useState(() => {
    const stored = readJSON(KEYS.SETTINGS, null)
    const merged = mergeSettings(stored)
    // Tema disimpan terpisah (dibaca skrip anti-flash di index.html).
    merged.theme = getThemePref()
    return merged
  })

  /* Terapkan tema setiap kali berubah. */
  useEffect(() => {
    applyTheme(settings.theme)
  }, [settings.theme])

  /* Terapkan ukuran font ke <html>. */
  useEffect(() => {
    document.documentElement.setAttribute('data-fontsize', settings.fontSize)
  }, [settings.fontSize])

  /* Simpan ke localStorage (debounce ringan agar tidak menulis tiap ketikan). */
  useEffect(() => {
    const t = setTimeout(() => writeJSON(KEYS.SETTINGS, settings), 200)
    return () => clearTimeout(t)
  }, [settings])

  /** Ubah satu atau beberapa pengaturan sekaligus. */
  const updateSettings = useCallback((patch) => {
    setSettings((prev) => mergeSettings({ ...prev, ...patch }))
  }, [])

  /** Kembalikan ke pengaturan awal (tema tidak diubah). */
  const resetSettings = useCallback(() => {
    setSettings((prev) => ({ ...DEFAULT_SETTINGS, theme: prev.theme }))
  }, [])

  const systemPromptFinal = useMemo(() => composeSystemPrompt(settings), [settings])

  return { settings, updateSettings, resetSettings, systemPromptFinal }
}
