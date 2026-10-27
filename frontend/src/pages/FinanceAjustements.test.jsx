/**
 * LOT 29 — Finance : ajustements horaires (`pages/FinanceAjustements.jsx`).
 * Corrections manuelles sur séances réelles : KPI et filtres par statut,
 * workflow valider / rejeter (motif obligatoire), proposition d'ajustement
 * avec recherche d'enseignant débordancée et choix d'une séance issue du
 * rapport finance d'un formateur.
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
import { flushPromises, wait as sleep } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import FinanceAjustements from '@/pages/FinanceAjustements'

const AJUST_PATH = '/formations/finance/ajustements/'
const FORMATEURS_PATH = '/formations/formateurs/list/'
const REPORT_PATH = '/formations/formateurs/finance-report/'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

const liste = {
  pending_count: 3,
  items: [
    {
      id: 1, statut: 'EN_ATTENTE', statut_label: 'En attente',
      formateur: { label: 'Mariam Traoré' },
      session: { module_intitule: 'LSF Niveau 1', grade: 'L1', groupe: 'G1', date_journee: '2026-03-02' },
      minutes_delta: 30, realise_avant_minutes: 60, realise_apres_minutes: 90,
      motif: 'Séance prolongée', proposed_by: 'jfinance', proposed_at: '2026-03-04T10:20:00Z',
    },
    {
      id: 2, statut: 'EN_ATTENTE', statut_label: 'En attente',
      formateur: { label: 'Koffi Diop' },
      session: { module_intitule: 'Interprétation', grade: 'M2', groupe: 'G3', date_journee: '2026-03-03' },
      minutes_delta: -15, realise_avant_minutes: 120, realise_apres_minutes: 105,
      motif: 'Coupure réseau', proposed_by: 'jfinance', proposed_at: '2026-03-04T11:00:00Z',
    },
    {
      id: 3, statut: 'VALIDE', statut_label: 'Validé',
      formateur: { label: 'Awa Koné' },
      session: { module_intitule: 'Lecture labiale', grade: '', groupe: '', date_journee: '2026-02-20' },
      minutes_delta: 45, realise_avant_minutes: 300, realise_apres_minutes: 345,
      motif: 'Remplacement', proposed_by: 'secret', proposed_at: '2026-02-21T08:00:00Z',
      validated_by: 'Marie Validation',
    },
    {
      id: 4, statut: 'REJETE', statut_label: 'Rejeté',
      formateur: { label: 'Yao Brou' },
      session: { module_intitule: 'Grammaire', grade: 'L2', groupe: 'G2', date_journee: '2026-02-15' },
      minutes_delta: -90, realise_avant_minutes: 200, realise_apres_minutes: 110,
      motif: 'Erreur de saisie manifeste sur la journée', proposed_by: 'secret',
      proposed_at: '2026-02-16T09:30:00Z',
      rejection_motif: 'Justificatif absent pour une réduction aussi importante.',
    },
    {
      id: 5, statut: 'REJETE', statut_label: 'Rejeté',
      formateur: { label: 'Sans Motif' },
      session: { module_intitule: 'Atelier', grade: 'L1', groupe: 'G1', date_journee: '2026-02-10' },
      minutes_delta: 10, realise_avant_minutes: 60, realise_apres_minutes: 70,
      motif: 'À vérifier', proposed_by: 'secret', proposed_at: '2026-02-11T09:00:00Z',
      rejection_motif: '',
    },
    {
      id: 6, statut: 'INCONNU_99', statut_label: 'Brouillon',
      formateur: { label: 'Sans Statut' },
      session: { module_intitule: 'Module mystère' },
      minutes_delta: 0, realise_avant_minutes: 0, realise_apres_minutes: 0,
      motif: 'Mystère', proposed_by: 'x', proposed_at: 'date-illisible',
    },
    {
      id: 7, statut: 'EN_ATTENTE', statut_label: 'En attente',
      // Données lacunaires : ni formateur, ni session.
      minutes_delta: 5, motif: 'Données lacunaires', proposed_by: 'y', proposed_at: null,
    },
  ],
}

// Résultat de la recherche d'enseignants (GET formateurs/list/).
const formateurs = {
  results: [
    { id: 700, nom: 'Traoré', prenom: 'Mariam', specialite: 'LSF', numerobadge: 'F-700' },
    { id: 701, nom: 'Traoré', prenom: 'Ibrahim', specialite: '', numerobadge: 'F-701' },
  ],
}

// Séances disponibles (GET formateurs/finance-report/) : deux blocs results,
// une séance sans date à filtrer et des dates à trier en ordre décroissant.
const report = {
  results: [
    {
      sessions: [
        { session_id: 101, date_journee: '2026-03-10', module_intitule: 'LSF 2', grade: 'L1', groupe: 'G2', duree_minutes: 120.4 },
        { session_id: 102, date_journee: '2026-03-12', module_intitule: 'LSF 3', grade: '', groupe: '', duree_minutes: 90 },
        { session_id: 103, date_journee: '', module_intitule: 'Sans date', grade: 'L1', groupe: '', duree_minutes: 60 },
      ],
    },
    {
      sessions: [
        { session_id: 104, date_journee: '2026-03-11', module_intitule: 'LSF 4', grade: 'M1', groupe: 'G1', duree_minutes: 45 },
        // Grade sans groupe (parenthèses réduites) et durée absente -> 0 min.
        { session_id: 105, date_journee: '2026-03-09', module_intitule: 'LSF 5', grade: 'L3', groupe: '' },
      ],
    },
  ],
}

// Rapports dégradés : résultats sans clé sessions, puis sans clé results.
const reportDegrade = { results: [{ sessions: [] }, {}] }
const reportVide = {}

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }
// Le debounce de la recherche est de 300 ms (horloge réelle, comme dans les
// tests de ModuleDetail/FormationDetail) : on attend un peu au-delà, dans act.
const waitReal = async (ms = 360) => { await act(async () => { await sleep(ms) }) }

const mount = () => {
  const me = makeUser('FINANCE', { username: 'finance' })
  apiController.setMe(me)
  return renderWithProviders(<FinanceAjustements />, {
    authUser: me,
    routePattern: '/finance-ajustements',
    initialEntries: ['/finance-ajustements'],
  })
}

const kpiCard = (labelText) => {
  const label = screen.getByText(
    (_c, el) => el.classList?.contains('finance-hero-kpi-label') && el.textContent.includes(labelText),
  )
  return label.closest('.finance-hero-kpi')
}

const filterTab = (labelText) =>
  within(document.querySelector('.finance-rank-tabs')).getByRole('button', { name: new RegExp(labelText, 'i') })

const rowFor = (formateurLabel) =>
  screen.getByText(formateurLabel).closest('tr')

const getCalls = (path) => apiMock.get.mock.calls.filter(([p]) => p === path)
const postCall = (suffix) =>
  apiMock.post.mock.calls.find(([p]) => p.endsWith(suffix))

// Les labels du formulaire n'ont pas de htmlFor : champ du même bloc.
const formField = (labelText) => {
  const label = screen.getByText(
    (_c, el) => el.tagName === 'LABEL' && el.textContent.trim() === labelText,
  )
  return label.parentElement.querySelector('input, select, textarea')
}

const openForm = () => fireEvent.click(screen.getByRole('button', { name: /nouvel ajustement/i }))

// La recherche d'enseignant est débordancée à 300 ms via setTimeout : après
// le nettoyage RTL de chaque test, on laisse les minuteurs résiduels tirer
// sur le composant démonté pour ne pas polluer les tests suivants (act).
afterEach(async () => { await waitReal(320) })

/* ------------------------------------------------------------------ */
/* LOT 29 — chargement, KPI, filtres, table                            */
/* ------------------------------------------------------------------ */

