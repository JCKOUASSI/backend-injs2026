import React, { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/campagnes.css'
import '../../styles/equivalences.css'

const BADGE_STATUT = {
  BROUILLON: 'secondary', SOUMISE: 'info', EN_INSTRUCTION: 'info',
  A_COMPLETER: 'warning', AVIS_PEDAGOGIQUE: 'primary', DECISION: 'primary',
  VALIDEE: 'success', REJETEE: 'danger', APPLIQUEE: 'dark',
}

// Teinte du chip de décision : lecture immédiate du sens (visuel seul).
const BADGE_DECISION = { FAVORABLE: 'text-bg-success', DEFAVORABLE: 'text-bg-danger' }

// Étapes « vivantes » du cycle : la demande n'est pas encore tranchée.
const STATUTS_EN_COURS = ['SOUMISE', 'EN_INSTRUCTION', 'AVIS_PEDAGOGIQUE', 'DECISION']
// Étapes abouties : décision rendue puis (éventuellement) appliquée.
const STATUTS_ABOUTIES = ['VALIDEE', 'APPLIQUEE']

export default function Equivalences() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [demandes, setDemandes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [selection, setSelection] = useState(null)
  const [form, setForm] = useState({
    type_demande: 'DISPENSE', etudiant_id: '', annee_academique_id: '',
    ref_formation_id: '', niveau_id: '', etablissement_origine: '', diplome_origine: '',
  })
  const [formDecision, setFormDecision] = useState({
    decision: 'FAVORABLE', credits_reconnus: '', note_transferee: '',
    autorite_validation: 'Direction des études INJS', analyse_pedagogique: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [], etudiants: [] })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/equivalences/demandes/')
      setDemandes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    Promise.all([
      api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
      api.get('/scolarite/ref/formations/'),
      api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
      api.get('/scolarite/etudiants/'),
    ])
      .then(([annees, formations, niveaux, etudiants]) => setOptions({
        annees: annees.data, formations: formations.data,
        niveaux: niveaux.data, etudiants: etudiants.data,
      }))
      .catch(() => toast.showToast('Chargement des référentiels impossible.', 'error'))
  }, [peutAgir, toast])

  const creer = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post('/equivalences/demandes/', {
        ...form,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        niveau_id: Number(form.niveau_id) || undefined,
        etudiant_id: Number(form.etudiant_id) || undefined,
      })
      toast.showToast('Demande créée en brouillon.')
      charger()
    } catch (err) {
      toast.showToast(JSON.stringify(err.response?.data) || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const transition = async (demande, statut) => {
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/transition/`, { statut })
      toast.showToast(`Demande ${statut.toLowerCase()}.`)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Transition impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const decider = async (demande) => {
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/decision/`, {
        ...formDecision,
        credits_reconnus: formDecision.credits_reconnus || undefined,
        note_transferee: formDecision.note_transferee || undefined,
      })
      toast.showToast('Décision enregistrée.')
      setSelection(null)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Décision impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const appliquer = async (demande) => {
    if (!window.confirm('Appliquer cette dispense/équivalence (effet académique) ?')) return
    setEnCours(true)
    try {
      await api.post(`/equivalences/demandes/${demande.id}/appliquer/`, {})
      toast.showToast('Dispense/équivalence appliquée.')
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Application impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  // Indicateurs de pilotage : calcul d'affichage, aucun appel supplémentaire.
  const stats = useMemo(() => ({
    total: demandes.length,
    enCours: demandes.filter((d) => STATUTS_EN_COURS.includes(d.statut)).length,
    abouties: demandes.filter((d) => STATUTS_ABOUTIES.includes(d.statut)).length,
    credits: demandes.reduce((somme, d) => somme + (Number(d.credits_reconnus) || 0), 0),
  }), [demandes])

  return (
    <div className="container-fluid py-4 camp-page equivalences-lmd-container">
      {/* ── En-tête de page ── */}
      <div className="camp-hero">
        <div className="camp-hero-text">
          <span className="eq-hero-flag">
            <i className="bi bi-diagram-3" aria-hidden="true"></i>
            Passerelles et continuité de parcours
          </span>
          <h1 className="h4 mb-0 camp-hero-title">
            <i className="bi bi-award" aria-hidden="true"></i>
            Équivalences et dispenses
          </h1>
          <p className="mb-0 camp-hero-sub">
            Reconnaissance des acquis antérieurs : instruction, avis pédagogique,
            décision motivée puis application au dossier de l'étudiant.
          </p>
        </div>
        <div className="camp-hero-side">
          <span className="plaquette plaquette-primary">
            <i className="bi bi-collection" aria-hidden="true"></i>
            {demandes.length} demande{demandes.length > 1 ? 's' : ''}
          </span>
          <span className="plaquette plaquette-soft">
            <i className="bi bi-shield-check" aria-hidden="true"></i>
            Application sous confirmation
          </span>
        </div>
      </div>

      {/* ── Indicateurs du cycle de vie ── */}
      <div className="camp-kpi-row">
        <div className="camp-kpi eq-kpi">
          <div>
            <span className="camp-kpi-label">Demandes</span>
            <span className="camp-kpi-value">{stats.total}</span>
          </div>
          <div className="camp-kpi-icon is-blue">
            <i className="bi bi-collection-fill" aria-hidden="true"></i>
          </div>
        </div>
        <div className="camp-kpi eq-kpi">
          <div>
            <span className="camp-kpi-label">En cours d'instruction</span>
            <span className="camp-kpi-value">{stats.enCours}</span>
          </div>
          <div className="camp-kpi-icon is-amber">
            <i className="bi bi-hourglass-split" aria-hidden="true"></i>
          </div>
        </div>
        <div className="camp-kpi eq-kpi">
          <div>
            <span className="camp-kpi-label">Validées / appliquées</span>
            <span className="camp-kpi-value">{stats.abouties}</span>
          </div>
          <div className="camp-kpi-icon is-green">
            <i className="bi bi-patch-check-fill" aria-hidden="true"></i>
          </div>
        </div>
        <div className="camp-kpi eq-kpi">
          <div>
            <span className="camp-kpi-label">Crédits reconnus</span>
            <span className="camp-kpi-value">{stats.credits}</span>
          </div>
          <div className="camp-kpi-icon is-slate">
            <i className="bi bi-123" aria-hidden="true"></i>
          </div>
        </div>
      </div>

      {/* ── Création d'une demande ── */}
      {peutAgir && (
        <div className="card camp-panel">
          <div className="camp-panel-head">
            <h2 className="camp-panel-title">
              <i className="bi bi-plus-circle" aria-hidden="true"></i>
              Nouvelle demande
            </h2>
            <span className="camp-count-pill">Statut initial : brouillon</span>
          </div>
          <div className="card-body camp-panel-body">
            <form className="row g-3 align-items-end camp-form" onSubmit={creer}>
              <div className="col-md-6 col-xl-2">
                <label className="form-label" htmlFor="eq-type">Type de demande</label>
                <select id="eq-type" className="form-select eq-select" value={form.type_demande}
                        onChange={(e) => setForm({ ...form, type_demande: e.target.value })}>
                  <option value="DISPENSE">Dispense</option>
                  <option value="EQUIVALENCE">Équivalence</option>
                </select>
              </div>
              <div className="col-md-6 col-xl-3">
                <label className="form-label" htmlFor="eq-etudiant">Étudiant *</label>
                <select id="eq-etudiant" className="form-select eq-select" required value={form.etudiant_id}
                        onChange={(e) => setForm({ ...form, etudiant_id: e.target.value })}>
                  <option value="">Étudiant…</option>
                  {options.etudiants.map((e) => (
                    <option key={e.id} value={e.id}>{e.matricule} — {e.nom_complet}</option>
                  ))}
                </select>
              </div>
              <div className="col-md-6 col-xl-2">
                <label className="form-label" htmlFor="eq-annee">Année académique *</label>
                <select id="eq-annee" className="form-select eq-select" required value={form.annee_academique_id}
                        onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}>
                  <option value="">Année…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="col-md-6 col-xl-3">
                <label className="form-label" htmlFor="eq-formation">Formation *</label>
                <select id="eq-formation" className="form-select eq-select" required value={form.ref_formation_id}
                        onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}>
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </div>
              <div className="col-md-6 col-xl-2">
                <label className="form-label" htmlFor="eq-niveau">Niveau *</label>
                <select id="eq-niveau" className="form-select eq-select" required value={form.niveau_id}
                        onChange={(e) => setForm({ ...form, niveau_id: e.target.value })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </div>
              <div className="col-12 eq-form-actions">
                <p className="form-text eq-hint mb-0">
                  La demande est ouverte au statut brouillon puis instruite tout au long du
                  cycle : soumission, instruction, avis pédagogique, décision, application.
                </p>
                <button type="submit" className="btn btn-primary eq-add-btn"
                        title="Ajouter la demande" disabled={enCours}>+</button>
              </div>
            </form>
          </div>
        </div>
      )}


      {/* ── Demandes : cycle de vie complet ── */}
      <div className="card camp-panel">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title">
            <i className="bi bi-table" aria-hidden="true"></i>
            Demandes
          </h2>
          <span className="camp-count-pill">
            {demandes.length} demande{demandes.length > 1 ? 's' : ''}
          </span>
        </div>
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0 camp-table eq-table">
            <thead>
              <tr>
                <th>Type</th><th>Matricule</th><th>Formation</th><th>Décision</th>
                <th>Statut</th><th>Crédits</th>
                {peutAgir && <th className="text-end">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr><td colSpan={7} className="text-center py-4"><div className="spinner-border spinner-border-sm text-primary" /></td></tr>
              ) : demandes.length === 0 ? (
                <tr><td colSpan={7}>
                  <div className="camp-empty">
                    <i className="bi bi-inbox" aria-hidden="true"></i>
                    Aucune demande.
                  </div>
                </td></tr>
              ) : demandes.map((d) => (
                <tr key={d.id}>
                  <td><span className="badge bg-light text-dark border eq-chip">{d.type_demande}</span></td>
                  <td><span className="fw-semibold">{d.matricule}</span></td>
                  <td>{d.ref_formation}</td>
                  <td>
                    {d.decision ? (
                      <span className={`badge eq-chip ${BADGE_DECISION[d.decision] || 'bg-light text-dark border'}`}>
                        {d.decision}
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td><span className={`badge text-bg-${BADGE_STATUT[d.statut] || 'secondary'} eq-chip`}>{d.statut}</span></td>
                  <td><span className="camp-candidatures">{d.credits_reconnus ?? '—'}</span></td>
                  {peutAgir && (
                    <td className="text-end">
                      <div className="d-inline-flex gap-2 flex-wrap justify-content-end">
                        {d.statut === 'BROUILLON' && (
                          <button className="btn btn-outline-info eq-action-btn" disabled={enCours}
                                  onClick={() => transition(d, 'SOUMISE')}>
                            <i className="bi bi-send me-1" aria-hidden="true"></i>Soumettre
                          </button>
                        )}
                        {d.statut === 'SOUMISE' && (
                          <button className="btn btn-outline-info eq-action-btn" disabled={enCours}
                                  onClick={() => transition(d, 'EN_INSTRUCTION')}>
                            <i className="bi bi-clipboard-check me-1" aria-hidden="true"></i>Instruire
                          </button>
                        )}
                        {d.statut === 'EN_INSTRUCTION' && (
                          <button className="btn btn-outline-primary eq-action-btn" disabled={enCours}
                                  onClick={() => transition(d, 'AVIS_PEDAGOGIQUE')}>
                            <i className="bi bi-mortarboard me-1" aria-hidden="true"></i>Avis pédagogique
                          </button>
                        )}
                        {(d.statut === 'AVIS_PEDAGOGIQUE' || d.statut === 'DECISION') && (
                          <button className="btn btn-outline-primary eq-action-btn"
                                  onClick={() => setSelection(d)}>
                            <i className="bi bi-check2-square me-1" aria-hidden="true"></i>Décider
                          </button>
                        )}
                        {d.statut === 'VALIDEE' && (
                          <button className="btn btn-outline-success eq-action-btn" disabled={enCours}
                                  onClick={() => appliquer(d)}>
                            <i className="bi bi-lightning-charge me-1" aria-hidden="true"></i>Appliquer
                          </button>
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


      {/* ── Décision pédagogique ── */}
      {selection && (
        <div className="card camp-panel eq-decision-panel">
          <div className="camp-panel-head">
            <h2 className="camp-panel-title">
              <i className="bi bi-clipboard2-check" aria-hidden="true"></i>
              Décision — demande #{selection.id}
            </h2>
            <span className="camp-count-pill">{selection.ref_formation}</span>
          </div>
          <div className="card-body camp-panel-body">
            <form className="row g-3 align-items-end camp-form" onSubmit={(e) => { e.preventDefault(); decider(selection) }}>
              <div className="col-md-3">
                <label className="form-label" htmlFor="eq-decision">Décision</label>
                <select id="eq-decision" className="form-select eq-select" value={formDecision.decision}
                        onChange={(e) => setFormDecision({ ...formDecision, decision: e.target.value })}>
                  <option value="FAVORABLE">Favorable</option>
                  <option value="DEFAVORABLE">Défavorable</option>
                </select>
              </div>
              <div className="col-md-2">
                <label className="form-label" htmlFor="eq-credits">Crédits reconnus</label>
                <input id="eq-credits" type="number" min="0" className="form-control eq-input" placeholder="Crédits reconnus"
                       value={formDecision.credits_reconnus}
                       onChange={(e) => setFormDecision({ ...formDecision, credits_reconnus: e.target.value })} />
              </div>
              <div className="col-md-2">
                <label className="form-label" htmlFor="eq-note">Note transférée</label>
                <input id="eq-note" type="number" step="0.25" min="0" max="20" className="form-control eq-input"
                       placeholder="Note transférée" value={formDecision.note_transferee}
                       onChange={(e) => setFormDecision({ ...formDecision, note_transferee: e.target.value })} />
              </div>
              <div className="col-md-3">
                <label className="form-label" htmlFor="eq-autorite">Autorité de validation</label>
                <input id="eq-autorite" className="form-control eq-input" placeholder="Autorité de validation"
                       value={formDecision.autorite_validation}
                       onChange={(e) => setFormDecision({ ...formDecision, autorite_validation: e.target.value })} />
              </div>
              <div className="col-md-2">
                <button className="btn btn-primary w-100 camp-submit-btn" disabled={enCours}>Enregistrer</button>
              </div>
            </form>
            <div className="eq-decision-foot">
              <p className="form-text eq-hint mb-0">
                La décision est horodatée et rattachée à la demande ; l'application au dossier
                reste soumise à confirmation.
              </p>
              <button className="btn btn-outline-secondary eq-action-btn" onClick={() => setSelection(null)}>
                Annuler
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
