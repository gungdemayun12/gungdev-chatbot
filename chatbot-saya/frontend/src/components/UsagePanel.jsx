/**
 * UsagePanel.jsx — panel pemakaian & sisa kuota AI.
 *
 * Prinsip desain:
 *   1. JUJUR — angka yang ditampilkan berasal dari penyedia AI, dan
 *      bila masih perkiraan, hal itu ditulis terang-terangan.
 *   2. TENANG — kuota bukan hal yang perlu dicemaskan pengguna biasa.
 *      Warna hanya berubah saat benar-benar mendekati batas.
 *   3. TIDAK MENGHABISKAN KUOTA — panel ini hanya membaca /usage,
 *      tidak memanggil model AI sama sekali.
 *
 * Tampilan mengikuti gaya yang sudah ada (token warna, radius, font)
 * agar tidak terasa seperti komponen tempelan.
 */
import { useCallback, useEffect, useState } from 'react'
import Modal from './Modal.jsx'
import { Activity, RefreshCw } from './icons.jsx'
import { getTokenRiwayat } from '../lib/riwayat.js'

/* ---------------- Bantuan format ---------------- */

/** 17500 -> "17.5 rb", 200000 -> "200 rb", 1000 -> "1.000" */
function angkaRingkas(n) {
  const v = Number(n) || 0
  if (v >= 1_000_000) return (v / 1_000_000).toFixed(1).replace('.0', '') + ' jt'
  if (v >= 10_000) return (v / 1000).toFixed(1).replace('.0', '') + ' rb'
  return v.toLocaleString('id-ID')
}

/** 25200 -> "7 jam", 900 -> "15 menit", 45 -> "45 detik" */
function durasi(detik) {
  const d = Math.max(0, Math.round(Number(detik) || 0))
  if (d >= 86400) {
    const hari = Math.floor(d / 86400)
    const sisaJam = Math.floor((d % 86400) / 3600)
    return sisaJam ? `${hari} hari ${sisaJam} jam` : `${hari} hari`
  }
  if (d >= 3600) {
    const jam = Math.floor(d / 3600)
    const menit = Math.floor((d % 3600) / 60)
    return menit ? `${jam} jam ${menit} menit` : `${jam} jam`
  }
  if (d >= 60) return `${Math.floor(d / 60)} menit`
  return `${d} detik`
}

/** Warna bar berdasarkan persen terpakai. */
function warnaBar(persen) {
  if (persen >= 90) return 'is-danger'
  if (persen >= 70) return 'is-warning'
  return ''
}

