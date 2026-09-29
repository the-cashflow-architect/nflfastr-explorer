import { QueryClient } from '@tanstack/react-query'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'
import { removeOldestQuery } from '@tanstack/react-query-persist-client'
import { RouterProvider } from 'react-router-dom'
import { BreadcrumbProvider } from './components/shell/Breadcrumb'
import { FreshnessBanner } from './components/shell/FreshnessBanner'
import { CACHE_BUSTER, CACHE_KEY, CACHE_MAX_AGE, shouldPersist } from './lib/offline'
import { router } from './routes'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      // Coming back to the tab, or to the app from the background, re-asks for
      // anything past its staleTime (an hour for reference pages), so a focus
      // costs nothing until then. It was off, and iOS keeps a backgrounded app
      // alive for days: reopened, it showed the same figures as current with
      // no refresh and no notice. React Query's focus listener is the page's
      // visibilitychange, which a web view fires on returning to the front.
      refetchOnWindowFocus: true,
      retry: 1,
      // An entry has to outlive the session for it to be worth writing to disk.
      // Queries built in api/endpoints.ts set their own, matching value.
      gcTime: CACHE_MAX_AGE,
    },
  },
})

/**
 * Answers are kept on disk so the app opens with something on screen.
 *
 * The API sleeps between visits and takes about a minute to wake. Without this
 * the app's first screen is a spinner for that whole minute, every time — which
 * is how an app gets judged broken, by a reviewer as much as by a visitor.
 *
 * localStorage, not the durable store: this is a cache. If iOS clears it the
 * app asks the server again and nothing anyone made is lost.
 */
const persister = createSyncStoragePersister({
  storage: typeof window === 'undefined' ? undefined : window.localStorage,
  key: CACHE_KEY,
  // A few megabytes is all a web view allows. When a write would overflow it,
  // drop the least recently used page and try again, rather than silently
  // leaving yesterday's snapshot on disk forever.
  retry: removeOldestQuery,
})

export default function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: CACHE_MAX_AGE,
        // Saved figures from another API contract are dropped, not rendered.
        buster: CACHE_BUSTER,
        // Reference pages with data, even when their last refresh failed — see shouldPersist.
        dehydrateOptions: { shouldDehydrateQuery: shouldPersist },
      }}
    >
      <BreadcrumbProvider>
        <FreshnessBanner />
        <RouterProvider router={router} />
      </BreadcrumbProvider>
    </PersistQueryClientProvider>
  )
}
