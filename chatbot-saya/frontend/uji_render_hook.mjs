/**
 * uji_render_hook.mjs — menjalankan hook React ASLI di Node tanpa DOM.
 *
 * Kenapa tidak memakai react-dom / jsdom?
 *   - react-dom/client membutuhkan DOM sungguhan (document.createElement
 *     dengan setAttribute, dsb.). Menirunya menjadi rapuh.
 *   - jsdom bukan dependensi proyek ini dan kita tidak ingin menambah
 *     dependensi hanya untuk uji.
 *
 * Pendekatan: React hooks adalah fungsi murni terhadap "slot" yang
 * disimpan React. Di sini slot itu kita tiru dengan benar untuk hook yang
 * dipakai proyek (useState, useEffect, useRef, useMemo, useCallback).
 * Urutan hook stabil karena tidak ada percabangan di hook useSessions.
 *
 * Modul 'react' diganti (lihat uji_hook_sesi.mjs) dengan implementasi ini
 * lewat pemetaan impor di sumber yang ditulis ulang.
 */

export function buatReactTiruan() {
  const hookReact = {
    useState(awal) {
      const s = slotSekarang()
      if (s.belumAda) {
        s.belumAda = false
        s.nilai = typeof awal === 'function' ? awal() : awal
      }
      const set = (baru) => {
        const nilaiBaru = typeof baru === 'function' ? baru(s.nilai) : baru
        if (Object.is(nilaiBaru, s.nilai)) return
        s.nilai = nilaiBaru
        // Seperti React: setState dari mana pun (termasuk await di
        // dalam effect) menjadwalkan render ulang.
        if (typeof globalThis.__JADWALKAN_RENDER__ === 'function') {
          globalThis.__JADWALKAN_RENDER__()
        }
      }
      return [s.nilai, set]
    },

    useRef(awal) {
      const s = slotSekarang()
      if (s.belumAda) {
        s.belumAda = false
        s.ref = { current: awal }
      }
      return s.ref
    },

    useMemo(fn, deps) {
      const s = slotSekarang()
      if (s.belumAda || !depSama(s.deps, deps)) {
        s.belumAda = false
        s.deps = deps
        s.nilai = fn()
      }
      return s.nilai
    },

    useCallback(fn, deps) {
      const s = slotSekarang()
      if (s.belumAda || !depSama(s.deps, deps)) {
        s.belumAda = false
        s.deps = deps
        s.nilai = fn
      }
      return s.nilai
    },

    useEffect(fn, deps) {
      const s = slotSekarang()
      if (s.belumAda || !depSama(s.deps, deps)) {
        s.belumAda = false
        s.deps = deps
        s.perluJalan = true
        s.fn = fn
      }
    },

    useLayoutEffect(fn, deps) {
      hookReact.useEffect(fn, deps)
    },

    useImperativeHandle() {},

    useReducer(reducer, awal) {
      const s = slotSekarang()
      if (s.belumAda) {
        s.belumAda = false
        s.nilai = typeof awal === 'function' ? awal(undefined) : awal
      }
      const dispatch = (aksi) => {
        const baru = reducer(s.nilai, aksi)
        if (!Object.is(baru, s.nilai)) {
          s.nilai = baru
          s.berubah = true
        }
      }
      return [s.nilai, dispatch]
    },
  }

  let slotList = []
  let indeks = 0

  function slotSekarang() {
    if (indeks >= slotList.length) slotList.push({ belumAda: true })
    const s = slotList[indeks]
    indeks += 1
    return s
  }

  function depSama(a, b) {
    if (!a || !b) return false
    if (a.length !== b.length) return false
    return a.every((v, i) => Object.is(v, b[i]))
  }

  /**
   * Merender hook seperti React: setiap setState (termasuk dari
   * callback async) mengubah state di slot dan menjadwalkan render
   * ulang. Tanpa penjadwalan ini, perubahan status dari `await` di
   * dalam effect tidak akan pernah terlihat — hasil uji jadi
   * menyesatkan (bukan bug kode, tapi bug harness).
   */
  function render(pakaiHook) {
    const objek = { current: undefined }
    let adaJadwal = false
    let berhenti = false

    function jadwalkan() {
      if (adaJadwal || berhenti) return
      adaJadwal = true
      queueMicrotask(() => {
        if (berhenti) return
        adaJadwal = false
        renderSekali()
      })
    }

    function renderSekali() {
      indeks = 0
      for (const s of slotList) s.berubah = false
      objek.current = pakaiHook()

      const efek = slotList.filter((s) => s.perluJalan)
      for (const s of efek) {
        s.perluJalan = false
        try {
          const bersih = s.fn()
          if (typeof bersih === 'function') bersihFn.push(bersih)
        } catch (err) {
          console.log('   [harness] effect error:', err && err.message)
        }
      }
    }

    /* Setiap setState memicu penjadwalan render. */
    const semulaJadwalkan = globalThis.__JADWALKAN_RENDER__
    globalThis.__JADWALKAN_RENDER__ = jadwalkan

    /** Selesai saat tidak ada lagi render terjadwal (mirip act/waitFor). */
    function tenang({ maksMs = 15000 } = {}) {
      return new Promise((resolve) => {
        const mulai = Date.now()
        const cek = () => {
          if (!adaJadwal) return resolve(true)
          if (Date.now() - mulai > maksMs) return resolve(false)
          setTimeout(cek, 15)
        }
        setTimeout(cek, 15)
      })
    }

    return {
      hasil: objek,
      /** Render awal + tunggu sampai tenang. */
      async jalankan() {
        renderSekali()
        await tenang()
        return objek
      },
      /** Render ulang manual (dipakai setelah aksi pengguna). */
      perbarui() {
        renderSekali()
      },
      unmount() {
        berhenti = true
        for (const f of bersihFn) {
          try {
            f()
          } catch {
            /* abaikan */
          }
        }
        bersihFn = []
        if (semulaJadwalkan === undefined) delete globalThis.__JADWALKAN_RENDER__
        else globalThis.__JADWALKAN_RENDER__ = semulaJadwalkan
      },
      tenang,
    }
  }

  let bersihFn = []

  return {
    React: {
      ...hookReact,
      createElement: () => null,
      Fragment: 'Fragment',
      useState: hookReact.useState,
      useEffect: hookReact.useEffect,
      useRef: hookReact.useRef,
      useMemo: hookReact.useMemo,
      useCallback: hookReact.useCallback,
    },
    render,
    reset() {
      slotList = []
      bersihFn = []
      indeks = 0
    },
  }
}

/** Menunggu sampai `syarat()` benar. */
export async function waitFor(syarat, { timeout = 5000, jeda = 20 } = {}) {
  const mulai = Date.now()
  while (Date.now() - mulai < timeout) {
    let ok = false
    try {
      ok = Boolean(syarat())
    } catch {
      ok = false
    }
    if (ok) return true
    await new Promise((r) => setTimeout(r, jeda))
  }
  return false
}
