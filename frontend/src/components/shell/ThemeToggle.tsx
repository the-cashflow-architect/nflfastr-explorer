import { Monitor, Moon, Sun } from 'lucide-react'
import { useState } from 'react'
import { getTheme, setTheme, type ThemeChoice } from '../../design/theme'

const ORDER: ThemeChoice[] = ['system', 'light', 'dark']
const ICON = { system: Monitor, light: Sun, dark: Moon }
const LABEL = { system: 'Match system', light: 'Light', dark: 'Dark' }

export function ThemeToggle() {
  const [choice, setChoice] = useState<ThemeChoice>(getTheme)
  const Icon = ICON[choice]
  return (
    <button
      type="button"
      title={`Appearance: ${LABEL[choice]}`}
      aria-label={`Appearance: ${LABEL[choice]}. Click to change.`}
      onClick={() => {
        const next = ORDER[(ORDER.indexOf(choice) + 1) % ORDER.length]
        setChoice(next)
        setTheme(next)
      }}
      className="motion-state rounded p-1.5 text-ink-3 hover:text-ink"
    >
      <Icon className="h-4 w-4" />
    </button>
  )
}
