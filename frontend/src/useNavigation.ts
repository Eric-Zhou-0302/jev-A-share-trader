import { useCallback, useEffect, useRef, useState } from 'react'
import { parseRoute } from './routes'

interface NavigationState { key: string; scroll: number; returnScroll: number }
interface Options { replace?: boolean; scroll?: number; returnScroll?: number }
const readLocation = () => ({ hash: window.location.hash || '#/analysis', state: (window.history.state?.jevNavigation ?? { key: 'initial', scroll: 0, returnScroll: 0 }) as NavigationState })

export function useNavigation() {
  const [location, setLocation] = useState(readLocation)
  const restored = useRef('')
  const current = useRef(location)
  current.current = location
  useEffect(() => {
    const old = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    const changed = () => {
      const next = readLocation()
      setLocation(previous => previous.hash === next.hash && previous.state.key === next.state.key ? previous : next)
    }
    const saveScroll = () => {
      if (restored.current !== current.current.state.key) return
      const state = window.history.state?.jevNavigation ?? current.current.state
      window.history.replaceState({ ...window.history.state, jevNavigation: { ...state, scroll: window.scrollY } }, '')
    }
    window.addEventListener('popstate', changed)
    window.addEventListener('hashchange', changed)
    window.addEventListener('scroll', saveScroll, { passive: true })
    return () => {
      window.history.scrollRestoration = old
      window.removeEventListener('popstate', changed)
      window.removeEventListener('hashchange', changed)
      window.removeEventListener('scroll', saveScroll)
    }
  }, [])
  const navigate = useCallback((hash: string, options: Options = {}) => {
    const state: NavigationState = { key: crypto.randomUUID(), scroll: options.scroll ?? 0, returnScroll: options.returnScroll ?? 0 }
    const oldState = window.history.state?.jevNavigation ?? current.current.state
    window.history.replaceState({ ...window.history.state, jevNavigation: { ...oldState, scroll: window.scrollY } }, '')
    window.history[options.replace ? 'replaceState' : 'pushState']({ jevNavigation: state }, '', hash)
    setLocation(readLocation())
  }, [])
  const onReady = useCallback(() => {
    const { key, scroll } = location.state
    if (restored.current === key) return
    requestAnimationFrame(() => {
      if (current.current.state.key !== key || restored.current === key) return
      restored.current = key
      window.scrollTo(0, scroll)
    })
  }, [location.state])
  return { ...location, route: parseRoute(location.hash), navigate, onReady }
}
