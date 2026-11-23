/** Aligné sur backend/authentication/role_groups.py */

export const ADMIN_LEVEL_ROLES = ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN']

export const ALLOWED_WEB_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'FINANCE',
  'ARCHIVE',
  'ENCADRANT',
  'SUPERVISEUR',
]

export const STAFF_WEB_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ENCADRANT',
  'SUPERVISEUR',
]

/** Module suivi-évaluation (questionnaires). */
export const EVALUATION_ALLOWED_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ENCADRANT',
  'SUPERVISEUR',
]

/** Gestion des notes/épreuves/moyennes (aligné IsGestionNotes). */
export const NOTE_GESTION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ENCADRANT',
  'SUPERVISEUR',
]

/** Validation des décisions pédagogiques (aligné IsDecisionValidator). */
export const DECISION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'ENCADRANT',
  'SUPERVISEUR',
]

/** FINANCE et ARCHIVE : module finance dédié (consultation + export). */
export const FINANCE_MODULE_ROLES = ['FINANCE', 'DIRECTION', 'ARCHIVE']

/** Consultation globale en lecture seule (fiches, données archivées). */
export const ARCHIVE_CONSULT_ROLES = ['ARCHIVE', 'DIRECTION', ...ADMIN_LEVEL_ROLES]

/** Personnel web hors module Finance (aligné OPERATIONAL_WEB_ROLES backend). */
export const OPERATIONAL_WEB_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ARCHIVE',
  'ENCADRANT',
  'SUPERVISEUR',
]

/** Navigation opérationnelle + consultation globale (cours, fiches module). */
export const OPERATION_VIEW_ROLES = [...OPERATIONAL_WEB_ROLES]

/** Liste / fiche auditeurs (aligné PARTICIPANT_LIST_ROLES + CanListParticipants backend). */
export const PARTICIPANT_LIST_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'ARCHIVE',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ENCADRANT',
]

/** Exports finance formateurs / encadrants (sans paramétrage). */
export const FINANCE_EXPORT_ROLES = ['FINANCE', 'DIRECTION', 'ARCHIVE']

/** Export liste de classe auditeurs par groupe. */
export const LISTE_CLASSE_EXPORT_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'ARCHIVE',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ENCADRANT',
]

/** Paramétrage et ajustements finance (hors archiviste). */
export const FINANCE_SETTINGS_ROLES = ['FINANCE', 'DIRECTION']

/** Module Scolarité LMD — consultation (aligné IsSecretariatOrDFRC, DIRECTION en lecture). */
export const SCOLARITE_VIEW_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

/** Module Scolarité LMD — actions (candidatures, admissions, inscriptions). */
export const SCOLARITE_MUTATION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

export function canActScolarite(cible) {
  return autorise(cible, 'scolarite', 'agir')
}

export const STATS_ALLOWED_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'ARCHIVE',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'FINANCE',
  'ENCADRANT',
]

export const USERS_ALLOWED_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

export const IMPORT_ALLOWED_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

/** Mutations formations / modules / séances / inscriptions (aligné IsSecretariatOrEncadrantOrDFRC + secrétariat). */
export const FORMATION_MUTATION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

/** Archivage de modules (masqués des listes opérationnelles). */
export const MODULE_ARCHIVE_ROLES = [
  ...FORMATION_MUTATION_ROLES,
  'DIRECTION',
]

/** POST /formations/participants/ — secrétariat exclu (role_groups exclude add_participant). */
export const PARTICIPANT_CREATE_ROLES = [...ADMIN_LEVEL_ROLES]

/** Modification / suppression fiche auditeur — secrétariat autorisé. */
export const PARTICIPANT_MANAGE_ROLES = FORMATION_MUTATION_ROLES

export const PRESENCE_VIEW_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'ARCHIVE',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'ENCADRANT',
]

export const PRESENCE_ACTION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'ENCADRANT',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

export const SUPERVISION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'ENCADRANT',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

/** Mutations comptes utilisateurs (aligné IsSecretariatOrDFRC — DIRECTION lecture seule). */
export const USER_MUTATION_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
]

