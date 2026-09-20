import { lazy, Suspense, useCallback, useEffect, useState } from 'react'
import { Activity, ArrowRight, ArrowUpRight, BarChart3, Check, ChevronRight, CircleHelp, Clock3, Globe2, Layers3, ListFilter, LoaderCircle, Plus, ScanLine, Search, Settings2, ShieldCheck, Star, X } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Analysis, Lang, Settings, Stock, Summary } from './types'
import SettingsDialog from './SettingsDialog'
import Scans from './Scans'

const Result = lazy(() => import('./Result'))

export default function App() {
  const [lang, setLang] = useState<Lang>(() => { try { return localStorage.getItem('jev-language-v1') === 'en' ? 'en' : 'zh' } catch { return 'zh' } })
  const [page, setPage] = useState<'workbench' | 'scans' | 'history'>('workbench')
  const [settings, setSettings] = useState<Settings | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [watchlist, setWatchlist] = useState<Stock[]>([])
  const [history, setHistory] = useState<Summary[]>([])
  const [result, setResult] = useState<Analysis | null>(null)
  const [symbol, setSymbol] = useState('')
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<Stock[]>([])
  const [searching, setSearching] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)

  const reload = useCallback(async () => {
    const results = await Promise.allSettled([api<Settings>('/settings', lang), api<Stock[]>('/watchlist', lang), api<Summary[]>('/analyses', lang)])
    if (results[0].status === 'fulfilled') setSettings(results[0].value)
    else setError(results[0].reason.message)
    if (results[1].status === 'fulfilled') setWatchlist(results[1].value)
    if (results[2].status === 'fulfilled') setHistory(results[2].value)
  }, [lang])
  useEffect(() => { void reload() }, [reload])
  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
    document.title = lang === 'zh' ? 'Jev · A 股技术分析' : 'Jev · A-share analysis'
    try { localStorage.setItem('jev-language-v1', lang) } catch { /* 无持久化权限时仍允许语言切换。 */ }
  }, [lang])
  useEffect(() => {
    const controller = new AbortController()
    if (query.trim().length < 2) { setMatches([]); setSearching(false); return }
    setSearching(true)
    const timer = window.setTimeout(async () => {
      try {
        const response = await api<{ items: Stock[] }>(`/stocks?q=${encodeURIComponent(query.trim())}`, lang, undefined, 'GET', controller.signal)
        setMatches(response.items)
      } catch (value) { if (!controller.signal.aborted) setError((value as Error).message) }
      finally { if (!controller.signal.aborted) setSearching(false) }
    }, 350)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, lang, settings?.provider])

  async function analyze(code = symbol) {
    if (!code.trim() || busy) return
    setBusy(true); setError(''); setPage('workbench')
    try { const data = await api<Analysis>('/analyze', lang, { symbol: code.trim() }); setResult(data); setSymbol(data.symbol); await reload() }
    catch (value) { setError((value as Error).message) }
    finally { setBusy(false) }
  }
  async function open(id: string) {
    setError('')
    try { const data = await api<Analysis>(`/analyses/${id}`, lang); setResult(data); setSymbol(data.symbol); setPage('workbench') }
    catch (value) { setError((value as Error).message) }
  }
  async function select(stock: Stock) {
    setSymbol(stock.symbol); setQuery(''); setPage('workbench'); setError('')
    const latest = history.find(item => item.symbol === stock.symbol)
    if (latest) await open(latest.id)
    else setResult(null)
  }
  async function watch(stock: Stock, remove = false) {
    setError('')
    try {
      setWatchlist(await api<Stock[]>(remove ? `/watchlist/${stock.symbol}` : '/watchlist', lang, remove ? undefined : { symbol: stock.symbol }, remove ? 'DELETE' : 'POST'))
    } catch (value) { setError((value as Error).message) }
  }
  const icons = { workbench: BarChart3, scans: ScanLine, history: Clock3 }
  const latestDate = result?.as_of ?? history[0]?.as_of
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={event => { event.preventDefault(); setPage('workbench') }} aria-label="Jev home"><span className="brand-symbol"><span/><span/><span/></span><span className="brand-word">jev<span className="brand-dot">.</span><small>A-SHARE TRADER</small></span></a>
      <nav className="main-nav" aria-label={lang === 'zh' ? '主导航' : 'Main navigation'}>{(['workbench', 'scans', 'history'] as const).map(item => { const Icon = icons[item]; return <button aria-label={t(item)} className={page === item ? 'active' : ''} key={item} onClick={() => { setPage(item); if (item === 'history') void reload() }}><Icon size={18}/><span>{t(item)}</span>{page === item && <span className="nav-dot"/>}</button> })}</nav>
      <div className="watch-heading"><span>{t('watchlist')}</span><span>{watchlist.length.toString().padStart(2, '0')}</span></div>
      <div className="stock-search"><Search size={15}/><input aria-label={t('searchPlaceholder')} placeholder={t('searchPlaceholder')} value={query} onChange={event => setQuery(event.target.value)}/>{searching && <LoaderCircle size={14} className="spin"/>}</div>
      {query.trim().length >= 2 && <div className="search-results">{!searching && matches.length === 0 && <p className="search-empty">{lang === 'zh' ? '未找到匹配股票' : 'No matching stocks'}</p>}{matches.map(stock => <div key={stock.symbol}><button onClick={() => select(stock)}><strong>{stock.name}</strong><small>{stock.symbol}</small></button><button className="icon-button" aria-label={`${t('addWatch')} ${stock.name}`} onClick={() => watch(stock)}>{watchlist.some(item => item.symbol === stock.symbol) ? <Check size={15}/> : <Plus size={15}/>}</button></div>)}</div>}
      <div className="watch-items">{watchlist.length ? watchlist.map(stock => { const summary = history.find(item => item.symbol === stock.symbol); return <div className={`watch-item ${symbol === stock.symbol ? 'selected' : ''}`} key={stock.symbol}><button className="watch-select" onClick={() => select(stock)}><span className="stock-avatar">{stock.name.slice(0, 1)}</span><span><strong>{stock.name}</strong><small>{stock.symbol}</small></span>{summary?.action && <span className={`watch-signal ${summary.action}`} title={t(summary.action)}/>}</button><button className="remove-watch" aria-label={`${t('remove')} ${stock.name}`} onClick={() => watch(stock, true)}><X size={13}/></button></div>}) : <div className="empty-watch"><Star size={23}/><p>{t('emptyWatch')}</p><small>{t('emptyWatchHint')}</small></div>}</div>
      {watchlist.length > 0 && <button className="watch-batch" onClick={() => setPage('scans')}><Layers3 size={15}/>{t('batch')}<ArrowRight size={14}/></button>}
      <div className="sidebar-bottom"><span className="local-indicator"><i/>{t('local')}</span><button onClick={() => setSettingsOpen(true)} disabled={!settings}><Settings2 size={17}/>{t('settings')}</button><p>JEV RESEARCH WORKSPACE<span>v0.1.1</span></p></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><span>WORKSPACE</span><ChevronRight size={13}/><strong>{t(page)}</strong></div><div className="topbar-actions"><span className="model-status"><i className={settings?.jev_configured ? 'online' : ''}/><span>Jev</span><small>{settings?.jev_configured ? t('connected') : t('notConfigured')}</small></span><button className="language-button" onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')} aria-label={lang === 'zh' ? 'Switch to English' : '切换为中文'}><Globe2 size={15}/>{lang === 'zh' ? 'EN' : '中文'}</button><button className="icon-button" aria-label={t('settings')} onClick={() => setSettingsOpen(true)} disabled={!settings}><Settings2 size={18}/></button></div></header>
      <main className="main-content">
        {error && <div className="error-banner" role="alert"><CircleHelp size={18}/><span>{error}</span><button className="icon-button" aria-label={t('close')} onClick={() => setError('')}><X size={16}/></button></div>}
        {busy && <div className="analysis-loading" role="status"><LoaderCircle size={18} className="spin"/><span>{t('analyzing')}</span><small>{t('completedOnly')}</small></div>}
        {page === 'workbench' && result && <form className="analysis-form compact-analysis" onSubmit={event => { event.preventDefault(); void analyze() }}><Search size={17}/><input required aria-label={t('enterSymbol')} placeholder={t('enterSymbol')} value={symbol} onChange={event => setSymbol(event.target.value)} maxLength={12}/><button className="button primary" disabled={busy} type="submit">{t('analyze')}<ArrowUpRight size={15}/></button></form>}
        {page === 'workbench' && (result ? <Suspense fallback={<div className="empty-panel">{t('loading')}</div>}><Result key={result.id} result={result} lang={lang} busy={busy} onRefresh={() => analyze(result.symbol)} onConfigure={() => setSettingsOpen(true)}/></Suspense> : <div className="welcome-workspace"><div className="welcome-eyebrow"><span/> AFTER THE CLOSE</div><h1>{t('emptyTitle')}</h1><p className="welcome-description">{t('emptyDescription')}</p>
          <form className="analysis-form" onSubmit={event => { event.preventDefault(); void analyze() }}><Search size={19}/><input required aria-label={t('enterSymbol')} placeholder={t('enterSymbol')} value={symbol} onChange={event => setSymbol(event.target.value)} autoComplete="off" maxLength={12}/><button className="button primary" disabled={busy || !symbol.trim()} type="submit">{t('startAnalysis')}<ArrowUpRight size={17}/></button></form>
          <div className="data-pills"><span><Activity size={13}/>{t('daily')}</span><span><ShieldCheck size={13}/>{t('positionFree')}</span><span><ListFilter size={13}/>{t('noReferencePrices')}</span></div>
          <div className="feature-grid">{([{ icon: Layers3, title: 'feature1', text: 'feature1Text', number: '01' }, { icon: FileEvidence, title: 'feature2', text: 'feature2Text', number: '02' }, { icon: ShieldCheck, title: 'feature3', text: 'feature3Text', number: '03' }] as const).map(({ icon: Icon, title, text, number }) => <article className="feature-card" key={number}><div><span className="feature-icon"><Icon size={21}/></span><span className="feature-number">{number}</span></div><h3>{t(title)}</h3><p>{t(text)}</p></article>)}</div>
          <section className="setup-strip"><div><span className="provider-mark">J</span><div><strong>{settings?.jev_configured ? t('connected') : t('configureJev')}</strong><p>{settings?.jev_configured ? settings.model : t('keyHint')}</p></div></div><button className="button secondary" disabled={!settings} onClick={() => setSettingsOpen(true)}>{t('settings')}<ArrowRight size={15}/></button></section>
        </div>)}
        {page === 'scans' && <Scans lang={lang} configured={settings?.jev_configured ?? false} onOpen={open} onConfigure={() => setSettingsOpen(true)}/>}
        {page === 'history' && <div className="history-workspace"><div className="page-heading"><span className="eyebrow">RESEARCH ARCHIVE</span><h1>{t('history')}</h1><p>{t('reportLanguage')}</p></div>{history.length ? <section className="panel"><div className="table-scroll"><table><thead><tr><th>{t('watchlist')}</th><th>{t('asOf')}</th><th>{t('decision')}</th><th>{t('horizon')}</th><th/></tr></thead><tbody>{history.map(item => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.symbol}</small></td><td>{item.as_of}</td><td><span className={`action-badge ${item.action ?? ''}`}>{item.action ? t(item.action) : t('noDecision')}</span></td><td>{item.horizon ? `${item.horizon} ${t('sessions')}` : '—'}</td><td><button className="text-button" onClick={() => open(item.id)}>{t('open')} →</button></td></tr>)}</tbody></table></div></section> : <div className="empty-panel"><Clock3 size={30}/><p>{t('noHistory')}</p></div>}</div>}
      </main><footer className="footer"><span><i/>{t('localResearch')}</span><span>{latestDate ? `${t('asOf')} ${latestDate}` : t('noDataService')}</span></footer><div className="chart-attribution">TradingView Lightweight Charts™ · Copyright (с) 2025 <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView, Inc.</a></div>
    </div>{settingsOpen && settings && <SettingsDialog settings={settings} lang={lang} onClose={() => setSettingsOpen(false)} onSaved={updated => { if (updated.provider !== settings.provider) { setResult(null); setMatches([]); setError('') }; setSettings(updated) }}/>}
  </div>
}

function FileEvidence({ size }: { size: number }) { return <ListFilter size={size}/> }
