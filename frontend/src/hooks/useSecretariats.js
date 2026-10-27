import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { SECRETARIATS_QUERY_KEY } from '../lib/queryClient'

async function fetchSecretariats() {
  const res = await api.get('/formations/secretariats/')
  const data = res.data
  return Array.isArray(data) ? data : (data.results || [])
}

/** Liste des secrétariats — cache 10 min. */
export function useSecretariats(options = {}) {
  const { enabled = true } = options
  return useQuery({
    queryKey: SECRETARIATS_QUERY_KEY,
    queryFn: fetchSecretariats,
    staleTime: 10 * 60 * 1000,
    enabled,
  })
}
