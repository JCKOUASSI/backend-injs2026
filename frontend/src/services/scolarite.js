import api from './api'

/** Appels de l'API Scolarité LMD : candidatures, admissions, inscriptions, groupes. */

// ── Référentiels ────────────────────────────────────────────────────────────

/** Année académique courante, ou null si aucune n'est définie. */
export async function getAnneeCourante() {
  const res = await api.get('/scolarite/annee-courante/')
  return res.data?.annee ?? null
}

export const getRefScolarite = (ressource, params) =>
  api.get(`/scolarite/ref/${ressource}/`, { params })
export const getRefAdmission = (ressource) => api.get(`/admissions/ref/${ressource}/`)

/** Cycles de formation : référentiel partagé avec le module Formations. */
export const getRefFormations = () => api.get('/formations/ref/formations/')
export const getRefCategories = () => api.get('/formations/ref/categories/')
export const getRefGrades = () => api.get('/formations/ref/grades/')
export const getRefVagues = () => api.get('/formations/ref/vagues/')
export const getFormationsOperationnelles = () => api.get('/formations/formations/')

// ── Candidatures ────────────────────────────────────────────────────────────

export const listCandidatures = (params) => api.get('/admissions/candidatures/', { params })
export const getCandidature = (id) => api.get(`/admissions/candidatures/${id}/`)
export const createCandidature = (body) => api.post('/admissions/candidatures/', body)
export const updateCandidature = (id, body) => api.patch(`/admissions/candidatures/${id}/`, body)
export const deleteCandidature = (id) => api.delete(`/admissions/candidatures/${id}/`)
export const transitionCandidature = (id, body) =>
  api.post(`/admissions/candidatures/${id}/transition/`, body)
export const getStatsCandidatures = (params) =>
  api.get('/admissions/candidatures/stats/', { params })

export const listCandidats = (params) => api.get('/admissions/candidats/', { params })
export const createCandidat = (body) => api.post('/admissions/candidats/', body)

// ── Pièces justificatives ───────────────────────────────────────────────────

export const getPieces = (candidatureId) =>
  api.get(`/admissions/candidatures/${candidatureId}/pieces/`)
export const initPieces = (candidatureId) =>
  api.post(`/admissions/candidatures/${candidatureId}/pieces/`, {})
export const deposerPiece = (pieceId, formData) =>
  api.post(`/admissions/pieces/${pieceId}/deposer/`, formData)
export const verifierPiece = (pieceId, body) =>
  api.post(`/admissions/pieces/${pieceId}/verifier/`, body)
export const telechargerPiece = (pieceId) => api.getBlob(`/admissions/pieces/${pieceId}/fichier/`)

// ── Admissions ──────────────────────────────────────────────────────────────

export const listAdmissions = (params) => api.get('/admissions/admissions/', { params })
export const createAdmission = (body) => api.post('/admissions/admissions/', body)
export const updateAdmission = (id, body) => api.patch(`/admissions/admissions/${id}/`, body)
export const decisionAdmission = (id, body) =>
  api.post(`/admissions/admissions/${id}/decision/`, body)
export const annulerAdmission = (id, body) =>
  api.post(`/admissions/admissions/${id}/annuler/`, body)
export const getStatsAdmissions = (params) => api.get('/admissions/admissions/stats/', { params })

// ── Étudiants et inscriptions ───────────────────────────────────────────────

export const listEtudiants = (params) => api.get('/scolarite/etudiants/', { params })
export const getEtudiant = (id) => api.get(`/scolarite/etudiants/${id}/`)
export const updateEtudiant = (id, body) => api.patch(`/scolarite/etudiants/${id}/`, body)

export const listInscriptions = (params) => api.get('/scolarite/inscriptions/', { params })
export const getInscription = (id) => api.get(`/scolarite/inscriptions/${id}/`)
export const updateInscription = (id, body) => api.patch(`/scolarite/inscriptions/${id}/`, body)
export const createInscription = (body) => api.post('/scolarite/inscriptions/', body)
export const deleteInscription = (id) => api.delete(`/scolarite/inscriptions/${id}/`)
export const transitionInscription = (id, body) =>
  api.post(`/scolarite/inscriptions/${id}/transition/`, body)
