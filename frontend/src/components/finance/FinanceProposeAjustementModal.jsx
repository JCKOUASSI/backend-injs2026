import { useEffect, useState } from 'react'
import api from '../../services/api'
import { useToast } from '../../context/ToastContext'

function suggestDelta(session) {
  const creneau = Math.round(Number(session?.duree_minutes || 0))
  const realise = Math.round(Number(session?.duree_realisee_minutes || 0))
  const ecart = creneau - realise
  return ecart > 0 ? ecart : ''
}

function suggestMotif(session) {
  const creneau = Math.round(Number(session?.duree_minutes || 0))
  const realise = Math.round(Number(session?.duree_realisee_minutes || 0))
  if (realise < creneau) {
    return `Écart séance : réalisé ${realise} min / créneau ${creneau} min`
  }
  return ''
}

export default function FinanceProposeAjustementModal({
  open,
  session,
  formateurId,
  formateurLabel,
  onClose,
  onSuccess,
}) {
  const { showToast } = useToast()
  const [minutesDelta, setMinutesDelta] = useState('')
  const [motif, setMotif] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    if (open && session) {
      setMinutesDelta(suggestDelta(session))
      setMotif(suggestMotif(session))
    }
  }, [open, session])

  if (!open || !session) return null

  const handleSubmit = async (e) => {
    e.preventDefault()
    const delta = Number(minutesDelta)
    if (!Number.isFinite(delta) || delta === 0) {
      showToast('Indiquez un nombre de minutes non nul (+ ou −)', 'error')
      return
    }
    if (!motif.trim()) {
      showToast('Le motif est obligatoire', 'error')
      return
    }
    setSubmitting(true)
    try {
      await api.post('/formations/finance/ajustements/', {
        session_id: session.session_id,
        formateur_id: formateurId,
        minutes_delta: delta,
        motif: motif.trim(),
      })
      showToast('Ajustement proposé — en attente de validation Direction/Finance', 'success')
      onSuccess?.()
      onClose()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Proposition impossible', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const creneau = Math.round(Number(session.duree_minutes || 0))
  const realise = Math.round(Number(session.duree_realisee_minutes || 0))

  return (
    <div
      className="modal-overlay finance-ajustement-nested"
      onClick={() => !submitting && onClose()}
    >
      <div
        className="modal-content"
        style={{ maxWidth: '520px', width: 'min(96vw, 520px)' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h5>
            <i className="bi bi-arrow-left-right me-2"></i>
            Proposer un ajustement
          </h5>
          <button
            type="button"
            className="btn-close"
            disabled={submitting}
            onClick={onClose}
          >
            &times;
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            <div className="small text-muted mb-3">
              <div><strong>{formateurLabel}</strong></div>
              <div>
                {session.date_journee} — {session.intitule || `Session ${session.numero}`}
                {session.module_intitule && ` · ${session.module_intitule}`}
              </div>
              <div>
                Créneau {creneau} min · Réalisé {realise} min
                {creneau > realise && (
                  <span className="text-warning ms-1">
                    (écart {creneau - realise} min)
                  </span>
                )}
              </div>
            </div>

            <div className="mb-3">
              <label className="form-label small">Minutes à ajouter (+) ou retirer (−)</label>
              <input
                type="number"
                className="form-control form-control-sm"
                value={minutesDelta}
                onChange={(e) => setMinutesDelta(e.target.value)}
                required
                disabled={submitting}
              />
              <div className="form-text">
                Impact paie après validation. Séance réelle modifiée à la validation.
              </div>
            </div>

            <div className="mb-0">
              <label className="form-label small">Motif</label>
              <textarea
                className="form-control form-control-sm"
                rows={3}
                value={motif}
                onChange={(e) => setMotif(e.target.value)}
                required
                disabled={submitting}
              />
            </div>
          </div>
          <div className="modal-footer">
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={submitting}
              onClick={onClose}
            >
              Annuler
            </button>
            <button type="submit" className="btn btn-finance-accent btn-sm" disabled={submitting}>
              {submitting ? 'Envoi…' : 'Soumettre'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
