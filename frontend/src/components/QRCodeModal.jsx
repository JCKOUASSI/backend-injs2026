import { useState, useEffect, useRef } from 'react'
import QRCode from 'qrcode'
import api from '../services/api'
import ConfirmModal from './ConfirmModal'

// Badge URL must point to the BACKEND (Django serves /dashboard/badge/), not the frontend SPA.
const BADGE_BASE_URL = import.meta.env.VITE_BADGE_BASE_URL
  || (import.meta.env.VITE_API_URL || '').replace(/\/api\/?$/, '')
  || window.location.origin

export default function QRCodeModal({
  formationId,
  sessionId,
  moduleId = null,
  moduleLabel = '',
  moduleGroupe = '',
  isOpen,
  onClose,
}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [token, setToken] = useState(null)
  const [qrMeta, setQrMeta] = useState(null)
  const [noActiveQr, setNoActiveQr] = useState(false)
  const [confirmRegenerate, setConfirmRegenerate] = useState(false)
  const canvasRef = useRef(null)

  useEffect(() => {
    if (isOpen && formationId && sessionId) loadActiveQR()
    if (isOpen && !sessionId) {
      setError('Séance non sélectionnée.')
      setToken(null)
      setQrMeta(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [isOpen, formationId, sessionId, moduleId])

  useEffect(() => {
    if (token && canvasRef.current) {
      const badgeUrl = `${BADGE_BASE_URL}/dashboard/badge/?token=${token}`
      QRCode.toCanvas(canvasRef.current, badgeUrl, {
        width: 220,
        margin: 2,
        color: { dark: '#000000', light: '#ffffff' },
        errorCorrectionLevel: 'H',
      }).catch(console.error)
    }
  }, [token])

  const buildParams = () => {
    const params = { session_id: sessionId }
    if (moduleId) params.module_id = moduleId
    return params
  }

  const applyQrPayload = (data) => {
    // Garde-fou contre une réponse tardive (race) : le QR reçu doit
    // correspondre à la séance actuellement affichée.
    if (data.session && sessionId && String(data.session) !== String(sessionId)) {
      return false
    }
    if (moduleId && data.module_id && String(data.module_id) !== String(moduleId)) {
      setError(
        `QR refusé : ce code appartient à « ${data.module_intitule || '?'} » `
        + `(${data.module_groupe || 'autre groupe'}), pas à ce module.`
      )
      setToken(null)
      setQrMeta(null)
      return false
    }
    setQrMeta({
      moduleIntitule: data.module_intitule || moduleLabel,
      moduleGroupe: data.module_groupe || moduleGroupe,
      sessionIntitule: data.session_intitule || '',
    })
    setToken(data.token)
    return true
  }

  const loadActiveQR = async () => {
    setLoading(true)
    setError(null)
    setToken(null)
    setQrMeta(null)
    setNoActiveQr(false)
    try {
      const response = await api.get(
        `/formations/superviseur/${formationId}/qr/`,
        { params: buildParams() },
      )
      if (!applyQrPayload(response.data)) {
        setNoActiveQr(false)
      }
    } catch (err) {
      if (err.response?.status === 404) {
        setNoActiveQr(true)
      } else {
        setError(err.response?.data?.detail || 'Erreur lors du chargement du QR code')
      }
    } finally {
      setLoading(false)
    }
  }

  const generateAndShowQR = async () => {
    setLoading(true)
    setError(null)
    setNoActiveQr(false)
    try {
      const body = moduleId ? { module_id: moduleId } : {}
      const response = await api.post(
        `/formations/${formationId}/sessions/${sessionId}/generate-qr/`,
        body,
      )
      applyQrPayload(response.data)
    } catch (err) {
      setError(err.response?.data?.detail || 'Erreur lors de la génération du QR code')
    } finally {
      setLoading(false)
    }
  }

  const handleRegenerateClick = () => {
    setConfirmRegenerate(true)
  }

  const downloadQR = () => {
    if (!canvasRef.current) return
    const filename = `qr_seance_${formationId}_${sessionId}.png`
    const link = document.createElement('a')
    link.href = canvasRef.current.toDataURL('image/png')
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const scopeLabel = moduleGroupe || qrMeta?.moduleGroupe
  const moduleTitle = moduleLabel || qrMeta?.moduleIntitule

  if (!isOpen) return null

  return (
    <>
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '420px' }}>
          <div className="modal-header">
            <h5>
              <i className="bi bi-qr-code me-2"></i>
              QR Code — Séance
            </h5>
            <button className="btn-close" onClick={onClose}>&times;</button>
          </div>
          <div className="modal-body text-center">
            {(moduleTitle || scopeLabel) && (
              <div className="alert alert-info py-2 mb-3 text-start" style={{ fontSize: '0.9rem' }}>
                <div><strong>{moduleTitle || 'Module'}</strong></div>
                {scopeLabel && <div className="text-muted">{scopeLabel}</div>}
                {qrMeta?.sessionIntitule && (
                  <div className="small mt-1">Séance : {qrMeta.sessionIntitule}</div>
                )}
              </div>
            )}
            {loading && <div className="loading"><div className="spinner"></div></div>}
            {error && <div className="alert alert-danger"><i className="bi bi-exclamation-triangle me-1"></i>{error}</div>}
            {noActiveQr && !loading && !error && (
              <p className="text-muted mb-0">
                <i className="bi bi-info-circle me-1"></i>
                Aucun QR code actif pour cette séance. Générez-en un ci-dessous.
              </p>
            )}
            <div style={{ display: token && !loading ? 'inline-block' : 'none', padding: '1rem', border: '2px solid #e2e8f0', borderRadius: '12px', marginBottom: '1rem', background: '#fff' }}>
              <canvas ref={canvasRef} />
            </div>
            {token && !loading && scopeLabel && (
              <p className="fw-semibold mb-2" style={{ color: 'var(--navy)' }}>
                {scopeLabel}
              </p>
            )}
          </div>
          <div className="modal-footer" style={{ justifyContent: 'center' }}>
            {token && !loading && (
              <button onClick={downloadQR} className="btn btn-dfrc btn-sm">
                <i className="bi bi-download me-1"></i>Télécharger
              </button>
            )}
            {token && !loading ? (
              <button onClick={handleRegenerateClick} className="btn btn-outline-warning btn-sm" disabled={loading}>
                <i className="bi bi-arrow-clockwise me-1"></i>Régénérer
              </button>
            ) : !loading && sessionId && (
              <button onClick={generateAndShowQR} className="btn btn-dfrc btn-sm" disabled={loading}>
                <i className="bi bi-qr-code me-1"></i>Générer le QR code
              </button>
            )}
            <button onClick={onClose} className="btn btn-secondary btn-sm">
              Fermer
            </button>
          </div>
        </div>
      </div>

      {confirmRegenerate && (
        <ConfirmModal
          message="Régénérer le QR code ?"
          detail="L'ancien QR code sera immédiatement invalidé. Les participants devront scanner le nouveau code pour badgear."
          confirmLabel="Régénérer"
          cancelLabel="Annuler"
          variant="primary"
          onConfirm={() => {
            setConfirmRegenerate(false)
            generateAndShowQR()
          }}
          onCancel={() => setConfirmRegenerate(false)}
        />
      )}
    </>
  )
}
