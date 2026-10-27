/**
 * LOT 40 — Scolarité : liste des maquettes pédagogiques LMD
 * (`pages/scolarite/Maquettes.jsx`), qui n'avait aucun test dédié.
 *
 * Chargement et états de la liste, filtre par statut, référentiels de
 * création (années / formations / niveaux), création d'une maquette (IDs
 * convertis en nombres), permissions `canActScolarite`, workflow
 * valider / activer / archiver / cloner sous confirmation, et tous les
 * chemins d'erreur. Tests PURS (aucune modification de la page).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, waitFor, fireEvent, within, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Maquettes from '@/pages/scolarite/Maquettes'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

const ANNEES = [
  { id: 1, libelle: '2025-2026' },
  { id: 2, libelle: '2026-2027' },
]
const FORMATIONS_REF = [
  { id: 10, intitule: 'Licence 1 LSF' },
  { id: 11, intitule: 'Licence 2 LSF' },
]
const NIVEAUX = [
  { id: 3, code: 'L1' },
  { id: 4, code: 'L2' },
]

const MAQUETTES = [
  {
    id: 1, ref_formation: 'Licence 1 LSF', niveau: 'Licence 1', parcours: 'LSF',
    annee_academique: '2025-2026', version: 1, statut: 'BROUILLON', nb_ue: 5, total_credits: 30,
  },
  {
    id: 2, ref_formation: 'Licence 2 LSF', niveau: 'Licence 2', parcours: '',
    annee_academique: '2025-2026', version: 2, statut: 'VALIDEE', nb_ue: 8, total_credits: 60,
  },
  {
    id: 3, ref_formation: 'Master LSF', niveau: 'Master 1', parcours: 'Recherche',
    annee_academique: '2026-2027', version: 1, statut: 'ACTIVE', nb_ue: 10, total_credits: 60,
  },
  {
    id: 4, ref_formation: 'Vieux cursus', niveau: 'Licence 3', parcours: 'Reprise',
    annee_academique: '2024-2025', version: 3, statut: 'ARCHIVEE', nb_ue: 6, total_credits: 40,
  },
  {
    id: 5, ref_formation: 'Cursus bizarre', niveau: 'Licence 1', parcours: 'Beta',
    annee_academique: '2026-2027', version: 1, statut: 'INCONNU', nb_ue: 0, total_credits: 0,
  },
]

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const LIST_PATH = '/scolarite/maquettes/'
const listCalls = () => apiMock.get.mock.calls.filter(([p]) => p === LIST_PATH)
const actionPosts = () =>
  apiMock.post.mock.calls.filter(([p]) => /^\/scolarite\/maquettes\/\d+\/(valider|activer|archiver|cloner)\//.test(p))

/** Routes standard : liste + 3 référentiels. */
function installRoutes(opts = {}) {
  apiController.reset()
  window.localStorage.clear()
  window.sessionStorage.clear()
  apiController.setRoute(LIST_PATH, () => {
    if (opts.listError) throw Object.assign(new Error('liste KO'), { response: { data: { error: 'Liste cassée' } } })
    if (opts.listDeferred) return opts.listDeferred.p
    return opts.list === undefined ? MAQUETTES : opts.list
  })
  apiController.setRoute('/scolarite/ref/annees/', () => {
    if (opts.refsError) throw new Error('refs KO')
    return ANNEES
  })
  apiController.setRoute('/scolarite/ref/formations/', () => {
    if (opts.refsError) throw new Error('refs KO')
    return FORMATIONS_REF
  })
  apiController.setRoute('/scolarite/ref/niveaux/', () => {
    if (opts.refsError) throw new Error('refs KO')
    return NIVEAUX
  })
  apiController.setRoute('/scolarite/maquettes/creer/', () => {
    if (opts.creerError) throw opts.creerError
    return opts.creerResponse ?? { version: 1 }
  })
}

const mount = (role = 'ADMIN', opts = {}) => {
  installRoutes(opts)
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<Maquettes />, {
    authUser: me,
    routePattern: '/scolarite/maquettes',
    initialEntries: ['/scolarite/maquettes'],
  })
}

// La formation apparaît aussi comme option du sélecteur de création : on
// passe par le lien du tableau (colonne Formation).
const rowOf = (formation) => screen.getByRole('link', { name: formation }).closest('tr')
const selectByPlaceholder = (optionLabel) =>
  screen.getByRole('option', { name: optionLabel }).closest('select')

beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})
afterEach(() => {
  vi.restoreAllMocks()
})

