import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useReferentiels } from '../hooks/useReferentiels'

const EMPTY_FORM = {
  titre: '', description: '', module: '', chapitre: '',
  seuil_reussite: '70', duree_max_minutes: '', actif: true,
  date_ouverture: '', date_fermeture: '',
  categories: [], grades: [],
}

export default function QuizList() {
  const { showToast } = useToast()
  const { user } = useAuth()
  const navigate = useNavigate()
  const [quizzes, setQuizzes] = useState([])
  const [loading, setLoading] = useState(true)
  const [modules, setModules] = useState([])
  const [refCategories, setRefCategories] = useState([])
  const [refGrades, setRefGrades] = useState([])
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [creating, setCreating] = useState(false)
  const [moduleSearch, setModuleSearch] = useState('')

  const isAuditeur = user?.role === 'AUDITEUR'

  const fetchQuizzes = useCallback(async () => {
    setLoading(true)
    try {
      const endpoint = isAuditeur ? '/evaluations/mes-quiz/' : '/evaluations/quiz/'
      const { data } = await api.get(endpoint)
      setQuizzes(data)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur chargement quiz', 'error')
    } finally { setLoading(false) }
  }, [isAuditeur, showToast])

  const { data: referentielsData } = useReferentiels({ enabled: !isAuditeur })

  useEffect(() => {
    if (!referentielsData) return
    setModules((referentielsData.modules || []).filter(m => m.actif !== false))
    setRefCategories((referentielsData.categories || []).filter(c => c.actif !== false))
    setRefGrades((referentielsData.grades || []).filter(g => g.actif !== false))
  }, [referentielsData])

  useEffect(() => { fetchQuizzes() }, [fetchQuizzes])

  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.titre.trim()) { showToast('Le titre est requis', 'error'); return }
    if (!form.module) { showToast('Sélectionnez un module', 'error'); return }
    setCreating(true)
    try {
      const payload = {
        titre: form.titre.trim(),
        module: parseInt(form.module),
        description: form.description,
        chapitre: form.chapitre,
        seuil_reussite: parseFloat(form.seuil_reussite) || 70,
        actif: form.actif,
        categories: form.categories,
        grades: form.grades,
        ...(form.duree_max_minutes ? { duree_max_minutes: parseInt(form.duree_max_minutes) } : {}),
        ...(form.date_ouverture ? { date_ouverture: form.date_ouverture } : {}),
        ...(form.date_fermeture ? { date_fermeture: form.date_fermeture } : {}),
      }
      const { data } = await api.post('/evaluations/quiz/', payload)
      showToast('Quiz créé', 'success')
      setShowCreate(false)
      setForm(EMPTY_FORM)
      setModuleSearch('')
      navigate(`/quiz/${data.id}`)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur création', 'error')
    } finally { setCreating(false) }
  }

  const handleToggleActif = async (q) => {
    try {
      const { data } = await api.patch(`/evaluations/quiz/${q.id}/`, { actif: !q.actif })
      setQuizzes(qs => qs.map(x => x.id === q.id ? { ...x, actif: data.actif } : x))
      showToast(data.actif ? 'Quiz activé' : 'Quiz désactivé', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur mise à jour', 'error')
    }
  }

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer ce quiz et toutes ses questions ?')) return
    try {
      await api.delete(`/evaluations/quiz/${id}/`)
      showToast('Quiz supprimé', 'success')
      fetchQuizzes()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur suppression', 'error')
    }
  }

  const filteredModules = modules.filter(m =>
    !moduleSearch || m.intitule.toLowerCase().includes(moduleSearch.toLowerCase())
  )

  const toggleItem = (field, val) => setForm(f => {
    const arr = f[field]
    return { ...f, [field]: arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val] }
  })

  const filteredGrades = refGrades.filter(g =>
    form.categories.length === 0 || refCategories.find(c => form.categories.includes(c.libelle) && c.id === g.categorie_id)
  )

  if (loading) return <div className="loading"><div className="spinner"></div></div>

  return (
    <div>
      {/* En-tête */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700 }}>Quiz manuels</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {isAuditeur
              ? 'Passez le quiz pour valider la lecture des manuels ou l\'évaluation pédagogique.'
              : 'Créez et gérez les quiz pour les étudiants.'}
          </p>
        </div>
        {!isAuditeur && (
          <button className="btn btn-primary" onClick={() => setShowCreate(true)}>
            <i className="bi bi-plus-lg me-1"></i>Nouveau quiz
          </button>
        )}
      </div>

      {/* Liste */}
      {quizzes.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-question-square" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>{isAuditeur ? 'Aucun quiz disponible' : 'Aucun quiz. Créez le premier.'}</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          {quizzes.map(q => (
            <div key={q.id} className="card" style={{ padding: '0.9rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
              <div style={{ minWidth: '240px', flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <span style={{ fontWeight: 700 }}>{q.titre}</span>
                </div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{q.module_intitule}</div>
                {!isAuditeur && (
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                    <span><i className="bi bi-question-circle me-1"></i>{q.nb_questions_reelles ?? 0} question{q.nb_questions_reelles !== 1 ? 's' : ''}</span>
                    {q.seuil_reussite != null && <span><i className="bi bi-bar-chart me-1"></i>Seuil {q.seuil_reussite}%</span>}
                    {q.duree_max_minutes && <span><i className="bi bi-clock me-1"></i>{q.duree_max_minutes} min</span>}
                    {q.date_fermeture && <span><i className="bi bi-calendar-x me-1"></i>Fermeture : {q.date_fermeture.slice(0, 10)}</span>}
                  </div>
                )}
                {isAuditeur && q.date_fermeture && (
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>Fermeture : {q.date_fermeture.slice(0, 10)}</div>
                )}
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                {isAuditeur ? (
                  <Link to={`/quiz/${q.id}`} className="btn btn-primary btn-sm">Passer</Link>
                ) : (
                  <>
                    <button
                      className={`btn btn-sm ${q.actif ? 'btn-success' : 'btn-outline-secondary'}`}
                      onClick={() => handleToggleActif(q)}
                      title={q.actif ? 'Désactiver' : 'Activer'}
                      style={{ minWidth: '90px' }}
                    >
                      <i className={`bi ${q.actif ? 'bi-toggle-on' : 'bi-toggle-off'} me-1`}></i>
                      {q.actif ? 'Actif' : 'Inactif'}
                    </button>
                    <Link to={`/quiz/${q.id}`} className="btn btn-outline-primary btn-sm">
                      <i className="bi bi-pencil me-1"></i>Éditer
                    </Link>
                    <button className="btn btn-outline-danger btn-sm" onClick={() => handleDelete(q.id)}>
                      <i className="bi bi-trash"></i>
                    </button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Modal création */}
      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem' }}
          onClick={() => { setShowCreate(false); setForm(EMPTY_FORM); setModuleSearch('') }}>
          <div className="card" style={{ maxWidth: 500, width: '100%', padding: '1.5rem', maxHeight: '90vh', overflowY: 'auto' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ marginTop: 0, fontWeight: 700 }}>Nouveau quiz</h3>
            <form onSubmit={handleCreate}>
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Titre *</label>
                <input className="form-control" value={form.titre}
                  onChange={e => setForm(f => ({ ...f, titre: e.target.value }))} placeholder="Ex: Quiz chapitre 1" />
              </div>
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Module *</label>
                <input className="form-control form-control-sm" placeholder="Rechercher un module…"
                  value={moduleSearch} onChange={e => setModuleSearch(e.target.value)}
                  style={{ marginBottom: '0.35rem' }} />
                <div style={{ maxHeight: '140px', overflowY: 'auto', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.4rem' }}>
                  {filteredModules.length === 0
                    ? <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Aucun module trouvé</span>
                    : filteredModules.map(m => (
                      <label key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '3px', cursor: 'pointer', borderRadius: '4px', background: String(form.module) === String(m.id) ? '#e3f2fd' : 'transparent', fontSize: '0.875rem' }}>
                        <input type="radio" name="module" value={m.id} checked={String(form.module) === String(m.id)}
                          onChange={() => setForm(f => ({ ...f, module: m.id }))} />
                        {m.intitule}
                      </label>
                    ))
                  }
                </div>
              </div>
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Description</label>
                <textarea className="form-control" rows={2} value={form.description}
                  onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              {refCategories.length > 0 && (
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Groupes ciblés <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>(vide = tous)</span></label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.3rem' }}>
                    {refCategories.map(c => {
                      const sel = form.categories.includes(c.libelle)
                      return (
                        <span key={c.id}
                          onClick={() => toggleItem('categories', c.libelle)}
                          style={{
                            cursor: 'pointer', padding: '4px 12px', borderRadius: '20px',
                            fontSize: '0.82rem', userSelect: 'none', fontWeight: sel ? 600 : 400,
                            background: sel ? '#1976d2' : '#f0f0f0',
                            color: sel ? '#fff' : '#333',
                            border: `1px solid ${sel ? '#1976d2' : '#ccc'}`,
                            transition: 'all 0.15s',
                          }}
                        >{c.libelle}</span>
                      )
                    })}
                  </div>
                </div>
              )}
              {refGrades.length > 0 && (
                <div style={{ marginBottom: '0.75rem' }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Grades ciblés <span style={{ fontWeight: 400, color: 'var(--text-muted)' }}>(vide = tous)</span></label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.3rem' }}>
                    {filteredGrades.length === 0
                      ? <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Sélectionnez un groupe d'abord</span>
                      : filteredGrades.map(g => (
                        <span key={g.id}
                          onClick={() => toggleItem('grades', g.libelle)}
                          style={{
                            cursor: 'pointer', padding: '4px 12px', borderRadius: '20px',
                            fontSize: '0.82rem', userSelect: 'none', fontWeight: form.grades.includes(g.libelle) ? 600 : 400,
                            background: form.grades.includes(g.libelle) ? '#0d47a1' : '#f0f0f0',
                            color: form.grades.includes(g.libelle) ? '#fff' : '#333',
                            border: `1px solid ${form.grades.includes(g.libelle) ? '#0d47a1' : '#ccc'}`,
                            transition: 'all 0.15s',
                          }}
                        >{g.libelle}</span>
                      ))
                    }
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Seuil de réussite (%)</label>
                  <input className="form-control" type="number" min="0" max="100" value={form.seuil_reussite}
                    onChange={e => setForm(f => ({ ...f, seuil_reussite: e.target.value }))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Durée max (min)</label>
                  <input className="form-control" type="number" min="1" value={form.duree_max_minutes}
                    onChange={e => setForm(f => ({ ...f, duree_max_minutes: e.target.value }))} placeholder="Illimitée" />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Date ouverture</label>
                  <input className="form-control" type="date" value={form.date_ouverture}
                    onChange={e => setForm(f => ({ ...f, date_ouverture: e.target.value }))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Date fermeture</label>
                  <input className="form-control" type="date" value={form.date_fermeture}
                    onChange={e => setForm(f => ({ ...f, date_fermeture: e.target.value }))} />
                </div>
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.actif}
                    onChange={e => setForm(f => ({ ...f, actif: e.target.checked }))} />
                  Quiz actif (visible par les étudiants)
                </label>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline-secondary btn-sm"
                  onClick={() => { setShowCreate(false); setForm(EMPTY_FORM); setModuleSearch('') }}>Annuler</button>
                <button type="submit" className="btn btn-primary btn-sm" disabled={creating}>
                  {creating ? 'Création…' : 'Créer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
