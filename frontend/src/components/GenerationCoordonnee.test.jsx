import { screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import GenerationCoordonnee from '@/components/GenerationCoordonnee'

const user = userEvent.setup()

const ADMIN = makeUser('ADMIN', { username: 'admin' })

const annees = [
  { id: 3, libelle: '2025-2026' },
  { id: 2, libelle: '2024-2025' },
]

const successBilan = {
  status_global: 'COORDONNEE_OK',
  annee_academique_id: 3,
  nb_formations: 2,
  totaux: {
    seances_attendues: 12,
    seances_placees: 12,
    seances_non_placees: 0,
    nb_edt: 2,
    nb_edt_complets: 2,
    nb_edt_incomplets: 0,
    nb_edt_persistes: 0,
    taux_couverture: 100,
  },
  persistence_demandee: false,
  conflits: { statut: 'NON_APPLIQUE', conflits: [], detail: {} },
  edts: [],
}

const partialBilan = {
  status_global: 'COORDONNEE_PARTIELLE',
  annee_academique_id: 3,
  nb_formations: 2,
  totaux: {
    seances_attendues: 12,
    seances_placees: 7,
    seances_non_placees: 5,
    nb_edt: 2,
    nb_edt_complets: 1,
    nb_edt_incomplets: 1,
    nb_edt_persistes: 0,
    taux_couverture: 58,
  },
  persistence_demandee: false,
  conflits: { statut: 'NON_APPLIQUE', conflits: [], detail: {} },
  edts: [],
}

const conflitsBilan = {
  status_global: 'COORDONNEE_CONFLITS',
  annee_academique_id: 3,
  nb_formations: 2,
  totaux: {
    seances_attendues: 12,
    seances_placees: 6,
    seances_non_placees: 6,
    nb_edt: 2,
    nb_edt_complets: 1,
    nb_edt_incomplets: 1,
    nb_edt_persistes: 0,
    taux_couverture: 50,
  },
  persistence_demandee: false,
  conflits: { statut: 'CONFLITS', conflits: [{ id: 1, description: 'Chevauchement salle' }], detail: {} },
  edts: [],
}

const erreurBilan = {
  status_global: 'COORDONNEE_ERREUR',
  annee_academique_id: 3,
  nb_formations: 2,
  totaux: {
    seances_attendues: 12,
    seances_placees: 6,
    seances_non_placees: 6,
    nb_edt: 2,
    nb_edt_complets: 1,
    nb_edt_incomplets: 1,
    nb_edt_persistes: 1,
    nb_formations_en_erreur: 1,
    taux_couverture: 50,
  },
  motif_echec: 'ERREUR_GENERATION_FORMATION',
  persistence_demandee: false,
  conflits: { statut: 'NON_APPLIQUE', conflits: [], detail: {} },
  edts: [],
}

const apiError = (status, motif, explication) => ({
  response: { status, data: { motif_echec: motif, detail: { explication, action_recommandee: 'Verifiez votre connexion' } } },
})

const mount = (_statusGlobal = 'COORDONNEE_OK', overrideProps = {}) => {
  const props = {
    annees,
    anneeSelectionnee: '3',
    onAnneeChange: vi.fn(),
    onResultat: vi.fn(),
    refresh: vi.fn(),
    ...overrideProps,
  }
  return renderWithProviders(<GenerationCoordonnee {...props} />, {
    authUser: ADMIN,
    initialEntries: ['/edt'],
    routePattern: '/edt',
  })
}

describe('GenerationCoordonnee', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setMe(ADMIN)
  })

  it('affiche le bouton de génération désactivé quand aucune année n est choisie', () => {
    renderWithProviders(
      <GenerationCoordonnee annees={annees} anneeSelectionnee="" onAnneeChange={vi.fn()} refresh={vi.fn()} />,
      { authUser: ADMIN, initialEntries: ['/edt'], routePattern: '/edt' },
    )
    const bouton = screen.getByRole('button', { name: /générer/i })
    expect(bouton).toBeDisabled()
  })

  it('envoie la bonne année et persister quand la case est cochee', async () => {
    mount()
    const checkbox = screen.getByRole('checkbox')
    await user.click(checkbox)
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(apiMock.post).toHaveBeenCalledTimes(1)
    expect(apiMock.post.mock.calls[0][1]).toEqual({ annee_academique_id: 3, persister: true })
  })

  it('affiche le bilan de succes COORDONNEE_OK, rafraichit et appelle le callback', async () => {
    apiController.setRoute('/edts/lmd/generate-coordinated/', successBilan)
    mount()
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('bilan-statut')).toHaveTextContent('Génération coordonnée réussie')
    expect(screen.getByTestId('gc-bilan')).toBeInTheDocument()
    expect(screen.getByTestId('gc-refresh')).toBeInTheDocument()
    expect(apiMock.post).toHaveBeenCalledWith('/edts/lmd/generate-coordinated/', { annee_academique_id: 3 })
    expect(screen.getByText('Génération coordonnée complète (prévisualisation).')).toBeInTheDocument()
    expect(screen.getByText(/Aucune publication n’est effectuée/)).toBeInTheDocument()
  })

  it('affiche le panneau partiel COORDONNEE_PARTIELLE', async () => {
    apiController.setRoute('/edts/lmd/generate-coordinated/', partialBilan)
    mount('COORDONNEE_PARTIELLE')
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-partiel')).toBeInTheDocument()
    expect(screen.getByTestId('bilan-statut')).toHaveTextContent('Génération coordonnée incomplète')
  })

  it('affiche le panneau de conflits COORDONNEE_CONFLITS', async () => {
    apiController.setRoute('/edts/lmd/generate-coordinated/', conflitsBilan)
    mount('COORDONNEE_CONFLITS')
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-conflits')).toBeInTheDocument()
    expect(screen.getByText(/conflits inter-EDT détectés/i)).toBeInTheDocument()
  })

  it('affiche une erreur métier de génération coordonnée sans la présenter comme un succès', async () => {
    apiController.setRoute('/edts/lmd/generate-coordinated/', erreurBilan)
    mount('COORDONNEE_ERREUR')
    await user.click(screen.getByRole('button', { name: /générer/i }))
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('bilan-statut')).toHaveTextContent('Erreur de génération coordonnée')
    expect(screen.queryByText(/Génération coordonnée complète/i)).not.toBeInTheDocument()
  })

  it('affiche une erreur 403 classée AUTORISATION', async () => {
    vi.spyOn(apiMock, 'post').mockRejectedValueOnce(apiError(403, 'ACCÈS_REFUSÉ', 'Action non autorisée'))
    mount()
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-erreur')).toHaveTextContent('Action non autorisée')
  })

  it('affiche une erreur de requête invalide 400 classée VALIDATION', async () => {
    vi.spyOn(apiMock, 'post').mockRejectedValueOnce(apiError(400, 'ANNEE_ACADEMIQUE_REQUISE', 'L année académique est obligatoire.'))
    mount()
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-erreur')).toHaveTextContent('L année académique est obligatoire.')
  })

  it('affiche une erreur 404 classée INTROUVABLE', async () => {
    vi.spyOn(apiMock, 'post').mockRejectedValueOnce(apiError(404, 'ANNEE_ACADEMIQUE_INTROUVABLE', 'L année académique sélectionnée est introuvable.'))
    mount()
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-erreur')).toHaveTextContent('L année académique sélectionnée est introuvable.')
  })

  it('affiche une erreur 500 classée SERVEUR', async () => {
    vi.spyOn(apiMock, 'post').mockRejectedValueOnce(apiError(500, 'GENERATION_IMPOSSIBLE', 'La génération n a pas pu aboutir.'))
    mount()
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-erreur')).toHaveTextContent('La génération n a pas pu aboutir.')
  })

  it('affiche une erreur de réseau quand le serveur ne répond pas', async () => {
    vi.spyOn(apiMock, 'post').mockRejectedValueOnce({ response: undefined })
    mount()
    const bouton = screen.getByRole('button', { name: /générer/i })
    await user.click(bouton)
    await act(async () => { await flushPromises(2) })
    expect(screen.getByTestId('gc-erreur')).toHaveTextContent('Le serveur n’a pas répondu.')
  })

  it('appelle onAnneeChange quand l utilisateur change l année', async () => {
    const onAnneeChange = vi.fn()
    mount('COORDONNEE_OK', { onAnneeChange })
    const select = screen.getByLabelText(/année académique/i)
    await user.selectOptions(select, '2')
    expect(screen.getByRole('button', { name: /générer/i })).not.toBeDisabled()
    expect(onAnneeChange).toHaveBeenCalledWith('2')
  })
})
