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
 *   refresh failed       the saved copy survives the failure, so the next two
 *                        launches still open on dated figures
 *   offline, unsaved     a page never saved says so, and so does the bar;
 *                        search says it needs a connection, never "no match"
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
  // The home page once flashed its empty message for a few frames while the
  // saved copy was read back from disk; too brief to screenshot, so watch for it.
  await ctx.addInitScript(() => {
    new MutationObserver(() => {
      if (document.body?.textContent?.includes('Season data is not available')) window.__falseEmpty = true
    }).observe(document, { childList: true, subtree: true, characterData: true })
  })
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
const flashedEmpty = (page) => page.evaluate(() => window.__falseEmpty === true)

/* ---- 1. server unreachable ---- */
{
  const { ctx, page, errors, label } = await fresh('unreachable', (route) => route.abort())
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForTimeout(4000)
  const t = await text(page)
  const b = await banner(page)
  if (!homeRendered(t)) problems.push(`${label}: the home page did not render from the snapshot — the seed's query keys no longer match the app's`)
  if (!b || !/saved/.test(b)) problems.push(`${label}: figures from the snapshot were shown with no notice saying when they were saved (banner: ${JSON.stringify(b)})`)
  if (await flashedEmpty(page)) problems.push(`${label}: "Season data is not available" flashed while the saved copy was being restored`)
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
  if (await flashedEmpty(page)) problems.push(`${label}: "Season data is not available" flashed while the saved copy was being restored`)
  if (errors.length) problems.push(`${label}: uncaught ${errors[0]}`)
  console.log(`  in-window     home rendered=${homeRendered(t)}  banner=${JSON.stringify(b)}`)
  await ctx.close()
}

/* ---- 4. a refresh fails, and the app is opened again ----
   One run of failed requests once wiped the saved copy. A query whose refresh
   fails keeps its data but flips to 'error', and only 'success' was saved, so
   the snapshot written after the failure was empty: the next launch said
   "Request failed (502)" with nothing on screen, and on a device the bundled
   seed was gone for good, since seedIfEmpty never refills a key that exists. */
{
  const failing = (route) =>
    route.fulfill({ status: 502, headers: { 'access-control-allow-origin': '*' }, body: 'Bad gateway' })
  const { ctx, page, errors, label } = await fresh('relaunch-after-failure', failing)
  const seen = []
  for (const launch of [1, 2, 3]) {
    await page.goto(BASE, { waitUntil: 'domcontentloaded' })
    // The failed refresh, its one retry, and the persister's throttled write.
    await page.waitForTimeout(6000)
    const t = await text(page)
    const b = await banner(page)
    const kept = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? '{}')?.clientState?.queries?.length ?? 0, CACHE_KEY)
    seen.push(`launch ${launch}: home=${homeRendered(t)} saved=${kept}`)
    if (!homeRendered(t)) problems.push(`${label}: launch ${launch} showed no figures — a failed refresh emptied the saved copy`)
    if (!b || !/saved/.test(b)) problems.push(`${label}: launch ${launch} showed saved figures without dating them (banner: ${JSON.stringify(b)})`)
    if (!kept) problems.push(`${label}: after launch ${launch} the saved copy on the device holds nothing`)
  }
  if (errors.length) problems.push(`${label}: uncaught ${errors[0]}`)
  await page.screenshot({ path: join(SHOTS, 'seed-relaunch-after-failure.png') })
  console.log(`  relaunch      ${seen.join('  ')}`)
  await ctx.close()
}

/* ---- 5. the signal goes, and the visitor taps somewhere never saved ----
   React Query holds the fetch until the connection returns, and that state has
   no data, no error and is not loading — so pages fell through to their empty
   message ("No seasons are loaded yet"), /teams rendered a bare heading,
   search said "Nothing matches" for real players, and the bar claimed
   "Showing figures saved …" over a page showing none. */
{
  const { ctx, page, errors, label } = await fresh('offline-unsaved', answer)
  await page.goto(BASE, { waitUntil: 'networkidle' })
  await page.waitForTimeout(1000)
  await ctx.setOffline(true)
  const seen = []
  for (const [name, path] of [['Seasons', '/seasons'], ['Teams', '/teams'], ['Draft', '/draft']]) {
    // A tap on the nav, not a page load: a reload offline would not reach the app at all.
    await page.getByRole('link', { name, exact: true }).first().click()
    await page.waitForURL((url) => url.pathname === path, { timeout: 5000 }).catch(() => {})
    await page.waitForTimeout(800)
    const main = await page.evaluate(() => document.querySelector('main')?.innerText ?? '')
    const b = await banner(page)
    seen.push(`${path}: ${JSON.stringify(main.replace(/\s+/g, ' ').slice(-70))}`)
    if (!/No connection, and this page has not been saved/.test(main)) {
      problems.push(`${label}: offline, ${path} did not say it has no saved copy (main: ${JSON.stringify(main.replace(/\s+/g, ' ').slice(0, 120))})`)
    }
    if (/No seasons are loaded yet/.test(main)) problems.push(`${label}: offline, ${path} claimed nothing is loaded`)
    if (!b || !/not been saved/.test(b)) problems.push(`${label}: offline on ${path}, the bar did not say the page is not saved (banner: ${JSON.stringify(b)})`)
  }
  await page.screenshot({ path: join(SHOTS, 'seed-offline-unsaved.png') })
  await page.keyboard.press('Control+k')
  await page.waitForSelector('[role="dialog"] input', { timeout: 5000 })
  await page.type('[role="dialog"] input', 'player', { delay: 40 })
  await page.waitForTimeout(800)
  const palette = await page.evaluate(() => document.querySelector('[role="dialog"]')?.innerText ?? '')
  if (/Nothing matches/.test(palette)) problems.push(`${label}: offline, search said "Nothing matches" — a missing connection, not a missing player`)
  if (!/No connection/.test(palette)) problems.push(`${label}: offline, search did not say it needs a connection (${JSON.stringify(palette.slice(0, 100))})`)
  if (errors.length) problems.push(`${label}: uncaught ${errors[0]}`)
  console.log(`  offline       ${seen.join('  ')}  search=${JSON.stringify(palette.replace(/\s+/g, ' ').slice(-45))}`)
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
