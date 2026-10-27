import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { useReferentiels } from '../hooks/useReferentiels'

const STATUT_LABELS  = { BROUILLON: 'Brouillon', PUBLIE: 'Publié', FERME: 'Fermé' }
const STATUT_COLORS  = {
  BROUILLON: { background: '#fff8e0', color: '#e69700' },
  PUBLIE:    { background: '#e8eff5', color: '#125a99' },
  FERME:     { background: '#f5f5f5', color: '#616161' },
}
const SECTION_LABELS = { COURS: 'Module', FORMATEUR: 'Enseignant' }
const SECTION_COLORS = {
  COURS:     { bg: '#e3f2fd', color: '#1565c0', icon: 'bi-book' },
  FORMATEUR: { bg: '#f3e5f5', color: '#6a1b9a', icon: 'bi-person-video3' },
}
const TYPE_LABELS    = { NOTE: 'Note (1 à 5)', CHOIX_UN: 'Choix unique', CHOIX_MUL: 'Choix multiple', TEXTE: 'Texte libre' }
const TYPE_ICONS     = { NOTE: 'bi-star', CHOIX_UN: 'bi-ui-radios', CHOIX_MUL: 'bi-ui-checks', TEXTE: 'bi-chat-left-text' }

const EMPTY_QUESTION = { intitule: '', type_question: 'NOTE', section: 'COURS', ordre: 1, obligatoire: true, choix: [] }

function StarBar({ moyenne, total }) {
  const pct = moyenne ? (moyenne / 5) * 100 : 0
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
      <div style={{ position: 'relative', width: '120px', height: '12px', borderRadius: '6px', background: '#e0e0e0', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: 'linear-gradient(90deg,#f9c925,#ffb100)', borderRadius: '6px', transition: 'width .4s' }} />
      </div>
      <span style={{ fontWeight: 700, fontSize: '1.1rem', color: '#e69700' }}>{moyenne ?? '—'}<span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 400 }}>/5</span></span>
      <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>({total} réponse{total !== 1 ? 's' : ''})</span>
    </div>
  )
}

function ChoixBar({ libelle, nb, total }) {
  const pct = total > 0 ? Math.round((nb / total) * 100) : 0
  return (
    <div style={{ marginBottom: '0.5rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px', fontSize: '0.85rem' }}>
        <span>{libelle}</span>
        <span style={{ fontWeight: 600 }}>{nb} ({pct}%)</span>
      </div>
      <div style={{ height: '8px', borderRadius: '4px', background: '#e0e0e0', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: 'var(--primary)', borderRadius: '4px', transition: 'width .4s' }} />
      </div>
    </div>
  )
}

