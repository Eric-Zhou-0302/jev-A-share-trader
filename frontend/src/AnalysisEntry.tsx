import { useEffect, useState } from 'react'
import { Activity, ArrowRight, ArrowUpRight, Layers3, ListFilter, LoaderCircle, Search, ShieldCheck } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Lang, Settings, Stock } from './types'

const stockCode = /^\d{6}(\.(SH|SZ|BJ))?$/i
export default function AnalysisEntry({ lang, initialSymbol, settings, busy, onAnalyze, onConfigure }: { lang: Lang; initialSymbol: string; settings: Settings | null; busy: boolean; onAnalyze: (symbol: string) => void; onConfigure: () => void }) {
  const [query, setQuery] = useState(initialSymbol)
  const [chosen, setChosen] = useState(!!initialSymbol)
  const [matches, setMatches] = useState<Stock[]>([])
  const [searching, setSearching] = useState(false)
  const [error, setError] = useState('')
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  useEffect(() => {
    setMatches([]); setError(''); setSearching(false)
    if (chosen || query.trim().length < 2) return
    const controller = new AbortController()
    setSearching(true)
    const timer = window.setTimeout(async () => {
      try {
        const data = await api<{ items: Stock[] }>(`/stocks?q=${encodeURIComponent(query.trim())}`, lang, undefined, 'GET', controller.signal)
        if (!controller.signal.aborted) setMatches(data.items)
      } catch (value) { if (!controller.signal.aborted) setError((value as Error).message) }
      finally { if (!controller.signal.aborted) setSearching(false) }
    }, 350)
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [query, chosen, lang, settings?.provider])
  return <div className="welcome-workspace"><div className="welcome-eyebrow"><span/> AFTER THE CLOSE</div><h1>{t('emptyTitle')}</h1><p className="welcome-description">{t('entryHint')}</p>
    <form className="analysis-form" onSubmit={event => { event.preventDefault(); if (stockCode.test(query.trim())) onAnalyze(query.trim()) }}><Search size={19}/><input required aria-label={t('searchPlaceholder')} placeholder={t('searchPlaceholder')} value={query} onChange={event => { setQuery(event.target.value); setChosen(false) }} autoComplete="off" maxLength={60}/><button className="button primary" disabled={busy || !stockCode.test(query.trim())} type="submit">{t('startAnalysis')}<ArrowUpRight size={17}/></button></form>
    {!chosen && query.trim().length >= 2 && <div className="entry-search" aria-label={t('searchResults')}>{searching ? <p role="status"><LoaderCircle className="spin" size={14}/>{t('loading')}</p> : error ? <p role="alert">{error}</p> : matches.length ? matches.map(stock => <button key={stock.symbol} onClick={() => { setQuery(stock.symbol); setChosen(true) }}><strong>{stock.name}</strong><span>{stock.symbol}</span><small>{t('selectStock')} →</small></button>) : <p>{t('noStocks')}</p>}</div>}
    <div className="data-pills"><span><Activity size={13}/>{t('daily')}</span><span><ShieldCheck size={13}/>{t('positionFree')}</span><span><ListFilter size={13}/>{t('noReferencePrices')}</span></div>
    <div className="feature-grid">{([{ icon: Layers3, title: 'feature1', text: 'feature1Text', number: '01' }, { icon: ListFilter, title: 'feature2', text: 'feature2Text', number: '02' }, { icon: ShieldCheck, title: 'feature3', text: 'feature3Text', number: '03' }] as const).map(({ icon: Icon, title, text, number }) => <article className="feature-card" key={number}><div><span className="feature-icon"><Icon size={21}/></span><span className="feature-number">{number}</span></div><h3>{t(title)}</h3><p>{t(text)}</p></article>)}</div>
    <section className="setup-strip"><div><span className="provider-mark">J</span><div><strong>{settings?.jev_configured ? t('connected') : t('configureJev')}</strong><p>{settings?.jev_configured ? settings.model : t('keyHint')}</p></div></div><button className="button secondary" disabled={!settings} onClick={onConfigure}>{t('settings')}<ArrowRight size={15}/></button></section>
  </div>
}
