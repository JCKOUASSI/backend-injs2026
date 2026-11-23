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
vi.mock('@/utils/downloadFile', () => ({ downloadFile: vi.fn() }))

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import { downloadFile } from '@/utils/downloadFile'
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

/* ------------------------------------------------------------------ */
/* Premium : cycle de validation, lot et matrice de couverture          */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/Maquettes.jsx — cycle, validation en lot, couverture', () => {
  it('affiche le cycle de validation et filtre en cliquant une étape', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    expect(screen.getByText('Cycle de validation académique')).toBeInTheDocument()
    const avant = listCalls().length
    fireEvent.click(screen.getByRole('button', { name: /Validée/ }))
    await waitFor(() => expect(listCalls()).toHaveLength(avant + 1))
    expect(listCalls().at(-1)[1].params).toEqual({ statut: 'VALIDEE' })
  })

  it('propose la validation en lot quand des brouillons existent et poste sur valider-toutes', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    const bouton = screen.getByRole('button', { name: /Valider tous les brouillons/ })
    fireEvent.click(bouton)
    expect(window.confirm).toHaveBeenCalledWith(
      'Valider toutes les maquettes en brouillon (contenu gelé) ?',
    )
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/scolarite/maquettes/valider-toutes/', {}),
    )
  })

  it('matrice de couverture : filières regroupées par niveau avec liens de détail', async () => {
    mount('ADMIN', {
      list: [
        {
          id: 21, ref_formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE', niveau: 'L1',
          parcours: null, annee_academique: '2026-2027', version: 1, statut: 'ACTIVE',
          nb_ue: 18, total_credits: 60, libelle: 'EM L1',
        },
        {
          id: 22, ref_formation: 'ÉDUCATION ET MOTRICITÉ — MASTER', niveau: 'M2',
          parcours: null, annee_academique: '2026-2027', version: 1, statut: 'BROUILLON',
          nb_ue: 5, total_credits: 45, libelle: '[Exemple] EM M2',
        },
      ],
    })
    expect(await screen.findByText('Couverture par formation')).toBeInTheDocument()
    expect(screen.getByText('ÉDUCATION ET MOTRICITÉ')).toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: /Détail de la maquette ÉDUCATION ET MOTRICITÉ L1/ }),
    ).toHaveAttribute('href', '/scolarite/maquettes/21')
    // Pastille « Exemple » sur la ligne marquée [Exemple] et conformité ECTS.
    expect(screen.getByText('Exemple')).toBeInTheDocument()
    expect(screen.getByText('Conforme')).toBeInTheDocument()
    expect(screen.getByText('À compléter')).toBeInTheDocument()
  })
})

describe('pages/scolarite/Maquettes.jsx — sélection, CRUD, exports et import', () => {
  it('sélectionne une ligne ou toute la liste et reflète le nombre sélectionné', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')

    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence 1 LSF Licence 1' }))
    expect(screen.getByText('1 sélectionnée')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner toutes les maquettes affichées' }))
    expect(screen.getByText('5 sélectionnées')).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: 'Sélectionner Vieux cursus Licence 3' })).toBeChecked()
  })

  it('exporte uniquement les identifiants sélectionnés et peut demander le contenu détaillé', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')

    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence 1 LSF Licence 1' }))
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence 2 LSF Licence 2' }))
    fireEvent.click(screen.getByLabelText('Inclure les UE/ECUE et volumes horaires'))
    fireEvent.click(screen.getByRole('button', { name: 'CSV' }))

    await waitFor(() => expect(apiMock.getBlob).toHaveBeenCalledWith(
      '/scolarite/maquettes/export/csv/?ids=1%2C2&detaille=1',
    ))
    expect(downloadFile).toHaveBeenCalled()
  })

  it('modifie un brouillon depuis le panneau de sélection', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence 1 LSF Licence 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Modifier', exact: true }))

    fireEvent.change(screen.getByLabelText('Libellé personnalisé'), { target: { value: 'Maquette revue' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(apiMock.patch).toHaveBeenCalledWith(
      '/scolarite/maquettes/1/modifier/',
      { libelle: 'Maquette revue', commentaire_validation: '' },
    ))
    expect(await screen.findByText('Maquette modifiée.')).toBeInTheDocument()
  })

  it('refuse la suppression avec UE et supprime uniquement un brouillon vide après confirmation', async () => {
    mount('ADMIN', {
      list: [
        ...MAQUETTES,
        {
          id: 6, ref_formation: 'Brouillon vide', niveau: 'L1', parcours: '',
          annee_academique: '2026-2027', version: 1, statut: 'BROUILLON', nb_ue: 0, total_credits: 0,
        },
      ],
    })
    await screen.findByText('Licence 1 LSF')

    expect(screen.getByRole('button', { name: 'Supprimer Licence 1 LSF' })).toBeDisabled()
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer Brouillon vide' }))

    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith('/scolarite/maquettes/6/'))
    expect(window.confirm).toHaveBeenCalledWith('Supprimer le brouillon « Brouillon vide » ?')
    expect(await screen.findByText('Maquette supprimée.')).toBeInTheDocument()
  })

  it('prévisualise un CSV et ne le confirme qu’avec l’empreinte affichée', async () => {
    mount()
    apiController.setRoute('/scolarite/maquettes/import/csv/', (_path, body) => {
      if (body.get('etape') === 'previsualiser') {
        return {
          valide: true, empreinte: 'empreinte-test', lignes: 1, maquettes: 1,
          ues: 1, ecues: 1, exemples: [], avertissements: [],
        }
      }
      return { detail: '1 maquette importée en brouillon.', crees: 1, ues_crees: 1, ecues_crees: 1 }
    })
    await screen.findByText('Licence 1 LSF')

    const fichier = new File(['csv'], 'maquettes.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByLabelText('Importer une maquette (.xlsx ou .csv)'), {
      target: { files: [fichier] },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Prévisualiser' }))
    expect(await screen.findByText(/Aperçu valide : 1 maquette/)).toBeInTheDocument()
    expect(apiMock.post).toHaveBeenCalledTimes(1)
    const [chemin, donnees] = apiMock.post.mock.calls[0]
    expect(chemin).toBe('/scolarite/maquettes/import/csv/')
    expect(donnees.get('etape')).toBe('previsualiser')
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer l’import' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledTimes(2))
    const [, confirmation] = apiMock.post.mock.calls[1]
    expect(confirmation.get('etape')).toBe('confirmer')
    expect(confirmation.get('empreinte')).toBe('empreinte-test')
    expect(await screen.findByText(/1 maquette importée en brouillon/)).toBeInTheDocument()
  })
})

