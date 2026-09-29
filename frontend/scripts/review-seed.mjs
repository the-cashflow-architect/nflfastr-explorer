/**
 * Prove the first-launch snapshot does its job, in a real browser.
 *
 * build-seed-cache.mjs mirrors the home page's query keys by hand, so the only
 * honest test is to hand the app that file and cut the API off: if the keys
 * have drifted, the home page renders nothing and this fails.
 *
 * It also holds the line the whole cache depends on — a figure from disk must
 * never pass for a current one — in both ways it can come up:
 *
 *   server unreachable   the page renders from the snapshot, and says it could
 *                        not update and when the figures were saved
 *   server waking        the page renders at once, says it is showing saved
 *                        figures while the latest load, and the notice goes
 *                        away once they have
 *
 * It writes the snapshot into storage directly rather than going through
 * seedIfEmpty(), which only runs on a device; that function's job is one guarded
 * copy, and this checks what the copy is for.
 *
 * Run: BASE=http://127.0.0.1:4173 node scripts/review-seed.mjs
 *      (a production build carrying public/seed-cache.json, served at BASE,
 *      and the fixture API on :8000 — see IOS.md, "Verifying it locally")
 *
 * Live answers come from the local fixture API, not whichever API the build
 * points at. The build points at the production API, which (rightly) sends
 * CORS headers only to the website's own address — so a request passed
 * straight through from 127.0.0.1 was refused, the "waking" case could never
 * clear its notice, and this review could not pass as shipped.
 */
import { chromium, devices } from 'playwright'
import { readFileSync, existsSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'

const BASE = process.env.BASE || 'http://127.0.0.1:4173'
const API = process.env.API || 'http://127.0.0.1:8000'
const RAW = readFileSync(join(process.cwd(), 'public', 'seed-cache.json'), 'utf8')

/**
 * The snapshot as it will actually be met: built on the Mac, opened by a
 * reviewer or a visitor days later. A snapshot minutes old sits inside the
 * app's one-hour freshness window, where it is treated as current like any
 * other answer — true, but not the case this review exists to hold the line on.
 */
function aged(raw, days) {
  const seed = JSON.parse(raw)
  const shift = days * 24 * 60 * 60 * 1000
  seed.timestamp -= shift
  for (const q of seed.clientState.queries) {
    q.state.dataUpdatedAt -= shift
    if (q.dehydratedAt) q.dehydratedAt -= shift
  }
  return JSON.stringify(seed)
}
const SEED = aged(RAW, 3)
const SHOTS = join(process.cwd(), 'review-shots')
mkdirSync(SHOTS, { recursive: true })
const CACHE_KEY = 'gridiron.query-cache.v1'
const seededAt = JSON.parse(RAW).timestamp

const BUNDLED = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(BUNDLED) ? { executablePath: BUNDLED } : {})
const problems = []

async function fresh(label, routeApi, seed = SEED) {
  const ctx = await browser.newContext({ ...devices['iPhone 15 Pro'] })
  await ctx.addInitScript(([key, value]) => {
    if (!localStorage.getItem(key)) localStorage.setItem(key, value)
  }, [CACHE_KEY, seed])
  await ctx.route((url) => url.pathname.startsWith('/api/'), routeApi)
  const page = await ctx.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push(e.message))
  return { ctx, page, errors, label }
}

/** A real answer from the fixture API, with the header a browser needs to accept it. */
async function answer(route) {
  const url = new URL(route.request().url())
  try {
    const response = await route.fetch({ url: `${API}${url.pathname}${url.search}` })
    await route.fulfill({ response, headers: { ...response.headers(), 'access-control-allow-origin': '*' } })
  } catch {
    await route.abort()
  }
}

const text = (page) => page.evaluate(() => document.body.innerText)
const banner = (page) => page.evaluate(() => document.querySelector('.freshness-banner')?.textContent ?? null)
const homeRendered = (t) => /Super Bowl|Standings/.test(t)

/* ---- 1. server unreachable ---- */
{
  const { ctx, page, errors, label } = await fresh('unreachable', (route) => route.abort())
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(4000)
  const t = await text(page)
  const b = await banner(page)
  if (!homeRendered(t)) problems.push(`${label}: the home page did not render from the snapshot — the seed's query keys no longer match the app's`)
  if (!b || !/saved/.test(b)) problems.push(`${label}: figures from the snapshot were shown with no notice saying when they were saved (banner: ${JSON.stringify(b)})`)
  if (errors.length) problems.push(`${label}: uncaught ${errors[0]}`)
  await page.screenshot({ path: join(SHOTS, 'seed-unreachable.png') })
  console.log(`  unreachable   home rendered=${homeRendered(t)}  banner=${JSON.stringify(b)}`)
  await ctx.close()
}

/* ---- 2. server waking (every answer 5 s late) ---- */
{
  const { ctx, page, errors, label } = await fresh('waking', async (route) => {
    await new Promise((r) => setTimeout(r, 5000))
    await answer(route)
  })
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(1500)
  const during = await banner(page)
  const t = await text(page)
  if (!homeRendered(t)) problems.push(`${label}: nothing on screen while the server woke — the snapshot did not render`)
  if (!during || !/while the latest load/.test(during)) problems.push(`${label}: saved figures shown during the wake without saying so (banner: ${JSON.stringify(during)})`)
  await page.screenshot({ path: join(SHOTS, 'seed-waking.png') })
  // Every answer takes 5 s and the home page's three are chained, so allow for all of them.
  await page.waitForTimeout(20000)
  const after = await banner(page)
  if (after) problems.push(`${label}: the notice stayed up after the live figures arrived (${JSON.stringify(after)})`)
  if (errors.length) problems.push(`${label}: uncaught ${errors[0]}`)
  console.log(`  waking        during=${JSON.stringify(during)}  after=${JSON.stringify(after)}`)
  await ctx.close()
}

/* ---- 3. snapshot inside the app's own freshness window ----
   Treated exactly like an answer fetched a few minutes ago: shown, not
   refetched, and not flagged — flagging it would contradict the staleness
   policy every other page already follows. */
{
  const { ctx, page, errors, label } = await fresh('in-window', (route) => route.abort(), RAW)
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(2500)
  const t = await text(page)
  const b = await banner(page)
  if (!homeRendered(t)) problems.push(`${label}: a minutes-old snapshot did not render`)
  if (b) problems.push(`${label}: flagged an answer still inside the one-hour freshness window (${JSON.stringify(b)})`)
  if (errors.length) problems.push(`${label}: uncaught ${errors[0]}`)
  console.log(`  in-window     home rendered=${homeRendered(t)}  banner=${JSON.stringify(b)}`)
  await ctx.close()
}

await browser.close()

console.log(`\n  snapshot dated ${new Date(seededAt).toISOString()}`)
if (problems.length) {
  console.error(`\n${problems.length} problem(s):`)
  problems.forEach((p) => console.error(`  · ${p}`))
  process.exit(1)
}
console.log('\nSeed review passed: the home page renders from the snapshot with the API unreachable, and saved figures are always labelled until live ones replace them.')
