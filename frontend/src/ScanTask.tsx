import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, LoaderCircle, Pause, Play, RotateCcw, ScanLine, Square, X } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Key } from './i18n'
import type { Job, Lang } from './types'
import { scanTaskHref } from './routes'
import type { ScanTaskView } from './routes'
import { activeStatuses, jobProgress } from './scanState'
import ReportLink from './ReportLink'
import NavigationLink from './NavigationLink'

export default function ScanTask({ id, from, lang, view, returnLabel, onBack, onChange, onOpen, onTask, onReady }: {
  id: string; from: string; lang: Lang; view: ScanTaskView; returnLabel: string; onBack: () => void;
  onChange: (view: ScanTaskView) => void; onOpen: (id: string, from: string) => void;
  onTask: (id: string, from: string) => void; onReady: () => void;
}) {
  const [detail, setDetail] = useState<Job | null>(null)
  const [jobs, setJobs] = useState<Job[]>([])
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [confirmStop, setConfirmStop] = useState(false)
  const stopDialog = useRef<HTMLDialogElement>(null)
  const cancelStopButton = useRef<HTMLButtonElement>(null)
  const mounted = useRef(true)
  const revision = useRef(0)
  const t = (key: Key) => translate(lang, key)
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  useEffect(() => { if (confirmStop) { stopDialog.current?.showModal(); cancelStopButton.current?.focus() } }, [confirmStop])
  useEffect(() => { if (!loading) onReady() }, [loading, onReady])
  useEffect(() => {
    if (busy) return
    const controller = new AbortController()
    const current = revision.current
    let timer: number
    async function poll() {
      const [saved, list] = await Promise.allSettled([
        api<Job>(`/jobs/${encodeURIComponent(id)}`, lang, undefined, 'GET', controller.signal),
        api<Job[]>('/jobs', lang, undefined, 'GET', controller.signal),
      ])
      if (controller.signal.aborted || current !== revision.current) return
      if (saved.status === 'fulfilled') setDetail(saved.value)
      if (list.status === 'fulfilled') setJobs(list.value)
      setPollError(saved.status === 'rejected' ? saved.reason.message : list.status === 'rejected' ? list.reason.message : '')
      setLoading(false)
      timer = window.setTimeout(poll, 2000)
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [id, lang, busy])

  async function control(operation: 'pause' | 'resume' | 'retry' | 'stop') {
    if (!detail || busy) return
    revision.current += 1
    setBusy(true); setError(''); setConfirmStop(false)
    try {
      const job = await api<Job>(`/jobs/${id}/${operation}`, lang, {})
      if (mounted.current) {
        setJobs(previous => [job, ...previous.filter(item => item.id !== job.id)])
        setDetail(previous => previous ? { ...previous, ...job } : job)
      }
    } catch (value) { if (mounted.current) setError((value as Error).message) }
    finally { if (mounted.current) setBusy(false) }
  }
  const active = jobs.find(job => activeStatuses.includes(job.status))
  const isActive = detail && activeStatuses.includes(detail.status)
  const isStopped = detail?.status === 'stopped' || detail?.status === 'stopping'
  const filtered = detail?.items?.filter(item => view.filter === 'all' || item.status === view.filter) ?? []
  const pages = Math.max(1, Math.ceil(filtered.length / 100))
  const currentPage = Math.min(view.page, pages - 1)
  const reportSource = scanTaskHref(id, { ...view, page: currentPage }, from)
  return <div className="scan-task-page">
    <div className="report-context"><button className="text-button" onClick={onBack}><ArrowLeft size={15}/>{returnLabel}</button><span><ScanLine size={14}/>{t('scanTask')}</span></div>
    <div className="page-heading scan-task-heading"><span className="eyebrow">{t('scanId')} {id}</span><h1>{t('scanTask')}</h1>{detail && <p>{detail.scope === 'market' ? t('fullMarket') : t('watchScope')} · {t('asOf')} {detail.as_of ?? '—'}{detail.created && <> · {t('reportCreated')} {new Date(detail.created * 1000).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { timeZone: 'Asia/Shanghai', hour12: false })} · {t('beijingTime')}</>}</p>}</div>
    {(error || pollError) && <div className="error-message" role="alert">{error || pollError}</div>}
    {active && active.id !== id && <div className="scan-active-note"><span>{t('otherScanActive')}</span><NavigationLink href={scanTaskHref(active.id, undefined, from)} onOpen={() => onTask(active.id, from)}>{t('viewActiveScan')} →</NavigationLink></div>}
    {loading ? <div className="empty-panel" role="status"><LoaderCircle size={30} className="spin"/><p>{t('loading')}</p></div> : detail && <>
      <section className="panel scan-status"><div className="panel-heading"><div><span className="eyebrow">{detail.as_of ?? '—'}</span><h3>{t('progress')} <span className="subtle-badge">{t(detail.status as Key) ?? detail.status}</span></h3></div><div className="heading-actions">
        {detail.status !== 'completed' && detail.status !== 'partial' && detail.status !== 'failed' && !isStopped && <button className="button secondary" disabled={busy} onClick={() => setConfirmStop(true)}><Square size={14}/>{t('stopScan')}</button>}
        {isActive ? !isStopped && <button className="button secondary" disabled={busy || detail.status === 'pausing'} onClick={() => control('pause')}><Pause size={14}/>{t('pause')}</button> : !isStopped && detail.status !== 'completed' && <><button className="button secondary" disabled={busy || !!active || !!pollError || detail.failed === 0} onClick={() => control('retry')}><RotateCcw size={14}/>{t('retry')}</button>{(detail.remaining > 0 || detail.status === 'paused') && <button className="button primary" disabled={busy || !!active || !!pollError} onClick={() => control('resume')}><Play size={14}/>{t('resume')}</button>}</>}
      </div></div><div className="progress-label"><span>{t(detail.phase === 'preparing' ? 'preparing' : detail.phase === 'data' ? 'dataProgress' : 'analysisProgress')}</span><strong>{jobProgress(detail).toFixed(0)}%</strong></div><div className="progress-track"><span style={{ width: `${jobProgress(detail)}%` }}/></div>
        <div className="scan-counters">{([['ready', detail.completed], ['failed', detail.failed], ['skipped', detail.skipped], ['pending', detail.remaining]] as const).map(([label, value]) => <div key={label}><span>{t(label)}</span><strong>{value.toLocaleString()}</strong></div>)}</div>
        {detail.error && <p className="error-message">{detail.error[lang]}</p>}{detail.status === 'pausing' && <p>{t('pauseHint')}</p>}{detail.status === 'stopping' && <p>{t('stopHint')}</p>}{detail.status === 'stopped' && <p>{t('scanStoppedDetail')}</p>}
      </section>
      <section className="panel"><div className="panel-heading"><h3>{t('result')}</h3><select aria-label={t('filters')} value={view.filter} onChange={event => onChange({ filter: event.target.value, page: 0 })}>{['all', 'ready', 'failed', 'skipped', 'pending'].map(value => <option value={value} key={value}>{t(value as Key)}</option>)}</select></div><div className="table-scroll"><table><thead><tr><th>{t('stock')}</th><th>{t('result')}</th><th>{t('details')}</th></tr></thead><tbody>{filtered.slice(currentPage * 100, (currentPage + 1) * 100).map(item => <tr key={item.stock.symbol}><td><strong>{item.stock.name}</strong><small>{item.stock.symbol}</small></td><td>{item.action ? <span className={`action-badge ${item.action}`}>{t(item.action)}</span> : t(item.status as Key)}{item.horizon && <small>{item.horizon} {t('sessions')}</small>}</td><td>{item.analysis_id ? <ReportLink id={item.analysis_id} from={reportSource} onOpen={() => onOpen(item.analysis_id!, reportSource)}>{t('viewReport')} →</ReportLink> : item.analysis_deleted ? t('reportDeleted') : item.error?.[lang] ?? '—'}</td></tr>)}</tbody></table>{!filtered.length && <p className="scan-empty-results">{t('noScanResults')}</p>}</div><div className="pagination"><button className="button secondary" disabled={currentPage === 0} onClick={() => onChange({ ...view, page: currentPage - 1 })}>{t('previousPage')}</button><span>{currentPage + 1} / {pages} · {filtered.length}</span><button className="button secondary" disabled={currentPage + 1 >= pages} onClick={() => onChange({ ...view, page: currentPage + 1 })}>{t('nextPage')}</button></div></section>
    </>}
    {confirmStop && <dialog ref={stopDialog} className="settings-dialog stop-dialog" onCancel={() => setConfirmStop(false)} aria-labelledby="stop-title" aria-describedby="stop-description"><div className="dialog-heading"><h2 id="stop-title">{t('stopTitle')}</h2><button className="icon-button" aria-label={t('close')} onClick={() => setConfirmStop(false)}><X size={20}/></button></div><p id="stop-description">{t('stopDescription')}</p><div className="heading-actions"><button className="button secondary" ref={cancelStopButton} autoFocus onClick={() => setConfirmStop(false)}>{t('cancel')}</button><button className="button primary" onClick={() => control('stop')}>{t('confirmStop')}</button></div></dialog>}
  </div>
}
