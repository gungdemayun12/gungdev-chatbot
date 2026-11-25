/**
 * useSettings.js — semua preferensi pengguna, tersimpan di localStorage.
 *
 * Setiap perubahan langsung diterapkan ke UI (ukuran font lewat atribut
 * data-fontsize di <html>, tema lewat data-theme).
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import { KEYS, readJSON, writeJSON } from '../lib/storage.js'
import { DEFAULT_API_URL } from '../lib/api.js'
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
  model: 'openai/gpt-oss-120b',
  temperature: 0.4,
  maxTokens: 2048,
  systemPrompt:
    'Kamu adalah GungDev, asisten AI berbahasa Indonesia yang ramah, akurat, dan ' +
    'jelas. Jawab dalam bahasa yang digunakan pengguna. Jika tidak yakin dengan ' +
    'sebuah fakta, katakan terus terang, jangan mengarang. Gunakan format Markdown ' +
    'seperlunya. Jawab langsung ke inti tanpa basa-basi berlebihan.',
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
  if (!['small', 'medium', 'large'].includes(merged.fontSize)) merged.fontSize = 'medium'
  if (!['light', 'dark', 'system'].includes(merged.theme)) merged.theme = 'system'
  if (!['concise', 'balanced', 'detailed'].includes(merged.responseStyle))
    merged.responseStyle = 'balanced'
  if (!['casual', 'formal'].includes(merged.tone)) merged.tone = 'casual'

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

  // Model lama DeepSeek/Llama yang kini hanya jalan di Ollama lokal.
  // Di situs publik model ditentukan server (GROQ_MODEL), jadi nilai
  // ini hanya catatan — tetapi dibuat masuk akal agar tidak membingungkan.
  const modelLokal = ['deepseek-r1:7b', 'deepseek-r1:1.5b', 'llama3.2', 'qwen2.5:7b']
  if (modelLokal.includes(merged.model) && sedangDiPublik()) {
    merged.model = DEFAULT_SETTINGS.model
  }

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
 * Menyusun system prompt final dari pengaturan:
 * base prompt + gaya jawaban + nada + instruksi kustom pengguna.
 */
export function composeSystemPrompt(settings) {
  const parts = [settings.systemPrompt?.trim()].filter(Boolean)

  const styleMap = {
    concise: 'Jawab sesingkat mungkin, langsung ke inti, maksimal beberapa kalimat.',
    balanced: 'Berikan jawaban seimbang: cukup detail namun tidak bertele-tele.',
    detailed: 'Berikan jawaban yang detail dan menyeluruh, sertakan contoh bila relevan.',
  }
  parts.push(styleMap[settings.responseStyle] || styleMap.balanced)

  const toneMap = {
    casual: 'Gunakan nada santai, hangat, dan akrab seperti teman yang membantu.',
    formal: 'Gunakan nada formal, sopan, dan profesional.',
  }
  parts.push(toneMap[settings.tone] || toneMap.casual)

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