describe('pages/FinanceAjustements.jsx — chargement, KPI et filtres (LOT 29)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute(AJUST_PATH, () => liste)
  })

  it('charge la liste et affiche titre, sous-titre, navigation sans filtre de période', async () => {
    const { container } = mount()
    expect(container.querySelector('.finance-empty .spinner-border')).toBeTruthy()
    await settle()

    expect(apiMock.get).toHaveBeenCalledWith(AJUST_PATH)
    expect(screen.getByRole('heading', { name: 'Ajustements horaires', level: 1 })).toBeInTheDocument()
    expect(screen.getByText(/workflow validation, impact paie, journal d'audit/i)).toBeInTheDocument()
    for (const label of ['Tableau de bord', 'Enseignants', 'Encadrants', 'Paramétrage']) {
      expect(screen.getByRole('link', { name: new RegExp(label, 'i') })).toBeInTheDocument()
    }
    const actif = screen.getByRole('link', { name: /ajustements/i })
    expect(actif).toHaveClass('btn-finance-accent')
    // Le compteur d'ajustements en attente est reporté sur la navigation.
    expect(within(actif).getByText('3')).toHaveClass('badge')
    expect(document.querySelector('.finance-filter-panel')).toBeNull()
  })

  it('calcule les quatre KPI selon les statuts', async () => {
    mount()
    await settle()
    expect(within(kpiCard('Total')).getByText('7')).toBeInTheDocument()
    expect(within(kpiCard('En attente')).getByText('3')).toBeInTheDocument()
    expect(within(kpiCard('Validés')).getByText('1')).toBeInTheDocument()
    expect(within(kpiCard('Rejetés')).getByText('2')).toBeInTheDocument()
  })

  it('filtre par statut côté client (En attente par défaut, Validés, Rejetés, Tous)', async () => {
    mount()
    await settle()
    expect(document.querySelectorAll('table.finance-table tbody tr')).toHaveLength(3)

    fireEvent.click(filterTab('Validés'))
    await settle()
    let rows = document.querySelectorAll('table.finance-table tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('Awa Koné')

    fireEvent.click(filterTab('Rejetés'))
    await settle()
    rows = document.querySelectorAll('table.finance-table tbody tr')
    expect(rows).toHaveLength(2)
    expect(rows[0]).toHaveTextContent('Yao Brou')

    fireEvent.click(filterTab('Tous'))
    await settle()
    expect(document.querySelectorAll('table.finance-table tbody tr')).toHaveLength(7)
  })

  it("affiche un delta positif (vert, flèche haut, signe +) et négatif (rouge)", async () => {
    mount()
    await settle()
    const pos = within(rowFor('Mariam Traoré')).getByText(/\+30 min/)
    expect(pos).toHaveClass('text-success')
    expect(pos.closest('.finance-evolution')).toHaveAttribute('data-positive', 'true')
    expect(rowFor('Mariam Traoré').querySelector('.bi-arrow-up')).toBeTruthy()

    const neg = within(rowFor('Koffi Diop')).getByText(/-15 min/)
    expect(neg).toHaveClass('text-danger')
    expect(neg.closest('.finance-evolution')).toHaveAttribute('data-positive', 'false')
    expect(rowFor('Koffi Diop').querySelector('.bi-arrow-down')).toBeTruthy()
  })

  it('détaille une ligne : statut, séance, avant→après, motif et proposition datée', async () => {
    mount()
    await settle()
    const row = rowFor('Mariam Traoré')
    expect(within(row).getByText('En attente')).toHaveClass('bg-warning')
    expect(row).toHaveTextContent('LSF Niveau 1')
    expect(row).toHaveTextContent('L1 G1')
    expect(row).toHaveTextContent('2026-03-02')
    // 60 min = 1h → 90 min = 1h 30min.
    expect(row).toHaveTextContent('1h')
    expect(row).toHaveTextContent('1h 30min')
    expect(row).toHaveTextContent('Séance prolongée')
    expect(row).toHaveTextContent('jfinance')
    // Format fr-FR avec mois en lettres (le padding du jour et un éventuel
    // « à » avant l'heure varient selon la version ICU : on reste souple).
    expect(row.textContent).toMatch(/0?4 mars 2026/)
  })

  it("affiche le valideur pour un VALIDE et le motif de rejet tronqué (ou tiret) pour un REJETE", async () => {
    mount()
    await settle()
    fireEvent.click(filterTab('Validés'))
    await settle()
    const valide = rowFor('Awa Koné')
    expect(within(valide).getByText(/Marie Validation/)).toBeInTheDocument()
    expect(valide.querySelectorAll('button')).toHaveLength(0)

    fireEvent.click(filterTab('Rejetés'))
    await settle()
    const rejete = rowFor('Yao Brou')
    const longMotif = 'Justificatif absent pour une réduction aussi importante.'
    const raison = within(rejete).getByTitle(longMotif)
    expect(raison.textContent.endsWith('…')).toBe(true)
    expect(raison.textContent).toHaveLength(41) // 40 caractères + « … »
    expect(rejete.querySelectorAll('button')).toHaveLength(0)

    const sansMotif = rowFor('Sans Motif')
    expect(within(sansMotif).getByText('—')).toBeInTheDocument()
  })

  it("replie sur une apparence neutre pour un statut inconnu, sans action", async () => {
    mount()
    await settle()
    fireEvent.click(filterTab('Tous'))
    await settle()
    const row = rowFor('Sans Statut')
    const badge = within(row).getByText('Brouillon')
    expect(badge).toHaveClass('bg-light')
    expect(row.querySelector('.bi-circle')).toBeTruthy()
    expect(row.querySelectorAll('button')).toHaveLength(0)
    // Date d'audit illisible -> tiret.
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0)
  })

  it("fonctionne sans la clé items et reporte quand même pending_count dans la navigation", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => ({ pending_count: 4 }))
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    expect(screen.getByText(/aucun ajustement avec le statut/i)).toBeInTheDocument()
    fireEvent.click(filterTab('Tous'))
    expect(screen.getByText('Aucun ajustement.')).toBeInTheDocument()
    const nav = screen.getByRole('link', { name: /ajustements/i })
    expect(within(nav).getByText('4')).toBeInTheDocument()
    // Tous les KPI sont à zéro.
    expect(within(kpiCard('Total')).getByText('0')).toBeInTheDocument()
  })

  it("n'expose Valider/Rejeter que pour les lignes en attente (y compris lacunaire)", async () => {
    mount()
    await settle()
    const row1 = rowFor('Mariam Traoré')
    expect(within(row1).getByRole('button', { name: /valider/i })).toBeInTheDocument()
    expect(within(row1).getByRole('button', { name: /rejeter/i })).toBeInTheDocument()
    const rowLacunaire = screen.getByText('Données lacunaires').closest('tr')
    expect(within(rowLacunaire).getByRole('button', { name: /valider/i })).toBeInTheDocument()
    // Date d'audit absente -> tiret.
    expect(within(rowLacunaire).getAllByText('—').length).toBeGreaterThan(0)
  })

  it("affiche le message vide spécifique au statut puis générique pour « Tous »", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => ({ items: [], pending_count: 0 }))
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    expect(screen.getByText(/aucun ajustement avec le statut "En attente"/i)).toBeInTheDocument()
    fireEvent.click(filterTab('Tous'))
    expect(screen.getByText('Aucun ajustement.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 29 — valider / rejeter                                          */
/* ------------------------------------------------------------------ */

describe('pages/FinanceAjustements.jsx — workflow de validation (LOT 29)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute(AJUST_PATH, () => liste)
  })

  it('valide un ajustement : POST valider, notification et rechargement', async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('Mariam Traoré')).getByRole('button', { name: /valider/i }))
    await waitFor(() => expect(postCall('/1/valider/')).toBeTruthy())
    expect(await screen.findByText('Ajustement validé — impact paie appliqué')).toBeInTheDocument()
    // Rechargement de la liste après action.
    expect(getCalls(AJUST_PATH).length).toBeGreaterThanOrEqual(2)
  })

  it("désactive les boutons de la ligne pendant l'action et affiche un spinner", async () => {
    let resolveAction
    apiMock.post.mockImplementation((path) => {
      if (path.endsWith('/2/valider/')) {
        return new Promise((res) => { resolveAction = () => res({ data: {} }) })
      }
      return Promise.resolve({ data: {} })
    })
    mount()
    await settle()
    const row = rowFor('Koffi Diop')
    fireEvent.click(within(row).getByRole('button', { name: /valider/i }))
    expect(within(row).getByRole('button', { name: /valider/i })).toBeDisabled()
    expect(within(row).getByRole('button', { name: /rejeter/i })).toBeDisabled()
    expect(row.querySelector('.spinner-border')).toBeTruthy()
    await act(async () => { resolveAction(); await flushPromises(4) })
    expect(within(row).getByRole('button', { name: /valider/i })).toBeEnabled()
  })

  it("notifie le détail d'une erreur de validation puis le message générique", async () => {
    mount()
    await settle()
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Clôture déjà payée' } } })
    fireEvent.click(within(rowFor('Mariam Traoré')).getByRole('button', { name: /valider/i }))
    expect(await screen.findByText('Clôture déjà payée')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(rowFor('Koffi Diop')).getByRole('button', { name: /valider/i }))
    expect(await screen.findByText('Validation impossible')).toBeInTheDocument()
  })

  it('ouvre la modale de rejet avec son résumé (delta positif en vert)', async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('Mariam Traoré')).getByRole('button', { name: /rejeter/i }))
    let modal
    await waitFor(() => { modal = document.querySelector('.modal.show'); expect(modal).toBeTruthy() })
    expect(within(modal).getByText(/rejeter l'ajustement/i)).toBeInTheDocument()
    expect(within(modal).getByText('Mariam Traoré')).toBeInTheDocument()
    expect(within(modal).getByText('2026-03-02')).toBeInTheDocument()
    const delta = within(modal).getByText(/\+30 min/)
    expect(delta).toHaveClass('text-success')
    // Le bouton de confirmation est désactivé tant que le motif est vide.
    expect(within(modal).getByRole('button', { name: /confirmer le rejet/i })).toBeDisabled()
  })

  it('affiche le delta en rouge dans le résumé pour un ajustement négatif', async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('Koffi Diop')).getByRole('button', { name: /rejeter/i }))
    let modal
    await waitFor(() => { modal = document.querySelector('.modal.show'); expect(modal).toBeTruthy() })
    expect(within(modal).getByText(/-15 min/)).toHaveClass('text-danger')
  })

  it('rejette avec motif : POST rejeter (motif élagué), notification, fermeture et rechargement', async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('Mariam Traoré')).getByRole('button', { name: /rejeter/i }))
    let modal
    await waitFor(() => { modal = document.querySelector('.modal.show'); expect(modal).toBeTruthy() })
    const textarea = modal.querySelector('textarea')
    fireEvent.change(textarea, { target: { value: '  Doublon avec la séance du matin  ' } })
    const confirmer = within(modal).getByRole('button', { name: /confirmer le rejet/i })
    expect(confirmer).toBeEnabled()
    fireEvent.click(confirmer)
    await waitFor(() => expect(postCall('/1/rejeter/')).toBeTruthy())
    expect(postCall('/1/rejeter/')[1]).toEqual({ motif: 'Doublon avec la séance du matin' })
    expect(await screen.findByText('Ajustement rejeté')).toBeInTheDocument()
    expect(document.querySelector('.modal.show')).toBeNull()
  })

  it("annule un rejet (croix et bouton Annuler) sans aucun appel d'écriture", async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('Koffi Diop')).getByRole('button', { name: /rejeter/i }))
    let modal
    await waitFor(() => { modal = document.querySelector('.modal.show'); expect(modal).toBeTruthy() })
    fireEvent.change(modal.querySelector('textarea'), { target: { value: 'Un motif' } })
    fireEvent.click(within(modal).getByRole('button', { name: /annuler/i }))
    await settle()
    expect(document.querySelector('.modal.show')).toBeNull()

    // Réouverture puis fermeture par la croix : la modale est réinitialisée.
    fireEvent.click(within(rowFor('Koffi Diop')).getByRole('button', { name: /rejeter/i }))
    await waitFor(() => { modal = document.querySelector('.modal.show'); expect(modal).toBeTruthy() })
    expect(modal.querySelector('textarea')).toHaveValue('')
    fireEvent.click(modal.querySelector('.btn-close'))
    await settle()
    expect(document.querySelector('.modal.show')).toBeNull()
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it("garde la modale ouverte et notifie l'erreur de rejet (détaillée puis générique)", async () => {
    mount()
    await settle()
    fireEvent.click(within(rowFor('Mariam Traoré')).getByRole('button', { name: /rejeter/i }))
    let modal
    await waitFor(() => { modal = document.querySelector('.modal.show'); expect(modal).toBeTruthy() })
    fireEvent.change(modal.querySelector('textarea'), { target: { value: 'Non' } })

    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Période clôturée' } } })
    fireEvent.click(within(modal).getByRole('button', { name: /confirmer le rejet/i }))
    expect(await screen.findByText('Période clôturée')).toBeInTheDocument()
    expect(document.querySelector('.modal.show')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    modal = document.querySelector('.modal.show')
    fireEvent.change(modal.querySelector('textarea'), { target: { value: 'Non vraiment' } })
    fireEvent.click(within(modal).getByRole('button', { name: /confirmer le rejet/i }))
    expect(await screen.findByText('Rejet impossible')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 29 — proposition d'ajustement (formulaire + pickers)           */
/* ------------------------------------------------------------------ */

describe('pages/FinanceAjustements.jsx — proposition d’ajustement (LOT 29)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => formateurs)
    apiController.setRoute(REPORT_PATH, () => report)
  })

  it('ouvre puis referme le formulaire (la fermeture réinitialise les champs)', async () => {
    mount()
    await settle()
    openForm()
    expect(screen.getByText('Proposer un ajustement')).toBeInTheDocument()
    expect(formField('Enseignant')).toBeInTheDocument()
    // Le sélecteur de séance est verrouillé tant qu'aucun enseignant n'est choisi.
    expect(formField('Séance')).toBeDisabled()

    // Passe par « Annuler » (pied de formulaire), puis rouvre : tout est remis à zéro.
    fireEvent.change(formField('Minutes (+/−)'), { target: { value: '25' } })
    fireEvent.click(within(document.querySelector('form')).getByRole('button', { name: /annuler/i }))
    await settle()
    expect(screen.queryByText('Proposer un ajustement')).toBeNull()

    openForm()
    expect(formField('Minutes (+/−)')).toHaveValue(null)
  })

  it('recherche les enseignants après 2 caractères et 300 ms de debounce', async () => {
    mount()
    await settle()
    // Le minuteur initial (recherche vide) tire au montage : aucun appel et
    // ça couvre le court-circuit « recherche vide ».
    await waitReal(320)
    expect(getCalls(FORMATEURS_PATH)).toHaveLength(0)

    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 't' } })
    await waitReal(360)
    expect(getCalls(FORMATEURS_PATH)).toHaveLength(0) // un seul caractère ne suffit pas

    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(getCalls(FORMATEURS_PATH).length).toBe(1))
    expect(getCalls(FORMATEURS_PATH)[0][1]).toEqual({ params: { search: 'tra', page_size: 20 } })
    // Deux enseignants proposés avec matricule et spécialité.
    const liste1 = screen.getByText('#F-700').closest('ul')
    expect(liste1).toHaveTextContent('Traoré')
    expect(liste1).toHaveTextContent('Mariam')
    expect(liste1).toHaveTextContent('LSF')
    expect(screen.getByText('#F-701')).toBeInTheDocument()
  })

  it('affiche un spinner pendant la recherche puis masque la liste après sélection', async () => {
    let resolveSearch
    mount()
    await settle()
    openForm()
    // Diffère uniquement la recherche d'enseignants (posé après le montage
    // pour ne pas être consommé par /auth/me/ ou le chargement initial) ;
    // les appels suivants (rapport de séances) retombent sur les routes du mock.
    apiMock.get.mockImplementationOnce(async (path) => {
      if (path === FORMATEURS_PATH) {
        return await new Promise((res) => { resolveSearch = () => res({ data: formateurs }) })
      }
      return { data: {} }
    })
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitReal(360) // laisse le debounce de 300 ms tirer (promesse toujours différée)
    const input = formField('Enseignant').parentElement
    expect(input.querySelector('.spinner-border')).toBeTruthy()
    await act(async () => { resolveSearch(); await flushPromises(4) })
    expect(screen.getByText('#F-700')).toBeInTheDocument()
    // La liste déroulante peut contenir plusieurs « #F-700 » : on choisit le li.
    const option = screen.getByText('#F-700').closest('li')
    await act(async () => {
      fireEvent.mouseDown(option)
      await flushPromises(5)
    })
    // La liste déroulante se ferme ; le matricule reste affiché dans la fiche.
    expect(document.querySelector('.list-group')).toBeNull()
    expect(screen.getByText(/#F-700/)).toBeInTheDocument()
  })

  it("charge les séances de l'enseignant choisi (filtrées sans date, triées date desc)", async () => {
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => {
      expect(getCalls(REPORT_PATH).length).toBe(1)
      expect(formField('Séance')).toBeEnabled()
    })
    expect(getCalls(REPORT_PATH)[0][1]).toEqual({
      params: { formateur_id: 700, include_sessions: 1, preset: 'tout' },
    })
    // L'enseignant sélectionné s'affiche en fiche avec son matricule.
    expect(screen.getByText(/#F-700/)).toBeInTheDocument()
    expect(screen.getByText(/Traoré Mariam/)).toBeInTheDocument()

    const select = formField('Séance')
    expect(select).toBeEnabled()
    // Trois séances datées (la séance sans date est écartée), tri récent d'abord.
    const options = [...select.options].map((o) => o.textContent)
    expect(options[0]).toContain('Choisir une séance')
    expect(options[1]).toContain('2026-03-12')
    expect(options[2]).toContain('2026-03-11')
    expect(options[3]).toContain('2026-03-10')
    expect(options[4]).toContain('2026-03-09')
    expect(options).toHaveLength(5) // 4 séances datées + le placeholder ; la sans-date est exclue
    expect(options.some((o) => o.includes('Sans date'))).toBe(false)
    // Libellé : grade/groupe entre parenthèses, durée arrondie.
    expect(options[3]).toContain('LSF 2')
    expect(options[3]).toContain('(L1 G2)')
    expect(options[3]).toContain('120 min') // 120,4 arrondi
    // Séance sans grade/groupe : pas de parenthèses.
    expect(options[1]).not.toContain('(')
    // Grade sans groupe : parenthèses réduites ; durée absente -> 0 min.
    expect(options[4]).toContain('(L3)')
    expect(options[4]).toContain('0 min')
  })

  it("propose « aucune séance » quand l'enseignant n'en a pas", async () => {
    apiController.reset()
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => formateurs)
    apiController.setRoute(REPORT_PATH, () => ({ results: [] }))
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await settle()
    expect(formField('Séance').querySelector('option')).toHaveTextContent('Aucune séance disponible')
  })

  it("encaisse des rapports dégradés (result sans sessions, puis résultats absents)", async () => {
    // Variante 1 : results présent mais un bloc sans clé sessions.
    apiController.reset()
    let me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => formateurs)
    apiController.setRoute(REPORT_PATH, () => reportDegrade)
    const rendu1 = renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    expect(formField('Séance').querySelector('option')).toHaveTextContent('Aucune séance disponible')
    rendu1.unmount()

    // Variante 2 : même pas de clé results.
    apiController.reset()
    me = makeUser('FINANCE', { username: 'finance2' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => formateurs)
    apiController.setRoute(REPORT_PATH, () => reportVide)
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    expect(formField('Séance').querySelector('option')).toHaveTextContent('Aucune séance disponible')
  })

  it("referme le formulaire par le bouton d'en-tête et réinitialise les champs", async () => {
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Minutes (+/−)'), { target: { value: '99' } })
    // Le bouton d'en-tête (hors <form>) bascule à « Annuler » quand le form est ouvert.
    const boutonEntete = screen
      .getAllByRole('button', { name: /annuler/i })
      .find((b) => !b.closest('form'))
    expect(boutonEntete).toBeTruthy()
    fireEvent.click(boutonEntete)
    await settle()
    expect(screen.queryByText('Proposer un ajustement')).toBeNull()
    openForm()
    expect(formField('Minutes (+/−)')).toHaveValue(null)
  })

  it("permet de changer d'enseignant (croix/crayon) et réinitialise la séance", async () => {
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    fireEvent.change(formField('Séance'), { target: { value: '102' } })

    // Bouton « Changer » de la fiche enseignant.
    fireEvent.click(screen.getByTitle('Changer'))
    await settle()
    expect(screen.getByPlaceholderText('Nom ou matricule…')).toBeInTheDocument()
    expect(formField('Séance')).toBeDisabled()
    expect(formField('Séance').querySelector('option')).toHaveTextContent("Sélectionner un enseignant d'abord")
  })

  it('soumet une proposition avec le payload exact puis referme et recharge', async () => {
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    fireEvent.change(formField('Séance'), { target: { value: '102' } })
    fireEvent.change(formField('Minutes (+/−)'), { target: { value: '-20' } })
    fireEvent.change(formField('Motif'), { target: { value: '  Fin anticipée  ' } })

    const soumettre = screen.getByRole('button', { name: /soumettre/i })
    expect(soumettre).toBeEnabled()
    fireEvent.click(soumettre)
    await waitFor(() => expect(apiController.findCall('post', AJUST_PATH)).toBeTruthy())
    expect(apiController.lastBody('post')).toEqual({
      session_id: 102, formateur_id: 700, minutes_delta: -20, motif: 'Fin anticipée',
    })
    expect(await screen.findByText('Ajustement proposé — en attente de validation')).toBeInTheDocument()
    // Le formulaire est refermé, la liste rechargée.
    expect(screen.queryByText('Proposer un ajustement')).toBeNull()
    expect(getCalls(AJUST_PATH).length).toBeGreaterThanOrEqual(2)
  })

  it("désactive le bouton Soumettre tant que la séance n'est pas choisie", async () => {
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    fireEvent.change(formField('Minutes (+/−)'), { target: { value: '10' } })
    fireEvent.change(formField('Motif'), { target: { value: 'Un motif' } })
    expect(screen.getByRole('button', { name: /soumettre/i })).toBeDisabled()
    fireEvent.change(formField('Séance'), { target: { value: '101' } })
    expect(screen.getByRole('button', { name: /soumettre/i })).toBeEnabled()
  })

  it("affiche l'état « Envoi… » pendant la soumission", async () => {
    let resolvePost
    apiMock.post.mockImplementation((path) => {
      if (path === AJUST_PATH) {
        return new Promise((res) => { resolvePost = () => res({ data: {} }) })
      }
      return Promise.resolve({ data: {} })
    })
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    fireEvent.change(formField('Séance'), { target: { value: '102' } })
    fireEvent.change(formField('Minutes (+/−)'), { target: { value: '5' } })
    fireEvent.change(formField('Motif'), { target: { value: 'Retard' } })
    fireEvent.click(screen.getByRole('button', { name: /soumettre/i }))
    expect(screen.getByRole('button', { name: /envoi/i })).toBeInTheDocument()
    await act(async () => { resolvePost(); await flushPromises(4) })
    expect(await screen.findByText('Ajustement proposé — en attente de validation')).toBeInTheDocument()
  })

  it("notifie l'erreur de proposition détaillée puis générique sans fermer le formulaire", async () => {
    mount()
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await waitFor(() => expect(formField('Séance')).toBeEnabled())
    fireEvent.change(formField('Séance'), { target: { value: '102' } })
    fireEvent.change(formField('Minutes (+/−)'), { target: { value: '5' } })
    fireEvent.change(formField('Motif'), { target: { value: 'Raison' } })

    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Séance déjà soldée' } } })
    fireEvent.click(screen.getByRole('button', { name: /soumettre/i }))
    expect(await screen.findByText('Séance déjà soldée')).toBeInTheDocument()
    expect(screen.getByText('Proposer un ajustement')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(screen.getByRole('button', { name: /soumettre/i }))
    expect(await screen.findByText('Proposition impossible')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 29 — erreurs de chargement et pickers dégradés                  */
/* ------------------------------------------------------------------ */

describe('pages/FinanceAjustements.jsx — filets défensifs (LOT 29)', () => {
  beforeEach(() => {
    apiController.reset()
  })

  it("notifie le détail d'une erreur de chargement puis le message générique", async () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Module finance indisponible' } } }
    })
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    expect(await screen.findByText('Module finance indisponible')).toBeInTheDocument()
  })

  it("générique si l'erreur de chargement n'a pas de détail (y compris réponse null)", async () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => null)
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    expect(await screen.findByText('Erreur de chargement')).toBeInTheDocument()
    // Le spinner s'est bien arrêté.
    await settle()
    expect(document.querySelector('.finance-empty .spinner-border')).toBeNull()
  })

  it("encaisse un échec de recherche d'enseignants (liste vide, sans crash)", async () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => {
      throw new Error('500')
    })
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitReal(360)
    expect(screen.queryByText('#F-700')).toBeNull()
    expect(screen.getByPlaceholderText('Nom ou matricule…')).toBeInTheDocument()
  })

  it("encaisse une recherche d'enseignants sans clé results (liste vide)", async () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => ({ autre: 1 }))
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitReal(360)
    expect(document.querySelector('.list-group')).toBeNull()
  })

  it("encaisse un échec du rapport de séances (aucune séance disponible)", async () => {
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    apiController.setRoute(AJUST_PATH, () => liste)
    apiController.setRoute(FORMATEURS_PATH, () => formateurs)
    apiController.setRoute(REPORT_PATH, () => {
      throw new Error('500')
    })
    renderWithProviders(<FinanceAjustements />, {
      authUser: me, routePattern: '/finance-ajustements', initialEntries: ['/finance-ajustements'],
    })
    await settle()
    openForm()
    fireEvent.change(formField('Enseignant'), { target: { value: 'tra' } })
    await waitFor(() => expect(screen.getByText('#F-700')).toBeInTheDocument())
    fireEvent.mouseDown(screen.getByText('#F-700').closest('li'))
    await settle()
    expect(formField('Séance').querySelector('option')).toHaveTextContent('Aucune séance disponible')
  })
})
