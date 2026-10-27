/**
 * Tests de la page Diplômation & Documents officiels (LOT 12) — liste des
 * diplômes, validation (gèle le PDF), révocation motivée, et portail public
 * de vérification d'un diplôme par son numéro unique. Termine le parcours
 * étudiant : après la délibération du jury, le diplôme est délivré puis
 * vérifiable par un tiers.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, act, within, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Graduation from '@/pages/scolarite/Graduation'

const listCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p === '/graduation/diplomes/')
    .map(([, opts]) => opts?.params || {})
const posts = (predicate = () => true) =>
  apiMock.post.mock.calls
    .filter(([p]) => predicate(p))
    .map(([p, body]) => ({ path: p, body }))
const verifierCalls = () =>
  apiMock.get.mock.calls.filter(([p]) => p.includes('/graduation/verifier/'))

const DIPLOMES = [
  {
    id: 1, nom_complet: 'Awa Koné', matricule: 'MAT-001', ref_formation: 'L1 LSF',
    niveau: 'N1', mention: '', credits_acquis: 60, statut: 'VALIDATION_PENDING',
    statut_display: 'En attente', date_validation: null,
  },
  {
    id: 2, nom_complet: 'Karim Diop', matricule: 'MAT-002', ref_formation: 'L2 LSF',
    niveau: 'N2', mention: 'Bien', credits_acquis: 120, statut: 'VALIDATED',
    statut_display: 'Validé', date_validation: '2026-07-01',
  },
  {
    id: 3, nom_complet: 'Fatou Bamba', matricule: 'MAT-003', ref_formation: 'L1 LSF',
    niveau: 'N1', mention: '', credits_acquis: 0, statut: 'BROUILLON',
    statut_display: 'Brouillon', date_validation: null,
  },
]

// Nombre d'échecs initiaux de la liste (test [écart §10.10]).
let listFailures = 0
const failListTimes = (n) => { listFailures = n }

const setupRoutes = () => {
  apiController.setRoute('/graduation/diplomes/', () => {
    if (listFailures > 0) {
      listFailures -= 1
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Service de diplômation indisponible.' } } }
    }
    return DIPLOMES
  })
}

const mount = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role === 'ADMIN' ? 'admin' : 'direction' })
  apiController.setMe(me)
  return renderWithProviders(<Graduation />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/graduation'],
  })
}
const settle = async (n = 6) => {
  await act(async () => { await flushPromises(n) })
}
const rowOf = (matricule) => screen.getByText(matricule).closest('tr')
const tokenInput = () => screen.getByPlaceholderText(/numéro unique/i)
const submitVerifier = () =>
  fireEvent.click(screen.getByRole('button', { name: /vérifier/i }))

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  listFailures = 0
  setupRoutes()
})
afterEach(() => vi.restoreAllMocks())

describe('pages/scolarite/Graduation — liste et filtres', () => {
  it('affiche les diplômes, leur mention/ECTS et le lien PDF pour un diplôme validé', async () => {
    mount()
    expect(await screen.findByText('MAT-001')).toBeInTheDocument()
    expect(screen.getByText('Fatou Bamba')).toBeInTheDocument()

    // Badges et données (scopé en ligne : le libellé est aussi une option du filtre).
    expect(within(rowOf('MAT-001')).getByText('En attente')).toHaveClass('text-bg-info')
    expect(within(rowOf('MAT-002')).getByText('Validé')).toHaveClass('text-bg-success')
    expect(within(rowOf('MAT-002')).getByText('Bien')).toBeInTheDocument()
    expect(within(rowOf('MAT-002')).getByText('120')).toBeInTheDocument()
    // Mention absente et date non validée : deux tirets dans la ligne.
    expect(within(rowOf('MAT-001')).getAllByText('—')).toHaveLength(2)

    // Le PDF n'est proposé que pour un diplôme validé.
    const pdf = within(rowOf('MAT-002')).getByRole('link', { name: 'PDF' })
    expect(pdf).toHaveAttribute('href', '/api/graduation/diplomes/2/pdf/')
    expect(pdf).toHaveAttribute('target', '_blank')
    expect(within(rowOf('MAT-001')).queryByRole('link', { name: 'PDF' })).not.toBeInTheDocument()
  })

  it('passe les filtres statut, année et formation au service', async () => {
    mount()
    await screen.findByText('MAT-001')

    expect(listCalls()[0]).toEqual({ statut: '', annee_id: '', formation_id: '' })

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'VALIDATED' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ statut: 'VALIDATED' })

    fireEvent.change(screen.getByPlaceholderText('ID année'), { target: { value: '3' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ statut: 'VALIDATED', annee_id: '3' })

    fireEvent.change(screen.getByPlaceholderText('ID formation'), { target: { value: '10' } })
    await settle()
    expect(listCalls().at(-1)).toEqual({ statut: 'VALIDATED', annee_id: '3', formation_id: '10' })
  })

  // Régression §10.10 (corrigé au LOT 13) : comme Jurys, un échec du
  // chargement initial ne doit produire qu'une seule requête et un seul toast,
  // puis l'état vide. Deux échecs puis un succès sont programmés : une page
  // saine ne consomme que le premier appel.
  it('échec de chargement : une seule requête, un seul toast et état vide (régression §10.10)', async () => {
    failListTimes(2)
    mount()

    expect(await screen.findByText('Service de diplômation indisponible.')).toBeInTheDocument()
    await settle()
    expect(listCalls()).toHaveLength(1)
    expect(screen.getAllByText('Service de diplômation indisponible.')).toHaveLength(1)
    expect(screen.getByText('Aucun diplôme.')).toBeInTheDocument()
  })
})

describe('pages/scolarite/Graduation — validation et révocation', () => {
  it('valide un diplôme en attente après confirmation, notifie et recharge', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await screen.findByText('MAT-001')

    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Valider' }))
    await settle(8)

    expect(posts((p) => p.includes('/valider/'))).toEqual([
      { path: '/graduation/diplomes/1/valider/', body: undefined },
    ])
    expect(await screen.findByText('Diplôme validé et PDF généré.')).toBeInTheDocument()
    expect(listCalls().length).toBeGreaterThan(1)
  })

  it('ne valide pas si la confirmation est annulée', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await screen.findByText('MAT-001')

    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Valider' }))
    await settle()

    expect(posts((p) => p.includes('/valider/'))).toHaveLength(0)
  })

  it('notifie l’erreur backend quand la validation échoue', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiController.setRoute(/\/graduation\/diplomes\/\d+\/valider\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Le PDF original est introuvable.' } } }
    })
    mount()
    await screen.findByText('MAT-001')

    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Valider' }))
    await settle(8)

    expect(await screen.findByText('Le PDF original est introuvable.')).toBeInTheDocument()
    expect(screen.queryByText('Diplôme validé et PDF généré.')).not.toBeInTheDocument()
  })

  it('révoque un diplôme validé avec le motif obligatoire, notifie et recharge', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('Signature du directeur manquante')
    mount()
    await screen.findByText('MAT-002')

    fireEvent.click(within(rowOf('MAT-002')).getByRole('button', { name: /révoquer/i }))
    await settle(8)

    expect(posts((p) => p.includes('/revoquer/'))).toEqual([
      { path: '/graduation/diplomes/2/revoquer/', body: { motif: 'Signature du directeur manquante' } },
    ])
    expect(await screen.findByText('Diplôme révoqué.')).toBeInTheDocument()
    expect(listCalls().length).toBeGreaterThan(1)
  })

  it('n’émet aucune révocation si le motif est vide ou la boîte annulée', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue(null)
    mount()
    await screen.findByText('MAT-002')

    fireEvent.click(within(rowOf('MAT-002')).getByRole('button', { name: /révoquer/i }))
    await settle()

    expect(posts((p) => p.includes('/revoquer/'))).toHaveLength(0)
    expect(screen.queryByText('Diplôme révoqué.')).not.toBeInTheDocument()
  })

  it('notifie l’erreur backend quand la révocation échoue (le motif est bien transmis)', async () => {
    vi.spyOn(window, 'prompt').mockReturnValue('Erreur matérielle sur le parchemin')
    apiController.setRoute(/\/graduation\/diplomes\/\d+\/revoquer\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Révocation rejetée par le bureau des archives.' } } }
    })
    mount()
    await screen.findByText('MAT-002')

    fireEvent.click(within(rowOf('MAT-002')).getByRole('button', { name: /révoquer/i }))
    await settle(8)

    expect(posts((p) => p.includes('/revoquer/'))).toEqual([
      { path: '/graduation/diplomes/2/revoquer/', body: { motif: 'Erreur matérielle sur le parchemin' } },
    ])
    expect(await screen.findByText('Révocation rejetée par le bureau des archives.')).toBeInTheDocument()
    expect(screen.queryByText('Diplôme révoqué.')).not.toBeInTheDocument()
  })

  it('n’offre aucune action sur un diplôme au stade brouillon', async () => {
    mount()
    await screen.findByText('MAT-003')
    expect(within(rowOf('MAT-003')).queryByRole('button')).not.toBeInTheDocument()
    expect(within(rowOf('MAT-003')).queryByRole('link', { name: 'PDF' })).not.toBeInTheDocument()
  })
})

describe('pages/scolarite/Graduation — portail public de vérification', () => {
  it('affiche les détails d’un diplôme valide à partir de son numéro unique', async () => {
    apiController.setRoute('/graduation/verifier/DIP-VALIDE-1/', () => ({
      valide: true,
      nom_complet: 'Awa Koné',
      formation: 'Licence LSF',
      niveau: 'N1',
      parcours: 'L3 Parcours LSF',
      mention: 'Bien',
      annee_academique: '2025-2026',
      date_validation: '2026-07-01',
    }))
    mount()
    expect(await screen.findByText(/portail public de vérification/i)).toBeInTheDocument()

    fireEvent.change(tokenInput(), { target: { value: 'DIP-VALIDE-1' } })
    submitVerifier()
    await settle()

    expect(verifierCalls()).toHaveLength(1)
    expect(verifierCalls()[0][0]).toBe('/graduation/verifier/DIP-VALIDE-1/')
    const alerte = screen.getByText('Diplôme valide').closest('.alert')
    expect(alerte).toHaveClass('alert-success')
    expect(within(alerte).getByText('Awa Koné')).toBeInTheDocument()
    expect(within(alerte).getByText(/Licence LSF/)).toBeInTheDocument()
    expect(within(alerte).getByText(/Mention : Bien/)).toBeInTheDocument()
    expect(within(alerte).getByText(/2025-2026/)).toBeInTheDocument()
  })

  it('affiche la raison renvoyée par le backend pour un numéro inconnu', async () => {
    apiController.setRoute('/graduation/verifier/INCONNU/', () => ({
      valide: false,
      raison: 'Aucun diplôme ne correspond à ce numéro.',
    }))
    mount()
    await screen.findByText(/portail public de vérification/i)

    fireEvent.change(tokenInput(), { target: { value: 'INCONNU' } })
    submitVerifier()
    await settle()

    const alerte = (await screen.findByText(/Aucun diplôme ne correspond/)).closest('.alert')
    expect(alerte).toHaveClass('alert-danger')
  })

  it('affiche une alerte d’erreur quand la vérification échoue (réseau/serveur)', async () => {
    apiController.setRoute(/\/graduation\/verifier\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { status: 500 } }
    })
    mount()
    await screen.findByText(/portail public de vérification/i)

    fireEvent.change(tokenInput(), { target: { value: 'DIP-CASSE' } })
    submitVerifier()
    await settle()

    expect(await screen.findByText('Erreur de vérification.')).toBeInTheDocument()
  })

  it('ne requête pas le portail tant qu’aucun numéro n’est saisi', async () => {
    mount()
    await screen.findByText(/portail public de vérification/i)

    submitVerifier()
    await settle()

    expect(verifierCalls()).toHaveLength(0)
    expect(screen.queryByText('Diplôme valide')).not.toBeInTheDocument()
  })
})

describe('pages/scolarite/Graduation — lecture seule', () => {
  it('masque les actions de gestion pour un rôle non habilité mais garde le portail public', async () => {
    mount('DIRECTION')
    expect(await screen.findByText('MAT-001')).toBeInTheDocument()

    expect(screen.queryByRole('columnheader', { name: 'Actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Valider' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /révoquer/i })).not.toBeInTheDocument()

    // Le portail de vérification reste accessible à tous (public).
    expect(screen.getByText(/portail public de vérification/i)).toBeInTheDocument()
    expect(tokenInput()).toBeInTheDocument()
  })
})
