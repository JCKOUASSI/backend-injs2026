/**
 * Services du Hub « Référentiels » : export et import.
 *
 * Mission « Référentiels » : un seul jeu de fonctions pour les 27
 * référentiels du registre. Le slug désigne le référentiel ; le format et le
 * mode sont les seuls autres paramètres. Aucune logique métier ici : le
 * backend décide des colonnes, des règles de validation et des permissions.
 */
import api, { API_BASE_URL } from './api'
import { safeLocalStorage } from '../utils/safeStorage'
import {
  estUnDocument,
  telechargerParUrl,
  dansUneIframe,
  ouvrirDansUnOnglet,
} from '../utils/telechargement'

/** Formats d'export pris en charge, avec libellé et extension. */
export const FORMATS_EXPORT = [
  { cle: 'xlsx', libelle: 'Excel', extension: '.xlsx', icone: 'bi-file-earmark-excel' },
  { cle: 'docx', libelle: 'Word', extension: '.docx', icone: 'bi-file-earmark-word' },
  { cle: 'csv', libelle: 'CSV', extension: '.csv', icone: 'bi-filetype-csv' },
  { cle: 'pdf', libelle: 'PDF', extension: '.pdf', icone: 'bi-file-earmark-pdf' },
]

/** Modes d'importation proposés à l'étape 4. */
export const MODES_IMPORT = [
  {
    cle: 'ajouter',
    libelle: 'Ajouter uniquement',
    description: "Crée les nouvelles valeurs ; les valeurs déjà connues sont signalées et ignorées.",
  },
  {
    cle: 'mettre_a_jour',
    libelle: 'Mettre à jour uniquement',
    description: 'Met à jour les valeurs existantes ; aucune création.',
  },
  {
    cle: 'les_deux',
    libelle: 'Ajouter et mettre à jour',
    description: 'Crée les valeurs absentes et met à jour les valeurs connues.',
  },
]

/** Extensions acceptées au téléversement (contrôle côté navigateur, doublé côté serveur). */
export const EXTENSIONS_ACCEPTEES = '.xlsx,.xls,.csv'

const TAILLE_MAX = 10 * 1024 * 1024 // 10 Mio — aligné sur TAILLE_MAX_PIECE

/**
 * Télécharge un export du référentiel.
 *
 * @param {string} slug identifiant du référentiel
 * @param {string} formatCible csv | xlsx | docx | pdf
 * @param {object} [filtres] critères de recherche courants (?search=, ?actif=, ?ordering=)
 * @returns {Promise<string>} nom du fichier téléchargé
 */
/**
 * Adresse de téléchargement direct d'un export.
 *
 * Le serveur accepte le jeton d'accès **en paramètre d'URL**
 * (`FlexibleJWTAuthentication`, prévu nommément pour les exports et les
 * lecteurs médias) : une simple requête GET suffit donc à obtenir le
 * document, sans en-tête `Authorization` — ce qu'un `<a href>` ne peut pas
 * poser. Le serveur répond avec `Content-Disposition: attachment`, et le
 * navigateur enregistre alors le fichier par le chemin le plus standard qui
 * soit, celui d'un lien ordinaire : plus de blob, plus d'URL d'objet à
 * créer puis à révoquer, plus de dépendance aux caprices du clic programmé
 * sur un `Blob` (Safari, Firefox, aperçus intégrés).
 *
 * C'est aussi ce qui rend le lien de repli réellement utilisable : il pointe
 * vers une ressource durable, que l'utilisateur peut cliquer lui-même.
 */
export function urlExportDirecte(slug, formatCible, filtres = {}) {
  const params = new URLSearchParams()
  params.set('export', formatCible)
  Object.entries(filtres).forEach(([cle, valeur]) => {
    if (valeur === undefined || valeur === null || valeur === '') return
    params.set(cle, String(valeur))
  })
  const jeton = safeLocalStorage.getItem('access_token')
  if (jeton) params.set('access_token', jeton)
  return `${API_BASE_URL}/referentiels/${slug}/exporter/?${params.toString()}`
}

