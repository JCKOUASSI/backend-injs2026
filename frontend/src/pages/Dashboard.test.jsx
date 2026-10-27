import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within, fireEvent, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import { dashboardStats, dashboardStatsWithPeriods } from '@/test/fixtures/dashboard'
import { useAuth } from '@/context/AuthContext'
import Dashboard from '@/pages/Dashboard'

function WaitForAuth({ children }) {
  const { isAuthenticated, loading } = useAuth()
  if (loading || !isAuthenticated) return <div className="loading"><div className="spinner" /></div>
  return children
}

const BASE = 'http://testserver'
const paramsOf = (url) => new URL(url, BASE).searchParams
const callsTo = (pathOnly) =>
  apiMock.get.mock.calls
    .filter(([p]) => p.split('?')[0] === pathOnly)
    .map(([p]) => paramsOf(p))

const mountDashboard = (me, entry = '/') => {
  apiController.setMe(me)
  return renderWithProviders(
    <WaitForAuth><Dashboard /></WaitForAuth>,
    { authUser: me, initialEntries: [entry], routePattern: '/' },
  )
}

// ADMIN : peut filtrer par secrétariat → le groupe de boutons période est
// celui de la barre latérale (« Jour spécifique / Semaine / Mois / Année »).
const adminMe = () => makeUser('ADMIN', { username: 'admin' })

const periodGroup = () => screen.getByRole('group', { name: /filtre de période dashboard/i })
const clickPeriod = (label) =>
  fireEvent.click(within(periodGroup()).getByRole('button', { name: label }))

describe('pages/Dashboard.jsx — chargement et période de présence', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('appelle les statistiques et les formations en cours au chargement', async () => {
    mountDashboard(adminMe())

    // On attend le rendu post-réception (les deux ressources sont alors
    // résolues) avant d'inspecter les paramètres des appels.
    await screen.findByText('Aucun module en cours')
    expect(callsTo('/formations/stats/').length).toBeGreaterThan(0)
    const list = callsTo('/formations/list/').at(-1)
    expect(list.get('statut')).toBe('EN_COURS')
    expect(list.get('page_size')).toBe('10')
    // Date = aujourd'hui : on reste sur « séance en cours ».
    expect(list.get('seance_en_cours')).toBe('true')
    expect(list.has('date_mode')).toBe(false)
  })

  it('avec un jour spécifique dans le passé, la liste utilise le mode date', async () => {
    mountDashboard(adminMe(), '/?reference_date=2026-01-15&presence_period=jour')
    await waitFor(() => expect(callsTo('/formations/list/').length).toBeGreaterThan(0))
    const list = callsTo('/formations/list/').at(-1)
    expect(list.get('date_mode')).toBe('date')
    expect(list.get('date')).toBe('2026-01-15')
    expect(list.has('seance_en_cours')).toBe(false)
  })

  it('bascule les indicateurs affichés selon la période (Jour → Année)', async () => {
    mountDashboard(adminMe())
    // On attend le RENDU (et non seulement l'émission de l'appel API, qui peut
    // précéder la réception des données) pour éviter toute course de timing.
    expect(await screen.findByText(/présences du /i)).toBeInTheDocument()

    clickPeriod('Année')
    expect(await screen.findByText(/présences de l.année/i)).toBeInTheDocument()
  })

  // Régression pour le bug de closure périmée (docs §10.5), corrigé au LOT 4 :
  // loadDashboardData listait presencePeriod dans l'effet déclencheur mais pas
  // dans ses propres dépendances de useCallback. Les bascules de période
  // rappelaient une closure figée sur l'ancienne valeur.
  it('Jour(date passée) → Semaine : la liste revient aux séances en cours', async () => {
    mountDashboard(adminMe(), '/?reference_date=2026-01-15&presence_period=jour')
    await waitFor(() => expect(callsTo('/formations/list/').length).toBeGreaterThan(0))
    expect(callsTo('/formations/list/').at(-1).get('date_mode')).toBe('date')

    const nBefore = callsTo('/formations/list/').length
    clickPeriod('Semaine')
    await waitFor(() => expect(callsTo('/formations/list/').length).toBeGreaterThan(nBefore))

    const q = callsTo('/formations/list/').at(-1)
    expect(q.has('date_mode')).toBe(false)
    expect(q.has('date')).toBe(false)
    expect(q.get('seance_en_cours')).toBe('true')
  })

  it('Semaine(date passée) → Jour : la liste passe en mode date épinglé', async () => {
    mountDashboard(adminMe(), '/?reference_date=2026-01-15&presence_period=semaine')
    await waitFor(() => expect(callsTo('/formations/list/').length).toBeGreaterThan(0))
    // En « Semaine », même avec une date passée, on reste sur le temps réel.
    expect(callsTo('/formations/list/').at(-1).get('seance_en_cours')).toBe('true')

    const nBefore = callsTo('/formations/list/').length
    clickPeriod('Jour spécifique')
    await waitFor(() => expect(callsTo('/formations/list/').length).toBeGreaterThan(nBefore))

    const q = callsTo('/formations/list/').at(-1)
    expect(q.get('date_mode')).toBe('date')
    expect(q.get('date')).toBe('2026-01-15')
    expect(q.has('seance_en_cours')).toBe(false)
  })
})

