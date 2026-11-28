/**
 * useSessions.js — state SEMUA percakapan + penyimpanan di SERVER.
 *
 * Model data:
 *   session = {
 *     id, title, messages: [{id, role, content, createdAt}],
 *     createdAt, updatedAt, pinned
 *   }
 *
 * "Satu sesi = satu item riwayat": seluruh bolak-balik pesan disimpan di
 * dalam satu objek session, jadi sidebar menampilkan satu baris per sesi.
 *
 * STRATEGI PENYIMPANAN (penting)
 * ------------------------------
 * Server adalah sumber kebenaran, tetapi TIDAK boleh membuat chat gagal.
 * Karena itu penyimpanan berlapis:
 *
 *   1. SERVER (Upstash) — sumber kebenaran. Satu akun Google = riwayat
 *      sama di semua perangkat. Diperbarui dengan sedikit jeda (debounce)
 *      agar tidak mengirim satu permintaan untuk setiap huruf jawaban.
 *
 *   2. PERANGKAT (localStorage) — cadangan + kecepatan. Dibaca lebih dulu
 *      saat halaman dibuka supaya sidebar langsung terisi (tanpa
 *      berkedip), lalu ditimpa data server bila server lebih baru.
 *      Bila server sedang tidak bisa dipakai (kuota habis / offline),
 *      salinan ini yang menyelamatkan riwayat pengguna.
 *
 * Tamu: tidak disimpan di mana pun (sesuai keputusan pemilik situs).
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  KEYS,
  keyActiveSession,
  keySessions,
  readJSON,
  removeKey,
  removeKeysWithPrefix,
  writeJSON,
  writeString,
} from '../lib/storage.js'
import { makeTitle } from '../lib/text.js'
import { pulihkanTokenRiwayat } from '../lib/auth.js'
import {
  ambilRiwayatServer,
  buatJudulServer,
  getTokenRiwayat,
  hapusRiwayatServer,
  simpanAktifServer,
  simpanSesiServer,
  sinkronSesiServer,
} from '../lib/riwayat.js'

/** ID unik sederhana (aman untuk localStorage & Redis). */
function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`
}

/** Membuat sesi baru yang kosong. */
export function createSession() {
  const now = Date.now()
  return {
    id: uid('s'),
    title: 'Percakapan baru',
    titleLocked: false, // true jika user sudah mengganti nama manual
    messages: [],
    createdAt: now,
    updatedAt: now,
    pinned: false,
  }
}

/** Validasi bentuk data dari server / localStorage. */
function sanitizeSessions(value) {
  if (!Array.isArray(value)) return []
  return value
    .filter((s) => s && typeof s.id === 'string' && Array.isArray(s.messages))
    .map((s) => ({
      id: s.id,
      title: typeof s.title === 'string' && s.title ? s.title : 'Percakapan baru',
      titleLocked: Boolean(s.titleLocked),
      messages: s.messages
        .filter((m) => m && (m.role === 'user' || m.role === 'assistant'))
        .map((m) => ({
          id: m.id || uid('m'),
          role: m.role,
          content: typeof m.content === 'string' ? m.content : '',
          createdAt: m.createdAt || Date.now(),
          feedback: m.feedback || null,
          // Sumber riset ikut disimpan agar kartu sumber tetap terlihat
          // setelah halaman dimuat ulang / dibuka di perangkat lain.
          ...(Array.isArray(m.sumber) && m.sumber.length
            ? {
                sumber: m.sumber
                  .filter((s) => s && typeof s.url === 'string')
                  .map((s) => ({
                    nomor: Number(s.nomor) || 0,
                    judul: String(s.judul || '').slice(0, 200),
                    url: String(s.url),
                    situs: String(s.situs || '').slice(0, 120),
                    tanggal: String(s.tanggal || '').slice(0, 60),
                  })),
              }
            : {}),
          // Gambar hasil pembuatan AI disimpan agar tetap tampil setelah
          // halaman dimuat ulang. Hanya data URL gambar yang diterima;
          // selain itu dibuang supaya riwayat tidak menyimpan sampah.
          ...(m.gambar && typeof m.gambar?.data_url === 'string' &&
          m.gambar.data_url.startsWith('data:image/')
            ? {
                gambar: {
                  data_url: m.gambar.data_url,
                  deskripsi: String(m.gambar.deskripsi || '').slice(0, 600),
                  sunting: Boolean(m.gambar.sunting),
                  // Penanda mesin pembuat gambar. WAJIB ikut disimpan:
                  // tanpa ini, gambar BARU kehilangan penandanya saat
                  // riwayat ditulis ulang, lalu UI menganggapnya gambar
                  // lama dan menampilkan peringatan palsu.
                  ...(m.gambar.mesin === 'utama' || m.gambar.mesin === 'cadangan'
                    ? { mesin: m.gambar.mesin }
                    : {}),
                },
              }
            : {}),
        })),
      createdAt: s.createdAt || Date.now(),
      updatedAt: s.updatedAt || s.createdAt || Date.now(),
      pinned: Boolean(s.pinned),
    }))
}

/** Jeda sebelum menyimpan ke server (menggabungkan perubahan beruntun). */
const JEDA_SIMPAN_MS = 900

export function useSessions(settings, akunSub = null, apiUrl = '') {
  /* ---------------------------------------------------------------
     `akunSub` = ID unik akun Google yang sedang login (null = tamu).

       tamu  -> tidak ada riwayat tersimpan (selalu mulai kosong)
       login -> server + salinan perangkat
     --------------------------------------------------------------- */

  /** Membaca salinan perangkat milik akun (bisa kosong). */
  function muatLokal(sub) {
    if (!sub) return { sessions: [], activeId: null }
    const sessions = sanitizeSessions(readJSON(keySessions(sub), []))
    let activeId = null
    try {
      activeId = localStorage.getItem(keyActiveSession(sub))
    } catch {
      activeId = null
    }
    if (!activeId || !sessions.some((s) => s.id === activeId)) activeId = null
    return { sessions, activeId }
  }

  const awal = useMemo(() => muatLokal(akunSub), [akunSub])

  const [sessions, setSessions] = useState(awal.sessions)
  const [activeId, setActiveId] = useState(awal.activeId)
  const [loaded, setLoaded] = useState(false)

  /* Keadaan penyimpanan — dipakai UI untuk jujur memberi tahu pengguna. */
  // 'lokal'    = tamu (tidak disimpan)
  // 'memuat'   = sedang membaca dari server
  // 'server'   = tersimpan di server (sama di semua perangkat)
  // 'perangkat'= server tidak bisa dipakai, riwayat hanya di perangkat ini
  // 'sesi'     = sudah login, token sedang disegarkan diam-diam.
  //              Pengguna TETAP login; tidak perlu diapa-apakan dan
  //              tidak ditampilkan sebagai peringatan.
  const [statusSimpan, setStatusSimpan] = useState(akunSub ? 'memuat' : 'lokal')

  /* Menandai bahwa isi state sudah berasal dari server (atau sudah
     dicoba). Tanpa ini, efek penyimpanan bisa menulis data lama
     perangkat ke server sebelum data server selesai dibaca. */
  const siapSimpanRef = useRef(false)

  /* Sesi yang isinya berubah dan perlu dikirim ke server. */
  const kotorRef = useRef(new Set())
  const timerRef = useRef(null)

  /* Sesi yang dihapus di perangkat; dikirim ke server berurutan. */
  const hapusAntreRef = useRef([])

  /* Menyimpan `apiUrl` di ref agar callback stabil. */
  const apiRef = useRef(apiUrl)
  useEffect(() => {
    apiRef.current = apiUrl
  }, [apiUrl])

  /* Berganti akun (login / keluar): ganti isi riwayat seketika.
     Ini juga yang membuat riwayat tamu tidak "terbawa" ke akun dan
     riwayat akun tidak tertinggal untuk tamu berikutnya. */
  const [subTerpasang, setSubTerpasang] = useState(akunSub)
  if (subTerpasang !== akunSub) {
    setSubTerpasang(akunSub)
    const baru = muatLokal(akunSub)
    setSessions(baru.sessions)
    setActiveId(baru.activeId)
    setStatusSimpan(akunSub ? 'memuat' : 'lokal')
  }

  /* Reset penanda & antrean setiap kali akun berganti. Dilakukan di
     effect (bukan saat render) karena mengubah ref di tengah render
     dilarang React dan bisa menghasilkan nilai yang tidak konsisten. */
  useEffect(() => {
    siapSimpanRef.current = false
    kotorRef.current.clear()
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [akunSub])

  /* Simulasikan pembacaan riwayat (untuk skeleton di sidebar). */
  useEffect(() => {
    const t = setTimeout(() => setLoaded(true), 220)
    return () => clearTimeout(t)
  }, [])

  /* Bersihkan sisa riwayat versi lama (sebelum ada login).

     Versi sebelumnya menyimpan riwayat tamu di gungdev:sessions tanpa
     nama akun. Sekarang riwayat tamu TIDAK boleh tersimpan, jadi kunci
     lama itu dibuang sekali saat aplikasi dimuat. */
  useEffect(() => {
    removeKey(KEYS.SESSIONS)
    removeKey(KEYS.ACTIVE_SESSION)
  }, [])

  /* ---------------------------------------------------------------
     1. MENYIMPAN SATU SESI KE SERVER (dengan jeda)
     --------------------------------------------------------------- */

  /* Salinan `sessions` terbaru untuk dipakai di dalam callback async
     tanpa membuat callback ikut berubah setiap kali state berubah. */
  const sessionsRef = useRef(sessions)
  useEffect(() => {
    sessionsRef.current = sessions
  }, [sessions])

  /* Salinan `activeId` terbaru, dipakai di dalam updater setSessions
     (mis. saat sesi baru langsung diisi pesan pertama). */
  const activeIdRef = useRef(activeId)
  useEffect(() => {
    activeIdRef.current = activeId
  }, [activeId])

  /** Mengirim semua sesi yang berubah ke server, satu per satu. */
  const kirimPerubahan = useCallback(async () => {
    const sub = subTerpasang
    if (!sub || !siapSimpanRef.current) return
    if (!settings.saveHistory) return
    if (!getTokenRiwayat()) {
      const pulih = await pulihkanTokenRiwayat()
      if (!pulih || !getTokenRiwayat()) {
        setStatusSimpan('perangkat')
        return
      }
    }

    const kotor = Array.from(kotorRef.current)
    kotorRef.current.clear()
    if (kotor.length === 0) return

    let semuaTersimpan = true
    for (const sid of kotor) {
      const sesi = sessionsRef.current.find((s) => s.id === sid)
      if (!sesi) continue // sudah dihapus; tidak perlu disimpan

      const hasil = await simpanSesiServer(apiRef.current, sesi)
      if (hasil.perluLogin) {
        // ID token Google memang kedaluwarsa berkala. Selama sesi aplikasi
        // masih login, pulihkan token secara diam-diam lalu ulangi sekali;
        // jangan langsung menakut-nakuti pengguna dengan "Masuk ulang".
        const pulih = await pulihkanTokenRiwayat()
        if (pulih) {
          const ulang = await simpanSesiServer(apiRef.current, sesi)
          if (ulang.tersimpan) continue
          if (ulang.perluLogin) {
            // Sudah login, hanya token belum diperbarui. Bukan alasan
            // menampilkan "riwayat hanya di perangkat".
            setStatusSimpan('sesi')
            return
          }
        }
        setStatusSimpan('sesi')
        return
      }
      if (!hasil.tersimpan) semuaTersimpan = false
    }

    setStatusSimpan(semuaTersimpan ? 'server' : 'perangkat')
  }, [subTerpasang, settings.saveHistory])

  /** Menjadwalkan pengiriman setelah perubahan berhenti sesaat. */
  const jadwalkanSimpan = useCallback(
    (id) => {
      if (id) kotorRef.current.add(id)
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        timerRef.current = null
        kirimPerubahan()
      }, JEDA_SIMPAN_MS)
    },
    [kirimPerubahan],
  )

  /* Kirim sisa perubahan saat halaman ditinggalkan (pengguna menutup
     tab). `beforeunload` tidak bisa menunggu async, jadi yang dikirim
     adalah permintaan "fire and forget"; salinan perangkat tetap ada
     sebagai jaring pengaman.

     PENTING: saklar "Simpan riwayat" WAJIB dihormati di sini juga.
     Sempat terjadi bug: bila pengguna mematikan saklar lalu menutup tab,
     sisa perubahan tetap terkirim ke server. Itu melanggar pilihan
     pengguna, jadi pemeriksaannya disimpan di ref (effect ini sengaja
     tidak dipasang ulang setiap setelan berubah — kalau dipasang ulang,
     justru ada celah saat handler sedang dilepas). */
  const simpanRef = useRef(settings.saveHistory)
  useEffect(() => {
    simpanRef.current = settings.saveHistory
  }, [settings.saveHistory])

  useEffect(() => {
    const onKeluar = () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (!simpanRef.current) return // pengguna mematikan penyimpanan
      if (kotorRef.current.size === 0) return
      if (!getTokenRiwayat()) return
      const semua = Array.from(kotorRef.current)
        .map((id) => sessionsRef.current.find((s) => s.id === id))
        .filter(Boolean)
      if (semua.length === 0) return
      sinkronSesiServer(apiRef.current, semua)
    }
    window.addEventListener('pagehide', onKeluar)
    return () => window.removeEventListener('pagehide', onKeluar)
  }, [])

  /* ---------------------------------------------------------------
     2. MEMBACA DARI SERVER saat halaman dibuka / akun berganti
     --------------------------------------------------------------- */
  useEffect(() => {
    if (!akunSub) {
      siapSimpanRef.current = false
      // Status awal untuk tamu sudah diatur saat render (lihat
      // setStatusSimpan di blok pergantian akun), jadi tidak perlu
      // setState di sini.
      return undefined
    }

    let batal = false
    const kendali = new AbortController()

    const muat = async () => {
      // Salinan perangkat dipakai lebih dulu supaya sidebar tidak kosong.
      const lokal = muatLokal(akunSub)
      if (!batal && lokal.sessions.length > 0) {
        setSessions(lokal.sessions)
        setActiveId(lokal.activeId)
      }

      /* Token sudah tersimpan di perangkat (lihat RiwayatSesi), jadi
         biasanya tidak perlu meminta apa pun ke Google. Bila token
         kedaluwarsa, `pulihkanTokenRiwayat` memperbaruinya diam-diam.

         PENTING: pengguna TETAP login selama pembaruan berjalan. Jangan
         menurunkan status ke 'perangkat' hanya karena token belum ada —
         itu yang membuat pengguna melihat "riwayat sementara" padahal
         profilnya masih tampil dan ia tidak pernah keluar. */
      if (!getTokenRiwayat()) {
        setStatusSimpan('memuat')
        await pulihkanTokenRiwayat()
        if (batal) return
      }

      const hasil = await ambilRiwayatServer(apiRef.current, { signal: kendali.signal })
      if (batal) return

      if (hasil.perluLogin) {
        // Token Google dapat kedaluwarsa walau pengguna belum logout.
        // Coba pulihkan diam-diam; sesi login lokal tetap dipertahankan.
        const pulih = await pulihkanTokenRiwayat()
        if (pulih && !batal) {
          const ulang = await ambilRiwayatServer(apiRef.current, { signal: kendali.signal })
          if (!batal && ulang.ok && !ulang.perluLogin) {
            setStatusSimpan(ulang.tersedia ? 'server' : 'perangkat')
            siapSimpanRef.current = ulang.tersedia
            if (ulang.sessions.length > 0) {
              const dariServer = sanitizeSessions(ulang.sessions)
              setSessions(dariServer)
              setActiveId(ulang.activeId)
            }
            return
          }
        }
        /* Google belum memberi token segar (bisa karena browser memblokir
           One Tap, atau pengguna perlu menyetujui sekali).

           PENTING: ini BUKAN alasan menampilkan "riwayat sementara hanya
           di perangkat". Pengguna tetap login (profilnya tampil) dan
           pesannya tetap dihitung sebagai akun. Status 'sesi' berarti
           "login, riwayat menyusul" — tenang, bukan peringatan. */
        siapSimpanRef.current = false
        setStatusSimpan('sesi')
        return
      }

      if (!hasil.ok) {
        // Server tidak bisa dihubungi: salinan perangkat yang berlaku.
        siapSimpanRef.current = false
        setStatusSimpan('perangkat')
        return
      }

      if (!hasil.tersedia) {
        // Server menjawab tetapi penyimpanannya belum aktif (env belum
        // diisi / kuota habis). Riwayat tetap aman di perangkat.
        siapSimpanRef.current = false
        setStatusSimpan('perangkat')
        return
      }

      // Server punya data. Bila kosong tetapi perangkat punya riwayat
      // (pengguna login pertama kali di perangkat ini), migrasikan
      // sekali agar riwayat lama tidak hilang.
      //
      // Migrasi hanya boleh terjadi bila pengguna MENYETUJUI penyimpanan
      // riwayat. Bila saklarnya mati, salinan perangkat memang harus
      // tetap tinggal di perangkat.
      if (
        hasil.sessions.length === 0 &&
        lokal.sessions.length > 0 &&
        simpanRef.current
      ) {
        await sinkronSesiServer(apiRef.current, lokal.sessions)
        if (batal) return

        const ulang = await ambilRiwayatServer(apiRef.current, { signal: kendali.signal })
        if (batal) return
        if (ulang.ok && ulang.sessions.length > 0) {
          setSessions(sanitizeSessions(ulang.sessions))
          setActiveId(ulang.activeId)
          siapSimpanRef.current = true
          setStatusSimpan('server')
          return
        }
      }

      if (hasil.sessions.length > 0) {
        const dariServer = sanitizeSessions(hasil.sessions)
        setSessions(dariServer)
        // Pertahankan pilihan sesi aktif pengguna bila masih ada;
        // kalau tidak, pakai yang dicatat server.
        setActiveId((sekarang) => {
          const masihAda = dariServer.some((s) => s.id === sekarang)
          if (masihAda) return sekarang
          return hasil.activeId && dariServer.some((s) => s.id === hasil.activeId)
            ? hasil.activeId
            : null
        })
      }

      siapSimpanRef.current = true
      setStatusSimpan('server')
    }

    muat()

    /* Bila pembaruan token belum berhasil (browser memblokir One Tap,
       sinyal sempat putus, dsb.), coba lagi diam-diam. Pengguna tidak
       perlu menekan apa pun dan tidak melihat ajakan masuk — ia memang
       sudah login. */
    const coba = setInterval(async () => {
      if (batal) return
      if (getTokenRiwayat()) {
        clearInterval(coba)
        return
      }
      const pulih = await pulihkanTokenRiwayat()
      if (batal || !pulih) return
      clearInterval(coba)
      const ulang = await ambilRiwayatServer(apiRef.current)
      if (batal || !ulang.ok) return
      if (ulang.sessions.length > 0) {
        const dariServer = sanitizeSessions(ulang.sessions)
        setSessions(dariServer)
        setActiveId((sekarang) =>
          dariServer.some((s) => s.id === sekarang) ? sekarang : ulang.activeId,
        )
      }
      siapSimpanRef.current = ulang.tersedia
      setStatusSimpan(ulang.tersedia ? 'server' : 'sesi')
    }, 45000)

    return () => {
      batal = true
      clearInterval(coba)
      kendali.abort()
    }
  }, [akunSub])

  /* ---------------------------------------------------------------
     3. SALINAN PERANGKAT (cadangan, selalu ditulis bila login)
     --------------------------------------------------------------- */
  const bolehSimpan = Boolean(akunSub) && Boolean(settings.saveHistory)
  useEffect(() => {
    if (!bolehSimpan) return
    writeJSON(keySessions(akunSub), sessions)
  }, [sessions, bolehSimpan, akunSub])

  /* Simpan sesi aktif agar refresh mengembalikan posisi terakhir. */
  useEffect(() => {
    if (!bolehSimpan) return
    if (activeId) writeString(keyActiveSession(akunSub), activeId)
  }, [activeId, bolehSimpan, akunSub])

  /* Kirim sesi aktif ke server (tanpa jeda lama — jarang berubah). */
  useEffect(() => {
    if (!akunSub || !siapSimpanRef.current || !settings.saveHistory) return
    if (!getTokenRiwayat()) return
    simpanAktifServer(apiRef.current, activeId)
  }, [activeId, akunSub, settings.saveHistory])

  /* ---------------------------------------------------------------
     4. OPERASI PADA SESI
     --------------------------------------------------------------- */
  const activeSession = useMemo(
    () => sessions.find((s) => s.id === activeId) || null,
    [sessions, activeId],
  )

  /** Memperbarui satu sesi lewat fungsi updater. */
  const updateSession = useCallback(
    (id, updater) => {
      setSessions((prev) => {
        // Sesi bisa belum ada di state saat dibuat & langsung diisi dalam
        // satu putaran (kirim pesan pertama). Dulu perubahan seperti itu
        // hilang diam-diam sehingga pesan pengguna tidak tampil sampai
        // jawaban datang. Bila id belum ada, pakai sesi aktif sebagai
        // dasar agar isinya tidak hilang.
        const ada = prev.some((s) => s.id === id)
        if (!ada) {
          const dasar = prev.find((s) => s.id === activeIdRef.current)
          if (!dasar) return prev
          const next =
            typeof updater === 'function' ? updater(dasar) : { ...dasar, ...updater }
          return prev.map((s) =>
            s.id === dasar.id ? { ...next, updatedAt: Date.now() } : s,
          )
        }
        return prev.map((s) => {
          if (s.id !== id) return s
          const next = typeof updater === 'function' ? updater(s) : { ...s, ...updater }
          return { ...next, updatedAt: Date.now() }
        })
      })
      // Setiap perubahan isi sesi perlu dikirim ke server.
      jadwalkanSimpan(id)
    },
    [jadwalkanSimpan],
  )

  /** Memastikan ada sesi aktif; membuat baru bila belum ada. */
  const ensureSession = useCallback(() => {
    if (activeSession) return activeSession
    const s = createSession()
    setSessions((prev) => [s, ...prev])
    setActiveId(s.id)
    jadwalkanSimpan(s.id)
    return s
  }, [activeSession, jadwalkanSimpan])

  /** Menambah pesan ke sesi (judul otomatis dari pesan pertama). */
  const addMessage = useCallback(
    (sessionId, message) => {
      const msg = {
        id: uid('m'),
        createdAt: Date.now(),
        feedback: null,
        ...message,
      }
      updateSession(sessionId, (s) => {
        const messages = [...s.messages, msg]
        const firstUser = messages.find((m) => m.role === 'user')
        // Judul awal: topik pesan pertama (bukan potongan mentah prompt).
        const title = s.titleLocked || !firstUser ? s.title : makeTitle(firstUser.content)
        return { ...s, messages, title }
      })
      return msg
    },
    [updateSession],
  )

  /* Sesi yang judulnya sudah diminta ke server (agar tidak berulang). */
  const judulDimintaRef = useRef(new Set())

  /**
   * Memperbaiki judul sesi menjadi ringkasan TOPIK dari seluruh percakapan.
   *
   * KENAPA SETELAH JAWABAN PERTAMA, BUKAN SAAT PESAN DIKIRIM
   * --------------------------------------------------------
   * Judul terbaik menyimpulkan apa yang SEDANG DIBICARAKAN. Pertanyaan
   * pertama saja belum tentu menggambarkan topik sesi ("Halo, boleh
   * tanya?"). Setelah ada satu pertanyaan + satu jawaban, server punya
   * bahan yang cukup untuk menuliskan topiknya.
   *
   * Dipanggil sekali per sesi. Judul yang sudah diubah pengguna
   * (`titleLocked`) atau sesi yang sudah punya judul dari server tidak
   * disentuh. Bila server tidak menjawab, judul lokal dari `makeTitle`
   * tetap dipakai — pengguna tidak melihat apa pun yang gagal.
   */
  const segarkanJudul = useCallback(
    async (sessionId) => {
      if (!sessionId || judulDimintaRef.current.has(sessionId)) return
      const sesi = sessionsRef.current.find((s) => s.id === sessionId)
      if (!sesi || sesi.titleLocked) return
      const pesan = sesi.messages || []
      if (!pesan.some((m) => m.role === 'user')) return
      if (!pesan.some((m) => m.role === 'assistant' && (m.content || '').trim())) return

      judulDimintaRef.current.add(sessionId)

      const judul = await buatJudulServer(apiRef.current, pesan.slice(0, 4))
      if (!judul) {
        // Gagal: biarkan judul lokal, izinkan percobaan lagi nanti.
        judulDimintaRef.current.delete(sessionId)
        return
      }

      setSessions((prev) =>
        prev.map((s) => {
          // Judul buatan pengguna selalu menang.
          if (s.id !== sessionId || s.titleLocked) return s
          if (s.title === judul) return s
          return { ...s, title: judul, updatedAt: Date.now() }
        }),
      )
      jadwalkanSimpan(sessionId)
    },
    [jadwalkanSimpan],
  )

  /** Menimpa isi satu pesan (dipakai streaming & edit). */
  const setMessageContent = useCallback(
    (sessionId, messageId, content) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) => (m.id === messageId ? { ...m, content } : m)),
      }))
    },
    [updateSession],
  )

  /**
   * Menyimpan daftar sumber riset pada satu pesan asisten.
   *
   * Dipakai agar kartu sumber tetap terlihat setelah halaman dimuat ulang
   * (ikut tersimpan bersama riwayat), bukan hanya selama streaming.
   */
  const setMessageSources = useCallback(
    (sessionId, messageId, sumber) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.id === messageId ? { ...m, sumber: Array.isArray(sumber) ? sumber : [] } : m,
        ),
      }))
    },
    [updateSession],
  )

  /**
   * Menandai bahwa pesan asisten ini sedang MENGGAMBAR.
   *
   * Dipakai agar UI bisa menampilkan animasi "Sedang menggambar" (kisi
   * titik + persen) alih-alih animasi "Berpikir". Server mengirim
   * sinyalnya SEBELUM gambar dibuat, jadi animasinya sudah benar sejak
   * detik pertama.
   *
   * `deskripsi` hanya dipakai sebagai keterangan kecil selama proses;
   * nilainya tidak disimpan ke riwayat.
   *
   * PENTING — tanda ini HARUS bisa dilepas lagi. Beri `deskripsi` null
   * (atau `selesai: true`) setelah proses gambar berakhir:
   *
   *     setMessageImagePhase(sessionId, messageId, null)
   *
   * Kalau lupa dilepas, animasi "Sedang menggambar" akan tertinggal di
   * layar meskipun gambarnya sudah tampil.
   */
  const setMessageImagePhase = useCallback(
    (sessionId, messageId, deskripsi) => {
      // `null`/`undefined` berarti: proses gambar sudah selesai.
      const sedang = deskripsi !== null && deskripsi !== undefined
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.id === messageId
            ? {
                ...m,
                membuatGambar: sedang,
                deskripsiGambar: sedang ? String(deskripsi || '') : '',
              }
            : m,
        ),
      }))
    },
    [updateSession],
  )

  /**
   * Menyimpan gambar hasil pembuatan AI pada satu pesan asisten.
   *
   * Dipakai agar gambar tetap terlihat setelah halaman dimuat ulang
   * (ikut tersimpan bersama riwayat), bukan hanya selama sesi ini.
   *
   * Catatan ukuran: gambar disimpan sebagai data URL (base64). Karena
   * itu hanya SATU gambar terakhir per pesan yang disimpan, dan
   * pemanggil sebaiknya tidak menyimpan gambar berukuran raksasa.
   */
  const setMessageImage = useCallback(
    (sessionId, messageId, gambar) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.id === messageId
            ? { ...m, gambar: gambar && typeof gambar === 'object' ? gambar : null }
            : m,
        ),
      }))
    },
    [updateSession],
  )

  /** Memberi tanda suka / tidak suka pada pesan asisten. */
  const setFeedback = useCallback(
    (sessionId, messageId, feedback) => {
      updateSession(sessionId, (s) => ({
        ...s,
        messages: s.messages.map((m) =>
          m.id === messageId
            ? { ...m, feedback: m.feedback === feedback ? null : feedback }
            : m,
        ),
      }))
    },
    [updateSession],
  )

  /** Menghapus pesan mulai dari index tertentu (untuk Edit & Regenerasi). */
  const truncateMessages = useCallback(
    (sessionId, keepCount) => {
      updateSession(sessionId, (s) => ({ ...s, messages: s.messages.slice(0, keepCount) }))
    },
    [updateSession],
  )

  const newSession = useCallback(() => {
    // Pakai sesi kosong yang sudah ada bila aktif pun sudah kosong.
    if (activeSession && activeSession.messages.length === 0) return activeSession
    const s = createSession()
    setSessions((prev) => [s, ...prev])
    setActiveId(s.id)
    // Sesi kosong belum punya pesan; tetap dicatat di server agar
    // perangkat lain melihat baris yang sama.
    jadwalkanSimpan(s.id)
    return s
  }, [activeSession, jadwalkanSimpan])

  const selectSession = useCallback((id) => setActiveId(id), [])

  const renameSession = useCallback(
    (id, title) => {
      const clean = title.trim()
      if (!clean) return
      updateSession(id, (s) => ({ ...s, title: clean.slice(0, 120), titleLocked: true }))
    },
    [updateSession],
  )

  const togglePin = useCallback(
    (id) => {
      updateSession(id, (s) => ({ ...s, pinned: !s.pinned }))
    },
    [updateSession],
  )

  const deleteSession = useCallback(
    (id) => {
      setSessions((prev) => prev.filter((s) => s.id !== id))
      setActiveId((cur) => (cur === id ? null : cur))
      kotorRef.current.delete(id)

      // Hapus di server. Bila gagal, sesi akan muncul lagi saat halaman
      // dimuat ulang — jadi pengguna diberi tahu lewat status.
      if (akunSub && settings.saveHistory && getTokenRiwayat()) {
        hapusRiwayatServer(apiRef.current, id).then((hasil) => {
          if (!hasil.ok) setStatusSimpan('perangkat')
        })
      }
    },
    [akunSub, settings.saveHistory],
  )

  const clearAll = useCallback(() => {
    setSessions([])
    setActiveId(null)
    kotorRef.current.clear()
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }

    if (akunSub) {
      writeJSON(keySessions(akunSub), [])
      removeKey(keyActiveSession(akunSub))

      if (getTokenRiwayat()) {
        hapusRiwayatServer(apiRef.current, null).then((hasil) => {
          if (!hasil.ok) setStatusSimpan('perangkat')
        })
      }
    }
  }, [akunSub])

  /* Saat keluar (logout), bersihkan antrean agar tidak mengirim data
     milik akun sebelumnya. Salinan perangkat TIDAK dihapus — riwayat
     akun tetap ada di kuncinya sendiri sehingga muncul lagi saat masuk. */
  useEffect(() => {
    if (akunSub) return
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    kotorRef.current.clear()
    hapusAntreRef.current = []
    // Bersihkan sisa riwayat tamu (tamu tidak boleh punya riwayat).
    removeKeysWithPrefix(KEYS.SESSIONS_PREFIX + 'tamu')
  }, [akunSub])

  /* Kirim sisa perubahan saat komponen dibongkar. */
  useEffect(
    () => () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    },
    [],
  )

  return {
    sessions,
    activeSession,
    activeId,
    loaded,
    ensureSession,
    addMessage,
    setMessageContent,
    setMessageSources,
    setMessageImage,
    setMessageImagePhase,
    setFeedback,
    segarkanJudul,
    truncateMessages,
    newSession,
    selectSession,
    renameSession,
    togglePin,
    deleteSession,
    clearAll,
    setActiveId,
    // False = riwayat tidak disimpan (tamu / saklar dimatikan). Dipakai UI
    // untuk jujur memberi tahu pengguna bahwa percakapannya akan hilang.
    tersimpan: bolehSimpan,
    // Keadaan penyimpanan nyata, untuk pesan di UI.
    statusSimpan,
  }
}
