import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'

vi.mock('@/services/api', async () => {
  const mod = await import('@/test/utils/mockApi')
  return { ...mod.apiModuleMock }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders, createTestQueryClient } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import { useAuth } from '@/context/AuthContext'
import { CAPABILITIES_QUERY_KEY } from '@/lib/queryClient'
import { useDroits } from './useDroits'

function caps(role, capacites, extras = {}) {
  return {
    version: 1,
    role,
    roles: [role],
    niveau: 'N2',
    niveau_provisoire: true,
    capacites,
    perimetres: { niveaux: [], secretariats: [], formations: [], groupes: [] },
    role_context: {},
    ...extras,
  }
}

function BoutonDroit({ module: mod, action, label }) {
  const droits = useDroits()
  if (!droits.peut(mod, action)) return null
  return <button>{label ?? `${mod}.${action}`}</button>
}

function Deconnexion() {
  const { logout } = useAuth()
  return <button onClick={() => logout()}>Se déconnecter</button>
}

function renderDroits(role, capacites, options = {}) {
  const queryClient = options.queryClient ?? createTestQueryClient()
  apiController.setMe(makeUser(role))
  apiController.setRoute('/auth/capabilities/', capacites)
  const ui = (
    <>
      <BoutonDroit module={options.module ?? 'notes'} action={options.action ?? 'valider_decisions'} />
      {options.withLogout && <Deconnexion />}
    </>
  )
  const utils = render(ui, {
    wrapper: ({ children }) => (
      <AllProviders queryClient={queryClient} authUser={makeUser(role)} routePattern="*">
        {children}
      </AllProviders>
    ),
  })
  return { ...utils, queryClient }
}

describe('useDroits — capacités dérivées du backend (P00-06)', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('n’appelle pas l’endpoint pour un visiteur non authentifié', async () => {
    render(<BoutonDroit module="finance" action="voir" />, {
      wrapper: ({ children }) => <AllProviders routePattern="*">{children}</AllProviders>,
    })
    await new Promise((r) => setTimeout(r, 50))
    expect(apiController.findCall('get', '/auth/capabilities/')).toBeUndefined()
  })

  it('après chargement, une action accordée par le backend s’affiche même si le repli statique la masquait', async () => {
    // SECRETARIAT : le repli statique DECISION_ROLES refuse valider_decisions,
    // mais la permission de groupe backend l’accorde.
    renderDroits(
      'SECRETARIAT',
      caps('SECRETARIAT', { notes: ['gerer', 'valider_decisions'] }),
    )
    expect(screen.queryByRole('button', { name: 'notes.valider_decisions' })).not.toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'notes.valider_decisions' })).toBeInTheDocument()
  })

  it('une action absente des capacités reçues ne s’affiche jamais (le backend fait loi)', async () => {
    // SECRETARIAT : « creer participant » est refusé en statique ET absent du
    // contrat backend ; le bouton ne doit apparaître à aucun moment.
    renderDroits('SECRETARIAT', caps('SECRETARIAT', { participants: ['gerer', 'lister'] }), {
      module: 'participants',
      action: 'creer',
    })
    await new Promise((r) => setTimeout(r, 80))
    expect(screen.queryByRole('button', { name: 'participants.creer' })).not.toBeInTheDocument()
  })

  it('FINANCE voit le module finance mais jamais la liste des participants', async () => {
    const capacites = caps('FINANCE', {
      web: ['acceder'],
      finance: ['voir', 'exporter', 'parametrer'],
      participants: [],
    })
    const queryClient = createTestQueryClient()
    apiController.setMe(makeUser('FINANCE'))
    apiController.setRoute('/auth/capabilities/', capacites)
    render(
      <>
        <BoutonDroit module="finance" action="voir" label="Voir finance" />
        <BoutonDroit module="participants" action="lister" label="Liste participants" />
      </>,
      {
        wrapper: ({ children }) => (
          <AllProviders queryClient={queryClient} authUser={makeUser('FINANCE')} routePattern="*">
            {children}
          </AllProviders>
        ),
      },
    )
    expect(await screen.findByRole('button', { name: 'Voir finance' })).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 50))
    expect(screen.queryByRole('button', { name: 'Liste participants' })).not.toBeInTheDocument()
  })

  it('DIRECTION voit les comptes : vrai en repli statique comme côté backend', async () => {
    // DIRECTION / utilisateurs.voir : vrai en statique, le bouton doit être
    // présent (au plus tard après le chargement, les deux sources concordent).
    renderDroits('DIRECTION', caps('DIRECTION', { utilisateurs: ['voir'] }), {
      module: 'utilisateurs',
      action: 'voir',
    })
    expect(await screen.findByRole('button', { name: 'utilisateurs.voir' })).toBeInTheDocument()
  })

  it('échec de l’endpoint : le repli statique s’applique (SECRETARIAT garde ses boutons)', async () => {
    apiController.setMe(makeUser('SECRETARIAT'))
    // Seul l'endpoint de capacités échoue (pas /auth/me, qui doit réussir).
    apiController.setRoute('/auth/capabilities/', async () => {
      throw { response: { status: 500 } }
    })
    render(
      <BoutonDroit module="utilisateurs" action="gerer" label="Gérer les comptes" />,
      {
        wrapper: ({ children }) => (
          <AllProviders authUser={makeUser('SECRETARIAT')} routePattern="*">
            {children}
          </AllProviders>
        ),
      },
    )
    // Le repli statique SECRETARIAT/USER_MUTATION autorise déjà l'action.
    expect(await screen.findByRole('button', { name: 'Gérer les comptes' })).toBeInTheDocument()
  })

  it('déconnexion : les capacités sont purgées du cache React Query', async () => {
    const { queryClient } = renderDroits(
      'SECRETARIAT',
      caps('SECRETARIAT', { notes: ['gerer', 'valider_decisions'] }),
      { withLogout: true },
    )
    await screen.findByRole('button', { name: 'notes.valider_decisions' })
    expect(queryClient.getQueriesData({ queryKey: CAPABILITIES_QUERY_KEY }).length).toBeGreaterThan(0)

    // Les capacités sont bien en cache avant la déconnexion…
    expect(queryClient.getQueryData(CAPABILITIES_QUERY_KEY)).not.toBeUndefined()

    fireEvent.click(screen.getByRole('button', { name: 'Se déconnecter' }))

    // …et aucune capacité ne subsiste après (l'entrée éventuellement recréée
    // par un observateur encore monté ne contient aucune donnée).
    await waitFor(() =>
      expect(queryClient.getQueryData(CAPABILITIES_QUERY_KEY)).toBeUndefined(),
    )
  })

  it('expose le niveau et les périmètres issus du backend', async () => {
    function Resume() {
      const { niveau, perimetres, charge } = useDroits()
      if (!charge) return <p>Chargement…</p>
      return <p>{niveau} / {(perimetres?.niveaux || []).join(',')}</p>
    }
    apiController.setMe(makeUser('SECRETARIAT'))
    apiController.setRoute(
      '/auth/capabilities/',
      caps('SECRETARIAT', {}, { niveau: 'N2', perimetres: { niveaux: ['SERVICE'] } }),
    )
    render(<Resume />, {
      wrapper: ({ children }) => (
        <AllProviders authUser={makeUser('SECRETARIAT')} routePattern="*">
          {children}
        </AllProviders>
      ),
    })
    expect(await screen.findByText('N2 / SERVICE')).toBeInTheDocument()
  })
})
