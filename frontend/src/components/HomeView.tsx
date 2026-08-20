import { Activity, ChevronRight, Shield, Users } from 'lucide-react'
import type { DatasetSummary } from '../types'
import type { Route } from '../hooks/useUrlState'
import type { StatTab } from '../lib/statViews'
import { TEAM_CODES, TEAM_NAMES } from '../lib/teams'

export interface NavOptions {
  position?: string
  statTab?: StatTab
  team?: string
  teamMode?: 'offense' | 'defense'
}

interface HomeViewProps {
  datasets: DatasetSummary[] | undefined
  onNavigate: (route: Route, opts?: NavOptions) => void
}

function rowCount(datasets: DatasetSummary[] | undefined, id: string): string {
  const ds = datasets?.find((d) => d.id === id)
  if (!ds || ds.row_count == null) return 'loading…'
  return `${ds.row_count.toLocaleString()} rows`
}

const QUICK_LINKS: { label: string; route: Route; opts: NavOptions }[] = [
  { label: 'Passing Leaders', route: 'players', opts: { position: 'qb', statTab: 'basic' } },
  { label: 'Rushing Leaders', route: 'players', opts: { position: 'rb', statTab: 'basic' } },
  { label: 'Receiving Leaders', route: 'players', opts: { position: 'wr', statTab: 'basic' } },
  { label: 'Team Offense', route: 'teams', opts: { teamMode: 'offense' } },
  { label: 'Team Defense', route: 'teams', opts: { teamMode: 'defense' } },
]

export function HomeView({ datasets, onNavigate }: HomeViewProps) {
  return (
    <div className="mx-auto w-full max-w-[1200px] px-4 py-10 lg:px-6">
      <div className="mb-10 text-center">
        <h1 className="text-3xl font-bold tracking-tight text-white sm:text-4xl">nflfastR Explorer</h1>
        <p className="mx-auto mt-3 max-w-xl text-slate-400">
          Player box scores, team totals, and play-by-play data from nflverse — 2022 to today.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <HomeCard
          icon={<Users className="h-6 w-6" />}
          title="Players"
          description="Game logs and season totals for every player — passing, rushing, receiving, defense, kicking, and punting."
          meta={rowCount(datasets, 'player_weekly')}
          onClick={() => onNavigate('players')}
        />
        <HomeCard
          icon={<Shield className="h-6 w-6" />}
          title="Teams"
          description="League-wide offense and defense totals by team, ranked and ready to compare."
          meta="32 teams"
          onClick={() => onNavigate('teams')}
        />
        <HomeCard
          icon={<Activity className="h-6 w-6" />}
          title="Plays"
          description="Individual plays filtered by down, distance, field position, and situation."
          meta={rowCount(datasets, 'play_by_play')}
          onClick={() => onNavigate('plays')}
        />
      </div>

      <div className="mt-10">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Quick Links</h2>
        <div className="flex flex-wrap gap-2">
          {QUICK_LINKS.map((link) => (
            <button
              key={link.label}
              type="button"
              onClick={() => onNavigate(link.route, link.opts)}
              className="rounded-xl border border-white/10 bg-slate-900/50 px-4 py-2.5 text-sm font-medium text-slate-200 transition-all duration-150 hover:bg-slate-800/80 hover:ring-1 hover:ring-blue-400/30"
            >
              {link.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-10">
        <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500">Jump to a Team</h2>
        <div className="grid grid-cols-4 gap-2 sm:grid-cols-8">
          {TEAM_CODES.map((code) => (
            <button
              key={code}
              type="button"
              title={TEAM_NAMES[code]}
              onClick={() => onNavigate('players', { team: code, position: 'all', statTab: 'basic' })}
              className="rounded-lg border border-white/10 bg-slate-900/40 py-2.5 text-center text-xs font-semibold text-slate-300 transition-all duration-150 hover:bg-slate-800/80 hover:text-white hover:ring-1 hover:ring-blue-400/30"
            >
              {code}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function HomeCard({
  icon,
  title,
  description,
  meta,
  onClick,
}: {
  icon: React.ReactNode
  title: string
  description: string
  meta: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group flex flex-col items-start rounded-2xl border border-white/10 bg-slate-900/50 p-6 text-left transition-all duration-200 hover:-translate-y-0.5 hover:bg-slate-900/70 hover:shadow-xl hover:shadow-black/20 hover:ring-1 hover:ring-blue-400/30"
    >
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-emerald-500 text-white shadow-lg shadow-blue-500/20">
        {icon}
      </div>
      <h3 className="flex items-center gap-1.5 text-lg font-semibold text-white">
        {title}
        <ChevronRight className="h-4 w-4 text-slate-500 transition-transform duration-200 group-hover:translate-x-0.5 group-hover:text-blue-400" />
      </h3>
      <p className="mt-1.5 text-sm leading-relaxed text-slate-400">{description}</p>
      <span className="mt-4 text-xs font-medium text-slate-500">{meta}</span>
    </button>
  )
}
