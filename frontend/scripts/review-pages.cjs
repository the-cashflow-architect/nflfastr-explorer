/**
 * Screenshot every route against a running app and report what broke.
 *
 *   npm run review            # needs the API on :8000 and the dev server on :5173
 *   ONLY=player npm run review
 *
 * This exists because a green build proves nothing about a page that renders
 * nothing. It was written after typecheck, lint and the production build all
 * passed while every one of the twenty-three routes rendered an empty
 * rectangle: one bad property read in the footer threw during render and React
 * unmounted the tree, which no static check can see.
 *
 * So it reports the three failures only a browser knows about — console errors,
 * failed requests, and a page whose main region is suspiciously short — and
 * leaves a PNG of every route in dark, light and mobile to look through.
 */
const { chromium } = require('playwright')
const fs = require('fs')
const path = require('path')

const EXE = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const BASE = process.env.BASE || 'http://127.0.0.1:5173'
const OUT = process.env.OUT || 'review-shots'
const ONLY = process.env.ONLY

/**
 * Ids from the fixture database (backend/tests/factories.py), which is what
 * this runs against: players are '00-00' + a five-digit index, games are
 * '{season}_{week}_{away}_{home}' over the fixture's eight clubs. These once
 * named real players and games (Mahomes, 2024_01_BAL_KC), so against the
 * documented fixture nine routes answered "We have no record of that" and the
 * sweep could not pass.
 */
const ROUTES = [
  ['home', '/'],
  ['players-index', '/players'],
  ['player-hub', '/players/00-0000000/player-0'],
  ['player-gamelog', '/players/00-0000000/gamelog?season=2024'],
  ['player-splits', '/players/00-0000000/splits?season=2024'],
  ['player-advanced', '/players/00-0000000/advanced?season=2024'],
  // No recent games in the fixture: blocks with no data must be absent, not empty.
  ['player-sparse', '/players/00-0000005'],
  ['teams-index', '/teams?season=2024'],
  ['teams-index-2001', '/teams?season=2001'],
  ['franchise', '/teams/KC'],
  ['franchise-relocated', '/teams/LA'],
  ['team-season', '/teams/KC/2024'],
  ['team-season-2001', '/teams/LA/2001'],
  ['team-roster', '/teams/KC/2024/roster'],
  ['game', '/games/2024_01_BUF_KC'],
  ['game-old', '/games/2001_01_CIN_BAL'],
  // Week 4 of the fixture's 2024 is scheduled but unplayed.
  ['game-future', '/games/2024_04_KC_BUF'],
  ['seasons-index', '/seasons'],
  ['season-hub', '/seasons/2024'],
  ['season-hub-2001', '/seasons/2001'],
  ['standings', '/seasons/2024/standings'],
  ['standings-2001', '/seasons/2001/standings'],
  ['week', '/seasons/2024/week/1'],
  ['leaders-hub', '/leaders'],
  ['leaderboard', '/leaders/passing/passing_yards?scope=season&season_min=2024&season_max=2024'],
  ['leaderboard-rate', '/leaders/passing/yards_per_attempt?scope=season&season_min=2024&season_max=2024'],
  ['draft-index', '/draft'],
  ['draft-class', '/draft/2017'],
  ['finder', '/finder'],
  ['compare', '/compare?players=00-0000000,00-0000005'],
  ['glossary', '/glossary'],
  ['about-data', '/about/data'],
  ['about-privacy', '/about/privacy'],
  ['about-support', '/about/support'],
  ['not-found', '/nope/nope'],
]

/**
 * Interactions the route sweep cannot reach.
 *
 * Loading a page only exercises what renders on arrival. The global search
 * palette shipped broken to production because nothing ever typed into it: its
 * client types were hand-written against the wrong field names, and it threw on
 * the second keystroke. Anything that only runs on input needs a step here.
 */
