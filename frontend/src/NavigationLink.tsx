import type { ReactNode } from 'react'

export default function NavigationLink({ href, onOpen, children, className }: { href: string; onOpen: () => void; children: ReactNode; className?: string }) {
  return <a href={href} className={className} onClick={event => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault(); onOpen()
  }}>{children}</a>
}
