import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { TrendLine } from '../../components/charts/TrendLine'
import { GameLink, TeamLink } from '../../components/ui/EntityLink'
import { ComputedByUs } from '../../components/ui/Honesty'
import { PageHeader, PrimaryAction, Section, Segmented, Tile, TileRow } from '../../components/ui/Page'
import { QueryBoundary } from '../../components/ui/QueryBoundary'
import { useAnchorScroll } from '../../components/ui/useAnchorScroll'
import { useCrumbLabel } from '../../components/shell/useCrumbLabel'
import { gameDate, num, plural } from '../../design/format'
import { usePlayerHub, type PlayerHub } from '../../api/endpoints'
import { CareerTable, StatValue } from './blocks/CareerTable'
import { PercentileStrip } from './blocks/PercentileStrip'
import { PlayerHeadshot, IdentityMeta, PlayerIdentity } from './blocks/PlayerIdentity'
import { PlayerNavRow, SeasonPicker } from './blocks/PlayerHeader'

/**
 * The player hub: one page per player, laid out as a cockpit for that one man.
 *
 * The ordering rule is that everything above the fold answers "how good was
 * he", and everything below answers "prove it". The percentile strip re-scopes
 * in place rather than navigating, the career table is the reference artefact,
 * and the deeper cockpits — game log, splits, advanced — are one click down
 * from the sub-nav rather than crammed in here.
 *
 * Blocks the payload does not carry are absent, not empty. A player with no
 * postseason row has no postseason section at all; an offensive lineman has no
 * season stat columns and gets a games-played table with the reason printed
 * under it.
 */

const PAGE_KEY = 'player-hub'
const CAREER = 'career'

export function PlayerHubPage() {
  const { gsisId = '', slug } = useParams()
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  const query = usePlayerHub(gsisId)
  const hub = query.data

  const canonicalSlug = hub?.identity.slug ?? null
  useCrumbLabel(canonicalSlug ? `/players/${gsisId}/${canonicalSlug}` : null, hub?.identity.display_name)
  useAnchorScroll(!!hub)

  // The slug is decoration, but it is the decoration the breadcrumb and every
  // shared link read the player's name from, so the URL is normalised once the
  // payload knows it.
  useEffect(() => {
    if (canonicalSlug && !slug) {
      navigate(`/players/${gsisId}/${canonicalSlug}${location.search}`, { replace: true })
    }
  }, [canonicalSlug, slug, gsisId, location.search, navigate])

  const seasons = useMemo(() => careerSeasons(hub), [hub])
  const defaultScope = hub?.career_regular?.total.last_season
    ? String(hub.career_regular.total.last_season)
    : CAREER
  const scope = params.get('season') ?? defaultScope

  return (
    <QueryBoundary isLoading={query.isLoading} error={query.error} onRetry={() => void query.refetch()}>
      {hub ? (
        <>
          <PageHeader
            title={hub.identity.display_name ?? 'Player'}
            mark={<PlayerHeadshot url={hub.identity.headshot_url} name={hub.identity.display_name} />}
            meta={<IdentityMeta identity={hub.identity} />}
            action={
              hub.available_tabs.gamelog ? (
                <PrimaryAction to={`/players/${gsisId}/gamelog`}>Game log</PrimaryAction>
              ) : undefined
            }
            subnav={
              <PlayerNavRow
                gsisId={gsisId}
                slug={canonicalSlug ?? undefined}
                available={hub.available_tabs}
              />
            }
          />

          <PlayerIdentity hub={hub} />

          {hub.tiles?.length ? (
            <div className="mt-4">
              <TileRow>
                {hub.tiles.slice(0, 4).map((tile) => (
                  <Tile
                    key={tile.id}
                    label={tile.label}
                    value={<StatValue value={tile.value} unit={tile.unit} id={tile.id} />}
                    context={
                      <>
                        {tile.context}
                        {tile.computed_by_us ? (
                          <ComputedByUs
                            formula={`${tile.label}, computed from the season stats we loaded`}
                            anchor="player-tiles"
                          />
                        ) : null}
                      </>
                    }
                  />
                ))}
              </TileRow>
            </div>
          ) : null}

          <Section
            title="How he compares"
            note={scope === CAREER ? 'Career, pooled across seasons' : `Season ${scope}`}
            controls={
              seasons.length ? (
                <SeasonPicker
                  seasons={seasons}
                  value={scope}
                  onChange={(value) => setParams({ season: value }, { replace: true })}
                  allValue={CAREER}
                  allLabel="Career"
                  ariaLabel="Percentile season"
                />
              ) : undefined
            }
          >
            <PercentileStrip gsisId={gsisId} scope={scope} />
          </Section>

          {hub.career_regular ? (
            <Section title="Career — regular season" note={hub.era.note}>
              <CareerTable
                block={hub.career_regular}
                seasonScope="regular"
                csvName={`${canonicalSlug ?? gsisId}-career`}
              />
            </Section>
          ) : null}

          {hub.career_postseason?.rows.length ? (
            <Section
              title="Career — postseason"
              collapsible
              defaultCollapsed
              count={plural(hub.career_postseason.total.seasons, 'postseason')}
              pageKey={PAGE_KEY}
              sectionKey="postseason"
            >
              <CareerTable
                block={hub.career_postseason}
                seasonScope="postseason"
                csvName={`${canonicalSlug ?? gsisId}-postseason`}
              />
            </Section>
          ) : null}

          {hub.career_regular ? (
            <TrendSection block={hub.career_regular} />
          ) : null}

          {hub.last_games?.length ? (
            <Section
              title="Last five games"
              controls={
                hub.available_tabs.gamelog ? (
                  <Link to={`/players/${gsisId}/gamelog`} className="text-[12px]">
                    Full game log
                  </Link>
                ) : undefined
              }
            >
              <LastGames games={hub.last_games} />
            </Section>
          ) : null}

          <Section
            title="What we hold on this player"
            collapsible
            defaultCollapsed
            count={plural(hub.coverage.length, 'source')}
            pageKey={PAGE_KEY}
            sectionKey="coverage"
          >
            <CoverageList hub={hub} gsisId={gsisId} />
          </Section>
        </>
      ) : null}
    </QueryBoundary>
  )
}

