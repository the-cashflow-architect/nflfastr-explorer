import { useCoverageQuery, useStandings } from '../../api/endpoints'
import { PageHeader } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'
import { gameDate, num, plural } from '../../design/format'

/**
 * The page where the product tells the truth about itself.
 *
 * Everything on it is either read straight from /api/coverage — the server's
 * actual load log, never a copy-pasted year — or, for the handful of numbers
 * this product calculates itself, the exact formula. Section 3 of the build
 * spec is explicit that this page has no CTA: it is a reference document, not
 * a funnel, so it carries no PrimaryAction.
 */

interface DatasetCoverage {
  id: string
  name: string
  description: string
  source_url: string
  season_min: number | null
  season_max: number | null
  row_count: number
  loaded_at: string
  coverage_note: string | null
  status: string
}

interface CoverageWindow {
  first_season: number
  note: string
}

interface NotBuildingItem {
  what: string
  why: string
}

interface CoverageData {
  datasets: DatasetCoverage[]
  coverage_windows: Record<string, CoverageWindow | undefined>
  not_building: NotBuildingItem[]
  disk_usage_bytes: number
  latest_completed_season: number | null
  latest_season_with_games: number | null
  generated_at: string
}

export function AboutDataPage() {
  const coverage = useCoverageQuery()
  const cov = coverage.data as CoverageData | undefined
  // The SRS/SOS/Pythagorean/seeding formulas below are quoted from the same
  // season-standings endpoint every team page calls, rather than retyped here
  // by hand — a paraphrase is exactly the kind of thing that drifts silently
  // from what the backend actually does.
  const formulaSeason = cov?.latest_completed_season ?? undefined
  const standings = useStandings(formulaSeason)

  // Every block on this page is a link target from elsewhere in the product
  // (ComputedByUs markers, "our method" links) — wait for both queries so the
  // anchor lands on content that actually rendered, not a still-loading page.
  useAnchorScroll(!coverage.isLoading && !!cov && !standings.isLoading)

  return (
    <div>
      <PageHeader
        title="Data & methods"
        meta="What Gridiron holds, where it comes from, what it deliberately does not have, and the formula behind every number we calculate ourselves."
      />

      <QueryBoundary
        isLoading={coverage.isLoading}
        error={coverage.error}
        onRetry={coverage.refetch}
        isEmpty={!cov}
        emptyMessage="Coverage data is not available right now."
      >
        {cov ? (
          <>
            <p className="mt-4 text-[13px] leading-5 text-ink-2">
              Our play-level data starts in {cov.coverage_windows.stats?.first_season ?? 'the modern era'} and does
              not pretend otherwise. The reference site we are built to replace covers a century; we cover the
              modern era exactly, and we say so on every leaderboard rather than blur the boundary. Below is
              everything that boundary actually means: every dataset loaded, every window it starts in, everything
              we chose not to build and why, and the full formula for every figure this product calculates rather
              than reads.
            </p>

            <DatasetTable datasets={cov.datasets} generatedAt={cov.generated_at} diskBytes={cov.disk_usage_bytes} />
            <NotBuildingSection items={cov.not_building} />
            <FormulasSection
              formulas={standings.data?.formulas}
              formulaSeason={formulaSeason}
              windows={cov.coverage_windows}
              latestSeason={cov.latest_completed_season}
            />
            <ModelSection windows={cov.coverage_windows} latestSeason={cov.latest_completed_season} />
          </>
        ) : null}
      </QueryBoundary>
    </div>
  )
}

