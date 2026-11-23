import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within, fireEvent, act } from '@testing-library/react'
import { flushPromises } from '@/test/utils/async'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import { LIST_STORAGE_KEYS } from '@/utils/listFilters'
import Users from '@/pages/Users'

const PAGE_SIZE = 50
const LABELS = {
  ADMIN: 'Administrateur', DIRECTION: 'Direction', CHEF_INJS_ADMIN: 'Chef INJS Admin',
  INJS_ADMIN: 'INJS Admin', CHEF_SECRETARIAT: 'Chef Secrétariat', SECRETARIAT: 'Secrétariat',
  FINANCE: 'Finance', ARCHIVE: 'Archiviste', ENCADRANT: 'Encadrant', SUPERVISEUR: 'Superviseur',
  FORMATEUR: 'Formateur', AUDITEUR: 'Étudiant',
}

/* Jeu de données simulé, tel que renverrait le backend DRF (50/page). */
const mk = (id, role, { first, last, username, matricule }) => ({
  id, role, first_name: first, last_name: last, username,
  matricule: matricule || null, email: `${username}@injs.test`,
  telephone: '0700000000', is_active: true, secretariat_nom: null,
})

const staff = [
  ...Array.from({ length: 52 }, (_, i) =>
    mk(1000 + i, 'ENCADRANT', {
      first: `Encadrant ${i + 1}`, last: 'Kouassi', username: `enc${i + 1}`, matricule: `E${1000 + i}`,
    })),
  mk(2000, 'FINANCE', { first: 'Régis', last: 'Trésor', username: 'finance1', matricule: 'F2000' }),
  mk(2001, 'FINANCE', { first: 'Awa', last: 'Budget', username: 'finance2', matricule: 'F2001' }),
  mk(2002, 'FINANCE', { first: 'Karim', last: 'Solde', username: 'finance3', matricule: 'F2002' }),
]
const auditeurs = Array.from({ length: 5 }, (_, i) =>
  mk(3000 + i, 'AUDITEUR', { first: `Étudiant ${i + 1}`, last: 'Lmd', username: `aud${i + 1}`, matricule: `A${3000 + i}` }))
const formateurs = Array.from({ length: 4 }, (_, i) =>
  mk(4000 + i, 'FORMATEUR', { first: `Formateur ${i + 1}`, last: 'Peda', username: `form${i + 1}`, matricule: `FB${4000 + i}` }))

/** Endpoint paginé : reproduit le filtrage serveur selon la query string. */
const usersHandler = (path) => {
  const q = new URL(path, 'http://testserver').searchParams
  const page = Number(q.get('page') || 1)
  const search = (q.get('search') || '').toLowerCase()
  const role = q.get('role')

  let rows
  if (role === 'AUDITEUR') rows = auditeurs
  else if (role === 'FORMATEUR') rows = formateurs
  else {
    rows = staff // l'onglet personnel exclut déjà AUDITEUR/FORMATEUR (exclude_role)
    if (role) rows = rows.filter((u) => u.role === role)
  }
  if (search) {
    rows = rows.filter((u) =>
      [u.first_name, u.last_name, u.username, u.matricule, u.email]
        .filter(Boolean).some((v) => String(v).toLowerCase().includes(search)),
    )
  }

  const count = rows.length
  const start = (page - 1) * PAGE_SIZE
  const results = rows.slice(start, start + PAGE_SIZE)
  return { count, total_pages: Math.max(1, Math.ceil(count / PAGE_SIZE)), results }
}

const adminMe = () =>
  makeUser('ADMIN', {
    username: 'admin',
    role_context: {
      labels: LABELS,
      badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
      can_mutate_users: true,
      manageable_roles: [
        'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT', 'SECRETARIAT',
        'FINANCE', 'ARCHIVE', 'ENCADRANT', 'SUPERVISEUR', 'FORMATEUR', 'AUDITEUR',
      ],
      staff_filter_roles: ['FINANCE', 'ENCADRANT'],
    },
  })

const viewerMe = () => makeUser('SECRETARIAT', { username: 'sec', role_context: {} })

const mountUsers = (me = adminMe(), initialEntry = '/users') => {
  apiController.setMe(me)
  return renderWithProviders(<Users />, {
    authUser: me,
    initialEntries: [initialEntry],
    routePattern: '/users',
  })
}

const usersParams = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.startsWith('/auth/users/'))
    .map(([p]) => new URL(p, 'http://testserver').searchParams)
const lastUsersParams = () => usersParams().at(-1)
const waitForTable = () => waitFor(() => expect(screen.getByText(/sur \d+/)).toBeInTheDocument())

// Les libellés des modales ne sont pas reliés par htmlFor : on récupère le
// champ (input/select) appartenant au même .form-group que le <label>.
const getModal = (title) =>
  screen.getByRole('heading', { name: title }).closest('.modal-content')
const modalField = (modal, labelRegex) => {
  const label = within(modal).getByText(
    (_content, el) => el.tagName === 'LABEL' && labelRegex.test(el.textContent),
  )
  return label.closest('.form-group').querySelector('input, select, textarea')
}