function careerSeasons(hub: PlayerHub | undefined): number[] {
  const seasons = new Set<number>()
  for (const row of hub?.career_regular?.rows ?? []) seasons.add(row.season)
  return [...seasons].sort((a, b) => b - a)
}

/**
 * One metric at a time over the seasons of a career. Multi-team seasons are
 * plotted from their combined row, so a traded player is one point per season
 * rather than two half-seasons that look like a collapse.
 */
function TrendSection({ block }: { block: NonNullable<PlayerHub['career_regular']> }) {
  const metrics = [
    { id: 'games', label: 'Games', unit: 'count', kind: 'count' as string | null, first_season: null as number | null },
    ...block.columns,
  ]
  const [metricId, setMetricId] = useState(metrics[metrics.length > 1 ? 1 : 0].id)
  const metric = metrics.find((entry) => entry.id === metricId) ?? metrics[0]

  const points = useMemo(() => {
    const bySeason = new Map<number, (typeof block.rows)[number]>()
    for (const row of block.rows) {
      const held = bySeason.get(row.season)
      if (!held || row.is_combined) bySeason.set(row.season, row)
    }
    return [...bySeason.values()]
      .sort((a, b) => a.season - b.season)
      .map((row) => ({
        season: row.season,
        value: metricId === 'games' ? (row.games ?? null) : (row.stats[metricId] ?? null),
      }))
  }, [block.rows, metricId])

  if (points.length < 2) return null

  const boundary =
    metric.first_season && points.some((point) => point.season < (metric.first_season ?? 0))
      ? [{ at: metric.first_season, label: `charted from ${metric.first_season}` }]
      : []

  return (
    <Section
      title="Season trend"
      collapsible
      defaultCollapsed
      count={plural(points.length, 'season')}
      pageKey={PAGE_KEY}
      sectionKey="trend"
      controls={
        <Segmented
          options={metrics.map((entry) => ({ value: entry.id, label: entry.label }))}
          value={metricId}
          onChange={setMetricId}
          ariaLabel="Trend metric"
        />
      }
    >
      <TrendLine
        data={points}
        xKey="season"
        yKey="value"
        yLabel={metric.label}
        zeroBased={metric.kind !== 'rate'}
        eraBoundaries={boundary}
        formatValue={(value) => num(value, metric.unit === 'epa' ? 3 : metric.unit === 'percent' ? 1 : 0)}
      />
    </Section>
  )
}

function LastGames({ games }: { games: NonNullable<PlayerHub['last_games']> }) {
  return (
    <ul className="divide-y divide-row-rule border-y border-row-rule">
      {games.map((game) => (
        <li key={game.game_id ?? `${game.season}-${game.week}`} className="flex flex-wrap items-baseline gap-x-3 py-1.5 text-[13px]">
          <span className="w-24 shrink-0 text-ink-3">{gameDate(game.gameday)}</span>
          <span className="w-16 shrink-0 text-ink-3">{game.week ? `Week ${game.week}` : null}</span>
          <span className="w-28 shrink-0">
            <span className="text-ink-3">{game.home_away === 'away' ? '@ ' : 'vs '}</span>
            <TeamLink abbr={game.opponent} season={game.season} />
          </span>
          <span>
            <GameLink gameId={game.game_id}>
              <span className={game.result === 'W' ? 'text-positive' : game.result === 'L' ? 'text-negative' : ''}>
                {game.result ?? '—'}
              </span>{' '}
              {game.team_score === null || game.opp_score === null ? (
                <span className="text-ink-3">—</span>
              ) : (
                `${num(game.team_score, 0)}–${num(game.opp_score, 0)}`
              )}
            </GameLink>
          </span>
        </li>
      ))}
    </ul>
  )
}

/**
 * Every source we tried for this player, including the ones with nothing in
 * them. A source that came back empty is named here rather than leaving a
 * silence a visitor would have to guess about.
 */
function CoverageList({ hub, gsisId }: { hub: PlayerHub; gsisId: string }) {
  return (
    <div className="space-y-1 text-[12px] leading-5">
      {hub.coverage.map((entry) => (
        <p key={entry.source} className="flex flex-wrap items-baseline gap-x-2">
          <span className="min-w-[16rem]">{entry.name}</span>
          <span className="text-ink-3">
            {entry.rows && entry.first_season
              ? `${entry.first_season}–${entry.last_season} · ${plural(entry.rows, 'row')}`
              : (entry.note ?? 'No rows for this player.')}
          </span>
          {entry.declared_first_season ? (
            <span className="text-[11px] text-ink-3">{`dataset from ${entry.declared_first_season}`}</span>
          ) : null}
        </p>
      ))}
      {hub.available_tabs.splits_note ? (
        <p className="pt-1 text-[11px] leading-4 text-ink-3">{hub.available_tabs.splits_note}</p>
      ) : null}
      {hub.available_tabs.advanced ? (
        <p className="pt-1">
          <Link to={`/players/${gsisId}/advanced`} className="text-[12px]">
            Advanced metrics and their windows
          </Link>
        </p>
      ) : null}
    </div>
  )
}
