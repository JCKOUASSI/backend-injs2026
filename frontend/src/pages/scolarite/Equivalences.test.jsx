/**
 * LOT 31 — Scolarité : équivalences et dispenses
 * (`pages/scolarite/Equivalences.jsx`).
 * Cycle de vie d'une demande (brouillon → soumission → instruction → avis →
 * décision → validée → appliquée), création avec référentiels chargés en
 * parallèle, décision pédagogique, application sous confirmation et
 * habilitations Scolarité.
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
import Equivalences from '@/pages/scolarite/Equivalences'

const DEMANDES_PATH = '/equivalences/demandes/'
const ANNEES_PATH = '/scolarite/ref/annees/'
const FORMATIONS_PATH = '/scolarite/ref/formations/'
const NIVEAUX_PATH = '/scolarite/ref/niveaux/'
const ETUDIANTS_PATH = '/scolarite/etudiants/'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

// Une demande par étape du workflow, plus les statuts terminaux et un
// statut inconnu (repli de badge) sans crédits (tiret).
const demandes = [
  { id: 1, type_demande: 'DISPENSE', matricule: 'A001', ref_formation: 'L1 LSF', decision: '', statut: 'BROUILLON', credits_reconnus: null },
  { id: 2, type_demande: 'EQUIVALENCE', matricule: 'A002', ref_formation: 'M2 Interprétation', decision: '', statut: 'SOUMISE', credits_reconnus: null },
  { id: 3, type_demande: 'DISPENSE', matricule: 'A003', ref_formation: 'L2 LFM', decision: '', statut: 'EN_INSTRUCTION', credits_reconnus: null },
  { id: 4, type_demande: 'EQUIVALENCE', matricule: 'A004', ref_formation: 'L1 LSF', decision: '', statut: 'AVIS_PEDAGOGIQUE', credits_reconnus: null },
  { id: 5, type_demande: 'DISPENSE', matricule: 'A005', ref_formation: 'L3 LSF', decision: '', statut: 'DECISION', credits_reconnus: null },
  { id: 6, type_demande: 'EQUIVALENCE', matricule: 'A006', ref_formation: 'M1 Interprétation', decision: 'FAVORABLE', statut: 'VALIDEE', credits_reconnus: 12 },
  { id: 7, type_demande: 'DISPENSE', matricule: 'A007', ref_formation: 'L1 LSF', decision: 'DEFAVORABLE', statut: 'REJETEE', credits_reconnus: 0 },
  { id: 8, type_demande: 'EQUIVALENCE', matricule: 'A008', ref_formation: 'L2 LFM', decision: 'FAVORABLE', statut: 'APPLIQUEE', credits_reconnus: 6 },
  { id: 9, type_demande: 'DISPENSE', matricule: 'A009', ref_formation: 'Autre', decision: '', statut: 'STATUT_MYSTERE', credits_reconnus: null },
]

const referentiels = {
  annees: [{ id: 2, libelle: '2025-2026' }, { id: 3, libelle: '2026-2027' }],
  formations: [{ id: 3, intitule: 'Licence LSF' }, { id: 4, intitule: 'Master Interprétation' }],
  niveaux: [{ id: 4, code: 'L1' }, { id: 5, code: 'M2' }],
  etudiants: [
    { id: 1, matricule: 'A001', nom_complet: 'Jean Dupont' },
    { id: 2, matricule: 'A002', nom_complet: 'Awa Koné' },
  ],
}

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }

// Purge le rechargement déclenché après chaque écriture (setChargement puis
// GET) pour ne pas laisser de mise à jour d'état inter-tests (warning act).
afterEach(async () => { await settle() })

const mount = (role = 'ADMIN', demandesFn = () => demandes) => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  apiController.setRoute(DEMANDES_PATH, demandesFn)
  if (canAct(role)) {
    apiController.setRoute(ANNEES_PATH, () => referentiels.annees)
    apiController.setRoute(FORMATIONS_PATH, () => referentiels.formations)
    apiController.setRoute(NIVEAUX_PATH, () => referentiels.niveaux)
    apiController.setRoute(ETUDIANTS_PATH, () => referentiels.etudiants)
  }
  return renderWithProviders(<Equivalences />, {
    authUser: me,
    routePattern: '/scolarite/equivalences',
    initialEntries: ['/scolarite/equivalences'],
  })
}

const ROLES_ACTEURS = ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT', 'SECRETARIAT']
const canAct = (role) => ROLES_ACTEURS.includes(role)

const getCalls = (path) =>
  apiMock.get.mock.calls.filter(([p]) => p.split('?')[0] === path)
const postsTo = (fragment) =>
  apiMock.post.mock.calls.filter(([p]) => p.includes(fragment))

const rowFor = (matricule) => screen.getByText(matricule).closest('tr')

// Les selects n'ont pas de <label> : on les retrouve par leur option fantôme.
const selectByPlaceholder = (optionText) => {
  const opt = [...document.querySelectorAll('select option')].find((o) => o.textContent === optionText)
  return opt.closest('select')
}
const creationCard = () => screen.getByText('Nouvelle demande').closest('.card')
const actionButtons = (matricule) =>
  [...rowFor(matricule).querySelectorAll('button')].map((b) => b.textContent.trim())

/* ------------------------------------------------------------------ */
/* LOT 31 — chargement, liste, référentiels et habilitations          */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Equivalences.jsx — chargement et liste (LOT 31)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche le spinner puis le tableau et charge les référentiels en parallèle', async () => {
    const { container } = mount()
    expect(container.querySelector('.spinner-border')).toBeTruthy()
    await settle()

    expect(apiMock.get).toHaveBeenCalledWith(DEMANDES_PATH)
    expect(screen.getByRole('heading', { name: /équivalences et dispenses/i })).toBeInTheDocument()

    // Les quatre référentiels sont demandés (années et niveaux en actif=true).
    expect(getCalls(ANNEES_PATH)[0][1]).toEqual({ params: { actif: 'true' } })
    expect(getCalls(NIVEAUX_PATH)[0][1]).toEqual({ params: { actif: 'true' } })
    expect(getCalls(FORMATIONS_PATH)).toHaveLength(1)
    expect(getCalls(ETUDIANTS_PATH)).toHaveLength(1)

    // Les options sont bien alimentées dans le formulaire de création.
    const carte = creationCard()
    expect(within(carte).getByRole('option', { name: /2026-2027/ })).toBeInTheDocument()
    expect(within(carte).getByRole('option', { name: /A001 — Jean Dupont/ })).toBeInTheDocument()
    expect(within(carte).getByRole('option', { name: 'M2' })).toBeInTheDocument()
  })

  it('affiche les en-têtes de colonnes (Actions comprise pour un rôle acteur)', async () => {
    mount()
    await settle()
    for (const col of ['Type', 'Matricule', 'Formation', 'Décision', 'Statut', 'Crédits', 'Actions']) {
      expect(screen.getByText(col, { selector: 'th' })).toBeInTheDocument()
    }
  })

  it('badge chaque statut selon la table et replie un statut inconnu en secondaire', async () => {
    mount()
    await settle()
    expect(within(rowFor('A001')).getByText('BROUILLON')).toHaveClass('text-bg-secondary')
    expect(within(rowFor('A002')).getByText('SOUMISE')).toHaveClass('text-bg-info')
    expect(within(rowFor('A005')).getByText('DECISION')).toHaveClass('text-bg-primary')
    expect(within(rowFor('A006')).getByText('VALIDEE')).toHaveClass('text-bg-success')
    expect(within(rowFor('A007')).getByText('REJETEE')).toHaveClass('text-bg-danger')
    expect(within(rowFor('A008')).getByText('APPLIQUEE')).toHaveClass('text-bg-dark')
    expect(within(rowFor('A009')).getByText('STATUT_MYSTERE')).toHaveClass('text-bg-secondary')
  })

  it('affiche les crédits reconnus ou un tiret, et la décision portée', async () => {
    mount()
    await settle()
    expect(rowFor('A006')).toHaveTextContent('12')
    expect(rowFor('A006')).toHaveTextContent('FAVORABLE')
    expect(rowFor('A007')).toHaveTextContent('0')
    expect(rowFor('A007')).toHaveTextContent('DEFAVORABLE')
    // Crédits null -> tiret.
    expect(rowFor('A001')).toHaveTextContent('—')
  })

  it("affiche « Aucune demande. » quand la liste est vide", async () => {
    mount('ADMIN', () => [])
    await settle()
    expect(screen.getByText('Aucune demande.')).toBeInTheDocument()
    expect(document.querySelectorAll('tbody tr')).toHaveLength(1) // la ligne du message
  })

  it("notifie le détail serveur puis le message générique d'un échec de chargement", async () => {
    mount('ADMIN', () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Module scolarité fermé' } } }
    })
    expect(await screen.findByText('Module scolarité fermé')).toBeInTheDocument()
  })

  it("notifie le message générique quand l'erreur de chargement n'a pas de détail", async () => {
    mount('ADMIN', () => { throw new Error('réseau') })
    expect(await screen.findByText('Chargement impossible.')).toBeInTheDocument()
  })

  it("en lecture seule (DIRECTION) : pas de création, pas d'actions, pas de référentiels chargés", async () => {
    mount('DIRECTION')
    await settle()
    // La liste reste lisible.
    expect(rowFor('A001')).toBeInTheDocument()
    expect(screen.queryByText('Nouvelle demande')).toBeNull()
    expect(screen.queryByText('Actions', { selector: 'th' })).toBeNull()
    expect(document.querySelector('form')).toBeNull()
    // Aucun référentiel n'est demandé pour un rôle qui ne peut pas agir.
    expect(getCalls(ANNEES_PATH)).toHaveLength(0)
    expect(getCalls(ETUDIANTS_PATH)).toHaveLength(0)
  })

  it("notifie l'échec du chargement des référentiels (la liste reste affichée)", async () => {
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(DEMANDES_PATH, () => demandes)
    apiController.setRoute(ANNEES_PATH, () => { throw new Error('500') })
    renderWithProviders(<Equivalences />, {
      authUser: me, routePattern: '/scolarite/equivalences', initialEntries: ['/scolarite/equivalences'],
    })
    expect(await screen.findByText('Chargement des référentiels impossible.')).toBeInTheDocument()
    // La liste des demandes, elle, a bien été chargée.
    expect(rowFor('A001')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 31 — création d'une demande                                      */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Equivalences.jsx — création (LOT 31)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const remplirFormulaire = () => {
    // Type : Équivalence.
    const typeSelect = creationCard().querySelectorAll('select')[0]
    fireEvent.change(typeSelect, { target: { value: 'EQUIVALENCE' } })
    fireEvent.change(selectByPlaceholder('Étudiant…'), { target: { value: '1' } })
    fireEvent.change(selectByPlaceholder('Année…'), { target: { value: '2' } })
    fireEvent.change(selectByPlaceholder('Formation…'), { target: { value: '3' } })
    fireEvent.change(selectByPlaceholder('Niveau…'), { target: { value: '4' } })
  }

  it('crée une demande en brouillon avec le payload complet et recharge', async () => {
    mount()
    await settle()
    remplirFormulaire()
    fireEvent.click(screen.getByRole('button', { name: '+' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(1))
    const [path, body] = apiMock.post.mock.calls[0]
    expect(path).toBe(DEMANDES_PATH)
    expect(body).toEqual({
      type_demande: 'EQUIVALENCE',
      etudiant_id: 1,
      annee_academique_id: 2,
      ref_formation_id: 3,
      niveau_id: 4,
      etablissement_origine: '',
      diplome_origine: '',
    })
    expect(await screen.findByText('Demande créée en brouillon.')).toBeInTheDocument()
    // Rechargement de la liste après création.
    await settle()
    expect(getCalls(DEMANDES_PATH).length).toBeGreaterThanOrEqual(2)
  })

  it("passe les identifiants non choisis en undefined (soumission sans sélection)", async () => {
    mount()
    await settle()
    // On contourne la validation native « required » pour exercer le
    // `Number(...) || undefined` de la page.
    fireEvent.submit(creationCard().querySelector('form'))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(1))
    const body = apiMock.post.mock.calls[0][1]
    expect(body.etudiant_id).toBeUndefined()
    expect(body.annee_academique_id).toBeUndefined()
    expect(body.ref_formation_id).toBeUndefined()
    expect(body.niveau_id).toBeUndefined()
    expect(body.type_demande).toBe('DISPENSE') // valeur par défaut
  })

  it("désactive le bouton + pendant l'envoi", async () => {
    mount()
    await settle()
    let resolvePost
    apiMock.post.mockImplementationOnce(() => new Promise((res) => { resolvePost = () => res({ data: {} }) }))
    remplirFormulaire()
    fireEvent.click(screen.getByRole('button', { name: '+' }))
    expect(screen.getByRole('button', { name: '+' })).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(6) })
    expect(await screen.findByText('Demande créée en brouillon.')).toBeInTheDocument()
    await settle()
  })

  it("notifie le détail JSON d'une erreur de création puis le message générique", async () => {
    mount()
    await settle()
    remplirFormulaire()
    apiMock.post.mockRejectedValueOnce({ response: { data: { non_field_errors: ['Doublon'] } } })
    fireEvent.click(screen.getByRole('button', { name: '+' }))
    expect(await screen.findByText(/Doublon/)).toBeInTheDocument()

    // Second essai sans réponse structurée : message générique.
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: '+' }))
    expect(await screen.findByText('Création impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 31 — workflow de transitions                                     */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Equivalences.jsx — transitions de statut (LOT 31)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('soumet un brouillon (POST transition, message, rechargement)', async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('A001')).getByRole('button', { name: 'Soumettre' }))
    await waitFor(() => expect(postsTo('/1/transition/')).toHaveLength(1))
    expect(postsTo('/1/transition/')[0][1]).toEqual({ statut: 'SOUMISE' })
    expect(await screen.findByText('Demande soumise.')).toBeInTheDocument()
    expect(getCalls(DEMANDES_PATH).length).toBeGreaterThanOrEqual(2)
  })

  it('instruit une demande soumise puis produit un avis pédagogique', async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('A002')).getByRole('button', { name: 'Instruire' }))
    await waitFor(() => expect(postsTo('/2/transition/')).toHaveLength(1))
    expect(postsTo('/2/transition/')[0][1]).toEqual({ statut: 'EN_INSTRUCTION' })
    expect(await screen.findByText('Demande en_instruction.')).toBeInTheDocument()

    // Nouvelle liste : l'identifiant 3 est en instruction.
    fireEvent.click(within(rowFor('A003')).getByRole('button', { name: /avis pédagogique/i }))
    await waitFor(() => expect(postsTo('/3/transition/')).toHaveLength(1))
    expect(postsTo('/3/transition/')[0][1]).toEqual({ statut: 'AVIS_PEDAGOGIQUE' })
  })

  it("n'expose aucune action sur les statuts terminaux ou inconnus", async () => {
    mount()
    await settle()
    expect(actionButtons('A007')).toEqual([]) // REJETEE
    expect(actionButtons('A008')).toEqual([]) // APPLIQUEE
    expect(actionButtons('A009')).toEqual([]) // inconnu
    // La validée ne propose que « Appliquer ».
    expect(actionButtons('A006')).toEqual(['Appliquer'])
  })

  it('désactive les actions pendant une transition en cours', async () => {
    let resolvePost
    apiController.reset()
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(DEMANDES_PATH, () => demandes)
    apiMock.post.mockImplementationOnce((path) =>
      path.includes('/1/transition/')
        ? new Promise((res) => { resolvePost = () => res({ data: {} }) })
        : Promise.resolve({ data: {} }),
    )
    renderWithProviders(<Equivalences />, {
      authUser: me, routePattern: '/scolarite/equivalences', initialEntries: ['/scolarite/equivalences'],
    })
    await settle()
    fireEvent.click(within(rowFor('A001')).getByRole('button', { name: 'Soumettre' }))
    // Tous les boutons d'action sont désactivés pendant le traitement.
    expect(within(rowFor('A001')).getByRole('button', { name: 'Soumettre' })).toBeDisabled()
    expect(within(rowFor('A002')).getByRole('button', { name: 'Instruire' })).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(4) })
    expect(await screen.findByText('Demande soumise.')).toBeInTheDocument()
  })

  it("notifie le détail puis le générique d'une transition impossible", async () => {
    mount()
    await settle()
    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Étape non permise' } } })
    fireEvent.click(within(rowFor('A001')).getByRole('button', { name: 'Soumettre' }))
    expect(await screen.findByText('Étape non permise')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(rowFor('A001')).getByRole('button', { name: 'Soumettre' }))
    expect(await screen.findByText('Transition impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 31 — décision pédagogique                                        */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Equivalences.jsx — décision pédagogique (LOT 31)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const openDecision = async (matricule) => {
    mount()
    await settle()
    fireEvent.click(within(rowFor(matricule)).getByRole('button', { name: 'Décider' }))
    return screen.getByText(/^Décision — demande/).closest('.card')
  }

  it('ouvre le formulaire de décision depuis AVIS_PEDAGOGIQUE comme depuis DECISION', async () => {
    let carte = await openDecision('A004')
    expect(carte).toHaveTextContent('Décision — demande #4')
    fireEvent.click(within(carte).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(screen.queryByText(/^Décision — demande/)).toBeNull()
  })

  it('propose aussi Décider au statut DECISION (retour pour modification)', async () => {
    const carte = await openDecision('A005')
    expect(carte).toHaveTextContent('Décision — demande #5')
  })

  it('enregistre une décision défavorable avec les données saisies puis ferme', async () => {
    const carte = await openDecision('A004')
    fireEvent.change(carte.querySelector('select'), { target: { value: 'DEFAVORABLE' } })
    fireEvent.change(within(carte).getByPlaceholderText('Crédits reconnus'), { target: { value: '8' } })
    fireEvent.change(within(carte).getByPlaceholderText('Note transférée'), { target: { value: '14.5' } })
    fireEvent.change(within(carte).getByPlaceholderText('Autorité de validation'), { target: { value: 'Direction INJS' } })
    fireEvent.click(within(carte).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(postsTo('/4/decision/')).toHaveLength(1))
    expect(postsTo('/4/decision/')[0][1]).toEqual({
      decision: 'DEFAVORABLE',
      credits_reconnus: '8', // la page transmet la chaîne saisie
      note_transferee: '14.5',
      autorite_validation: 'Direction INJS',
      analyse_pedagogique: '',
    })
    expect(await screen.findByText('Décision enregistrée.')).toBeInTheDocument()
    // Le formulaire est refermé et la liste rechargée.
    expect(screen.queryByText(/^Décision — demande/)).toBeNull()
    expect(getCalls(DEMANDES_PATH).length).toBeGreaterThanOrEqual(2)
  })

  it('omet les crédits et la note laissés vides (undefined)', async () => {
    const carte = await openDecision('A004')
    fireEvent.click(within(carte).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/4/decision/')).toHaveLength(1))
    const body = postsTo('/4/decision/')[0][1]
    expect(body.credits_reconnus).toBeUndefined()
    expect(body.note_transferee).toBeUndefined()
    expect(body.decision).toBe('FAVORABLE') // défaut
    expect(body.autorite_validation).toBe('Direction des études INJS') // défaut
  })

  it("annule sans appel et garde la liste intacte", async () => {
    const carte = await openDecision('A004')
    fireEvent.click(within(carte).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(apiMock.post).not.toHaveBeenCalled()
    expect(screen.queryByText(/^Décision — demande/)).toBeNull()
  })

  it("notifie le détail puis le générique d'une décision impossible, formulaire conservé", async () => {
    const carte = await openDecision('A004')
    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Décision verrouillée' } } })
    fireEvent.click(within(carte).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Décision verrouillée')).toBeInTheDocument()
    expect(screen.getByText(/^Décision — demande/)).toBeInTheDocument()

    const carte2 = screen.getByText(/^Décision — demande/).closest('.card')
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(carte2).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Décision impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 31 — application d'une décision validée                          */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Equivalences.jsx — application (LOT 31)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it("n'appelle rien si la confirmation est refusée", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await settle()
    fireEvent.click(within(rowFor('A006')).getByRole('button', { name: 'Appliquer' }))
    await settle()
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/effet académique/i))
    expect(postsTo('/appliquer/')).toHaveLength(0)
  })

  it('applique après confirmation (POST vide, notification, rechargement)', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await settle()
    fireEvent.click(within(rowFor('A006')).getByRole('button', { name: 'Appliquer' }))
    await waitFor(() => expect(postsTo('/6/appliquer/')).toHaveLength(1))
    expect(postsTo('/6/appliquer/')[0][1]).toEqual({})
    expect(await screen.findByText('Dispense/équivalence appliquée.')).toBeInTheDocument()
    expect(getCalls(DEMANDES_PATH).length).toBeGreaterThanOrEqual(2)
  })

  it("notifie le détail puis le générique d'une application impossible", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await settle()
    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Année clôturée' } } })
    fireEvent.click(within(rowFor('A006')).getByRole('button', { name: 'Appliquer' }))
    expect(await screen.findByText('Année clôturée')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(rowFor('A006')).getByRole('button', { name: 'Appliquer' }))
    expect(await screen.findByText('Application impossible.')).toBeInTheDocument()
  })
})
