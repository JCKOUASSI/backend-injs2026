/**
 * Tests de la page Sessions de jury LMD (LOT 12) — liste, filtres et workflow
 * de transition d'une session (contrôler → calculer → délibérer → décider →
 * générer le PV → valider → verrouiller → publier), qui parachève le parcours
 * académique de l'étudiant après la saisie des notes.
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
import Jurys from '@/pages/scolarite/Jurys'

const listCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p === '/juries/sessions/')
    .map(([, opts]) => opts?.params || {})
const actionCalls = () =>
  apiMock.post.mock.calls
    .filter(([p]) => p.includes('/action/'))
    .map(([p, body]) => ({ path: p, body }))
const refCalls = () =>
  apiMock.get.mock.calls.filter(([p]) => p.startsWith('/scolarite/ref/'))

const makeSession = (id, statut, libelle) => ({
  id, libelle: libelle || `Session ${statut} #${id}`, annee_academique_id: 1,
  ref_formation_id: 10, niveau_id: 2, type_session: 'NORMAL', statut,
})
const SESSIONS = [
  makeSession(1, 'PREPARATION', 'Jury normal L1 2025-2026'),
  makeSession(2, 'VERROUILLE', 'Jury rattrapage L1'),
  makeSession(3, 'PUBLIE', 'Jury publié L2'),
]

// État pilotable par test : sessions renvoyées et nombre d'échecs initials de
// la liste (utilisé par le test [écart §10.10]).
let sessions = SESSIONS
let listFailures = 0
const setSessions = (arr) => { sessions = arr }
const failListTimes = (n) => { listFailures = n }

const setupRoutes = () => {
  apiController.setRoute('/scolarite/ref/annees/', () => [
    { id: 1, libelle: '2025-2026' },
    { id: 2, libelle: '2024-2025' },
  ])
  apiController.setRoute('/scolarite/ref/formations/', () => [
    { id: 10, intitule: 'L1 LSF' },
    { id: 11, intitule: 'L2 LSF' },
  ])
  apiController.setRoute('/juries/sessions/', () => {
    if (listFailures > 0) {
      listFailures -= 1
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Serveur de jurys indisponible.' } } }
    }
    return sessions
  })
}

const mount = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role === 'ADMIN' ? 'admin' : 'direction' })
  apiController.setMe(me)
  return renderWithProviders(<Jurys />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/jurys'],
  })
}
const settle = async (n = 6) => {
  await act(async () => { await flushPromises(n) })
}
const rowOf = (libelle) => screen.getByText(libelle).closest('tr')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  sessions = SESSIONS
  listFailures = 0
  setupRoutes()
})
afterEach(() => vi.restoreAllMocks())

describe('pages/scolarite/Jurys — liste et filtres', () => {
  it('affiche les sessions avec leur badge et charge les référentiels (rôle acteur)', async () => {
    mount()
    expect(await screen.findByText('Jury normal L1 2025-2026')).toBeInTheDocument()
    expect(screen.getByText('Jury publié L2')).toBeInTheDocument()

    // Un badge par statut (scopé en ligne : le libellé est aussi une option du filtre).
    expect(within(rowOf('Jury normal L1 2025-2026')).getByText('PREPARATION')).toHaveClass('text-bg-secondary')
    expect(within(rowOf('Jury publié L2')).getByText('PUBLIE')).toHaveClass('text-bg-success')

    // Les référentiels alimentant les filtres sont chargés (rôle peutAgir).
    expect(refCalls()).toHaveLength(2)
    expect(screen.getByRole('option', { name: '2025-2026' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'L1 LSF' })).toBeInTheDocument()

    // La colonne Actions et le bouton contextuel du statut sont présents.
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument()
    expect(within(rowOf('Jury normal L1 2025-2026')).getByRole('button', { name: 'Contrôler' })).toBeInTheDocument()
  })

  it('passe les trois filtres tels quels (clés toujours présentes, valeurs vides comprises)', async () => {
    mount()
    await screen.findByText('Jury normal L1 2025-2026')

    // L'appel initial véhicule les trois clés, même vides (params bruts).
    expect(listCalls()[0]).toEqual({ statut: '', annee_id: '', formation_id: '' })

    const [statutSel, anneeSel, formationSel] = screen.getAllByRole('combobox')
    fireEvent.change(statutSel, { target: { value: 'PREPARATION' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ statut: 'PREPARATION' })

    fireEvent.change(anneeSel, { target: { value: '1' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ statut: 'PREPARATION', annee_id: '1' })

    fireEvent.change(formationSel, { target: { value: '10' } })
    await settle()
    expect(listCalls().at(-1)).toEqual({ statut: 'PREPARATION', annee_id: '1', formation_id: '10' })
  })

  // Régression §10.10 (corrigé au LOT 13) : un échec du chargement initial ne
  // doit déclencher QU'UNE SEULE requête et QU'UN SEUL toast, puis l'écran doit
  // montrer l'état vide — pas de relance automatique. La valeur du
  // ToastContext étant désormais stable, l'échec ne recrée plus `charger`.
  // On programme deux échecs puis un succès : une page saine ne consomme que
  // la première réponse (l'échec) et ne requête jamais à nouveau.
  it('échec de chargement : une seule requête, un seul toast et état vide (régression §10.10)', async () => {
    failListTimes(2)
    mount()

    expect(await screen.findByText('Serveur de jurys indisponible.')).toBeInTheDocument()
    await settle()
    expect(listCalls()).toHaveLength(1)
    expect(screen.getAllByText('Serveur de jurys indisponible.')).toHaveLength(1)
    expect(screen.getByText('Aucune session de jury.')).toBeInTheDocument()
  })
})

describe('pages/scolarite/Jurys — actions de transition', () => {
  it('exécute « Contrôler » (PREPARATION) après confirmation, notifie et recharge', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await screen.findByText('Jury normal L1 2025-2026')

    fireEvent.click(
      within(rowOf('Jury normal L1 2025-2026')).getByRole('button', { name: 'Contrôler' }),
    )
    await settle(8)

    expect(actionCalls()).toEqual([
      { path: '/juries/sessions/1/action/', body: { action: 'transition' } },
    ])
    expect(await screen.findByText(/exécutée/i)).toBeInTheDocument()
    expect(window.confirm).toHaveBeenCalledTimes(1)
    // La liste est rechargée après l'action.
    expect(listCalls().length).toBeGreaterThan(1)
  })

  it('appelle la bonne action selon le statut : « publier » pour une session verrouillée', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await screen.findByText('Jury publié L2')

    fireEvent.click(within(rowOf('Jury rattrapage L1')).getByRole('button', { name: 'Publier' }))
    await settle(8)

    expect(actionCalls()).toEqual([
      { path: '/juries/sessions/2/action/', body: { action: 'publier' } },
    ])

    // Une session déjà PUBLIÉE n'offre plus aucun bouton (workflow terminé).
    expect(
      within(rowOf('Jury publié L2')).queryByRole('button'),
    ).not.toBeInTheDocument()
  })

  // Le workflow complet : à chaque statut correspond un unique bouton qui émet
  // la bonne action (PREPARATION et VERROUILLE sont vérifiés dans les tests
  // dédiés ci-dessus ; on couvre ici les six autres étapes).
  it.each([
    ['CONTROLE', 'Calculer', 'calcul'],
    ['CALCUL', 'Délibérer', 'transition'],
    ['DELIBERATION', 'Décider', 'transition'],
    ['DECISION', 'Générer PV', 'generer_pv'],
    ['PV_GENERE', 'Valider', 'transition'],
    ['VALIDE', 'Verrouiller', 'transition'],
  ])('statut %s — le bouton « %s » émet l’action « %s »', async (statut, bouton, actionAttendue) => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    setSessions([makeSession(9, statut)])
    mount()
    expect(await screen.findByText(`Session ${statut} #9`)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: new RegExp(bouton) }))
    await settle(8)

    expect(actionCalls()).toEqual([
      { path: '/juries/sessions/9/action/', body: { action: actionAttendue } },
    ])
  })

  it('n’émet rien si l’agent annule la confirmation', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await screen.findByText('Jury normal L1 2025-2026')

    fireEvent.click(
      within(rowOf('Jury normal L1 2025-2026')).getByRole('button', { name: 'Contrôler' }),
    )
    await settle()

    expect(actionCalls()).toHaveLength(0)
    expect(screen.queryByText(/exécutée/i)).not.toBeInTheDocument()
  })

  it('notifie le détail renvoyé par le backend quand l’action échoue', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiController.setRoute(/\/juries\/sessions\/\d+\/action\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Le procès-verbal manque.' } } }
    })
    mount()
    await screen.findByText('Jury normal L1 2025-2026')

    fireEvent.click(
      within(rowOf('Jury normal L1 2025-2026')).getByRole('button', { name: 'Contrôler' }),
    )
    await settle(8)

    expect(actionCalls()).toHaveLength(1)
    expect(await screen.findByText('Le procès-verbal manque.')).toBeInTheDocument()
    expect(screen.queryByText(/exécutée/i)).not.toBeInTheDocument()
  })
})

describe('pages/scolarite/Jurys — lecture seule', () => {
  it('masque les actions et ne charge pas les référentiels pour un rôle non habilité', async () => {
    // La DIRECTION n'appartient pas à SCOLARITE_MUTATION_ROLES.
    mount('DIRECTION')
    expect(await screen.findByText('Jury normal L1 2025-2026')).toBeInTheDocument()

    expect(screen.queryByRole('columnheader', { name: 'Actions' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Contrôler' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Publier' })).not.toBeInTheDocument()
    expect(refCalls()).toHaveLength(0)
  })
})
