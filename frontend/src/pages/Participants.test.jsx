import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within, fireEvent, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Participants from '@/pages/Participants'

const LIST = '/formations/participants/list/'
const REFS = '/formations/referentiels/'
const PAGE_SIZE = 50

/* ------------------------------------------------------------------ */
/* Jeu de données                                                       */
/* ------------------------------------------------------------------ */

// 55 participants pour exercer la pagination (50/page) et les filtres.
// Nom54 (i=53, page 2) est laissé sans sexe/grade/téléphone pour couvrir
// les tirets de repli de la table.
const participants = Array.from({ length: 55 }, (_, i) => ({
  id: i + 1,
  nom: `Nom${i + 1}`,
  prenom: `Prenom${i + 1}`,
  matricule: i === 53 ? '' : `P${String(i + 1).padStart(4, '0')}`,
  sexe: i === 53 ? '' : (i % 2 === 0 ? 'FEMININ' : 'MASCULIN'),
  grade: i === 53 ? '' : (i % 3 === 0 ? 'L2' : 'L1'),
  telephone: i === 53 ? '' : `0700${String(i).padStart(6, '0')}`,
  secretariat: i % 2 === 0 ? 'INJS Cocody' : 'INJS Marcory',
  groupe: i % 2 === 0 ? 'G2' : 'G1',
  type_concours: i % 2 === 0 ? 'PROFESSIONNEL' : 'CONCOURS DIRECT',
  vague: 'V2026',
}))

const referentiels = () => ({
  categories: [{ id: 1, libelle: 'Fonction publique' }],
  grades: [
    { id: 10, libelle: 'A1', categorie_id: 1 },
    { id: 11, libelle: 'B1', categorie_id: 2 },
  ],
  sites: [
    { id: 20, nom: 'Marcory' },
    { id: 21, nom: 'Cocody' },
  ],
  salles: [
    { id: 30, nom: 'Salle Marcory', site_id: 20 },
    { id: 31, nom: 'Salle Cocody', site_id: 21 },
  ],
  vagues: [{ id: 40, libelle: 'V2026' }],
})

/** Reproduit le filtrage + la pagination serveur de la liste. */
const listHandler = (path) => {
  const q = new URL(path, 'http://testserver').searchParams
  const page = Number(q.get('page') || 1)
  const search = (q.get('search') || '').toLowerCase()
  let rows = participants
  if (search) {
    rows = rows.filter((p) =>
      [p.matricule, p.nom, p.prenom, p.telephone, p.type_concours]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(search)),
    )
  }
  for (const key of ['sexe', 'secretariat', 'grade', 'groupe', 'type_concours', 'vague']) {
    const v = q.get(key)
    if (v) rows = rows.filter((p) => p[key] === v)
  }
  const count = rows.length
  const start = (page - 1) * PAGE_SIZE
  const results = rows.slice(start, start + PAGE_SIZE)
  return {
    count,
    total_pages: Math.max(1, Math.ceil(count / PAGE_SIZE)),
    results,
    filter_options: {
      secretariats: ['INJS Cocody', 'INJS Marcory'],
      grades: ['L1', 'L2'],
      groupes: ['G1', 'G2'],
      types_concours: ['CONCOURS DIRECT', 'PROFESSIONNEL'],
    },
  }
}

/* ------------------------------------------------------------------ */
/* Helpers de montage / interrogation                                   */
/* ------------------------------------------------------------------ */

const mount = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<Participants />, {
    authUser: me,
    initialEntries: ['/participants'],
    routePattern: '/participants',
  })
}

const listParams = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.startsWith(LIST))
    .map(([p]) => new URL(p, 'http://testserver').searchParams)
const lastParams = () => listParams().at(-1)

const waitForTable = async (text = /55 résultat\(s\)/) =>
  waitFor(() => expect(screen.getByText(text)).toBeInTheDocument())

const rowFor = (fullName) => screen.getByText(fullName).closest('tr')

