import { describe, it, expect } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { usePickerPagination } from './usePickerPagination'
import { PICKER_PAGE_SIZE } from './useClientPagination'

describe('hooks/usePickerPagination', () => {
  it('démarre page 1, sans résultat, avec la taille de page « picker »', () => {
    const { result } = renderHook(({ open }) => usePickerPagination(open), {
      initialProps: { open: false },
    })
    expect(result.current.page).toBe(1)
    expect(result.current.totalPages).toBe(1)
    expect(result.current.totalCount).toBe(0)
    expect(result.current.pageSize).toBe(PICKER_PAGE_SIZE)
  })

  it('calcule le nombre de pages depuis count quand total_pages est absent', () => {
    const { result } = renderHook(() => usePickerPagination(true))
    act(() => result.current.applyResponse({ count: 120 }))
    expect(result.current.totalCount).toBe(120)
    expect(result.current.totalPages).toBe(3) // ceil(120/50)
  })

  it('retient total_pages renvoyé par le backend', () => {
    const { result } = renderHook(() => usePickerPagination(true))
    act(() => result.current.applyResponse({ count: 5, total_pages: 9 }))
    expect(result.current.totalCount).toBe(5)
    expect(result.current.totalPages).toBe(9)
  })

  it('se rabat sur la longueur des résultats quand count est absent', () => {
    const { result } = renderHook(() => usePickerPagination(true))
    act(() => result.current.applyResponse(undefined, 51))
    expect(result.current.totalCount).toBe(51)
    expect(result.current.totalPages).toBe(2)
  })

  it('garde au moins une page même sans aucune donnée', () => {
    const { result } = renderHook(() => usePickerPagination(true))
    act(() => result.current.applyResponse(null))
    expect(result.current.totalCount).toBe(0)
    expect(result.current.totalPages).toBe(1)
  })

  it('resetPage ramène en page 1', () => {
    const { result } = renderHook(() => usePickerPagination(true))
    act(() => result.current.setPage(4))
    expect(result.current.page).toBe(4)
    act(() => result.current.resetPage())
    expect(result.current.page).toBe(1)
  })

  it('repasse en page 1 à chaque ouverture (transition fermé → ouvert)', () => {
    const { result, rerender } = renderHook(({ open }) => usePickerPagination(open), {
      initialProps: { open: false },
    })
    act(() => result.current.setPage(3))
    expect(result.current.page).toBe(3)
    rerender({ open: true })
    expect(result.current.page).toBe(1)
  })
})
