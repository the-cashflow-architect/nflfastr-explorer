import { Link } from 'react-router-dom'
import { PageHeader } from '../../components/ui/Page'

/**
 * What Gridiron knows about the person using it.
 *
 * Apple requires this inside the app (Guideline 5.1.1(i)), and it has to say
 * what is collected, who else sees it, and how long it is kept. Gridiron's
 * honest answer is short — no accounts, no analytics — but not "nothing": the
 * server keeps request logs, and player photos and team logos load straight
 * from the NFL's and GitHub's servers, which therefore see the device ask for
 * them. Both are stated plainly rather than rounded down to zero, which is the
 * same rule the rest of the product follows about its numbers.
 *
 * It is a reference document, so, like Data & methods, it carries no primary
 * action.
 */
const UPDATED = '28 September 2026'
const CONTACT = 'engineering@evadaroo.com'

export function PrivacyPage() {
  return (
    <div>
      <PageHeader title="Privacy" meta={`What Gridiron knows about you, and who else sees what · Last updated ${UPDATED}`} />

      <div className="mt-6 max-w-[680px] space-y-6 text-[14px] leading-6 text-ink-2">
        <p className="rounded-md border border-line bg-raised px-4 py-3 text-[15px] leading-6 text-ink">
          Gridiron has no accounts, no analytics, no advertising and no tracking. We do not collect anything that
          identifies you. The two things that do leave your device are described below, so you do not have to take
          &ldquo;nothing&rdquo; on trust.
        </p>

        <Section title="Who we are">
          Gridiron is made by Evadaroo &amp; Co. You can reach us at <Mail />.
        </Section>

        <Section title="When you look something up">
          The app asks our server for the football figures on the page you are viewing. The server is hosted by
          Render, and like any web server it records standard request logs &mdash; the network address the request came
          from, the page asked for, and the time &mdash; which Render keeps for a limited period to run and protect the
          service. We use them for nothing else, and they are not tied to any account, because there are none.
        </Section>

        <Section title="Photos and logos">
          Player photos load directly from the NFL&rsquo;s image service (static.www.nfl.com), and team logos from
          GitHub, where the open nflverse project publishes them. Your device asks those servers for the pictures
          itself, so &mdash; as with any image on the web &mdash; they see that request, including your network address
          and the kind of device, under their own privacy policies. We send them nothing else.
        </Section>

        <Section title="What is kept on your device">
          <ul className="list-disc space-y-1 pl-5">
            <li>Your display choices: light or dark, and table density.</li>
            <li>Queries you save in the Finder.</li>
            <li>
              A copy of the figures you have recently viewed, so pages open at once and still work with no signal. The
              app always says when figures on screen came from this copy, and when they were saved.
            </li>
          </ul>
          <p className="mt-2">None of it is ever sent to us.</p>
        </Section>

        <Section title="Third parties">
          We share no data with anyone. The only outside services involved are the ones named above: Render, which
          hosts our server and this website, and the NFL and GitHub image servers your device contacts for pictures.
          The statistics themselves come from nflverse and are public records about football, not about you. If this
          ever changes, this page will say so first, and anyone we share with will be held to the protection described
          here.
        </Section>

        <Section title="Keeping and deleting">
          <p>
            What is on your device stays there until you remove it: delete the app, or on the website clear this
            site&rsquo;s data in your browser settings. The server&rsquo;s request logs are deleted automatically when
            Render&rsquo;s retention period ends. Because we hold nothing tied to you, there is no account to close and no
            consent to revoke &mdash; but if you have a question about any of it, write to <Mail />.
          </p>
        </Section>

        <Section title="Children">
          Gridiron is a sports reference for a general audience and is not directed at children. We do not knowingly
          collect information from anyone, of any age.
        </Section>

        <Section title="Changes">
          If this ever changes, we will update this page and the date at the top before the change reaches the app.
        </Section>

        <p className="border-t border-line pt-4 text-[13px] text-ink-3">
          Questions about privacy: <Mail />. For anything else, see <Link to="/about/support">Support</Link>.
        </p>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="mb-1 text-[15px] font-semibold leading-5 text-ink">{title}</h2>
      <div>{children}</div>
    </section>
  )
}

function Mail() {
  return <a href={`mailto:${CONTACT}`}>{CONTACT}</a>
}