async function checkInteractions(context, report) {
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + String(e.message).slice(0, 200)))
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 160)) })
  let results = 0
  try {
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
    await page.keyboard.press('Control+k')
    await page.waitForSelector('[role="dialog"] input', { timeout: 10000 })
    // Every fixture player is called "Player N".
    await page.type('[role="dialog"] input', 'player', { delay: 40 })
    await page.waitForTimeout(2500)
    results = await page.locator('[role="dialog"] button').count()
    await page.screenshot({ path: path.join(OUT, 'interaction-search.png') })
  } catch (e) {
    errors.push('SEARCH ' + String(e.message).slice(0, 160))
  }
  report.push({
    name: 'search-palette',
    route: '(Cmd+K, type "player")',
    chars: results * 100,
    words: results,
    errors: [...new Set(errors)].slice(0, 4),
    failed: [],
    snippet: `${results} result row(s) rendered`,
  })
  await page.close()

  await checkHomeSearchCloses(context, report)
  await checkRefusedSave(context, report)
}

/**
 * A saved view the browser refused to store must not be listed as saved.
 * It once was: the write swallowed the error after the list had already
 * shown the view, and it was simply gone on the next visit.
 */
async function checkRefusedSave(context, report) {
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + String(e.message).slice(0, 200)))
  await page.addInitScript(() => {
    const setItem = Storage.prototype.setItem
    Storage.prototype.setItem = function (key, value) {
      if (key === 'gridiron.finder.views') throw new DOMException('The quota has been exceeded.', 'QuotaExceededError')
      return setItem.call(this, key, value)
    }
  })
  try {
    await page.goto(BASE + '/finder?run=1', { waitUntil: 'networkidle', timeout: 45000 })
    await page.fill('input[aria-label="Name this query"]', 'Review view', { timeout: 10000 })
    await page.getByRole('button', { name: 'Save view' }).click()
    await page.waitForTimeout(300)
    const body = await page.locator('main').innerText()
    if (!/Couldn.t save on this device/.test(body)) errors.push('FINDER a refused save said nothing')
    if (await page.getByRole('button', { name: 'Review view', exact: true }).count()) errors.push('FINDER a view the browser refused to store was listed as saved')
  } catch (e) {
    errors.push('FINDER-SAVE ' + String(e.message).slice(0, 160))
  }
  report.push({
    name: 'finder-refused-save',
    route: '(Finder: save a view the browser refuses)',
    chars: errors.length ? 0 : 1000,
    words: 0,
    errors: [...new Set(errors)].slice(0, 4),
    failed: [],
    snippet: errors.length ? 'refused save misreported' : 'refused save reported, not listed',
  })
  await page.close()
}

/**
 * The home page's search box must let go of a visitor.
 *
 * It once trapped them: the hero input opened the palette on focus, the palette
 * hands focus back to whatever had it when it closes, and so Escape or a tap
 * outside reopened it in the same millisecond. At 768px and wider the input is
 * focused on load, so the palette was also up before anyone touched it — on
 * the first screen an iPad App Review tester sees. Only a browser can see this.
 */
