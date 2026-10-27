/**
 * LOT 30 — Finance : tableau de bord (`pages/FinanceDashboard.jsx`), dernier
 * écran du module Finance transverse. Cinq KPI héro cliquables (ventilation
 * par module), KPI d'effectifs, activité mensuelle, spécialités et leur
 * forage, classement des enseignants (trois mesures, médailles), synthèse de
 * paie paginée, badges de tolérance, comparaison de période et filtre de
 * période partagé.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
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
import FinanceDashboard from '@/pages/FinanceDashboard'

const DASH_PATH = '/formations/finance/dashboard/'

const moisCourant = () => {
  const n = new Date()
  return `${n.getFullYear()}-${String(n.getMonth() + 1).padStart(2, '0')}`
}
const anneeCourante = () => String(new Date().getFullYear())

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

const volumes = [
  {
    module_id: 1, module_intitule: 'LSF Niveau 1', formation_intitule: 'Licence LSF',
    grade: 'L1', groupe: 'G1', secretariat_nom: 'INJS Marcory', sessions_count: 5,
    total_duree_minutes: 300, total_duree_realisee_minutes: 240, taux_realisation_pct: 80,
    montant_prevu: 100000, montant_realise: 80000, prix_heure_realisee: 5000,
  },
  {
    module_id: 2, module_intitule: 'Interprétation', formation_intitule: 'Master Interprétation',
    grade: 'M2', groupe: 'G3', sessions_count: 2,
    total_duree_minutes: 120, total_duree_realisee_minutes: 60, taux_realisation_pct: 50,
    montant_prevu: 50000, montant_realise: 40000, prix_heure_realisee: null,
  },
  {
    module_id: 3, // champs lacunaires : tous les replis « — »
    sessions_count: undefined,
    total_duree_minutes: 60, total_duree_realisee_minutes: 60, taux_realisation_pct: 100,
    montant_prevu: 30000, montant_realise: 30000,
  },
]

// 26 enseignants de synthèse pour faire deux pages (25/page).
const syntheseRows = Array.from({ length: 26 }, (_, i) => {
  const tolerance =
    i === 0 ? null
      : i === 1 ? { tolerance_active: true, statut: 'ok', statut_label: 'Conforme ✓' }
        : i === 2 ? { tolerance_active: true, statut: 'alerte' }
          : i === 3 ? { tolerance_active: true, statut: 'anomalie' }
            : i === 4 ? { tolerance_active: true, statut: 'ecart' }
              : i === 5 ? { tolerance_active: true, statut: 'STATUT_INCONNU' }
                : { tolerance_active: false, statut: 'anomalie' }
  return {
    id: 500 + i, numerobadge: `F-${500 + i}`, nom: `Nom${i + 1}`, prenom: `Prénom${i + 1}`,
    modules_dispenses: `Module ${i + 1}`, grades: 'L1', groupes: 'G1',
    nb_formations: 1, sessions_count: i,
    statistiques: { taux_realisation_pct: i % 2 ? 50 : 100 },
    tolerance,
    total_duree_minutes: 60 * (i + 1), total_duree_realisee_minutes: 30 * (i + 1),
    montant_total_realise: 1000 * i,
  }
})

const dashboard = {
  kpis: {
    total_duree_minutes: 120,
    total_montant_prevu: 200000,
    total_duree_realisee_minutes: 90,
    taux_realisation_global_pct: 75,
    total_montant_realise: 150000,
    total_sessions: 12,
    total_duree_heures: 2.5,
    formateurs_actifs: 4,
    total_formateurs: 6,
    formateurs_inactifs: 2,
    sessions_avec_pointage: 9,
    moyenne_heures_realisees_par_enseignant: 3.75,
    tarifs_appliques: [5000, 7500.5],
    tolerance: {
      tolerance_active: true, tolerance_minutes: 30, tolerance_pct: 5,
      formateurs_anomalie: 1, formateurs_alerte: 2, formateurs_conformes: 3,
    },
  },
  comparaison: {
    kpis: { taux_realisation_global_pct: 80 },
    evolution: {
      total_duree_minutes: { delta: 30, pourcent: 25 },            // +0h 30min, haut
      total_montant_prevu: { delta: 5000, pourcent: 2.6 },         // +5 000 F, argent
      taux_realisation_global_pct: { delta: -5, pourcent: -6.25 }, // -5 pts, bas
      total_montant_realise: { delta: 0, pourcent: 0 },            // plat
    },
  },
  periode: { label: 'Période mars', periode_label: 'Mois en cours' },
  activite_par_mois: [
    { mois: '2026-01', label: 'Jan 2026', minutes_realisees: 600, montant: 50000 },
    { mois: '2026-02', label: 'Fév 2026', minutes_realisees: 300, montant: 25000 },
    { mois: '2026-03', label: 'Mar 2026', minutes_realisees: 0, montant: 0 },
  ],
  repartition_specialites: [
    {
      specialite: 'LSF', count: 2,
      formateurs: [
        { id: 901, nom: 'Traoré', prenom: 'Mariam', numerobadge: 'F-901' },
        { id: 902, nom: 'Diop', prenom: 'Koffi' }, // pas de matricule -> tiret
      ],
    },
    { specialite: 'LFM', count: 0 }, // clé formateurs absente : repli `|| []`
  ],
  top_temps_realise: [
    { id: 11, prenom: 'Awa', nom: 'Koné', numerobadge: 'F-11', specialite: 'LSF', sessions_count: 10, total_duree_realisee_minutes: 300 },
    { id: 12, prenom: 'Ibrahim', nom: 'Traoré', numerobadge: 'F-12', specialite: 'LFM', sessions_count: 8, total_duree_realisee_minutes: 240 },
    { id: 13, prenom: 'Fatou', nom: 'Ndiaye', numerobadge: 'F-13', specialite: 'LSF', sessions_count: 6, total_duree_realisee_minutes: 180 },
    { id: 14, prenom: 'Yao', nom: 'Brou', numerobadge: 'F-14', specialite: 'LFM', sessions_count: 4, total_duree_realisee_minutes: 120 },
    { id: 15, prenom: 'Sans', nom: 'Replis', numerobadge: null, specialite: '', sessions_count: undefined, total_duree_realisee_minutes: 60 },
  ],
  top_formateurs: [
    { id: 21, prenom: 'Planif', nom: 'Un', numerobadge: 'F-21', specialite: 'LSF', sessions_count: 9, total_duree_minutes: 400 },
    { id: 22, prenom: 'Planif', nom: 'Deux', numerobadge: 'F-22', specialite: 'LFM', sessions_count: 7, total_duree_minutes: 200 },
  ],
  top_montants: [
    { id: 31, prenom: 'Riche', nom: 'Un', numerobadge: 'F-31', specialite: 'LSF', sessions_count: 11, montant_total_realise: 120000 },
    { id: 32, prenom: 'Riche', nom: 'Deux', numerobadge: 'F-32', specialite: 'LFM', sessions_count: 3, montant_total_realise: 60000 },
  ],
  volumes_par_module: volumes,
  synthese_formateurs: syntheseRows,
  generated_at: '2026-03-04T10:20:00Z',
}

// Variante « année » : valeurs reconnaissables pour valider le rechargement.
const dashboardAnnee = {
  kpis: { total_sessions: 99, total_duree_minutes: 6000, taux_realisation_global_pct: 88 },
  comparaison: null,
  activite_par_mois: [], repartition_specialites: [],
  top_temps_realise: [], top_formateurs: [], top_montants: [],
  volumes_par_module: [], synthese_formateurs: [],
}

// Variante vide : tout est absent / tableau vide.
const dashboardVide = {
  kpis: { tarifs_appliques: [] },
  comparaison: null,
  periode: {},
  activite_par_mois: [], repartition_specialites: [],
  top_temps_realise: [], top_formateurs: [], top_montants: [],
  volumes_par_module: [], synthese_formateurs: [],
}

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }

const mount = (options = {}) => {
  const me = makeUser('FINANCE', { username: 'finance' })
  if (options.data !== undefined || options.routeFn) {
    // Une route pour ce chemin existe peut-être déjà (matchRoute prend la
    // première) : on repart d'un mock propre avant de reposer l'utilisateur.
    apiController.reset()
    apiController.setMe(me)
    apiController.setRoute(DASH_PATH, options.routeFn || (() => options.data))
  } else {
    apiController.setMe(me)
  }
  return renderWithProviders(<FinanceDashboard />, {
    authUser: me,
    routePattern: '/finance-dashboard',
    initialEntries: options.initialEntries || ['/finance-dashboard'],
  })
}

const dataCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.startsWith(DASH_PATH))
    .map(([p]) => new URL(p, 'http://testserver').searchParams)
const lastParams = () => dataCalls().at(-1)

const heroCard = (labelRe) => screen.getByRole('button', { name: labelRe })
const sectionFor = (headingRe) => screen.getByRole('heading', { name: headingRe }).closest('section')
const rankTab = (label) => within(sectionFor(/classement enseignants/i)).getByRole('button', { name: new RegExp(label, 'i') })
const filterPanel = () => document.querySelector('.finance-filter-panel')
const applyButton = () => within(filterPanel()).getByRole('button', { name: /appliquer/i })
const overlay = () => document.querySelector('.modal-overlay')

const openDrill = async (cardRe) => {
  fireEvent.click(heroCard(cardRe))
  await waitFor(() => expect(document.querySelector('.modal-overlay .modal-title')).toBeTruthy())
}

/* ------------------------------------------------------------------ */
/* LOT 30 — chargement, KPI héro, tolérance, infos                     */
/* ------------------------------------------------------------------ */

