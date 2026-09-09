import { Link } from 'react-router-dom'
import type { SeasonHub } from '../../../api/endpoints'
import { TeamLink } from '../../../components/ui/EntityLink'
import { num } from '../../../design/format'
import { Mark } from '../../../components/ui/Mark'

/**
 * A real seeded tree, wild card through the championship game — the block
 * Pro-Football-Reference does not have.
 *
 * The field is six seeds before 2020 and seven after, and this component
 * never hardcodes either number. It reads the actual rounds the payload sent
 * and works out byes structurally: whichever team appears in the divisional
 * round without having appeared in the wild-card round *is* the bye, for
 * either era, with no seed-count constant anywhere in this file. The same
 * logic degrades gracefully mid-postseason — a season with only a wild-card
 * round played renders just that column, no phantom later rounds.
 */

type BracketData = NonNullable<SeasonHub['bracket']>
type BracketRoundData = BracketData['rounds'][number]
type BracketGame = BracketRoundData['games'][number]
type BracketTeam = BracketGame['home']
type Conference = 'AFC' | 'NFC'

type Slot = { seed: number; box: { kind: 'bye'; team: BracketTeam } | { kind: 'game'; game: BracketGame } }

export function PlayoffBracket({
  bracket,
  teamConference,
  season,
}: {
  bracket: BracketData
  /** Franchise abbr → conference, read off the season's own standings. */
  teamConference: Record<string, Conference>
  season: number
}) {
  const byRound = new Map(bracket.rounds.map((round) => [round.round, round]))
  const wc = byRound.get('WC')
  const div = byRound.get('DIV')
  const con = byRound.get('CON')
  const sb = byRound.get('SB')

  const inConference = (game: BracketGame, conference: Conference) => teamConference[game.home.abbr] === conference

  const pods = (['AFC', 'NFC'] as const)
    .map((conference) => ({
      conference,
      wcGames: wc?.games.filter((g) => inConference(g, conference)) ?? [],
      divGames: (div?.games.filter((g) => inConference(g, conference)) ?? []).slice().sort((a, b) => matchSeed(a) - matchSeed(b)),
      conGame: con?.games.find((g) => inConference(g, conference)) ?? null,
    }))
    .filter((pod) => pod.wcGames.length || pod.divGames.length || pod.conGame)

  const sbGame = sb?.games[0] ?? null

  if (!pods.length && !sbGame) {
    return <p className="py-4 text-[13px] text-ink-3">No postseason games are recorded for this season.</p>
  }

  return (
    <div className="overflow-x-auto pb-1">
      <div className="flex min-w-max flex-col gap-8">
        {pods.map((pod) => (
          <ConferencePod
            key={pod.conference}
            conference={pod.conference}
            wcGames={pod.wcGames}
            divGames={pod.divGames}
            conGame={pod.conGame}
            wcLabel={wc?.round_label ?? 'Wild Card'}
            divLabel={div?.round_label ?? 'Divisional'}
            conLabel={con?.round_label ?? 'Conference Championship'}
            season={season}
          />
        ))}
        {sbGame ? <SuperBowlCard game={sbGame} label={sb?.round_label ?? 'Super Bowl'} /> : null}
      </div>
    </div>
  )
}

function matchSeed(game: BracketGame): number {
  return Math.min(game.home.seed ?? 99, game.away.seed ?? 99)
}

function buildSlot(team: BracketTeam, wcGames: BracketGame[]): Slot {
  const game = wcGames.find((g) => g.home.abbr === team.abbr || g.away.abbr === team.abbr)
  if (game) return { seed: matchSeed(game), box: { kind: 'game', game } }
  return { seed: team.seed ?? 99, box: { kind: 'bye', team } }
}

