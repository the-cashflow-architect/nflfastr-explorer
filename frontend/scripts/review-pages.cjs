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

const ROUTES = [
  ['home', '/'],
  ['players-index', '/players'],
  ['player-hub', '/players/00-0033873/patrick-mahomes'],
  ['player-gamelog', '/players/00-0033873/gamelog?season=2024'],
  ['player-splits', '/players/00-0033873/splits?season=2024'],
  ['player-advanced', '/players/00-0033873/advanced?season=2024'],
  ['player-lineman', '/players/00-0031852'],
  ['teams-index', '/teams?season=2024'],
  ['teams-index-2001', '/teams?season=2001'],
  ['franchise', '/teams/KC'],
  ['franchise-relocated', '/teams/LA'],
  ['team-season', '/teams/KC/2024'],
  ['team-season-2001', '/teams/LA/2001'],
  ['team-roster', '/teams/KC/2024/roster'],
  ['game', '/games/2024_01_BAL_KC'],
  ['game-old', '/games/2001_01_CHI_BAL'],
  ['game-future', '/games/2026_01_NE_SEA'],
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
  ['compare', '/compare?players=00-0033873,00-0036355'],
  ['glossary', '/glossary'],
  ['about-data', '/about/data'],
  ['not-found', '/nope/nope'],
]

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