async function checkHomeSearchCloses(context, report) {
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push('PAGEERROR ' + String(e.message).slice(0, 200)))
  const dialogs = () => page.locator('[role="dialog"]').count()
  try {
    await page.goto(BASE + '/', { waitUntil: 'networkidle', timeout: 45000 })
    await page.waitForTimeout(300)
    if (await dialogs()) errors.push('HOME the search palette opened by itself on load')
    for (const [how, close] of [
      ['Escape', () => page.keyboard.press('Escape')],
      ['a tap outside it', () => page.mouse.click(8, 8)],
    ]) {
      if (!(await dialogs())) {
        await page.click('#home-search')
        await page.waitForSelector('[role="dialog"]', { timeout: 5000 })
      }
      await close()
      await page.waitForTimeout(300)
      if (await dialogs()) errors.push(`HOME the search palette is still open after ${how}`)
    }
    // Focus is back on the hero; typing into it should still search, not vanish.
    await page.focus('#home-search')
    await page.keyboard.type('pl', { delay: 60 })
    const value = await page.locator('[role="dialog"] input').inputValue({ timeout: 5000 }).catch(() => null)
    if (value !== 'pl') errors.push(`HOME typing into the focused search box reached the palette as ${JSON.stringify(value)}, not "pl"`)
  } catch (e) {
    errors.push('HOME-SEARCH ' + String(e.message).slice(0, 160))
  }
  report.push({
    name: 'home-search-closes',
    route: '(Home: open search, Escape, tap outside)',
    chars: errors.length ? 0 : 1000,
    words: 0,
    errors: [...new Set(errors)].slice(0, 4),
    failed: [],
    snippet: errors.length ? 'palette would not close' : 'palette closes on Escape and on a tap outside',
  })
  await page.close()
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await chromium.launch({ executablePath: EXE })
  const report = []

  for (const theme of ['dark', 'light']) {
    for (const [width, tag] of [[1440, 'desktop'], [390, 'mobile']]) {
      if (tag === 'mobile' && theme === 'light') continue // one mobile pass is enough
      const context = await browser.newContext({
        viewport: { width, height: tag === 'mobile' ? 844 : 1000 },
        deviceScaleFactor: 1,
        colorScheme: theme === 'dark' ? 'dark' : 'light',
      })
      await context.addInitScript((t) => {
        try { localStorage.setItem('gridiron.theme', t) } catch { /* private window */ }
      }, theme)

      for (const [name, route] of ROUTES) {
        if (ONLY && !name.includes(ONLY)) continue
        const page = await context.newPage()
        const errors = []
        const failed = []
        page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)) })
        page.on('pageerror', (e) => errors.push('PAGEERROR ' + String(e.message).slice(0, 200)))
        page.on('response', (r) => {
          if (r.status() >= 400) failed.push(`${r.status()} ${r.url().replace(BASE, '')}`)
        })
        let text = ''
        try {
          await page.goto(BASE + route, { waitUntil: 'networkidle', timeout: 45000 })
          await page.waitForTimeout(700)
          text = (await page.locator('main').innerText().catch(() => '')) || ''
          const file = path.join(OUT, `${theme}-${tag}-${name}.png`)
          await page.screenshot({ path: file, fullPage: true })
        } catch (navError) {
          errors.push('NAV ' + String(navError.message).slice(0, 160))
        }
        if (theme === 'dark' && tag === 'desktop') {
          report.push({
            name, route,
            chars: text.length,
            words: text.split(/\s+/).filter(Boolean).length,
            errors: [...new Set(errors)].slice(0, 4),
            failed: [...new Set(failed)].slice(0, 4),
            snippet: text.replace(/\s+/g, ' ').slice(0, 180),
          })
        }
        await page.close()
      }
      if (theme === 'dark' && tag === 'desktop') await checkInteractions(context, report)
      await context.close()
    }
  }
  await browser.close()
  fs.writeFileSync(path.join(OUT, 'report.json'), JSON.stringify(report, null, 1))
  console.log('route                  chars  errs  fails  first text')
  console.log('-'.repeat(110))
  for (const r of report) {
    const flag = r.errors.length || r.failed.length ? '!!' : r.chars < 300 ? '??' : 'ok'
    console.log(`${flag} ${r.name.padEnd(20)} ${String(r.chars).padStart(6)} ${String(r.errors.length).padStart(5)} ${String(r.failed.length).padStart(6)}  ${r.snippet.slice(0, 60)}`)
  }
  const broken = report.filter((r) => r.errors.length || r.failed.length || r.chars < 300)
  console.log(`\n${broken.length} route(s) need attention:`)
  for (const r of broken) {
    console.log(`\n  ${r.name} (${r.route})  chars=${r.chars}`)
    r.errors.forEach((e) => console.log('    err: ' + e))
    r.failed.forEach((f) => console.log('    net: ' + f))
  }
})()
