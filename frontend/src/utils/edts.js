/**
 * Utilitaires du module GET-INJS (emplois du temps).
 *
 * Source unique de vérité pour les libellés français et les transformations
 * de grille — les pages Edts / AffectationNew / EdtNew ne doivent pas
 * réinventer ces mappages (l'audit du 2026-09-15 relevait des enums bruts
 * affichés à l'écran : « LUNDI 08:00:00 », « EN_VALIDATION », etc.).
 */

export const LIBELLES_JOURS = {
  LUNDI: 'Lundi',
  MARDI: 'Mardi',
  MERCREDI: 'Mercredi',
  JEUDI: 'Jeudi',
  VENDREDI: 'Vendredi',
  SAMEDI: 'Samedi',
  DIMANCHE: 'Dimanche',
}

export const JOURS_OUVRES = ['LUNDI', 'MARDI', 'MERCREDI', 'JEUDI', 'VENDREDI', 'SAMEDI']

export const LIBELLES_STATUTS = {
  BROUILLON: 'Brouillon',
  EN_VALIDATION: 'En validation',
  VALIDE: 'Validé',
  PUBLIE: 'Publié',
  ARCHIVE: 'Archivé',
}

export const COULEURS_STATUTS = {
  BROUILLON: 'text-bg-secondary',
  EN_VALIDATION: 'text-bg-warning',
  VALIDE: 'text-bg-info',
  PUBLIE: 'text-bg-success',
  ARCHIVE: 'text-bg-dark',
}

export const LIBELLES_NATURES = {
  COURS: 'Cours',
  TD: 'TD',
  TP: 'TP',
  EVALUATION: 'Évaluation',
  REMPLACEMENT: 'Remplacement',
  AUTRE: 'Autre',
}

export const COULEURS_NATURES = {
  COURS: 'text-bg-primary',
  TD: 'text-bg-info',
  TP: 'text-bg-success',
  EVALUATION: 'text-bg-danger',
  REMPLACEMENT: 'text-bg-warning',
  AUTRE: 'text-bg-secondary',
}

export const LIBELLES_CONFLITS = {
  HORAIRE_ENSEIGNANT: 'Chevauchement enseignant',
  HORAIRE_GROUPETUDIANT: 'Chevauchement groupe',
  HORAIRE_SALLE: 'Chevauchement salle',
  HORAIRE_MODULE: 'Chevauchement formation',
  MANUEL: 'Signalé manuellement',
}

/** Rôles habilités à valider/publier (miroir de edts.permissions.VALIDATION_ROLES). */
export const ROLES_VALIDATION = ['ADMIN', 'DIRECTION']

/** Rôles planificateurs (miroir de edts.permissions.PLANIFICATION_ROLES). */
export const ROLES_PLANIFICATION = [
  'ADMIN', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'SECRETARIAT',
  'CHEF_SECRETARIAT', 'DIRECTION', 'ENCADRANT',
]

/** '08:00:00' → '08:00' ; accepte déjà '08:00'. */
export function formatHeure(heure) {
  if (!heure) return ''
  const [h, m] = String(heure).split(':')
  return `${String(h).padStart(2, '0')}:${String(m ?? '00').padStart(2, '0')}`
}

export function libelleJour(jour) {
  return LIBELLES_JOURS[jour] || jour || ''
}

export function libelleStatut(statut) {
  return LIBELLES_STATUTS[statut] || statut || ''
}

export function classeBadgeStatut(statut) {
  return `badge ${COULEURS_STATUTS[statut] || 'text-bg-secondary'}`
}

export function formatDuree(minutes) {
  if (minutes == null) return ''
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (!h) return `${m} min`
  return m ? `${h} h ${String(m).padStart(2, '0')}` : `${h} h`
}

/**
 * Transforme la réponse de `GET /edts/emplois/<id>/grille/` en matrice
 * jours × créneaux prête à afficher, et marque les cellules dont une
 * affectation est impliquée dans un conflit actif.
 */
export function construireMatriceGrille(grilleApi, conflits = [], joursAttendus = JOURS_OUVRES) {
  const idsEnConflit = new Set()
  for (const conflit of conflits) {
    for (const id of conflit.lignes_creneaux || []) idsEnConflit.add(id)
  }
  const parJour = new Map((grilleApi?.jours || []).map((j) => [j.jour, j.creneaux]))
  return joursAttendus
    .map((jour) => {
      const lignes = (parJour.get(jour) || [])
        .slice()
        .sort((a, b) => String(a.heure_debut).localeCompare(String(b.heure_debut)))
        .map((c) => ({
          ...c,
          enConflit: (c.affectations || []).some((a) => idsEnConflit.has(a.id)),
        }))
      return { jour, libelle: libelleJour(jour), lignes }
    })
    .filter((j) => j.lignes.length > 0)
}

/** Extrait le message d'erreur lisible d'une réponse d'API (DRF ou vue custom). */
export function messageErreurApi(err, fallback = 'Erreur inattendue') {
  const data = err?.response?.data
  if (!data) return err?.message || fallback
  if (typeof data === 'string') return data
  if (data.detail) {
    return typeof data.detail === 'string' ? data.detail : data.detail.join(' ')
  }
  const premieres = Object.entries(data).slice(0, 3)
    .map(([champ, valeur]) => `${champ} : ${Array.isArray(valeur) ? valeur.join(', ') : valeur}`)
  return premieres.length ? premieres.join(' — ') : fallback
}

/** Extrait une réponse {affectation, avertissements_conflits} ou l'objet plat (compat). */
export function lireMutationAffectation(reponse) {
  const data = reponse?.data || {}
  return {
    affectation: data.affectation || data,
    avertissements: data.avertissements_conflits || [],
  }
}