describe('pages/FinanceDashboard.jsx — chargement et KPI héro (LOT 30)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DASH_PATH, (path) =>
      path.includes('preset=annee') ? dashboardAnnee : dashboard,
    )
  })

  it('affiche le spinner puis titre, navigation et requête du mois avec le panneau de période', async () => {
    const { container } = mount()
    expect(container.querySelector('.loading .spinner')).toBeTruthy()
    await settle()

    expect(lastParams().get('preset')).toBe('mois')
    expect(lastParams().get('mois')).toBe(moisCourant())
    expect(screen.getByRole('heading', { name: 'Tableau de Bord Finance', level: 1 })).toBeInTheDocument()
    expect(screen.getByText(/suivi des temps de cours et rémunération/i)).toBeInTheDocument()
    const actif = screen.getByRole('link', { name: /tableau de bord/i })
    expect(actif).toHaveClass('btn-finance-accent')
    expect(filterPanel()).toBeTruthy()
    // La période servie est affichée dans le badge du shell.
    expect(screen.getByText('Période mars')).toBeInTheDocument()
  })

  it('formate les cinq KPI héro avec leurs sous-textes et les évolutions', async () => {
    mount()
    await settle()

    // Planifié : 120 min = 2h, 12 séances, évolution +0h 30min (hausse).
    const planifie = heroCard(/volume horaire total planifié/i)
    expect(within(planifie).getByText('2h')).toBeInTheDocument()
    expect(within(planifie).getByText(/12 séance\(s\)/)).toBeInTheDocument()
    const evPlan = within(planifie).getByText(/0h 30min/)
    expect(evPlan).toHaveClass('finance-evolution--up')
    expect(evPlan.closest('.finance-evolution')).toHaveAttribute('title', expect.stringContaining('+25'))

    // Coût prévu : argent, heures planifiées arrondies (2,5 -> 3), évolution argent.
    const coutPrevu = heroCard(/coût prévisionnel/i)
    expect(within(coutPrevu).getByText(/200\s?000 FCFA/)).toBeInTheDocument()
    expect(within(coutPrevu).getByText(/Basé sur 3 h planifiées/)).toBeInTheDocument()
    expect(within(coutPrevu).getByText(/\+5\s?000 F/)).toHaveClass('finance-evolution--up')

    // Réalisé : 90 min = 1h 30min, 4 actifs.
    const realise = heroCard(/volume horaire total réalisé/i)
    expect(within(realise).getByText('1h 30min')).toBeInTheDocument()
    expect(within(realise).getByText(/4 enseignant\(s\) actif\(s\)/)).toBeInTheDocument()

    // Taux : 75 %, période précédente 80 %, évolution -5 pts (baisse).
    const taux = heroCard(/taux de réalisation global/i)
    expect(within(taux).getByText('75 %')).toBeInTheDocument()
    expect(within(taux).getByText(/Période précédente : 80 %/)).toBeInTheDocument()
    const evTaux = within(taux).getByText(/-5 pts/)
    expect(evTaux).toHaveClass('finance-evolution--down')

    // Coût réalisé : 150 000 FCFA, deux tarifs, évolution plate.
    const cout = heroCard(/coût global du volume horaire réalisé/i)
    expect(within(cout).getByText(/150\s?000 FCFA/)).toBeInTheDocument()
    expect(within(cout).getByText(/2 tarifs appliqués/)).toBeInTheDocument()
    // Évolution plate (delta 0) formatée en argent : « 0 F ».
    const evPlat = within(cout).getByText('0 F')
    expect(evPlat).toHaveClass('finance-evolution--flat')
    expect(evPlat.closest('.finance-evolution').querySelector('.bi-arrow-right-short')).toBeTruthy()
  })

  it('affiche les six petites cartes de KPI (effectifs, séances, moyenne)', async () => {
    mount()
    await settle()
    const cards = document.querySelectorAll('.finance-kpi-card')
    expect(cards).toHaveLength(6)
    const grid = document.querySelector('.finance-kpi-grid')
    expect(within(grid).getByText('6')).toBeInTheDocument() // enseignants
    expect(within(grid).getByText('4')).toBeInTheDocument() // actifs
    expect(within(grid).getByText('2')).toBeInTheDocument() // inactifs
    expect(within(grid).getByText('12')).toBeInTheDocument() // séances
    expect(within(grid).getByText('9')).toBeInTheDocument() // pointées
    expect(within(grid).getByText('4 h')).toBeInTheDocument() // moyenne 3,75 -> 4 h
    for (const label of ['Enseignants', 'Actifs', 'Inactifs', 'Séances', 'Pointées', 'Moy. h / actif']) {
      expect(within(grid).getByText(label)).toBeInTheDocument()
    }
  })

  it('affiche l’alerte de tolérance active avec ses trois compteurs', async () => {
    mount()
    await settle()
    const alerte = screen.getByText(/tolérance active/i).closest('.alert')
    expect(alerte).toHaveClass('alert-warning')
    expect(alerte).toHaveTextContent('Tolérance active : 30 min ou 5 %')
    expect(alerte).toHaveTextContent('hors tolérance')
    expect(alerte).toHaveTextContent('dans la tolérance')
    expect(alerte).toHaveTextContent('conforme(s)')
  })

  it("masque l'alerte quand la tolérance est inactive et liste les tarifs dans l'info", async () => {
    const data = JSON.parse(JSON.stringify(dashboard))
    data.kpis.tolerance.tolerance_active = false
    mount({ data })
    await settle()
    expect(screen.queryByText(/tolérance active/i)).toBeNull()
    // L'alerte d'info liste les tarifs entre parenthèses.
    const info = screen.getByText(/les montants sont calculés/i).closest('.alert')
    expect(info).toHaveTextContent(/5\s?000 F\/h/)
    expect(info).toHaveTextContent(/7\s?500,5 F\/h/)
  })

  it("affiche l'horodatage de génération puis le masque s'il est absent", async () => {
    const rendu1 = mount()
    await settle()
    expect(screen.getByText(/actualisé le/i).textContent).toMatch(/04\/03\/2026/)
    rendu1.unmount()

    const data = { ...dashboard, generated_at: null }
    const rendu2 = mount({ data })
    await settle()
    expect(screen.queryByText(/actualisé le/i)).toBeNull()
    rendu2.unmount()
  })

  it("calcule le coût prévisionnel en repli depuis les modules (null puis chaîne vide)", async () => {
    const base = JSON.parse(JSON.stringify(dashboard))
    delete base.kpis.total_montant_prevu
    const { unmount } = mount({ data: base })
    await settle()
    // 100 000 + 50 000 + 30 000 = 180 000 FCFA.
    expect(within(heroCard(/coût prévisionnel/i)).getByText(/180\s?000 FCFA/)).toBeInTheDocument()
    unmount()

    const base2 = JSON.parse(JSON.stringify(dashboard))
    base2.kpis.total_montant_prevu = ''
    const rendu2 = mount({ data: base2 })
    await settle()
    expect(within(heroCard(/coût prévisionnel/i)).getByText(/180\s?000 FCFA/)).toBeInTheDocument()
    rendu2.unmount()

    // Module sans montant_prevu : le `|| 0` du cumul est exercé (5 000 seulement).
    const base3 = {
      ...JSON.parse(JSON.stringify(dashboard)),
      kpis: {},
      volumes_par_module: [
        { module_id: 1, montant_prevu: 5000 },
        { module_id: 2 }, // absent -> 0
      ],
    }
    delete base3.kpis.total_montant_prevu
    const rendu3 = mount({ data: base3 })
    await settle()
    expect(within(heroCard(/coût prévisionnel/i)).getByText(/5\s?000 FCFA/)).toBeInTheDocument()
    rendu3.unmount()
  })

  it("affiche des compteurs à zéro quand la tolérance active omet ses décomptes", async () => {
    const data = JSON.parse(JSON.stringify(dashboard))
    data.kpis.tolerance = { tolerance_active: true }
    mount({ data })
    await settle()
    const alerte = screen.getByText(/tolérance active/i).closest('.alert')
    expect(alerte).toHaveTextContent('0 hors tolérance')
    expect(alerte).toHaveTextContent('0 dans la tolérance')
    expect(alerte).toHaveTextContent('0 conforme(s)')
  })

  it("affiche l'erreur détaillée puis le message générique de chargement", async () => {
    mount({ routeFn: () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Module finance indisponible' } } }
    } })
    expect(await screen.findByText('Module finance indisponible')).toBeInTheDocument()
  })

  it("replie sur le message générique sans détail puis supporte data:null", async () => {
    const rendu1 = mount({ routeFn: () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: {} } }
    } })
    expect(await screen.findByText('Impossible de charger le dashboard finance.')).toBeInTheDocument()
    rendu1.unmount()

    const rendu2 = mount({ data: null })
    await settle()
    // Rendu dégradé sans crash : KPI à zéro et états vides.
    expect(within(heroCard(/volume horaire total planifié/i)).getByText('0h')).toBeInTheDocument()
    expect(screen.getByText('Aucun enseignant')).toBeInTheDocument()
    rendu2.unmount()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 30 — activité, spécialités, classement                          */
