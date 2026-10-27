/**
 * Stockage Web résilient (aperçu intégré).
 *
 * Dans l'aperçu Arena, l'application tourne dans une iframe tierce
 * (*.e2b.app intégrée par *.arena.site) : certains navigateurs bloquent alors
 * l'accès à localStorage/sessionStorage (SecurityError — Safari, réglages
 * « bloquer les cookies tiers », navigation privée renforcée). Sans repli,
 * la connexion échouait APRÈS le 200 de l'API au moment d'écrire le jeton.
 *
 * Ce module choisit UNE fois par page le meilleur stockage disponible
 * (localStorage → sessionStorage → mémoire) pour rester cohérent entre
 * lectures et écritures ; chaque opération reste protégée (quota dépassé,
 * stockage vidé en cours de session → repli mémoire).
 */

const CLE_SONDE = '__injs_probe_storage__'
const MEMOIRE = new Map()
let _stockage = undefined // undefined = pas encore résolu ; null = mémoire

function resoudreStockage() {
  if (_stockage !== undefined) return _stockage
  for (const candidat of [window.localStorage, window.sessionStorage]) {
    try {
      candidat.setItem(CLE_SONDE, '1')
      candidat.removeItem(CLE_SONDE)
      _stockage = candidat
      return _stockage
    } catch {
      // Stockage inaccessible (SecurityError / QuotaExceededError) → suivant.
    }
  }
  // Repli ultime : mémoire de la page courante (la session ne survit pas à un
  // rechargement, l'utilisateur se reconnecte — comportement dégradé assumé).
  _stockage = null
  return _stockage
}

export const safeLocalStorage = {
  getItem(cle) {
    const stockage = resoudreStockage()
    if (stockage) {
      try {
        return stockage.getItem(cle)
      } catch {
        // Lecture impossible → tenter la mémoire (peut contenir une écriture
        // de secours posée après une panne du stockage).
      }
    }
    return MEMOIRE.has(cle) ? MEMOIRE.get(cle) : null
  },

  setItem(cle, valeur) {
    const stockage = resoudreStockage()
    if (stockage) {
      try {
        stockage.setItem(cle, String(valeur))
        return
      } catch {
        // Écriture impossible → conserver au moins en mémoire.
      }
    }
    MEMOIRE.set(cle, String(valeur))
  },

  removeItem(cle) {
    const stockage = resoudreStockage()
    if (stockage) {
      try {
        stockage.removeItem(cle)
      } catch {
        // Déjà hors service → purge mémoire ci-dessous.
      }
    }
    MEMOIRE.delete(cle)
  },
}

export default safeLocalStorage