export default function EvaluationDetail() {
  const { id } = useParams()
  const { showToast } = useToast()
  const navigate = useNavigate()
  const [tab, setTab] = useState('questions') // 'questions' | 'resultats'

  const [questionnaire, setQuestionnaire] = useState(null)
  const [resultats, setResultats]         = useState(null)
  const [loading, setLoading]             = useState(true)
  const [loadingRes, setLoadingRes]       = useState(false)

  // Question form
  const [showQForm, setShowQForm]   = useState(false)
  const [editingQ, setEditingQ]     = useState(null) // null = nouveau
  const [qForm, setQForm]           = useState(EMPTY_QUESTION)
  const [savingQ, setSavingQ]       = useState(false)
  const [newChoixLabel, setNewChoixLabel] = useState('')

  const [refGroupes, setRefGroupes] = useState([])
  const [editGroupes, setEditGroupes] = useState(false)
  const [groupesDraft, setGroupesDraft] = useState([])
  const [savingGroupes, setSavingGroupes] = useState(false)
  const [filterGroupeRes, setFilterGroupeRes] = useState('')

  const fetchQuestionnaire = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get(`/evaluations/questionnaires/${id}/`)
      setQuestionnaire(data)
    } catch {
      showToast('Questionnaire introuvable', 'error')
      navigate('/evaluations')
    } finally {
      setLoading(false)
    }
  }, [id, showToast, navigate])

  const fetchResultats = useCallback(async () => {
    setLoadingRes(true)
    try {
      const { data } = await api.get(`/evaluations/questionnaires/${id}/resultats/`)
      setResultats(data)
      const groupes = Object.keys(data.par_groupe || {})
      if (groupes.length) {
        const avecReponses = groupes.find(g => (data.par_groupe[g]?.nb_soumissions || 0) > 0)
        setFilterGroupeRes(prev => (prev && groupes.includes(prev) ? prev : (avecReponses || groupes[0])))
      } else {
        setFilterGroupeRes('')
      }
    } catch {
      showToast('Erreur chargement résultats', 'error')
    } finally {
      setLoadingRes(false)
    }
  }, [id, showToast])

  useEffect(() => { fetchQuestionnaire() }, [fetchQuestionnaire])
  useEffect(() => { if (tab === 'resultats') fetchResultats() }, [tab, fetchResultats])

  const { data: referentielsData } = useReferentiels()

  useEffect(() => {
    if (referentielsData) setRefGroupes(referentielsData.groupes || [])
  }, [referentielsData])

  useEffect(() => {
    if (questionnaire && !editGroupes) {
      setGroupesDraft(questionnaire.groupes || [])
    }
  }, [questionnaire, editGroupes])

  // ── Statut ──────────────────────────────────────────────────────────────────
  const handleStatut = async (statut) => {
    try {
      await api.post(`/evaluations/questionnaires/${id}/statut/`, { statut })
      showToast(`Questionnaire ${STATUT_LABELS[statut].toLowerCase()}`, 'success')
      fetchQuestionnaire()
    } catch { showToast('Erreur changement de statut', 'error') }
  }

  // ── Questions ───────────────────────────────────────────────────────────────
  const openNewQuestion = () => {
    const nextOrdre = questionnaire?.questions?.length
      ? Math.max(...questionnaire.questions.map(q => q.ordre)) + 1
      : 1
    setEditingQ(null)
    setQForm({ ...EMPTY_QUESTION, ordre: nextOrdre })
    setNewChoixLabel('')
    setShowQForm(true)
  }

  const openEditQuestion = (q) => {
    setEditingQ(q)
    setQForm({
      intitule: q.intitule,
      type_question: q.type_question,
      section: q.section || 'COURS',
      ordre: q.ordre,
      obligatoire: q.obligatoire,
      choix: q.choix ? q.choix.map(c => ({ ...c })) : [],
    })
    setNewChoixLabel('')
    setShowQForm(true)
  }

  const addChoix = () => {
    if (!newChoixLabel.trim()) return
    const nextOrdre = qForm.choix.length + 1
    setQForm(f => ({ ...f, choix: [...f.choix, { libelle: newChoixLabel.trim(), ordre: nextOrdre }] }))
    setNewChoixLabel('')
  }

  const removeChoix = (idx) => {
    setQForm(f => ({ ...f, choix: f.choix.filter((_, i) => i !== idx) }))
  }

  const saveQuestion = async (e) => {
    e.preventDefault()
    if (!qForm.intitule.trim()) { showToast('L\'intitulé est requis', 'error'); return }
    if (['CHOIX_UN', 'CHOIX_MUL'].includes(qForm.type_question) && qForm.choix.length < 2) {
      showToast('Ajoutez au moins 2 choix', 'error'); return
    }
    setSavingQ(true)
    try {
      if (editingQ) {
        await api.patch(`/evaluations/questionnaires/${id}/questions/${editingQ.id}/`, qForm)
        showToast('Question mise à jour', 'success')
      } else {
        await api.post(`/evaluations/questionnaires/${id}/questions/`, qForm)
        showToast('Question ajoutée', 'success')
      }
      setShowQForm(false)
      fetchQuestionnaire()
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.response?.data?.intitule?.[0] || 'Erreur lors de la sauvegarde'
      showToast(msg, 'error')
    } finally { setSavingQ(false) }
  }

  const deleteQuestion = async (qid) => {
    if (!window.confirm('Supprimer cette question ?')) return
    try {
      await api.delete(`/evaluations/questionnaires/${id}/questions/${qid}/`)
      showToast('Question supprimée', 'success')
      fetchQuestionnaire()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur suppression', 'error')
    }
  }

  const toggleGroupeDraft = (groupe) => {
    setGroupesDraft(prev =>
      prev.includes(groupe) ? prev.filter(g => g !== groupe) : [...prev, groupe]
    )
  }

  const saveGroupes = async () => {
    setSavingGroupes(true)
    try {
      await api.patch(`/evaluations/questionnaires/${id}/`, { groupes: groupesDraft })
      showToast('Groupes mis à jour', 'success')
      setEditGroupes(false)
      fetchQuestionnaire()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la mise à jour des groupes', 'error')
    } finally {
      setSavingGroupes(false)
    }
  }

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleExportGroupe = async (fmt, groupe, { tous = false } = {}) => {
    const g = groupe || filterGroupeRes
    if (!tous && !g) {
      showToast('Sélectionnez un groupe à exporter', 'error')
      return
    }
    try {
      const params = new URLSearchParams()
      if (tous) params.set('tous', '1')
      else params.set('groupe', g)
      const q = params.toString() ? `?${params}` : ''
      const { blob, fileName } = await api.getBlob(`/evaluations/questionnaires/${id}/export/${fmt}/${q}`)
      const ext = fmt === 'pdf' ? 'pdf' : 'xlsx'
      downloadBlob(blob, fileName || `evaluation_${id}_${(g || 'tous_groupes').replace(/\s+/g, '_')}.${ext}`)
      showToast('Export téléchargé', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de l\'export', 'error')
    }
  }

  const isLocked = questionnaire?.statut === 'PUBLIE'

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!questionnaire) return null

  const groupesResultats = Object.keys(resultats?.par_groupe || {}).sort()
  const statsGroupe = filterGroupeRes ? resultats?.par_groupe?.[filterGroupeRes] : null
  const questionsResultats = statsGroupe?.questions || resultats?.questions || []
  const totalReponses = statsGroupe?.nb_soumissions ?? resultats?.nb_soumissions ?? 0

  return (
    <div>
      {/* En-tête */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ flex: 1, minWidth: '200px' }}>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.4rem' }}>
              <span style={{ ...STATUT_COLORS[questionnaire.statut], fontSize: '0.72rem', fontWeight: 700, padding: '2px 10px', borderRadius: '20px', letterSpacing: '0.04em' }}>
                {STATUT_LABELS[questionnaire.statut]}
              </span>
              <span style={{ fontSize: '0.72rem', background: '#e8eff5', color: '#125a99', padding: '2px 10px', borderRadius: '20px', fontWeight: 600 }}>
                <i className="bi bi-layers me-1"></i>2 sections : Module + Enseignant
              </span>
              {(questionnaire.categories || []).map(c => (
                <span key={c} style={{ fontSize: '0.72rem', background: '#f3e5f5', color: '#6a1b9a', padding: '2px 10px', borderRadius: '20px', fontWeight: 600 }}>{c}</span>
              ))}
              {(questionnaire.grades || []).map(g => (
                <span key={g} style={{ fontSize: '0.72rem', background: '#e8eaf6', color: '#283593', padding: '2px 10px', borderRadius: '20px', fontWeight: 600 }}>{g}</span>
              ))}
            </div>
            <h2 style={{ margin: 0, fontWeight: 700 }}>{(questionnaire.titres || []).join(' · ')}</h2>
            <div style={{ display: 'flex', gap: '1rem', marginTop: '0.35rem', fontSize: '0.82rem', color: 'var(--text-muted)', flexWrap: 'wrap' }}>
              {questionnaire.createur_nom && <span><i className="bi bi-person me-1"></i>{questionnaire.createur_nom}</span>}
              <span><i className="bi bi-question-circle me-1"></i>{questionnaire.questions?.length || 0} question{(questionnaire.questions?.length || 0) !== 1 ? 's' : ''}</span>
            </div>
          </div>

          {/* Actions statut */}
          <div style={{ display: 'flex', gap: '0.5rem', flexShrink: 0, flexWrap: 'wrap' }}>
            {questionnaire.statut === 'BROUILLON' && (
              <button className="btn btn-success btn-sm" onClick={() => handleStatut('PUBLIE')}>
                <i className="bi bi-send me-1"></i>Publier
              </button>
            )}
            {questionnaire.statut === 'PUBLIE' && (
              <button className="btn btn-secondary btn-sm" onClick={() => handleStatut('FERME')}>
                <i className="bi bi-lock me-1"></i>Fermer
              </button>
            )}
            {questionnaire.statut === 'FERME' && (
              <button className="btn btn-outline-secondary btn-sm" onClick={() => handleStatut('BROUILLON')}>
                <i className="bi bi-arrow-counterclockwise me-1"></i>Brouillon
              </button>
            )}
            {questionnaire.statut !== 'BROUILLON' && (
              <Link to={`/evaluations/${id}/analyse?tab=graphiques`} className="btn btn-outline-primary btn-sm">
                <i className="bi bi-graph-up-arrow me-1"></i>Analyse & graphiques
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Ciblage groupes — modifiable même une fois publié */}
      <div className="card" style={{ padding: '1rem 1.25rem', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', flexWrap: 'wrap', marginBottom: editGroupes ? '0.75rem' : 0 }}>
          <div>
            <h6 style={{ margin: 0, fontWeight: 700 }}>
              <i className="bi bi-people me-2" style={{ color: '#e69700' }}></i>
              Groupes ciblés
            </h6>
            <p style={{ margin: '0.25rem 0 0', fontSize: '0.82rem', color: 'var(--text-muted)' }}>
              Ajoutez un groupe pour ouvrir le questionnaire à de nouveaux étudiants. Les réponses existantes sont conservées.
            </p>
          </div>
          {!editGroupes ? (
            <button className="btn btn-sm btn-outline-primary" onClick={() => { setGroupesDraft(questionnaire.groupes || []); setEditGroupes(true) }}>
              <i className="bi bi-pencil me-1"></i>Modifier les groupes
            </button>
          ) : (
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-sm btn-secondary" onClick={() => setEditGroupes(false)} disabled={savingGroupes}>Annuler</button>
              <button type="button" className="btn btn-sm btn-primary" onClick={saveGroupes} disabled={savingGroupes}>
                {savingGroupes ? 'Enregistrement…' : 'Enregistrer'}
              </button>
            </div>
          )}
        </div>
        {editGroupes ? (
          <div style={{ maxHeight: '140px', overflowY: 'auto', display: 'flex', flexWrap: 'wrap', gap: '0.4rem', alignContent: 'flex-start', padding: '0.25rem' }}>
            {refGroupes.map(g => (
              <label key={g} style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', padding: '4px 10px', borderRadius: '20px', cursor: 'pointer', border: '1.5px solid', borderColor: groupesDraft.includes(g) ? '#e69700' : 'var(--border)', background: groupesDraft.includes(g) ? '#fff8e0' : 'transparent', color: groupesDraft.includes(g) ? '#e69700' : 'inherit', fontSize: '0.85rem', fontWeight: groupesDraft.includes(g) ? 700 : 400 }}>
                <input type="checkbox" style={{ display: 'none' }} checked={groupesDraft.includes(g)} onChange={() => toggleGroupeDraft(g)} />
                {g}
              </label>
            ))}
            {refGroupes.length === 0 && (
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Aucun groupe disponible</span>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginTop: '0.5rem' }}>
            {(questionnaire.groupes || []).length === 0 ? (
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>Tous les groupes (aucune restriction)</span>
            ) : (
              (questionnaire.groupes || []).map(g => (
                <span key={g} style={{ fontSize: '0.82rem', background: '#fff8e0', color: '#e69700', padding: '4px 10px', borderRadius: '20px', fontWeight: 600 }}>{g}</span>
              ))
            )}
          </div>
        )}
      </div>

      {/* Onglets */}
      <div style={{ display: 'flex', gap: '0', borderBottom: '2px solid var(--border)', marginBottom: '1.5rem' }}>
        {[
          { key: 'questions', label: 'Questions', icon: 'bi-list-check' },
          { key: 'resultats', label: `Résultats${questionnaire.statut !== 'BROUILLON' ? '' : ''}`, icon: 'bi-bar-chart-line' },
        ].map(t => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            style={{
              border: 'none', background: 'none', padding: '0.6rem 1.25rem',
              fontWeight: tab === t.key ? 700 : 400,
              color: tab === t.key ? 'var(--primary)' : 'var(--text-muted)',
              borderBottom: tab === t.key ? '2px solid var(--primary)' : '2px solid transparent',
              marginBottom: '-2px', cursor: 'pointer', transition: 'all .15s', fontSize: '0.9rem',
            }}
          >
            <i className={`bi ${t.icon} me-1`}></i>{t.label}
          </button>
        ))}
      </div>

      {/* ── Tab Questions ────────────────────────────────────────────────────── */}
      {tab === 'questions' && (
        <div>
          {isLocked && (
            <div className="alert alert-info" style={{ marginBottom: '1rem', fontSize: '0.85rem' }}>
              <i className="bi bi-info-circle me-1"></i>
              Ce questionnaire est publié — les questions ne peuvent plus être modifiées.
              Fermez-le d'abord pour pouvoir l'éditer.
            </div>
          )}

          {!isLocked && (
            <div style={{ marginBottom: '1rem' }}>
              <button className="btn btn-primary btn-sm" onClick={openNewQuestion}>
                <i className="bi bi-plus-lg me-1"></i>Ajouter une question
              </button>
            </div>
          )}

          {(!questionnaire.questions || questionnaire.questions.length === 0) ? (
            <div className="empty-state">
              <i className="bi bi-question-circle" style={{ fontSize: '2.5rem', color: 'var(--text-muted)' }}></i>
              <p>Aucune question — {isLocked ? 'repassez en brouillon pour éditer' : 'ajoutez votre première question'}</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {['COURS', 'FORMATEUR'].map(section => {
                const sqs = questionnaire.questions.filter(q => (q.section || 'COURS') === section)
                const sc = SECTION_COLORS[section]
                return (
                  <div key={section}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
                      <span style={{ background: sc.bg, color: sc.color, padding: '3px 12px', borderRadius: '20px', fontSize: '0.82rem', fontWeight: 700 }}>
                        <i className={`bi ${sc.icon} me-1`}></i>{SECTION_LABELS[section]}
                      </span>
                      <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{sqs.length} question{sqs.length !== 1 ? 's' : ''}</span>
                      {!isLocked && (
                        <button className="btn btn-sm btn-outline-primary" style={{ padding: '1px 8px', fontSize: '0.78rem', marginLeft: 'auto' }}
                          onClick={() => { const nextOrdre = sqs.length ? Math.max(...sqs.map(q => q.ordre)) + 1 : 1; setEditingQ(null); setQForm({ ...EMPTY_QUESTION, section, ordre: nextOrdre }); setNewChoixLabel(''); setShowQForm(true) }}>
                          <i className="bi bi-plus-lg me-1"></i>Ajouter
                        </button>
                      )}
                    </div>
                    {sqs.length === 0 ? (
                      <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', fontStyle: 'italic', paddingLeft: '0.5rem' }}>Aucune question dans cette section.</p>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                        {sqs.map((q, idx) => (
                          <div key={q.id} className="card" style={{ padding: '1rem', display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                            <div style={{ minWidth: '28px', height: '28px', borderRadius: '50%', background: sc.color, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.85rem', flexShrink: 0 }}>
                              {idx + 1}
                            </div>
                            <div style={{ flex: 1 }}>
                              <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.2rem', alignItems: 'center', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: '0.72rem', background: '#f5f5f5', color: '#616161', padding: '1px 7px', borderRadius: '20px', fontWeight: 600 }}>
                                  <i className={`bi ${TYPE_ICONS[q.type_question]} me-1`}></i>{TYPE_LABELS[q.type_question]}
                                </span>
                                {!q.obligatoire && <span style={{ fontSize: '0.72rem', background: '#fffae1', color: '#f5b417', padding: '1px 7px', borderRadius: '20px', fontWeight: 600 }}>Optionnel</span>}
                              </div>
                              <p style={{ margin: 0, fontWeight: 500 }}>{q.intitule}</p>
                              {q.choix && q.choix.length > 0 && (
                                <ul style={{ margin: '0.4rem 0 0 0', paddingLeft: '1.2rem', fontSize: '0.83rem', color: 'var(--text-muted)' }}>
                                  {q.choix.map(c => <li key={c.id}>{c.libelle}</li>)}
                                </ul>
                              )}
                            </div>
                            {!isLocked && (
                              <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
                                <button className="btn btn-sm btn-outline-secondary" onClick={() => openEditQuestion(q)} title="Modifier">
                                  <i className="bi bi-pencil"></i>
                                </button>
                                <button className="btn btn-sm btn-outline-danger" onClick={() => deleteQuestion(q.id)} title="Supprimer">
                                  <i className="bi bi-trash"></i>
                                </button>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* ── Tab Résultats ────────────────────────────────────────────────────── */}
      {tab === 'resultats' && (
        <div>
          {loadingRes ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : (
            <>
              {groupesResultats.length > 0 && (
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem', alignItems: 'center' }}>
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', flex: 1 }}>
                  {groupesResultats.map(g => {
                    const nb = resultats.par_groupe[g]?.nb_soumissions || 0
                    const actif = filterGroupeRes === g
                    return (
                      <button
                        key={g}
                        type="button"
                        onClick={() => setFilterGroupeRes(g)}
                        style={{
                          padding: '6px 14px', borderRadius: '20px', cursor: 'pointer', fontSize: '0.85rem', fontWeight: actif ? 700 : 500,
                          border: actif ? '2px solid #e69700' : '1px solid var(--border)',
                          background: actif ? '#fff8e0' : 'transparent',
                          color: actif ? '#e69700' : 'inherit',
                        }}
                      >
                        {g}
                        <span style={{ marginLeft: '0.4rem', opacity: 0.75 }}>({nb})</span>
                      </button>
                    )
                  })}
                  </div>
                  {filterGroupeRes && (
                    <div style={{ display: 'flex', gap: '0.4rem', flexShrink: 0 }}>
                      <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => handleExportGroupe('pdf')} title={`Tirer PDF — ${filterGroupeRes}`}>
                        <i className="bi bi-file-earmark-pdf"></i>
                      </button>
                      <button type="button" className="btn btn-sm btn-outline-success" onClick={() => handleExportGroupe('excel')} title={`Tirer Excel — ${filterGroupeRes}`}>
                        <i className="bi bi-file-earmark-excel"></i>
                      </button>
                      {groupesResultats.length > 1 && (
                        <button type="button" className="btn btn-sm btn-outline-success" onClick={() => handleExportGroupe('excel', null, { tous: true })} title="Tirer Excel — tous les groupes">
                          <i className="bi bi-files"></i>
                        </button>
                      )}
                    </div>
                  )}
                </div>
              )}

              <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                <div className="card" style={{ padding: '1rem 1.5rem', flex: '0 0 auto' }}>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--primary)', lineHeight: 1 }}>{totalReponses}</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    soumission{totalReponses !== 1 ? 's' : ''}
                    {filterGroupeRes && <span> · {filterGroupeRes}</span>}
                  </div>
                </div>
                {filterGroupeRes && resultats?.nb_soumissions_total > totalReponses && (
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>
                    {resultats.nb_soumissions_total} soumissions au total (tous groupes)
                  </span>
                )}
              </div>

              {!questionsResultats.length ? (
                <div className="empty-state">
                  <i className="bi bi-inbox" style={{ fontSize: '2.5rem', color: 'var(--text-muted)' }}></i>
                  <p>{filterGroupeRes ? `Aucune réponse pour ${filterGroupeRes}` : 'Aucune réponse encore'}</p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {questionsResultats.map((q, idx) => (
                    <div key={q.id} className="card" style={{ padding: '1.25rem' }}>
                      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '0.5rem', alignItems: 'baseline' }}>
                        <span style={{ fontWeight: 700, color: 'var(--primary)', fontSize: '0.9rem' }}>Q{idx + 1}</span>
                        <span style={{ fontSize: '0.72rem', background: '#f5f5f5', color: '#616161', padding: '1px 7px', borderRadius: '20px', fontWeight: 600 }}>
                          {TYPE_LABELS[q.type_question]}
                        </span>
                      </div>
                      <p style={{ margin: '0 0 0.75rem', fontWeight: 600 }}>{q.intitule}</p>

                      {q.type_question === 'NOTE' && (
                        <StarBar moyenne={q.moyenne} total={q.total_reponses} />
                      )}

                      {(q.type_question === 'CHOIX_UN' || q.type_question === 'CHOIX_MUL') && q.choix_stats && (
                        <div>
                          {q.choix_stats.map(c => (
                            <ChoixBar
                              key={c.id}
                              libelle={c.libelle}
                              nb={c.nb_reponses}
                              total={q.choix_stats.reduce((s, x) => s + x.nb_reponses, 0)}
                            />
                          ))}
                        </div>
                      )}

                      {q.type_question === 'TEXTE' && (
                        <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
                          <i className="bi bi-chat-left-text me-1"></i>{q.nb_reponses_texte} réponse{q.nb_reponses_texte !== 1 ? 's' : ''} texte
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* ── Modal question ──────────────────────────────────────────────────── */}
      {showQForm && (
        <div className="modal-overlay" onClick={() => setShowQForm(false)}>
          <div className="modal-content" style={{ maxWidth: '540px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h4 className="modal-title">{editingQ ? 'Modifier la question' : 'Nouvelle question'}</h4>
              <button className="modal-close" onClick={() => setShowQForm(false)}><i className="bi bi-x-lg"></i></button>
            </div>
            <form onSubmit={saveQuestion}>
              <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                <div>
                  <label className="form-label">Intitulé <span style={{ color: 'red' }}>*</span></label>
                  <textarea
                    className="form-control"
                    rows={2}
                    required
                    value={qForm.intitule}
                    onChange={e => setQForm(f => ({ ...f, intitule: e.target.value }))}
                    placeholder="Ex: Comment évaluez-vous la clarté du module ?"
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label className="form-label">Section <span style={{ color: 'red' }}>*</span></label>
                    <select className="form-select" value={qForm.section} onChange={e => setQForm(f => ({ ...f, section: e.target.value }))}>
                      <option value="COURS">Module</option>
                      <option value="FORMATEUR">Enseignant</option>
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Type</label>
                    <select className="form-select" value={qForm.type_question} onChange={e => setQForm(f => ({ ...f, type_question: e.target.value, choix: [] }))}>
                      <option value="NOTE">Note (1 à 5)</option>
                      <option value="CHOIX_UN">Choix unique</option>
                      <option value="CHOIX_MUL">Choix multiple</option>
                      <option value="TEXTE">Texte libre</option>
                    </select>
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label className="form-label">Ordre</label>
                    <input type="number" min={1} className="form-control" value={qForm.ordre} onChange={e => setQForm(f => ({ ...f, ordre: parseInt(e.target.value) || 1 }))} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.875rem', marginBottom: '0.35rem' }}>
                      <input type="checkbox" checked={qForm.obligatoire} onChange={e => setQForm(f => ({ ...f, obligatoire: e.target.checked }))} />
                      Obligatoire
                    </label>
                  </div>
                </div>

                {['CHOIX_UN', 'CHOIX_MUL'].includes(qForm.type_question) && (
                  <div>
                    <label className="form-label">Options de réponse</label>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', marginBottom: '0.5rem' }}>
                      {qForm.choix.map((c, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', background: '#f5f5f5', borderRadius: '6px', padding: '0.35rem 0.6rem' }}>
                          <span style={{ flex: 1, fontSize: '0.875rem' }}>{c.libelle}</span>
                          <button type="button" className="btn btn-sm btn-outline-danger" style={{ padding: '1px 6px' }} onClick={() => removeChoix(i)}>
                            <i className="bi bi-x"></i>
                          </button>
                        </div>
                      ))}
                    </div>
                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                      <input
                        className="form-control form-control-sm"
                        placeholder="Libellé du choix…"
                        value={newChoixLabel}
                        onChange={e => setNewChoixLabel(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addChoix() } }}
                      />
                      <button type="button" className="btn btn-sm btn-outline-primary" onClick={addChoix}>
                        <i className="bi bi-plus"></i>
                      </button>
                    </div>
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowQForm(false)}>Annuler</button>
                <button type="submit" className="btn btn-primary" disabled={savingQ}>
                  {savingQ ? <><span className="spinner-border spinner-border-sm me-1"></span>Enregistrement…</> : (editingQ ? 'Mettre à jour' : 'Ajouter')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
