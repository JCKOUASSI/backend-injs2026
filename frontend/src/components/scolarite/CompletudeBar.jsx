import React from 'react'

/** Barre de complétude du dossier de pièces justificatives. */
export default function CompletudeBar({ validees, total, taux }) {
  const pourcentage = taux ?? (total ? Math.round((validees * 100) / total) : 0)
  const variante = pourcentage === 100 ? 'success' : pourcentage >= 50 ? 'warning' : 'danger'
  return (
    <div className="d-flex align-items-center gap-2">
      <div className="progress flex-grow-1" style={{ height: '0.5rem', minWidth: '80px' }}>
        <div
          className={`progress-bar bg-${variante}`}
          style={{ width: `${pourcentage}%` }}
          role="progressbar"
          aria-valuenow={pourcentage}
          aria-valuemin={0}
          aria-valuemax={100}
        />
      </div>
      <small className="text-muted text-nowrap">{validees}/{total}</small>
    </div>
  )
}
