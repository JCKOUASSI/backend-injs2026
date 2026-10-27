import api from './api'

/**
 * Service du module Emplois du temps (GET-INJS) — INJS-LMD / Abidjan.
 *
 * Appels spécifiques à l'orchestration LMD (LOT 3) : la génération coordonnée
 * couvre **toutes** les formations INJS de l'année académique portant des
 * affectations pédagogiques planifiables. Le périmètre est dérivé des données
 * validées côté serveur : aucune liste de formations n'est transmise.
 */

/** Route de génération coordonnée (POST). */
export const BASE_COORDONNEE = '/edts/lmd/generate-coordinated/'

/**
 * Déclenche la génération coordonnée des emplois du temps d'une année.
 *
 * @param {object} params
 * @param {number|string} params.annee_academique_id  Année académique visée (obligatoire).
 * @param {number[]} [params.semaines]                Semaines à couvrir (optionnel).
 * @param {boolean} [params.persister]                Persister les plans (défaut : false).
 * @param {boolean} [params.remplacer]                Remplacer les séances générées (défaut : true).
 * @returns {Promise<{data: object, status: number}>} Bilan de l'opération.
 */
export function genererEdtsCoordonne({ annee_academique_id, semaines, persister, remplacer } = {}) {
  const corps = { annee_academique_id }
  if (Array.isArray(semaines) && semaines.length) corps.semaines = semaines
  if (persister) corps.persister = true
  if (remplacer !== undefined) corps.remplacer = Boolean(remplacer)
  return api.post(BASE_COORDONNEE, corps)
}
