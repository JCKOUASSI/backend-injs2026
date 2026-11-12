/**
 * Services du Hub « Référentiels » : export et import.
 *
 * Mission « Référentiels » : un seul jeu de fonctions pour les 27
 * référentiels du registre. Le slug désigne le référentiel ; le format et le
 * mode sont les seuls autres paramètres. Aucune logique métier ici : le
 * backend décide des colonnes, des règles de validation et des permissions.
 */
import api from './api'

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
export async function exporterReferentiel(slug, formatCible, filtres = {}) {
  const { data, headers } = await api.get(`/referentiels/${slug}/exporter/`, {
    params: { export: formatCible, ...filtres },
    responseType: 'blob',
  })
  const nom = nomDeFichierDepuis(headers, slug, formatCible)
  telechargerBlob(data, nom)
  return nom
}

/** Déclenche le téléchargement d'un blob reçu sous le nom fourni. */
export function telechargerBlob(blob, nom) {
  const url = window.URL.createObjectURL(new Blob([blob]))
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nom
  document.body.appendChild(lien)
  lien.click()
  lien.remove()
  window.URL.revokeObjectURL(url)
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
  const { data } = await api.post(`/referentiels/${slug}/importer/analyse/`, corps, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
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
  const { data } = await api.post(`/referentiels/${slug}/importer/`, corps, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
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
