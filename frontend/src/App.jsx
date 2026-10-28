import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Link } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import ProtectedRoute, { FORCED_PASSWORD_PATH } from './components/auth/ProtectedRoute'
// Coquille (barre latérale RBAC + barre supérieure) extraite de ce fichier :
// la navigation est déclarée dans `src/menu/arborescence.js` et filtrée par les
// droits du compte connecté (`hooks/useMenuAutorise`).
import Layout from './components/layout/Layout'
import { routesGeneriques } from './menu/routesGeneriques'
import CapabilitiesSync from './components/auth/CapabilitiesSync'
import Login from './pages/Login'
import ForcedPasswordChange from './pages/ForcedPasswordChange'
import Formations from './pages/Formations'
import FormationsLmd from './pages/FormationsLmd'
import FormationDetail from './pages/FormationDetail'
import ModuleDetail from './pages/ModuleDetail'
import Participants from './pages/Participants'
import Rattrapages from './pages/Rattrapages'
import Formateurs from './pages/Formateurs'
import Users from './pages/Users'
import ImportExcel from './pages/ImportExcel'
import Secretariats from './pages/Secretariats'
import Organigramme from './pages/Organigramme'
import Referentiels from './pages/Referentiels'
import Parametres from './pages/Parametres'
import FeatureFlags from './pages/FeatureFlags'
// Planche de style : documentation vivante du socle visuel (lecture seule).
import PlancheDeStyle from './pages/design/PlancheDeStyle'
// U4 — console CURP d'administration des comptes (derrière le drapeau
// CURP_UI_ADMIN : sans la capacité habilitations_admin.gerer, rien n'apparaît).
import HabilitationsLayout from './pages/habilitations/HabilitationsLayout'
import ListeComptes from './pages/habilitations/ListeComptes'
import FicheCompte from './pages/habilitations/FicheCompte'
import AssistantCreation from './pages/habilitations/AssistantCreation'
import ModificationCompte from './pages/habilitations/ModifierCompte'
import GestionRoles from './pages/habilitations/GestionRoles'
import MatricePermissions from './pages/habilitations/MatricePermissions'
import Derogations from './pages/habilitations/Derogations'
import Delegations from './pages/habilitations/Delegations'
import DemandesAcces from './pages/habilitations/DemandesAcces'
import OperationsMasse from './pages/habilitations/OperationsMasse'
import FileProvisionnement from './pages/habilitations/FileProvisionnement'
import NotificationsHabilitation from './pages/habilitations/NotificationsHabilitation'
import RevueHabilitations from './pages/habilitations/RevueHabilitations'
import JournalHabilitations from './pages/habilitations/JournalHabilitations'
// Couche IMPACT (additive) — vues d'impact, accès effectifs, dashboard.
import DashboardHabilitations from './pages/habilitations/Dashboard'
import ImpactPermission from './pages/habilitations/ImpactPermission'
import ImpactModule from './pages/habilitations/ImpactModule'
import ImpactRole from './pages/habilitations/ImpactRole'
import ImpactUtilisateur from './pages/habilitations/ImpactUtilisateur'
import AccesEffectifs from './pages/habilitations/AccesEffectifs'
import CataloguePermissions from './pages/habilitations/CataloguePermissions'
import Modules from './pages/Modules'
import Profile from './pages/Profile'
import FinanceDashboard from './pages/FinanceDashboard'
import FinanceParametrage from './pages/FinanceParametrage'
import FinanceAjustements from './pages/FinanceAjustements'
import FinanceEncadrants from './pages/FinanceEncadrants'
import EvaluationList from './pages/EvaluationList'
import EvaluationDetail from './pages/EvaluationDetail'
import EvaluationTake from './pages/EvaluationTake'
import Edts from './pages/Edts'
import EdtPresences from './pages/EdtPresences'
import CoursLmd from './pages/CoursLmd'
import EdtNew from './pages/EdtNew'
import AffectationNew from './pages/AffectationNew'

