import React, { useCallback, useEffect, useState } from 'react'
import api from '../../services/api'
import '../../styles/jurys.css'
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
  const [optionsChargees, setOptionsChargees] = useState(false)

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
    if (!peutAgir) { setOptionsChargees(true); return }
    Promise.all([
      api.get('/scolarite/ref/annees/'),
      api.get('/scolarite/ref/formations/'),
    ])
      .then(([annees, formations]) => setOptions({
        annees: annees.data?.results || annees.data || [],
        formations: formations.data?.results || formations.data || [],
      }))
      .catch(() => toast.showToast('Référentiels indisponibles.', 'error'))
      .finally(() => setOptionsChargees(true))
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

  const nbEnCours = sessions.filter(s => !['VALIDE', 'VERROUILLE', 'PUBLIE'].includes(s.statut)).length
  const nbDeliberation = sessions.filter(s => ['DELIBERATION', 'DECISION'].includes(s.statut)).length
  const nbPubliees = sessions.filter(s => s.statut === 'PUBLIE').length
  const libelleAnnee = (id) => options.annees.find(a => String(a.id) === String(id))?.libelle || id
  const libelleFormation = (id) => options.formations.find(f => String(f.id) === String(id))?.intitule || id
  const ETAPES = ['PREPARATION', 'CONTROLE', 'CALCUL', 'DELIBERATION', 'DECISION', 'PV_GENERE', 'VALIDE', 'VERROUILLE', 'PUBLIE']

  return (
    <div className="container-fluid py-4 jury-page">
      <header className="jury-hero">
        <div className="jury-hero-main">
          <span className="jury-hero-kicker"><i className="bi bi-award-fill"></i>Scolarité · Délibérations LMD</span>
          <h1 className="jury-title"><i className="bi bi-clipboard-check"></i>Sessions de jury LMD</h1>
          <p className="jury-sub">Pilotez chaque session de la préparation à la publication : contrôle des notes, calcul, délibération, procès-verbal et verrouillage.</p>
          <div className="jury-flow" aria-hidden="true">
            {ETAPES.map((e, i) => (
              <React.Fragment key={e}>
                <span className={`jury-flow-step${e === 'PUBLIE' ? ' is-final' : ''}`}><b>{i + 1}</b>{e}</span>
                {i < ETAPES.length - 1 && <i className="bi bi-chevron-right jury-flow-arrow"></i>}
              </React.Fragment>
            ))}
          </div>
        </div>
        <div className="jury-hero-actions">
          <button className="btn jury-btn-refresh" onClick={charger}>
            <i className="bi bi-arrow-clockwise me-1"></i>Actualiser
          </button>
        </div>
      </header>

      <section className="jury-kpis" aria-label="Indicateurs des sessions de jury">
        <div className="jury-kpi"><div><span className="jury-kpi-label">Sessions totales</span><span className="jury-kpi-value">{sessions.length}</span></div><span className="jury-kpi-icon is-indigo"><i className="bi bi-clipboard-data"></i></span></div>
        <div className="jury-kpi"><div><span className="jury-kpi-label">En cours</span><span className="jury-kpi-value">{nbEnCours}</span></div><span className="jury-kpi-icon is-amber"><i className="bi bi-hourglass-split"></i></span></div>
        <div className="jury-kpi"><div><span className="jury-kpi-label">En délibération</span><span className="jury-kpi-value">{nbDeliberation}</span></div><span className="jury-kpi-icon is-violet"><i className="bi bi-people"></i></span></div>
        <div className="jury-kpi"><div><span className="jury-kpi-label">Publiées</span><span className="jury-kpi-value">{nbPubliees}</span></div><span className="jury-kpi-icon is-green"><i className="bi bi-patch-check"></i></span></div>
      </section>

      <div className="card jury-panel">
        <div className="jury-panel-head">
          <h2 className="jury-panel-title"><i className="bi bi-funnel"></i>Filtrer les sessions</h2>
          <span className="jury-count">{sessions.length} session{sessions.length > 1 ? 's' : ''}</span>
        </div>
        <div className="jury-filters">
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


      <div className="card jury-panel">
        <div className="jury-panel-head">
          <h2 className="jury-panel-title"><i className="bi bi-table"></i>Sessions</h2>
          <span className="jury-count">{chargement ? 'Chargement…' : `${sessions.length} résultat${sessions.length > 1 ? 's' : ''}`}</span>
        </div>
        <div className="table-responsive">
          <table className="table table-hover align-middle jury-table">
            <thead>
              <tr>
                <th>Session</th><th>Année</th><th>Formation</th><th>Niveau</th>
                <th>Type</th><th>Statut</th>
                {peutAgir && <th className="text-end">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement || !optionsChargees ? (
                <tr><td colSpan={7} className="text-center py-4"><div className="spinner-border spinner-border-sm" /></td></tr>
              ) : sessions.length === 0 ? (
                <tr><td colSpan={7} className="jury-empty"><div className="jury-empty-icon"><i className="bi bi-clipboard-x"></i></div><div className="jury-empty-title">Aucune session de jury.</div><p>Aucune session ne correspond aux filtres sélectionnés. Élargissez la recherche ou créez les sessions depuis le hub Jurys après la saisie des notes.</p><div className="jury-empty-hint"><span>Statut : Tous</span><span>Année : Toutes</span><span>Formation : Toutes</span></div></td></tr>
              ) : sessions.map((s) => (
                <tr key={s.id}>
                  <td><span className="jury-session">{s.libelle || `Session #${s.id}`}</span><span className="jury-session-sub">Session #{s.id}</span></td>
                  <td>{libelleAnnee(s.annee_academique_id)}</td>
                  <td>{libelleFormation(s.ref_formation_id)}</td>
                  <td>{s.niveau_id}</td>
                  <td>{s.type_session}</td>
                  <td><span className={`badge jury-badge text-bg-${BADGE_STATUT[s.statut] || 'secondary'}`}>{s.statut}</span></td>
                  {peutAgir && (
                    <td className="text-end">
                      <div className="btn-group btn-group-sm">
                        {s.statut === 'PREPARATION' && (
                          <button className="btn btn-outline-info jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Contrôler</button>
                        )}
                        {s.statut === 'CONTROLE' && (
                          <button className="btn btn-outline-primary jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'calcul')}>Calculer</button>
                        )}
                        {s.statut === 'CALCUL' && (
                          <button className="btn btn-outline-warning jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Délibérer</button>
                        )}
                        {s.statut === 'DELIBERATION' && (
                          <button className="btn btn-outline-warning jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Décider</button>
                        )}
                        {s.statut === 'DECISION' && (
                          <button className="btn btn-outline-info jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'generer_pv')}>Générer PV</button>
                        )}
                        {s.statut === 'PV_GENERE' && (
                          <button className="btn btn-outline-success jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Valider</button>
                        )}
                        {s.statut === 'VALIDE' && (
                          <button className="btn btn-outline-dark jury-action-btn" disabled={enCours}
                                  onClick={() => action(s, 'transition')}>Verrouiller</button>
                        )}
                        {s.statut === 'VERROUILLE' && (
                          <button className="btn btn-outline-success jury-action-btn" disabled={enCours}
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

