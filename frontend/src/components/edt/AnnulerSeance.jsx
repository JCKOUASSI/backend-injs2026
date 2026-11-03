import { useState } from 'react'
import api from '../../services/api'
import { messageErreurApi } from '../../utils/edts'

/**
 * GET-INJS — annulation (ou réactivation) d'une séance, **motivée et traçable**.
 *
 * Passe par `POST /api/edts/lmd/items/<id>/cancel/` : désactivation logique
 * (`actif = false`), aucune suppression physique, motif obligatoire, action
 * journalisée et réversible (`reactiver: true`).
 *
 * Le serveur reste seul juge : un refus (409 sur un EDT publié, 400 sans motif)
 * est affiché tel quel avec son code, et l'écran ne ferme pas.
 */

export default function AnnulerSeance({ affectation, reactiver = false, onClose, onDone }) {
  const [motif, setMotif] = useState('')
  const [envoi, setEnvoi] = useState(false)
  const [erreur, setErreur] = useState('')

  const envoyer = async () => {
    setEnvoi(true)
    setErreur('')
    try {
      await api.post(`/edts/lmd/items/${affectation.id}/cancel/`, {
        motif: motif.trim(),
        ...(reactiver ? { reactiver: true } : {}),
      })
      onDone?.()
    } catch (e) {
      setErreur(messageErreurApi(e, 'Opération refusée.'))
    } finally {
      setEnvoi(false)
    }
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content"
        style={{ maxWidth: 620 }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label={reactiver ? 'Réactiver la séance' : 'Annuler la séance'}
      >
        <div className="modal-header">
          <h5 className="modal-title">
            <i className={`bi ${reactiver ? 'bi-arrow-counterclockwise' : 'bi-slash-circle'} me-2`} />
            {reactiver ? 'Réactiver' : 'Annuler'} « {affectation.intitule || 'séance'} »
          </h5>
          <button type="button" className="btn-close" onClick={onClose} aria-label="Fermer" />
        </div>

        <div className="modal-body">
          <p className="small text-muted">
            {reactiver
              ? 'La séance redevient active dans l’emploi du temps et redevient visible des étudiants.'
              : 'La séance est désactivée : elle disparaît de l’emploi du temps sans être supprimée, et reste réactivable.'}
          </p>

          <label className="form-label" htmlFor="motif-annulation">
            Motif <span className="text-danger">*</span>
          </label>
          <textarea
            id="motif-annulation"
            className="form-control"
            rows={3}
            value={motif}
            onChange={(e) => setMotif(e.target.value)}
            placeholder="Ex : enseignant indisponible, salle fermée pour travaux…"
            required
          />
          <div className="form-text">
            Ce motif est journalisé et restera attaché à la séance (traçabilité).
          </div>

          {erreur && (
            <div className="alert alert-danger mt-3 mb-0" role="alert">{erreur}</div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-outline-secondary" onClick={onClose}>
            Fermer
          </button>
          <button
            type="button"
            className={`btn ${reactiver ? 'btn-success' : 'btn-danger'}`}
            disabled={!motif.trim() || envoi}
            onClick={envoyer}
          >
            {envoi ? 'Envoi…' : (reactiver ? 'Réactiver' : 'Annuler la séance')}
          </button>
        </div>
      </div>
    </div>
  )
}
