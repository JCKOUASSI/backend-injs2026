import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/campagnes.css'
import '../../styles/maquettes.css'

const STATUTS = [
  { value: '', label: 'Tous les statuts' },
  { value: 'BROUILLON', label: 'Brouillons' },
  { value: 'VALIDEE', label: 'Validées' },
  { value: 'ACTIVE', label: 'Actives' },
  { value: 'ARCHIVEE', label: 'Archivées' },
]

const BADGE_STATUT = {
  BROUILLON: 'secondary',
  VALIDEE: 'info',
  ACTIVE: 'success',
  ARCHIVEE: 'dark',
}

export default function Maquettes() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [maquettes, setMaquettes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [filtreStatut, setFiltreStatut] = useState('')
  const [recherche, setRecherche] = useState('')
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({
    annee_academique_id: '', ref_formation_id: '', niveau_id: '', libelle: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [], niveaux: [] })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const params = {}
      if (filtreStatut) params.statut = filtreStatut
      const res = await api.get('/scolarite/maquettes/', { params })
      setMaquettes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement des maquettes impossible.', 'error')
    } finally {
      setChargement(false)
    }
  }, [filtreStatut, toast])

  useEffect(() => { charger() }, [charger])

  useEffect(() => {
    if (!peutAgir) return
    ;(async () => {
      try {
        const [annees, formations, niveaux] = await Promise.all([
          api.get('/scolarite/ref/annees/', { params: { actif: 'true' } }),
          api.get('/scolarite/ref/formations/'),
          api.get('/scolarite/ref/niveaux/', { params: { actif: 'true' } }),
        ])
        setOptions({ annees: annees.data, formations: formations.data, niveaux: niveaux.data })
      } catch {
        toast.showToast('Chargement des référentiels impossible.', 'error')
      }
    })()
  }, [peutAgir, toast])

  const creer = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      const res = await api.post('/scolarite/maquettes/creer/', {
        ...form,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        niveau_id: Number(form.niveau_id) || undefined,
      })
      toast.showToast(`Maquette v${res.data.version} créée en brouillon.`)
      setForm({ annee_academique_id: '', ref_formation_id: '', niveau_id: '', libelle: '' })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const action = async (maquette, verbe, confirmation) => {
    if (confirmation && !window.confirm(confirmation)) return
    setEnCours(true)
    try {
      const res = await api.post(`/scolarite/maquettes/${maquette.id}/${verbe}/`, {})
      toast.showToast(res.data?.detail || 'Opération effectuée.')
      charger()
    } catch (err) {
      const problemes = err.response?.data?.problemes
      toast.showToast(
        problemes?.length ? problemes.join(' ') : (err.response?.data?.error || 'Action impossible.'),
        'error',
      )
    } finally {
      setEnCours(false)
    }
  }

  // Statistiques calculées
  const stats = useMemo(() => {
    const total = maquettes.length
    const actives = maquettes.filter((m) => m.statut === 'ACTIVE').length
    const validees = maquettes.filter((m) => m.statut === 'VALIDEE').length
    const brouillons = maquettes.filter((m) => m.statut === 'BROUILLON').length
    return { total, actives, validees, brouillons }
  }, [maquettes])

  // Filtrage local par recherche textuelle
  const maquettesFiltrees = useMemo(() => {
    if (!recherche.trim()) return maquettes
    const q = recherche.toLowerCase()
    return maquettes.filter(
      (m) =>
        (m.ref_formation || '').toLowerCase().includes(q) ||
        (m.niveau || '').toLowerCase().includes(q) ||
        (m.parcours || '').toLowerCase().includes(q) ||
        (m.annee_academique || '').toLowerCase().includes(q),
    )
  }, [maquettes, recherche])

  return (
    <div className="container-fluid maquettes-lmd-container camp-page py-4">
      {/* ── En-tête de page ── */}
      <div className="camp-hero mb-4 maquettes-header">
        <div className="camp-hero-text">
          <h1 className="h4 mb-0 maquettes-title camp-hero-title">
            <i className="bi bi-diagram-3"></i>
            Maquettes pédagogiques LMD
          </h1>
          <p className="text-muted small mb-0 maquettes-subtitle camp-hero-sub">
            Conception, structuration des parcours (UE/ECUE/ECTS) et cycles de validation académique.
          </p>
        </div>
        <div className="camp-hero-side">
          <span className="plaquette plaquette-primary">
            <i className="bi bi-mortarboard"></i>{maquettes.length} maquette{maquettes.length > 1 ? 's' : ''}
          </span>
          <span className="plaquette plaquette-soft">
            <i className="bi bi-shield-lock"></i>Actives immuables
          </span>
        </div>
      </div>

      {/* ── Rangée de KPI Plaquettes ── */}
      <div className="maquettes-stats-grid camp-kpi-row">
        <div className="maquette-kpi-card maquette-kpi-card--primary camp-kpi">
          <div className="maquette-kpi-info camp-kpi-info">
            <span className="maquette-kpi-title camp-kpi-label">Total Maquettes</span>
            <span className="maquette-kpi-value camp-kpi-value">{stats.total}</span>
          </div>
          <div className="maquette-kpi-icon camp-kpi-icon">
            <i className="bi bi-mortarboard-fill"></i>
          </div>
        </div>

        <div className="maquette-kpi-card camp-kpi">
          <div className="maquette-kpi-info camp-kpi-info">
            <span className="maquette-kpi-title camp-kpi-label">Actives (Immuables)</span>
            <span className="maquette-kpi-value camp-kpi-value">{stats.actives}</span>
          </div>
          <div className="maquette-kpi-icon camp-kpi-icon is-green">
            <i className="bi bi-check-circle-fill"></i>
          </div>
        </div>

        <div className="maquette-kpi-card camp-kpi">
          <div className="maquette-kpi-info camp-kpi-info">
            <span className="maquette-kpi-title camp-kpi-label">Validées (Gelées)</span>
            <span className="maquette-kpi-value camp-kpi-value">{stats.validees}</span>
          </div>
          <div className="maquette-kpi-icon camp-kpi-icon is-blue">
            <i className="bi bi-lock-fill"></i>
          </div>
        </div>

        <div className="maquette-kpi-card camp-kpi">
          <div className="maquette-kpi-info camp-kpi-info">
            <span className="maquette-kpi-title camp-kpi-label">Brouillons</span>
            <span className="maquette-kpi-value camp-kpi-value">{stats.brouillons}</span>
          </div>
          <div className="maquette-kpi-icon camp-kpi-icon is-amber">
            <i className="bi bi-pencil-square"></i>
          </div>
        </div>
      </div>

      {/* ── Filtres & Recherche ── */}
      <div className="maquettes-glass-card camp-panel mb-4">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title"><i className="bi bi-funnel"></i>Filtres et recherche</h2>
          <span className="camp-count-pill">{maquettesFiltrees.length} résultat{maquettesFiltrees.length > 1 ? 's' : ''}</span>
        </div>
        <div className="camp-panel-body">
          <div className="row g-3 align-items-end camp-form">
            <div className="col-md-4">
              <label className="form-label" htmlFor="maq-filtre-statut">Filtrer par statut</label>
              <select
                id="maq-filtre-statut"
                className="form-select maq-select"
                value={filtreStatut}
                onChange={(e) => setFiltreStatut(e.target.value)}
              >
                {STATUTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
              </select>
            </div>
            <div className="col-md-5">
              <label className="form-label" htmlFor="maq-recherche">Rechercher une formation ou parcours</label>
              <div className="input-group maq-search">
                <span className="input-group-text">
                  <i className="bi bi-search"></i>
                </span>
                <input
                  id="maq-recherche"
                  type="text"
                  className="form-control"
                  placeholder="Filtrer par intitulé, niveau, parcours…"
                  value={recherche}
                  onChange={(e) => setRecherche(e.target.value)}
                />
                {recherche && (
                  <button className="btn btn-outline-secondary" type="button" onClick={() => setRecherche('')} aria-label="Effacer la recherche">
                    <i className="bi bi-x" aria-hidden="true"></i>
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ── Formulaire de Création ── */}
      {peutAgir && (
        <div className="card maquettes-glass-card camp-panel mb-4">
          <div className="camp-panel-head">
            <h2 className="camp-panel-title"><i className="bi bi-plus-circle"></i>Nouvelle maquette</h2>
            <span className="camp-count-pill">Brouillon v1</span>
          </div>
          <div className="card-body camp-panel-body">
            <form className="row g-3 align-items-end camp-form" onSubmit={creer}>
              <div className="col-md-3">
                <label className="form-label" htmlFor="maq-annee">Année académique *</label>
                <select id="maq-annee" className="form-select maq-select" required value={form.annee_academique_id}
                        onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}>
                  <option value="">Année académique…</option>
                  {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                </select>
              </div>
              <div className="col-md-3">
                <label className="form-label" htmlFor="maq-formation">Formation *</label>
                <select id="maq-formation" className="form-select maq-select" required value={form.ref_formation_id}
                        onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}>
                  <option value="">Formation…</option>
                  {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                </select>
              </div>
              <div className="col-md-2">
                <label className="form-label" htmlFor="maq-niveau">Niveau *</label>
                <select id="maq-niveau" className="form-select maq-select" required value={form.niveau_id}
                        onChange={(e) => setForm({ ...form, niveau_id: e.target.value })}>
                  <option value="">Niveau…</option>
                  {options.niveaux.map((n) => <option key={n.id} value={n.id}>{n.code}</option>)}
                </select>
              </div>
              <div className="col-md-2">
                <label className="form-label" htmlFor="maq-libelle">Libellé</label>
                <input id="maq-libelle" className="form-control maq-input" placeholder="Libellé (optionnel)"
                       value={form.libelle} onChange={(e) => setForm({ ...form, libelle: e.target.value })} />
              </div>
              <div className="col-md-2">
                <button className="btn btn-primary w-100 fw-bold camp-submit-btn" disabled={enCours}>
                  <i className="bi bi-plus-lg me-1" aria-hidden="true"></i>Créer
                </button>
              </div>
              <div className="col-12">
                <p className="form-text mb-0">La maquette est enregistrée au statut brouillon : ajoutez les UE/ECUE puis validez avant activation (immuable).</p>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Tableau des Maquettes ── */}
      <div className="card maquettes-table-container camp-panel">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title"><i className="bi bi-table"></i>Maquettes</h2>
          <span className="camp-count-pill">{maquettesFiltrees.length} maquette{maquettesFiltrees.length > 1 ? 's' : ''}</span>
        </div>
        <div className="table-responsive">
          <table className="table table-hover align-middle mb-0 camp-table maq-table">
            <thead>
              <tr>
                <th>Formation</th><th>Niveau</th><th>Parcours</th><th>Année</th>
                <th>Version</th><th>Statut</th><th>UE</th><th>Crédits</th>
                {peutAgir && <th className="text-end">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {chargement ? (
                <tr><td colSpan={9} className="text-center py-4"><div className="spinner-border spinner-border-sm text-primary" /></td></tr>
              ) : maquettesFiltrees.length === 0 ? (
                <tr><td colSpan={9}>
                  <div className="camp-empty"><i className="bi bi-inbox"></i>Aucune maquette.</div>
                </td></tr>
              ) : maquettesFiltrees.map((m) => (
                <tr key={m.id}>
                  <td>
                    <Link to={`/scolarite/maquettes/${m.id}`} className="fw-semibold text-decoration-none camp-link">
                      {m.ref_formation}
                    </Link>
                    <span className="camp-sub">Maquette v{m.version}</span>
                  </td>
                  <td><span className="badge bg-light text-dark border maq-chip">{m.niveau}</span></td>
                  <td>{m.parcours || '—'}</td>
                  <td>{m.annee_academique}</td>
                  <td><span className="badge bg-secondary-subtle text-secondary border maq-chip">v{m.version}</span></td>
                  <td>
                    <span className={`badge text-bg-${BADGE_STATUT[m.statut] || 'secondary'} maquette-badge`}>
                      {m.statut}
                    </span>
                  </td>
                  <td><span className="camp-candidatures">{m.nb_ue}</span></td>
                  <td><span className="camp-candidatures">{m.total_credits}</span></td>
                  {peutAgir && (
                    <td className="text-end">
                      <div className="d-inline-flex gap-2 flex-wrap justify-content-end">
                        {m.statut === 'BROUILLON' && (
                          <button className="btn btn-outline-info maquette-action-btn camp-action-btn" disabled={enCours}
                                  onClick={() => action(m, 'valider', 'Valider cette maquette (contenu gelé) ?')}>
                            <i className="bi bi-check2-circle me-1" aria-hidden="true"></i>Valider
                          </button>
                        )}
                        {m.statut === 'VALIDEE' && (
                          <button className="btn btn-outline-success maquette-action-btn camp-action-btn" disabled={enCours}
                                  onClick={() => action(m, 'activer', 'Activer cette maquette (immuable) ?')}>
                            <i className="bi bi-lightning-charge me-1" aria-hidden="true"></i>Activer
                          </button>
                        )}
                        {m.statut === 'ACTIVE' && (
                          <button className="btn btn-outline-dark maquette-action-btn camp-action-btn" disabled={enCours}
                                  onClick={() => action(m, 'archiver', 'Archiver cette maquette ?')}>
                            <i className="bi bi-archive me-1" aria-hidden="true"></i>Archiver
                          </button>
                        )}
                        {m.statut !== 'BROUILLON' && (
                          <button className="btn btn-outline-secondary maquette-action-btn camp-action-btn" disabled={enCours}
                                  onClick={() => action(m, 'cloner', 'Créer une nouvelle version (clonage) ?')}>
                            <i className="bi bi-copy me-1" aria-hidden="true"></i>Cloner
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
    </div>
  )
}
