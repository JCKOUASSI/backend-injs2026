import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, fireEvent, within } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Modules from '@/pages/Modules'

const LABELS = {
  ADMIN: 'Administrateur', DIRECTION: 'Direction', CHEF_INJS_ADMIN: 'Chef INJS Admin',
  INJS_ADMIN: 'INJS Admin', CHEF_SECRETARIAT: 'Chef Secrétariat', SECRETARIAT: 'Secrétariat',
  FINANCE: 'Finance', ARCHIVE: 'Archiviste', ENCADRANT: 'Encadrant', SUPERVISEUR: 'Superviseur',
  FORMATEUR: 'Formateur', AUDITEUR: 'Étudiant',
}

const adminMe = () =>
  makeUser('ADMIN', {
    username: 'admin',
    role_context: {
      labels: LABELS,
      badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
      can_mutate_users: true,
      manageable_roles: ['ENCADRANT', 'FORMATEUR', 'AUDITEUR'],
      staff_filter_roles: ['FINANCE', 'ENCADRANT'],
    },
  })

/** Référentiels : les grades connus sont 1 et 2 ; toute autre valeur est invalide. */
const mountModules = (initialEntry = '/modules') => {
  apiController.setMe(adminMe())
  apiController.setRoute('/formations/referentiels/', () => ({
    formations: [],
    // formations_reelles non vide : l'effet référentiels ne lance pas le
    // chargement de secours /formations/list/?page_size=500.
    formations_reelles: [{ id: 1, formation: 'Formation 1' }],
    grades: [],
    grades_modules: [1, 2],
    categories: [],
    sites: [],
    batiments: [],
    salles: [],
    types_secretariat: [],
    vagues: [],
    groupes: [],
    modules: [],
  }))
  apiController.setRoute('/formations/list/', () => ({
    count: 0,
    total_pages: 1,
    results: [],
  }))
  return renderWithProviders(<Modules />, {
    authUser: adminMe(),
    initialEntries: [initialEntry],
    routePattern: '/modules',
  })
}

/** Équivalent test du `getTodayIso` interne de Modules.jsx (date locale, sans UTC). */
const getTodayIsoForTest = () => {
  const now = new Date()
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
}

/** Appels du chargement des modules (page_size=50), hors fallback référentiels. */
const moduleCalls = () =>
  apiMock.get.mock.calls
    .map(([p]) => p)
    .filter((p) => p.startsWith('/formations/list/') && p.includes('page_size=50'))
    .map((p) => new URL(p, 'http://testserver').searchParams)

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  window.sessionStorage.clear()
})

