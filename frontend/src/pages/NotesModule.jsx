import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'
import { useToast } from '../context/ToastContext'

const MENTION_LABELS = {
  TRES_BIEN:   'Très bien',
  BIEN:        'Bien',
  ASSEZ_BIEN:  'Assez bien',
  PASSABLE:    'Passable',
  INSUFFISANT: 'Insuffisant',
  '':          '—',
}
const MENTION_COLORS = {
  TRES_BIEN:   { background: '#e8eff5', color: '#093f70' },
  BIEN:        { background: '#e3f2fd', color: '#0d47a1' },
  ASSEZ_BIEN:  { background: '#e8eaf6', color: '#283593' },
  PASSABLE:    { background: '#fffae1', color: '#f5b417' },
  INSUFFISANT: { background: '#ffebee', color: '#b71c1c' },
  '':          { background: '#f5f5f5', color: '#9e9e9e' },
}

function normalizeTo20(note, noteMax = 20) {
  const n = parseFloat(note)
  const max = parseFloat(noteMax) || 20
  if (isNaN(n) || max <= 0) return null
  return (n * 20) / max
}

function mentionAuto(note, noteMax = 20) {
  const normalized = normalizeTo20(note, noteMax)
  if (normalized === null) return ''
  if (normalized >= 16) return 'TRES_BIEN'
  if (normalized >= 14) return 'BIEN'
  if (normalized >= 12) return 'ASSEZ_BIEN'
  if (normalized >= 10) return 'PASSABLE'
  return 'INSUFFISANT'
}

function mentionFromNotes(notesEntries, colonnesById) {
  const normalized = notesEntries
    .map(([colId, val]) => {
      if (val === '' || val === null || val === undefined) return null
      const col = colonnesById[colId]
      return normalizeTo20(val, col?.note_max ?? 20)
    })
    .filter(v => v !== null)
  if (!normalized.length) return ''
  const avg = normalized.reduce((a, b) => a + b, 0) / normalized.length
  return mentionAuto(avg, 20)
}

function MentionBadge({ mention }) {
  const style = MENTION_COLORS[mention] || MENTION_COLORS['']
  return (
    <span style={{ ...style, fontSize: '0.72rem', fontWeight: 700, padding: '2px 9px', borderRadius: '20px', whiteSpace: 'nowrap' }}>
      {MENTION_LABELS[mention] || '—'}
    </span>
  )
}

