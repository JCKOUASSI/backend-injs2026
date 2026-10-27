import { describe, it, expect } from 'vitest'
import { parsePaginatedResponse } from './paginatedResponse'

describe('utils/paginatedResponse — parsePaginatedResponse', () => {
  it('gère une réponse « legacy » qui est directement un tableau', () => {
    const r = parsePaginatedResponse([{ id: 1 }, { id: 2 }])
    expect(r.results).toHaveLength(2)
    expect(r.count).toBe(2)
    expect(r.totalPages).toBe(1)
  })

  it('lit une réponse DRF paginée complète', () => {
    const r = parsePaginatedResponse({ count: 120, total_pages: 6, results: [{ id: 1 }] })
    expect(r.count).toBe(120)
    expect(r.totalPages).toBe(6)
    expect(r.results).toEqual([{ id: 1 }])
  })

  it('retient total_pages fourni par le backend même sans count cohérent', () => {
    const r = parsePaginatedResponse({ count: 300, total_pages: 12, results: [] })
    expect(r.totalPages).toBe(12)
  })

  it('calcule totalPages depuis count et la taille de page quand absent', () => {
    const r = parsePaginatedResponse({ count: 55, results: [] }, 25)
    expect(r.totalPages).toBe(3) // 55 / 25 → 3 pages
  })

  it('applique une taille de page par défaut de 50', () => {
    expect(parsePaginatedResponse({ count: 51, results: [] }).totalPages).toBe(2)
  })

  it('se protège des réponses nulles / vides', () => {
    expect(parsePaginatedResponse(null)).toEqual({ results: [], count: 0, totalPages: 1 })
    expect(parsePaginatedResponse({}).results).toEqual([])
    expect(parsePaginatedResponse({ count: 0, results: [] }).totalPages).toBe(1)
  })
})