/* ------------------------------------------------------------------ */

describe('pages/FinanceDashboard.jsx — activité, spécialités et classement (LOT 30)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DASH_PATH, () => dashboard)
  })

  it('trace l’activité mensuelle (barres proportionnelles, durée et montant)', async () => {
    mount()
    await settle()
    const section = sectionFor(/activité mensuelle/i)
    const rows = section.querySelectorAll('.finance-chart-row')
    expect(rows).toHaveLength(3)
    const bars = [...section.querySelectorAll('.finance-chart-bar')]
    expect(bars[0].style.width).toBe('100%')   // 600 / max 600
    expect(bars[1].style.width).toBe('50%')    // 300 / 600
    expect(bars[2].style.width).toBe('0%')
    expect(rows[0]).toHaveTextContent('Jan 2026')
    expect(rows[0]).toHaveTextContent('10h')
    expect(rows[0]).toHaveTextContent(/50\s?000 F/)
    expect(rows[1]).toHaveTextContent('5h')
  })

  it('ouvre la ventilation des enseignants d’une spécialité (puis vide, puis fermeture)', async () => {
    mount()
    await settle()
    const section = sectionFor(/spécialités/i)
    expect(section).toHaveTextContent('LSF')
    fireEvent.click(within(section).getAllByTitle('Voir les enseignants')[0])
    await waitFor(() => expect(overlay()).toBeTruthy())
    const modal = overlay()
    expect(modal).toHaveTextContent('LSF')
    expect(modal).toHaveTextContent('Traoré')
    expect(modal).toHaveTextContent('Mariam')
    // Matricule présent pour l'un, tiret pour l'autre.
    expect(modal).toHaveTextContent('F-901')
    expect(modal.textContent).toContain('Diop')
    fireEvent.click(modal.querySelector('.btn-close'))
    await settle()
    expect(overlay()).toBeNull()

    // Seconde spécialité sans enseignant : message dédié, fermeture par « Fermer ».
    const section2 = sectionFor(/spécialités/i)
    const badges = section2.querySelectorAll('.badge-bg-info')
    fireEvent.click(badges[1])
    await waitFor(() => expect(overlay()).toBeTruthy())
    expect(overlay()).toHaveTextContent('Aucun enseignant.')
    fireEvent.click(within(overlay()).getByRole('button', { name: 'Fermer' }))
    await settle()
    expect(overlay()).toBeNull()
  })

  it('ferme la modale de spécialité en cliquant le voile (pas en cliquant dedans)', async () => {
    mount()
    await settle()
    const badgesSpec = within(sectionFor(/spécialités/i)).getAllByTitle('Voir les enseignants')
    fireEvent.click(badgesSpec[0])
    await waitFor(() => expect(overlay()).toBeTruthy())
    const voile = overlay()
    // Un clic dans le contenu ne ferme pas (stopPropagation).
    fireEvent.click(voile.querySelector('.modal-header'))
    await settle()
    expect(overlay()).toBeTruthy()
    fireEvent.click(voile)
    await settle()
    expect(overlay()).toBeNull()
  })

  it('classe en temps réalisé par défaut : médailles des trois premiers, replis ensuite', async () => {
    mount()
    await settle()
    const section = sectionFor(/classement enseignants/i)
    const rows = section.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(5)
    expect(within(rows[0]).getByText('1')).toHaveClass('finance-rank-medal--1')
    expect(within(rows[1]).getByText('2')).toHaveClass('finance-rank-medal--2')
    expect(within(rows[2]).getByText('3')).toHaveClass('finance-rank-medal--3')
    // Quatrième : simple numéro grisé (scope sur la cellule du rang).
    const rang4 = rows[3].querySelector('td:first-child')
    expect(within(rang4).getByText('4')).toHaveClass('text-muted')
    expect(rang4.querySelector('.finance-rank-medal')).toBeNull()
    // Première ligne : 300 min = 5h.
    expect(rows[0]).toHaveTextContent('Awa Koné')
    expect(rows[0]).toHaveTextContent('F-11')
    expect(rows[0]).toHaveTextContent('5h')
    // Dernière ligne : tous les replis (matricule/spécialité/séances).
    const last = rows[4]
    expect(last).toHaveTextContent('Sans Replis')
    expect(last).toHaveTextContent('—')
    expect(within(last).getByText('0')).toBeInTheDocument()
    // Onglet réalisé actif.
    expect(within(section).getByRole('button', { name: /temps réalisé/i })).toHaveClass('active')
  })

  it('bascule sur les classements planifié et montants (formats et en-tête)', async () => {
    mount()
    await settle()
    const section = sectionFor(/classement enseignants/i)
    fireEvent.click(rankTab('Temps planifié'))
    await settle()
    expect(section).toHaveTextContent('Planif Un')
    expect(section).toHaveTextContent('6h 40min') // 400 min
    expect(section.querySelector('thead')).toHaveTextContent('Temps planifié')

    fireEvent.click(rankTab('Montants'))
    await settle()
    expect(section).toHaveTextContent('Riche Un')
    expect(section).toHaveTextContent(/120\s?000 FCFA/)
    expect(section.querySelector('thead')).toHaveTextContent('Montant')
  })

  it("persiste l'onglet de classement dans la query partagée (rank_tab)", async () => {
    mount()
    await settle()
    fireEvent.click(rankTab('Montants'))
    await waitFor(() =>
      expect(window.sessionStorage.getItem('finance_list_query')).toContain('rank_tab=montants'),
    )
    // Le classement réalisé par défaut n'expose pas ce paramètre.
  })

  it('honore rank_tab fourni dans l’URL initiale (et retombe sur le réalisé si inconnu)', async () => {
    mount({ initialEntries: ['/finance-dashboard?rank_tab=planifie'] })
    await settle()
    const section = sectionFor(/classement enseignants/i)
    expect(section).toHaveTextContent('Planif Un')
  })

  it("retombe sur le classement réalisé pour un rank_tab inconnu dans l'URL", async () => {
    mount({ initialEntries: ['/finance-dashboard?rank_tab=inconnu'] })
    await settle()
    const section = sectionFor(/classement enseignants/i)
    expect(section).toHaveTextContent('Awa Koné')
    expect(section.querySelector('thead')).toHaveTextContent('Temps réalisé')
  })

  it("masque l'activité et les spécialités absentes et dit qu'un classement vide n'a pas de données", async () => {
    mount({ data: dashboardVide })
    await settle()
    expect(screen.queryByText(/activité mensuelle/i)).toBeNull()
    expect(screen.queryByText(/spécialités/i)).toBeNull()
    const section = sectionFor(/classement enseignants/i)
    expect(section).toHaveTextContent('Aucune donnée sur cette période')
  })
})

