/**
 * Console CURP d'administration des comptes (unité U4, prompt C2).
 *
 * Toutes les routes sont gardées côté Django par le drapeau
 * ``flag.curp_ui_admin`` ET le trio d'administration ; ce module ne fait que
 * les appeler. La visibilité de l'interface dérive de la capacité
 * ``habilitations_admin.gerer`` servie par /api/auth/capabilities/ : aucune
 * liste de rôles n'est codée en dur dans l'interface.
 */
import api from './api'

const BASE = '/habilitations'

export const HAB_KEYS = {
  comptes: ['habilitations', 'comptes'],
  roles: ['habilitations', 'roles'],
  roleDetail: (code) => ['habilitations', 'roles', code],
  matrice: ['habilitations', 'matrice'],
  journal: ['habilitations', 'journal'],
  integrite: ['habilitations', 'journal', 'integrite'],
  derogations: ['habilitations', 'derogations'],
  delegations: ['habilitations', 'delegations'],
  revue: ['habilitations', 'revue'],
}

const urlParams = (filtres = {}) => {
  const params = new URLSearchParams()
  Object.entries(filtres).forEach(([cle, valeur]) => {
    if (valeur !== '' && valeur !== null && valeur !== undefined) {
      params.append(cle, valeur)
    }
  })
  const chaine = params.toString()
  return chaine ? `?${chaine}` : ''
}

// ── Comptes ────────────────────────────────────────────────────────────
export const listerComptes = (filtres) =>
  api.get(`${BASE}/comptes/${urlParams(filtres)}`).then((r) => r.data)

export const recupererCompte = (id) =>
  api.get(`${BASE}/comptes/${id}/`).then((r) => r.data)

export const creerCompte = (payload) =>
  api.post(`${BASE}/comptes/`, payload).then((r) => r.data)

export const simulerModification = (id, payload) =>
  api.post(`${BASE}/comptes/${id}/simuler-modification/`, payload).then((r) => r.data)

export const modifierCompte = (id, payload) =>
  api.patch(`${BASE}/comptes/${id}/modifier/`, payload).then((r) => r.data)

export const changerStatutCompte = (id, transition, motif) =>
  api.post(`${BASE}/comptes/${id}/statut/`, { transition, motif }).then((r) => r.data)

export const rechercherPersonnes = (q) =>
  api.get(`${BASE}/personnes/${urlParams({ q })}`).then((r) => r.data.resultats || [])

export const simulerImport = (lignes) =>
  api.post(`${BASE}/comptes/import-simuler/`, { lignes }).then((r) => r.data)

export const recupererRevue = () =>
  api.get(`${BASE}/comptes/revue/`).then((r) => r.data)

// ── Référentiel ─────────────────────────────────────────────────────────
export const listerRolesCurp = () =>
  api.get(`${BASE}/roles/`).then((r) => {
    const data = r.data
    return data.results || data
  })

/** Catalogue des permissions (pagination serveur, API U2 existante).
 *  Lot d'intégration : filtres serveur module/ressource/action/criticité/q
 *  et compteur réel de rôles octroyants (total_roles).
 */
export const listerPermissions = (params = {}) => {
  const query = typeof params === 'number' ? { page: params } : { page: 1, ...params }
  return api.get(`${BASE}/permissions/${urlParams(query)}`).then((r) => r.data)
}

export const recupererRole = (code) =>
  api.get(`${BASE}/roles/${encodeURIComponent(code)}/`).then((r) => r.data)

export const recupererMatrice = () =>
  api.get(`${BASE}/matrice/`).then((r) => r.data)

// ── Journal ─────────────────────────────────────────────────────────────
export const listerJournal = (filtres) =>
  api.get(`${BASE}/journal/${urlParams(filtres)}`).then((r) => r.data)

export const integriteJournal = () =>
  api.get(`${BASE}/journal/integrite/`).then((r) => r.data)

// ── Dérogations / délégations ───────────────────────────────────────────
export const listerDerogations = (filtres = {}) =>
  api.get(`${BASE}/derogations/${urlParams(filtres)}`).then((r) => r.data)

