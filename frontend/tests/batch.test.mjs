import assert from 'node:assert/strict'
import test from 'node:test'
import { parseSymbols } from '../src/batchInput.ts'
import { jobProgress } from '../src/scanState.ts'
import { parseRoute } from '../src/routes.ts'

test('pasted symbols normalize, deduplicate and preserve their order', () => {
  assert.deepEqual(parseSymbols('600000，sz000001\n600000.SH; BJ920001、000001.SZ'), {
    symbols: ['600000.SH', '000001.SZ', '920001.BJ'], duplicates: 2, invalid: [],
  })
  assert.deepEqual(parseSymbols('000001.SH bad 600000'), { symbols: ['600000.SH'], duplicates: 0, invalid: ['000001.SH', 'bad'] })
  assert.deepEqual(parseSymbols(' ,；\n'), { symbols: [], duplicates: 0, invalid: [] })
})

test('progress counts finished stocks and never resets when the next download starts', () => {
  const job = { total: 4, completed: 1, failed: 1, skipped: 0, downloaded: 4 }
  assert.equal(jobProgress({ ...job, phase: 'data' }), 50)
  assert.equal(jobProgress({ ...job, phase: 'analysis' }), 50)
  assert.equal(jobProgress({ ...job, total: 0, completed: 0, failed: 0 }), 0)
})

test('old market launch bookmarks lead to the batch input', () => {
  assert.deepEqual(parseRoute('#/scans?scope=market'), { page: 'scans', view: { scope: 'batch' } })
  assert.deepEqual(parseRoute('#/scans?scope=watchlist'), { page: 'scans', view: { scope: 'watchlist' } })
  assert.equal(parseRoute('#/scan-history?scope=batch').view.scope, 'batch')
})
