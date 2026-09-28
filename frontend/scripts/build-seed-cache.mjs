#!/usr/bin/env node
/**
 * Bundle a snapshot of the home page into the app, for its first launch.
 *
 * WHY
 * The API sleeps when idle and takes about 43 seconds to wake. The saved cache
 * covers every launch after the first — but on a fresh install the cache is
 * empty, and the first screen would be a 43-second wait. That is precisely the
 * screen an App Review reviewer sees, and an app that appears to hang gets
 * rejected as incomplete.
 *
 * So at build time this asks the live API for exactly what the home page asks
 * for, in the same order and under the same query keys, and writes it in the
 * format the app's persister restores. On a fresh install the app starts from
 * it, and the FreshnessBanner dates it until the live answer replaces it.
 *
 * The format comes from TanStack's own dehydrate(), not from a hand-built
 * object, so it cannot drift from what the app reads back. The query keys are
 * the one thing mirrored by hand from HomePage.tsx and api/endpoints.ts — and
 * scripts/review-seed.mjs proves in a real browser that the app renders the
 * home page from this file with the API unreachable, so a drift fails there.
 *
 * Run: node scripts/build-seed-cache.mjs   (npm run ios does this for you)
 */
import { QueryClient, dehydrate } from '@tanstack/query-core'
import { readFileSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

const OUT = join(process.cwd(), 'public', 'seed-cache.json')
const CACHE_BUSTER = '' // must match the persister's (none is set in App.tsx)

const fail = (lines) => {
  console.error(`\n${lines.join('\n')}\n`)
  process.exit(1)
}

// The app's API address, from the same file `vite build` reads for production.
const base =
  process.env.VITE_API_BASE_URL ||
  readFileSync('.env.production', 'utf8').match(/^VITE_API_BASE_URL=(.+)$/m)?.[1]?.trim()
if (!base) fail(['No VITE_API_BASE_URL in the environment or .env.production.'])
const API = base.replace(/\/+$/, '')

/**
 * Fetch one answer, waiting out a cold start. A sleeping free-plan service
 * takes the better part of a minute to answer its first request, so the first
 * call gets a long leash and a couple of retries.
 */
async function get(path) {
  let lastError
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const res = await fetch(`${API}${path}`, {
        headers: { Accept: 'application/json' },
        signal: AbortSignal.timeout(120_000),
      })
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
      return await res.json()
    } catch (err) {
      lastError = err
      if (attempt < 3) console.log(`  ${path}: ${err.message} — retrying (the API may be waking)`)
    }
  }
  throw lastError
}

console.log(`  api            ${API}`)
const started = Date.now()

const client = new QueryClient()
const put = (key, data) => client.setQueryData(key, data, { updatedAt: Date.now() })

try {
  // HomePage.tsx: coverage first, because the season depends on it…
  const coverage = await get('/api/coverage')
  put(['coverage'], coverage)
  const season = coverage.latest_completed_season ?? coverage.latest_season_with_games ?? null
  if (!season) throw new Error('coverage names no season')

  // …then the season hub, whose weeks decide which scoreboard the page opens on…
  const hub = await get(`/api/seasons/${season}`)
  put(['season', season], hub)
  const weeks = hub.weeks ?? []
  const latestWeek = weeks.length ? Math.max(...weeks) : undefined

  // …then that scoreboard, under the key WeekStrip and HomePage share.
  if (latestWeek !== undefined) put(['week', season, latestWeek], await get(`/api/seasons/${season}/week/${latestWeek}`))

  console.log(`  home page      season ${season}, week ${latestWeek ?? '—'}  (${((Date.now() - started) / 1000).toFixed(1)}s)`)
} catch (err) {
  if (process.env.ALLOW_NO_SEED === '1') {
    console.warn(`\n  !! Could not build the seed (${err.message}). ALLOW_NO_SEED=1, so continuing without one.`)
    console.warn('  !! A fresh install will open on a ~43-second wait. Do not submit this build.\n')
    process.exit(0)
  }
  fail([
    `Could not build the first-launch snapshot: ${err.message}`,
    '',
    'Without it, a fresh install opens on the API cold start — about 43 seconds of',
    'loading, which is the first thing an App Review reviewer would see. Check the',
    'API is up and build again. (ALLOW_NO_SEED=1 skips this, for a build that will',
    'never be submitted.)',
  ])
}

const clientState = dehydrate(client)
const snapshot = { buster: CACHE_BUSTER, timestamp: Date.now(), clientState }
writeFileSync(OUT, JSON.stringify(snapshot))
console.log(`  wrote          public/seed-cache.json  (${clientState.queries.length} queries, ${(JSON.stringify(snapshot).length / 1024).toFixed(0)} KB)`)
