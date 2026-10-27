/**
 * SensibleBadge — signal visuel réutilisable de sensibilité (couche IMPACT).
 *
 * Exploite UNIQUEMENT la classification déjà existante dans CURP :
 * - rôles : fanion `sensible` du catalogue de l'annexe A1 (ROLES_SENSIBLES) ;
 * - permissions : criticité NORMALE / SENSIBLE / CRITIQUE du modèle
 *   PermissionMetier (crossée avec PERMISSIONS_CRITIQUES par le service).
 * Aucune nouvelle taxonomie n'est introduite : toute valeur hors
 * classification ne produit aucun badge.
 *
 * Réutilise le style visuel existant de la console (hab-badge-sensible).
 */
const TITRES = {
  role: 'Rôle sensible : traçabilité et contrôles renforcés (MFA, double validation).',
  permission:
    'Permission sensible : motif obligatoire et journalisation renforcée.',
  acces: 'Accès sensible dérivé d’un rôle ou d’une dérogation sensible.',
  utilisateur:
    'Compte privilégié : détient au moins un rôle sensible actif.',
}

export default function SensibleBadge({ type = 'role', niveau, critique = false }) {
  // Rôle : fanion booléen. Permission/acces : niveau NORMALE/SENSIBLE/CRITIQUE.
  const sensible = niveau === true || niveau === 'SENSIBLE' || niveau === 'CRITIQUE' || critique
  if (!sensible) return null
  const estCritique = niveau === 'CRITIQUE' || critique
  const titre = TITRES[type] || TITRES.role
  return (
    <span
      className={`hab-badge-sensible ${estCritique ? 'hab-badge-critique' : ''}`}
      title={titre}
      data-testid={`sensible-badge-${type}`}
    >
      <i className="bi bi-shield-exclamation me-1" aria-hidden="true"></i>
      {estCritique ? 'Critique' : 'Sensible'}
    </span>
  )
}

/** Variante d'affichage compacte (icône seule), réutilisée dans les tableaux. */
export function SensibleIcone({ type = 'role', niveau, critique = false }) {
  const sensible = niveau === true || niveau === 'SENSIBLE' || niveau === 'CRITIQUE' || critique
  if (!sensible) return null
  const estCritique = niveau === 'CRITIQUE' || critique
  return (
    <i
      className={`bi bi-shield-exclamation ${estCritique ? 'text-danger' : 'text-warning'} me-1`}
      title={TITRES[type] || TITRES.role}
      data-testid={`sensible-icone-${type}`}
    />
  )
}
