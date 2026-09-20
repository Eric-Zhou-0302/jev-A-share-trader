import { useEffect, useRef, useState } from 'react'
import { CandlestickSeries, ColorType, createChart, createSeriesMarkers, HistogramSeries, LineSeries } from 'lightweight-charts'
import type { Time } from 'lightweight-charts'
import type { Analysis, Bar, Evidence, Lang, Point } from './types'
import { translate } from './i18n'

export default function Chart({ result, lang, focus }: { result: Analysis; lang: Lang; focus: Evidence | null }) {
  const container = useRef<HTMLDivElement>(null)
  const [period, setPeriod] = useState<'daily' | 'weekly' | 'monthly'>('daily')
  const [overlay, setOverlay] = useState('sma')
  const [indicator, setIndicator] = useState('volume')
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  useEffect(() => { if (focus) setPeriod('daily') }, [focus])
  useEffect(() => {
    const element = container.current
    if (!element) return
    const chart = createChart(element, {
      autoSize: true, height: 400,
      layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#74817b', fontFamily: 'system-ui, sans-serif', attributionLogo: true, panes: { separatorColor: '#e5ebe7', separatorHoverColor: '#d4e1da' } },
      grid: { vertLines: { color: '#f3f5f3' }, horzLines: { color: '#eef2ef' } },
      rightPriceScale: { borderColor: '#edf0ed' }, timeScale: { borderColor: '#edf0ed', timeVisible: false },
      crosshair: { vertLine: { color: '#90aaa0' }, horzLine: { color: '#90aaa0' } }, localization: { locale: lang === 'zh' ? 'zh-CN' : 'en-US' },
    })
    const bars = (period === 'daily' ? result.bars : result.charts[period] as Bar[]).filter(bar => [bar.open, bar.high, bar.low, bar.close].every(Number.isFinite))
    const candles = chart.addSeries(CandlestickSeries, { upColor: '#db735f', downColor: '#409984', wickUpColor: '#db735f', wickDownColor: '#409984', borderVisible: false, priceLineVisible: false })
    candles.setData(bars.map(bar => ({ time: bar.date as Time, open: bar.open, high: bar.high, low: bar.low, close: bar.close })))
    if (focus && period === 'daily' && bars.some(bar => bar.date === focus.date)) {
      createSeriesMarkers(candles, [{ time: focus.date as Time, position: 'aboveBar', shape: 'circle', color: '#927135', text: focus.date }])
    }
    const line = (key: string, color: string, pane = 0) => {
      const data = result.charts[key] as Point[] | undefined
      if (!data) return
      const series = chart.addSeries(LineSeries, { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, title: key.toUpperCase() }, pane)
      series.setData(data.map(point => ({ ...point, time: point.time as Time })))
    }
    if (period === 'daily') {
      if (overlay === 'sma') { line('sma_20', '#c8984e'); line('sma_60', '#729cbb') }
      if (overlay === 'boll') { line('bb_upper', '#98b5a7'); line('bb_middle', '#c8984e'); line('bb_lower', '#98b5a7') }
      if (overlay === 'ema') { line('ema_20', '#c8984e'); line('ema_60', '#729cbb') }
    }
    if (indicator === 'volume' || period !== 'daily') {
      const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, 1)
      volume.setData(bars.map(bar => ({ time: bar.date as Time, value: bar.volume, color: bar.close >= bar.open ? '#e9b7a8' : '#a4c9b9' })))
    } else if (indicator === 'macd') {
      line('macd', '#c8984e', 1); line('macd_signal', '#729cbb', 1)
      const histogram = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 1)
      histogram.setData((result.charts.macd_hist as Point[]).map(point => ({ time: point.time as Time, value: point.value, color: point.value >= 0 ? '#e9b7a8' : '#a4c9b9' })))
    } else { line('rsi_14', '#8e9a67', 1) }
    chart.panes()[0]?.setHeight(300)
    chart.panes()[1]?.setHeight(100)
    chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, bars.length - 100), to: bars.length + 3 })
    return () => chart.remove()
  }, [result, period, overlay, indicator, lang, focus])
  return <section className="panel chart-panel">
    <div className="panel-heading"><div><span className="eyebrow">PRICE ACTION</span><h3>{t('priceChart')} <span className="subtle-badge">{t('adjusted')}</span></h3></div>
      <div className="segments" aria-label={t('completedOnly')}>{(['daily', 'weekly', 'monthly'] as const).map((value, index) => <button key={value} className={period === value ? 'active' : ''} onClick={() => setPeriod(value)}>{t((['day', 'week', 'month'] as const)[index])}</button>)}</div>
    </div>
    <div className="chart-controls"><label>{t('overlay')}<select value={overlay} onChange={event => setOverlay(event.target.value)} disabled={period !== 'daily'}><option value="sma">MA20 / MA60</option><option value="ema">EMA20 / EMA60</option><option value="boll">BOLL</option><option value="none">—</option></select></label><label>{t('indicator')}<select value={indicator} onChange={event => setIndicator(event.target.value)} disabled={period !== 'daily'}><option value="volume">{t('volume')}</option><option value="macd">MACD</option><option value="rsi">RSI14</option></select></label><span>{t('completedOnly')}</span></div>
    <div ref={container} className="chart-container" role="img" aria-label={`${result.symbol} ${t('priceChart')}`} />
  </section>
}
