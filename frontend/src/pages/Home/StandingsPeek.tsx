import { ChevronRight } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { Standings } from '../../api/endpoints'
import { TeamLink } from '../../components/ui/EntityLink'
import { getCollapsed, setCollapsed } from '../../design/theme'
import { record } from '../../design/format'

const PAGE_KEY = 'home'
const SECTION_KEY = 'standings-full'
const CONFERENCES = ['AFC', 'NFC'] as const

/**
 * Division leaders and records only — no seeds. Seeds are a derived read of
 * the postseason bracket (or a projection mid-season) and that derivation
 * deserves its own labelled home on /seasons/:season/standings, not a
 * five-second homepage glance.
 *
 * "Peek" means the leaders are visible without a click; "Full standings"
 * expands the rest of each division in place, no navigation.
 */
export function StandingsPeek({ season, standings }: { season: number; standings: Standings }) {
  const [collapsed, setLocalCollapsed] = useState(() => getCollapsed(PAGE_KEY, SECTION_KEY, true))

  const toggle = () => {
    const next = !collapsed
    setLocalCollapsed(next)
    setCollapsed(PAGE_KEY, SECTION_KEY, next)
  }

  const teamCount = standings.groups.reduce((sum, group) => sum + group.teams.length, 0)

  return (
    <section className="mb-6">
      <div className="mb-2 flex items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold leading-5">
          Standings <span className="font-normal text-ink-3">· {season}</span>
        </h2>
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          className="motion-state flex items-center gap-1 text-[12px] text-ink-2 hover:text-accent"
        >
          {collapsed ? `Show all ${teamCount}` : 'Show leaders only'}
          <ChevronRight className={`h-3.5 w-3.5 transition-transform duration-200 ${collapsed ? '' : 'rotate-90'}`} />
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        {CONFERENCES.map((conf) => (
          <div key={conf} className="rounded-lg border border-line bg-raised p-3">
            <p className="mb-2 text-[11px] uppercase tracking-[0.04em] text-ink-3">{conf}</p>
            <div className="space-y-2.5">
              {standings.groups
                .filter((group) => group.conference === conf)
                .map((group) => (
                  <div key={group.label}>
                    <p className="mb-1 text-[11px] text-ink-3">{group.division ?? group.label}</p>
                    {group.teams
                      .filter((team) => !collapsed || team.division_rank === 1)
                      .map((team) => (
                        <div key={team.abbr} className="flex items-center justify-between py-0.5 text-[13px]">
                          <TeamLink
                            abbr={team.abbr}
                            season={season}
                            className={`no-underline hover:underline ${
                              team.division_rank === 1 ? 'font-semibold text-ink' : 'text-ink-2'
                            }`}
                          />
                          <span className="tabular-nums text-ink-2">{record(team.w, team.l, team.t)}</span>
                        </div>
                      ))}
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>

      <Link
        to={`/seasons/${season}/standings`}
        className="mt-2 inline-block text-[11px] text-ink-3 no-underline hover:text-accent hover:underline"
      >
        Full standings with seeds and tiebreak basis →
      </Link>
    </section>
  )
}
