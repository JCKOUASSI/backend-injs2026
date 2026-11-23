import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { REFERENTIELS_QUERY_KEY } from '../lib/queryClient'

async function fetchReferentiels() {
  const res = await api.get('/formations/referentiels/')
  return res.data
}

/** Données référentielles partagées (sites, grades, modules, etc.) — cache 10 min. */
export function useReferentiels(options = {}) {
  const { enabled = true } = options
  return useQuery({
    queryKey: REFERENTIELS_QUERY_KEY,
    queryFn: fetchReferentiels,
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}

export function invalidateReferentielsQuery(queryClient) {
  if (queryClient) {
    queryClient.invalidateQueries({ queryKey: REFERENTIELS_QUERY_KEY })
  }
}
