# Putting Gridiron on the App Store

Everything that can be done without a Mac is done, committed and on `main`. Gridiron is still the riskiest of the four
apps — read the first two sections before spending time on the rest.

---

## The sleeping server, and what was done instead of paying for it

The API is on Render's free plan, which spins it down after 15 minutes idle. Measured on
the live service: **43.6 seconds** for the first request, 0.7 seconds after that. You decided
on 28 September not to move it to the $7/month plan, so the app is built to cope:

- **It never opens on a blank wait.** `npm run ios` fetches the home page's figures from the
  live API and bundles them into the app. A fresh install — which is what an App Review
  reviewer has — opens straight onto the home page.
- **It never passes old figures off as current.** Anything shown from the device rather than
  from this session's request says so at the bottom of the screen, with the date it was
  saved: *"Showing figures saved … while the latest load"*, or *"Couldn't update. Showing
  figures saved …"* if the server doesn't answer.
- **Everything else still waits on the server** the first time it is opened. A reviewer who
  goes straight to a player page on a cold server waits up to a minute, under a message that
  says the server is waking. That is the remaining risk, and the $7 plan is still the only
  thing that removes it.

---

## The other risk, stated plainly

Guideline 4.2 rejects apps that are "a repackaged website", and a reference site is the
closest thing there is to that description. In Gridiron's favour: it works offline from what
it has saved, has no browser chrome, and is a deep tool rather than a few pages. That is an
argument, not a certainty. If Apple pushes back, the strongest answers are a Home Screen
widget (a team's next game, a player's last line) and Spotlight search — things a website
cannot do. **Submit this one last**, after the other three have been through review once.

---

## What you need first

- [ ] A Mac
- [ ] **Xcode 26 or later.** Check with **Xcode → About Xcode**; update from the Mac App Store
      if it is lower. The project is built on Capacitor 8, which needs Xcode 26.
- [ ] Your **Apple Developer Program** membership, active (team `DJYJ6Z3ZJH`)
- [ ] **Node.js 22+**

## Already decided — do not change

| | |
|---|---|
| Bundle identifier | `com.evadaroo.gridiron` — on your own domain. It becomes permanent the moment the first build is uploaded. |
| Team | `DJYJ6Z3ZJH`, already filled in. |

---

## Steps on the Mac

```bash
git clone https://github.com/the-cashflow-architect/nflfastr-explorer.git
cd nflfastr-explorer/frontend
npm install
npm run ios
npm run ios:open
```

`npm run ios` can take a couple of minutes the first time: it waits for the
server to wake so it can bundle the home page's figures. If it stops saying it could not
reach the API, run it again.

In Xcode: blue **App** icon → **App** target → **Signing & Capabilities** → confirm **Team**
shows your developer account. Pick an iPhone simulator and press ▶, then an **iPad Pro
13-inch** (the app runs on iPad, so Apple reviews it on one).

**The one check that matters most:** delete the app from the simulator, launch it fresh, and
open a **player page** — not just the home page, which comes from the bundled figures and
proves nothing about the connection. It should load (after up to a minute if the server was
asleep). If it says it could not reach the server, send me a screenshot.

To upload: device dropdown on **Any iOS Device** → **Product → Archive → Distribute App →
App Store Connect → Upload**.

---

## What App Store Connect will ask

**Privacy Policy URL and Support URL** — both required.

- Privacy Policy URL: `https://nflfastr-explorer.onrender.com/about/privacy`
- Support URL: `https://nflfastr-explorer.onrender.com/about/support`

**These do not load today, and neither does any other link on the site except the home
page** — the site is missing the rule that sends every address to the app. It is a one-time
setting: Render dashboard → **nflfastr-explorer** (the static site) → **Redirects/Rewrites** →
add Source `/*`, Destination `/index.html`, Action **Rewrite** → Save. Then open both URLs in
a browser. The same pages are inside the app (footer → Privacy, Support), which Apple also
requires.

**App Privacy → Data collection** — **"No, we do not collect data from this app."** True: no
accounts, no identifiers, no analytics. It asks for public football statistics and shows them.
The API's host keeps ordinary request logs; that is covered in the privacy page.

**Age rating** — **4+**.

**Export compliance** — already declared.

**Screenshots** — two sets, because the app runs on iPad: **6.9" iPhone** (e.g. iPhone 17 Pro
Max simulator) and **13" iPad** (iPad Pro 13-inch simulator), with **⌘S**. A player page, a
leaderboard and the standings show what it is.

---

## How the app differs from the website

- **Requests go through iOS, not the web view.** The live API only accepts requests from the
  website's own address, and the app is not the website. Rather than change the server, the
  app sends its requests through Capacitor's native networking, which the server sees as an
  ordinary request.
- **No export buttons.** "Export as CSV" and "Export JSON" cannot save a file inside an iPhone
  web view — the tap does nothing — so the app does not offer them. The website still does.
- **"Copy a link" copies the website address**, so the link opens for whoever receives it.
- **The launch screen comes down on the first frame**, with a four-second self-hide as a
  backstop. An earlier build never hid it at all.

---

## Verifying it locally

```
cd backend && python -m pytest -q                          # 395 passed
cd frontend && npx tsc -b && npx oxlint --deny-warnings && npm run build
cd frontend && npm run review                              # every route, real browser
cd frontend && npm run review:native                       # the iPhone-only paths
cd frontend && npm run review:seed                         # the bundled first-launch figures
```

`review:native` runs the built app against a stand-in for the iPhone's native layer and fails
if the launch screen is never dismissed, if an export button is offered, or if "copy a link"
copies an address nobody can open. It failed on all of those against the earlier code.

The browser reviews need an API with data behind it:

```bash
cd backend
python -m scripts.build_fixture_db /tmp/fixture.duckdb     # ~30s, no network
DUCKDB_PATH=/tmp/fixture.duckdb DUCKDB_MEMORY_LIMIT=1GB \
  CORS_ORIGINS=http://127.0.0.1:5173 uvicorn app.main:app --port 8000
```

That database is built by the real loader over locally generated files covering 2001 and 2024.
Its numbers are generated, not real — for checking that pages render, never for figures.

**Not checked: the actual iOS build**, which needs Xcode on macOS.
