import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
  },
}))

import api from './api'
import {
  BASE,
  genererReleve,
  getHistoriqueNotes,
  getPreparation,
  getRegles,
  getReglesVersions,
  getSession,
  getTypesEvaluation,
} from './evaluations'

describe('service évaluations — contrats lecture et génération', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('normalise les types d’évaluation paginés', async () => {
    const types = [{ id: 1, code: 'EXAMEN' }]
    api.get.mockResolvedValueOnce({ data: { results: types } })

    await expect(getTypesEvaluation()).resolves.toEqual(types)
    expect(api.get).toHaveBeenCalledWith(`${BASE}/types-evaluation/`)
  })

  it('accepte une liste directe pour le référentiel des règles', async () => {
    const regles = [{ id: 2, code: 'LMD' }]
    api.get.mockResolvedValueOnce({ data: regles })

    await expect(getRegles()).resolves.toEqual(regles)
    expect(api.get).toHaveBeenCalledWith(`${BASE}/regles/`)
  })

  it('transmet les filtres des versions de règles et renvoie la réponse', async () => {
    const filtres = { actif: true, page: 2 }
    const resultats = { results: [{ id: 3, version: 1 }] }
    api.get.mockResolvedValueOnce({ data: resultats })

    await expect(getReglesVersions(filtres)).resolves.toEqual(resultats)
    expect(api.get).toHaveBeenCalledWith(`${BASE}/regles/versions/`, { params: filtres })
  })

  it('charge une session par son identifiant', async () => {
    const session = { id: 8, libelle: 'Session 2026' }
    api.get.mockResolvedValueOnce({ data: session })

    await expect(getSession(8)).resolves.toEqual(session)
    expect(api.get).toHaveBeenCalledWith(`${BASE}/sessions/8/`)
  })

  it('charge la préparation calculée par le backend sans la recalculer', async () => {
    const preparation = { moyenne: null, diagnostics: ['NOTE_MANQUANTE'] }
    api.get.mockResolvedValueOnce({ data: preparation })

    await expect(getPreparation(11, 12)).resolves.toEqual(preparation)
    expect(api.get).toHaveBeenCalledWith(
      `${BASE}/evaluations/11/participants/12/preparation/`,
    )
  })

  it('transmet les filtres de l’historique des notes', async () => {
    const filtres = { evaluation_id: 9, page: 3 }
    const historique = { results: [{ id: 20, valeur: null }] }
    api.get.mockResolvedValueOnce({ data: historique })

    await expect(getHistoriqueNotes(filtres)).resolves.toEqual(historique)
    expect(api.get).toHaveBeenCalledWith(`${BASE}/notes/historique/`, { params: filtres })
  })

  it('génère un relevé avec les seuls identifiants attendus par l’API', async () => {
    const criteres = { inscription_id: 14, session_id: 5 }
    const releve = { id: 31, version: 2 }
    api.post.mockResolvedValueOnce({ data: releve })

    await expect(genererReleve(criteres)).resolves.toEqual(releve)
    expect(api.post).toHaveBeenCalledWith(`${BASE}/releves/generer/`, criteres)
  })
})
