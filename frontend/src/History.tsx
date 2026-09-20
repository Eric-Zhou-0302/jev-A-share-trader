import { useEffect, useState } from 'react'
import { Clock3, LoaderCircle, Search } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import { historyHref } from './routes'
import type { HistoryView } from './routes'
import type { Lang, Summary } from './types'
import ReportLink from './ReportLink'

interface Records { items: Summary[]; total: number; page: number; limit: number }
export default function History({ lang, view, onChange, onOpen, onReady }: { lang: Lang; view: HistoryView; onChange: (view: HistoryView) => void; onOpen: (id: string, from: string) => void; onReady: () => void }) {
  const [records, setRecords] = useState<Records>({ items: [], total: 0, page: 0, limit: 50 })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [loadedQuery, setLoadedQuery] = useState('')
  const { query, fromDate, toDate, page } = view
  const [draft, setDraft] = useState({ query, fromDate, toDate })
  useEffect(() => setDraft({ query, fromDate, toDate }), [query, fromDate, toDate])
  const queryKey = JSON.stringify([query, fromDate, toDate, page, lang])
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    const timer = window.setTimeout(async () => {
      const params = new URLSearchParams({ q: query, page: String(page) })
      if (fromDate) params.set('date_from', fromDate)
      if (toDate) params.set('date_to', toDate)
      try {
        const result = await api<Records>(`/analyses/search?${params}`, lang, undefined, 'GET', controller.signal)
        if (!controller.signal.aborted) setRecords(result)
      } catch (value) { if (!controller.signal.aborted) setError((value as Error).message) }
      finally { if (!controller.signal.aborted) { setLoadedQuery(queryKey); setLoading(false) } }
    }, 200)
    return () => { window.clearTimeout(timer); controller.abort() }
  }, [query, fromDate, toDate, page, lang, queryKey])
  useEffect(() => { if (!loading && loadedQuery === queryKey) onReady() }, [loading, loadedQuery, queryKey, onReady])
  const source = historyHref({ ...view, page: records.page })
  const pages = Math.max(1, Math.ceil(records.total / records.limit))
  return <div className="history-workspace"><div className="page-heading"><span className="eyebrow">RESEARCH ARCHIVE</span><h1>{t('history')}</h1><p>{t('historyHint')}</p></div>
    <form className="panel history-filters" aria-label={t('filters')} onSubmit={event => { event.preventDefault(); onChange({ ...draft, page: 0 }) }}>
      <label><span><Search size={14}/>{t('stock')}</span><input aria-label={t('historySearch')} value={draft.query} maxLength={60} placeholder={t('historySearch')} onChange={event => setDraft({ ...draft, query: event.target.value })}/></label>
      <label><span>{t('dateFrom')}</span><input type="text" placeholder="YYYY-MM-DD" maxLength={10} pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" value={draft.fromDate} onChange={event => setDraft({ ...draft, fromDate: event.target.value })}/></label>
      <label><span>{t('dateTo')}</span><input type="text" placeholder="YYYY-MM-DD" maxLength={10} pattern="[0-9]{4}-[0-9]{2}-[0-9]{2}" value={draft.toDate} onChange={event => setDraft({ ...draft, toDate: event.target.value })}/></label>
      <button className="button primary" type="submit">{t('applyFilters')}</button>
      <button type="button" className="button secondary" disabled={!query && !fromDate && !toDate && !draft.query && !draft.fromDate && !draft.toDate} onClick={() => { setDraft({ query: '', fromDate: '', toDate: '' }); onChange({ query: '', fromDate: '', toDate: '', page: 0 }) }}>{t('clearFilters')}</button>
    </form>
    {loading ? <div className="empty-panel" role="status"><LoaderCircle className="spin" size={28}/><p>{t('loading')}</p></div> : error ? <div className="error-message" role="alert">{error}</div> : records.total ? <section className="panel"><div className="table-scroll"><table><thead><tr><th>{t('stock')}</th><th>{t('asOf')}</th><th>{t('decision')}</th><th>{t('horizon')}</th><th>{t('reportCreated')}</th><th/></tr></thead><tbody>{records.items.map(item => <tr key={item.id}><td><strong>{item.name}</strong><small>{item.symbol}</small></td><td>{item.as_of}</td><td><span className={`action-badge ${item.action ?? ''}`}>{item.action ? t(item.action) : t('noDecision')}</span></td><td>{item.horizon ? `${item.horizon} ${t('sessions')}` : '—'}</td><td>{new Date(item.created_at).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { timeZone: 'Asia/Shanghai', hour12: false })}</td><td><ReportLink id={item.id} from={source} onOpen={() => onOpen(item.id, source)}>{t('viewReport')} →</ReportLink></td></tr>)}</tbody></table></div>
      <div className="pagination"><button className="button secondary" disabled={records.page === 0} onClick={() => onChange({ ...view, page: records.page - 1 })}>{t('previousPage')}</button><span>{records.page + 1} / {pages} · {records.total}</span><button className="button secondary" disabled={records.page + 1 >= pages} onClick={() => onChange({ ...view, page: records.page + 1 })}>{t('nextPage')}</button></div>
    </section> : <div className="empty-panel"><Clock3 size={30}/><p>{t(query || fromDate || toDate ? 'noMatchingRecords' : 'noHistory')}</p></div>}
  </div>
}
