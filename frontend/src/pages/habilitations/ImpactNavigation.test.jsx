/** Tests d'intégration UI/UX du module « Utilisateurs & Accès »
 * (navigation contextuelle F1→F8 intégrée).
 *
 * Parcours validés :
 * A. Compte → fiche → accès effectifs / impact (?user=)
 * B. Rôle → impact (?code=) depuis le référentiel ET la matrice
 * C. Permission → impact (?code=) depuis le catalogue
 * D. Dashboard → tuiles cliquables vers les données correspondantes
 *
 * Convention d'erreurs du mock : fonction qui `throw { response: … }`.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, within } from '@testing-library/react'
import { Routes, Route } from 'react-router-dom'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import GestionRoles from './GestionRoles'
import MatricePermissions from './MatricePermissions'
import CataloguePermissions from './CataloguePermissions'
import FicheCompte from './FicheCompte'
import Dashboard from './Dashboard'
import ImpactPermission from './ImpactPermission'
import ImpactRole from './ImpactRole'
import ImpactUtilisateur from './ImpactUtilisateur'
import AccesEffectifs from './AccesEffectifs'

function monter(element, chemin = '/administration/comptes',
                routePattern = chemin) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  return render(element, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern={routePattern}
                    initialEntries={[chemin]}>{children}</AllProviders>
    ),
  })
}

/** Monte un arbre de routes (pour tester la navigation réelle entre écrans). */
function monterRoutes(routesJsx, chemin) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  return render(routesJsx, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="*"
                    initialEntries={[chemin]}>
        <Routes>{children}</Routes>
      </AllProviders>
    ),
  })
}

const arbreConsole = (
  <>
    <Route path="/administration/comptes/roles" element={<GestionRoles />} />
    <Route path="/administration/comptes/matrice" element={<MatricePermissions />} />
    <Route path="/administration/comptes/permissions" element={<CataloguePermissions />} />
    <Route path="/administration/comptes/impact-role" element={<ImpactRole />} />
    <Route path="/administration/comptes/impact-permission" element={<ImpactPermission />} />
    <Route path="/administration/comptes/impact-utilisateur" element={<ImpactUtilisateur />} />
    <Route path="/administration/comptes/acces-effectifs" element={<AccesEffectifs />} />
    <Route path="/administration/comptes/dashboard" element={<Dashboard />} />
    <Route path="/administration/comptes/:id" element={<FicheCompte />} />
  </>
)

const compteDetail = {
  id: 3, user_id: 21, username: 'hab.agent', email: 'agent@injs.ci',
  is_active: true, role_legacy: 'SECRETARIAT', statut: 'ACTIF', canal: 'WEB',
  mfa_actif: false, nb_roles: 1, nb_roles_sensibles: 1,
  personne: { nom: 'KONE', prenoms: 'Awa', matricule: 'HAB-0001' },
  roles_actifs: [{
    id: 9, role: 'RESPONSABLE_CONCOURS', role_libelle:
    'Responsable concours et sélection', niveau: 'N3', sensible: true,
    validee: true, perimetres: [],
  }],
  journal: [],
  impact: {
    type: 'utilisateur', user_id: 21, compte_id: 3, username: 'hab.agent',
    total_roles: 1, total_directes: 2, total_heritees: 5,
    total_effectives: 7, total_retraits: 1,
    modules_effectifs: [
      { module: 'candidatures', module_libelle: 'Candidatures et concours' },
      { module: 'scolarite', module_libelle: 'Scolarité' },
    ],
    actions_sensibles_effectives: ['jurys.pv.signer'],
    arbre: { roles: [], derogations: [], retraits: [] },
    octrois_directs: [], retraits: [],
  },
}

const rolesCurp = [
  { code: 'RESPONSABLE_CONCOURS', libelle: 'Responsable concours et sélection',
    domaine: 'CANDIDATURES', niveau_defaut: 'N3', sensible: true,
    disponible: true, canal_impose: '', permissions_count: 12 },
  { code: 'SCOLARITE', libelle: 'Scolarité', domaine: 'ADMINISTRATION',
    niveau_defaut: 'N3', sensible: false, disponible: true,
    canal_impose: '', permissions_count: 9 },
]

const detailRole = {
  code: 'RESPONSABLE_CONCOURS',
  libelle: 'Responsable concours et sélection',
  description: 'Organise les concours.',
  domaine: 'CANDIDATURES', niveau_defaut: 'N3',
  perimetre_defaut: 'INJS_ENTIER', sensible: true, disponible: true,
  incompatible_avec: [],
  comptes_titulaires: [{ compte: 3, nom: 'KONE', prenoms: 'Awa',
                         username: 'hab.agent', statut: 'ACTIF' }],
}