describe('pages/Dashboard.jsx — gestion des erreurs de chargement (§10.6)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  const boom = () => {
    throw Object.assign(new Error('réseau'), { response: { data: { detail: 'indisponible' } } })
  }

  it('échec des DEUX requêtes → message d’erreur totale', async () => {
    apiController.setRoute('/formations/stats/', boom)
    apiController.setRoute('/formations/list/', boom)

    mountDashboard(adminMe())
    expect(await screen.findByText('Erreur lors du chargement des données')).toBeInTheDocument()
    expect(screen.queryByText(/certaines données/i)).not.toBeInTheDocument()
  })

  it('une seule requête échoue → message d’erreur partielle', async () => {
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', boom)

    mountDashboard(adminMe())
    expect(await screen.findByText(/certaines données/i)).toBeInTheDocument()
    expect(screen.queryByText('Erreur lors du chargement des données')).not.toBeInTheDocument()
  })
})

// ─────────────────────────────────────────────────────────────────────────
// LOT 42 : couverture fonctionnelle complète du rendu (KPI, tableaux,
// secrétariats, période VH, rôles). Aucune modification de la page.
// ─────────────────────────────────────────────────────────────────────────

const statCard = (label) => screen.getByText(label).closest('.stat-card')
const statValue = (label) => statCard(label).querySelector('.stat-value')?.textContent

const modulesCard = () => screen.getByText('Modules débutés').closest('.card')
const comingCard = () => screen.getByText('Prochaines séances').closest('.card')
const pointagesCard = () => screen.getByText('Derniers pointages').closest('.card')

const richStats = () => dashboardStats({
  periode: { label: 'Septembre 2026', periode_label: 'Mois en cours' },
  total_modules: 341,
  modules_en_cours: 21,
  modules_planifies: 88,
  modules_termines: 232,
  volume_horaire_effectue_heures: 480,
  volume_horaire_total_heures: 600,
  volume_horaire_effectue_taux: 80,
  total_participants: 1207,
  auditeurs_presents_jour: 70,
  auditeurs_attendus_jour: 90,
  formateurs_presents_jour: 5,
  formateurs_attendus_jour: 8,
  seances_planifiees_aujourd_hui: 6,
  seances_actives: 3,
  pointages_aujourd_hui: 42,
  en_salle_now: 33,
  retard_moyen_minutes: 4.5,
  total_attendus_jour: 100,
  presents_aujourd_hui: 80,
  taux_presence: 80,
  // Absence 40 % (jaune) en semaine, 80 % (rouge) au mois, 100 % l'année.
  total_attendus_semaine: 100,
  presents_semaine: 60,
  taux_presence_semaine: 60,
  total_attendus_mois: 100,
  presents_mois: 20,
  taux_presence_mois: 20,
  // Taux servi à 0 (falsy) avec des attendus > 0 : exerce le repli `taux || 0`.
  total_attendus_annee: 50,
  presents_annee: 0,
  taux_presence_annee: 0,
  prochaines_seances: [
    {
      session_id: 11, module: 'LSF Niveau 2', formation_id: 3, module_id: 30,
      date_journee: '2026-09-20', heure_debut_prevue: '08:30:00',
    },
    {
      session_id: 12, formation: 'Licence 1 LSF', formation_id: 4, module_id: null,
      date_journee: '2026-09-21',
    },
  ],
  derniers_pointages: [
    {
      nom: 'Awa Koné', matricule: 'MAT-001', type: 'formateur', module: 'LSF A1',
      date: '2026-09-12', heure_entree: '2026-09-12T07:55:00', heure_sortie: '2026-09-12T12:05:00',
    },
    {
      nom: 'Yao Brou', matricule: 'ENC-002', type: 'encadrant', module: 'Morphologie',
      date: '2026-09-12', heure_entree: '2026-09-12T08:10:00',
    },
    { type: 'etudiant', date: '2026-09-12', heure_entree: '2026-09-12T09:00:00' },
  ],
})

