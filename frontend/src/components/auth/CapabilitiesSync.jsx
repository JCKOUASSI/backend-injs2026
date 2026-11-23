import { useEffect } from 'react'
import { useAuth } from '@/context/AuthContext'
import { useCapabilities } from '@/hooks/useCapabilities'

/**
 * P00-06 — pont entre React Query et le contexte d'authentification.
 *
 * Monte la requête GET /auth/capabilities/ (gérée par `useCapabilities`, mise
 * en cache React Query avec invalidation connexion/déconnexion/changement de
 * rôle) et attache le contrat reçu (`data`, référence stable une fois en
 * cache) à l'utilisateur exposé par `useAuth`. Aucune page n'a ainsi besoin
 * d'être réécrite : les helpers de `src/utils/roles.js` lisent
 * `user.capabilities` et dérivent du backend, avec repli statique tant que la
 * réponse n'est pas arrivée.
 *
 * À placer sous `QueryClientProvider` ET sous `AuthProvider`.
 */
export default function CapabilitiesSync() {
  const { isAuthenticated, syncCapabilities } = useAuth()
  const { data } = useCapabilities()

  useEffect(() => {
    syncCapabilities(isAuthenticated && data ? data : null)
  }, [isAuthenticated, data, syncCapabilities])

  return null
}
