import { NavLink, Outlet } from 'react-router-dom'
import { Breadcrumb } from './Breadcrumb'
import { ThemeToggle } from './ThemeToggle'
import { SearchLauncher } from '../search/SearchLauncher'
import { CoverageLine } from './CoverageLine'

/**
 * The shell owns all the chrome. No page renders its own header, and no page
 * links to a top-level index that is not in this nav — which is what stops a
 * route becoming unreachable from the home page.
 */

const NAV = [
  { to: '/players', label: 'Players' },
  { to: '/teams', label: 'Teams' },
  { to: '/seasons', label: 'Seasons' },
  { to: '/leaders', label: 'Leaders' },
  { to: '/draft', label: 'Draft' },
  { to: '/finder', label: 'Finder' },
]

export function AppShell() {
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-40 border-b border-line bg-page/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1280px] items-center gap-4 px-4 py-2.5 sm:px-6">
          <NavLink to="/" className="shrink-0 text-[15px] font-semibold tracking-tight no-underline">
            Gridiron
          </NavLink>
          <nav className="hidden min-w-0 flex-1 items-center gap-1 md:flex">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  [
                    'motion-state relative px-2 py-1 text-[13px] no-underline',
                    isActive ? 'text-ink' : 'text-ink-2 hover:text-ink',
                  ].join(' ')
                }
              >
                {({ isActive }) => (
                  <>
                    {item.label}
                    {/* The current item is a 2px bar, never a filled pill. */}
                    {isActive ? (
                      <span className="absolute inset-x-2 -bottom-[11px] h-[2px] bg-accent" />
                    ) : null}
                  </>
                )}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-1">
            <SearchLauncher />
            <ThemeToggle />
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto border-t border-line px-4 py-1.5 md:hidden">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `motion-state whitespace-nowrap px-2 py-0.5 text-[12px] no-underline ${
                  isActive ? 'text-ink underline decoration-accent decoration-2 underline-offset-4' : 'text-ink-2'
                }`
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </header>

      <main className="mx-auto w-full max-w-[1280px] flex-1 px-4 py-4 sm:px-6">
        <Breadcrumb />
        <Outlet />
      </main>

      <footer className="mt-8 border-t border-line px-4 py-4 text-[11px] leading-4 text-ink-3 sm:px-6">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-x-3 gap-y-1">
          <CoverageLine />
          <a href="https://nflverse.com" target="_blank" rel="noreferrer" className="no-underline hover:underline">
            Data from nflverse
          </a>
        </div>
      </footer>
    </div>
  )
}
