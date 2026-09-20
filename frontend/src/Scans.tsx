import { useEffect, useState } from 'react'
import { LoaderCircle, ScanLine } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Key } from './i18n'
import type { Job, Lang } from './types'
import { scanHref, scanTaskHref } from './routes'
import type { ScanView } from './routes'
import { activeStatuses, jobProgress } from './scanState'
import NavigationLink from './NavigationLink'

export default function Scans({ lang, configured, busy, view, onChange, onStart, onTask, onConfigure, onReady }: {
  lang: Lang; configured: boolean; busy: boolean; view: ScanView; onChange: (view: ScanView) => void;
  onStart: () => void; onTask: (id: string, from: string) => void; onConfigure: () => void; onReady: () => void;
}) {
  const [jobs, setJobs] = useState<Job[]>([])
  const [recent, setRecent] = useState<Job | null>(null)
  const [loadedScope, setLoadedScope] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const t = (key: Key) => translate(lang, key)
  useEffect(() => {
    const controller = new AbortController()
    let timer: number
    async function poll() {
      try {
        const [data, history] = await Promise.all([
          api<Job[]>('/jobs', lang, undefined, 'GET', controller.signal),
          api<{ items: Job[] }>(`/jobs/search?scope=${view.scope}&limit=1`, lang, undefined, 'GET', controller.signal),
        ])
        if (!controller.signal.aborted) { setJobs(data); setRecent(history.items[0] ?? null); setError('') }
      } catch (value) { if (!controller.signal.aborted) { setRecent(null); setError((value as Error).message) } }
      if (!controller.signal.aborted) { setLoadedScope(view.scope); setLoading(false); timer = window.setTimeout(poll, 2000) }
    }
    void poll()
    return () => { controller.abort(); window.clearTimeout(timer) }
  }, [lang, view.scope])
  const pending = loading || loadedScope !== view.scope
  useEffect(() => { if (!pending) onReady() }, [pending, onReady])
  const active = jobs.find(job => activeStatuses.includes(job.status))
  const shown = active ?? recent
  const from = scanHref(view)
  return <div className="scan-workspace">
    <div className="page-heading"><span className="eyebrow">MARKET RESEARCH</span><h1>{t('scans')}</h1><p>{t('scanEntryHint')}</p></div>
    <section className="panel scan-launch"><label>{t('scope')}<select value={view.scope} disabled={busy} onChange={event => onChange({ scope: event.target.value as ScanView['scope'] })}><option value="watchlist">{t('watchScope')}</option><option value="market">{t('fullMarket')}</option></select></label><button className="button primary" disabled={busy || pending || !!active || !!error} onClick={configured ? onStart : onConfigure}>{busy ? <LoaderCircle size={17} className="spin"/> : <ScanLine size={17}/>} {configured ? t('startScan') : t('configureJev')}</button></section>
    {error && <div className="error-message" role="alert">{error}</div>}
    {active && <p className="scan-active-note">{t('otherScanActive')}</p>}
    {pending ? <div className="empty-panel" role="status"><LoaderCircle size={28} className="spin"/><p>{t('loading')}</p></div> : shown ? <section className="panel scan-summary">
      <div><span className="eyebrow">{t(active ? 'currentScan' : 'latestScan')}</span><h3>{shown.scope === 'market' ? t('fullMarket') : t('watchScope')}<span className="subtle-badge">{t(shown.status as Key) ?? shown.status}</span></h3><p>{t('asOf')} {shown.as_of ?? '—'} · {t('scanId')} {shown.id.slice(0, 8)}</p><p>{t('progress')} {jobProgress(shown).toFixed(0)}% · {shown.completed.toLocaleString()} / {shown.total.toLocaleString()} {t('ready')}</p></div>
      <NavigationLink className="button secondary" href={scanTaskHref(shown.id, undefined, from)} onOpen={() => onTask(shown.id, from)}>{t('viewScanTask')} →</NavigationLink>
    </section> : <div className="empty-panel"><ScanLine size={30}/><p>{t('noScans')}</p></div>}
  </div>
}