describe('pages/scolarite/Maquettes.jsx — compléments sélection/export/lecture', () => {
  it('exporte la vue courante par défaut quand aucune maquette n’est cochée', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')

    fireEvent.click(screen.getByRole('button', { name: 'CSV' }))

    await waitFor(() => expect(apiMock.getBlob).toHaveBeenCalledWith(
      '/scolarite/maquettes/export/csv/?ids=1%2C2%2C3%2C4%2C5',
    ))
    expect(downloadFile).toHaveBeenCalled()
  })

  it('conserve les cases sélectionnées au changement des filtres locaux', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence 1 LSF Licence 1' }))
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'Master' } })

    expect(screen.getByText('1 sélectionnée')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Modifier', exact: true })).toBeEnabled()
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: '' } })
    expect(screen.getByRole('checkbox', { name: 'Sélectionner Licence 1 LSF Licence 1' })).toBeChecked()
  })

  it('ouvre un détail de maquette en lecture seule depuis la sélection', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    apiController.setRoute('/scolarite/maquettes/1/', {
      id: 1,
      ref_formation: 'Licence 1 LSF',
      niveau: 'L1',
      annee_academique: '2026-2027',
      version: 1,
      statut: 'BROUILLON',
      parcours: null,
      commentaire_validation: '',
      unites_enseignement: [{
        id: 10, code: 'UE1', intitule: 'Sciences du sport', credits: 6,
        caractere: 'OBLIGATOIRE', semestre: { libelle: 'Semestre 1' },
        ecues: [{
          id: 100, code: 'ECUE1', intitule: 'Anatomie', credits: 3, coefficient: 1,
          volume_cm: 12, volume_td: 8, volume_tp: 4, volume_total: 24, archive: false,
        }],
      }],
    })
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence 1 LSF Licence 1' }))
    fireEvent.click(screen.getByRole('button', { name: 'Visualiser' }))

    const dialog = await screen.findByRole('dialog', { name: 'Visualiser la maquette' })
    expect(within(dialog).getByText('Consultation en lecture seule · contenu pédagogique')).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: /Sciences du sport/ })).toBeInTheDocument()
    expect(within(dialog).getAllByRole('row').at(-1).textContent).toContain('Anatomie')
    expect(within(dialog).queryByRole('button', { name: 'Modifier', exact: true })).not.toBeInTheDocument()
  })
})

describe('pages/scolarite/Maquettes.jsx — suppression groupée', () => {
  it('confirme une suppression multiple en indiquant le nombre et tente chaque élément sélectionné', async () => {
    mount()
    await screen.findByText('Licence 1 LSF')
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner toutes les maquettes affichées' }))
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer (5)' }))

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining('5 maquette(s) sélectionnée(s)'))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledTimes(5))
    expect(apiMock.delete.mock.calls.map(([path]) => path)).toEqual([
      '/scolarite/maquettes/1/',
      '/scolarite/maquettes/2/',
      '/scolarite/maquettes/3/',
      '/scolarite/maquettes/4/',
      '/scolarite/maquettes/5/',
    ])
  })

})
