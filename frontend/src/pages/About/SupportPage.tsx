import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/ui/Page'

/**
 * How to reach a person, and the questions people actually ask.
 *
 * Apple requires a way to contact the developer from inside the app and on the
 * Support URL (Guideline 1.5). No coverage years are typed here — the product's
 * rule is that every window comes from /api/coverage — so the questions about
 * what Gridiron holds point at Data & methods, which reads the live load log.
 */
const CONTACT = 'engineering@evadaroo.com'

export function SupportPage() {
  return (
    <div>
      <PageHeader title="Support" meta="How to reach us, and answers to common questions" />

      <div className="mt-6 max-w-[680px] space-y-6 text-[14px] leading-6 text-ink-2">
        <p className="rounded-md border border-line bg-raised px-4 py-3 text-[15px] leading-6 text-ink">
          Write to us at <a href={`mailto:${CONTACT}`}>{CONTACT}</a>. A person reads every message. If a number looks
          wrong, tell us the page and the figure &mdash; that is the report we most want.
        </p>

        <Question title="Why does it say &ldquo;Showing figures saved&rdquo;?">
          Gridiron keeps a copy of what you have viewed so pages open at once. When the figures on screen come from that
          copy rather than from just now, the bar at the bottom says so and gives the time they were saved. It goes away
          as soon as the latest figures arrive.
        </Question>

        <Question title="Why was the first page slow to load?">
          The server rests when nobody is using it and takes up to a minute to wake. Only the first request pays that
          wait; everything after it is quick. The app shows what it already has in the meantime.
        </Question>

        <Question title="Which seasons do you cover?">
          Every dataset&rsquo;s window, and everything we chose not to include, is on{' '}
          <Link to="/about/data">Data &amp; methods</Link>, read live from our last data load.
        </Question>

        <Question title="How is this number calculated?">
          Anything we compute rather than read is marked on the page with its formula. The full list is on{' '}
          <Link to="/about/data">Data &amp; methods</Link>, and every stat is defined in the{' '}
          <Link to="/glossary">Glossary</Link>.
        </Question>

        <Question title="Privacy">
          No accounts, no analytics, no tracking. <Link to="/about/privacy">Read the privacy policy</Link>.
        </Question>
      </div>
    </div>
  )
}

function Question({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-1 text-[15px] font-semibold leading-5 text-ink">{title}</h2>
      <p>{children}</p>
    </section>
  )
}
