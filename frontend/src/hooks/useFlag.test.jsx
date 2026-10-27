import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async () => {
  const mod = await import('@/test/utils/mockApi')
  return { ...mod.apiModuleMock }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders, createTestQueryClient } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import { useAuth } from '@/context/AuthContext'
import { useFlag } from './useFlag'
import { FLAGS_QUERY_KEY } from '@/lib/queryClient'

function Sonde({ cle }) {
  const actif = useFlag(cle)
  return <p>{cle}={actif ? 'ON' : 'OFF'}</p>
}
function Deconnexion() {
  const { logout } = useAuth()
  return <button onClick={() => logout()}>Se déconnecter</button>
}

function renderFlags(role, flagsMap, { withLogout = false } = {}) {
  const queryClient = createTestQueryClient()
  const me = makeUser(role)
  apiController.setMe(me)
  apiController.setRoute('/parametres/flags/', { flags: flagsMap })
  render(
    <>
      <Sonde cle="flag.test_un" />
      <Sonde cle="flag.test_deux" />
      {withLogout && <Deconnexion />}
    </>,
    {
      wrapper: ({ children }) => (
        <AllProviders queryClient={queryClient} authUser={me} routePattern="*">
          {children}
        </AllProviders>
      ),
    },
  )
  return { queryClient }
}

describe('useFlag — feature flags backend (P00-08)', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('aucun appel endpoint pour un visiteur', async () => {
    render(<Sonde cle="flag.test_un" />, {
      wrapper: ({ children }) => <AllProviders routePattern="*">{children}</AllProviders>,
    })
    await new Promise((r) => setTimeout(r, 50))
    expect(apiController.findCall('get', '/parametres/flags/')).toBeUndefined()
  })

  it('reflète la carte serveur (true/false)', async () => {
    renderFlags('ADMIN', { 'flag.test_un': true, 'flag.test_deux': false })
    expect(await screen.findByText('flag.test_un=ON')).toBeInTheDocument()
    expect(screen.getByText('flag.test_deux=OFF')).toBeInTheDocument()
  })

  it('une clé absente ou un corps inattendu équivaut à éteint', async () => {
    const queryClient = createTestQueryClient()
    const me = makeUser('ADMIN')
    apiController.setMe(me)
    apiController.setRoute('/parametres/flags/', []) // tableau = corps invalide
    render(<Sonde cle="flag.test_un" />, {
      wrapper: ({ children }) => (
        <AllProviders queryClient={queryClient} authUser={me} routePattern="*">{children}</AllProviders>
      ),
    })
    expect(await screen.findByText('flag.test_un=OFF')).toBeInTheDocument()
  })

  it('échec de l’endpoint : tous les flags restent éteints (sécurité par défaut)', async () => {
    const me = makeUser('ADMIN')
    apiController.setMe(me)
    apiController.setRoute('/parametres/flags/', async () => {
      throw { response: { status: 500 } }
    })
    render(<Sonde cle="flag.test_un" />, {
      wrapper: ({ children }) => (
        <AllProviders authUser={me} routePattern="*">{children}</AllProviders>
      ),
    })
    expect(await screen.findByText('flag.test_un=OFF')).toBeInTheDocument()
  })

  it('déconnexion : les flags sont purgés du cache', async () => {
    const { queryClient } = renderFlags('ADMIN', { 'flag.test_un': true }, { withLogout: true })
    await screen.findByText('flag.test_un=ON')
    expect(queryClient.getQueryData(FLAGS_QUERY_KEY)).not.toBeUndefined()
    fireEvent.click(screen.getByRole('button', { name: 'Se déconnecter' }))
    await waitFor(() => expect(queryClient.getQueryData(FLAGS_QUERY_KEY)).toBeUndefined())
  })
})