export async function exporterReferentiel(slug, formatCible, filtres = {}, options = {}) {
  // 1) Validation : `api.get` est bâti sur `fetch`, où l'option
  // `responseType: 'blob'` est ignorée — la réponse binaire passait alors par
  // `res.text()` + `JSON.parse()`, ce qui faisait échouer **tous** les
  // exports. Le chemin correct est `getBlob`, qui lit la réponse en `blob()`
  // et extrait le nom de fichier de l'en-tête Content-Disposition.
  //
  // Cette requête sert ici à **valider** : elle prouve que le document
  // existe, fournit son nom et remonte les erreurs (403, format refusé)
  // avant toute tentative de téléchargement.
  const resultat = await api.getBlob(`/referentiels/${slug}/exporter/`, {
    export: formatCible,
    ...filtres,
  })
  // Garde-fou : une erreur d'export renvoie du JSON. Mieux vaut ne rien
  // télécharger qu'un document corrompu silencieux — et surtout ne pas
  // déclencher une requête de téléchargement vouée à enregistrer une erreur.
  if (!estUnDocument(resultat.blob, resultat.contentType)) {
    const erreur = new Error(
      "Réponse inattendue du serveur : aucun document à télécharger.",
    )
    erreur.corrompu = true
    throw erreur
  }
  const nom = resultat.fileName || nomDeFichierDepuis(null, slug, formatCible)

  // 2) Remise : par une URL HTTP réelle et non par le blob. Le document est
  // régénéré côté serveur (quelques millisecondes pour un référentiel) :
  // c'est le prix d'une remise qui ne dépend plus du `Blob`.
  const url = urlExportDirecte(slug, formatCible, filtres)
  telechargerParUrl(url, nom)

  // Dans un aperçu intégré, le téléchargement peut être bloqué : on tente
  // alors aussi l'ouverture d'un onglet de premier niveau.
  const dansIframe = dansUneIframe()
  const ongletOuvert = dansIframe ? ouvrirDansUnOnglet(url) : false

  if (typeof options.onDiagnostic === 'function') {
    options.onDiagnostic({
      nom,
      url,
      // Le contenu est transmis pour que l'écran puisse, à défaut de le
      // remettre, au moins l'**afficher** (aperçu intégré : téléchargements et
      // fenêtres surgissées interdits).
      blob: resultat.blob,
      contentType: resultat.contentType,
      ongletOuvert,
      dansUneIframe: dansIframe,
    })
  }
  return nom
}

/**
 * Extrait le nom de fichier de l'en-tête Content-Disposition renvoyé par le
 * serveur, sinon le reconstruit à l'identique (slug + horodatage).
 */
export function nomDeFichierDepuis(headers, slug, formatCible) {
  const disposition =
    headers?.['content-disposition'] || headers?.get?.('content-disposition') || ''
  const trouve = /filename="([^"]+)"/i.exec(disposition)
  if (trouve) return trouve[1]
  const horodate = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  const stamp = `${horodate.getFullYear()}${pad(horodate.getMonth() + 1)}${pad(
    horodate.getDate(),
  )}-${pad(horodate.getHours())}${pad(horodate.getMinutes())}`
  return `${slug}_${stamp}.${formatCible}`
}

/**
 * Contrôle local du fichier avant envoi (étape 1).
 * @returns {string|null} message d'erreur, ou null si le fichier est acceptable
 */
export function controlerFichier(fichier) {
  if (!fichier) return 'Aucun fichier sélectionné.'
  const nom = (fichier.name || '').toLowerCase()
  const extension = nom.includes('.') ? nom.split('.').pop() : ''
  if (!['xlsx', 'xls', 'csv'].includes(extension)) {
    return 'Format non pris en charge : seuls .xlsx, .xls et .csv sont acceptés.'
  }
  if (fichier.size === 0) return 'Le fichier est vide.'
  if (fichier.size > TAILLE_MAX) {
    return `Fichier trop volumineux (${Math.round(
      fichier.size / (1024 * 1024),
    )} Mio) : la taille maximale est de 10 Mio.`
  }
  return null
}

/**
 * Étapes 1 à 3 : téléversement contrôlé, prévisualisation et validation.
 * Aucune écriture en base côté serveur.
 */
export async function analyserImport(slug, fichier, options = {}) {
  const corps = new FormData()
  corps.append('fichier', fichier)
  if (options.aEntete !== undefined) corps.append('a_entete', String(options.aEntete))
  if (options.correspondance) {
    corps.append('correspondance', JSON.stringify(options.correspondance))
  }
  const { data } = await api.post(`/referentiels/${slug}/importer/analyse/`, corps)
  return data
}

/** Étape 4 : importation transactionnelle. */
export async function importerReferentiel(slug, fichier, options = {}) {
  const corps = new FormData()
  corps.append('fichier', fichier)
  corps.append('mode', options.mode || 'les_deux')
  if (options.aEntete !== undefined) corps.append('a_entete', String(options.aEntete))
  if (options.correspondance) {
    corps.append('correspondance', JSON.stringify(options.correspondance))
  }
  const { data } = await api.post(`/referentiels/${slug}/importer/`, corps)
  return data
}

/** Construit le fichier des anomalies à télécharger (étape 5, CSV UTF-8 « ; »). */
export function genererCsvAnomalies(anomalies) {
  const entetes = ['Ligne', 'Colonne', 'Valeur', 'Message']
  const echapper = (valeur) => {
    const texte = valeur === null || valeur === undefined ? '' : String(valeur)
    return /[";\n]/.test(texte) ? `"${texte.replace(/"/g, '""')}"` : texte
  }
  const lignes = (anomalies || []).map((a) =>
    [a.ligne, a.colonne, a.valeur, a.message].map(echapper).join(';'),
  )
  // BOM UTF-8 : Excel lit correctement les accents.
  return '﻿' + [entetes.join(';'), ...lignes].join('\r\n')
}
