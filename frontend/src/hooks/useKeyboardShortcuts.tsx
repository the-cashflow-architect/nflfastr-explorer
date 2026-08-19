import { useEffect } from 'react'

interface KeyboardShortcutProps {
  onToggleCompare: () => void
  onExport: () => void
  onSearch: () => void
  onCycleViewMode: (index: number) => void
  onToggleChart: () => void
}

export function useKeyboardShortcuts({
  onToggleCompare,
  onExport,
  onSearch,
  onCycleViewMode,
  onToggleChart,
}: KeyboardShortcutProps) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().includes('MAC')
      const modKey = isMac ? e.metaKey : e.ctrlKey

      // Cmd/Ctrl + K: Focus search or toggle compare
      if (modKey && e.key === 'k') {
        e.preventDefault()
        onSearch()
      }

      // Cmd/Ctrl + E: Export
      if (modKey && e.key === 'e') {
        e.preventDefault()
        onExport()
      }

      // Cmd/Ctrl + 1-3: Cycle view modes
      if (modKey && e.key >= '1' && e.key <= '3') {
        e.preventDefault()
        onCycleViewMode(Number(e.key) - 1)
      }

      // Cmd/Ctrl + C: Toggle to Compare view
      if (modKey && (e.key === 'c' || e.key === 'C')) {
        e.preventDefault()
        onToggleCompare()
      }

      // Cmd/Ctrl + T: Toggle chart/table
      if (modKey && e.key === 't') {
        e.preventDefault()
        onToggleChart()
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onToggleCompare, onExport, onSearch, onCycleViewMode, onToggleChart])
}

export function KeyboardShortcutHelp() {
  const isMac = navigator.platform.toUpperCase().includes('MAC')
  const mod = isMac ? 'Cmd' : 'Ctrl'

  return (
    <div className="text-xs text-slate-500">
      <span className="hidden sm:inline">
        {mod}+E Export | {mod}+C Compare | {mod}+K Search | {mod}+T Chart
      </span>
    </div>
  )
}