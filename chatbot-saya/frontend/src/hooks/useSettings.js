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
  apiUrl: DEFAULT_API_URL,
  model: 'deepseek-r1:7b',
  temperature: 0.4,
  maxTokens: 2048,
  systemPrompt:
    'Kamu adalah GungDev, asisten AI berbahasa Indonesia yang ramah, akurat, dan ' +
    'jelas. Jawab dalam bahasa yang digunakan pengguna. Jika tidak yakin dengan ' +
    'sebuah fakta, katakan terus terang, jangan mengarang. Gunakan format Markdown ' +
    'seperlunya. Jawab langsung ke inti tanpa basa-basi berlebihan.',
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
  if (typeof merged.apiUrl !== 'string' || !merged.apiUrl.trim())
    merged.apiUrl = DEFAULT_API_URL
  return merged
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
