import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import RapportsWorkflowPanel from '@/components/RapportsWorkflowPanel'

/* ------------------------------------------------------------------ */
/* Jeu de données                                                       */
/* ------------------------------------------------------------------ */

const RAPPORTS = [
  {
    id: 1, titre: 'Rapport mensuel — Août 2026', type: 'MENSUEL', statut: 'BROUILLON',
    periode_debut: '2026-08-01', periode_fin: '2026-08-31',
    created_at: '2026-08-15T10:30:00', generateur__username: 'admin1',
    validateur__username: null, commentaire: '',
  },
  {
    id: 2, titre: 'Rapport hebdo — S33', type: 'HEBDOMADAIRE', statut: 'EN_VALIDATION',
    periode_debut: '2026-08-17', periode_fin: '2026-08-23',
    created_at: '2026-08-18T09:00:00', generateur__username: 'secretaire1',
    validateur__username: null, commentaire: '',
  },
  {
    id: 3, titre: 'Rapport trimestriel — T3', type: 'TRIMESTRIEL', statut: 'VALIDE',
    periode_debut: '2026-07-01', periode_fin: '2026-09-30',
    created_at: '2026-07-05T14:00:00', generateur__username: 'admin1',
    validateur__username: 'direction1', commentaire: '',
  },
  {
    id: 4, titre: 'Bilan annuel 2025', type: 'ANNUEL', statut: 'PUBLIE',
    periode_debut: '2025-01-01', periode_fin: '2025-12-31',
    created_at: '2026-01-10T08:15:00', generateur__username: 'admin1',
    validateur__username: 'direction1', commentaire: 'Version publique',
  },
  {
    id: 5, titre: 'Rapport rejeté — Juillet', type: 'MENSUEL', statut: 'REJETE',
    periode_debut: '2026-07-01', periode_fin: '2026-07-31',
    created_at: '2026-07-08T16:45:00', generateur__username: 'secretaire1',
    validateur__username: 'direction1', commentaire: 'Chiffres incomplets',
  },
]

const detailFor = (r, overrides = {}) => ({
  ...r,
  generateur: 'Admin Principal',
  validateur: r.validateur__username ? 'Direction INJS' : null,
  donnees_json: {
    kpis: { taux_presence: 88.5, taux_execution_vh: 62, nb_seances: 34, nb_auditeurs: 120 },
  },
  ...overrides,
})

/** Erreur « réseau » portant un détail backend, comme l'axios réel. */
const apiError = (detail) => ({ response: { data: { detail } } })

/** Promesse contrôlable pour figer un état de chargement. */
function deferred() {
  let resolve
  const promise = new Promise((r) => { resolve = r })
  return { promise, resolve }
}

/* ------------------------------------------------------------------ */
/* Routes mock et helpers                                               */
/* ------------------------------------------------------------------ */

/**
 * Installe les routes standard du workflow.
 *  - GET  `/statistiques/rapports/`        → liste (surcharge `list`)
 *  - POST `/statistiques/rapports/`        → création (surcharge `create`)
 *  - GET/PATCH `/statistiques/rapports/<id>/`
 *  - POST `/statistiques/rapports/<id>/workflow/` (surcharge `workflow`)
 */
function installRoutes(overrides = {}) {
  apiController.reset()

  apiController.setRoute('/statistiques/rapports/', (path, body) => {
    // POST de création (le mock passe le corps) vs GET de liste (pas de corps).
    if (body) {
      return overrides.create
        ? overrides.create(path, body)
        : { id: 99, statut: 'BROUILLON', periode_debut: null, periode_fin: null, ...body }
    }
    return overrides.list ? overrides.list(path) : RAPPORTS
  })

  apiController.setRoute(/^\/statistiques\/rapports\/\d+\/$/, (path, body) => {
    const id = Number(path.split('?')[0].split('/')[3])
    const base = RAPPORTS.find((r) => r.id === id) || { id, titre: `Rapport ${id}`, type: 'MENSUEL', statut: 'BROUILLON' }
    if (body) return overrides.patch ? overrides.patch(path, body, id) : detailFor(base, body)
    return overrides.detail ? overrides.detail(path, id) : detailFor(base)
  })

  apiController.setRoute(/workflow\/$/, (path, body) => (
    overrides.workflow ? overrides.workflow(path, body) : { ok: true }
  ))
}

const urlOf = (raw) => new URL(raw, 'http://testserver')
const listCalls = () =>
  apiMock.get.mock.calls.filter(([p]) => urlOf(p).pathname === '/statistiques/rapports/')
