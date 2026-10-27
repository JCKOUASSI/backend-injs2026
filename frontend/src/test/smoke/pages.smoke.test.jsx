/**
 * Tests SMOKE des pages : chaque écran doit monter sans planter avec des
 * données mockées vides (et un compte administrateur). Ces tests ne
 * vérifient pas le détail fonctionnel (couvert par des tests dédiés), mais
 * ils garantissent qu'aucun import cassé, accès à undefined ou erreur de
 * cycle de vie ne fait écran blanc.
 *
 * La liste des pages qu'il n'est PAS possible de monter ainsi (et la raison)
 * est tenue dans docs/TESTS_FRONTEND.md.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, cleanup, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import TestErrorBoundary from '@/test/utils/ErrorBoundary'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import { dashboardStats } from '@/test/fixtures/dashboard'

// Pages principales
import AffectationNew from '@/pages/AffectationNew'
import AnalyseQualitative from '@/pages/AnalyseQualitative'
import Dashboard from '@/pages/Dashboard'
import DecisionsPedagogiques from '@/pages/DecisionsPedagogiques'
import EdtNew from '@/pages/EdtNew'
import Edts from '@/pages/Edts'
import EvaluationAcademique from '@/pages/EvaluationAcademique'
import EvaluationDashboard from '@/pages/EvaluationDashboard'
import EvaluationDetail from '@/pages/EvaluationDetail'
import EvaluationList from '@/pages/EvaluationList'
import EvaluationTake from '@/pages/EvaluationTake'
import FicheAuditeur from '@/pages/FicheAuditeur'
import FicheFormateur from '@/pages/FicheFormateur'
import ForcedPasswordChange from '@/pages/ForcedPasswordChange'
import FinanceAjustements from '@/pages/FinanceAjustements'
import FinanceDashboard from '@/pages/FinanceDashboard'
import FinanceEncadrants from '@/pages/FinanceEncadrants'
import FinanceParametrage from '@/pages/FinanceParametrage'
import Formateurs from '@/pages/Formateurs'
import FormationDetail from '@/pages/FormationDetail'
import Formations from '@/pages/Formations'
import ImportExcel from '@/pages/ImportExcel'
import ModuleDetail from '@/pages/ModuleDetail'
import Modules from '@/pages/Modules'
import NotesModule from '@/pages/NotesModule'
import Parametres from '@/pages/Parametres'
import FeatureFlags from '@/pages/FeatureFlags'
import Participants from '@/pages/Participants'
import Profile from '@/pages/Profile'
import QuizList from '@/pages/QuizList'
import QuizTake from '@/pages/QuizTake'
import Rattrapages from '@/pages/Rattrapages'
import Referentiels from '@/pages/Referentiels'
import Secretariats from '@/pages/Secretariats'
import Statistiques from '@/pages/Statistiques'
import Users from '@/pages/Users'
import ArchivesDashboard from '@/pages/archives/ArchivesDashboard'
import ArchiveListesNotes from '@/pages/archives/ArchiveListesNotes'
import ArchiveCahiersAppel from '@/pages/archives/ArchiveCahiersAppel'

// Pages Scolarité
import Admissions from '@/pages/scolarite/Admissions'
import CampagneDetail from '@/pages/scolarite/CampagneDetail'
import Campagnes from '@/pages/scolarite/Campagnes'
import Candidatures from '@/pages/scolarite/Candidatures'
import ChargesEnseignants from '@/pages/scolarite/ChargesEnseignants'
import Equivalences from '@/pages/scolarite/Equivalences'
import FicheEtudiant from '@/pages/scolarite/FicheEtudiant'
import FinancesEtudiantes from '@/pages/scolarite/FinancesEtudiantes'
import Graduation from '@/pages/scolarite/Graduation'
import Groupes from '@/pages/scolarite/Groupes'
import Inscriptions from '@/pages/scolarite/Inscriptions'
import Jurys from '@/pages/scolarite/Jurys'
import MaquetteDetail from '@/pages/scolarite/MaquetteDetail'
import Maquettes from '@/pages/scolarite/Maquettes'
import MonEspace from '@/pages/scolarite/MonEspace'
import ScolariteDashboard from '@/pages/scolarite/ScolariteDashboard'

// [nom, composant, motif de route, URL initiale]
const PAGES = [
  ['AffectationNew', AffectationNew, '/edt/:edtId/affectation/nouveau', '/edt/1/affectation/nouveau'],
  ['AnalyseQualitative', AnalyseQualitative, '/evaluations/:id/analyse', '/evaluations/1/analyse'],
  ['Dashboard', Dashboard, '/dashboard', '/dashboard'],
  ['DecisionsPedagogiques', DecisionsPedagogiques, '/formations/:formationId/decisions', '/formations/1/decisions'],
  ['EdtNew', EdtNew, '/edt/nouveau', '/edt/nouveau'],
  ['Edts', Edts, '/edt', '/edt'],
  ['EvaluationAcademique', EvaluationAcademique, '*', '/x'],
  ['EvaluationDashboard', EvaluationDashboard, '*', '/x'],
  ['EvaluationDetail', EvaluationDetail, '/evaluations/:id', '/evaluations/1'],
  ['EvaluationList', EvaluationList, '/evaluations', '/evaluations'],
  ['EvaluationTake', EvaluationTake, '/evaluations/repondre/:id', '/evaluations/repondre/1'],
  ['FicheAuditeur', FicheAuditeur, '/auditeurs/:participantId/formations/:formationId/fiche', '/auditeurs/1/formations/1/fiche'],
  ['FicheFormateur', FicheFormateur, '/formateurs/:formateurId/modules/:moduleId/fiche', '/formateurs/1/modules/1/fiche'],
  // Compte admin non flagué : l'écran redirige vers l'accueil via <Navigate>,
  // sans planter ; le comportement forcé est testé dans ForcedPasswordChange.test.jsx.
  ['ForcedPasswordChange', ForcedPasswordChange, '/changement-mot-de-passe-obligatoire', '/changement-mot-de-passe-obligatoire'],
  ['FinanceAjustements', FinanceAjustements, '/finance-ajustements', '/finance-ajustements'],
  ['FinanceDashboard', FinanceDashboard, '/finance-dashboard', '/finance-dashboard'],
  ['FinanceEncadrants', FinanceEncadrants, '/finance-encadrants', '/finance-encadrants'],
  ['FinanceParametrage', FinanceParametrage, '/finance-parametrage', '/finance-parametrage'],
  ['Formateurs', Formateurs, '/formateurs', '/formateurs'],
  ['FormationDetail', FormationDetail, '/formations/:id', '/formations/1'],
  ['Formations', Formations, '/formations', '/formations'],
  ['ImportExcel', ImportExcel, '/import', '/import'],
  ['ModuleDetail', ModuleDetail, '/formations/:formationId/modules/:moduleId', '/formations/1/modules/1'],
  ['Modules', Modules, '/modules', '/modules'],
  ['NotesModule', NotesModule, '/formations/:formationId/modules/:moduleId/notes', '/formations/1/modules/1/notes'],
  ['Parametres', Parametres, '/parametres', '/parametres'],
  ['FeatureFlags', FeatureFlags, '/parametres/flags', '/parametres/flags'],
  ['Participants', Participants, '/participants', '/participants'],
  ['Profile', Profile, '/profile', '/profile'],
  ['QuizList', QuizList, '*', '/quiz'],
  ['QuizTake', QuizTake, '*', '/quiz/1'],
  ['Rattrapages', Rattrapages, '/rattrapages', '/rattrapages'],
  ['Referentiels', Referentiels, '/referentiels', '/referentiels'],
  ['Secretariats', Secretariats, '/secretariats', '/secretariats'],
  ['Statistiques', Statistiques, '/statistiques', '/statistiques'],
  ['Users', Users, '/users', '/users'],
  ['ArchivesDashboard', ArchivesDashboard, '/archives', '/archives'],
  ['ArchiveListesNotes', ArchiveListesNotes, '/archives/listes-notes', '/archives/listes-notes'],
  ['ArchiveCahiersAppel', ArchiveCahiersAppel, '/archives/cahiers-appel', '/archives/cahiers-appel'],
  ['Admissions', Admissions, '/scolarite/admissions', '/scolarite/admissions'],
  ['CampagneDetail', CampagneDetail, '/scolarite/campagnes/:id', '/scolarite/campagnes/1'],
  ['Campagnes', Campagnes, '/scolarite/campagnes', '/scolarite/campagnes'],
  ['Candidatures', Candidatures, '/scolarite/candidatures', '/scolarite/candidatures'],
  ['ChargesEnseignants', ChargesEnseignants, '/scolarite/charges', '/scolarite/charges'],
  ['Equivalences', Equivalences, '/scolarite/equivalences', '/scolarite/equivalences'],
  ['FicheEtudiant', FicheEtudiant, '/scolarite/etudiants/:id', '/scolarite/etudiants/1'],
  ['FinancesEtudiantes', FinancesEtudiantes, '/scolarite/finances', '/scolarite/finances'],
  ['Graduation', Graduation, '/scolarite/graduation', '/scolarite/graduation'],
  ['Groupes', Groupes, '/scolarite/groupes', '/scolarite/groupes'],
  ['Inscriptions', Inscriptions, '/scolarite/inscriptions', '/scolarite/inscriptions'],
  ['Jurys', Jurys, '/scolarite/jurys', '/scolarite/jurys'],
  ['MaquetteDetail', MaquetteDetail, '/scolarite/maquettes/:id', '/scolarite/maquettes/1'],
  ['Maquettes', Maquettes, '/scolarite/maquettes', '/scolarite/maquettes'],
  ['MonEspace', MonEspace, '/mon-espace', '/mon-espace'],
  ['ScolariteDashboard', ScolariteDashboard, '/scolarite', '/scolarite'],
]

// Réponses dédiées quand une page exige des formes de données précises
// (nombres, clés spécifiques) que le mock « vide » générique ne peut fournir.
const FIXTURES = {
  Dashboard: [[/\/formations\/stats/, dashboardStats()]],
}

describe('Tests smoke — toutes les pages montent sans crash', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
    apiController.setMe(makeUser('ADMIN', { username: 'admin' }))
  })

  for (const [name, Component, pattern, url] of PAGES) {
    it(`page « ${name} » monte avec des données vides`, async () => {
      for (const [matcher, data] of FIXTURES[name] || []) apiController.setRoute(matcher, data)
      let captured = null
      const ui = (
        <TestErrorBoundary onError={(e) => (captured = e)}>
          <Component />
        </TestErrorBoundary>
      )
      renderWithProviders(ui, {
        authUser: makeUser('ADMIN', { username: 'admin' }),
        routePattern: pattern,
        initialEntries: [url],
      })

      // Laisse le cycle mount → effets → promesses se résoudre (dans act()
      // pour ne pas laisser de mises à jour d'état asynchrones en suspens).
      await act(async () => {
        await flushPromises(4)
      })

      const crash = screen.queryByTestId('render-crash')
      if (crash) {
        throw new Error(`La page ${name} a planté au rendu : ${crash.textContent} — ${captured?.stack || ''}`)
      }
      expect(crash).toBeNull()
    })
  }
})
