import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { FLAGS_QUERY_KEY } from '../lib/queryClient'

/**
 * Charge la carte des feature flags depuis GET /api/parametres/flags/ (P00-08).
 * Le serveur évalue déjà chaque flag pour l'utilisateur courant (interrupteur
 * global ou liste de rôles) : le frontend ne reçoit que des booléens.
 *
 * - requête activée uniquement en session authentifiée ;
 * - fraîcheur courte (1 min) pour propager quasi immédiatement une bascule
 *   d'urgence, l'écran d'administration invalidant en outre la requête ;
 * - tout corps inattendu ou échec donne une carte vide : tous les flags sont
 *   alors considérés éteints (sécurité par défaut, aucun comportement activé).
 */
export function useFlags() {
  const { isAuthenticated } = useAuth()
  const { data } = useQuery({
    queryKey: FLAGS_QUERY_KEY,
    queryFn: async ({ signal }) => {
      const res = await api.get('/parametres/flags/', { signal })
      const flags = res?.data?.flags
      return flags && typeof flags === 'object' && !Array.isArray(flags) ? flags : {}
    },
    enabled: !!isAuthenticated,
    staleTime: 60 * 1000,
    gcTime: 10 * 60 * 1000,
    retry: false,
  })
  return data ?? {}
}

/** Vrai si le flag `cle` est activé pour l'utilisateur courant. */
export function useFlag(cle) {
  const flags = useFlags()
  return Boolean(flags[cle])
}