const detailCalls = () =>
  apiMock.get.mock.calls.filter(([p]) => /^\/statistiques\/rapports\/\d+\/$/.test(urlOf(p).pathname))
const createCalls = () =>
  apiMock.post.mock.calls.filter(([p]) => urlOf(p).pathname === '/statistiques/rapports/')
const workflowCalls = () =>
  apiMock.post.mock.calls.filter(([p]) => urlOf(p).pathname.endsWith('/workflow/'))

const mountPanel = (props = {}) => {
  const utils = renderWithProviders(
    <RapportsWorkflowPanel user={makeUser('ADMIN')} {...props} />,
  )
  return {
    ...utils,
    rerenderAs: (newProps) =>
      utils.rerender(<RapportsWorkflowPanel user={makeUser('ADMIN')} {...newProps} />),
  }
}

const listItem = (name) => screen.getByRole('button', { name: new RegExp(name) })
const modalBox = () => document.querySelector('.modal.show .modal-content')

/* ═══════════════════════════════════════════════════════════════════ */
/* 1. Chargement, périmètre et droits                                   */
/* ═══════════════════════════════════════════════════════════════════ */

describe('RapportsWorkflowPanel — chargement, périmètre et droits', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    installRoutes()
  })

  it('charge la liste au montage et rend titre, compteur, lignes, badges et périodes', async () => {
    mountPanel()

    expect(await screen.findByRole('heading', { name: /Rapports périodiques — validation/ })).toBeInTheDocument()
    expect(screen.getByText('5 rapports')).toBeInTheDocument()
    expect(screen.getByText('Sélectionnez un rapport dans la liste.')).toBeInTheDocument()
    expect(listCalls()).toHaveLength(1)
    expect(listCalls()[0][0]).toBe('/statistiques/rapports/') // aucun périmètre forcé

    expect(listItem('Rapport mensuel — Août 2026')).toBeInTheDocument()
    // Un badge par ligne (et pas de doublon tant qu'aucun détail n'est ouvert).
    expect(screen.getAllByText('Brouillon')).toHaveLength(1)
    expect(screen.getAllByText('En validation')).toHaveLength(1)
    expect(screen.getAllByText('Validé')).toHaveLength(1)
    expect(screen.getAllByText('Publié')).toHaveLength(1)
    expect(screen.getAllByText('Rejeté')).toHaveLength(1)
    // Période formatée en français avec la flèche de la liste.
    expect(listItem('Rapport mensuel')).toHaveTextContent('01/08/2026 → 31/08/2026')
  })

  it('affiche « Chargement… » et désactive Actualiser pendant le chargement', async () => {
    const d = deferred()
    installRoutes({ list: () => d.promise })
    mountPanel()

    expect(await screen.findByText('Chargement…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Actualiser/ })).toBeDisabled()
    expect(screen.queryByText('5 rapports')).not.toBeInTheDocument()

    d.resolve(RAPPORTS)
    await screen.findByText('5 rapports')
    expect(screen.getByRole('button', { name: /Actualiser/ })).not.toBeDisabled()
  })

  it("affiche l'état vide quand aucun rapport ne revient", async () => {
    installRoutes({ list: () => [] })
    mountPanel()

    expect(await screen.findByText('Aucun rapport pour ce périmètre.')).toBeInTheDocument()
    expect(screen.getByText('0 rapport')).toBeInTheDocument() // singulier
  })

  it("signale une erreur backend au chargement sans planter (liste vide)", async () => {
    installRoutes({ list: () => { throw apiError('Service rapports indisponible') } })
    mountPanel()

    expect(await screen.findByText('Service rapports indisponible')).toBeInTheDocument()
    expect(screen.getByText('Aucun rapport pour ce périmètre.')).toBeInTheDocument()
  })

  it("retombe sur le message générique si l'erreur n'a pas de détail", async () => {
    installRoutes({ list: () => { throw new Error('network') } })
    mountPanel()

    expect(await screen.findByText('Erreur chargement rapports')).toBeInTheDocument()
  })

  it('le bouton Actualiser relance le chargement de la liste', async () => {
    mountPanel()
    await screen.findByText('5 rapports')

    fireEvent.click(screen.getByRole('button', { name: /Actualiser/ }))
    await waitFor(() => expect(listCalls()).toHaveLength(2))
  })

  it('porte formation_id, secretariat_id et la période mensuelle dans la query', async () => {
    mountPanel({
      formationId: 10,
      secretariatId: 3,
      appliedVhPeriod: { preset: 'mois', mois: '2026-08' },
    })
    await screen.findByText('5 rapports')

    const q = urlOf(listCalls()[0][0])
    expect(q.searchParams.get('formation_id')).toBe('10')
    expect(q.searchParams.get('secretariat_id')).toBe('3')
    expect(q.searchParams.get('preset')).toBe('mois')
    expect(q.searchParams.get('mois')).toBe('2026-08')
  })

  it('porte une période custom avec dates de début/fin', async () => {
    mountPanel({
      appliedVhPeriod: { preset: 'custom', dateDebut: '2026-08-01', dateFin: '2026-08-15' },
    })
    await screen.findByText('5 rapports')

    const q = urlOf(listCalls()[0][0])
    expect(q.searchParams.get('preset')).toBe('custom')
    expect(q.searchParams.get('date_debut')).toBe('2026-08-01')
    expect(q.searchParams.get('date_fin')).toBe('2026-08-15')
  })

  it('recharge la liste quand le périmètre (props) change', async () => {
    const { rerenderAs } = mountPanel()
    await screen.findByText('5 rapports')

    rerenderAs({ formationId: 11 })
    await waitFor(() => expect(listCalls()).toHaveLength(2))
    expect(urlOf(listCalls().at(-1)[0]).searchParams.get('formation_id')).toBe('11')
  })

  it('masque les actions de génération/validation à un rôle non habilité (auditeur)', async () => {
    renderWithProviders(<RapportsWorkflowPanel user={makeUser('AUDITEUR')} />)
    await screen.findByText('5 rapports')

    expect(screen.queryByRole('button', { name: /Générer un rapport/ })).not.toBeInTheDocument()
    fireEvent.click(listItem('Rapport mensuel — Août 2026'))
    expect(await screen.findByRole('heading', { name: 'Rapport mensuel — Août 2026' })).toBeInTheDocument()
    // Aucune action : ni Modifier, ni Supprimer, ni Soumettre.
    expect(screen.queryByRole('button', { name: /Modifier/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Supprimer/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Soumettre/ })).not.toBeInTheDocument()
  })

  it('un secrétariat peut générer et soumettre mais pas valider ni supprimer', async () => {
    renderWithProviders(<RapportsWorkflowPanel user={makeUser('SECRETARIAT')} />)
    await screen.findByText('5 rapports')

    expect(screen.getByRole('button', { name: /Générer un rapport/ })).toBeInTheDocument()
    fireEvent.click(listItem('Rapport mensuel — Août 2026')) // BROUILLON
    expect(await screen.findByRole('button', { name: /Soumettre à validation/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Supprimer/ })).not.toBeInTheDocument()

    fireEvent.click(listItem('Rapport hebdo — S33')) // EN_VALIDATION
    await waitFor(() => expect(screen.queryByRole('button', { name: /^Valider$/ })).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Rejeter/ })).not.toBeInTheDocument()
  })

  it('affiche le libellé brut d’un statut inconnu dans le badge', async () => {
    installRoutes({
      list: () => [
        { id: 42, titre: 'Rapport exotique', type: 'FAB', statut: 'EN_PAUSE', periode_debut: null, periode_fin: null },
      ],
    })
    mountPanel()

    expect(await screen.findByText('EN_PAUSE')).toBeInTheDocument()
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* 2. Sélection et détail                                               */
/* ═══════════════════════════════════════════════════════════════════ */

describe('RapportsWorkflowPanel — sélection et panneau de détail', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    installRoutes()
  })

  it('ouvre le détail d’un rapport (GET par id) avec type, période, acteurs et date', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))

    await waitFor(() => expect(detailCalls()).toHaveLength(1))
    expect(detailCalls()[0][0]).toBe('/statistiques/rapports/1/')

    // En-tête du détail (le titre de la liste reste présent dans la sidebar).
    expect(screen.getByRole('heading', { name: 'Rapport mensuel — Août 2026' })).toBeInTheDocument()
    expect(screen.getByText('Type : Mensuel')).toBeInTheDocument()
    expect(screen.getByText('Période : 01/08/2026 — 31/08/2026')).toBeInTheDocument()
    expect(screen.getByText(/Admin Principal/)).toBeInTheDocument()
    expect(screen.getByText(/15 août 2026/)).toBeInTheDocument()
    expect(screen.getByText(/10:30/)).toBeInTheDocument()
    // Pas de validateur sur ce brouillon.
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    // Le commentaire vide n'est pas affiché.
    expect(screen.queryByText(/^Commentaire :/)).not.toBeInTheDocument()
  })

  it('affiche le spinner de détail pendant son chargement', async () => {
    const d = deferred()
    installRoutes({ detail: () => d.promise })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))

    const panneau = screen.getByText(/Rapports périodiques/).closest('div').parentElement
    await waitFor(() => expect(panneau.querySelector('.spinner')).toBeInTheDocument())

    d.resolve(detailFor(RAPPORTS[0]))
    await screen.findByText('Type : Mensuel')
  })

  it('rend les 4 cartes KPI issues de donnees_json.kpis', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))

    expect(await screen.findByText('Assiduité')).toBeInTheDocument()
    expect(screen.getByText('Exéc. VH')).toBeInTheDocument()
    expect(screen.getByText('Séances')).toBeInTheDocument()
    expect(screen.getByText('Étudiants')).toBeInTheDocument()
    // Les taux sont affichés tels quels (concaténation ' %', sans trame FR).
    expect(screen.getByText('88.5 %')).toBeInTheDocument()
    expect(screen.getByText('62 %')).toBeInTheDocument()
    expect(screen.getByText('34')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
  })

  it('gère des KPI partiels avec des valeurs manquantes (—)', async () => {
    installRoutes({
      detail: () => detailFor(RAPPORTS[0], {
        donnees_json: { kpis: { taux_presence: null, taux_execution_vh: null, nb_seances: null, nb_auditeurs: null } },
      }),
    })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))

    await screen.findByText('Assiduité')
    expect(screen.getAllByText('— %').length).toBe(2)
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })

  it('n’affiche pas la grille KPI en l’absence de donnees_json.kpis', async () => {
    installRoutes({ detail: () => detailFor(RAPPORTS[0], { donnees_json: {} }) })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))

    await waitFor(() => expect(detailCalls()).toHaveLength(1))
    expect(screen.queryByText('Assiduité')).not.toBeInTheDocument()
  })

  it('affiche validateur et commentaire quand ils existent (rapport rejeté)', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport rejeté — Juillet/ }))

    expect(await screen.findByText(/Direction INJS/)).toBeInTheDocument()
    // « Commentaire : » est dans un <strong>, le texte suit dans le même div.
    expect(screen.getByText((_c, el) => el?.tagName === 'DIV' && /^Commentaire : Chiffres incomplets$/.test(el.textContent))).toBeInTheDocument()
  })

  it('une erreur de chargement du détail émet un toast et retombe sur les données de la liste', async () => {
    installRoutes({ detail: () => { throw apiError('Détail KO') } })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))

    expect(await screen.findByText('Détail KO')).toBeInTheDocument()
    // Le titre et le type de la liste assurent l'en-tête du panneau malgré
    // l'absence de détail (repli sur `selected`).
    expect(screen.getByRole('heading', { name: 'Rapport trimestriel — T3' })).toBeInTheDocument()
    expect(screen.getByText('Type : Trimestriel')).toBeInTheDocument()
    expect(screen.getByText(/admin1/)).toBeInTheDocument()
  })

  it('change de détail quand on sélectionne un autre rapport', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Bilan annuel 2025/ }))
    await waitFor(() => expect(detailCalls()).toHaveLength(1))
    expect(await screen.findByText('Type : Annuel')).toBeInTheDocument()

    fireEvent.click(listItem('Rapport hebdo — S33'))
    await waitFor(() => expect(detailCalls()).toHaveLength(2))
    expect(detailCalls().at(-1)[0]).toBe('/statistiques/rapports/2/')
    expect(await screen.findByText('Type : Hebdomadaire')).toBeInTheDocument()
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* 3. Workflow de validation (admin)                                    */
/* ═══════════════════════════════════════════════════════════════════ */