const MODULES_EN_COURS = [
  {
    id: 1, module_id: 101, module: 'LSF A1', formation: 'Licence 1 LSF',
    site: 'Marcory', batiment: 'Bât A', salle: 'Salle 12', categorie: 'CM',
    superviseur_nom: 'Yao Brou', nb_participants: 10, nb_presents: 8,
    date_debut: '2026-09-01', date_fin: '2026-12-15',
  },
  {
    // Taux 50 % (warning), absence 50 % (rouge) ; replis intitulé / grade / site / encadrant.
    id: 2, module_id: 102, intitule: 'Grammaire', grade: 'L2',
    nb_participants: 4, nb_presents: 2, date_debut: '2026-09-02',
  },
  {
    // Taux 25 % (rouge), absence 75 % (rouge) ; tous les libellés en repli « — ».
    id: 3, module_id: 103, nb_participants: 4, nb_presents: 1,
  },
  {
    // Aucun effectif renseigné : tous les replis numériques (0), taux 0 %,
    // absence sans pourcentage, et libellés entièrement en repli.
    id: 4, module_id: 104,
  },
  {
    // Taux de présence 60 % (warning) et 40 % d'absence (jaune : 25-49 %).
    id: 5, module_id: 105, module: 'LSF B2', nb_participants: 5, nb_presents: 3,
  },
]

// Même formatage que fmtTime dans Dashboard.jsx.
const expectedFmtTime = (ts) => (ts
  ? new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })
  : '—')

