import { QueryClient } from '@tanstack/react-query'
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client'
import { createSyncStoragePersister } from '@tanstack/query-sync-storage-persister'
import { RouterProvider } from 'react-router-dom'
import { BreadcrumbProvider } from './components/shell/Breadcrumb'
import { OfflineBanner } from './components/shell/OfflineBanner'
import { CACHE_KEY, CACHE_MAX_AGE } from './lib/offline'
import { router } from './routes'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Football data changes weekly at most, and a reference page that refetches
      // on every window focus wastes the visitor's bandwidth to show them the
      // same number.
      staleTime: 5 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: 1,
      // An entry has to outlive the session for it to be worth writing to disk:
      // the default five minutes would evict it long before the app is opened
      // again, and the persisted copy would only ever be empty.
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
})

export default function App() {
  return (
    <PersistQueryClientProvider
      client={queryClient}
      persistOptions={{
        persister,
        maxAge: CACHE_MAX_AGE,
        // Never persist a failure. A cached error would greet the next launch
        // with a problem the server may have long since stopped having.
        dehydrateOptions: {
          shouldDehydrateQuery: (query) => query.state.status === 'success',
        },
      }}
    >
      <BreadcrumbProvider>
        <OfflineBanner />
        <RouterProvider router={router} />
      </BreadcrumbProvider>
    </PersistQueryClientProvider>
  )
}
