import { useQuery } from '@tanstack/react-query'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { MES_ACCES_QUERY_KEY } from '../lib/queryClient'

/**
 * Navigation RBAC — état gouverné du compte connecté.
 *
 * Monte `GET /api/habilitations/mes-acces/` (lecture auto-portée, aucun droit
 * d'administration requis) et en extrait ce dont la barre latérale a besoin :
 *
 * - `gouverne`              : le compte possède-t-il un profil CURP ?
 * - `permissions_effectives`: codes `<module>.<ressource>.<action>` réellement
 *                             détenus (rôles actifs + dérogations OCTROI − RETRAIT),
 *                             clé **additive** exposée par le backend ;
 * - `statut`, `canal`, `mfa_actif` : utiles au bandeau de diagnostic.
 *
 * Tolérance aux pannes (règle de repli) : si l'endpoint échoue, n'est pas
 * accessible ou renvoie un corps inattendu, le hook renvoie `null` et la navigation
 * retombe sur les capacités legacy — **aucun compte ne perd son menu**.
 * L'API reste la seule autorité : ces données ne servent qu'à afficher.
 */
export function useMesAcces() {
  const { isAuthenticated } = useAuth()
  return useQuery({
    queryKey: MES_ACCES_QUERY_KEY,
    queryFn: async ({ signal }) => {
      try {
        const res = await api.get('/habilitations/mes-acces/', { signal })
        const data = res?.data
        if (!data || typeof data !== 'object' || Array.isArray(data)) return null
        return data
      } catch {
        return null
      }
    },
    enabled: !!isAuthenticated,
    staleTime: 5 * 60 * 1000,
    gcTime: 15 * 60 * 1000,
    retry: false,
  })
}

export default useMesAcces