describe('RapportsWorkflowPanel — workflow de validation', () => {
  /** État mutable des statuts pour simuler les transitions backend. */
  let statutById

  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    statutById = Object.fromEntries(RAPPORTS.map((r) => [r.id, r.statut]))
    installRoutes({
      list: () => RAPPORTS.map((r) => ({ ...r, statut: statutById[r.id] })),
      detail: (_path, id) => {
        const base = RAPPORTS.find((r) => r.id === id)
        return detailFor({ ...base, statut: statutById[id] })
      },
      workflow: (_path, body) => {
        const next = {
          soumettre: 'EN_VALIDATION',
          valider: 'VALIDE',
          publier: 'PUBLIE',
          rejeter: 'REJETE',
        }[body.action]
        const id = Number(_path.split('?')[0].split('/')[3])
        statutById[id] = next
        return { ok: true }
      },
    })
  })

  it('BROUILLON : « Soumettre à validation » poste immédiatement l’action et rafraîchit', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Soumettre à validation/ }))

    await waitFor(() => expect(workflowCalls()).toHaveLength(1))
    const [path, body] = workflowCalls()[0]
    expect(path).toBe('/statistiques/rapports/1/workflow/')
    expect(body).toEqual({ action: 'soumettre' })
    expect(await screen.findByText('Action « soumettre » effectuée')).toBeInTheDocument()
    // Le refresh rappelle la liste puis le détail.
    await waitFor(() => expect(detailCalls().length).toBeGreaterThanOrEqual(2))
    // Après transition, les boutons de validation apparaissent.
    expect(await screen.findByRole('button', { name: 'Valider' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Rejeter' })).toBeInTheDocument()
  })

  it('EN_VALIDATION : « Valider » ouvre une modale et poste avec le commentaire saisi', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport hebdo — S33/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Valider' }))

    const box = await screen.findByRole('heading', { name: 'Valider le rapport' })
    expect(box).toBeInTheDocument()
    expect(screen.getByText('Commentaire (optionnel)')).toBeInTheDocument()
    fireEvent.change(within(modalBox()).getByRole('textbox'), { target: { value: 'Conforme' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    await waitFor(() => expect(workflowCalls()).toHaveLength(1))
    const [path, body] = workflowCalls()[0]
    expect(path).toBe('/statistiques/rapports/2/workflow/')
    expect(body).toEqual({ action: 'valider', commentaire: 'Conforme' })
    expect(await screen.findByText('Action « valider » effectuée')).toBeInTheDocument()
    // La modale se ferme.
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Valider le rapport' })).not.toBeInTheDocument())
    // Le rapport passe en VALIDE : le bouton Publier apparaît.
    expect(await screen.findByRole('button', { name: /Publier/ })).toBeInTheDocument()
  })

  it('VALIDE : « Publier » poste avec un commentaire vide si rien n’est saisi', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Publier/ }))

    expect(await screen.findByRole('heading', { name: 'Publier le rapport' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    await waitFor(() => expect(workflowCalls()).toHaveLength(1))
    expect(workflowCalls()[0][1]).toEqual({ action: 'publier', commentaire: '' })
    // PUBLIE : plus aucune action de workflow.
    await waitFor(() => expect(screen.queryByRole('button', { name: /Soumettre/ })).not.toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /^Publier$/ })).not.toBeInTheDocument()
  })

  it('Rejeter exige un motif : pas de POST sans saisie, POST doublé commentaire/motif avec', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport hebdo — S33/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Rejeter' }))

    expect(await screen.findByRole('heading', { name: 'Rejeter le rapport' })).toBeInTheDocument()
    expect(screen.getByText('Motif de rejet (obligatoire)')).toBeInTheDocument()

    // Confirmation à vide : garde-fou, aucun appel.
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Motif de rejet requis')).toBeInTheDocument()
    expect(workflowCalls()).toHaveLength(0)
    // La modale reste ouverte.
    expect(screen.getByRole('heading', { name: 'Rejeter le rapport' })).toBeInTheDocument()

    fireEvent.change(within(modalBox()).getByRole('textbox'), { target: { value: 'Données fausses' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    await waitFor(() => expect(workflowCalls()).toHaveLength(1))
    expect(workflowCalls()[0][1]).toEqual({
      action: 'rejeter', commentaire: 'Données fausses', motif: 'Données fausses',
    })
  })

  it('l’Annulation et la croix ferment la modale de workflow sans aucun appel', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport hebdo — S33/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Valider' }))
    expect(await screen.findByRole('heading', { name: 'Valider le rapport' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Valider le rapport' })).not.toBeInTheDocument())
    expect(workflowCalls()).toHaveLength(0)
  })

  it('parcours complet brouillon → en validation → validé → publié', async () => {
    mountPanel()
    // 1) Sélection du brouillon et soumission immédiate.
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Soumettre à validation/ }))
    await waitFor(() => expect(workflowCalls()).toHaveLength(1))

    // 2) Validation via modale.
    fireEvent.click(await screen.findByRole('button', { name: 'Valider' }))
    expect(await screen.findByRole('heading', { name: 'Valider le rapport' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    await waitFor(() => expect(workflowCalls()).toHaveLength(2))

    // 3) Publication via modale.
    fireEvent.click(await screen.findByRole('button', { name: /^Publier$/ }))
    expect(await screen.findByRole('heading', { name: 'Publier le rapport' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))
    await waitFor(() => expect(workflowCalls()).toHaveLength(3))
    expect(workflowCalls().map(([, b]) => b.action)).toEqual(['soumettre', 'valider', 'publier'])

    // État final : aucun bouton d'action.
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /Soumettre/ })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Valider' })).not.toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /^Publier$/ })).not.toBeInTheDocument()
    })
  })

  it('une erreur workflow affiche le détail backend et laisse la modale ouverte', async () => {
    installRoutes({ workflow: () => { throw apiError('Transition interdite') } })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport hebdo — S33/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Valider' }))
    expect(await screen.findByRole('heading', { name: 'Valider le rapport' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    expect(await screen.findByText('Transition interdite')).toBeInTheDocument()
    // La modale n'est pas refermée en cas d'erreur.
    expect(screen.getByRole('heading', { name: 'Valider le rapport' })).toBeInTheDocument()
    expect(workflowCalls()).toHaveLength(1)
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* 4. Création d'un rapport                                             */
/* ═══════════════════════════════════════════════════════════════════ */

describe('RapportsWorkflowPanel — génération (création)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    installRoutes()
  })

  it('ouvre la modale avec les 10 types de rapport et les valeurs par défaut', async () => {
    mountPanel()
    await screen.findByText('5 rapports')
    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))

    expect(await screen.findByRole('heading', { name: 'Générer un rapport' })).toBeInTheDocument()
    expect(screen.getByText(/Snapshot des statistiques/)).toBeInTheDocument()
    const box = modalBox()
    expect(within(box).getByPlaceholderText('Auto si vide')).toHaveValue('')
    expect(box.querySelector('textarea')).toHaveValue('') // commentaire
    // Les 10 types + le type courant dans le select.
    const typeSelect = within(box).getAllByRole('combobox')[0]
    expect(typeSelect.value).toBe('MENSUEL')
    expect(within(typeSelect).getAllByRole('option')).toHaveLength(10)
    expect(within(typeSelect).getByRole('option', { name: 'Consolidé FAB + FAC' })).toHaveValue('CONSOLIDE')
  })

  it('Annuler et la croix ferment la modale sans POST', async () => {
    mountPanel()
    await screen.findByText('5 rapports')
    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))
    expect(await screen.findByRole('heading', { name: 'Générer un rapport' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Générer un rapport' })).not.toBeInTheDocument())
    expect(createCalls()).toHaveLength(0)
  })

  it('Générer poste le formulaire complet sur le périmètre filtré, ferme et sélectionne le nouveau rapport', async () => {
    mountPanel({ formationId: 10, secretariatId: 3 })
    await screen.findByText('5 rapports')
    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))
    await screen.findByRole('heading', { name: 'Générer un rapport' })

    const box = modalBox()
    const typeSelect = within(box).getAllByRole('combobox')[0]
    fireEvent.change(typeSelect, { target: { value: 'TRIMESTRIEL' } })
    fireEvent.change(within(box).getByPlaceholderText('Auto si vide'), { target: { value: 'Mon titre' } })
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Commentaire initial' } })
    fireEvent.click(screen.getByRole('button', { name: 'Générer' }))

    await waitFor(() => expect(createCalls()).toHaveLength(1))
    const [path, body] = createCalls()[0]
    const q = urlOf(path).searchParams
    expect(q.get('formation_id')).toBe('10')
    expect(q.get('secretariat_id')).toBe('3')
    expect(body).toEqual({ type: 'TRIMESTRIEL', titre: 'Mon titre', commentaire: 'Commentaire initial' })

    expect(await screen.findByText('Rapport généré')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Générer un rapport' })).not.toBeInTheDocument())
    // Le rapport créé (id 99) est automatiquement sélectionné → GET détail.
    await waitFor(() => expect(detailCalls().some(([p]) => p === '/statistiques/rapports/99/')).toBe(true))
  })

  it('après création, rouvrir la modale montre le formulaire réinitialisé', async () => {
    mountPanel()
    await screen.findByText('5 rapports')
    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))
    await screen.findByRole('heading', { name: 'Générer un rapport' })

    const box = modalBox()
    fireEvent.change(within(box).getByPlaceholderText('Auto si vide'), { target: { value: 'Titre provisoire' } })
    fireEvent.click(screen.getByRole('button', { name: 'Générer' }))
    await waitFor(() => expect(createCalls()).toHaveLength(1))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Générer un rapport' })).not.toBeInTheDocument())

    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))
    await screen.findByRole('heading', { name: 'Générer un rapport' })
    expect(within(modalBox()).getByPlaceholderText('Auto si vide')).toHaveValue('')
    expect(within(modalBox()).getAllByRole('combobox')[0]).toHaveValue('MENSUEL')
  })

  it('un titre vide est bien envoyé (génération automatique côté backend)', async () => {
    mountPanel()
    await screen.findByText('5 rapports')
    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))
    await screen.findByRole('heading', { name: 'Générer un rapport' })
    fireEvent.click(screen.getByRole('button', { name: 'Générer' }))

    await waitFor(() => expect(createCalls()).toHaveLength(1))
    expect(createCalls()[0][1]).toEqual({ type: 'MENSUEL', titre: '', commentaire: '' })
  })

  it('une erreur de génération affiche le détail backend et garde la modale ouverte', async () => {
    installRoutes({ create: () => { throw apiError('Périmètre sans donnée') } })
    mountPanel()
    await screen.findByText('5 rapports')
    fireEvent.click(screen.getByRole('button', { name: /Générer un rapport/ }))
    await screen.findByRole('heading', { name: 'Générer un rapport' })
    fireEvent.click(screen.getByRole('button', { name: 'Générer' }))

    expect(await screen.findByText('Périmètre sans donnée')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Générer un rapport' })).toBeInTheDocument()
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* 5. Modification                                                      */
/* ═══════════════════════════════════════════════════════════════════ */

describe('RapportsWorkflowPanel — modification', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    installRoutes()
  })

  const patchCalls = () =>
    apiMock.patch.mock.calls.filter(([p]) => /^\/statistiques\/rapports\/\d+\/$/.test(urlOf(p).pathname))

  it('admin : modale pré-remplie (y compris sur un rapport PUBLIÉ), avec champ motif', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Bilan annuel 2025/ }))

    const editBtn = await screen.findByRole('button', { name: /Modifier/ })
    expect(editBtn).toBeInTheDocument()
    fireEvent.click(editBtn)

    expect(await screen.findByRole('heading', { name: 'Modifier le rapport' })).toBeInTheDocument()
    const box = modalBox()
    const inputs = within(box).getAllByRole('textbox')
    expect(inputs[0]).toHaveValue('Bilan annuel 2025') // titre
    expect(inputs[1]).toHaveValue('Version publique') // commentaire
    expect(within(box).getAllByRole('combobox')[0]).toHaveValue('ANNUEL')
    expect(within(box).getByText('Motif (notification)')).toBeInTheDocument()
  })

  it('PATCH complet sans motif quand le champ reste vide, puis fermeture et rafraîchissement', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Modifier/ }))
    await screen.findByRole('heading', { name: 'Modifier le rapport' })

    const box = modalBox()
    const inputs = within(box).getAllByRole('textbox')
    fireEvent.change(inputs[0], { target: { value: 'T3 corrigé' } })
    fireEvent.change(inputs[1], { target: { value: 'Commentaire revu' } })
    fireEvent.change(within(box).getAllByRole('combobox')[0], { target: { value: 'SEMESTRIEL' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    const [path, body] = patchCalls()[0]
    expect(path).toBe('/statistiques/rapports/3/')
    expect(body).toEqual({ titre: 'T3 corrigé', commentaire: 'Commentaire revu', type: 'SEMESTRIEL' })
    expect(body).not.toHaveProperty('motif')
    expect(await screen.findByText('Rapport modifié')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Modifier le rapport' })).not.toBeInTheDocument())
  })

  it('admin : ajoute le motif trimé quand il est renseigné', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Modifier/ }))
    await screen.findByRole('heading', { name: 'Modifier le rapport' })

    const inputs = within(modalBox()).getAllByRole('textbox')
    // Le champ motif est le 3e champ de saisie (titre, commentaire, motif).
    fireEvent.change(inputs[2], { target: { value: '  Rectification demandée  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(patchCalls()[0][1].motif).toBe('Rectification demandée')
  })

  it('secrétariat : peut modifier un brouillon mais sans champ motif', async () => {
    renderWithProviders(<RapportsWorkflowPanel user={makeUser('SECRETARIAT')} />)
    fireEvent.click(await screen.findByRole('button', { name: /Rapport mensuel — Août/ }))

    fireEvent.click(await screen.findByRole('button', { name: /Modifier/ }))
    expect(await screen.findByRole('heading', { name: 'Modifier le rapport' })).toBeInTheDocument()
    expect(screen.queryByText('Motif (notification)')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(patchCalls()).toHaveLength(1))
    expect(patchCalls()[0][1]).not.toHaveProperty('motif')
  })

  it('secrétariat : ne peut pas modifier un rapport PUBLIÉ (bouton masqué)', async () => {
    renderWithProviders(<RapportsWorkflowPanel user={makeUser('CHEF_SECRETARIAT')} />)
    fireEvent.click(await screen.findByRole('button', { name: /Bilan annuel 2025/ }))

    await waitFor(() => expect(detailCalls()).toHaveLength(1))
    expect(screen.queryByRole('button', { name: /Modifier/ })).not.toBeInTheDocument()
  })

  it('une erreur de PATCH émet un toast et laisse la modale ouverte', async () => {
    installRoutes({ patch: () => { throw apiError('Modification refusée') } })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Modifier/ }))
    await screen.findByRole('heading', { name: 'Modifier le rapport' })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))

    expect(await screen.findByText('Modification refusée')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Modifier le rapport' })).toBeInTheDocument()
  })

  it('Annuler ferme la modale d’édition sans PATCH', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: /Modifier/ }))
    await screen.findByRole('heading', { name: 'Modifier le rapport' })

    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Modifier le rapport' })).not.toBeInTheDocument())
    expect(patchCalls()).toHaveLength(0)
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* 6. Suppression                                                       */
/* ═══════════════════════════════════════════════════════════════════ */