const matrice = {
  modules: [{ code: 'candidatures', libelle: 'Candidatures et concours' }],
  lignes: [
    { code: 'SCOLARITE', libelle: 'Scolarité', domaine: 'ADMINISTRATION',
      sensible: false,
      niveaux: { candidatures: { niveau: 'N3', origine: 'A2' } } },
  ],
}

const catalogue = {
  count: 2,
  results: [
    { code: 'evaluations.note.modifier', libelle: 'modifier note',
      module: 'evaluations', ressource: 'note', action: 'modifier',
      criticite: 'CRITIQUE', necessite_motif: true, journalisee: true,
      actif: true, portee_maximale: 'INJS_ENTIER',
      necessite_double_validation: true },
    { code: 'scolarite.annee.consulter', libelle: 'consulter annee',
      module: 'scolarite', ressource: 'annee', action: 'consulter',
      criticite: 'NORMALE', necessite_motif: false, journalisee: false,
      actif: true, portee_maximale: 'INJS_ENTIER',
      necessite_double_validation: false },
  ],
}

const dashboardData = {
  comptes: { total: 3, par_statut: { ACTIF: 3 }, actifs: 3, non_actifs: 0 },
  roles: { total: 35, actifs: 34, sensibles: 11, disponibles: 33 },
  permissions: {
    total: 1155, actives: 1155, sensibles: 15, avec_motif: 19,
    par_module: [{ module: 'evaluations', total: 90 }],
  },
  comptes_privileges: 1,
  derogations: { octrois: 0, retraits: 0 },
  delegations: { actives: 0, expirant_prochainement: 0 },
  provisionnement: { propositions_en_attente: 0 },
  dernieres_actions: [],
  date_reference: '2026-10-05',
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

describe('Parcours A — Compte → fiche → accès effectifs / impact', () => {
  it('la fiche affiche les compteurs CURP et les liens contextuels', async () => {
    apiController.setRoute(/comptes\/3\/$/, compteDetail)
    apiController.setRoute(/comptes\/3\/effective-permissions\//, {
      count: 7, codes: ['candidatures.concours.consulter'],
    })
    monter(<FicheCompte />, '/administration/comptes/3',
           '/administration/comptes/:id')
    expect(await screen.findByTestId('fiche-impact-compteurs'))
      .toHaveTextContent('effectives au total : 7')
    const lienArbre = screen.getByTestId('fiche-lien-acces-effectifs')
    const lienImpact = screen.getByTestId('fiche-lien-impact-utilisateur')
    // Cohérence des paramètres : l'API d'impact attend le user_id (21),
    // pas le pk du compte CURP (3).
    expect(lienArbre.getAttribute('href'))
      .toBe('/administration/comptes/acces-effectifs?user=21')
    expect(lienImpact.getAttribute('href'))
      .toBe('/administration/comptes/impact-utilisateur?user=21')
    expect(screen.getByTestId('fiche-impact-sensibles'))
      .toHaveTextContent('jurys.pv.signer')
  })
})

describe('Parcours B — Rôle → impact (?code=)', () => {
  it('le référentiel expose un lien impact par rôle, le détail aussi', async () => {
    apiController.setRoute(/roles\/$/, rolesCurp)
    apiController.setRoute(/roles\/RESPONSABLE_CONCOURS\/$/, detailRole)
    monterRoutes(arbreConsole, '/administration/comptes/roles')
    const lienLigne = await screen.findByTestId(
      'lien-impact-role-RESPONSABLE_CONCOURS')
    expect(lienLigne.getAttribute('href'))
      .toBe('/administration/comptes/impact-role?code=RESPONSABLE_CONCOURS')
    apiController.setRoute(/impact\/role\/RESPONSABLE_CONCOURS\/$/, {
      type: 'role', code: 'RESPONSABLE_CONCOURS',
      libelle: 'Responsable concours et sélection', description: '',
      domaine: 'CANDIDATURES', niveau_defaut: 'N3',
      perimetre_defaut: 'INJS_ENTIER', canal_impose: '', sensible: true,
      disponible: true, actif: true, cumulable: true,
      total_permissions: 0, permissions_par_module: [], modules_impactes: [],
      permissions_sensibles: [], total_titulaires: 1,
      titulaires: [{ id: 3, user_id: 21, username: 'hab.agent', nom: 'KONE',
                     prenoms: 'Awa', statut: 'ACTIF' }],
    })
    const utilisateur = userEvent.setup()
    await utilisateur.click(lienLigne)
    expect(await screen.findByTestId('impact-role-resultat')).toBeInTheDocument()
    expect(screen.getByTestId('impact-role-resultat'))
      .toHaveTextContent('Responsable concours et sélection')
  })

  it('la matrice ouvre l impact du rôle depuis chaque ligne', async () => {
    apiController.setRoute(/matrice\/$/, matrice)
    monter(<MatricePermissions />, '/administration/comptes/matrice')
    const lien = await screen.findByTestId('lien-impact-matrice-SCOLARITE')
    expect(lien.getAttribute('href'))
      .toBe('/administration/comptes/impact-role?code=SCOLARITE')
  })
})

