import { useMemo } from 'react'
import { useAuth } from '../context/AuthContext'
import { useCapabilities } from './useCapabilities'
import { useMesAcces } from './useMesAcces'
import { useFlags } from './useFlag'
import { ARBORESCENCE, PIED_DE_BARRE } from '../menu/arborescence'
import {
  FLAG_CONSOLE,
  SOURCES,
  filtrerArborescence,
  indexParChemin,
  itemAutorise,
  resoudreSource,
} from '../menu/autorisation'

/**
 * Barre latérale pilotée par les droits (RBAC).
 *
 * Retourne l'arborescence **filtrée** pour le compte connecté, la source de la
 * décision (permissions CURP ou capacités legacy), et un index chemin → entrée
 * utilisé par les routes génériques : une URL saisie à la main ne contourne pas
 * le masquage du menu.
 *
 * Deux requêtes, toutes deux en lecture et toutes deux tolérantes aux pannes :
 *
 * - `GET /api/auth/capabilities/`     — capacités projetées (12 modules legacy) ;
 * - `GET /api/habilitations/mes-acces/` — état gouverné + permissions effectives
 *   CURP (clé additive `permissions_effectives`).
 *
 * Ni l'une ni l'autre n'accorde quoi que ce soit : l'API et les vues DRF
 * restent la seule autorité (règle S3). En cas d'échec réseau, le repli
 * statique de `utils/roles.js` s'applique et le menu reste utilisable.
 */
export function useMenuAutorise(arbre = ARBORESCENCE, pied = PIED_DE_BARRE) {
  const { user } = useAuth()
  const { data: capacites, isLoading: chargeCapacites } = useCapabilities()
  const { data: mesAcces, isLoading: chargeAcces } = useMesAcces()
  // Drapeau kill-switch de la console CURP, évalué par le serveur pour le
  // compte courant : voir `estEntreeConsole` (menu/autorisation.js).
  const flags = useFlags()

  const utilisateur = useMemo(
    () => (user ? { ...user, capabilities: capacites ?? user.capabilities ?? null } : null),
    [user, capacites],
  )

  return useMemo(() => {
    const contexte = resoudreSource({ user: utilisateur, mesAcces })
    contexte.drapeauConsole = flags?.[FLAG_CONSOLE] === true
    const sections = filtrerArborescence(arbre, contexte)
    return {
      sections,
      pied: pied.filter((item) => itemAutorise(item, contexte)),
      source: contexte.source,
      gouverne: contexte.gouverne,
      estCurp: contexte.source === SOURCES.CURP,
      nombreCodes: contexte.codes.size,
      parChemin: indexParChemin(sections),
      enChargement: (chargeCapacites || chargeAcces) && !utilisateur,
      compte: mesAcces?.compte ?? null,
      attributions: mesAcces?.attributions ?? [],
    }
  }, [arbre, pied, utilisateur, mesAcces, chargeCapacites, chargeAcces, flags])
}

export default useMenuAutorise
