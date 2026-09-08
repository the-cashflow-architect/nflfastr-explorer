# Gridiron — build spec

> The next generation of pro-football-reference.com, built on nflverse data.
>
> This document is the single source of truth. Where it and any agent's judgement
> disagree, this document wins. Where it is silent, ask before inventing.

## 0. Verified facts and corrections

Everything in section 0 was measured against the real nflverse files, not assumed.
Several earlier design assumptions were **wrong** and are corrected here. Do not
re-derive these; they cost real download time to establish.

### 0.1 League structure changes inside our data window

| Seasons | Teams | Divisions | Playoff seeds per conference |
|---|---|---|---|
| 1999–2001 | 31 (no HOU) | 6 (AFC/NFC East, Central, West) | 6 |
| 2002–2019 | 32 | 8 (E/N/S/W per conference) | 6 |
| 2020–present | 32 | 8 | 7 |

`teams_colors_logos.csv` carries **current** division only. It must never be used to
group a historical season. A hand-authored season→team→(conference, division)
alignment table is required (~850 rows) and lives in `backend/app/etl/alignment.py`.
The build fails loudly on any team-season with no alignment row.

Franchise moves inside the window (alias → current): `STL`→`LA`, `SD`→`LAC`,
`OAK`→`LV`. `LAR` and `LA` both appear in source files and must normalise to `LA`.

### 0.2 Charting eras — measured null counts in play_by_play

| Field | 1999 | 2005 | 2006 | 2024 |
|---|---|---|---|---|
| plays | 46,136 | 46,823 | 46,299 | 49,492 |
| `air_yards` non-null | **0** | **0** | 17,109 | 18,580 |
| `cpoe` non-null | **0** | **0** | 15,823 | 17,748 |
| `yards_after_catch` non-null | 0 | 0 | 10,213 | 12,136 |
| `epa`, `wp`, `success`, `qb_epa` | full | full | full | full |
| `fixed_drive`, `series_success` | full | full | full | full |

**The air-yards charting boundary is 2006, not 1999.** EPA, WP, success rate and
drive data are complete from 1999. Anything derived from air yards — CPOE, ADOT,
aDOT-based shares, YAC — is **NULL before 2006 and must be written as NULL, never 0.**
The registry exposes this as a first-class coverage window. Two distinct CPOE
windows exist and must be labelled separately: nflfastR CPOE (2006+) and
NGS CPOE (2016+).

Column count is a stable 372 in every season 1999–2025 — no schema drift.

### 0.3 Join keys — measured coverage

- `snap_counts.pfr_player_id` → `players.pfr_id`: **26,557 of 26,612 rows match (99.8%)**.
  Good enough to ship. Unmatched rows render `—` with a note, never `0`.
- `players.pfr_id` is present on 22,648 of 24,826 players (91%).
- `combine.parquet` **carries `pfr_id`** on 7,437 of 8,968 rows. Join on it.
  Do **not** fuzzy-match on name + college + year; college strings differ
  systematically between files ("Ohio St." vs "Ohio State").
- `draft_picks`: `gsis_id` on 11,084 of 12,927; `pfr_player_id` on 11,175.

### 0.4 Approximate Value — what actually exists

`draft_picks.car_av` is **100% NULL in every season**. It does not exist. Any block
specced against "career AV" is wrong as written.

What is populated: `w_av` (10,589 rows), `dr_av` (9,506), and `hof`, `allpro`,
`probowls`, `seasons_started`, `to` (all 12,927 — drafted players only).

Therefore: the honors line uses **`w_av`, labelled "Weighted career AV (PFR, drafted
players only)"**. "Best value by round" ranks on `w_av` against a cohort median
restricted to draft classes at least five seasons old, with the cohort definition
printed on the page. Undrafted players have no AV and no honors row — the block is
removed for them, not shown empty.

### 0.5 Team defence is not in the team dataset

`stats_team_reg`'s `def_*` columns are the team's defensive **production** (sacks,
interceptions, tackles, passes defended). They are **not** yards allowed, points
allowed, or opponent rushing/passing yards.

Allowed-side stats are computed as a self-join of `stats_team_week`: for team T in
season S, sum the offensive rows of T's opponents in the games T played. Points
allowed comes from `games.csv`. Every allowed-side column carries the
`ComputedByUs` marker and the join is documented on `/about/data`.

### 0.6 Drive yard lines are text

