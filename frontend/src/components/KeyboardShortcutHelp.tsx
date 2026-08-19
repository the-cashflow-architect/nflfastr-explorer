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