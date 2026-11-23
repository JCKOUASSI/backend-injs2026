import { useEffect, useId, useRef } from 'react'

/**
 * Boîte de confirmation générique pour les actions sensibles
 * (validation d'inscription, suppression, révocation…).
 *
 * Accessibilité (WCAG 2.2 AA) :
 * - rôle `dialog` + `aria-modal`, titre et description reliés par identifiant ;
 * - touche Échap = annulation ;
 * - focus placé sur l'action de confirmation à l'ouverture, puis rendu à
 *   l'élément d'origine à la fermeture ;
 * - bouton de fermeture doté d'un nom accessible (le « × » seul ne veut rien
 *   dire pour un lecteur d'écran).
 *
 * Apparence : boutons du socle (`btn btn-danger` / `btn btn-success`) au lieu
 * de styles inline, pour hériter des états survol/focus/désactivé.
 */
export default function ConfirmModal({
  message,
  detail,
  confirmLabel = 'Confirmer',
  cancelLabel = 'Annuler',
  variant = 'danger',
  onConfirm,
  onCancel,
}) {
  const titreId = useId()
  const descId = useId()
  const actionRef = useRef(null)
  const retourFocusRef = useRef(null)

  useEffect(() => {
    retourFocusRef.current = document.activeElement
    // Le focus doit entrer dans la boîte de dialogue dès son ouverture.
    const t = setTimeout(() => actionRef.current?.focus(), 0)
    const onKeyDown = (e) => { if (e.key === 'Escape') onCancel?.() }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      clearTimeout(t)
      document.removeEventListener('keydown', onKeyDown)
      const cible = retourFocusRef.current
      if (cible && typeof cible.focus === 'function') cible.focus()
    }
  }, [onCancel])

  const classeAction = variant === 'danger' ? 'btn btn-danger' : 'btn btn-success'

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal-content"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titreId}
        aria-describedby={descId}
        style={{ maxWidth: '420px' }}
        onClick={e => e.stopPropagation()}
      >
        <div className="modal-header">
          <h5 id={titreId}>
            <i
              className={`bi bi-${variant === 'danger' ? 'exclamation-triangle' : 'question-circle'} me-2`}
              aria-hidden="true"
              style={{ color: variant === 'danger' ? 'var(--injs-warning)' : 'var(--injs-success)' }}
            />
            Confirmation
          </h5>
          <button type="button" className="btn-close" onClick={onCancel} aria-label="Fermer la boîte de dialogue">
            &times;
          </button>
        </div>
        <div className="modal-body" id={descId}>
          <p style={{ marginBottom: detail ? '0.5rem' : 0 }}>{message}</p>
          {detail && <p className="text-muted small" style={{ marginBottom: 0 }}>{detail}</p>}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn-outline-secondary" onClick={onCancel}>{cancelLabel}</button>
          <button type="button" ref={actionRef} className={classeAction} onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  )
}
