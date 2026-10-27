import { useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { listHref } from '../utils/listFilters'

/** Retour vers une liste en conservant filtres (historique ou sessionStorage). */
export function useListReturn(pathname, storageKey) {
  const location = useLocation()
  const navigate = useNavigate()

  return useCallback(() => {
    if (location.state?.from) {
      navigate(location.state.from)
      return
    }
    navigate(listHref(pathname, storageKey))
  }, [location.state, navigate, pathname, storageKey])
}

/** État à passer aux liens vers une page détail. */
export function useListNavigationState() {
  const location = useLocation()
  return { from: `${location.pathname}${location.search}` }
}
