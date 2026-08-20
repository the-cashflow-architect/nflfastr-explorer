import { useEffect } from 'react'

interface KeyboardShortcutProps {
  onSearch: () => void
  onEscape: () => void
}

/**
 * Cmd/Ctrl+C and Cmd/Ctrl+T used to be bound to app actions here, silently
 * fighting the browser's own copy and new-tab shortcuts. Kept to the small
 * set of bindings that don't collide with anything the browser already owns.
 */
export function useKeyboardShortcuts({ onSearch, onEscape }: KeyboardShortcutProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC')
      const modKey = isMac ? e.metaKey : e.ctrlKey

      if (modKey && e.key === 'k') {
        e.preventDefault()
        onSearch()
      }

      if (e.key === 'Escape') {
        onEscape()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onSearch, onEscape])
}
