/**
 * Fixtures numériques pour les écrans qui consomment les statistiques du
 * tableau de bord. Le mock « vide » générique (`safeData`) renvoie des
 * tableaux pour toutes les propriétés, ce qui casse les `.toFixed()` et
 * totaux du Dashboard : on fournit donc un objet 100 % chiffré.
 */

const NUMERIC_KEYS = [
  'retard_moyen_minutes', 'auditeurs_attendus_jour', 'auditeurs_presents_jour',
  'en_salle_now', 'formateurs_attendus_jour', 'formateurs_presents_jour',
  'modules_en_cours', 'modules_planifies', 'modules_termines',
  'pointages_aujourd_hui', 'presents_annee', 'presents_aujourd_hui',
  'presents_mois', 'presents_semaine', 'seances_actives',
  'seances_planifiees_aujourd_hui', 'taux_presence', 'taux_presence_annee',
  'taux_presence_mois', 'taux_presence_semaine', 'total_attendus_annee',
  'total_attendus_jour', 'total_attendus_mois', 'total_attendus_semaine',
  'total_modules', 'total_participants', 'volume_horaire_effectue_heures',
  'volume_horaire_effectue_taux', 'volume_horaire_total_heures',
]

/** Statistiques toutes à zéro (montage sans erreur). `overrides` est fusionné. */
export function dashboardStats(overrides = {}) {
  const stats = {
    periode: 'jour',
    derniers_pointages: [],
    prochaines_seances: [],
  }
  for (const k of NUMERIC_KEYS) stats[k] = 0
  return { ...stats, ...overrides }
}

/**
 * Statistiques avec des valeurs DISTINCTES par période, pour vérifier que le
 * sélecteur Jour / Semaine / Mois / Année change bien les chiffres affichés.
 */
export function dashboardStatsWithPeriods() {
  return dashboardStats({
    total_attendus_jour: 100, presents_aujourd_hui: 80, taux_presence: 80,
    auditeurs_attendus_jour: 90, auditeurs_presents_jour: 70,
    total_attendus_semaine: 500, presents_semaine: 450, taux_presence_semaine: 90,
    total_attendus_mois: 2000, presents_mois: 1700, taux_presence_mois: 85,
    total_attendus_annee: 20000, presents_annee: 18000, taux_presence_annee: 90,
  })
}
