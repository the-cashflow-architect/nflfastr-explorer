import { useEffect, useRef } from 'react'

/** Scrolls a deep-linked anchor into view once its content has rendered. */
export function useAnchorScroll(ready: boolean) {
  const done = useRef(false)
  useEffect(() => {
    if (!ready || done.current) return
    const hash = window.location.hash.slice(1)
    if (!hash) return
    const target = document.getElementById(hash)
    if (target) {
      target.scrollIntoView({ block: 'center' })
      done.current = true
    }
  }, [ready])
}
