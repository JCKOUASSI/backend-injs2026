import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import { useAuth } from '@/context/AuthContext'
import DashboardEngineView from '@/pages/DashboardEngineView'

function WaitForAuth({ children }) {
  const { isAuthenticated, loading } = useAuth()
  if (loading || !isAuthenticated) return <div className="loading"><div className="spinner" /></div>
  return children
}

const mountDashboardEngine = (me, entry = '/') => {
  apiController.setMe(me)
  return renderWithProviders(
    <WaitForAuth><DashboardEngineView /></WaitForAuth>,
    { authUser: me, initialEntries: [entry], routePattern: '/' },
  )
}

const mockOverviewData = {
  annee_academique: '2026-2027',
  kpis: {
    etudiants_inscrits: 120,
    candidats: 350,
    admis: 130,
    taux_admission: '37.1%',
    enseignants: 24,
    taux_presence: '95.4%',
    jurys_ouverts: 2,
    diplomes_delivres: 85,
  },
  pipeline: [
    { id: 'candidature', label: 'Candidatures', value: 350, icon: 'bi-pencil-square', active: true },
    { id: 'admission', label: 'Admissions', value: 130, icon: 'bi-check2-circle', active: true },
    { id: 'inscription', label: 'Inscriptions', value: 120, icon: 'bi-card-checklist', active: true },
    { id: 'cours', label: 'Enseignement', value: 18, icon: 'bi-journal-bookmark', active: true },
    { id: 'evaluation', label: 'Évaluations', value: 36, icon: 'bi-file-earmark-text', active: true },
    { id: 'jury', label: 'Jurys', value: 2, icon: 'bi-balance-scale', active: true },
    { id: 'diplome', label: 'Diplômation', value: 85, icon: 'bi-award', active: true },
  ],
  charts: {
    inscriptions_par_formation: [
      { label: 'Licence STAPS', value: 80 },
      { label: 'Master Management', value: 40 },
    ],
    taux_presences_par_vague: [
      { label: 'Vague 1', value: 60, color: '#10B981' },
      { label: 'Vague 2', value: 40, color: '#2F80ED' },
    ],
  },
  alerts: [
    { type: 'warning', message: '2 conventions en attente de signature.', link: '/scolarite' },
  ],
  quick_actions: [
    { label: 'Nouvelle inscription', to: '/scolarite/inscriptions', icon: 'bi-person-plus-fill' },
  ],
}

const mockScolariteData = {
  annee_academique: '2026-2027',
  kpis: {
    total_inscrits: 120,
    inscriptions_validees: 110,
    en_attente_pieces: 10,
    total_candidatures: 350,
    groupes_pedagogiques: 6,
    maquettes_actives: 4,
  },
  charts: {
    inscriptions_par_formation: [{ label: 'STAPS', value: 120 }],
  },
}

const mockFinancesData = {
  kpis: {
    total_facture_xof: '960,000 XOF',
    total_recouvre_xof: '960,000 XOF',
    taux_recouvrement: '100%',
    factures_soldes: 6,
    quittances_delivrees: 18,
    echeanciers_actifs: 6,
  },
  charts: {
    recouvrement_statuts: [{ label: 'Soldé', value: 960000, color: '#10B981' }],
  },
}

const mockPresencesData = {
  kpis: {
    seances_jour: 4,
    pointages_jour: 31,
    presents_jour: 28,
    retards_jour: 2,
    absents_jour: 1,
    total_historique_pointages: 1450,
  },
}

const mockEtudiantData = {
  annee_academique: '2026-2027',
  etudiant: 'Jean Kouassi',
  matricule: 'INJS26-0042',
  formation: 'Master Management du Sport',
  niveau: 'M1',
  credits_valides: 30,
  credits_requis: 60,
  moyenne_generale: '13.38 / 20',
  taux_presence: '96%',
  solde_finance: '0 FCFA (À jour)',
  kpis: {
    credits_obtenus: 30,
    credits_restants: 30,
    moyenne_generale: '13.38 / 20',
    assiduite: '96%',
    ue_validees: 4,
    ue_a_valider: 2,
    solde_finance: '0 FCFA',
    stage_statut: 'À planifier',
  },
  pipeline: [
    { label: 'Admission', value: 'Validée', active: true, icon: 'bi-check2' },
    { label: 'Inscription LMD', value: 'Inscrit', active: true, icon: 'bi-card-checklist' },
  ],
}

const mockEnseignantData = {
  annee_academique: '2026-2027',
  enseignant: 'Awa Koné',
  specialite: 'STAPS',
  kpis: {
    cours_assignes: 4,
    heures_prevues: 120,
    heures_realisees: 85,
    heures_cm: 42,
    heures_td: 28,
    heures_tp: 16,
    groupes: 3,
    etudiants: 96,
    evaluations_en_attente: 1,
    absences_a_traiter: 2,
  },
}

const mockJurysData = {
  kpis: {
    sessions_ouvertes: 2,
    deliberations_en_cours: 1,
    pv_scelles: 3,
    diplomes_sha256: 6,
    diplomes_delivres: 6,
  },
}

