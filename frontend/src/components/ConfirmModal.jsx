export default function ConfirmModal({ message, detail, confirmLabel = 'Confirmer', cancelLabel = 'Annuler', variant = 'danger', onConfirm, onCancel }) {
  const btnDanger = { background: '#c62828', color: '#fff', border: 'none', padding: '0.45rem 1.2rem', borderRadius: 6, fontWeight: 500, cursor: 'pointer', fontSize: '0.9rem' }
  const btnPrimary = { background: 'var(--ci-success)', color: '#fff', border: 'none', padding: '0.45rem 1.2rem', borderRadius: 6, fontWeight: 500, cursor: 'pointer', fontSize: '0.9rem' }

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" style={{ maxWidth: '400px' }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h5>
            <i className={`bi bi-${variant === 'danger' ? 'exclamation-triangle' : 'question-circle'} me-2`}
               style={{ color: variant === 'danger' ? '#f5c10b' : 'var(--ci-success)' }}></i>
            Confirmation
          </h5>
          <button className="btn-close" onClick={onCancel}>&times;</button>
        </div>
        <div className="modal-body">
          <p style={{ marginBottom: detail ? '0.5rem' : 0 }}>{message}</p>
          {detail && <p className="text-muted small" style={{ marginBottom: 0 }}>{detail}</p>}
        </div>
        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onCancel}>{cancelLabel}</button>
          <button style={variant === 'danger' ? btnDanger : btnPrimary} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
