import React, { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import api from '../../services/api'
import { canActScolarite } from '../../utils/roles'
import { useAuth } from '../../context/AuthContext'
import { useToast } from '../../context/ToastContext'
import '../../styles/campagnes.css'

const BADGE_STATUT = {
  BROUILLON: 'secondary', PLANIFIEE: 'info', OUVERTE: 'success',
  SUSPENDUE: 'warning', CLOTUREE: 'dark', ANNULEE: 'danger', ARCHIVEE: 'dark',
}

const LIBELLES_STATUT = {
  BROUILLON: 'Brouillon', PLANIFIEE: 'Planifiée', OUVERTE: 'Ouverte',
  SUSPENDUE: 'Suspendue', CLOTUREE: 'Clôturée', ANNULEE: 'Annulée', ARCHIVEE: 'Archivée',
}

const formaterDate = (iso) => {
  if (!iso) return null
  const [a, m, j] = String(iso).split('-')
  return (a && m && j) ? `${j}/${m}/${a}` : iso
}

export default function Campagnes() {
  const { user } = useAuth()
  const toast = useToast()
  const peutAgir = canActScolarite(user)

  const [campagnes, setCampagnes] = useState([])
  const [chargement, setChargement] = useState(true)
  const [enCours, setEnCours] = useState(false)
  const [form, setForm] = useState({
    libelle: '', annee_academique_id: '', ref_formation_id: '',
    date_ouverture: '', date_fermeture: '', quota_admissibles: '', quota_admis: '',
  })
  const [options, setOptions] = useState({ annees: [], formations: [] })
  const [filtres, setFiltres] = useState({ q: '', statut: '', formation: '' })

  const charger = useCallback(async () => {
    setChargement(true)
    try {
      const res = await api.get('/admissions/campagnes/')
      setCampagnes(res.data)
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Chargement des campagnes impossible.', 'error')
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
    ])
      .then(([annees, formations]) => setOptions({ annees: annees.data, formations: formations.data }))
      .catch(() => toast.showToast('Chargement des référentiels impossible.', 'error'))
  }, [peutAgir, toast])

  const creer = async (e) => {
    e.preventDefault()
    setEnCours(true)
    try {
      await api.post('/admissions/campagnes/', {
        ...form,
        annee_academique_id: Number(form.annee_academique_id) || undefined,
        ref_formation_id: Number(form.ref_formation_id) || undefined,
        quota_admissibles: Number(form.quota_admissibles) || undefined,
        quota_admis: Number(form.quota_admis) || undefined,
      })
      toast.showToast('Campagne créée en brouillon.')
      setForm({ libelle: '', annee_academique_id: '', ref_formation_id: '', date_ouverture: '', date_fermeture: '', quota_admissibles: '', quota_admis: '' })
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Création impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const transition = async (campagne, statut, confirmation) => {
    if (confirmation && !window.confirm(confirmation)) return
    setEnCours(true)
    try {
      await api.post(`/admissions/campagnes/${campagne.id}/transition/`, { statut })
      toast.showToast(`Campagne ${statut.toLowerCase()}.`)
      charger()
    } catch (err) {
      toast.showToast(err.response?.data?.error || 'Transition impossible.', 'error')
    } finally {
      setEnCours(false)
    }
  }

  const intituleFormation = (c) =>
    options.formations.find((f) => f.id === c.ref_formation_id)?.intitule
    || c.ref_formation_intitule || c.ref_formation || c.ref_formation_id || '—'
  const libelleAnnee = (c) =>
    options.annees.find((a) => a.id === c.annee_academique_id)?.libelle
    || c.annee_academique_libelle || c.annee_academique || c.annee_academique_id || '—'

  const campagnesFiltrees = useMemo(() => {
    const q = filtres.q.trim().toLowerCase()
    return campagnes.filter((c) => {
      if (filtres.statut && c.statut !== filtres.statut) return false
      if (filtres.formation && String(c.ref_formation_id) !== String(filtres.formation)) return false
      if (q && !`${c.libelle || ''} ${intituleFormation(c)}`.toLowerCase().includes(q)) return false
      return true
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campagnes, filtres, options])

  const kpis = useMemo(() => ({
    total: campagnes.length,
    brouillons: campagnes.filter((c) => c.statut === 'BROUILLON').length,
    ouvertes: campagnes.filter((c) => ['OUVERTE', 'PLANIFIEE', 'SUSPENDUE'].includes(c.statut)).length,
    candidatures: campagnes.reduce((s, c) => s + (Number(c.nb_candidatures) || 0), 0),
  }), [campagnes])

  return (
    <div className="camp-page">
      <div className="camp-hero">
        <div className="camp-hero-text">
          <h1 className="camp-hero-title"><i className="bi bi-megaphone"></i>Campagnes d&apos;admission</h1>
          <p className="camp-hero-sub">Fenêtres de candidature par formation — Brouillon → Planifiée → Ouverte → Clôturée → Archivée.</p>
        </div>
        <div className="camp-hero-side">
          <span className="plaquette plaquette-primary"><i className="bi bi-mortarboard"></i>{options.annees[0]?.libelle || 'Année en cours'}</span>
          <span className="plaquette plaquette-soft"><i className="bi bi-diagram-3"></i>{kpis.total} campagne{kpis.total > 1 ? 's' : ''}</span>
        </div>
      </div>

      <div className="camp-kpi-row">
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">Campagnes</span><span className="camp-kpi-value">{kpis.total}</span></div>
          <span className="camp-kpi-icon is-blue"><i className="bi bi-megaphone"></i></span>
        </div>
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">En brouillon</span><span className="camp-kpi-value">{kpis.brouillons}</span></div>
          <span className="camp-kpi-icon is-slate"><i className="bi bi-pencil-square"></i></span>
        </div>
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">Actives / planifiées</span><span className="camp-kpi-value">{kpis.ouvertes}</span></div>
          <span className="camp-kpi-icon is-green"><i className="bi bi-door-open"></i></span>
        </div>
        <div className="camp-kpi">
          <div><span className="camp-kpi-label">Candidatures</span><span className="camp-kpi-value">{kpis.candidatures}</span></div>
          <span className="camp-kpi-icon is-amber"><i className="bi bi-people"></i></span>
        </div>
      </div>

      {peutAgir && (
        <div className="camp-panel card">
          <div className="camp-panel-head">
            <h2 className="camp-panel-title"><i className="bi bi-plus-circle"></i>Nouvelle campagne</h2>
            <span className="camp-count-pill">Créée en brouillon</span>
          </div>
          <div className="camp-panel-body">
            <form className="camp-form" onSubmit={creer}>
              <div className="row g-3">
                <div className="col-md-4">
                  <label className="form-label" htmlFor="camp-libelle">Libellé *</label>
                  <input id="camp-libelle" className="form-control" placeholder="Libellé" required value={form.libelle}
                         onChange={(e) => setForm({ ...form, libelle: e.target.value })} />
                </div>
                <div className="col-md-4">
                  <label className="form-label" htmlFor="camp-annee">Année académique *</label>
                  <select id="camp-annee" className="form-select" required value={form.annee_academique_id}
                          onChange={(e) => setForm({ ...form, annee_academique_id: e.target.value })}>
                    <option value="">Année…</option>
                    {options.annees.map((a) => <option key={a.id} value={a.id}>{a.libelle}</option>)}
                  </select>
                </div>
                <div className="col-md-4">
                  <label className="form-label" htmlFor="camp-formation">Formation *</label>
                  <select id="camp-formation" className="form-select" required value={form.ref_formation_id}
                          onChange={(e) => setForm({ ...form, ref_formation_id: e.target.value })}>
                    <option value="">Formation…</option>
                    {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
                  </select>
                </div>
              </div>
              <div className="row g-3 mt-1 align-items-stretch">
                <div className="col-lg-5">
                  <fieldset className="camp-fieldset">
                    <legend>Période de candidature</legend>
                    <div className="row g-2">
                      <div className="col-6">
                        <label className="form-label" htmlFor="camp-ouv">Ouverture</label>
                        <input id="camp-ouv" type="date" className="form-control" value={form.date_ouverture}
                               onChange={(e) => setForm({ ...form, date_ouverture: e.target.value })} />
                      </div>
                      <div className="col-6">
                        <label className="form-label" htmlFor="camp-ferm">Fermeture</label>
                        <input id="camp-ferm" type="date" className="form-control" value={form.date_fermeture}
                               min={form.date_ouverture || undefined}
                               onChange={(e) => setForm({ ...form, date_fermeture: e.target.value })} />
                      </div>
                    </div>
                  </fieldset>
                </div>
                <div className="col-lg-5">
                  <fieldset className="camp-fieldset">
                    <legend>Quotas (optionnel)</legend>
                    <div className="row g-2">
                      <div className="col-6">
                        <label className="form-label" htmlFor="camp-qa">Admissibles</label>
                        <input id="camp-qa" type="number" min="0" className="form-control" placeholder="Quota admiss."
                               title="Quota d'admissibles (optionnel)" value={form.quota_admissibles}
                               onChange={(e) => setForm({ ...form, quota_admissibles: e.target.value })} />
                      </div>
                      <div className="col-6">
                        <label className="form-label" htmlFor="camp-qad">Admis</label>
                        <input id="camp-qad" type="number" min="0" className="form-control" placeholder="Quota admis"
                               title="Quota d'admis (optionnel)" value={form.quota_admis}
                               onChange={(e) => setForm({ ...form, quota_admis: e.target.value })} />
                      </div>
                    </div>
                    <div className="form-text mt-1">Admissibles = classement · Admis = admis final. Vide = sans quota.</div>
                  </fieldset>
                </div>
                <div className="col-lg-2 d-flex align-items-end justify-content-lg-end">
                  <button className="btn btn-primary camp-submit-btn w-100" disabled={enCours}>
                    <i className="bi bi-check2-circle me-1"></i>Créer
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      <div className="camp-panel card">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title"><i className="bi bi-list-check"></i>Dossiers de campagne</h2>
          <span className="camp-count-pill">{campagnesFiltrees.length} dossier{campagnesFiltrees.length > 1 ? 's' : ''}</span>
        </div>
        <div className="camp-panel-body">
          <div className="camp-filters mb-3">
            <div className="camp-search">
              <i className="bi bi-search"></i>
              <input className="form-control form-control-sm" placeholder="Rechercher un libellé, une formation…"
                     aria-label="Rechercher une campagne" value={filtres.q}
                     onChange={(e) => setFiltres({ ...filtres, q: e.target.value })} />
            </div>
            <select className="form-select form-select-sm camp-filter-select" aria-label="Filtrer par statut"
                    value={filtres.statut} onChange={(e) => setFiltres({ ...filtres, statut: e.target.value })}>
              <option value="">Tous les statuts</option>
              {Object.entries(LIBELLES_STATUT).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <select className="form-select form-select-sm camp-filter-select" aria-label="Filtrer par formation"
                    value={filtres.formation} onChange={(e) => setFiltres({ ...filtres, formation: e.target.value })}>
              <option value="">Toutes les formations</option>
              {options.formations.map((f) => <option key={f.id} value={f.id}>{f.intitule}</option>)}
            </select>
          </div>
          <div className="table-responsive">
            <table className="table table-hover align-middle mb-0 camp-table">
              <thead className="table-light">
                <tr>
                  <th>Formation</th><th>Période</th><th>Quotas</th><th>Statut</th><th>Candidatures</th>
                  {peutAgir && <th className="text-end">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {chargement ? (
                  <tr><td colSpan={peutAgir ? 6 : 5} className="text-center py-4"><div className="spinner-border spinner-border-sm" /></td></tr>
                ) : campagnesFiltrees.length === 0 ? (
                  <tr><td colSpan={peutAgir ? 6 : 5}>
                    <div className="camp-empty"><i className="bi bi-inbox"></i>
                      {campagnes.length === 0 ? 'Aucune campagne. Créez votre première campagne ci-dessus.' : 'Aucun résultat pour ces filtres.'}
                    </div>
                  </td></tr>
                ) : campagnesFiltrees.map((c) => {
                  const ouv = formaterDate(c.date_ouverture)
                  const ferm = formaterDate(c.date_fermeture)
                  return (
                    <tr key={c.id}>
                      <td>
                        <Link className="camp-link" to={`/scolarite/campagnes/${c.id}`}>{intituleFormation(c)}</Link>
                        <span className="visually-hidden">{c.libelle}</span>
                        <span className="camp-sub">{libelleAnnee(c)}</span>
                      </td>
                      <td className="text-nowrap">
                        {ouv || ferm ? <>{ouv || '…'} <span className="text-muted">→</span> {ferm || '…'}</> : <span className="text-muted">—</span>}
                        {c.statut === 'BROUILLON' && !ouv && !ferm && <span className="camp-sub warn">Dates à compléter avant planification</span>}
                      </td>
                      <td className="text-nowrap">
                        {(c.quota_admissibles ?? c.quota_admis) != null
                          ? <><i className="bi bi-people me-1 text-muted"></i>Adm. {c.quota_admissibles ?? '—'} / Admis {c.quota_admis ?? '—'}</>
                          : <span className="text-muted">—</span>}
                      </td>
                      <td><span className={`badge text-bg-${BADGE_STATUT[c.statut] || 'secondary'}`}>{LIBELLES_STATUT[c.statut] || c.statut}</span></td>
                      <td><span className="camp-candidatures">{c.nb_candidatures ?? 0}</span></td>
                      {peutAgir && (
                        <td className="text-end">
                          <div className="btn-group btn-group-sm">
                            {c.statut === 'BROUILLON' && (
                              <button className="btn btn-outline-info camp-action-btn" disabled={enCours}
                                      title="Passer en planifiée"
                                      onClick={() => transition(c, 'PLANIFIEE')}><i className="bi bi-calendar-check me-1"></i>Planifier</button>
                            )}
                            {c.statut === 'PLANIFIEE' && (
                              <button className="btn btn-outline-success camp-action-btn" disabled={enCours}
                                      onClick={() => transition(c, 'OUVERTE', 'Ouvrir la campagne aux candidatures ?')}><i className="bi bi-door-open me-1"></i>Ouvrir</button>
                            )}
                            {c.statut === 'OUVERTE' && (
                              <>
                                <button className="btn btn-outline-warning camp-action-btn" disabled={enCours}
                                        onClick={() => transition(c, 'SUSPENDUE')}><i className="bi bi-pause-circle me-1"></i>Suspendre</button>
                                <button className="btn btn-outline-dark camp-action-btn" disabled={enCours}
                                        onClick={() => transition(c, 'CLOTUREE', 'Clôturer ? Plus aucune candidature ne sera acceptée.')}><i className="bi bi-lock me-1"></i>Clôturer</button>
                              </>
                            )}
                            {c.statut === 'SUSPENDUE' && (
                              <button className="btn btn-outline-success camp-action-btn" disabled={enCours}
                                      onClick={() => transition(c, 'OUVERTE')}><i className="bi bi-arrow-counterclockwise me-1"></i>Réouvrir</button>
                            )}
                            {c.statut === 'CLOTUREE' && (
                              <button className="btn btn-outline-secondary camp-action-btn" disabled={enCours}
                                      onClick={() => transition(c, 'ARCHIVEE')}><i className="bi bi-archive me-1"></i>Archiver</button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
