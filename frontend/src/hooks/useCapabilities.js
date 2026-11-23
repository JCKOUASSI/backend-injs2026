import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { CAPABILITIES_QUERY_KEY } from '../lib/queryClient'

/**
 * Charge les capacités effectives de l'utilisateur depuis
 * GET /auth/capabilities/ (P00-06 — source unique de vérité des droits UI).
 *
 * Le cache React Query est invalidé à la connexion et purgé à la
 * déconnexion par AuthContext ; la requête ne part que pour une session
 * authentifiée. En cas d'échec de l'endpoint, les helpers de `utils/roles`
 * retombent sur le référentiel statique (identique à l'ancien comportement).
 */
export function useCapabilities() {
  const { isAuthenticated } = useAuth()
  return useQuery({
    queryKey: CAPABILITIES_QUERY_KEY,
    queryFn: async ({ signal }) => {
      const res = await api.get('/auth/capabilities/', { signal })
      const data = res?.data
      // Validation de forme stricte : un corps inattendu (page d'erreur,
      // tableau, proxy de secours des tests…) déclenche le repli statique
      // plutôt qu'une capacité « truthy » mais inexploitable.
      if (
        data &&
        !Array.isArray(data) &&
        typeof data === 'object' &&
        data.capacites &&
        typeof data.capacites === 'object' &&
        !Array.isArray(data.capacites)
      ) {
        return data
      }
      return null
    },
    enabled: !!isAuthenticated,
    staleTime: 5 * 60 * 1000,
    gcTime: 15 * 60 * 1000,
    retry: false,
  })
}