function emptyDraftRow(colonnes) {
  const notes = {}
  colonnes.forEach(c => { notes[c.id] = '' })
  return { notes, observations: '' }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function NotesModule() {
  const { formationId, moduleId } = useParams()
  const { showToast } = useToast()

  const [module, setModule] = useState(null)
  const [colonnes, setColonnes] = useState([])
  const [rows, setRows] = useState([])
  const [criteres, setCriteres] = useState({ seuil_admission: 12, taux_presence_min: 80 })
  const [draft, setDraft] = useState({})
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [search, setSearch] = useState('')
  const [dirty, setDirty] = useState(false)
  const [showAddColonne, setShowAddColonne] = useState(false)
  const [newColonneLibelle, setNewColonneLibelle] = useState('')
  const [addingColonne, setAddingColonne] = useState(false)
  const [printing, setPrinting] = useState(null)
  const inputRefs = useRef({})

  const colonnesById = Object.fromEntries(colonnes.map(c => [c.id, c]))

  const fetchData = useCallback(async (signal) => {
    setLoading(true)
    try {
      const opts = signal ? { signal } : {}
      const [modRes, notesRes] = await Promise.all([
        api.get(`/formations/${formationId}/modules/${moduleId}/`, opts),
        api.get(`/formations/${formationId}/modules/${moduleId}/notes/`, opts),
      ])
      setModule(modRes.data)
      const cols = notesRes.data.colonnes || []
      const dataRows = notesRes.data.rows || []
      setColonnes(cols)
      setRows(dataRows)
      if (notesRes.data.criteres) setCriteres(notesRes.data.criteres)
      const init = {}
      dataRows.forEach(r => {
        const notes = {}
        cols.forEach(c => {
          const cell = r.notes?.[String(c.id)]
          notes[c.id] = cell?.note !== null && cell?.note !== undefined ? String(cell.note) : ''
        })
        init[r.participant_id] = {
          notes,
          observations: r.observations || '',
        }
      })
      setDraft(init)
      setDirty(false)
    } catch (err) {
      if (err?.code !== 'ERR_CANCELED' && err?.name !== 'CanceledError') {
        showToast('Erreur lors du chargement', 'error')
      }
    } finally {
      setLoading(false)
    }
  }, [formationId, moduleId, showToast])

  useEffect(() => {
    const ac = new AbortController()
    fetchData(ac.signal)
    return () => ac.abort()
  }, [fetchData])

  const updateDraftNote = (pid, colonneId, value) => {
    setDraft(d => {
      const prev = d[pid] || emptyDraftRow(colonnes)
      return {
        ...d,
        [pid]: {
          ...prev,
          notes: { ...prev.notes, [colonneId]: value },
        },
      }
    })
    setDirty(true)
  }

  const updateDraftObservations = (pid, value) => {
    setDraft(d => {
      const prev = d[pid] || emptyDraftRow(colonnes)
      return { ...d, [pid]: { ...prev, observations: value } }
    })
    setDirty(true)
  }

  const handleAddColonne = async (e) => {
    e.preventDefault()
    const libelle = newColonneLibelle.trim()
    if (!libelle) {
      showToast('Saisissez un intitulé pour la colonne', 'error')
      return
    }
    setAddingColonne(true)
    try {
      const { data } = await api.post(
        `/formations/${formationId}/modules/${moduleId}/notes/colonnes/`,
        { libelle, note_max: 20 },
      )
      setColonnes(prev => [...prev, data])
      setDraft(d => {
        const next = { ...d }
        Object.keys(next).forEach(pid => {
          next[pid] = {
            ...next[pid],
            notes: { ...next[pid].notes, [data.id]: '' },
          }
        })
        rows.forEach(r => {
          if (!next[r.participant_id]) {
            next[r.participant_id] = emptyDraftRow([...colonnes, data])
          }
        })
        return next
      })
      setNewColonneLibelle('')
      setShowAddColonne(false)
      showToast('Colonne ajoutée', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de l\'ajout', 'error')
    } finally {
      setAddingColonne(false)
    }
  }

  const handleDeleteColonne = async (colonne) => {
    if (colonnes.length <= 1) return
    if (!window.confirm(`Supprimer la colonne « ${colonne.libelle} » et toutes ses notes ?`)) return
    try {
      await api.delete(
        `/formations/${formationId}/modules/${moduleId}/notes/colonnes/${colonne.id}/`,
      )
      showToast('Colonne supprimée', 'success')
      fetchData()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la suppression', 'error')
    }
  }

  const handleSaveAll = async () => {
    setSaving(true)
    try {
      const notePayload = []
      const synthesePayload = []
      const syntheseSeen = new Set()

      Object.entries(draft).forEach(([pid, v]) => {
        colonnes.forEach(c => {
          const val = v.notes?.[c.id]
          if (val !== '' && val !== undefined) {
            notePayload.push({
              participant_id: parseInt(pid),
              colonne_id: c.id,
              note: parseFloat(val),
            })
          }
        })
        const hasObs = (v.observations || '').trim()
        const hasNotes = Object.values(v.notes || {}).some(val => val !== '')
        const mention = mentionFromNotes(
          Object.entries(v.notes || {}),
          colonnesById,
        )
        if (hasObs || mention || hasNotes) {
          synthesePayload.push({
            participant_id: parseInt(pid),
            mention,
            observations: v.observations || '',
          })
          syntheseSeen.add(pid)
        }
      })

      const { data } = await api.post(
        `/formations/${formationId}/modules/${moduleId}/notes/bulk/`,
        { notes: notePayload, syntheses: synthesePayload },
      )
      if (data.errors && data.errors.length > 0) {
        showToast(`${data.saved} enregistrement(s), ${data.errors.length} erreur(s)`, 'warning')
      } else {
        showToast(`${data.saved} enregistrement(s) sauvegardé(s)`, 'success')
      }
      setDirty(false)
      fetchData()
    } catch {
      showToast('Erreur lors de la sauvegarde', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handlePrintFiche = async (participant = null) => {
    if (dirty && !window.confirm(
      'Des notes ne sont pas encore enregistrées : la fiche imprimée ne les contiendra pas. Continuer ?'
    )) return

    const key = participant ? `p-${participant.participant_id}` : 'module'
    const path = participant
      ? `/formations/${formationId}/modules/${moduleId}/notes/fiche/${participant.participant_id}/pdf/`
      : `/formations/${formationId}/modules/${moduleId}/notes/fiche/pdf/`
    const fallback = participant
      ? `fiche_notes_${participant.nom}_${participant.prenom}.pdf`.replace(/\s+/g, '_')
      : `fiche_notes_module_${moduleId}.pdf`

    setPrinting(key)
    try {
      const { blob, fileName } = await api.getBlob(path)
      downloadBlob(blob, fileName || fallback)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la génération de la fiche', 'error')
    } finally {
      setPrinting(null)
    }
  }

  const filtered = rows.filter(n =>
    !search ||
    n.nom.toLowerCase().includes(search.toLowerCase()) ||
    n.prenom.toLowerCase().includes(search.toLowerCase()) ||
    n.matricule.toLowerCase().includes(search.toLowerCase()) ||
    (n.grade || '').toLowerCase().includes(search.toLowerCase())
  )

  const stats = rows.reduce((acc, n) => {
    const d = draft[n.participant_id]
    const mention = d
      ? mentionFromNotes(Object.entries(d.notes || {}), colonnesById)
      : n.mention || ''
    if (mention) acc[mention] = (acc[mention] || 0) + 1

    const vals = d
      ? Object.entries(d.notes || {}).map(([cid, val]) => normalizeTo20(val, colonnesById[cid]?.note_max ?? 20)).filter(v => v !== null)
      : Object.entries(n.notes || {}).map(([cid, cell]) => normalizeTo20(cell?.note, colonnesById[cid]?.note_max ?? 20)).filter(v => v !== null)
    vals.forEach(v => {
      acc._sum = (acc._sum || 0) + v
      acc._count = (acc._count || 0) + 1
    })
    return acc
  }, {})
  const moyenne = stats._count ? (stats._sum / stats._count).toFixed(2) : null
  const nbSaisies = rows.filter(n => {
    const d = draft[n.participant_id]
    if (d) {
      return Object.values(d.notes || {}).some(v => v !== '')
    }
    return Object.values(n.notes || {}).some(cell => cell?.note !== null && cell?.note !== undefined)
  }).length

  const focusNextInput = (participantId, colonneId) => {
    const ids = filtered.map(x => x.participant_id)
    const colIds = colonnes.map(c => c.id)
    const pIdx = ids.indexOf(participantId)
    const cIdx = colIds.indexOf(colonneId)
    const nextP = ids[pIdx + 1]
    const nextC = colIds[cIdx + 1]
    const refKey = nextP ? `${nextP}-${colonneId}` : (nextC ? `${participantId}-${nextC}` : null)
    if (refKey && inputRefs.current[refKey]) {
      inputRefs.current[refKey].focus()
    } else if (nextP && inputRefs.current[`${nextP}-${colonneId}`]) {
      inputRefs.current[`${nextP}-${colonneId}`].focus()
    }
  }

  if (loading) return <div className="loading"><div className="spinner"></div></div>

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }}>
        <div>
          <h2 style={{ margin: 0, fontWeight: 700 }}>Notes — {module?.intitule}</h2>
          <p style={{ margin: '0.25rem 0 0', color: 'var(--text-muted)', fontSize: '0.88rem' }}>
            {rows.length} étudiant{rows.length !== 1 ? 's' : ''} inscrit{rows.length !== 1 ? 's' : ''} · {nbSaisies} avec note{nbSaisies !== 1 ? 's' : ''}
            {colonnes.length > 1 && <> · {colonnes.length} colonnes</>}
            {moyenne && <> · Moyenne&nbsp;<strong>{moyenne}/20</strong></>}
            <span style={{ display: 'block', marginTop: 4 }}>
              Admis si moyenne ≥ <strong>{criteres.seuil_admission}/20</strong> et présence au module ≥ <strong>{criteres.taux_presence_min}%</strong>
            </span>
          </p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <Link
            to={`/formations/${formationId}/decisions`}
            className="btn btn-outline-secondary btn-sm"
            title="Décisions pédagogiques de la formation"
          >
            <i className="bi bi-clipboard-check me-1"></i>Décisions
          </Link>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => setShowAddColonne(v => !v)}
          >
            <i className="bi bi-plus-lg me-1"></i>Ajouter une colonne
          </button>
          <button
            type="button"
            className="btn btn-outline-secondary btn-sm"
            onClick={() => handlePrintFiche()}
            disabled={printing !== null || rows.length === 0}
            title="Imprimer la fiche de notes du module (tous les étudiants)"
          >
            {printing === 'module'
              ? <><span className="spinner-border spinner-border-sm me-1"></span>Génération…</>
              : <><i className="bi bi-printer me-1"></i>Imprimer la fiche</>}
          </button>
          <Link to={`/formations/${module?.formation ?? formationId}/modules/${moduleId}`} className="btn btn-sm btn-outline-secondary">
            <i className="bi bi-arrow-left me-1"></i>Retour au module
          </Link>
          <button
            className="btn btn-primary btn-sm"
            onClick={handleSaveAll}
            disabled={saving || !dirty}
          >
            {saving
              ? <><span className="spinner-border spinner-border-sm me-1"></span>Sauvegarde…</>
              : <><i className="bi bi-floppy me-1"></i>Enregistrer tout</>}
          </button>
        </div>
      </div>

      {showAddColonne && (
        <form
          onSubmit={handleAddColonne}
          className="card"
          style={{ padding: '1rem', marginBottom: '1rem', display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}
        >
          <div style={{ flex: '1 1 220px' }}>
            <label className="form-label" style={{ fontSize: '0.82rem', fontWeight: 600 }}>Intitulé de la colonne</label>
            <input
              className="form-control form-control-sm"
              placeholder="Ex : Examen final, CC2…"
              value={newColonneLibelle}
              onChange={e => setNewColonneLibelle(e.target.value)}
              autoFocus
            />
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="submit" className="btn btn-primary btn-sm" disabled={addingColonne}>
              {addingColonne ? 'Ajout…' : 'Ajouter'}
            </button>
            <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => setShowAddColonne(false)}>
              Annuler
            </button>
          </div>
        </form>
      )}

      {rows.length > 0 && (
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
          {['TRES_BIEN', 'BIEN', 'ASSEZ_BIEN', 'PASSABLE', 'INSUFFISANT'].map(m => (
            <div key={m} className="card" style={{ padding: '0.6rem 1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <MentionBadge mention={m} />
              <span style={{ fontWeight: 700 }}>{stats[m] || 0}</span>
            </div>
          ))}
        </div>
      )}

      <div style={{ marginBottom: '1rem' }}>
        <input
          className="form-control"
          placeholder="Rechercher par nom, matricule, grade…"
          value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ maxWidth: 360 }}
        />
      </div>

      {rows.length === 0 ? (
        <div className="empty-state">
          <i className="bi bi-people" style={{ fontSize: '3rem', color: 'var(--text-muted)' }}></i>
          <p>Aucun étudiant inscrit à ce module</p>
        </div>
      ) : (
        <div className="card" style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.875rem' }}>
            <thead>
              <tr style={{ borderBottom: '2px solid var(--border)', background: 'var(--bg-secondary, #f9fafb)' }}>
                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontWeight: 700, whiteSpace: 'nowrap' }}>Étudiant</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'left', fontWeight: 700 }}>Grade</th>
                {colonnes.map(c => (
                  <th key={c.id} style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700, minWidth: 110 }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }}>
                      <span>{c.libelle}</span>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 500 }}>/ {c.note_max}</span>
                      {colonnes.length > 1 && (
                        <button
                          type="button"
                          className="btn btn-link btn-sm p-0"
                          style={{ fontSize: '0.68rem', color: '#c62828' }}
                          title="Supprimer cette colonne"
                          onClick={() => handleDeleteColonne(c)}
                        >
                          <i className="bi bi-trash"></i>
                        </button>
                      )}
                    </div>
                  </th>
                ))}
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Mention</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Moy. /20</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Présence au module</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Admis</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'left', fontWeight: 700 }}>Observations</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'left', fontWeight: 700, color: 'var(--text-muted)', fontSize: '0.78rem' }}>Saisi par</th>
                <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', fontWeight: 700 }}>Fiche</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((n, idx) => {
                const d = draft[n.participant_id] || emptyDraftRow(colonnes)
                const rowMention = mentionFromNotes(Object.entries(d.notes || {}), colonnesById)
                const liveMoy = (() => {
                  const vals = Object.entries(d.notes || {})
                    .map(([cid, val]) => normalizeTo20(val, colonnesById[cid]?.note_max ?? 20))
                    .filter(v => v !== null)
                  if (!vals.length) return n.moyenne
                  return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2)
                })()
                const moyNum = liveMoy !== null && liveMoy !== undefined && liveMoy !== '' ? parseFloat(liveMoy) : null
                const taux = n.taux_presence
                const admis = moyNum !== null && taux !== null
                  && moyNum >= criteres.seuil_admission
                  && taux >= criteres.taux_presence_min
                return (
                  <tr key={n.participant_id} style={{ borderBottom: '1px solid var(--border)', background: idx % 2 === 0 ? 'transparent' : 'var(--bg-secondary, #fafafa)' }}>
                    <td style={{ padding: '0.65rem 1rem', whiteSpace: 'nowrap' }}>
                      <div style={{ fontWeight: 600 }}>{n.nom} {n.prenom}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{n.matricule}</div>
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem' }}>
                      {n.grade && (
                        <span style={{ fontSize: '0.78rem', background: '#e8eaf6', color: '#283593', padding: '2px 8px', borderRadius: '20px', fontWeight: 600 }}>
                          {n.grade}
                        </span>
                      )}
                    </td>
                    {colonnes.map(c => {
                      const val = d.notes?.[c.id] ?? ''
                      const noteNum = val !== '' ? parseFloat(val) : null
                      const max = c.note_max || 20
                      const isValid = val === '' || (noteNum !== null && !isNaN(noteNum) && noteNum >= 0 && noteNum <= max)
                      const refKey = `${n.participant_id}-${c.id}`
                      const normalized = noteNum !== null && !isNaN(noteNum) ? normalizeTo20(noteNum, max) : null
                      return (
                        <td key={c.id} style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                          <input
                            ref={el => { inputRefs.current[refKey] = el }}
                            type="number"
                            step="0.25"
                            min="0"
                            max={max}
                            value={val}
                            onChange={e => updateDraftNote(n.participant_id, c.id, e.target.value)}
                            style={{
                              width: 72, textAlign: 'center', padding: '4px 6px',
                              border: `1.5px solid ${isValid ? 'var(--border)' : '#e53935'}`,
                              borderRadius: 6, fontSize: '0.9rem', fontWeight: 600,
                              background: val !== '' && isValid ? ((normalized ?? 0) >= 10 ? '#e9f3f8' : '#fff8f8') : '',
                            }}
                            placeholder="—"
                            onKeyDown={e => {
                              if (e.key === 'Enter') {
                                e.preventDefault()
                                focusNextInput(n.participant_id, c.id)
                              }
                            }}
                          />
                          {!isValid && (
                            <div style={{ fontSize: '0.68rem', color: '#e53935', marginTop: 2 }}>0–{max}</div>
                          )}
                        </td>
                      )
                    })}
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                      <MentionBadge mention={rowMention} />
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center', fontWeight: 700,
                      color: moyNum !== null ? (moyNum >= criteres.seuil_admission ? '#125a99' : '#b71c1c') : 'var(--text-muted)' }}>
                      {moyNum !== null && !isNaN(moyNum) ? `${moyNum.toFixed(2)}` : '—'}
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                      {taux !== null && taux !== undefined ? (
                        <>
                          <span style={{ fontWeight: 600, color: taux >= criteres.taux_presence_min ? '#125a99' : '#b71c1c' }}>
                            {taux}%
                          </span>
                          {n.heures_prevues > 0 && (
                            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>
                              {n.heures_presence}h / {n.heures_prevues}h
                            </div>
                          )}
                        </>
                      ) : '—'}
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                      {moyNum !== null && taux !== null && taux !== undefined ? (
                        admis
                          ? <span style={{ color: '#125a99', fontWeight: 700 }}><i className="bi bi-check-circle-fill"></i> Oui</span>
                          : <span style={{ color: '#b71c1c', fontWeight: 600 }}><i className="bi bi-x-circle"></i> Non</span>
                      ) : <span style={{ color: 'var(--text-muted)' }}>—</span>}
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', minWidth: 180 }}>
                      <input
                        type="text"
                        value={d.observations}
                        onChange={e => updateDraftObservations(n.participant_id, e.target.value)}
                        style={{ width: '100%', padding: '4px 8px', border: '1.5px solid var(--border)', borderRadius: 6, fontSize: '0.82rem' }}
                        placeholder="Observations…"
                      />
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                      {n.saisie_par || '—'}
                      {n.updated_at && (
                        <div style={{ fontSize: '0.68rem' }}>
                          {new Date(n.updated_at).toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' })}
                        </div>
                      )}
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center' }}>
                      <button
                        type="button"
                        className="btn btn-sm btn-outline-secondary"
                        style={{ padding: '2px 8px' }}
                        onClick={() => handlePrintFiche(n)}
                        disabled={printing !== null}
                        title={`Imprimer la fiche de notes de ${n.nom} ${n.prenom}`}
                      >
                        {printing === `p-${n.participant_id}`
                          ? <span className="spinner-border spinner-border-sm"></span>
                          : <i className="bi bi-printer"></i>}
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {dirty && (
        <div style={{
          position: 'fixed', bottom: '1.5rem', right: '1.5rem',
          background: 'var(--primary)', color: '#fff',
          borderRadius: 12, padding: '0.75rem 1.25rem',
          boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
          display: 'flex', alignItems: 'center', gap: '0.75rem', zIndex: 999,
        }}>
          <i className="bi bi-exclamation-circle"></i>
          <span style={{ fontSize: '0.875rem' }}>Modifications non sauvegardées</span>
          <button className="btn btn-sm" style={{ background: '#fff', color: 'var(--primary)', fontWeight: 700 }}
            onClick={handleSaveAll} disabled={saving}>
            {saving ? 'Sauvegarde…' : 'Enregistrer'}
          </button>
        </div>
      )}
    </div>
  )
}