const filterSelect = (defaultOptionText) =>
  screen.getByText(defaultOptionText, { selector: 'option' }).closest('select')

const settle = async (n = 4) => { await act(async () => { await flushPromises(n) }) }

// Les libellés des modales ne sont pas reliés par htmlFor : on récupère le
// champ (input/select) du même .form-group que le <label>.
const getFormModal = (titleRegex) =>
  screen.getByRole('heading', { name: titleRegex }).closest('.modal-content')
const modalField = (modal, labelRegex) => {
  const label = within(modal).getByText(
    (content, el) => el.tagName === 'LABEL' && labelRegex.test(el.textContent),
  )
  return label.closest('.form-group').querySelector('input, select, textarea')
}

const stubBlobDownload = () => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

const openCreate = async () => {
  fireEvent.click(screen.getByRole('button', { name: /nouvel étudiant/i }))
  const modal = await screen.findByRole('heading', { name: /nouvel étudiant/i })
  return modal.closest('.modal-content')
}

const fillRequired = (modal, { matricule = 'P9001', nom = 'Nouveau', prenom = 'Test' } = {}) => {
  fireEvent.change(modalField(modal, /n° d'inscription/i), { target: { value: matricule } })
  fireEvent.change(modalField(modal, /^Nom/i), { target: { value: nom } })
  fireEvent.change(modalField(modal, /^Prénom/i), { target: { value: prenom } })
}

/* ------------------------------------------------------------------ */
/* LOT 23 — liste serveur, recherche, filtres, pagination              */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — liste serveur (LOT 23)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
  })

  it('charge la première page : titre, colonnes, badge de compte, plage et requête', async () => {
    mount()
    await waitForTable()

    expect(screen.getByText('Liste des étudiants')).toBeInTheDocument()
    for (const col of ["N° d'inscription", 'Nom & Prénom', 'Sexe', 'Grade', 'Téléphone', 'Actions']) {
      expect(screen.getByText(col)).toBeInTheDocument()
    }
    // 50 lignes sur 55 à la première page.
    expect(screen.getByText('Nom1 Prenom1')).toBeInTheDocument()
    expect(screen.getByText('Nom50 Prenom50')).toBeInTheDocument()
    expect(screen.queryByText('Nom51 Prenom51')).not.toBeInTheDocument()
    expect(screen.getByText(/1–50 sur 55/)).toBeInTheDocument()
    expect(lastParams().get('page')).toBe('1')
    // Sexe et grade sont rendus via les helpers de libellé.
    expect(within(rowFor('Nom1 Prenom1')).getByText('Féminin')).toBeInTheDocument()
  })

  it('applique la recherche avec debounce et revient en page 1', async () => {
    mount()
    await waitForTable()

    fireEvent.change(screen.getByPlaceholderText(/nom, prénom, matricule/i), {
      target: { value: 'nom12' },
    })
    await waitFor(() => expect(lastParams().get('search')).toBe('nom12'))
    expect(lastParams().get('page')).toBe('1')
    // Sur la plage Nom1..Nom55, « nom12 » ne correspond qu'à la ligne 12
    // (nom et prénom contiennent la sous-chaîne ; pas de Nom120+).
    expect(screen.getByText('Nom12 Prenom12')).toBeInTheDocument()
    expect(screen.queryByText('Nom1 Prenom1')).not.toBeInTheDocument()
  })

  it("filtre par secrétariat via le menu déroulant et transmet le paramètre", async () => {
    mount()
    await waitForTable()

    fireEvent.change(filterSelect('Tous (secrétariat)'), { target: { value: 'INJS Marcory' } })
    await waitFor(() => expect(lastParams().get('secretariat')).toBe('INJS Marcory'))
    // Les impairs (Marcory) : Nom2 (i=1) présent, Nom1 (Cocody) absent.
    expect(screen.getByText('Nom2 Prenom2')).toBeInTheDocument()
    expect(screen.queryByText('Nom1 Prenom1')).not.toBeInTheDocument()
    expect(screen.getByText(/27 résultat\(s\)/)).toBeInTheDocument()
  })

  it('combine les filtres grade, sexe, type de concours et groupe', async () => {
    mount()
    await waitForTable()

    fireEvent.change(filterSelect('Tous (grade)'), { target: { value: 'L2' } })
    await waitFor(() => expect(lastParams().get('grade')).toBe('L2'))

    fireEvent.change(filterSelect('Tous (sexe)'), { target: { value: 'FEMININ' } })
    await waitFor(() => expect(lastParams().get('sexe')).toBe('FEMININ'))

    fireEvent.change(filterSelect('Tous (type concours)'), { target: { value: 'PROFESSIONNEL' } })
    await waitFor(() => expect(lastParams().get('type_concours')).toBe('PROFESSIONNEL'))

    fireEvent.change(filterSelect('Tous (groupe)'), { target: { value: 'G2' } })
    await waitFor(() => {
      const p = lastParams()
      expect(p.get('grade')).toBe('L2')
      expect(p.get('sexe')).toBe('FEMININ')
      expect(p.get('type_concours')).toBe('PROFESSIONNEL')
      expect(p.get('groupe')).toBe('G2')
    })
    // i pairs, multiples de 3 : 0, 6, 12, … → 10 lignes (i < 55).
    expect(screen.getByText(/10 résultat\(s\)/)).toBeInTheDocument()
  })

  it("propose le filtre de vague dès que les référentiels sont chargés", async () => {
    mount()
    await waitForTable()
    const select = await screen.findByText('Toutes les vagues', { selector: 'option' })
    expect(within(select.closest('select')).getByText('V2026')).toBeInTheDocument()
    fireEvent.change(select.closest('select'), { target: { value: 'V2026' } })
    await waitFor(() => expect(lastParams().get('vague')).toBe('V2026'))
  })

  it("garnit les options de filtre depuis filter_options de la réponse", async () => {
    mount()
    await waitForTable()
    const secretariats = filterSelect('Tous (secrétariat)')
    expect(within(secretariats).getByText('INJS Marcory')).toBeInTheDocument()
    expect(within(secretariats).getByText('INJS Cocody')).toBeInTheDocument()
    expect(within(filterSelect('Tous (grade)')).getByText('L2')).toBeInTheDocument()
  })

  it("affiche l'état vide quand aucun étudiant ne correspond", async () => {
    mount()
    await waitForTable()
    fireEvent.change(screen.getByPlaceholderText(/nom, prénom, matricule/i), {
      target: { value: 'zzz-introuvable' },
    })
    await waitFor(() => expect(lastParams().get('search')).toBe('zzz-introuvable'))
    expect(screen.getByText('Aucun étudiant trouvé')).toBeInTheDocument()
    expect(screen.getByText(/0 résultat\(s\)/)).toBeInTheDocument()
  })

  it("notifie une erreur quand le chargement de la liste échoue", async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiController.reset()
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(LIST, () => { throw { response: { status: 500, data: {} } } })
    renderWithProviders(<Participants />, {
      authUser: me, initialEntries: ['/participants'], routePattern: '/participants',
    })
    expect(await screen.findByText('Erreur lors du chargement des étudiants')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('pagine vers la seconde page (Suivant → page=2, 5 lignes)', async () => {
    mount()
    await waitForTable()
    fireEvent.click(screen.getByRole('button', { name: /suivant/i }))
    await waitFor(() => expect(lastParams().get('page')).toBe('2'))
    expect(screen.getByText('Nom51 Prenom51')).toBeInTheDocument()
    expect(screen.getByText('Nom55 Prenom55')).toBeInTheDocument()
    expect(screen.queryByText('Nom1 Prenom1')).not.toBeInTheDocument()
    expect(screen.getByText(/51–55 sur 55/)).toBeInTheDocument()
    // Nom54 n'a ni matricule, sexe, grade ni téléphone : quatre tirets de repli.
    expect(within(rowFor('Nom54 Prenom54')).getAllByText('-')).toHaveLength(4)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 23 — habilitations                                              */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — habilitations (LOT 23)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
  })

  it('ADMIN : création, gestion et exports sont disponibles', async () => {
    mount('ADMIN')
    await waitForTable()
    expect(screen.getByRole('button', { name: /nouvel étudiant/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listes de classe pdf/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listes de classe excel/i })).toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).getByTitle('Modifier')).toBeInTheDocument()
    expect(within(row).getByTitle('Supprimer')).toBeInTheDocument()
  })

  it('SECRETARIAT : peut modifier/supprimer et exporter, mais pas créer', async () => {
    mount('SECRETARIAT')
    await waitForTable()
    expect(screen.queryByRole('button', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listes de classe pdf/i })).toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).getByTitle('Modifier')).toBeInTheDocument()
    expect(within(row).getByTitle('Supprimer')).toBeInTheDocument()
  })

  it('DIRECTION : lecture seule avec exports, sans création ni gestion', async () => {
    mount('DIRECTION')
    await waitForTable()
    expect(screen.queryByRole('button', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listes de classe pdf/i })).toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
    expect(within(row).getByTitle('Visualiser')).toBeInTheDocument()
  })

  it('SUPERVISEUR : ni gestion ni export liste de classe', async () => {
    mount('SUPERVISEUR')
    await waitForTable()
    expect(screen.queryByRole('button', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /liste.*classe pdf/i })).not.toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 23 — création / édition                                         */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — création et édition (LOT 23)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
  })

  it('crée un étudiant (POST), ferme la modale, recharge et notifie', async () => {
    mount()
    await waitForTable()
    const modal = await openCreate()
    fillRequired(modal)
    fireEvent.change(modalField(modal, /^Téléphone 1/i), { target: { value: '0711111111' } })

    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/formations/participants/',
        expect.objectContaining({ matricule: 'P9001', nom: 'Nouveau', prenom: 'Test', telephone: '0711111111' }),
      ),
    )
    // Une date vide n'est pas envoyée.
    const body = apiMock.post.mock.calls.at(-1)[1]
    expect(body).not.toHaveProperty('date_naissance')
    expect(await screen.findByText('Étudiant créé')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
  })

  it('pré-remplit la modale de modification et envoie un PATCH ciblé', async () => {
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom7 Prenom7')).getByTitle('Modifier'))
    const modal = getFormModal(/modifier l'étudiant/i)
    expect(modalField(modal, /n° d'inscription/i)).toHaveValue('P0007')
    expect(modalField(modal, /^Nom/i)).toHaveValue('Nom7')
    fireEvent.change(modalField(modal, /^Nom/i), { target: { value: 'Nom7-modifie' } })
    // Une date renseignée est transmise.
    fireEvent.change(modalField(modal, /date de naissance/i), { target: { value: '2000-05-17' } })

    fireEvent.click(within(modal).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith(
        '/formations/participants/7/',
        expect.objectContaining({ nom: 'Nom7-modifie', date_naissance: '2000-05-17' }),
      ),
    )
    expect(await screen.findByText('Étudiant modifié')).toBeInTheDocument()
  })

  it("affiche les erreurs de validation du backend formatées par champ, sans fermer", async () => {
    mount()
    await waitForTable()
    const modal = await openCreate()
    fillRequired(modal)
    apiMock.post.mockRejectedValueOnce({
      response: { data: { matricule: ['Ce matricule existe déjà.'] } },
    })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))
    expect(await within(modal).findByText(/matricule : Ce matricule existe déjà\./)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /nouvel étudiant/i })).toBeInTheDocument()
  })

  it("gère les erreurs de validation dont la valeur n'est pas un tableau", async () => {
    mount()
    await waitForTable()
    const modal = await openCreate()
    fillRequired(modal)
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Opération refusée' } } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))
    expect(await within(modal).findByText('detail : Opération refusée')).toBeInTheDocument()
  })

  it("l'édition d'un étudiant aux champs optionnels vides garde des chaînes (repli '')", async () => {
    mount()
    await waitForTable()
    // Nom54 (i=53) est en page 2, sans matricule/sexe/grade/téléphone.
    fireEvent.click(screen.getByRole('button', { name: /suivant/i }))
    await waitFor(() => expect(lastParams().get('page')).toBe('2'))
    fireEvent.click(within(rowFor('Nom54 Prenom54')).getByTitle('Modifier'))
    const modal = getFormModal(/modifier l'étudiant/i)
    const matriculeInput = modalField(modal, /n° d'inscription/i)
    expect(matriculeInput).toHaveValue('')
    expect(modalField(modal, /téléphone 1/i)).toHaveValue('')
    expect(modalField(modal, /^Sexe/i)).toHaveValue('')
    // Le matricule vide bloque la validation native de jsdom : on la neutralise
    // pour exercer l'envoi réel (le backend reste juge du caractère requis).
    matriculeInput.removeAttribute('required')
    fireEvent.click(within(modal).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith(
        '/formations/participants/54/',
        expect.objectContaining({ matricule: '', telephone: '', sexe: '' }),
      ),
    )
    expect(await screen.findByText('Étudiant modifié')).toBeInTheDocument()
  })

  it("affiche un message générique quand l'erreur de sauvegarde n'a pas de détail", async () => {
    mount()
    await waitForTable()
    const modal = await openCreate()
    fillRequired(modal)
    apiMock.post.mockRejectedValueOnce(new Error('réseau coupé'))
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))
    expect(await within(modal).findByText('Erreur lors de la sauvegarde')).toBeInTheDocument()
  })

  it("l'annulation ne déclenche aucun appel d'écriture", async () => {
    mount()
    await waitForTable()
    const modal = await openCreate()
    fillRequired(modal)
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(screen.queryByRole('heading', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('filtre les grades par catégorie et les salles par site (référentiels liés)', async () => {
    mount()
    await waitForTable()
    const modal = await openCreate()

    // Avant sélection, tous les grades et toutes les salles sont proposés.
    // /^Grade$/ exact : « Grade-Groupe » porterait sinon la même ancre.
    const gradeSelect = modalField(modal, /^Grade$/)
    expect(within(gradeSelect).getByText('A1')).toBeInTheDocument()
    expect(within(gradeSelect).getByText('B1')).toBeInTheDocument()

    // Attention : /^Grade/ matche aussi le libellé « Grade-Groupe » → ancre exacte.
    const categorieSelect = modalField(modal, /^Catégorie/i)
    fireEvent.change(categorieSelect, { target: { value: 'Fonction publique' } })
    // Catégorie id 1 → seul A1 (categorie_id 1) subsiste, et le grade est remis à vide.
    expect(within(gradeSelect).getByText('A1')).toBeInTheDocument()
    expect(within(gradeSelect).queryByText('B1')).not.toBeInTheDocument()
    fireEvent.change(gradeSelect, { target: { value: 'A1' } })
    expect(gradeSelect).toHaveValue('A1')

    fireEvent.change(modalField(modal, /^Site/i), { target: { value: 'Marcory' } })
    const salleSelect = modalField(modal, /^Salle/i)
    expect(within(salleSelect).getByText('Salle Marcory')).toBeInTheDocument()
    expect(within(salleSelect).queryByText('Salle Cocody')).not.toBeInTheDocument()
    fireEvent.change(salleSelect, { target: { value: 'Salle Marcory' } })
    expect(salleSelect).toHaveValue('Salle Marcory')
  })

  it("ferme la modale par le bouton X puis par un clic sur le voile, sans enregistrer", async () => {
    mount()
    await waitForTable()

    let modalBox = await openCreate()
    fireEvent.click(within(modalBox).getByText('×'))
    await settle()
    expect(screen.queryByRole('heading', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(apiMock.post).not.toHaveBeenCalled()

    modalBox = await openCreate()
    // Clic sur le voile (overlay), en dehors du contenu de la modale.
    fireEvent.click(document.querySelector('.modal-overlay'))
    await settle()
    expect(screen.queryByRole('heading', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it("retombe sur des champs texte quand les référentiels sont vides", async () => {
    // La route REFS du beforeEach gagnerait sinon (première correspondance) :
    // reset complet puis reprogrammation avec des référentiels vides.
    apiController.reset()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, () => ({
      categories: [], grades: [], sites: [], salles: [], vagues: [],
    }))
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    renderWithProviders(<Participants />, {
      authUser: me, initialEntries: ['/participants'], routePattern: '/participants',
    })
    await waitForTable()
    // Sans vague référentielle, le select de filtre de vague n'existe pas.
    expect(screen.queryByText('Toutes les vagues', { selector: 'option' })).not.toBeInTheDocument()
    const modal = await openCreate()
    expect(modalField(modal, /^Catégorie/i).tagName).toBe('INPUT')
    expect(modalField(modal, /^Grade$/).tagName).toBe('INPUT')
    expect(modalField(modal, /^Vague/i).tagName).toBe('INPUT')
    expect(modalField(modal, /^Site/i).tagName).toBe('INPUT')
  })
})

/* ------------------------------------------------------------------ */
/* LOT 23 — suppression                                                */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — suppression (LOT 23)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
  })

  it('demande confirmation et annule sans supprimer', async () => {
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Supprimer'))
    const dialog = await screen.findByText('Supprimer cet étudiant ?')
    expect(dialog).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it('confirme la suppression (DELETE), recharge la liste et notifie', async () => {
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Supprimer'))
    expect(await screen.findByText('Supprimer cet étudiant ?')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith('/formations/participants/1/'))
    expect(await screen.findByText('Étudiant supprimé')).toBeInTheDocument()
  })

  it("notifie l'échec de la suppression sans quitter la page", async () => {
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Supprimer'))
    expect(await screen.findByText('Supprimer cet étudiant ?')).toBeInTheDocument()
    apiMock.delete.mockRejectedValueOnce(new Error('verrou'))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Erreur lors de la suppression')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 23 — fenêtre de détail                                          */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — fenêtre de détail (LOT 23)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
  })

  it('ADMIN : charge la fiche admin complète (modules, pointages, stats)', async () => {
    // modules/pointages absents : la page applique elle-même le repli [].
    apiController.setRoute('/participant/1/fiche-admin/', () => ({
      modules: null, pointages: null, stats: null, notes_fiche: null,
    }))
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Visualiser'))
    expect(await screen.findByRole('heading', { name: /Nom1 Prenom1/ })).toBeInTheDocument()
    // Le contenu (onglets) ne s'affiche qu'après le chargement.
    expect(await screen.findByRole('tablist')).toBeInTheDocument()
    expect(
      apiMock.get.mock.calls.some(([p]) => p === '/participant/1/fiche-admin/'),
    ).toBe(true)
    expect(
      apiMock.get.mock.calls.some(([p]) => p.startsWith('/formations/participants/1/formations/')),
    ).toBe(false)
  })

  it('rôle sans vue présence : accepte aussi une réponse paginée {results}', async () => {
    // Couvre la normalisation Array.isArray ? data : data.results.
    apiController.setRoute('/formations/participants/1/formations/', () => ({ count: 0, results: [] }))
    mount('SUPERVISEUR')
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Visualiser'))
    expect(await screen.findByRole('tablist')).toBeInTheDocument()
    expect(
      apiMock.get.mock.calls.some(([p]) => p === '/participant/1/fiche-admin/'),
    ).toBe(false)
    expect(
      apiMock.get.mock.calls.some(([p]) => p.startsWith('/formations/participants/1/formations/')),
    ).toBe(true)
  })

  it("reste fonctionnelle si la fiche admin échoue (contenu vide, pas de crash)", async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiController.setRoute('/participant/1/fiche-admin/', () => {
      throw { response: { status: 500, data: {} } }
    })
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Visualiser'))
    expect(await screen.findByRole('tablist')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: /Nom1 Prenom1/ })).toBeInTheDocument()
    // La pastille « Modules 0 » du résumé (un autre libellé « Modules » existe
    // dans les panneaux d'onglets) : on discrimine par le <strong> 0.
    const modulesChip = screen
      .getAllByText(/Modules/)
      .find((el) => el.querySelector('strong')?.textContent === '0')
    expect(modulesChip).toBeTruthy()
    spy.mockRestore()
  })

  it('ferme la fenêtre de détail', async () => {
    apiController.setRoute('/participant/1/fiche-admin/', () => ({
      modules: [], pointages: [], stats: null, notes_fiche: null,
    }))
    mount()
    await waitForTable()
    fireEvent.click(within(rowFor('Nom1 Prenom1')).getByTitle('Visualiser'))
    const heading = await screen.findByRole('heading', { name: /Nom1 Prenom1/ })
    await screen.findByRole('tablist')
    const close = heading.closest('.modal-content').querySelector('.btn-close')
    fireEvent.click(close)
    await settle()
    expect(screen.queryByRole('heading', { name: /Nom1 Prenom1/ })).not.toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 23 — exports liste de classe                                    */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — exports liste de classe (LOT 23)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
    stubBlobDownload()
  })

  it('exporte en PDF tous groupes et notifie', async () => {
    mount()
    await waitForTable()
    fireEvent.click(screen.getByRole('button', { name: /listes de classe pdf/i }))
    await waitFor(() =>
      expect(apiMock.getBlob).toHaveBeenCalledWith('/exports/participants/liste-classe/pdf/'),
    )
    expect(await screen.findByText('Listes de classe exportées (PDF) — tous les groupes')).toBeInTheDocument()
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('exporte en Excel en tenant compte du filtre de groupe', async () => {
    mount()
    await waitForTable()
    fireEvent.change(filterSelect('Tous (groupe)'), { target: { value: 'G1' } })
    await waitFor(() => expect(lastParams().get('groupe')).toBe('G1'))
    // Le libellé passe au singulier (« Liste de classe Excel »).
    fireEvent.click(screen.getByRole('button', { name: /^Liste de classe Excel/i }))
    await waitFor(() =>
      expect(apiMock.getBlob).toHaveBeenCalledWith('/exports/participants/liste-classe/excel/?groupe=G1'),
    )
    expect(await screen.findByText('Liste de classe exportée (EXCEL) — G1')).toBeInTheDocument()
  })

  it("notifie l'erreur remontée par le serveur d'export", async () => {
    mount()
    await waitForTable()
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'Génération impossible' } } })
    fireEvent.click(screen.getByRole('button', { name: /listes de classe pdf/i }))
    expect(await screen.findByText('Génération impossible')).toBeInTheDocument()
  })

  it("notifie un message générique quand l'erreur d'export n'a pas de détail", async () => {
    mount()
    await waitForTable()
    apiMock.getBlob.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: /listes de classe pdf/i }))
    expect(await screen.findByText('Erreur export liste de classe')).toBeInTheDocument()
  })

  it('reporte tous les filtres actifs dans la query string du export', async () => {
    mount()
    await waitForTable()
    fireEvent.change(screen.getByPlaceholderText(/nom, prénom, matricule/i), {
      target: { value: 'nom1' },
    })
    await waitFor(() => expect(lastParams().get('search')).toBe('nom1'))
    fireEvent.change(filterSelect('Tous (secrétariat)'), { target: { value: 'INJS Marcory' } })
    await waitFor(() => expect(lastParams().get('secretariat')).toBe('INJS Marcory'))
    fireEvent.change(filterSelect('Tous (sexe)'), { target: { value: 'MASCULIN' } })
    await waitFor(() => expect(lastParams().get('sexe')).toBe('MASCULIN'))

    fireEvent.click(screen.getByRole('button', { name: /listes de classe excel/i }))
    await waitFor(() => expect(apiMock.getBlob).toHaveBeenCalled())
    const path = apiMock.getBlob.mock.calls.at(-1)[0]
    expect(path.startsWith('/exports/participants/liste-classe/excel/?')).toBe(true)
    const q = new URL(path, 'http://testserver').searchParams
    expect(q.get('search')).toBe('nom1')
    expect(q.get('secretariat')).toBe('INJS Marcory')
    expect(q.get('sexe')).toBe('MASCULIN')
  })
})

