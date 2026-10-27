import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Routes, Route } from 'react-router-dom'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AuthProvider } from '@/context/AuthContext'
import CapabilitiesSync from '@/components/auth/CapabilitiesSync'
import { ToastProvider } from '@/context/ToastContext'
import { makeUser } from '@/test/utils/factories'
import HabilitationsLayout from './HabilitationsLayout'
import NavigationUtilisateursAcces from './NavigationUtilisateursAcces'
import { CAPABILITIES_QUERY_KEY, FLAGS_QUERY_KEY } from '@/lib/queryClient'

function monter(capacites) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(FLAGS_QUERY_KEY, { 'flag.curp_ui_admin': true })
  qc.setQueryData(CAPABILITIES_QUERY_KEY, {
    role: 'ADMIN', roles: ['ADMIN'], niveau: 'N4', capacites,
  })
  window.localStorage.setItem('access_token', 'jeton-test')
  apiController.setMe(makeUser('ADMIN'))
  apiController.setRoute('/auth/capabilities/', { capacites })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/administration/comptes']}>
        <AuthProvider>
          <CapabilitiesSync />
          <ToastProvider>
            <Routes>
              <Route path="/administration/comptes" element={<HabilitationsLayout />}>
                <Route index element={<div data-testid="enfant-liste">liste</div>} />
              </Route>
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('HabilitationsLayout — dérivation des capacités (C2 §3)', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche un message d\'accès refusé explicite sans la capacité habilitations_admin.gerer', async () => {
    monter({}) // capacités chargées mais sans la clé
    expect(await screen.findByTestId('hab-403')).toBeInTheDocument()
    expect(screen.queryByTestId('enfant-liste')).not.toBeInTheDocument()
    expect(screen.getByText(/CURP_UI_ADMIN/)).toBeInTheDocument()
  })

  it('affiche la console et le bandeau de traçabilité avec la capacité', async () => {
    monter({ habilitations_admin: ['gerer'] })
    expect(await screen.findByTestId('enfant-liste')).toBeInTheDocument()
    expect(screen.getByText(/Toute action sur les habilitations est tracée/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Journal/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Profils/ })).toBeInTheDocument()
  })

  it('ne montre pas les liens console lorsque le drapeau est fermé', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    qc.setQueryData(FLAGS_QUERY_KEY, { 'flag.curp_ui_admin': false })
    qc.setQueryData(CAPABILITIES_QUERY_KEY, {
      role: 'ADMIN', roles: ['ADMIN'], niveau: 'N4',
      capacites: { habilitations_admin: ['gerer'] },
    })
    window.localStorage.setItem('access_token', 'jeton-test')
    apiController.setMe(makeUser('ADMIN'))
    apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/users']}>
          <AuthProvider>
            <CapabilitiesSync />
            <Routes><Route path="/users" element={<NavigationUtilisateursAcces />} /></Routes>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByRole('link', { name: /Profils/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Comptes/ })).not.toBeInTheDocument()
  })
})