describe('pages/Dashboard.jsx — indicateurs et tableaux avec données riches', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => richStats())
    apiController.setRoute('/formations/list/', () => ({ results: MODULES_EN_COURS, count: 3 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('rend les KPI d’en-tête avec les valeurs servies', async () => {
    mountDashboard(adminMe())

    await screen.findByText('341')
    expect(screen.getByText('1207')).toBeInTheDocument()
    expect(screen.getByText('480h / 600h')).toBeInTheDocument()
    expect(screen.getByText(/80% effectué/)).toBeInTheDocument()
    expect(screen.getByText(/21 démarrés/)).toBeInTheDocument()
    expect(screen.getByText(/88 planifiés/)).toBeInTheDocument()
    expect(screen.getByText(/232 terminés/)).toBeInTheDocument()
  })

  it('rend les cartes capacité du jour et exécution live', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')

    expect(statValue('Nombre Étudiants Présents/Attendus')).toBe('70/90')
    expect(statValue('Nombre Enseignants Présents/Attendus')).toBe('5/8')
    expect(statValue('Séances planifiées')).toBe('6')
    expect(statValue('Séances actives')).toBe('3')
    expect(statValue('Pointages du jour')).toBe('42')
    expect(statValue('En salle maintenant')).toBe('33')
    expect(statValue('Retard moyen (jour)')).toBe('4.5 min')
  })

  it('rend la table des modules débutés avec tous les replis et couleurs', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')
    const cardEl = modulesCard()
    expect(within(cardEl).getByText('LSF A1')).toBeInTheDocument()
    // Ligne complète.
    expect(within(cardEl).getByText('Licence 1 LSF')).toBeInTheDocument()
    expect(within(cardEl).getByText('Marcory / Bât A / Salle 12')).toBeInTheDocument()
    expect(within(cardEl).getByText('CM')).toBeInTheDocument()
    expect(within(cardEl).getByText('Yao Brou')).toBeInTheDocument()
    expect(within(cardEl).getByText('01/09/2026 — 15/12/2026')).toBeInTheDocument()
    // Ligne à replis (intitulé, grade, site et encadrant non assigné, dates '-').
    expect(within(cardEl).getByText('Grammaire')).toBeInTheDocument()
    expect(within(cardEl).getByText('L2')).toBeInTheDocument()
    expect(within(cardEl).getAllByText('—').length).toBeGreaterThan(0)
    // Modules 2, 3, 4 et 5 sans superviseur_nom → « Non assigné ».
    expect(within(cardEl).getAllByText('Non assigné')).toHaveLength(4)
    // Pourcentages d'absence (n'apparaissent que si attendus > 0) : le module
    // sans effectif n'affiche PAS de pourcentage.
    expect(within(cardEl).getByText('(20%)')).toBeInTheDocument()
    expect(within(cardEl).getByText('(40%)')).toBeInTheDocument()
    expect(within(cardEl).getByText('(50%)')).toBeInTheDocument()
    expect(within(cardEl).getByText('(75%)')).toBeInTheDocument()
    expect(within(cardEl).queryByText('(0%)')).not.toBeInTheDocument()
    // Cinq lignes → cinq liens œil vers le détail de module.
    const eyes = within(cardEl).getAllByTitle('Voir détail')
    expect(eyes).toHaveLength(5)
    expect(eyes[0]).toHaveAttribute('href', '/formations/1/modules/101')
    expect(eyes[2]).toHaveAttribute('href', '/formations/3/modules/103')
    expect(eyes[3]).toHaveAttribute('href', '/formations/4/modules/104')
    // Le module sans effectif affiche 0 / 0, 0 absent et un taux de 0 %.
    const rows = within(cardEl).getAllByRole('row')
    const noEffectifRow = rows[4] // [0] = en-tête, puis les 5 modules
    expect(noEffectifRow).toHaveTextContent('0 / 0')
    expect(noEffectifRow).toHaveTextContent('0%')
  })

  it('rend les prochaines séances (avec et sans heure) et leurs liens', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')
    const card = comingCard()

    expect(within(card).getByText('Licence 1 LSF')).toBeInTheDocument()
    expect(within(card).getByText(/20\/09\/2026.*08:30/)).toBeInTheDocument()
    // La seconde séance n'a pas d'heure prévue : pas de puise « • HH:MM ».
    expect(within(card).getByText('21/09/2026')).toBeInTheDocument()
    const links = within(card).getAllByRole('link')
    expect(links[0]).toHaveAttribute('href', '/formations/3/modules/30')
    expect(links[1]).toHaveAttribute('href', '/formations/4/modules/null')
  })

  it('rend les derniers pointages avec les trois types de badge et les heures formatées', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')
    const card = pointagesCard()

    expect(within(card).getByText('MAT-001')).toBeInTheDocument()
    expect(within(card).getByText('ENC-002')).toBeInTheDocument()
    expect(within(card).getByText('Enseignant')).toBeInTheDocument()
    expect(within(card).getByText('Encadrant')).toBeInTheDocument()
    expect(within(card).getByText('Étudiant')).toBeInTheDocument()
    expect(within(card).getByText('Morphologie')).toBeInTheDocument()
    // Dates des trois lignes.
    expect(within(card).getAllByText('12/09/2026')).toHaveLength(3)
    // Heures d'entrée/sortie via fmtTime.
    expect(within(card).getByText(expectedFmtTime('2026-09-12T07:55:00'))).toBeInTheDocument()
    expect(within(card).getByText(expectedFmtTime('2026-09-12T12:05:00'))).toBeInTheDocument()
    // Deux sorties absentes (lignes 2 et 3) + nom/matricule/module de la ligne
    // étudiante sans identité : 5 cellules de repli « — ».
    expect(within(card).getAllByText('—')).toHaveLength(5)
  })

  it('rend le badge de la période volume horaire servie par les stats', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')
    expect(screen.getByText('Septembre 2026')).toBeInTheDocument()
    expect(screen.getByText(/Mois en cours/)).toBeInTheDocument()
  })

  it('calcule présents/absents/taux du bloc présence pour la période courante', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')
    // Fixture jour : 100 attendus, 80 présents, taux 80 % → 20 absents, 20.0 % d'absence.
    expect(screen.getByText('80.0% présents')).toBeInTheDocument()
    expect(screen.getByText('20.0% absents')).toBeInTheDocument()
    expect(screen.queryByText(/aucune personne attendue/i)).not.toBeInTheDocument()
  })

  it('applique les seuils d’absence (jaune puis rouge) et le repli de taux sur les autres périodes', async () => {
    mountDashboard(adminMe())
    await screen.findByText('341')

    clickPeriod('Semaine')
    expect(await screen.findByText(/présences de la semaine/i)).toBeInTheDocument()
    // 60/100, taux 60 → 40 absents, 40.0 % (jaune) ; mêmes chiffres dans les
    // deux cartes (capacité non-jour et bloc présences).
    expect(statValue('Absents (semaine)')).toBe('40 (40.0%)')
    expect(screen.getByText('40.0% absents')).toBeInTheDocument()

    clickPeriod('Mois')
    expect(await screen.findByText(/présences du mois/i)).toBeInTheDocument()
    // 20/100, taux 20 → 80 absents, 80.0 % (rouge).
    expect(statValue('Absents (mois)')).toBe('80 (80.0%)')
    expect(screen.getByText('80.0% absents')).toBeInTheDocument()

    clickPeriod('Année')
    expect(await screen.findByText(/présences de l.année/i)).toBeInTheDocument()
    // 0/50 avec un taux servi à 0 (falsy) : le repli `taux || 0` s'applique et
    // le taux d'absence affiché est bien 100 %.
    expect(statValue('Absents (année)')).toBe('50 (100.0%)')
    expect(screen.getByText('100.0% absents')).toBeInTheDocument()
    await act(async () => {})
  })
})