describe('Parcours C — Permission → impact (?code=)', () => {
  it('le catalogue liste les permissions, badge sensible et lien impact', async () => {
    apiController.setRoute(/permissions\/\?page=1$/, catalogue)
    monter(<CataloguePermissions />, '/administration/comptes/permissions')
    const ligneSensible = await screen.findByTestId(
      'catalogue-ligne-evaluations.note.modifier')
    expect(within(ligneSensible)
      .getByTestId('sensible-badge-permission')).toBeInTheDocument()
    expect(screen.getByTestId('catalogue-total'))
      .toHaveTextContent('2 permissions au total')
    expect(screen.getByTestId('catalogue-impact-evaluations.note.modifier')
      .getAttribute('href'))
      .toBe('/administration/comptes/impact-permission?code=evaluations.note.modifier')
  })

  it('la vue impact lit le paramètre ?code= du lien contextuel', async () => {
    apiController.setRoute(/impact\/permission\/.+\/$/, {
      type: 'permission', code: 'evaluations.note.modifier',
      module: 'evaluations', module_libelle: 'Évaluations et notes',
      ressource: 'note', action: 'modifier', niveau: 2,
      criticite: 'CRITIQUE', sensible: true, necessite_motif: true,
      necessite_double_validation: true, journalisee: true,
      portee_maximale: 'INJS_ENTIER', roles: [], total_roles: 0,
      total_comptes_roles: 0, total_comptes_derogation: 0,
      total_comptes: 0, comptes_roles: [], comptes_derogation: [],
    })
    monter(<ImpactPermission />,
           '/administration/comptes/impact-permission?code=evaluations.note.modifier',
           '/administration/comptes/impact-permission')
    expect(await screen.findByTestId('impact-permission-resultat'))
      .toBeInTheDocument()
  })
})

describe('Parcours D — Dashboard → données correspondantes', () => {
  it('les tuiles cliquables pointent vers les écrans réels', async () => {
    apiController.setRoute(/dashboard\/$/, dashboardData)
    monter(<Dashboard />, '/administration/comptes/dashboard')
    const tuileComptes = await screen.findByTestId('dash-comptes')
    expect(tuileComptes.closest('a'))
      .toHaveAttribute('href', '/administration/comptes')
    expect(screen.getByTestId('dash-permissions-sensibles').closest('a'))
      .toHaveAttribute('href', '/administration/comptes/permissions')
    expect(screen.getByTestId('dash-privileges')).not.toHaveAttribute('href')
  })
})

describe('AccesEffectifs lit ?user= (parcours A, étape finale)', () => {
  it('analyse automatiquement via ?user=21', async () => {
    apiController.setRoute(/impact\/utilisateur\/21\/$/, {
      type: 'utilisateur', user_id: 21, compte_id: 3,
      username: 'hab.agent', nom: 'KONE', prenoms: 'Awa', statut: 'ACTIF',
      total_roles: 1, total_effectives: 7,
      roles: [{
        code: 'RESPONSABLE_CONCOURS',
        libelle: 'Responsable concours et sélection', sensible: true,
        niveau_effectif: 'N3', perimetres: [], date_debut: '2026-09-01',
        date_fin: null,
        modules: [{ module: 'candidatures',
                    module_libelle: 'Candidatures et concours',
                    permissions: ['candidatures.concours.consulter'] }],
        permissions: ['candidatures.concours.consulter'],
      }],
      arbre: {
        roles: [{
          code: 'RESPONSABLE_CONCOURS',
          libelle: 'Responsable concours et sélection', sensible: true,
          niveau_effectif: 'N3', perimetres: [],
          date_debut: '2026-09-01', date_fin: null,
          modules: [{ module: 'candidatures',
                      module_libelle: 'Candidatures et concours',
                      permissions: ['candidatures.concours.consulter'] }],
          permissions: ['candidatures.concours.consulter'],
        }],
        derogations: [], retraits: [],
      },
      permissions_directes: [], permissions_retraits: [],
      total_directes: 0, total_heritees: 1, total_retraits: 0,
      modules_effectifs: [{ module: 'candidatures',
                            module_libelle: 'Candidatures et concours' }],
      actions_sensibles_effectives: ['jurys.pv.signer'],
      delegations_recues: [], octrois_directs: [], retraits: [],
    })
    monter(<AccesEffectifs />, '/administration/comptes/acces-effectifs?user=21',
           '/administration/comptes/acces-effectifs')
    expect(await screen.findByTestId('arbre-acces')).toBeInTheDocument()
    expect(screen.getByTestId('arbre-bascule-role-RESPONSABLE_CONCOURS'))
      .toBeInTheDocument()
  })
})
