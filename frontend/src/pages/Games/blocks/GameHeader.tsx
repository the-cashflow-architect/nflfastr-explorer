import { Link } from 'react-router-dom'
import type { Game } from '../../../api/endpoints'
import { ComputedByUs } from '../../../components/ui/Honesty'
import { PageHeader } from '../../../components/ui/Page'
import { gameDate, num, record as formatRecord, signed } from '../../../design/format'
import { Mark } from '../../../components/ui/Mark'

type Header = Game['header']
type Side = Header['home']

/** Postseason rounds arrive as source codes; "Week 20" would hide what they are. */
const ROUND: Record<string, string> = {
  WC: 'Wild card',
  DIV: 'Divisional round',
  CON: 'Conference championship',
  SB: 'Super Bowl',
}

/**
 * The identity block for one game: who played, what it finished, and the
 * conditions it was played in.
 *
 * Every fact here is printed only if the schedule row carries it. Attendance,
 * game duration and the television network are in no source we load, so they are
 * not blank rows — they are absent, and `/about/data` says why. The same rule
 * runs down to the weather: a dome game has no temperature, and an empty
 * temperature is not zero degrees.
 */
export function GameHeader({ data }: { data: Game }) {
  const { header, status, final, betting } = data
  const away = header.away
  const home = header.home

  const roundLabel =
    header.game_type && header.game_type !== 'REG'
      ? (ROUND[header.game_type] ?? header.game_type)
      : header.week
        ? `Week ${header.week}`
        : null

  const meta = (
    <>
      {header.gameday ? (
        <span>{header.weekday ? `${header.weekday}, ${gameDate(header.gameday)}` : gameDate(header.gameday)}</span>
      ) : null}
      {kickoff(header.gametime) ? <span> · {kickoff(header.gametime)}</span> : null}
      {roundLabel ? (
        <span>
          {' · '}
          {data.week_href ? <Link to={data.week_href}>{roundLabel}</Link> : roundLabel}
        </span>
      ) : null}
      <span>
        {' · '}
        <Link to={data.season_href}>{data.season} season</Link>
      </span>
      {header.div_game ? <span> · Division game</span> : null}
    </>
  )

  return (
    <div className="mb-5">
      <PageHeader title={`${nameOf(away)} at ${nameOf(home)}`} meta={meta} />

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <TeamCard side={away} played={status.played} winner={final?.winner === away.abbr} recordNote={header.record_note} />
        <TeamCard side={home} played={status.played} winner={final?.winner === home.abbr} recordNote={header.record_note} />
      </div>

      <p className="mt-2 text-[12px] text-ink-2">
        {status.label}
        {status.played && header.overtime ? ' · overtime' : ''}
        {status.played && final && final.tie ? ' · tied' : ''}
      </p>

      {status.note ? (
        <p className="mt-3 rounded-md border border-line bg-raised px-3 py-2.5 text-[13px] leading-5 text-ink-2">
          {status.note}
        </p>
      ) : null}

      <Facts header={header} betting={betting} officials={data.officials} />
    </div>
  )
}

function TeamCard({
  side,
  played,
  winner,
  recordNote,
}: {
  side: Side
  played: boolean
  winner: boolean
  recordNote?: string | null
}) {
  const entering = side.record_entering
  return (
    <div className="overflow-hidden rounded-lg border border-line bg-raised">
      {/* Team colour is data, not chrome: a 3px stripe, and nothing else on the page. */}
      {side.colors.primary ? (
        <div aria-hidden className="h-[3px] w-full" style={{ background: side.colors.primary }} />
      ) : null}
      <div className="flex items-center gap-3 px-3 py-2.5">
        <Mark src={side.logo} label={side.abbr ?? '?'} size={32} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] font-medium leading-5">
            {side.href ? <Link to={side.href}>{side.name ?? side.abbr}</Link> : (side.name ?? side.abbr ?? '—')}
          </p>
          <p className="truncate text-[11px] leading-4 text-ink-3">
            {side.side === 'home' ? 'Home' : 'Away'}
            {entering ? (
              <>
                {` · ${formatRecord(entering.w, entering.l, entering.t)} entering`}
                {recordNote ? <ComputedByUs formula={recordNote} /> : null}
              </>
            ) : null}
            {side.coach ? ` · ${side.coach}` : ''}
          </p>
        </div>
        {played ? (
          <p className={`text-[30px] leading-9 ${winner ? 'font-semibold' : 'font-normal text-ink-2'}`}>
            {num(side.score, 0)}
          </p>
        ) : null}
      </div>
    </div>
  )
}

