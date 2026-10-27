import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'

const STATUTS = ['', 'PREPARATION', 'CONTROLE', 'CALCUL', 'DELIBERATION', 'DECISION', 'PV_GENERE', 'VALIDE', 'VERROUILLE', 'PUBLIE']
const BADGE_STATUT = {
  PREPARATION: 'secondary', CONTROLE: 'info', CALCUL: 'primary',
  DELIBERATION: 'warning', DECISION: 'warning', PV_GENERE: 'info',
  VALIDE: 'success', VERROUILLE: 'dark', PUBLIE: 'success',
}

export default function Jurys() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [sessions, setSessions] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [filtres, setFiltres] = useState({ statut: '', annee_id: '', formation_id: '' })
  const [options, setOptions] = useState({ annees: [], formations: [] })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/juries/sessions/', { params: filtres })
      setSessions(res.data.results || res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.detail || 'Chargement des sessions de jury impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast, filtres])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    Promise.all([
      api.get('/scolarite/ref/annees/'),
      api.get('/scolarite/ref/formations/'),
    ])
      .then(([annees, formations]) => setOptions({
        annees: annees.data?.results || annees.data || [],
        formations: formations.data?.results || formations.data || [],
      }))
      .catch(() => toast.showToast('Référentiels indisponibles.', 'error'))
  }, [peutAgir, toast])

  const action = async (session, act) => {
    if (!window.confirm(`Action « ${act} » sur la session ${session.libelle || session.id} ?`)) return
    setEnCours(true)
    try {
      await api.post(`/juries/sessions/${session.id}/action/`, { action: act })
      toast.showToast(`Action « ${act} » exécutée.`)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.detail || 'Action impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  return (
    <div className="container-fluid py-4">
      <div className="d-flex justify-content-between align-items-center mb-3">
        <h1 className="h4 mb-0"><i className="bi bi-clipboard-check me-2"></i>Sessions de jury LMD</h1>
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
                {STATUTS.map(s => <option key={s} value={s}>{s || 'Tous'}</option>)}
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Année académique</label>
              <select className="form-select form-select-sm" value={filtres.annee_id}
                      onChange={(e) => setFiltres(f => ({ ...f, annee_id: e.target.value }))}>
                <option value="">Toutes</option>
                {options.annees.map(a => <option key={a.id} value={a.id}>{a.libelle}</option>)}
              </select>
            </div>
            <div className="col-md-4">
              <label className="form-label small">Formation</label>
              <select className="form-select form-select-sm" value={filtres.formation_id}
                      onChange={(e) => setFiltres(f => ({ ...f, formation_id: e.target.value }))}>
                <option value="">Toutes</option>
                {options.formations.map(f => <option key={f.id} value={f.id}>{f.intitule}</option>)}
              </select>
            </div>
          </div>
        </div>
      </div>


      <div className="card">
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0">
            <thead className="table-light">
              <tr>
                <th>Session</th><th>Année</th><th>Formation</th><th>Niveau</th>
                <th>Type</th><th>Statut</th>
                {peutAgir && <th className="text-end">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr><td colSpan={7} className="text-center py-4"><div className="spinner-border spinner-border-sm" /></td></tr>
              ) : sessions.length === 0 ? (
                <tr><td colSpan={7} className="text-center text-muted py-4">Aucune session de jury.</td></tr>
              ) : sessions.map((s) => (
                <tr key={s.id}>
                  <td>{s.libelle || `Session #${s.id}`}</td>
                  <td>{s.annee_academique_id}</td>
                  <td>{s.ref_formation_id}</td>
                  <td>{s.niveau_id}</td>
                  <td>{s.type_session}</td>
                  <td><span className={`badge text-bg-${BADGE_STATUT[s.statut] || 'secondary'}`}>{s.statut}</span></td>
                  {peutAgir && (
                    <td className="text-end">
                      <div className="btn-group btn-group-sm">
                        {s.statut === 'PREPARATION' && (
                          <button className="btn btn-outline-info" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Contrôler</button>
                        )}
                        {s.statut === 'CONTROLE' && (
                          <button className="btn btn-outline-primary" disabled={enCours}
                                  onClick={() => action(s, 'calcul')}>Calculer</button>
                        )}
                        {s.statut === 'CALCUL' && (
                          <button className="btn btn-outline-warning" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Délibérer</button>
                        )}
                        {s.statut === 'DELIBERATION' && (
                          <button className="btn btn-outline-warning" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Décider</button>
                        )}
                        {s.statut === 'DECISION' && (
                          <button className="btn btn-outline-info" disabled={enCours}
                                  onClick={() => action(s, 'generer_pv')}>Générer PV</button>
                        )}
                        {s.statut === 'PV_GENERE' && (
                          <button className="btn btn-outline-success" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Valider</button>
                        )}
                        {s.statut === 'VALIDE' && (
                          <button className="btn btn-outline-dark" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Verrouiller</button>
                        )}
                        {s.statut === 'VERROUILLE' && (
                          <button className="btn btn-outline-success" disabled={enCours}
                                  onClick={() => action(s, 'publier')}>Publier</button>
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
    </div>
  )
}

