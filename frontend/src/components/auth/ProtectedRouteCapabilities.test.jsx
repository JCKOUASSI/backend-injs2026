/**
 * P00-06 — ProtectedRoute dérive des capacités backend quand elles sont
 * chargées (prop `capacite`), avec repli strictement identique sur
 * `allowedRoles` tant que le contrat /auth/capabilities/ n'est pas arrivé.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
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
import { createTestQueryClient } from '@/test/utils/renderWithProviders'
import { QueryClientProvider } from '@tanstack/react-query'
import { makeUser } from '@/test/utils/factories'
import ProtectedRoute from '@/components/auth/ProtectedRoute'
import { PARTICIPANT_LIST_ROLES } from '@/utils/roles'

const capsPayload = (role, capacites) => ({
  version: 1,
  role,
  roles: [role],
  niveau: 'N2',
  niveau_provisoire: true,
  capacites: { participants: [], ...capacites },
  perimetres: { niveaux: [], secretariats: [], formations: [], groupes: [] },
  role_context: {},
})

function renderApp(role, caps) {
  const qc = createTestQueryClient()
  const me = makeUser(role)
  apiController.setMe(me)
  window.localStorage.setItem('access_token', 'test-access-token')
  if (caps !== undefined) {
    apiController.setRoute('/auth/capabilities/', capsPayload(role, caps))
  }
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/participants']}>
        <AuthProvider>
          <CapabilitiesSync />
          <ToastProvider>
            <Routes>
              <Route path="/login" element={<div>PAGE LOGIN</div>} />
              <Route path="/participants" element={
                <ProtectedRoute
                  allowedRoles={PARTICIPANT_LIST_ROLES}
                  capacite={{ module: 'participants', action: 'lister' }}
                >
                  <div>PAGE PARTICIPANTS</div>
                </ProtectedRoute>
              } />
              <Route path="/" element={<ProtectedRoute><div>PAGE ACCUEIL</div></ProtectedRoute>} />
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('ProtectedRoute — P00-06 (capacités backend)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('FINANCE sans capacité « participants.lister » est reconduit à l’accueil', async () => {
    renderApp('FINANCE', { participants: [] })
    expect(await screen.findByText('PAGE ACCUEIL')).toBeInTheDocument()
    expect(screen.queryByText('PAGE PARTICIPANTS')).not.toBeInTheDocument()
  })

  it('SECRETARIAT avec « participants.lister » accordé atteint la page', async () => {
    renderApp('SECRETARIAT', { participants: ['lister'] })
    expect(await screen.findByText('PAGE PARTICIPANTS')).toBeInTheDocument()
  })

  it('le backend fait autorité même en contradiction avec le rôle statique (ADMIN sans capacité → reconduit)', async () => {
    renderApp('ADMIN', { participants: [] })
    expect(await screen.findByText('PAGE ACCUEIL')).toBeInTheDocument()
    expect(screen.queryByText('PAGE PARTICIPANTS')).not.toBeInTheDocument()
  })

  it('capacités non chargées : repli sur allowedRoles (SECRETARIAT statique autorisé)', async () => {
    // Aucune route /auth/capabilities/ définie : le mock renvoie une forme
    // invalide → le hook renvoie null → comportement historique par rôles.
    renderApp('SECRETARIAT')
    expect(await screen.findByText('PAGE PARTICIPANTS')).toBeInTheDocument()
  })
})
