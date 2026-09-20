export type ScanScope = 'watchlist' | 'market'
export interface ScanView { scope: ScanScope }
export interface ScanHistoryView { scope: 'all' | ScanScope; status: string; page: number }
export interface ScanTaskView { filter: string; page: number }
export interface HistoryView { query: string; fromDate: string; toDate: string; page: number }
export type SourceRoute = { page: 'workbench'; symbol: string } | { page: 'scans'; view: ScanView } | { page: 'scanHistory'; view: ScanHistoryView } | { page: 'history'; view: HistoryView } | { page: 'scanTask'; id: string; view: ScanTaskView; from: string }
export type Route = SourceRoute | { page: 'report'; id: string; from: string }
export const jobStatuses = ['preparing', 'running', 'pausing', 'paused', 'completed', 'partial', 'failed', 'stopping', 'stopped']
const filters = ['all', 'ready', 'failed', 'skipped', 'pending']
const pageNumber = (value: string | null) => /^\d{1,6}$/.test(value ?? '') ? Math.max(0, Number(value)) : 0
const dateValue = (value: string | null) => /^\d{4}-\d{2}-\d{2}$/.test(value ?? '') ? value! : ''
const validId = (id: string) => /^[a-zA-Z0-9_-]{1,128}$/.test(id)
const taskView = (params: URLSearchParams): ScanTaskView => ({ filter: filters.includes(params.get('filter') ?? '') ? params.get('filter')! : 'all', page: pageNumber(params.get('page')) })
const taskSource = (from: string) => {
  if (/^#\/scan-history(\?|$)/.test(from)) return from
  if (/^#\/scans(\?|$)/.test(from) && !new URLSearchParams(from.split('?')[1]).has('job')) return from
  return '#/scan-history'
}

export function parseRoute(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#/, '').split('?')
  const params = new URLSearchParams(query)
  if (path === '/scans') {
    const view: ScanView = { scope: params.get('scope') === 'market' ? 'market' : 'watchlist' }
    const id = params.get('job')
    // 兼容旧扫描详情链接，入口本身不再自动打开最近任务。
    if (id && validId(id)) return { page: 'scanTask', id, view: taskView(params), from: scanHref(view) }
    return { page: 'scans', view }
  }
  // 旧书签中的重置筛选仍对应同一批已中止任务。
  if (params.get('status') === 'reset') params.set('status', 'stopped')
  if (params.get('status') === 'resetting') params.set('status', 'stopping')
  if (path === '/scan-history') return { page: 'scanHistory', view: { scope: ['market', 'watchlist'].includes(params.get('scope') ?? '') ? params.get('scope') as ScanScope : 'all', status: jobStatuses.includes(params.get('status') ?? '') ? params.get('status')! : 'all', page: pageNumber(params.get('page')) } }
  if (path?.startsWith('/scans/')) {
    const id = path.slice('/scans/'.length)
    if (validId(id)) return { page: 'scanTask', id, view: taskView(params), from: taskSource(params.get('from') ?? '#/scan-history') }
  }
  if (path === '/history') return { page: 'history', view: { query: (params.get('q') ?? '').slice(0, 60), fromDate: dateValue(params.get('from')), toDate: dateValue(params.get('to')), page: pageNumber(params.get('page')) } }
  if (path?.startsWith('/reports/')) {
    const id = path.slice('/reports/'.length)
    const from = params.get('from') ?? '#/history'
    let safeFrom = /^#\/(analysis|scans|scan-history|history)(\?|$)/.test(from) ? from : '#/history'
    if (/^#\/scans\/[a-zA-Z0-9_-]{1,128}(\?|$)/.test(from)) {
      const task = parseRoute(from)
      if (task.page === 'scanTask') safeFrom = scanTaskHref(task.id, task.view, task.from)
    }
    if (validId(id)) return { page: 'report', id, from: safeFrom }
  }
  return { page: 'workbench', symbol: (params.get('symbol') ?? '').slice(0, 12) }
}

export const scanHref = (view: ScanView = { scope: 'watchlist' }) => `#/scans?${new URLSearchParams({ scope: view.scope })}`
export function scanHistoryHref(view: ScanHistoryView = { scope: 'all', status: 'all', page: 0 }): string {
  const params = new URLSearchParams()
  if (view.scope !== 'all') params.set('scope', view.scope)
  if (view.status !== 'all') params.set('status', view.status)
  if (view.page) params.set('page', String(view.page))
  return `#/scan-history${params.size ? `?${params}` : ''}`
}
export function scanTaskHref(id: string, view: ScanTaskView = { filter: 'all', page: 0 }, from = '#/scan-history'): string {
  const params = new URLSearchParams({ from: taskSource(from) })
  if (view.filter !== 'all') params.set('filter', view.filter)
  if (view.page) params.set('page', String(view.page))
  return `#/scans/${encodeURIComponent(id)}?${params}`
}
export function historyHref(view: HistoryView): string {
  const params = new URLSearchParams()
  if (view.query) params.set('q', view.query)
  if (view.fromDate) params.set('from', view.fromDate)
  if (view.toDate) params.set('to', view.toDate)
  if (view.page) params.set('page', String(view.page))
  return `#/history${params.size ? `?${params}` : ''}`
}
export const reportHref = (id: string, from = '#/history') => `#/reports/${encodeURIComponent(id)}?${new URLSearchParams({ from })}`
export const analysisHref = (symbol = '') => `#/analysis${symbol ? `?${new URLSearchParams({ symbol })}` : ''}`