export const creerDerogation = (payload) =>
  api.post(`${BASE}/derogations/`, payload).then((r) => r.data)

export const revoquerDerogation = (id, motif) =>
  api.post(`${BASE}/derogations/${id}/revoquer/`, { motif }).then((r) => r.data)

export const listerDelegations = (filtres = {}) =>
  api.get(`${BASE}/delegations/${urlParams(filtres)}`).then((r) => r.data)

export const creerDelegation = (payload) =>
  api.post(`${BASE}/delegations/`, payload).then((r) => r.data)

export const terminerDelegation = (id, motif) =>
  api.post(`${BASE}/delegations/${id}/terminer/`, { motif }).then((r) => r.data)

// ── U5 : cycle de vie, file de provisionnement, imports écrits ──────────
export const listerPropositions = (filtres = {}) =>
  api.get(`${BASE}/propositions/${urlParams(filtres)}`).then((r) => r.data)

export const approuverProposition = (id, motif, ajustements) =>
  api
    .post(`${BASE}/propositions/${id}/approuver/`, { motif, ajustements })
    .then((r) => r.data)

export const rejeterProposition = (id, motif) =>
  api.post(`${BASE}/propositions/${id}/rejeter/`, { motif }).then((r) => r.data)

export const scannerProvisions = (declencheurs) =>
  api
    .post(`${BASE}/provisions/scanner/`, { declencheurs })
    .then((r) => r.data)

export const executerImport = (lignes, nomFichier = '') =>
  api
    .post(`${BASE}/comptes/imports/`, { lignes, nom_fichier: nomFichier })
    .then((r) => r.data)

export const recupererImport = (reference) =>
  api
    .get(`${BASE}/comptes/imports/${encodeURIComponent(reference)}/`)
    .then((r) => r.data)

export const annulerImport = (reference, motif) =>
  api
    .post(`${BASE}/comptes/imports/${encodeURIComponent(reference)}/annuler/`, {
      motif,
    })
    .then((r) => r.data)

export const listerNotifications = (filtres = {}) =>
  api.get(`${BASE}/notifications/${urlParams(filtres)}`).then((r) => r.data)

export const lireNotification = (id) =>
  api.post(`${BASE}/notifications/${id}/lire/`).then((r) => r.data)

export const toutLireNotifications = () =>
  api.post(`${BASE}/notifications/tout-lire/`).then((r) => r.data)

export const activerDelegation = (id, motif) =>
  api
    .post(`${BASE}/delegations/${id}/activer/`, { motif })
    .then((r) => r.data)

export const actionParDelegation = (id, action, detail) =>
  api
    .post(`${BASE}/delegations/${id}/action/`, { action, detail })
    .then((r) => r.data)

// ── LOT 3 : organisation administrative ───────────────────────────────
export const ORG_KEYS = {
  directions: ['habilitations', 'organisation', 'directions'],
  departements: ['habilitations', 'organisation', 'departements'],
  services: ['habilitations', 'organisation', 'services'],
}

export const listerDirections = () =>
  api.get(`${BASE}/organisation/directions/`).then((r) => r.data.results)

export const creerDirection = (payload) =>
  api.post(`${BASE}/organisation/directions/`, payload).then((r) => r.data)

export const modifierDirection = (id, payload) =>
  api.patch(`${BASE}/organisation/directions/${id}/`, payload).then((r) => r.data)

export const listerDepartements = (filtres = {}) =>
  api.get(`${BASE}/organisation/departements/${urlParams(filtres)}`).then((r) => r.data.results)

export const creerDepartement = (payload) =>
  api.post(`${BASE}/organisation/departements/`, payload).then((r) => r.data)

export const modifierDepartement = (id, payload) =>
  api.patch(`${BASE}/organisation/departements/${id}/`, payload).then((r) => r.data)

export const recupererDepartement = (id) =>
  api.get(`${BASE}/organisation/departements/${id}/`).then((r) => r.data)

export const rattacherCompteDepartement = (id, compteId) =>
  api.post(`${BASE}/organisation/departements/${id}/comptes/`, { compte_id: compteId }).then((r) => r.data)

