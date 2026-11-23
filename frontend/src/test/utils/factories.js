/**
 * Fabriques d'objets réalistes pour les tests.
 * Les 12 rôles métier sont alignés sur backend/authentication/models.py
 * et frontend/src/utils/roles.js.
 */

export const ALL_ROLES = [
  'ADMIN',
  'DIRECTION',
  'CHEF_INJS_ADMIN',
  'INJS_ADMIN',
  'CHEF_SECRETARIAT',
  'SECRETARIAT',
  'FINANCE',
  'ARCHIVE',
  'ENCADRANT',
  'SUPERVISEUR',
  'FORMATEUR',
  'AUDITEUR',
]

export const ROLE_LABELS = {
  ADMIN: 'Administrateur',
  DIRECTION: 'Direction',
  CHEF_INJS_ADMIN: 'Chef INJS Admin',
  INJS_ADMIN: 'INJS Admin',
  CHEF_SECRETARIAT: 'Chef Secrétariat',
  SECRETARIAT: 'Secrétariat',
  FINANCE: 'Finance',
  ARCHIVE: 'Archiviste',
  ENCADRANT: 'Encadrant',
  SUPERVISEUR: 'Superviseur',
  FORMATEUR: 'Formateur',
  AUDITEUR: 'Étudiant',
}

/** Rôles qui ne doivent PAS pouvoir se connecter à la plateforme web. */
export const WEB_FORBIDDEN_ROLES = ['FORMATEUR', 'AUDITEUR']

let seq = 0

export function makeUser(role = 'ADMIN', overrides = {}) {
  seq += 1
  const username = overrides.username || `${role.toLowerCase()}${seq}`
  const id = overrides.id ?? seq
  return {
    id,
    pk: id,
    username,
    first_name: ROLE_LABELS[role] || 'Prénom',
    last_name: 'Test',
    email: `${username}@injs.test`,
    role,
    roles: undefined,
    is_active: true,
    is_staff: ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN'].includes(role),
    secretariat: null,
    role_context: {},
    ...overrides,
  }
}

/** Un utilisateur par rôle, indexé par clé de rôle. */
export function makeUsersForAllRoles(overridesByRole = {}) {
  return ALL_ROLES.map((role) => makeUser(role, overridesByRole[role] || {}))
}

/** Réponse POST /auth/login/ telle que renvoyée par le backend. */
export function makeLoginResponse(user, { refreshInCookie = true, refresh = 'refresh.jwt', access = 'access.jwt' } = {}) {
  return {
    access,
    refresh: refreshInCookie ? undefined : refresh,
    refresh_in_cookie: refreshInCookie,
    // Présent en tête et dans le profil utilisateur, comme la vue de login
    // réelle (UserSerializer) ; le garde de changement obligatoire (§10.1)
    // lit user.must_change_password juste après la connexion.
    must_change_password: user.must_change_password ?? false,
    user: {
      id: user.id,
      username: user.username,
      first_name: user.first_name,
      last_name: user.last_name,
      email: user.email,
      role: user.role,
      secretariat: user.secretariat ?? null,
      must_change_password: user.must_change_password ?? false,
    },
    role_context: user.role_context || {},
  }
}

/** Jeu paginé typique DRF. */
export function paginated(results, page = 1, pageSize = 25) {
  const count = results.length
  return {
    count,
    next: page * pageSize < count ? 'http://testserver/?page=' + (page + 1) : null,
    previous: page > 1 ? 'http://testserver/?page=' + (page - 1) : null,
    results,
  }
}