describe('pages/Users.jsx — liste serveur (recherche, filtres, onglets, pagination)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(/^\/auth\/users\//, usersHandler)
  })

  it('charge la première page du personnel : plage, onglets, titre et requête initiale', async () => {
    mountUsers()
    await waitForTable()

    expect(screen.getByText('Liste des utilisateurs')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /utilisateurs/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /étudiants/i })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /enseignants/i })).toBeInTheDocument()

    // Première page : 50 lignes sur 55 personnel.
    expect(screen.getByText(/1.50 sur 55/)).toBeInTheDocument()
    expect(screen.getByText('50 résultat(s)')).toBeInTheDocument()
    expect(screen.getByText('Encadrant 1 Kouassi')).toBeInTheDocument()
    expect(screen.getByText('Encadrant 50 Kouassi')).toBeInTheDocument()
    expect(screen.queryByText('Encadrant 51 Kouassi')).not.toBeInTheDocument()

    const params = lastUsersParams()
    expect(params.get('page')).toBe('1')
    expect(params.get('exclude_role')).toBe('AUDITEUR,FORMATEUR')
    expect(params.get('search')).toBe(null)
  })

  it('navigue à la page suivante puis revient, avec les bons paramètres serveur', async () => {
    mountUsers()
    await waitForTable()

    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    await waitFor(() => expect(lastUsersParams().get('page')).toBe('2'))

    expect(screen.getByText(/51.55 sur 55/)).toBeInTheDocument()
    expect(screen.getByText('5 résultat(s)')).toBeInTheDocument()
    expect(screen.getByText('Encadrant 51 Kouassi')).toBeInTheDocument()
    expect(screen.getByText('Karim Solde')).toBeInTheDocument()
    expect(screen.queryByText('Encadrant 1 Kouassi')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /page précédente/i }))
    await waitFor(() => expect(lastUsersParams().get('page')).toBe('1'))
    expect(screen.getByText('Encadrant 1 Kouassi')).toBeInTheDocument()
  })

  it('applique la recherche avec debounce et réémet la requête en page 1', async () => {
    mountUsers()
    await waitForTable()

    fireEvent.change(screen.getByPlaceholderText(/rechercher par nom/i), { target: { value: 'karim' } })
    expect(screen.getByDisplayValue('karim')).toBeInTheDocument()

    // La requête n'est réémise qu'après le debounce (400 ms).
    await waitFor(() => expect(lastUsersParams().get('search')).toBe('karim'))
    expect(lastUsersParams().get('page')).toBe('1')
    expect(screen.getByText('Karim Solde')).toBeInTheDocument()
    expect(screen.getByText('1 résultat(s)')).toBeInTheDocument()
    expect(screen.queryByText('Encadrant 1 Kouassi')).not.toBeInTheDocument()
  })

  it('filtre le personnel par rôle via le menu déroulant', async () => {
    mountUsers()
    await waitForTable()

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'FINANCE' } })
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('FINANCE'))

    expect(screen.getByText('3 résultat(s)')).toBeInTheDocument()
    expect(screen.getByText('Régis Trésor')).toBeInTheDocument()
    expect(screen.getByText('Karim Solde')).toBeInTheDocument()
    expect(screen.queryByText('Encadrant 1 Kouassi')).not.toBeInTheDocument()
  })

  it("passe à l'onglet étudiants : reset page 1, role=AUDITEUR, pas d'exclude", async () => {
    mountUsers()
    await waitForTable()
    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    await waitFor(() => expect(lastUsersParams().get('page')).toBe('2'))

    fireEvent.click(screen.getByRole('tab', { name: /étudiants/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('AUDITEUR'))

    expect(lastUsersParams().get('page')).toBe('1')
    expect(lastUsersParams().get('exclude_role')).toBe(null)
    expect(screen.getAllByText('Comptes étudiants').length).toBeGreaterThan(0)
    expect(screen.getByText('5 résultat(s)')).toBeInTheDocument()
    expect(screen.getByText('Étudiant 1 Lmd')).toBeInTheDocument()
    expect(screen.queryByText('Tous les rôles')).not.toBeInTheDocument()
  })

  it("passe à l'onglet enseignants et requête role=FORMATEUR", async () => {
    mountUsers()
    await waitForTable()

    fireEvent.click(screen.getByRole('tab', { name: /enseignants/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('FORMATEUR'))

    expect(screen.getAllByText('Comptes enseignants').length).toBeGreaterThan(0)
    expect(screen.getByText('4 résultat(s)')).toBeInTheDocument()
    expect(screen.getByText('Formateur 1 Peda')).toBeInTheDocument()
  })

  it('persiste l’onglet courant dans l’URL / sessionStorage', async () => {
    mountUsers()
    await waitForTable()

    fireEvent.click(screen.getByRole('tab', { name: /étudiants/i }))
    await waitFor(() =>
      expect(window.sessionStorage.getItem(LIST_STORAGE_KEYS.users)).toContain('tab=auditeurs'),
    )
  })

  it('replie sur le seul onglet disponible quand l’URL demande un onglet interdit (§10.2 LOT 6)', async () => {
    // Utilisateur SANS gestion de comptes étudiants/enseignants mais avec un
    // filtre personnel : seule l'onglet « personnel » existe. Un lien obsolète
    // ?tab=auditeurs doit être ignoré (effet de repli sur les permissions).
    const personnelOnly = () =>
      makeUser('SECRETARIAT', {
        username: 'sec-limit',
        role_context: {
          labels: LABELS,
          badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
          staff_filter_roles: ['FINANCE'],
        },
      })

    mountUsers(personnelOnly(), '/users?tab=auditeurs')
    await waitForTable()

    // La requête finale est bien celle du personnel : pas de `tab`, avec
    // l'exclusion des comptes à badge, et jamais role=AUDITEUR.
    expect(lastUsersParams().get('tab')).toBe(null)
    expect(lastUsersParams().get('role')).toBe(null)
    expect(lastUsersParams().get('exclude_role')).toContain('AUDITEUR')
    // La barre d'onglets (Comptes étudiants/enseignants) n'est pas rendue.
    expect(screen.queryByRole('tab', { name: /étudiants/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('tab', { name: /enseignants/i })).not.toBeInTheDocument()
  })

  it('affiche un état vide quand aucun utilisateur ne correspond', async () => {
    mountUsers()
    await waitForTable()

    fireEvent.change(screen.getByPlaceholderText(/rechercher par nom/i), { target: { value: 'zzzz-introuvable' } })
    await waitFor(() => expect(lastUsersParams().get('search')).toBe('zzzz-introuvable'))

    expect(screen.getByText(/aucun utilisateur trouvé/i)).toBeInTheDocument()
    expect(screen.getByText('0 résultat(s)')).toBeInTheDocument()
  })

  it('affiche un message d’erreur formaté quand le chargement échoue', async () => {
    // Une route « qui lève » rejette la promesse du mock GET (async) : cela
    // simule une erreur HTTP sans toucher à l'implémentation du client.
    apiController.reset()
    const me = adminMe()
    apiController.setMe(me)
    apiController.setRoute(/^\/auth\/users\//, () => {
      throw Object.assign(new Error('boom'), { response: { data: { detail: 'Droits insuffisants' } } })
    })

    renderWithProviders(<Users />, { authUser: me, initialEntries: ['/users'], routePattern: '/users' })
    expect(await screen.findByText('Droits insuffisants')).toBeInTheDocument()
  })

  it('propose les actions de gestion à un gestionnaire (créer, modifier, supprimer)', async () => {
    mountUsers()
    await waitForTable()

    expect(screen.getByRole('button', { name: /nouvel utilisateur/i })).toBeInTheDocument()
    const row = screen.getByText('Encadrant 1 Kouassi').closest('tr')
    expect(within(row).getByTitle('Modifier')).toBeInTheDocument()
    expect(within(row).getByTitle('Supprimer')).toBeInTheDocument()
  })

  it('supprime un utilisateur après confirmation, notifie et recharge la liste', async () => {
    mountUsers()
    await waitForTable()

    const row = screen.getByText('Encadrant 1 Kouassi').closest('tr')
    fireEvent.click(within(row).getByTitle('Supprimer'))

    expect(await screen.findByText(/supprimer cet utilisateur/i)).toBeInTheDocument()
    const before = usersParams().length
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith('/auth/users/1000/'))
    expect(await screen.findByText('Utilisateur supprimé')).toBeInTheDocument()
    await waitFor(() => expect(usersParams().length).toBeGreaterThan(before))
  })

  it('masque les contrôles de gestion pour un utilisateur sans permission', async () => {
    mountUsers(viewerMe())
    await waitForTable()

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nouvel utilisateur/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Tous les rôles')).not.toBeInTheDocument()
    const row = screen.getByText('Encadrant 1 Kouassi').closest('tr')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(row).queryByTitle('Supprimer')).not.toBeInTheDocument()
  })

  it('crée un utilisateur personnel (POST) avec les champs requis et notifie', async () => {
    mountUsers()
    await waitForTable()

    fireEvent.click(screen.getByRole('button', { name: /nouvel utilisateur/i }))
    const modal = getModal('Nouvel utilisateur')

    fireEvent.change(modalField(modal, /nom d'utilisateur/i), { target: { value: 'newenc' } })
    fireEvent.change(modalField(modal, /^mot de passe/i), { target: { value: 'Secret-123' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/auth/users/',
        expect.objectContaining({ username: 'newenc', password: 'Secret-123', role: 'DIRECTION' }),
      ),
    )
    expect(await screen.findByText('Utilisateur créé')).toBeInTheDocument()
    // La modale se referme.
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Nouvel utilisateur' })).not.toBeInTheDocument())
  })

  it('affiche les erreurs de validation renvoyées par le serveur sans fermer la modale', async () => {
    mountUsers()
    await waitForTable()
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('bad'), { response: { data: { username: ['Ce nom d’utilisateur existe déjà.'] } } }),
    )

    fireEvent.click(screen.getByRole('button', { name: /nouvel utilisateur/i }))
    const modal = getModal('Nouvel utilisateur')
    fireEvent.change(modalField(modal, /nom d'utilisateur/i), { target: { value: 'doublon' } })
    fireEvent.change(modalField(modal, /^mot de passe/i), { target: { value: 'Secret-123' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    expect(await within(modal).findByText(/ce nom d’utilisateur existe déjà/i)).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nouvel utilisateur' })).toBeInTheDocument()
    expect(screen.queryByText('Utilisateur créé')).not.toBeInTheDocument()
  })

  it('modifie un utilisateur (PATCH), notamment le statut, et notifie', async () => {
    mountUsers()
    await waitForTable()

    const row = screen.getByText('Encadrant 1 Kouassi').closest('tr')
    fireEvent.click(within(row).getByTitle('Modifier'))

    const modal = await screen.findByRole('heading', { name: /modifier — enc1/i }).then((h) => h.closest('.modal-content'))
    fireEvent.change(modalField(modal, /^statut/i), { target: { value: 'false' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith(
        '/auth/users/1000/',
        expect.objectContaining({ role: 'ENCADRANT', is_active: false, username: 'enc1' }),
      ),
    )
    // Mot de passe laissé vide → non transmis.
    const payload = apiMock.patch.mock.calls.at(-1)[1]
    expect(payload).not.toHaveProperty('password')
    expect(await screen.findByText('Utilisateur modifié')).toBeInTheDocument()
  })

  it("crée un compte étudiant depuis l'onglet dédié (libellé et rôle adaptés)", async () => {
    mountUsers()
    await waitForTable()

    fireEvent.click(screen.getByRole('tab', { name: /étudiants/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('AUDITEUR'))

    fireEvent.click(screen.getByRole('button', { name: /nouveau compte étudiant/i }))
    const modal = getModal('Nouveau compte étudiant')
    fireEvent.change(modalField(modal, /nom d'utilisateur/i), { target: { value: 'newaud' } })
    fireEvent.change(modalField(modal, /^mot de passe/i), { target: { value: 'Secret-123' } })
    fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/auth/users/',
        expect.objectContaining({ username: 'newaud', role: 'AUDITEUR' }),
      ),
    )
    expect(await screen.findByText('Compte étudiant créé')).toBeInTheDocument()
  })
})

/* ================================================================== */
/* LOT 36 : complétion fonctionnelle de Users (CRUD, secrétariat,     */
/* éditions, suppressions, permissions dégradées).                    */
/* ================================================================== */

const NEW_USER_ID = 9001
const NEW_SEC_ID = 50
const SECRETARIATS = [
  { id: 10, nom: 'Secrétariat Abidjan', type: 'A' },
  { id: 11, nom: 'Secrétariat Bouaké', type: 'B' },
]

/** Utilisateur de liste, tel que renvoyé par la page paginée du backend. */
const cu = (id, over = {}) => ({
  id, role: 'ENCADRANT', username: `u${id}`,
  first_name: `Prenom${id}`, last_name: `Nom${id}`,
  matricule: `M${id}`, email: `u${id}@injs.test`,
  telephone: '0700000000', is_active: true,
  secretariat: null, secretariat_nom: null, ...over,
})

const rowForName = (fullName) => {
  // Pour un utilisateur sans prénom/nom, le nom de repli (= username) apparaît
  // deux fois : dans le <strong> de la 1re colonne et en 2e colonne Identifiant.
  const matches = screen.getAllByText(fullName)
  const strong = matches.find((el) => el.tagName === 'STRONG')
  return (strong || matches[0]).closest('tr')
}
const overlayNode = () => document.querySelector('.modal-overlay')

/**
 * Monte la page avec une route users combinée :
 * - GET : liste statique `rows` si fournie, sinon le handler paginé réel ;
 * - POST/PATCH : renvoie l'utilisateur avec un id stable (création à la
 *   volée de secrétariat), sans dépendre d'une route séparée.
 * La route secrétariats satisfait le hook React Query (GET) puis le POST.
 */
const setup = (me = adminMe(), opts = {}) => {
  apiController.setMe(me)
  const rows = opts.rows
  apiController.setRoute(/^\/auth\/users\//, (path, body) => {
    if (body !== undefined) return { data: { id: NEW_USER_ID, ...body }, status: 200 }
    if (rows) return { count: rows.length, total_pages: 1, results: rows }
    return usersHandler(path)
  })
  apiController.setRoute('/formations/secretariats/', (path, body) => (
    body === undefined ? SECRETARIATS : { data: { id: NEW_SEC_ID, ...body }, status: 200 }
  ))
  return renderWithProviders(<Users />, {
    authUser: me,
    initialEntries: [opts.initialEntry || '/users'],
    routePattern: '/users',
  })
}

const openCreate = async (trigger = /nouvel utilisateur/i) => {
  fireEvent.click(screen.getByRole('button', { name: trigger }))
  const h = await screen.findByRole('heading', { name: /nouvel utilisateur|nouveau compte/i })
  return h.closest('.modal-content')
}

const openEdit = async (fullName) => {
  fireEvent.click(within(rowForName(fullName)).getByTitle('Modifier'))
  const h = await screen.findByRole('heading', { name: /^modifier —/i })
  return h.closest('.modal-content')
}

/** Carte bleue « Ou créer un nouveau secrétariat », quand elle est rendue. */
const newSecCard = (modal) =>
  within(modal).getByText(/ou créer un nouveau secrétariat/i).closest('div')
const cardField = (card, exactLabel) => {
  const label = within(card).getByText(
    (_c, el) => el.tagName === 'LABEL' && el.textContent.trim() === exactLabel,
  )
  return label.closest('.form-group').querySelector('input, select')
}
const roleBadge = (fullName) =>
  rowForName(fullName).querySelector('td:nth-child(5) span.badge')

const waitForResults = (n) => screen.findByText(`${n} résultat(s)`)

const resetForLot36 = () => {
  apiController.reset()
  window.localStorage.clear()
  window.sessionStorage.clear()
}

describe('pages/Users.jsx — présentation de la liste, données dégradées et permissions (LOT 36)', () => {
  beforeEach(resetForLot36)

  it('affiche les replis "-", le username, les initiales de secours et le statut inactif', async () => {
    setup(adminMe(), {
      rows: [cu(1, {
        first_name: '', last_name: '', username: 'solo',
        matricule: null, email: null, telephone: null, is_active: false,
      })],
    })
    await waitForResults(1)

    // Nom complet absent -> repli sur le username (colonne nom + colonne identifiant).
    const occurrences = screen.getAllByText('solo')
    expect(occurrences.length).toBe(2)
    const row = occurrences[0].closest('tr')

    // Initiales construites depuis la première lettre du username.
    expect(row.querySelector('.prof-avatar').textContent).toBe('S')
    // Trois champs absents (matricule, e-mail, téléphone).
    expect(within(row).getAllByText('-').length).toBe(3)
    // Badge de statut inactif.
    const statut = within(row).getByText('Inactif')
    expect(statut).toHaveClass('badge-danger')
  })

  it('affiche le nom du secrétariat rattaché et le badge actif de succès', async () => {
    setup(adminMe(), {
      rows: [cu(2, { role: 'SECRETARIAT', secretariat_nom: 'Secrétariat Abidjan' })],
    })
    await waitForResults(1)
    const row = rowForName('Prenom2 Nom2')
    expect(within(row).getByText('Secrétariat Abidjan')).toBeInTheDocument()
    expect(within(row).getByText('Actif')).toHaveClass('badge-success')
  })

  it('choisit la classe de badge selon le rôle, avec repli badge-info pour un rôle inconnu', async () => {
    setup(adminMe(), {
      rows: [
        cu(3, { role: 'DIRECTION', first_name: 'Dir', last_name: 'A' }),
        cu(4, { role: 'CHEF_INJS_ADMIN', first_name: 'Chf', last_name: 'B' }),
        cu(5, { role: 'CHEF_SECRETARIAT', first_name: 'Chs', last_name: 'C' }),
        cu(6, { role: 'ARCHIVE', first_name: 'Arc', last_name: 'D' }),
        cu(7, { role: 'ROLE_BIDON', first_name: 'Bid', last_name: 'E' }),
      ],
    })
    await waitForResults(5)

    expect(roleBadge('Dir A')).toHaveClass('badge-direction')
    expect(roleBadge('Chf B')).toHaveClass('badge-dfrc')
    expect(roleBadge('Chs C')).toHaveClass('badge-secretariat')
    expect(roleBadge('Arc D')).toHaveClass('badge-info')
    // Rôle absent du dictionnaire et des libellés : classe de repli + clé brute.
    expect(roleBadge('Bid E')).toHaveClass('badge-info')
    expect(roleBadge('Bid E').textContent).toBe('ROLE_BIDON')
  })

  it('remplace CPFAE par INJS dans les libellés de rôle renvoyés par le backend', async () => {
    const me = makeUser('ADMIN', {
      username: 'cpfaadmin',
      role_context: {
        labels: { ...LABELS, INJS_ADMIN: 'Administrateur CPFAE' },
        badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
        can_mutate_users: true,
        manageable_roles: ['INJS_ADMIN', 'ENCADRANT'],
        staff_filter_roles: [],
      },
    })
    setup(me, { rows: [cu(8, { role: 'INJS_ADMIN', first_name: 'Cpf', last_name: 'X' })] })
    await waitForResults(1)
    // Le remplacement vaut pour le badge de la ligne (le libellé est aussi dans le filtre).
    expect(roleBadge('Cpf X').textContent).toBe('Administrateur INJS')
  })

  it("n'offre modifier/supprimer que sur les lignes dont le rôle est gérable", async () => {
    setup(adminMe(), {
      rows: [
        cu(9, { role: 'ADMIN', first_name: 'Admi', last_name: 'G' }),
        cu(10, { role: 'ENCADRANT', first_name: 'Gera', last_name: 'H' }),
      ],
    })
    await waitForResults(2)

    const rowAdmin = rowForName('Admi G')
    expect(within(rowAdmin).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(rowAdmin).queryByTitle('Supprimer')).not.toBeInTheDocument()

    const rowEncadrant = rowForName('Gera H')
    expect(within(rowEncadrant).getByTitle('Modifier')).toBeInTheDocument()
    expect(within(rowEncadrant).getByTitle('Supprimer')).toBeInTheDocument()
  })

  it("se replie sur l'onglet personnel sans aucun contrôle quand le role_context est vide", async () => {
    const naked = makeUser('DIRECTION', { username: 'nu', role_context: {} })
    setup(naked, { rows: [cu(11, { first_name: 'Lec', last_name: 'Ture' })] })
    await waitForResults(1)

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nouvel/i })).not.toBeInTheDocument()
    expect(screen.queryByText('Tous les rôles')).not.toBeInTheDocument()
    expect(screen.getByText('Liste des utilisateurs')).toBeInTheDocument()
    // Les lignes restent lisibles mais sans action.
    const row = rowForName('Lec Ture')
    expect(within(row).queryByTitle('Modifier')).not.toBeInTheDocument()
    // Repli des rôles à badge pour l'exclusion serveur.
    expect(lastUsersParams().get('exclude_role')).toBe('AUDITEUR,FORMATEUR')
  })

  it("n'affiche pas de bouton de création si le gestionnaire n'a aucun rôle maniable", async () => {
    const me = makeUser('ADMIN', {
      username: 'emptyadmin',
      role_context: { labels: LABELS, can_mutate_users: true },
    })
    setup(me, { rows: [cu(12)] })
    await waitForResults(1)
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nouvel/i })).not.toBeInTheDocument()
  })

  it("replie le filtre de rôles du personnel sur les rôles maniables quand staff_filter_roles est absent", async () => {
    const me = makeUser('ADMIN', {
      username: 'mgr',
      role_context: {
        labels: LABELS,
        badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
        can_mutate_users: true,
        manageable_roles: ['FINANCE', 'ENCADRANT', 'SECRETARIAT', 'CHEF_SECRETARIAT'],
      },
    })
    setup(me)
    await waitForTable()
    const filtre = screen.getByRole('combobox')
    expect(within(filtre).getByRole('option', { name: 'Secrétariat' })).toBeInTheDocument()
    expect(within(filtre).getByRole('option', { name: 'Finance' })).toBeInTheDocument()
  })

  it("conserve le filtre de rôle quand on reclique sur l'onglet personnel, puis le vide en revenant d'un autre onglet", async () => {
    setup(adminMe())
    await waitForTable()

    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'FINANCE' } })
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('FINANCE'))

    // Cliquer sur l'onglet déjà courant (personnel) ne touche pas au filtre.
    fireEvent.click(screen.getByRole('tab', { name: /utilisateurs/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('FINANCE'))

    // Aller aux étudiants vide le filtre ; revenir au personnel ne le restaure pas.
    fireEvent.click(screen.getByRole('tab', { name: /étudiants/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('AUDITEUR'))
    fireEvent.click(screen.getByRole('tab', { name: /utilisateurs/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe(null))
  })

  it("replie sur l'onglet étudiants quand c'est le seul onglet disponible, même avec une URL personnel", async () => {
    // Couvre le cas où l'effet de repli sélectionne l'id d'un onglet existant
    // (et non le défaut 'personnel') : gestionnaire sans rôle staff, étudiants seuls.
    const me = makeUser('ADMIN', {
      username: 'audonly',
      role_context: {
        labels: LABELS,
        badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
        can_mutate_users: true,
        manageable_roles: ['AUDITEUR'],
      },
    })
    setup(me)
    // Le premier rendu (user en cours de résolution) charge le personnel ; après
    // réception du me, l'effet de repli bascule sur le seul onglet étudiants.
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('AUDITEUR'))

    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /nouveau compte étudiant/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nouvel utilisateur/i })).not.toBeInTheDocument()
  })

  it("réarme la page 1 quand on change le filtre de rôle depuis la page 2", async () => {
    setup(adminMe())
    await waitForTable()

    fireEvent.click(screen.getByRole('button', { name: 'Page 2' }))
    await waitFor(() => expect(lastUsersParams().get('page')).toBe('2'))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'FINANCE' } })
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('FINANCE'))
    expect(lastUsersParams().get('page')).toBe('1')
  })
})