describe('pages/Dashboard.jsx — carte Secrétariats (rôles administrateurs)', () => {
  const SECRETARIATS = [
    { id: 1, nom: 'INJS Marcory' },
    { id: 2, nom: 'INJS Yopougon' },
  ]

  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
  })

  it('filtre les deux ressources sur le secrétariat sélectionné puis réélargit à tous', async () => {
    apiController.setRoute('/formations/secretariats/', () => SECRETARIATS)
    mountDashboard(adminMe())

    const marcory = await screen.findByRole('button', { name: 'INJS Marcory' })
    expect(screen.getByText(/Vue: Tous les secrétariats/)).toBeInTheDocument()

    fireEvent.click(marcory)
    await waitFor(() => {
      expect(callsTo('/formations/stats/').at(-1).get('secretariat')).toBe('1')
      expect(callsTo('/formations/list/').at(-1).get('secretariat')).toBe('1')
    })
    expect(await screen.findByText(/Vue: INJS Marcory/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /tous les secrétariats/i }))
    await waitFor(() => {
      expect(callsTo('/formations/stats/').at(-1).has('secretariat')).toBe(false)
      expect(callsTo('/formations/list/').at(-1).has('secretariat')).toBe(false)
    })
    expect(screen.getByText(/Vue: Tous les secrétariats/)).toBeInTheDocument()
  })

  it('affiche l’état de chargement des secrétariats puis la liste', async () => {
    let resolveSec = null
    // Les secrétariats restent en attente tant que le test ne les débloque pas ;
    // les stats et la liste sont déjà servis par le beforeEach, donc l'écran
    // principal s'affiche tandis que la carte est en état « Chargement... ».
    apiController.setRoute('/formations/secretariats/', () => new Promise((resolve) => {
      resolveSec = resolve
    }))

    mountDashboard(adminMe())
    expect(await screen.findByText('Chargement...')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'INJS Marcory' })).not.toBeInTheDocument()

    await act(async () => { resolveSec(SECRETARIATS) })
    expect(await screen.findByRole('button', { name: 'INJS Marcory' })).toBeInTheDocument()
    expect(screen.queryByText('Chargement...')).not.toBeInTheDocument()
  })
})

describe('pages/Dashboard.jsx — jour de référence', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('une date passée épingle la liste en mode date et transmet reference_date aux stats', async () => {
    mountDashboard(adminMe())
    const dateInput = await screen.findByLabelText('Jour spécifique')

    fireEvent.change(dateInput, { target: { value: '2026-01-15' } })

    await waitFor(() => expect(callsTo('/formations/list/').at(-1).get('date')).toBe('2026-01-15'))
    const list = callsTo('/formations/list/').at(-1)
    expect(list.get('date_mode')).toBe('date')
    expect(list.has('seance_en_cours')).toBe(false)
    expect(callsTo('/formations/stats/').at(-1).get('reference_date')).toBe('2026-01-15')
    // Le sous-titre de bienvenue reflète la date de référence.
    expect(screen.getByText(/Référence: 15\/01\/2026/)).toBeInTheDocument()
  })
})

