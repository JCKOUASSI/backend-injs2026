/**
 * Année académique « courante » calculée à partir de la date.
 *
 * Une année académique démarre en septembre : du 1er septembre au 31 août,
 * la période affichée est « N-(N+1) ». Cette règle évite les libellés figés
 * dans le code (l'écran de connexion annonçait encore « 2025-2026 » alors que
 * l'application était réglée sur 2026-2027).
 */

const MOIS_DE_RENTREE = 8 // septembre (index 0)

/** Année académique au format `AAAA-AAAA`, ex. `2026-2027`. */
export function anneeAcademiqueCourante(date = new Date()) {
  const annee = date.getFullYear()
  const debut = date.getMonth() >= MOIS_DE_RENTREE ? annee : annee - 1
  return `${debut}-${debut + 1}`
}

/** Même valeur avec le tiret demi-cadratin utilisé par les en-têtes (`2026–2027`). */
export function anneeAcademiqueAffichee(date = new Date()) {
  return anneeAcademiqueCourante(date).replace('-', '–')
}

/**
 * Année académique précédente (`2025-2026` quand la courante est `2026-2027`).
 * Sert aux libellés de comparaison des indicateurs (« vs … ») : figés dans le
 * code, ils devenaient faux dès le changement d'année.
 */
export function anneeAcademiquePrecedente(date = new Date(), avecTiret = false) {
  const [debut] = anneeAcademiqueCourante(date).split('-')
  const precedente = `${Number(debut) - 1}-${debut}`
  return avecTiret ? precedente.replace('-', '–') : precedente
}
