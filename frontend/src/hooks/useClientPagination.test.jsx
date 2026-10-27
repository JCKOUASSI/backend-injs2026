import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useClientPagination, TABLE_PAGE_SIZE, PICKER_PAGE_SIZE } from '@/hooks/useClientPagination'

describe('hooks/useClientPagination', () => {
  it('expose les tailles de page standard', () => {
    expect(TABLE_PAGE_SIZE).toBe(25)
    expect(PICKER_PAGE_SIZE).toBe(50)
  })

  it('pagine côté client et expose les totaux', () => {
    const items = Array.from({ length: 55 }, (_, i) => ({ id: i + 1 }))
    const { result } = renderHook(() => useClientPagination(items, 25))
    expect(result.current.totalItems).toBe(55)
    expect(result.current.totalPages).toBe(3)
    expect(result.current.pageItems).toHaveLength(25)
    expect(result.current.pageItems[0].id).toBe(1)
    act(() => result.current.setPage(3))
    expect(result.current.pageItems).toHaveLength(5)
    expect(result.current.pageItems[4].id).toBe(55)
  })

  it('gère les tableaux vides ou absents sans page invalide', () => {
    const { result, rerender } = renderHook(({ list }) => useClientPagination(list, 25), {
      initialProps: { list: undefined },
    })
    expect(result.current.totalPages).toBe(1)
    expect(result.current.pageItems).toHaveLength(0)
    rerender({ list: [] })
    expect(result.current.pageItems).toHaveLength(0)
  })

  it('ramène à la première page quand les dépendances de reset changent', () => {
    const items = Array.from({ length: 60 }, (_, i) => ({ id: i + 1 }))
    const { result, rerender } = renderHook(({ filtre }) => useClientPagination(items, 25, [filtre]), {
      initialProps: { filtre: 'A' },
    })
    act(() => result.current.setPage(2))
    expect(result.current.page).toBe(2)
    rerender({ filtre: 'B' })
    expect(result.current.page).toBe(1)
  })

  it('borne la page courante si le tableau rétrécit', () => {
    const big = Array.from({ length: 60 }, (_, i) => ({ id: i + 1 }))
    const { result, rerender } = renderHook(({ list }) => useClientPagination(list, 25), {
      initialProps: { list: big },
    })
    act(() => result.current.setPage(3))
    expect(result.current.page).toBe(3)
    rerender({ list: big.slice(0, 10) })
    expect(result.current.page).toBe(1)
    expect(result.current.totalPages).toBe(1)
  })
})
