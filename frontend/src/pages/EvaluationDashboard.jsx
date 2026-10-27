import { useState, useEffect, useCallback } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useReferentiels } from '../hooks/useReferentiels'
import { parsePaginatedResponse } from '../utils/paginatedResponse'
import Pagination from '../components/Pagination'

const STATUT_LABELS = { BROUILLON: 'Brouillon', PUBLIE: 'Publié', FERME: 'Fermé' }
const STATUT_COLORS = {
  BROUILLON: { background: '#fff8e0', color: '#e69700' },
  PUBLIE:    { background: '#e8eff5', color: '#125a99' },
  FERME:     { background: '#f5f5f5', color: '#616161' },
}

// ─── KPI Card ───────────────────────────────────────────────────────────────
function KpiCard({ icon, label, value, sub, color }) {
  return (
    <div className="card" style={{ padding: '1.25rem 1.5rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.35rem' }}>
        <span style={{ width: 36, height: 36, borderRadius: '10px', background: color + '22', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <i className={`bi ${icon}`} style={{ fontSize: '1.1rem', color }}></i>
        </span>
        <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--text-primary)', lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.15rem' }}>{sub}</div>}
    </div>
  )
}

// ─── Mini bar chart ──────────────────────────────────────────────────────────
function StatutBar({ brouillon, publie, ferme }) {
  const total = brouillon + publie + ferme || 1
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      {[
        { label: 'Brouillon', val: brouillon, color: '#e69700', bg: '#fff8e0' },
        { label: 'Publié',    val: publie,    color: '#125a99', bg: '#e8eff5' },
        { label: 'Fermé',     val: ferme,     color: '#616161', bg: '#f5f5f5' },
      ].map(({ label, val, color }) => (
        <div key={label}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: '3px' }}>
            <span style={{ fontWeight: 600, color }}>{label}</span>
            <span style={{ fontWeight: 700 }}>{val}</span>
          </div>
          <div style={{ height: '8px', borderRadius: '4px', background: '#eee', overflow: 'hidden' }}>
            <div style={{ width: `${(val / total) * 100}%`, height: '100%', background: color, borderRadius: '4px', transition: 'width .4s' }} />
          </div>
        </div>
      ))}
    </div>
  )
}