describe('pages/Modules.jsx — nettoyage des filtres obsolètes (§10.2 LOT 6)', () => {
  it('écarte un filtre grade absent des référentiels, recharge sans lui et notifie', async () => {
    // Lien obsolète : grade=999 ne figure dans aucun référentiel ; statut, lui,
    // est valide (STATUT_VALUES) et doit être conservé.
    mountModules('/modules?grade=999&statut=PLANIFIEE&date_mode=all')

    // Après l'arrivée des référentiels, la dernière requête modules ne porte
    // plus le grade invalide, tout en conservant le statut valide.
    await waitFor(() => {
      const calls = moduleCalls()
      expect(calls.length).toBeGreaterThan(0)
      const last = calls.at(-1)
      expect(last.get('grade')).toBe(null)
      expect(last.get('statut')).toBe('PLANIFIEE')
    })

    // L'utilisateur est informé du filtre écarté (message complet du toast).
    expect(
      await screen.findByText(/filtre\(s\) ignoré\(s\), valeur inconnue : grade/i),
    ).toBeInTheDocument()
  })

  it('ne touche pas aux filtres valides et n’affiche aucune alerte', async () => {
    mountModules('/modules?grade=2&statut=PLANIFIEE&date_mode=all')

    await waitFor(() => {
      const calls = moduleCalls()
      expect(calls.length).toBeGreaterThan(0)
      expect(calls.at(-1).get('grade')).toBe('2')
    })
    expect(screen.queryByText(/filtre\(s\) ignoré/i)).not.toBeInTheDocument()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// LOT 39 — Couverture fonctionnelle de pages/Modules.jsx : liste et états,
// filtres/pagination, permissions par rôle, CRUD module (création / édition /
// suppression), archivage à 3 confirmations et création de formation. Tests
// PURS (aucune modification de Modules.jsx dans ce lot).
// ════════════════════════════════════════════════════════════════════════════

/** Référentiels complets (toutes les listes déroulantes de la page). */
const REFS_RICHES = {
  // `formations` = intituliés du référentiel pédagogique (modale « Nouvelle
  // formation » ET filtre des modules proposés lors de la création).
  formations: [{ id: 1, intitule: 'Licence 1 LSF' }],
  formations_reelles: [
    { id: 10, formation: 'Licence 1 LSF' },
    { id: 11, formation: 'Licence 2 LSF' },
  ],
  grades: [
    { id: 1, libelle: 'A1' },
    { id: 2, libelle: 'A2' },
  ],
  grades_modules: [1, 2],
  categories: [],
  sites: [
    { id: 1, nom: 'Site Marcory' },
    { id: 2, nom: 'Site Cocody' },
  ],
  batiments: [
    { id: 1, nom: 'Bâtiment A', site_id: 1 },
    { id: 2, nom: 'Bâtiment B', site_id: 2 },
  ],
  salles: [
    { id: 1, nom: 'Salle 101', batiment_id: 1, site_id: 1 },
    { id: 3, nom: 'Salle 102', batiment_id: 1, site_id: 1 },
    { id: 2, nom: 'Salle 202', batiment_id: 2, site_id: 2 },
  ],
  types_secretariat: [{ id: 5, libelle: 'INJS Centre' }],
  vagues: [
    { id: 1, libelle: 'V2024' },
    { id: 2, libelle: 'V2025' },
  ],
  groupes: ['G1', 'G2'],
  modules: [
    { id: 100, intitule: 'Droit Administratif', volume_horaire: 40, formation_ids: [1] },
    { id: 101, intitule: 'Histoire des institutions', volume_horaire: 20, formation_ids: [] },
  ],
}

/** Une ligne par statut, avec des replis à exercer (grade/groupe/secrétariat/dates). */
const MODULES = [
  {
    id: 10, module_id: 100, module: 'Droit Administratif', formation: 'Licence 1 LSF', grade: 'A1',
    secretariat_nom: 'INJS Centre', groupe: 'G1', date_debut: '2026-09-01', date_fin: '2026-09-30',
    nb_participants: 25, statut: 'PLANIFIEE', archived: false,
  },
  {
    id: 10, module_id: 101, module: 'Droit du travail', formation: 'Licence 1 LSF', grade: 'A2',
    secretariat_nom: '', groupe: '', date_debut: '', date_fin: '',
    nb_participants: 0, statut: 'EN_COURS', archived: false,
  },
  {
    id: 11, module_id: 200, module: 'Lecture labiale', formation: 'Licence 2 LSF', grade: '',
    secretariat_nom: null, groupe: 'G2', date_debut: '2026-10-01', date_fin: null,
    nb_participants: 12, statut: 'TERMINEE', archived: false,
  },
  {
    id: 11, module_id: 201, module: 'Ancien stage', formation: 'Licence 2 LSF', grade: 'A1',
    secretariat_nom: 'INJS Marcory', groupe: 'G1', date_debut: '2025-01-10', date_fin: '2025-02-10',
    nb_participants: 8, statut: 'SUSPENDUE', archived: true,
  },
  {
    id: 11, module_id: 202, module: 'Module sans statut', formation: 'Licence 2 LSF', grade: 'A1',
    secretariat_nom: 'INJS Marcory', groupe: 'G1', date_debut: null, date_fin: null,
    nb_participants: 3, statut: 'INCONNU', archived: false,
  },
]

/** Réfs sans catalogue de modules → intitulé libre en champ texte à la création. */
const REFS_SANS_CATALOGUE = { ...REFS_RICHES, modules: [] }

const listParams = () =>
  apiMock.get.mock.calls
    .map(([p]) => p)
    .filter((p) => p.startsWith('/formations/list/') && p.includes('page_size=50'))
    .map((p) => new URL(p, 'http://testserver').searchParams)
const lastListParams = () => listParams().at(-1)

/** Routes LOT 39 : référentiels riches + liste paramétrable. */
function installModulesRoutes(opts = {}) {
  apiController.reset()
  window.localStorage.clear()
  window.sessionStorage.clear()
  const refs = opts.refs === undefined ? REFS_RICHES : opts.refs
  apiController.setRoute('/formations/referentiels/', () => {
    if (opts.refsError) throw Object.assign(new Error('refs KO'))
    return refs
  })
  apiController.setRoute('/formations/list/', (path) => {
    const q = new URL(path, 'http://testserver').searchParams
    if (q.get('page_size') === '500') {
      return opts.fallbackFormations ?? { results: [], count: 0 }
    }
    if (opts.listDeferred) return opts.listDeferred.p
    if (opts.listError) throw Object.assign(new Error('liste KO'))
    if (opts.listHandler) return opts.listHandler(q)
    const rows = opts.modules === undefined ? MODULES : opts.modules
    return opts.paginated ?? { count: rows.length, total_pages: 1, results: rows }
  })
  // Création d'une formation (la route exacte ne capture pas /formations/<id>/…).
  apiController.setRoute('/formations/', () => ({
    id: 99, formation: 'Cycle Spécial', intitule: 'Cycle Spécial',
  }))
}

const roleMe = (role, overrides = {}) => makeUser(role, { username: `u-${role.toLowerCase()}`, ...overrides })

const mountModulesRiche = (me = roleMe('ADMIN'), opts = {}) => {
  installModulesRoutes(opts)
  apiController.setMe(me)
  return renderWithProviders(<Modules />, {
    authUser: me,
    initialEntries: [opts.entry || '/modules'],
    routePattern: '/modules',
  })
}

const waitForList = async () => {
  await screen.findByText('Droit Administratif')
}

/** Retrouve un <select> de la barre de filtres via l'une de ses options. */
const filterSelect = (optionLabel) =>
  screen.getByRole('option', { name: optionLabel }).closest('select')

const getModal = (title) =>
  screen.getByRole('heading', { name: title }).closest('.modal-content')

// Les libellés des modales ne sont pas reliés par htmlFor : champ du même
// `.form-group` que le <label>.
const modalField = (modal, labelRegex) => {
  const label = within(modal).getByText(
    (content, el) => el.tagName === 'LABEL' && labelRegex.test(el.textContent),
  )
  return label.closest('.form-group').querySelector('input, select, textarea')
}

// ── Rendu de la liste, états et badges ───────────────────────────────────────
describe('pages/Modules.jsx (LOT 39) — liste, états de chargement et badges', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('rend les colonnes, les 5 modules, les badges de statut et les replis d’affichage', async () => {
    mountModulesRiche()
    await waitForList()

    expect(screen.getByText('Liste des cours')).toBeInTheDocument()
    expect(screen.getByText('5 module(s)')).toBeInTheDocument()
    for (const h of ['Modules', 'Formation', 'Grade', 'Secrétariat', 'Groupe', 'Dates', 'Étudiants', 'Statut', 'Actions']) {
      expect(screen.getByText(h)).toBeInTheDocument()
    }

    // Intitulés et formations.
    expect(screen.getByText('Droit du travail')).toBeInTheDocument()
    expect(screen.getAllByText('Licence 1 LSF').length).toBeGreaterThan(0)

    // Badges de statut (libellés français) + classe CSS associée, ciblés dans
    // leur ligne (le même libellé existe comme option du filtre de statut).
    const rowPlanifiee = screen.getByText('Droit Administratif').closest('tr')
    expect(within(rowPlanifiee).getByText('Planifié').className).toContain('badge-planifiee')
    expect(within(screen.getByText('Droit du travail').closest('tr')).getByText('En cours').className).toContain('badge-en-cours')
    expect(within(screen.getByText('Lecture labiale').closest('tr')).getByText('Terminé').className).toContain('badge-terminee')
    expect(within(screen.getByText('Ancien stage').closest('tr')).getByText('Suspendu').className).toContain('badge-suspendue')
    // Statut inconnu : le libellé brut est conservé avec le badge générique.
    expect(within(screen.getByText('Module sans statut').closest('tr')).getByText('INCONNU').className).toContain('badge-info')

    // Dates formatées JJ/MM/AAAA (deux fois 01/09/2026 et 30/09/2026).
    expect(screen.getByText('01/09/2026')).toBeInTheDocument()
    expect(screen.getByText('30/09/2026')).toBeInTheDocument()

    // Replis : grade absent → « — », secrétariat vide/null → « - », dates nulles → « - ».
    const rowSansGrade = screen.getByText('Lecture labiale').closest('tr')
    expect(within(rowSansGrade).getByText('—')).toBeInTheDocument()
    expect(within(rowSansGrade).getAllByText('-').length).toBeGreaterThan(0)
    const rowDroitTravail = screen.getByText('Droit du travail').closest('tr')
    expect(within(rowDroitTravail).getAllByText('-').length).toBeGreaterThan(0)
    // Nombre d’étudiants attendus (le libellé est dans le même td que le chiffre).
    expect(rowDroitTravail.textContent).toContain('0 attendus')
    expect(rowPlanifiee.textContent).toContain('25 attendus')
  })

  it('affiche le spinner puis la ligne « Aucun module trouvé » et le compteur 0', async () => {
    const deferred = { p: null, res: null }
    deferred.p = new Promise((resolve) => { deferred.res = resolve })
    mountModulesRiche(roleMe('ADMIN'), { listDeferred: deferred })

    // Pendant le chargement, le spinner de la carte liste est présent.
    const card = screen.getByText('Liste des cours').closest('.card')
    expect(card.querySelector('.spinner')).toBeInTheDocument()
    expect(screen.queryByText('Droit Administratif')).not.toBeInTheDocument()

    deferred.res({ count: 0, total_pages: 1, results: [] })
    expect(await screen.findByText('Aucun module trouvé')).toBeInTheDocument()
    expect(screen.getByText('0 module(s)')).toBeInTheDocument()
  })

  it('affiche le message d’erreur quand le chargement de la liste échoue', async () => {
    mountModulesRiche(roleMe('ADMIN'), { listError: true })
    expect(await screen.findByText('Erreur lors du chargement des modules')).toBeInTheDocument()
  })

  it('propose un lien Détail vers la fiche du module', async () => {
    mountModulesRiche()
    await waitForList()
    const row = screen.getByText('Droit Administratif').closest('tr')
    const link = within(row).getByTitle('Détail').closest('a')
    expect(link).toHaveAttribute('href', '/formations/10/modules/100')
  })
})

// ── Filtres, recherche et pagination ─────────────────────────────────────────
describe('pages/Modules.jsx (LOT 39) — recherche, filtres et pagination', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('recherche texte (debounce 400 ms) et réinitialise la page à 1', async () => {
    mountModulesRiche(roleMe('ADMIN'), {
      paginated: { count: 51, total_pages: 2, results: MODULES },
    })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    await waitFor(() => expect(lastListParams().get('page')).toBe('2'))

    fireEvent.change(screen.getByPlaceholderText('Rechercher un module ou une formation…'), {
      target: { value: 'droit' },
    })
    await waitFor(() => expect(lastListParams().get('search')).toBe('droit'))
    // La recherche repart toujours de la première page (l'appel porte page=1).
    expect(lastListParams().get('page')).toBe('1')
  })

  it('filtre par statut', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.change(filterSelect('Tous les statuts'), { target: { value: 'EN_COURS' } })
    await waitFor(() => expect(lastListParams().get('statut')).toBe('EN_COURS'))
  })

  it('filtre par secrétariat, vague, grade et groupe', async () => {
    mountModulesRiche()
    await waitForList()

    fireEvent.change(filterSelect('Tous les secrétariats'), { target: { value: '5' } })
    await waitFor(() => expect(lastListParams().get('secretariat_type')).toBe('5'))

    fireEvent.change(filterSelect('Toutes les vagues'), { target: { value: 'V2025' } })
    await waitFor(() => expect(lastListParams().get('vague')).toBe('V2025'))

    fireEvent.change(filterSelect('Tous les grades'), { target: { value: '1' } })
    await waitFor(() => expect(lastListParams().get('grade')).toBe('1'))

    fireEvent.change(filterSelect('Tous les groupes'), { target: { value: 'G2' } })
    await waitFor(() => expect(lastListParams().get('groupe')).toBe('G2'))
  })

  it('masque le filtre de secrétariat pour les rôles du périmètre secrétariat', async () => {
    mountModulesRiche(roleMe('SECRETARIAT'))
    await waitForList()
    expect(screen.queryByRole('option', { name: 'Tous les secrétariats' })).not.toBeInTheDocument()
    // Les autres filtres restent disponibles.
    expect(screen.getByRole('option', { name: 'Tous les statuts' })).toBeInTheDocument()
  })

  it('mode « Jour spécifique » : affiche le sélecteur de date et transmet date_mode + date', async () => {
    mountModulesRiche()
    await waitForList()
    expect(screen.queryByDisplayValue(getTodayIsoForTest())).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('option', { name: 'Jour spécifique' }).closest('select'), {
      target: { value: 'date' },
    })
    const dateInput = await screen.findByDisplayValue(getTodayIsoForTest())
    expect(dateInput).toBeInTheDocument()
    await waitFor(() => {
      expect(lastListParams().get('date_mode')).toBe('date')
      expect(lastListParams().get('date')).toBe(getTodayIsoForTest())
    })

    fireEvent.change(dateInput, { target: { value: '2026-03-15' } })
    await waitFor(() => expect(lastListParams().get('date')).toBe('2026-03-15'))
  })

  it('mode « Aujourd’hui » : transmet date_mode=today sans date', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.change(screen.getByRole('option', { name: "Aujourd'hui" }).closest('select'), {
      target: { value: 'today' },
    })
    await waitFor(() => {
      expect(lastListParams().get('date_mode')).toBe('today')
      expect(lastListParams().get('date')).toBe(null)
    })
  })

  it('pagine : 51 modules sur 2 pages, le clic sur la page 2 requête page=2', async () => {
    mountModulesRiche(roleMe('ADMIN'), {
      paginated: { count: 51, total_pages: 2, results: MODULES },
    })
    await waitForList()
    expect(screen.getByText('51 module(s)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Page suivante' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    await waitFor(() => expect(lastListParams().get('page')).toBe('2'))
  })

  it('corrige un mode de date invalide dans l’URL sans notifier (comme pour les filtres obsolètes)', async () => {
    mountModulesRiche(roleMe('ADMIN'), { entry: '/modules?date_mode=bogus' })
    await waitForList()
    await waitFor(() => expect(lastListParams().get('date_mode')).toBe('all'))
    expect(screen.queryByText(/filtre\(s\) ignoré/i)).not.toBeInTheDocument()
  })

  it('charge la liste de secours des formations si le référentiel n’a pas de formations réelles', async () => {
    const doublon = { id: 77, formation: 'Formation distante' }
    mountModulesRiche(roleMe('ADMIN'), {
      refs: { ...REFS_RICHES, formations_reelles: [] },
      fallbackFormations: {
        results: [doublon, { ...doublon }, { id: 78, formation: 'Autre formation' }],
        count: 3,
      },
    })
    await waitForList()
    const fallbackCall = apiMock.get.mock.calls
      .map(([p]) => p)
      .find((p) => p.startsWith('/formations/list/') && p.includes('page_size=500'))
    expect(fallbackCall).toBeTruthy()

    // Ouverture de la modale de création : le select liste les formations
    // dédupliquées (une seule entrée pour l'id 77).
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')
    const optionsFormation = within(modal).getAllByRole('option')
    expect(within(modal).getAllByRole('option', { name: 'Formation distante' })).toHaveLength(1)
    expect(within(modal).getByRole('option', { name: 'Autre formation' })).toBeInTheDocument()
    expect(optionsFormation.map((o) => o.value)).toContain('78')
  })
})

// ── Permissions par rôle ─────────────────────────────────────────────────────
describe('pages/Modules.jsx (LOT 39) — permissions par rôle', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('ADMIN : boutons Nouveau module, Modifier, Supprimer et Archiver présents', async () => {
    mountModulesRiche(roleMe('ADMIN'))
    await waitForList()
    expect(screen.getByRole('button', { name: /Nouveau module/ })).toBeInTheDocument()
    const row = screen.getByText('Droit Administratif').closest('tr')
    expect(within(row).getByTitle('Modifier')).toBeInTheDocument()
    expect(within(row).getByTitle('Supprimer')).toBeInTheDocument()
    expect(within(row).getByTitle('Archiver ce module (3 confirmations)')).toBeInTheDocument()
  })

  it('AUDITEUR : aucune action de mutation, seul le lien Détail reste visible', async () => {
    mountModulesRiche(roleMe('AUDITEUR'))
    await waitForList()
    expect(screen.queryByRole('button', { name: /Nouveau module/ })).not.toBeInTheDocument()
    const row = screen.getByText('Droit Administratif').closest('tr')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
    expect(within(row).queryByTitle(/Archiver/)).not.toBeInTheDocument()
    expect(within(row).getByTitle('Détail')).toBeInTheDocument()
  })

  it('DIRECTION : peut archiver mais ne peut pas créer, modifier ni supprimer', async () => {
    mountModulesRiche(roleMe('DIRECTION'))
    await waitForList()
    expect(screen.queryByRole('button', { name: /Nouveau module/ })).not.toBeInTheDocument()
    const row = screen.getByText('Droit Administratif').closest('tr')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
    expect(within(row).getByTitle('Archiver ce module (3 confirmations)')).toBeInTheDocument()
  })

  it('un module déjà archivé n’affiche pas le bouton Archiver', async () => {
    mountModulesRiche()
    await waitForList()
    const row = screen.getByText('Ancien stage').closest('tr')
    expect(within(row).queryByTitle(/Archiver/)).not.toBeInTheDocument()
  })

  it('le flag role_context.can_archive_modules donne le droit d’archivage à un rôle non listé', async () => {
    mountModulesRiche(roleMe('ENCADRANT', { role_context: { can_archive_modules: true } }))
    await waitForList()
    const row = screen.getByText('Droit Administratif').closest('tr')
    expect(within(row).getByTitle('Archiver ce module (3 confirmations)')).toBeInTheDocument()
  })
})