import FicheAuditeur from './pages/FicheAuditeur'
import FicheFormateur from './pages/FicheFormateur'
import EvaluationDashboard from './pages/EvaluationDashboard'
import {
  ListeEvaluations,
  TableauDeBordEvaluations,
  SaisieNotes,
  ControleNotes,
  Deliberations,
  ResultatsEvaluations,
  Reveles,
} from './pages/EvaluationsModule'
import AnalyseQualitative from './pages/AnalyseQualitative'
import NotesModule from './pages/NotesModule'
import DecisionsPedagogiques from './pages/DecisionsPedagogiques'
import ArchivesDashboard from './pages/archives/ArchivesDashboard'
import ArchiveListesNotes from './pages/archives/ArchiveListesNotes'
import ArchiveCahiersAppel from './pages/archives/ArchiveCahiersAppel'
import ModulesListLink from './components/ModulesListLink'
import {
  ADMIN_LEVEL_ROLES,
  STATS_ALLOWED_ROLES,
  USERS_ALLOWED_ROLES,
  IMPORT_ALLOWED_ROLES,
  EVALUATION_ALLOWED_ROLES,
  NOTE_GESTION_ROLES,
  FINANCE_EXPORT_ROLES,
  FINANCE_SETTINGS_ROLES,
  OPERATION_VIEW_ROLES,
  OPERATIONAL_WEB_ROLES,
  PARTICIPANT_LIST_ROLES,
  ARCHIVE_CONSULT_ROLES,
  PRESENCE_VIEW_ROLES,
  SCOLARITE_VIEW_ROLES,
} from './utils/roles'

const Statistiques = lazy(() => import('./pages/Statistiques'))
const ScolariteDashboard = lazy(() => import('./pages/scolarite/ScolariteDashboard'))
const Candidatures = lazy(() => import('./pages/scolarite/Candidatures'))
const AdmissionsPage = lazy(() => import('./pages/scolarite/Admissions'))
const Inscriptions = lazy(() => import('./pages/scolarite/Inscriptions'))
const FicheEtudiant = lazy(() => import('./pages/scolarite/FicheEtudiant'))
const GroupesPedagogiques = lazy(() => import('./pages/scolarite/Groupes'))
const Maquettes = lazy(() => import('./pages/scolarite/Maquettes'))
const MaquetteDetail = lazy(() => import('./pages/scolarite/MaquetteDetail'))
const Campagnes = lazy(() => import('./pages/scolarite/Campagnes'))
const CampagneDetail = lazy(() => import('./pages/scolarite/CampagneDetail'))
const MonEspace = lazy(() => import('./pages/scolarite/MonEspace'))
const Equivalences = lazy(() => import('./pages/scolarite/Equivalences'))
const ChargesEnseignants = lazy(() => import('./pages/scolarite/ChargesEnseignants'))
const Jurys = lazy(() => import('./pages/scolarite/Jurys'))
const Graduation = lazy(() => import('./pages/scolarite/Graduation'))
const FinancesEtudiantes = lazy(() => import('./pages/scolarite/FinancesEtudiantes'))
const DashboardEngineView = lazy(() => import('./pages/DashboardEngineView'))

/**
 * Fil d'Ariane du module Évaluations (E1.3).
 *
 * Toutes les routes du module partagent le même préfixe « Évaluations » puis
 * portent LEUR PROPRE libellé : c'est ce qui corrige l'affichage de
 * « Évaluations » comme titre de « Saisie des notes ».
 *
 * @param {string} libelle  Libellé du sous-module (ex. « Saisie des notes »)
 * @param {string} [detail] Détail optionnel (ex. code ECUE réel)
 */
function filEvaluations(libelle, detail) {
  return (
    <>
      <li><Link to="/">Accueil</Link></li>
      <li className="separator">/</li>
      <li><Link to="/evaluations/tableau-de-bord">Évaluations</Link></li>
      <li className="separator">/</li>
      <li>{libelle}</li>
      {detail && (
        <>
          <li className="separator">/</li>
          <li>{detail}</li>
        </>
      )}
    </>
  )
}


