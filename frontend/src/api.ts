import type { Lang } from './types'

export async function api<T>(path: string, lang: Lang, body?: unknown, method = body === undefined ? 'GET' : 'POST', signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api${path}${path.includes('?') ? '&' : '?'}lang=${lang}`, {
    method, signal, headers: body === undefined ? {} : { 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!response.ok) {
    const error = await response.json().catch(() => ({}))
    throw new Error(error.message ?? (lang === 'zh' ? `请求失败（${response.status}）` : `Request failed (${response.status})`))
  }
  return response.json() as Promise<T>
}
