import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App.jsx'

const createClient = () => new QueryClient({
  defaultOptions: {
    queries: { retry: false, gcTime: 0 },
    mutations: { retry: false },
  },
})

describe('App — montage du shell de production', () => {
  it('monte les providers globaux et affiche la connexion sans session', async () => {
    const queryClient = createClient()
    render(
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>,
    )

    expect(await screen.findByRole('heading', { name: 'Connexion' })).toBeInTheDocument()
    expect(screen.queryByText(/L’application n’a pas pu s’afficher/i)).not.toBeInTheDocument()
  })
})
