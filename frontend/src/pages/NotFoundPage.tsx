import { Link } from 'react-router-dom'
import { PageHeader } from '../components/ui/Page'

export function NotFoundPage() {
  return (
    <>
      <PageHeader title="Nothing here" meta="That address does not match a player, team, game or season we hold." />
      <p className="mt-4 text-[13px] text-ink-2">
        Our data covers the 1999 season onward. If you were looking for something older, we
        don’t have it — <Link to="/about/data">here is exactly what we do have</Link>.
      </p>
    </>
  )
}
