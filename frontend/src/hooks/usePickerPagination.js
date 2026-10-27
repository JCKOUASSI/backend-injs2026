import { useEffect, useState } from 'react'

import { PICKER_PAGE_SIZE } from './useClientPagination'

/**
 * État pagination pour modales de sélection (API page / total_pages).
 */
export function usePickerPagination(open) {
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)

  useEffect(() => {
    if (open) setPage(1)
  }, [open])

  const resetPage = () => setPage(1)

  const applyResponse = (responseData, resultsLength) => {
    const count = responseData?.count ?? resultsLength ?? 0
    setTotalCount(count)
    setTotalPages(
      responseData?.total_pages || Math.max(1, Math.ceil(count / PICKER_PAGE_SIZE)),
    )
  }

  return {
    page,
    setPage,
    totalPages,
    totalCount,
    pageSize: PICKER_PAGE_SIZE,
    resetPage,
    applyResponse,
  }
}