/* ------------------------------------------------------------------ */
/* LOT 30 — synthèse de paie paginée et badges de tolérance            */
/* ------------------------------------------------------------------ */

describe('pages/FinanceDashboard.jsx — synthèse enseignants paginée (LOT 30)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DASH_PATH, (path) =>
      path.includes('preset=annee') ? dashboardAnnee : dashboard,
    )
  })

  it('affiche 25 lignes sur la première page avec les badges de tolérance', async () => {
    mount()
    await settle()
    const section = sectionFor(/fiche de paie globale/i)
    expect(section).toHaveTextContent('26 formateur(s)')
    expect(section).toHaveTextContent('page 1 / 2')
    expect(section.querySelectorAll('tbody tr')).toHaveLength(25)

    // En-têtes des 13 colonnes.
    for (const col of ['N°', 'Nom', 'Prénom', 'Modules dispensés', 'Grade(s)', 'Groupe(s)', 'Mod.', 'Séances', 'Taux', 'Statut', 'Planifié', 'Réalisé', 'Montant']) {
      expect(within(section).getByText(col, { selector: 'th' })).toBeInTheDocument()
    }

    // Première ligne : tolérance nulle => aucune pastille de statut.
    const row1 = section.querySelector('tbody tr')
    expect(row1).toHaveTextContent('Nom1')
    expect(row1).toHaveTextContent('1h')      // 60 min planifié
    expect(row1).toHaveTextContent('0h 30min') // 30 min réalisé
    expect(row1.querySelectorAll('.badge')).toHaveLength(0)

    // Badges de tolérance des lignes suivantes.
    expect(section).toHaveTextContent('Conforme ✓')
    expect(section).toHaveTextContent('Dans la tolérance')
    expect(section).toHaveTextContent('Hors tolérance')
    expect(section).toHaveTextContent('Écart')
    // Statut inconnu : repli « — » ; l'inactif montre quand même son statut (showInactive).
  })

  it('pagine : suivante, numéro de page, précédente, et revient à 1 après Appliquer', async () => {
    mount()
    await settle()
    const section = () => sectionFor(/fiche de paie globale/i)
    expect(section().querySelectorAll('tbody tr')).toHaveLength(25)
    expect(section()).toHaveTextContent('Nom1')

    fireEvent.click(within(section()).getByRole('button', { name: 'Page suivante' }))
    await settle()
    expect(section().querySelectorAll('tbody tr')).toHaveLength(1)
    expect(section()).toHaveTextContent('Nom26')
    expect(section()).not.toHaveTextContent('Nom1')
    expect(section()).toHaveTextContent('page 2 / 2')

    fireEvent.click(within(section()).getByRole('button', { name: 'Page 1' }))
    await settle()
    expect(section().querySelectorAll('tbody tr')).toHaveLength(25)

    // Après un changement de période appliqué, la pagination se réinitialise.
    fireEvent.click(within(section()).getByRole('button', { name: 'Page suivante' }))
    await settle()
    expect(section()).toHaveTextContent('page 2 / 2')
    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Cette année' }))
    fireEvent.click(applyButton())
    await waitFor(() => expect(lastParams().get('preset')).toBe('annee'))
    await settle()
    expect(section()).toHaveTextContent('0 formateur(s)')
    expect(section()).toHaveTextContent('Aucun enseignant')
  })

  it('encaisse une ligne de synthèse lacunaire (tirets, zéros, pastilles absentes)', async () => {
    const data = {
      ...dashboardVide,
      synthese_formateurs: [{ id: 1, nom: 'Lacunaire', prenom: 'Test' }],
    }
    mount({ data })
    await settle()
    const section = sectionFor(/fiche de paie globale/i)
    const row = section.querySelector('tbody tr')
    expect(row).toHaveTextContent('Lacunaire')
    expect(row).toHaveTextContent('-')     // N° sans matricule
    // Modules/grades/groupes absents -> trois tirets.
    expect(row).toHaveTextContent('—')
    expect(row).toHaveTextContent('0%')    // ni statistiques, ni taux
    expect(row).toHaveTextContent('0h')    // durées absentes
    expect(row).toHaveTextContent(/0\s?F/) // montant absent -> 0 F
    expect(row.querySelectorAll('.badge')).toHaveLength(0) // tolérance absente
  })

  it('affiche le message vide quand aucun enseignant n’est synthétisé', async () => {
    mount({ data: dashboardVide })
    await settle()
    const section = sectionFor(/fiche de paie globale/i)
    expect(section).toHaveTextContent('0 formateur(s)')
    expect(section).toHaveTextContent('Aucun enseignant')
  })
})

