# Putting Gridiron on the App Store

Everything that can be done without a Mac is done and committed. But read the
next section before spending time on this one — Gridiron is the riskiest of the
four apps, and one thing has to change before it is worth submitting.

---

## The thing that decides whether this can ship

**The API sleeps, and takes 43 seconds to wake up.** I measured it against the
live service today: 43.6 seconds on the first request, 0.7 seconds on the next.

That is Render's free plan doing what free plans do — it spins the service down
after 15 minutes with no traffic. On the website it reads as a slow first load.
In an app it is close to fatal:

- An App Review reviewer opens the app on a fresh install, with nothing cached,
  and watches a loading screen for the better part of a minute. Apps that appear
  to hang get rejected as incomplete, and the reviewer has no reason to think
  it's a sleeping server rather than a broken app.
- A real visitor who opens it once a week hits the 43 seconds every single time.

**My recommendation: move `gridiron-api` to Render's Starter plan, $7/month,
before submitting.** The service never sleeps and every request is the 0.7
seconds. This is already an open decision in Profusia ("Decide whether to pay
$7/mo to remove the one-minute cold start") — for the website it was a judgement
call, but for the App Store it's the difference between plausible and probably
rejected.

I can make the change on Render as soon as you say go. It's one setting.

**What I did to soften it in the meantime:** the app now keeps every answer it
receives on the device, so it opens instantly with the last-known figures and
then refreshes in the background. If a wait does run long, it says *"The server
sleeps when nobody is using it, and takes about a minute to wake"* rather than
showing an anonymous spinner. That helps a returning visitor a lot. It does
nothing for a reviewer's first launch, because their cache is empty.

---

## The other risk, stated plainly

Apple's Guideline 4.2 rejects apps that are "a repackaged website". A reference
site is the closest thing there is to that description, so Gridiron has the
weakest case of the four apps regardless of the cold start.

What's on its side: it works offline from the cache, it holds its own data on
the device, it has no browser chrome, and it's a genuinely deep reference tool
rather than a few pages. That is a real argument, but it is an argument — not a
certainty. If Apple pushes back, the strongest answers are a Home Screen widget
(a team's next game, a player's last line) and Spotlight search integration,
both of which are things a website cannot do at all. Say the word and I'll build
them.

**Of the four apps, this is the one I'd submit last** — after the other three
have been through review once and you know how the process goes.

---

## What you need first

- [ ] A Mac
- [ ] **Xcode** — free, Mac App Store, ~8 GB
- [ ] Your **Apple Developer Program** membership, active
- [ ] **Node.js 22+**

The permanent identifier is `com.cashflowarchitect.gridiron`, derived from your
GitHub account. It can never change once submitted; say so now if you want a
different one.

---

## Steps on the Mac

```bash
git clone https://github.com/the-cashflow-architect/nflfastr-explorer.git
cd nflfastr-explorer/frontend
npm install
npm run ios
npm run ios:open
```

Then in Xcode: blue **App** icon → **App** target → **Signing & Capabilities** →
tick **Automatically manage signing**, set **Team**. Pick a device and press ▶.

To submit: **Product → Archive** (device dropdown on "Any iOS Device") →
**Distribute App → App Store Connect**.

There is no database to build and nothing to download — the app talks to
`https://gridiron-api-mhw9.onrender.com`, the same API the website uses.

---

## What App Store Connect will ask

**Privacy** — **"No, we do not collect data from this app."** True: no accounts,
no identifiers, no analytics. It asks for public football statistics and shows
them.

**Age rating** — **4+**.

**Export compliance** — already declared.

**Screenshots** — 6.7" iPhone. A player page, a leaderboard and the standings
show what it is.

---

## Verifying it locally

All three of the project's gates pass:

```
cd backend && python -m pytest -q                          # 395 passed
cd frontend && npx tsc -b && npx oxlint --deny-warnings && npm run build
cd frontend && npm run review                              # every route, real browser
```

The third one needs an API with data behind it, which used to mean a four-minute
build and 200 MB of downloads. There is now a shortcut:

```bash
cd backend
python -m scripts.build_fixture_db /tmp/fixture.duckdb     # ~30s, no network
DUCKDB_PATH=/tmp/fixture.duckdb DUCKDB_MEMORY_LIMIT=1GB \
  CORS_ORIGINS=http://127.0.0.1:5173 uvicorn app.main:app --port 8000
```

It builds the same database the test suite builds — the real loader, the real
derived tables, over locally generated nflverse-shaped files covering 2001 and
2024. The numbers are generated, not real, so it is for checking that pages
render, never for looking at figures.

---

## What I could not verify

The app builds, typechecks, lints, passes all 395 backend tests, renders every
route in a real browser, and — checked directly — shows a full page of cached
figures with the API unreachable, under an honest banner saying when they were
saved.

**I could not compile the actual iOS app**, which needs Xcode on macOS.

---

## What changed in the app itself

- **It opens instantly instead of waiting on the server.** Every answer is kept
  on the device, so the last-known figures are on screen immediately and the
  fresh ones replace them when they arrive.
- **It works with no signal**, showing what it last fetched — under a bar that
  says there is no connection and when those figures were saved. It never lets
  an old number pass for a current one.
- **A long wait explains itself** instead of showing a silent spinner.
- **It no longer fetches fonts from Google**, so it renders correctly offline.

---

## One note on how this was delivered

Your working agreement for this repo says to push straight to `main`. This
session was started with an instruction to develop on `claude/eager-volta-uozifl`
and not to push anywhere else, so that is where the work is. Merging it to
`main` deploys it, and nothing here changes the website's behaviour except the
four improvements above — which are good for the website too.