describe('pages/Users.jsx — création de comptes (LOT 36)', () => {
  beforeEach(resetForLot36)

  const fillCreate = (modal, { username, password: pw, first, last, matricule, email, telephone, role, secretariat }) => {
    if (first !== undefined) fireEvent.change(modalField(modal, /^prénom/i), { target: { value: first } })
    if (last !== undefined) fireEvent.change(modalField(modal, /^nom$/i), { target: { value: last } })
    if (username !== undefined) fireEvent.change(modalField(modal, /nom d'utilisateur/i), { target: { value: username } })
    if (matricule !== undefined) fireEvent.change(modalField(modal, /matricule|badge/i), { target: { value: matricule } })
    if (email !== undefined) fireEvent.change(modalField(modal, /adresse e-mail/i), { target: { value: email } })
    if (telephone !== undefined) fireEvent.change(modalField(modal, /^téléphone/i), { target: { value: telephone } })
    if (role !== undefined) fireEvent.change(modalField(modal, /^rôle/i), { target: { value: role } })
    if (secretariat !== undefined) fireEvent.change(modalField(modal, /^secrétariat$/i), { target: { value: secretariat } })
    if (pw !== undefined) fireEvent.change(modalField(modal, /^mot de passe/i), { target: { value: pw } })
  }
  const submitCreate = (modal) => fireEvent.click(within(modal).getByRole('button', { name: 'Créer' }))
  const postBodies = (path) =>
    apiMock.post.mock.calls.filter(([p]) => p === path).map(([, body]) => body)

  it("crée un compte enseignant depuis l'onglet dédié : badge, note, rôle et notification", async () => {
    setup(adminMe())
    await waitForTable()

    fireEvent.click(screen.getByRole('tab', { name: /enseignants/i }))
    await waitFor(() => expect(lastUsersParams().get('role')).toBe('FORMATEUR'))

    const modal = await openCreate(/nouveau compte enseignant/i)
    expect(within(modal).getByText('N° badge enseignant')).toBeInTheDocument()
    expect(within(modal).getByPlaceholderText('Ex. F0042')).toBeInTheDocument()
    expect(within(modal).getByText(/doit correspondre au n° badge de l'enseignant/i)).toBeInTheDocument()

    fillCreate(modal, { username: 'newform', password: 'Secret-123' })
    submitCreate(modal)

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/auth/users/',
        expect.objectContaining({ username: 'newform', role: 'FORMATEUR' }),
      ),
    )
    expect(postBodies('/auth/users/')[0]).not.toHaveProperty('secretariat')
    expect(await screen.findByText('Compte enseignant créé')).toBeInTheDocument()
  })

  it('crée un personnel FINANCE avec tous les champs facultatifs remplis', async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, {
      first: 'Awa', last: 'Budget', username: 'awa2', matricule: 'X1',
      email: 'awa2@injs.test', telephone: '0799000000', role: 'FINANCE', password: 'Secret-123',
    })
    submitCreate(modal)

    await waitFor(() => expect(postBodies('/auth/users/')).toHaveLength(1))
    expect(postBodies('/auth/users/')[0]).toEqual({
      username: 'awa2', first_name: 'Awa', last_name: 'Budget', email: 'awa2@injs.test',
      matricule: 'X1', role: 'FINANCE', password: 'Secret-123', telephone: '0799000000',
    })
    expect(await screen.findByText('Utilisateur créé')).toBeInTheDocument()
  })

  it('rattache le nouveau SECRETARIAT à un secrétariat existant sans créer de structure', async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { username: 'secnew', password: 'Secret-123', role: 'SECRETARIAT' })

    // La carte de création à la volée est proposée tant qu'aucun secrétariat n'est choisi.
    expect(within(modal).getByText(/ou créer un nouveau secrétariat/i)).toBeInTheDocument()
    await within(modal).findByRole('option', { name: 'Secrétariat Abidjan' })
    fillCreate(modal, { secretariat: '10' })

    // Le choix d'un secrétariat existant fait disparaître la carte.
    expect(within(modal).queryByText(/ou créer un nouveau secrétariat/i)).not.toBeInTheDocument()
    submitCreate(modal)

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/auth/users/',
        expect.objectContaining({ role: 'SECRETARIAT', secretariat: '10' }),
      ),
    )
    expect(postBodies('/formations/secretariats/')).toHaveLength(0)
    expect(apiMock.patch).not.toHaveBeenCalled()
    expect(await screen.findByText('Utilisateur créé')).toBeInTheDocument()
  })

  it('crée un secrétariat à la volée (nom + type), le rattache au compte et met le cache à jour', async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    await within(modal).findByRole('option', { name: 'Secrétariat Abidjan' })
    fillCreate(modal, { username: 'secvol', password: 'Secret-123', role: 'SECRETARIAT' })
    const card = newSecCard(modal)
    fireEvent.change(cardField(card, 'Nom'), { target: { value: 'Secrétariat Neuf' } })
    fireEvent.change(cardField(card, 'Type'), { target: { value: 'B' } })
    submitCreate(modal)

    // 1) le compte est créé sans rattachement, sans clés de création à la volée ;
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/auth/users/',
        expect.objectContaining({ username: 'secvol', role: 'SECRETARIAT' }),
      ),
    )
    const userBody = postBodies('/auth/users/')[0]
    expect(userBody).not.toHaveProperty('secretariat')
    expect(userBody).not.toHaveProperty('new_secretariat_nom')
    // 2) le secrétariat est créé avec le nouvel utilisateur comme responsable ;
    expect(apiMock.post).toHaveBeenCalledWith('/formations/secretariats/', {
      nom: 'Secrétariat Neuf', type: 'B', responsable: NEW_USER_ID,
    })
    // 3) le compte est rattaché au secrétariat créé.
    expect(apiMock.patch).toHaveBeenCalledWith(`/auth/users/${NEW_USER_ID}/`, { secretariat: NEW_SEC_ID })

    // Ordre des opérations : user -> secrétariat -> rattachement.
    const posts = apiMock.post.mock.calls
    const iUser = posts.findIndex(([p]) => p === '/auth/users/')
    const iSec = posts.findIndex(([p]) => p === '/formations/secretariats/')
    expect(iSec).toBe(iUser + 1)
    expect(apiMock.patch.mock.invocationCallOrder[0]).toBeGreaterThan(
      apiMock.post.mock.invocationCallOrder[iSec])

    expect(await screen.findByText('Utilisateur créé')).toBeInTheDocument()

    // Le cache React Query des secrétariats contient désormais la nouvelle structure.
    const modal2 = await openCreate()
    fillCreate(modal2, { role: 'SECRETARIAT' })
    expect(await within(modal2).findByRole('option', { name: 'Secrétariat Neuf' })).toBeInTheDocument()
  })

  it("transmet un type vide quand le secrétariat à la volée est créé sans type choisi", async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { username: 'secnotype', password: 'Secret-123', role: 'SECRETARIAT' })
    fireEvent.change(cardField(newSecCard(modal), 'Nom'), { target: { value: 'Sec Sans Type' } })
    submitCreate(modal)

    await waitFor(() => expect(postBodies('/formations/secretariats/')).toHaveLength(1))
    expect(postBodies('/formations/secretariats/')[0]).toEqual({
      nom: 'Sec Sans Type', type: '', responsable: NEW_USER_ID,
    })
  })

  it("ne crée pas de secrétariat à la volée si le nom n'est pas renseigné", async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { username: 'secseul', password: 'Secret-123', role: 'SECRETARIAT' })
    submitCreate(modal)

    await waitFor(() => expect(postBodies('/auth/users/')).toHaveLength(1))
    expect(postBodies('/formations/secretariats/')).toHaveLength(0)
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it("réinitialise nom et type du secrétariat à la volée quand le rôle change", async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { role: 'SECRETARIAT' })
    const card = newSecCard(modal)
    fireEvent.change(cardField(card, 'Nom'), { target: { value: 'Poubelle' } })
    fireEvent.change(cardField(card, 'Type'), { target: { value: 'A' } })

    // Quitter le rôle SECRETARIAT puis y revenir : les champs sont repartis à zéro.
    fillCreate(modal, { role: 'FINANCE' })
    expect(within(modal).queryByText(/ou créer un nouveau secrétariat/i)).not.toBeInTheDocument()
    fillCreate(modal, { role: 'SECRETARIAT' })
    const card2 = newSecCard(modal)
    expect(cardField(card2, 'Nom')).toHaveValue('')
    expect(cardField(card2, 'Type')).toHaveValue('')
  })

  it("masque le rattachement et la création de secrétariat pour un gestionnaire lui-même secrétariat", async () => {
    const me = makeUser('SECRETARIAT', {
      username: 'secmgr',
      role_context: {
        labels: LABELS,
        badge_account_roles: ['AUDITEUR', 'FORMATEUR'],
        can_mutate_users: true,
        manageable_roles: ['ENCADRANT', 'FINANCE', 'SECRETARIAT'],
        staff_filter_roles: ['ENCADRANT'],
      },
    })
    setup(me, { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { role: 'SECRETARIAT' })
    expect(within(modal).queryByText(/ou créer un nouveau secrétariat/i)).not.toBeInTheDocument()
    expect(
      within(modal).queryByText((_c, el) => el.tagName === 'LABEL' && /^secrétariat$/i.test(el.textContent)),
    ).toBeNull()
  })

  it("signale qu'un Chef INJS Admin existe déjà dès qu'on choisit ce rôle en création", async () => {
    setup(adminMe(), { rows: [cu(20, { role: 'CHEF_INJS_ADMIN', first_name: 'Chef', last_name: 'Installe' })] })
    await waitForResults(1)

    const modal = await openCreate()
    expect(within(modal).queryByText(/rôle est unique/i)).not.toBeInTheDocument()
    fillCreate(modal, { role: 'CHEF_INJS_ADMIN' })
    expect(await within(modal).findByText(/un chef injs admin existe déjà/i)).toBeInTheDocument()
    fillCreate(modal, { role: 'DIRECTION' })
    expect(within(modal).queryByText(/rôle est unique/i)).not.toBeInTheDocument()
  })

  it("signale qu'un secrétariat a déjà un chef, et seulement pour ce secrétariat", async () => {
    setup(adminMe(), {
      rows: [cu(21, { role: 'CHEF_SECRETARIAT', secretariat: 10, first_name: 'Chef', last_name: 'Dix' })],
    })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { role: 'CHEF_SECRETARIAT' })
    await within(modal).findByRole('option', { name: 'Secrétariat Abidjan' })
    fillCreate(modal, { secretariat: '10' })
    expect(within(modal).getByText(/ce secrétariat a déjà un chef secrétariat/i)).toBeInTheDocument()
    fillCreate(modal, { secretariat: '11' })
    expect(within(modal).queryByText(/ce secrétariat a déjà un chef secrétariat/i)).not.toBeInTheDocument()
  })

  it("remplace CPFAE par INJS dans les erreurs de création renvoyées par le serveur", async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('bad'), { response: { data: { detail: 'Accès CPFAE refusé' } } }),
    )

    const modal = await openCreate()
    fillCreate(modal, { username: 'x1', password: 'Secret-123' })
    submitCreate(modal)
    expect(await within(modal).findByText('Accès INJS refusé')).toBeInTheDocument()
  })

  it("affiche le message générique quand la création échoue sans réponse serveur", async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))

    const modal = await openCreate()
    fillCreate(modal, { username: 'x2', password: 'Secret-123' })
    submitCreate(modal)
    expect(await within(modal).findByText("Erreur lors de la création de l'utilisateur.")).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Nouvel utilisateur' })).toBeInTheDocument()
  })

  it("passe le bouton en Création... pendant l'envoi puis le réactive", async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    const modal = await openCreate()
    fillCreate(modal, { username: 'x3', password: 'Secret-123' })
    let resolvePost
    apiMock.post.mockImplementationOnce(() => new Promise((res) => { resolvePost = () => res({ data: { id: 77 } }) }))
    submitCreate(modal)
    expect(within(modal).getByRole('button', { name: 'Création...' })).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(4) })
    expect(await screen.findByText('Utilisateur créé')).toBeInTheDocument()
  })

  it('ferme la modale de création par la croix, Annuler ou le voile, sans appel, et réinitialise le formulaire', async () => {
    setup(adminMe(), { rows: [cu(1)] })
    await waitForResults(1)

    let modal = await openCreate()
    fireEvent.change(modalField(modal, /nom d'utilisateur/i), { target: { value: 'oublie' } })
    fireEvent.click(within(modal).getByText('×'))
    expect(screen.queryByRole('heading', { name: 'Nouvel utilisateur' })).not.toBeInTheDocument()

    // Réouverture : la saisie précédente a été effacée (formulaire réinitialisé après succès comme annulation).
    modal = await openCreate()
    expect(modalField(modal, /nom d'utilisateur/i)).toHaveValue('')
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    expect(overlayNode()).toBeNull()

    modal = await openCreate()
    fireEvent.click(overlayNode())
    expect(overlayNode()).toBeNull()
    expect(apiMock.post).not.toHaveBeenCalled()
  })
})

describe('pages/Users.jsx — édition d\'un utilisateur (LOT 36)', () => {
  beforeEach(resetForLot36)

  const fillEdit = (modal, { username, password: pw, first, last, matricule, email, telephone, role, secretariat, statut }) => {
    if (first !== undefined) fireEvent.change(modalField(modal, /^prénom/i), { target: { value: first } })
    if (last !== undefined) fireEvent.change(modalField(modal, /^nom$/i), { target: { value: last } })
    if (username !== undefined) fireEvent.change(modalField(modal, /nom d'utilisateur/i), { target: { value: username } })
    if (matricule !== undefined) fireEvent.change(modalField(modal, /^n° matricule/i), { target: { value: matricule } })
    if (email !== undefined) fireEvent.change(modalField(modal, /adresse e-mail/i), { target: { value: email } })
    if (telephone !== undefined) fireEvent.change(modalField(modal, /^téléphone/i), { target: { value: telephone } })
    if (role !== undefined) fireEvent.change(modalField(modal, /^rôle$/i), { target: { value: role } })
    if (secretariat !== undefined) fireEvent.change(modalField(modal, /^secrétariat$/i), { target: { value: secretariat } })
    if (statut !== undefined) fireEvent.change(modalField(modal, /^statut/i), { target: { value: statut } })
    if (pw !== undefined) fireEvent.change(modalField(modal, /nouveau mot de passe/i), { target: { value: pw } })
  }
  const submitEdit = (modal) => fireEvent.click(within(modal).getByRole('button', { name: 'Enregistrer' }))

  it('pré-remplit la modale avec toutes les données, y compris secrétariat et statut inactif', async () => {
    setup(adminMe(), {
      rows: [cu(30, {
        role: 'SECRETARIAT', secretariat: 10, is_active: false, username: 'sec30',
        first_name: 'Mariam', last_name: 'Diallo', matricule: 'M30',
        email: 'sec30@injs.test', telephone: '0711000000',
      })],
    })
    await waitForResults(1)

    const modal = await openEdit('Mariam Diallo')
    expect(within(modal).getByRole('heading', { name: 'Modifier — sec30' })).toBeInTheDocument()
    expect(modalField(modal, /nom d'utilisateur/i)).toHaveValue('sec30')
    expect(modalField(modal, /^prénom/i)).toHaveValue('Mariam')
    expect(modalField(modal, /^nom$/i)).toHaveValue('Diallo')
    expect(modalField(modal, /^n° matricule/i)).toHaveValue('M30')
    expect(modalField(modal, /adresse e-mail/i)).toHaveValue('sec30@injs.test')
    expect(modalField(modal, /^téléphone/i)).toHaveValue('0711000000')
    expect(modalField(modal, /^rôle$/i)).toHaveValue('SECRETARIAT')
    expect(modalField(modal, /^secrétariat$/i)).toHaveValue('10')
    expect(modalField(modal, /^statut/i)).toHaveValue('false')
    expect(modalField(modal, /nouveau mot de passe/i)).toHaveValue('')
  })

  it('gère les utilisateurs renvoyés sans prénom, nom, matricule, e-mail ni téléphone', async () => {
    setup(adminMe(), {
      rows: [cu(31, {
        role: 'FINANCE', username: 'nu31', first_name: '', last_name: '',
        matricule: null, email: null, telephone: null,
      })],
    })
    await waitForResults(1)

    // Nom complet de repli et initiale depuis le username.
    const [nom] = screen.getAllByText('nu31')
    const row = nom.closest('tr')
    expect(within(row).getAllByText('-').length).toBe(3)
    expect(row.querySelector('.prof-avatar').textContent).toBe('N')

    const modal = await openEdit('nu31')
    expect(modalField(modal, /nom d'utilisateur/i)).toHaveValue('nu31')
    expect(modalField(modal, /^prénom/i)).toHaveValue('')
    expect(modalField(modal, /^nom$/i)).toHaveValue('')
    expect(modalField(modal, /^n° matricule/i)).toHaveValue('')
    expect(modalField(modal, /adresse e-mail/i)).toHaveValue('')
    expect(modalField(modal, /^téléphone/i)).toHaveValue('')
    // Absence de is_active côté backend -> considéré actif.
    expect(modalField(modal, /^statut/i)).toHaveValue('true')
  })

  it('gère un utilisateur sans username à l’ouverture de la modale (valeur de repli)', async () => {
    // Le rôle reste gérable (sinon les boutons d'édition n'existent pas, cf. le
    // filet « rôle protégé ») ; seul le username est absent côté backend.
    setup(adminMe(), { rows: [cu(40, { username: '', first_name: 'Sans', last_name: 'Identite' })] })
    await waitForResults(1)

    const modal = await openEdit('Sans Identite')
    // Le titre utilise editingUser.username : chaîne vide, sans planter.
    expect(within(modal).getByRole('heading', { name: 'Modifier —' })).toBeInTheDocument()
    expect(modalField(modal, /nom d'utilisateur/i)).toHaveValue('')
  })

  it('envoie une édition complète avec nouveau mot de passe et rattachement à un secrétariat', async () => {
    setup(adminMe(), {
      rows: [cu(32, { role: 'FINANCE', username: 'fin32', first_name: 'Fin', last_name: 'TrenteDeux' })],
    })
    await waitForResults(1)

    const modal = await openEdit('Fin TrenteDeux')
    fillEdit(modal, {
      username: 'fin32b', first: 'Awa', last: 'Yao', matricule: 'Z9',
      email: 'new@injs.test', telephone: '0722000000', statut: 'false',
      role: 'SECRETARIAT', secretariat: '11', password: 'New-1234',
    })
    submitEdit(modal)

    await waitFor(() => expect(apiMock.patch).toHaveBeenCalled())
    expect(apiMock.patch).toHaveBeenCalledWith('/auth/users/32/', {
      username: 'fin32b', first_name: 'Awa', last_name: 'Yao', email: 'new@injs.test',
      matricule: 'Z9', role: 'SECRETARIAT', telephone: '0722000000',
      is_active: false, password: 'New-1234', secretariat: '11',
    })
    expect(await screen.findByText('Utilisateur modifié')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: /^modifier — /i })).not.toBeInTheDocument()
  })

  it('affiche les erreurs de validation (avec CPFAE->INJS) puis le message générique, sans fermer', async () => {
    setup(adminMe(), { rows: [cu(33, { first_name: 'Err', last_name: 'Edit' })] })
    await waitForResults(1)

    const modal = await openEdit('Err Edit')
    apiMock.patch.mockRejectedValueOnce(
      Object.assign(new Error('bad'), { response: { data: { detail: 'Compte CPFAE verrouillé' } } }),
    )
    submitEdit(modal)
    expect(await within(modal).findByText('Compte INJS verrouillé')).toBeInTheDocument()

    apiMock.patch.mockRejectedValueOnce(new Error('réseau'))
    submitEdit(modal)
    expect(await within(modal).findByText("Erreur lors de la modification de l'utilisateur.")).toBeInTheDocument()
    expect(within(modal).getByRole('heading', { name: /^modifier — /i })).toBeInTheDocument()
  })

  it('ferme la modale d\'édition par la croix, Annuler ou le voile, sans aucun PATCH', async () => {
    setup(adminMe(), { rows: [cu(34, { username: 'fer34', first_name: 'Close', last_name: 'Me' })] })
    await waitForResults(1)

    let modal = await openEdit('Close Me')
    fireEvent.click(modal.querySelector('.btn-close'))
    expect(overlayNode()).toBeNull()

    modal = await openEdit('Close Me')
    fireEvent.click(within(modal).getByRole('button', { name: 'Annuler' }))
    expect(overlayNode()).toBeNull()

    modal = await openEdit('Close Me')
    fireEvent.click(overlayNode())
    expect(overlayNode()).toBeNull()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it("signale en édition qu'un Chef INJS Admin existe déjà (en excluant l'utilisateur édité)", async () => {
    setup(adminMe(), {
      rows: [
        cu(35, { username: 'cand35', first_name: 'Cand', last_name: 'Idat' }),
        cu(36, { role: 'CHEF_INJS_ADMIN', username: 'lechef', first_name: 'Le', last_name: 'Chef' }),
      ],
    })
    await waitForResults(2)

    const modal = await openEdit('Cand Idat')
    expect(within(modal).queryByText(/rôle est unique/i)).not.toBeInTheDocument()
    fillEdit(modal, { role: 'CHEF_INJS_ADMIN' })
    expect(within(modal).getByText(/un chef injs admin existe déjà/i)).toBeInTheDocument()
  })

  it("signale en édition qu'un secrétariat a déjà un chef, et lève l'alerte en changeant de secrétariat", async () => {
    setup(adminMe(), {
      rows: [
        cu(37, { role: 'SECRETARIAT', secretariat: 10, username: 'sec37', first_name: 'Sec', last_name: 'Dix' }),
        cu(38, { role: 'CHEF_SECRETARIAT', secretariat: 10, username: 'chef10', first_name: 'Chef', last_name: 'Dix' }),
      ],
    })
    await waitForResults(2)

    const modal = await openEdit('Sec Dix')
    // En passant le rôle à Chef Secrétariat, le secrétariat 10 est déjà pourvu.
    fillEdit(modal, { role: 'CHEF_SECRETARIAT' })
    expect(within(modal).getByText(/ce secrétariat a déjà un chef secrétariat/i)).toBeInTheDocument()
    fillEdit(modal, { secretariat: '11' })
    expect(within(modal).queryByText(/ce secrétariat a déjà un chef secrétariat/i)).not.toBeInTheDocument()
  })

  it("passe le bouton en Enregistrement... pendant l'envoi puis le réactive", async () => {
    setup(adminMe(), { rows: [cu(39, { first_name: 'Wait', last_name: 'Ing' })] })
    await waitForResults(1)

    const modal = await openEdit('Wait Ing')
    let resolvePatch
    apiMock.patch.mockImplementationOnce(() => new Promise((res) => { resolvePatch = () => res({ data: {} }) }))
    submitEdit(modal)
    expect(within(modal).getByRole('button', { name: 'Enregistrement...' })).toBeDisabled()
    await act(async () => { resolvePatch(); await flushPromises(4) })
    expect(await screen.findByText('Utilisateur modifié')).toBeInTheDocument()
  })
})

describe('pages/Users.jsx — suppression confirmée (LOT 36)', () => {
  beforeEach(resetForLot36)

  const askDelete = async (fullName) => {
    fireEvent.click(within(rowForName(fullName)).getByTitle('Supprimer'))
    await screen.findByText('Supprimer cet utilisateur ?')
    return document.querySelector('.modal-overlay')
  }

  it('affiche le message et le détail, et annule sans appel DELETE', async () => {
    setup(adminMe(), { rows: [cu(50, { first_name: 'Poub', last_name: 'Elle' })] })
    await waitForResults(1)

    const boite = await askDelete('Poub Elle')
    expect(within(boite).getByText('Supprimer cet utilisateur ?')).toBeInTheDocument()
    expect(within(boite).getByText('Cette action est définitive.')).toBeInTheDocument()
    fireEvent.click(within(boite).getByRole('button', { name: 'Annuler' }))
    expect(overlayNode()).toBeNull()
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it("régression §10.14 (LOT 37) : réécrit CPFAE en INJS dans le toast d'erreur de suppression comme partout ailleurs", async () => {
    // Avant le LOT 37, le toast d'erreur de suppression affichait le message
    // serveur brut ; il applique désormais le même rebranding CPFAE -> INJS que
    // les libellés de rôle et les alertes des modales création/édition.
    setup(adminMe(), { rows: [cu(51, { first_name: 'Sup', last_name: 'Prime' })] })
    await waitForResults(1)
    apiMock.delete.mockRejectedValueOnce(
      Object.assign(new Error('forbidden'), { response: { data: { detail: 'Compte CPFAE protégé' } } }),
    )

    const boite = await askDelete('Sup Prime')
    fireEvent.click(within(boite).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Compte INJS protégé')).toBeInTheDocument()
    expect(screen.queryByText('Compte CPFAE protégé')).not.toBeInTheDocument()
  })

  it('notifie le message générique quand la suppression échoue sans réponse serveur', async () => {
    setup(adminMe(), { rows: [cu(52, { first_name: 'Sup', last_name: 'Reseau' })] })
    await waitForResults(1)
    apiMock.delete.mockRejectedValueOnce(new Error('réseau'))

    const boite = await askDelete('Sup Reseau')
    fireEvent.click(within(boite).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Erreur lors de la suppression.')).toBeInTheDocument()
    expect(apiMock.delete).toHaveBeenCalledWith('/auth/users/52/')
  })
})
