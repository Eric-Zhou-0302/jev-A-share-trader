export interface ScanView { scope: 'watchlist' | 'market'; selected: string | null; filter: string; page: number }
export interface HistoryView { query: string; fromDate: string; toDate: string; page: number }
export type SourceRoute = { page: 'workbench'; symbol: string } | { page: 'scans'; view: ScanView } | { page: 'history'; view: HistoryView }
export type Route = SourceRoute | { page: 'report'; id: string; from: string }
const filters = ['all', 'ready', 'failed', 'skipped', 'pending']
const pageNumber = (value: string | null) => /^\d{1,6}$/.test(value ?? '') ? Math.max(0, Number(value)) : 0
const dateValue = (value: string | null) => /^\d{4}-\d{2}-\d{2}$/.test(value ?? '') ? value! : ''

export function parseRoute(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#/, '').split('?')
  const params = new URLSearchParams(query)
  if (path === '/scans') return { page: 'scans', view: { scope: params.get('scope') === 'market' ? 'market' : 'watchlist', selected: params.get('job') || null, filter: filters.includes(params.get('filter') ?? '') ? params.get('filter')! : 'all', page: pageNumber(params.get('page')) } }
  if (path === '/history') return { page: 'history', view: { query: (params.get('q') ?? '').slice(0, 60), fromDate: dateValue(params.get('from')), toDate: dateValue(params.get('to')), page: pageNumber(params.get('page')) } }
  if (path?.startsWith('/reports/')) {
    const id = path.slice('/reports/'.length)
    const from = params.get('from') ?? '#/history'
    // 返回地址只允许应用内的列表或入口，避免外部地址及报告之间递归嵌套。
    const safeFrom = /^#\/(analysis|scans|history)(\?|$)/.test(from) ? from : '#/history'
    if (/^[a-zA-Z0-9_-]{1,128}$/.test(id)) return { page: 'report', id, from: safeFrom }
  }
  return { page: 'workbench', symbol: (params.get('symbol') ?? '').slice(0, 12) }
}

export function scanHref(view: ScanView): string {
  const params = new URLSearchParams({ scope: view.scope })
  if (view.selected) params.set('job', view.selected)
  if (view.filter !== 'all') params.set('filter', view.filter)
  if (view.page) params.set('page', String(view.page))
  return `#/scans?${params}`
}
export function historyHref(view: HistoryView): string {
  const params = new URLSearchParams()
  if (view.query) params.set('q', view.query)
  if (view.fromDate) params.set('from', view.fromDate)
  if (view.toDate) params.set('to', view.toDate)
  if (view.page) params.set('page', String(view.page))
  return `#/history${params.size ? `?${params}` : ''}`
}
export function reportHref(id: string, from = '#/history'): string {
  return `#/reports/${encodeURIComponent(id)}?${new URLSearchParams({ from })}`
}
export const analysisHref = (symbol = '') => `#/analysis${symbol ? `?${new URLSearchParams({ symbol })}` : ''}`
