import { PageHeader } from '../../../components/ui/Page'
import { Mark } from '../../../components/ui/Mark'

/**
 * The identity header shared by the franchise hub, the team-season cockpit and
 * the roster.
 *
 * The 3px rule under the header is the only place a team's colour appears on
 * these pages. It is data, not chrome — so a club whose branding row carries no
 * colour gets no rule at all rather than a grey stand-in that would read as a
 * colour we know.
 */

interface HeaderTeam {
  name?: string | null
  abbr?: string | null
  logo?: string | null
  colors: { primary?: string | null; secondary?: string | null }
}

export function TeamHeader({
  team,
  title,
  meta,
  action,
  prev,
  next,
  subnav,
}: {
  team: HeaderTeam
  title: React.ReactNode
  meta?: React.ReactNode
  action?: React.ReactNode
  prev?: { to: string; label: string }
  next?: { to: string; label: string }
  subnav?: React.ReactNode
}) {
  return (
    <div className="mb-5">
      <PageHeader
        title={title}
        mark={
          <Mark src={team.logo} label={team.abbr ?? team.name ?? '?'} size={40} />
        }
        meta={meta}
        action={action}
        prev={prev}
        next={next}
        subnav={subnav}
      />
      {team.colors.primary ? (
        <div aria-hidden className="h-[3px] w-full" style={{ background: team.colors.primary }} />
      ) : null}
    </div>
  )
}
