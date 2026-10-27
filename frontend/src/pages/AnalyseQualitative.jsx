import { useState, useEffect, useCallback } from 'react'
import { useParams, Link, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import {
  DonutChart, HistogramChart, HorizontalBarChart, TrendChart,
  NoteHistogram, NoteDonut, ChartEmpty, CHART_COLORS,
} from '../components/evaluation/EvaluationCharts'

const STATUT_COLORS = {
  BROUILLON: { background: '#fff8e0', color: '#e69700' },
  PUBLIE:    { background: '#e8eff5', color: '#125a99' },
  FERME:     { background: '#f5f5f5', color: '#616161' },
}
const STATUT_LABELS = { BROUILLON: 'Brouillon', PUBLIE: 'Publié', FERME: 'Fermé' }
const TYPE_LABELS   = { NOTE: 'Note (1 à 5)', CHOIX_UN: 'Choix unique', CHOIX_MUL: 'Choix multiple', TEXTE: 'Texte libre' }
const TYPE_ICONS    = { NOTE: 'bi-star', CHOIX_UN: 'bi-ui-radios', CHOIX_MUL: 'bi-ui-checks', TEXTE: 'bi-chat-left-text' }

// ── Composants utilitaires ───────────────────────────────────────────────────

function ScoreGauge({ score }) {
  if (score == null) return <span style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>—</span>
  const pct = (score / 5) * 100
  const color = score >= 4 ? '#0f4fbd' : score >= 3 ? '#4895d9' : score >= 2 ? '#fde135' : '#ef5350'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
      <div style={{ position: 'relative', width: 80, height: 80, flexShrink: 0 }}>
        <svg width="80" height="80" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="34" fill="none" stroke="#e0e0e0" strokeWidth="8" />
          <circle cx="40" cy="40" r="34" fill="none" stroke={color} strokeWidth="8"
            strokeDasharray={`${2 * Math.PI * 34 * pct / 100} ${2 * Math.PI * 34}`}
            strokeLinecap="round"
            transform="rotate(-90 40 40)"
            style={{ transition: 'stroke-dasharray .6s ease' }}
          />
        </svg>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
          <span style={{ fontWeight: 800, fontSize: '1.1rem', color, lineHeight: 1 }}>{score}</span>
          <span style={{ fontSize: '0.6rem', color: 'var(--text-muted)' }}>/5</span>
        </div>
      </div>
      <div>
        <div style={{ fontWeight: 700, fontSize: '1.5rem', color }}>{score}<span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', fontWeight: 400 }}>/5</span></div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Score global moyen</div>
      </div>
    </div>
  )
}

function StarMini({ value }) {
  return (
    <span>
      {[1, 2, 3, 4, 5].map(i => (
        <i key={i} className={`bi bi-star${i <= Math.round(value) ? '-fill' : ''}`}
          style={{ color: i <= Math.round(value) ? '#ffbf00' : '#ddd', fontSize: '0.75rem' }} />
      ))}
    </span>
  )
}

// ── Page principale ──────────────────────────────────────────────────────────