function Facts({
  header,
  betting,
  officials,
}: {
  header: Header
  betting?: Game['betting']
  officials?: Game['officials']
}) {
  const weather = [
    header.temp !== null && header.temp !== undefined ? `${num(header.temp, 0)}°F` : null,
    header.wind !== null && header.wind !== undefined ? `wind ${num(header.wind, 0)} mph` : null,
  ].filter(Boolean)

  const rest =
    header.away_rest !== null && header.away_rest !== undefined && header.home_rest !== null && header.home_rest !== undefined
      ? `${header.away.abbr ?? 'Away'} ${header.away_rest}d · ${header.home.abbr ?? 'Home'} ${header.home_rest}d`
      : null

  const spread = spreadText(betting?.spread_line, header)
  const moneylines = [
    betting?.home_moneyline !== null && betting?.home_moneyline !== undefined
      ? `${header.home.abbr} ${signed(betting.home_moneyline, 0)}`
      : null,
    betting?.away_moneyline !== null && betting?.away_moneyline !== undefined
      ? `${header.away.abbr} ${signed(betting.away_moneyline, 0)}`
      : null,
  ].filter(Boolean)

  const items: { label: string; value: React.ReactNode }[] = []
  if (header.stadium) items.push({ label: 'Venue', value: header.stadium })
  if (header.roof) items.push({ label: 'Roof', value: sentence(header.roof) })
  if (header.surface) items.push({ label: 'Surface', value: sentence(header.surface) })
  if (weather.length) items.push({ label: 'Weather', value: weather.join(' · ') })
  if (rest) items.push({ label: 'Rest', value: rest })
  if (header.referee) items.push({ label: 'Referee', value: header.referee })
  if (betting) {
    const line = [spread, betting?.total_line != null ? `total ${num(betting.total_line, 1)}` : null].filter(Boolean)
    if (line.length) items.push({ label: 'Closing line', value: line.join(' · ') })
  }
  if (moneylines.length) items.push({ label: 'Moneyline', value: moneylines.join(' · ') })

  const settled = settlement(betting, header)

  if (!items.length && !settled && !officials?.length) return null

  return (
    <div className="mt-4 border-t border-line pt-3">
      {items.length ? (
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
          {items.map((item) => (
            <div key={item.label}>
              <dt className="text-[11px] uppercase leading-4 tracking-[0.04em] text-ink-3">{item.label}</dt>
              <dd className="m-0 text-[13px] leading-5">{item.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {settled ? (
        <p className="mt-2 text-[12px] leading-4 text-ink-2">
          {settled}
          {betting?.note ? <ComputedByUs formula={betting.note} anchor="betting" /> : null}
        </p>
      ) : null}

      {officials?.length ? (
        <p className="mt-2 text-[12px] leading-4 text-ink-3">
          Crew: {officials.map((o) => (o.position ? `${o.name} (${o.position})` : o.name)).join(' · ')}
        </p>
      ) : null}
    </div>
  )
}

/**
 * The line score, and the one place on this page where a number could be
 * mistaken for something the league published: it is rebuilt from the scoring
 * plays we hold, so it says so, and it carries the payload's own note when the
 * quarters do not add to the final.
 */
export function LineScore({ line, header }: { line: NonNullable<Game['line_score']>; header: Header }) {
  const rows: { side: Side; total: number; final: number | null | undefined }[] = [
    { side: header.away, total: line.away_total, final: line.final_away },
    { side: header.home, total: line.home_total, final: line.final_home },
  ]
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="border-collapse text-[13px]">
          <thead>
            <tr>
              <th className="border-b border-line-strong px-2 py-1.5 text-left text-[11px] font-semibold uppercase tracking-[0.03em] text-ink-2">
                Team
              </th>
              {line.periods.map((period) => (
                <th
                  key={period.period}
                  className="w-12 border-b border-line-strong px-2 py-1.5 text-right text-[11px] font-semibold uppercase tracking-[0.03em] text-ink-2"
                >
                  {period.label}
                </th>
              ))}
              <th className="w-14 border-b border-line-strong px-2 py-1.5 text-right text-[11px] font-semibold uppercase tracking-[0.03em] text-ink-2">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.side.side} className="border-b border-row-rule">
                <td className="px-2 py-1">
                  {row.side.href ? <Link to={row.side.href}>{row.side.abbr}</Link> : (row.side.abbr ?? '—')}
                </td>
                {line.periods.map((period) => (
                  <td key={period.period} className="px-2 py-1 text-right">
                    {num(row.side.side === 'home' ? period.home : period.away, 0)}
                  </td>
                ))}
                <td className="px-2 py-1 text-right font-semibold">{num(row.final ?? row.total, 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-1.5 text-[11px] leading-4 text-ink-3">
        Quarters are rebuilt from the scoring plays we hold.
        <ComputedByUs formula={`Line score built from ${line.source}`} anchor="line-score" />
        {line.note ? ` ${line.note}` : ''}
      </p>
    </div>
  )
}

function nameOf(side: Side): string {
  return side.nick ?? side.name ?? side.abbr ?? 'Unknown'
}

/**
 * The schedule file records kickoff without a timezone, so none is printed. A
 * "ET" we invented would be a fact we do not have.
 */
function kickoff(value?: string | null): string | null {
  if (!value) return null
  const [hours, minutes] = value.split(':').map(Number)
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null
  const hour = hours % 12 === 0 ? 12 : hours % 12
  return `${hour}:${String(minutes).padStart(2, '0')} ${hours < 12 ? 'am' : 'pm'}`
}

function sentence(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1)
}

/** `spread_line` is the home club's line, positive when the home club is favoured. */
function spreadText(spread: number | null | undefined, header: Header): string | null {
  if (spread === null || spread === undefined) return null
  if (spread === 0) return 'Pick’em'
  const favourite = spread > 0 ? header.home.abbr : header.away.abbr
  return `${favourite ?? '—'} −${num(Math.abs(spread), 1)}`
}

function settlement(betting: Game['betting'], header: Header): string | null {
  if (!betting) return null
  const parts: string[] = []
  if (betting.ats_result === 'push') parts.push('The spread pushed')
  else if (betting.ats_result === 'home') parts.push(`${header.home.abbr ?? 'The home club'} covered`)
  else if (betting.ats_result === 'away') parts.push(`${header.away.abbr ?? 'The away club'} covered`)
  if (betting.ou_result && betting.total_points !== null && betting.total_points !== undefined) {
    const total = betting.total_line !== null && betting.total_line !== undefined ? num(betting.total_line, 1) : null
    parts.push(
      betting.ou_result === 'push'
        ? `the total pushed at ${betting.total_points}`
        : `${betting.total_points} points went ${betting.ou_result}${total ? ` the ${total}` : ''}`,
    )
  }
  return parts.length ? `${parts.join(' · ')}.` : null
}
