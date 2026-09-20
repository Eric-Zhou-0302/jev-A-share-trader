import { useEffect, useRef, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, CircleMinus, Download, FileCheck2, Info, RefreshCw } from 'lucide-react'
import Chart from './Chart'
import { groupName, groups, translate } from './i18n'
import type { Analysis, Evidence, Lang } from './types'

export default function Result({ result, lang, busy, onRefresh, onConfigure, onReady }: { result: Analysis; lang: Lang; busy: boolean; onRefresh: () => void; onConfigure: () => void; onReady?: () => void }) {
  useEffect(() => { onReady?.() }, [onReady, result.id])
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  const [tab, setTab] = useState('evidence')
  const [group, setGroup] = useState('all')
  const [metricQuery, setMetricQuery] = useState('')
  const [focus, setFocus] = useState<Evidence | null>(null)
  const chart = useRef<HTMLDivElement>(null)
  const sideEvidence = (side: string) => result.evidence.filter(item => (result.action ? item.side : item.polarity > 0 ? 'support' : item.polarity < 0 ? 'oppose' : 'context') === side && (group === 'all' || item.group === group))
  const sideTitle = (side: 'support' | 'oppose' | 'context') => result.action
    ? t(side).replace('{action}', t(result.action))
    : t(({ support: 'positive', oppose: 'negative', context: 'neutral' } as const)[side])
  return <div className="result-workspace">
    <div className="stock-heading"><div><span className="eyebrow">{result.symbol}</span><h1>{result.name}</h1><p>{t('asOf')} <strong>{result.as_of}</strong><span>·</span>{t('adjusted')}<span>·</span>{result.rows.toLocaleString()} {t('candles')}</p></div><div className="heading-actions"><button className="button secondary" disabled={busy} onClick={onRefresh}><RefreshCw size={15} className={busy ? 'spin' : ''} />{t('refresh')}</button><details className="export-menu"><summary><Download size={15}/>{t('download')}</summary><div>{['html', 'json', 'csv'].map(format => <a key={format} onClick={event => event.currentTarget.closest('details')?.removeAttribute('open')} href={`/api/analyses/${result.id}/export?format=${format}&lang=${lang}`} download>{format.toUpperCase()}</a>)}</div></details></div></div>
    <section className={`decision-panel ${result.action ?? 'unavailable'}`}>
      <div className="decision-main"><div className="decision-icon">{result.action === 'buy' ? <ArrowUpRight size={28}/> : result.action === 'sell' ? <ArrowDownRight size={28}/> : <CircleMinus size={26}/>}</div><div><span className="eyebrow">{t('decision')}</span><h2>{result.action ? t(result.action) : t('noDecision')}</h2></div></div>
      <div className="decision-horizon"><span className="eyebrow">{t('horizon')}</span><p>{result.horizon ? <><strong>{result.horizon}</strong> {t('sessions')}</> : '—'}</p></div>
      {(!result.action || result.cached) && <div className="decision-note">{result.action ? <><FileCheck2 size={17}/><span>{t('cached')}</span></> : <><Info size={18}/><span>{result.status === 'technical_only' ? t('technicalPreview') : result.notices.at(-1)?.[lang] ?? t('keyHint')}{['needs_key', 'technical_only'].includes(result.status) && <button className="text-button" onClick={onConfigure}>{t('configureJev')} →</button>}</span></>}</div>}
    </section>
    <div ref={chart}><Chart result={result} lang={lang} focus={focus}/></div>
    <section className="panel evidence-panel"><div className="content-tabs">{(['evidence', 'indicators', 'quality'] as const).map(value => <button key={value} onClick={() => setTab(value)} className={tab === value ? 'active' : ''}>{t(({ evidence: 'evidenceTab', indicators: 'indicatorsTab', quality: 'qualityTab' } as const)[value])}{value === 'quality' && result.notices.length > 0 && <span className="tab-count">{result.notices.length}</span>}</button>)}</div>
      {tab !== 'quality' && <div className="group-filters"><button onClick={() => setGroup('all')} className={group === 'all' ? 'active' : ''}>{t('all')}</button>{Object.keys(groups).filter(key => key !== 'summary').map(key => <button key={key} className={group === key ? 'active' : ''} onClick={() => setGroup(key)}>{groupName(key, lang)}</button>)}</div>}
      {tab === 'evidence' && <div className="evidence-columns">{(['support', 'oppose', 'context'] as const).map(side => <div className={`evidence-column ${side}`} key={side}><h4><span className="side-dot"/>{sideTitle(side)}<span>{sideEvidence(side).length}</span></h4>{sideEvidence(side).length === 0 ? <p className="empty-evidence">{t('noEvidence')}</p> : sideEvidence(side).map(item => <button className={`evidence-card ${focus?.id === item.id ? 'focused' : ''}`} key={item.id} title={t('locateEvidence')} onClick={() => { setFocus(item); chart.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }}><div><span>{groupName(item.group, lang)}</span><time>{item.date}</time></div><p>{item[lang]}</p><small className="evidence-link">{t('locateEvidence')} ↗</small></button>)}</div>)}</div>}
      {tab === 'indicators' && <div className="metrics-view"><input className="metric-search" value={metricQuery} onChange={event => setMetricQuery(event.target.value)} placeholder={`${t('search')} RSI, MACD…`} aria-label={t('metrics')}/><div className="metrics-grid">{result.metrics.filter(metric => (group === 'all' || metric.group === group) && `${metric.key} ${metric.label}`.toLowerCase().includes(metricQuery.toLowerCase())).map(metric => <div className="metric-item" key={metric.key}><span>{metric.label.includes(' / ') ? metric.label.split(' / ')[lang === 'en' ? 1 : 0] : metric.label}<small>{groupName(metric.group, lang)}</small></span><strong>{metric.value == null ? '—' : metric.value.toLocaleString(lang === 'en' ? 'en-US' : 'zh-CN', { maximumFractionDigits: 3 })}<small>{metric.unit === 'shares' ? lang === 'zh' ? '股' : 'shares' : metric.unit}</small></strong></div>)}</div></div>}
      {tab === 'quality' && <div className="quality-view"><dl><div><dt>{t('asOf')}</dt><dd>{result.as_of}</dd></div><div><dt>{t('source')}</dt><dd>{result.source}</dd></div><div><dt>{t('rows')}</dt><dd>{result.rows}</dd></div></dl><p className="quality-note"><Info size={16}/>{t('onlyLatest')}</p>{result.notices.length ? result.notices.map((item, index) => <p className="data-notice" key={`${item.code}-${index}`}>{item[lang]}</p>) : <p>{t('noNotices')}</p>}</div>}
    </section>
  </div>
}