export default function AnalyseQualitative() {
  const { id } = useParams()
  const { showToast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const activeTab = searchParams.get('tab') || 'graphiques'
  const setTab = (t) => {
    const params = { tab: t }
    if (filterGroupe) params.groupe = filterGroupe
    setSearchParams(params, { replace: true })
  }

  const selectGroupe = (g) => {
    setFilterGroupe(g)
    const params = { tab: activeTab }
    if (g) params.groupe = g
    setSearchParams(params, { replace: true })
  }

  const downloadBlob = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleExport = async (fmt, { tous = false } = {}) => {
    if (!tous && !filterGroupe) {
      showToast('Sélectionnez un groupe à exporter', 'error')
      return
    }
    try {
      const params = new URLSearchParams()
      if (tous) params.set('tous', '1')
      else params.set('groupe', filterGroupe)
      const q = params.toString() ? `?${params}` : ''
      const { blob, fileName } = await api.getBlob(`/evaluations/questionnaires/${id}/export/${fmt}/${q}`)
      const ext = fmt === 'pdf' ? 'pdf' : 'xlsx'
      const safeGroupe = (filterGroupe || 'tous_groupes').replace(/\s+/g, '_')
      downloadBlob(blob, fileName || `evaluation_${id}_${safeGroupe}.${ext}`)
      showToast('Export téléchargé', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de l\'export', 'error')
    }
  }

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [filterCat, setFilterCat] = useState('')
  const [filterGroupe, setFilterGroupe] = useState(searchParams.get('groupe') || '')

  const fetchAnalyse = useCallback(async () => {
    setLoading(true)
    try {
      const { data: d } = await api.get(`/evaluations/questionnaires/${id}/analyse/`, {
        params: filterGroupe ? { groupe: filterGroupe } : {},
      })
      setData(d)
    } catch {
      showToast('Erreur lors du chargement de l\'analyse', 'error')
    } finally {
      setLoading(false)
    }
  }, [id, filterGroupe, showToast])

  useEffect(() => { fetchAnalyse() }, [fetchAnalyse])

  useEffect(() => {
    if (!data || filterGroupe) return
    const groupes = Object.keys(data.distribution_groupes || {})
    if (!groupes.length) return
    const avecReponses = groupes.find(g => (data.distribution_groupes[g] || 0) > 0)
    setFilterGroupe(avecReponses || groupes[0])
  }, [data, filterGroupe])

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (!data) return null

  const questionsNote    = data.questions.filter(q => q.type_question === 'NOTE')
  const questionsChoix   = data.questions.filter(q => ['CHOIX_UN', 'CHOIX_MUL'].includes(q.type_question))
  const questionsTexte   = data.questions.filter(q => q.type_question === 'TEXTE')
  const allVerbatims     = questionsTexte.flatMap(q => (q.verbatims || []).map(v => ({ ...v, question: q.intitule, qid: q.id })))
  const filteredVerbatims = filterCat ? allVerbatims.filter(v => v.categorie === filterCat) : allVerbatims
  const cats = [...new Set(allVerbatims.map(v => v.categorie).filter(Boolean))].sort()

  const totalGrades = Object.values(data.distribution_grades).reduce((a, b) => a + b, 0) || 1
  const totalGroupes = Object.values(data.distribution_groupes || {}).reduce((a, b) => a + b, 0) || 1
  const groupesDisponibles = [
    ...new Set([
      ...(data.groupes || []),
      ...Object.keys(data.distribution_groupes || {}),
    ]),
  ].sort()

  const comparaisonGroupes = (data.comparaison_groupes || []).map(g => ({
    label: g.groupe,
    value: g.nb_soumissions,
    color: g.groupe === filterGroupe ? '#e69700' : '#4f46e5',
  }))

  const scoresParGroupe = (data.comparaison_groupes || [])
    .filter(g => g.score_global != null)
    .map(g => ({
      label: g.groupe,
      value: g.score_global,
      color: g.groupe === filterGroupe ? '#0f4fbd' : '#4895d9',
    }))

  const moyennesChart = (data.moyennes_par_question || []).map((q, i) => ({
    label: `Q${i + 1}`,
    value: q.moyenne,
    color: q.moyenne >= 4 ? '#0f4fbd' : q.moyenne >= 3 ? '#4895d9' : q.moyenne >= 2 ? '#fde135' : '#ef5350',
  }))

  const gradesChart = Object.entries(data.distribution_grades || {}).map(([grade, nb], i) => ({
    label: grade,
    value: nb,
    color: CHART_COLORS[i % CHART_COLORS.length],
  }))

  const categoriesChart = Object.entries(data.distribution_categories || {}).map(([cat, nb], i) => ({
    label: `Cat. ${cat}`,
    value: nb,
    color: CHART_COLORS[(i + 2) % CHART_COLORS.length],
  }))

  const choixToDonut = (choixStats) => (choixStats || [])
    .filter(c => c.nb_reponses > 0)
    .map((c, i) => ({
      label: c.libelle,
      value: c.nb_reponses,
      color: CHART_COLORS[i % CHART_COLORS.length],
    }))

  return (
    <div>
      {/* ── En-tête ── */}
      <div style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ flex: 1, minWidth: 200 }}>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.4rem' }}>
              <span style={{ ...STATUT_COLORS[data.statut], fontSize: '0.72rem', fontWeight: 700, padding: '2px 10px', borderRadius: '20px' }}>
                {STATUT_LABELS[data.statut]}
              </span>
              <span style={{ fontSize: '0.72rem', background: '#e3f2fd', color: '#1565c0', padding: '2px 10px', borderRadius: '20px', fontWeight: 600 }}>
                <i className={`bi bi-${data.cible === 'COURS' ? 'book' : 'person-video3'} me-1`}></i>
                {data.cible === 'COURS' ? 'Évaluation du module' : "Évaluation de l'enseignant"}
              </span>
            </div>
            <h2 style={{ margin: 0, fontWeight: 700 }}>{(data.titres || []).join(' · ')}</h2>
            <p style={{ margin: '0.3rem 0 0', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
              Analyse qualitative · {data.nb_soumissions} soumission{data.nb_soumissions !== 1 ? 's' : ''}
              {filterGroupe && data.nb_soumissions_total != null && data.nb_soumissions_total !== data.nb_soumissions && (
                <span> sur {data.nb_soumissions_total} au total</span>
              )}
              {filterGroupe && (
                <span style={{ marginLeft: '0.5rem', fontSize: '0.78rem', background: '#fff8e0', color: '#e69700', padding: '2px 8px', borderRadius: '20px', fontWeight: 600 }}>
                  {filterGroupe}
                </span>
              )}
            </p>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
            {filterGroupe && (
              <>
                <button type="button" className="btn btn-sm btn-outline-danger" onClick={() => handleExport('pdf')} title={`Tirer PDF — ${filterGroupe}`}>
                  <i className="bi bi-file-earmark-pdf me-1"></i>PDF
                </button>
                <button type="button" className="btn btn-sm btn-outline-success" onClick={() => handleExport('excel')} title={`Tirer Excel — ${filterGroupe}`}>
                  <i className="bi bi-file-earmark-excel me-1"></i>Excel
                </button>
              </>
            )}
            {groupesDisponibles.length > 1 && (
              <button type="button" className="btn btn-sm btn-outline-success" onClick={() => handleExport('excel', { tous: true })} title="Tirer Excel — tous les groupes (une feuille par groupe)">
                <i className="bi bi-files me-1"></i>Excel tous
              </button>
            )}
            {groupesDisponibles.length > 0 && (
              <select
                className="form-select form-select-sm"
                style={{ width: 'auto', minWidth: 160 }}
                value={filterGroupe}
                onChange={e => selectGroupe(e.target.value)}
              >
                <option value="">Tous les groupes</option>
                {groupesDisponibles.map(g => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            )}
            <Link to={`/evaluations/${id}`} className="btn btn-sm btn-outline-secondary">
              <i className="bi bi-arrow-left me-1"></i>Retour au questionnaire
            </Link>
          </div>
        </div>
      </div>

      {/* Sélecteur groupes */}
      {groupesDisponibles.length > 0 && (
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
          {groupesDisponibles.map(g => {
            const nb = data.distribution_groupes?.[g] || 0
            const actif = filterGroupe === g
            return (
              <button
                key={g}
                type="button"
                onClick={() => selectGroupe(g)}
                style={{
                  padding: '6px 14px', borderRadius: '20px', cursor: 'pointer', fontSize: '0.85rem',
                  fontWeight: actif ? 700 : 500,
                  border: actif ? '2px solid #e69700' : '1px solid var(--border)',
                  background: actif ? '#fff8e0' : 'transparent',
                  color: actif ? '#e69700' : 'inherit',
                }}
              >
                {g} <span style={{ opacity: 0.75 }}>({nb})</span>
              </button>
            )
          })}
        </div>
      )}

      {/* ── Onglets ── */}
      <div style={{ display: 'flex', borderBottom: '2px solid var(--border)', marginBottom: '1.75rem' }}>
        {[
          { key: 'global',      label: 'Vue globale',    icon: 'bi-speedometer2' },
          { key: 'graphiques',  label: 'Graphiques',     icon: 'bi-graph-up' },
          { key: 'questions',   label: 'Par question',   icon: 'bi-bar-chart-line' },
          { key: 'verbatims',   label: `Verbatims (${allVerbatims.length})`, icon: 'bi-chat-left-quote' },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            border: 'none', background: 'none', padding: '0.6rem 1.25rem',
            fontWeight: activeTab === t.key ? 700 : 400,
            color: activeTab === t.key ? 'var(--primary)' : 'var(--text-muted)',
            borderBottom: activeTab === t.key ? '2px solid var(--primary)' : '2px solid transparent',
            marginBottom: '-2px', cursor: 'pointer', transition: 'all .15s', fontSize: '0.9rem',
          }}>
            <i className={`bi ${t.icon} me-1`}></i>{t.label}
          </button>
        ))}
      </div>

      {/* ══════════════════════════ VUE GLOBALE ══════════════════════════ */}
      {activeTab === 'global' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {/* KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem' }}>
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                <i className="bi bi-people me-1"></i>Soumissions
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: 'var(--primary)' }}>{data.nb_soumissions}</div>
            </div>
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                <i className="bi bi-question-circle me-1"></i>Questions
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: '#4f46e5' }}>{data.questions.length}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {questionsNote.length} notes · {questionsChoix.length} choix · {questionsTexte.length} textes
              </div>
            </div>
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                <i className="bi bi-trophy me-1"></i>Score global
              </div>
              <ScoreGauge score={data.score_global} />
            </div>
            <div className="card" style={{ padding: '1.25rem' }}>
              <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                <i className="bi bi-chat-left-text me-1"></i>Verbatims
              </div>
              <div style={{ fontSize: '2rem', fontWeight: 800, color: '#0f766e' }}>{allVerbatims.length}</div>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {questionsTexte.length} question{questionsTexte.length !== 1 ? 's' : ''} texte libre
              </div>
            </div>
          </div>

          {/* Distribution par catégorie + notes globale */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
            {/* Participation par grade */}
            {Object.keys(data.distribution_grades).length > 0 && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '1rem' }}>
                  <i className="bi bi-diagram-3 me-2" style={{ color: 'var(--primary)' }}></i>
                  Participation par grade
                </h6>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                  {Object.entries(data.distribution_grades).map(([grade, nb]) => (
                    <div key={grade} style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      <span style={{ width: 36, textAlign: 'center', padding: '2px 0', borderRadius: '6px', background: '#e8eaf6', color: '#283593', fontWeight: 700, fontSize: '0.82rem' }}>{grade}</span>
                      <div style={{ flex: 1, height: '8px', borderRadius: '4px', background: '#eee', overflow: 'hidden' }}>
                        <div style={{ width: `${(nb / totalGrades) * 100}%`, height: '100%', background: '#3f51b5', borderRadius: '4px', transition: 'width .4s' }} />
                      </div>
                      <span style={{ width: 24, textAlign: 'right', fontWeight: 700, fontSize: '0.85rem' }}>{nb}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Participation par catégorie */}
            {Object.keys(data.distribution_categories).length > 0 && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '1rem' }}>
                  <i className="bi bi-pie-chart me-2" style={{ color: 'var(--primary)' }}></i>
                  Participation par catégorie
                </h6>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                  {Object.entries(data.distribution_categories).map(([cat, nb]) => {
                    const pct = Math.round((nb / data.nb_soumissions) * 100)
                    return (
                      <div key={cat}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem', marginBottom: '3px' }}>
                          <span style={{ fontWeight: 600 }}>Catégorie {cat}</span>
                          <span>{nb} <span style={{ color: 'var(--text-muted)' }}>({pct}%)</span></span>
                        </div>
                        <div style={{ height: '8px', borderRadius: '4px', background: '#eee', overflow: 'hidden' }}>
                          <div style={{ width: `${pct}%`, height: '100%', background: '#6a1b9a', borderRadius: '4px', transition: 'width .4s' }} />
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* Participation par groupe */}
            {Object.keys(data.distribution_groupes || {}).length > 0 && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '1rem' }}>
                  <i className="bi bi-people me-2" style={{ color: '#e69700' }}></i>
                  Participation par groupe
                </h6>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                  {Object.entries(data.distribution_groupes).map(([groupe, nb]) => (
                    <button
                      key={groupe}
                      type="button"
                      onClick={() => selectGroupe(filterGroupe === groupe ? groupesDisponibles[0] || '' : groupe)}
                      style={{
                        display: 'flex', alignItems: 'center', gap: '0.6rem',
                        border: filterGroupe === groupe ? '2px solid #e69700' : '1px solid var(--border)',
                        borderRadius: '8px', padding: '0.35rem 0.5rem', background: filterGroupe === groupe ? '#fff8e0' : 'transparent',
                        cursor: 'pointer', width: '100%', textAlign: 'left',
                      }}
                    >
                      <span style={{ width: 90, fontWeight: 700, fontSize: '0.82rem', color: '#e69700' }}>{groupe}</span>
                      <div style={{ flex: 1, height: '8px', borderRadius: '4px', background: '#eee', overflow: 'hidden' }}>
                        <div style={{ width: `${(nb / totalGroupes) * 100}%`, height: '100%', background: '#e69700', borderRadius: '4px', transition: 'width .4s' }} />
                      </div>
                      <span style={{ width: 24, textAlign: 'right', fontWeight: 700, fontSize: '0.85rem' }}>{nb}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Classement questions NOTE */}
            {questionsNote.length > 0 && (
              <div className="card" style={{ padding: '1.25rem', gridColumn: Object.keys(data.distribution_grades).length === 0 ? 'span 2' : '' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '1rem' }}>
                  <i className="bi bi-star me-2" style={{ color: '#ffbf00' }}></i>
                  Classement des questions notées
                </h6>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.7rem' }}>
                  {[...questionsNote]
                    .filter(q => q.moyenne != null)
                    .sort((a, b) => b.moyenne - a.moyenne)
                    .map((q, idx) => (
                      <div key={q.id} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                        <span style={{
                          width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
                          background: idx === 0 ? '#fffae1' : '#f5f5f5',
                          color: idx === 0 ? '#f5b417' : '#616161',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontWeight: 700, fontSize: '0.75rem',
                        }}>{idx + 1}</span>
                        <span style={{ flex: 1, fontSize: '0.85rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={q.intitule}>
                          {q.intitule}
                        </span>
                        <StarMini value={q.moyenne} />
                        <span style={{ fontWeight: 700, fontSize: '0.9rem', color: q.moyenne >= 4 ? '#0f4fbd' : q.moyenne >= 3 ? '#4895d9' : '#ef5350', marginLeft: '0.25rem' }}>
                          {q.moyenne}
                        </span>
                      </div>
                    ))
                  }
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════ GRAPHIQUES ══════════════════════════ */}
      {activeTab === 'graphiques' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {!filterGroupe && (
            <div className="alert alert-info" style={{ fontSize: '0.85rem', margin: 0 }}>
              <i className="bi bi-info-circle me-1"></i>
              Sélectionnez un groupe pour l&apos;analyse détaillée, ou consultez la comparaison entre groupes ci-dessous.
            </div>
          )}

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
            {/* Comparaison nb réponses par groupe */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <h6 style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                <i className="bi bi-people me-2" style={{ color: '#e69700' }}></i>
                Nombre de réponses par groupe
              </h6>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                Comparaison de la participation entre groupes
              </p>
              {comparaisonGroupes.length > 0 ? (
                <HistogramChart data={comparaisonGroupes} color="#e69700" height={140} />
              ) : (
                <ChartEmpty />
              )}
            </div>

            {/* Score moyen par groupe */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <h6 style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                <i className="bi bi-trophy me-2" style={{ color: '#0f4fbd' }}></i>
                Score moyen par groupe
              </h6>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                Moyenne des questions notées (/5) — tendance par groupe
              </p>
              {scoresParGroupe.length > 0 ? (
                <HistogramChart data={scoresParGroupe} color="#0f4fbd" height={140} unit="" />
              ) : (
                <ChartEmpty label="Pas encore de notes" />
              )}
            </div>

            {/* Tendance soumissions groupe sélectionné */}
            {filterGroupe && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                  <i className="bi bi-graph-up-arrow me-2" style={{ color: '#1565c0' }}></i>
                  Tendance des réponses — {filterGroupe}
                </h6>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                  Soumissions par jour
                </p>
                <TrendChart data={data.tendance || []} color="#1565c0" />
              </div>
            )}

            {/* Disque distribution notes */}
            {filterGroupe && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                  <i className="bi bi-pie-chart me-2" style={{ color: '#ffbf00' }}></i>
                  Répartition des notes — {filterGroupe}
                </h6>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                  Distribution globale (1 à 5)
                </p>
                <NoteDonut distribution={data.distribution_notes || {}} />
              </div>
            )}

            {/* Histogramme moyennes par question */}
            {filterGroupe && moyennesChart.length > 0 && (
              <div className="card" style={{ padding: '1.25rem', gridColumn: '1 / -1' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '0.35rem' }}>
                  <i className="bi bi-bar-chart me-2" style={{ color: '#4f46e5' }}></i>
                  Moyenne par question — {filterGroupe}
                </h6>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
                  Tendance des satisfactions question par question (/5)
                </p>
                <HistogramChart data={moyennesChart} height={160} unit="" />
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '0.75rem' }}>
                  {(data.moyennes_par_question || []).map((q, i) => (
                    <span key={q.id} style={{ fontSize: '0.72rem', background: '#f5f5f5', padding: '2px 8px', borderRadius: '6px' }}>
                      <b>Q{i + 1}</b> {q.intitule.length > 40 ? `${q.intitule.slice(0, 40)}…` : q.intitule}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Grades / catégories du groupe */}
            {filterGroupe && gradesChart.length > 0 && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '1rem' }}>
                  <i className="bi bi-pie-chart me-2" style={{ color: '#283593' }}></i>
                  Réponses par grade
                </h6>
                <DonutChart data={gradesChart} />
              </div>
            )}

            {filterGroupe && categoriesChart.length > 0 && (
              <div className="card" style={{ padding: '1.25rem' }}>
                <h6 style={{ fontWeight: 700, marginBottom: '1rem' }}>
                  <i className="bi bi-pie-chart me-2" style={{ color: '#6a1b9a' }}></i>
                  Réponses par catégorie
                </h6>
                <DonutChart data={categoriesChart} />
              </div>
            )}
          </div>
        </div>
      )}

      {/* ══════════════════════════ PAR QUESTION ══════════════════════════ */}
      {activeTab === 'questions' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          {data.questions.length === 0 ? (
            <div className="empty-state">
              <i className="bi bi-question-circle" style={{ fontSize: '2.5rem', color: 'var(--text-muted)' }}></i>
              <p>Aucune question dans ce questionnaire</p>
            </div>
          ) : data.questions.map((q, idx) => (
            <div key={q.id} className="card" style={{ padding: '1.25rem' }}>
              {/* Entête question */}
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem', marginBottom: '1rem' }}>
                <div style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.85rem', flexShrink: 0 }}>
                  {idx + 1}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '0.25rem', flexWrap: 'wrap' }}>
                    <span style={{ fontSize: '0.72rem', background: '#f5f5f5', color: '#616161', padding: '1px 8px', borderRadius: '20px', fontWeight: 600 }}>
                      <i className={`bi ${TYPE_ICONS[q.type_question]} me-1`}></i>{TYPE_LABELS[q.type_question]}
                    </span>
                    {!q.obligatoire && <span style={{ fontSize: '0.72rem', background: '#fffae1', color: '#f5b417', padding: '1px 8px', borderRadius: '20px', fontWeight: 600 }}>Optionnel</span>}
                  </div>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: '0.95rem' }}>{q.intitule}</p>
                </div>
              </div>

              {/* Contenu selon le type */}
              {q.type_question === 'NOTE' && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.5rem' }}>Moyenne · {q.total_reponses} rép.</div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1rem' }}>
                      <div style={{ fontSize: '2.5rem', fontWeight: 800, color: q.moyenne >= 4 ? '#0f4fbd' : q.moyenne >= 3 ? '#4895d9' : q.moyenne != null ? '#ef5350' : 'var(--text-muted)', lineHeight: 1 }}>
                        {q.moyenne ?? '—'}
                      </div>
                      {q.moyenne && <StarMini value={q.moyenne} />}
                    </div>
                    <NoteHistogram distribution={q.distribution || {}} total={q.total_reponses || 0} />
                  </div>
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.75rem' }}>Répartition (disque)</div>
                    <NoteDonut distribution={q.distribution || {}} />
                  </div>
                </div>
              )}

              {(q.type_question === 'CHOIX_UN' || q.type_question === 'CHOIX_MUL') && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
                  <div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                      {q.total_reponses} réponse{q.total_reponses !== 1 ? 's' : ''} · histogramme
                    </div>
                    {(q.choix_stats || []).length === 0 ? (
                      <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Aucune réponse</p>
                    ) : (
                      <HorizontalBarChart
                        data={(q.choix_stats || []).sort((a, b) => b.nb_reponses - a.nb_reponses).map(c => ({
                          label: c.libelle,
                          value: c.nb_reponses,
                        }))}
                      />
                    )}
                  </div>
                  <div>
                    <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '0.75rem' }}>Répartition (disque)</div>
                    {(q.choix_stats || []).some(c => c.nb_reponses > 0) ? (
                      <DonutChart data={choixToDonut(q.choix_stats)} />
                    ) : (
                      <ChartEmpty label="Aucune réponse" />
                    )}
                  </div>
                </div>
              )}

              {q.type_question === 'TEXTE' && (
                <div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                    {q.nb_reponses_texte} réponse{q.nb_reponses_texte !== 1 ? 's' : ''} texte libre
                  </div>
                  {(q.verbatims || []).length === 0 ? (
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Aucun verbatim</p>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
                      {(q.verbatims || []).map((v, i) => (
                        <div key={i} style={{ background: '#f8f9fa', borderRadius: '8px', padding: '0.75rem 1rem', borderLeft: '3px solid var(--primary)' }}>
                          <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.5 }}>{v.texte}</p>
                          {v.grade && (
                            <span style={{ display: 'inline-block', marginTop: '0.4rem', fontSize: '0.72rem', background: '#e8eaf6', color: '#283593', padding: '1px 8px', borderRadius: '20px', fontWeight: 600 }}>
                              {v.grade}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* ══════════════════════════ VERBATIMS ══════════════════════════ */}
      {activeTab === 'verbatims' && (
        <div>
          {allVerbatims.length === 0 ? (
            <div className="empty-state">
              <i className="bi bi-chat-left-quote" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
              <p>Aucune réponse texte libre enregistrée</p>
            </div>
          ) : (
            <>
              {/* Filtre catégorie */}
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1.25rem', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>{filteredVerbatims.length} verbatim{filteredVerbatims.length !== 1 ? 's' : ''}</span>
                <select className="form-select form-select-sm" style={{ width: 'auto', minWidth: 160 }}
                  value={filterCat} onChange={e => setFilterCat(e.target.value)}>
                  <option value="">Toutes catégories</option>
                  {cats.map(c => <option key={c} value={c}>Catégorie {c}</option>)}
                </select>
              </div>

              {/* Groupement par question */}
              {questionsTexte.map(q => {
                const vbs = (q.verbatims || []).filter(v => !filterCat || v.categorie === filterCat)
                if (vbs.length === 0) return null
                return (
                  <div key={q.id} style={{ marginBottom: '1.5rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                      <span style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '0.8rem', flexShrink: 0 }}>
                        {q.ordre}
                      </span>
                      <h6 style={{ margin: 0, fontWeight: 700, fontSize: '0.95rem' }}>{q.intitule}</h6>
                      <span style={{ marginLeft: 'auto', fontSize: '0.78rem', color: 'var(--text-muted)', flexShrink: 0 }}>{vbs.length} réponse{vbs.length !== 1 ? 's' : ''}</span>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '0.75rem' }}>
                      {vbs.map((v, i) => (
                        <div key={i} className="card" style={{ padding: '1rem', borderLeft: '3px solid #0f766e', background: '#f0f5fd' }}>
                          <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.6, color: '#134e4a' }}>{v.texte}</p>
                          {v.grade && (
                            <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.4rem', alignItems: 'center' }}>
                              <span style={{ fontSize: '0.72rem', background: '#e8eaf6', color: '#283593', padding: '1px 8px', borderRadius: '20px', fontWeight: 600 }}>{v.grade}</span>
                              {v.categorie && <span style={{ fontSize: '0.72rem', background: '#f3e5f5', color: '#6a1b9a', padding: '1px 8px', borderRadius: '20px', fontWeight: 600 }}>Cat. {v.categorie}</span>}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )
              })}
            </>
          )}
        </div>
      )}
    </div>
  )
}
