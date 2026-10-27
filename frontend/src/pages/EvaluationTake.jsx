import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'

const SECTION_CONFIG = {
  COURS:     { label: 'Évaluation du module',      icon: 'bi-book',          bg: '#e3f2fd', color: '#1565c0' },
  FORMATEUR: { label: "Évaluation de l'enseignant",  icon: 'bi-person-video3', bg: '#f3e5f5', color: '#6a1b9a' },
}

function StarRating({ questionId, value, onChange }) {
  const [hovered, setHovered] = useState(null)
  return (
    <div style={{ display: 'flex', gap: '0.35rem' }}>
      {[1, 2, 3, 4, 5].map(n => (
        <button
          key={n}
          type="button"
          onMouseEnter={() => setHovered(n)}
          onMouseLeave={() => setHovered(null)}
          onClick={() => onChange(questionId, n)}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: '2px',
            color: n <= (hovered ?? value ?? 0) ? '#f5c10b' : '#d1d5db',
            fontSize: '1.6rem', lineHeight: 1,
          }}
        >
          <i className="bi bi-star-fill"></i>
        </button>
      ))}
      {value && (
        <span style={{ marginLeft: '0.4rem', fontSize: '0.85rem', color: 'var(--text-muted)', alignSelf: 'center' }}>
          {value}/5
        </span>
      )}
    </div>
  )
}

function QuestionBlock({ question, answer, onChange }) {
  const { type_question, choix } = question

  if (type_question === 'NOTE') {
    return (
      <StarRating
        questionId={question.id}
        value={answer ?? null}
        onChange={onChange}
      />
    )
  }

  if (type_question === 'CHOIX_UN') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        {(choix || []).map(c => (
          <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', fontSize: '0.9rem' }}>
            <input
              type="radio"
              name={`q_${question.id}`}
              value={c.id}
              checked={answer === c.id}
              onChange={() => onChange(question.id, c.id)}
            />
            {c.libelle}
          </label>
        ))}
      </div>
    )
  }

  if (type_question === 'CHOIX_MUL') {
    const selected = answer || []
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
        {(choix || []).map(c => (
          <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', cursor: 'pointer', fontSize: '0.9rem' }}>
            <input
              type="checkbox"
              checked={selected.includes(c.id)}
              onChange={() => {
                const next = selected.includes(c.id)
                  ? selected.filter(x => x !== c.id)
                  : [...selected, c.id]
                onChange(question.id, next)
              }}
            />
            {c.libelle}
          </label>
        ))}
      </div>
    )
  }

  return (
    <textarea
      className="form-control"
      rows={3}
      placeholder="Votre réponse…"
      value={answer || ''}
      onChange={e => onChange(question.id, e.target.value)}
    />
  )
}

