/**
 * Tests de la planification des rattrapages de présence (Rattrapages, LOT 15) :
 * déplacer un étudiant vers la séance d'une autre cohorte, générer le pointage
 * ou annuler — sans toucher à son groupe d'origine.
 *
 * Sont couverts : liste et filtres (statut, recherche), habilitations
 * (PRESENCE_ACTION_ROLES), création via recherche d'étudiant + sélection
 * multiple de séances (ou d'un module entier), blocage des séances où
 * l'étudiant est déjà inscrit, génération de présence, annulation confirmée
 * (avec/sans pointage), états vide/erreur/lecture seule.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
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
import Rattrapages from '@/pages/Rattrapages'

const PARTICIPANTS = [
  { id: 7, nom: 'Koné', prenom: 'Awa', matricule: 'MAT-001', grade: 'L1', groupe: 'G1' },
]
const SEANCES = [
  {
    id: 100, date: '2026-09-15', intitule: 'Séance LSF rattrapage', heure_debut: '09:00', heure_fin: '11:00',
    module: { id: 50, intitule: 'LSF A1', cohorte: 'L1 / G1' }, deja_inscrit: false,
  },
  {
    id: 101, date: '2026-09-16', intitule: 'Séance déjà suivie', heure_debut: '10:00', heure_fin: '12:00',
    module: { id: 51, intitule: 'LSF A2', cohorte: 'L1 / G2' }, deja_inscrit: true,
  },
]
const MODULES = [
  {
    id: 60, intitule: 'Module accueil complet', cohorte: 'L2 / G3', formation: 'L2 LSF', nb_seances: 2, deja_inscrit: false,
    seances: [
      { id: 200, date: '2026-09-20', intitule: 'Jour 1', heure_debut: '09:00', heure_fin: '12:00', module: { id: 60, intitule: 'Module accueil complet', cohorte: 'L2 / G3' }, deja_inscrit: false },
      { id: 201, date: '2026-09-21', intitule: 'Jour 2', heure_debut: '09:00', heure_fin: '12:00', module: { id: 60, intitule: 'Module accueil complet', cohorte: 'L2 / G3' }, deja_inscrit: false },
    ],
  },
  {
    id: 61, intitule: 'Module déjà fait', cohorte: 'L2 / G4', formation: 'L2 LSF', nb_seances: 1, deja_inscrit: true,
    seances: [{ id: 300, date: '2026-09-22', intitule: 'Jour X', module: { id: 61, intitule: 'Module déjà fait' }, deja_inscrit: true }],
  },
]
const RATTRAPAGES = [
  {
    id: 1, statut: 'PLANIFIE', pointage_id: null,
    participant: { id: 7, nom: 'Koné', prenom: 'Awa', matricule: 'MAT-001', grade: 'L1', groupe: 'G1' },
    module_accueil: { intitule: 'LSF A1', formation: 'L1 LSF', cohorte: 'L1 / G1' },
    seance_rattrapage: { date: '2026-09-15', intitule: 'Séance LSF rattrapage', heure_debut: '09:00', heure_fin: '11:00' },
  },
  {
    id: 2, statut: 'EFFECTUE', pointage_id: 555,
    participant: { id: 8, nom: 'Diop', prenom: 'Karim', matricule: 'MAT-002', grade: 'L1' },
    module_accueil: { intitule: 'LSF A2', formation: 'L1 LSF', cohorte: 'L1 / G2' },
    seance_rattrapage: { date: '2026-09-16', intitule: 'Séance A2', heure_debut: '10:00', heure_fin: '12:00' },
  },
  {
    id: 3, statut: 'ANNULE', pointage_id: null,
    participant: { id: 9, nom: 'Bamba', prenom: 'Fatou', matricule: 'MAT-003', grade: 'L1' },
    module_accueil: { intitule: 'LSF B1', formation: 'L1 LSF', cohorte: 'L1 / G3' },
    seance_rattrapage: { date: '2026-09-17', intitule: 'Séance B1' },
  },
]

let list = RATTRAPAGES
let listFailures = 0
let createResponse = { count: 1, skipped: [], reactivated: [] }
let createThrows = null

const setupRoutes = () => {
  // Même chemin exact pour le GET liste et le POST création : on distingue par
  // la présence d'un corps (POST).
  apiController.setRoute('/rattrapages/', (path, body) => {
    if (body) {
      if (createThrows) throw createThrows
      return createResponse
    }
    if (listFailures > 0) {
      listFailures -= 1
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Service indisponible' } } }
    }
    return list
  })
  apiController.setRoute('/rattrapages/participants/', () => PARTICIPANTS)
  apiController.setRoute('/rattrapages/seances/', () => SEANCES)
  apiController.setRoute('/rattrapages/modules/', () => MODULES)
}

const mount = (role = 'ENCADRANT') => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<Rattrapages />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/rattrapages'],
  })
}
const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }
// Les recherches déroulantes et les filtres sont débordancés à 250/300 ms.
const waitReal = async (ms = 320) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)) }) }
const modal = () => document.querySelector('.modal-content')
const listGets = () =>
  apiMock.get.mock.calls.filter(([p]) => p.split('?')[0] === '/rattrapages/').map(([p]) => p)
const postsWhere = (pred) =>
  apiMock.post.mock.calls.filter(([p]) => pred(p)).map(([p, b]) => ({ path: p, body: b }))
const rowOf = (matricule) => screen.getByText(matricule).closest('tr')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  list = RATTRAPAGES
  listFailures = 0
  createResponse = { count: 1, skipped: [], reactivated: [] }
  createThrows = null
  setupRoutes()
})

describe('Rattrapages — liste, filtres et habilitations', () => {
  it('affiche les rattrapages avec leur badge, cohorte et actions (rôle gestion)', async () => {
    mount()
    expect(await screen.findByText('MAT-001')).toBeInTheDocument()

    // Badges scopés en ligne (les libellés existent aussi comme options de filtre).
    expect(within(rowOf('MAT-001')).getByText('Planifié')).toBeInTheDocument()
    expect(within(rowOf('MAT-002')).getByText('Effectué')).toBeInTheDocument()
    expect(within(rowOf('MAT-003')).getByText('Annulé')).toBeInTheDocument()
    expect(within(rowOf('MAT-001')).getByText('LSF A1')).toBeInTheDocument()
    expect(within(rowOf('MAT-001')).getByText(/Séance LSF rattrapage/)).toBeInTheDocument()

    expect(screen.getByRole('button', { name: /nouveau rattrapage/i })).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument()
  })

  it('transmet le filtre de statut puis la recherche en paramètres (debounced)', async () => {
    mount()
    await screen.findByText('MAT-001')

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'PLANIFIE' } })
    await waitReal(360)
    expect(listGets().at(-1)).toContain('statut=PLANIFIE')

    fireEvent.change(screen.getByPlaceholderText('Rechercher (étudiant, module…)'), {
      target: { value: 'Koné' },
    })
    await waitReal(360)
    const last = listGets().at(-1)
    expect(last).toContain('statut=PLANIFIE')
    expect(last).toContain('q=Kon%C3%A9')
  })

  it('affiche un message d’erreur si le chargement échoue', async () => {
    listFailures = 5 // plusieurs échecs : la page se contente d’afficher l’erreur, sans boucle.
    mount()
    expect(await screen.findByText('Erreur lors du chargement des rattrapages')).toBeInTheDocument()
  })

  it('affiche l’état vide avec une invitation à créer pour un gestionnaire', async () => {
    list = []
    mount()
    const empty = await screen.findByText(/aucun rattrapage/i)
    // Le paragraphe d'état vide porte aussi l'invite à créer (le bouton existe par ailleurs).
    expect(empty.textContent).toMatch(/nouveau rattrapage/i)
    expect(screen.getByRole('button', { name: /nouveau rattrapage/i })).toBeInTheDocument()
  })

  it('masque la création et les actions pour un rôle en lecture seule (DIRECTION)', async () => {
    mount('DIRECTION')
    expect(await screen.findByText('MAT-001')).toBeInTheDocument()

    expect(screen.queryByRole('button', { name: /nouveau rattrapage/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Actions' })).not.toBeInTheDocument()
    expect(
      within(rowOf('MAT-001')).queryByRole('button', { name: /générer la présence/i }),
    ).not.toBeInTheDocument()
  })
})

describe('Rattrapages — création', () => {
  const openModal = async () => {
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(screen.getByRole('button', { name: /nouveau rattrapage/i }))
    expect(await screen.findByText('Nouveau rattrapage', { selector: 'h5' })).toBeInTheDocument()
  }
  const chooseParticipant = async () => {
    const input = within(modal()).getByPlaceholderText(/rechercher par matricule ou nom/i)
    fireEvent.focus(input)
    const option = await within(modal()).findByText(/MAT-001/)
    fireEvent.click(option.closest('button'))
    // L'étudiant sélectionné reste affiché (champ figé).
    expect(within(modal()).getByText(/MAT-001/)).toBeInTheDocument()
  }

  it('refuse la création sans étudiant ou sans séance (aucun appel API)', async () => {
    await openModal()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Créer' }))
    expect(await within(modal()).findByText(/sélectionnez un étudiant et au moins une séance/i)).toBeInTheDocument()
    expect(postsWhere((p) => p === '/rattrapages/')).toHaveLength(0)
  })

  it('crée un rattrapage après recherche étudiant + choix d’une séance, motif et forçage de présence', async () => {
    await openModal()
    await chooseParticipant()

    // La recherche des séances est ciblée sur l'étudiant choisi.
    const seanceInput = within(modal()).getByPlaceholderText(/rechercher un module \/ groupe/i)
    fireEvent.focus(seanceInput)
    await waitReal()
    expect(apiMock.get.mock.calls.some(([p]) => p.includes('/rattrapages/seances/') && p.includes('participant=7'))).toBe(true)

    // La séance où l'étudiant est déjà inscrit est verrouillée ; l'autre est cliquable.
    const blocked = within(modal()).getByText(/Séance déjà suivie/).closest('button')
    expect(blocked).toBeDisabled()
    fireEvent.click(within(modal()).getByText(/Séance LSF rattrapage/).closest('button'))
    // La séance ajoutée apparaît sous forme de pastille.
    expect(within(modal()).getByTitle('Retirer')).toBeInTheDocument()

    fireEvent.change(within(modal()).getByPlaceholderText(/absence justifiée/i), {
      target: { value: 'Absence justifiée' },
    })
    fireEvent.click(within(modal()).getByRole('checkbox'))

    fireEvent.click(within(modal()).getByRole('button', { name: 'Créer' }))

    expect(await screen.findByText('1 rattrapage(s) créé(s)')).toBeInTheDocument()
    expect(postsWhere((p) => p === '/rattrapages/')).toEqual([{
      path: '/rattrapages/',
      body: {
        participant_id: 7,
        seance_rattrapage_ids: [100],
        motif: 'Absence justifiée',
        generer_presence: true,
      },
    }])
    // La modale se ferme et la liste est rechargée.
    expect(document.querySelector('.modal-overlay')).toBeNull()
    expect(listGets().length).toBeGreaterThan(2)
  })

  it('permet d’ajouter toutes les séances d’un module d’accueil et verrouille un module déjà fait', async () => {
    await openModal()
    await chooseParticipant()

    fireEvent.click(within(modal()).getByRole('button', { name: /module entier/i }))
    const moduleInput = within(modal()).getByPlaceholderText(/module d.accueil/i)
    fireEvent.focus(moduleInput)
    await waitReal()

    expect(within(modal()).getByText('Module déjà fait').closest('button')).toBeDisabled()
    fireEvent.click(within(modal()).getByText('Module accueil complet').closest('button'))

    // Les deux séances du module sont ajoutées (pastilles « Jour 1 » / « Jour 2 »).
    expect(within(modal()).getByText(/Jour 1/)).toBeInTheDocument()
    expect(within(modal()).getByText(/Jour 2/)).toBeInTheDocument()
    expect(within(modal()).getAllByTitle('Retirer')).toHaveLength(2)
  })

  it('permet de retirer une séance sélectionnée', async () => {
    await openModal()
    await chooseParticipant()
    const seanceInput = within(modal()).getByPlaceholderText(/rechercher un module \/ groupe/i)
    fireEvent.focus(seanceInput)
    await waitReal()
    fireEvent.click(within(modal()).getByText(/Séance LSF rattrapage/).closest('button'))
    expect(within(modal()).getAllByTitle('Retirer')).toHaveLength(1)

    fireEvent.click(within(modal()).getByTitle('Retirer'))
    expect(within(modal()).queryAllByTitle('Retirer')).toHaveLength(0)
  })

  it('détaille les créations, réactivations et ignorés dans le toast de résultat', async () => {
    createResponse = { count: 2, skipped: [{ id: 1 }], reactivated: [{ id: 2 }] }
    await openModal()
    await chooseParticipant()
    const seanceInput = within(modal()).getByPlaceholderText(/rechercher un module \/ groupe/i)
    fireEvent.focus(seanceInput)
    await waitReal()
    fireEvent.click(within(modal()).getByText(/Séance LSF rattrapage/).closest('button'))
    fireEvent.click(within(modal()).getByRole('button', { name: 'Créer' }))

    expect(await screen.findByText(/2 rattrapage\(s\) créé\(s\)/)).toHaveTextContent(
      '2 rattrapage(s) créé(s) (1 réactivé(s)) — 1 ignoré(s) (déjà existant)',
    )
  })

  it('affiche l’erreur serveur dans la modale sans la fermer', async () => {
    createThrows = { response: { data: { detail: 'Hors calendrier de rattrapage' } } }
    await openModal()
    await chooseParticipant()
    const seanceInput = within(modal()).getByPlaceholderText(/rechercher un module \/ groupe/i)
    fireEvent.focus(seanceInput)
    await waitReal()
    fireEvent.click(within(modal()).getByText(/Séance LSF rattrapage/).closest('button'))
    fireEvent.click(within(modal()).getByRole('button', { name: 'Créer' }))

    expect(await within(modal()).findByText('Hors calendrier de rattrapage')).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).not.toBeNull()
  })
})

describe('Rattrapages — actions sur une ligne', () => {
  it('génère la présence (POST) puis recharge et notifie', async () => {
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: /générer la présence/i }))
    await settle(8)

    expect(postsWhere((p) => p.includes('/generer-presence/'))).toEqual([
      { path: '/rattrapages/1/generer-presence/', body: undefined },
    ])
    expect(await screen.findByText('Présence de rattrapage générée')).toBeInTheDocument()
  })

  it('annule un rattrapage planifié (sans pointage) après confirmation', async () => {
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Annuler' }))

    // La modale de confirmation précise qu'aucune présence n'existe encore.
    expect(await screen.findByText('Annuler ce rattrapage ?')).toBeInTheDocument()
    expect(screen.getByText('Le rattrapage passera au statut « Annulé ».')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))

    expect(await screen.findByText('Rattrapage annulé')).toBeInTheDocument()
    expect(postsWhere((p) => p.includes('/annuler/'))).toEqual([
      { path: '/rattrapages/1/annuler/', body: { supprimer_pointage: false } },
    ])
  })

  it('à l’annulation d’un rattrapage effectué, supprime le pointage généré', async () => {
    mount()
    await screen.findByText('MAT-002')
    fireEvent.click(within(rowOf('MAT-002')).getByRole('button', { name: 'Annuler' }))
    expect(await screen.findByText('La présence générée sera également supprimée.')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)

    expect(postsWhere((p) => p.includes('/annuler/'))).toEqual([
      { path: '/rattrapages/2/annuler/', body: { supprimer_pointage: true } },
    ])
  })

  it('n’émet rien si la confirmation d’annulation est refusée', async () => {
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Annuler' }))
    expect(await screen.findByText('Annuler ce rattrapage ?')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()

    expect(postsWhere((p) => p.includes('/annuler/'))).toHaveLength(0)
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })

  it('notifie l’erreur renvoyée si la génération de présence échoue', async () => {
    apiController.setRoute(/\/rattrapages\/\d+\/generer-presence\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Séance non démarrée' } } }
    })
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: /générer la présence/i }))
    await settle(8)

    expect(await screen.findByText('Séance non démarrée')).toBeInTheDocument()
    expect(screen.queryByText('Présence de rattrapage générée')).not.toBeInTheDocument()
  })

  it('notifie l’erreur renvoyée si l’annulation échoue', async () => {
    apiController.setRoute(/\/rattrapages\/\d+\/annuler\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Annulation refusée par le backend' } } }
    })
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Annuler' }))
    expect(await screen.findByText('Annuler ce rattrapage ?')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)

    expect(await screen.findByText('Annulation refusée par le backend')).toBeInTheDocument()
    expect(screen.queryByText('Rattrapage annulé')).not.toBeInTheDocument()
  })

  it('n’offre aucune action sur un rattrapage déjà annulé', async () => {
    mount()
    await screen.findByText('MAT-003')
    const row = rowOf('MAT-003')
    expect(within(row).queryByRole('button', { name: /présence/i })).not.toBeInTheDocument()
    expect(within(row).queryByRole('button', { name: 'Annuler' })).not.toBeInTheDocument()
  })
})
