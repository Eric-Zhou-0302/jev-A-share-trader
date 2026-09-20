import { useEffect, useState } from 'react'
import { CheckCircle2, LoaderCircle, Pause, Play, RotateCcw, ScanLine } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Key } from './i18n'
import type { Job, Lang } from './types'

export default function Scans({ lang, configured, onOpen, onConfigure }: { lang: Lang; configured: boolean; onOpen: (id: string) => void; onConfigure: () => void }) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [detail, setDetail] = useState<Job | null>(null)
  const [scope, setScope] = useState('watchlist')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [filter, setFilter] = useState('all')
  const [page, setPage] = useState(0)
  useEffect(() => setPage(0), [filter, selected])
  const t = (key: Key) => translate(lang, key)
  useEffect(() => {
    let stopped = false
    let timer: number
    const controller = new AbortController()
    async function poll() {
      try {
        const items = await api<Job[]>('/jobs', lang, undefined, 'GET', controller.signal)
        if (stopped) return
        setJobs(items)
        const id = selected ?? items[0]?.id
        if (id) {
          const job = await api<Job>(`/jobs/${id}`, lang, undefined, 'GET', controller.signal)
          if (!stopped) setDetail(job)
        }
      } catch (value) { if (!stopped) setError((value as Error).message) }
      if (!stopped) timer = window.setTimeout(poll, 2000)
    }
    void poll()
    return () => { stopped = true; controller.abort(); window.clearTimeout(timer) }
  }, [selected, lang])
  async function start() {
    setBusy(true); setError('')
    try { const job = await api<Job>('/jobs', lang, { scope }); setSelected(job.id); setDetail(job) }
    catch (value) { setError((value as Error).message) } finally { setBusy(false) }
  }
  async function control(operation: string) {
    if (!detail) return
    setBusy(true); setError('')
    try { await api(`/jobs/${detail.id}/${operation}`, lang, {}); setDetail(await api<Job>(`/jobs/${detail.id}`, lang)) }
    catch (value) { setError((value as Error).message) } finally { setBusy(false) }
  }
  const active = jobs.some(job => ['running', 'preparing', 'pausing'].includes(job.status))
  const progress = detail ? (detail.phase === 'data' ? detail.downloaded : detail.completed + detail.skipped + detail.failed) / Math.max(detail.total, 1) * 100 : 0
  const filtered = detail?.items?.filter(item => filter === 'all' || item.status === filter) ?? []
  const pages = Math.max(1, Math.ceil(filtered.length / 100))
  const currentPage = Math.min(page, pages - 1)
  return <div className="scan-workspace"><div className="page-heading"><span className="eyebrow">MARKET RESEARCH</span><h1>{t('scans')}</h1><p>{t('scanHint')}</p></div>
    <section className="panel scan-launch"><div><label>{t('scope')}<select value={scope} onChange={event => setScope(event.target.value)}><option value="watchlist">{t('watchScope')}</option><option value="market">{t('fullMarket')}</option></select></label></div><button className="button primary" disabled={busy || active} onClick={configured ? start : onConfigure}><ScanLine size={17}/>{configured ? t('startScan') : t('configureJev')}</button></section>
    {error && <div className="error-message" role="alert">{error}</div>}
    {detail ? <><section className="panel scan-status"><div className="panel-heading"><div><span className="eyebrow">{detail.as_of ?? '—'}</span><h3>{t('progress')} <span className="subtle-badge">{t(detail.status as Key) ?? detail.status}</span></h3></div><div className="heading-actions">{['running', 'preparing', 'pausing'].includes(detail.status) ? <button className="button secondary" disabled={busy || detail.status === 'pausing'} onClick={() => control('pause')}><Pause size={14}/>{t('pause')}</button> : <><button className="button secondary" disabled={busy || detail.failed === 0} onClick={() => control('retry')}><RotateCcw size={14}/>{t('retry')}</button>{detail.remaining > 0 && <button className="button primary" disabled={busy} onClick={() => control('resume')}><Play size={14}/>{t('resume')}</button>}</>}</div></div>
      <div className="progress-label"><span>{t(detail.phase === 'data' ? 'dataProgress' : 'analysisProgress')}</span><strong>{progress.toFixed(0)}%</strong></div><div className="progress-track"><span style={{ width: `${progress}%` }}/></div>
      <div className="scan-counters">{([['ready', detail.completed], ['failed', detail.failed], ['skipped', detail.skipped], ['pending', detail.remaining]] as const).map(([label, value]) => <div key={label}><span>{t(label)}</span><strong>{value.toLocaleString()}</strong></div>)}</div>
      {detail.error && <p className="error-message">{detail.error[lang]}</p>}{detail.status === 'pausing' && <p>{t('pauseHint')}</p>}
    </section><section className="panel"><div className="panel-heading"><h3>{t('result')}</h3><select aria-label={t('filters')} value={filter} onChange={event => setFilter(event.target.value)}>{['all', 'ready', 'failed', 'skipped', 'pending'].map(value => <option value={value} key={value}>{t(value as Key)}</option>)}</select></div><div className="table-scroll"><table><thead><tr><th>{t('watchlist')}</th><th>{t('result')}</th><th>{t('details')}</th></tr></thead><tbody>{filtered.slice(currentPage * 100, (currentPage + 1) * 100).map(item => <tr key={item.stock.symbol}><td><strong>{item.stock.name}</strong><small>{item.stock.symbol}</small></td><td>{item.action ? <span className={`action-badge ${item.action}`}>{t(item.action)}</span> : t(item.status as Key)}{item.horizon && <small>{item.horizon} {t('sessions')}</small>}</td><td>{item.analysis_id ? <button className="text-button" onClick={() => onOpen(item.analysis_id!)}>{t('open')} →</button> : item.error?.[lang] ?? '—'}</td></tr>)}</tbody></table></div><div className="pagination"><button className="button secondary" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>{lang === 'zh' ? '上一页' : 'Previous'}</button><span>{currentPage + 1} / {pages} · {filtered.length}</span><button className="button secondary" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>{lang === 'zh' ? '下一页' : 'Next'}</button></div></section></> : <div className="empty-panel"><ScanLine size={32}/><p>{t('noScans')}</p></div>}
    {jobs.length > 1 && <section className="panel older-jobs"><h3>{t('history')}</h3>{jobs.map(job => <button key={job.id} className={detail?.id === job.id ? 'selected' : ''} onClick={() => setSelected(job.id)}>{job.status === 'completed' ? <CheckCircle2 size={16}/> : <LoaderCircle size={16}/>}<span>{job.as_of} · {job.scope === 'market' ? t('fullMarket') : t('watchScope')}</span><small>{t(job.status as Key)}</small></button>)}</section>}
  </div>
}
