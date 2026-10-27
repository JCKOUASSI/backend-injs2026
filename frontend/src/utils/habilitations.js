/**
 * Fonctions pures de la console CURP (U4) : libellés, résumé du différentiel
 * de droits, analyse CSV des imports en masse. Aucun effet de bord, aucune
 * liste de rôles codée en dur : les rôles et permissions viennent de l'API.
 */

export const LIBELLES_STATUT = {
  INVITE: 'Invité',
  ACTIF: 'Actif',
  SUSPENDU: 'Suspendu',
  DESACTIVE: 'Désactivé',
  VERROUILLE: 'Verrouillé',
  EXPIRE: 'Expiré',
}

export const LIBELLES_CANAL = {
  WEB: 'Web',
  MOBILE: 'Mobile',
  LES_DEUX: 'Web et mobile',
}

export const LIBELLES_DOMAINE = {
  ADMINISTRATION: 'Administration',
  CANDIDATURES: 'Candidatures',
  SCOLARITE: 'Scolarité',
  PEDAGOGIE: 'Pédagogie',
  ENSEIGNANTS: 'Enseignants',
  EVALUATIONS: 'Évaluations',
  DIPLOMATION: 'Diplômation',
  FINANCE: 'Finance',
  STAGES: 'Stages',
  RH: 'Ressources humaines',
  PATRIMOINE: 'Patrimoine',
  ADMINISTRATION_GENERALE: 'Administration générale',
  DESTINATAIRES: 'Destinataires',
  TECHNIQUE: 'Technique',
}

export const moduleDuCode = (codePermission) => String(codePermission || '').split('.')[0]

export const libelleStatut = (statut) => LIBELLES_STATUT[statut] || statut || '—'
export const libelleCanal = (canal) => LIBELLES_CANAL[canal] || canal || '—'
export const libelleDomaine = (domaine) => LIBELLES_DOMAINE[domaine] || domaine || '—'

/** Compte des permissions par module à partir d'une liste de codes. */
export function compterParModule(codes = []) {
  return codes.reduce((acc, code) => {
    const module = moduleDuCode(code)
    acc[module] = (acc[module] || 0) + 1
    return acc
  }, {})
}

/**
 * Résume le différentiel renvoyé par l'API en données d'affichage :
 * permissions gagnées/perdues regroupées par module, totaux et rôle-level
 * changements. Le détail complet reste disponible pour l'écran.
 */
export function resumerDifferential(diff) {
  const gagnes = diff?.gagnes || []
  const perdus = diff?.perdus || []
  return {
    totalGagnes: gagnes.length,
    totalPerdus: perdus.length,
    totalConserves: diff?.conserves?.length || 0,
    totalActuel: diff?.total_actuel ?? null,
    totalCible: diff?.total_cible ?? null,
    gagnesParModule: compterParModule(gagnes),
    perdusParModule: compterParModule(perdus),
    rolesAjoutes: diff?.roles_ajoutes || [],
    rolesRetires: diff?.roles_retires || [],
    avertissements: diff?.avertissements || [],
    gagnes,
    perdus,
    vide: gagnes.length === 0 && perdus.length === 0,
  }
}

/** Un avertissement SEUIL_ADMINISTRATEURS est bloquant (l'API refusera). */
export const differentialAvertissementBloquant = (resume) =>
  resume.avertissements.some((a) => a.code === 'SEUIL_ADMINISTRATEURS')

/**
 * La validation n'est possible qu'après avoir :
 *  - reçu un différentiel ;
 *  - affiché puis acquitté le différentiel (case à cocher) ;
 *  - et qu'aucun avertissement bloquant n'est présent.
 */
export function peutValiderModification(resume, acquitte) {
  if (!resume) return false
  if (differentialAvertissementBloquant(resume)) return false
  if (!resume.vide && !acquitte) return false
  return true
}

/**
 * Analyse un tableau CSV (séparateur virgule ou point-virgule, première
 * ligne d'en-tête). Retourne des objets dont les clés sont les en-têtes
 * normalisés (minuscule, sans accents). Aucune écriture ici : l'écriture en
 * une transaction de l'import relève de l'unité U5.
 */
export function analyserCsv(texte) {
  const lignes = String(texte || '')
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0)
  if (lignes.length === 0) return []
  const separateur = lignes[0].includes(';') ? ';' : ','
  const decouper = (ligne) =>
    ligne
      .split(separateur)
      .map((cellule) => cellule.trim().replace(/^"|"$/g, ''))
  const entetes = decouper(lignes[0]).map(normaliserCle)
  return lignes.slice(1).map((ligne) => {
    const cellules = decouper(ligne)
    return entetes.reduce((objet, cle, index) => {
      objet[cle] = cellules[index] ?? ''
      return objet
    }, {})
  })
}

export function normaliserCle(libelle) {
  return String(libelle || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
}

/** Convertit des lignes CSV en charges utiles compatibles avec import-simuler. */
export function lignesCsvVersImport(lignes = []) {
  return lignes.map((l) => ({
    username: l.identifiant || l.username || l.nom_utilisateur || '',
    nom: l.nom || '',
    prenoms: l.prenoms || l.prenom || '',
    email: l.email || '',
    mot_de_passe: l.mot_de_passe || l.motdepasse || '',
    roles: l.roles || l.role || '',
    canal: l.canal || 'WEB',
  }))
}

export const filtreNonNull = (obj) =>
  Object.fromEntries(Object.entries(obj).filter(([, v]) => v !== '' && v != null))

/** Échappe une cellule CSV (point-virgule, guillemets, sauts de ligne). */
const celluleCsv = (valeur) => {
  const texte = String(valeur ?? '')
  return /[;"\n]/.test(texte) ? `"${texte.replace(/"/g, '""')}"` : texte
}

/**
 * Provoque le téléchargement navigateur d'un CSV (export de consultation :
 * l'export serveur paginé/global n'est pas au périmètre U4).
 */
export function telechargerCsv(nomFichier, entetes, lignes) {
  const corps = lignes.map((ligne) => ligne.map(celluleCsv).join(';')).join('\n')
  const blob = new Blob([`${entetes.map(celluleCsv).join(';')}\n${corps}`], {
    type: 'text/csv;charset=utf-8;',
  })
  const url = URL.createObjectURL(blob)
  const lien = document.createElement('a')
  lien.href = url
  lien.download = nomFichier
  lien.click()
  URL.revokeObjectURL(url)
}
