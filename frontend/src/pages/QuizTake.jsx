import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { useReferentiels } from '../hooks/useReferentiels'

function toggleArr(arr, val) {
  return arr.includes(val) ? arr.filter(x => x !== val) : [...arr, val]
}

const TYPE_LABELS = { QCM: 'QCM', VRAI_FAUX: 'Vrai/Faux', OUVERTE: 'Ouverte' }
const EMPTY_Q = { question: '', type_question: 'QCM', reponse_correcte: '', options: ['', '', '', ''], points: '1', ordre: '' }

// ─── Vue auditeur ────────────────────────────────────────────
function QuizPassage({ quiz }) {
  const { showToast } = useToast()
  const navigate = useNavigate()
  const [answers, setAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)

  const handleChange = (qId, value) => setAnswers(a => ({ ...a, [qId]: value }))

  const submit = async (e) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload = { reponses: {}, temps_pris_minutes: 5 }
      for (const q of quiz.questions) payload.reponses[String(q.id)] = answers[q.id] ?? ''
      const { data } = await api.post(`/evaluations/quiz/${quiz.id}/soumettre/`, payload)
      showToast(`Score : ${data.score}% — ${data.reussi ? 'Réussi ✓' : 'Non réussi'}`, data.reussi ? 'success' : 'error')
      navigate('/evaluations')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur soumission', 'error')
    } finally { setSubmitting(false) }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
        <Link to="/quiz" className="btn btn-outline-secondary btn-sm"><i className="bi bi-arrow-left"></i></Link>
        <h2 style={{ margin: 0, fontWeight: 700 }}>{quiz.titre}</h2>
      </div>
      {quiz.description && <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>{quiz.description}</p>}
      <form onSubmit={submit}>
        {(quiz.questions || []).map((q, idx) => (
          <div key={q.id} className="card" style={{ padding: '0.9rem', marginBottom: '0.6rem' }}>
            <div style={{ fontWeight: 600, marginBottom: '0.5rem' }}>
              <span style={{ color: 'var(--text-muted)', marginRight: '0.5rem' }}>{idx + 1}.</span>{q.question}
              <span style={{ float: 'right', fontSize: '0.78rem', color: 'var(--text-muted)' }}>{q.points} pt{q.points > 1 ? 's' : ''}</span>
            </div>
            {q.type_question === 'QCM' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                {(q.options || []).filter(o => o).map((opt, i) => (
                  <label key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                    <input type="radio" name={String(q.id)} value={opt} checked={answers[q.id] === opt} onChange={() => handleChange(q.id, opt)} />
                    {opt}
                  </label>
                ))}
              </div>
            )}
            {q.type_question === 'VRAI_FAUX' && (
              <div style={{ display: 'flex', gap: '1.5rem' }}>
                {['vrai', 'faux'].map(v => (
                  <label key={v} style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer' }}>
                    <input type="radio" name={String(q.id)} value={v} checked={answers[q.id] === v} onChange={() => handleChange(q.id, v)} />
                    {v.charAt(0).toUpperCase() + v.slice(1)}
                  </label>
                ))}
              </div>
            )}
            {q.type_question === 'OUVERTE' && (
              <textarea className="form-control" rows={3} value={answers[q.id] || ''} onChange={e => handleChange(q.id, e.target.value)} />
            )}
          </div>
        ))}
        <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
          <Link to="/quiz" className="btn btn-outline-secondary btn-sm">Annuler</Link>
          <button className="btn btn-primary" disabled={submitting}>{submitting ? 'Envoi…' : 'Soumettre'}</button>
        </div>
      </form>
    </div>
  )
}