/* ------------------------------------------------------------------ */
/* LOT 30 — modale de ventilation par module                           */
/* ------------------------------------------------------------------ */

describe('pages/FinanceDashboard.jsx — ventilation par module (LOT 30)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DASH_PATH, () => dashboard)
  })

  const titres = {
    planifie: { card: /volume horaire total planifié/i, titre: /volume horaire planifié par module/i, total: '8h' },
    realise: { card: /volume horaire total réalisé/i, titre: /volume horaire réalisé par module/i, total: '6h' },
    taux: { card: /taux de réalisation global/i, titre: /taux de réalisation par module/i, total: '75 %' },
    cout: { card: /coût global du volume horaire réalisé/i, titre: /coût du volume horaire réalisé par module/i, total: /150\s?000 FCFA/ },
    cout_prevu: { card: /coût prévisionnel/i, titre: /coût prévisionnel du volume horaire par module/i, total: /180\s?000 FCFA/ },
  }

  it('ouvre les cinq ventilations avec titres, tri, totaux et colonne tarif pour l’argent', async () => {
    mount()
    await settle()

    for (const spec of Object.values(titres)) {
      await openDrill(spec.card)
      const modal = overlay()
      expect(within(modal).getByText(spec.titre)).toBeInTheDocument()
      expect(modal).toHaveTextContent('3 modules sur la période')
      // Total de pied : durée, pourcentage ou argent.
      expect(modal).toHaveTextContent(spec.total)
      fireEvent.click(modal.querySelector('.modal-footer .btn'))
      await settle()
      expect(overlay()).toBeNull()
    }

    // Détail complémentaire sur la ventilation « coût réalisé ».
    await openDrill(titres.cout.card)
    let modal = overlay()
    expect(modal.querySelector('thead')).toHaveTextContent('Tarif / h')
    expect(modal).toHaveTextContent('5 000 F')
    // Module 2 sans tarif -> tiret.
    expect(modal).toHaveTextContent('INJS Marcory')
    // Module 3 sans libellés : quatre tirets et séances à 0.
    fireEvent.click(modal.querySelector('.btn-close'))
    await settle()

    // Ventilation des taux : tri du plus fort au plus faible (100, 80, 50).
    await openDrill(titres.taux.card)
    modal = overlay()
    const valeurs = [...modal.querySelectorAll('tbody tr td:last-child')].map((td) => td.textContent)
    expect(valeurs).toEqual(['100 %', '80 %', '50 %'])
    fireEvent.click(modal) // clic sur le voile lui-même
    await settle()
    expect(overlay()).toBeNull()
  })

  it('filtre les modules par recherche avec total filtré et total global', async () => {
    mount()
    await settle()
    await openDrill(titres.planifie.card)
    const modal = overlay()
    const search = within(modal).getByPlaceholderText(/filtrer par module/i)

    fireEvent.change(search, { target: { value: 'Interprétation' } })
    await settle()
    expect(modal).toHaveTextContent('1 affiché')
    const rows = modal.querySelectorAll('tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]).toHaveTextContent('Interprétation')
    // Pied : total du filtre (120 min = 2h) et rappel global (8h).
    expect(modal).toHaveTextContent('TOTAL (filtre)')
    expect(modal).toHaveTextContent('2h')
    expect(modal).toHaveTextContent(/Global : 8h/)

    fireEvent.change(search, { target: { value: 'mot-sans-correspondance' } })
    await settle()
    expect(modal).toHaveTextContent('Aucun module ne correspond au filtre')
  })

  it('gère une période sans module (message, pas de recherche) et le singulier « 1 module »', async () => {
    const rendu1 = mount({ data: dashboardVide })
    await settle()
    await openDrill(/volume horaire total planifié/i)
    let modal = overlay()
    expect(modal).toHaveTextContent('Aucun module sur cette période')
    expect(within(modal).queryByPlaceholderText(/filtrer par module/i)).toBeNull()
    fireEvent.click(modal.querySelector('.btn-close'))
    await settle()
    expect(overlay()).toBeNull()
    rendu1.unmount()

    const dataUnModule = { ...dashboardVide, volumes_par_module: [volumes[0]] }
    const rendu2 = mount({ data: dataUnModule })
    await settle()
    await openDrill(/volume horaire total planifié/i)
    modal = overlay()
    expect(modal).toHaveTextContent('1 module sur la période')
    expect(modal).not.toHaveTextContent('modules sur la période')
    rendu2.unmount()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 30 — période partagée                                           */
/* ------------------------------------------------------------------ */

describe('pages/FinanceDashboard.jsx — période partagée (LOT 30)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute(DASH_PATH, (path) =>
      path.includes('preset=annee') ? dashboardAnnee : dashboard,
    )
  })

  it("ne recharge qu'après Appliquer et persiste la période « année »", async () => {
    mount()
    await settle()
    const appelsAvant = dataCalls().length
    expect(lastParams().get('preset')).toBe('mois')

    fireEvent.click(within(filterPanel()).getByRole('button', { name: 'Cette année' }))
    await settle()
    expect(dataCalls()).toHaveLength(appelsAvant) // pas de rechargement immédiat

    fireEvent.click(applyButton())
    await waitFor(() => expect(lastParams().get('preset')).toBe('annee'))
    expect(lastParams().get('annee')).toBe(anneeCourante())
    // Données de la variante année : 99 séances.
    expect(within(heroCard(/volume horaire total planifié/i)).getByText(/99 séance\(s\)/)).toBeInTheDocument()
    expect(within(heroCard(/volume horaire total planifié/i)).getByText('100h')).toBeInTheDocument() // 6000 min
    expect(window.sessionStorage.getItem('finance_period')).toContain('"annee"')
  })

  it("supporte une période dégradée sans preset : requête sur le chemin de base, sans query", async () => {
    window.sessionStorage.setItem('finance_period', JSON.stringify({ preset: '' }))
    mount()
    await settle()
    expect(apiMock.get).toHaveBeenCalledWith(DASH_PATH)
  })

  it("retombe sur le sous-texte de taux par défaut sans période de comparaison", async () => {
    mount({ data: dashboardAnnee })
    await settle()
    expect(within(heroCard(/taux de réalisation global/i)).getByText('88 %')).toBeInTheDocument()
    expect(within(heroCard(/taux de réalisation global/i)).getByText(/hors séances sans horaire planifié/i)).toBeInTheDocument()
  })
})
