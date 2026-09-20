import type { ReactNode } from 'react'
import { reportHref } from './routes'

export default function ReportLink({ id, from, onOpen, children }: { id: string; from: string; onOpen: () => void; children: ReactNode }) {
  return <a className="text-button" href={reportHref(id, from)} onClick={event => {
    if (event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return
    event.preventDefault(); onOpen()
  }}>{children}</a>
}