/* ------------------------------------------------------------------ */
/* Liste, états et filtre                                               */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Maquettes.jsx (LOT 40) — liste, états et filtre', () => {
  it('rend le titre, les colonnes et toutes les maquettes avec liens, badges et replis', async () => {
    mount()
    expect(await screen.findByText('Maquettes pédagogiques LMD')).toBeInTheDocument()

    for (const h of ['Formation', 'Niveau', 'Parcours', 'Année', 'Version', 'Statut', 'UE', 'Crédits', 'Actions']) {
      expect(screen.getByText(h)).toBeInTheDocument()
    }

    // Lien vers le détail.
    expect(screen.getByRole('link', { name: 'Licence 1 LSF' })).toHaveAttribute('href', '/scolarite/maquettes/1')

    // Versions, UE, crédits.
    const row1 = rowOf('Licence 1 LSF')
    expect(within(row1).getByText('v1')).toBeInTheDocument()
    expect(within(row1).getByText('5')).toBeInTheDocument()
    expect(within(row1).getByText('30')).toBeInTheDocument()

    // Parcours vide → repli « — ».
    expect(within(rowOf('Licence 2 LSF')).getByText('—')).toBeInTheDocument()

    // Classes de badge par statut.
    expect(within(rowOf('Licence 1 LSF')).getByText('BROUILLON').className).toContain('text-bg-secondary')
    expect(within(rowOf('Licence 2 LSF')).getByText('VALIDEE').className).toContain('text-bg-info')
    expect(within(rowOf('Master LSF')).getByText('ACTIVE').className).toContain('text-bg-success')
    expect(within(rowOf('Vieux cursus')).getByText('ARCHIVEE').className).toContain('text-bg-dark')
    // Statut inconnu : badge secondaire générique.
    expect(within(rowOf('Cursus bizarre')).getByText('INCONNU').className).toContain('text-bg-secondary')
  })

  it('affiche le spinner pendant le chargement puis « Aucune maquette. »', async () => {
    const deferred = { p: null }
    deferred.p = new Promise((resolve) => { deferred.res = resolve })
    mount('ADMIN', { listDeferred: deferred })
    expect(document.querySelector('.spinner-border')).toBeInTheDocument()
    deferred.res([])
    expect(await screen.findByText('Aucune maquette.')).toBeInTheDocument()
  })

  it('notifie une erreur de chargement avec le détail du serveur', async () => {
    mount('ADMIN', { listError: true })
    expect(await screen.findByText('Liste cassée')).toBeInTheDocument()
  })

  it('filtre par statut : le rappel porte le paramètre statut et la liste est rechargée', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    const avant = listCalls().length

    fireEvent.change(selectByPlaceholder('Validées'), { target: { value: 'VALIDEE' } })

    await waitFor(() => expect(listCalls()).toHaveLength(avant + 1))
    const [, config] = listCalls().at(-1)
    expect(config.params).toEqual({ statut: 'VALIDEE' })

    // Repasser à « Tous les statuts » recharge sans paramètre statut.
    fireEvent.change(selectByPlaceholder('Tous les statuts'), { target: { value: '' } })
    await waitFor(() => {
      const [, cfg] = listCalls().at(-1)
      expect(cfg.params).toEqual({})
    })
  })
})

