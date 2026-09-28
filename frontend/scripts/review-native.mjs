/**
 * The app's device-only paths, on a stand-in for the device.
 *
 * Every other review runs in a browser, where isNativePlatform() is false and
 * none of this code runs. That is how a build once shipped with a launch screen
 * nothing ever dismissed: typecheck, lint, the production build and a browser
 * sweep of every route all passed, and on an iPhone the app would have sat on
 * its logo forever, swallowing every touch.
 *
 * So this installs a stub of Capacitor's native bridge — enough for
 * @capacitor/core to believe it is on iOS and for each plugin call to be
 * recorded — and checks what only a device would show:
 *
 *   the launch screen is dismissed, and the status bar set, on the first frame
 *   export buttons, which cannot work in the iOS web view, are not offered
 *   "copy a link" copies the public website address, not capacitor://localhost
 *
 * API calls go to the local fixture API, as `npm run review` does. Nothing
 * reaches the network.
 *
 * Run: node scripts/review-native.mjs   (after `npm run build`; the fixture API on :8000)
 */
import { chromium, devices } from 'playwright'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { extname, join } from 'node:path'

const DIST = join(process.cwd(), 'dist')
const API = process.env.API || 'http://127.0.0.1:8000'
const TYPES = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json',
  '.woff2': 'font/woff2', '.png': 'image/png', '.svg': 'image/svg+xml',
}
const LEADERBOARD = '/leaders/passing/passing_yards?scope=season&season_min=2024&season_max=2024'

const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname)
  for (const candidate of [join(DIST, path), join(DIST, 'index.html')]) {
    try {
      const body = await readFile(candidate)
      res.writeHead(200, { 'Content-Type': TYPES[extname(candidate)] ?? 'application/octet-stream' })
      return res.end(body)
    } catch { /* fall through to the SPA entry */ }
  }
  res.writeHead(404).end()
})
await new Promise((r) => server.listen(0, '127.0.0.1', r))
const base = `http://127.0.0.1:${server.address().port}`

const BUNDLED = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome'
const browser = await chromium.launch(existsSync(BUNDLED) ? { executablePath: BUNDLED } : {})
const problems = []

const ctx = await browser.newContext({ ...devices['iPhone 15 Pro'], permissions: ['clipboard-read', 'clipboard-write'] })
await ctx.addInitScript(() => {
  const calls = []
  window.__calls = calls
  window.webkit = { messageHandlers: { bridge: { postMessage() {} } } }
  const methods = (...names) => names.map((name) => ({ name, rtype: 'promise' }))
  window.Capacitor = {
    PluginHeaders: [
      { name: 'SplashScreen', methods: methods('show', 'hide') },
      { name: 'StatusBar', methods: methods('setStyle', 'show', 'hide') },
      { name: 'Network', methods: methods('getStatus', 'addListener', 'removeAllListeners') },
    ],
    nativePromise: (plugin, method, options) => {
      calls.push({ plugin, method, options })
      if (plugin === 'Network' && method === 'getStatus') return Promise.resolve({ connected: true, connectionType: 'wifi' })
      return Promise.resolve({})
    },
    nativeCallback: () => String(Math.random()),
  }
})
// The built app points at the production API; send it to the fixture instead.
// Headshots and logos come from outside hosts; a device fetches them, this
// does not. (One handler: Playwright tries the last-registered route first.)
await ctx.route('**/*', async (route) => {
  const url = new URL(route.request().url())
  if (url.pathname.startsWith('/api/')) {
    try {
      const response = await route.fetch({ url: `${API}${url.pathname}${url.search}` })
      return await route.fulfill({ response, headers: { ...response.headers(), 'access-control-allow-origin': '*' } })
    } catch {
      return await route.abort()
    }
  }
  if (url.hostname === '127.0.0.1') return await route.continue()
  return await route.abort()
})

const page = await ctx.newPage()
const errors = []
page.on('pageerror', (e) => errors.push(String(e)))

await page.goto(base + '/', { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
const launch = await page.evaluate(() => window.__calls)
if (!launch.some((c) => c.plugin === 'SplashScreen' && c.method === 'hide')) {
  problems.push('the launch screen is never dismissed — the app would sit on its logo, ignoring every touch')
}
const style = launch.find((c) => c.plugin === 'StatusBar' && c.method === 'setStyle')
if (!style) problems.push('the status bar style is never set')

await page.goto(base + LEADERBOARD, { waitUntil: 'networkidle' })
await page.waitForTimeout(500)
const text = await page.evaluate(() => document.body.innerText)
if (text.length < 500) problems.push(`the leaderboard is nearly empty on a device (${text.length} chars) — is the fixture API on ${API}?`)
if (await page.getByRole('button', { name: 'Export as CSV' }).count()) problems.push('"Export as CSV" is offered on a device, where it cannot save anything')
if (await page.getByRole('button', { name: 'Export JSON' }).count()) problems.push('"Export JSON" is offered on a device, where it cannot save anything')

const copy = page.getByRole('button', { name: 'Copy a link to this view' }).first()
if (await copy.count()) {
  await copy.click()
  const copied = await page.evaluate(() => navigator.clipboard.readText())
  if (!copied.startsWith('https://')) problems.push(`"Copy a link" copied ${copied || 'nothing'}, which opens nothing for whoever it is sent to`)
} else {
  problems.push('no "Copy a link to this view" button on the leaderboard')
}

for (const e of errors) problems.push(`page error on a device: ${e}`)

await browser.close()
server.close()

if (problems.length) {
  console.error(`\n${problems.length} problem(s) on the device path:`)
  problems.forEach((p) => console.error(`  · ${p}`))
  process.exit(1)
}
console.log('\nDevice review passed: launch screen dismissed, status bar set, no dead export buttons, shared links are public.')
