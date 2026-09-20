import type { Job } from './types'

export const activeStatuses = ['running', 'preparing', 'pausing', 'resetting']
export const jobProgress = (job: Job) => job.phase === 'preparing' ? 0 : Math.min(100, (job.phase === 'data' ? job.downloaded : job.completed + job.skipped + job.failed) / Math.max(job.total, 1) * 100)