/* ------------------------------------------------------------------ */
/* P00-06 — les capacités renvoyées par le backend font autorité       */
/* d'affichage : aucune action absente du contrat ne doit s'afficher,  */
/* y compris en contradiction avec le repli statique.                  */
/* ------------------------------------------------------------------ */

describe('pages/Participants.jsx — P00-06 (capacités backend)', () => {
  const mountWithCaps = (role, capacites) => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    const me = makeUser(role, { username: role.toLowerCase() })
    apiController.setMe(me)
    apiController.setRoute('/auth/capabilities/', {
      version: 1,
      role,
      roles: [role],
      niveau: 'N2',
      niveau_provisoire: true,
      capacites: { participants: [], exports: [], notes: [], ...capacites },
      perimetres: { niveaux: [], secretariats: [], formations: [], groupes: [] },
      role_context: {},
    })
    apiController.setRoute(LIST, listHandler)
    apiController.setRoute(REFS, referentiels)
    renderWithProviders(<Participants />, {
      authUser: me,
      initialEntries: ['/participants'],
      routePattern: '/participants',
    })
  }

  /** Attend que le contrat de capacités soit chargé ET appliqué au user du contexte. */
  const waitForCapacites = async () => {
    await waitFor(() =>
      expect(apiController.findCall('get', '/auth/capabilities/')).toBeDefined(),
    )
    await settle(3)
  }

  it('un SECRETARIAT limité à « lister » par le backend ne voit aucune action de gestion', async () => {
    // Le repli statique autorise pourtant gerer (FORMATEUR statique =
    // FORMATION_MUTATION_ROLES) : le contrat backend, plus restrictif, gagne.
    mountWithCaps('SECRETARIAT', { participants: ['lister'] })
    await waitForTable()
    await waitForCapacites()
    expect(screen.queryByRole('button', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /listes de classe pdf/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /listes de classe excel/i })).not.toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
    // La lecture (fiche) reste possible : l'action « lister » est bien présente.
    expect(within(row).getByTitle('Visualiser')).toBeInTheDocument()
  })

  it('un SECRETARIAT doté de « creer » par le backend voit le bouton de création (le backend peut accorder plus que le statique)', async () => {
    mountWithCaps('SECRETARIAT', { participants: ['creer', 'gerer', 'lister'], exports: ['liste_classe'], notes: ['gerer'] })
    await waitForTable()
    await waitForCapacites()
    expect(screen.getByRole('button', { name: /nouvel étudiant/i })).toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).getByTitle('Modifier')).toBeInTheDocument()
    expect(within(row).getByTitle('Supprimer')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /listes de classe pdf/i })).toBeInTheDocument()
  })

  it('FINANCE (participants absent du contrat) ne voit ni création ni gestion ni export', async () => {
    mountWithCaps('FINANCE', { participants: [], exports: [] })
    await waitForTable()
    await waitForCapacites()
    expect(screen.queryByRole('button', { name: /nouvel étudiant/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /listes de classe pdf/i })).not.toBeInTheDocument()
    const row = rowFor('Nom1 Prenom1')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
  })
})
