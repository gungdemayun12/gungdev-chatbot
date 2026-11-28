/**
 * LanguageProvider.jsx — mengganti seluruh antarmuka sekaligus.
 *
 * Teks tidak langsung diganti begitu satu hasil datang. Semua teks yang
 * terlihat dikumpulkan, diterjemahkan, lalu dipasang dalam satu langkah.
 * Itulah yang membuat perpindahan terasa seperti tombol bahasa Google,
 * bukan perubahan satu per satu.
 */
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { translateMany } from '../lib/translate.js'

const LanguageContext = createContext({ language: 'id', translating: false })

export function useLanguage() {
  return useContext(LanguageContext)
}

const ASLI = new WeakMap()

function teksLayak(nilai) {
  const teks = String(nilai || '').trim()
  return teks.length > 1 && /[A-Za-zÀ-ÿ]/.test(teks)
}

function sumberNode(node) {
  if (!ASLI.has(node)) ASLI.set(node, node.textContent)
  return ASLI.get(node)
}

function kumpulkan(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const daftar = []
  while (walker.nextNode()) {
    const node = walker.currentNode
    const sumber = sumberNode(node)
    if (teksLayak(sumber)) daftar.push({ node, sumber, inti: sumber.trim() })
  }
  return daftar
}

function pasang(daftar, terjemahan) {
  for (const item of daftar) {
    if (!item.node.isConnected) continue
    const hasil = terjemahan.get(item.inti) || item.inti
    item.node.textContent = item.sumber.replace(item.inti, hasil)
  }
}

function kembalikan(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
  const daftar = []
  while (walker.nextNode()) daftar.push(walker.currentNode)
  daftar.forEach((node) => {
    if (ASLI.has(node)) node.textContent = ASLI.get(node)
  })
}

export default function LanguageProvider({ language = 'id', children }) {
  const [translating, setTranslating] = useState(false)
  const nilai = useMemo(() => ({ language, translating }), [language, translating])

  useEffect(() => {
    document.documentElement.lang = language === 'en' ? 'en' : 'id'
  }, [language])

  useEffect(() => {
    const root = document.getElementById('root')
    if (!root) return undefined
    if (language !== 'en') {
      kembalikan(root)
      return undefined
    }

    let dibatalkan = false
    let timer = 0
    let generasi = 0

    const terapkan = async () => {
      const giliran = ++generasi
      const daftar = kumpulkan(root)
      if (!daftar.length) return
      setTranslating(true)
      const terjemahan = await translateMany(daftar.map((item) => item.inti), 'id', 'en')
      if (dibatalkan || giliran !== generasi) return
      pasang(daftar, terjemahan)
      setTranslating(false)
    }

    const jadwalkan = () => {
      clearTimeout(timer)
      timer = setTimeout(() => {
        terapkan().catch(() => setTranslating(false))
      }, 80)
    }

    jadwalkan()
    const pengamat = new MutationObserver((mutasi) => {
      const adaTeksBaru = mutasi.some(
        (item) =>
          item.type === 'childList' &&
          [...item.addedNodes].some((node) => node.nodeType !== Node.COMMENT_NODE),
      )
      if (adaTeksBaru) jadwalkan()
    })
    pengamat.observe(root, { subtree: true, childList: true })

    return () => {
      dibatalkan = true
      generasi += 1
      clearTimeout(timer)
      pengamat.disconnect()
      setTranslating(false)
    }
  }, [language])

  return <LanguageContext.Provider value={nilai}>{children}</LanguageContext.Provider>
}