function ConferencePod({
  conference,
  wcGames,
  divGames,
  conGame,
  wcLabel,
  divLabel,
  conLabel,
  season,
}: {
  conference: Conference
  wcGames: BracketGame[]
  divGames: BracketGame[]
  conGame: BracketGame | null
  wcLabel: string
  divLabel: string
  conLabel: string
  season: number
}) {
  // Each divisional match's two feeders are either a wild-card game (the
  // winner advances) or a bye — found by asking "did this team play a
  // wild-card game," never by counting seeds, so 1999's two byes per
  // conference and 2024's one both fall out of the same lookup. A season
  // whose divisional round has not been played yet has nothing to pair the
  // wild-card games against, so that case renders the wild-card column
  // alone rather than silently dropping those games.
  const hasDiv = divGames.length > 0
  const hasCon = hasDiv && !!conGame

  const divMatches = hasDiv
    ? divGames.map((game) => ({
        game,
        slots: [buildSlot(game.home, wcGames), buildSlot(game.away, wcGames)].sort((a, b) => a.seed - b.seed),
      }))
    : []

  const standaloneWc = hasDiv
    ? []
    : wcGames
        .slice()
        .sort((a, b) => matchSeed(a) - matchSeed(b))
        .map((game) => ({ seed: matchSeed(game), game }))

  const rows = hasDiv ? Math.max(divMatches.length * 2, 1) : Math.max(standaloneWc.length, 1)

  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.04em] text-ink-3">{conference}</p>
      <div
        className="grid items-stretch gap-x-3"
        style={{
          gridTemplateColumns: hasCon ? '13rem 1.25rem 13rem 1.25rem 13rem' : hasDiv ? '13rem 1.25rem 13rem' : '13rem',
          gridTemplateRows: `repeat(${rows}, minmax(3.5rem, auto))`,
        }}
      >
        {hasDiv
          ? divMatches.map((match, index) =>
              match.slots.map((slot, slotIndex) => (
                <div
                  key={`${match.game.game_id}-slot-${slotIndex}`}
                  style={{ gridColumn: 1, gridRow: index * 2 + slotIndex + 1 }}
                  className="flex items-center"
                >
                  {slot.box.kind === 'game' ? (
                    <MatchCard game={slot.box.game} label={wcLabel} />
                  ) : (
                    <ByeCard team={slot.box.team} label={wcLabel} season={season} />
                  )}
                </div>
              )),
            )
          : standaloneWc.map((slot, index) => (
              <div key={slot.game.game_id} style={{ gridColumn: 1, gridRow: index + 1 }} className="flex items-center">
                <MatchCard game={slot.game} label={wcLabel} />
              </div>
            ))}

        {hasDiv
          ? divMatches.map((match, index) => (
              <div key={`connector-wc-div-${match.game.game_id}`} style={{ gridColumn: 2, gridRow: `${index * 2 + 1} / ${index * 2 + 3}` }}>
                <Connector />
              </div>
            ))
          : null}

        {hasDiv
          ? divMatches.map((match, index) => (
              <div
                key={match.game.game_id}
                style={{ gridColumn: 3, gridRow: `${index * 2 + 1} / ${index * 2 + 3}` }}
                className="flex items-center"
              >
                <MatchCard game={match.game} label={divLabel} />
              </div>
            ))
          : null}

        {hasCon ? (
          <div style={{ gridColumn: 4, gridRow: `1 / ${rows + 1}` }}>
            <Connector />
          </div>
        ) : null}

        {hasCon && conGame ? (
          <div style={{ gridColumn: 5, gridRow: `1 / ${rows + 1}` }} className="flex items-center">
            <MatchCard game={conGame} label={conLabel} emphasis />
          </div>
        ) : null}
      </div>
    </div>
  )
}

/** The elbow that makes two feeders read as one tree rather than two lists. */
function Connector() {
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" className="h-full w-full" aria-hidden>
      <path
        d="M0,25 H50 V75 M0,75 H50 M50,50 H100"
        fill="none"
        stroke="var(--c-line-strong)"
        strokeWidth={1}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

function MatchCard({ game, label, emphasis }: { game: BracketGame; label: string; emphasis?: boolean }) {
  const homeWon = game.winner ? game.winner === game.home.abbr : game.home_score > game.away_score
  const awayWon = game.winner ? game.winner === game.away.abbr : game.away_score > game.home_score
  return (
    <Link
      to={game.href}
      className={`block w-full rounded-md border border-line bg-raised px-2.5 py-1.5 no-underline hover:border-line-strong ${emphasis ? 'shadow-sm' : ''}`}
    >
      <p className="mb-1 text-[10px] uppercase tracking-[0.03em] text-ink-3">{label}</p>
      <BracketTeamRow team={game.away} score={game.away_score} won={awayWon} />
      <BracketTeamRow team={game.home} score={game.home_score} won={homeWon} />
    </Link>
  )
}

function BracketTeamRow({ team, score, won }: { team: BracketTeam; score: number; won: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="flex min-w-0 items-center gap-1.5">
        <Mark src={team.logo} label={team.code_in_season ?? team.abbr ?? '?'} size={16} />
        <span className={`truncate text-[12px] ${won ? 'font-semibold text-ink' : 'text-ink-2'}`}>
          {team.seed ? <span className="text-ink-3">{team.seed} </span> : null}
          {team.code_in_season}
        </span>
      </span>
      <span className={`shrink-0 text-[12px] tabular-nums ${won ? 'font-semibold text-positive' : 'text-ink-3'}`}>{num(score)}</span>
    </div>
  )
}

function ByeCard({ team, label, season }: { team: BracketTeam; label: string; season: number }) {
  return (
    <div className="w-full rounded-md border border-dashed border-line px-2.5 py-1.5">
      <p className="mb-1 text-[10px] uppercase tracking-[0.03em] text-ink-3">{label}</p>
      <div className="flex items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5">
          <Mark src={team.logo} label={team.code_in_season ?? team.abbr ?? '?'} size={16} />
          <span className="truncate text-[12px] font-medium text-ink">
            {team.seed ? <span className="text-ink-3">{team.seed} </span> : null}
            <TeamLink abbr={team.abbr} season={season} className="no-underline hover:underline">
              {team.code_in_season}
            </TeamLink>
          </span>
        </span>
        <span className="shrink-0 text-[11px] text-ink-3">Bye</span>
      </div>
    </div>
  )
}

function SuperBowlCard({ game, label }: { game: BracketGame; label: string }) {
  return (
    <div>
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.04em] text-ink-3">{label}</p>
      <div className="w-[13rem]">
        <MatchCard game={game} label={label} emphasis />
      </div>
    </div>
  )
}