function App() {
  function HomeRoute() {
    const { user } = useAuth()
    // FINANCE est redirigé vers finance-dashboard par défaut
    if (user?.role === 'FINANCE') return <Navigate to="/finance-dashboard" replace />
    if (user?.role === 'ARCHIVE') return <Navigate to="/archives" replace />
    // DIRECTION peut choisir entre les deux dashboards
    if (user?.role === 'SUPERVISEUR') return <Navigate to="/evaluations" replace />
    return (
      <Layout breadcrumb={<li>Tableau de bord LMD 2026</li>}>
        <DashboardEngineView />
      </Layout>
    )
  }

  function DashboardRoute() {
    return (
      <Layout breadcrumb={<li>Tableau de bord LMD 2026</li>}>
        <DashboardEngineView />
      </Layout>
    )
  }

  function EvaluationRoute() {
    const { user } = useAuth()
    return (
      <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Évaluations</li></>}>
        {user?.role === 'SUPERVISEUR' ? <EvaluationDashboard /> : <EvaluationList />}
      </Layout>
    )
  }

  return (
    <AuthProvider>
      <CapabilitiesSync />
      <ToastProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route path={FORCED_PASSWORD_PATH} element={
            <ProtectedRoute>
              <ForcedPasswordChange />
            </ProtectedRoute>
          } />
          <Route path="/" element={
            <ProtectedRoute>
              <HomeRoute />
            </ProtectedRoute>
          } />
          <Route path="/mon-espace" element={
            <ProtectedRoute>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Mon espace étudiant</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <MonEspace />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/profile" element={
            <ProtectedRoute>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Mon profil</li></>}>
                <Profile />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formations" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Formations LMD</li></>}>
                <FormationsLmd />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formations-operations" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Formations</li></>}>
                <Formations />
              </Layout>
            </ProtectedRoute>
          } />
          {/* Alias historique : /formations/operational conserve l'accès aux
              sessions d'exploitation (modules, notes, présences) sans
              l'exposer sous le libellé « Formations LMD » (L6 §11). */}
          <Route path="/formations/operational" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Formations</li></>}>
                <Formations />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formations/:formationId/modules/:moduleId/notes" element={
            <ProtectedRoute allowedRoles={NOTE_GESTION_ROLES} capacite={{ module: 'notes', action: 'gerer' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><ModulesListLink>Cours</ModulesListLink></li><li className="separator">/</li><li>Notes</li></>}>
                <NotesModule />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formations/:formationId/decisions" element={
            <ProtectedRoute allowedRoles={NOTE_GESTION_ROLES} capacite={{ module: 'notes', action: 'gerer' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><ModulesListLink>Cours</ModulesListLink></li><li className="separator">/</li><li>Décisions pédagogiques</li></>}>
                <DecisionsPedagogiques />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formations/:formationId/modules/:moduleId" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><ModulesListLink>Cours</ModulesListLink></li><li className="separator">/</li><li>Cours</li></>}>
                <ModuleDetail />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/auditeurs/:participantId/formations/:formationId/fiche" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Fiche étudiant</li></>}>
                <FicheAuditeur />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formateurs/:formateurId/modules/:moduleId/fiche" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Fiche enseignant</li></>}>
                <FicheFormateur />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formations/:id" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><ModulesListLink>Cours</ModulesListLink></li><li className="separator">/</li><li>Formation</li></>}>
                <FormationDetail />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/modules" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Cours</li></>}>
                <Modules />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/participants" element={
            <ProtectedRoute allowedRoles={PARTICIPANT_LIST_ROLES} capacite={{ module: 'participants', action: 'lister' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Étudiants</li></>}>
                <Participants />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Scolarité</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <ScolariteDashboard />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/candidatures" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Candidatures</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Candidatures />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/admissions" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Admissions</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <AdmissionsPage />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/inscriptions" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Inscriptions</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Inscriptions />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/etudiants/:id" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Fiche étudiant</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <FicheEtudiant />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/groupes" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Groupes</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <GroupesPedagogiques />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/maquettes" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Maquettes LMD</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Maquettes />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/maquettes/:id" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li><Link to="/scolarite/maquettes">Maquettes LMD</Link></li><li className="separator">/</li><li>Détail</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <MaquetteDetail />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/campagnes" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Campagnes d'admission</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Campagnes />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/campagnes/:id" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li><Link to="/scolarite/campagnes">Campagnes</Link></li><li className="separator">/</li><li>Détail</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <CampagneDetail />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/equivalences" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Équivalences et dispenses</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Equivalences />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/charges" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Charges pédagogiques</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <ChargesEnseignants />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/jurys" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Sessions de jury</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Jurys />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/graduation" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Diplômation</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Graduation />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/scolarite/finances" element={
            <ProtectedRoute allowedRoles={SCOLARITE_VIEW_ROLES} capacite={{ module: 'scolarite', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/scolarite">Scolarité</Link></li><li className="separator">/</li><li>Finances étudiantes</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <FinancesEtudiantes />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/rattrapages" element={
            <ProtectedRoute allowedRoles={PRESENCE_VIEW_ROLES} capacite={{ module: 'presences', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Rattrapages</li></>}>
                <Rattrapages />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/formateurs" element={
            <ProtectedRoute allowedRoles={[...OPERATION_VIEW_ROLES, 'FINANCE']}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Enseignants</li></>}>
                <Formateurs />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/dashboard" element={
            <ProtectedRoute allowedRoles={OPERATIONAL_WEB_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <DashboardRoute />
            </ProtectedRoute>
          } />
          <Route path="/finance-dashboard" element={
            <ProtectedRoute allowedRoles={FINANCE_EXPORT_ROLES} capacite={{ module: 'finance', action: 'exporter' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Tableau de Bord Finance</li></>}>
                <FinanceDashboard />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/finance-ajustements" element={
            <ProtectedRoute allowedRoles={FINANCE_SETTINGS_ROLES} capacite={{ module: 'finance', action: 'parametrer' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Ajustements Finance</li></>}>
                <FinanceAjustements />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/finance-encadrants" element={
            <ProtectedRoute allowedRoles={FINANCE_EXPORT_ROLES} capacite={{ module: 'finance', action: 'exporter' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Encadrants Finance</li></>}>
                <FinanceEncadrants />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/finance-parametrage" element={
            <ProtectedRoute allowedRoles={FINANCE_SETTINGS_ROLES} capacite={{ module: 'finance', action: 'parametrer' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Paramétrage Finance</li></>}>
                <FinanceParametrage />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/users" element={
            <ProtectedRoute allowedRoles={USERS_ALLOWED_ROLES} capacite={{ module: 'utilisateurs', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Utilisateurs</li></>}>
                <Users />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/administration/comptes" element={
            <ProtectedRoute capacite={{ module: 'habilitations_admin', action: 'gerer' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Habilitations</li></>}>
                <HabilitationsLayout />
              </Layout>
            </ProtectedRoute>
          }>
            <Route index element={<ListeComptes />} />
            <Route path="nouveau" element={<AssistantCreation />} />
            <Route path="provisionnement" element={<FileProvisionnement />} />
            <Route path="operations-masse" element={<OperationsMasse />} />
            <Route path="notifications" element={<NotificationsHabilitation />} />
            <Route path="revue" element={<RevueHabilitations />} />
            <Route path="journal" element={<JournalHabilitations />} />
            <Route path="roles" element={<GestionRoles />} />
            <Route path="permissions" element={<CataloguePermissions />} />
            <Route path="matrice" element={<MatricePermissions />} />
            <Route path="derogations" element={<Derogations />} />
            <Route path="delegations" element={<Delegations />} />
            <Route path="demandes" element={<DemandesAcces />} />
            <Route path="organisation" element={<Organigramme />} />
            {/* Couche IMPACT (additive) — placées avant :id pour la lisibilité */}
            <Route path="dashboard" element={<DashboardHabilitations />} />
            <Route path="impact-permission" element={<ImpactPermission />} />
            <Route path="impact-module" element={<ImpactModule />} />
            <Route path="impact-role" element={<ImpactRole />} />
            <Route path="impact-utilisateur" element={<ImpactUtilisateur />} />
            <Route path="acces-effectifs" element={<AccesEffectifs />} />
            <Route path=":id" element={<FicheCompte />} />
            <Route path=":id/modifier" element={<ModificationCompte />} />
          </Route>
          <Route path="/organisation" element={
            <ProtectedRoute>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Directions / Départements / Services</li></>}>
                <Organigramme />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/secretariats" element={<Navigate to="/organisation?onglet=secretariats" replace />} />
          {/* Écran historique conservé pour les liens profonds (remplacé par /organisation). */}
          <Route path="/secretariats/historique" element={
            <ProtectedRoute allowedRoles={ADMIN_LEVEL_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Secrétariats</li></>}>
                <Secretariats />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/import" element={
            <ProtectedRoute allowedRoles={IMPORT_ALLOWED_ROLES} capacite={{ module: 'participants', action: 'gerer' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Import Excel</li></>}>
                <ImportExcel />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/evaluations" element={
            <ProtectedRoute allowedRoles={EVALUATION_ALLOWED_ROLES} capacite={{ module: 'evaluations', action: 'consulter' }}>
              <Layout breadcrumb={filEvaluations('Évaluations')}>
                <ListeEvaluations />
              </Layout>
            </ProtectedRoute>
          } />
          {/* Questionnaires auditeurs : découplés du module Évaluations
              (décision produit E1.2 option a). Fonctionnalité conservée. */}
          <Route path="/evaluations/questionnaires" element={
            <ProtectedRoute allowedRoles={EVALUATION_ALLOWED_ROLES} capacite={{ module: 'evaluations', action: 'gerer_questionnaires' }}>
              <EvaluationRoute />
            </ProtectedRoute>
          } />
          {/* ── Module Évaluations (INJS-LMD) : 7 sous-modules ─────────────
              E1.3 : chaque route porte SON propre fil d'Ariane. Le tableau de
              bord est déclaré avant les autres pour garder l'ordre de la
              barre latérale ; React Router ne dépend pas de cet ordre.
              `/evaluations/saisie` rend l'écran de saisie dédié (E1.3 §2) :
              il ne doit plus afficher « Évaluations » comme titre. */}
          {/* Les éléments sont instanciés dans le `map` (et non dans un tableau
              littéral) : chaque Route porte son propre `key`. */}
          {[
            ['/evaluations/tableau-de-bord', () => <TableauDeBordEvaluations />, 'Tableau de bord des évaluations'],
            ['/evaluations/saisie', () => <SaisieNotes />, 'Saisie des notes'],
            ['/evaluations/saisie/:id', () => <SaisieNotes />, 'Saisie des notes'],
            ['/evaluations/controle', () => <ControleNotes />, 'Contrôle des notes'],
            ['/evaluations/deliberations', () => <Deliberations />, 'Délibérations'],
            ['/evaluations/resultats', () => <ResultatsEvaluations />, 'Résultats'],
            ['/evaluations/releves', () => <Reveles />, 'Relevés de notes'],
          ].map(([chemin, fabrique, libelle]) => (
            <Route
              key={chemin}
              path={chemin}
              element={
                <ProtectedRoute allowedRoles={EVALUATION_ALLOWED_ROLES} capacite={{ module: 'evaluations', action: 'consulter' }}>
                  <Layout breadcrumb={filEvaluations(libelle)}>
                    {fabrique()}
                  </Layout>
                </ProtectedRoute>
              }
            />
          ))}
          {/* Rattrapage : aucun sous-menu (API non exposée — cf. E1.2 §16) */}
          <Route path="/evaluations/repondre/:id" element={
            <ProtectedRoute allowedRoles={EVALUATION_ALLOWED_ROLES} capacite={{ module: 'evaluations', action: 'gerer_questionnaires' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/evaluations">Évaluations</Link></li><li className="separator">/</li><li>Répondre</li></>}>
                <EvaluationTake />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/evaluations/:id" element={
            <ProtectedRoute allowedRoles={EVALUATION_ALLOWED_ROLES} capacite={{ module: 'evaluations', action: 'gerer_questionnaires' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/evaluations">Évaluations</Link></li><li className="separator">/</li><li>Détail</li></>}>
                <EvaluationDetail />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/evaluations/:id/analyse" element={
            <ProtectedRoute allowedRoles={EVALUATION_ALLOWED_ROLES} capacite={{ module: 'evaluations', action: 'gerer_questionnaires' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/evaluations">Évaluations</Link></li><li className="separator">/</li><li>Analyse qualitative</li></>}>
                <AnalyseQualitative />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/referentiels" element={
            <ProtectedRoute allowedRoles={ADMIN_LEVEL_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Référentiels</li></>}>
                <Referentiels />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/parametres" element={
            <ProtectedRoute allowedRoles={ADMIN_LEVEL_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Paramètres</li></>}>
                <Parametres />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/parametres/flags" element={
            <ProtectedRoute allowedRoles={ADMIN_LEVEL_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/parametres">Paramètres</Link></li><li className="separator">/</li><li>Fonctionnalités</li></>}>
                <FeatureFlags />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/referentiels/planche-de-style" element={
            <ProtectedRoute allowedRoles={ADMIN_LEVEL_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/referentiels">Référentiels</Link></li><li className="separator">/</li><li>Planche de style</li></>}>
                <PlancheDeStyle />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/statistiques" element={
            <ProtectedRoute allowedRoles={STATS_ALLOWED_ROLES} capacite={{ module: 'statistiques', action: 'voir' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Statistiques</li></>}>
                <Suspense fallback={<div className="loading"><div className="spinner"/></div>}>
                  <Statistiques />
                </Suspense>
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/archives" element={
            <ProtectedRoute allowedRoles={ARCHIVE_CONSULT_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Archives</li></>}>
                <ArchivesDashboard />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/archives/listes-notes" element={
            <ProtectedRoute allowedRoles={ARCHIVE_CONSULT_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/archives">Archives</Link></li><li className="separator">/</li><li>Listes de note</li></>}>
                <ArchiveListesNotes />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/archives/cahiers-appel" element={
            <ProtectedRoute allowedRoles={ARCHIVE_CONSULT_ROLES}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/archives">Archives</Link></li><li className="separator">/</li><li>Cahiers d'appel</li></>}>
                <ArchiveCahiersAppel />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/edt" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Emplois du temps</li></>}>
                <Edts />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/cours" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li>Cours (LMD)</li></>}>
                <CoursLmd />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/edt/presences" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/edt">Emplois du temps</Link></li><li className="separator">/</li><li>Présences de séance</li></>}>
                <EdtPresences />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/edt/nouveau" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/edt">Emplois du temps</Link></li><li className="separator">/</li><li>Nouvel EDT</li></>}>
                <EdtNew />
              </Layout>
            </ProtectedRoute>
          } />
          <Route path="/edt/:edtId/affectation/nouveau" element={
            <ProtectedRoute allowedRoles={OPERATION_VIEW_ROLES} capacite={{ module: 'web', action: 'operationnel' }}>
              <Layout breadcrumb={<><li><Link to="/">Accueil</Link></li><li className="separator">/</li><li><Link to="/edt">Emplois du temps</Link></li><li className="separator">/</li><li>Nouvelle affectation</li></>}>
                <AffectationNew />
              </Layout>
            </ProtectedRoute>
          } />
          {/* Écrans de la navigation réorganisée : routes dérivées de
              l'arborescence du menu (une seule source de vérité). */}
          {routesGeneriques()}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      </ToastProvider>
    </AuthProvider>
  )
}

export default App
