import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'

const STATUT_LABELS = {
  PLANIFIEE: 'Planifiée', EN_COURS: 'En cours', TERMINEE: 'Terminée', ANNULEE: 'Annulée',
}
const STATUT_COLORS = {
  PLANIFIEE: { background: '#fff8e0', color: '#e69700' },
  EN_COURS:  { background: '#e3f2fd', color: '#0d47a1' },
  TERMINEE:  { background: '#e8eff5', color: '#125a99' },
  ANNULEE:   { background: '#ffebee', color: '#b71c1c' },
}

const EMPTY_EPREUVE = {
  type_epreuve: '', intitule: '', coefficient: '1', note_max: '20',
  date_epreuve: '', salle: '', anonyme: false, description: '',
}

function mentionAuto(note) {
  if (note === null || note === '' || isNaN(parseFloat(note))) return ''
  const n = parseFloat(note)
  if (n >= 16) return 'Très bien'
  if (n >= 14) return 'Bien'
  if (n >= 12) return 'Assez bien'
  if (n >= 10) return 'Passable'
  return 'Insuffisant'
}

export default function EvaluationAcademique() {
  const { formationId, moduleId } = useParams()
  const { showToast } = useToast()

  const [module, setModule] = useState(null)
  const [types, setTypes] = useState([])
  const [epreuves, setEpreuves] = useState([])
  const [moyennes, setMoyennes] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('epreuves') // 'epreuves' | 'moyennes'

  // Création épreuve
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState(EMPTY_EPREUVE)
  const [creating, setCreating] = useState(false)

  // Saisie notes
  const [selectedEpreuve, setSelectedEpreuve] = useState(null)
  const [rows, setRows] = useState([])
  const [draft, setDraft] = useState({})
  const [dirty, setDirty] = useState(false)
  const [savingNotes, setSavingNotes] = useState(false)
  const [search, setSearch] = useState('')
  const inputRefs = useRef({})

  const fetchData = useCallback(async () => {
    setLoading(true)
    try {
      const [modRes, typesRes, epreuvesRes] = await Promise.all([
        api.get(`/formations/${formationId}/modules/${moduleId}/`),
        api.get('/evaluations/types-epreuves/?actif=true'),
        api.get(`/evaluations/epreuves/?module_id=${moduleId}`),
      ])
      setModule(modRes.data)
      setTypes(typesRes.data)
      setEpreuves(epreuvesRes.data)
    } catch {
      showToast('Erreur lors du chargement', 'error')
    } finally {
      setLoading(false)
    }
  }, [formationId, moduleId, showToast])

  useEffect(() => { fetchData() }, [fetchData])

  const fetchMoyennes = useCallback(async () => {
    try {
      const { data } = await api.get(`/evaluations/modules/${moduleId}/moyennes/`)
      setMoyennes(data)
    } catch { showToast('Erreur chargement moyennes', 'error') }
  }, [moduleId, showToast])

  useEffect(() => { if (tab === 'moyennes') fetchMoyennes() }, [tab, fetchMoyennes])

  // ── Création épreuve ──
  const handleCreate = async (e) => {
    e.preventDefault()
    if (!form.type_epreuve) { showToast('Sélectionnez un type d\'épreuve', 'error'); return }
    if (!form.intitule.trim()) { showToast('L\'intitulé est requis', 'error'); return }
    setCreating(true)
    try {
      const payload = {
        type_epreuve: parseInt(form.type_epreuve),
        module: parseInt(moduleId),
        intitule: form.intitule.trim(),
        coefficient: parseFloat(form.coefficient) || 1,
        note_max: parseFloat(form.note_max) || 20,
        anonyme: form.anonyme,
        description: form.description,
        ...(form.date_epreuve ? { date_epreuve: form.date_epreuve } : {}),
        ...(form.salle ? { salle: form.salle } : {}),
      }
      await api.post('/evaluations/epreuves/', payload)
      showToast('Épreuve créée', 'success')
      setShowCreate(false)
      setForm(EMPTY_EPREUVE)
      fetchData()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la création', 'error')
    } finally { setCreating(false) }
  }

  const handleDeleteEpreuve = async (id) => {
    if (!window.confirm('Supprimer cette épreuve et toutes ses notes ?')) return
    try {
      await api.delete(`/evaluations/epreuves/${id}/`)
      showToast('Épreuve supprimée', 'success')
      if (selectedEpreuve?.id === id) setSelectedEpreuve(null)
      fetchData()
    } catch { showToast('Erreur lors de la suppression', 'error') }
  }

  const handleTogglePublier = async (ep) => {
    try {
      await api.patch(`/evaluations/epreuves/${ep.id}/`, { publier_notes: !ep.publier_notes })
      fetchData()
    } catch { showToast('Erreur', 'error') }
  }

  // ── Saisie notes ──
  const openNotes = async (ep) => {
    setSelectedEpreuve(ep)
    setSearch('')
    try {
      const { data } = await api.get(`/evaluations/epreuves/${ep.id}/notes/`)
      setRows(data)
      const init = {}
      data.forEach(r => {
        init[r.participant] = {
          note: r.note !== null && r.note !== undefined ? String(r.note) : '',
          observations: r.observations || '',
          absent: r.absent || false,
          exclu: r.exclu || false,
        }
      })
      setDraft(init)
      setDirty(false)
    } catch { showToast('Erreur chargement notes', 'error') }
  }

  const updateDraft = (pid, field, value) => {
    setDraft(d => ({ ...d, [pid]: { ...(d[pid] || {}), [field]: value } }))
    setDirty(true)
  }

  const handleSaveNotes = async () => {
    setSavingNotes(true)
    try {
      const notes = Object.entries(draft)
        .filter(([, v]) => v.note !== '' || v.observations || v.absent || v.exclu)
        .map(([pid, v]) => ({
          participant: parseInt(pid),
          note: v.note !== '' ? parseFloat(v.note) : null,
          observations: v.observations || '',
          absent: !!v.absent,
          exclu: !!v.exclu,
        }))
      const { data } = await api.post(
        `/evaluations/epreuves/${selectedEpreuve.id}/notes/bulk/`,
        { notes },
      )
      showToast(data.detail || 'Notes enregistrées', 'success')
      setDirty(false)
      openNotes(selectedEpreuve)
    } catch {
      showToast('Erreur lors de la sauvegarde', 'error')
    } finally { setSavingNotes(false) }
  }

  const handleRecalcMoyennes = async () => {
    try {
      const { data } = await api.post(`/evaluations/modules/${moduleId}/moyennes/recalculer/`)
      showToast(data.detail || 'Moyennes recalculées', 'success')
      fetchMoyennes()
    } catch { showToast('Erreur recalcul', 'error') }
  }

  const filteredRows = rows.filter(r =>
    !search ||
    r.nom.toLowerCase().includes(search.toLowerCase()) ||
    r.prenom.toLowerCase().includes(search.toLowerCase()) ||
    (r.matricule || '').toLowerCase().includes(search.toLowerCase())
  )

  if (loading) return <div className="loading"><div className="spinner"></div></div>

  return (
    <div>
      {/* En-tête */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.25rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700 }}>Évaluation académique — {module?.intitule}</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
            {epreuves.length} épreuve{epreuves.length !== 1 ? 's' : ''} · gestion des notes et moyennes
          </p>
        </div>
        <Link to={`/formations/${formationId}/modules/${moduleId}`} className="btn btn-sm btn-outline-secondary">
          <i className="bi bi-arrow-left me-1"></i>Retour au module
        </Link>
      </div>

      {/* Onglets */}
      <div style={{ display: 'flex', borderBottom: '2px solid var(--border)', marginBottom: '1.5rem' }}>
        {[
          { key: 'epreuves', label: 'Épreuves & Notes', icon: 'bi-pencil-square' },
          { key: 'moyennes', label: 'Moyennes du module', icon: 'bi-calculator' },
        ].map(t => (
          <button key={t.key} onClick={() => setTab(t.key)} style={{
            background: 'none', border: 'none', padding: '0.6rem 1.1rem', cursor: 'pointer',
            fontWeight: tab === t.key ? 700 : 500, fontSize: '0.9rem',
            color: tab === t.key ? 'var(--primary)' : 'var(--text-muted)',
            borderBottom: tab === t.key ? '2px solid var(--primary)' : '2px solid transparent',
            marginBottom: -2,
          }}>
            <i className={`bi ${t.icon} me-1`}></i>{t.label}
          </button>
        ))}
      </div>

      {/* ── Onglet ÉPREUVES ── */}
      {tab === 'epreuves' && (
        <div style={{ display: 'grid', gridTemplateColumns: selectedEpreuve ? '320px 1fr' : '1fr', gap: '1.25rem' }}>
          {/* Liste des épreuves */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>Épreuves</h3>
              <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
                <i className="bi bi-plus-lg me-1"></i>Nouvelle
              </button>
            </div>
            {epreuves.length === 0 ? (
              <div className="empty-state" style={{ padding: '1.5rem' }}>
                <i className="bi bi-clipboard-x" style={{ fontSize: '2rem', color: 'var(--text-muted)' }}></i>
                <p style={{ fontSize: '0.85rem' }}>Aucune épreuve</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {epreuves.map(ep => (
                  <div key={ep.id} className="card" style={{
                    padding: '0.75rem', cursor: 'pointer',
                    border: selectedEpreuve?.id === ep.id ? '2px solid var(--primary)' : '1px solid var(--border)',
                  }} onClick={() => openNotes(ep)}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontWeight: 600, fontSize: '0.88rem' }}>{ep.intitule}</div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 2 }}>
                          {ep.type_epreuve_libelle} · coeff {ep.coefficient} · {ep.nb_notes} note{ep.nb_notes !== 1 ? 's' : ''}
                        </div>
                      </div>
                      <span style={{ ...STATUT_COLORS[ep.statut], fontSize: '0.68rem', fontWeight: 700, padding: '2px 8px', borderRadius: '20px', whiteSpace: 'nowrap' }}>
                        {STATUT_LABELS[ep.statut]}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: '0.4rem', marginTop: '0.5rem' }}>
                      <button className="btn btn-sm btn-outline-secondary" style={{ fontSize: '0.7rem', padding: '1px 8px' }}
                        onClick={(e) => { e.stopPropagation(); handleTogglePublier(ep) }}>
                        <i className={`bi bi-${ep.publier_notes ? 'eye' : 'eye-slash'} me-1`}></i>
                        {ep.publier_notes ? 'Publiée' : 'Masquée'}
                      </button>
                      <button className="btn btn-sm btn-outline-danger" style={{ fontSize: '0.7rem', padding: '1px 8px' }}
                        onClick={(e) => { e.stopPropagation(); handleDeleteEpreuve(ep.id) }}>
                        <i className="bi bi-trash"></i>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Grille de saisie */}
          {selectedEpreuve && (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', flexWrap: 'wrap', gap: '0.5rem' }}>
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
                  Notes — {selectedEpreuve.intitule}
                </h3>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <input className="form-control form-control-sm" placeholder="Rechercher…"
                    value={search} onChange={e => setSearch(e.target.value)} style={{ maxWidth: 200 }} />
                  <button className="btn btn-primary btn-sm" onClick={handleSaveNotes} disabled={savingNotes || !dirty}>
                    {savingNotes ? 'Sauvegarde…' : <><i className="bi bi-floppy me-1"></i>Enregistrer</>}
                  </button>
                </div>
              </div>
              <div className="card" style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '2px solid var(--border)', background: 'var(--bg-secondary, #f9fafb)' }}>
                      <th style={{ padding: '0.6rem 0.75rem', textAlign: 'left', fontWeight: 700 }}>Étudiant</th>
                      <th style={{ padding: '0.6rem 0.5rem', textAlign: 'center', fontWeight: 700, minWidth: 90 }}>Note /20</th>
                      <th style={{ padding: '0.6rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Mention</th>
                      <th style={{ padding: '0.6rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Abs.</th>
                      <th style={{ padding: '0.6rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Exclu</th>
                      <th style={{ padding: '0.6rem 0.5rem', textAlign: 'left', fontWeight: 700 }}>Observations</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredRows.map((r, idx) => {
                      const d = draft[r.participant] || { note: '', observations: '', absent: false, exclu: false }
                      const noteNum = d.note !== '' ? parseFloat(d.note) : null
                      const isValid = d.note === '' || (noteNum !== null && !isNaN(noteNum) && noteNum >= 0 && noteNum <= 20)
                      return (
                        <tr key={r.participant} style={{ borderBottom: '1px solid var(--border)', background: idx % 2 === 0 ? 'transparent' : 'var(--bg-secondary, #fafafa)' }}>
                          <td style={{ padding: '0.5rem 0.75rem', whiteSpace: 'nowrap' }}>
                            <div style={{ fontWeight: 600 }}>{r.nom} {r.prenom}</div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>{r.matricule} · {r.grade}</div>
                          </td>
                          <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                            <input
                              ref={el => { inputRefs.current[r.participant] = el }}
                              type="number" step="0.25" value={d.note}
                              disabled={d.absent || d.exclu}
                              onChange={e => updateDraft(r.participant, 'note', e.target.value)}
                              onKeyDown={e => {
                                if (e.key === 'Enter') {
                                  const ids = filteredRows.map(x => x.participant)
                                  const next = ids[ids.indexOf(r.participant) + 1]
                                  if (next && inputRefs.current[next]) { e.preventDefault(); inputRefs.current[next].focus() }
                                }
                              }}
                              style={{
                                width: 64, textAlign: 'center', padding: '4px',
                                border: `1.5px solid ${isValid ? 'var(--border)' : '#e53935'}`,
                                borderRadius: 6, fontWeight: 600,
                                background: d.note !== '' && isValid ? (noteNum >= 10 ? '#e9f3f8' : '#fff8f8') : '',
                              }}
                              placeholder="—"
                            />
                          </td>
                          <td style={{ padding: '0.5rem', textAlign: 'center', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                            {mentionAuto(d.note) || '—'}
                          </td>
                          <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                            <input type="checkbox" checked={d.absent}
                              onChange={e => updateDraft(r.participant, 'absent', e.target.checked)} />
                          </td>
                          <td style={{ padding: '0.5rem', textAlign: 'center' }}>
                            <input type="checkbox" checked={d.exclu}
                              onChange={e => updateDraft(r.participant, 'exclu', e.target.checked)} />
                          </td>
                          <td style={{ padding: '0.5rem' }}>
                            <input type="text" value={d.observations}
                              onChange={e => updateDraft(r.participant, 'observations', e.target.value)}
                              style={{ width: '100%', padding: '4px 8px', border: '1.5px solid var(--border)', borderRadius: 6, fontSize: '0.8rem' }}
                              placeholder="…" />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Onglet MOYENNES ── */}
      {tab === 'moyennes' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.75rem' }}>
            <button className="btn btn-primary btn-sm" onClick={handleRecalcMoyennes}>
              <i className="bi bi-arrow-clockwise me-1"></i>Recalculer les moyennes
            </button>
          </div>
          {moyennes.length === 0 ? (
            <div className="empty-state">
              <i className="bi bi-calculator" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
              <p>Aucune moyenne calculée. Saisissez des notes puis recalculez.</p>
            </div>
          ) : (
            <div className="card" style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
                <thead>
                  <tr style={{ borderBottom: '2px solid var(--border)', background: 'var(--bg-secondary, #f9fafb)' }}>
                    <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 700 }}>Étudiant</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Nb épreuves</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Coeff. total</th>
                    <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Moyenne /20</th>
                  </tr>
                </thead>
                <tbody>
                  {moyennes.map((m, idx) => (
                    <tr key={m.id} style={{ borderBottom: '1px solid var(--border)', background: idx % 2 === 0 ? 'transparent' : 'var(--bg-secondary, #fafafa)' }}>
                      <td style={{ padding: '0.65rem 1rem' }}>{m.participant_nom}</td>
                      <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>{m.nb_epreuves}</td>
                      <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>{m.total_coefficients}</td>
                      <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                        <strong style={{ color: m.moyenne >= 10 ? '#125a99' : '#b71c1c' }}>
                          {m.moyenne !== null ? `${m.moyenne}/20` : '—'}
                        </strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Modal création épreuve */}
      {showCreate && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem' }}
          onClick={() => setShowCreate(false)}>
          <div className="card" style={{ maxWidth: 500, width: '100%', padding: '1.5rem' }} onClick={e => e.stopPropagation()}>
            <h3 style={{ marginTop: 0, fontWeight: 700 }}>Nouvelle épreuve</h3>
            <form onSubmit={handleCreate}>
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Type d'épreuve *</label>
                <select className="form-control" value={form.type_epreuve}
                  onChange={e => setForm(f => ({ ...f, type_epreuve: e.target.value }))}>
                  <option value="">— Sélectionner —</option>
                  {types.map(t => <option key={t.id} value={t.id}>{t.libelle}</option>)}
                </select>
              </div>
              <div style={{ marginBottom: '0.75rem' }}>
                <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Intitulé *</label>
                <input className="form-control" value={form.intitule}
                  onChange={e => setForm(f => ({ ...f, intitule: e.target.value }))} placeholder="Ex: Examen final" />
              </div>
              <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Coefficient</label>
                  <input className="form-control" type="number" step="0.5" value={form.coefficient}
                    onChange={e => setForm(f => ({ ...f, coefficient: e.target.value }))} />
                </div>
                <div style={{ flex: 1 }}>
                  <label style={{ fontSize: '0.82rem', fontWeight: 600 }}>Date</label>
                  <input className="form-control" type="date" value={form.date_epreuve}
                    onChange={e => setForm(f => ({ ...f, date_epreuve: e.target.value }))} />
                </div>
              </div>
              <div style={{ marginBottom: '1rem' }}>
                <label style={{ fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <input type="checkbox" checked={form.anonyme}
                    onChange={e => setForm(f => ({ ...f, anonyme: e.target.checked }))} />
                  Correction anonyme
                </label>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setShowCreate(false)}>Annuler</button>
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