describe('pages/Dashboard.jsx — période volume horaire', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('applique « Cette année » puis le bouton Appliquer et propage preset=annee aux stats', async () => {
    mountDashboard(adminMe())
    const anneeBtn = await screen.findByRole('button', { name: 'Cette année' })

    fireEvent.click(anneeBtn)
    await waitFor(() => expect(callsTo('/formations/stats/').at(-1).get('preset')).toBe('annee'))
    const year = String(new Date().getFullYear())
    expect(callsTo('/formations/stats/').at(-1).get('annee')).toBe(year)

    // Le bouton Appliquer explicite reste fonctionnel (ré-applique la même période).
    const callsBefore = callsTo('/formations/stats/').length
    fireEvent.click(screen.getByRole('button', { name: /Appliquer/ }))
    await waitFor(() => expect(callsTo('/formations/stats/').length).toBeGreaterThan(callsBefore))
  })

  it('avertit d’une période entièrement future puis le raccourci « Voir ce mois » rétablit le mois courant', async () => {
    window.sessionStorage.setItem('finance_period', JSON.stringify({
      preset: 'custom', dateDebut: '2031-01-01', dateFin: '2031-02-01',
    }))

    mountDashboard(adminMe())
    expect(await screen.findByText(/n'a pas encore commencé/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Voir ce mois' }))
    await waitFor(() => expect(screen.queryByText(/n'a pas encore commencé/i)).not.toBeInTheDocument())
    const now = new Date()
    const mois = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
    expect(callsTo('/formations/stats/').at(-1).get('preset')).toBe('mois')
    expect(callsTo('/formations/stats/').at(-1).get('mois')).toBe(mois)
  })
})

describe('pages/Dashboard.jsx — habilitations et variantes de rôles', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [
      { id: 1, nom: 'INJS Marcory' },
    ])
  })

  const secretariatCalls = () =>
    apiMock.get.mock.calls.filter(([p]) => p.split('?')[0] === '/formations/secretariats/')

  it('pour la DIRECTION : carte Secrétariats présente mais carte « Pointages du jour » masquée', async () => {
    mountDashboard(makeUser('DIRECTION', { username: 'direction' }))
    expect(await screen.findByRole('group', { name: /filtre de période dashboard/i })).toBeInTheDocument()

    expect(screen.getByRole('button', { name: /tous les secrétariats/i })).toBeInTheDocument()
    expect(screen.getByRole('group', { name: /filtre de période dashboard/i })).toBeInTheDocument()
    expect(screen.queryByText('Pointages du jour')).not.toBeInTheDocument()
    // Les deux autres cartes d'exécution live restent visibles.
    expect(statValue('Séances actives')).toBe('0')
    expect(statValue('En salle maintenant')).toBe('0')
    // Le sélecteur de période redondant dans la carte présence est absent.
    expect(screen.queryByRole('group', { name: /^Période présence$/i })).not.toBeInTheDocument()
  })

  it('pour un ENCADRANT : pas de carte Secrétariats ni de requête, titre « Mes modules », sélecteur de période inline', async () => {
    mountDashboard(makeUser('ENCADRANT', { username: 'encadrant' }))
    expect(await screen.findByText('Mes modules débutés')).toBeInTheDocument()

    expect(secretariatCalls()).toHaveLength(0)
    expect(screen.queryByRole('button', { name: /tous les secrétariats/i })).not.toBeInTheDocument()
    expect(screen.getByText('Mes modules débutés')).toBeInTheDocument()
    const inlineGroup = screen.getByRole('group', { name: /^Période présence$/i })
    expect(inlineGroup).toBeInTheDocument()

    // Le sélecteur inline pilote la période : Semaine → totaux semaine (450/500).
    fireEvent.click(within(inlineGroup).getByRole('button', { name: 'Semaine' }))
    expect(await screen.findByText(/présences de la semaine/i)).toBeInTheDocument()
    expect(statValue(`Présents / Attendus (semaine)`)).toBe('450/500')
  })

  it('pour un compte SECRETARIAT : mention du secrétariat rattaché dans le sous-titre', async () => {
    mountDashboard(makeUser('SECRETARIAT', {
      username: 'secmarcory', secretariat: 1, secretariat_nom: 'INJS Marcory',
    }))
    expect(await screen.findByText(/Secrétariat : INJS Marcory/)).toBeInTheDocument()
    // Pas de carte de filtrage multi-secrétariats pour un rôle borné.
    expect(screen.queryByRole('button', { name: /tous les secrétariats/i })).not.toBeInTheDocument()
  })
})