/* ---------------- Satu baris kuota ---------------- */
function BarKuota({ label, terpakai, batas, sisa, persen, satuan }) {
  return (
    <div className="usage-bar">
      <div className="usage-bar__head">
        <span className="usage-bar__label">{label}</span>
        <span className="usage-bar__value">
          <strong>{angkaRingkas(terpakai)}</strong>
          <span className="usage-bar__of"> / {angkaRingkas(batas)} {satuan}</span>
        </span>
      </div>
      <div
        className={`usage-bar__track ${warnaBar(persen)}`}
        role="progressbar"
        aria-valuenow={Math.round(persen)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${label}: ${persen}% terpakai`}
      >
        <div
          className="usage-bar__fill"
          style={{ width: `${Math.max(persen, terpakai > 0 ? 1.5 : 0)}%` }}
        />
      </div>
      <div className="usage-bar__foot">
        <span>Sisa {angkaRingkas(sisa)} {satuan}</span>
        <span>{persen}% terpakai</span>
      </div>
    </div>
  )
}

/* ---------------- Isi panel (dipakai modal & Pengaturan) ---------------- */
export function UsageContent({ apiUrl, apiOnline, aktif = true }) {
  const [data, setData] = useState(null)
  const [memuat, setMemuat] = useState(false)
  const [galat, setGalat] = useState(false)

  const ambil = useCallback(async () => {
    if (!apiUrl) return
    setMemuat(true)
    setGalat(false)
    try {
      // Token dikirim agar backend menyertakan pemakaian akun ini.
      const token = getTokenRiwayat()
      const res = await fetch(`${apiUrl.replace(/\/+$/, '')}/usage`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      })
      if (!res.ok) throw new Error('HTTP ' + res.status)
      setData(await res.json())
    } catch {
      setGalat(true)
      setData(null)
    } finally {
      setMemuat(false)
    }
  }, [apiUrl])

  /* Muat saat aktif + segarkan tiap 30 detik.
     setState dipanggil di dalam promise (bukan langsung di body
     effect) agar tidak memicu render berantai. */
  useEffect(() => {
    if (!aktif) return undefined
    let batal = false
    const jalan = () => {
      if (batal) return
      ambil()
    }
    Promise.resolve().then(jalan)
    const id = setInterval(jalan, 30000)
    return () => {
      batal = true
      clearInterval(id)
    }
  }, [aktif, ambil])

  const persenRequest = data?.requests?.persen ?? 0
  const hampirHabis = persenRequest >= 90
  // Bagian "pemakaian saya" hanya ada bila backend mengenali akunnya.
  const akun = data?.akun || null

  return (
    <div className="usage">
      {!apiOnline && (
        <div className="usage__notice is-danger">
          Server tidak terhubung. Angka di bawah mungkin sudah usang.
        </div>
      )}

      {memuat && !data && (
        <div className="usage__loading">
          <RefreshCw size={16} className="spin" />
          <span>Memuat data pemakaian…</span>
        </div>
      )}

      {galat && !memuat && (
        <div className="usage__notice is-danger">
          Data pemakaian belum bisa diambil. Coba lagi sebentar lagi.
        </div>
      )}

      {data && (
        <>
          {/* --- Ringkasan model aktif --- */}
          <div className="usage__hero">
            <div className="usage__hero-icon">
              <Activity size={18} />
            </div>
            <div className="usage__hero-text">
              <div className="usage__hero-title">
                Kuota hari ini
              </div>
              <div className="usage__hero-sub">
                Reset dalam <strong>{durasi(data.reset?.detik)}</strong>
                {data.reset?.waktu_utc && (
                  <span className="usage__hero-time">
                    <span className="usage__hero-sep">·</span>{' '}
                    {new Date(data.reset.waktu_utc).toLocaleString('id-ID', {
                      hour: '2-digit',
                      minute: '2-digit',
                      day: 'numeric',
                      month: 'short',
                    })}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* --- Pemakaian akun ini sendiri ---
               Ini JATAH SUNGGUHAN milik akun ini (100 pesan/hari),
               terpisah dari kuota bersama di bawah. Bila habis, chat
               ditolak sampai reset — jadi angkanya harus terlihat
               jelas, bukan tersembunyi di rincian. */}
          {akun && (
            <div className="usage__akun">
              <div className="usage__akun-head">
                <span className="usage__akun-label">Pemakaian saya</span>
                <span className="usage__akun-total">
                  {angkaRingkas(akun.requests?.terpakai || 0)}
                  <span className="usage__akun-sep"> / </span>
                  {angkaRingkas(akun.requests?.batas || 0)} pesan
                </span>
              </div>

              <div
                className={`usage-bar__track usage__akun-track ${warnaBar(
                  akun.requests?.persen ?? 0,
                )}`}
                role="progressbar"
                aria-valuenow={Math.round(akun.requests?.persen ?? 0)}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Jatah pesan akun ini: ${akun.requests?.persen ?? 0}% terpakai`}
              >
                <div
                  className="usage-bar__fill"
                  style={{
                    width: `${Math.max(
                      akun.requests?.persen ?? 0,
                      (akun.requests?.terpakai || 0) > 0 ? 1.5 : 0,
                    )}%`,
                  }}
                />
              </div>

              <div className="usage__akun-note">
                Sisa <strong>{angkaRingkas(akun.requests?.sisa || 0)}</strong> pesan
                hari ini
                {akun.reset?.detik > 0 && (
                  <> · pulih dalam {durasi(akun.reset.detik)}</>
                )}
                {(akun.tokens?.terpakai || 0) > 0 && (
                  <>
                    <span className="usage__akun-sep">·</span>
                    {angkaRingkas(akun.tokens.terpakai)} token terpakai
                  </>
                )}
              </div>

              {akun.habis && (
                <div className="usage__akun-habis">
                  Jatah Anda hari ini habis. Chat bisa dipakai lagi setelah
                  reset — riwayat lama tetap bisa dibaca.
                </div>
              )}
            </div>
          )}

          {!akun && data.tamu && (
            <div className="usage__akun">
              <div className="usage__akun-head">
                <span className="usage__akun-label">Mode tamu</span>
                <span className="usage__akun-total">
                  {angkaRingkas(data.tamu.batas_pesan || 0)} pesan/hari
                </span>
              </div>
              <div className="usage__akun-note">
                Masuk dengan Google untuk mendapat jatah{' '}
                <strong>100 pesan/hari</strong> milik akun Anda sendiri.
              </div>
            </div>
          )}

          {hampirHabis && (
            <div className="usage__notice is-warning">
              Kuota harian hampir habis. Pemakaian akan pulih otomatis
              dalam {durasi(data.reset?.detik)}.
            </div>
          )}

          {/* --- Dua bar utama --- */}
          <BarKuota
            label="Permintaan (request)"
            terpakai={data.requests?.terpakai}
            batas={data.requests?.batas}
            sisa={data.requests?.sisa}
            persen={data.requests?.persen}
            satuan="req"
          />
          <BarKuota
            label="Token"
            terpakai={data.tokens?.terpakai}
            batas={data.tokens?.batas}
            sisa={data.tokens?.sisa}
            persen={data.tokens?.persen}
            satuan="token"
          />

          {/* --- Rincian --- */}
          <div className="usage__grid">
            <div className="usage__cell">
              <div className="usage__cell-label">Reset berikutnya</div>
              <div className="usage__cell-value">{durasi(data.reset?.detik)}</div>
            </div>
            <div className="usage__cell">
              <div className="usage__cell-label">Zona waktu</div>
              <div className="usage__cell-value">{data.reset?.zona || 'UTC'}</div>
            </div>
            <div className="usage__cell">
              <div className="usage__cell-label">Batas per menit</div>
              <div className="usage__cell-value">
                {data.per_menit?.request_batas} req ·{' '}
                {angkaRingkas(data.per_menit?.token_batas)} token
              </div>
            </div>
            <div className="usage__cell">
              <div className="usage__cell-label">Akurasi permintaan</div>
              <div className="usage__cell-value">
                {data.requests?.akurat ? 'Langsung dari penyedia' : 'Perkiraan server'}
              </div>
            </div>
          </div>

          {/* --- Penjelasan jujur --- */}
          <p className="usage__fineprint">
            Jatah <strong>Pemakaian saya</strong> adalah milik akun Anda sendiri
            ({angkaRingkas(akun?.requests?.batas || 100)} pesan/hari) dan terpisah
            dari akun lain. Bila habis, chat berhenti sampai reset — riwayat tetap
            bisa dibaca. Bar <strong>Permintaan</strong> dan <strong>Token</strong>{' '}
            di atas adalah kuota bersama seluruh pengunjung situs, ditampilkan agar
            Anda tahu kondisi layanan. Panel ini tidak memakai kuota saat dibuka.
          </p>

          <button
            type="button"
            className="btn btn--ghost btn--sm usage__refresh"
            onClick={ambil}
            disabled={memuat}
          >
            <RefreshCw size={14} className={memuat ? 'spin' : ''} />
            {memuat ? 'Menyegarkan…' : 'Segarkan'}
          </button>
        </>
      )}
    </div>
  )
}

/* ---------------- Panel modal ---------------- */
export default function UsagePanel({ open, onClose, apiUrl, apiOnline }) {
  return (
    <Modal open={open} onClose={onClose} title="Pemakaian & Kuota" size="md">
      <UsageContent apiUrl={apiUrl} apiOnline={apiOnline} aktif={open} />
    </Modal>
  )
}
