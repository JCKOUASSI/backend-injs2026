import api from './api'

/**
 * Service officiel du module Évaluations (INJS-LMD / INJS Abidjan - Marcory).
 *
 * Montage backend : `/api/evaluations-academiques/`.
 *
 * Règles strictes de ce service :
 * - il ne calcule RIEN (moyennes, seuils, validation, éligibilité) ;
 * - il ne déduit aucune règle de substitution de rattrapage (D3) ;
 * - il ne convertit JAMAIS `null` en 0 (D2 / D6).
 * Le frontend consomme les valeurs backend, point final.
 */

export const BASE = '/evaluations-academiques'

// ── Référentiels de règles (lecture seule) ─────────────────────────────────

/** Types d'évaluation déclarés par la scolarité. */
export async function getTypesEvaluation() {
  const res = await api.get(`${BASE}/types-evaluation/`)
  return res.data?.results ?? res.data ?? []
}

/** Familles de règles de calcul (RegleCalcul). */
export async function getRegles() {
  const res = await api.get(`${BASE}/regles/`)
  return res.data?.results ?? res.data ?? []
}

/** Versions de règles déclarées — porteuses des paramètres (D3, D1). */
export async function getReglesVersions(params = {}) {
  const res = await api.get(`${BASE}/regles/versions/`, { params })
  return res.data ?? {}
}

// ── Sessions ───────────────────────────────────────────────────────────────

/** Sessions d'évaluation. Filtres réellement supportés par l'API. */
export async function getSessions(params = {}) {
  const res = await api.get(`${BASE}/sessions/`, { params })
  return res.data ?? {}
}

export async function getSession(pk) {
  const res = await api.get(`${BASE}/sessions/${pk}/`)
  return res.data
}

// ── Évaluations ────────────────────────────────────────────────────────────

/** Liste des évaluations. Filtres réellement supportés par l'API. */
export async function getEvaluations(params = {}) {
  const res = await api.get(`${BASE}/evaluations/`, { params })
  return res.data ?? {}
}

export async function getEvaluation(pk) {
  const res = await api.get(`${BASE}/evaluations/${pk}/`)
  return res.data
}

export async function getComposants(pk) {
  const res = await api.get(`${BASE}/evaluations/${pk}/composants/`)
  return res.data?.results ?? res.data ?? []
}

/**
 * Participants d'une évaluation.
 * L'API renvoie ici un **tableau simple** (vue non paginée) : on normalise
 * pour que l'appelant manipule toujours une liste.
 */
export async function getParticipants(pk) {
  const res = await api.get(`${BASE}/evaluations/${pk}/participants/`)
  const data = res.data
  if (Array.isArray(data)) return data
  return data?.results ?? []
}

// ── Moteur C2 : préparation (projection calculée, lecture seule) ───────────

/**
 * Préparation du calcul d'un participant : moyenne, composants, règle LMD,
 * diagnostics et empreinte. Le backend a déjà tout décidé : le frontend
 * affiche, il ne recalcule rien.
 */
export async function getPreparation(evaluationPk, participantPk) {
  const res = await api.get(
    `${BASE}/evaluations/${evaluationPk}/participants/${participantPk}/preparation/`,
  )
  return res.data
}

// ── Notes ──────────────────────────────────────────────────────────────────

/**
 * Saisie des notes d'un composant (verrouillage géré par le backend).
 *
 * Deux contrats réels de l'API, souvent confondus :
 * - la vue `notes_saisie` n'accepte que **PUT** (`@api_view(['PUT'])`) ;
 * - le corps est une **liste** `{ evaluation_participant_id, valeur }`
 *   (`EvaluationGradeSaisieSerializer(many=True)`), jamais un objet.
 * Un `POST` renvoyait 405 et un objet renvoyait 400.
 *
 * Une valeur `null` est acceptée par l'API (champ laissé vide) ; elle n'est
 * jamais convertie en 0 côté frontend (D2 / D6).
 */
export async function saisirNotes(composantPk, notes) {
  const res = await api.put(`${BASE}/composants/${composantPk}/notes/`, notes)
  return res.data
}

/** Historique append-only des notes. */
export async function getHistoriqueNotes(params = {}) {
  const res = await api.get(`${BASE}/notes/historique/`, { params })
  return res.data ?? {}
}

// ── Résultats (valeurs calculées par le backend) ───────────────────────────

export async function getResultatsEcue(params = {}) {
  const res = await api.get(`${BASE}/resultats/ecue/`, { params })
  return res.data ?? {}
}

export async function getResultatsUe(params = {}) {
  const res = await api.get(`${BASE}/resultats/ue/`, { params })
  return res.data ?? {}
}

export async function getResultatsSemestre(params = {}) {
  const res = await api.get(`${BASE}/resultats/semestre/`, { params })
  return res.data ?? {}
}

/**
 * Passage de niveau — calcul technique fourni par le backend.
 * Le frontend ne recalcule NI moyenne, NI crédits, NI éligibilité : il se
 * contente d'afficher la réponse du moteur (D10 : aucune décision de jury
 * n'est fabriquée côté client).
 */
export async function getPassageNiveau({ inscription_id, session_id, niveau_id }) {
  const res = await api.get(`${BASE}/resultats/passage/`, {
    params: { inscription_id, session_id, niveau_id },
  })
  return res.data ?? {}
}

/** Relevés de notes — consultation paginée. */
export async function getReleves(params = {}) {
  const res = await api.get(`${BASE}/releves/`, { params })
  return res.data ?? {}
}

/** Génère le relevé : crée la version suivante, ne réécrit jamais l'existant. */
export async function genererReleve({ inscription_id, session_id }) {
  const res = await api.post(`${BASE}/releves/generer/`, {
    inscription_id,
    session_id,
  })
  return res.data ?? {}
}

/** Détail d'une version de relevé (contenu canonique inclus). */
export async function getReleve(pk) {
  const res = await api.get(`${BASE}/releves/${pk}/`)
  return res.data ?? {}
}

// ── Délibérations (source de vérité : module Jurys) ────────────────────────
// La décision académique est UNIQUE : elle est produite par le moteur
// LMD/ECTS du module `jurys`. Ce service ne fait qu'exposer l'API existante
// — aucun calcul, aucun seuil, aucune moyenne côté client.

/** Montée des routes Jurys (cf. config/urls.py). */
export const BASE_JURYS = '/jurys'

/** Sessions de jury paginées (filtres : statut, année, formation…). */
export async function getJurySessions(params = {}) {
  const res = await api.get(`${BASE_JURYS}/sessions/`, { params })
  return res.data ?? { results: [] }
}

/** Anomalies de délibération d'une session (contrôles réels du workflow). */
export async function getJuryAnomalies(sessionId) {
  const res = await api.get(`${BASE_JURYS}/sessions/${sessionId}/anomalies/`)
  return res.data ?? {}
}

/** Statistiques agrégées d'une session (calculées côté backend). */
export async function getJuryStatistiques(sessionId) {
  const res = await api.get(`${BASE_JURYS}/sessions/${sessionId}/statistiques/`)
  return res.data ?? {}
}