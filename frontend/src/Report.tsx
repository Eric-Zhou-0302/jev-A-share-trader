import { lazy, Suspense, useEffect, useState } from 'react'
import { ArrowLeft, FileText, LoaderCircle } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Analysis, Lang } from './types'

const Result = lazy(() => import('./Result'))

export default function Report({ id, lang, initial, busy, returnLabel, onBack, onAnalyze, onConfigure, onLoaded, onReady }: {
  id: string; lang: Lang; initial: Analysis | null; busy: boolean; returnLabel: string;
  onBack: () => void; onAnalyze: (symbol: string) => void; onConfigure: () => void;
  onLoaded: (report: Analysis) => void; onReady: () => void;
}) {
  const [report, setReport] = useState<Analysis | null>(initial?.id === id ? initial : null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true); setError('')
    async function load() {
      try {
        const saved = await api<Analysis>(`/analyses/${encodeURIComponent(id)}`, lang, undefined, 'GET', controller.signal)
        if (!controller.signal.aborted) { setReport(saved); onLoaded(saved) }
      } catch (value) { if (!controller.signal.aborted) { setReport(null); setError((value as Error).message) } }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }
    void load()
    return () => controller.abort()
  }, [id, lang, initial, onLoaded])
  useEffect(() => { if (!loading && error) onReady() }, [loading, error, onReady])
  return <div className="report-page">
    <div className="report-context"><button className="text-button" onClick={onBack}><ArrowLeft size={15}/>{returnLabel}</button><span><FileText size={14}/>{t('report')}</span></div>
    {loading ? <div className="empty-panel" role="status"><LoaderCircle className="spin" size={28}/><p>{t('loading')}</p></div> : error ? <div className="error-message" role="alert">{error}</div> : report && <>
      <p className="report-snapshot">{t('reportCreated')} {new Date(report.created_at).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US', { timeZone: 'Asia/Shanghai', hour12: false })} · {t('beijingTime')}</p>
      <Suspense fallback={<div className="empty-panel">{t('loading')}</div>}><Result result={report} lang={lang} busy={busy} onRefresh={() => onAnalyze(report.symbol)} onConfigure={onConfigure} onReady={onReady}/></Suspense>
    </>}
  </div>
}
