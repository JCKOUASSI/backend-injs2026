import { useEffect, useMemo, useState } from 'react'

export const TABLE_PAGE_SIZE = 25
export const PICKER_PAGE_SIZE = 50

/**
 * Pagination côté client (slice d’un tableau déjà chargé).
 * @param {unknown[]} items
 * @param {number} pageSize
 * @param {unknown[]} resetDeps — remet la page à 1 quand ces valeurs changent
 */
export function useClientPagination(items, pageSize = TABLE_PAGE_SIZE, resetDeps = []) {
  const [page, setPage] = useState(1)
  // Mémoïsé pour garder une référence stable quand `items` est null/undefined
  // (sinon le `?? []` créerait un tableau neuf à chaque rendu et casserait les
  // dépendances du useMemo de pagination).
  const list = useMemo(() => items ?? [], [items])
  const totalItems = list.length
  const totalPages = Math.max(1, Math.ceil(totalItems / pageSize) || 1)
  const pageSafe = Math.min(Math.max(1, page), totalPages)

  useEffect(() => {
    setPage(1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, resetDeps)

  const pageItems = useMemo(() => {
    const start = (pageSafe - 1) * pageSize
    return list.slice(start, start + pageSize)
  }, [list, pageSafe, pageSize])

  return {
    page: pageSafe,
    setPage,
    totalPages,
    totalItems,
    pageItems,
    pageSize,
  }
}
