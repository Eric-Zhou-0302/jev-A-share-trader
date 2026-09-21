import type { Job } from './types'

export const activeStatuses = ['running', 'preparing', 'pausing', 'stopping']
export const scopeKey = (scope: string) => scope === 'market' ? 'fullMarket' : scope === 'batch' ? 'batchScope' : 'watchScope'
export const jobProgress = (job: Job) => Math.min(100, (job.completed + job.skipped + job.failed) / Math.max(job.total, 1) * 100)
