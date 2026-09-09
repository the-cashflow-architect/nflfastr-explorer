import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider } from 'react-router-dom'
import { BreadcrumbProvider } from './components/shell/Breadcrumb'
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
    },
  },
})

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BreadcrumbProvider>
        <RouterProvider router={router} />
      </BreadcrumbProvider>
    </QueryClientProvider>
  )
}
