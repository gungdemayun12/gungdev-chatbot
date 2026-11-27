/**
 * Settings.jsx — panel pengaturan dengan tab:
 * Umum, Personalisasi, Percakapan, Akun, Lanjutan, Pintasan, Tentang.
 *
 * Semua nilai disimpan di localStorage lewat useSettings dan langsung
 * diterapkan (tema, ukuran font, dsb).
 */
import { useState } from 'react'
import Modal from './Modal.jsx'
import { UsageContent } from './UsagePanel.jsx'
import { MODEL_PILIHAN } from '../lib/models.js'
import {
  AlignLeft,
  Download,
  Info,
  Keyboard,
  LogOut,
  Monitor,
  Moon,
  MessagesSquare,
  Palette,
  RotateCcw,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Type,
  User,
  Wand2,
  Trash2,
} from './icons.jsx'

const TABS = [
  { key: 'umum', label: 'Umum', icon: SlidersHorizontal },
  { key: 'personalisasi', label: 'Personalisasi', icon: Wand2 },
  { key: 'percakapan', label: 'Percakapan', icon: MessagesSquare },
  { key: 'akun', label: 'Akun', icon: User },
  { key: 'lanjutan', label: 'Lanjutan', icon: Palette },
  { key: 'pintasan', label: 'Pintasan', icon: Keyboard },
  { key: 'tentang', label: 'Tentang', icon: Info },
]

/** Baris pengaturan dengan label + deskripsi. */
function Field({ label, hint, children, htmlFor }) {
  return (
    <div className="field">
      <div className="field__label-wrap">
        <label className="field__label" htmlFor={htmlFor}>
          {label}
        </label>
        {hint && <p className="field__hint">{hint}</p>}
      </div>
      <div className="field__control">{children}</div>
    </div>
  )
}

/** Grup tombol pilihan (segmented control). */
function Segmented({ value, onChange, options, name }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={name}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className={`segmented__btn ${value === o.value ? 'is-active' : ''}`}
          onClick={() => onChange(o.value)}
        >
          {o.icon && <o.icon size={14} aria-hidden="true" />}
          {o.label}
        </button>
      ))}
    </div>
  )
}