export const detacherCompteDepartement = (id, compteId) =>
  api.delete(`${BASE}/organisation/departements/${id}/comptes/`, { data: { compte_id: compteId } }).then((r) => r.data)

export const listerServicesOrganisation = (filtres = {}) =>
  api.get(`${BASE}/organisation/services/${urlParams(filtres)}`).then((r) => r.data.results)

export const creerServiceOrganisation = (payload) =>
  api.post(`${BASE}/organisation/services/`, payload).then((r) => r.data)

export const modifierServiceOrganisation = (id, payload) =>
  api.patch(`${BASE}/organisation/services/${id}/`, payload).then((r) => r.data)

export const recupererServiceOrganisation = (id) =>
  api.get(`${BASE}/organisation/services/${id}/`).then((r) => r.data)

export const rattacherCompteService = (id, compteId) =>
  api.post(`${BASE}/organisation/services/${id}/comptes/`, { compte_id: compteId }).then((r) => r.data)

export const detacherCompteService = (id, compteId) =>
  api.delete(`${BASE}/organisation/services/${id}/comptes/`, { data: { compte_id: compteId } }).then((r) => r.data)

export const permissionsEffectives = (id) =>
  api.get(`${BASE}/comptes/${id}/effective-permissions/`).then((r) => r.data)

// ── Lot B : versions, comparaison et restauration des rôles ────────────
export const listerVersionsRole = (code) =>
  api.get(`${BASE}/roles/${encodeURIComponent(code)}/versions/`).then((r) => r.data)

export const capturerVersionRole = (code, motif) =>
  api.post(`${BASE}/roles/${encodeURIComponent(code)}/versions/`, { motif })
    .then((r) => r.data)

export const restaurerVersionRole = (code, numero, motif) =>
  api.post(
    `${BASE}/roles/${encodeURIComponent(code)}/versions/${numero}/restaurer/`,
    { motif },
  ).then((r) => r.data)

export const comparerRoles = (code, params) => {
  const query = params.avec
    ? `avec=${encodeURIComponent(params.avec)}`
    : `de=${params.de}&vers=${params.vers}`
  return api.get(
    `${BASE}/roles/${encodeURIComponent(code)}/comparer/?${query}`,
  ).then((r) => r.data)
}

// ── Lot C : demandes d'accès ────────────────────────────────────────────
export const listerDemandesAcces = (filtres = {}) =>
  api.get(`${BASE}/demandes/${urlParams(filtres)}`).then((r) => r.data)

export const creerDemandeAcces = (payload) =>
  api.post(`${BASE}/demandes/`, payload).then((r) => r.data)

export const actionDemandeAcces = (id, action, motif_decision = '') =>
  api.post(`${BASE}/demandes/${id}/action/`, { action, motif_decision })
    .then((r) => r.data)

// ── Couche IMPACT (additive) : endpoints impact/dashboard, garde identique
// à la console (drapeau + trio d'administration côté Django). ─────────────
export const impactModule = (code) =>
  api.get(`${BASE}/impact/module/${encodeURIComponent(code)}/`).then((r) => r.data)

export const impactPermission = (code) =>
  api.get(`${BASE}/impact/permission/${encodeURIComponent(code)}/`).then((r) => r.data)

export const impactRole = (code) =>
  api.get(`${BASE}/impact/role/${encodeURIComponent(code)}/`).then((r) => r.data)

export const impactUtilisateur = (user_id) =>
  api.get(`${BASE}/impact/utilisateur/${user_id}/`).then((r) => r.data)

export const dashboardHabilitations = () =>
  api.get(`${BASE}/dashboard/`).then((r) => r.data)

/** Extrait le message français d'une erreur DRF (403, 409, 400). */
export function messageErreur(erreur, repli = 'Une erreur est survenue.') {
  const data = erreur?.response?.data
  if (data?.detail) return data.detail
  if (data && typeof data === 'object') {
    const champs = Object.entries(data)
      .map(([champ, valeur]) => {
        const texte = Array.isArray(valeur) ? valeur.join(' ') : String(valeur)
        return champ === 'non_field_errors' ? texte : `${champ} : ${texte}`
      })
      .join(' — ')
    if (champs) return champs
  }
  return repli
}
