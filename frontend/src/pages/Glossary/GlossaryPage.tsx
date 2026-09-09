import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { useCoverageQuery } from '../../api/endpoints'
import { PageHeader, Segmented } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'

/**
 * Every stat and dataset this product uses, in one searchable, anchored list.
 *
 * There is no `/api/glossary` endpoint wired up yet — `backend/app/glossary.py`
 * exists but no router exposes it, and the OpenAPI schema for `/api/search`
 * and `/api/coverage` is untyped besides. Rather than invent stat definitions
 * client-side, this page is built from what genuinely has a live source
 * (every loaded dataset, from `/api/coverage`) plus the metrics this product
 * calculates itself, documented once and cross-linked from `/about/data`.
 * When a real glossary endpoint ships, the "Metrics" list below moves there.
 */

interface DatasetCoverage {
  id: string
  name: string
  description: string
  season_min: number | null
  season_max: number | null
  source_url: string
  coverage_note: string | null
}

interface CoverageWindow {
  first_season: number
}

interface CoverageData {
  datasets: DatasetCoverage[]
  coverage_windows: Record<string, CoverageWindow | undefined>
}

interface Entry {
  id: string
  label: string
  abbr?: string
  category: 'metric' | 'dataset'
  definition: string
  formula?: string
  source: string
  window?: string
}

/** Static except the `started-proxy` window, which is read from live coverage. */
function buildMetrics(windows: Record<string, CoverageWindow | undefined>): Entry[] {
  return [
  {
    id: 'epa',
    label: 'Expected Points Added',
    abbr: 'EPA',
    category: 'metric',
    definition: 'The change in expected points from before a play to after it.',
    source: "nflfastR's open expected-points model",
    window: 'full coverage from the play-level floor',
  },
  {
    id: 'wpa',
    label: 'Win Probability Added',
    abbr: 'WPA',
    category: 'metric',
    definition: 'The change in home win probability from before a play to after it.',
    source: "nflfastR's open win-probability model",
    window: 'full coverage from the play-level floor',
  },
  {
    id: 'success-rate',
    label: 'Success rate',
    category: 'metric',
    definition:
      'Share of plays gaining at least 40% of yards to go on 1st down, 60% on 2nd, or the full distance on 3rd/4th — not simply a positive-EPA play.',
    source: "nflfastR's open model",
    window: 'full coverage from the play-level floor',
  },
  {
    id: 'cpoe',
    label: 'Completion % Over Expected',
    abbr: 'CPOE',
    category: 'metric',
    definition: "A passer's actual completion percentage minus the model's expected completion percentage.",
    source: "nflfastR's open model",
    window: 'requires charted air yards',
  },
  {
    id: 'srs',
    label: 'Simple Rating System',
    abbr: 'SRS',
    category: 'metric',
    definition: 'Margin of victory adjusted for strength of schedule, solved iteratively across a season.',
    formula: 'SRS = MOV + mean(opponent SRS), re-centred to a league mean of zero each pass.',
    source: 'Computed by Gridiron',
    window: 'regular season only',
  },
  {
    id: 'osrs',
    label: 'Offensive SRS',
    abbr: 'OSRS',
    category: 'metric',
    definition: "A team's scoring offence adjusted for the defences it faced. OSRS + DSRS = SRS.",
    source: 'Computed by Gridiron',
  },
  {
    id: 'dsrs',
    label: 'Defensive SRS',
    abbr: 'DSRS',
    category: 'metric',
    definition: "A team's scoring defence adjusted for the offences it faced. Positive is a good defence.",
    source: 'Computed by Gridiron',
  },
  {
    id: 'sos',
    label: 'Strength of Schedule',
    abbr: 'SOS',
    category: 'metric',
    definition: 'The average SRS of the opponents a team actually played, one term per meeting.',
    formula: 'SOS = SRS − MOV',
    source: 'Computed by Gridiron',
  },
  {
    id: 'pythagorean',
    label: 'Pythagorean expected wins',
    category: 'metric',
    definition: "Expected win total from points scored and allowed, using PFR's fitted NFL exponent.",
    formula: 'games × PF^2.37 / (PF^2.37 + PA^2.37)',
    source: 'Computed by Gridiron',
  },
  {
    id: 'seeding',
    label: 'Playoff seed',
    category: 'metric',
    definition:
      "For a completed season, read off the postseason bracket where the bracket alone determines it; where it doesn't, the league's own tiebreakers (first five levels) pick among the remaining candidates. In-progress seeds are projected and labelled as such.",
    source: 'Computed by Gridiron',
  },
  {
    id: 'percentiles',
    label: 'Position percentile',
    category: 'metric',
    definition:
      "Share of a qualified cohort — same position group, same season, meeting that season's own volume qualifier — at or below this player's value.",
    source: 'Computed by Gridiron',
  },
  {
    id: 'similarity',
    label: 'Similar players',
    category: 'metric',
    definition:
      "Cosine similarity over each player's z-scored career stat vector within their position group. Our own method — not PFR's Approximate Value similarity.",
    formula: 'method: normalized-career-vector-cosine-v1',
    source: 'Computed by Gridiron',
  },
  {
    id: 'started-proxy',
    label: 'Started (proxy)',
    category: 'metric',
    definition: 'Snap share of 50% or higher, standing in for an official starter designation nflverse does not carry.',
    source: 'Computed by Gridiron',
    window: windows.snap_counts?.first_season ? `snap counts from ${windows.snap_counts.first_season}` : undefined,
  },
  {
    id: 'fantasy',
    label: 'Fantasy points',
    category: 'metric',
    definition:
      'Standard: 1 pt / 25 passing yds, 4 / passing TD, −2 / INT, 1 pt / 10 rushing or receiving yds, 6 / rushing or receiving TD. PPR adds 1 pt / reception, Half-PPR adds 0.5.',
    source: 'Computed by Gridiron from box-score counting stats',
  },
  {
    id: 'allowed-side',
    label: 'Allowed-side team stats',
    category: 'metric',
    definition:
      "A team's defence summed from its opponents' offensive rows in the games it actually played — nflverse's own def_* columns are production (sacks, INTs), not yards or points allowed.",
    source: 'Computed by Gridiron, self-join of team-week data',
  },
  {
    id: 'drives',
    label: 'Drive start / end field position',
    category: 'metric',
    definition: 'Yards from the possessing team\'s own goal line (0–100), parsed from the source\'s text yard line.',
    source: 'Computed by Gridiron',
  },
  {
    id: 'pf-pa',
    label: 'Points For / Points Against',
    abbr: 'PF / PA',
    category: 'metric',
    definition: 'Regular-season points scored and allowed.',
    source: 'games.csv',
  },
  {
    id: 'win-pct',
    label: 'Win percentage',
    abbr: 'Pct',
    category: 'metric',
    definition: 'Written as a three-decimal fraction, football-style (.625), not a percentage.',
    formula: '(wins + 0.5 × ties) / games played',
    source: 'games.csv',
  },
  {
    id: 'w-av',
    label: 'Weighted career Approximate Value',
    abbr: 'w_av',
    category: 'metric',
    definition:
      "Pro-Football-Reference's own weighted career AV figure, read directly from the draft file — drafted players only. PFR's per-season and total career AV (car_av) are not present in any nflverse file, so we do not show or estimate them.",
    source: 'draft_picks.parquet (PFR)',
  },
  ]
}

