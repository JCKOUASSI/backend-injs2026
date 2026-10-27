/** Petits éléments partagés de la console CURP (U4). */
import { libelleCanal, libelleStatut } from '@/utils/habilitations'

export function BadgeSensible({ avecLabel = true }) {
  return (
    <span className="hab-badge-sensible" title="Rôle sensible : traçabilité et contrôles renforcés">
      <i className="bi bi-shield-exclamation me-1"></i>
      {avecLabel ? 'Sensible' : ''}
    </span>
  )
}

export function BadgeCanal({ canal }) {
  if (!canal || canal === 'LES_DEUX') return null
  return (
    <span className="hab-badge-canal" title="Canal d'accès imposé">
      <i className={`bi ${canal === 'MOBILE' ? 'bi-phone' : 'bi-window'} me-1`}></i>
      {libelleCanal(canal)}
    </span>
  )
}

export function BadgeStatut({ statut }) {
  return <span className={`hab-statut hab-statut-${statut}`}>{libelleStatut(statut)}</span>
}

/** Bandeau permanent de traçabilité (C2 §2). */
export function BandeauTraçabilite() {
  return (
    <div className="hab-bandeau" role="note">
      <i className="bi bi-journal-lock"></i>
      <span>
        <strong>Toute action sur les habilitations est tracée</strong> dans un journal
        immuable et horodaté.
      </span>
    </div>
  )
}

export function Message403({ detail }) {
  return (
    <div className="hab-403" data-testid="hab-403">
      <h4><i className="bi bi-shield-lock me-2"></i>Accès refusé</h4>
      <p className="mb-1">
        Vous ne disposez pas des droits nécessaires, ou la console d'habilitation
        n'est pas activée sur cet environnement.
      </p>
      {detail && <p className="hab-muted mb-0">{detail}</p>}
    </div>
  )
}

export function EnChargement({ message = 'Chargement…' }) {
  return (
    <div className="hab-muted" role="status">
      <span className="spinner-border spinner-border-sm me-2" aria-hidden="true" />
      {message}
    </div>
  )
}

export function nomCompte(compte) {
  const p = compte?.personne
  if (p && (p.nom || p.prenoms)) return [p.prenoms, p.nom].filter(Boolean).join(' ')
  return compte?.username || '—'
}
