import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowRight, Archive, BarChart3, Check, ChevronRight, CircleHelp, Clock3, Globe2, Layers3, LoaderCircle, Plus, ScanLine, Search, Settings2, Star, X } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Analysis, Job, Lang, Settings, Stock, Summary } from './types'
import { analysisHref, historyHref, parseRoute, reportHref, scanHref, scanHistoryHref, scanTaskHref } from './routes'
import type { ScanScope } from './routes'
import { useNavigation } from './useNavigation'
import AnalysisEntry from './AnalysisEntry'
import History from './History'
import Report from './Report'
import SettingsDialog from './SettingsDialog'
import Scans from './Scans'
import ScanHistory from './ScanHistory'
import ScanTask from './ScanTask'

export default function App() {
  const [lang, setLang] = useState<Lang>(() => { try { return localStorage.getItem('jev-language-v1') === 'en' ? 'en' : 'zh' } catch { return 'zh' } })
  const navigation = useNavigation()
  const { route, navigate, onReady } = navigation
  const currentNavigation = useRef(navigation)
  currentNavigation.current = navigation
  const page = route.page
  const [settings, setSettings] = useState<Settings | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [watchlist, setWatchlist] = useState<Stock[]>([])
  const [history, setHistory] = useState<Summary[]>([])
  const [reportCache, setReportCache] = useState<Analysis | null>(null)
  const [viewedReport, setViewedReport] = useState<Analysis | null>(null)
  const [completedElsewhere, setCompletedElsewhere] = useState<Analysis | null>(null)
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState<Stock[]>([])
  const [searching, setSearching] = useState(false)
  const [busy, setBusy] = useState(false)
  const [scanStarting, setScanStarting] = useState(false)
  const [batchInput, setBatchInput] = useState('')
  const [createdScan, setCreatedScan] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const selectionRequest = useRef<AbortController | null>(null)
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  const source = route.page === 'report' || route.page === 'scanTask' ? parseRoute(route.from) : route
  const rootSource = source.page === 'scanTask' ? parseRoute(source.from) : source
  const activePage = rootSource.page === 'report' || rootSource.page === 'scanTask' ? 'scanHistory' : rootSource.page
  const loadedReport = route.page === 'report' && viewedReport?.id === route.id ? viewedReport : null
  const selectedSymbol = loadedReport?.symbol ?? (route.page === 'workbench' ? route.symbol : '')
  const latestDate = loadedReport?.as_of ?? history[0]?.as_of

  const reload = useCallback(async () => {
    const results = await Promise.allSettled([api<Settings>('/settings', lang), api<Stock[]>('/watchlist', lang), api<Summary[]>('/analyses', lang)])
    if (results[0].status === 'fulfilled') setSettings(results[0].value)
    else setError(results[0].reason.message)
    if (results[1].status === 'fulfilled') setWatchlist(results[1].value)
    if (results[2].status === 'fulfilled') setHistory(results[2].value)
  }, [lang])
  useEffect(() => { void reload() }, [reload])
  useEffect(() => { if (page === 'workbench') onReady() }, [page, onReady])
  useEffect(() => {
    document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en'
    const title = page === 'report' ? `${translate(lang, 'report')}${loadedReport ? ` · ${loadedReport.name}` : ''}` : translate(lang, page)
    document.title = `Jev · ${title}`
    try { localStorage.setItem('jev-language-v1', lang) } catch { /* 无持久化权限时仍允许语言切换。 */ }
  }, [lang, page, loadedReport])
  useEffect(() => () => selectionRequest.current?.abort(), [])
  useEffect(() => {
    const controller = new AbortController()
    if (query.trim().length < 2) { setMatches([]); setSearching(false); return }
    setSearching(true)
    const timer = window.setTimeout(async () => {
      try {
        const response = await api<{ items: Stock[] }>(`/stocks?q=${encodeURIComponent(query.trim())}`, lang, undefined, 'GET', controller.signal)
        if (!controller.signal.aborted) setMatches(response.items)
      } catch (value) { if (!controller.signal.aborted) setError((value as Error).message) }
      finally { if (!controller.signal.aborted) setSearching(false) }
    }, 350)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, lang, settings?.provider])

  function go(hash: string) {
    selectionRequest.current?.abort()
    setError(''); setCompletedElsewhere(null); navigate(hash)
  }
  function open(id: string, from = navigation.hash, returnScroll = window.scrollY) {
    setError(''); setCompletedElsewhere(null)
    if (parseRoute(from).page === route.page && (route.page === 'scanTask' || route.page === 'history')) {
      navigate(from, { replace: true, scroll: returnScroll })
    }
    navigate(reportHref(id, from), { returnScroll })
  }
  function openTask(id: string, from: string) {
    setError(''); setCreatedScan(null)
    const samePage = parseRoute(from).page === route.page
    const returnScroll = samePage ? window.scrollY : navigation.state.positions?.[from] ?? navigation.state.returnScroll
    if (samePage) navigate(from, { replace: true, scroll: returnScroll })
    navigate(scanTaskHref(id, undefined, from), { returnScroll })
  }
  async function startScan(scope: ScanScope, symbols?: string[]) {
    if (scanStarting) return
    const started = navigation.state.key
    const from = scanHref({ scope })
    const returnScroll = window.scrollY
    setScanStarting(true); setError(''); setCreatedScan(null)
    try {
      const job = await api<Job>('/jobs', lang, { scope, symbols })
      if (currentNavigation.current.state.key === started) navigate(scanTaskHref(job.id, undefined, from), { returnScroll })
      else setCreatedScan(job)
    } catch (value) { setError((value as Error).message) }
    finally { setScanStarting(false) }
  }
  async function analyze(code: string) {
    if (!code.trim() || busy) return
    const started = navigation.state.key
    const origin = route.page === 'report' ? route.from : analysisHref(code)
    const returnScroll = route.page === 'report' ? navigation.state.returnScroll : window.scrollY
    setBusy(true); setError(''); setCompletedElsewhere(null)
    try {
      const data = await api<Analysis>('/analyze', lang, { symbol: code.trim() })
      setReportCache(data)
      await reload()
      if (currentNavigation.current.state.key === started) open(data.id, origin, returnScroll)
      else setCompletedElsewhere(data)
    } catch (value) { setError((value as Error).message) }
    finally { setBusy(false) }
  }
  async function select(stock: Stock) {
    selectionRequest.current?.abort()
    const controller = new AbortController()
    selectionRequest.current = controller
    const started = navigation.state.key
    setQuery(''); setError('')
    try {
      const saved = await api<Summary[]>(`/analyses?symbol=${encodeURIComponent(stock.symbol)}`, lang, undefined, 'GET', controller.signal)
      if (controller.signal.aborted || currentNavigation.current.state.key !== started) return
      const origin = analysisHref(stock.symbol)
      if (saved[0]) open(saved[0].id, origin, 0)
      else go(origin)
    } catch (value) { if (!controller.signal.aborted) setError((value as Error).message) }
  }
  async function watch(stock: Stock, remove = false) {
    setError('')
    try {
      setWatchlist(await api<Stock[]>(remove ? `/watchlist/${stock.symbol}` : '/watchlist', lang, remove ? undefined : { symbol: stock.symbol }, remove ? 'DELETE' : 'POST'))
    } catch (value) { setError((value as Error).message) }
  }
  const icons = { workbench: BarChart3, scans: ScanLine, history: Clock3, scanHistory: Archive }
  const returnLabel = t(source.page === 'scanTask' ? 'backToScanTask' : source.page === 'scans' ? 'backToScans' : source.page === 'scanHistory' ? 'backToScanHistory' : source.page === 'history' ? 'backToHistory' : 'backToAnalysis')
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" onClick={event => { event.preventDefault(); go(analysisHref()) }} aria-label="Jev home"><span className="brand-symbol"><span/><span/><span/></span><span className="brand-word">jev<span className="brand-dot">.</span><small>A-SHARE TRADER</small></span></a>
      <nav className="main-nav" aria-label={lang === 'zh' ? '主导航' : 'Main navigation'}>{(['workbench', 'scans', 'history', 'scanHistory'] as const).map(item => { const Icon = icons[item]; return <button aria-label={t(item)} className={activePage === item ? 'active' : ''} key={item} onClick={() => go(item === 'workbench' ? analysisHref() : item === 'scanHistory' ? scanHistoryHref() : `#/${item}`)}><Icon size={18}/><span>{t(item)}</span>{activePage === item && <span className="nav-dot"/>}</button> })}</nav>
      <div className="watch-heading"><span>{t('watchlist')}</span><span>{watchlist.length.toString().padStart(2, '0')}</span></div>
      <div className="stock-search"><Search size={15}/><input aria-label={t('searchPlaceholder')} placeholder={t('searchPlaceholder')} value={query} onChange={event => setQuery(event.target.value)}/>{searching && <LoaderCircle size={14} className="spin"/>}</div>
      {query.trim().length >= 2 && <div className="search-results">{!searching && matches.length === 0 && <p className="search-empty">{lang === 'zh' ? '未找到匹配股票' : 'No matching stocks'}</p>}{matches.map(stock => <div key={stock.symbol}><button onClick={() => select(stock)}><strong>{stock.name}</strong><small>{stock.symbol}</small></button><button className="icon-button" aria-label={`${t('addWatch')} ${stock.name}`} onClick={() => watch(stock)}>{watchlist.some(item => item.symbol === stock.symbol) ? <Check size={15}/> : <Plus size={15}/>}</button></div>)}</div>}
      <div className="watch-items">{watchlist.length ? watchlist.map(stock => { const summary = history.find(item => item.symbol === stock.symbol); return <div className={`watch-item ${selectedSymbol === stock.symbol ? 'selected' : ''}`} key={stock.symbol}><button className="watch-select" onClick={() => select(stock)}><span className="stock-avatar">{stock.name.slice(0, 1)}</span><span><strong>{stock.name}</strong><small>{stock.symbol}</small></span>{summary?.action && <span className={`watch-signal ${summary.action}`} title={t(summary.action)}/>}</button><button className="remove-watch" aria-label={`${t('remove')} ${stock.name}`} onClick={() => watch(stock, true)}><X size={13}/></button></div>}) : <div className="empty-watch"><Star size={23}/><p>{t('emptyWatch')}</p><small>{t('emptyWatchHint')}</small></div>}</div>
      {watchlist.length > 0 && <button className="watch-batch" onClick={() => go('#/scans?scope=watchlist')}><Layers3 size={15}/>{t('batch')}<ArrowRight size={14}/></button>}
      <div className="sidebar-bottom"><span className="local-indicator"><i/>{t('local')}</span><button onClick={() => setSettingsOpen(true)} disabled={!settings}><Settings2 size={17}/>{t('settings')}</button><p>JEV RESEARCH WORKSPACE<span>v0.1.1</span></p></div>
    </aside>
    <div className="main-shell"><header className="topbar"><div className="breadcrumb"><span>WORKSPACE</span><ChevronRight size={13}/>{route.page === 'report' || route.page === 'scanTask' ? <><button onClick={() => navigate(route.from, { scroll: navigation.state.returnScroll })}>{t(source.page)}</button><ChevronRight size={13}/><strong>{route.page === 'scanTask' ? `${t('scanTask')} · ${route.id.slice(0, 8)}` : loadedReport?.name ?? t('report')}</strong></> : <strong>{t(page)}</strong>}</div><div className="topbar-actions"><span className="model-status"><i className={settings?.jev_configured ? 'online' : ''}/><span>Jev</span><small>{settings?.jev_configured ? t('connected') : t('notConfigured')}</small></span><button className="language-button" onClick={() => setLang(lang === 'zh' ? 'en' : 'zh')} aria-label={lang === 'zh' ? 'Switch to English' : '切换为中文'}><Globe2 size={15}/>{lang === 'zh' ? 'EN' : '中文'}</button><button className="icon-button" aria-label={t('settings')} onClick={() => setSettingsOpen(true)} disabled={!settings}><Settings2 size={18}/></button></div></header>
      <main className="main-content">
        {error && <div className="error-banner" role="alert"><CircleHelp size={18}/><span>{error}</span><button className="icon-button" aria-label={t('close')} onClick={() => setError('')}><X size={16}/></button></div>}
        {busy && <div className="analysis-loading" role="status"><LoaderCircle size={18} className="spin"/><span>{t('analyzing')}</span><small>{t('completedOnly')}</small></div>}
        {completedElsewhere && <div className="analysis-loading" role="status"><span>{t('analysisFinished')} · {completedElsewhere.name}</span><button className="text-button" onClick={() => open(completedElsewhere.id, analysisHref(completedElsewhere.symbol), 0)}>{t('viewReport')} →</button></div>}
        {route.page === 'workbench' && <AnalysisEntry key={route.symbol} lang={lang} initialSymbol={route.symbol} settings={settings} busy={busy} onAnalyze={analyze} onConfigure={() => setSettingsOpen(true)}/>}
        {route.page === 'report' && <Report key={route.id} id={route.id} lang={lang} initial={reportCache} busy={busy} returnLabel={returnLabel} onBack={() => navigate(route.from, { scroll: navigation.state.returnScroll })} onAnalyze={analyze} onConfigure={() => setSettingsOpen(true)} onLoaded={setViewedReport} onReady={onReady}/>}
        {createdScan && <div className="analysis-loading" role="status"><span>{t('scanStarted')}</span><button className="text-button" onClick={() => openTask(createdScan.id, scanHref({ scope: createdScan.scope as ScanScope }))}>{t('viewScanTask')} →</button></div>}
        {route.page === 'scans' && <Scans lang={lang} configured={settings?.jev_configured ?? false} busy={scanStarting} view={route.view} input={batchInput} onInput={setBatchInput} watchlist={watchlist} onChange={view => navigate(scanHref(view), { replace: true, scroll: window.scrollY })} onStart={symbols => startScan(route.view.scope, symbols)} onTask={openTask} onConfigure={() => setSettingsOpen(true)} onReady={onReady}/>}
        {route.page === 'scanHistory' && <ScanHistory lang={lang} view={route.view} onChange={view => navigate(scanHistoryHref(view), { replace: true, scroll: window.scrollY })} onTask={openTask} onReady={onReady}/>}
        {route.page === 'scanTask' && <ScanTask key={route.id} id={route.id} from={route.from} lang={lang} view={route.view} returnLabel={returnLabel} onBack={() => navigate(route.from, { scroll: navigation.state.returnScroll })} onChange={view => navigate(scanTaskHref(route.id, view, route.from), { replace: true, scroll: window.scrollY, returnScroll: navigation.state.returnScroll })} onOpen={open} onTask={openTask} onReady={onReady}/>}
        {route.page === 'history' && <History lang={lang} view={route.view} onChange={view => navigate(historyHref(view), { replace: true, scroll: window.scrollY })} onOpen={open} onReady={onReady} onChanged={() => { setReportCache(null); setCompletedElsewhere(null); void reload() }}/>}
      </main><footer className="footer"><span><i/>{t('localResearch')}</span><span>{latestDate ? `${t('asOf')} ${latestDate}` : t('noDataService')}</span></footer><div className="chart-attribution">TradingView Lightweight Charts™ · Copyright (с) 2025 <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView, Inc.</a></div>
    </div>{settingsOpen && settings && <SettingsDialog settings={settings} lang={lang} onClose={() => setSettingsOpen(false)} onSaved={updated => { if (updated.provider !== settings.provider) { setMatches([]); setError('') }; setSettings(updated) }}/>}
  </div>
}
