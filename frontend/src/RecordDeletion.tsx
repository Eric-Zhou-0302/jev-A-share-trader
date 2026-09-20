import { useEffect, useRef, useState } from 'react'
import { RotateCcw, Trash2, X } from 'lucide-react'
import { api } from './api'
import { translate } from './i18n'
import type { Lang } from './types'

export interface DeletionItem { id: string; label: string; disabled?: boolean }
interface Undo { token: string; count: number }
const readUndo = (key: string): Undo | null => {
  try {
    const value = JSON.parse(sessionStorage.getItem(key) ?? 'null')
    return value && /^[a-f0-9]{32}$/.test(value.token) && value.count > 0 ? value : null
  } catch { return null }
}

export function useRecordDeletion(kind: 'analyses' | 'jobs', lang: Lang, scopeKey: string, items: DeletionItem[], onChanged: () => void) {
  const storageKey = `jev-delete-undo-${kind}-v1`
  const [selection, setSelection] = useState<{ scope: string; ids: string[] }>({ scope: scopeKey, ids: [] })
  const [pending, setPending] = useState<DeletionItem[]>([])
  const [undo, setUndo] = useState<Undo | null>(() => readUndo(storageKey))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [restored, setRestored] = useState<number | null>(null)
  const working = useRef(false)
  const mounted = useRef(true)
  const changed = useRef(onChanged)
  changed.current = onChanged
  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const available = items.filter(item => !item.disabled)
  const selectedItems = available.filter(item => selection.scope === scopeKey && selection.ids.includes(item.id))
  const selected = new Set(selectedItems.map(item => item.id))
  const allSelected = available.length > 0 && selected.size === available.length
  function toggle(id: string) {
    const ids = new Set(selected)
    if (ids.has(id)) ids.delete(id); else ids.add(id)
    setSelection({ scope: scopeKey, ids: [...ids] })
  }
  function toggleAll() { setSelection({ scope: scopeKey, ids: allSelected ? [] : available.map(item => item.id) }) }
  function request(targets: DeletionItem[]) {
    if (working.current || targets.some(item => item.disabled)) return
    setError(''); setPending(targets)
  }
  async function mutate(restore = false) {
    if (working.current || (restore ? !undo : !pending.length)) return
    working.current = true; setBusy(true); setError('')
    try {
      if (restore) {
        const result = await api<{ count: number }>(`/${kind}/restore`, lang, { token: undo!.token })
        try { sessionStorage.removeItem(storageKey) } catch { /* 无存储权限时仍可在当前页面撤销。 */ }
        if (mounted.current) { setUndo(null); setRestored(result.count) }
      } else {
        const result = await api<Undo>(`/${kind}/delete`, lang, { ids: pending.map(item => item.id) })
        try { sessionStorage.setItem(storageKey, JSON.stringify(result)) } catch { /* 删除完成后仍在内存中保留撤销信息。 */ }
        if (mounted.current) { setUndo(result); setRestored(null); setPending([]); setSelection({ scope: scopeKey, ids: [] }) }
      }
      changed.current()
    } catch (value) { if (mounted.current) setError((value as Error).message) }
    finally { working.current = false; if (mounted.current) setBusy(false) }
  }
  return { kind, lang, pending, undo, busy, error, restored, selected, selectedItems, allSelected, available, toggle, toggleAll, request, mutate, close: () => { if (!working.current) { setPending([]); setError('') } } }
}

export default function RecordDeletion({ manager }: { manager: ReturnType<typeof useRecordDeletion> }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancel = useRef<HTMLButtonElement>(null)
  const selectAll = useRef<HTMLInputElement>(null)
  const { lang, pending, undo, selected, busy, error, restored, kind } = manager
  const t = (key: Parameters<typeof translate>[1]) => translate(lang, key)
  const counted = (key: Parameters<typeof translate>[1], count: number) => t(key).replace('{count}', String(count)).replace('{plural}', count === 1 ? '' : 's')
  useEffect(() => { if (pending.length) { dialog.current?.showModal(); cancel.current?.focus() } }, [pending])
  useEffect(() => { if (selectAll.current) selectAll.current.indeterminate = selected.size > 0 && !manager.allSelected }, [selected.size, manager.allSelected])
  return <>
    <div className="record-management"><label><input ref={selectAll} type="checkbox" checked={manager.allSelected} disabled={busy || !manager.available.length} onChange={manager.toggleAll}/>{t('selectCurrentPage')}</label><span>{t('selectedCount').replace('{count}', String(selected.size))}</span><button className="button secondary delete-button" disabled={busy || !selected.size} onClick={() => manager.request(manager.selectedItems)}><Trash2 size={14}/>{t('deleteSelected')}</button></div>
    {(undo || restored !== null) && <div className="deletion-notice" role="status"><span>{undo ? counted('recordsDeleted', undo.count) : counted('recordsRestored', restored ?? 0)}</span>{undo && <button className="text-button" disabled={busy} onClick={() => manager.mutate(true)}><RotateCcw size={14}/>{t('undoDelete')}</button>}</div>}
    {error && !pending.length && <div className="error-message" role="alert">{error}</div>}
    {pending.length > 0 && <dialog ref={dialog} className="settings-dialog delete-dialog" aria-labelledby="delete-title" aria-describedby="delete-description" onCancel={event => { event.preventDefault(); manager.close() }}>
      <div className="dialog-heading"><h2 id="delete-title">{counted(kind === 'analyses' ? 'deleteAnalysesTitle' : 'deleteScansTitle', pending.length)}</h2><button className="icon-button" disabled={busy} aria-label={t('close')} onClick={manager.close}><X size={20}/></button></div>
      <p id="delete-description">{t(kind === 'analyses' ? 'deleteAnalysesHint' : 'deleteScansHint')}</p><ul className="delete-targets">{pending.map(item => <li key={item.id}>{item.label}</li>)}</ul>
      {error && <div className="error-message" role="alert">{error}</div>}
      <div className="heading-actions"><button ref={cancel} className="button secondary" disabled={busy} onClick={manager.close}>{t('cancel')}</button><button className="button danger" disabled={busy} onClick={() => manager.mutate()}><Trash2 size={14}/>{t(busy ? 'deleting' : 'confirmDelete')}</button></div>
    </dialog>}
  </>
}