describe('pages/Dashboard.jsx — libellé du bloc présences selon le jour de référence', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('avec une date valide dans l’URL, le titre mentionne cette date', async () => {
    mountDashboard(adminMe(), '/?reference_date=2026-01-15&presence_period=jour')
    expect(await screen.findByText(/présences du 15\/01\/2026/i)).toBeInTheDocument()
  })

  it('avec une date invalide, normalise vers aujourd’hui : titre daté du jour, sous-titre cohérent (§10.17)', async () => {
    mountDashboard(adminMe(), '/?reference_date=date-invalide&presence_period=jour')
    // La date invalide est remplacée par aujourd'hui : le titre est daté du
    // jour courant (et non plus « du jour » avec un sous-titre « Invalid Date »).
    const todayLabel = new Date().toLocaleDateString('fr-FR')
    expect(
      await screen.findByText(new RegExp(`présences du ${todayLabel.replace(/\//g, '\\/')}`, 'i')),
    ).toBeInTheDocument()
    expect(screen.queryByText(/date-invalide/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument()
    // La date invalide n'est transmise à aucune ressource.
    expect(apiMock.get.mock.calls.some(([p]) => String(p).includes('date-invalide'))).toBe(false)
    // La liste reste en temps réel (la référence normalisée vaut aujourd'hui).
    expect(callsTo('/formations/list/').at(-1).get('seance_en_cours')).toBe('true')
  })
})

describe('pages/Dashboard.jsx — états vides et valeurs à zéro', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStats())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('affiche les trois messages de tableaux vides et le message d’effectif nul', async () => {
    mountDashboard(adminMe())
    expect(await screen.findByText('Aucun module en cours')).toBeInTheDocument()
    expect(screen.getByText('Aucune séance à venir')).toBeInTheDocument()
    expect(screen.getByText('Aucun pointage récent')).toBeInTheDocument()
    expect(screen.getByText(/aucune personne attendue sur cette période/i)).toBeInTheDocument()
    // Les KPI du jour sont rendus avec des zéros explicites.
    expect(statValue('Nombre Étudiants Présents/Attendus')).toBe('0/0')
    expect(statValue('Nombre Enseignants Présents/Attendus')).toBe('0/0')
    expect(statValue('En salle maintenant')).toBe('0')
  })

  it('en période autre que le jour et sans données, les cartes capacité montrent des zéros formatés', async () => {
    mountDashboard(adminMe())
    await screen.findByText('Aucun module en cours')

    const nCalls = callsTo('/formations/stats/').length
    fireEvent.click(within(periodGroup()).getByRole('button', { name: 'Semaine' }))
    await waitFor(() => expect(callsTo('/formations/stats/').length).toBe(nCalls + 1))

    expect(statValue('Présents / Attendus (semaine)')).toBe('0/0')
    expect(statValue('Taux de présence (semaine)')).toBe('0.0%')
    expect(statValue('Absents (semaine)')).toBe('0 (0.0%)')
    // Le bloc présence reste sur son message d'effectif nul.
    expect(screen.getByText(/aucune personne attendue sur cette période/i)).toBeInTheDocument()
    // Laisse le refetch déclenché par la bascule se résoudre avant la fin.
    await act(async () => {})
  })
})

describe('pages/Dashboard.jsx — formes de réponse liste défensives', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStats())
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('accepte une réponse de liste sous forme de tableau brut', async () => {
    apiController.setRoute('/formations/list/', () => [])
    mountDashboard(adminMe())
    expect(await screen.findByText('Aucun module en cours')).toBeInTheDocument()
  })

  it('accepte une réponse de liste sans propriété results (retombe sur le fallback)', async () => {
    apiController.setRoute('/formations/list/', () => ({ count: 0 }))
    mountDashboard(adminMe())
    expect(await screen.findByText('Aucun module en cours')).toBeInTheDocument()
  })
})

