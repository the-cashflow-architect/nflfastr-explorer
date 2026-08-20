import { Moon, Sun } from 'lucide-react'
import { useEffect, useState } from 'react'

type Theme = 'dark' | 'light'

const STORAGE_KEY = 'nflfastr-theme'

function getInitialTheme(): Theme {
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' ? 'light' : 'dark'
}

/** Toggles `data-theme` on <html>, which every `light:` utility class keys off. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(getInitialTheme)

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem(STORAGE_KEY, theme)
  }, [theme])

  return (
    <button
      type="button"
      onClick={() => setTheme((t) => (t === 'dark' ? 'light' : 'dark'))}
      title={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
      className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-white/10 light:border-slate-200 bg-slate-900/60 light:bg-white text-slate-300 light:text-slate-500 transition hover:text-white light:hover:text-slate-900"
    >
      {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  )
}
