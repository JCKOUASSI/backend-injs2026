import { useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { persistListQuery } from '../utils/listFilters'

/**
 * Synchronise filtres / pagination → URL (?…) + sessionStorage (liens Retour).
 */
export function usePersistedListQuery(storageKey, buildParams, deps) {
  const [searchParams, setSearchParams] = useSearchParams()

  useEffect(() => {
    const next = buildParams()
    persistListQuery(storageKey, next)
    if (next.toString() !== searchParams.toString()) {
      setSearchParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey, searchParams, setSearchParams, ...deps])

  return searchParams
}