describe('pages/DashboardEngineView.jsx — Rendu et Pilotage LMD 2026', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute('/dashboard/overview/', () => mockOverviewData)
    apiController.setRoute('/dashboard/scolarite/', () => mockScolariteData)
    apiController.setRoute('/dashboard/finances/', () => mockFinancesData)
    apiController.setRoute('/dashboard/presences/', () => mockPresencesData)
    apiController.setRoute('/dashboard/etudiant/', () => mockEtudiantData)
    apiController.setRoute('/dashboard/enseignant/', () => mockEnseignantData)
    apiController.setRoute('/dashboard/jurys/', () => mockJurysData)
    apiController.setRoute('/dashboard/examens/', () => mockJurysData)
    apiController.setRoute('/formations/stats/', () => ({ auditeurs_presents_jour: 10 }))
    apiController.setRoute('/formations/list/', () => ({ results: [], count: 0 }))
    apiController.setRoute('/formations/secretariats/', () => [])
  })

  it('affiche le tableau de bord direction avec pipeline LMD, KPIs et alertes', async () => {
    const admin = makeUser('ADMIN', { username: 'admin' })
    mountDashboardEngine(admin)

    expect(await screen.findByText('Tableau de Bord LMD 2026')).toBeInTheDocument()
    expect(await screen.findByText('Étudiants Inscrits')).toBeInTheDocument()
    expect(screen.getByText(/Cycle de Vie Académique LMD/i)).toBeInTheDocument()
    expect(screen.getAllByText('120').length).toBeGreaterThan(0)
    expect(screen.getByText('Diplômes Scellés')).toBeInTheDocument()
    expect(screen.getAllByText('85').length).toBeGreaterThan(0)
    expect(screen.getByText(/2 conventions en attente de signature/i)).toBeInTheDocument()
  })

  it('permet de naviguer entre les onglets (Vue d\'ensemble → Scolarité)', async () => {
    const admin = makeUser('ADMIN', { username: 'admin' })
    mountDashboardEngine(admin)

    await screen.findByText('Tableau de Bord LMD 2026')
    const scolariteTab = screen.getByRole('tab', { name: /Scolarité & Admissions/i })
    fireEvent.click(scolariteTab)

    expect(await screen.findByText('Total Inscrits LMD')).toBeInTheDocument()
    expect(screen.getByText('En Attente de Pièces')).toBeInTheDocument()
    expect(screen.getByText('Maquettes Actives')).toBeInTheDocument()
  })

  it('ouvre directement l\'espace scolarité pour le rôle SECRETARIAT', async () => {
    const sec = makeUser('SECRETARIAT', { username: 'secretariat1' })
    mountDashboardEngine(sec)

    expect(await screen.findByText('Total Inscrits LMD')).toBeInTheDocument()
    expect(screen.getByText('Inscriptions Validées')).toBeInTheDocument()
    expect(screen.getByText('Maquettes Actives')).toBeInTheDocument()
  })

  it('ouvre directement l\'espace finance pour le rôle FINANCE', async () => {
    const fin = makeUser('FINANCE', { username: 'agent_finance' })
    mountDashboardEngine(fin)

    expect(await screen.findByText('Total Facturé')).toBeInTheDocument()
    expect(screen.getByText('Total Recouvré')).toBeInTheDocument()
    expect(screen.getByText('Factures Soldées')).toBeInTheDocument()
    expect(screen.getAllByText('960,000 XOF').length).toBe(2)
  })

  it('ouvre directement l\'espace présences pour le rôle SUPERVISEUR', async () => {
    const sup = makeUser('SUPERVISEUR', { username: 'superviseur1' })
    mountDashboardEngine(sup)

    expect(await screen.findByText('Séances du Jour')).toBeInTheDocument()
    expect(screen.getByText('Pointages du Jour')).toBeInTheDocument()
    expect(screen.getByText('Présents en Salle')).toBeInTheDocument()
  })

  it('permet de basculer vers le mode opérationnel (séances en direct) et revenir', async () => {
    const admin = makeUser('ADMIN', { username: 'admin' })
    mountDashboardEngine(admin)

    await screen.findByText('Tableau de Bord LMD 2026')
    await screen.findByText('Étudiants Inscrits')
    const directBtn = screen.getByRole('button', { name: /Séances en direct/i })
    fireEvent.click(directBtn)

    // Vérifie le passage en mode opérationnel
    expect(await screen.findByText('Mode Opérationnel')).toBeInTheDocument()
    expect(screen.getByText(/Basculer vers Tableau de bord LMD 2026/i)).toBeInTheDocument()

    // Clic pour revenir au mode décisionnel LMD 2026
    fireEvent.click(screen.getByText(/Basculer vers Tableau de bord LMD 2026/i))
    expect(await screen.findByText('Tableau de Bord LMD 2026')).toBeInTheDocument()
  })

  it('permet à ADMIN de prévisualiser le cockpit étudiant (spec §7)', async () => {
    const admin = makeUser('ADMIN', { username: 'admin' })
    mountDashboardEngine(admin)

    await screen.findByText('Tableau de Bord LMD 2026')
    const etudiantTab = screen.getByRole('tab', { name: /Espace Étudiant/i })
    fireEvent.click(etudiantTab)

    expect(await screen.findByText('Mon parcours LMD')).toBeInTheDocument()
    expect(screen.getByText('Jean Kouassi')).toBeInTheDocument()
    expect(screen.getByText('Crédits obtenus')).toBeInTheDocument()
    expect(screen.getByText('Assiduité')).toBeInTheDocument()
  })

  it('permet à ADMIN de prévisualiser le cockpit enseignant (spec §8)', async () => {
    const admin = makeUser('ADMIN', { username: 'admin' })
    mountDashboardEngine(admin)

    await screen.findByText('Tableau de Bord LMD 2026')
    const enseignantTab = screen.getByRole('tab', { name: /Espace Enseignant/i })
    fireEvent.click(enseignantTab)

    expect(await screen.findByText('Espace enseignant')).toBeInTheDocument()
    expect(screen.getByText('Awa Koné')).toBeInTheDocument()
    expect(screen.getByText('Cours affectés')).toBeInTheDocument()
    expect(screen.getByText('Évaluations en attente')).toBeInTheDocument()
  })
})
