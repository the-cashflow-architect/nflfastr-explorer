import { QueryClient, QueryClientProvider, useQuery } from '@tanstack/react-query'
import { Activity, Sparkles } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { fetchDatasets } from './api'
import { Breadcrumb, type Crumb } from './components/Breadcrumb'
import { HomeView, type NavOptions } from './components/HomeView'
import { KeyboardShortcutHelp } from './components/KeyboardShortcutHelp'
import { PlayersExplorer } from './components/PlayersExplorer'
import { PlaysExplorer } from './components/PlaysExplorer'
import { TeamsExplorer } from './components/TeamsExplorer'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useUrlState, type Route } from './hooks/useUrlState'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
})

const ROUTE_LABEL: Record<Route, string> = {
  players: 'Players',
  teams: 'Teams',
  plays: 'Plays',
}

function ExplorerApp() {
  const { urlState, isRestoring, updateUrl, getShareableUrl, clearUrl } = useUrlState()

  const [route, setRoute] = useState<Route | 'home'>(urlState?.route ?? 'home')
  const [navOpts, setNavOpts] = useState<NavOptions | null>(null)
  const [detailPlayer, setDetailPlayer] = useState<string | null>(null)

  // A URL opened after the app already mounted (back/forward navigation)
  // updates the route to match.
  useEffect(() => {
    if (urlState?.route) setRoute(urlState.route)
  }, [urlState])

  const { data: datasets } = useQuery({ queryKey: ['datasets'], queryFn: fetchDatasets })

  const navigate = useCallback((next: Route, opts?: NavOptions) => {
    setRoute(next)
    setNavOpts(opts ?? null)
    setDetailPlayer(null)
  }, [])

  const goHome = useCallback(() => {
    setRoute('home')
    setNavOpts(null)
    setDetailPlayer(null)
    clearUrl()
  }, [clearUrl])

  useKeyboardShortcuts({
    onSearch: () => {
      (document.querySelector('input[placeholder*="Search"]') as HTMLInputElement | null)?.focus()
    },
    onEscape: () => {
      if (detailPlayer) setDetailPlayer(null)
      else if (route !== 'home') goHome()
    },
  })

  const crumbs: Crumb[] = (() => {
    if (route === 'home') return [{ label: 'Home' }]
    const trail: Crumb[] = [
      { label: 'Home', onClick: goHome },
      {
        label: ROUTE_LABEL[route],
        onClick: detailPlayer ? () => setDetailPlayer(null) : undefined,
      },
    ]
    if (detailPlayer) trail.push({ label: detailPlayer })
    return trail
  })()

  return (
    <div className="flex h-full flex-col">
      <header className="border-b border-white/10 bg-slate-950/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-4 lg:px-6">
          <button type="button" onClick={goHome} className="flex items-center gap-3 text-left">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 shadow-lg shadow-blue-500/20">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight text-white">nflfastR Explorer</h1>
              <p className="text-xs text-slate-400">nflverse data · smart filters · stat glossary</p>
            </div>
          </button>
          <div className="hidden items-center gap-4 text-xs text-slate-400 md:flex">
            <span className="inline-flex items-center gap-1.5">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              Live nflverse
            </span>
            <KeyboardShortcutHelp />
          </div>
        </div>
        {route !== 'home' ? (
          <div className="mx-auto max-w-[1600px] px-4 pb-3 lg:px-6">
            <Breadcrumb trail={crumbs} />
          </div>
        ) : null}
      </header>

      <main className="mx-auto flex w-full max-w-[1600px] flex-1 gap-4 overflow-hidden p-4 lg:p-6">
        {route === 'home' ? (
          <div className="w-full overflow-auto">
            <HomeView datasets={datasets} onNavigate={navigate} />
          </div>
        ) : route === 'players' ? (
          <PlayersExplorer
            navOpts={navOpts}
            detailPlayer={detailPlayer}
            setDetailPlayer={setDetailPlayer}
            urlState={urlState}
            isRestoring={isRestoring}
            updateUrl={updateUrl}
            getShareableUrl={getShareableUrl}
          />
        ) : route === 'teams' ? (
          <TeamsExplorer navOpts={navOpts} onDrillToTeam={(team) => navigate('players', { team, position: 'all', statTab: 'basic' })} />
        ) : (
          <PlaysExplorer urlState={urlState} isRestoring={isRestoring} updateUrl={updateUrl} getShareableUrl={getShareableUrl} />
        )}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ExplorerApp />
    </QueryClientProvider>
  )
}