export const DASHBOARD_SECRETARIAT_FILTER_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
]

/** Comptes limités aux données de leur secrétariat (stats, dashboard opérationnel). */
export const SECRETARIAT_SCOPED_ROLES = ['SECRETARIAT', 'CHEF_SECRETARIAT']

export function isAdminLevelRole(role) {
  return ADMIN_LEVEL_ROLES.includes(role)
}

// ---------------------------------------------------------------------------
// P00-06 — les helpers d'action ci-dessous acceptent INDISTINCTEMENT une
// chaîne de rôle (comportement historique, repli statique) ou un objet user.
// Avec un user dont les capacités backend sont chargées, c'est le contrat
// GET /auth/capabilities/ qui fait autorité d'affichage ; sinon le repli
// statique FALLBACK_CAPACITES s'applique, à l'identique de l'historique.
// L'API reste quoi qu'il arrive la seule autorité de sécurité.
// ---------------------------------------------------------------------------

export function canMutateFormations(cible) {
  return autorise(cible, 'participants', 'gerer')
}

export function canArchiveModule(cible) {
  return autorise(cible, 'modules', 'archiver')
}

/** Archivage module — capacités backend si chargées, sinon role_context puis rôle. */
export function canArchiveModuleFromUser(user) {
  if (!user) return false
  if (capacitesChargees(user)) return peut(user, 'modules', 'archiver')
  if (user.role_context?.can_archive_modules === true) return true
  return canArchiveModule(user.role)
}

export function canCreateParticipant(cible) {
  return autorise(cible, 'participants', 'creer')
}

export function canManageParticipant(cible) {
  return autorise(cible, 'participants', 'gerer')
}

export function canListParticipants(cible) {
  return autorise(cible, 'participants', 'lister')
}

export function canViewPresences(cible) {
  return autorise(cible, 'presences', 'voir')
}

export function canPresenceAction(cible) {
  return autorise(cible, 'presences', 'agir')
}

export function canSuperviseSessions(cible) {
  return autorise(cible, 'presences', 'superviser')
}

export function canMutateUsers(cible) {
  return autorise(cible, 'utilisateurs', 'gerer')
}

export function canFilterDashboardBySecretariat(cible) {
  return autorise(cible, 'dashboard', 'filtrer_secretariat')
}

export function isSecretariatScopedRole(role) {
  return SECRETARIAT_SCOPED_ROLES.includes(role)
}

/** ID secrétariat imposé pour un compte secrétariat (null si non applicable). */
export function lockedSecretariatId(user) {
  if (!hasAppRole(user, SECRETARIAT_SCOPED_ROLES) || user?.secretariat == null || user?.secretariat === '') {
    return null
  }
  return String(user.secretariat)
}

export function isWebRoleAllowed(role) {
  return ALLOWED_WEB_ROLES.includes(role)
}

export function webLoginForbiddenMessage(role) {
  if (role === 'AUDITEUR') {
    return 'Les comptes étudiant sont réservés à l\'application mobile.'
  }
  if (role === 'FORMATEUR') {
    return 'Les comptes enseignant sont réservés à l\'application mobile.'
  }
  return 'Ce compte n\'a pas accès à la plateforme web.'
}

export function getUserRoles(user) {
  if (!user) return []
  if (Array.isArray(user.roles) && user.roles.length) return user.roles
  return user.role ? [user.role] : []
}

export function hasAppRole(user, allowedRoles) {
  const roles = getUserRoles(user)
  return roles.some((role) => allowedRoles.includes(role))
}

// ---------------------------------------------------------------------------
// P00-06 — capacités dérivées du backend (GET /auth/capabilities/).
// Le dictionnaire ci-dessous n'est que le REPLI statique, utilisé avant le
// chargement, hors-ligne ou si l'endpoint échoue : il doit rester strictement
// identique aux helpers de rôles existants (mêmes tableaux, même comportement).
// Quand les capacités backend sont présentes sur l'utilisateur, elles font
// autorité d'affichage. L'API garde quoi qu'il arrive le dernier mot.
// ---------------------------------------------------------------------------

