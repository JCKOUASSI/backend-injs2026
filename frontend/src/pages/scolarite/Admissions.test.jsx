/**
 * Tests de la page Admissions (LOT 10) — boucle la chaîne admission :
 *   décision (PATCH profil + POST décision), inscription d'un admis via la
 *   modale de confirmation (POST depuis-admission), annulation, filtres.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Admissions from '@/pages/scolarite/Admissions'

const admissionsList = () => [
  {
    id: 1, candidat: 'Awa Koné', candidature_numero: 'C-005', ref_formation: 'L1 LSF',
    niveau: 'N1', decision: 'EN_ATTENTE', decision_libelle: 'En attente',
    permet_inscription: false, reference_decision: '', date_limite_inscription: '',
  },
  {
    id: 2, candidat: 'Karim Diop', candidature_numero: 'C-006', ref_formation: 'L1 LSF',
    niveau: 'N1', decision: 'ADMIS', decision_libelle: 'Admis',
    permet_inscription: true, reference_decision: '', date_limite_inscription: '',
  },
]

const writes = (predicate) =>
  apiMock.post.mock.calls
    .filter(([p]) => predicate(p))
    .map(([p, body]) => ({ path: p, body }))
const patches = (predicate) =>
  apiMock.patch.mock.calls
    .filter(([p]) => predicate(p))
    .map(([p, body]) => ({ path: p, body }))
const listCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.split('?')[0] === '/admissions/admissions/')
    .map(([, opts]) => opts?.params || {})

const setupRoutes = () => {
  apiController.setRoute('/scolarite/annee-courante/', () => ({ annee: { id: 1, libelle: '2025-2026' } }))
  apiController.setRoute('/formations/ref/categories/', () => [{ id: 1, libelle: 'Catégorie A' }])
  apiController.setRoute('/formations/ref/grades/', () => [
    { id: 10, libelle: 'Grade 1', categorie: 1 },
    { id: 11, libelle: 'Grade 2', categorie: 2 },
  ])
  apiController.setRoute('/admissions/admissions/', () => admissionsList())
  apiController.setRoute('/scolarite/inscriptions/depuis-admission/', () => ({
    matricule: 'MAT-2026-001', etudiant_id: 5,
  }))
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  // '*' : la page appelle navigate(...) après inscription ; elle reste montée.
  return renderWithProviders(<Admissions />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/admissions'],
  })
}
const settle = async (n = 5) => {
  await act(async () => { await flushPromises(n) })
}
const rowOf = (numero) => screen.getByText(numero).closest('tr')
const openPanel = (numero) => {
  fireEvent.click(within(rowOf(numero)).getByRole('button', { name: 'Décision' }))
  return screen.getByText('Enregistrer le profil').closest('.card')
}
const confirmModal = () => document.querySelector('.modal-content')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('pages/scolarite/Admissions — liste et filtres', () => {
  it('affiche les admissions, l’année et gère l’état du bouton Inscrire', async () => {
    mount()
    expect(await screen.findByText('Awa Koné')).toBeInTheDocument()
    expect(screen.getByText('Karim Diop')).toBeInTheDocument()
    expect(screen.getByText(/année 2025-2026/i)).toBeInTheDocument()

    // Admission non finalisée : inscription impossible ; l'admis est éligible.
    expect(within(rowOf('C-005')).getByRole('button', { name: 'Inscrire' })).toBeDisabled()
    expect(within(rowOf('C-006')).getByRole('button', { name: 'Inscrire' })).toBeEnabled()
    // Une admission déjà annulée ne peut pas être réannulée.
    expect(within(rowOf('C-005')).getByRole('button', { name: 'Annuler' })).toBeEnabled()
  })

  it('filtre par décision en passant le paramètre au service', async () => {
    mount()
    await screen.findByText('Awa Koné')
    fireEvent.change(screen.getByDisplayValue('Toutes les décisions'), { target: { value: 'ADMIS' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ decision: 'ADMIS' })
  })
})

describe('pages/scolarite/Admissions — panneau Décision (écritures)', () => {
  it('enregistre le profil administratif (PATCH catégorie/grade liés)', async () => {
    mount()
    await screen.findByText('Awa Koné')
    const card = openPanel('C-005')

    const combos = within(card).getAllByRole('combobox')
    fireEvent.change(combos[0], { target: { value: '1' } }) // catégorie
    await settle()
    fireEvent.change(combos[1], { target: { value: '10' } }) // grade filtré par catégorie
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer le profil' }))
    await settle()

    const p = patches((pth) => /\/admissions\/admissions\/\d+\/$/.test(pth))
    expect(p).toHaveLength(1)
    expect(p[0].path).toBe('/admissions/admissions/1/')
    expect(p[0].body).toEqual({ categorie_id: '1', grade_id: '10' })
    expect(await screen.findByText('Catégorie et grade enregistrés')).toBeInTheDocument()
  })

  it('prononce une décision admise (POST decision, panneau fermé)', async () => {
    mount()
    await screen.findByText('Awa Koné')
    const card = openPanel('C-005')

    fireEvent.change(within(card).getByPlaceholderText('DEC-2026-001'), { target: { value: 'DEC-2026-042' } })
    const combos = within(card).getAllByRole('combobox')
    // Décision par défaut = ADMIS pour une admission en attente ; on explicite.
    fireEvent.change(combos[2], { target: { value: 'ADMIS' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Prononcer' }))
    await settle()

    const d = writes((p) => p.includes('/decision/'))
    expect(d).toHaveLength(1)
    expect(d[0].path).toBe('/admissions/admissions/1/decision/')
    expect(d[0].body).toMatchObject({ decision: 'ADMIS', reference_decision: 'DEC-2026-042' })
    expect(await screen.findByText('Décision enregistrée')).toBeInTheDocument()
    // Le panneau se ferme après prononcé.
    await waitFor(() => expect(screen.queryByText('Enregistrer le profil')).not.toBeInTheDocument())
  })

  it('affiche l’erreur serveur dans le panneau si la décision est refusée', async () => {
    apiController.reset()
    apiController.setRoute(/\/admissions\/admissions\/\d+\/decision\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Décision non autorisée pour ce dossier.' } } }
    })
    setupRoutes()
    mount()
    await screen.findByText('Awa Koné')
    const card = openPanel('C-005')
    fireEvent.click(within(card).getByRole('button', { name: 'Prononcer' }))
    await settle()
    expect(await within(card).findByText(/décision non autorisée/i)).toBeInTheDocument()
  })
})

describe('pages/scolarite/Admissions — inscription et annulation (modale)', () => {
  it('inscrit un admis après confirmation (POST depuis-admission) et notifie le matricule', async () => {
    mount()
    await screen.findByText('Karim Diop')
    fireEvent.click(within(rowOf('C-006')).getByRole('button', { name: 'Inscrire' }))

    const modal = await screen.findByText(/inscrire karim diop/i).then((el) => el.closest('.modal-content'))
    fireEvent.click(within(modal).getByRole('button', { name: 'Confirmer' }))
    await settle(7)

    const posts = writes((p) => p === '/scolarite/inscriptions/depuis-admission/')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toEqual({ admission_id: 2, valider: true })
    expect(await screen.findByText(/matricule MAT-2026-001/i)).toBeInTheDocument()
  })

  it('annule une admission après confirmation (POST annuler) et recharge', async () => {
    mount()
    await screen.findByText('Awa Koné')
    fireEvent.click(within(rowOf('C-005')).getByRole('button', { name: 'Annuler' }))

    const modal = await screen.findByText(/annuler l.admission de awa koné/i).then((el) => el.closest('.modal-content'))
    fireEvent.click(within(modal).getByRole('button', { name: 'Confirmer' }))
    await settle()

    const cancelled = writes((p) => p.includes('/annuler/'))
    expect(cancelled).toHaveLength(1)
    expect(cancelled[0].path).toBe('/admissions/admissions/1/annuler/')
    expect(await screen.findByText('Admission annulée')).toBeInTheDocument()
  })

  it('annuler la modale n’émet aucune écriture', async () => {
    mount()
    await screen.findByText('Awa Koné')
    fireEvent.click(within(rowOf('C-005')).getByRole('button', { name: 'Annuler' }))
    const modal = confirmModal()
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(writes((p) => p.includes('/annuler/'))).toHaveLength(0)
  })
})

describe('pages/scolarite/Admissions — refonte premium (recherche, année, inscrits)', () => {
  const listeRiche = () => [
    {
      id: 1, candidat: 'Awa Koné', candidature_numero: 'C-005', ref_formation: 'L1 LSF',
      niveau: 'L1', annee_academique: '2025-2026', decision: 'EN_ATTENTE',
      decision_libelle: 'En attente', permet_inscription: false,
      reference_decision: '', date_limite_inscription: '', inscrit: false,
    },
    {
      id: 2, candidat: 'Karim Diop', candidature_numero: 'C-006', ref_formation: 'L1 LSF',
      niveau: 'L1', annee_academique: '2025-2026', decision: 'ADMIS',
      decision_libelle: 'Admis', permet_inscription: true,
      reference_decision: 'DEC-2025-006', date_limite_inscription: '2020-01-15',
      est_expiree: true, date_decision: '2025-11-20T10:00:00Z', decide_par: 'admin',
      inscrit: false,
    },
    {
      id: 3, candidat: 'Inscrite Inès Yao', candidature_numero: 'C-007', ref_formation: 'L1 LSF',
      niveau: 'L1', annee_academique: '2025-2026', decision: 'ADMIS',
      decision_libelle: 'Admis', permet_inscription: true,
      reference_decision: 'DEC-2025-007', date_limite_inscription: '2027-01-31',
      inscrit: true, matricule: 'INJS26-0007', etudiant_id: 42,
      inscription_statut: 'Validée',
    },
  ]

  const setupRiche = () => {
    apiController.reset()
    apiController.setRoute('/admissions/admissions/', () => listeRiche())
    apiController.setRoute('/admissions/admissions/stats/', () => ({
      total: 19,
      par_decision: { ADMIS: 7, ADMIS_SOUS_RESERVE: 2, EN_ATTENTE: 7, REFUSEE: 2, ANNULEE: 1 },
      a_inscrire: 6, inscrits: 2,
    }))
    setupRoutes()
  }

  it('filtre par l’année courante par défaut et recherche via le paramètre q', async () => {
    setupRiche()
    mount()
    await screen.findByText('Awa Koné')
    // Année courante du mock (id 1) appliquée dès le premier chargement.
    expect(listCalls().at(-1)).toMatchObject({ annee_academique_id: '1' })
    fireEvent.change(screen.getByRole('searchbox', { name: 'Rechercher une admission' }),
      { target: { value: 'Koné' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ q: 'Koné' })
  })

  it('affiche le matricule des inscrits sans bouton Inscrire, et l’échéance dépassée', async () => {
    setupRiche()
    mount()
    await screen.findByText('Inscrite Inès Yao')
    const ligneInscrite = rowOf('C-007')
    expect(within(ligneInscrite).getByRole('button', { name: /INJS26-0007/ })).toBeInTheDocument()
    expect(within(ligneInscrite).queryByRole('button', { name: 'Inscrire' })).toBeNull()
    const ligneExpiree = rowOf('C-006')
    expect(within(ligneExpiree).getByText('15/01/2020')).toBeInTheDocument()
    expect(within(ligneExpiree).getByText(/dépassée/i)).toBeInTheDocument()
    expect(within(ligneExpiree).getByText(/par admin/)).toBeInTheDocument()
  })

  it('indicateurs alimentés par les stats (année) : 5 cartes dont Inscrits', async () => {
    setupRiche()
    mount()
    await screen.findByText('Awa Koné')
    expect(await screen.findByText('dossiers étudiants créés')).toBeInTheDocument()
    expect(screen.getByText(/% des décisions/)).toBeInTheDocument()
    const statsCalls = apiMock.get.mock.calls
      .filter(([p]) => p === '/admissions/admissions/stats/')
    expect(statsCalls.length).toBeGreaterThan(0)
    expect(statsCalls.at(-1)[1]?.params).toMatchObject({ annee_academique_id: '1' })
  })
})
