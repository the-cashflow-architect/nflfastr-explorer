import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './components/shell/AppShell'
import { NotFoundPage } from './pages/NotFoundPage'
import { HomePage } from './pages/Home/HomePage'
import { PlayerIndexPage } from './pages/Players/PlayerIndexPage'
import { PlayerHubPage } from './pages/Players/PlayerHubPage'
import { PlayerGameLogPage } from './pages/Players/PlayerGameLogPage'
import { PlayerSplitsPage } from './pages/Players/PlayerSplitsPage'
import { PlayerAdvancedPage } from './pages/Players/PlayerAdvancedPage'
import { TeamIndexPage } from './pages/Teams/TeamIndexPage'
import { FranchisePage } from './pages/Teams/FranchisePage'
import { TeamSeasonPage } from './pages/Teams/TeamSeasonPage'
import { TeamRosterPage } from './pages/Teams/TeamRosterPage'
import { GamePage } from './pages/Games/GamePage'
import { SeasonIndexPage } from './pages/Seasons/SeasonIndexPage'
import { SeasonHubPage } from './pages/Seasons/SeasonHubPage'
import { StandingsPage } from './pages/Seasons/StandingsPage'
import { WeekPage } from './pages/Seasons/WeekPage'
import { LeadersHubPage } from './pages/Leaders/LeadersHubPage'
import { LeaderboardPage } from './pages/Leaders/LeaderboardPage'
import { DraftIndexPage } from './pages/Draft/DraftIndexPage'
import { DraftClassPage } from './pages/Draft/DraftClassPage'
import { FinderPage } from './pages/Finder/FinderPage'
import { ComparePage } from './pages/Compare/ComparePage'
import { GlossaryPage } from './pages/Glossary/GlossaryPage'
import { AboutDataPage } from './pages/AboutData/AboutDataPage'

/**
 * The route table. Real URLs, because every one of them is something a person
 * might send to someone else — which the old client-side-state model made
 * impossible.
 *
 * Two rules hold here:
 * - The path identifies the entity; query parameters carry view state, one
 *   readable parameter per concept. No opaque blobs.
 * - Every route in this table is reachable from `/` by following links, via the
 *   shell nav or the home tiles. A route nothing links to is a route nobody
 *   finds.
 */
export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    errorElement: <AppShell />,
    children: [
      { index: true, element: <HomePage /> },

      { path: 'players', element: <PlayerIndexPage /> },
      { path: 'players/:gsisId', element: <PlayerHubPage /> },
      { path: 'players/:gsisId/gamelog', element: <PlayerGameLogPage /> },
      { path: 'players/:gsisId/splits', element: <PlayerSplitsPage /> },
      { path: 'players/:gsisId/advanced', element: <PlayerAdvancedPage /> },
      // The slug is decoration for humans and search engines; the id is the key.
      // It comes last so it never shadows the sub-pages above.
      { path: 'players/:gsisId/:slug', element: <PlayerHubPage /> },

      { path: 'teams', element: <TeamIndexPage /> },
      { path: 'teams/:abbr', element: <FranchisePage /> },
      { path: 'teams/:abbr/:season', element: <TeamSeasonPage /> },
      { path: 'teams/:abbr/:season/roster', element: <TeamRosterPage /> },

      { path: 'games/:gameId', element: <GamePage /> },

      { path: 'seasons', element: <SeasonIndexPage /> },
      { path: 'seasons/:season', element: <SeasonHubPage /> },
      { path: 'seasons/:season/standings', element: <StandingsPage /> },
      { path: 'seasons/:season/week/:week', element: <WeekPage /> },

      { path: 'leaders', element: <LeadersHubPage /> },
      { path: 'leaders/:category/:stat', element: <LeaderboardPage /> },

      { path: 'draft', element: <DraftIndexPage /> },
      { path: 'draft/:year', element: <DraftClassPage /> },

      { path: 'finder', element: <FinderPage /> },
      { path: 'compare', element: <ComparePage /> },
      { path: 'glossary', element: <GlossaryPage /> },
      { path: 'about/data', element: <AboutDataPage /> },

      { path: '*', element: <NotFoundPage /> },
    ],
  },
])
