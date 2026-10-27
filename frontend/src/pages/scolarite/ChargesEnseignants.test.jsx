/**
 * LOT 33 — Scolarité : charges pédagogiques des enseignants
 * (`pages/scolarite/ChargesEnseignants.jsx`).
 * Année académique courante résolue au montage (§10.8), occupation et
 * anomalies chargées en parallèle, détail d'un enseignant (charge +
 * affectations), création d'affectation pédagogique typée, référentiels et
 * carte de création réservés aux rôles `canActScolarite`.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
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
import ChargesEnseignants from '@/pages/scolarite/ChargesEnseignants'

const ANNEE_PATH = '/scolarite/annee-courante/'
const OCCUPATION_PATH = '/enseignants/occupation/'
const ANOMALIES_PATH = '/enseignants/anomalies/'
const AFFECTATIONS_PATH = '/enseignants/affectations/'
const ANNEES_REF_PATH = '/scolarite/ref/annees/'
const FORMATIONS_REF_PATH = '/scolarite/ref/formations/'
const NIVEAUX_REF_PATH = '/scolarite/ref/niveaux/'
const SEMESTRES_REF_PATH = '/scolarite/ref/semestres/'
const FORMATEURS_PATH = '/formateurs/list/'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

const anneeCourante = { id: 9, libelle: '2025-2026' }

const occupation = [
  { enseignant_id: 4, enseignant: 'Jean Dupont', prevue: 100, affectee: 80, planifiee: 60, realisee: 50, surcharge: false },
  { enseignant_id: 5, enseignant: 'Awa Koné', prevue: 50, affectee: 70, planifiee: 70, realisee: 60, surcharge: true },
]

const referentiels = {
  annees: [{ id: 9, libelle: '2025-2026' }],
  formations: [{ id: 1, intitule: 'L1 LSF' }],
  niveaux: [{ id: 2, code: 'N1' }, { id: 5, code: 'N2' }],
  semestres: [
    { id: 3, libelle: 'S1 N1', niveau_id: 2 },
    { id: 4, libelle: 'S2 N1', niveau_id: 2 },
    { id: 7, libelle: 'S1 N2', niveau_id: 5 },
  ],
  formateurs: [
    { id: 4, nom: 'Dupont', prenom: 'Jean' },
    { id: 5, nom: 'Koné', prenom: 'Awa' },
  ],
}

const charge4 = { enseignant: 'Jean Dupont', prevue: 100, affectee: 80, planifiee: 60, realisee: 50 }
const affectations4 = [
  { id: 100, ecue: 'ECUE Alpha', type_enseignement: 'CM', volume_horaire: 12, statut: 'PLANIFIEE' },
  { id: 101, ecue: null, type_enseignement: 'TD', volume_horaire: 8, statut: 'PREVISIONNELLE' },
]
const charge5 = { enseignant: 'Awa Koné', prevue: 50, affectee: 70, planifiee: 70, realisee: 60 }
const affectations5 = [
  { id: 200, ecue: 'ECUE Beta', type_enseignement: 'TP', volume_horaire: 10, statut: 'REALISEE' },
]

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }

afterEach(async () => { await settle() })

const mount = (role = 'ADMIN', {
  annee = anneeCourante,
  occupation: occ = occupation,
  anomalies = [],
  charge4Fn = () => charge4,
  charge5Fn = () => charge5,
  affectationsFn = () => {
    // Les params sont le second argument de api.get (pas dans le chemin).
    const appels = apiMock.get.mock.calls.filter(([p]) => p.split('?')[0] === AFFECTATIONS_PATH)
    const params = appels.length ? appels[appels.length - 1][1]?.params : {}
    return Number(params.enseignant_id) === 4 ? affectations4 : affectations5
  },
} = {}) => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  apiController.setRoute(ANNEE_PATH, typeof annee === 'function' ? annee : () => annee)
  apiController.setRoute(OCCUPATION_PATH, () => ({ occupation: occ }))
  apiController.setRoute(ANOMALIES_PATH, () => ({ anomalies }))
  // Le détail d'un enseignant reste consultatif pour tous les rôles.
  apiController.setRoute('/enseignants/charges/4/', charge4Fn)
  apiController.setRoute('/enseignants/charges/5/', charge5Fn)
  apiController.setRoute(AFFECTATIONS_PATH, affectationsFn)
  if (role !== 'DIRECTION' && role !== 'ENCADRANT' && role !== 'FINANCE') {
    apiController.setRoute(ANNEES_REF_PATH, () => referentiels.annees)
    apiController.setRoute(FORMATIONS_REF_PATH, () => referentiels.formations)
    apiController.setRoute(NIVEAUX_REF_PATH, () => referentiels.niveaux)
    apiController.setRoute(SEMESTRES_REF_PATH, () => referentiels.semestres)
    apiController.setRoute(FORMATEURS_PATH, () => referentiels.formateurs)
  }
  return renderWithProviders(<ChargesEnseignants />, {
    authUser: me,
    routePattern: '/scolarite/charges',
    initialEntries: ['/scolarite/charges'],
  })
}

// Implémentation par défaut du mock (les restoreMocks entre tests peuvent
// rendre getMockImplementation() indisponible à l'intérieur d'un test).
const getInitialImpl = apiMock.get.getMockImplementation()

const getCalls = (method, path) =>
  apiMock[method].mock.calls.filter(([p]) => p.split('?')[0] === path)
const postsTo = (path) =>
  apiMock.post.mock.calls.filter(([p]) => p.split('?')[0] === path)

const rowFor = (nom) => screen.getByText(nom).closest('tr')
const creationCard = () => screen.getByText('Nouvelle affectation pédagogique').closest('.card')

/* ------------------------------------------------------------------ */
/* LOT 33 — chargement, année courante, occupation et anomalies         */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/ChargesEnseignants.jsx — chargement et occupation (LOT 33)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche le spinner puis le titre avec le libellé de l’année courante', async () => {
    const { container } = mount()
    expect(container.querySelector('.spinner-border')).toBeTruthy()
    await settle()
    expect(await screen.findByRole('heading', { name: /charges pédagogiques des enseignants/i })).toBeInTheDocument()
    expect(screen.getByText(/Occupation par enseignant — 2025-2026/)).toBeInTheDocument()
  })

  it('résout l’année courante au montage puis charge occupation et anomalies avec son id', async () => {
    mount()
    await settle()
    expect(getCalls('get', ANNEE_PATH).length).toBeGreaterThan(0)
    const occCalls = getCalls('get', OCCUPATION_PATH)
    const anoCalls = getCalls('get', ANOMALIES_PATH)
    expect(occCalls.length).toBeGreaterThan(0)
    expect(anoCalls.length).toBeGreaterThan(0)
    expect(occCalls[0][1].params).toEqual({ annee_id: 9 })
    expect(anoCalls[0][1].params).toEqual({ annee_id: 9 })
  })

  it('rend le tableau d’occupation : en-têtes, valeurs et badges OK/Surcharge', async () => {
    mount()
    await settle()
    for (const enTete of ['Enseignant', 'Prévue (h)', 'Affectée (h)', 'Planifiée (h)', 'Réalisée (h)', 'Charge']) {
      expect(screen.getByText(enTete)).toBeInTheDocument()
    }
    const ligne4 = rowFor('Jean Dupont')
    expect(ligne4.textContent).toContain('100')
    expect(within(ligne4).getByText('OK')).toHaveClass('text-bg-success')
    const ligne5 = rowFor('Awa Koné')
    expect(within(ligne5).getByText('Surcharge')).toHaveClass('text-bg-danger')
  })

  it("signale une table vide (aucune affectation)", async () => {
    mount('ADMIN', { occupation: [] })
    await settle()
    expect(screen.getByText('Aucune affectation.')).toBeInTheDocument()
  })

  it("n'affiche aucune alerte sans anomalie", async () => {
    mount()
    await settle()
    expect(document.querySelector('.alert-warning')).toBeNull()
  })

  it('affiche les anomalies (compteur, détails, limite de 8 lignes)', async () => {
    const anomalies = Array.from({ length: 10 }, (_, i) => ({ detail: `Anomalie ${i + 1}` }))
    mount('ADMIN', { anomalies })
    await settle()
    const alerte = document.querySelector('.alert-warning')
    expect(alerte.textContent).toContain('10 anomalie(s) détectée(s)')
    expect(within(alerte).getAllByRole('listitem')).toHaveLength(8)
    expect(within(alerte).getByText('Anomalie 1')).toBeInTheDocument()
    expect(within(alerte).getByText('Anomalie 8')).toBeInTheDocument()
    expect(within(alerte).queryByText('Anomalie 9')).toBeNull()
  })

  it("notifie l'absence d'année courante et ne charge ni occupation ni anomalies", async () => {
    const { container } = mount('ADMIN', { annee: () => { throw { response: { status: 404 } } } })
    await settle()
    expect(await screen.findByText('Aucune année académique courante.')).toBeInTheDocument()
    expect(getCalls('get', OCCUPATION_PATH)).toHaveLength(0)
    expect(getCalls('get', ANOMALIES_PATH)).toHaveLength(0)
    // Sans année, l'écran reste en attente (spinner).
    expect(container.querySelector('.spinner-border')).toBeTruthy()
  })

  it("notifie l'échec du chargement de l'occupation et affiche quand même la page", async () => {
    apiController.setRoute(OCCUPATION_PATH, () => { throw new Error('500') })
    mount()
    expect(await screen.findByText('Chargement des charges impossible.')).toBeInTheDocument()
    // Le `finally` lève le chargement : la page et son état vide sont rendus.
    expect(await screen.findByText('Aucune affectation.')).toBeInTheDocument()
  })

  it("notifie l'échec du chargement des anomalies (Promise.all en échec)", async () => {
    apiController.setRoute(ANOMALIES_PATH, () => { throw new Error('500') })
    mount()
    expect(await screen.findByText('Chargement des charges impossible.')).toBeInTheDocument()
  })

  it("supporte des réponses dépourvues des clés occupation/anomalies (repli [])", async () => {
    apiController.setRoute(OCCUPATION_PATH, () => ({}))
    apiController.setRoute(ANOMALIES_PATH, () => ({}))
    mount()
    await settle()
    expect(screen.getByText('Aucune affectation.')).toBeInTheDocument()
    expect(document.querySelector('.alert-warning')).toBeNull()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 33 — détail d'un enseignant                                      */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/ChargesEnseignants.jsx — détail enseignant (LOT 33)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it("charge la charge et les affectations d'un enseignant au clic sur sa ligne", async () => {
    mount()
    await settle()
    expect(screen.queryByText(/^Détail —/)).toBeNull()

    fireEvent.click(rowFor('Jean Dupont'))
    await waitFor(() => expect(getCalls('get', '/enseignants/charges/4/').length).toBeGreaterThan(0))
    expect(getCalls('get', '/enseignants/charges/4/')[0][1].params).toEqual({ annee_id: 9 })
    const affCalls = getCalls('get', AFFECTATIONS_PATH)
    expect(affCalls.at(-1)[1].params).toEqual({ enseignant_id: 4, annee_academique_id: 9 })
    await settle()

    const carte = screen.getByText(/^Détail — Jean Dupont/).closest('.card')
    expect(carte.textContent).toContain('Prévue : 100 h')
    expect(carte.textContent).toContain('Affectée : 80 h')
    expect(carte.textContent).toContain('Planifiée : 60 h')
    expect(carte.textContent).toContain('Réalisée : 50 h')
    // ECUE absente → tiret ; les autres colonnes sont restituées.
    const lignes = within(carte).getAllByRole('row').slice(1)
    expect(lignes).toHaveLength(2)
    expect(lignes[0].textContent).toContain('ECUE Alpha')
    expect(lignes[0].textContent).toContain('CM')
    expect(lignes[0].textContent).toContain('12')
    expect(lignes[1].textContent).toContain('—')
    expect(lignes[1].textContent).toContain('TD')
    // La ligne cliquée est mise en évidence.
    expect(rowFor('Jean Dupont')).toHaveClass('table-active')
  })

  it("change de détail au clic sur un autre enseignant", async () => {
    mount()
    await settle()
    fireEvent.click(rowFor('Awa Koné'))
    await settle()
    expect(screen.getByText(/^Détail — Awa Koné/)).toBeInTheDocument()
    expect(screen.queryByText(/^Détail — Jean Dupont/)).toBeNull()
    const carte = screen.getByText(/^Détail — Awa Koné/).closest('.card')
    expect(within(carte).getByText('ECUE Beta')).toBeInTheDocument()
    expect(rowFor('Awa Koné')).toHaveClass('table-active')
    expect(rowFor('Jean Dupont')).not.toHaveClass('table-active')
  })

  it("notifie l'échec du chargement de la charge sans afficher de carte", async () => {
    mount('ADMIN', { charge4Fn: () => { throw new Error('500') } })
    await settle()
    fireEvent.click(rowFor('Jean Dupont'))
    expect(await screen.findByText('Chargement de la charge impossible.')).toBeInTheDocument()
    expect(screen.queryByText(/^Détail —/)).toBeNull()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 33 — référentiels et habilitations                               */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/ChargesEnseignants.jsx — référentiels et habilitations (LOT 33)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('charge les cinq référentiels pour un rôle acteur et alimente les sélecteurs', async () => {
    mount('SECRETARIAT')
    await settle()
    expect(getCalls('get', ANNEES_REF_PATH)[0][1].params).toEqual({ actif: 'true' })
    expect(getCalls('get', FORMATIONS_REF_PATH).length).toBeGreaterThan(0)
    expect(getCalls('get', NIVEAUX_REF_PATH)[0][1].params).toEqual({ actif: 'true' })
    expect(getCalls('get', SEMESTRES_REF_PATH).length).toBeGreaterThan(0)
    expect(getCalls('get', FORMATEURS_PATH).length).toBeGreaterThan(0)

    const carte = creationCard()
    const combos = within(carte).getAllByRole('combobox')
    expect(within(combos[0]).getByRole('option', { name: 'Dupont Jean' })).toBeInTheDocument()
    expect(within(combos[1]).getByRole('option', { name: 'L1 LSF' })).toBeInTheDocument()
    expect(within(combos[2]).getByRole('option', { name: 'N1' })).toBeInTheDocument()
  })

  it('filtre les semestres selon le niveau choisi', async () => {
    mount()
    await settle()
    const combos = within(creationCard()).getAllByRole('combobox')
    // Avant choix du niveau : aucun semestre proposé (filtre Number('') = NaN).
    expect(within(combos[3]).queryAllByRole('option')).toHaveLength(1)
    fireEvent.change(combos[2], { target: { value: '2' } }) // N1
    const optionsN1 = within(combos[3]).getAllByRole('option').map((o) => o.textContent)
    expect(optionsN1).toEqual(expect.arrayContaining(['Semestre…', 'S1 N1', 'S2 N1']))
    expect(optionsN1).not.toContain('S1 N2')
    fireEvent.change(combos[2], { target: { value: '5' } }) // N2
    const optionsN2 = within(combos[3]).getAllByRole('option').map((o) => o.textContent)
    expect(optionsN2).toContain('S1 N2')
    expect(optionsN2).not.toContain('S1 N1')
  })

  it('masque la carte de création et ne charge aucun référentiel pour un rôle non acteur', async () => {
    mount('ENCADRANT')
    await settle()
    // La consultation de l’occupation reste disponible.
    expect(screen.getByText('Jean Dupont')).toBeInTheDocument()
    expect(screen.queryByText('Nouvelle affectation pédagogique')).toBeNull()
    expect(getCalls('get', FORMATEURS_PATH)).toHaveLength(0)
    expect(getCalls('get', FORMATIONS_REF_PATH)).toHaveLength(0)
    expect(getCalls('get', SEMESTRES_REF_PATH)).toHaveLength(0)
    // Le détail d'un enseignant reste consultable en lecture.
    fireEvent.click(rowFor('Jean Dupont'))
    await settle()
    expect(screen.getByText(/^Détail — Jean Dupont/)).toBeInTheDocument()
    expect(screen.getByText('ECUE Alpha')).toBeInTheDocument()
  })

  // Régression §10.13 (LOT 34) : l'état initial `options` déclare désormais
  // toutes les clés (`formateurs`, `annees` comprises). Un échec du
  // chargement des référentiels affiche le toast MAIS la page reste stable
  // avec des sélecteurs vides, au lieu de crasher sur `.map()`.
  it('§10.13 (LOT 34) un échec des référentiels affiche le toast sans crasher, sélecteurs vides', async () => {
    apiController.setRoute(FORMATEURS_PATH, () => { throw new Error('500') })
    mount()
    expect(await screen.findByText('Chargement des référentiels impossible.')).toBeInTheDocument()
    // L'écran (occupation) reste rendu.
    expect(await screen.findByRole('heading', { name: /charges pédagogiques des enseignants/i })).toBeInTheDocument()
    expect(screen.getByText('Jean Dupont')).toBeInTheDocument()
    // La carte de création est là, avec les seules options fantômes.
    const combos = within(creationCard()).getAllByRole('combobox')
    expect(within(combos[0]).queryAllByRole('option')).toHaveLength(1)
    expect(within(combos[1]).queryAllByRole('option')).toHaveLength(1)
    expect(screen.queryByTestId('render-crash')).toBeNull()
  })

  it('§10.13 (LOT 34) des référentiels lents (occupation servie avant eux) ne font pas crasher la page', async () => {
    // Le GET des formateurs ne répond jamais ; l’occupation, elle, se résout
    // tout de suite → la carte s’affiche alors que les référentiels sont
    // encore en vol : elle doit rester stable avec des sélecteurs vides.
    apiMock.get.mockImplementation((chemin, ...reste) => (
      chemin === FORMATEURS_PATH ? new Promise(() => {}) : getInitialImpl(chemin, ...reste)
    ))
    mount()
    expect(await screen.findByRole('heading', { name: /charges pédagogiques des enseignants/i })).toBeInTheDocument()
    expect(screen.getByText('Jean Dupont')).toBeInTheDocument()
    const combos = within(creationCard()).getAllByRole('combobox')
    expect(within(combos[0]).queryAllByRole('option')).toHaveLength(1)
    expect(screen.queryByTestId('render-crash')).toBeNull()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 33 — création d'affectation                                      */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/ChargesEnseignants.jsx — création d’affectation (LOT 33)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const remplirFormulaire = (carte) => {
    const combos = within(carte).getAllByRole('combobox')
    fireEvent.change(combos[0], { target: { value: '4' } }) // enseignant
    fireEvent.change(combos[1], { target: { value: '1' } }) // formation
    fireEvent.change(combos[2], { target: { value: '2' } }) // niveau N1
    fireEvent.change(combos[3], { target: { value: '3' } }) // S1 N1
    fireEvent.change(within(carte).getByPlaceholderText('Volume (h)'), { target: { value: '12' } })
  }

  it('affiche le libellé de l’année sur le bouton de création', async () => {
    mount()
    await settle()
    expect(within(creationCard()).getByRole('button', { name: /Créer l'affectation \(2025-2026\)/ })).toBeInTheDocument()
  })

  it('crée l’affectation avec le payload complet et typé, recharge tout et réinitialise partiellement', async () => {
    mount()
    await settle()
    const carte = creationCard()
    // Un enseignant est d'abord sélectionné : sa charge devra aussi être rechargée.
    fireEvent.click(rowFor('Jean Dupont'))
    await settle()
    const occAvant = getCalls('get', OCCUPATION_PATH).length
    const chargeAvant = getCalls('get', '/enseignants/charges/4/').length
    const affAvant = getCalls('get', AFFECTATIONS_PATH).length

    remplirFormulaire(carte)
    fireEvent.click(within(carte).getByRole('button', { name: /créer l'affectation/i }))

    await waitFor(() => expect(postsTo(AFFECTATIONS_PATH)).toHaveLength(1))
    expect(postsTo(AFFECTATIONS_PATH)[0][1]).toEqual({
      ref_formation_id: 1,
      niveau_id: 2,
      semestre_id: 3,
      ecue_id: '',
      groupe_id: '',
      enseignant_id: 4,
      type_enseignement: 'CM',
      volume_horaire: 12,
      annee_academique_id: 9,
    })
    expect(await screen.findByText('Affectation créée.')).toBeInTheDocument()
    await settle()

    // Réinitialisation partielle : enseignant et volume vidés (la carte est
    // remontée après le passage par le spinner du rechargement : on la
    // ré-acquiert plutôt que de lire des nœuds détachés).
    const carteRechargee = screen.getByText('Nouvelle affectation pédagogique').closest('.card')
    const combos = within(carteRechargee).getAllByRole('combobox')
    expect(combos[0].value).toBe('')
    expect(within(carteRechargee).getByPlaceholderText('Volume (h)').value).toBe('')
    // …mais la formation, le niveau et le semestre sont conservés.
    expect(combos[1].value).toBe('1')
    expect(combos[2].value).toBe('2')
    expect(combos[3].value).toBe('3')

    // Rechargement global (occupation + anomalies) et du détail sélectionné.
    expect(getCalls('get', OCCUPATION_PATH).length).toBeGreaterThan(occAvant)
    expect(getCalls('get', '/enseignants/charges/4/').length).toBeGreaterThan(chargeAvant)
    expect(getCalls('get', AFFECTATIONS_PATH).length).toBeGreaterThan(affAvant)
  })

  it("passe les identifiants non choisis en undefined et un volume invalide à 0", async () => {
    mount()
    await settle()
    const carte = creationCard()
    const volume = within(carte).getByPlaceholderText('Volume (h)')
    fireEvent.change(volume, { target: { value: 'abc' } })
    // Soumission directe pour contourner la validation native (required/number).
    fireEvent.submit(carte.querySelector('form'))
    await waitFor(() => expect(postsTo(AFFECTATIONS_PATH)).toHaveLength(1))
    const body = postsTo(AFFECTATIONS_PATH)[0][1]
    expect(body.ref_formation_id).toBeUndefined()
    expect(body.niveau_id).toBeUndefined()
    expect(body.semestre_id).toBeUndefined()
    expect(body.enseignant_id).toBeUndefined()
    expect(body.volume_horaire).toBe(0)
    expect(body.annee_academique_id).toBe(9)
    expect(body.type_enseignement).toBe('CM')
  })

  it("désactive le bouton pendant l'envoi puis le réactive", async () => {
    mount()
    await settle()
    const carte = creationCard()
    remplirFormulaire(carte)
    let resolvePost
    apiMock.post.mockImplementationOnce(() => new Promise((res) => { resolvePost = () => res({ data: {} }) }))
    const bouton = within(carte).getByRole('button', { name: /créer l'affectation/i })
    fireEvent.click(bouton)
    expect(bouton).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(8) })
    expect(await screen.findByText('Affectation créée.')).toBeInTheDocument()
    expect(within(carte).getByRole('button', { name: /créer l'affectation/i })).not.toBeDisabled()
    await settle()
  })

  it("notifie le détail JSON d'une erreur de création puis le message générique", async () => {
    mount()
    await settle()
    const carte = creationCard()
    remplirFormulaire(carte)

    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Conflit de service' } } })
    fireEvent.click(within(carte).getByRole('button', { name: /créer l'affectation/i }))
    expect(await screen.findByText(/Conflit de service/)).toBeInTheDocument()

    remplirFormulaire(carte)
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(carte).getByRole('button', { name: /créer l'affectation/i }))
    expect(await screen.findByText('Création impossible.')).toBeInTheDocument()
  })
})
