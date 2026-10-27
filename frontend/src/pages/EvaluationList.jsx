import { useState, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useReferentiels } from '../hooks/useReferentiels'
import { parsePaginatedResponse } from '../utils/paginatedResponse'
import Pagination from '../components/Pagination'

const CIBLE_LABELS = { COURS: 'Évaluation du module', FORMATEUR: "Évaluation de l'enseignant" }
const STATUT_LABELS = { BROUILLON: 'Brouillon', PUBLIE: 'Publié', FERME: 'Fermé' }
const STATUT_COLORS = {
  BROUILLON: { background: '#fff8e0', color: '#e69700' },
  PUBLIE:    { background: '#e8eff5', color: '#125a99' },
  FERME:     { background: '#f5f5f5', color: '#616161' },
}


const SECTION_COLORS = {
  COURS:     { bg: '#e3f2fd', color: '#1565c0', icon: 'bi-book' },
  FORMATEUR: { bg: '#f3e5f5', color: '#6a1b9a', icon: 'bi-person-video3' },
}

function AuditeurEvaluationList() {
  const { showToast } = useToast()
  const [questionnaires, setQuestionnaires] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchMesQuestionnaires = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/evaluations/mes-questionnaires/')
      setQuestionnaires(data)
    } catch {
      showToast('Erreur lors du chargement des évaluations', 'error')
    } finally {
      setLoading(false)
    }
  }, [showToast])

  useEffect(() => { fetchMesQuestionnaires() }, [fetchMesQuestionnaires])

  if (loading) return <div className="loading"><div className="spinner"></div></div>

  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ margin: 0, fontWeight: 700 }}>Mes évaluations</h2>
        <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
          Questionnaires disponibles pour vous
        </p>
      </div>
      {questionnaires.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-clipboard-check" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>Aucune évaluation disponible pour le moment.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {questionnaires.map(q => {
            const sections = [...new Set((q.questions || []).map(qu => qu.section || 'COURS'))]
            return (
              <div key={q.id} style={{ background: 'var(--card-bg, #fff)', border: '1px solid var(--border)', borderRadius: '10px', padding: '1rem 1.25rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 700, fontSize: '1rem', marginBottom: '0.3rem' }}>
                    {(q.titres || []).join(' · ')}
                  </div>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {sections.map(s => {
                      const sc = SECTION_COLORS[s]
                      return (
                        <span key={s} style={{ fontSize: '0.75rem', background: sc.bg, color: sc.color, padding: '2px 10px', borderRadius: '20px', fontWeight: 600 }}>
                          <i className={`bi ${sc.icon} me-1`}></i>{s === 'COURS' ? 'Module' : 'Enseignant'}
                        </span>
                      )
                    })}
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {(q.questions || []).length} question{(q.questions || []).length !== 1 ? 's' : ''}
                    </span>
                  </div>
                </div>
                <Link to={`/evaluations/repondre/${q.id}`} className="btn btn-primary btn-sm">
                  <i className="bi bi-pencil-square me-1"></i>Répondre
                </Link>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function EvaluationList() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [questionnaires, setQuestionnaires] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [filters, setFilters] = useState({ cible: '', statut: '', categorie: '' })
  const [refModules, setRefModules] = useState([])
  const [refCategories, setRefCategories] = useState([])
  const [refGrades, setRefGrades] = useState([])
  const [refGroupes, setRefGroupes] = useState([])
  const [titreSearch, setTitreSearch] = useState('')
  const [showCreate, setShowCreate] = useState(false)
  const [creating, setCreating] = useState(false)
  const EMPTY_FORM = { titres: [], cible: 'COURS', categories: [], grades: [], groupes: [], date_ouverture: '', date_fermeture: '' }
  const [form, setForm] = useState(EMPTY_FORM)

  const toggleItem = (field, value) => {
    setForm(f => {
      const arr = f[field]
      return { ...f, [field]: arr.includes(value) ? arr.filter(x => x !== value) : [...arr, value] }
    })
  }

  const fetchQuestionnaires = useCallback(async () => {
    if (user?.role === 'AUDITEUR') return
    setLoading(true)
    try {
      const params = new URLSearchParams({ page: String(page), page_size: '50' })
      if (filters.cible) params.append('cible', filters.cible)
      if (filters.statut) params.append('statut', filters.statut)
      if (filters.categorie) params.append('categorie', filters.categorie)
      const res = await api.get(`/evaluations/questionnaires/?${params}`)
      const { results, count, totalPages: pages } = parsePaginatedResponse(res.data, 50)
      setQuestionnaires(results)
      setTotalCount(count)
      setTotalPages(pages)
    } catch {
      showToast('Erreur lors du chargement des questionnaires', 'error')
    } finally {
      setLoading(false)
    }
  }, [filters, page, showToast, user?.role])

  const { data: referentielsData } = useReferentiels({ enabled: user?.role !== 'AUDITEUR' })

  useEffect(() => {
    if (!referentielsData) return
    setRefModules((referentielsData.modules || []).filter(m => m.actif !== false))
    setRefCategories((referentielsData.categories || []).filter(c => c.actif !== false))
    setRefGrades((referentielsData.grades || []).filter(g => g.actif !== false))
    setRefGroupes(referentielsData.groupes || [])
  }, [referentielsData])

  useEffect(() => { setPage(1) }, [filters.cible, filters.statut, filters.categorie])

  useEffect(() => { fetchQuestionnaires() }, [fetchQuestionnaires])

  if (user?.role === 'AUDITEUR') return <AuditeurEvaluationList />

  const closeCreate = () => { setShowCreate(false); setTitreSearch(''); setForm(EMPTY_FORM) }

  const handleCreate = async (e) => {
    e.preventDefault()
    if (form.titres.length === 0) { showToast('Sélectionnez au moins un module', 'error'); return }
    setCreating(true)
    try {
      const payload = {
        titres: form.titres,
        cible: form.cible,
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
      const msg = err?.response?.data?.detail || 'Impossible de supprimer ce questionnaire'
      showToast(msg, 'error')
    }
  }

  return (
    <div>
      {/* En-tête */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700 }}>Évaluations</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            Gérez les questionnaires d'évaluation des modules et enseignants
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <i className="bi bi-plus-lg me-1"></i> Nouveau questionnaire
          </button>
        </div>
      </div>

      {/* Filtres */}
      <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <select
          className="form-select form-select-sm"
          style={{ width: 'auto', minWidth: '160px' }}
          value={filters.cible}
          onChange={e => setFilters(f => ({ ...f, cible: e.target.value }))}
        >
          <option value="">Toutes les cibles</option>
          <option value="COURS">Module</option>
          <option value="FORMATEUR">Enseignant</option>
        </select>
        <select
          className="form-select form-select-sm"
          style={{ width: 'auto', minWidth: '140px' }}
          value={filters.statut}
          onChange={e => setFilters(f => ({ ...f, statut: e.target.value }))}
        >
          <option value="">Tous les statuts</option>
          <option value="BROUILLON">Brouillon</option>
          <option value="PUBLIE">Publié</option>
          <option value="FERME">Fermé</option>
        </select>
        <select
          className="form-select form-select-sm"
          style={{ width: 'auto', minWidth: '160px' }}
          value={filters.categorie}
          onChange={e => setFilters(f => ({ ...f, categorie: e.target.value }))}
        >
          <option value="">Toutes catégories</option>
          {refCategories.map(c => <option key={c.id} value={c.libelle}>{c.libelle}</option>)}
          {refCategories.length === 0 && (
            <>
              <option value="A">A</option>
              <option value="B">B</option>
              <option value="C">C</option>
              <option value="D">D</option>
            </>
          )}
        </select>
      </div>

      {/* Liste */}
      {loading ? (
        <div className="loading"><div className="spinner"></div></div>
      ) : questionnaires.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-clipboard-check" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>Aucun questionnaire trouvé</p>
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
            Créer un questionnaire
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '1rem' }}>
          {questionnaires.map(q => (
            <div key={q.id} className="card" style={{ padding: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ flex: 1, minWidth: '200px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.35rem' }}>
                    <span
                      style={{
                        ...STATUT_COLORS[q.statut],
                        fontSize: '0.72rem', fontWeight: 700, padding: '2px 8px',
                        borderRadius: '20px', letterSpacing: '0.04em',
                      }}
                    >
                      {STATUT_LABELS[q.statut]}
                    </span>
                    <span style={{ fontSize: '0.72rem', background: '#e3f2fd', color: '#1565c0', padding: '2px 8px', borderRadius: '20px', fontWeight: 600 }}>
                      <i className={`bi bi-${q.cible === 'COURS' ? 'book' : 'person-video3'} me-1`}></i>
                      {CIBLE_LABELS[q.cible]}
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

      {!loading && totalPages > 1 && (
        <div style={{ marginTop: '1rem' }}>
          <Pagination page={page} totalPages={totalPages} onPageChange={setPage} totalCount={totalCount} />
        </div>
      )}

      {/* Modal création */}
      {showCreate && (
        <div className="modal-overlay" onClick={closeCreate}>
          <div className="modal-content" style={{ maxWidth: '580px', maxHeight: 'calc(100vh - 3rem)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h4 className="modal-title">Nouveau questionnaire</h4>
              <button className="btn-close" onClick={closeCreate}>&times;</button>
            </div>
            <form onSubmit={handleCreate} style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflow: 'hidden' }}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', flex: 1, overflowY: 'auto', minHeight: 0 }}>

                {/* ── Titres (modules) ── */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Modules ciblés <span style={{ color: 'red' }}>*</span>
                    {form.titres.length > 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 400 }}>{form.titres.length} sélectionné{form.titres.length > 1 ? 's' : ''}</span>}
                  </label>
                  <input
                    className="form-control form-control-sm"
                    placeholder="Rechercher un module…"
                    value={titreSearch}
                    onChange={e => setTitreSearch(e.target.value)}
                    style={{ marginBottom: '0.4rem' }}
                  />
                  <div style={{ maxHeight: '160px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.4rem 0.6rem', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    {refModules
                      .filter(m => !titreSearch || m.intitule.toLowerCase().includes(titreSearch.toLowerCase()))
                      .map(m => (
                        <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '3px 2px', cursor: 'pointer', borderRadius: '4px', background: form.titres.includes(m.intitule) ? '#e3f2fd' : 'transparent', fontSize: '0.875rem' }}>
                          <input type="checkbox" checked={form.titres.includes(m.intitule)} onChange={() => toggleItem('titres', m.intitule)} style={{ flexShrink: 0 }} />
                          {m.intitule}
                        </label>
                      ))
                    }
                    {refModules.filter(m => !titreSearch || m.intitule.toLowerCase().includes(titreSearch.toLowerCase())).length === 0 && (
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)', padding: '4px' }}>Aucun module trouvé</span>
                    )}
                  </div>
                </div>

                {/* ── Cible ── */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>Cible <span style={{ color: 'red' }}>*</span></label>
                  <select className="form-select" value={form.cible} onChange={e => setForm(f => ({ ...f, cible: e.target.value }))}>
                    <option value="COURS">Module</option>
                    <option value="FORMATEUR">Enseignant</option>
                  </select>
                </div>

                {/* ── Catégories ── */}
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

                {/* ── Grades (filtrés par catégories cochées) ── */}
                <div>
                  <label className="form-label" style={{ fontWeight: 600 }}>
                    Grades
                    {form.grades.length > 0 && <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', color: 'var(--primary)', fontWeight: 400 }}>{form.grades.length} sélectionné{form.grades.length > 1 ? 's' : ''}</span>}
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                    {refGrades
                      .filter(g => {
                        if (form.categories.length === 0) return true
                        const cat = refCategories.find(c => form.categories.includes(c.libelle) && c.id === g.categorie_id)
                        return !!cat
                      })
                      .map(g => (
                        <label key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '4px 10px', borderRadius: '20px', cursor: 'pointer', border: '1.5px solid', borderColor: form.grades.includes(g.libelle) ? '#283593' : 'var(--border)', background: form.grades.includes(g.libelle) ? '#e8eaf6' : 'transparent', color: form.grades.includes(g.libelle) ? '#283593' : 'inherit', fontSize: '0.85rem', fontWeight: form.grades.includes(g.libelle) ? 700 : 400, transition: 'all .15s' }}>
                          <input type="checkbox" style={{ display: 'none' }} checked={form.grades.includes(g.libelle)} onChange={() => toggleItem('grades', g.libelle)} />
                          {g.libelle}
                        </label>
                      ))
                    }
                    {refGrades.filter(g => form.categories.length === 0 || refCategories.find(c => form.categories.includes(c.libelle) && c.id === g.categorie_id)).length === 0 && (
                      <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Aucun grade disponible</span>
                    )}
                  </div>
                </div>

                {/* ── Groupes ── */}
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

                {/* ── Dates ── */}
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