/* ------------------------------------------------------------------ */
/* Permissions et référentiels                                          */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Maquettes.jsx (LOT 40) — permissions et référentiels', () => {
  it('un rôle non habilité voit la liste mais pas la création ni les actions (et ne charge pas les référentiels)', async () => {
    mount('AUDITEUR')
    await screen.findByText('Licence 1 LSF')

    expect(screen.queryByText('Nouvelle maquette')).not.toBeInTheDocument()
    expect(screen.queryByText('Actions')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Valider' })).not.toBeInTheDocument()
    // Les référentiels de création ne sont chargés que si l'on peut agir.
    const refsCalls = apiMock.get.mock.calls.filter(([p]) => p.startsWith('/scolarite/ref/'))
    expect(refsCalls).toHaveLength(0)
  })

  it('un administrateur charge les 3 référentiels et les expose dans les sélecteurs', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    expect(screen.getByRole('option', { name: '2026-2027' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Licence 2 LSF' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'L2' })).toBeInTheDocument()
  })

  it("un échec des référentiels notifie 'Chargement des référentiels impossible.'", async () => {
    mount('ADMIN', { refsError: true })
    expect(await screen.findByText('Chargement des référentiels impossible.')).toBeInTheDocument()
    // La liste, elle, reste disponible.
    expect(await screen.findByText('Licence 1 LSF')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* Création                                                             */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Maquettes.jsx (LOT 40) — création', () => {
  it('crée une maquette (IDs numériques + libellé), notifie, réinitialise et recharge', async () => {
    mount('ADMIN', { creerResponse: { version: 4 } })
    await screen.findByText('Licence 1 LSF')
    const avant = listCalls().length

    fireEvent.change(selectByPlaceholder('Année académique…'), { target: { value: '2' } })
    fireEvent.change(selectByPlaceholder('Formation…'), { target: { value: '11' } })
    fireEvent.change(selectByPlaceholder('Niveau…'), { target: { value: '4' } })
    fireEvent.change(screen.getByPlaceholderText('Libellé (optionnel)'), { target: { value: 'Parcours renforcé' } })

    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/scolarite/maquettes/creer/', {
        annee_academique_id: 2,
        ref_formation_id: 11,
        niveau_id: 4,
        libelle: 'Parcours renforcé',
      }),
    )
    expect(await screen.findByText('Maquette v4 créée en brouillon.')).toBeInTheDocument()
    // Formulaire réinitialisé et liste rechargée.
    expect(selectByPlaceholder('Année académique…').value).toBe('')
    expect(screen.getByPlaceholderText('Libellé (optionnel)').value).toBe('')
    expect(listCalls().length).toBe(avant + 1)
  })

  it('envoie une chaîne vide pour un libellé absent', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    fireEvent.change(selectByPlaceholder('Année académique…'), { target: { value: '1' } })
    fireEvent.change(selectByPlaceholder('Formation…'), { target: { value: '10' } })
    fireEvent.change(selectByPlaceholder('Niveau…'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    const [, body] = apiMock.post.mock.calls.at(-1)
    expect(body.annee_academique_id).toBe(1)
    expect(body.libelle).toBe('')
  })

  it('convertit les IDs des sélecteurs en nombres dans le corps de création', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    // Les valeurs de <select> sont des chaînes : le handler doit les convertir.
    fireEvent.change(selectByPlaceholder('Année académique…'), { target: { value: '2' } })
    fireEvent.change(selectByPlaceholder('Formation…'), { target: { value: '11' } })
    fireEvent.change(selectByPlaceholder('Niveau…'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    const [, body] = apiMock.post.mock.calls.at(-1)
    expect(typeof body.ref_formation_id).toBe('number')
    expect(typeof body.niveau_id).toBe('number')
    expect(body).toMatchObject({ annee_academique_id: 2, ref_formation_id: 11, niveau_id: 4 })
  })

  it('affiche l’erreur détaillée du serveur à la création', async () => {
    mount('ADMIN', {
      creerError: Object.assign(new Error('ko'), { response: { data: { error: 'Doublon de maquette.' } } }),
    })
    await screen.findByText('Licence 1 LSF')
    fireEvent.change(selectByPlaceholder('Année académique…'), { target: { value: '1' } })
    fireEvent.change(selectByPlaceholder('Formation…'), { target: { value: '10' } })
    fireEvent.change(selectByPlaceholder('Niveau…'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))

    expect(await screen.findByText('Doublon de maquette.')).toBeInTheDocument()
    expect(screen.queryByText(/créée en brouillon/)).not.toBeInTheDocument()
  })

  it('retombe sur le message générique sans détail serveur', async () => {
    mount('ADMIN', { creerError: new Error('réseau') })
    await screen.findByText('Licence 1 LSF')
    fireEvent.change(selectByPlaceholder('Année académique…'), { target: { value: '1' } })
    fireEvent.change(selectByPlaceholder('Formation…'), { target: { value: '10' } })
    fireEvent.change(selectByPlaceholder('Niveau…'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))
    expect(await screen.findByText('Création impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* Workflow des actions (valider / activer / archiver / cloner)        */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Maquettes.jsx (LOT 40) — workflow des actions', () => {
  it('n’affiche que les actions permises par le statut', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')

    // BROUILLON : Valider seulement (pas de Cloner).
    const rowBrouillon = rowOf('Licence 1 LSF')
    expect(within(rowBrouillon).getByRole('button', { name: 'Valider' })).toBeInTheDocument()
    expect(within(rowBrouillon).queryByRole('button', { name: 'Cloner' })).not.toBeInTheDocument()

    // VALIDEE : Activer + Cloner.
    const rowValidee = rowOf('Licence 2 LSF')
    expect(within(rowValidee).getByRole('button', { name: 'Activer' })).toBeInTheDocument()
    expect(within(rowValidee).getByRole('button', { name: 'Cloner' })).toBeInTheDocument()

    // ACTIVE : Archiver + Cloner.
    const rowActive = rowOf('Master LSF')
    expect(within(rowActive).getByRole('button', { name: 'Archiver' })).toBeInTheDocument()
    expect(within(rowActive).getByRole('button', { name: 'Cloner' })).toBeInTheDocument()

    // ARCHIVEE et statut inconnu : Cloner seulement.
    expect(within(rowOf('Vieux cursus')).queryByRole('button', { name: 'Archiver' })).not.toBeInTheDocument()
    expect(within(rowOf('Cursus bizarre')).getByRole('button', { name: 'Cloner' })).toBeInTheDocument()
  })

  it('Valider : demande confirmation, POST valider, notifie le détail et recharge', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    const avant = listCalls().length
    const row = rowOf('Licence 1 LSF')

    // Refus de confirmation : aucun appel.
    vi.mocked(window.confirm).mockReturnValueOnce(false)
    fireEvent.click(within(row).getByRole('button', { name: 'Valider' }))
    expect(window.confirm).toHaveBeenCalledWith('Valider cette maquette (contenu gelé) ?')
    expect(actionPosts()).toHaveLength(0)

    // Acceptation : POST + toast détaillé.
    fireEvent.click(within(row).getByRole('button', { name: 'Valider' }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/scolarite/maquettes/1/valider/', {}),
    )
    expect(listCalls().length).toBe(avant + 1)
  })

  it('Activer et Archiver postent sur les bons verbes avec leurs messages de confirmation', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')

    fireEvent.click(within(rowOf('Licence 2 LSF')).getByRole('button', { name: 'Activer' }))
    expect(window.confirm).toHaveBeenCalledWith('Activer cette maquette (immuable) ?')
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/scolarite/maquettes/2/activer/', {}),
    )

    fireEvent.click(within(rowOf('Master LSF')).getByRole('button', { name: 'Archiver' }))
    expect(window.confirm).toHaveBeenCalledWith('Archiver cette maquette ?')
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/scolarite/maquettes/3/archiver/', {}),
    )
  })

  it('Cloner une maquette validée poste sur le verbe cloner', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    fireEvent.click(within(rowOf('Licence 2 LSF')).getByRole('button', { name: 'Cloner' }))
    expect(window.confirm).toHaveBeenCalledWith('Créer une nouvelle version (clonage) ?')
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/scolarite/maquettes/2/cloner/', {}),
    )
  })

  it('reprend le message « Opération effectuée. » quand le serveur ne renvoie pas de détail', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    fireEvent.click(within(rowOf('Licence 1 LSF')).getByRole('button', { name: 'Valider' }))
    expect(await screen.findByText('Opération effectuée.')).toBeInTheDocument()
  })

  it('en cas d’échec, agrège la liste `problemes` en un seul message', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('ko'), {
        response: { data: { problemes: ['UE manquante.', 'Crédits invalides.'] } },
      }),
    )
    fireEvent.click(within(rowOf('Licence 1 LSF')).getByRole('button', { name: 'Valider' }))
    expect(await screen.findByText('UE manquante. Crédits invalides.')).toBeInTheDocument()
  })

  it('en cas d’échec sans probleme, affiche error puis le message générique', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    apiMock.post.mockRejectedValueOnce(
      Object.assign(new Error('ko'), { response: { data: { error: 'Transition interdite.' } } }),
    )
    fireEvent.click(within(rowOf('Licence 1 LSF')).getByRole('button', { name: 'Valider' }))
    expect(await screen.findByText('Transition interdite.')).toBeInTheDocument()

    // Second essai, erreur sans corps exploitable.
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(rowOf('Licence 1 LSF')).getByRole('button', { name: 'Valider' }))
    expect(await screen.findByText('Action impossible.')).toBeInTheDocument()
  })

  it('désactive les boutons d’action pendant le traitement', async () => {
    let resolveAction
    const enAttente = new Promise((resolve) => { resolveAction = resolve })
    mount()
    apiMock.post.mockImplementationOnce(async (path) => {
      if (path.includes('/valider/')) { await enAttente; return { data: {} } }
      return { data: {} }
    })
    await screen.findByText('Licence 1 LSF')

    await act(async () => {
      fireEvent.click(within(rowOf('Licence 1 LSF')).getByRole('button', { name: 'Valider' }))
    })
    // Le bouton de création comme toutes les actions sont désactivés en cours.
    expect(screen.getByRole('button', { name: 'Créer' })).toBeDisabled()
    expect(within(rowOf('Licence 2 LSF')).getByRole('button', { name: 'Activer' })).toBeDisabled()

    await act(async () => {
      resolveAction()
      await enAttente
    })
    await waitFor(() => expect(screen.getByText('Opération effectuée.')).toBeInTheDocument())
  })
})
