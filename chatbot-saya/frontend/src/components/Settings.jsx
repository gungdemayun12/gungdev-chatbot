/**
 * Settings.jsx — panel pengaturan dengan 6 tab:
 * Umum, Personalisasi, Percakapan, Lanjutan, Pintasan, Tentang.
 *
 * Semua nilai disimpan di localStorage lewat useSettings dan langsung
 * diterapkan (tema, ukuran font, dsb).
 */
import { useState } from 'react'
import Modal from './Modal.jsx'
import { DEFAULT_API_URL } from '../lib/api.js'
import {
  AlignLeft,
  Download,
  Info,
  Keyboard,
  Monitor,
  Moon,
  MessagesSquare,
  Palette,
  RotateCcw,
  SlidersHorizontal,
  Sun,
  Type,
  Wand2,
  Trash2,
} from './icons.jsx'

const TABS = [
  { key: 'umum', label: 'Umum', icon: SlidersHorizontal },
  { key: 'personalisasi', label: 'Personalisasi', icon: Wand2 },
  { key: 'percakapan', label: 'Percakapan', icon: MessagesSquare },
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
            </>
          )}

          {/* ---------------- PERCAKAPAN ---------------- */}
          {tab === 'percakapan' && (
            <>
              <Field
                label="Simpan riwayat"
                hint="Jika dimatikan, percakapan tidak disimpan setelah tab ditutup."
              >
                <label className="switch">
                  <input
                    type="checkbox"
                    checked={settings.saveHistory}
                    onChange={(e) => updateSettings({ saveHistory: e.target.checked })}
                  />
                  <span className="switch__track" aria-hidden="true" />
                  <span className="switch__label">
                    {settings.saveHistory ? 'Aktif' : 'Nonaktif'}
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

          {/* ---------------- LANJUTAN ---------------- */}
          {tab === 'lanjutan' && (
            <>
              <Field
                label="URL backend"
                hint={
                  settings.apiUrl
                    ? `Status: ${apiOnline ? 'terhubung' : 'tidak terhubung'} — memakai isian manual.`
                    : `Status: ${apiOnline ? 'terhubung' : 'tidak terhubung'} — memakai bawaan aplikasi (${DEFAULT_API_URL}).`
                }
                htmlFor="set-api"
              >
                <input
                  id="set-api"
                  className="input"
                  type="url"
                  value={settings.apiUrl}
                  onChange={(e) => updateSettings({ apiUrl: e.target.value })}
                  placeholder={DEFAULT_API_URL}
                />
                {settings.apiUrl && (
                  <div className="btn-row" style={{ marginTop: 8 }}>
                    <button
                      type="button"
                      className="btn btn--ghost btn--sm"
                      onClick={() => updateSettings({ apiUrl: '' })}
                    >
                      Kembalikan ke bawaan
                    </button>
                  </div>
                )}
              </Field>

              <Field
                label="Model"
                hint="Pilihan ini hanya sebagai catatan — model yang benar-benar dipakai ditentukan oleh variabel GROQ_MODEL / OLLAMA_MODEL di server."
                htmlFor="set-model"
              >
                <select
                  id="set-model"
                  className="input"
                  value={settings.model}
                  onChange={(e) => updateSettings({ model: e.target.value })}
                >
                  <optgroup label="Groq (cloud)">
                    <option value="openai/gpt-oss-120b">openai/gpt-oss-120b</option>
                    <option value="openai/gpt-oss-20b">openai/gpt-oss-20b</option>
                  </optgroup>
                  <optgroup label="Ollama (lokal)">
                    <option value="deepseek-r1:7b">deepseek-r1:7b</option>
                    <option value="deepseek-r1:1.5b">deepseek-r1:1.5b</option>
                    <option value="llama3.2">llama3.2</option>
                    <option value="qwen2.5:7b">qwen2.5:7b</option>
                  </optgroup>
                </select>
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

              <Field
                label="System prompt"
                hint="Instruksi dasar yang menentukan kepribadian GungDev."
              >
                <textarea
                  className="input input--area"
                  rows={6}
                  value={settings.systemPrompt}
                  onChange={(e) => updateSettings({ systemPrompt: e.target.value })}
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
                GungDev adalah asisten AI berbahasa Indonesia yang ramah, akurat, dan jelas.
                Berjalan sepenuhnya di komputer Anda melalui Ollama — tidak ada data
                percakapan yang dikirim ke layanan pihak ketiga.
              </p>
              <ul className="about__list">
                <li>Riwayat disimpan lokal di peramban Anda (localStorage).</li>
                <li>Jawaban dihasilkan model lokal melalui backend FastAPI.</li>
                <li>GungDev bisa membuat kesalahan — periksa kembali informasi penting.</li>
              </ul>
              <p className="about__meta">
                Antarmuka: React + Vite · Backend: FastAPI + Ollama · Markdown: react-markdown
              </p>
            </div>
          )}
        </div>
      </div>
    </Modal>
  )
}
