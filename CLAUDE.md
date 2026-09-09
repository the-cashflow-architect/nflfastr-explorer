# Gridiron — working agreement

## Who this is for

Adam is not a developer and **will not read code or review pull requests**. He sees the
product only once it is **deployed to production**. Two consequences, and they are not
negotiable:

- **Push directly to `main` and deploy.** No pull requests, no review gates, no "ready for
  your review". The repository is not public and there is no second pair of eyes coming.
- **"Done" means deployed.** A green build on a branch is not a deliverable. If it is not
  live, it does not exist yet.

Report to him the way `.claude/skills/app-design` describes: plain language, user-visible
behaviour, real risks, and decisions with a recommendation attached — never a list of options
without one.

## Tracking work — Profusia is the system of record

Every workstream, epic, feature, task, bug, risk and decision lives in **Profusia**, and is
updated there as the work moves. The test this has to pass:

> Adam opens a card in Profusia, starts a fresh Claude session, says "go", and Claude has
> enough to do the work without asking him anything.

So a card is not a title. Each one carries what to change, where, why, and what done looks
like. Write them for a session that has never seen this conversation.

- Plan: **nflfastR Explorer** (`pln_7a22db856c9048af9b0d`), unit = Features.
- At the **start** of a session: `get_plans` for that plan before touching anything, so you
  build on what is there instead of duplicating it.
- At the **end** of a session, and as work lands: `update_step` to move statuses, `add_step`
  for work discovered along the way, and `record_turn` when the project's direction actually
  changes — not for routine progress.
- A card that is finished is marked finished. A card that turned out to be wrong is marked
  and says why. A plan padded with non-events is worse than a short one.

## What this product is

The next generation of pro-football-reference.com, built on nflverse data covering
**1999–2025** (the draft reaches back to 1980). `docs/SPEC.md` is the build contract, and
**section 0 records facts measured against the real files** — several of which contradict
what the design originally assumed. Trust section 0 over instinct, and do not re-derive it;
it cost real download time to establish.

## The rules that keep it honest

Honesty is the product. A reference site that is confidently wrong once is finished.

- **A block with no data is removed, not shown empty.** Payloads omit absent blocks so pages
  can omit them.
- **Never render a zero for a gap.** `null` means "we do not have this" and prints as an em
  dash, with a note where one is warranted.
- **Never type a coverage year into a component.** Every window comes from `/api/coverage`,
  which reads the loader's own log. `EraBadge` renders it.
- **The phrase "all-time" appears nowhere.** The floor is 1999; leaderboards say "modern era"
  and carry their window.
- **Anything computed rather than read carries `ComputedByUs`** with its formula — SRS,
  Pythagorean wins, percentiles, the started-proxy, fantasy points, allowed-side team stats.
- **An error is never an empty state.** `QueryBoundary` distinguishes them, because a visitor
  cannot tell a real zero from a broken connection, and one bad guess costs the site its
  credibility.
- **Rates are never stored and never averaged.** Store counts; compute
  `SUM(numerator)/SUM(denominator)` at read time.

## Design

One accent (marker orange), spent only on the single primary action, link hover, and the
current-nav bar. Two semantic colours, for wins and losses alone — a value's standing is
carried by its rank, its percentile bar or bold weight, never by hue. Team colours are data,
not chrome. Tabular numerals everywhere; decimals fixed per stat in `design/format.ts`. Five
chart idioms and no pie charts. Full detail in `docs/SPEC.md` section 6.

## Verifying

Three gates, in order, and the third is the one that catches what matters:

    cd backend && python -m pytest -q          # 395 tests, no network
    cd frontend && npx tsc -b && npx oxlint --deny-warnings && npm run build
    cd frontend && npm run review              # a real browser over every route

The third exists because typecheck, lint and the production build all passed once while every
single route rendered an empty rectangle: one bad property read in a shared component threw
during render and React unmounted the tree. No static check can see that.

Test fixtures generate nflverse-shaped files locally and cover **2001 and 2024** — one season
either side of both the 2002 realignment and the 2006 air-yards charting boundary. Never add a
test that reaches the network.

## Data

`python -m app.build` is a **job you run**, not something a deploy triggers: it pulls ~40
files and writes a database every later start simply opens. Measured on real data: about four
minutes, ~200 MB on disk, 313 MB peak memory. `--report` shows what is loaded and whether the
derived tables are current.

Building and serving have separate memory budgets on purpose — the serving budget cannot
build 27 seasons, and finds out at commit time rather than while streaming.
