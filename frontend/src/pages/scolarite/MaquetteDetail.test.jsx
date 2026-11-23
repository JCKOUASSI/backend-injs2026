/**
 * LOT 32 — Scolarité : détail d'une maquette pédagogique
 * (`pages/scolarite/MaquetteDetail.jsx`).
 * Consultation (regroupement des UE par semestre, journal des validations),
 * workflow valider / activer / archiver / cloner sous confirmation, ajout
 * d'UE et d'ECUE (champs typés) et archivage d'une ECUE, avec les
 * habilitations `canActScolarite` et tous les chemins d'erreur.
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
import MaquetteDetail from '@/pages/scolarite/MaquetteDetail'

const MAQ_PATH_RE = /\/scolarite\/maquettes\/\d+\/$/
const JOURNAL_PATH_RE = /\/journal\/$/
const SEMESTRES_PATH = '/scolarite/ref/semestres/'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

const ecue = (id, overrides = {}) => ({
  id, code: `EC${id}`, intitule: `ECUE ${id}`,
  credits: 3, coefficient: 1, volume_total: 20, archive: false,
  ...overrides,
})
const ue = (id, semestreId = 1, overrides = {}) => ({
  id, code: `UE${id}`, intitule: `Unité ${id}`, credits: 6, caractere: 'OB',
  semestre: { id: semestreId, libelle: `Semestre ${semestreId}` },
  ecues: [ecue(id * 100)],
  ...overrides,
})

const maquetteBrouillon = (overrides = {}) => ({
  id: 1, libelle: 'Maquette L1 LSF', ref_formation: 'L1 LSF',
  niveau: 'Licence 1', annee_academique: '2025-2026', version: 1,
  statut: 'BROUILLON', credits_total: 60, volume_horaire_total: 600,
  unites_enseignement: [ue(50, 1)],
  ...overrides,
})

const journal = [
  { action: 'VALIDATION', utilisateur: 'Alice Diarra', horodatage: '2026-03-15T10:30:00Z' },
  { action: 'CREATION', utilisateur: '', horodatage: '2026-03-01T08:00:00Z' },
]

const semestresRef = [
  { id: 1, libelle: 'Semestre 1' },
  { id: 2, libelle: 'Semestre 2' },
]

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }

afterEach(async () => { await settle() })

const mount = (role = 'ADMIN', { maquette: maq, journal: jr = [] } = {}) => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  apiController.setRoute(MAQ_PATH_RE, typeof maq === 'function' ? maq : () => maq)
  apiController.setRoute(JOURNAL_PATH_RE, () => jr)
  if (role !== 'DIRECTION' && role !== 'ENCADRANT' && role !== 'FINANCE') {
    apiController.setRoute(SEMESTRES_PATH, () => semestresRef)
  }
  return renderWithProviders(<MaquetteDetail />, {
    authUser: me,
    routePattern: '/scolarite/maquettes/:id',
    initialEntries: ['/scolarite/maquettes/1'],
  })
}

const getMaqCalls = () => apiMock.get.mock.calls.filter(([p]) => MAQ_PATH_RE.test(p.split('?')[0]))
const postsTo = (re) => apiMock.post.mock.calls.filter(([p]) => re.test(p))
const posts = () => apiMock.post.mock.calls.map(([p, body]) => ({ path: p, body }))

const ueBlock = (codeUe) => screen.getByText(new RegExp(`^${codeUe} —`)).closest('.mb-3')
const ueFormCard = () => screen.getByText("Ajouter une unité d'enseignement").closest('.card')
const workflowGroup = () => document.querySelector('.btn-group')
const workflowButtons = () =>
  [...(workflowGroup()?.querySelectorAll('button') || [])].map((b) => b.textContent.trim())

// Bascule window.location en objet simple pour observer la redirection de clonage.
const stubLocation = () => {
  const original = window.location
  delete window.location
  window.location = { href: '' }
  return () => { Object.defineProperty(window, 'location', { configurable: true, value: original }) }
}

/* ------------------------------------------------------------------ */
/* LOT 32 — chargement et rendu                                         */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — chargement et rendu (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche le spinner puis charge maquette et journal en parallèle', async () => {
    const { container } = mount('ADMIN', { maquette: maquetteBrouillon(), journal })
    expect(container.querySelector('.spinner-border')).toBeTruthy()
    await settle()

    expect(apiMock.get).toHaveBeenCalledWith('/scolarite/maquettes/1/')
    expect(apiMock.get).toHaveBeenCalledWith('/scolarite/maquettes/1/journal/')
    expect(screen.getByRole('heading', { name: 'Maquette L1 LSF' })).toBeInTheDocument()
    const sousTitre = screen.getByText(/Licence 1/).textContent
    expect(sousTitre).toContain('2025-2026')
    expect(sousTitre).toContain('v1')
    expect(sousTitre).toContain('BROUILLON')
    expect(sousTitre).toContain('60 crédits')
    expect(sousTitre).toContain('600 h')
    expect(screen.getByRole('link', { name: '← Retour' })).toHaveAttribute('href', '/scolarite/maquettes')
  })

  it("replie le titre sur ref_formation quand le libellé est absent", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon({ libelle: '' }) })
    expect(await screen.findByRole('heading', { name: 'L1 LSF' })).toBeInTheDocument()
  })

  it('regroupe les UE par semestre et restitue UE, ECUE et leurs attributs', async () => {
    const maq = maquetteBrouillon({
      unites_enseignement: [
        ue(50, 1, { ecues: [ecue(5001, { credits: 3, coefficient: 2, volume_total: 24 })] }),
        ue(51, 1, { code: 'UE51', caractere: 'OP', ecues: [ecue(5002)] }),
        ue(60, 2, { ecues: [ecue(6001)] }),
      ],
    })
    mount('ADMIN', { maquette: maq })
    await settle()

    const cartes = document.querySelectorAll('.card')
    const entetes = [...cartes].map((c) => c.querySelector('.card-header')?.textContent).filter(Boolean)
    expect(entetes).toContain('Semestre 1')
    expect(entetes).toContain('Semestre 2')
    // Deux UE du semestre 1 figurent dans la même carte.
    const carteS1 = [...cartes].find((c) => c.querySelector('.card-header')?.textContent === 'Semestre 1')
    expect(within(carteS1).getByText(/^UE50 —/)).toBeInTheDocument()
    expect(within(carteS1).getByText(/^UE51 —/)).toBeInTheDocument()
    expect(within(carteS1).getByText('OP')).toBeInTheDocument()

    const ligne = screen.getByText(/^EC5001 —/).closest('li').textContent
    expect(ligne).toContain('3 cr.')
    expect(ligne).toContain('coeff. 2')
    expect(ligne).toContain('24 h')
  })

  it("badge une ECUE archivée et retire son action d'archivage", async () => {
    const maq = maquetteBrouillon({
      unites_enseignement: [ue(50, 1, { ecues: [
        ecue(5001, { archive: false }),
        ecue(5002, { archive: true }),
      ] })],
    })
    mount('ADMIN', { maquette: maq })
    await settle()

    const ligneArchivee = screen.getByText(/^EC5002 —/).closest('li')
    expect(within(ligneArchivee).getByText('archivée')).toBeInTheDocument()
    expect(ligneArchivee.querySelector('button')).toBeNull()
    // L'ECUE active garde son lien d'archivage.
    const ligneActive = screen.getByText(/^EC5001 —/).closest('li')
    expect(within(ligneActive).getByRole('button', { name: 'archiver' })).toBeInTheDocument()
  })

  it('affiche les contrôles de cohérence en alerte quand la maquette en comporte', async () => {
    mount('ADMIN', { maquette: maquetteBrouillon({
      problemes_coherence: ['Crédits insuffisants au S1', 'ECUE sans coefficient'],
    }) })
    await settle()
    const alerte = document.querySelector('.alert-warning')
    expect(alerte).toBeTruthy()
    expect(within(alerte).getByText('Crédits insuffisants au S1')).toBeInTheDocument()
    expect(within(alerte).getByText('ECUE sans coefficient')).toBeInTheDocument()
  })

  it("n'affiche aucune alerte sans problème de cohérence", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon({ problemes_coherence: [] }) })
    await settle()
    expect(document.querySelector('.alert-warning')).toBeNull()
  })

  it("restitue le journal : action, utilisateur (ou tiret) et date fr-FR", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal })
    await settle()
    expect(screen.getByText('VALIDATION')).toBeInTheDocument()
    expect(screen.getByText('Alice Diarra')).toBeInTheDocument()
    // Utilisateur de seconde entrée absent → tiret.
    const ligneCreation = screen.getByText('CREATION').closest('li')
    expect(ligneCreation.textContent).toMatch(/—/)
    // Date formatée en français (15/03/2026).
    expect(screen.getByText(/15\/03\/2026/)).toBeInTheDocument()
  })

  it("signale un journal vide", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    expect(screen.getByText('Aucune entrée.')).toBeInTheDocument()
  })

  it("notifie le détail serveur d'un échec de chargement et reste sur le spinner", async () => {
    apiController.setRoute(MAQ_PATH_RE, () => { throw { response: { data: { error: 'Maquette introuvable' } } } })
    apiController.setRoute(JOURNAL_PATH_RE, () => [])
    const me = makeUser('ADMIN')
    apiController.setMe(me)
    const { container } = renderWithProviders(<MaquetteDetail />, {
      authUser: me, routePattern: '/scolarite/maquettes/:id', initialEntries: ['/scolarite/maquettes/9'],
    })
    expect(await screen.findByText('Maquette introuvable')).toBeInTheDocument()
    expect(container.querySelector('.spinner-border')).toBeTruthy()
    expect(screen.queryByRole('heading', { name: 'Maquette L1 LSF' })).toBeNull()
  })

  it("notifie le message générique d'un échec de chargement sans réponse", async () => {
    apiController.setRoute(MAQ_PATH_RE, () => { throw new Error('réseau') })
    apiController.setRoute(JOURNAL_PATH_RE, () => [])
    const me = makeUser('ADMIN')
    apiController.setMe(me)
    renderWithProviders(<MaquetteDetail />, {
      authUser: me, routePattern: '/scolarite/maquettes/:id', initialEntries: ['/scolarite/maquettes/1'],
    })
    expect(await screen.findByText('Chargement impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 32 — habilitations et états de statut                            */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — habilitations et statuts (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('masque tous les contrôles de rédaction pour un rôle non acteur', async () => {
    mount('ENCADRANT', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    expect(workflowGroup()).toBeNull()
    expect(screen.queryByText("Ajouter une unité d'enseignement")).toBeNull()
    expect(screen.queryByRole('button', { name: 'archiver' })).toBeNull()
    expect(screen.queryByPlaceholderText('Code ECUE')).toBeNull()
    // Les référentiels de rédaction ne sont pas chargés.
    expect(apiMock.get.mock.calls.map(([p]) => p)).not.toContain(SEMESTRES_PATH)
    // La consultation reste disponible.
    expect(screen.getByText('Semestre 1')).toBeInTheDocument()
  })

  it.each([
    ['BROUILLON', ['Valider'], 'Cloner en nouvelle version'],
    ['VALIDEE', ['Activer', 'Cloner en nouvelle version'], 'Valider'],
    ['ACTIVE', ['Archiver', 'Cloner en nouvelle version'], 'Valider'],
    ['ARCHIVEE', ['Cloner en nouvelle version'], 'Archiver'],
  ])('statut %s : expose les boutons attendus', async (statut, attendus, absent) => {
    mount('ADMIN', { maquette: maquetteBrouillon({ statut }), journal: [] })
    await settle()
    const boutons = workflowButtons()
    for (const nom of attendus) expect(boutons.join('|')).toContain(nom)
    if (absent) expect(boutons.join('|')).not.toContain(absent)
    // Les formulaires de rédaction n'existent qu'en brouillon.
    const formVisible = !!screen.queryByText("Ajouter une unité d'enseignement")
    expect(formVisible).toBe(statut === 'BROUILLON')
    // Le référentiel des semestres n'est chargé qu'en brouillon éditable.
    const chargeSemestres = apiMock.get.mock.calls.map(([p]) => p).includes(SEMESTRES_PATH)
    expect(chargeSemestres).toBe(statut === 'BROUILLON')
  })

  it('autorise SECRETARIAT (rôle acteur secondaire) mais pas DIRECTION', async () => {
    const vue = mount('SECRETARIAT', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    expect(screen.getByRole('button', { name: /Valider/ })).toBeInTheDocument()
    expect(screen.getByText("Ajouter une unité d'enseignement")).toBeInTheDocument()
    vue.unmount()
    await settle()

    apiController.reset()
    const vue2 = mount('DIRECTION', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    expect(workflowGroup()).toBeNull()
    vue2.unmount()
  })

  it("avale en silence un échec du référentiel des semestres (le select reste utilisable)", async () => {
    apiController.setRoute(SEMESTRES_PATH, () => { throw new Error('500') })
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const carte = ueFormCard()
    expect(within(carte).getByText('Semestre…')).toBeInTheDocument()
    // Une seule option : le fantôme ; aucun toast d'erreur.
    const select = carte.querySelector('select')
    expect(select.options).toHaveLength(1)
    expect(screen.queryByText(/impossible/i)).toBeNull()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 32 — workflow valider / activer / archiver                       */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — workflow de validation (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const mountMutable = (statutInitial = 'BROUILLON') => {
    let maq = maquetteBrouillon({ statut: statutInitial })
    const setStatut = (statut) => { maq = { ...maq, statut } }
    const get = () => maq
    mount('ADMIN', { maquette: get, journal: [] })
    return { setStatut, get }
  }

  it('valide un brouillon après confirmation : POST, toast, nouveau statut, rechargement', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    confirmSpy.mockReturnValueOnce(false).mockReturnValue(true)
    const { setStatut } = mountMutable('BROUILLON')
    apiController.setRoute(/\/valider\/$/, () => { setStatut('VALIDEE'); return { ...maquetteBrouillon({ statut: 'VALIDEE' }) } })
    await settle()

    // Première demande : confirmation refusée, aucun appel.
    fireEvent.click(screen.getByRole('button', { name: /Valider/ }))
    expect(postsTo(/\/valider\/$/)).toHaveLength(0)
    expect(confirmSpy).toHaveBeenCalledWith('Valider cette maquette (contenu gelé) ?')

    // Confirmation acceptée.
    fireEvent.click(screen.getByRole('button', { name: /Valider/ }))
    await waitFor(() => expect(postsTo(/\/valider\/$/)).toHaveLength(1))
    expect(posts()[0].body).toEqual({})
    expect(await screen.findByText('Opération effectuée.')).toBeInTheDocument()
    await settle()
    // La maquette rechargée est VALIDEE : Activer + Cloner présents, Valider et formulaires partis.
    expect(screen.getByRole('button', { name: /Activer/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Cloner/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Valider/ })).toBeNull()
    expect(screen.queryByText("Ajouter une unité d'enseignement")).toBeNull()
    expect(getMaqCalls().length).toBeGreaterThanOrEqual(2)
  })

  it('active une maquette validée (POST activer, confirmation immuable)', async () => {
    const vi2 = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { setStatut } = mountMutable('VALIDEE')
    apiController.setRoute(/\/activer\/$/, () => { setStatut('ACTIVE'); return { ...maquetteBrouillon({ statut: 'ACTIVE' }) } })
    await settle()

    fireEvent.click(screen.getByRole('button', { name: /Activer/ }))
    expect(vi2).toHaveBeenCalledWith('Activer cette maquette (immuable) ?')
    await waitFor(() => expect(postsTo(/\/activer\/$/)).toHaveLength(1))
    expect(await screen.findByText('Opération effectuée.')).toBeInTheDocument()
    await settle()
    expect(screen.getByRole('button', { name: /Archiver/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Activer/ })).toBeNull()
  })

  it('archive une maquette active (POST archiver, clonage reste possible)', async () => {
    const vi2 = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const { setStatut } = mountMutable('ACTIVE')
    apiController.setRoute(/\/archiver\/$/, () => { setStatut('ARCHIVEE'); return { ...maquetteBrouillon({ statut: 'ARCHIVEE' }) } })
    await settle()

    fireEvent.click(screen.getByRole('button', { name: /Archiver/ }))
    expect(vi2).toHaveBeenCalledWith('Archiver cette maquette ?')
    await waitFor(() => expect(postsTo(/\/archiver\/$/)).toHaveLength(1))
    expect(await screen.findByText('Opération effectuée.')).toBeInTheDocument()
    await settle()
    expect(screen.queryByRole('button', { name: /^Archiver/ })).toBeNull()
    // Une archivée (non brouillon) reste clonable.
    expect(screen.getByRole('button', { name: /Cloner/ })).toBeInTheDocument()
  })

  it("désactive les boutons du groupe pendant l'appel puis les réactive", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mountMutable('BROUILLON')
    await settle()
    let resolvePost
    apiMock.post.mockImplementationOnce(() => new Promise((res) => { resolvePost = () => res({ data: {} }) }))

    fireEvent.click(screen.getByRole('button', { name: /Valider/ }))
    expect(screen.getByRole('button', { name: /Valider/ })).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(6) })
    expect(await screen.findByText('Opération effectuée.')).toBeInTheDocument()
    await settle()
  })

  it("notifie les problèmes de cohérence, puis le détail, puis le message générique", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mountMutable('BROUILLON')
    await settle()
    const bouton = () => screen.getByRole('button', { name: /Valider/ })

    apiMock.post.mockRejectedValueOnce({ response: { data: { problemes: ['Crédits S1 insuffisants', 'ECUE orpheline'] } } })
    fireEvent.click(bouton())
    expect(await screen.findByText('Crédits S1 insuffisants ECUE orpheline')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Transition refusée' } } })
    fireEvent.click(bouton())
    expect(await screen.findByText('Transition refusée')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(bouton())
    expect(await screen.findByText('Action impossible.')).toBeInTheDocument()
    // Échec : pas de rechargement.
    expect(getMaqCalls()).toHaveLength(1)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 32 — clonage                                                     */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — clonage (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('clone une maquette validée : confirmation, POST, toast versionné et redirection', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm')
    confirmSpy.mockReturnValueOnce(false).mockReturnValue(true)
    mount('ADMIN', { maquette: maquetteBrouillon({ statut: 'VALIDEE' }), journal: [] })
    await settle()
    const restore = stubLocation()

    // Annulation : aucun appel, pas de navigation.
    fireEvent.click(screen.getByRole('button', { name: /Cloner/ }))
    expect(postsTo(/\/cloner\/$/)).toHaveLength(0)
    expect(confirmSpy).toHaveBeenCalledWith('Créer une nouvelle version (clonage) ?')

    apiController.setRoute(/\/cloner\/$/, () => ({ id: 9, version: 2 }))
    fireEvent.click(screen.getByRole('button', { name: /Cloner/ }))
    await waitFor(() => expect(postsTo(/\/cloner\/$/)).toHaveLength(1))
    expect(posts()[0].body).toEqual({})
    expect(await screen.findByText('Version v2 créée en brouillon.')).toBeInTheDocument()
    expect(window.location.href).toBe('/scolarite/maquettes/9')
    restore()
  })

  it("notifie le détail puis le message générique d'un échec de clonage", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('ADMIN', { maquette: maquetteBrouillon({ statut: 'VALIDEE' }), journal: [] })
    await settle()
    const restore = stubLocation()

    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Maquette verrouillée' } } })
    fireEvent.click(screen.getByRole('button', { name: /Cloner/ }))
    expect(await screen.findByText('Maquette verrouillée')).toBeInTheDocument()
    expect(window.location.href).toBe('')

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: /Cloner/ }))
    expect(await screen.findByText('Clonage impossible.')).toBeInTheDocument()
    restore()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 32 — ajout d'UE                                                  */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — ajout d’une UE (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const remplirFormulaireUe = (carte, { semestre = '1', code = 'UE99', intitule = 'Nouvelle UE', credits = '6' } = {}) => {
    if (semestre !== null) fireEvent.change(carte.querySelector('select'), { target: { value: semestre } })
    fireEvent.change(within(carte).getByPlaceholderText('Code UE'), { target: { value: code } })
    fireEvent.change(within(carte).getByPlaceholderText('Intitulé'), { target: { value: intitule } })
    fireEvent.change(within(carte).getByPlaceholderText('Cr.'), { target: { value: credits } })
  }

  it('ajoute une UE avec les identifiants et crédits typés, puis recharge et réinitialise', async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const carte = ueFormCard()
    // Le select est alimenté par le référentiel des semestres.
    expect(within(carte).getByText('Semestre 2')).toBeInTheDocument()

    remplirFormulaireUe(carte)
    fireEvent.click(within(carte).getByRole('button', { name: 'Ajouter' }))

    await waitFor(() => expect(postsTo(/\/ues\/$/)).toHaveLength(1))
    const [path, body] = postsTo(/\/ues\/$/)[0]
    expect(path).toBe('/scolarite/maquettes/1/ues/')
    expect(body).toEqual({ semestre_id: 1, code: 'UE99', intitule: 'Nouvelle UE', credits: 6 })
    expect(await screen.findByText('UE ajoutée.')).toBeInTheDocument()
    // Formulaire réinitialisé.
    expect(carte.querySelector('select').value).toBe('')
    expect(within(carte).getByPlaceholderText('Code UE').value).toBe('')
    expect(getMaqCalls().length).toBeGreaterThanOrEqual(2)
  })

  it("coerce des crédits non numériques à 0 (soumission directe du formulaire)", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const carte = ueFormCard()
    remplirFormulaireUe(carte, { credits: 'abc' })
    // Le navigateur bloquerait normalement un champ number invalide ; on force
    // la soumission pour exercer le `Number(...) || 0` de la page.
    fireEvent.submit(carte.querySelector('form'))
    await waitFor(() => expect(postsTo(/\/ues\/$/)).toHaveLength(1))
    expect(postsTo(/\/ues\/$/)[0][1].credits).toBe(0)
  })

  it("notifie le détail serveur puis le message générique d'un échec d'ajout", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const carte = ueFormCard()
    remplirFormulaireUe(carte)

    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Code UE déjà pris' } } })
    fireEvent.click(within(carte).getByRole('button', { name: 'Ajouter' }))
    expect(await screen.findByText('Code UE déjà pris')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(carte).getByRole('button', { name: 'Ajouter' }))
    expect(await screen.findByText('Ajout impossible.')).toBeInTheDocument()
    // Le formulaire est conservé après échec.
    expect(within(carte).getByPlaceholderText('Code UE').value).toBe('UE99')
  })

  it("désactive le bouton Ajouter pendant l'envoi", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const carte = ueFormCard()
    remplirFormulaireUe(carte)
    let resolvePost
    apiMock.post.mockImplementationOnce(() => new Promise((res) => { resolvePost = () => res({ data: {} }) }))
    fireEvent.click(within(carte).getByRole('button', { name: 'Ajouter' }))
    expect(within(carte).getByRole('button', { name: 'Ajouter' })).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(6) })
    expect(await screen.findByText('UE ajoutée.')).toBeInTheDocument()
    await settle()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 32 — ajout d'ECUE                                                */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — ajout d’une ECUE (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const maquetteDeuxUe = () => maquetteBrouillon({
    unites_enseignement: [
      ue(50, 1, { ecues: [ecue(5001)] }),
      ue(51, 1, { ecues: [ecue(5002)] }),
    ],
  })

  const remplirFormulaireEcue = (block, { code = 'EC999', intitule = 'Nouvelle ECUE', credits = '4' } = {}) => {
    // Le focus fixe l'UE rattachée (onFocus du formulaire ECUE), comme un clic réel.
    const codeInput = within(block).getByPlaceholderText('Code ECUE')
    fireEvent.focus(codeInput)
    fireEvent.change(codeInput, { target: { value: code } })
    const intituleInput = within(block).getByPlaceholderText('Intitulé')
    fireEvent.focus(intituleInput)
    fireEvent.change(intituleInput, { target: { value: intitule } })
    const creditsInput = within(block).getByPlaceholderText('Cr.')
    fireEvent.focus(creditsInput)
    fireEvent.change(creditsInput, { target: { value: credits } })
  }

  it('ajoute une ECUE sous la bonne UE (URL) avec crédits typés et coefficient 1, puis recharge', async () => {
    mount('ADMIN', { maquette: maquetteDeuxUe(), journal: [] })
    await settle()
    const block = ueBlock('UE50')
    remplirFormulaireEcue(block)
    fireEvent.click(within(block).getByRole('button', { name: '+ ECUE' }))

    await waitFor(() => expect(postsTo(/\/ecues\/$/)).toHaveLength(1))
    const [path, body] = postsTo(/\/ecues\/$/)[0]
    expect(path).toBe('/scolarite/ues/50/ecues/')
    expect(body).toEqual({ code: 'EC999', intitule: 'Nouvelle ECUE', credits: 4, coefficient: 1 })
    expect(await screen.findByText('ECUE ajoutée.')).toBeInTheDocument()
    await settle()
    // Formulaire réinitialisé et liste rechargée.
    expect(within(block).getByPlaceholderText('Code ECUE').value).toBe('')
    expect(getMaqCalls().length).toBeGreaterThanOrEqual(2)
  })

  it("isole les formulaires ECUE de chaque UE (saisie UE50 invisible côté UE51)", async () => {
    mount('ADMIN', { maquette: maquetteDeuxUe(), journal: [] })
    await settle()
    const block50 = ueBlock('UE50')
    const block51 = ueBlock('UE51')
    remplirFormulaireEcue(block50)
    expect(within(block51).getByPlaceholderText('Code ECUE').value).toBe('')
    expect(within(block51).getByPlaceholderText('Intitulé').value).toBe('')

    fireEvent.click(within(block50).getByRole('button', { name: '+ ECUE' }))
    await waitFor(() => expect(postsTo(/\/ecues\/$/)).toHaveLength(1))
    expect(postsTo(/\/ecues\/$/)[0][0]).toBe('/scolarite/ues/50/ecues/')
  })

  it("coerce des crédits ECUE non numériques à 0", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const block = ueBlock('UE50')
    remplirFormulaireEcue(block, { credits: 'xyz' })
    fireEvent.submit(block.querySelector('form'))
    await waitFor(() => expect(postsTo(/\/ecues\/$/)).toHaveLength(1))
    const body = postsTo(/\/ecues\/$/)[0][1]
    expect(body.credits).toBe(0)
    expect(body.coefficient).toBe(1)
  })

  it("notifie le détail serveur puis le message générique d'un échec d'ajout", async () => {
    mount('ADMIN', { maquette: maquetteBrouillon(), journal: [] })
    await settle()
    const block = ueBlock('UE50')
    remplirFormulaireEcue(block)

    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Doublon de code ECUE' } } })
    fireEvent.click(within(block).getByRole('button', { name: '+ ECUE' }))
    expect(await screen.findByText('Doublon de code ECUE')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(block).getByRole('button', { name: '+ ECUE' }))
    expect(await screen.findByText('Ajout impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 32 — archivage d'une ECUE                                        */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/MaquetteDetail.jsx — archivage d’une ECUE (LOT 32)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  const maquetteAvecEcue = () => maquetteBrouillon({
    unites_enseignement: [ue(50, 1, { ecues: [ecue(77, { archive: false })] })],
  })

  it("n'archive rien quand la confirmation est annulée", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount('ADMIN', { maquette: maquetteAvecEcue(), journal: [] })
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'archiver' }))
    expect(window.confirm).toHaveBeenCalledWith(
      "Archiver cette ECUE ? Elle ne pourra plus entrer dans une nouvelle maquette.",
    )
    expect(apiMock.delete).not.toHaveBeenCalled()
    expect(screen.queryByText('ECUE archivée.')).toBeNull()
  })

  it('archive une ECUE (DELETE ?mode=archive), notifie et recharge', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('ADMIN', { maquette: maquetteAvecEcue(), journal: [] })
    await settle()
    const appelsAvant = getMaqCalls().length
    fireEvent.click(screen.getByRole('button', { name: 'archiver' }))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledTimes(1))
    expect(apiMock.delete.mock.calls[0][0]).toBe('/scolarite/ecues/77/?mode=archive')
    expect(await screen.findByText('ECUE archivée.')).toBeInTheDocument()
    await settle()
    expect(getMaqCalls().length).toBeGreaterThan(appelsAvant)
  })

  it("notifie le détail serveur puis le message générique d'un échec d'archivage", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount('ADMIN', { maquette: maquetteAvecEcue(), journal: [] })
    await settle()

    apiMock.delete.mockRejectedValueOnce({ response: { data: { error: 'ECUE utilisée' } } })
    fireEvent.click(screen.getByRole('button', { name: 'archiver' }))
    expect(await screen.findByText('ECUE utilisée')).toBeInTheDocument()

    apiMock.delete.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: 'archiver' }))
    expect(await screen.findByText('Suppression impossible.')).toBeInTheDocument()
  })
})
