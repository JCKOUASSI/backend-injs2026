/**
 * Confirmation explicite des gestes sensibles/irréversibles (C2 §2).
 * Nomme l'action et ses conséquences et exige la saisie d'un motif avant de
 * permettre la validation. Aucune action n'est lancée sans motif.
 */
import { useState } from 'react'

export default function MotifModal({
  titre,
  action,
  consequences,
  confirmationLabel = 'Confirmer l’action',
  variant = 'danger',
  enCours = false,
  onConfirmer,
  onAnnuler,
}) {
  const [motif, setMotif] = useState('')
  const motifOk = motif.trim().length >= 8

  return (
    <div className="modal-overlay" onClick={onAnnuler}>
      <div className="modal-content" role="dialog" aria-modal="true" style={{ maxWidth: '480px' }} onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h5>
            <i className={`bi ${variant === 'danger' ? 'bi-exclamation-triangle' : 'bi-pencil-square'} me-2`} />
            {titre}
          </h5>
          <button className="btn-close" onClick={onAnnuler} aria-label="Fermer">&times;</button>
        </div>
        <div className="modal-body">
          <p className="fw-semibold mb-1">{action}</p>
          {consequences && <p className="text-muted small mb-3">{consequences}</p>}
          <label className="form-label" htmlFor="motif-action">
            Motif de l'action (obligatoire, conservé au journal)
          </label>
          <textarea
            id="motif-action"
            className="form-control"
            rows="3"
            value={motif}
            data-testid="motif-input"
            onChange={(e) => setMotif(e.target.value)}
            placeholder="Décrivez la raison de cette action…"
          />
          {!motifOk && motif.length > 0 && (
            <div className="form-text text-danger">Le motif doit comporter au moins 8 caractères.</div>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onAnnuler} disabled={enCours}>Annuler</button>
          <button
            className={`btn ${variant === 'danger' ? 'btn-danger' : 'btn-success'}`}
            disabled={!motifOk || enCours}
            data-testid="motif-confirmation"
            onClick={() => onConfirmer(motif.trim())}
          >
            {enCours ? 'Traitement…' : confirmationLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