// ── Création et édition d'un module ──────────────────────────────────────────
describe('pages/Modules.jsx (LOT 39) — création et édition de modules', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('crée un module (POST) avec tous les champs, les dates vides en null et notifie', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: REFS_SANS_CATALOGUE })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')

    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '11' } })
    fireEvent.change(modalField(modal, /Intitulé du module/), { target: { value: 'Nouveau module test' } })
    fireEvent.change(modalField(modal, /^Grade/), { target: { value: 'A2' } })
    fireEvent.change(modalField(modal, /^Statut/), { target: { value: 'EN_COURS' } })
    fireEvent.change(modalField(modal, /^Groupe/), { target: { value: 'G3' } })
    fireEvent.change(modalField(modal, /^Vague/), { target: { value: 'V2025' } })
    fireEvent.change(modalField(modal, /Date début/), { target: { value: '2026-11-02' } })
    fireEvent.change(modalField(modal, /Date fin/), { target: { value: '2026-11-20' } })
    // Cascade site → bâtiment → salle.
    fireEvent.change(modalField(modal, /^Site/), { target: { value: 'Site Marcory' } })
    fireEvent.change(modalField(modal, /^Bâtiment/), { target: { value: 'Bâtiment A' } })
    fireEvent.change(modalField(modal, /^Salle/), { target: { value: 'Salle 101' } })
    fireEvent.change(modalField(modal, /Volume horaire/), { target: { value: '15' } })

    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/formations/11/modules/',
        expect.objectContaining({
          intitule: 'Nouveau module test',
          grade: 'A2',
          groupe: 'G3',
          vague: 'V2025',
          statut: 'EN_COURS',
          date_debut: '2026-11-02',
          date_fin: '2026-11-20',
          site: 'Site Marcory',
          batiment: 'Bâtiment A',
          salle: 'Salle 101',
          duree_prevue_heures: '15',
        }),
      ),
    )
    expect(await screen.findByText('Module créé')).toBeInTheDocument()
    // La modale se referme et la liste est rechargée.
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouveau module' })).not.toBeInTheDocument())
    expect(listParams().length).toBeGreaterThan(1)
  })

  it('envoie null pour les dates vides et 0 pour un volume horaire absent', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: REFS_SANS_CATALOGUE })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')
    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '11' } })
    fireEvent.change(modalField(modal, /Intitulé du module/), { target: { value: 'Module minimal' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    const [url, body] = apiMock.post.mock.calls.at(-1)
    expect(url).toBe('/formations/11/modules/')
    expect(body.date_debut).toBeNull()
    expect(body.date_fin).toBeNull()
    expect(body.duree_prevue_heures).toBe(0)
  })

  it('propose les modules du référentiel pour la formation choisie et pré-remplit le volume horaire', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')

    // La formation 10 correspond à l'intitulé référentiel « Licence 1 LSF »
    // (id référentiel 1) : l'intitulé devient une liste dérivée de refs.modules.
    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '10' } })
    const intituleField = modalField(modal, /Intitulé du module/)
    expect(intituleField.tagName).toBe('SELECT')
    fireEvent.change(intituleField, { target: { value: 'Droit Administratif' } })
    expect(modalField(modal, /Volume horaire/).value).toBe('40')
    // L'autre module référentiel n'est pas rattaché à cette formation.
    expect(within(modal).queryByRole('option', { name: 'Histoire des institutions' })).not.toBeInTheDocument()

    // La formation 11 n'a pas d'intitulé référentiel associé : TOUS les modules
    // référentiels sont proposés (aucun filtrage quand la correspondance échoue).
    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '11' } })
    const intituleField2 = modalField(modal, /Intitulé du module/)
    expect(intituleField2.tagName).toBe('SELECT')
    expect(within(modal).getByRole('option', { name: 'Histoire des institutions' })).toBeInTheDocument()
  })

  it('filtre les bâtiments puis les salles en cascade selon le site et le bâtiment choisis', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')

    const site = modalField(modal, /^Site/)
    const batiment = modalField(modal, /^Bâtiment/)
    const salle = modalField(modal, /^Salle/)
    // Avant sélection : les deux bâtiments et les trois salles sont proposés.
    expect(within(modal).getByRole('option', { name: 'Bâtiment A' })).toBeInTheDocument()
    expect(within(modal).getByRole('option', { name: 'Bâtiment B' })).toBeInTheDocument()

    fireEvent.change(site, { target: { value: 'Site Marcory' } })
    // Changer de site réinitialise bâtiment et salle ; le bâtiment B (Cocody) disparaît.
    expect(batiment.value).toBe('')
    expect(salle.value).toBe('')
    expect(within(modal).queryByRole('option', { name: 'Bâtiment B' })).not.toBeInTheDocument()

    fireEvent.change(batiment, { target: { value: 'Bâtiment A' } })
    expect(salle.value).toBe('')
    // Salles du bâtiment A uniquement.
    expect(within(modal).getByRole('option', { name: 'Salle 101' })).toBeInTheDocument()
    expect(within(modal).getByRole('option', { name: 'Salle 102' })).toBeInTheDocument()
    expect(within(modal).queryByRole('option', { name: 'Salle 202' })).not.toBeInTheDocument()
  })

  it('affiche les erreurs de validation du serveur sans fermer la modale', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: REFS_SANS_CATALOGUE })
    await waitForList()
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('bad'), {
        response: { data: { intitule: ['Ce module existe déjà.'], duree: ['Doit être positive.'] } },
      }),
    )
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')
    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '11' } })
    fireEvent.change(modalField(modal, /Intitulé du module/), { target: { value: 'Doublon' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    expect(await within(modal).findByText(/intitule: Ce module existe déjà\./i)).toBeInTheDocument()
    expect(within(modal).getByText(/duree: Doit être positive\./i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nouveau module' })).toBeInTheDocument()
  })

  it('affiche un message générique pour une erreur sans corps de validation', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: REFS_SANS_CATALOGUE })
    await waitForList()
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')
    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '11' } })
    fireEvent.change(modalField(modal, /Intitulé du module/), { target: { value: 'X' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    expect(await within(modal).findByText('Erreur lors de la sauvegarde')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nouveau module' })).toBeInTheDocument()
  })

  it('ouvre la modale d’édition pré-remplie (dates tranchées, valeurs) puis PATCH et notifie', async () => {
    mountModulesRiche()
    await waitForList()
    const row = screen.getByText('Droit Administratif').closest('tr')
    fireEvent.click(within(row).getByTitle('Modifier'))

    const modal = await screen.findByRole('heading', { name: 'Modifier le module' })
      .then((h) => h.closest('.modal-content'))
    expect(modalField(modal, /Intitulé du module/).value).toBe('Droit Administratif')
    expect(modalField(modal, /^Groupe/).value).toBe('G1')
    expect(modalField(modal, /Date début/).value).toBe('2026-09-01')
    expect(modalField(modal, /Date fin/).value).toBe('2026-09-30')
    // La formation n'est pas modifiable à l'édition (pas de select Formation).
    expect(within(modal).queryByText(/^Formation \*/)).not.toBeInTheDocument()

    fireEvent.change(modalField(modal, /Intitulé du module/), { target: { value: 'Droit Administratif avancé' } })
    fireEvent.change(modalField(modal, /^Statut/), { target: { value: 'TERMINEE' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith(
        '/formations/10/modules/100/',
        expect.objectContaining({ intitule: 'Droit Administratif avancé', statut: 'TERMINEE' }),
      ),
    )
    expect(await screen.findByText('Module modifié')).toBeInTheDocument()
  })

  it('retombe sur des champs texte libres pour grade/site/bâtiment/salle quand les référentiels sont vides', async () => {
    const refsLegeres = {
      ...REFS_SANS_CATALOGUE,
      grades: [], sites: [], batiments: [], salles: [],
    }
    mountModulesRiche(roleMe('ADMIN'), { refs: refsLegeres })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')
    fireEvent.change(modalField(modal, /^Formation/), { target: { value: '11' } })
    fireEvent.change(modalField(modal, /Intitulé du module/), { target: { value: 'Module manuel' } })

    const grade = modalField(modal, /^Grade/)
    const site = modalField(modal, /^Site/)
    const batiment = modalField(modal, /^Bâtiment/)
    const salle = modalField(modal, /^Salle/)
    expect(grade.tagName).toBe('INPUT')
    expect(site.tagName).toBe('INPUT')
    expect(batiment.tagName).toBe('INPUT')
    expect(salle.tagName).toBe('INPUT')
    fireEvent.change(grade, { target: { value: 'A3' } })
    fireEvent.change(site, { target: { value: 'Site manuel' } })
    fireEvent.change(batiment, { target: { value: 'Bâtiment manuel' } })
    fireEvent.change(salle, { target: { value: 'Salle manuelle' } })

    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/formations/11/modules/',
        expect.objectContaining({
          grade: 'A3',
          site: 'Site manuel',
          batiment: 'Bâtiment manuel',
          salle: 'Salle manuelle',
        }),
      ),
    )
  })

  it('ferme les modales par la croix et par un clic sur l’overlay (sans POST)', async () => {
    mountModulesRiche()
    await waitForList()

    // Croix de la modale module.
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    let modal = getModal('Nouveau module')
    fireEvent.click(within(modal).getByRole('button', { name: '×' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouveau module' })).not.toBeInTheDocument())

    // Clic directement sur l'overlay (hors contenu) de la modale module.
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    modal = getModal('Nouveau module')
    fireEvent.click(modal.closest('.modal-overlay'))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouveau module' })).not.toBeInTheDocument())

    // Double modale (module + formation) : l'overlay du dessus ferme seulement
    // la modale de formation, celle du module reste ouverte.
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: /créez-en une nouvelle/ }))
    const overlays = document.querySelectorAll('.modal-overlay')
    expect(overlays).toHaveLength(2)
    // La modale formation est rendue AVANT celle du module dans le DOM.
    fireEvent.click(overlays[0])
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouvelle formation' })).not.toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Nouveau module' })).toBeInTheDocument()
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('annule la création via le bouton Annuler (aucun POST, modale fermée)', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const modal = getModal('Nouveau module')
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouveau module' })).not.toBeInTheDocument())
    expect(apiMock.post).not.toHaveBeenCalled()
  })
})

