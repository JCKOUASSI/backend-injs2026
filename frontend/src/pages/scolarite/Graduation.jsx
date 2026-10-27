import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

const BADGE_STATUT = {
  BROUILLON: 'secondary', VALIDATION_PENDING: 'info',
  VALIDATED: 'success', REVOKED: 'danger',
}

export default function Graduation() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [diplomes, setDiplomes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [filtres, setFiltres] = useState({ statut: '', annee_id: '', formation_id: '' })
  const [verifToken, setVerifToken] = useState('')
  const [verifResult, setVerifResult] = useState(null)

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/graduation/diplomes/', { params: filtres })
      setDiplomes(res.data.results || res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement des diplômes impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast, filtres])

  useEffect(() => { charger() }, [charger])

  const valider = async (d) => {
    if (!window.confirm(`Valider le diplôme de ${d.nom_complet} (${d.formation}) ?\nLe PDF original sera gelé après validation.`)) return
    setEnCours(true)
    try {
      await api.post(`/graduation/diplomes/${d.id}/valider/`)
      toast.showToast('Diplôme validé et PDF généré.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Validation impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const revoquer = async (d) => {
    const motif = window.prompt(`Motif de révocation du diplôme de ${d.nom_complet} (obligatoire) :`)
    if (!motif) return
    setEnCours(true)
    try {
      await api.post(`/graduation/diplomes/${d.id}/revoquer/`, { motif })
      toast.showToast('Diplôme révoqué.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Révocation impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const verifier = async (e) => {
    e.preventDefault()
    setVerifResult(null)
    if (!verifToken.trim()) return
    try {
      const res = await api.get(`/graduation/verifier/${encodeURIComponent(verifToken.trim())}/`)
      setVerifResult(res.data)
    } catch (err) {
      setVerifResult({ valide: false, raison: 'Erreur de vérification.' })
    }
  }

  return (
    <div className="container-fluid py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h4 mb-0"><i className="bi bi-mortarboard-fill me-2"></i>Diplômation & Documents officiels</h1>
        <button className="btn btn-outline-secondary btn-sm" onClick={charger}>
          <i className="bi bi-arrow-clockwise me-1"></i>Actualiser
        </button>
      </div>

      <div className="card mb-3">
        <div className="card-body">
          <div className="row g-2">
            <div className="col-md-4">
              <label className="form-label small">Statut</label>
              <select className="form-select form-select-sm" value={filtres.statut}
                      onChange={(e) => setFiltres(f => ({ ...f, statut: e.target.value }))}>
                <option value="">Tous</option>
                <option value="BROUILLON">Brouillon</option>
                <option value="VALIDATION_PENDING">En attente</option>
                <option value="VALIDATED">Validé</option>
                <option value="REVOKED">Révoqué</option>
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Année académique</label>
              <input type="number" className="form-control form-control-sm" placeholder="ID année"
                     value={filtres.annee_id} onChange={(e) => setFiltres(f => ({ ...f, annee_id: e.target.value }))} />
            </div>
            <div className="col-md-4">
              <label className="form-label small">Formation</label>
              <input type="number" className="form-control form-control-sm" placeholder="ID formation"
                     value={filtres.formation_id} onChange={(e) => setFiltres(f => ({ ...f, formation_id: e.target.value }))} />
            </div>
          </div>
        </div>
      </div>

      <div className="card">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr>
                <th>Étudiant</th><th>Matricule</th><th>Formation</th><th>Niveau</th>
                <th>Mention</th><th>ECTS</th><th>Statut</th><th>Validation</th>
                {peutAgir && <th className="text-end">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr><td colSpan={9} className="text-center py-4"><div className="spinner-border spinner-border-sm" /></td></tr>
              ) : diplomes.length === 0 ? (
                <tr><td colSpan={9} className="text-center text-muted py-4">Aucun diplôme.</td></tr>
              ) : diplomes.map((d) => (
                <tr key={d.id}>
                  <td>{d.nom_complet}</td>
                  <td>{d.matricule}</td>
                  <td>{d.ref_formation}</td>
                  <td>{d.niveau}</td>
                  <td>{d.mention || '—'}</td>
                  <td>{d.credits_acquis}</td>
                  <td><span className={`badge text-bg-${BADGE_STATUT[d.statut] || 'secondary'}`}>{d.statut_display}</span></td>
                  <td>{d.date_validation ? new Date(d.date_validation).toLocaleDateString() : '—'}</td>
                  {peutAgir && (
                    <td className="text-end">
                      <div className="btn-group btn-group-sm">
                        {d.statut === 'VALIDATION_PENDING' && (
                          <button className="btn btn-outline-success" disabled={enCours} onClick={() => valider(d)}>Valider</button>
                        )}
                        {d.statut === 'VALIDATED' && (
                          <>
                            <a className="btn btn-outline-primary" href={`/api/graduation/diplomes/${d.id}/pdf/`} target="_blank" rel="noreferrer">PDF</a>
                            <button className="btn btn-outline-danger" disabled={enCours} onClick={() => revoquer(d)}>Révoquer</button>
                          </>
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card mt-4">
        <div className="card-header"><strong><i className="bi bi-shield-check me-2"></i>Portail public de vérification</strong></div>
        <div className="card-body">
          <p className="text-muted small">Saisissez le numéro unique (UUID) du diplôme — accessible publiquement, sans authentification requise côté backend.</p>
          <form className="row g-2" onSubmit={verifier}>
            <div className="col-md-8">
              <input type="text" className="form-control" placeholder="Numéro unique (UUID) du diplôme"
                     value={verifToken} onChange={(e) => setVerifToken(e.target.value)} />
            </div>
            <div className="col-md-4">
              <button type="submit" className="btn btn-primary w-100"><i className="bi bi-search me-1"></i>Vérifier</button>
            </div>
          </form>
          {verifResult && (
            <div className={`alert alert-${verifResult.valide ? 'success' : 'danger'} mt-3 mb-0`}>
              {verifResult.valide ? (
                <div>
                  <strong><i className="bi bi-check-circle-fill me-1"></i>Diplôme valide</strong>
                  <ul className="mb-0 mt-2">
                    <li><strong>{verifResult.nom_complet}</strong></li>
                    <li>{verifResult.formation} — {verifResult.niveau}{verifResult.parcours ? ` / ${verifResult.parcours}` : ''}</li>
                    <li>Mention : {verifResult.mention || '—'}</li>
                    <li>Année académique : {verifResult.annee_academique}</li>
                    <li>Délivré le : {verifResult.date_validation ? new Date(verifResult.date_validation).toLocaleDateString() : '—'}</li>
                  </ul>
                </div>
              ) : (
                <div><i className="bi bi-x-circle-fill me-2"></i>{verifResult.raison || 'Aucun diplôme trouvé.'}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