`drive_start_yard_line` / `drive_end_yard_line` are strings like `"KC 25"`, `"50"`.
The ETL computes `start_yardline_100` and `end_yardline_100` as integers (yards from
the drive team's own goal line, resolved against `posteam`) and keeps the text only
for display.

### 0.7 Rates are never stored, never averaged

Derived tables store **counts and totals only** — `plays`, `successes`, `epa_total`.
Every rate is computed at read time as `SUM(successes) / SUM(plays)`. Averaging
season rates is wrong and is a review failure.

### 0.8 Playoff seeding

For **completed** seasons, seeds are **read off the bracket in `games.csv`** — who
hosted whom in which round constrains the seeding, so no tiebreaker engine runs on
history and no history can be guessed wrong.

An earlier version of this section said the bracket determines seeding *exactly*.
Measured against real brackets, that is not true in the six-seed era: nothing
separates seed 3 from seed 4 unless those two clubs meet, because swapping the
first-round hosts also swaps their opponents and explains every game equally well.
Verified on the real 2004 AFC bracket (the byes are pinned, the four wild-card
clubs are not) and the real 2001 NFC (nothing is pinned, because St. Louis and
Chicago never met).

So the implementation **enumerates every seeding a bracket allows**. One surviving
candidate means `seed_basis = "postseason results"`. Several means the league's own
ordering — division winners first, then win percentage, then point differential —
picks among them, `seed_basis` says so, and the affected rows carry a note. The
2015 AFC bracket is recovered exactly with no record input at all.

A season counts as completed when it has a played Super Bowl, not when it has no
unplayed games: the 2022 Bills–Bengals game was cancelled and never played, and the
second definition would leave that season permanently "in progress" and stamp
projected seeds onto finished history.

For an **in-progress** season only, a five-level tiebreaker approximation runs and
every seeded row is labelled `projected`, with an explicit "our rules could not break
this tie" marker where they run out. Division ties resolve before wild-card ties.

Playoff field size comes from the alignment table (6 seeds pre-2020, 7 from 2020).

### 0.9 Disk, not memory, is the constraint

DuckDB `DROP TABLE` does not return space to the OS and there is no online VACUUM.
Every lazily-materialised play-by-play season is therefore its own **ATTACHed database
file** (`data/pbp_1999.duckdb`); eviction is `DETACH` + `os.remove`, which actually
reclaims disk. Provision ≥2 GB of disk with headroom, not the ~420 MB the data occupies.

Connection settings are pinned explicitly at open: `SET threads TO 1`,
`SET memory_limit`, `SET temp_directory`. Lazy materialisation is guarded by a
per-season lock; a second request for an in-flight season joins the same wait; a
request for a third distinct season while two are in flight returns an honest
"another season is loading" response rather than queueing a third download.


## 1. The pitch

Every deep feature must roll up into one of these three sentences. If it does not, it does not ship.

1. ONE PAGE PER THING — every player, team-season, game, season and draft class since 1999 has a single permanent, shareable URL that shows everything the data honestly knows about it, laid out like a cockpit built for that one thing.

2. EVERY NUMBER IN CONTEXT — no stat sits alone: each carries its rank among peers, its percentile for the position, the era window it covers, and a click through to the plays that produced it.

3. ASK ANYTHING, FREE — the full query engine is the product, not a paywalled add-on: any leaderboard, split, streak or play search can be built in the browser and shared as a plain URL.


## 2. Route table

| Path | Page | Entity | Primary action (the five-second glance) |
|---|---|---|---|
| `/` | Home | League | The search field — one large input, the only accent-colored element on the page: "Find any player, team, or game" |
| `/players` | Player Index | Player (collection) | The name filter input at the top of the rail |
| `/players/:gsisId/:slug?` | Player Hub | Player | 'Game log' button in the identity header (the only accent element on the page) |
| `/players/:gsisId/gamelog` | Player Game Log | Player · season range | Season segmented control (All / each season) — it is what a returning visitor changes first |
| `/players/:gsisId/splits` | Player Splits | Player · split buckets | Scope selector: one season vs. career range (career splits are the thing PFR charges for) |
| `/players/:gsisId/advanced` | Player Advanced | Player · advanced metrics | Season selector, with an unmissable coverage banner stating which windows have data |
| `/teams` | Teams Index | Team (collection) | Pick a team — the 32-card grid is the page |
| `/teams/:abbr` | Franchise Hub | Franchise | The year-by-year table — its most recent row is the default click target |
| `/teams/:abbr/:season` | Team Season | Team-season | 'Full roster' button in the header — the deepest-value next click for the page's main visitor |
| `/teams/:abbr/:season/roster` | Team Roster | Team-season roster | Position-group tabs (Offense / Defense / Special teams / All) |
| `/games/:gameId` | Game | Game | The win-probability chart — it is the hero block, and its 'biggest swing' marker is the one accent element |
| `/seasons` | Seasons Index | Season (collection) | Pick a season — a compact grid of 1999 through the current season |
| `/seasons/:season` | Season Hub | Season | The week picker above the scoreboard strip |
| `/seasons/:season/week/:week` | Week Scoreboard | Season week | Week navigation (prev/next week arrows plus the picker) |
| `/seasons/:season/standings` | Standings | Season standings | Division / Conference view toggle |
| `/leaders` | Leaders Hub | Leaderboards (collection) | Pick a category — a grid of stat categories |
| `/leaders/:category/:stat` | Leaderboard | Leaderboard | Scope toggle: Career / Single season / Single game |
| `/draft` | Draft Index | Draft (collection) | Pick a draft year |
| `/draft/:year` | Draft Class | Draft class | Round navigation (jump to round 1–7) |
| `/finder` | Finder | Query | 'Run' on the filter builder — the one accent button on the page |
| `/compare` | Compare | 2–6 entities | 'Add' entity search field |
| `/glossary` | Glossary | Stat definitions | Search field |
| `/about/data` | Data & Methods | Coverage and methodology | None — this is a reference document, deliberately without a CTA |

### Global navigation (resolves the critics' orphan-route finding)

`AppShell` owns one quiet header nav row — **Players · Teams · Seasons · Leaders ·
Draft · Finder** — present on every page, current item marked with a 2px accent bar
and nothing else. Home additionally shows six entry tiles covering the same six
destinations plus Compare. Every route in the table above must be reachable from `/`
by following links only; `/compare` is reachable from Home, from any player hub, and
from the player index when two or more rows are selected.

All five player routes share a persistent sub-nav — **Overview · Game log · Splits ·
Advanced** — rendered by `PlayerSubNav`. "Game log" remains the accent primary
action in the header; the sub-nav itself is neutral.


## 3. Page specifications


### `/` — Home

**Entity:** League  
**Primary action:** The search field — one large input, the only accent-colored element on the page: "Find any player, team, or game"


**Blocks, top to bottom:**

- Search hero: oversized input, autofocus on desktop, sample chips beneath it (a current star QB, a team, last week's marquee game) that are real links, not placeholders
- Latest completed week strip: horizontal scroller of that week's final scores, each card linking to /games/:gameId, with a WP-swing sparkline per card
- Standings peek: two collapsed conference panels showing only the current division leaders + seeds; 'Full standings' expands in place, does not navigate
- Three quiet entry tiles (no accent): Leaders, Finder, Draft — one line of copy each
- Coverage footline: 'Play-level data 1999–2025 · Next Gen Stats 2016+ · snap counts 2012+ · draft 1936+ · last refreshed <date>' linking to /about/data

**Progressive disclosure:** Standings are a peek-able collapsible that expands inline. The week strip has a week picker that changes it in place rather than navigating. Everything below the fold is quiet secondary tiles. Nothing on Home requires a page load to explore one level.


**Data:** GET /api/search, GET /api/seasons/{season}/week/{week}, GET /api/seasons/{season}/standings, GET /api/coverage


### `/players` — Player Index

**Entity:** Player (collection)  
**Primary action:** The name filter input at the top of the rail


**Blocks, top to bottom:**

- Filter rail (left, sticky): name search, position group, team, active/retired, season active in, college, draft year
- Virtualized player table: name, position, team(s), first/last season, games, one headline career volume stat for the position group, career AV where present (labeled: PFR career total, drafted players only)
- Row → /players/:gsisId/:slug
- Footer link: 'Need a harder question? Open the Finder' → /finder?mode=player_season

**Progressive disclosure:** Column picker and density control live in the table toolbar. Any filter combination this page does not expose is one click away in the Finder, pre-seeded with the current filters.


**Data:** GET /api/players (list, paged), players.parquet, player_season_reg (career rollup), draft_picks.parquet


### `/players/:gsisId/:slug?` — Player Hub

**Entity:** Player  
**Primary action:** 'Game log' button in the identity header (the only accent element on the page)


**Blocks, top to bottom:**

- Identity header: headshot, display name, position + jersey, current/last team with logo and link, status pill (Active / Last played 20XX), height-weight, age computed from birth_date, college + conference (linked to a college filter in the Finder), draft line ('Round 1, pick 10 · 2017 · KC' linked to /draft/2017), rookie & last season, years of experience
- At-a-glance tiles (exactly four, no color): Games (reg + post), career total in the position's headline volume stat with its modern-era rank, career rate in the position's headline efficiency stat with its position percentile, latest-season snap share (2012+) — each tile states its era window in 10px caption text
- Percentile strip: horizontal neutral bars vs position peers for the selected season (EPA/play, success rate, and 4–6 position-specific metrics), median tick on every bar, season segmented control above it
- Career table (regular season): one row per season-team, multi-team seasons show per-team rows plus a combined row, career total row bolded at the bottom, league-leading cells bolded and tooltipped ('led NFL, 2024'), sortable, exportable
- Playoff career table: same shape, collapsed, renders only if postseason rows exist
- Career trend chart: single line, one metric selector (volume / EPA per play / success rate / snap %), season on x-axis
- Last five games: compact rows linking to /games/:gameId, with 'Full game log' link
- Advanced preview (collapsed): NGS 2016+ and PFR advanced 2018+ headline rows with an explicit coverage banner; 'Open advanced' → /players/:gsisId/advanced
- Similar players (collapsed): 10 comparables from our own published similarity method, labeled 'Our method — not PFR's Approximate Value similarity' with a link to /about/data#similarity
- Combine measurables (collapsed): forty/bench/vertical/broad/cone/shuttle with position percentiles; hidden entirely if the player has no combine row
- Injury history (collapsed): season-by-season report/practice status timeline, 2009+ only, hidden with a coverage note for earlier players

**Progressive disclosure:** Six of the eleven blocks ship collapsed. Game log, splits and advanced are one level down as their own cockpits. The season segmented control re-scopes the percentile strip in place. Any block with no data for this player is removed, never shown empty.


**Data:** GET /api/players/{gsis_id}, GET /api/players/{gsis_id}/percentiles, GET /api/players/{gsis_id}/similar, players.parquet + draft_picks + combine + player_season_reg/post + snap_counts + injuries + ngs_* + advstats_season_* + qbr_season


### `/players/:gsisId/gamelog` — Player Game Log

**Entity:** Player · season range  
**Primary action:** Season segmented control (All / each season) — it is what a returning visitor changes first


**Blocks, top to bottom:**

- Sticky mini-identity bar: headshot thumb, name, position, team, breadcrumb back to the hub
- Scope controls: season selector, Regular / Postseason / Both toggle, fantasy scoring format (Standard / PPR / Half) — format persists per visitor
- Range summary tiles: games, per-game averages for the position's four headline stats over the scoped range
- Game table: Date, Age, Team, @/vs with opponent logo, Result (linked to /games/:gameId, W/L colored), started proxy (snap share ≥ 50%, labeled as a proxy), full position box line, snap counts and % (2012+), game EPA and success rate, fantasy points
- Context rail (right, collapsible): home/away, win/loss, indoor/outdoor, grass/turf split summaries for the scoped range
- Export CSV / JSON and Copy link

**Progressive disclosure:** Column picker hides advanced columns by default for pre-2012 seasons where snaps do not exist. The context rail is collapsible. Deeper situational work escalates to /players/:gsisId/splits.


**Data:** GET /api/players/{gsis_id}/gamelog, player_week + games.csv + snap_counts + player_game_epa (derived)


### `/players/:gsisId/splits` — Player Splits

**Entity:** Player · split buckets  
**Primary action:** Scope selector: one season vs. career range (career splits are the thing PFR charges for)


**Blocks, top to bottom:**

- Sticky mini-identity bar + breadcrumb
- Scope bar: season or season range, Regular / Postseason
- Situation splits table: by down, by distance bucket, red zone (inside 20), goal-to-go (inside 5), first half / second half, by quarter, two-minute — each row with attempts, the position's counting stats, EPA/play, success rate
- Game-context splits table: home/away, win/loss, division game, roof (dome/outdoor/retractable), surface (grass/turf), rest days bucket, temperature bucket, wind bucket
- Opponent splits table (collapsed): career line vs each opponent, sortable
- Small-sample flag: any bucket under 20 plays is rendered muted with an 'n=' badge; nothing is hidden, but nothing pretends to be stable
- Note line: 'Computed from play-level data, 1999–2025' with link to /about/data

**Progressive disclosure:** Opponent splits collapsed. Career-range splits are the default advertised value; single-season is the narrower view. Every table has 'Open in Finder' which reproduces that exact split as an editable query.


**Data:** GET /api/players/{gsis_id}/splits, player_season_situational (derived, all 27 seasons), player_week + games.csv for game-context splits


### `/players/:gsisId/advanced` — Player Advanced

**Entity:** Player · advanced metrics  
**Primary action:** Season selector, with an unmissable coverage banner stating which windows have data


**Blocks, top to bottom:**

- Sticky mini-identity bar + breadcrumb
- Coverage banner: explicit per-source windows for this player ('Next Gen Stats: 2018–2025 · PFR advanced: 2018–2025 · snap counts: 2016–2025 · ESPN QBR: 2018–2025')
- Next Gen Stats table + trend chart (2016+): position-appropriate metrics (time to throw, aggressiveness, CPOE, expected completion %, air yards to sticks / separation, cushion / efficiency)
- PFR advanced table (2018+): pressure %, pocket time, drops, bad-throw %, on-target %, times blitzed / hurried / hit, RPO and play-action splits — labeled 'source: Pro-Football-Reference charting via nflverse'
- Snap share trend (2012+): weekly offense/defense/ST snap % line chart with season selector
- ESPN QBR (QB only): season-level QBR, points added, EPA total, plotted against traditional passer rating
- Every column header carries a glossary popover with the formula

**Progressive disclosure:** Sections with zero coverage for this player are removed and named in the banner instead — the honest empty state. Glossary definitions are popovers, never a page load.


**Data:** GET /api/players/{gsis_id}/advanced, ngs_passing/rushing/receiving.parquet, advstats_season_{pass,rush,rec,def}.parquet, snap_counts_{season}.parquet, qbr_season_level.parquet


### `/teams` — Teams Index

**Entity:** Team (collection)  
**Primary action:** Pick a team — the 32-card grid is the page


**Blocks, top to bottom:**

- Season selector (defaults to latest complete season)
- Eight division panels, AFC then NFC: each team a card with squared logo, a 3px color stripe in the team's primary color, name, that season's record and division finish
- Card → /teams/:abbr/:season; the team name within the card → /teams/:abbr (franchise)

**Progressive disclosure:** Two links per card (season vs franchise) is the whole disclosure model here. No filters, no toolbar — this page is a menu.


**Data:** GET /api/teams?season=, teams_colors_logos.csv, standings (derived from games.csv)


### `/teams/:abbr` — Franchise Hub

**Entity:** Franchise  
**Primary action:** The year-by-year table — its most recent row is the default click target


**Blocks, top to bottom:**

- Identity banner: wordmark, full name, conference/division, team color stripe
- Era badge, prominent: 'Season records shown from 1999. Draft history from 1936.'
- Since-1999 summary tiles: regular-season record, playoff appearances, postseason record, best and worst season by point differential (each linked)
- Year-by-year table: season (linked to /teams/:abbr/:season), W-L-T, W-L%, PF, PA, point diff, SRS, SOS, division finish, playoff result, head coach — 1999 through latest
- Franchise leaders since 1999 (collapsed, category tabs): passing / rushing / receiving / defense / scoring career and single-season top ten, each row linked, each table carrying a persistent 'Since 1999 only' label
- Draft history (collapsed, by decade): all picks 1936–present from draft_picks — flagged as the one block with true deep history
- Head coaches since 1999 (collapsed): coach, seasons, regular-season and postseason record

**Progressive disclosure:** Three of six blocks collapsed. The era badge is not collapsible and not dismissible — it is the honesty contract for this page.


**Data:** GET /api/teams/{abbr}, games.csv (1999–2026), team_season_ratings (derived: SRS, SOS, Pythagorean), player_season_reg (leaders), draft_picks.parquet (1936+)


### `/teams/:abbr/:season` — Team Season

**Entity:** Team-season  
**Primary action:** 'Full roster' button in the header — the deepest-value next click for the page's main visitor


**Blocks, top to bottom:**

- Banner: logo, '2024 Kansas City Chiefs', record, division finish, head coach, prev/next season arrows
- Rating tiles (four): Offense EPA/play with 1–32 rank, Defense EPA/play with 1–32 rank, Points For / Against with ranks, SRS and Pythagorean expected record (both labeled as our computation, formula linked)
- Schedule & results table: week, day, date, opponent with logo, home/away, result, score, running record, that game's team yards / turnovers / EPA, a 40px win-probability sparkline per row, row → /games/:gameId
- Team stats vs opponents table: offense produced and defense allowed side by side with 1–32 rank chips per stat — sourced from stats_team_reg, never summed from player box scores
- Drive profile: average drive start field position, drives per game, and a horizontal stacked bar of drive result mix (TD / FG / punt / turnover / downs / end of half), team and opponent
- Roster leaders: top five by snap share, plus the leader in each headline offensive and defensive stat, each linked
- Special teams (collapsed): field goals by distance bucket, punting, return averages
- Injury summary (collapsed, 2009+): players who missed games, weeks missed
- Full drive log (collapsed): every drive of the season with start, plays, yards, time, result

**Progressive disclosure:** Three blocks collapsed; roster is one level down at its own URL. Rank chips are inline context, not a separate 'advanced' tab. The WP sparkline in each schedule row is the whisper that a full game cockpit exists one click away.


**Data:** GET /api/teams/{abbr}/{season}, stats_team_reg + stats_team_week, games.csv, game_team_stats + drives + wp_series (derived), snap_counts, injuries, player_season_reg


### `/teams/:abbr/:season/roster` — Team Roster

**Entity:** Team-season roster  
**Primary action:** Position-group tabs (Offense / Defense / Special teams / All)


**Blocks, top to bottom:**

- Sticky team-season mini-banner + breadcrumb
- Position-group tabs and a snap-share sort toggle
- Roster table: number, player (linked), position, depth position, age, height, weight, college, entry year, draft club, games played, offense/defense/ST snaps and %, that season's headline stat line, current injury designation for in-progress seasons
- Coverage note: 'Snap counts available 2012 onward' shown only for earlier seasons

**Progressive disclosure:** Column picker; snap columns auto-hidden pre-2012 rather than shown as blanks. Sorting by snap share is the implicit depth chart — we do not ship depth_charts data (cost gate).


**Data:** GET /api/teams/{abbr}/{season}/roster, roster_{season}.parquet, snap_counts_{season}.parquet, player_season_reg, injuries_{season}.parquet


### `/games/:gameId` — Game

**Entity:** Game  
**Primary action:** The win-probability chart — it is the hero block, and its 'biggest swing' marker is the one accent element


**Blocks, top to bottom:**

- Scorebox: both teams with logos and color stripes, final score, quarter-by-quarter line score derived from scoring plays, overtime flag, date, kickoff time, stadium, roof, surface, temperature, wind, referee — each team name links to /teams/:abbr/:season
- Win probability chart (hero): home-team win probability across game seconds, scoring plays as ticks on the axis, hover shows the play and its WPA, clicking a point scrolls-and-highlights that play in the log below; a second toggleable series shows the Vegas-informed model, labeled
- Team stats comparison: first downs, rush/pass/total yards, sacks, turnovers, penalties, third and fourth down conversions, time of possession, EPA/play, success rate — each with a small 'x of 32 that season' context chip
- Scoring summary: chronological scoring plays with quarter, clock, team, description, running score, each deep-linkable
- Drive chart: two rows of horizontal field-position bars, one per team, each bar a drive from start to end yard line, colored neutral with result glyphs; hover reveals plays/yards/time; click filters the play log to that drive
- Box score: tabbed passing / rushing / receiving / defense / kicking / returns for both teams, every player name linked
- Betting line and result (collapsed): closing spread, total, both moneylines, and how the game finished against each
- Snap counts (collapsed, 2012+): offense/defense/ST snaps and % for both teams
- Officials (collapsed): full crew where officials.parquet has it, referee always
- Play-by-play log (collapsed behind a labeled count, e.g. 'All 164 plays'): virtualized table with quarter, clock, down, distance, field position, description, EPA, WPA, success flag; filters for team, quarter, down, play type, and a minimum-|EPA| slider; every row deep-linkable as #play-{play_id}

**Progressive disclosure:** Four blocks collapsed including the 164-row play log — the single biggest DOM cost on the site loads only on request. The drive chart and the WP chart are both filters into the play log: clicking either narrows it, which is how a casual visitor discovers the depth without being shown it first. Pre-2020 games show a one-line notice while the season's play data materializes (2–4s, once per season).


**Data:** GET /api/games/{game_id}, GET /api/games/{game_id}/plays, games.csv, stats_team_week + stats_player_week, drives / scoring_plays / wp_series / game_team_stats (derived, all seasons), pbp_recent (2020+) or lazily materialized pbp_season_{year} (pre-2020), snap_counts, officials


### `/seasons` — Seasons Index

**Entity:** Season (collection)  
**Primary action:** Pick a season — a compact grid of 1999 through the current season


**Blocks, top to bottom:**

- Season grid, newest first: year, Super Bowl winner, and the season's highest-scoring team, each cell linked
- Coverage strip explaining what exists per era, linking to /about/data

**Progressive disclosure:** None needed — this is a menu. Deliberately does not pretend to offer pre-1999 seasons.


**Data:** GET /api/seasons, games.csv, GET /api/coverage


### `/seasons/:season` — Season Hub

**Entity:** Season  
**Primary action:** The week picker above the scoreboard strip


**Blocks, top to bottom:**

- Header: '2024 NFL Season', prev/next arrows, links to standings / leaders / draft class
- Week scoreboard strip with week picker (1–18 plus WC/DIV/CON/SB): score cards linking to /games/:gameId, bye teams listed
- Standings: eight division tables, AFC then NFC, with W-L-T, PF, PA, diff, division and conference records, and seed numbers where the season is complete
- Playoff bracket: a real visual tree, wild card through Super Bowl, seeded, each matchup linked to its game — this is the block PFR does not have
- League EPA quadrant: 32-team scatter of offense EPA/play vs defense EPA/play, logos as marks, quadrant labels, each point linked
- League leaders snapshot (tabbed): top ten passing / rushing / receiving / scoring / defense / EPA per play, each with 'Full leaderboard' link
- Season notes: coverage line for anything era-limited in this year's blocks

**Progressive disclosure:** Standings render division-grouped with a 'Conference seeding' toggle that re-sorts in place. Leader tabs swap without navigation. The bracket is only rendered when postseason games exist — never as an empty shell.


**Data:** GET /api/seasons/{season}, games.csv, standings + team_season_ratings (derived), stats_team_reg, player_season_reg


### `/seasons/:season/week/:week` — Week Scoreboard

**Entity:** Season week  
**Primary action:** Week navigation (prev/next week arrows plus the picker)


**Blocks, top to bottom:**

- Header with season link, week picker, prev/next arrows
- Game cards: teams with logos, final score, overtime and division-game flags, a WP sparkline, the game's biggest single WPA play in one line, and closing spread with the against-the-spread result
- Bye teams row (computed: 32 teams minus teams appearing this week)
- Week leaders (collapsed): best single-game performances of the week by EPA and by fantasy points

**Progressive disclosure:** Week leaders collapsed. Each card is a link into the full game cockpit; the sparkline is the whisper.


**Data:** GET /api/seasons/{season}/week/{week}, games.csv, wp_series + player_game_epa (derived), stats_player_week


### `/seasons/:season/standings` — Standings

**Entity:** Season standings  
**Primary action:** Division / Conference view toggle


**Blocks, top to bottom:**

- Header, season link, view toggle
- Standings tables with W-L-T, W-L%, PF, PA, diff, home, away, division and conference records, streak, SRS, SOS, Pythagorean expected wins
- Seeding column in conference view, with a per-row tiebreaker note naming which rule decided it
- Honesty note: 'Seeds ordered by win percentage, then head-to-head, division record, common games and conference record. Ties our implemented rules cannot break are marked and left in alphabetical order.'

**Progressive disclosure:** Advanced rating columns (SRS/SOS/Pythagorean) are behind the column picker, off by default. The tiebreaker note is a persistent line, not a tooltip.


**Data:** GET /api/seasons/{season}/standings, games.csv, standings + team_season_ratings (derived)


### `/leaders` — Leaders Hub

**Entity:** Leaderboards (collection)  
**Primary action:** Pick a category — a grid of stat categories


**Blocks, top to bottom:**

- Era badge: 'Modern era — 1999 to present. We do not have pre-1999 seasons and do not claim all-time records.'
- Category grid: Passing, Rushing, Receiving, Defense, Kicking, Returns, Scoring, Advanced (EPA / CPOE / success rate) — each opening its default stat
- Quick links: active-player leaders, single-season records, single-game records

**Progressive disclosure:** The hub is a menu; scope switching happens on the leaderboard page itself.


**Data:** GET /api/leaders (metadata), player_season_reg / player_week / play-derived tables


### `/leaders/:category/:stat` — Leaderboard

**Entity:** Leaderboard  
**Primary action:** Scope toggle: Career / Single season / Single game


**Blocks, top to bottom:**

- Header: stat name with its glossary definition inline, era badge
- Scope toggle, position filter, season range, active-only toggle
- Qualified toggle with the threshold written out in full ('qualified: 14 pass attempts per team game'), never a bare checkbox
- Ranked table: rank, player (linked), position, team(s), seasons, value, plus 3–5 supporting columns; the leader row is not styled specially — rank 1 is enough
- Advanced leaderboards carry their own narrower coverage badge (CPOE and NGS metrics: 2016+)
- Export CSV / JSON, Copy link (the full state is in the URL)

**Progressive disclosure:** Supporting columns via the column picker. 'Open in Finder' carries the exact leaderboard into the editable query builder — the edit checkpoint for this surface.


**Data:** GET /api/leaders, player_season_reg / player_season_post / player_week, player_game_epa + player_season_situational (derived) for EPA and success-rate boards, ngs_* for CPOE and NGS boards


### `/draft` — Draft Index

**Entity:** Draft (collection)  
**Primary action:** Pick a draft year


**Blocks, top to bottom:**

- Coverage note: 'Draft results 1936–present. Career outcome columns reflect the full career PFR recorded, not our 1999 stat window.'
- Year grid 1936–present, newest first, with first overall pick shown per year

**Progressive disclosure:** None — a menu. The coverage note prevents the obvious misreading that our 1999 floor applies here.


**Data:** GET /api/draft, draft_picks.parquet


### `/draft/:year` — Draft Class

**Entity:** Draft class  
**Primary action:** Round navigation (jump to round 1–7)


**Blocks, top to bottom:**

- Header: '2017 NFL Draft', prev/next year, pick count
- Class summary tiles: picks, Pro Bowlers, All-Pros, Hall of Famers, median career games — all from draft_picks' own career fields, labeled as such
- Draft board table: round, pick, team (linked), player (linked when a gsis_id exists), position, age, college, last season played, career games, seasons started, Pro Bowls, All-Pros, career AV and draft-team AV — each AV column labeled 'PFR Approximate Value, career total'
- Combine measurables (collapsed): forty, bench, vertical, broad, cone, shuttle, joined by name + college + draft year with a match-confidence badge; unmatched players show blank, never a guessed value
- Best value by round (collapsed): picks whose career AV most exceeds the median AV for their pick slot, with the method stated
- Team filter chips

**Progressive disclosure:** Two blocks collapsed. The combine join's imprecision is surfaced as a badge rather than hidden — an honest join beats a silent wrong one.


**Data:** GET /api/draft/{year}, draft_picks.parquet, combine.parquet (fuzzy join, confidence-flagged), players.parquet for linking


### `/finder` — Finder

**Entity:** Query  
**Primary action:** 'Run' on the filter builder — the one accent button on the page


**Blocks, top to bottom:**

- Mode selector: Player seasons, Player games, Plays, Games, Team seasons — each mode swaps the field catalogue
- Filter builder: chip-based conditions (the existing FilterBar pattern, preserved), each chip removable, '+ Add condition' searching every field in the mode
- Ranking controls: sort, and an optional qualification rule with the threshold written out
- Results table: virtualized, sortable, column picker, rank column optional
- Saved views: name a query, stored in this browser only, stated as such
- Export CSV / JSON with the row cap shown before download; Copy link (every part of the query is in the URL query string, one readable parameter per concept)
- Coverage line per mode: Plays mode states its 1999–2025 window and that pre-2020 seasons load on demand

**Progressive disclosure:** The whole page is one deep feature that rolls up to pitch #3. It opens with a single empty condition and a mode, not with every control expanded. Ranking, qualification and column controls appear only after the first result set exists.


**Data:** POST /api/datasets/{dataset_id}/query (existing), POST /api/datasets/{dataset_id}/rankings (existing), POST /api/datasets/{dataset_id}/export (existing), GET /api/datasets/{id}/schema, /filter-options (existing)


### `/compare` — Compare

**Entity:** 2–6 entities  
**Primary action:** 'Add' entity search field


**Blocks, top to bottom:**

- Entity chips with add/remove, players or teams (not mixed)
- Scope bar: season, career, or a season range
- Percentile bars view (default): one row per metric, one bar segment per entity, median tick, entity legend using neutral tints not team colors
- Table view toggle: the same numbers as a plain comparison table
- Metric set selector: position-appropriate presets plus a custom picker
- Copy link — the comparison is fully in the URL

**Progressive disclosure:** Bars first, table one toggle away — the edit checkpoint. Radar/pizza view is deliberately not offered (see not_building).


**Data:** GET /api/compare?entities=&scope=, player_season_reg / team_season / derived EPA tables


### `/glossary` — Glossary

**Entity:** Stat definitions  
**Primary action:** Search field


**Blocks, top to bottom:**

- Search + category filter
- Definition list: abbreviation, full name, plain-language definition, formula where one exists, source dataset, coverage window
- Anchor links so every popover elsewhere in the app can deep-link here

**Progressive disclosure:** Every column header in the product opens a popover with the short definition and a link to this page's anchor — the page itself is the fallback, not the primary route.


**Data:** GET /api/glossary (existing glossary.py, extended)


### `/about/data` — Data & Methods

**Entity:** Coverage and methodology  
**Primary action:** None — this is a reference document, deliberately without a CTA


**Blocks, top to bottom:**

- Coverage table: every dataset, its source URL, its season window, its row count, and when it was last refreshed (live from /api/coverage, never hardcoded)
- What we do not have: pre-1999 seasons, season-by-season awards and All-Pro selections, transactions, attendance, official starters and inactives, per-season Approximate Value — each with the reason
- Metrics we compute ourselves: SRS, SOS, Pythagorean expectation, playoff seeding, similarity score, the started-proxy, drive aggregations, percentile cohorts — each with its full formula and its known limitation
- How EPA, WPA, CPOE and success rate are defined, and that they come from nflfastR's open model

**Progressive disclosure:** None. This page is the opposite of progressive disclosure by design — it is where everything hidden elsewhere is stated plainly.


**Data:** GET /api/coverage, static authored content


### Corrections applied to the page specs above

These override anything in section 3 that contradicts them.

1. **Player Hub honors line.** The identity header carries an Honors line for drafted
   players: HOF badge where `hof`, then `Pro Bowl 5× · All-Pro 3× · Weighted career AV 142`,
   labelled "PFR career totals, drafted players only". Hidden entirely for undrafted players.
2. **Player Hub tiles are "up to four", not "exactly four".** Offensive-line and
   special-teams players have no `stats_player_reg` row; their hub is a three-tile
   variant (Games · Snap share · Draft line) plus combine and injury blocks. Similar
   Players is suppressed for position groups whose stat vector has fewer than four
   non-zero dimensions, and the exclusion is named on `/about/data#similarity`.
3. **Splits page: no "by quarter" row set.** The situational ETL builds sixteen fixed
   buckets — down 1/2/3/4, distance short/medium/long, red zone, goal-to-go, first
   half, second half, two-minute, leading, tied, trailing, garbage time — and quarters
   are not among them. Halves plus two-minute cover the intent.
4. **Splits are offence-only** (roles: passer, rusher, receiver). The Splits sub-nav
   item is hidden for defensive players and the reason is stated on `/about/data`.
5. **Game page rank chips.** A single game's stat is never chipped "x of 32". Where
   context is shown it is a percentile among all team-games in that season
   ("82nd pct of team-games, 2024"). 1-of-32 ranks appear only on team-season pages.
6. **Season pages render 3 or 4 division panels per conference depending on the
   season**, driven by the alignment table. `/seasons/2001` must render six divisions.
7. **Home shows division leaders and records only** — no seeds. Seeds live on the
   standings page where their derivation can be labelled.
8. **"Open in Finder"** appears only on single-season and single-game tables, which the
   generic query engine can actually express. Career-scope and split tables get
   "Copy link" instead. `derived_player_season_situational` is registered as a sixth
   Finder mode so splits remain explorable.
9. **Fantasy is a first-class surface.** `Fantasy` is a ninth Leaders category (season
   and single-game scopes, PPR/Half/Standard as a scope control computed in SQL from the
   existing box line). Fantasy points per game and positional rank are an available
   headline stat for offensive skill positions on the hub and the index. The scoring
   format is stored once per visitor and shared by every surface that uses it.


## 4. Backend

### 4.1 Datasets

| id | source | seasons | notes |
|---|---|---|---|
| `games` | https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv | 1999–2026 (single file) | 7,548 rows × 46 cols ≈ 2 MB source, ~1.5 MB in DuckDB. Negligible. |
| `teams_meta` | https://raw.githubusercontent.com/nflverse/nflfastR-data/master/teams_colors_logos.csv | n/a | <50 KB. |
| `players` | {release}/players/players.parquet | all | 24,826 rows, project 22 of 39 cols ≈ 4 MB. |
| `draft_picks` | {release}/draft_picks/draft_picks.parquet | 1936–present | 12,927 rows ≈ 3 MB. |
| `combine` | {release}/combine/combine.parquet | all | 8,968 rows ≈ 1.5 MB. |
| `player_season_reg` | {release}/stats_player/stats_player_reg_{season}.parquet | 1999–2025 (27 files) | ~1,900 rows/season ≈ 51k rows, ~90 projected cols ≈ 30 MB. |
| `player_season_post` | {release}/stats_player/stats_player_post_{season}.parquet | 1999–2025 | ~15k rows total ≈ 10 MB. |
| `player_week` | {release}/stats_player/stats_player_week_{season}.parquet | 1999–2025 (27 files) | ~28k rows/season ≈ 760k rows, ~85 projected cols ≈ 110 MB on disk. The largest non-pbp table. |
| `team_week` | {release}/stats_team/stats_team_week_{season}.parquet | 1999–2025 | ~570 rows/season ≈ 15k rows, project ~90 of 138 cols ≈ 8 MB. |
| `team_season` | {release}/stats_team/stats_team_reg_{season}.parquet | 1999–2025 | 32 rows/season ≈ 864 rows ≈ 2 MB. |
| `rosters` | {release}/rosters/roster_{season}.parquet | 1999–2025 | ~2,900 rows/season ≈ 78k rows, project 14 of 36 cols ≈ 12 MB. |
| `snap_counts` | {release}/snap_counts/snap_counts_{season}.parquet | 2012–2025 (14 files) | ~26k rows/season ≈ 365k rows, narrow ≈ 14 MB. (The audit's 554k-rows/season figure belongs to depth_charts, not snap_counts — verified against the source description.) |
| `injuries` | {release}/injuries/injuries_{season}.parquet | 2009–2025 | ~10k rows/season ≈ 170k rows, narrow ≈ 10 MB. |
| `ngs` | {release}/nextgen_stats/ngs_passing.parquet | ngs_rushing.parquet | ngs_receiving.parquet | 2016+ (all seasons in one file per type — the per-season variant does not exist) | three files ≈ 6 MB total. |
| `advstats` | {release}/pfr_advstats/advstats_season_{pass,rush,rec,def}.parquet | 2018+ (season grain only) | four files ≈ 3 MB total. |
| `qbr_season` | {release}/espn_data/qbr_season_level.parquet | 2006+ | <1 MB. |
| `officials` | {release}/officials/officials.parquet | per game | ≈ 2 MB. |
| `pbp_recent` | {release}/pbp/play_by_play_{season}.parquet | 2020–2025 (6 files) | ~50k rows/season ≈ 300k rows, 48-col projection ≈ 55 MB (vs ~1.4 GB for all 380 cols × 27 seasons). |
| `pbp_season_cache` | {release}/pbp/play_by_play_{season}.parquet (on demand, 1999–2019) | lazily materialized, LRU of 2 seasons | ≈ 10 MB per cached season, hard cap 2 tables ≈ 20 MB. Third request drops the least-recently-used table. |
| `derived_drives` | built from pbp during the one-time ETL pass | 1999–2025 | ~5,700 drives/season ≈ 154k rows, narrow ≈ 15 MB. |
| `derived_scoring_plays` | built from pbp during ETL | 1999–2025 | ~3,100/season ≈ 85k rows ≈ 8 MB. |
| `derived_wp_series` | built from pbp during ETL | 1999–2025 | ~1.2 M rows × 5 narrow cols ≈ 25 MB (columnar compresses game_id heavily). |
| `derived_game_team_stats` | built from pbp during ETL | 1999–2025 | 2 rows/game ≈ 15k rows ≈ 3 MB. |
| `derived_player_game_epa` | built from pbp during ETL | 1999–2025 | ~13k rows/season ≈ 350k rows, narrow ≈ 22 MB. |
| `derived_player_season_situational` | built from pbp during ETL | 1999–2025 | ~1,200 players × 16 fixed buckets ≈ 19k rows/season ≈ 520k rows, narrow ≈ 35 MB. |
| `derived_standings_and_ratings` | built from games.csv at load | 1999–2025 | 864 rows ≈ <1 MB. |

### 4.2 Play-by-play column projection

`backend/app/sources.py::PBP_COLUMNS` is the single source of truth. It is **77 of the
file's 372 columns**, verified present in every season from 1999 to 2025. Do not read
the file unprojected, and do not add a column here without adding the ETL that
consumes it.

The projection deliberately includes the player **id** columns (`passer_player_id`,
`rusher_player_id`, `receiver_player_id`, `interception_player_id`,
`fumbled_1_player_id`, `td_player_id`, `penalty_player_id`) — every derived table keys
on `gsis_id`, and the name columns alone cannot support that.

Measured: a projected single-season read is 0.69 s and 49,492 rows.

### 4.3 Endpoints


#### `GET /api/coverage`

The honesty payload. Every dataset's real season window, row count and last-refresh timestamp.


*Request:* none


*Response:* { datasets: [{ id, label, source_url, season_min, season_max, row_count, loaded_at, status: 'loaded'|'loading'|'unavailable' }], generated_at }


*Notes:* Feeds the footer coverage line, every era badge, and /about/data. No coverage string anywhere in the frontend may be hardcoded — this endpoint is the single source. Replaces the current dishonest 'Live nflverse' badge.


#### `GET /api/search`

Global typeahead across players, teams, team-seasons, games, seasons and draft classes.


*Request:* ?q=<string, min 2>&limit=<default 8 per group>


*Response:* { query, groups: [{ type: 'player'|'team'|'team_season'|'game'|'season'|'draft', items: [{ id, label, sublabel, href, logo_url?, headshot_url? }] }] }


*Notes:* Players matched by prefix on a precomputed lowercase search_name, then by contains, ordered by last_season desc so active players surface first. Games matched by 'TEAM at TEAM' and by game_id fragments. Target p95 under 80 ms; it is a single indexed scan of a 25k-row table plus small lookups.


#### `GET /api/players`

Player index, paged and filtered.


*Request:* ?q=&position=&team=&season=&college=&draft_year=&status=&page=&page_size=


*Response:* { rows: [{ gsis_id, slug, display_name, position, teams, first_season, last_season, games, headline_stat, headline_value, career_av }], total, page, page_size }


*Notes:* Career rollup is a GROUP BY over player_season_reg, 51k rows — cheap. Never joins pbp.


#### `GET /api/players/{gsis_id}`

Everything the Player Hub renders in one payload.


*Request:* path param only


*Response:* { identity: {...players.parquet fields, age, slug, headshot_url, team: {abbr,name,logo,colors}}, draft: {year, round, pick, team, class_href} | null, combine: {...} | null, career: { regular: {totals, seasons: [row per season-team]}, postseason: {...} }, honors: { pro_bowls, all_pros, hof, career_av, source_note }, era: { stats_from: 1999, note }, available_tabs: { gamelog: true, splits: bool, advanced: {ngs_from, advstats_from, snaps_from, qbr_from} }, injuries_available: bool }


*Notes:* One endpoint, several small joins: players + draft_picks + combine + player_season_reg + player_season_post + rosters (for per-season team). League-leader flags computed with a window function over player_season_reg per season per stat, min-qualification applied for rate stats.


#### `GET /api/players/{gsis_id}/percentiles`

Percentile bars vs positional peers.


*Request:* ?season=<int|career>&position_group=<override>


*Response:* { scope, cohort: { position_group, season, n, qualification }, metrics: [{ id, label, value, percentile, median, unit, coverage_note }] }


*Notes:* Cohort = all players in the same position_group with at least the stated qualifying volume that season. Percentile computed with PERCENT_RANK() over player_season_reg joined to derived EPA tables. Cohort size n is always returned and always displayed — a percentile without its n is a dishonest number.


#### `GET /api/players/{gsis_id}/gamelog`

Game log rows.


*Request:* ?season=<int|all>&type=reg|post|all&page=&page_size=


*Response:* { rows: [{ game_id, game_href, gameday, season, week, team, opponent, home_away, result, team_score, opp_score, age, ...box_line, offense_snaps, offense_pct, started_proxy, epa, success_rate, fantasy_std, fantasy_ppr, fantasy_half }], totals, averages, splits_summary: { home, away, wins, losses }, coverage: { snaps_from: 2012 } }


*Notes:* player_week filtered by gsis_id (range scan on the build-time sort), left-joined to games.csv, snap_counts and derived_player_game_epa. Fantasy points computed in SQL from the box line — never stored.


#### `GET /api/players/{gsis_id}/splits`

Situational and game-context splits.


*Request:* ?season=<int|career>&season_min=&season_max=&type=reg|post


*Response:* { scope, situation: [{ bucket, label, plays, ...stats, epa_per_play, success_rate, low_sample: bool }], game_context: [{ bucket, label, games, ...stats }], opponents: [{ opponent, games, ...stats }], method_note }


*Notes:* Situation buckets read straight from derived_player_season_situational (a SUM across seasons for career scope) — no pbp scan at request time, which is what makes the free career Split Finder affordable. Game-context and opponent splits are player_week joined to games.csv.


#### `GET /api/players/{gsis_id}/advanced`

NGS, PFR advanced, snaps, QBR.


*Request:* ?season=<int|all>


*Response:* { coverage: { ngs_from, ngs_to, advstats_from, advstats_to, snaps_from, qbr_from }, ngs: { season_rows, weekly_rows }, advstats: [...], snaps: { weekly: [...], season: [...] }, qbr: [...] }


*Notes:* Any source with no rows for this player returns an empty array and is named in coverage — the frontend removes the section and lists it in the banner.


#### `GET /api/players/{gsis_id}/similar`

Comparable players, our own published method.


*Request:* ?limit=10&through_age=<int optional>


*Response:* { method: 'normalized-career-vector-cosine-v1', method_href: '/about/data#similarity', cohort: { position_group, n }, players: [{ gsis_id, display_name, href, score, seasons }] }


*Notes:* Cosine distance over a per-game-normalized career stat vector within position_group, computed at request time over player_season_reg (51k rows, a single GROUP BY + vector op). Explicitly NOT PFR's AV similarity and labeled as such everywhere it renders.


#### `GET /api/teams`

Team index with a season's records.


*Request:* ?season=


*Response:* { season, conferences: [{ conf, divisions: [{ division, teams: [{ abbr, name, nick, logo, colors, wins, losses, ties, division_finish, href }] }] }] }


*Notes:* teams_colors_logos joined to derived standings. Franchise alias table applied so a season's abbreviation resolves to the current franchise.


#### `GET /api/teams/{abbr}`

Franchise hub.


*Request:* path param; ?leaders_category= for the collapsed block


*Response:* { team: {...branding}, era: { seasons_from: 1999, draft_from: 1936 }, summary: { record, playoff_appearances, postseason_record, best_season, worst_season }, seasons: [{ season, href, w, l, t, pct, pf, pa, diff, srs, sos, division_finish, playoff_result, coach }], leaders: { [category]: { career: [...], single_season: [...] } }, draft: [{ season, round, pick, player, position, college, career_av, href }], coaches: [{ name, seasons, w, l, t, playoff_w, playoff_l }] }


*Notes:* Franchise alias resolution is applied to every historical abbreviation. Leaders carry a mandatory since_1999 flag in the payload so the UI cannot render them without the disclaimer.


#### `GET /api/teams/{abbr}/{season}`

Team-season cockpit.


*Request:* path params


*Response:* { team, season, record, division_finish, coach, prev_season, next_season, ratings: [{ id, label, value, rank, of: 32, computed_by_us: bool, formula_href }], schedule: [{ week, gameday, opponent, home_away, result, score, running_record, yards, turnovers, epa_per_play, wp_sparkline: [[secs, wp]...], game_href }], team_stats: [{ stat, label, offense, offense_rank, defense_allowed, defense_rank }], drive_profile: { avg_start_yardline, drives_per_game, result_mix: {...}, opponent_result_mix: {...} }, roster_leaders: [...], special_teams: {...}, injuries_summary: [...], drive_log: [...] }


*Notes:* team_stats comes from stats_team_reg — the structural fix for the current app's summed-player-box-scores bug. WP sparklines are downsampled to 40 points per game server-side so a 17-row schedule ships ~680 points, not 11,000.


#### `GET /api/teams/{abbr}/{season}/roster`

Roster page.


*Request:* ?position_group=


*Response:* { team, season, coverage: { snaps_from: 2012 }, rows: [{ gsis_id, href, number, name, position, depth_chart_position, age, height, weight, college, entry_year, draft_club, games, offense_snaps, offense_pct, defense_snaps, defense_pct, st_pct, stat_line: {...}, injury_status }] }


*Notes:* rosters + snap_counts + player_season_reg + injuries. Snap columns omitted from the payload entirely pre-2012 rather than returned as nulls.


#### `GET /api/games/{game_id}`

Everything on the game page except the play log.


*Request:* path param


*Response:* { header: { game_id, season, week, game_type, gameday, gametime, stadium, roof, surface, temp, wind, referee, overtime, location, div_game, home: {...team, score, record_entering}, away: {...} }, line_score: [{ period, home, away }], win_probability: { points: [{ play_id, secs, home_wp, vegas_home_wp }], markers: [{ play_id, secs, label, wpa }], biggest_swing: { play_id, wpa, description } }, team_stats: [{ stat, label, home, away, home_rank_context, away_rank_context }], scoring: [{ play_id, quarter, clock, team, description, home_score, away_score }], drives: [{ team, number, quarter, start_yard_line, plays, yards, top, result, epa }], box_score: { passing: {home:[],away:[]}, rushing, receiving, defense, kicking, returns }, snaps: {...}|null, betting: { spread_line, total_line, home_moneyline, away_moneyline, ats_result, ou_result }, officials: [...]|null, play_log: { total_plays, source: 'pbp_recent'|'lazy', ready: bool } }


*Notes:* WP points downsampled to at most 200 for the chart; the play log is a separate request. When source is 'lazy' and ready is false, the frontend shows a real progress state and polls once — never a fake skeleton. Every joined table here is small; nothing scans pbp except the derived tables.


#### `GET /api/games/{game_id}/plays`

Filterable play log, loaded only when the visitor opens it.


*Request:* ?team=&quarter=&down=&play_type=&min_abs_epa=&drive=&page=&page_size=(max 500)


*Response:* { rows: [{ play_id, quarter, clock, down, ydstogo, yardline, posteam, description, yards_gained, epa, wpa, success, play_type }], total, page, page_size, source, coverage_note }


*Notes:* Reads pbp_recent for 2020+, or the lazily materialized pbp_season_{year} table otherwise (LRU cap of 2 such tables, dropped oldest-first). A pre-2020 first request triggers the materialization and returns 202 with a retry hint; the UI shows honest progress. Filtered by game_id first, which is a row-group-pruned predicate.


#### `GET /api/seasons`

Season index.


*Request:* none


*Response:* { seasons: [{ season, href, champion, champion_href, top_scoring_team, complete: bool }], coverage_href: '/about/data' }


*Notes:* Derived entirely from games.csv.


#### `GET /api/seasons/{season}`

Season hub.


*Request:* path param


*Response:* { season, weeks: [int], standings: <same shape as /standings>, bracket: { rounds: [{ round, games: [{ game_id, href, home_seed, away_seed, home, away, home_score, away_score }] }] }|null, leaders: { passing:[...], rushing:[...], receiving:[...], scoring:[...], defense:[...], epa:[...] }, epa_quadrant: [{ team, logo, off_epa, def_epa, href }], draft_href }


*Notes:* bracket is null (and the block is not rendered) when no postseason games exist for the season — no empty shell.


#### `GET /api/seasons/{season}/standings`

Full standings with seeding.


*Request:* ?view=division|conference


*Response:* { season, view, groups: [{ label, teams: [{ abbr, name, logo, href, w, l, t, pct, pf, pa, diff, home, away, div, conf, streak, srs, sos, pythagorean_wins, seed, tiebreak_note }] }], tiebreak_rules_implemented: [...], note }


*Notes:* Seeding implements win percentage, then head-to-head, division record, common games and conference record. Any tie those rules cannot break carries an explicit tiebreak_note and is left alphabetical — stated on the page, never silently ordered.


#### `GET /api/seasons/{season}/week/{week}`

Week scoreboard.


*Request:* path params


*Response:* { season, week, games: [{ game_id, href, home, away, home_score, away_score, overtime, div_game, spread_line, ats_result, wp_sparkline, biggest_play: { description, wpa } }], bye_teams: [abbr], week_leaders: { by_epa: [...], by_fantasy: [...] } }


*Notes:* bye_teams computed as the 32-team set minus teams appearing this week.


#### `GET /api/leaders`

Every leaderboard.


*Request:* ?scope=career|season|game&category=&stat=&position=&season_min=&season_max=&active_only=&qualified=&page=&page_size=


*Response:* { scope, stat: { id, label, definition, formula, unit }, qualification: { applied: bool, rule_text, threshold }, era: { from, to, note }, rows: [{ rank, gsis_id, href, player, position, teams, seasons, value, support: {...} }], total }


*Notes:* Career scope is a GROUP BY over player_season_reg (51k rows). Season scope is a window RANK() over the same table. Game scope hits player_week filtered by season range. EPA/CPOE boards read the derived tables and carry their own narrower era block. Ranks use RANK() OVER — never the current app's per-row correlated subquery, which is O(rows × fields) and does not survive 27 seasons.


#### `GET /api/draft`

Draft index.


*Request:* none


*Response:* { years: [{ year, href, picks, first_overall: { player, team, href } }], coverage_note }


*Notes:* draft_picks.parquet only.


#### `GET /api/draft/{year}`

Draft class board.


*Request:* ?team=&round=


*Response:* { year, summary: { picks, pro_bowlers, all_pros, hof, median_games }, picks: [{ round, pick, team, team_href, gsis_id, player, player_href, position, age, college, to, games, seasons_started, allpro, probowls, hof, w_av, car_av, dr_av, combine: {...}|null, combine_match_confidence: 'exact'|'probable'|null }], best_value: [{ pick, player, career_av, slot_median_av, delta }] }


*Notes:* Combine joined on lower(name)+college+draft_year; a non-exact match is flagged, an ambiguous match returns null rather than a guess.


#### `GET /api/compare`

Multi-entity comparison.


*Request:* ?type=player|team&ids=<comma separated>&scope=season|career&season=&metrics=


*Response:* { type, scope, cohort: { label, n }, entities: [{ id, label, href }], metrics: [{ id, label, unit, values: [{ entity_id, value, percentile }], median }] }


*Notes:* Maximum six entities, enforced server-side. Percentiles come from the same cohort logic as the player percentile endpoint so the two surfaces never disagree.


#### `GET /api/glossary`

Stat definitions for popovers and the glossary page.


*Request:* ?ids=<comma separated, optional>


*Response:* { terms: [{ id, abbr, label, definition, formula, source_dataset, coverage_from, coverage_to, anchor }] }


*Notes:* Extends the existing glossary.py. Coverage windows are read from /api/coverage's underlying registry, not duplicated as literals.


#### `POST /api/datasets/{dataset_id}/query | /rankings | /filter-options | /export | GET /schema`

Unchanged generic engine — now the Finder's backend.


*Request:* existing shapes


*Response:* existing shapes


*Notes:* Kept as-is, with two changes: dataset registry gains player_season (1999–2025), player_week (1999–2025), plays (pbp_recent + lazy seasons), games and team_season modes; and ranked_query's correlated subquery is replaced with a single RANK() OVER window pass. No breaking change to request shapes.


## 5. Navigation, search, URLs

GLOBAL SEARCH. One search, everywhere, and it is real. A single component mounted in the app shell: a persistent input in the header on desktop (collapsing to an icon under 900px) and a command palette on Cmd/Ctrl+K and on "/". Both open the same overlay. It queries GET /api/search with a 150ms debounce from 2 characters, and renders grouped results in fixed order: Players, Teams, Games, Seasons, Draft classes. Players show headshot, name, position, and years active; teams show the squared logo and full name; games show "BAL at KC — Jan 28, 2024 — 17-10". Arrow keys move, Enter navigates, Escape closes and returns focus exactly where it was. Recent searches (last five, this browser only, labeled as such) show on an empty query alongside three real example links. The palette also accepts navigation commands typed as text — "2024 standings", "2017 draft" — matched against the route table, not by an LLM. There is exactly one dead-binding rule: if the search endpoint is unreachable, the palette shows the error, never an empty state that looks like "no results".

The Cmd+K claim currently printed in the header is removed until this ships, and ships with it.

BREADCRUMBS. Derived from the URL path on every render, never from click history — a cold-loaded deep link renders the correct trail immediately. The trail is a single line of small text above the page header, each segment a link except the last:
- /players/00-0033873/patrick-mahomes → Players / Patrick Mahomes
- /players/00-0033873/gamelog → Players / Patrick Mahomes / Game log
- /teams/KC/2024 → Teams / Kansas City Chiefs / 2024
- /teams/KC/2024/roster → Teams / Kansas City Chiefs / 2024 / Roster
- /games/2024_01_BAL_KC → Seasons / 2024 / Week 1 / Ravens at Chiefs
- /seasons/2024/week/3 → Seasons / 2024 / Week 3
- /draft/2017 → Draft / 2017
Entity names in the trail come from the loaded payload; while loading, the segment renders the URL-derived label (the team abbreviation, the season, the slug in title case) rather than a shimmer — an honest approximation beats a placeholder. The trail never exceeds four segments; deeper paths elide the middle with an ellipsis that opens a menu.

Sibling navigation is a separate, consistent affordance: prev/next arrows flanking the page title on any page with a natural sequence — season on team-season and season hub, week on week scoreboard, game on the game page (previous and next game for the home team), year on draft class. Keyboard: left/right arrow when no input is focused.

CROSS-LINKING RULES. This is the product's connective tissue and it is enforced structurally, not by discipline. One `EntityLink` component handles every entity reference; tables declare which columns are entity references in their column definitions, and the table renderer wraps them automatically. The rules:
1. Every player name anywhere → /players/{gsis_id}/{slug}. If a row has no gsis_id, the name renders as plain text — never a link that 404s.
2. Every team abbreviation in a season-scoped context → /teams/{abbr}/{season}. In a season-less context → /teams/{abbr}. Franchise aliases resolve to the current abbreviation before the href is built, so a 2015 STL row links to the Rams' franchise page.
3. Every game_id, every date+matchup, and every W/L result cell → /games/{game_id}.
4. Every season number → /seasons/{season}; season inside a team context → /teams/{abbr}/{season}.
5. Every draft line ("Round 1, pick 10, 2017") → /draft/2017, with the team portion linking to that team's 2017 season.
6. Every college name → /finder?mode=player_season&college=<name> — a real query, not a page we do not have.
7. Every abbreviated column header → a glossary popover, and the popover's title links to /glossary#<anchor>.
8. Every leaderboard, split table and season table carries an "Open in Finder" link that reproduces that exact view as an editable query. This is the edit checkpoint: no table in the product is a dead end.

Links are never accent-colored (see design system). They carry a 1px underline at 25% opacity that goes solid and accent-colored on hover — the whole table reads as navigable without a single saturated pixel.

URL AND STATE RULES. The path identifies the entity; query parameters carry view state, one readable parameter per concept (?season=2024&type=post&sort=-epa&cols=a,b,c). No base64 blobs. Filter-level changes use history.replace; navigation uses push. Every parameter degrades independently — an unrecognized parameter is ignored with the rest of the view intact, which is the specific failure the current base64 scheme cannot survive. Old ?state= links are decoded once on load by a compatibility shim and redirected to /finder with the equivalent readable parameters; if decoding fails, redirect to / with no error theatre. The shim is deleted after one release.

Scroll restoration on back-navigation is on for list pages, off for entity pages (which always open at the top). Deep-linked anchors (#play-1247, #drive-6, #glossary-anyA) scroll into view and pulse the target once.

## 6. Design system

ONE ACCENT. The accent is **Marker Orange `#E2603A`** (dark-mode tint `#F2795A`, light-mode shade `#C94A26`). It appears in exactly three places and nowhere else: (1) the single primary action on a page — the search input's focus ring and submit on Home, the "Game log" button on a player hub, "Full roster" on a team-season, "Run" in the Finder, the biggest-swing marker on a win-probability chart; (2) link hover underlines; (3) the current-item indicator in navigation (a 2px bar, not a filled background). It is never a background fill for a tab, pill, chip, badge, tile, or table cell. If a screen has two orange things, one of them is wrong. Rationale for orange over the current blue: it survives adjacency with 32 team colors (no team's primary is this hue at this value), it reads as annotation/highlighter which is exactly its job on a reference site, and it cannot be confused with the win/loss semantics below.

SEMANTIC COLORS — exactly two, both muted, both used only where they carry meaning: **positive `#3C7D5A`** (win, above-median, made field goal, drive ends in a score) and **negative `#A8453B`** (loss, below-median, turnover). Ties and neutral outcomes are foreground-muted gray. There is no third semantic color, no five-step traffic-light tier system, and no per-stat color assignment — the current QuickStats six-hue palette and the DataTable five-hue tier dots are both deleted. A value's standing is communicated by its rank number, its percentile bar, or bold weight — never by hue.

TEAM COLOR. Team colors are data, not chrome. A team's primary color appears only as a 3px stripe on the left edge of a team card, a 3px rule under a team-season page header, and as the mark fill in the league EPA quadrant. Team colors never color text, buttons, backgrounds, or chart lines in any chart where two teams appear together (in a two-team chart, home is a solid neutral line and away is a dashed neutral line, distinguished by direct labels at the line ends, not by a legend).

SURFACES AND ELEVATION. Two surface levels, not five. Dark: page `#0E0F11`, raised `#17191C`, border `rgba(255,255,255,0.09)`. Light: page `#FBFAF8`, raised `#FFFFFF`, border `rgba(0,0,0,0.10)`. Text dark: primary `#E8E6E3`, secondary `#A3A29F`, tertiary `#6E6D6B`. Text light: primary `#1A1918`, secondary `#5C5B59`, tertiary `#8A8987`. Every color is a CSS custom property defined once on `:root` and once under `[data-theme="light"]`; no component hardcodes a hex. The current radial-gradient body background is deleted — it is decoration and it fights every chart.

LIGHT/DARK. Dark is the default; light is a first-class equal, not an afterthought. Three states: system (no attribute), explicit light, explicit dark, stored in localStorage and applied before first paint by an inline script to prevent flash. Every token is redefined for light; no component uses a `light:` one-off utility. Charts read their colors from the same custom properties so they invert correctly with no chart-specific code.

TYPOGRAPHY. One family: Inter (already loaded), system fallback stack. Sizes: page title 24/32 semibold, section header 15/20 semibold, body and table 13/18 regular, caption and coverage notes 11/14 regular in text-tertiary, tile value 28/32 medium. **Every numeral in the product is tabular** — `font-variant-numeric: tabular-nums` is set globally on body and never overridden; columns of numbers that do not align are the single fastest way a stats site looks amateur. Numbers are right-aligned, text left-aligned, always. Decimals are fixed per stat (yards 0, EPA/play 3, rates 1, percentages 1) and defined once in a shared formatter, never per component.

DENSITY. Three table densities — Comfortable (36px rows), Compact (30px, default), Dense (24px) — set from a single control in the table toolbar, persisted per visitor in localStorage, applied to every table in the product. This is the "one predictable place" switch. Off hides, never deletes: hiding a column via the column picker keeps it available and keeps it in the export.

THE FOUR REPEATED PATTERNS. Six agents building six pages must produce these identically:
1. **Page header.** Breadcrumb line (11px, tertiary) → title row (24px title, optional entity mark on the left at 40px, prev/next arrows, one accent primary action right-aligned) → a single metadata line of tertiary text (12px, pipe-separated facts) → a 1px border-bottom. Nothing else. No hero images, no gradient banners.
2. **Tile row.** Exactly four tiles maximum, one row, equal width, no color. Each tile: label (11px tertiary uppercase, letter-spaced 0.04em), value (28px medium), and one line of context (11px tertiary — a rank, a cohort size, or an era window). A tile with no honest context line does not ship.
3. **Section.** Header row (15px semibold title, optional 11px tertiary coverage note on the same line, optional right-aligned controls) → content → 24px gap. Collapsible sections use a chevron on the title, animate height, and remember their open state per page in localStorage. A collapsed section states its content count in the header ("All 164 plays", "Injury history · 6 seasons") — that count is the whisper that there is more.
4. **Table.** Sticky header, sticky first column on horizontal scroll, sortable headers with a small caret, glossary popover on every abbreviated header, zebra striping OFF (a 1px row rule at 6% opacity instead), hover row tint at 4%, right-aligned numerics, entity columns auto-linked, virtualized above 100 rows, and one toolbar: column picker, density, export, copy link. Every table wraps in `overflow-x: auto`; the page body never scrolls horizontally. Empty state is a single sentence naming why there are no rows and, where relevant, the coverage window.

CHART IDIOMS (Recharts, no new libraries). Five idioms and no others:
1. **Win probability** — area chart, 0–100% home win probability, y-axis midline at 50% drawn 1px solid, area filled at 12% opacity in text-primary, line 1.5px. Scoring plays are 6px ticks on the x-axis. The biggest swing is the only accent mark. Hover shows a crosshair, the clock, the score, and the play text.
2. **Sparkline** — 40×14px, 1px line, no axes, no grid, no dots except a 2px dot at the final point. Used in schedule rows and scoreboard cards.
3. **Percentile bar** — 100% width track at 8% opacity, fill in text-secondary, a 1px median tick, the numeric percentile right-aligned outside the bar, cohort size in the row's caption. No color ramp, no gradient.
4. **Trend line** — one metric at a time, x-axis is season or week, 1.5px line, dots only when fewer than 15 points, y-axis starts at data minimum not zero for rate stats and at zero for counting stats, era boundaries drawn as 1px vertical rules with a small label ("NGS from 2016").
5. **Quadrant scatter** — offense vs defense EPA, team logos as 22px marks, league-average crosshair, quadrant labels in tertiary text at the corners.
Every chart: no legend when direct labels will do, no gridlines except a single baseline, no animation on data change beyond a 150ms ease, no tooltips that obscure the point being hovered. Bar charts are horizontal when the category labels are words. **Pie and donut charts are not used anywhere in this product.** Every chart has a table equivalent reachable in one click.

ICONS. lucide-react only, 16px in UI, 14px in tables, 1.5px stroke, always paired with text except in the four universally-understood cases (close, chevron, external link, search). No icon is ever the sole affordance for an action a first-time visitor needs.

MOTION. Two durations: 120ms for state (hover, focus, toggle) and 200ms for layout (collapse, modal). One easing curve. Nothing animates on page load. `prefers-reduced-motion` disables all of it.

COVERAGE AND HONESTY COMPONENTS. Two shared components every page uses rather than writing their own copy: `<EraBadge from={1999} to={2025} note="..."/>` — an 11px tertiary line, never dismissible, rendered above any block whose data window is narrower than the page implies; and `<ComputedByUs formula="..." href="/about/data#srs"/>` — a small superscript marker next to any number we calculate rather than read (SRS, SOS, Pythagorean, similarity, percentiles, started-proxy, fantasy points). Both read their values from /api/coverage. Hardcoding a coverage year anywhere in the frontend is a review failure.

WHAT THE SHELL OWNS. A single AppShell provides header (wordmark, search, theme toggle), breadcrumb, page container (max-width 1280px, 24px gutters, 16px under 640px), and footer (coverage line, link to /about/data, link to nflverse). No page renders its own header chrome.

## 7. What we are deliberately not building

- Per-season Approximate Value, and any AV-based similarity or Hall-of-Fame monitor. PFR's AV is a proprietary formula with no per-season value in any nflverse file, and reimplementing Drinen's method from scratch would produce a number that looks like AV, is not AV, and would be quoted as if it were. We show draft_picks' career AV where it exists, labeled as PFR's career total for drafted players only, and we ship a similarity feature with our own published cosine method under its own name.

- Season-by-season awards: MVP, OPOY, DPOY, Rookie of the Year, Coach of the Year, All-Pro teams and Pro Bowl rosters. No verified source carries which season an honor was earned — draft_picks has career counts only. Fails the honesty test outright; building it would require hand-maintained data we would then have to keep current forever (management-cost gate).

- Transactions logs, draft-day trade trackers, and pick-ownership boards. No transaction dataset exists in the verified sources. Team-changed-between-seasons inference is not a transaction log and would read as one.

- Official starters and inactives per game. Nothing in the verified data marks who started. We ship a snap-share-based started proxy, labeled a proxy, on the game log only — and nowhere present it as the official designation.

- Attendance, game duration, coin toss, and TV network. Not in games.csv or any verified source. Rather than blank cells, these fields do not appear.

- Pre-1999 seasons of any kind, and the phrase 'all-time' anywhere in the product. Our stat floor is 1999 (draft is the sole exception at 1936). Every leaderboard is labeled modern era. Adopting PFR's seamless-looking century of data is the one thing we cannot honestly imitate, so we turn it into a trust advantage instead.

- A coaches hub with career records and coaching trees. games.csv carries only free-text head-coach names per game — no coach IDs, no assistants, no tenure table, and name-variant fragility. We surface head coach as a field on team pages and a small since-1999 coach table on the franchise page, and stop there.

- Officials analytics (crew penalty tendencies). officials.parquet gives assignments; tendencies would need a heavy pbp penalty aggregation for a block PFR itself treats as an afterthought. Fails the adoption test — we cannot name the moment it changes what a fan does next.

- Contract and salary cap data. historical_contracts.parquet is 11MB and its currency and completeness are unverified. Shipping unverified money figures on a reference site is a brand-integrity risk out of proportion to the feature. Revisit only after a validation pass.

- depth_charts_{season}.parquet. 554k rows per season with high churn — larger than every other dataset we load combined, for a page whose job is already done by sorting the roster by snap share. Direct-cost gate; declined.

- Radar / 'pizza' charts as any default view. Harder to read than a sorted percentile bar list, degrade past two entities, and would be a second visual grammar competing with the one we have. The comparison tool ships bars and a table, and nothing else.

- A conversational 'ask the data' box. The audience for hard questions wants an auditable, editable, permalinkable filter builder — which the Finder is. An LLM query box adds token cost per query (direct-cost gate), adds a hallucination surface on a site whose entire promise is accuracy (brand-integrity gate), and would be slower to refine than chips.

- Predictive game-outcome models, power-rating forecasts, and any proprietary 0–100 player grading. We publish an EPA-and-schedule-adjusted team rating with its formula stated, and nothing that claims to know the future or to grade a player's technique from data that does not contain it.

- Live in-progress game state. nflverse releases are post-game; there is no real-time feed in the verified sources. No live badge, no ticking scores, no 'live' label anywhere — which also removes the current app's dishonest 'Live nflverse' header claim.

- User accounts, saved queries on the server, and any ad or paywall surface. Saved views live in the visitor's own browser and say so. No credentials are handled anywhere, which keeps the security gate closed by construction.

- Full 27-season raw play-by-play held in DuckDB. All 380 columns × 27 seasons is roughly 1.4GB and would make every query on a 128MB budget spill to disk on a single-threaded, single-worker instance. We hold six recent seasons projected to 48 columns, precompute the six derived tables that carry the historical value, and materialize an older season on demand behind an LRU of two.


## 8. Value-lens gate report (for the owner)

- GATE 2 — DIRECT COST (hosting). This trips, and it is the one decision that needs your sign-off before anyone builds. Today the app stores about 20MB of data. To cover 1999–2025 with game pages, career totals, splits and win-probability charts, it needs roughly 420MB of stored data — about twenty times more. On Render that is a persistent disk, billed at roughly a quarter of a dollar per gigabyte per month, so the storage itself costs cents. The real question is whether the app still needs only the small 512MB instance. The plan is built so that it does: data is loaded one season at a time, nothing wide is ever held in memory, and the heaviest table (play-by-play) is deliberately not stored in full — we store six recent seasons plus six small summary tables that carry the historical value. RECOMMENDATION: proceed, with two conditions. First, the one-time data build runs as a separate job you trigger, not on every deploy, so a deploy is never a twenty-minute download. Second, we measure memory after the first full build and report the number back to you before shipping; if it does not fit, the fallback is to cut recent play-by-play from six seasons to three, which costs nothing visible except older play logs taking two seconds to open.

- GATE 2 — DIRECT COST (data transfer). A second, smaller cost. Building the historical summaries means reading 27 seasons of the largest files once. Read naively that is over a gigabyte of downloading, repeated every day under the app's current 24-hour refresh rule. The fix is in the plan: we read only the 48 columns we need instead of all 380, which cuts the transfer to roughly 190MB, and we stop refreshing completed seasons entirely — a 2014 season never changes, so it is downloaded once and never again. Only the current season refreshes daily, at a few megabytes. RECOMMENDATION: proceed. This is a fix, not a compromise; it makes the app cheaper to run than it is today on a per-day basis.

- GATE 3 — MANAGEMENT COST (one-way door). Every link in the app is about to change shape. Today a shared link is an unreadable code; after this it is a real address like /players/00-0033873/patrick-mahomes. Any link anyone has already saved will stop working. We keep a translator for old links for one release and then delete it. RECOMMENDATION: proceed now. This is only cheap because the site has not been publicly shared or indexed yet — every week it waits, the cost of doing it grows. It is also the single change that unlocks sharing, browser back/forward, and search-engine traffic, none of which the app has today.

- GATE 3 — MANAGEMENT COST (two complexity islands). Two things in this plan are genuinely intricate and will need care: the NFL's playoff seeding tiebreaker rules, which run seven levels deep with special cases for three-way ties, and the iterative team-strength rating (SRS). RECOMMENDATION: build both, but deliberately incomplete and openly labeled. We implement the first five tiebreaker rules, which resolve the overwhelming majority of real cases, and when a tie falls through we say on the page that our rules could not break it rather than guessing an order. That keeps the code something an AI can hold whole, and it keeps us honest. The alternative — a full rules engine — is weeks of work for a handful of historical edge cases nobody will look up.

- GATE 5 — BRAND INTEGRITY (the honesty problem this plan is designed around). Our data starts in 1999. The site we are competing with covers a century. If we ever print the words 'all-time' next to a leaderboard, we are wrong, and one screenshot of Dan Marino missing from a passing-yards list would do more damage than any feature could repay. RECOMMENDATION: turn it into the differentiator. Every leaderboard says 'modern era, 1999–present'. Every block whose data starts later than the page implies carries its own small window label. There is a page, /about/data, that lists everything we have, everything we do not have, and every number we calculate ourselves with its formula. Competitors blur their coverage boundaries; being the site that states them is a durable brand position, not an apology.

- GATE 5 — BRAND INTEGRITY (three things in the app today that are not honest, being removed). The header currently says 'Live nflverse' beside a green dot; the data is a static snapshot with no live refresh, so that comes out and is replaced with a real 'data through [date]' line driven by the actual load timestamp. The Team Defense view sums individual defenders' tackles and presents it as team defense; it cannot show points or yards allowed and is being replaced with the real team dataset. And the header advertises a Cmd+K search that does nothing on the home screen; the shortcut ships with a search that actually exists, or the claim comes off. RECOMMENDATION: all three, immediately, in the first work package. These are not features, they are corrections.

- GATE 1 — VISION FIT (the Finder). The free query builder is the most powerful thing here and the most likely to sprawl into a database console with a hundred knobs. It passes the adoption test — a fantasy manager on a Wednesday asking 'which running backs had 100 yards in a game on the road this year' has no free way to answer that today — and it rolls up cleanly to the third pitch concept. RECOMMENDATION: proceed, with a hard rule: the Finder opens with one empty condition and a mode selector, and nothing else. Ranking, qualification and column controls appear only after the first result exists. Every leaderboard and split table in the site has an 'Open in Finder' link, so the depth is discovered by people who need it rather than displayed to people who do not.

- GATE 4 — SECURITY. No gate trips. Everything is public read-only sports data, there are no accounts, no credentials are stored or requested, saved views live in the visitor's own browser, and the only outbound network calls are to nflverse's public files. Worth stating plainly so it stays true: if anyone later proposes accounts or server-side saved queries, that is a new decision, not an extension of this one.

- NOT A GATE, BUT A DECISION YOU SHOULD KNOW ABOUT. The accent color changes from blue to a warm orange. The reason is practical, not cosmetic: this site will show 32 team color schemes on the same pages, and a blue accent collides with roughly a third of them, which is why the current app's blue reads as a default rather than a choice. Orange sits apart from every team's primary color, and it lets us keep green and red exclusively for wins and losses. It is spent on one thing per screen and nowhere else.


## 9. Work packages


### P1 — Backend foundation: dataset registry, loader, coverage, router skeleton

**Depends on:** —


**Owns:**

- `backend/app/config.py`
- `backend/app/sources.py`
- `backend/app/loader.py`
- `backend/app/main.py`
- `backend/app/routers/__init__.py`
- `backend/app/routers/coverage.py`
- `backend/app/routers/search.py (empty stub)`
- `backend/app/routers/players.py (empty stub)`
- `backend/app/routers/teams.py (empty stub)`
- `backend/app/routers/games.py (empty stub)`
- `backend/app/routers/seasons.py (empty stub)`
- `backend/app/routers/leaders.py (empty stub)`
- `backend/app/routers/draft.py (empty stub)`
- `backend/app/routers/compare.py (empty stub)`
- `backend/app/repo/__init__.py`
- `backend/app/repo/base.py`
- `backend/tests/test_loader.py`
- `backend/tests/test_coverage.py`

**Job:** Replace the three-dataset hardcoded registry with a declarative source registry covering all datasets in the backend spec, each with its season range, column projection and refresh policy. Implement per-dataset TTL: a completed season is loaded once and never re-downloaded; only the current season and games.csv refresh on the 24-hour clock. Implement DuckDB httpfs remote-parquet reading with column projection pushed to the reader, falling back to the existing stream-to-disk path when httpfs is unavailable. Add a build_all CLI entrypoint (python -m app.build) that materializes everything one season at a time so a deploy never triggers a long download. Register every router module up front so downstream packages only ever touch their own file. Ship GET /api/coverage. Replace ranked_query's correlated-subquery ranking with a single RANK() OVER window pass. Do not touch query_builder's WHERE/ORDER logic or the existing generic endpoint shapes.


**Acceptance:**

- python -m app.build completes on a 512MB container with peak RSS under 400MB, verified by logging RSS after each dataset
- GET /api/coverage returns a real season_min/season_max/row_count/loaded_at for every registered dataset, and 'loading' rather than an error for one not yet built
- Re-running build with a warm database re-downloads only the current season and games.csv; a log line proves completed seasons were skipped
- Existing /api/datasets/* endpoints still pass backend/tests/test_api.py unchanged
- /api/datasets/{id}/rankings produces identical output to the previous implementation on the existing fixtures, with no correlated subquery in the generated SQL
- All eight stub routers are registered and return 501 with a clear message until their owning package lands

### P2 — Frontend foundation: real routing, design system, shell, shared UI

**Depends on:** P1


**Owns:**

- `frontend/package.json`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/routes.tsx`
- `frontend/src/index.css`
- `frontend/src/design/tokens.css`
- `frontend/src/design/format.ts`
- `frontend/src/components/shell/AppShell.tsx`
- `frontend/src/components/shell/Header.tsx`
- `frontend/src/components/shell/Breadcrumb.tsx`
- `frontend/src/components/shell/Footer.tsx`
- `frontend/src/components/ui/PageHeader.tsx`
- `frontend/src/components/ui/TileRow.tsx`
- `frontend/src/components/ui/Section.tsx`
- `frontend/src/components/ui/DataTable.tsx`
- `frontend/src/components/ui/EntityLink.tsx`
- `frontend/src/components/ui/EraBadge.tsx`
- `frontend/src/components/ui/ComputedByUs.tsx`
- `frontend/src/components/ui/GlossaryPopover.tsx`
- `frontend/src/components/ui/DensityControl.tsx`
- `frontend/src/components/ui/ColumnPicker.tsx`
- `frontend/src/components/ui/ExportMenu.tsx`
- `frontend/src/components/ui/CopyLinkButton.tsx`
- `frontend/src/components/ui/EmptyState.tsx`
- `frontend/src/components/charts/Sparkline.tsx`
- `frontend/src/components/charts/PercentileBar.tsx`
- `frontend/src/components/charts/TrendLine.tsx`
- `frontend/src/components/ThemeToggle.tsx`
- `frontend/src/hooks/useQueryParamState.ts`
- `frontend/src/hooks/useCoverage.ts`
- `frontend/src/api/client.ts`
- `frontend/src/lib/teams.ts`
- `frontend/src/lib/entityHrefs.ts`

**Job:** Add react-router-dom (the only new dependency) and stand up the full route table with placeholder page components each package will replace. Implement the design system exactly as specified: one accent, two semantic colors, two surface levels, tokens as CSS custom properties for both themes, tabular numerals globally, no gradients. Build the four repeated patterns (PageHeader, TileRow, Section, DataTable) and the three chart primitives. DataTable must support sticky header and first column, sort, column picker, three densities persisted to localStorage, virtualization above 100 rows, automatic entity-column linking via EntityLink, glossary popovers on headers, and an honest empty state. Implement path-derived breadcrumbs and the readable-query-param state hook. Delete App.css, the six-hue QuickStats palette, the five-hue tier-dot system, the radial-gradient background, the 'Live nflverse' badge, and the dead Cmd+K binding (P3 restores the shortcut with a working search).


**Acceptance:**

- Every route in the spec resolves, renders its breadcrumb correctly on a cold load with no prior navigation, and browser back/forward works
- Theme toggles between system/light/dark with no flash of the wrong theme on first paint
- A grep for hex colors outside design/tokens.css returns nothing
- A grep for the string 'Live' in the header, and for App.css, returns nothing
- DataTable renders 5,000 rows at 60fps in a scroll test, keeps the header and first column pinned, and never causes horizontal scroll on the page body
- Density and column-picker choices survive a reload; hiding a column keeps it in the CSV export
- All numerals align in a column of mixed-width values at every density

### P3 — Search, command palette, and Home

**Depends on:** P1, P2


**Owns:**

- `backend/app/routers/search.py`
- `backend/app/repo/search.py`
- `backend/tests/test_search.py`
- `frontend/src/components/search/SearchInput.tsx`
- `frontend/src/components/search/CommandPalette.tsx`
- `frontend/src/pages/Home/HomePage.tsx`
- `frontend/src/pages/Home/WeekStrip.tsx`
- `frontend/src/pages/Home/StandingsPeek.tsx`
- `frontend/src/api/search.ts`
- `frontend/src/hooks/useKeyboardShortcuts.ts`

**Job:** Build GET /api/search over a precomputed lowercase search_name column on players plus teams, games, seasons and draft classes, grouped and prefix-weighted with active players first. Build the one global search: header input on desktop, Cmd/Ctrl+K and '/' palette everywhere, arrow-key navigation, Enter to navigate, Escape restoring focus. Recent searches from localStorage, labeled as local. Route-name matching for typed navigation commands. Build Home to the spec: search hero as the single accent element, latest-week scoreboard strip with real WP sparklines, a collapsible standings peek that expands in place, three quiet entry tiles, and a coverage footline read from /api/coverage.


**Acceptance:**

- Typing two characters returns grouped results in under 150ms on a warm instance; p95 measured and reported
- Cmd+K works on every route including Home, and the shortcut is only advertised where it works
- Five-second glance test on Home: the eye lands on the search field and nothing else is accent-colored
- The standings peek expands and collapses without navigating and without a layout jump
- No sample chip, example link, or recent search on Home is a placeholder — every one resolves to a real page
- When the search endpoint fails, the palette shows the error, never an empty 'no results' state

### P4 — Play-by-play ETL: the six derived tables and the lazy season cache

**Depends on:** P1


**Owns:**

- `backend/app/etl/__init__.py`
- `backend/app/etl/pbp_derive.py`
- `backend/app/etl/buckets.py`
- `backend/app/repo/pbp.py`
- `backend/tests/test_pbp_derive.py`

**Job:** Build the one-season-at-a-time ETL that produces derived_drives, derived_scoring_plays, derived_wp_series, derived_game_team_stats, derived_player_game_epa and derived_player_season_situational for 1999–2025, reading each season's parquet with the 48-column projection and inserting results into permanent tables before releasing the season. Implement the sixteen fixed situational buckets exactly as listed in the backend spec — a fixed list, never a cross-product. Implement the pbp_recent table for 2020–2025 and the lazy pbp_season_{year} materializer with a strict LRU cap of two cached seasons and a status API the games router can report honestly. Every function here must be callable per-season and must not hold more than one season in memory.


**Acceptance:**

- All six derived tables build for 1999–2025 with peak RSS under 400MB, one season at a time, logged
- Row counts are within 10% of the estimates in the backend spec; any larger deviation is reported before merge, not absorbed
- Spot-check three known games across three eras: drive counts, scoring plays, and final score reconstructed from scoring plays all match games.csv
- derived_wp_series covers every game in games.csv for 1999–2025 that has a pbp file; gaps are enumerated in the build log, not silently dropped
- Requesting a third lazy season drops the least-recently-used table and never exceeds two cached season tables on disk
- A career splits query for one player across 27 seasons returns in under 300ms and touches no pbp table

### P5 — Standings, ratings, and franchise continuity

**Depends on:** P1


**Owns:**

- `backend/app/etl/standings.py`
- `backend/app/etl/ratings.py`
- `backend/app/etl/franchises.py`
- `backend/app/repo/standings.py`
- `backend/tests/test_standings.py`
- `backend/tests/test_ratings.py`

**Job:** Compute from games.csv, at load time: per team-season W-L-T, PF, PA, differential, home/away/division/conference records, streak, division finish and playoff result; SRS, OSRS, DSRS, SOS, margin of victory and Pythagorean expected wins; and conference seeding implementing win percentage, head-to-head, division record, common games and conference record — with an explicit tiebreak_note on every seeded row and an unbroken-tie marker where the implemented rules run out. Ship the hand-maintained franchise alias table (STL/LA, SD/LAC, OAK/LV, WAS variants) and a resolver every other package uses so historical abbreviations map to the current franchise.


**Acceptance:**

- Standings for 2024, 2015 and 2001 match the official final standings including division order
- Seeding for five sampled seasons matches the official playoff seeds; any mismatch is traced to a named unimplemented tiebreaker and surfaced in tiebreak_note, never silently ordered
- SRS values sum to approximately zero across the league in every season, and the iterative solve converges in under 50 iterations for all 27 seasons
- A 2015 St. Louis row and a 2016 Los Angeles row resolve to the same franchise page
- Every computed metric has a formula string exposed for the ComputedByUs marker

### P6 — Player cockpit: hub, game log, splits, advanced, index

**Depends on:** P1, P2, P4


**Owns:**

- `backend/app/routers/players.py`
- `backend/app/repo/players.py`
- `backend/app/repo/percentiles.py`
- `backend/app/repo/similarity.py`
- `backend/tests/test_players.py`
- `frontend/src/pages/Players/PlayerIndexPage.tsx`
- `frontend/src/pages/Players/PlayerHubPage.tsx`
- `frontend/src/pages/Players/PlayerGameLogPage.tsx`
- `frontend/src/pages/Players/PlayerSplitsPage.tsx`
- `frontend/src/pages/Players/PlayerAdvancedPage.tsx`
- `frontend/src/pages/Players/blocks/*.tsx`
- `frontend/src/api/players.ts`
- `frontend/src/lib/fantasy.ts`

**Job:** Build the six player endpoints and the five player pages exactly as specced. Player identity is gsis_id everywhere; display_name is render-only. League-leader bolding computed with a window function including rate-stat qualification. Percentile cohorts always return and always display their n. Similarity ships under its own published name with a link to its method. Blocks with no data for a player are removed, never rendered empty. The advanced page's coverage banner is generated from real per-player data windows, not from constants.


**Acceptance:**

- A player who changed teams mid-season renders per-team rows plus a combined row, and the career total row equals the sum of the season rows
- A player with no combine, no postseason and no NGS coverage renders a clean page with those blocks absent and named in the coverage banner — no empty tables
- Career splits for a 15-season player load in under 500ms end to end
- Every player name, team abbreviation, season and result on all five pages is a working link
- Six of the eleven hub blocks are collapsed on first load, and each collapsed header states its content count
- No number derived by us (percentile, similarity, started-proxy, fantasy points) renders without its ComputedByUs marker

### P7 — Team cockpit: index, franchise hub, team-season, roster

**Depends on:** P1, P2, P5


**Owns:**

- `backend/app/routers/teams.py`
- `backend/app/repo/teams.py`
- `backend/tests/test_teams.py`
- `frontend/src/pages/Teams/TeamIndexPage.tsx`
- `frontend/src/pages/Teams/FranchisePage.tsx`
- `frontend/src/pages/Teams/TeamSeasonPage.tsx`
- `frontend/src/pages/Teams/TeamRosterPage.tsx`
- `frontend/src/pages/Teams/blocks/*.tsx`
- `frontend/src/api/teams.ts`

**Job:** Build the four team endpoints and four pages. Team stats come from stats_team_reg and stats_team_week — the old client-side aggregation of player box scores is deleted, and TeamsExplorer.tsx is removed in this package. Schedule rows carry server-downsampled 40-point WP sparklines. Rank chips are inline 1-of-32 context, not a separate advanced tab. Franchise leaders carry a non-dismissible since-1999 label enforced by the payload flag. Franchise alias resolution applied throughout.


**Acceptance:**

- Team defense on a team-season page shows real points and yards allowed from the team dataset; a grep proves no player-row summation remains anywhere in the frontend
- frontend/src/components/TeamsExplorer.tsx no longer exists and nothing imports it
- A 17-row schedule renders 17 sparklines with under 700 total data points transferred
- Every stat in the team stats table carries a 1-of-32 rank chip for both the offense and the defense side
- The franchise page's era badge is present, non-dismissible, and states both the 1999 stat floor and the 1936 draft floor
- A relocated franchise's year-by-year table is continuous across the relocation season

### P8 — Game cockpit: box score, drives, win probability, play log

**Depends on:** P1, P2, P4


**Owns:**

- `backend/app/routers/games.py`
- `backend/app/repo/games.py`
- `backend/tests/test_games.py`
- `frontend/src/pages/Games/GamePage.tsx`
- `frontend/src/pages/Games/blocks/*.tsx`
- `frontend/src/components/charts/WinProbabilityChart.tsx`
- `frontend/src/components/charts/DriveChart.tsx`
- `frontend/src/components/games/PlayLog.tsx`
- `frontend/src/api/games.ts`

**Job:** Build the two game endpoints and the full game page. The win-probability chart is the hero and the only place the accent appears (on the biggest-swing marker). The drive chart is an interactive field-position bar set; clicking a drive filters the play log. The play log is collapsed behind a labeled count, virtualized, filterable by team/quarter/down/type/minimum absolute EPA, and every row is deep-linkable as #play-{play_id}. Pre-2020 games show a real progress state while the season materializes and then load normally; there is no fake skeleton and no silent failure. Snap counts, officials and betting are collapsed blocks that disappear entirely when the data window does not cover the game.


**Acceptance:**

- A 2024 game and a 2001 game both render a complete page: scorebox, line score, WP chart, team stats, scoring summary, drives, box score
- The 2001 game's first load shows an honest progress state naming what is loading, completes in under 6 seconds, and subsequent games in that season load immediately
- Clicking a scoring marker on the WP chart scrolls to and highlights that play in the log; clicking a drive bar filters the log to that drive
- A shared #play-1247 URL opens the log expanded, scrolled to that play, with the play pulsed once
- The play log renders 170 rows without the page body scrolling horizontally, at 60fps
- A pre-2012 game omits the snap counts block entirely rather than rendering it empty

### P9 — Season cockpit: hub, standings, week scoreboard, playoff bracket

**Depends on:** P1, P2, P5


**Owns:**

- `backend/app/routers/seasons.py`
- `backend/app/repo/seasons.py`
- `backend/tests/test_seasons.py`
- `frontend/src/pages/Seasons/SeasonIndexPage.tsx`
- `frontend/src/pages/Seasons/SeasonHubPage.tsx`
- `frontend/src/pages/Seasons/StandingsPage.tsx`
- `frontend/src/pages/Seasons/WeekPage.tsx`
- `frontend/src/pages/Seasons/blocks/*.tsx`
- `frontend/src/components/charts/PlayoffBracket.tsx`
- `frontend/src/components/charts/EpaQuadrant.tsx`
- `frontend/src/api/seasons.ts`

**Job:** Build the four season endpoints and four pages. The playoff bracket is a real visual tree — wild card through Super Bowl, seeded, every matchup linked — and is the block PFR does not have; it renders only when postseason games exist. The EPA quadrant plots 32 teams with logo marks and league-average crosshairs. Standings offer a division/conference toggle that re-sorts in place, with advanced rating columns behind the column picker and off by default, and the tiebreaker note rendered as persistent page text.


**Acceptance:**

- The bracket renders correctly for a 12-team-field season and a 14-team-field season, and is absent for an in-progress season with no postseason games
- Seeds shown on the bracket match the seeds on the standings page for every sampled season
- The division/conference toggle re-sorts without a navigation or a refetch
- Every team logo mark in the quadrant is a working link and the chart is readable in both themes
- The week scoreboard's bye-team list is correct for a sampled week in 2020 and 2024
- The tiebreaker note is visible page text, not a tooltip

### P10 — Leaders and Draft

**Depends on:** P1, P2, P4


**Owns:**

- `backend/app/routers/leaders.py`
- `backend/app/repo/leaders.py`
- `backend/app/routers/draft.py`
- `backend/app/repo/draft.py`
- `backend/tests/test_leaders.py`
- `backend/tests/test_draft.py`
- `frontend/src/pages/Leaders/LeadersHubPage.tsx`
- `frontend/src/pages/Leaders/LeaderboardPage.tsx`
- `frontend/src/pages/Draft/DraftIndexPage.tsx`
- `frontend/src/pages/Draft/DraftClassPage.tsx`
- `frontend/src/api/leaders.ts`
- `frontend/src/api/draft.ts`

**Job:** Build the leaderboard endpoint across career, single-season and single-game scopes with position filtering, season ranges, active-only, and a qualification rule whose threshold is always written out in words. Every leaderboard carries the modern-era badge; EPA and NGS boards carry their own narrower window. Build the draft index and class board including the combine join with an explicit match-confidence flag (ambiguous matches return null, never a guess) and a best-value-by-round block whose method is stated on the page.


**Acceptance:**

- No leaderboard anywhere in the product uses the word 'all-time'; the era badge is present on every one
- Qualification is stated as a full sentence with its numeric threshold, never as a bare checkbox label
- Career, season and game scopes each return in under 400ms for the widest case
- A 2017 draft class shows combine measurables with confidence flags, and at least one deliberately ambiguous name renders blank rather than a wrong match
- Every leaderboard has a working 'Open in Finder' link that reproduces the same rows in the query builder
- The draft index's coverage note explains that draft history reaches 1936 while stats start in 1999

### P11 — Finder and Compare

**Depends on:** P1, P2, P6


**Owns:**

- `backend/app/routers/compare.py`
- `backend/app/repo/compare.py`
- `backend/app/filter_config.py`
- `backend/tests/test_compare.py`
- `frontend/src/pages/Finder/FinderPage.tsx`
- `frontend/src/pages/Finder/ModeSelector.tsx`
- `frontend/src/pages/Compare/ComparePage.tsx`
- `frontend/src/components/finder/FilterBar.tsx`
- `frontend/src/components/finder/FilterEditor.tsx`
- `frontend/src/components/finder/SavedViews.tsx`
- `frontend/src/api/finder.ts`
- `frontend/src/api/compare.ts`
- `frontend/src/lib/filterDefs.ts`

**Job:** Rebuild the Finder on the existing generic endpoints with five modes (player seasons, player games, plays, games, team seasons), extending filter_config with the new dataset modes and their 1999–2025 windows. Preserve the chip-based filter pattern, which is the best thing in the current app. The page opens with one empty condition and a mode selector and nothing else; ranking, qualification and column controls appear only after the first result set. All state lives in readable query parameters, one per concept — no base64. Saved views are localStorage and say so. Build Compare with percentile bars as the default view and a table toggle, maximum six entities enforced server-side, using the same cohort logic as the player percentile endpoint. Ship the one-release compatibility shim that translates old ?state= links to the new parameters.


**Acceptance:**

- Every Finder state is reproducible from the URL alone in a fresh browser, and an unrecognized parameter is ignored with the rest of the view intact
- A plays-mode query touching a pre-2020 season shows an honest loading state and completes, or explains the limit — it never fails silently
- On first load the Finder shows exactly one condition row, a mode selector, and a Run button; no ranking or column controls are visible
- Compare renders identical percentile values to the player hub for the same player, season and metric
- An old base64 ?state= link redirects to an equivalent Finder view, or to Home with no error dialog if it cannot be decoded
- Saved views are labeled as stored in this browser only

### P12 — Glossary, Data & Methods, and the honesty sweep

**Depends on:** P2, P3, P6, P7, P8, P9, P10, P11


**Owns:**

- `backend/app/glossary.py`
- `backend/app/routers/glossary.py`
- `backend/tests/test_glossary.py`
- `frontend/src/pages/Glossary/GlossaryPage.tsx`
- `frontend/src/pages/AboutData/AboutDataPage.tsx`
- `frontend/src/pages/AboutData/content.tsx`
- `frontend/src/components/legacy/README.md`

**Job:** Extend the glossary to cover every column the new pages display, each with a plain-language definition, its formula where one exists, its source dataset and its coverage window read from the registry rather than duplicated. Build /glossary with anchors and /about/data as the coverage-and-methodology document: the live dataset table from /api/coverage, the explicit list of what we do not have and why, and the full formula for every metric we compute ourselves. Then run the honesty sweep across the whole frontend: delete the old PlayersExplorer, PlaysExplorer, PlayerDetail, HomeView, QuickStats and DataQualityIndicator once their replacements have landed; confirm no hardcoded coverage year, no dead control, no placeholder number and no 'coming soon' string survives anywhere.


**Acceptance:**

- Every abbreviated column header in the product opens a popover that resolves to a real glossary term; a scripted crawl of all column ids reports zero misses
- /about/data renders live refresh timestamps from the API, and a grep for hardcoded coverage years in the frontend returns nothing
- Every metric marked with ComputedByUs has a matching formula section with a working anchor
- The six superseded components are deleted and nothing imports them
- A full-site crawl finds zero dead buttons, zero empty tables without an explanatory empty state, and zero occurrences of 'coming soon', 'TBD' or 'Live'

### Dependency corrections

`P7` and `P9` both consume `derived_wp_series` and `derived_game_team_stats`, which
`P4` owns. Both depend on **P1, P2, P4, P5**.
