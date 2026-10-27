import { describe, it, expect } from 'vitest'
import { buildPaginationItems } from './paginationPages'

describe('utils/paginationPages — buildPaginationItems', () => {
  it('retourne toujours au moins la page 1', () => {
    expect(buildPaginationItems(1, 0)).toEqual([1])
    expect(buildPaginationItems(1, 1)).toEqual([1])
  })

  it('énumère toutes les pages jusqu’à 9 sans ellipse', () => {
    expect(buildPaginationItems(1, 9)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9])
    expect(buildPaginationItems(5, 5)).toEqual([1, 2, 3, 4, 5])
  })

  it('garde les bornes et le voisinage courant avec ellipses au-delà de 9 pages', () => {
    // Page courante au milieu : 1 … 8 9 [10] 11 12 … 50
    expect(buildPaginationItems(10, 50)).toEqual([1, '…', 8, 9, 10, 11, 12, '…', 50])
  })

  it('n’insère pas d’ellipse quand le voisinage touche déjà une borne', () => {
    // Courant 3 → 1 2 3 4 5 … 50 (pas de trou entre 1 et 5)
    expect(buildPaginationItems(3, 50)).toEqual([1, 2, 3, 4, 5, '…', 50])
    // Courant près de la fin : 1 … 46 47 48 49 50
    expect(buildPaginationItems(48, 50)).toEqual([1, '…', 46, 47, 48, 49, 50])
  })

  it('ne produit jamais de doublon et reste trié', () => {
    for (let total = 10; total <= 30; total++) {
      for (let cur = 1; cur <= total; cur++) {
        const items = buildPaginationItems(cur, total)
        const nums = items.filter((x) => x !== '…')
        expect(new Set(nums).size).toBe(nums.length)
        expect([...nums].sort((a, b) => a - b)).toEqual(nums)
        expect(nums).toContain(1)
        expect(nums).toContain(total)
        expect(nums).toContain(cur)
      }
    }
  })
})
