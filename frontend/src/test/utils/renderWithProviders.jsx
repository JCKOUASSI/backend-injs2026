import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { AuthProvider } from '@/context/AuthContext'
import CapabilitiesSync from '@/components/auth/CapabilitiesSync'
import { ToastProvider } from '@/context/ToastContext'

/**
 * Rend une UI avec toute la chaîne de providers réels :
 * QueryClientProvider + AuthProvider + ToastProvider + MemoryRouter.
 *
 * L'authentification est pilotée par le mock de services/api :
 *   - passer `authUser` pose un jeton en localStorage ; le mock /auth/me
 *     (apiController.setMe) doit alors renvoyer cet utilisateur ;
 *   - sans `authUser`, aucun jeton n'est posé (visiteur).
 *
 * `routePattern` + `initialEntries` permettent d'alimenter useParams().
 */
export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
}

export function AllProviders({ children, queryClient, authUser, initialEntries = ['/'], routePattern = '*' }) {
  const qc = queryClient || createTestQueryClient()
  if (authUser) {
    window.localStorage.setItem('access_token', 'test-access-token')
  }
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={initialEntries}>
        <AuthProvider>
          <CapabilitiesSync />
          <ToastProvider>
            <Routes>
              <Route path={routePattern} element={children} />
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

export function renderWithProviders(ui, options = {}) {
  const queryClient = options.queryClient || createTestQueryClient()
  const utils = render(ui, {
    wrapper: ({ children }) => (
      <AllProviders
        queryClient={queryClient}
        authUser={options.authUser}
        initialEntries={options.initialEntries}
        routePattern={options.routePattern}
      >
        {children}
      </AllProviders>
    ),
  })
  return { ...utils, queryClient }
}
