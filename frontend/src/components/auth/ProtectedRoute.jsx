import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext'
import { hasAppRole, peut, capacitesChargees } from '../../utils/roles'

/**
 * Écran de changement de mot de passe obligatoire. Un compte dont
 * `must_change_password` est vrai (compte badge créé par l'administration,
 * première connexion) ne peut accéder à aucune autre page tant que le mot de
 * passe n'a pas été changé (§10.1, corrigé au LOT 46).
 */
export const FORCED_PASSWORD_PATH = '/changement-mot-de-passe-obligatoire'

/**
 * Garde de route. Deux modes :
 * - `allowedRoles` (historique) : contrôle statique par liste de rôles,
 *   conservé comme repli strictement identique ;
 * - `capacite={{ module, action }}` (P00-06) : quand les capacités backend
 *   sont chargées, c'est le contrat GET /auth/capabilities/ qui décide ;
 *   avant chargement, on retombe sur `allowedRoles` (ou l'accès autorisé si
 *   aucune liste n'est fournie). L'API reste la seule autorité de sécurité.
 */
export default function ProtectedRoute({ children, allowedRoles, capacite }) {
  const { isAuthenticated, loading, user } = useAuth()
  const location = useLocation()

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!isAuthenticated) return <Navigate to="/login" replace />

  // Quelle que soit la page demandée, un changement de mot de passe obligatoire
  // renvoie vers l'écran dédié (sauf cet écran lui-même, pour éviter une boucle).
  if (user?.must_change_password && location.pathname !== FORCED_PASSWORD_PATH) {
    return <Navigate to={FORCED_PASSWORD_PATH} replace state={{ from: location }} />
  }

  if (capacite && capacitesChargees(user)) {
    if (!peut(user, capacite.module, capacite.action)) return <Navigate to="/" replace />
  } else if (allowedRoles && !hasAppRole(user, allowedRoles)) {
    return <Navigate to="/" replace />
  }
  return children
}