// ─── Main component ──────────────────────────────────────────────────────────
export default function EvaluationDashboard() {
  const { showToast } = useToast()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const activeTab = searchParams.get('tab') || 'dashboard'
  const setTab = (t) => setSearchParams({ tab: t }, { replace: true })

  // ── State questionnaires ─────────────────────────────────────────────────
  const [questionnaires, setQuestionnaires] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [filters, setFilters] = useState({ statut: '', categorie: '' })
  const [refModules, setRefModules] = useState([])
  const [refCategories, setRefCategories] = useState([])
  const [refGrades, setRefGrades] = useState([])
  const [refGroupes, setRefGroupes] = useState([])
  const [titreSearch, setTitreSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const EMPTY_FORM = { titres: [], categories: [], grades: [], groupes: [], date_ouverture: '', date_fermeture: '' }
  const [form, setForm] = useState(EMPTY_FORM)

  const toggleItem = (field, value) =>
    setForm(f => ({ ...f, [field]: f[field].includes(value) ? f[field].filter(x => x !== value) : [...f[field], value] }))

  const fetchQuestionnaires = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({
        page: String(activeTab === 'dashboard' ? 1 : page),
        page_size: activeTab === 'dashboard' ? '500' : '50',
      })
      if (filters.statut) params.append('statut', filters.statut)
      if (filters.categorie) params.append('categorie', filters.categorie)
      const res = await api.get(`/evaluations/questionnaires/?${params}`)
      const pageSize = activeTab === 'dashboard' ? 500 : 50
      const { results, count, totalPages: pages } = parsePaginatedResponse(res.data, pageSize)
      setQuestionnaires(results)
      setTotalCount(count)
      setTotalPages(pages)
    } catch {
      showToast('Erreur lors du chargement des questionnaires', 'error')
    } finally {
      setLoading(false)
    }
  }, [filters, page, activeTab, showToast])

  const { data: referentielsData } = useReferentiels()

  useEffect(() => {
    if (!referentielsData) return
    setRefModules((referentielsData.modules || []).filter(m => m.actif !== false))
    setRefCategories((referentielsData.categories || []).filter(c => c.actif !== false))
    setRefGrades((referentielsData.grades || []).filter(g => g.actif !== false))
    setRefGroupes(referentielsData.groupes || [])
  }, [referentielsData])

  useEffect(() => { setPage(1) }, [filters.statut, filters.categorie, activeTab])

  useEffect(() => { fetchQuestionnaires() }, [fetchQuestionnaires])

  // ── KPIs calculés ────────────────────────────────────────────────────────
  const allQuestionnaires = questionnaires
  const kpis = {
    total:      totalCount || allQuestionnaires.length,
    brouillon:  allQuestionnaires.filter(q => q.statut === 'BROUILLON').length,
    publie:     allQuestionnaires.filter(q => q.statut === 'PUBLIE').length,
    ferme:      allQuestionnaires.filter(q => q.statut === 'FERME').length,
    questions:  allQuestionnaires.reduce((s, q) => s + (q.nb_questions || 0), 0),
  }
  const recents = [...allQuestionnaires].sort((a, b) => b.id - a.id).slice(0, 5)

  // ── Actions ──────────────────────────────────────────────────────────────
  const closeCreate = () => { setShowCreate(false); setTitreSearch(''); setForm(EMPTY_FORM) }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (form.titres.length === 0) { showToast('Sélectionnez au moins un module', 'error'); return }
    setCreating(true)
    try {
      const payload = {
        titres: form.titres,
        categories: form.categories,
        grades: form.grades,
        groupes: form.groupes,
        ...(form.date_ouverture ? { date_ouverture: form.date_ouverture } : {}),
        ...(form.date_fermeture ? { date_fermeture: form.date_fermeture } : {}),
      }
      const { data } = await api.post('/evaluations/questionnaires/', payload)
      showToast('Questionnaire créé avec succès', 'success')
      closeCreate()
      navigate(`/evaluations/${data.id}`)
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.response?.data?.titres?.[0] || 'Erreur lors de la création'
      showToast(msg, 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleChangeStatut = async (id, statut) => {
    try {
      await api.post(`/evaluations/questionnaires/${id}/statut/`, { statut })
      showToast(`Questionnaire ${STATUT_LABELS[statut].toLowerCase()}`, 'success')
      fetchQuestionnaires()
    } catch {
      showToast('Erreur lors du changement de statut', 'error')
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer ce questionnaire ?')) return
    try {
      await api.delete(`/evaluations/questionnaires/${id}/`)
      showToast('Questionnaire supprimé', 'success')
      fetchQuestionnaires()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Impossible de supprimer ce questionnaire', 'error')
    }
  }

  // ─────────────────────────────────────────────────────────────────────────
  return (
    <div>
      {/* ── En-tête ────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700 }}>Évaluations</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Gérez les questionnaires d'évaluation des modules et enseignants
          </p>
        </div>
        <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
          <i className="bi bi-plus-lg me-1"></i> Nouveau questionnaire
        </button>
      </div>

      <div style={{ marginBottom: '1.75rem', borderBottom: '2px solid var(--border)' }} />

      {/* ══════════════════════════════════════════════════════════════════
          ONGLET DASHBOARD
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'dashboard' && (
        <div>
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : (
            <>
              {/* KPIs principaux */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                <KpiCard icon="bi-clipboard-check" label="Total questionnaires" value={kpis.total}     color="#4f46e5" />
                <KpiCard icon="bi-send"            label="Publiés"              value={kpis.publie}    color="#125a99" sub="En cours de réponse" />
                <KpiCard icon="bi-pencil-square"   label="Brouillons"           value={kpis.brouillon} color="#e69700" sub="En cours de rédaction" />
                <KpiCard icon="bi-lock"            label="Fermés"               value={kpis.ferme}     color="#616161" sub="Réponses clôturées" />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {/* Répartition par statut */}
                <div className="card" style={{ padding: '1.25rem' }}>
                  <h6 style={{ fontWeight: 700, marginBottom: '1rem', color: 'var(--text-primary)' }}>
                    <i className="bi bi-pie-chart me-2" style={{ color: 'var(--primary)' }}></i>
                    Répartition par statut
                  </h6>
                  {kpis.total === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', margin: 0 }}>Aucun questionnaire</p>
                  ) : (
                    <StatutBar brouillon={kpis.brouillon} publie={kpis.publie} ferme={kpis.ferme} />
                  )}
                </div>

                <div className="card" style={{ padding: '1.25rem' }}>
                  <h6 style={{ fontWeight: 700, marginBottom: '1rem', color: 'var(--text-primary)' }}>
                    <i className="bi bi-question-circle me-2" style={{ color: 'var(--primary)' }}></i>
                    Questions au total
                  </h6>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--primary)', lineHeight: 1 }}>{kpis.questions}</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>2 sections par questionnaire : cours + enseignant</div>
                </div>
              </div>

              {/* Questionnaires récents */}
              <div className="card" style={{ padding: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                  <h6 style={{ fontWeight: 700, margin: 0, color: 'var(--text-primary)' }}>
                    <i className="bi bi-clock-history me-2" style={{ color: 'var(--primary)' }}></i>
                    Questionnaires récents
                  </h6>
                  <button
                    className="btn btn-sm btn-outline-primary"
                    onClick={() => setTab('questionnaires')}
                  >
                    Voir tous <i className="bi bi-arrow-right ms-1"></i>
                  </button>
                </div>
                {recents.length === 0 ? (
                  <div className="empty-state" style={{ padding: '1.5rem 0' }}>
                    <i className="bi bi-clipboard-check" style={{ fontSize: '2rem', color: 'var(--text-muted)' }}></i>
                    <p style={{ margin: '0.5rem 0 0' }}>Aucun questionnaire créé</p>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                    {recents.map(q => (
                      <div
                        key={q.id}
                        style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.65rem 0.75rem', borderRadius: '8px', transition: 'background .15s' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--bg-hover, #f5f5f5)'}
                        onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                      >
                        <span style={{ ...STATUT_COLORS[q.statut], fontSize: '0.7rem', fontWeight: 700, padding: '2px 8px', borderRadius: '20px', letterSpacing: '0.04em', flexShrink: 0 }}>
                          {STATUT_LABELS[q.statut]}
                        </span>
                        <span
                          onClick={() => navigate(`/evaluations/${q.id}`)}
                          style={{ flex: 1, fontWeight: 600, fontSize: '0.9rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', color: 'var(--primary)' }}
                        >
                          {(q.titres || []).join(' · ')}
                        </span>
                        <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                          <i className="bi bi-question-circle me-1"></i>{q.nb_questions} q.
                        </span>
                        {q.statut !== 'BROUILLON' && (
                          <button
                            className="btn btn-sm btn-outline-primary"
                            style={{ padding: '1px 8px', fontSize: '0.75rem', flexShrink: 0 }}
                            onClick={() => navigate(`/evaluations/${q.id}/analyse`)}
                            title="Analyse qualitative"
                          >
                            <i className="bi bi-graph-up-arrow"></i>
                          </button>
                        )}
                        <i className="bi bi-chevron-right" onClick={() => navigate(`/evaluations/${q.id}`)} style={{ color: 'var(--text-muted)', fontSize: '0.75rem', flexShrink: 0, cursor: 'pointer' }}></i>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* ══════════════════════════════════════════════════════════════════
          ONGLET QUESTIONNAIRES
         ══════════════════════════════════════════════════════════════════ */}
      {activeTab === 'questionnaires' && (
        <div>
          {/* Filtres */}
          <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
            <select className="form-select form-select-sm" style={{ width: 'auto', minWidth: '140px' }}
              value={filters.statut} onChange={e => setFilters(f => ({ ...f, statut: e.target.value }))}>
              <option value="">Tous les statuts</option>
              <option value="BROUILLON">Brouillon</option>
              <option value="PUBLIE">Publié</option>
              <option value="FERME">Fermé</option>
            </select>
            <select className="form-select form-select-sm" style={{ width: 'auto', minWidth: '160px' }}
              value={filters.categorie} onChange={e => setFilters(f => ({ ...f, categorie: e.target.value }))}>
              <option value="">Toutes catégories</option>
              {refCategories.map(c => <option key={c.id} value={c.libelle}>{c.libelle}</option>)}
              {refCategories.length === 0 && (<><option value="A">A</option><option value="B">B</option><option value="C">C</option><option value="D">D</option></>)}
            </select>
          </div>

          {/* Liste */}
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : questionnaires.length === 0 ? (
            <div className="empty-state">
              <i className="bi bi-clipboard-check" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
              <p>Aucun questionnaire trouvé</p>
              <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>Créer un questionnaire</button>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: '1rem' }}>
              {questionnaires.map(q => (
                <div key={q.id} className="card" style={{ padding: '1.25rem' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
                        <span style={{ ...STATUT_COLORS[q.statut], fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px', borderRadius: '20px', letterSpacing: '0.04em' }}>
                          {STATUT_LABELS[q.statut]}
                        </span>
                        {(q.categories || []).map(c => (
                          <span key={c} style={{ fontSize: '0.72rem', background: '#f3e5f5', color: '#6a1b9a', padding: '2px 8px', borderRadius: '20px', fontWeight: 600 }}>{c}</span>
                        ))}
                        {(q.grades || []).map(g => (
                          <span key={g} style={{ fontSize: '0.72rem', background: '#e8eaf6', color: '#283593', padding: '2px 8px', borderRadius: '20px', fontWeight: 600 }}>{g}</span>
                        ))}
                        {(q.groupes || []).map(g => (
                          <span key={g} style={{ fontSize: '0.72rem', background: '#fff8e0', color: '#e69700', padding: '2px 8px', borderRadius: '20px', fontWeight: 600 }}>{g}</span>
                        ))}
                      </div>
                      <h4 style={{ margin: 0, fontWeight: 700, fontSize: '1.05rem', cursor: 'pointer', color: 'var(--primary)' }}
                        onClick={() => navigate(`/evaluations/${q.id}`)}>
                        {(q.titres || []).join(' · ')}
                      </h4>
                      <div style={{ display: 'flex', gap: '1rem', marginTop: '0.4rem', flexWrap: 'wrap', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                        <span><i className="bi bi-question-circle me-1"></i>{q.nb_questions} question{q.nb_questions !== 1 ? 's' : ''}</span>
                        {q.createur_nom && <span><i className="bi bi-person me-1"></i>{q.createur_nom}</span>}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0, alignItems: 'center' }}>
                      {q.statut === 'BROUILLON' && (
                        <button className="btn btn-sm btn-success" onClick={() => handleChangeStatut(q.id, 'PUBLIE')} title="Publier">
                          <i className="bi bi-send"></i>
                        </button>
                      )}
                      {q.statut === 'PUBLIE' && (
                        <button className="btn btn-sm btn-secondary" onClick={() => handleChangeStatut(q.id, 'FERME')} title="Fermer">
                          <i className="bi bi-lock"></i>
                        </button>
                      )}
                      {q.statut === 'FERME' && (
                        <button className="btn btn-sm btn-outline-secondary" onClick={() => handleChangeStatut(q.id, 'BROUILLON')} title="Remettre en brouillon">
                          <i className="bi bi-arrow-counterclockwise"></i>
                        </button>
                      )}
                      <button className="btn btn-sm btn-outline-primary" onClick={() => navigate(`/evaluations/${q.id}`)} title="Voir / modifier">
                        <i className="bi bi-pencil"></i>
                      </button>
                      {q.statut === 'BROUILLON' && (
                        <button className="btn btn-sm btn-outline-danger" onClick={() => handleDelete(q.id)} title="Supprimer">
                          <i className="bi bi-trash"></i>
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && activeTab === 'questionnaires' && totalPages > 1 && (
            <div style={{ marginTop: '1rem' }}>
              <Pagination page={page} totalPages={totalPages} onPageChange={setPage} totalCount={totalCount} />
            </div>
          )}
        </div>
      )}

      {/* ── Modal création ─────────────────────────────────────────────── */}
      {showCreate && (
        <div className="modal-overlay" onClick={closeCreate}>
          <div className="modal-content" style={{ maxWidth: '580px', maxHeight: 'calc(100vh - 3rem)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h4 className="modal-title">Nouveau questionnaire</h4>
              <button className="btn-close" onClick={closeCreate}>&times;</button>
            </div>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', flex: 1, overflowY: 'auto', minHeight: 0 }}>

                {/* Titres (modules) */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Modules ciblés <span style={{ color: 'red' }}>*</span>
                    {form.titres.length > 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 400 }}>{form.titres.length} sélectionné{form.titres.length > 1 ? 's' : ''}</span>}
                  </label>
                  <input className="form-control form-control-sm" placeholder="Rechercher un module…"
                    value={titreSearch} onChange={e => setTitreSearch(e.target.value)} style={{ marginBottom: '0.4rem' }} />
                  <div style={{ maxHeight: '160px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.4rem 0.6rem', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    {refModules.filter(m => !titreSearch || m.intitule.toLowerCase().includes(titreSearch.toLowerCase())).map(m => (
                      <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '3px 2px', cursor: 'pointer', borderRadius: '4px', background: form.titres.includes(m.intitule) ? '#e3f2fd' : 'transparent', fontSize: '0.875rem' }}>
                        <input type="checkbox" checked={form.titres.includes(m.intitule)} onChange={() => toggleItem('titres', m.intitule)} style={{ flexShrink: 0 }} />
                        {m.intitule}
                      </label>
                    ))}
                    {refModules.filter(m => !titreSearch || m.intitule.toLowerCase().includes(titreSearch.toLowerCase())).length === 0 && (
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', padding: '4px' }}>Aucun module trouvé</span>
                    )}
                  </div>
                </div>

                {/* Catégories */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Catégories
                    {form.categories.length > 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 400 }}>{form.categories.length} sélectionnée{form.categories.length > 1 ? 's' : ''}</span>}
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                    {refCategories.map(c => (
                      <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '4px 10px', borderRadius: '20px', cursor: 'pointer', border: '1.5px solid', borderColor: form.categories.includes(c.libelle) ? '#6a1b9a' : 'var(--border)', background: form.categories.includes(c.libelle) ? '#f3e5f5' : 'transparent', color: form.categories.includes(c.libelle) ? '#6a1b9a' : 'inherit', fontSize: '0.85rem', fontWeight: form.categories.includes(c.libelle) ? 700 : 400, transition: 'all .15s' }}>
                        <input type="checkbox" style={{ display: 'none' }} checked={form.categories.includes(c.libelle)} onChange={() => { toggleItem('categories', c.libelle); setForm(f => ({ ...f, grades: f.grades.filter(g => { const gr = refGrades.find(rg => rg.libelle === g); return gr ? refCategories.find(rc => rc.libelle === c.libelle)?.id !== gr.categorie_id : true }) })) }} />
                        {c.libelle}
                      </label>
                    ))}
                  </div>
                </div>

                {/* Grades */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Grades
                    {form.grades.length > 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 400 }}>{form.grades.length} sélectionné{form.grades.length > 1 ? 's' : ''}</span>}
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                    {refGrades.filter(g => form.categories.length === 0 || refCategories.find(c => form.categories.includes(c.libelle) && c.id === g.categorie_id)).map(g => (
                      <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '4px 10px', borderRadius: '20px', cursor: 'pointer', border: '1.5px solid', borderColor: form.grades.includes(g.libelle) ? '#283593' : 'var(--border)', background: form.grades.includes(g.libelle) ? '#e8eaf6' : 'transparent', color: form.grades.includes(g.libelle) ? '#283593' : 'inherit', fontSize: '0.85rem', fontWeight: form.grades.includes(g.libelle) ? 700 : 400, transition: 'all .15s' }}>
                        <input type="checkbox" style={{ display: 'none' }} checked={form.grades.includes(g.libelle)} onChange={() => toggleItem('grades', g.libelle)} />
                        {g.libelle}
                      </label>
                    ))}
                  </div>
                </div>

                {/* Groupes */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Groupes
                    {form.groupes.length > 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 400 }}>{form.groupes.length} sélectionné{form.groupes.length > 1 ? 's' : ''}</span>}
                    {form.groupes.length === 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 400 }}>Tous les groupes</span>}
                  </label>
                  <div style={{ maxHeight: '140px', overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: '0.4rem', alignContent: 'flex-start', padding: '0.25rem' }}>
                    {refGroupes.map(g => (
                      <label key={g} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '4px 10px', borderRadius: '20px', cursor: 'pointer', border: '1.5px solid', borderColor: form.groupes.includes(g) ? '#e69700' : 'var(--border)', background: form.groupes.includes(g) ? '#fff8e0' : 'transparent', color: form.groupes.includes(g) ? '#e69700' : 'inherit', fontSize: '0.85rem', fontWeight: form.groupes.includes(g) ? 700 : 400, transition: 'all .15s' }}>
                        <input type="checkbox" style={{ display: 'none' }} checked={form.groupes.includes(g)} onChange={() => toggleItem('groupes', g)} />
                        {g}
                      </label>
                    ))}
                    {refGroupes.length === 0 && (
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Aucun groupe disponible</span>
                    )}
                  </div>
                </div>

                {/* Dates */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label className="form-label">Date d'ouverture</label>
                    <input type="datetime-local" className="form-control" value={form.date_ouverture} onChange={e => setForm(f => ({ ...f, date_ouverture: e.target.value }))} />
                  </div>
                  <div>
                    <label className="form-label">Date de fermeture</label>
                    <input type="datetime-local" className="form-control" value={form.date_fermeture} onChange={e => setForm(f => ({ ...f, date_fermeture: e.target.value }))} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={closeCreate}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={creating}>
                  {creating ? <><span className="spinner-border spinner-border-sm me-1"></span>Création…</> : 'Créer et ajouter les questions'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
