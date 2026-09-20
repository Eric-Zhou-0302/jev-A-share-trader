import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, LoaderCircle, Pause, Play, RotateCcw, ScanLine, Square, X } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Key } from './i18n'
import type { Job, Lang } from './types'
import { scanHref } from './routes'
import type { ScanView } from './routes'
import ReportLink from './ReportLink'

const activeStatuses = ['running', 'preparing', 'pausing', 'resetting']

export default function Scans({ lang, configured, viewState, onViewChange, onOpen, onConfigure, onReady }: { lang: Lang; configured: boolean; viewState: ScanView; onViewChange: (view: ScanView) => void; onOpen: (id: string, from: string) => void; onConfigure: () => void; onReady: () => void }) {
  const { selected, scope, filter, page } = viewState
  const [jobs, setJobs] = useState<Job[]>([])
  const [detail, setDetail] = useState<Job | null>(null)
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [loadedView, setLoadedView] = useState('')
  const viewKey = `${scope}:${selected ?? ''}`
  const [confirmReset, setConfirmReset] = useState(false)
  const resetDialog = useRef<HTMLDialogElement>(null)
  const revision = useRef(0)
  const t = (key: Key) => translate(lang, key)
  useEffect(() => { if (!loading && loadedView === viewKey) onReady() }, [loading, loadedView, viewKey, onReady])
  useEffect(() => { if (confirmReset) resetDialog.current?.showModal() }, [confirmReset])
  useEffect(() => {
    if (busy) return
    setLoading(true)
    let stopped = false
    let timer: number
    const controller = new AbortController()
    const current = revision.current
    const valid = () => !stopped && current === revision.current
    async function poll() {
      try {
        const items = await api<Job[]>('/jobs', lang, undefined, 'GET', controller.signal)
        if (!valid()) return
        const scoped = items.filter(job => job.scope === scope)
        const chosen = scoped.find(job => job.id === selected) ?? scoped[0]
        // 重置后的默认工作区保持空白，历史任务仍可显式打开。
        const id = chosen && (selected === chosen.id || chosen.status !== 'reset') ? chosen.id : null
        const job = id ? await api<Job>(`/jobs/${id}`, lang, undefined, 'GET', controller.signal) : null
        if (!valid()) return
        setJobs(items)
        setDetail(job?.scope === scope && (selected === job.id || job.status !== 'reset') ? job : null)
        setPollError('')
      } catch (value) { if (valid()) setPollError((value as Error).message) }
      if (valid()) { setLoadedView(viewKey); setLoading(false); timer = window.setTimeout(poll, 2000) }
    }
    void poll()
    return () => { stopped = true; controller.abort(); window.clearTimeout(timer) }
  }, [selected, scope, lang, busy, viewKey])

  function view(nextScope: ScanView['scope'], id: string | null = null) {
    // 切换视图时立即使旧请求失效，不能让其结果覆盖新范围。
    revision.current += 1
    setDetail(null); setLoading(true)
    onViewChange({ scope: nextScope, selected: id, filter: 'all', page: 0 })
    setError(''); setPollError(''); setConfirmReset(false)
  }
  function update(job: Job) {
    setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)])
  }
  async function start() {
    revision.current += 1
    setBusy(true); setError('')
    try {
      const job = await api<Job>('/jobs', lang, { scope })
      update(job); setDetail(job); onViewChange({ scope, selected: job.id, filter: 'all', page: 0 })
    } catch (value) { setError((value as Error).message) } finally { setBusy(false) }
  }
  async function control(operation: 'pause' | 'resume' | 'retry' | 'reset') {
    if (!detail) return
    revision.current += 1
    setBusy(true); setError(''); setConfirmReset(false)
    try {
      const job = await api<Job>(`/jobs/${detail.id}/${operation}`, lang, {})
      update(job)
      setDetail(job.status === 'reset' ? null : { ...detail, ...job })
      if (operation === 'reset') onViewChange({ scope, selected: null, filter: 'all', page: 0 })
    } catch (value) { setError((value as Error).message) } finally { setBusy(false) }
  }
  const scopedJobs = jobs.filter(job => job.scope === scope)
  const active = jobs.find(job => activeStatuses.includes(job.status))
  const shown = detail?.scope === scope && (!selected || detail.id === selected) ? detail : null
  const isActive = shown && activeStatuses.includes(shown.status)
  const isReset = shown?.status === 'reset' || shown?.status === 'resetting'
  const progress = shown ? (shown.phase === 'data' ? shown.downloaded : shown.completed + shown.skipped + shown.failed) / Math.max(shown.total, 1) * 100 : 0
  const filtered = shown?.items?.filter(item => filter === 'all' || item.status === filter) ?? []
  const pages = Math.max(1, Math.ceil(filtered.length / 100))
  const currentPage = Math.min(page, pages - 1)
  return <div className="scan-workspace"><div className="page-heading"><span className="eyebrow">MARKET RESEARCH</span><h1>{t('scans')}</h1><p>{t('scanHint')}</p></div>
    <section className="panel scan-launch"><div><label>{t('scope')}<select value={scope} disabled={busy} onChange={event => view(event.target.value as ScanView['scope'])}><option value="watchlist">{t('watchScope')}</option><option value="market">{t('fullMarket')}</option></select></label></div><button className="button primary" disabled={busy || loading || !!active} onClick={configured ? start : onConfigure}><ScanLine size={17}/>{configured ? t('startScan') : t('configureJev')}</button></section>
    {active && (active.scope !== scope || (shown && active.id !== shown.id)) && <div className="scan-active-note"><span>{t('otherScanActive')}</span><button className="text-button" disabled={busy} onClick={() => view(active.scope as ScanView['scope'], active.id)}>{t('viewActiveScan')} →</button></div>}
    {(error || pollError) && <div className="error-message" role="alert">{error || pollError}</div>}
    {shown ? <><section className="panel scan-status"><div className="panel-heading"><div><span className="eyebrow">{shown.as_of ?? '—'}</span><h3>{t('progress')} <span className="subtle-badge">{t(shown.status as Key) ?? shown.status}</span></h3></div><div className="heading-actions">
      {!isReset && <button className="button secondary" disabled={busy} onClick={() => setConfirmReset(true)}><Square size={14}/>{t('resetScan')}</button>}
      {isActive ? !isReset && <button className="button secondary" disabled={busy || shown.status === 'pausing'} onClick={() => control('pause')}><Pause size={14}/>{t('pause')}</button> : !isReset && <><button className="button secondary" disabled={busy || !!active || shown.failed === 0} onClick={() => control('retry')}><RotateCcw size={14}/>{t('retry')}</button>{(shown.remaining > 0 || shown.status === 'paused') && <button className="button primary" disabled={busy || !!active} onClick={() => control('resume')}><Play size={14}/>{t('resume')}</button>}</>}
    </div></div>
      <div className="progress-label"><span>{t(shown.phase === 'preparing' ? 'preparing' : shown.phase === 'data' ? 'dataProgress' : 'analysisProgress')}</span><strong>{progress.toFixed(0)}%</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }}/></div>
      <div className="scan-counters">{([['ready', shown.completed], ['failed', shown.failed], ['skipped', shown.skipped], ['pending', shown.remaining]] as const).map(([label, value]) => <div key={label}><span>{t(label)}</span><strong>{value.toLocaleString()}</strong></div>)}</div>
      {shown.error && <p className="error-message">{shown.error[lang]}</p>}{shown.status === 'pausing' && <p>{t('pauseHint')}</p>}{shown.status === 'resetting' && <p>{t('resetHint')}</p>}
    </section><section className="panel"><div className="panel-heading"><h3>{t('result')}</h3><select aria-label={t('filters')} value={filter} onChange={event => onViewChange({ ...viewState, filter: event.target.value, page: 0 })}>{['all', 'ready', 'failed', 'skipped', 'pending'].map(value => <option value={value} key={value}>{t(value as Key)}</option>)}</select></div><div className="table-scroll"><table><thead><tr><th>{t('stock')}</th><th>{t('result')}</th><th>{t('details')}</th></tr></thead><tbody>{filtered.slice(currentPage * 100, (currentPage + 1) * 100).map(item => <tr key={item.stock.symbol}><td><strong>{item.stock.name}</strong><small>{item.stock.symbol}</small></td><td>{item.action ? <span className={`action-badge ${item.action}`}>{t(item.action)}</span> : t(item.status as Key)}{item.horizon && <small>{item.horizon} {t('sessions')}</small>}</td><td>{item.analysis_id ? <ReportLink id={item.analysis_id} from={scanHref({ ...viewState, selected: shown.id, page: currentPage })} onOpen={() => onOpen(item.analysis_id!, scanHref({ ...viewState, selected: shown.id, page: currentPage }))}>{t('viewReport')} →</ReportLink> : item.error?.[lang] ?? '—'}</td></tr>)}</tbody></table></div><div className="pagination"><button className="button secondary" disabled={currentPage === 0} onClick={() => onViewChange({ ...viewState, page: currentPage - 1 })}>{lang === 'zh' ? '上一页' : 'Previous'}</button><span>{currentPage + 1} / {pages} · {filtered.length}</span><button className="button secondary" disabled={currentPage + 1 >= pages} onClick={() => onViewChange({ ...viewState, page: currentPage + 1 })}>{lang === 'zh' ? '下一页' : 'Next'}</button></div></section></> : <div className="empty-panel" role="status">{loading ? <LoaderCircle size={32} className="spin"/> : <ScanLine size={32}/>}<p>{t(loading ? 'loading' : scopedJobs[0]?.status === 'reset' ? 'scanResetEmpty' : 'noScans')}</p></div>}
    {scopedJobs.length > 0 && <section className="panel older-jobs"><h3>{t('scanHistory')}</h3>{scopedJobs.map(job => <button key={job.id} disabled={busy || shown?.id === job.id} className={shown?.id === job.id ? 'selected' : ''} onClick={() => view(scope, job.id)}>{job.status === 'completed' ? <CheckCircle2 size={16}/> : <ScanLine size={16}/>}<span>{job.as_of ?? '—'} · {job.scope === 'market' ? t('fullMarket') : t('watchScope')} · {job.id.slice(0, 8)}</span><small>{t(job.status as Key) ?? job.status}</small></button>)}</section>}
    {confirmReset && <dialog ref={resetDialog} className="settings-dialog reset-dialog" onCancel={() => setConfirmReset(false)} aria-labelledby="reset-title" aria-describedby="reset-description"><div className="dialog-heading"><h2 id="reset-title">{t('resetTitle')}</h2><button className="icon-button" aria-label={t('close')} onClick={() => setConfirmReset(false)}><X size={20}/></button></div><p id="reset-description">{t('resetDescription')}</p><div className="heading-actions"><button className="button secondary" autoFocus onClick={() => setConfirmReset(false)}>{t('cancel')}</button><button className="button primary" onClick={() => control('reset')}>{t('confirmReset')}</button></div></dialog>}
  </div>
}