/** Stats globales (toutes fédérations) — aligné GLOBAL_STATS_ROLES backend. */
export const GLOBAL_STATS_ROLES = [
  ...ADMIN_LEVEL_ROLES,
  'DIRECTION',
  'ARCHIVE',
  'FINANCE',
]

const FALLBACK_CAPACITES = {
  web: {
    acceder: ALLOWED_WEB_ROLES,
    operationnel: OPERATIONAL_WEB_ROLES,
  },
  utilisateurs: {
    voir: USERS_ALLOWED_ROLES,
    gerer: USER_MUTATION_ROLES,
  },
  participants: {
    lister: PARTICIPANT_LIST_ROLES,
    creer: PARTICIPANT_CREATE_ROLES,
    gerer: PARTICIPANT_MANAGE_ROLES,
  },
  modules: {
    archiver: MODULE_ARCHIVE_ROLES,
  },
  presences: {
    voir: PRESENCE_VIEW_ROLES,
    agir: PRESENCE_ACTION_ROLES,
    superviser: SUPERVISION_ROLES,
  },
  finance: {
    voir: FINANCE_MODULE_ROLES,
    exporter: FINANCE_EXPORT_ROLES,
    parametrer: FINANCE_SETTINGS_ROLES,
  },
  statistiques: {
    voir: STATS_ALLOWED_ROLES,
    voir_globales: GLOBAL_STATS_ROLES,
  },
  evaluations: {
    gerer_questionnaires: EVALUATION_ALLOWED_ROLES,
    consulter: ALLOWED_WEB_ROLES,
  },
  notes: {
    gerer: NOTE_GESTION_ROLES,
    valider_decisions: DECISION_ROLES,
  },
  scolarite: {
    voir: SCOLARITE_VIEW_ROLES,
    agir: SCOLARITE_MUTATION_ROLES,
  },
  exports: {
    liste_classe: LISTE_CLASSE_EXPORT_ROLES,
  },
  dashboard: {
    filtrer_secretariat: DASHBOARD_SECRETARIAT_FILTER_ROLES,
  },
}

/** Vrai si les capacités du backend sont présentes sur l'objet utilisateur. */
export function capacitesChargees(user) {
  return Boolean(user?.capabilities?.capacites && typeof user.capabilities.capacites === 'object')
}

/**
 * Autorisation d'afficher une action (module/action).
 * 1. capacités backend si chargées (source de vérité) ;
 * 2. repli statique sinon, avec le comportement historique exact.
 */
export function peut(user, module, action) {
  const caps = user?.capabilities?.capacites
  if (caps) {
    return Array.isArray(caps[module]) && caps[module].includes(action)
  }
  const roles = getUserRoles(user)
  const allowed = FALLBACK_CAPACITES[module]?.[action] || []
  return roles.some((role) => allowed.includes(role))
}

/**
 * Cœur des helpers `can*` : accepte soit une chaîne de rôle (repli statique
 * historique, y compris pour les appels existants en `user?.role`), soit un
 * objet utilisateur. Dans ce dernier cas, si les capacités backend sont
 * chargées, elles font autorité ; sinon le repli statique reste appliqué.
 */
export function autorise(cible, module, action) {
  if (cible && typeof cible === 'object' && capacitesChargees(cible)) {
    return peut(cible, module, action)
  }
  const roles =
    cible && typeof cible === 'object'
      ? getUserRoles(cible)
      : cible
        ? [cible]
        : []
  const allowed = FALLBACK_CAPACITES[module]?.[action] || []
  return roles.some((role) => allowed.includes(role))
}

/** Niveau N0–N4 effectif (backend) ; null tant que les capacités ne sont pas chargées. */
export function niveauAcces(user) {
  return user?.capabilities?.niveau ?? null
}

/** Périmètres effectifs (backend) ; null avant chargement. */
export function perimetresAcces(user) {
  return user?.capabilities?.perimetres ?? null
}
