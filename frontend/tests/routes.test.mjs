import assert from 'node:assert/strict'
import test from 'node:test'
import { analysisHref, historyHref, parseRoute, reportHref, scanHref } from '../src/routes.ts'

test('reports retain a specific scan, universe, result filter and page on return', () => {
  const view = { scope: 'market', selected: 'job-old', filter: 'ready', page: 4 }
  const report = parseRoute(reportHref('report-01', scanHref(view)))
  assert.equal(report.page, 'report')
  assert.deepEqual(parseRoute(report.from), { page: 'scans', view })
})
test('history links preserve Chinese queries and both cutoff dates', () => {
  const view = { query: '测试 & 股票', fromDate: '2026-09-01', toDate: '2026-09-18', page: 2 }
  const report = parseRoute(reportHref('report-02', historyHref(view)))
  assert.deepEqual(parseRoute(report.from), { page: 'history', view })
})
test('direct report links fall back to history and retain legacy report ids', () => {
  assert.deepEqual(parseRoute('#/reports/abc123-needs_key'), { page: 'report', id: 'abc123-needs_key', from: '#/history' })
})
test('external or recursive return destinations cannot hijack report navigation', () => {
  for (const from of ['https://example.com', '#/reports/other', '#/scans-unknown']) {
    assert.equal(parseRoute(reportHref('report-03', from)).from, '#/history')
  }
})
test('malformed filters and page numbers recover to usable list defaults', () => {
  assert.deepEqual(parseRoute('#/scans?scope=bad&filter=bad&page=-5'), { page: 'scans', view: { scope: 'watchlist', selected: null, filter: 'all', page: 0 } })
  assert.equal(parseRoute('#/history?page=Infinity&from=oops').view.page, 0)
  assert.equal(parseRoute('#/history?page=Infinity&from=oops').view.fromDate, '')
})
test('stock entry remains distinct from a report and can be prefilled', () => {
  assert.deepEqual(parseRoute(analysisHref('000001.SZ')), { page: 'workbench', symbol: '000001.SZ' })
  assert.deepEqual(parseRoute('#/analysis'), { page: 'workbench', symbol: '' })
})