function DatasetTable({
  datasets,
  generatedAt,
  diskBytes,
}: {
  datasets: DatasetCoverage[]
  generatedAt: string
  diskBytes: number
}) {
  return (
    <section id="datasets" className="mt-8 scroll-mt-16">
      <h2 className="mb-1 text-[15px] font-semibold leading-5">What we hold</h2>
      <p className="mb-3 text-[11px] text-ink-3">
        Live from the last data load, generated {gameDate(generatedAt)} · {plural(datasets.length, 'dataset')} ·{' '}
        {(diskBytes / 1_000_000).toFixed(0)} MB on disk
      </p>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-line-strong text-left text-[11px] font-semibold uppercase tracking-[0.03em] text-ink-2">
              <th className="px-2 py-1.5">Dataset</th>
              <th className="px-2 py-1.5">Season window</th>
              <th className="px-2 py-1.5 text-right">Rows</th>
              <th className="px-2 py-1.5">Last refreshed</th>
              <th className="px-2 py-1.5">Note</th>
            </tr>
          </thead>
          <tbody>
            {datasets.map((d) => (
              <tr key={d.id} className="border-b border-row-rule align-top">
                <td className="px-2 py-1.5">
                  <a
                    href={d.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-ink no-underline hover:text-accent hover:underline"
                  >
                    {d.name}
                  </a>
                  <p className="mt-0.5 text-[11px] leading-4 text-ink-3">{d.description}</p>
                </td>
                <td className="px-2 py-1.5 whitespace-nowrap tabular-nums">
                  {d.season_min && d.season_max ? `${d.season_min}–${d.season_max}` : '—'}
                </td>
                <td className="px-2 py-1.5 text-right tabular-nums">{num(d.row_count)}</td>
                <td className="px-2 py-1.5 whitespace-nowrap tabular-nums">{gameDate(d.loaded_at)}</td>
                <td className="px-2 py-1.5 text-[12px] text-ink-2">{d.coverage_note ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function NotBuildingSection({ items }: { items: NotBuildingItem[] }) {
  if (!items.length) return null
  return (
    <section id="not-building" className="mt-8 scroll-mt-16">
      <h2 className="mb-1 text-[15px] font-semibold leading-5">What we do not have</h2>
      <p className="mb-3 text-[11px] text-ink-3">
        Each of these was a deliberate decision, not an oversight — the reason is the point.
      </p>
      <dl className="space-y-3">
        {items.map((item) => (
          <div key={item.what} className="border-b border-row-rule pb-3">
            <dt className="text-[13px] font-medium text-ink">{item.what}</dt>
            <dd className="mt-0.5 text-[12px] leading-5 text-ink-2">{item.why}</dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

interface ComputedMetric {
  id: string
  label: string
  formula: string
  limitation?: string
}

function FormulasSection({
  formulas,
  formulaSeason,
  windows,
  latestSeason,
}: {
  formulas: Record<string, string> | undefined
  formulaSeason: number | undefined
  windows: Record<string, CoverageWindow | undefined>
  latestSeason: number | null
}) {
  const statsFrom = windows.stats?.first_season
  const era = statsFrom && latestSeason ? `${statsFrom}–${latestSeason}, regular season only` : 'modern era'

  const ratingMetrics: ComputedMetric[] = formulas
    ? [
        { id: 'srs', label: 'SRS — Simple Rating System', formula: formulas.srs, limitation: `Solved for ${era}.` },
        { id: 'osrs', label: 'OSRS — Offensive SRS', formula: formulas.osrs },
        { id: 'dsrs', label: 'DSRS — Defensive SRS', formula: formulas.dsrs },
        { id: 'sos', label: 'SOS — Strength of Schedule', formula: formulas.sos },
        { id: 'mov', label: 'MOV — Margin of Victory', formula: formulas.mov },
        {
          id: 'pythagorean',
          label: 'Pythagorean expected wins',
          formula: formulas.pythagorean_wins,
        },
        {
          id: 'seeding',
          label: 'Playoff seeding',
          formula: formulas.playoff_seed,
          limitation:
            'We implement the first five tiebreaker levels. Where a tie survives those five, the page says our rules could not break it rather than guessing an order.',
        },
      ].filter((m) => m.formula)
    : []

  const otherMetrics: ComputedMetric[] = [
    {
      id: 'allowed-side',
      label: 'Allowed-side team stats',
      formula:
        "For team T in season S, sum the offensive rows of T's opponents in the games T actually played — a self-join of team-week data. Points allowed comes from the schedule file. The team dataset's own def_* columns are what a defence produced (sacks, interceptions), never what it allowed.",
    },
    {
      id: 'percentiles',
      label: 'Position percentiles',
      formula:
        "A player's percentile is the share of a qualified cohort — same position group, same season, meeting that season's own volume qualifier (for example, the NFL's own attempts-per-team-game bar for quarterbacks) — at or below their value. The cohort size and qualifier are printed with every percentile strip so a thin cohort cannot pass for a wide one.",
    },
    {
      id: 'similarity',
      label: 'Similar players',
      formula:
        "Method normalized-career-vector-cosine-v1: each player's career rate and volume stats, within their position group, are z-scored against that cohort and compared by cosine similarity. It is our own method, published under its own name — not PFR's Approximate Value similarity, which is a different, proprietary formula we do not have the inputs to reproduce.",
      limitation:
        'Suppressed for position groups whose stat vector has fewer than four non-zero dimensions (offensive line, most special teams) — there is not enough signal to compare on.',
    },
    {
      id: 'started-proxy',
      label: 'Started (proxy)',
      formula:
        "A player is flagged as having started a game when their offensive or defensive snap share was 50% or higher. Nothing in the verified data marks who actually started, so this is a proxy — labelled as one everywhere it appears — never presented as the official designation.",
      limitation: windows.snap_counts?.first_season
        ? `Snap counts exist from ${windows.snap_counts.first_season} onward, so the proxy does not exist before then.`
        : 'Depends on snap counts, which do not cover the full window.',
    },
    {
      id: 'drives',
      label: 'Drive start / end field position',
      formula:
        "The source stores drive start and end as text (\"KC 25\", \"50\"). We parse that into yards from the possessing team's own goal line (0–100) so it can be averaged and compared. The text is kept alongside for display.",
    },
    {
      id: 'fantasy',
      label: 'Fantasy points',
      formula:
        'Standard (non-PPR) scoring, computed by us from raw counting stats: 1 point per 25 passing yards, 4 per passing touchdown, −2 per interception, 1 point per 10 rushing or receiving yards, 6 per rushing or receiving touchdown. PPR adds 1 point per reception and Half-PPR adds 0.5; the format is chosen once per visitor and used everywhere fantasy points appear.',
    },
  ]

  return (
    <section id="computed" className="mt-8 scroll-mt-16">
      <h2 className="mb-1 text-[15px] font-semibold leading-5">Metrics we compute ourselves</h2>
      <p className="mb-3 text-[11px] text-ink-3">
        Anything on this list carries a small <span className="align-super text-[9px]">ƒ</span> marker wherever it
        appears, linking back to its entry here.
        {formulaSeason ? ` Rating formulas below are quoted live from the ${formulaSeason} standings.` : null}
      </p>
      <dl className="space-y-4">
        {[...ratingMetrics, ...otherMetrics].map((metric) => (
          <div key={metric.id} id={metric.id} className="scroll-mt-16 border-b border-row-rule pb-4">
            <dt className="text-[13px] font-medium text-ink">{metric.label}</dt>
            <dd className="mt-1 text-[12px] leading-5 text-ink-2">{metric.formula}</dd>
            {metric.limitation ? <dd className="mt-1 text-[11px] leading-4 text-ink-3">{metric.limitation}</dd> : null}
          </div>
        ))}
      </dl>
    </section>
  )
}

function ModelSection({
  windows,
  latestSeason,
}: {
  windows: Record<string, CoverageWindow | undefined>
  latestSeason: number | null
}) {
  const statsFrom = windows.stats?.first_season
  const chartingFrom = windows.charting?.first_season

  return (
    <section id="model" className="mt-8 scroll-mt-16">
      <h2 className="mb-1 text-[15px] font-semibold leading-5">EPA, WPA, CPOE and success rate</h2>
      <p className="mb-3 text-[11px] text-ink-3">
        These four are not ours — they come from nflfastR's open, published expected-points and win-probability
        models. We read them, we do not fit them.
      </p>
      <dl className="space-y-4">
        <div id="epa" className="scroll-mt-16 border-b border-row-rule pb-4">
          <dt className="text-[13px] font-medium text-ink">EPA — Expected Points Added</dt>
          <dd className="mt-1 text-[12px] leading-5 text-ink-2">
            The change in expected points from before a play to after it, per nflfastR's expected-points model
            (down, distance, field position and score state in, expected next points out).
          </dd>
          {statsFrom && latestSeason ? (
            <dd className="mt-1 text-[11px] leading-4 text-ink-3">
              Full coverage {statsFrom}–{latestSeason}.
            </dd>
          ) : null}
        </div>
        <div id="wpa" className="scroll-mt-16 border-b border-row-rule pb-4">
          <dt className="text-[13px] font-medium text-ink">WPA — Win Probability Added</dt>
          <dd className="mt-1 text-[12px] leading-5 text-ink-2">
            The change in home win probability from before a play to after it, per nflfastR's win-probability
            model. The same figures drive every win-probability chart on the site.
          </dd>
        </div>
        <div id="success-rate" className="scroll-mt-16 border-b border-row-rule pb-4">
          <dt className="text-[13px] font-medium text-ink">Success rate</dt>
          <dd className="mt-1 text-[12px] leading-5 text-ink-2">
            The share of plays nflfastR marks successful: roughly, gaining at least 40% of yards to go on first
            down, 60% on second, or the full distance on third or fourth — the classic down-adjusted threshold,
            not simply a positive-EPA play.
          </dd>
        </div>
        <div id="cpoe" className="scroll-mt-16">
          <dt className="text-[13px] font-medium text-ink">CPOE — Completion % Over Expected</dt>
          <dd className="mt-1 text-[12px] leading-5 text-ink-2">
            A quarterback's actual completion percentage minus nflfastR's expected completion percentage for
            those same throws, given depth of target, pressure and other charted context.
          </dd>
          {chartingFrom ? (
            <dd className="mt-1 text-[11px] leading-4 text-ink-3">
              Air yards were not charted before {chartingFrom}, so CPOE is empty — not zero — in earlier seasons.
            </dd>
          ) : null}
        </div>
      </dl>
    </section>
  )
}