export default function EvaluationTake() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { showToast } = useToast()

  const [questionnaire, setQuestionnaire] = useState(null)
  const [loading, setLoading] = useState(true)
  const [answers, setAnswers] = useState({})
  const [submitting, setSubmitting] = useState(false)

  const fetchQuestionnaire = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get('/evaluations/mes-questionnaires/')
      const q = (data || []).find(x => String(x.id) === String(id))
      if (!q) {
        showToast('Questionnaire non disponible', 'error')
        navigate('/evaluations')
        return
      }
      setQuestionnaire(q)
    } catch {
      showToast('Erreur chargement questionnaire', 'error')
      navigate('/evaluations')
    } finally {
      setLoading(false)
    }
    // navigate et showToast sont des références stables.
  }, [id, navigate, showToast])

  useEffect(() => { fetchQuestionnaire() }, [fetchQuestionnaire])

  const handleChange = (questionId, value) => {
    setAnswers(prev => ({ ...prev, [questionId]: value }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const questions = questionnaire?.questions || []
    const missing = questions.filter(q => q.obligatoire && (answers[q.id] === undefined || answers[q.id] === '' || (Array.isArray(answers[q.id]) && answers[q.id].length === 0)))
    if (missing.length > 0) {
      showToast(`${missing.length} question(s) obligatoire(s) sans réponse`, 'error')
      return
    }

    setSubmitting(true)
    try {
      const reponses = questions.map(q => {
        const val = answers[q.id]
        const entry = { question: q.id }
        if (q.type_question === 'NOTE') entry.note = val
        else if (q.type_question === 'CHOIX_UN') entry.choix_unique = val
        else if (q.type_question === 'CHOIX_MUL') entry.choix_multiples = val || []
        else entry.texte = val || ''
        return entry
      })
      await api.post('/evaluations/soumettre/', {
        questionnaire: questionnaire.id,
        reponses,
      })
      showToast('Évaluation soumise avec succès !', 'success')
      navigate('/evaluations')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la soumission', 'error')
    } finally {
      setSubmitting(false)
    }
  }

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!questionnaire) return null

  const questions = questionnaire.questions || []
  const sections = ['COURS', 'FORMATEUR']
  const totalObligs = questions.filter(q => q.obligatoire).length
  const answeredObligs = questions.filter(q => q.obligatoire && answers[q.id] !== undefined && answers[q.id] !== '' && !(Array.isArray(answers[q.id]) && answers[q.id].length === 0)).length
  const progress = totalObligs > 0 ? Math.round((answeredObligs / totalObligs) * 100) : 100

  return (
    <div style={{ maxWidth: '720px', margin: '0 auto' }}>
      {/* En-tête */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '1.5rem' }}>
        <Link to="/evaluations" className="btn btn-outline-secondary btn-sm" style={{ marginTop: '0.2rem' }}>
          <i className="bi bi-arrow-left"></i>
        </Link>
        <div style={{ flex: 1 }}>
          <h2 style={{ margin: 0, fontWeight: 700 }}>
            {(questionnaire.titres || []).join(' · ')}
          </h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
            {questions.length} question{questions.length !== 1 ? 's' : ''} — répondez à toutes les questions obligatoires
          </p>
        </div>
      </div>

      {/* Barre de progression */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
          <span>Progression</span>
          <span>{answeredObligs}/{totalObligs} obligatoires</span>
        </div>
        <div style={{ height: '6px', background: 'var(--border)', borderRadius: '3px', overflow: 'hidden' }}>
          <div style={{ height: '100%', width: `${progress}%`, background: progress === 100 ? '#125a99' : 'var(--primary)', borderRadius: '3px', transition: 'width .3s' }} />
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        {sections.map(section => {
          const sqs = questions.filter(q => (q.section || 'COURS') === section)
          if (sqs.length === 0) return null
          const sc = SECTION_CONFIG[section]
          return (
            <div key={section} style={{ marginBottom: '2rem' }}>
              {/* Titre de section */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem', padding: '0.6rem 1rem', borderRadius: '8px', background: sc.bg }}>
                <i className={`bi ${sc.icon}`} style={{ color: sc.color, fontSize: '1.1rem' }}></i>
                <span style={{ fontWeight: 700, color: sc.color, fontSize: '0.95rem' }}>{sc.label}</span>
                <span style={{ marginLeft: 'auto', fontSize: '0.78rem', color: sc.color, opacity: 0.8 }}>
                  {sqs.length} question{sqs.length !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Questions */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                {sqs.map((q, idx) => {
                  const isAnswered = answers[q.id] !== undefined && answers[q.id] !== '' && !(Array.isArray(answers[q.id]) && answers[q.id].length === 0)
                  return (
                    <div key={q.id} style={{
                      background: 'var(--card-bg, #fff)',
                      border: '1px solid',
                      borderColor: isAnswered ? '#94c0e7' : 'var(--border)',
                      borderRadius: '10px',
                      padding: '1rem 1.25rem',
                      transition: 'border-color .2s',
                    }}>
                      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.75rem' }}>
                        <span style={{ fontWeight: 700, color: 'var(--text-muted)', fontSize: '0.82rem', minWidth: '1.5rem' }}>{idx + 1}.</span>
                        <p style={{ margin: 0, fontWeight: 600, fontSize: '0.95rem', flex: 1 }}>
                          {q.intitule}
                          {q.obligatoire && <span style={{ color: 'red', marginLeft: '4px' }}>*</span>}
                        </p>
                        {isAnswered && (
                          <i className="bi bi-check-circle-fill" style={{ color: '#125a99', fontSize: '1rem', flexShrink: 0 }}></i>
                        )}
                      </div>
                      <QuestionBlock question={q} answer={answers[q.id]} onChange={handleChange} />
                    </div>
                  )
                })}
              </div>
            </div>
          )
        })}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1rem', paddingBottom: '2rem' }}>
          <Link to="/evaluations" className="btn btn-outline-secondary">Annuler</Link>
          <button type="submit" className="btn btn-primary" disabled={submitting}>
            {submitting
              ? <><span className="spinner-border spinner-border-sm me-1"></span>Envoi…</>
              : <><i className="bi bi-send me-1"></i>Soumettre l'évaluation</>}
          </button>
        </div>
      </form>
    </div>
  )
}