describe('pages/Dashboard.jsx — replis de configuration', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    apiController.setRoute('/formations/stats/', () => dashboardStatsWithPeriods())
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('salue avec le username quand first_name est absent', async () => {
    mountDashboard(makeUser('ADMIN', { username: 'sansprenom', first_name: '' }))
    expect(await screen.findByText(/Bonjour, sansprenom/)).toBeInTheDocument()
  })

  // Régression §10.17 (corrigé au LOT 43) : readDashboardFilters normalise
  // désormais une `presence_period` inconnue (URL trafiquée ou lien erroné)
  // vers « jour ». Avant le correctif, `periodLabels[presencePeriod]` valait
  // undefined et le rendu levait sur `.toUpperCase()`, rendant l'écran blanc.
  it('une presence_period inconnue dans l’URL est normalisée vers le jour sans planter (§10.17)', async () => {
    mountDashboard(adminMe(), '/?presence_period=bizarre')
    // Les indicateurs du jour s'affichent normalement.
    expect(await screen.findByText('Nombre Étudiants Présents/Attendus')).toBeInTheDocument()
    expect(screen.getByText(/présences du /i)).toBeInTheDocument()
    // La valeur invalide n'est jamais répercutée vers l'API.
    const anyCallWithBizarre = apiMock.get.mock.calls.some(([p]) => String(p).includes('bizarre'))
    expect(anyCallWithBizarre).toBe(false)
    expect(screen.queryByText(/bizarre/i)).not.toBeInTheDocument()
  })

  it('sans aucun filtre actif (ni période, ni jour de référence), l’appel stats n’a aucune query string', async () => {
    // Une préférence de période corrompue/vide équivaut à « tout » sans émettre
    // le paramètre preset (buildFinancePeriodQuery court-circuite si !preset).
    window.sessionStorage.setItem('finance_period', JSON.stringify({ preset: '' }))
    mountDashboard(adminMe())
    const dateInput = await screen.findByLabelText('Jour spécifique')

    // La référence par défaut est la date du jour : il faut la vider pour que
    // l'appel stats ne porte plus aucun paramètre.
    fireEvent.change(dateInput, { target: { value: '' } })
    await waitFor(() => {
      const rawCalls = apiMock.get.mock.calls
        .map(([p]) => p)
        .filter((p) => p.split('?')[0] === '/formations/stats/')
      expect(rawCalls.at(-1)).toBe('/formations/stats/')
    })
  })

  // Régression §10.17 (corrigé au LOT 43) : quand l'utilisateur vide le champ
  // « Jour spécifique », referenceDate devient '' : le bloc présences et la
  // liste retombent sur le jour courant, et le sous-titre affiche désormais
  // la date du jour (avant : « Référence: Invalid Date »).
  it('vider « Jour spécifique » replace sur le jour et affiche la date du jour en référence (§10.17)', async () => {
    mountDashboard(adminMe())
    const input = await screen.findByLabelText('Jour spécifique')
    fireEvent.change(input, { target: { value: '2026-01-15' } })
    expect(await screen.findByText(/Référence: 15\/01\/2026/)).toBeInTheDocument()

    fireEvent.change(input, { target: { value: '' } })
    expect(await screen.findByText(/présences du jour/i)).toBeInTheDocument()
    expect(screen.queryByText(/Invalid Date/)).not.toBeInTheDocument()
    const todayLabel = new Date().toLocaleDateString('fr-FR')
    expect(screen.getByText(new RegExp(`Référence: ${todayLabel.replace(/\//g, '\\/')}`))).toBeInTheDocument()
    const last = callsTo('/formations/list/').at(-1)
    expect(last.has('date_mode')).toBe(false)
    expect(last.get('seance_en_cours')).toBe('true')
  })

})

describe('pages/Dashboard.jsx — rafraîchissement au retour d’onglet (§10.16)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    window.sessionStorage.clear()
    // Pas de route stats ici : chaque teste définit la sienne.
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  // Régression §10.16 (corrigé au LOT 43) : useVisibilityPolling appelle le
  // rafraîchissement avec un booléen (`callback(true)`), convention que
  // loadDashboardData respecte désormais (signature positionnelle `silent`,
  // comme ModuleDetail.refreshPresences). Un échec du rechargement de fond au
  // retour d'onglet ne doit donc PAS faire apparaître le bandeau d'erreur.
  it('le rafraîchissement au retour d’onglet est silencieux : un échec de fond n’affiche pas le bandeau (§10.16)', async () => {
    let statsAttempts = 0
    apiController.setRoute('/formations/stats/', () => {
      statsAttempts += 1
      if (statsAttempts > 1) {
        throw Object.assign(new Error('réseau'), { response: { data: { detail: 'indisponible' } } })
      }
      return dashboardStats()
    })

    mountDashboard(adminMe())
    await waitFor(() => expect(callsTo('/formations/stats/').length).toBe(1))
    expect(screen.queryByText(/n'ont pas pu être chargées/)).not.toBeInTheDocument()

    // jsdom expose visibilityState sur Document.prototype : on pose un
    // descripteur propre (« visible ») qu'on supprimera pour restaurer l'état
    // initial et éviter toute fuite vers les tests suivants.
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      get: () => 'visible',
    })
    try {
      await act(async () => {
        document.dispatchEvent(new Event('visibilitychange'))
      })

      await waitFor(() => expect(callsTo('/formations/stats/').length).toBe(2))
      // Le deuxième appel a bien eu lieu (silencieux) et l'écran reste sans
      // bandeau d'erreur ; une courte attente garantit qu'aucun état n'est posé.
      await act(async () => {})
      expect(screen.queryByText(/certaines données n'ont pas pu être chargées/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/erreur lors du chargement/i)).not.toBeInTheDocument()
    } finally {
      delete document.visibilityState
    }
  })
})
