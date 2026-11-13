/**
 * Téléchargement d'un fichier reçu de l'API — un seul point de vérité.
 *
 * Avant ce module, 28 endroits de l'application recopiaient le même bloc
 * `createObjectURL` / `<a download>` / `click()` / `revokeObjectURL`. Deux
 * défauts étaient ainsi dupliqués partout :
 *
 * 1. **`revokeObjectURL` appelé juste après `click()`** — la révocation
 *    intervenait avant que le navigateur ait réellement démarré le
 *    téléchargement, ce qui peut l'annuler (comportement observé sur
 *    Safari et Firefox). La révocation est donc différée d'un tour
 *    d'horloge, après que le clic a été traité.
 * 2. **Aucune vérification du type** : si l'API renvoyait une erreur JSON
 *    au lieu d'un fichier, on téléchargeait un document corrompu sans
 *    rien signaler. Le type est donc contrôlé ici aussi.
 *
 * Le téléchargement reste une opération du navigateur : aucun texte n'est
 * fabriqué côté client, le serveur produit toujours le document.
 */

/** Délai de révocation de l'URL : laisse au navigateur le temps de démarrer. */
const DELAI_REVOCATION_MS = 60_000

/**
 * Vrai si le blob est un document, et non une réponse d'erreur.
 *
 * Seuls le JSON et le HTML sont écartés : ce sont les deux formes que prend
 * une erreur d'export. Un type absent ou inconnu n'est **pas** bloquant —
 * mieux vaut laisser le navigateur tenter le téléchargement que refuser un
 * document valide dont le serveur n'a pas déclaré le type.
 */
export function estUnDocument(blob, contentType = '') {
  if (blob == null) return false
  const type = (contentType || blob.type || '').split(';')[0].trim().toLowerCase()
  if (!type) return true
  return type !== 'application/json' && type !== 'text/html'
}

/**
 * Déclenche le téléchargement d'un blob sous le nom fourni.
 *
 * @param {Blob} blob contenu binaire reçu de l'API
 * @param {string} nomFichier nom proposé au navigateur (extension incluse)
 * @param {object} [options]
 * @param {string} [options.contentType] type MIME renvoyé par le serveur
 * @param {AbortSignal} [options.signal] annulation éventuelle
 * @returns {string} le nom de fichier utilisé
 */
export function telechargerBlob(blob, nomFichier, options = {}) {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return nomFichier
  }
  if (!estUnDocument(blob, options.contentType)) {
    const erreur = new Error('Réponse inattendue du serveur : aucun document à télécharger.')
    erreur.corrompu = true
    throw erreur
  }

  const nom = nomFichier || 'export'
  const url = window.URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nom
  lien.rel = 'noopener'
  // Sorti du flux mais **rendu** : Firefox et Safari n'honorent pas
  // toujours le clic sur un élément en `display: none`. On le décale hors
  // écran plutôt que de le masquer.
  lien.style.position = 'fixed'
  lien.style.top = '-1000px'
  lien.style.left = '-1000px'
  lien.style.opacity = '0'
  document.body.appendChild(lien)
  try {
    lien.click()
  } finally {
    lien.remove()
  }

  // Repli pour les aperçus intégrés : dans une iframe, le navigateur peut
  // bloquer silencieusement un téléchargement (sandbox sans
  // `allow-downloads`). On ouvre alors aussi le document dans un onglet de
  // premier niveau, qui n'est pas soumis à la même restriction. L'URL du
  // blob reste valable le temps du délai de révocation ci-dessous.
  const ongletOuvert = ouvrirDansUnOnglet(url)

  // Révocation différée : révoquer immédiatement peut annuler un
  // téléchargement qui n'a pas encore démarré, et viderait l'onglet ouvert.
  const revoquer = () => window.URL.revokeObjectURL(url)
  if (options.signal) {
    if (options.signal.aborted) revoquer()
    else options.signal.addEventListener('abort', revoquer, { once: true })
  }
  window.setTimeout(revoquer, DELAI_REVOCATION_MS)

  if (typeof options.onDiagnostic === 'function') {
    options.onDiagnostic({ nom, url, ongletOuvert, dansUneIframe: dansUneIframe() })
  }
  return nom
}

/** Vrai si la page est affichée à l'intérieur d'une iframe. */
export function dansUneIframe() {
  if (typeof window === 'undefined') return false
  try {
    return window.self !== window.top
  } catch {
    // Accès refusé à `window.top` : cross-origin, donc bien dans une iframe.
    return true
  }
}

/**
 * Ouvre le document dans un onglet de premier niveau.
 *
 * Réservé au cas de l'iframe : un onglet ouvert est un contexte de
 * navigation complet, où le téléchargement (ou l'affichage du PDF) n'est
 * pas soumis au `sandbox` de l'élément parent. Renvoie `false` si le
 * navigateur a bloqué l'ouverture (pop-up bloquée).
 */
function ouvrirDansUnOnglet(url) {
  if (!dansUneIframe() || typeof window === 'undefined') return false
  try {
    return Boolean(window.open(url, '_blank', 'noopener'))
  } catch {
    return false
  }
}

/**
 * Télécharge directement le résultat de `api.getBlob`.
 *
 * @param {{blob: Blob, fileName?: string, contentType?: string}} resultat
 * @param {string} [nomParDefaut] utilisé si le serveur n'a pas nommé le fichier
 * @returns {string} le nom de fichier utilisé
 */
export function telechargerReponseBlob(resultat, nomParDefaut = 'export') {
  const { blob, fileName, contentType } = resultat || {}
  return telechargerBlob(blob, fileName || nomParDefaut, { contentType })
}
