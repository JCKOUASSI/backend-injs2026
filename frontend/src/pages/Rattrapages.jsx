import React, { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import { PRESENCE_ACTION_ROLES } from '../utils/roles'

const STATUT_BADGE = {
  PLANIFIE: { label: 'Planifié', bg: '#fffae8', fg: '#9a7a00' },
  EFFECTUE: { label: 'Effectué', bg: '#e8eef6', fg: '#09306c' },
  ANNULE: { label: 'Annulé', bg: '#fdecec', fg: '#b42318' },
}

const emptyForm = {
  participant: null,
  seances: [],
  motif: '',
  generer_presence: false,
}

function cohorteLabel(obj) {
  if (!obj) return ''
  return obj.cohorte || [obj.grade, obj.groupe, obj.vague].filter(Boolean).join(' / ')
}

function seanceLabel(s) {
  if (!s) return ''
  const horaires = s.heure_debut && s.heure_fin ? ` ${s.heure_debut}–${s.heure_fin}` : ''
  return `${s.date || ''} · ${s.intitule}${horaires}`
}

/** Champ de recherche avec liste déroulante (auditeur ou séance). */
function SearchSelect({ placeholder, icon, value, onSelect, fetcher, renderItem, disabled }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef(null)

  useEffect(() => {
    if (!open) return
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const data = await fetcher(query)
        setResults(Array.isArray(data) ? data : [])
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 250)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [query, open])

  useEffect(() => {
    const onClickOutside = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  if (value) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <div className="form-control" style={{ display: 'flex', alignItems: 'center', background: '#f1f5f9' }}>
          <i className={`bi ${icon} me-2`}></i>
          <span>{renderItem(value, true)}</span>
        </div>
        {!disabled && (
          <button type="button" className="btn btn-outline-secondary btn-sm" onClick={() => onSelect(null)} title="Changer">
            <i className="bi bi-x-lg"></i>
          </button>
        )}
      </div>
    )
  }

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <input
        type="text"
        className="form-control"
        placeholder={placeholder}
        value={query}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
      />
      {open && (
        <div style={{
          position: 'absolute', zIndex: 20, left: 0, right: 0, top: '100%',
          background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6,
          maxHeight: 280, overflowY: 'auto', boxShadow: '0 6px 18px rgba(0,0,0,0.12)',
        }}>
          {loading ? (
            <div className="text-muted" style={{ padding: '0.6rem 0.8rem' }}>Recherche…</div>
          ) : results.length === 0 ? (
            <div className="text-muted" style={{ padding: '0.6rem 0.8rem' }}>Aucun résultat</div>
          ) : results.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => { onSelect(item); setOpen(false); setQuery('') }}
              style={{
                display: 'block', width: '100%', textAlign: 'left', border: 'none',
                background: 'transparent', padding: '0.5rem 0.8rem', cursor: 'pointer',
                borderBottom: '1px solid #f1f5f9',
              }}
              onMouseOver={(e) => (e.currentTarget.style.background = '#f8fafc')}
              onMouseOut={(e) => (e.currentTarget.style.background = 'transparent')}
            >
              {renderItem(item, false)}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Sélection multiple de séances (plusieurs jours), par séance ou par module entier. */
function SeanceMultiSelect({ selected, onAdd, onAddMany, onRemove, fetchSeances, fetchModules, disabled }) {
  const [mode, setMode] = useState('seance')
  const [query, setQuery] = useState('')
  const [results, setResults] = useState([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const boxRef = useRef(null)
  const selectedIds = new Set(selected.map((s) => s.id))

  useEffect(() => {
    if (!open || disabled) return
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const data = mode === 'module' ? await fetchModules(query) : await fetchSeances(query)
        setResults(Array.isArray(data) ? data : [])
      } catch {
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 250)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [query, open, disabled, mode])

  useEffect(() => {
    const onClickOutside = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  const switchMode = (m) => { setMode(m); setResults([]); setOpen(true) }

  return (
    <div ref={boxRef} style={{ position: 'relative' }}>
      <div className="btn-group btn-group-sm" style={{ marginBottom: '0.4rem' }}>
        <button type="button" className={`btn btn-outline-primary ${mode === 'seance' ? 'active' : ''}`} disabled={disabled} onClick={() => switchMode('seance')}>
          <i className="bi bi-calendar-event me-1"></i>Par séance
        </button>
        <button type="button" className={`btn btn-outline-primary ${mode === 'module' ? 'active' : ''}`} disabled={disabled} onClick={() => switchMode('module')}>
          <i className="bi bi-collection me-1"></i>Module entier
        </button>
      </div>

      {selected.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', marginBottom: '0.4rem' }}>
          {selected.map((s) => (
            <span key={s.id} style={{
              background: '#e8eef6', border: '1px solid #96b8e8', borderRadius: 6,
              padding: '2px 8px', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
            }}>
              <i className="bi bi-calendar-event"></i>
              {s.module?.intitule} · {seanceLabel(s)}
              <button type="button" onClick={() => onRemove(s.id)} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#b42318' }} title="Retirer">
                <i className="bi bi-x-lg"></i>
              </button>
            </span>
          ))}
        </div>
      )}
      <input
        type="text"
        className="form-control"
        placeholder={mode === 'module'
          ? 'Rechercher un module d\u2019accueil (ajoute toutes ses séances)…'
          : 'Rechercher un module / groupe / date… (cochez plusieurs séances)'}
        value={query}
        disabled={disabled}
        onFocus={() => setOpen(true)}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
      />
      {open && !disabled && (
        <div style={{
          position: 'absolute', zIndex: 20, left: 0, right: 0, top: '100%',
          background: '#fff', border: '1px solid #e2e8f0', borderRadius: 6,
          maxHeight: 300, overflowY: 'auto', boxShadow: '0 6px 18px rgba(0,0,0,0.12)',
        }}>
          {loading ? (
            <div className="text-muted" style={{ padding: '0.6rem 0.8rem' }}>Recherche…</div>
          ) : results.length === 0 ? (
            <div className="text-muted" style={{ padding: '0.6rem 0.8rem' }}>Aucun résultat</div>
          ) : mode === 'module' ? results.map((m) => {
            const seances = (m.seances || []).map((s) => ({ ...s, module: { id: m.id, intitule: m.intitule, cohorte: m.cohorte, formation: m.formation }, deja_inscrit: m.deja_inscrit }))
            const nbAdded = seances.filter((s) => selectedIds.has(s.id)).length
            const allBlocked = m.deja_inscrit
            return (
              <button
                key={m.id}
                type="button"
                disabled={seances.length === 0 || allBlocked}
                onClick={() => { if (!allBlocked) onAddMany(seances) }}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%', textAlign: 'left',
                  border: 'none', background: 'transparent', padding: '0.5rem 0.8rem',
                  cursor: seances.length ? 'pointer' : 'not-allowed', borderBottom: '1px solid #f1f5f9',
                }}
              >
                <i className="bi bi-collection text-primary"></i>
                <span>
                  <strong>{m.intitule}</strong> <small className="text-muted">{m.cohorte}</small>
                  {m.deja_inscrit && <span className="text-warning ms-1" title="Déjà inscrit à ce module">⚠ déjà inscrit</span>}
                  <br /><small className="text-muted">{m.formation} · {m.nb_seances} séance(s){nbAdded ? ` — ${nbAdded} déjà ajoutée(s)` : ''}</small>
                </span>
              </button>
            )
          }) : results.map((s) => {
            const isSel = selectedIds.has(s.id)
            const blocked = s.deja_inscrit
            return (
              <button
                key={s.id}
                type="button"
                disabled={blocked && !isSel}
                onClick={() => {
                  if (blocked && !isSel) return
                  isSel ? onRemove(s.id) : onAdd(s)
                }}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem', width: '100%', textAlign: 'left',
                  border: 'none', background: isSel ? '#f0f6fd' : (blocked ? '#fef2f2' : 'transparent'),
                  padding: '0.5rem 0.8rem',
                  cursor: blocked && !isSel ? 'not-allowed' : 'pointer',
                  opacity: blocked && !isSel ? 0.65 : 1,
                  borderBottom: '1px solid #f1f5f9',
                }}
              >
                <i className={`bi ${isSel ? 'bi-check-square-fill text-success' : 'bi-square'}`}></i>
                <span>
                  <strong>{s.module?.intitule}</strong> <small className="text-muted">{s.module?.cohorte}</small>
                  {s.deja_inscrit && <span className="text-warning ms-1" title="Déjà inscrit à ce module">⚠ déjà inscrit</span>}
                  <br /><small className="text-muted">{seanceLabel(s)}</small>
                </span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function Rattrapages() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const canManage = PRESENCE_ACTION_ROLES.includes(user?.role)

  const [rattrapages, setRattrapages] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filterStatut, setFilterStatut] = useState('')
  const [search, setSearch] = useState('')

  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ ...emptyForm })
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      if (filterStatut) params.set('statut', filterStatut)
      if (search.trim()) params.set('q', search.trim())
      const qs = params.toString()
      const res = await api.get(`/rattrapages/${qs ? `?${qs}` : ''}`)
      setRattrapages(Array.isArray(res.data) ? res.data : [])
      setError('')
    } catch {
      setError('Erreur lors du chargement des rattrapages')
    } finally {
      setLoading(false)
    }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { load() }, [])
  useEffect(() => {
    const t = setTimeout(load, 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [filterStatut, search])

  const searchParticipants = async (q) => {
    const res = await api.get(`/rattrapages/participants/?q=${encodeURIComponent(q || '')}`)
    return res.data
  }
  const searchSeances = async (q) => {
    const pid = form.participant?.id ? `&participant=${form.participant.id}` : ''
    const res = await api.get(`/rattrapages/seances/?q=${encodeURIComponent(q || '')}${pid}`)
    return res.data
  }
  const searchModules = async (q) => {
    const pid = form.participant?.id ? `&participant=${form.participant.id}` : ''
    const res = await api.get(`/rattrapages/modules/?q=${encodeURIComponent(q || '')}${pid}`)
    return res.data
  }

  const addSeances = (list) => setForm((f) => {
    const incoming = Array.isArray(list) ? list : [list]
    const blocked = incoming.filter((s) => s.deja_inscrit)
    if (blocked.length > 0) {
      showToast(
        "Séance ignorée : l'étudiant est déjà inscrit à ce module d'accueil.",
        'error',
      )
    }
    const allowed = incoming.filter((s) => !s.deja_inscrit)
    if (allowed.length === 0) return f
    const existing = new Set(f.seances.map((s) => s.id))
    const toAdd = allowed.filter((s) => !existing.has(s.id))
    return { ...f, seances: [...f.seances, ...toAdd] }
  })

  const openCreate = () => {
    setForm({ ...emptyForm })
    setFormError('')
    setShowModal(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')
    if (!form.participant || form.seances.length === 0) {
      setFormError('Sélectionnez un étudiant et au moins une séance de rattrapage.')
      return
    }
    if (form.seances.some((s) => s.deja_inscrit)) {
      setFormError("Retirez les séances où l'étudiant est déjà inscrit au module d'accueil.")
      return
    }
    setSaving(true)
    try {
      const res = await api.post('/rattrapages/', {
        participant_id: form.participant.id,
        seance_rattrapage_ids: form.seances.map((s) => s.id),
        motif: form.motif,
        generer_presence: form.generer_presence,
      })
      setShowModal(false)
      const created = res.data?.count ?? 1
      const skipped = res.data?.skipped?.length || 0
      const reactivated = res.data?.reactivated?.length || 0
      showToast(
        `${created} rattrapage(s) créé(s)${
          reactivated ? ` (${reactivated} réactivé(s))` : ''
        }${skipped ? ` — ${skipped} ignoré(s) (déjà existant)` : ''}`,
      )
      load()
    } catch (err) {
      const data = err.response?.data
      setFormError(data?.detail || 'Erreur lors de la création du rattrapage')
    } finally {
      setSaving(false)
    }
  }

  const handleGenerer = async (r) => {
    setBusyId(r.id)
    try {
      await api.post(`/rattrapages/${r.id}/generer-presence/`)
      showToast('Présence de rattrapage générée')
      load()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de la génération', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const handleAnnuler = (r) => {
    setConfirmDialog({
      message: 'Annuler ce rattrapage ?',
      detail: r.pointage_id
        ? 'La présence générée sera également supprimée.'
        : 'Le rattrapage passera au statut « Annulé ».',
      onConfirm: async () => {
        setBusyId(r.id)
        try {
          await api.post(`/rattrapages/${r.id}/annuler/`, { supprimer_pointage: !!r.pointage_id })
          showToast('Rattrapage annulé')
          load()
        } catch (err) {
          showToast(err.response?.data?.detail || 'Erreur lors de l\'annulation', 'error')
        } finally {
          setBusyId(null)
        }
      },
    })
  }

  return (
    <div>
      <div className="card">
        <div className="card-body">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <h6 className="mb-0" style={{ fontWeight: 700 }}>
                <i className="bi bi-arrow-left-right me-2"></i>Rattrapages
              </h6>
              <small className="text-muted">
                Déplacer un étudiant vers la séance d&apos;une autre cohorte (groupe / grade / secrétariat) pour rattraper une séance manquée, sans modifier son groupe d&apos;origine.
              </small>
            </div>
            {canManage && (
              <button className="btn btn-dfrc" onClick={openCreate}>
                <i className="bi bi-plus-lg me-1"></i>Nouveau rattrapage
              </button>
            )}
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="card">
        <div className="card-header-bar" style={{ gap: '0.75rem', flexWrap: 'wrap' }}>
          <span><i className="bi bi-arrow-left-right me-2"></i>Liste des rattrapages</span>
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <select className="form-control form-control-sm" style={{ width: 'auto' }} value={filterStatut} onChange={(e) => setFilterStatut(e.target.value)}>
              <option value="">Tous les statuts</option>
              <option value="PLANIFIE">Planifié</option>
              <option value="EFFECTUE">Effectué</option>
              <option value="ANNULE">Annulé</option>
            </select>
            <input
              type="text"
              className="form-control form-control-sm"
              style={{ width: 220 }}
              placeholder="Rechercher (étudiant, module…)"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>
        <div className="card-body-flush">
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : rattrapages.length === 0 ? (
            <div className="text-center py-5 text-muted">
              <i className="bi bi-arrow-left-right" style={{ fontSize: '2rem' }}></i>
              <p className="mt-2">Aucun rattrapage.{canManage ? ' Cliquez sur « Nouveau rattrapage » pour commencer.' : ''}</p>
            </div>
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Étudiant</th>
                    <th>Cohorte d&apos;origine</th>
                    <th>Module (accueil)</th>
                    <th>Séance de rattrapage</th>
                    <th>Statut</th>
                    {canManage && <th>Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {rattrapages.map((r) => {
                    const badge = STATUT_BADGE[r.statut] || { label: r.statut, bg: '#f3f4f6', fg: '#374151' }
                    return (
                      <tr key={r.id}>
                        <td>
                          <strong>{r.participant.nom} {r.participant.prenom}</strong>
                          <br /><small className="text-muted"><code>{r.participant.matricule}</code> {cohorteLabel(r.participant)}</small>
                        </td>
                        <td>{cohorteLabel(r.participant) || <span className="text-muted">—</span>}</td>
                        <td>
                          {r.module_accueil?.intitule}
                          <br /><small className="text-muted">{r.module_accueil?.formation} · {r.module_accueil?.cohorte}</small>
                        </td>
                        <td>{seanceLabel(r.seance_rattrapage)}</td>
                        <td>
                          <span style={{ background: badge.bg, color: badge.fg, padding: '3px 8px', borderRadius: 999, fontWeight: 600, fontSize: '0.78rem' }}>
                            {badge.label}
                          </span>
                        </td>
                        {canManage && (
                          <td>
                            <div className="btn-group">
                              {r.statut !== 'ANNULE' && (
                                <button
                                  className="btn btn-outline-success btn-sm"
                                  disabled={busyId === r.id}
                                  onClick={() => handleGenerer(r)}
                                  title={r.statut === 'EFFECTUE' ? 'Régénérer la présence' : 'Générer la présence'}
                                >
                                  <i className="bi bi-check2-circle"></i>
                                </button>
                              )}
                              {r.statut !== 'ANNULE' && (
                                <button
                                  className="btn btn-outline-danger btn-sm"
                                  disabled={busyId === r.id}
                                  onClick={() => handleAnnuler(r)}
                                  title="Annuler"
                                >
                                  <i className="bi bi-x-circle"></i>
                                </button>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {confirmDialog && (
        <ConfirmModal
          message={confirmDialog.message}
          detail={confirmDialog.detail}
          onConfirm={() => { setConfirmDialog(null); confirmDialog.onConfirm() }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-arrow-left-right me-2"></i>Nouveau rattrapage</h5>
              <button className="btn-close" onClick={() => setShowModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {formError && (
                  <div className="alert alert-danger" style={{ whiteSpace: 'pre-line', fontSize: '0.85rem', padding: '0.5rem 0.75rem' }}>
                    {formError}
                  </div>
                )}
                <div className="form-group">
                  <label className="form-label">Étudiant *</label>
                  <SearchSelect
                    placeholder="Rechercher par matricule ou nom…"
                    icon="bi-person"
                    value={form.participant}
                    onSelect={(p) => setForm({ ...form, participant: p, seances: [] })}
                    fetcher={searchParticipants}
                    renderItem={(p) => (
                      <span>{p.nom} {p.prenom} <small className="text-muted">({p.matricule}{cohorteLabel(p) ? ` · ${cohorteLabel(p)}` : ''})</small></span>
                    )}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label">Séances de rattrapage (cohorte d&apos;accueil) *</label>
                  <SeanceMultiSelect
                    selected={form.seances}
                    disabled={!form.participant}
                    fetchSeances={searchSeances}
                    fetchModules={searchModules}
                    onAdd={(s) => addSeances(s)}
                    onAddMany={(list) => addSeances(list)}
                    onRemove={(id) => setForm((f) => ({ ...f, seances: f.seances.filter((x) => x.id !== id) }))}
                  />
                  <small className="text-muted">
                    {form.participant
                      ? 'Cochez une ou plusieurs séances (plusieurs jours possibles).'
                      : 'Sélectionnez d\u2019abord l\u2019étudiant.'}
                  </small>
                </div>
                <div className="form-group">
                  <label className="form-label">Motif</label>
                  <textarea className="form-control" rows="2"
                    placeholder="Ex. absence justifiée, chevauchement d'emploi du temps…"
                    value={form.motif} onChange={(e) => setForm({ ...form, motif: e.target.value })} />
                </div>
                <div className="form-check">
                  <input
                    type="checkbox"
                    className="form-check-input"
                    id="generer_presence"
                    checked={form.generer_presence}
                    onChange={(e) => setForm({ ...form, generer_presence: e.target.checked })}
                  />
                  <label className="form-check-label" htmlFor="generer_presence">
                    Forcer la présence immédiatement (sans badgeage de l&apos;étudiant)
                  </label>
                </div>
                <div style={{ background: '#fffae1', border: '1px solid #ffea82', borderRadius: 6, padding: '0.5rem 0.75rem', marginTop: '0.75rem' }}>
                  <small><i className="bi bi-info-circle me-1"></i>
                    L&apos;étudiant garde son groupe/grade/secrétariat d&apos;origine. Les effectifs de la cohorte d&apos;accueil ne sont pas modifiés.
                  </small>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>
                  {saving ? 'Enregistrement…' : 'Créer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
