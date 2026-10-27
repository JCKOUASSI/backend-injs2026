import { useState } from 'react'

const STEPS = [
  {
    message: 'Archiver ce module ?',
    detail: 'Les données (notes, présences, étudiants) seront conservées et consultables dans l\'espace Archives.',
    confirmLabel: 'Continuer',
    variant: 'warning',
  },
  {
    message: 'Confirmez l\'archivage',
    detail: 'Ce module disparaîtra des listes opérationnelles : secrétariat, encadrants, statistiques et filtres du tableau de bord.',
    confirmLabel: 'Je comprends',
    variant: 'warning',
  },
  {
    message: 'Dernière confirmation',
    detail: 'Seul le rôle Archiviste pourra consulter ces données. Le désarchivage reste possible depuis l\'espace Archives (secrétariat / direction).',
    confirmLabel: 'Archiver définitivement',
    variant: 'danger',
  },
]

export default function TripleConfirmModal({ title, subject, onConfirm, onCancel }) {
  const [step, setStep] = useState(0)
  const current = STEPS[step]
  const isLast = step === STEPS.length - 1

  const btnDanger = {
    background: '#c62828', color: '#fff', border: 'none',
    padding: '0.45rem 1.2rem', borderRadius: 6, fontWeight: 500, cursor: 'pointer', fontSize: '0.9rem',
  }
  const btnWarning = {
    background: '#e69700', color: '#fff', border: 'none',
    padding: '0.45rem 1.2rem', borderRadius: 6, fontWeight: 500, cursor: 'pointer', fontSize: '0.9rem',
  }

  const handleNext = () => {
    if (isLast) {
      onConfirm()
    } else {
      setStep(s => s + 1)
    }
  }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" style={{ maxWidth: '440px' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h5>
            <i
              className={`bi bi-${current.variant === 'danger' ? 'exclamation-triangle' : 'archive'} me-2`}
              style={{ color: current.variant === 'danger' ? '#f5c10b' : '#e69700' }}
            />
            {title || 'Archivage'} — étape {step + 1}/{STEPS.length}
          </h5>
          <button className="btn-close" onClick={onCancel}>&times;</button>
        </div>
        <div className="modal-body">
          {subject && (
            <p style={{ fontWeight: 600, marginBottom: '0.75rem', color: 'var(--text)' }}>
              <i className="bi bi-journal-bookmark me-1" />
              {subject}
            </p>
          )}
          <p style={{ marginBottom: current.detail ? '0.5rem' : 0 }}>{current.message}</p>
          {current.detail && (
            <p className="text-muted small" style={{ marginBottom: 0 }}>{current.detail}</p>
          )}
          <div style={{ display: 'flex', gap: '0.35rem', marginTop: '1rem' }}>
            {STEPS.map((_, i) => (
              <div
                key={i}
                style={{
                  flex: 1, height: 4, borderRadius: 2,
                  background: i <= step ? (i === STEPS.length - 1 ? '#c62828' : '#e69700') : '#e2e8f0',
                  transition: 'background 0.2s',
                }}
              />
            ))}
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>Annuler</button>
          <button
            style={current.variant === 'danger' ? btnDanger : btnWarning}
            onClick={handleNext}
          >
            {current.confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