export const inscrireDepuisAdmission = (body) =>
  api.post('/scolarite/inscriptions/depuis-admission/', body)
export const getStatsInscriptions = (params) =>
  api.get('/scolarite/inscriptions/stats/', { params })

// ── Inscriptions pédagogiques ───────────────────────────────────────────────

export const getPedagogie = (inscriptionId, params) =>
  api.get(`/scolarite/inscriptions/${inscriptionId}/pedagogie/`, { params })
export const genererPedagogie = (inscriptionId, body) =>
  api.post(`/scolarite/inscriptions/${inscriptionId}/pedagogie/generer/`, body)
export const ajouterEcue = (inscriptionId, body) =>
  api.post(`/scolarite/inscriptions/${inscriptionId}/pedagogie/ajouter/`, body)
export const retirerEcue = (ligneId) => api.delete(`/scolarite/pedagogie/${ligneId}/`)

// ── Groupes, réinscription, événements ──────────────────────────────────────

export const getEffectifsGroupes = (params) => api.get('/scolarite/groupes/effectifs/', { params })
export const getAffectations = (inscriptionId) =>
  api.get(`/scolarite/inscriptions/${inscriptionId}/affectations/`)
export const affecterGroupe = (inscriptionId, body) =>
  api.post(`/scolarite/inscriptions/${inscriptionId}/affectations/`, body)
export const retirerGroupe = (inscriptionId, body) =>
  api.post(`/scolarite/inscriptions/${inscriptionId}/retirer-groupe/`, body)
export const repartirGroupes = (body) => api.post('/scolarite/groupes/repartition/', body)
export const reinscrire = (body) => api.post('/scolarite/reinscriptions/', body)
export const getEvenements = (etudiantId) =>
  api.get(`/scolarite/etudiants/${etudiantId}/evenements/`)
export const createEvenement = (etudiantId, body) =>
  api.post(`/scolarite/etudiants/${etudiantId}/evenements/`, body)

// ── Passerelle vers les modules opérationnels ───────────────────────────────

export const analyserPasserelle = (inscriptionId, body) =>
  api.post(`/scolarite/inscriptions/${inscriptionId}/passerelle/analyser/`, body)
export const synchroniserPasserelle = (inscriptionId, body) =>
  api.post(`/scolarite/inscriptions/${inscriptionId}/passerelle/`, body)
export const synchroniserLot = (body) => api.post('/scolarite/passerelle/lot/', body)

// ── Présentation ────────────────────────────────────────────────────────────

/** Classe Bootstrap associée à un statut de candidature, d'admission ou d'inscription. */
export const STATUT_VARIANTS = {
  BROUILLON: 'secondary',
  SOUMISE: 'info',
  EN_ATTENTE_DE_VERIFICATION: 'info',
  PIECES_INCOMPLETES: 'warning',
  PIECES_VALIDEES: 'primary',
  EN_ETUDE: 'primary',
  ADMISSIBLE: 'primary',
  ADMIS: 'success',
  ADMIS_SOUS_RESERVE: 'success',
  LISTE_ATTENTE: 'warning',
  REFUSE: 'danger',
  REFUSEE: 'danger',
  ANNULE: 'dark',
  ANNULEE: 'dark',
  EN_ATTENTE: 'warning',
  A_VALIDER: 'info',
  VALIDEE: 'success',
  REJETEE: 'danger',
  SUSPENDUE: 'warning',
  TERMINEE: 'dark',
  MANQUANTE: 'secondary',
  FOURNIE: 'info',
  EN_VERIFICATION: 'info',
  REFUSEE_PIECE: 'danger',
  EXPIREE: 'danger',
  PREVUE: 'secondary',
}

export function statutVariant(statut) {
  return STATUT_VARIANTS[statut] || 'secondary'
}

/** Message d'erreur lisible à partir d'une réponse d'API en échec. */
export function messageErreur(err, defaut = 'Une erreur est survenue') {
  const data = err?.response?.data
  if (!data) return defaut
  if (typeof data === 'string') return data
  if (data.error) return data.error
  const entries = Object.entries(data)
  if (!entries.length) return defaut
  return entries
    .map(([champ, valeur]) => `${champ} : ${Array.isArray(valeur) ? valeur.join(', ') : valeur}`)
    .join('\n')
}
