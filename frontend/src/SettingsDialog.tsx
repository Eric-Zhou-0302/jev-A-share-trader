import { useEffect, useRef, useState } from 'react'
import { Check, KeyRound, X } from 'lucide-react'
import type { Lang, Settings } from './types'
import { translate } from './i18n'
import { api } from './api'

export default function SettingsDialog({ settings, lang, onClose, onSaved }: { settings: Settings; lang: Lang; onClose: () => void; onSaved: (value: Settings) => void }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const [key, setKey] = useState('')
  const [provider, setProvider] = useState(settings.provider)
  const [token, setToken] = useState('')
  const [model, setModel] = useState(settings.model)
  const [markets, setMarkets] = useState(settings.markets)
  const [exclude, setExclude] = useState(settings.exclude_special)
  const [amount, setAmount] = useState(settings.min_amount)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const t = (word: Parameters<typeof translate>[1]) => translate(lang, word)
  useEffect(() => { dialog.current?.showModal() }, [])
  async function save(event: React.FormEvent) {
    event.preventDefault(); setSaving(true); setError('')
    try {
      const updated = await api<Settings>('/settings', lang, { provider: ['akshare', 'tushare'].includes(provider) ? provider : null, tushare_token: token.trim() || null, model, jev_api_key: key || null, markets, exclude_special: exclude, min_amount: amount, language: lang }, 'PUT')
      setKey(''); setToken(''); onSaved(updated); onClose()
    } catch (value) { setError((value as Error).message) } finally { setSaving(false) }
  }
  return <dialog ref={dialog} className="settings-dialog" onCancel={onClose} aria-labelledby="settings-title">
    <form onSubmit={save}><div className="dialog-heading"><div><span className="eyebrow">WORKSPACE</span><h2 id="settings-title">{t('settings')}</h2></div><button type="button" className="icon-button" aria-label={t('close')} onClick={onClose}><X size={20} /></button></div>
      <label className="field"><span>{t('provider')}</span><select value={provider} onChange={event => setProvider(event.target.value)}><option value="akshare">AKShare</option><option value="tushare">Tushare Pro</option>{!['akshare', 'tushare'].includes(provider) && <option value={provider}>{provider}</option>}</select><small>{t('providerHelp')}</small></label>
      <div className="provider-note"><span className="provider-mark">{provider === 'tushare' ? 'TS' : 'AK'}</span><div><strong>{provider === 'tushare' ? 'Tushare Pro' : provider === 'akshare' ? 'AKShare' : provider}</strong><p>{t(provider === 'tushare' ? 'tushareHelp' : 'sourceHelp')}</p></div></div>
      {provider === 'tushare' && <label className="field"><span><KeyRound size={14} /> Tushare Token {settings.tushare_configured && <Check size={14} />}</span><input type="password" autoComplete="new-password" maxLength={512} required={!settings.tushare_configured} value={token} onChange={event => setToken(event.target.value)} placeholder={settings.tushare_configured ? t('keySaved') : t('tokenPlaceholder')} /><small>{t('keyHelp')}</small></label>}
      <label className="field"><span><KeyRound size={14} /> {t('key')} {settings.jev_configured && <Check size={14} />}</span><input type="password" autoComplete="new-password" value={key} onChange={event => setKey(event.target.value)} placeholder={settings.jev_configured ? t('keySaved') : t('keyPlaceholder')} /><small>{t('keyHelp')}</small></label>
      <label className="field"><span>{t('model')}</span><input value={model} required maxLength={100} onChange={event => setModel(event.target.value)} /><small>{t('modelHelp')}</small></label>
      <fieldset><legend>{t('exchanges')}</legend><div className="checkbox-row">{['SH', 'SZ', 'BJ'].map(market => <label key={market}><input type="checkbox" checked={markets.includes(market)} onChange={event => setMarkets(event.target.checked ? [...markets, market] : markets.filter(value => value !== market))} />{({ SH: ['上海', 'Shanghai'], SZ: ['深圳', 'Shenzhen'], BJ: ['北京', 'Beijing'] } as Record<string, string[]>)[market][lang === 'en' ? 1 : 0]}</label>)}</div></fieldset>
      <label className="checkbox-label"><input type="checkbox" checked={exclude} onChange={event => setExclude(event.target.checked)} />{t('excludeSpecial')}</label>
      <label className="field"><span>{t('liquidity')}</span><input type="number" min="0" step="100000" value={amount} onChange={event => setAmount(Number(event.target.value))} /><small>{t('liquidityHelp')}</small></label>
      {error && <p className="error-message" role="alert">{error}</p>}
      <button className="button primary full-width" type="submit" disabled={saving || markets.length === 0}>{saving ? t('saving') : t('save')}</button>
    </form>
  </dialog>
}