// ─── Vue staff : édition quiz + questions ───────────────────
function QuizEdit({ quiz: initialQuiz }) {
  const { showToast } = useToast()
  const [quiz, setQuiz] = useState(initialQuiz)
  const [questions, setQuestions] = useState(initialQuiz.questions || [])
  const [showAdd, setShowAdd] = useState(false)
  const [form, setForm] = useState(EMPTY_Q)
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [editForm, setEditForm] = useState(null)
  const [showMeta, setShowMeta] = useState(false)
  const [metaForm, setMetaForm] = useState(null)
  const [refCategories, setRefCategories] = useState([])
  const [refGrades, setRefGrades] = useState([])
  const [savingMeta, setSavingMeta] = useState(false)

  const { data: referentielsData } = useReferentiels()

  useEffect(() => {
    if (!referentielsData) return
    setRefCategories((referentielsData.categories || []).filter(c => c.actif !== false))
    setRefGrades((referentielsData.grades || []).filter(g => g.actif !== false))
  }, [referentielsData])

  const openMeta = () => {
    setMetaForm({
      titre: quiz.titre || '',
      description: quiz.description || '',
      chapitre: quiz.chapitre || '',
      seuil_reussite: String(quiz.seuil_reussite ?? 70),
      duree_max_minutes: String(quiz.duree_max_minutes || ''),
      actif: quiz.actif,
      date_ouverture: quiz.date_ouverture ? quiz.date_ouverture.slice(0, 10) : '',
      date_fermeture: quiz.date_fermeture ? quiz.date_fermeture.slice(0, 10) : '',
      categories: quiz.categories || [],
      grades: quiz.grades || [],
    })
    setShowMeta(true)
  }

  const handleSaveMeta = async (e) => {
    e.preventDefault()
    if (!metaForm.titre.trim()) { showToast('Le titre est requis', 'error'); return }
    setSavingMeta(true)
    try {
      const payload = {
        titre: metaForm.titre.trim(),
        description: metaForm.description,
        chapitre: metaForm.chapitre,
        seuil_reussite: parseFloat(metaForm.seuil_reussite) || 70,
        actif: metaForm.actif,
        categories: metaForm.categories,
        grades: metaForm.grades,
        ...(metaForm.duree_max_minutes ? { duree_max_minutes: parseInt(metaForm.duree_max_minutes) } : { duree_max_minutes: null }),
        ...(metaForm.date_ouverture ? { date_ouverture: metaForm.date_ouverture } : { date_ouverture: null }),
        ...(metaForm.date_fermeture ? { date_fermeture: metaForm.date_fermeture } : { date_fermeture: null }),
      }
      const { data } = await api.patch(`/evaluations/quiz/${quiz.id}/`, payload)
      setQuiz(q => ({ ...q, ...data }))
      setShowMeta(false)
      showToast('Quiz mis à jour', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur mise à jour', 'error')
    } finally { setSavingMeta(false) }
  }

  const filteredGradesMeta = metaForm
    ? refGrades.filter(g =>
        metaForm.categories.length === 0 ||
        refCategories.find(c => metaForm.categories.includes(c.libelle) && c.id === g.categorie_id)
      )
    : []

  const openAdd = () => { setForm(EMPTY_Q); setShowAdd(true) }
  const closeAdd = () => { setShowAdd(false); setForm(EMPTY_Q) }

  const setOpt = (idx, val) => setForm(f => {
    const opts = [...f.options]; opts[idx] = val; return { ...f, options: opts }
  })
  const setEditOpt = (idx, val) => setEditForm(f => {
    const opts = [...f.options]; opts[idx] = val; return { ...f, options: opts }
  })

  const handleAddQuestion = async (e) => {
    e.preventDefault()
    if (!form.question.trim()) { showToast('La question est requise', 'error'); return }
    if (!form.points || parseFloat(form.points) <= 0) { showToast('Les points doivent être > 0', 'error'); return }
    if (form.type_question === 'QCM' && form.options.filter(o => o.trim()).length < 2) {
      showToast('Ajoutez au moins 2 options pour un QCM', 'error'); return
    }
    if (form.type_question !== 'OUVERTE' && !form.reponse_correcte.trim()) {
      showToast('La réponse correcte est requise', 'error'); return
    }
    setSaving(true)
    try {
      const payload = {
        question: form.question.trim(),
        type_question: form.type_question,
        reponse_correcte: form.type_question === 'OUVERTE' ? '' : form.reponse_correcte.trim(),
        options: form.type_question === 'QCM' ? form.options.filter(o => o.trim()) : [],
        points: parseFloat(form.points),
        ordre: form.ordre ? parseInt(form.ordre) : questions.length + 1,
      }
      const { data } = await api.post(`/evaluations/quiz/${quiz.id}/questions/`, payload)
      setQuestions(qs => [...qs, data])
      showToast('Question ajoutée', 'success')
      closeAdd()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur ajout question', 'error')
    } finally { setSaving(false) }
  }

  const startEdit = (q) => {
    setEditingId(q.id)
    setEditForm({
      question: q.question,
      type_question: q.type_question,
      reponse_correcte: q.reponse_correcte || '',
      options: q.options?.length >= 4 ? [...q.options] : [...(q.options || []), '', '', '', ''].slice(0, 4),
      points: String(q.points ?? 1),
      ordre: String(q.ordre ?? ''),
    })
  }

  const handleSaveEdit = async (qId) => {
    if (!editForm.question.trim()) { showToast('La question est requise', 'error'); return }
    if (!editForm.points || parseFloat(editForm.points) <= 0) { showToast('Les points doivent être > 0', 'error'); return }
    setSaving(true)
    try {
      const payload = {
        question: editForm.question.trim(),
        type_question: editForm.type_question,
        reponse_correcte: editForm.type_question === 'OUVERTE' ? '' : editForm.reponse_correcte.trim(),
        options: editForm.type_question === 'QCM' ? editForm.options.filter(o => o.trim()) : [],
        points: parseFloat(editForm.points),
        ...(editForm.ordre ? { ordre: parseInt(editForm.ordre) } : {}),
      }
      const { data } = await api.patch(`/evaluations/quiz/${quiz.id}/questions/${qId}/`, payload)
      setQuestions(qs => qs.map(q => q.id === qId ? data : q))
      setEditingId(null)
      showToast('Question mise à jour', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur modification', 'error')
    } finally { setSaving(false) }
  }

  const handleDeleteQuestion = async (qId) => {
    if (!window.confirm('Supprimer cette question ?')) return
    try {
      await api.delete(`/evaluations/quiz/${quiz.id}/questions/${qId}/`)
      setQuestions(qs => qs.filter(q => q.id !== qId))
      showToast('Question supprimée', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur suppression', 'error')
    }
  }

  const totalPoints = questions.reduce((s, q) => s + (parseFloat(q.points) || 0), 0)

  const renderQuestionForm = (f, setF, setOptFn, onSubmit, onCancel, isSaving, submitLabel) => (
    <form onSubmit={onSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
      <div>
        <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Énoncé *</label>
        <input className="form-control" value={f.question} onChange={e => setF(prev => ({ ...prev, question: e.target.value }))} placeholder="Rédigez la question…" />
      </div>
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <div style={{ flex: 2 }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Type</label>
          <select className="form-control" value={f.type_question} onChange={e => setF(prev => ({ ...prev, type_question: e.target.value, reponse_correcte: '', options: ['', '', '', ''] }))}>
            {Object.entries(TYPE_LABELS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Points *</label>
          <input className="form-control" type="number" min="0.5" step="0.5" value={f.points}
            onChange={e => setF(prev => ({ ...prev, points: e.target.value }))} />
        </div>
        <div style={{ flex: 1 }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Ordre</label>
          <input className="form-control" type="number" min="1" value={f.ordre}
            onChange={e => setF(prev => ({ ...prev, ordre: e.target.value }))} placeholder="Auto" />
        </div>
      </div>
      {f.type_question === 'QCM' && (
        <div>
          <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Options (min. 2)</label>
          {f.options.map((opt, i) => (
            <input key={i} className="form-control form-control-sm" style={{ marginBottom: '0.3rem' }}
              value={opt} onChange={e => setOptFn(i, e.target.value)} placeholder={`Option ${i + 1}`} />
          ))}
          <label style={{ fontSize: '0.82rem', fontWeight: 600, marginTop: '0.35rem' }}>Réponse correcte *</label>
          <select className="form-control form-control-sm" value={f.reponse_correcte}
            onChange={e => setF(prev => ({ ...prev, reponse_correcte: e.target.value }))}>
            <option value="">— sélectionner —</option>
            {f.options.filter(o => o.trim()).map((o, i) => <option key={i} value={o}>{o}</option>)}
          </select>
        </div>
      )}
      {f.type_question === 'VRAI_FAUX' && (
        <div>
          <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Réponse correcte *</label>
          <select className="form-control form-control-sm" value={f.reponse_correcte}
            onChange={e => setF(prev => ({ ...prev, reponse_correcte: e.target.value }))}>
            <option value="">— sélectionner —</option>
            <option value="vrai">Vrai</option>
            <option value="faux">Faux</option>
          </select>
        </div>
      )}
      {f.type_question === 'OUVERTE' && (
        <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', margin: 0 }}>Question ouverte — correction manuelle.</p>
      )}
      <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
        <button type="button" className="btn btn-outline-secondary btn-sm" onClick={onCancel}>Annuler</button>
        <button type="submit" className="btn btn-primary btn-sm" disabled={isSaving}>{isSaving ? 'Enregistrement…' : submitLabel}</button>
      </div>
    </form>
  )

  return (
    <div>
      {/* En-tête */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
        <Link to="/quiz" className="btn btn-outline-secondary btn-sm" style={{ marginTop: '0.2rem' }}>
          <i className="bi bi-arrow-left"></i>
        </Link>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontWeight: 700 }}>{quiz.titre}</h2>
          <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '0.2rem', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
            <span><i className="bi bi-book me-1"></i>{quiz.module_intitule}</span>
            <span><i className="bi bi-question-circle me-1"></i>{questions.length} question{questions.length !== 1 ? 's' : ''}</span>
            <span><i className="bi bi-trophy me-1"></i>{totalPoints} pt{totalPoints !== 1 ? 's' : ''} au total</span>
            {quiz.seuil_reussite != null && <span><i className="bi bi-bar-chart me-1"></i>Seuil {quiz.seuil_reussite}%</span>}
            {(quiz.categories || []).length > 0 && (
              <span><i className="bi bi-people me-1"></i>{quiz.categories.join(', ')}</span>
            )}
            {(quiz.grades || []).length > 0 && (
              <span><i className="bi bi-award me-1"></i>{quiz.grades.join(', ')}</span>
            )}
            <span style={{
              fontWeight: 700, padding: '1px 8px', borderRadius: '20px', fontSize: '0.75rem',
              background: quiz.actif ? '#e8eff5' : '#f5f5f5',
              color: quiz.actif ? '#125a99' : '#757575',
            }}>{quiz.actif ? 'Actif' : 'Inactif'}</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button className="btn btn-outline-secondary btn-sm" onClick={openMeta}>
            <i className="bi bi-gear me-1"></i>Modifier
          </button>
          <button className="btn btn-primary btn-sm" onClick={openAdd}>
            <i className="bi bi-plus-lg me-1"></i>Ajouter une question
          </button>
        </div>
      </div>

      {/* Modal édition métadonnées */}
      {showMeta && metaForm && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem' }}
          onClick={() => setShowMeta(false)}>
          <div className="card" style={{ maxWidth: 520, width: '100%', padding: '1.5rem', maxHeight: '90vh', overflowY: 'auto' }}
            onClick={e => e.stopPropagation()}>
            <h3 style={{ marginTop: 0, fontWeight: 700 }}>Modifier le quiz</h3>
            <form onSubmit={handleSaveMeta} style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
              <div>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Titre *</label>
                <input className="form-control" value={metaForm.titre}
                  onChange={e => setMetaForm(f => ({ ...f, titre: e.target.value }))} />
              </div>
              <div>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Description</label>
                <textarea className="form-control" rows={2} value={metaForm.description}
                  onChange={e => setMetaForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              {refCategories.length > 0 && (
                <div>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Groupes ciblés <span style={{ fontWeight: 400, color: '#888' }}>(vide = tous)</span></label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.3rem' }}>
                    {refCategories.map(c => {
                      const sel = metaForm.categories.includes(c.libelle)
                      return (
                        <span key={c.id}
                          onClick={() => setMetaForm(f => ({ ...f, categories: toggleArr(f.categories, c.libelle) }))}
                          style={{
                            cursor: 'pointer', padding: '4px 12px', borderRadius: '20px',
                            fontSize: '0.82rem', userSelect: 'none', fontWeight: sel ? 600 : 400,
                            background: sel ? '#1976d2' : '#f0f0f0',
                            color: sel ? '#fff' : '#333',
                            border: `1px solid ${sel ? '#1976d2' : '#ccc'}`,
                          }}
                        >{c.libelle}</span>
                      )
                    })}
                  </div>
                </div>
              )}
              {refGrades.length > 0 && (
                <div>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Grades ciblés <span style={{ fontWeight: 400, color: '#888' }}>(vide = tous)</span></label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.3rem' }}>
                    {filteredGradesMeta.length === 0
                      ? <span style={{ fontSize: '0.82rem', color: '#888' }}>Sélectionnez un groupe d'abord</span>
                      : filteredGradesMeta.map(g => {
                          const sel = metaForm.grades.includes(g.libelle)
                          return (
                            <span key={g.id}
                              onClick={() => setMetaForm(f => ({ ...f, grades: toggleArr(f.grades, g.libelle) }))}
                              style={{
                                cursor: 'pointer', padding: '4px 12px', borderRadius: '20px',
                                fontSize: '0.82rem', userSelect: 'none', fontWeight: sel ? 600 : 400,
                                background: sel ? '#0d47a1' : '#f0f0f0',
                                color: sel ? '#fff' : '#333',
                                border: `1px solid ${sel ? '#0d47a1' : '#ccc'}`,
                              }}
                            >{g.libelle}</span>
                          )
                        })
                    }
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Seuil de réussite (%)</label>
                  <input className="form-control" type="number" min="0" max="100" value={metaForm.seuil_reussite}
                    onChange={e => setMetaForm(f => ({ ...f, seuil_reussite: e.target.value }))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Durée max (min)</label>
                  <input className="form-control" type="number" min="1" value={metaForm.duree_max_minutes}
                    onChange={e => setMetaForm(f => ({ ...f, duree_max_minutes: e.target.value }))} placeholder="Illimitée" />
                </div>
              </div>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Date ouverture</label>
                  <input className="form-control" type="date" value={metaForm.date_ouverture}
                    onChange={e => setMetaForm(f => ({ ...f, date_ouverture: e.target.value }))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Date fermeture</label>
                  <input className="form-control" type="date" value={metaForm.date_fermeture}
                    onChange={e => setMetaForm(f => ({ ...f, date_fermeture: e.target.value }))} />
                </div>
              </div>
              <div>
                <label style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={metaForm.actif}
                    onChange={e => setMetaForm(f => ({ ...f, actif: e.target.checked }))} />
                  Quiz actif (visible par les étudiants)
                </label>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setShowMeta(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary btn-sm" disabled={savingMeta}>
                  {savingMeta ? 'Enregistrement…' : 'Enregistrer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Formulaire ajout */}
      {showAdd && (
        <div className="card" style={{ padding: '1rem', marginBottom: '1rem', borderLeft: '3px solid var(--primary)' }}>
          <h5 style={{ marginTop: 0, fontWeight: 700 }}>Nouvelle question</h5>
          {renderQuestionForm(form, setForm, setOpt, handleAddQuestion, closeAdd, saving, 'Ajouter')}
        </div>
      )}

      {/* Liste questions */}
      {questions.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-question-circle" style={{ fontSize: '2.5rem', color: 'var(--text-muted)' }}></i>
          <p>Aucune question. Ajoutez la première.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
          {questions.map((q, idx) => (
            <div key={q.id} className="card" style={{ padding: '0.9rem' }}>
              {editingId === q.id ? (
                <>
                  <h6 style={{ marginTop: 0, fontWeight: 700 }}>Modifier la question {idx + 1}</h6>
                  {renderQuestionForm(editForm, setEditForm, setEditOpt,
                    (e) => { e.preventDefault(); handleSaveEdit(q.id) },
                    () => setEditingId(null), saving, 'Enregistrer')}
                </>
              ) : (
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', fontWeight: 600 }}>Q{idx + 1}</span>
                      <span style={{ fontWeight: 600 }}>{q.question}</span>
                      <span style={{ fontSize: '0.72rem', padding: '1px 7px', borderRadius: '20px', background: '#e3f2fd', color: '#1565c0' }}>{TYPE_LABELS[q.type_question]}</span>
                    </div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                      <span style={{ fontWeight: 700, color: 'var(--primary)' }}>{q.points} pt{q.points > 1 ? 's' : ''}</span>
                      {q.type_question !== 'OUVERTE' && q.reponse_correcte && (
                        <span><i className="bi bi-check-circle-fill text-success me-1"></i>Réponse : {q.reponse_correcte}</span>
                      )}
                      {q.type_question === 'QCM' && q.options?.length > 0 && (
                        <span>{q.options.filter(o => o).length} options</span>
                      )}
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
                    <button className="btn btn-outline-secondary btn-sm" onClick={() => startEdit(q)}>
                      <i className="bi bi-pencil"></i>
                    </button>
                    <button className="btn btn-outline-danger btn-sm" onClick={() => handleDeleteQuestion(q.id)}>
                      <i className="bi bi-trash"></i>
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ─── Composant principal ─────────────────────────────────────
export default function QuizTake() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()
  const { user } = useAuth()
  const [quiz, setQuiz] = useState(null)
  const [loading, setLoading] = useState(true)

  const isÉtudiant = user?.role === 'AUDITEUR'

  const fetchQuiz = useCallback(async () => {
    setLoading(true)
    try {
      if (isÉtudiant) {
        const { data } = await api.get('/evaluations/mes-quiz/')
        const q = (data || []).find(x => String(x.id) === String(id))
        if (!q) { showToast('Quiz non disponible', 'error'); navigate('/quiz'); return }
        setQuiz(q)
      } else {
        const { data } = await api.get(`/evaluations/quiz/${id}/`)
        setQuiz(data)
      }
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur chargement quiz', 'error')
      navigate('/quiz')
    } finally { setLoading(false) }
    // navigate et showToast sont des références stables.
  }, [id, isÉtudiant, navigate, showToast])

  useEffect(() => { fetchQuiz() }, [fetchQuiz])

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!quiz) return null

  return isÉtudiant
    ? <QuizPassage quiz={quiz} />
    : <QuizEdit quiz={quiz} onRefresh={fetchQuiz} />
}