describe('RapportsWorkflowPanel — suppression (admin uniquement)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    installRoutes()
  })

  it('ouvre la modale de suppression avec un commentaire optionnel', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))

    expect(await screen.findByRole('heading', { name: 'Supprimer le rapport' })).toBeInTheDocument()
    expect(screen.getByText('Commentaire (optionnel)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmer' })).toBeInTheDocument()
  })

  it('DELETE avec le motif saisi, déselectionne le rapport et rafraîchit la liste', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    expect(await screen.findByRole('heading', { name: 'Rapport trimestriel — T3' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Supprimer' }))
    expect(await screen.findByRole('heading', { name: 'Supprimer le rapport' })).toBeInTheDocument()
    fireEvent.change(within(modalBox()).getByRole('textbox'), { target: { value: 'Doublon' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledTimes(1))
    const [path, opts] = apiMock.delete.mock.calls[0]
    expect(path).toBe('/statistiques/rapports/3/')
    expect(opts).toEqual({ data: { motif: 'Doublon' } })

    expect(await screen.findByText('Rapport supprimé')).toBeInTheDocument()
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Supprimer le rapport' })).not.toBeInTheDocument())
    expect(screen.getByText('Sélectionnez un rapport dans la liste.')).toBeInTheDocument()
    // La liste a été rechargée après suppression.
    expect(listCalls().length).toBeGreaterThan(1)
  })

  it('DELETE avec une chaîne de motif vide si rien n’est saisi', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
    expect(await screen.findByRole('heading', { name: 'Supprimer le rapport' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledTimes(1))
    expect(apiMock.delete.mock.calls[0][1]).toEqual({ data: { motif: '' } })
  })

  it('une erreur de suppression émet un toast et conserve la sélection et la modale', async () => {
    apiMock.delete.mockImplementationOnce(async () => { throw apiError('Suppression refusée') })
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
    expect(await screen.findByRole('heading', { name: 'Supprimer le rapport' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer' }))

    expect(await screen.findByText('Suppression refusée')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Supprimer le rapport' })).toBeInTheDocument()
    // Le détail reste sélectionné.
    expect(screen.getByRole('heading', { name: 'Rapport trimestriel — T3' })).toBeInTheDocument()
  })

  it('l’Annulation ferme la modale sans DELETE', async () => {
    mountPanel()
    fireEvent.click(await screen.findByRole('button', { name: /Rapport trimestriel — T3/ }))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
    expect(await screen.findByRole('heading', { name: 'Supprimer le rapport' })).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await waitFor(() => expect(screen.queryByRole('heading', { name: 'Supprimer le rapport' })).not.toBeInTheDocument())
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it('un secrétariat ne voit pas le bouton Supprimer', async () => {
    renderWithProviders(<RapportsWorkflowPanel user={makeUser('SECRETARIAT')} />)
    fireEvent.click(await screen.findByRole('button', { name: /Bilan annuel 2025/ }))

    await waitFor(() => expect(detailCalls()).toHaveLength(1))
    expect(screen.queryByRole('button', { name: 'Supprimer' })).not.toBeInTheDocument()
  })
})
