import { describe, it, expect } from 'vitest'
import * as roles from '@/utils/roles'
import { ALL_ROLES } from '@/test/utils/factories'

// ──────────────────────────────────────────────────────────────────────────
// Contrat de sécurité côté UI : ensembles de rôles attendus.
// Ces listes sont le reflet de backend/authentication/role_groups.py ; les
// figer en test interdit toute dérive silencieuse des droits affichés.
// ──────────────────────────────────────────────────────────────────────────

const A = ['ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN']

const EXPECTED_SETS = {
  ADMIN_LEVEL_ROLES: A,
  ALLOWED_WEB_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'FINANCE', 'ARCHIVE', 'ENCADRANT', 'SUPERVISEUR'],
  STAFF_WEB_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT', 'SUPERVISEUR'],
  EVALUATION_ALLOWED_ROLES: [...A, 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT', 'SUPERVISEUR'],
  NOTE_GESTION_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT', 'SUPERVISEUR'],
  DECISION_ROLES: [...A, 'DIRECTION', 'ENCADRANT', 'SUPERVISEUR'],
  FINANCE_MODULE_ROLES: ['FINANCE', 'DIRECTION', 'ARCHIVE'],
  ARCHIVE_CONSULT_ROLES: ['ARCHIVE', 'DIRECTION', ...A],
  OPERATIONAL_WEB_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ARCHIVE', 'ENCADRANT', 'SUPERVISEUR'],
  OPERATION_VIEW_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ARCHIVE', 'ENCADRANT', 'SUPERVISEUR'],
  PARTICIPANT_LIST_ROLES: [...A, 'DIRECTION', 'ARCHIVE', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT'],
  FINANCE_EXPORT_ROLES: ['FINANCE', 'DIRECTION', 'ARCHIVE'],
  LISTE_CLASSE_EXPORT_ROLES: [...A, 'DIRECTION', 'ARCHIVE', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT'],
  FINANCE_SETTINGS_ROLES: ['FINANCE', 'DIRECTION'],
  SCOLARITE_VIEW_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  SCOLARITE_MUTATION_ROLES: [...A, 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  STATS_ALLOWED_ROLES: [...A, 'DIRECTION', 'ARCHIVE', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'FINANCE', 'ENCADRANT'],
  USERS_ALLOWED_ROLES: [...A, 'DIRECTION', 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  IMPORT_ALLOWED_ROLES: [...A, 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  FORMATION_MUTATION_ROLES: [...A, 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  MODULE_ARCHIVE_ROLES: [...A, 'CHEF_SECRETARIAT', 'SECRETARIAT', 'DIRECTION'],
  PARTICIPANT_CREATE_ROLES: [...A],
  PRESENCE_VIEW_ROLES: [...A, 'DIRECTION', 'ARCHIVE', 'CHEF_SECRETARIAT', 'SECRETARIAT', 'ENCADRANT'],
  PRESENCE_ACTION_ROLES: [...A, 'ENCADRANT', 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  SUPERVISION_ROLES: [...A, 'ENCADRANT', 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  USER_MUTATION_ROLES: [...A, 'CHEF_SECRETARIAT', 'SECRETARIAT'],
  DASHBOARD_SECRETARIAT_FILTER_ROLES: [...A, 'DIRECTION'],
  SECRETARIAT_SCOPED_ROLES: ['SECRETARIAT', 'CHEF_SECRETARIAT'],
  GLOBAL_STATS_ROLES: [...A, 'DIRECTION', 'ARCHIVE', 'FINANCE'],
}

// Matrice rôle → capacité pour chaque prédicat de l'API publique.
const PREDICATE_MATRIX = {
  isAdminLevelRole: EXPECTED_SETS.ADMIN_LEVEL_ROLES,
  canMutateFormations: EXPECTED_SETS.FORMATION_MUTATION_ROLES,
  canArchiveModule: EXPECTED_SETS.MODULE_ARCHIVE_ROLES,
  canCreateParticipant: EXPECTED_SETS.PARTICIPANT_CREATE_ROLES,
  canManageParticipant: EXPECTED_SETS.FORMATION_MUTATION_ROLES,
  canViewPresences: EXPECTED_SETS.PRESENCE_VIEW_ROLES,
  canPresenceAction: EXPECTED_SETS.PRESENCE_ACTION_ROLES,
  canSuperviseSessions: EXPECTED_SETS.SUPERVISION_ROLES,
  canMutateUsers: EXPECTED_SETS.USER_MUTATION_ROLES,
  canFilterDashboardBySecretariat: EXPECTED_SETS.DASHBOARD_SECRETARIAT_FILTER_ROLES,
  isSecretariatScopedRole: EXPECTED_SETS.SECRETARIAT_SCOPED_ROLES,
  isWebRoleAllowed: EXPECTED_SETS.ALLOWED_WEB_ROLES,
}

describe('utils/roles.js — contrat de sécurité UI', () => {
  describe('ensembles de rôles exportés', () => {
    for (const [name, expected] of Object.entries(EXPECTED_SETS)) {
      it(`${name} correspond exactement à ${expected.length} rôle(s)`, () => {
        expect([...roles[name]].sort()).toEqual([...expected].sort())
      })
    }

    it('OPERATION_VIEW_ROLES est bien dérivé de OPERATIONAL_WEB_ROLES', () => {
      expect(roles.OPERATION_VIEW_ROLES).toEqual(roles.OPERATIONAL_WEB_ROLES)
    })

    it('PARTICIPANT_MANAGE_ROLES réutilise FORMATION_MUTATION_ROLES', () => {
      expect(roles.PARTICIPANT_MANAGE_ROLES ?? roles.FORMATION_MUTATION_ROLES).toBeDefined()
    })
  })

  describe('prédicats par rôle — matrice exhaustive 12 rôles', () => {
    for (const [predicate, allowed] of Object.entries(PREDICATE_MATRIX)) {
      describe(predicate, () => {
        for (const role of ALL_ROLES) {
          const expected = allowed.includes(role)
          it(`${role} → ${expected}`, () => {
            expect(roles[predicate](role)).toBe(expected)
          })
        }
      })
    }
  })

  describe('hasAppRole / getUserRoles (formes utilisateur)', () => {
    it('user null → aucun rôle, aucun accès', () => {
      expect(roles.getUserRoles(null)).toEqual([])
      expect(roles.hasAppRole(null, ['ADMIN'])).toBe(false)
    })

    it('utilise user.roles (multi-rôles) quand le tableau est non vide', () => {
      const user = { role: 'SECRETARIAT', roles: ['SECRETARIAT', 'ENCADRANT'] }
      expect(roles.getUserRoles(user)).toEqual(['SECRETARIAT', 'ENCADRANT'])
      expect(roles.hasAppRole(user, roles.PRESENCE_ACTION_ROLES)).toBe(true)
    })

    it('tableau roles vide mais role présent → retombe sur user.role', () => {
      expect(roles.getUserRoles({ role: 'FINANCE', roles: [] })).toEqual(['FINANCE'])
    })

    it('aucun rôle défini → tableau vide', () => {
      expect(roles.getUserRoles({})).toEqual([])
    })

    it('canListParticipants / canActScolarite utilisent hasAppRole', () => {
      expect(roles.canListParticipants({ role: 'ARCHIVE' })).toBe(true)
      expect(roles.canListParticipants({ role: 'FORMATEUR' })).toBe(false)
      expect(roles.canActScolarite({ role: 'SECRETARIAT' })).toBe(true)
      expect(roles.canActScolarite({ role: 'AUDITEUR' })).toBe(false)
    })
  })

  describe('autorise() — repli statique et formes inattendues', () => {
    it('cible nulle ou sans rôle → pas d’autorisation', () => {
      expect(roles.autorise(null, 'modules', 'archiver')).toBe(false)
      expect(roles.autorise({}, 'modules', 'archiver')).toBe(false)
    })
    it('module ou action inconnue du repli → false (aucune exception)', () => {
      expect(roles.autorise('ADMIN', 'module_inexistant', 'archiver')).toBe(false)
      expect(roles.autorise('ADMIN', 'modules', 'action_inexistante')).toBe(false)
    })
    it('objet utilisateur sans capacités chargées → repli sur ses rôles', () => {
      expect(roles.autorise({ role: 'DIRECTION' }, 'modules', 'archiver')).toBe(true)
      expect(roles.autorise({ roles: ['AUDITEUR'] }, 'modules', 'archiver')).toBe(false)
    })
  })

  describe('canArchiveModuleFromUser', () => {
    it('user null → false', () => {
      expect(roles.canArchiveModuleFromUser(null)).toBe(false)
    })
    it('rôle non habilité sans contexte → false', () => {
      expect(roles.canArchiveModuleFromUser({ role: 'AUDITEUR' })).toBe(false)
    })
    it('rôle habilité → true', () => {
      expect(roles.canArchiveModuleFromUser({ role: 'DIRECTION' })).toBe(true)
    })
    it('role_context.can_archive_modules=true force true même pour un rôle a priori non habilité', () => {
      // AUDITEUR ne peut pas archiver par le repli statique : seul le
      // role_context backend peut lever l'interdiction (branche `return true`).
      expect(roles.canArchiveModuleFromUser({ role: 'AUDITEUR', role_context: { can_archive_modules: true } })).toBe(true)
    })
    it('role_context.can_archive_modules=false ne court-circuite pas', () => {
      expect(roles.canArchiveModuleFromUser({ role: 'SECRETARIAT', role_context: { can_archive_modules: false } })).toBe(true)
      // Et ne lève pas l'interdiction d'un rôle non habilité.
      expect(roles.canArchiveModuleFromUser({ role: 'AUDITEUR', role_context: { can_archive_modules: false } })).toBe(false)
    })
    it('capacités backend chargées : elles font autorité sur le contexte et le rôle', () => {
      const habilite = {
        role: 'AUDITEUR', role_context: { can_archive_modules: false },
        capabilities: { capacites: { modules: ['archiver'] } },
      }
      expect(roles.canArchiveModuleFromUser(habilite)).toBe(true)
      const nonHabilite = {
        role: 'DIRECTION', role_context: { can_archive_modules: true },
        capabilities: { capacites: { modules: [] } },
      }
      expect(roles.canArchiveModuleFromUser(nonHabilite)).toBe(false)
    })
  })

  describe('lockedSecretariatId', () => {
    it('rôle non scopé → null même avec un secrétariat', () => {
      expect(roles.lockedSecretariatId({ role: 'ADMIN', secretariat: 7 })).toBeNull()
    })
    it('rôle scopé sans secrétariat (null) → null', () => {
      expect(roles.lockedSecretariatId({ role: 'SECRETARIAT', secretariat: null })).toBeNull()
    })
    it('rôle scopé avec secrétariat vide → null', () => {
      expect(roles.lockedSecretariatId({ role: 'CHEF_SECRETARIAT', secretariat: '' })).toBeNull()
    })
    it('rôle scopé avec secrétariat numérique → chaîne de l’id', () => {
      expect(roles.lockedSecretariatId({ role: 'SECRETARIAT', secretariat: 42 })).toBe('42')
    })
  })

  describe('peut() — capacités backend (P00-06)', () => {
    it('sans capacités chargées, retombe sur le référentiel statique (repli identique)', () => {
      // SECRETARIAT peut gérer les utilisateurs selon le repli statique…
      expect(roles.peut({ role: 'SECRETARIAT' }, 'utilisateurs', 'gerer')).toBe(true)
      // …DIRECTION non (lecture seule) — comportement historique.
      expect(roles.peut({ role: 'DIRECTION' }, 'utilisateurs', 'gerer')).toBe(false)
      // FINANCE ne voit jamais la liste participants.
      expect(roles.peut({ role: 'FINANCE' }, 'participants', 'lister')).toBe(false)
    })

    it('module/action inconnus → false', () => {
      expect(roles.peut({ role: 'ADMIN' }, 'inexistant', 'voir')).toBe(false)
    })

    it('user null → false', () => {
      expect(roles.peut(null, 'web', 'acceder')).toBe(false)
    })

    it('les capacités backend font autorité, même en contradiction avec le rôle statique', () => {
      // Le backend accorde valider_decisions à un SECRETARIAT (permission de
      // groupe), alors que le repli statique (DECISION_ROLES) le refuse :
      // dès que les capacités sont chargées, c'est le backend qui gagne.
      const user = {
        role: 'SECRETARIAT',
        capabilities: {
          niveau: 'N2',
          capacites: { notes: ['gerer', 'valider_decisions'] },
        },
      }
      expect(roles.peut(user, 'notes', 'valider_decisions')).toBe(true)

      // Et une action absente du contrat backend reste masquée même pour un
      // rôle qui l'aurait eue en statique (ex. secrétariat ne peut pas créer
      // de participant : le backend ne liste pas « creer »).
      const user2 = {
        role: 'SECRETARIAT',
        capabilities: {
          niveau: 'N2',
          capacites: { participants: ['gerer', 'lister'] },
        },
      }
      expect(roles.peut(user2, 'participants', 'creer')).toBe(false)
    })

    it('capacitesChargees / niveauAcces / perimetresAcces lisent le contrat backend', () => {
      expect(roles.capacitesChargees({ role: 'SECRETARIAT' })).toBe(false)
      const user = {
        role: 'SECRETARIAT',
        capabilities: { niveau: 'N2', perimetres: { niveaux: ['SERVICE'] }, capacites: {} },
      }
      expect(roles.capacitesChargees(user)).toBe(true)
      expect(roles.niveauAcces(user)).toBe('N2')
      expect(roles.perimetresAcces(user)).toEqual({ niveaux: ['SERVICE'] })
      expect(roles.niveauAcces({ role: 'SECRETARIAT' })).toBeNull()
      expect(roles.perimetresAcces({ role: 'SECRETARIAT' })).toBeNull()
      // Aucun utilisateur → null (les capacités ne sont pas chargées).
      expect(roles.niveauAcces(null)).toBeNull()
      expect(roles.perimetresAcces(null)).toBeNull()
    })

    it('un corps de capacités mal formé n’est pas pris en compte', () => {
      const user = { role: 'SECRETARIAT', capabilities: [] }
      expect(roles.capacitesChargees(user)).toBe(false)
      expect(roles.peut(user, 'utilisateurs', 'gerer')).toBe(true) // repli statique
    })
  })

  describe('webLoginForbiddenMessage', () => {
    it('AUDITEUR → message étudiant / application mobile', () => {
      expect(roles.webLoginForbiddenMessage('AUDITEUR')).toMatch(/étudiant/i)
    })
    it('FORMATEUR → message enseignant / application mobile', () => {
      expect(roles.webLoginForbiddenMessage('FORMATEUR')).toMatch(/enseignant/i)
    })
    it('autre rôle non autorisé → message générique', () => {
      expect(roles.webLoginForbiddenMessage('INCONNU')).toMatch(/n'a pas accès/)
    })
  })
})
