import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import FeatureFlags from '@/pages/FeatureFlags'
import { useFlag } from '@/hooks/useFlag'

const CLE = 'flag.test_bascule'
const row = (valeur = 'false') => ({
  id: 1,
  cle: CLE,
  libelle: 'Flag de test',
  description: 'Interrupteur de démonstration.',
  categorie: 'flags',
  type: 'bool',
  valeur,
  valeur_defaut: 'false',
  modifiable: true,
  actif: true,
  can_edit: true,
  can_view: true,
})

function Sonde() {
  const on = useFlag(CLE)
  return <p data-testid="sonde">{on ? 'FLAG ON' : 'FLAG OFF'}</p>
}

function mount(me) {
  const user = me ?? makeUser('ADMIN')
  apiController.setMe(user)
  render(
    <>
      <FeatureFlags />
      <Sonde />
    </>,
    {
      wrapper: ({ children }) => (
        <AllProviders authUser={user} routePattern="/parametres/flags" initialEntries={['/parametres/flags']}>
          {children}
        </AllProviders>
      ),
    },
  )
}

describe('pages/FeatureFlags.jsx — P00-08', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche les flags livrés désactivés (sélecteur sur Désactivé)', async () => {
    apiController.setRoute(/^\/parametres\/$/, [row()])
    apiController.setRoute('/parametres/flags/', { flags: { [CLE]: false } })
    mount()

    expect(await screen.findByText('Flag de test')).toBeInTheDocument()
    expect(screen.getByText(/0\/1 activé/)).toBeInTheDocument()
    expect(screen.getByLabelText(`État du flag ${CLE}`)).toHaveValue('false')
    expect(screen.getByTestId('sonde')).toHaveTextContent('FLAG OFF')
    // Pas de modification en cours : le bouton Enregistrer est désactivé.
    expect(screen.getByRole('button', { name: 'Enregistrer' })).toBeDisabled()
  })

  it('bascule un flag : PATCH historisable, effet immédiat sur useFlag', async () => {
    let on = false
    apiController.setRoute(/^\/parametres\/$/, () => [row(on ? 'true' : 'false')])
    apiController.setRoute('/parametres/flags/', () => ({ flags: { [CLE]: on } }))
    // Le PATCH bascule l'état (et sert aussi de réponse au rechargement).
    apiController.setRoute(/\/parametres\/1\/$/, (path, body) => {
      if (body && body.valeur === 'true') on = true
      return row(on ? 'true' : 'false')
    })
    mount()

    await screen.findByText('Flag de test')
    fireEvent.change(screen.getByLabelText(`État du flag ${CLE}`), { target: { value: 'true' } })
    fireEvent.change(screen.getByLabelText(`Motif pour ${CLE}`), { target: { value: 'activation de démo' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    // Le PATCH porte la nouvelle valeur et le motif (historique).
    await waitFor(() => {
      const call = apiMock.patch.mock.calls.find(([p]) => /\/parametres\/1\/$/.test(p))
      expect(call?.[1]).toMatchObject({ valeur: 'true', motif_modification: 'activation de démo' })
    })
    // Effet immédiat : la carte flags est invalidée et reflète l'activation.
    expect(await screen.findByTestId('sonde')).toHaveTextContent('FLAG ON')
    expect(screen.getByText(/1\/1 activé/)).toBeInTheDocument()
  })

  it('affiche l’historique des bascules à la demande', async () => {
    apiController.setRoute(/^\/parametres\/$/, [row('true')])
    apiController.setRoute('/parametres/flags/', { flags: { [CLE]: true } })
    apiController.setRoute('/parametres/1/historique/', [
      {
        id: 9,
        ancienne_valeur: 'false',
        nouvelle_valeur: 'true',
        modifie_par_username: 'admin',
        modifie_le: '2026-09-13T10:00:00Z',
        motif_modification: 'mise en service',
      },
    ])
    mount()

    await screen.findByText('Flag de test')
    fireEvent.click(screen.getByRole('button', { name: 'Historique' }))
    expect(await screen.findByText(/mise en service/)).toBeInTheDocument()
    expect(screen.getByText(/par admin/)).toBeInTheDocument()
  })

  it('liste vide (utilisateur non habilité côté API) : état vide, sans planter', async () => {
    apiController.setRoute(/^\/parametres\/$/, [])
    apiController.setRoute('/parametres/flags/', { flags: {} })
    mount(makeUser('SECRETARIAT'))
    expect(await screen.findByText('Aucun feature flag.')).toBeInTheDocument()
  })
})