// ── Création d'une formation depuis la modale module ─────────────────────────
describe('pages/Modules.jsx (LOT 39) — création d’une formation', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('crée la formation (POST), l’ajoute au select, la présélectionne et notifie', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    const moduleModal = getModal('Nouveau module')
    fireEvent.click(within(moduleModal).getByRole('button', { name: /créez-en une nouvelle/ }))

    const formationModal = getModal('Nouvelle formation')
    // refs.formations non vide : un select d'intitulés est proposé.
    const cycleField = modalField(formationModal, /^Formation \(cycle\)/)
    expect(cycleField.tagName).toBe('SELECT')
    fireEvent.change(cycleField, { target: { value: 'Licence 1 LSF' } })
    fireEvent.change(modalField(formationModal, /Premier module/), { target: { value: 'Module inaugural' } })
    fireEvent.click(within(formationModal).getByRole('button', { name: 'Créer' }))

    await waitFor(() =>
      // Lot B (lien D3) : l'intitulé choisi dans le référentiel des cycles est
      // automatiquement rattaché via ref_formation (id du cycle).
      expect(apiMock.post).toHaveBeenCalledWith('/formations/', {
        formation: 'Licence 1 LSF',
        module_input: 'Module inaugural',
        ref_formation: 1,
      }),
    )
    expect(await screen.findByText('Formation créée — vous pouvez y rattacher d’autres modules')).toBeInTheDocument()
    // La modale formation est fermée, celle du module reste ouverte avec l'id 99 présélectionné.
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouvelle formation' })).not.toBeInTheDocument())
    expect(screen.getByRole('heading', { name: 'Nouveau module' })).toBeInTheDocument()
    expect(modalField(getModal('Nouveau module'), /^Formation/).value).toBe('99')

    // Une réouverture conserve la dernière formation créée en présélection.
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: 'Annuler' }))
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    expect(modalField(getModal('Nouveau module'), /^Formation/).value).toBe('99')
  })

  it('propose un champ texte libre quand le référentiel n’a aucune formation', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: { ...REFS_RICHES, formations: [] } })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: /créez-en une nouvelle/ }))

    const formationModal = getModal('Nouvelle formation')
    const cycleField = modalField(formationModal, /^Formation \(cycle\)/)
    expect(cycleField.tagName).toBe('INPUT')
    fireEvent.change(cycleField, { target: { value: 'Formation des cadres' } })
    fireEvent.change(modalField(formationModal, /Premier module/), { target: { value: 'Droit public' } })
    fireEvent.click(within(formationModal).getByRole('button', { name: 'Créer' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/formations/', {
        formation: 'Formation des cadres',
        module_input: 'Droit public',
      }),
    )
  })

  it('affiche les erreurs de validation dans la modale de formation', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: { ...REFS_RICHES, formations: [] } })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: /créez-en une nouvelle/ }))
    const formationModal = getModal('Nouvelle formation')
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('bad'), { response: { data: { formation: ['Nom déjà utilisé.'] } } }),
    )
    fireEvent.change(modalField(formationModal, /^Formation \(cycle\)/), { target: { value: 'Cycle X' } })
    fireEvent.change(modalField(formationModal, /Premier module/), { target: { value: 'M1' } })
    fireEvent.click(within(formationModal).getByRole('button', { name: 'Créer' }))
    expect(await within(formationModal).findByText(/formation: Nom déjà utilisé\./i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nouvelle formation' })).toBeInTheDocument()
  })

  it('retombe sur un message générique pour une erreur réseau sans détail', async () => {
    mountModulesRiche(roleMe('ADMIN'), { refs: { ...REFS_RICHES, formations: [] } })
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: /créez-en une nouvelle/ }))
    const formationModal = getModal('Nouvelle formation')
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.change(modalField(formationModal, /^Formation \(cycle\)/), { target: { value: 'Cycle Y' } })
    fireEvent.change(modalField(formationModal, /Premier module/), { target: { value: 'M1' } })
    fireEvent.click(within(formationModal).getByRole('button', { name: 'Créer' }))
    expect(await within(formationModal).findByText('Erreur lors de la création')).toBeInTheDocument()
  })

  it('annule la création de formation (bouton Annuler et croix de fermeture)', async () => {
    mountModulesRiche()
    await waitForList()
    fireEvent.click(screen.getByRole('button', { name: /Nouveau module/ }))
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: /créez-en une nouvelle/ }))

    let formationModal = getModal('Nouvelle formation')
    fireEvent.click(within(formationModal).getByRole('button', { name: 'Annuler' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouvelle formation' })).not.toBeInTheDocument())
    expect(apiMock.post).not.toHaveBeenCalled()

    // Réouverture puis fermeture via la croix.
    fireEvent.click(within(getModal('Nouveau module')).getByRole('button', { name: /créez-en une nouvelle/ }))
    formationModal = getModal('Nouvelle formation')
    fireEvent.click(within(formationModal).getByRole('button', { name: '×' }))
    await waitFor(() =>
      expect(screen.queryByRole('heading', { name: 'Nouvelle formation' })).not.toBeInTheDocument())
  })
})

