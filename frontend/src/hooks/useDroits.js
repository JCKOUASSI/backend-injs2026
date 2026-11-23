import { useMemo } from 'react'
import { useAuth } from '../context/AuthContext'
import { useCapabilities } from './useCapabilities'
import { peut as peutStatic, niveauAcces, perimetresAcces } from '../utils/roles'

/**
 * Point d'accès unique aux droits UI (P00-06) :
 * - `peut(module, action)` suit les capacités backend dès qu'elles sont
 *   chargées, sinon le repli statique ;
 * - `niveau` (N0–N4 provisoire) et `perimetres` viennent du backend ;
 * - `userAugmente` est l'objet utilisateur avec `capabilities` attaché,
 *   directement compatible avec les helpers de `utils/roles`.
 *
 * Ne remplace aucune vérification côté API : les vues DRF restent l'autorité.
 */
export function useDroits() {
  const { user } = useAuth()
  const { data: capabilities, isLoading, error } = useCapabilities()

  const userAugmente = useMemo(
    () => (user ? { ...user, capabilities } : null),
    [user, capabilities],
  )

  return useMemo(
    () => ({
      user: userAugmente,
      // Tant que rien n'est chargé, les capacités sont absentes et le repli
      // statique s'applique ; `charge` passe à vrai à la première réponse.
      charge: Boolean(capabilities),
      enChargement: isLoading,
      erreur: error ?? null,
      capacites: capabilities?.capacites ?? null,
      niveau: capabilities ? niveauAcces(userAugmente) : null,
      perimetres: capabilities ? perimetresAcces(userAugmente) : null,
      peut: (module, action) => peutStatic(userAugmente, module, action),
    }),
    [userAugmente, capabilities, isLoading, error],
  )
}
