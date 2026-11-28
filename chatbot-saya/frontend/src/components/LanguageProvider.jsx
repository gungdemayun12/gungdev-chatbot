/**
 * LanguageProvider.jsx — menerapkan pilihan bahasa ke seluruh antarmuka.
 *
 * Teks sumber di komponen tetap bahasa Indonesia. Saat pengguna memilih
 * English, provider ini menerjemahkan node teks yang terlihat melalui
 * MyMemory. Hasilnya disimpan, jadi perpindahan bahasa berikutnya cepat.
 */
import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { translateText } from '../lib/translate.js'

const LanguageContext = createContext({
  language: 'id',
  translating: false,
})

export function useLanguage() {
  return useContext(LanguageContext)
}

function nodeTeks(node) {
  return node.nodeType === Node.TEXT_NODE && node.textContent.trim().length > 1
}

export default function LanguageProvider({ language = 'id', children }) {
  const [translating, setTranslating] = useState(false)
  const nilai = useMemo(() => ({ language, translating }), [language, translating])

  useEffect(() => {
    document.documentElement.lang = language === 'en' ? 'en' : 'id'
  }, [language])

  useEffect(() => {
    if (language !== 'en') return undefined
    const root = document.getElementById('root')
    if (!root) return undefined

    let dibatalkan = false
    const asli = new WeakMap()
    const sedang = new WeakSet()

    const terjemahkan = (node) => {
      if (!nodeTeks(node) || sedang.has(node)) return
      const sumber = node.textContent
      if (!asli.has(node)) asli.set(node, sumber)
      const teks = asli.get(node).trim()
      if (!/[A-Za-zÀ-ÿ]/.test(teks)) return

      sedang.add(node)
      setTranslating(true)
      translateText(teks, 'id', 'en')
        .then((hasil) => {
          if (dibatalkan || !node.isConnected || !hasil) return
          const awal = asli.get(node)
          node.textContent = awal.replace(teks, hasil)
        })
        .catch(() => {
          /* Kuota atau jaringan gagal: biarkan teks asli. */
        })
        .finally(() => {
          sedang.delete(node)
          if (!dibatalkan) setTranslating(false)
        })
    }

    const pindai = (awal) => {
      const walker = document.createTreeWalker(awal, NodeFilter.SHOW_TEXT)
      const daftar = []
      while (walker.nextNode()) daftar.push(walker.currentNode)
      daftar.forEach(terjemahkan)
    }

    pindai(root)
    const pengamat = new MutationObserver((mutasi) => {
      for (const item of mutasi) {
        if (item.type === 'characterData') terjemahkan(item.target)
        item.addedNodes.forEach((node) => {
          if (node.nodeType === Node.TEXT_NODE) terjemahkan(node)
          else if (node.nodeType === Node.ELEMENT_NODE) pindai(node)
        })
      }
    })
    pengamat.observe(root, { subtree: true, childList: true, characterData: true })

    return () => {
      dibatalkan = true
      pengamat.disconnect()
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT)
      const daftar = []
      while (walker.nextNode()) daftar.push(walker.currentNode)
      daftar.forEach((node) => {
        if (asli.has(node)) node.textContent = asli.get(node)
      })
      setTranslating(false)
    }
  }, [language])

  return <LanguageContext.Provider value={nilai}>{children}</LanguageContext.Provider>
}