// ── Suppression ──────────────────────────────────────────────────────────────
describe('pages/Modules.jsx (LOT 39) — suppression d’un module', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  it('demande confirmation (message + caractère définitif), DELETE puis notifie et recharge', async () => {
    mountModulesRiche()
    await waitForList()
    const before = listParams().length
    const row = screen.getByText('Droit Administratif').closest('tr')
    fireEvent.click(within(row).getByTitle('Supprimer'))

    const modal = await screen.findByText('Cette action est définitive.').then((el) => el.closest('.modal-content'))
    expect(modal.textContent).toContain('Supprimer le module "Droit Administratif" ?')
    fireEvent.click(within(modal).getByRole('button', { name: 'Confirmer' }))

    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith('/formations/10/modules/100/'))
    expect(await screen.findByText('Module supprimé')).toBeInTheDocument()
    expect(listParams().length).toBe(before + 1)
  })

  it('l’annulation ne déclenche aucun DELETE', async () => {
    mountModulesRiche()
    await waitForList()
    const row = screen.getByText('Droit Administratif').closest('tr')
    fireEvent.click(within(row).getByTitle('Supprimer'))
    const modal = await screen.findByText('Cette action est définitive.').then((el) => el.closest('.modal-content'))
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    await waitFor(() =>
      expect(screen.queryByText('Cette action est définitive.')).not.toBeInTheDocument())
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it('en cas d’échec avec détail, affiche le détail renvoyé par le serveur', async () => {
    mountModulesRiche()
    await waitForList()
    apiMock.delete.mockRejectedValueOnce(
      Object.assign(new Error('forbidden'), { response: { data: { detail: 'Module utilisé par des séances' } } }),
    )
    const row = screen.getByText('Droit Administratif').closest('tr')
    fireEvent.click(within(row).getByTitle('Supprimer'))
    const modal = await screen.findByText('Cette action est définitive.').then((el) => el.closest('.modal-content'))
    fireEvent.click(within(modal).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Module utilisé par des séances')).toBeInTheDocument()
    expect(screen.queryByText('Module supprimé')).not.toBeInTheDocument()
  })

  it('en cas d’échec sans détail, affiche le message générique', async () => {
    mountModulesRiche()
    await waitForList()
    apiMock.delete.mockRejectedValueOnce(new Error('réseau'))
    const row = screen.getByText('Droit Administratif').closest('tr')
    fireEvent.click(within(row).getByTitle('Supprimer'))
    const modal = await screen.findByText('Cette action est définitive.').then((el) => el.closest('.modal-content'))
    fireEvent.click(within(modal).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Erreur lors de la suppression')).toBeInTheDocument()
  })
})

// ── Archivage (triple confirmation) ──────────────────────────────────────────
describe('pages/Modules.jsx (LOT 39) — archivage avec triple confirmation', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
  })

  const openArchive = async (moduleName = 'Droit Administratif') => {
    const row = screen.getByText(moduleName).closest('tr')
    fireEvent.click(within(row).getByTitle('Archiver ce module (3 confirmations)'))
    return screen.findByText(/étape 1\/3/).then((el) => el.closest('.modal-content'))
  }

  it('parcourt les 3 étapes, POST archive, notifie et recharge', async () => {
    mountModulesRiche()
    await waitForList()
    const before = listParams().length
    const modal = await openArchive()
    expect(modal.textContent).toContain('Droit Administratif')
    expect(modal.textContent).toContain('Archiver ce module ?')

    fireEvent.click(within(modal).getByRole('button', { name: 'Continuer' }))
    expect(await within(modal).findByText(/étape 2\/3/)).toBeInTheDocument()
    fireEvent.click(within(modal).getByRole('button', { name: 'Je comprends' }))
    expect(await within(modal).findByText(/étape 3\/3/)).toBeInTheDocument()
    fireEvent.click(within(modal).getByRole('button', { name: 'Archiver définitivement' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/formations/10/modules/100/archive/'))
    expect(await screen.findByText(/Module archivé/)).toBeInTheDocument()
    expect(listParams().length).toBe(before + 1)
  })

  it('l’annulation à la première étape ne déclenche aucun archivage', async () => {
    mountModulesRiche()
    await waitForList()
    const modal = await openArchive()
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    await waitFor(() => expect(screen.queryByText(/étape 1\/3/)).not.toBeInTheDocument())
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('en cas d’échec avec détail, notifie le détail ; sans détail, le message générique', async () => {
    mountModulesRiche()
    await waitForList()
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('ko'), { response: { data: { detail: 'Archivage bloqué' } } }),
    )
    let modal = await openArchive()
    fireEvent.click(within(modal).getByRole('button', { name: 'Continuer' }))
    fireEvent.click(within(modal).getByRole('button', { name: 'Je comprends' }))
    fireEvent.click(within(modal).getByRole('button', { name: 'Archiver définitivement' }))
    expect(await screen.findByText('Archivage bloqué')).toBeInTheDocument()

    // Second essai sans détail serveur.
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    modal = await openArchive()
    fireEvent.click(within(modal).getByRole('button', { name: 'Continuer' }))
    fireEvent.click(within(modal).getByRole('button', { name: 'Je comprends' }))
    fireEvent.click(within(modal).getByRole('button', { name: 'Archiver définitivement' }))
    expect(await screen.findByText("Erreur lors de l'archivage")).toBeInTheDocument()
  })
})