export function GlossaryPage() {
  const coverage = useCoverageQuery()
  const cov = coverage.data as CoverageData | undefined
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<'all' | 'metric' | 'dataset'>('all')

  const metrics = useMemo(() => buildMetrics(cov?.coverage_windows ?? {}), [cov])

  const datasetEntries: Entry[] = useMemo(
    () =>
      (cov?.datasets ?? []).map((d) => ({
        id: `dataset-${d.id}`,
        label: d.name,
        category: 'dataset' as const,
        definition: d.description,
        source: d.source_url,
        window: d.season_min && d.season_max ? `${d.season_min}–${d.season_max}` : (d.coverage_note ?? undefined),
      })),
    [cov],
  )

  const all = useMemo(() => [...metrics, ...datasetEntries], [metrics, datasetEntries])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return all.filter((entry) => {
      if (category !== 'all' && entry.category !== category) return false
      if (!q) return true
      return (
        entry.label.toLowerCase().includes(q) ||
        entry.abbr?.toLowerCase().includes(q) ||
        entry.definition.toLowerCase().includes(q)
      )
    })
  }, [all, query, category])

  useAnchorScroll(!coverage.isLoading)

  return (
    <div>
      <PageHeader
        title="Glossary"
        meta="Every stat and dataset this product uses — definition, formula where one exists, source and coverage window."
        action={
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-3" />
            <input
              type="text"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search the glossary"
              className="motion-state w-52 rounded-md border border-line bg-raised py-1.5 pl-8 pr-2.5 text-[13px] outline-none placeholder:text-ink-3 focus:border-accent focus:ring-2 focus:ring-accent/30"
            />
          </div>
        }
      />

      <p className="mt-3 text-[11px] leading-4 text-ink-3">
        A dedicated glossary API is not wired up yet, so this page is built from the live dataset registry plus the
        metrics Gridiron calculates itself — the same formulas documented in full on{' '}
        <Link to="/about/data#computed" className="no-underline hover:text-accent hover:underline">
          Data &amp; methods
        </Link>
        . Column-level definitions for individual raw stats will move here once that endpoint ships.
      </p>

      <div className="mt-4">
        <Segmented
          ariaLabel="Filter by category"
          value={category}
          onChange={setCategory}
          options={[
            { value: 'all', label: `All · ${all.length}` },
            { value: 'metric', label: `Metrics · ${metrics.length}` },
            { value: 'dataset', label: `Datasets · ${datasetEntries.length}` },
          ]}
        />
      </div>

      <QueryBoundary
        isLoading={coverage.isLoading}
        error={coverage.error}
        onRetry={coverage.refetch}
        isEmpty={!coverage.isLoading && !filtered.length}
        emptyMessage={query ? `Nothing matches "${query}".` : 'Nothing in this category.'}
      >
        <dl className="mt-4 divide-y divide-row-rule">
          {filtered.map((entry) => (
            <div key={entry.id} id={entry.id} className="scroll-mt-16 py-3">
              <dt className="flex flex-wrap items-baseline gap-x-2">
                <span className="text-[13px] font-medium text-ink">{entry.label}</span>
                {entry.abbr ? <span className="text-[11px] text-ink-3">{entry.abbr}</span> : null}
              </dt>
              <dd className="mt-0.5 text-[12px] leading-5 text-ink-2">{entry.definition}</dd>
              {entry.formula ? (
                <dd className="mt-1 font-mono text-[11px] leading-4 text-ink-3">{entry.formula}</dd>
              ) : null}
              <dd className="mt-1 text-[11px] text-ink-3">
                {entry.source.startsWith('http') ? (
                  <a href={entry.source} target="_blank" rel="noreferrer" className="no-underline hover:text-accent hover:underline">
                    source
                  </a>
                ) : (
                  entry.source
                )}
                {entry.window ? ` · ${entry.window}` : ''}
              </dd>
            </div>
          ))}
        </dl>
      </QueryBoundary>
    </div>
  )
}
