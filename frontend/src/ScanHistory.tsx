import { useEffect, useState } from 'react'
import { History, LoaderCircle } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Key } from './i18n'
import type { Job, Lang } from './types'
import { jobStatuses, scanHistoryHref, scanTaskHref } from './routes'
import type { ScanHistoryView } from './routes'
import { activeStatuses, jobProgress, scopeKey } from './scanState'
import NavigationLink from './NavigationLink'
import RecordDeletion, { useRecordDeletion } from './RecordDeletion'

interface Page { items: Job[]; total: number; page: number; limit: number }
export default function ScanHistory({ lang, view, onChange, onTask, onReady }: { lang: Lang; view: ScanHistoryView; onChange: (view: ScanHistoryView) => void; onTask: (id: string, from: string) => void; onReady: () => void }) {
  const [data, setData] = useState<Page | null>(null)
  const [error, setError] = useState('')
  const [loadedQuery, setLoadedQuery] = useState('')
  const [revision, setRevision] = useState(0)
  const query = new URLSearchParams({ scope: view.scope, status: view.status, page: String(view.page), limit: '20' }).toString()
  const loadKey = `${query}:${lang}:${revision}`
  const loading = loadedQuery !== loadKey
  const t = (key: Key) => translate(lang, key)
  const deletionItems = (data?.items ?? []).map(job => ({ id: job.id, label: `${t(scopeKey(job.scope))} · ${job.as_of ?? '—'} · ${job.id}`, disabled: activeStatuses.includes(job.status) }))
  const manager = useRecordDeletion('jobs', lang, loadKey, loading ? [] : deletionItems, () => setRevision(value => value + 1))
  useEffect(() => {
    if (manager.busy) return
    const controller = new AbortController()
    let timer: number
    async function poll() {
      try {
        const page = await api<Page>(`/jobs/search?${query}`, lang, undefined, 'GET', controller.signal)
        if (!controller.signal.aborted) { setData(page); setError(''); if (page.page !== view.page) onChange({ ...view, page: page.page }) }
      } catch (value) { if (!controller.signal.aborted) { setData(null); setError((value as Error).message) } }
      if (!controller.signal.aborted) { setLoadedQuery(loadKey); timer = window.setTimeout(poll, 4000) }
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [query, lang, loadKey, manager.busy])
  useEffect(() => { if (!loading) onReady() }, [loading, onReady])
  const page = data?.page ?? 0
  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / (data?.limit ?? 20)))
  const from = scanHistoryHref({ ...view, page })
  return <div className="scan-history-page">
    <div className="page-heading"><span className="eyebrow">SCAN ARCHIVE</span><h1>{t('scanHistory')}</h1><p>{t('scanHistoryHint')}</p></div>
    <section className="panel history-filters scan-history-filters"><label><span>{t('scope')}</span><select value={view.scope} onChange={event => onChange({ ...view, scope: event.target.value as ScanHistoryView['scope'], page: 0 })}><option value="all">{t('all')}</option><option value="batch">{t('batchScope')}</option><option value="watchlist">{t('watchScope')}</option><option value="market">{t('fullMarket')}</option></select></label><label><span>{t('taskStatus')}</span><select value={view.status} onChange={event => onChange({ ...view, status: event.target.value, page: 0 })}><option value="all">{t('all')}</option>{jobStatuses.map(status => <option value={status} key={status}>{t(status as Key)}</option>)}</select></label></section>
    <RecordDeletion manager={manager}/>
    {error && <div className="error-message" role="alert">{error}</div>}
    {loading ? <div className="empty-panel" role="status"><LoaderCircle size={28} className="spin"/><p>{t('loading')}</p></div> : data?.items.length ? <section className="panel"><div className="table-scroll"><table><thead><tr><th className="selection-cell"><span className="sr-only">{t('selectRecord')}</span></th><th>{t('scanId')}</th><th>{t('scope')}</th><th>{t('asOf')}</th><th>{t('taskStatus')}</th><th>{t('progress')}</th><th>{t('manage')}</th></tr></thead><tbody>{data.items.map(job => <tr key={job.id}><td className="selection-cell"><input type="checkbox" aria-label={`${t('selectRecord')} ${job.id.slice(0, 8)}`} title={activeStatuses.includes(job.status) ? t('pauseBeforeDelete') : undefined} disabled={manager.busy || activeStatuses.includes(job.status)} checked={manager.selected.has(job.id)} onChange={() => manager.toggle(job.id)}/></td><td><strong>{job.id.slice(0, 8)}</strong><small>{job.created ? new Date(job.created * 1000).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { timeZone: 'Asia/Shanghai', hour12: false }) : '—'}</small></td><td>{t(scopeKey(job.scope))}</td><td>{job.as_of ?? '—'}</td><td>{t(job.status as Key) ?? job.status}</td><td><strong>{jobProgress(job).toFixed(0)}%</strong><small>{job.completed.toLocaleString()} / {job.total.toLocaleString()} {t('ready')}</small></td><td><div className="record-actions"><NavigationLink href={scanTaskHref(job.id, undefined, from)} onOpen={() => onTask(job.id, from)}>{t('viewScanTask')} →</NavigationLink><button className="text-button delete-button" aria-label={`${t('deleteRecord')} ${job.id.slice(0, 8)}`} title={activeStatuses.includes(job.status) ? t('pauseBeforeDelete') : undefined} disabled={manager.busy || activeStatuses.includes(job.status)} onClick={() => manager.request(deletionItems.filter(record => record.id === job.id))}>{t('deleteRecord')}</button></div></td></tr>)}</tbody></table></div><div className="pagination"><button className="button secondary" disabled={page === 0} onClick={() => onChange({ ...view, page: page - 1 })}>{t('previousPage')}</button><span>{page + 1} / {pages} · {data.total}</span><button className="button secondary" disabled={page + 1 >= pages} onClick={() => onChange({ ...view, page: page + 1 })}>{t('nextPage')}</button></div></section> : !error && <div className="empty-panel"><History size={28}/><p>{t('noMatchingScans')}</p></div>}
  </div>
}
