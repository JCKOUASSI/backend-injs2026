
import { useCallback, useEffect, useRef, useState } from 'react'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import FinancePageShell, { FinanceNavActions } from '../components/finance/FinancePageShell'
import '../styles/finance.css'

const fmtDuration = (minutes) => {
  const total = Math.round(Number(minutes || 0))
  const h = Math.floor(total / 60)
  const m = total % 60
  if (m === 0) return `${h}h`
  return `${h}h ${m}min`
}

const formatDateTime = (value) => {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const STATUT_CFG = {
  EN_ATTENTE: { cls: 'bg-warning text-dark', icon: 'bi-hourglass-split' },
  VALIDE:     { cls: 'bg-success',           icon: 'bi-check-circle-fill' },
  REJETE:     { cls: 'bg-secondary',         icon: 'bi-x-circle-fill' },
}

const FILTERS = [
  { key: 'EN_ATTENTE', label: 'En attente', icon: 'bi-hourglass-split' },
  { key: 'VALIDE',     label: 'Validés',    icon: 'bi-check-circle' },
  { key: 'REJETE',     label: 'Rejetés',    icon: 'bi-x-circle' },
  { key: '',           label: 'Tous',       icon: 'bi-list-ul' },
]

export default function FinanceAjustements() {
  const { showToast } = useToast()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState([])
  const [allItems, setAllItems] = useState([])
  const [pendingCount, setPendingCount] = useState(0)
  const [filter, setFilter] = useState('EN_ATTENTE')
  const [actingId, setActingId] = useState(null)
  const [rejectId, setRejectId] = useState(null)
  const [rejectMotif, setRejectMotif] = useState('')
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ session_id: '', formateur_id: '', minutes_delta: '', motif: '' })
  const [submitting, setSubmitting] = useState(false)

  // Recherche formateur
  const [formateurSearch, setFormateurSearch] = useState('')
  const [formateurOptions, setFormateurOptions] = useState([])
  const [formateurLoading, setFormateurLoading] = useState(false)
  const [formateurSelected, setFormateurSelected] = useState(null)
  const formateurSearchRef = useRef(null)

  // Séances disponibles
  const [sessionOptions, setSessionOptions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(false)

  const loadItems = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/formations/finance/ajustements/')
      const all = data.items || []
      setAllItems(all)
      setPendingCount(data.pending_count || 0)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur de chargement', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { loadItems() }, [loadItems])

  useEffect(() => {
    setItems(filter ? allItems.filter(i => i.statut === filter) : allItems)
  }, [filter, allItems])

  const counts = {
    EN_ATTENTE: allItems.filter(i => i.statut === 'EN_ATTENTE').length,
    VALIDE:     allItems.filter(i => i.statut === 'VALIDE').length,
    REJETE:     allItems.filter(i => i.statut === 'REJETE').length,
    total:      allItems.length,
  }

  const handleValidate = async (id) => {
    setActingId(id)
    try {
      await api.post(`/formations/finance/ajustements/${id}/valider/`)
      showToast('Ajustement validé — impact paie appliqué', 'success')
      loadItems()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Validation impossible', 'error')
    } finally {
      setActingId(null)
    }
  }

  const handleReject = async () => {
    if (!rejectMotif.trim()) { showToast('Le motif de rejet est obligatoire', 'error'); return }
    setActingId(rejectId)
    try {
      await api.post(`/formations/finance/ajustements/${rejectId}/rejeter/`, { motif: rejectMotif.trim() })
      showToast('Ajustement rejeté', 'success')
      setRejectId(null)
      setRejectMotif('')
      loadItems()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Rejet impossible', 'error')
    } finally {
      setActingId(null)
    }
  }

  const searchFormateurs = useCallback(async (q) => {
    if (!q || q.trim().length < 2) { setFormateurOptions([]); return }
    setFormateurLoading(true)
    try {
      const { data } = await api.get('/formations/formateurs/list/', { params: { search: q, page_size: 20 } })
      setFormateurOptions(data.results || [])
    } catch { setFormateurOptions([]) }
    finally { setFormateurLoading(false) }
  }, [])

  useEffect(() => {
    const t = setTimeout(() => searchFormateurs(formateurSearch), 300)
    return () => clearTimeout(t)
  }, [formateurSearch, searchFormateurs])

  const selectFormateur = async (f) => {
    setFormateurSelected(f)
    setFormateurOptions([])
    setFormateurSearch('')
    setForm(prev => ({ ...prev, formateur_id: f.id, session_id: '' }))
    setSessionsLoading(true)
    try {
      const { data } = await api.get('/formations/formateurs/finance-report/', {
        params: { formateur_id: f.id, include_sessions: 1, preset: 'tout' },
      })
      const sessions = (data.results || []).flatMap(r => (r.sessions || []).filter(s => s.date_journee))
      sessions.sort((a, b) => b.date_journee?.localeCompare(a.date_journee))
      setSessionOptions(sessions)
    } catch { setSessionOptions([]) }
    finally { setSessionsLoading(false) }
  }

  const clearFormateur = () => {
    setFormateurSelected(null)
    setFormateurSearch('')
    setSessionOptions([])
    setForm(prev => ({ ...prev, formateur_id: '', session_id: '' }))
  }

  const resetForm = () => {
    setForm({ session_id: '', formateur_id: '', minutes_delta: '', motif: '' })
    setFormateurSelected(null)
    setFormateurSearch('')
    setSessionOptions([])
  }

  const handlePropose = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      await api.post('/formations/finance/ajustements/', {
        session_id: Number(form.session_id),
        formateur_id: Number(form.formateur_id),
        minutes_delta: Number(form.minutes_delta),
        motif: form.motif.trim(),
      })
      showToast('Ajustement proposé — en attente de validation', 'success')
      resetForm()
      setShowForm(false)
      setFilter('EN_ATTENTE')
      loadItems()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Proposition impossible', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  const rejectItem = rejectId ? allItems.find(i => i.id === rejectId) : null

  return (
    <FinancePageShell
      title="Ajustements horaires"
      subtitle="Corrections manuelles sur séances réelles — workflow validation, impact paie, journal d'audit"
      icon="bi-arrow-left-right"
      showPeriodFilter={false}
      actions={<FinanceNavActions active="ajustements" pendingAjustements={pendingCount} />}
    >
      {/* KPIs */}
      <div className="finance-hero-kpis finance-hero-kpis--4 mb-3">
        <div className="finance-hero-kpi finance-hero-kpi--plan">
          <div className="finance-hero-kpi-label"><i className="bi bi-list-ul me-1"></i>Total</div>
          <div className="finance-hero-kpi-value">{counts.total}</div>
          <div className="finance-hero-kpi-hint">ajustements</div>
        </div>
        <div className="finance-hero-kpi finance-hero-kpi--rate">
          <div className="finance-hero-kpi-label"><i className="bi bi-hourglass-split me-1"></i>En attente</div>
          <div className="finance-hero-kpi-value">{counts.EN_ATTENTE}</div>
          <div className="finance-hero-kpi-hint">à traiter</div>
        </div>
        <div className="finance-hero-kpi finance-hero-kpi--money">
          <div className="finance-hero-kpi-label"><i className="bi bi-check-circle me-1"></i>Validés</div>
          <div className="finance-hero-kpi-value">{counts.VALIDE}</div>
          <div className="finance-hero-kpi-hint">impact paie appliqué</div>
        </div>
        <div className="finance-hero-kpi finance-hero-kpi--plan" style={{ background: 'linear-gradient(135deg,#455a64,#607d8b)' }}>
          <div className="finance-hero-kpi-label"><i className="bi bi-x-circle me-1"></i>Rejetés</div>
          <div className="finance-hero-kpi-value">{counts.REJETE}</div>
          <div className="finance-hero-kpi-hint">sans impact</div>
        </div>
      </div>

      {/* Barre filtres + bouton proposer */}
      <div className="finance-section mb-3">
        <div className="finance-section-header">
          <div className="finance-rank-tabs" style={{ border: 'none', padding: 0, background: 'transparent' }}>
            {FILTERS.map(({ key, label, icon }) => (
              <button
                key={key || 'all'}
                type="button"
                className={`finance-rank-tab${filter === key ? ' active' : ''}`}
                onClick={() => setFilter(key)}
              >
                <i className={`bi ${icon} me-1`}></i>
                {label}
                {key === 'EN_ATTENTE' && counts.EN_ATTENTE > 0 && (
                  <span className="badge bg-danger ms-1" style={{ fontSize: '0.7rem' }}>{counts.EN_ATTENTE}</span>
                )}
              </button>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-sm btn-finance-accent"
            onClick={() => { setShowForm(v => !v); if (showForm) resetForm() }}
          >
            <i className={`bi ${showForm ? 'bi-x-lg' : 'bi-plus-circle'} me-1`}></i>
            {showForm ? 'Annuler' : 'Nouvel ajustement'}
          </button>
        </div>

        {/* Formulaire de proposition */}
        {showForm && (
          <div className="finance-section-body" style={{ borderTop: '1px solid #f1f5f9', background: '#fafbfc' }}>
            <div className="d-flex align-items-center gap-2 mb-3">
              <span style={{ width: 32, height: 32, borderRadius: 10, background: 'var(--fin-accent-soft)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <i className="bi bi-pencil-square" style={{ color: 'var(--fin-accent)' }}></i>
              </span>
              <div>
                <div className="fw-bold" style={{ fontSize: '0.9rem', color: '#1e293b' }}>Proposer un ajustement</div>
                <div className="text-muted" style={{ fontSize: '0.75rem' }}>La modification sera soumise à validation avant d'affecter la paie.</div>
              </div>
            </div>
            <form onSubmit={handlePropose}>
              <div className="row g-3">
                {/* Enseignant */}
                <div className="col-md-4">
                  <label className="finance-filter-field label" style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: '#64748b', marginBottom: '0.25rem' }}>
                    Enseignant
                  </label>
                  {formateurSelected ? (
                    <div className="d-flex align-items-center gap-2 p-2" style={{ background: '#e8eff5', borderRadius: 8, border: '1px solid #94c0e7' }}>
                      <i className="bi bi-person-check-fill" style={{ color: 'var(--fin-accent)' }}></i>
                      <span className="fw-semibold" style={{ fontSize: '0.88rem' }}>{formateurSelected.nom} {formateurSelected.prenom}</span>
                      <span className="text-muted" style={{ fontSize: '0.78rem' }}>#{formateurSelected.numerobadge}</span>
                      <button type="button" className="btn btn-sm ms-auto py-0 px-1" style={{ color: '#64748b', background: 'transparent', border: 'none' }} onClick={clearFormateur} title="Changer">
                        <i className="bi bi-pencil"></i>
                      </button>
                    </div>
                  ) : (
                    <div style={{ position: 'relative' }}>
                      <div style={{ position: 'relative' }}>
                        <i className="bi bi-search" style={{ position: 'absolute', left: 9, top: '50%', transform: 'translateY(-50%)', color: '#94a3b8', fontSize: '0.8rem', zIndex: 1 }}></i>
                        <input
                          ref={formateurSearchRef}
                          type="text"
                          className="form-control form-control-sm"
                          style={{ paddingLeft: 28 }}
                          placeholder="Nom ou matricule…"
                          value={formateurSearch}
                          onChange={e => setFormateurSearch(e.target.value)}
                          autoComplete="off"
                        />
                        {formateurLoading && (
                          <span className="spinner-border spinner-border-sm" style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', width: 14, height: 14 }} />
                        )}
                      </div>
                      {formateurOptions.length > 0 && (
                        <ul className="list-group shadow-sm" style={{ position: 'absolute', zIndex: 999, width: '100%', maxHeight: 220, overflowY: 'auto', top: '100%', marginTop: 2, border: '1px solid #e2e8f0', borderRadius: 8 }}>
                          {formateurOptions.map(f => (
                            <li key={f.id}
                              className="list-group-item list-group-item-action d-flex align-items-center gap-2 py-2 px-3"
                              style={{ cursor: 'pointer', fontSize: '0.84rem', border: 'none', borderBottom: '1px solid #f1f5f9' }}
                              onMouseDown={() => selectFormateur(f)}>
                              <span style={{ width: 28, height: 28, borderRadius: 7, background: '#f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                <i className="bi bi-person" style={{ fontSize: '0.8rem', color: '#64748b' }}></i>
                              </span>
                              <div>
                                <strong>{f.nom}</strong> {f.prenom}
                                {f.specialite && <span className="text-muted ms-1">— {f.specialite}</span>}
                              </div>
                              <span className="text-muted ms-auto" style={{ fontSize: '0.75rem' }}>#{f.numerobadge}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  )}
                </div>

                {/* Séance */}
                <div className="col-md-4">
                  <label className="finance-filter-field label" style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: '#64748b', marginBottom: '0.25rem' }}>
                    Séance
                  </label>
                  {sessionsLoading ? (
                    <div className="d-flex align-items-center gap-2 text-muted" style={{ fontSize: '0.83rem', paddingTop: 6 }}>
                      <span className="spinner-border spinner-border-sm" style={{ width: 14, height: 14 }} />
                      Chargement des séances…
                    </div>
                  ) : (
                    <select
                      className="form-select form-select-sm"
                      value={form.session_id}
                      onChange={e => setForm(f => ({ ...f, session_id: e.target.value }))}
                      required
                      disabled={!formateurSelected}
                      style={!formateurSelected ? { opacity: 0.5 } : {}}
                    >
                      <option value="">
                        {formateurSelected
                          ? sessionOptions.length === 0 ? '— Aucune séance disponible —' : '— Choisir une séance —'
                          : '— Sélectionner un enseignant d\'abord —'}
                      </option>
                      {sessionOptions.map(s => (
                        <option key={s.session_id} value={s.session_id}>
                          {s.date_journee} · {s.module_intitule}{s.grade ? ` (${s.grade}${s.groupe ? ` ${s.groupe}` : ''})` : ''} · {Math.round(s.duree_minutes || 0)} min
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {/* Delta */}
                <div className="col-6 col-md-2">
                  <label className="finance-filter-field label" style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: '#64748b', marginBottom: '0.25rem' }}>
                    Minutes (+/−)
                  </label>
                  <input
                    type="number"
                    className="form-control form-control-sm"
                    placeholder="ex : −15"
                    value={form.minutes_delta}
                    onChange={e => setForm(f => ({ ...f, minutes_delta: e.target.value }))}
                    required
                  />
                </div>

                {/* Motif */}
                <div className="col-6 col-md-2">
                  <label className="finance-filter-field label" style={{ display: 'block', fontSize: '0.72rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: '#64748b', marginBottom: '0.25rem' }}>
                    Motif
                  </label>
                  <input
                    type="text"
                    className="form-control form-control-sm"
                    placeholder="Raison…"
                    value={form.motif}
                    onChange={e => setForm(f => ({ ...f, motif: e.target.value }))}
                    required
                  />
                </div>
              </div>

              <div className="mt-3 d-flex justify-content-end gap-2">
                <button type="button" className="btn btn-sm btn-outline-secondary" onClick={() => { setShowForm(false); resetForm() }}>
                  Annuler
                </button>
                <button
                  type="submit"
                  className="btn btn-sm btn-finance-accent"
                  disabled={submitting || !form.formateur_id || !form.session_id}
                >
                  {submitting
                    ? <><span className="spinner-border spinner-border-sm me-1" />Envoi…</>
                    : <><i className="bi bi-send me-1"></i>Soumettre</>}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* Table */}
        {loading ? (
          <div className="finance-empty">
            <span className="spinner-border" style={{ width: 32, height: 32, opacity: 0.4 }} />
          </div>
        ) : items.length === 0 ? (
          <div className="finance-empty">
            <i className="bi bi-inbox"></i>
            Aucun ajustement{filter ? ` avec le statut "${FILTERS.find(f => f.key === filter)?.label}"` : ''}.
          </div>
        ) : (
          <div className="finance-table-wrap">
            <table className="finance-table">
              <thead>
                <tr>
                  <th>Statut</th>
                  <th>Enseignant</th>
                  <th>Séance</th>
                  <th style={{ textAlign: 'center' }}>Δ min</th>
                  <th>Avant → Après</th>
                  <th>Motif</th>
                  <th>Proposé par</th>
                  <th style={{ textAlign: 'right' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item) => {
                  const cfg = STATUT_CFG[item.statut] || { cls: 'bg-light text-dark', icon: 'bi-circle' }
                  return (
                    <tr key={item.id}>
                      <td>
                        <span className={`badge d-inline-flex align-items-center gap-1 ${cfg.cls}`}>
                          <i className={`bi ${cfg.icon}`}></i>
                          {item.statut_label}
                        </span>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: '0.86rem' }}>{item.formateur?.label}</div>
                      </td>
                      <td>
                        <div style={{ fontWeight: 600, fontSize: '0.84rem' }}>{item.session?.module_intitule}</div>
                        <div className="text-muted" style={{ fontSize: '0.76rem' }}>
                          {[item.session?.grade, item.session?.groupe].filter(Boolean).join(' ')}
                          {item.session?.date_journee && ` — ${item.session.date_journee}`}
                        </div>
                      </td>
                      <td style={{ textAlign: 'center' }}>
                        <span
                          className="finance-evolution"
                          style={{ fontSize: '0.82rem' }}
                          data-positive={item.minutes_delta >= 0}
                        >
                          <i className={`bi ${item.minutes_delta >= 0 ? 'bi-arrow-up' : 'bi-arrow-down'}`}></i>
                          <strong className={item.minutes_delta >= 0 ? 'text-success' : 'text-danger'}>
                            {item.minutes_delta >= 0 ? '+' : ''}{item.minutes_delta} min
                          </strong>
                        </span>
                      </td>
                      <td style={{ whiteSpace: 'nowrap', fontSize: '0.84rem' }}>
                        <span className="text-muted">{fmtDuration(item.realise_avant_minutes)}</span>
                        <i className="bi bi-arrow-right mx-1 text-muted" style={{ fontSize: '0.7rem' }}></i>
                        <strong>{fmtDuration(item.realise_apres_minutes)}</strong>
                      </td>
                      <td style={{ maxWidth: 180, fontSize: '0.82rem' }}>
                        <span title={item.motif} style={{ display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          {item.motif}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.78rem' }}>
                        <div className="fw-semibold">{item.proposed_by}</div>
                        <div className="text-muted">{formatDateTime(item.proposed_at)}</div>
                      </td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {item.statut === 'EN_ATTENTE' && (
                          <div className="d-flex gap-1 justify-content-end">
                            <button
                              type="button"
                              className="btn btn-sm btn-success"
                              disabled={actingId === item.id}
                              onClick={() => handleValidate(item.id)}
                              title="Valider"
                            >
                              {actingId === item.id
                                ? <span className="spinner-border spinner-border-sm" style={{ width: 12, height: 12 }} />
                                : <><i className="bi bi-check-lg me-1"></i>Valider</>}
                            </button>
                            <button
                              type="button"
                              className="btn btn-sm btn-outline-danger"
                              disabled={actingId === item.id}
                              onClick={() => { setRejectId(item.id); setRejectMotif('') }}
                              title="Rejeter"
                            >
                              <i className="bi bi-x-lg me-1"></i>Rejeter
                            </button>
                          </div>
                        )}
                        {item.statut === 'VALIDE' && (
                          <span className="text-muted" style={{ fontSize: '0.78rem' }}>
                            <i className="bi bi-person-check me-1"></i>{item.validated_by}
                          </span>
                        )}
                        {item.statut === 'REJETE' && (
                          <span className="text-muted" style={{ fontSize: '0.78rem' }} title={item.rejection_motif}>
                            <i className="bi bi-chat-left-text me-1"></i>
                            {item.rejection_motif ? item.rejection_motif.slice(0, 40) + (item.rejection_motif.length > 40 ? '…' : '') : '—'}
                          </span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Modale rejet */}
      {rejectId && (
        <div className="modal show d-block finance-modal" style={{ background: 'rgba(15,23,42,0.5)', backdropFilter: 'blur(2px)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <div className="d-flex align-items-center gap-2">
                  <i className="bi bi-x-circle-fill" style={{ fontSize: '1.2rem' }}></i>
                  <h5 className="modal-title mb-0">Rejeter l&apos;ajustement</h5>
                </div>
                <button type="button" className="btn-close" onClick={() => setRejectId(null)}></button>
              </div>
              {rejectItem && (
                <div className="finance-modal-summary">
                  <span><i className="bi bi-person me-1"></i><strong>{rejectItem.formateur?.label}</strong></span>
                  <span><i className="bi bi-calendar3 me-1"></i>{rejectItem.session?.date_journee}</span>
                  <span><i className="bi bi-arrow-left-right me-1"></i>
                    <strong className={rejectItem.minutes_delta >= 0 ? 'text-success' : 'text-danger'}>
                      {rejectItem.minutes_delta >= 0 ? '+' : ''}{rejectItem.minutes_delta} min
                    </strong>
                  </span>
                </div>
              )}
              <div className="modal-body">
                <label className="form-label fw-semibold">Motif de rejet <span className="text-danger">*</span></label>
                <textarea
                  className="form-control"
                  rows={3}
                  placeholder="Expliquer la raison du rejet…"
                  value={rejectMotif}
                  onChange={e => setRejectMotif(e.target.value)}
                  autoFocus
                />
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-outline-secondary" onClick={() => setRejectId(null)}>
                  Annuler
                </button>
                <button
                  type="button"
                  className="btn btn-danger"
                  disabled={actingId === rejectId || !rejectMotif.trim()}
                  onClick={handleReject}
                >
                  {actingId === rejectId
                    ? <><span className="spinner-border spinner-border-sm me-1" />Traitement…</>
                    : <><i className="bi bi-x-circle me-1"></i>Confirmer le rejet</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </FinancePageShell>
  )
}
