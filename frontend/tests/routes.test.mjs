import assert from 'node:assert/strict'
import test from 'node:test'
import { analysisHref, historyHref, parseRoute, reportHref, scanHref, scanHistoryHref, scanTaskHref } from '../src/routes.ts'

test('scan entry contains only its selected universe', () => {
  assert.deepEqual(parseRoute(scanHref({ scope: 'market' })), { page: 'scans', view: { scope: 'market' } })
})
test('report links preserve both scan task state and its filtered history source', () => {
  const history = { scope: 'market', status: 'completed', page: 3 }
  const view = { filter: 'ready', page: 1 }
  const source = scanHistoryHref(history)
  const task = scanTaskHref('old-job', view, source)
  const report = parseRoute(reportHref('report-01', task))
  assert.equal(report.page, 'report')
  assert.deepEqual(parseRoute(report.from), { page: 'scanTask', id: 'old-job', view, from: source })
  assert.deepEqual(parseRoute(parseRoute(report.from).from), { page: 'scanHistory', view: history })
})
test('legacy scan links still open their original task and result page', () => {
  assert.deepEqual(parseRoute('#/scans?scope=market&job=job-old&filter=ready&page=4'), {
    page: 'scanTask', id: 'job-old', view: { filter: 'ready', page: 4 }, from: scanHref({ scope: 'market' }),
  })
})
test('history links preserve Chinese queries and both cutoff dates', () => {
  const view = { query: '测试 & 股票', fromDate: '2026-09-01', toDate: '2026-09-18', page: 2 }
  const report = parseRoute(reportHref('report-02', historyHref(view)))
  assert.deepEqual(parseRoute(report.from), { page: 'history', view })
})
test('direct report and task links have safe standalone return destinations', () => {
  assert.deepEqual(parseRoute('#/reports/abc123-needs_key'), { page: 'report', id: 'abc123-needs_key', from: '#/history' })
  assert.deepEqual(parseRoute('#/scans/job-01'), { page: 'scanTask', id: 'job-01', view: { filter: 'all', page: 0 }, from: '#/scan-history' })
})
test('external and recursive return destinations cannot hijack navigation', () => {
  for (const from of ['https://example.com', '#/reports/other', '#/scans-unknown']) {
    assert.equal(parseRoute(reportHref('report-03', from)).from, '#/history')
  }
  for (const from of ['https://example.com', '#/scans/another-task', '#/scans?job=another-task', '#/scan-history-unknown']) {
    const rawTask = `#/scans/job-01?${new URLSearchParams({ from })}`
    assert.equal(parseRoute(rawTask).from, '#/scan-history')
    const reportTask = parseRoute(parseRoute(reportHref('report-04', rawTask)).from)
    assert.equal(reportTask.from, '#/scan-history')
  }
})
test('malformed filters and page numbers recover to usable defaults', () => {
  assert.deepEqual(parseRoute('#/scans?scope=bad&filter=bad&page=-5'), { page: 'scans', view: { scope: 'watchlist' } })
  assert.deepEqual(parseRoute('#/scan-history?scope=bad&status=bad&page=Infinity').view, { scope: 'all', status: 'all', page: 0 })
  assert.deepEqual(parseRoute('#/scans/valid?filter=bad&page=-3').view, { filter: 'all', page: 0 })
  assert.equal(parseRoute('#/history?page=Infinity&from=oops').view.fromDate, '')
})
test('stock entry remains distinct from a report and can be prefilled', () => {
  assert.deepEqual(parseRoute(analysisHref('000001.SZ')), { page: 'workbench', symbol: '000001.SZ' })
  assert.deepEqual(parseRoute('#/analysis'), { page: 'workbench', symbol: '' })
})