export default function Settings({
  open,
  onClose,
  settings,
  updateSettings,
  resetSettings,
  onClearAll,
  onExportAll,
  apiOnline,
  apiUrl,
  user,
  onOpenLogin,
  onLogout,
}) {
  const [tab, setTab] = useState('umum')

  return (
    <Modal open={open} onClose={onClose} title="Pengaturan" size="lg">
      <div className="settings">
        <nav className="settings__tabs" role="tablist" aria-label="Kategori pengaturan">
          {TABS.map((t) => {
            const Icon = t.icon
            return (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={tab === t.key}
                aria-controls={`panel-${t.key}`}
                id={`tab-${t.key}`}
                className={`settings__tab ${tab === t.key ? 'is-active' : ''}`}
                onClick={() => setTab(t.key)}
              >
                <Icon size={15} aria-hidden="true" />
                <span>{t.label}</span>
              </button>
            )
          })}
        </nav>

        <div
          className="settings__panel"
          role="tabpanel"
          id={`panel-${tab}`}
          aria-labelledby={`tab-${tab}`}
        >
          {/* ---------------- UMUM ---------------- */}
          {tab === 'umum' && (
            <>
              <Field label="Tema" hint="Pilih tampilan terang, gelap, atau ikuti sistem.">
                <Segmented
                  name="Tema"
                  value={settings.theme}
                  onChange={(v) => updateSettings({ theme: v })}
                  options={[
                    { value: 'light', label: 'Terang', icon: Sun },
                    { value: 'dark', label: 'Gelap', icon: Moon },
                    { value: 'system', label: 'Sistem', icon: Monitor },
                  ]}
                />
              </Field>

              <Field label="Bahasa" hint="Bahasa antarmuka aplikasi." htmlFor="set-lang">
                <select
                  id="set-lang"
                  className="input"
                  value={settings.language}
                  onChange={(e) => updateSettings({ language: e.target.value })}
                >
                  <option value="id">Bahasa Indonesia</option>
                  <option value="en">English (segera)</option>
                </select>
              </Field>

              <Field label="Ukuran font" hint="Ukuran teks percakapan.">
                <Segmented
                  name="Ukuran font"
                  value={settings.fontSize}
                  onChange={(v) => updateSettings({ fontSize: v })}
                  options={[
                    { value: 'small', label: 'Kecil', icon: Type },
                    { value: 'medium', label: 'Sedang', icon: Type },
                    { value: 'large', label: 'Besar', icon: Type },
                  ]}
                />
              </Field>

              <Field label="Nama panggilan" hint="Dipakai pada sapaan dan profil.">
                <input
                  className="input"
                  type="text"
                  maxLength={40}
                  value={settings.nickname}
                  placeholder="Kamu"
                  onChange={(e) => updateSettings({ nickname: e.target.value })}
                />
              </Field>
            </>
          )}

          {/* ---------------- PERSONALISASI ---------------- */}
          {tab === 'personalisasi' && (
            <>
              <Field
                label="Apa yang perlu GungDev ketahui tentang kamu?"
                hint="Ditambahkan ke instruksi sistem. Contoh: profesi, gaya kerja, konteks proyek."
              >
                <textarea
                  className="input input--area"
                  rows={5}
                  maxLength={2000}
                  value={settings.customInstructions}
                  placeholder="Contoh: Saya frontend developer, lebih suka contoh kode TypeScript…"
                  onChange={(e) => updateSettings({ customInstructions: e.target.value })}
                />
              </Field>

              <Field label="Gaya jawaban">
                <Segmented
                  name="Gaya jawaban"
                  value={settings.responseStyle}
                  onChange={(v) => updateSettings({ responseStyle: v })}
                  options={[
                    { value: 'concise', label: 'Singkat', icon: AlignLeft },
                    { value: 'balanced', label: 'Seimbang' },
                    { value: 'detailed', label: 'Detail' },
                  ]}
                />
              </Field>

              <Field label="Nada">
                <Segmented
                  name="Nada"
                  value={settings.tone}
                  onChange={(v) => updateSettings({ tone: v })}
                  options={[
                    { value: 'casual', label: 'Santai' },
                    { value: 'formal', label: 'Formal' },
                  ]}
                />
              </Field>

              <Field
                label="Bahasa jawaban AI"
                hint="Bahasa yang dipakai AI saat menjawab. Bisa berbeda dari bahasa menu."
                htmlFor="set-bahasa-jawaban"
              >
                <select
                  id="set-bahasa-jawaban"
                  className="input"
                  value={settings.bahasaJawaban}
                  onChange={(e) => updateSettings({ bahasaJawaban: e.target.value })}
                >
                  <option value="id">Bahasa Indonesia</option>
                  <option value="en">English</option>
                </select>
              </Field>

              <Field
                label="Panjang jawaban"
                hint="Perkiraan panjang jawaban yang Anda inginkan."
              >
                <Segmented
                  name="Panjang jawaban"
                  value={settings.panjangJawaban}
                  onChange={(v) => updateSettings({ panjangJawaban: v })}
                  options={[
                    { value: 'pendek', label: 'Pendek' },
                    { value: 'sedang', label: 'Sedang' },
                    { value: 'panjang', label: 'Panjang' },
                  ]}
                />
              </Field>
            </>
          )}

          {/* ---------------- PERCAKAPAN ---------------- */}
          {tab === 'percakapan' && (
            <>
              {/* Status akun: apakah riwayat benar-benar tersimpan. */}
              <Field
                label="Akun"
                hint={
                  user
                    ? 'Riwayat percakapan disimpan di perangkat ini dan terikat ke akun Google Anda.'
                    : 'Anda memakai mode tamu. Riwayat tidak disimpan dan pemakaian dibatasi.'
                }
              >
                {user ? (
                  <div className="set-account">
                    <span className="set-account__avatar" aria-hidden="true">
                      {user.name.charAt(0).toUpperCase()}
                    </span>
                    <span className="set-account__text">
                      <span className="set-account__name">{user.name}</span>
                      <span className="set-account__mail">{user.email}</span>
                    </span>
                    <span className="set-account__ok">Terhubung</span>
                  </div>
                ) : (
                  <button type="button" className="btn btn--primary" onClick={onOpenLogin}>
                    <User size={15} /> Masuk dengan Google
                  </button>
                )}
              </Field>

              <Field
                label="Simpan riwayat"
                hint={
                  user
                    ? 'Jika dimatikan, percakapan tidak disimpan setelah tab ditutup.'
                    : 'Aktifkan dengan masuk ke akun Google Anda terlebih dahulu.'
                }
              >
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={settings.saveHistory}
                    disabled={!user}
                    onChange={(e) => updateSettings({ saveHistory: e.target.checked })}
                  />
                  <span className="switch__track" aria-hidden="true" />
                  <span className="switch__label">
                    {!user ? 'Perlu masuk' : settings.saveHistory ? 'Aktif' : 'Nonaktif'}
                  </span>
                </label>
              </Field>

              <Field
                label="Kirim dengan Enter"
                hint="Aktif: Enter mengirim pesan, Shift+Enter membuat baris baru. Nonaktif: Enter membuat baris baru."
              >
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={settings.sendWithEnter}
                    onChange={(e) => updateSettings({ sendWithEnter: e.target.checked })}
                  />
                  <span className="switch__track" aria-hidden="true" />
                  <span className="switch__label">
                    {settings.sendWithEnter ? 'Aktif' : 'Nonaktif'}
                  </span>
                </label>
              </Field>

              <Field
                label="Gulir otomatis"
                hint="Selalu gulir ke pesan terbaru saat jawaban AI sedang berjalan."
              >
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={settings.autoScroll}
                    onChange={(e) => updateSettings({ autoScroll: e.target.checked })}
                  />
                  <span className="switch__track" aria-hidden="true" />
                  <span className="switch__label">
                    {settings.autoScroll ? 'Aktif' : 'Nonaktif'}
                  </span>
                </label>
              </Field>

              <Field label="Tampilkan jam pesan" hint="Menampilkan waktu kirim di setiap pesan.">
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={settings.showTimestamps}
                    onChange={(e) => updateSettings({ showTimestamps: e.target.checked })}
                  />
                  <span className="switch__track" aria-hidden="true" />
                  <span className="switch__label">
                    {settings.showTimestamps ? 'Aktif' : 'Nonaktif'}
                  </span>
                </label>
              </Field>

              <Field
                label="Konfirmasi sebelum menghapus"
                hint="Menampilkan dialog tanya dulu sebelum percakapan dihapus."
              >
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={settings.confirmBeforeDelete}
                    onChange={(e) =>
                      updateSettings({ confirmBeforeDelete: e.target.checked })
                    }
                  />
                  <span className="switch__track" aria-hidden="true" />
                  <span className="switch__label">
                    {settings.confirmBeforeDelete ? 'Aktif' : 'Nonaktif'}
                  </span>
                </label>
              </Field>

              <Field label="Ekspor semua percakapan" hint="Unduh seluruh riwayat sebagai file.">
                <div className="btn-row">
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => onExportAll('json')}
                  >
                    <Download size={15} /> JSON
                  </button>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    onClick={() => onExportAll('md')}
                  >
                    <Download size={15} /> Markdown
                  </button>
                </div>
              </Field>

              <Field label="Hapus semua riwayat" hint="Tindakan ini tidak dapat dibatalkan.">
                <button type="button" className="btn btn--danger" onClick={onClearAll}>
                  <Trash2 size={15} /> Hapus semua
                </button>
              </Field>
            </>
          )}

          {/* ---------------- AKUN ---------------- */}
          {tab === 'akun' && (
            <>
              <Field
                label="Status akun"
                hint={
                  user
                    ? 'Anda masuk. Percakapan tersimpan ke akun Google Anda dan bisa dibuka di perangkat lain.'
                    : 'Anda memakai mode tamu. Masuk agar percakapan tersimpan dan jatah lebih besar.'
                }
              >
                {user ? (
                  <div className="set-account">
                    <span className="set-account__avatar" aria-hidden="true">
                      {user.name.charAt(0).toUpperCase()}
                    </span>
                    <span className="set-account__text">
                      <span className="set-account__name">{user.name}</span>
                      <span className="set-account__mail">{user.email}</span>
                    </span>
                    <span className="set-account__ok">Terhubung</span>
                  </div>
                ) : (
                  <button type="button" className="btn btn--primary" onClick={onOpenLogin}>
                    <User size={15} /> Masuk dengan Google
                  </button>
                )}
              </Field>

              <Field
                label="Jatah saya"
                hint="Berapa pesan yang masih tersisa dan kapan jatah diperbarui. Membuka panel ini tidak memakai jatah."
              >
                <div className="settings-usage">
                  <UsageContent apiUrl={apiUrl} apiOnline={apiOnline} aktif={open} />
                </div>
              </Field>

              <Field
                label="Privasi"
                hint="Percakapan hanya bisa dibuka oleh akun Anda sendiri. Data disimpan di penyimpanan server yang terenkripsi saat transit."
              >
                <div className="set-privacy">
                  <ShieldCheck size={15} aria-hidden="true" />
                  <span>
                    {user
                      ? 'Riwayat terikat ke akun Anda dan tidak dibagikan ke akun lain.'
                      : 'Mode tamu: riwayat hanya ada di perangkat ini.'}
                  </span>
                </div>
              </Field>

              {user && (
                <Field
                  label="Keluar dari akun"
                  hint="Percakapan tetap tersimpan dan akan muncul lagi saat Anda masuk kembali."
                >
                  <button type="button" className="btn btn--danger" onClick={onLogout}>
                    <LogOut size={15} /> Keluar
                  </button>
                </Field>
              )}
            </>
          )}

          {/* ---------------- LANJUTAN ---------------- */}
          {tab === 'lanjutan' && (
            <>
              <Field
                label="Model AI"
                hint="Pilih model yang ingin dipakai. Bisa juga diganti kapan saja dari kotak pesan."
              >
                <div className="model-list" role="radiogroup" aria-label="Pilih model AI">
                  {MODEL_PILIHAN.map((m) => {
                    const aktifModel = settings.model === m.id
                    return (
                      <button
                        key={m.id}
                        type="button"
                        role="radio"
                        aria-checked={aktifModel}
                        className={`model-list__item ${aktifModel ? 'is-active' : ''}`}
                        onClick={() => updateSettings({ model: m.id })}
                      >
                        <span className="model-list__dot" aria-hidden="true" />
                        <span className="model-list__text">
                          <span className="model-list__name">{m.id}</span>
                          <span className="model-list__ket">{m.ket}</span>
                        </span>
                      </button>
                    )
                  })}
                </div>
              </Field>

              <Field
                label={`Temperature: ${settings.temperature.toFixed(1)}`}
                hint="Rendah (0.2–0.5) untuk jawaban faktual, tinggi untuk kreatif."
                htmlFor="set-temp"
              >
                <input
                  id="set-temp"
                  className="range"
                  type="range"
                  min="0"
                  max="1.5"
                  step="0.1"
                  value={settings.temperature}
                  onChange={(e) => updateSettings({ temperature: Number(e.target.value) })}
                />
              </Field>

              <Field
                label={`Panjang maksimum jawaban: ${settings.maxTokens} token`}
                htmlFor="set-maxtok"
              >
                <input
                  id="set-maxtok"
                  className="range"
                  type="range"
                  min="256"
                  max="8192"
                  step="128"
                  value={settings.maxTokens}
                  onChange={(e) => updateSettings({ maxTokens: Number(e.target.value) })}
                />
              </Field>

              <button type="button" className="btn btn--ghost" onClick={resetSettings}>
                <RotateCcw size={15} /> Kembalikan pengaturan awal
              </button>
            </>
          )}

          {/* ---------------- PINTASAN ---------------- */}
          {tab === 'pintasan' && (
            <ul className="shortcuts">
              {[
                { keys: ['Ctrl', 'K'], desc: 'Cari percakapan' },
                { keys: ['Ctrl', 'Shift', 'O'], desc: 'Percakapan baru' },
                { keys: ['Ctrl', 'B'], desc: 'Tampilkan / sembunyikan sidebar' },
                { keys: ['Esc'], desc: 'Tutup dialog' },
                { keys: ['Enter'], desc: 'Kirim pesan' },
                { keys: ['Shift', 'Enter'], desc: 'Baris baru di kotak pesan' },
              ].map((s) => (
                <li key={s.desc} className="shortcuts__row">
                  <span className="shortcuts__desc">{s.desc}</span>
                  <span className="shortcuts__keys">
                    {s.keys.map((k, i) => (
                      <span key={k}>
                        <kbd>{k}</kbd>
                        {i < s.keys.length - 1 && <span className="shortcuts__plus">+</span>}
                      </span>
                    ))}
                  </span>
                </li>
              ))}
            </ul>
          )}

          {/* ---------------- TENTANG ---------------- */}
          {tab === 'tentang' && (
            <div className="about">
              <div className="about__brand">
                <span className="about__mark" aria-hidden="true">
                  G
                </span>
                <div>
                  <h3 className="about__name">GungDev</h3>
                  <p className="about__ver">Versi 2.0.0</p>
                </div>
              </div>
              <p className="about__desc">
                GungDev adalah asisten AI berbahasa Indonesia yang ramah, akurat, dan
                jelas. Dirancang untuk membantu Anda menjawab pertanyaan, menulis,
                belajar, dan menyelesaikan pekerjaan sehari-hari.
              </p>
              <ul className="about__list">
                <li>Riwayat percakapan disimpan lokal di peramban Anda.</li>
                <li>Anda bisa memilih model yang paling pas dari kotak pesan.</li>
                <li>GungDev bisa membuat kesalahan — periksa kembali informasi penting.</li>
              </ul>
              <p className="about__meta">Dibuat dan dikembangkan oleh GungDev.</p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
