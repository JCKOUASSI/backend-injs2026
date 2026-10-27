import { useState, useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import ConfirmModal from '../components/ConfirmModal'
import TripleConfirmModal from '../components/TripleConfirmModal'
import { useDebounce } from '../hooks/useDebounce'
import { formatDate } from '../utils/dates'
import {
  buildModulesSearchParams,
  LIST_STORAGE_KEYS,
  parseListPage,
  readModulesFilters,
} from '../utils/listFilters'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import { canMutateFormations, canArchiveModuleFromUser } from '../utils/roles'
import { useReferentiels } from '../hooks/useReferentiels'
import Pagination from '../components/Pagination'
import { parsePaginatedResponse } from '../utils/paginatedResponse'
import { useListNavigationState } from '../hooks/useListReturn'

const emptyForm = {
  formation_id: '', intitule: '', grade: '', groupe: '', vague: '',
  statut: 'PLANIFIEE', date_debut: '', date_fin: '',
  site: '', batiment: '', salle: '', duree_prevue_heures: '',
}

const emptyFormationForm = { formation: '', module: '', ref_formation: '' }
const STATUT_VALUES = ['PLANIFIEE', 'EN_COURS', 'TERMINEE', 'SUSPENDUE']
const DATE_MODES = ['today', 'all', 'date']
const FILTER_LABELS = {
  statut: 'statut',
  secretariat_type: 'secrétariat',
  vague: 'vague',
  grade: 'grade',
  groupe: 'groupe',
}
const getTodayIso = () => {
  const now = new Date()
  const tzOffset = now.getTimezoneOffset() * 60000
  return new Date(now.getTime() - tzOffset).toISOString().slice(0, 10)
}

export default function Modules() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const listNavState = useListNavigationState()
  const [searchParams] = useSearchParams()
  const [modules, setModules] = useState([])
  const [refs, setRefs] = useState({ formations: [], formations_reelles: [], grades: [], grades_modules: [], categories: [], sites: [], batiments: [], salles: [], types_secretariat: [], vagues: [], groupes: [] })
  const [allFormations, setAllFormations] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(() => parseListPage(searchParams))
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [filters, setFilters] = useState(() => readModulesFilters(searchParams, getTodayIso))
  const debouncedSearch = useDebounce(filters.search)

  const [showModal, setShowModal] = useState(false)
  const [editingModule, setEditingModule] = useState(null)
  const [form, setForm] = useState({ ...emptyForm })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState('')
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [archiveTarget, setArchiveTarget] = useState(null)
  const [showFormationModal, setShowFormationModal] = useState(false)
  const [formationForm, setFormationForm] = useState({ ...emptyFormationForm })
  const [savingFormation, setSavingFormation] = useState(false)
  const [formationError, setFormationError] = useState('')
  const [lastCreatedFormationId, setLastCreatedFormationId] = useState('')

  const canManage = canMutateFormations(user)
  const canArchive = canArchiveModuleFromUser(user)

  const refFormationIdForSelectedFormation = () => {
    if (!form.formation_id) return null
    const selected = allFormations.find(f => String(f.id) === String(form.formation_id))
    if (!selected) return null
    const ref = refs.formations.find(rf => rf.intitule === selected.formation)
    return ref?.id ?? null
  }

  const availableRefModules = () => {
    const refFormationId = refFormationIdForSelectedFormation()
    if (!refFormationId) return refs.modules || []
    return (refs.modules || []).filter(m => (m.formation_ids || []).includes(refFormationId))
  }

  const { data: referentielsData } = useReferentiels()

  useEffect(() => {
    if (!referentielsData) return
    const data = referentielsData
    if (data.formations_reelles?.length) {
      setAllFormations(data.formations_reelles)
    } else {
      api.get('/formations/list/?page_size=500').then(r2 => {
        const rows = Array.isArray(r2.data) ? r2.data : (r2.data.results || [])
        const seen = new Set()
        setAllFormations(rows.filter(f => { if (seen.has(f.id)) return false; seen.add(f.id); return true }))
      }).catch(() => {})
    }
    setRefs(data)

    // Une valeur de filtre absente des référentiels (lien obsolète, import modifiant
    // les grades/groupes) reste appliquée à l'API alors qu'aucune option ne peut
    // l'afficher ni la désélectionner : la liste paraît vide sans raison visible.
    const allowed = {
      statut: STATUT_VALUES,
      secretariat_type: (data.types_secretariat || []).map(t => String(t.id)),
      vague: (data.vagues || []).map(v => String(v.libelle)),
      grade: (data.grades_modules || []).map(String),
      groupe: (data.groupes || []).map(String),
    }
    const dropped = Object.keys(allowed).filter(key => (
      filters[key] && allowed[key].length && !allowed[key].includes(String(filters[key]))
    ))
    const badMode = !DATE_MODES.includes(filters.date_mode)
    if (dropped.length || badMode) {
      setFilters(prev => {
        const next = { ...prev }
        dropped.forEach(key => { next[key] = '' })
        if (badMode) next.date_mode = 'all'
        return next
      })
      setPage(1)
    }
    if (dropped.length) {
      showToast(
        `Filtre(s) ignoré(s), valeur inconnue : ${dropped.map(k => FILTER_LABELS[k]).join(', ')}`,
        'info',
      )
    }
    // Faux positif exhaustive-deps (tranché au LOT 6, cf. TESTS_FRONTEND §10.2) :
    // cet effet ne doit se déclencher QU'À L'ARRIVÉE des référentiels pour y
    // confronter les filtres persistés. Il lit volontairement le `filters` du
    // rendu courant (React exécute la dernière version de l'effet, donc jamais
    // de valeur périmée) ; ajouter `filters` le ferait revalider après chaque
    // saisie, et `showToast` est une fonction stable du ToastProvider.
    // Régressions : Modules.test.jsx « nettoie les filtres obsolètes ».
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [referentielsData])
  usePersistedListQuery(
    LIST_STORAGE_KEYS.modules,
    () => buildModulesSearchParams(filters, page, debouncedSearch),
    [
      page,
      filters.statut,
      filters.secretariat_type,
      filters.vague,
      filters.grade,
      filters.groupe,
      filters.date_mode,
      filters.date,
      debouncedSearch,
    ],
  )

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { loadModules() }, [page, filters.statut, filters.secretariat_type, filters.vague, filters.grade, filters.groupe, filters.date_mode, filters.date, debouncedSearch])

  const loadModules = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page, page_size: 50 })
      if (filters.statut) params.set('statut', filters.statut)
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (filters.secretariat_type) params.set('secretariat_type', filters.secretariat_type)
      if (filters.vague) params.set('vague', filters.vague)
      if (filters.grade) params.set('grade', filters.grade)
      if (filters.groupe) params.set('groupe', filters.groupe)
      if (filters.date_mode) params.set('date_mode', filters.date_mode)
      if (filters.date_mode === 'date' && filters.date) params.set('date', filters.date)
      const res = await api.get(`/formations/list/?${params}`)
      const { results, count, totalPages: pages } = parsePaginatedResponse(res.data, 50)
      setModules(results)
      setTotalPages(pages)
      setTotal(count)
    } catch {
      setError('Erreur lors du chargement des modules')
    } finally {
      setLoading(false)
    }
  }

  const openCreate = () => {
    setEditingModule(null)
    setForm({ ...emptyForm, formation_id: lastCreatedFormationId })
    setFormError('')
    setShowModal(true)
  }

  const openEdit = (m) => {
    setEditingModule(m)
    setForm({
      formation_id: m.id || '',
      intitule: m.module || '',
      grade: m.grade || '',
      groupe: m.groupe || '',
      vague: m.vague || '',
      statut: m.statut || 'PLANIFIEE',
      date_debut: m.date_debut ? m.date_debut.slice(0, 10) : '',
      date_fin: m.date_fin ? m.date_fin.slice(0, 10) : '',
      site: m.site || '',
      batiment: m.batiment || '',
      salle: m.salle || '',
      duree_prevue_heures: m.duree_prevue_heures || '',
    })
    setFormError('')
    setShowModal(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      if (editingModule) {
        await api.patch(`/formations/${editingModule.id}/modules/${editingModule.module_id}/`, {
          intitule: form.intitule,
          grade: form.grade,
          groupe: form.groupe,
          vague: form.vague,
          statut: form.statut,
          date_debut: form.date_debut || null,
          date_fin: form.date_fin || null,
          site: form.site,
          batiment: form.batiment,
          salle: form.salle,
          duree_prevue_heures: form.duree_prevue_heures || 0,
        })
        showToast('Module modifié')
      } else {
        await api.post(`/formations/${form.formation_id}/modules/`, {
          intitule: form.intitule,
          grade: form.grade,
          groupe: form.groupe,
          vague: form.vague,
          statut: form.statut,
          date_debut: form.date_debut || null,
          date_fin: form.date_fin || null,
          site: form.site,
          batiment: form.batiment,
          salle: form.salle,
          duree_prevue_heures: form.duree_prevue_heures || 0,
        })
        showToast('Module créé')
      }
      setShowModal(false)
      loadModules()
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        setFormError(Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('\n'))
      } else {
        setFormError('Erreur lors de la sauvegarde')
      }
    } finally {
      setSaving(false)
    }
  }

  const handleCreateFormation = async (e) => {
    e.preventDefault()
    setFormationError('')
    setSavingFormation(true)
    try {
      // Lien D3 (modèle 04.4) : si l'intitulé choisi provient du référentiel
      // des cycles, la session est adossée au cycle correspondant.
      const cycle = (refs.formations || []).find((f) => f.intitule === formationForm.formation)
      const res = await api.post('/formations/', {
        formation: formationForm.formation,
        module_input: formationForm.module,
        ...(cycle ? { ref_formation: cycle.id } : {}),
      })
      const created = res.data
      const title = created?.formation || created?.intitule || formationForm.formation
      if (created?.id) {
        setAllFormations(prev => {
          if (prev.some(f => String(f.id) === String(created.id))) return prev
          return [...prev, { id: created.id, formation: title }]
        })
        setLastCreatedFormationId(String(created.id))
        setForm(f => ({ ...f, formation_id: String(created.id) }))
      }
      setShowFormationModal(false)
      setFormationForm({ ...emptyFormationForm })
      loadModules()
      showToast('Formation créée — vous pouvez y rattacher d’autres modules')
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        setFormationError(Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`).join('\n'))
      } else {
        setFormationError('Erreur lors de la création')
      }
    } finally {
      setSavingFormation(false)
    }
  }

  const handleArchive = (m) => {
    setArchiveTarget(m)
  }

  const confirmArchive = async () => {
    const m = archiveTarget
    if (!m) return
    setArchiveTarget(null)
    try {
      await api.post(`/formations/${m.id}/modules/${m.module_id}/archive/`)
      loadModules()
      showToast('Module archivé — visible uniquement dans l\'espace Archives')
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de l\'archivage', 'error')
    }
  }

  const handleDelete = (m) => {
    setConfirmDialog({
      message: `Supprimer le module "${m.module}" ?`,
      detail: 'Cette action est définitive.',
      onConfirm: async () => {
        try {
          await api.delete(`/formations/${m.id}/modules/${m.module_id}/`)
          loadModules()
          showToast('Module supprimé')
        } catch (err) {
          showToast(err.response?.data?.detail || 'Erreur lors de la suppression', 'error')
        }
      }
    })
  }

  const getStatutBadge = (s) => {
    const map = { PLANIFIEE: 'badge-planifiee', EN_COURS: 'badge-en-cours', TERMINEE: 'badge-terminee', SUSPENDUE: 'badge-suspendue' }
    return map[s] || 'badge-info'
  }
  const getStatutLabel = (s) => {
    const map = { PLANIFIEE: 'Planifié', EN_COURS: 'En cours', TERMINEE: 'Terminé', SUSPENDUE: 'Suspendu' }
    return map[s] || s
  }

  return (
    <div>
      {/* Filtres */}
      <div className="card">
        <div className="card-body">
          <div style={{
            display: 'flex',
            gap: '0.5rem',
            flexWrap: 'wrap',
            alignItems: 'center',
            rowGap: '0.5rem',
          }}>
            <div style={{ flex: '1 1 160px', minWidth: 140 }}>
              <input type="text" className="form-control"
                placeholder="Rechercher un module ou une formation…"
                value={filters.search}
                onChange={e => { setFilters({ ...filters, search: e.target.value }); setPage(1) }} />
            </div>
            <div style={{ flexShrink: 0 }}>
              <select className="form-control" value={filters.statut}
                onChange={e => { setFilters({ ...filters, statut: e.target.value }); setPage(1) }}>
                <option value="">Tous les statuts</option>
                <option value="PLANIFIEE">Planifié</option>
                <option value="EN_COURS">En cours</option>
                <option value="TERMINEE">Terminé</option>
                <option value="SUSPENDUE">Suspendu</option>
              </select>
            </div>
            {!['SECRETARIAT', 'CHEF_SECRETARIAT', 'ENCADRANT'].includes(user?.role) && refs.types_secretariat?.length > 0 && (
              <div style={{ flexShrink: 0 }}>
                <select className="form-control" value={filters.secretariat_type}
                  onChange={e => { setFilters({ ...filters, secretariat_type: e.target.value }); setPage(1) }}>
                  <option value="">Tous les secrétariats</option>
                  {refs.types_secretariat.map(t => (
                    <option key={t.id} value={t.id}>{t.libelle}</option>
                  ))}
                </select>
              </div>
            )}
            {refs.vagues?.length > 0 && (
              <div style={{ flexShrink: 0 }}>
                <select className="form-control" value={filters.vague}
                  onChange={e => { setFilters({ ...filters, vague: e.target.value }); setPage(1) }}>
                  <option value="">Toutes les vagues</option>
                  {refs.vagues.map(v => (
                    <option key={v.id} value={v.libelle}>{v.libelle}</option>
                  ))}
                </select>
              </div>
            )}
            {refs.grades_modules?.length > 0 && (
              <div style={{ flexShrink: 0 }}>
                <select className="form-control" value={filters.grade}
                  onChange={e => { setFilters({ ...filters, grade: e.target.value }); setPage(1) }}>
                  <option value="">Tous les grades</option>
                  {refs.grades_modules.map(g => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </div>
            )}
            {refs.groupes?.length > 0 && (
              <div style={{ flexShrink: 0 }}>
                <select className="form-control" value={filters.groupe}
                  onChange={e => { setFilters({ ...filters, groupe: e.target.value }); setPage(1) }}>
                  <option value="">Tous les groupes</option>
                  {refs.groupes.map(g => (
                    <option key={g} value={g}>{g}</option>
                  ))}
                </select>
              </div>
            )}
            <div style={{ flexShrink: 0 }}>
              <select
                className="form-control"
                value={filters.date_mode}
                onChange={e => {
                  const mode = e.target.value
                  setFilters({
                    ...filters,
                    date_mode: mode,
                    date: mode === 'date' ? (filters.date || getTodayIso()) : filters.date,
                  })
                  setPage(1)
                }}
              >
                <option value="today">Aujourd'hui</option>
                <option value="all">Tous les jours</option>
                <option value="date">Jour spécifique</option>
              </select>
            </div>
            {filters.date_mode === 'date' && (
              <div style={{ flexShrink: 0 }}>
                <input
                  type="date"
                  className="form-control"
                  value={filters.date}
                  onChange={e => { setFilters({ ...filters, date: e.target.value }); setPage(1) }}
                />
              </div>
            )}
            {canManage && (
              <button onClick={openCreate} className="btn btn-dfrc" style={{ flexShrink: 0, marginLeft: 'auto', whiteSpace: 'nowrap' }}>
                <i className="bi bi-plus-lg me-1"></i>Nouveau module
              </button>
            )}
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="card">
        <div className="card-header-bar">
          <span><i className="bi bi-book me-2"></i>Liste des cours</span>
          <span className="badge-bg-secondary">{total} module(s)</span>
        </div>
        <div className="card-body-flush">
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : (
            <>
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Modules</th>
                      <th>Formation</th>
                      <th>Grade</th>
                      <th>Secrétariat</th>
                      <th>Groupe</th>
                      <th>Dates</th>
                      <th>Étudiants</th>
                      <th>Statut</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modules.length > 0 ? modules.map(m => (
                      <tr key={m.module_id || m.id}>
                        <td><strong style={{ color: '#805ad5' }}>{m.module}</strong></td>
                        <td><span style={{ fontSize: '0.82rem', color: '#64748b' }}>{m.formation}</span></td>
                        <td><span style={{ fontSize: '0.82rem', background: '#f0f7ff', color: '#11407d', padding: '2px 7px', borderRadius: 4 }}>{m.grade || '—'}</span></td>
                        <td>{m.secretariat_nom
                          ? <span className="text-muted" style={{ fontSize: '0.82rem' }}>{m.secretariat_nom}</span>
                          : <span className="text-muted">-</span>}
                        </td>
                        <td>{m.groupe || '-'}</td>
                        <td>
                          <small>{formatDate(m.date_debut)}</small>
                          <br /><small>{formatDate(m.date_fin)}</small>
                        </td>
                        <td>{m.nb_participants || 0} <small className="text-muted">attendus</small></td>
                        <td>
                          <span className={`badge ${getStatutBadge(m.statut)}`}>{getStatutLabel(m.statut)}</span>
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', alignItems: 'center' }}>
                            <Link
                              to={`/formations/${m.id}/modules/${m.module_id}`}
                              state={listNavState}
                              className="btn btn-outline-primary btn-sm"
                              title="Détail"
                            >
                              <i className="bi bi-eye"></i>
                            </Link>
                            {canManage && (
                              <button onClick={() => openEdit(m)} className="btn btn-outline-secondary btn-sm" title="Modifier">
                                <i className="bi bi-pencil"></i>
                              </button>
                            )}
                            {canArchive && !m.archived && (
                              <button
                                onClick={() => handleArchive(m)}
                                className="btn btn-warning btn-sm"
                                title="Archiver ce module (3 confirmations)"
                                style={{ whiteSpace: 'nowrap' }}
                              >
                                <i className="bi bi-archive me-1"></i>Archiver
                              </button>
                            )}
                            {canManage && (
                              <button onClick={() => handleDelete(m)} className="btn btn-outline-danger btn-sm" title="Supprimer">
                                <i className="bi bi-trash"></i>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="9" className="text-center py-4 text-muted">Aucun module trouvé</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                totalItems={total}
                pageSize={50}
              />
            </>
          )}
        </div>
      </div>

      {/* ── MODAL NOUVELLE FORMATION ── */}
      {showFormationModal && (
        <div className="modal-overlay" style={{ zIndex: 1100 }} onClick={() => setShowFormationModal(false)}>
          <div className="modal-content" style={{ maxWidth: '480px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-mortarboard me-2"></i>Nouvelle formation</h5>
              <button className="btn-close" onClick={() => setShowFormationModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleCreateFormation}>
              <div className="modal-body">
                {formationError && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line' }}>{formationError}</div>}
                <div className="form-group">
                  <label className="form-label">Formation (cycle) *</label>
                  {refs.formations?.length > 0 ? (
                    <select className="form-control" required value={formationForm.formation}
                      onChange={e => setFormationForm({ ...formationForm, formation: e.target.value })}>
                      <option value="">-- Choisir --</option>
                      {refs.formations.map(f => <option key={f.id} value={f.intitule}>{f.intitule}</option>)}
                    </select>
                  ) : (
                    <input type="text" className="form-control" required value={formationForm.formation}
                      placeholder="Ex : Formation des cadres"
                      onChange={e => setFormationForm({ ...formationForm, formation: e.target.value })} />
                  )}
                </div>
                <div className="form-group">
                  <label className="form-label">Premier module (intitulé) *</label>
                  <input type="text" className="form-control" required value={formationForm.module}
                    placeholder="Ex : Droit Administratif"
                    onChange={e => setFormationForm({ ...formationForm, module: e.target.value })} />
                  <small className="text-muted" style={{ display: 'block', marginTop: '0.35rem' }}>
                    Vous pourrez rattacher d’autres modules à cette formation ensuite.
                  </small>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowFormationModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={savingFormation}>
                  {savingFormation ? 'Création...' : 'Créer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL CRÉATION / ÉDITION ── */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" style={{ maxWidth: '600px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-book me-2"></i>{editingModule ? 'Modifier le module' : 'Nouveau module'}</h5>
              <button className="btn-close" onClick={() => setShowModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body" style={{ maxHeight: '72vh', overflowY: 'auto' }}>
                {formError && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line' }}>{formError}</div>}

                {/* Formation (création seulement) */}
                {!editingModule && (
                  <div className="form-group">
                    <label className="form-label">Formation *</label>
                    <select className="form-control" required value={form.formation_id}
                      onChange={e => setForm({ ...form, formation_id: e.target.value })}>
                      <option value="">-- Choisir une formation --</option>
                      {allFormations.map(f => (
                        <option key={f.id} value={f.id}>{f.formation}</option>
                      ))}
                    </select>
                    <small className="text-muted" style={{ display: 'block', marginTop: '0.35rem' }}>
                      Une formation peut regrouper un ou plusieurs modules. Choisissez une formation existante
                      {' '}
                      <button
                        type="button"
                        className="btn btn-link btn-sm p-0 align-baseline"
                        onClick={() => { setFormationError(''); setShowFormationModal(true) }}
                      >
                        ou créez-en une nouvelle
                      </button>
                      .
                    </small>
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label">Intitulé du module *</label>
                  {!editingModule && availableRefModules().length > 0 ? (
                    <select className="form-control" required value={form.intitule}
                      onChange={e => {
                        const sel = availableRefModules().find(m => m.intitule === e.target.value)
                        setForm({ ...form, intitule: e.target.value, duree_prevue_heures: sel?.volume_horaire || form.duree_prevue_heures })
                      }}>
                      <option value="">-- Choisir un module --</option>
                      {availableRefModules().map(m => <option key={m.id} value={m.intitule}>{m.intitule}</option>)}
                    </select>
                  ) : (
                    <input type="text" className="form-control" required value={form.intitule}
                      placeholder="Ex : Droit Administratif"
                      onChange={e => setForm({ ...form, intitule: e.target.value })} />
                  )}
                </div>

                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Grade</label>
                    {refs.grades?.length > 0 ? (
                      <select className="form-control" value={form.grade}
                        onChange={e => setForm({ ...form, grade: e.target.value })}>
                        <option value="">-- Grade --</option>
                        {refs.grades.map(g => <option key={g.id} value={g.libelle}>{g.libelle}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="form-control" placeholder="A4, A3…" value={form.grade}
                        onChange={e => setForm({ ...form, grade: e.target.value })} />
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Statut</label>
                    <select className="form-control" value={form.statut}
                      onChange={e => setForm({ ...form, statut: e.target.value })}>
                      <option value="PLANIFIEE">Planifié</option>
                      <option value="EN_COURS">En cours</option>
                      <option value="SUSPENDUE">Suspendu</option>
                      <option value="TERMINEE">Terminé</option>
                    </select>
                  </div>
                </div>

                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Groupe</label>
                    <input type="text" className="form-control" placeholder="GROUPE 1…" value={form.groupe}
                      onChange={e => setForm({ ...form, groupe: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Vague</label>
                    <select className="form-control" value={form.vague}
                      onChange={e => setForm({ ...form, vague: e.target.value })}>
                      <option value="">-- Sélectionner --</option>
                      {(refs.vagues || []).map(v => (
                        <option key={v.id} value={v.libelle}>{v.libelle}</option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Date début</label>
                    <input type="date" className="form-control" value={form.date_debut}
                      onChange={e => setForm({ ...form, date_debut: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Date fin</label>
                    <input type="date" className="form-control" value={form.date_fin}
                      onChange={e => setForm({ ...form, date_fin: e.target.value })} />
                  </div>
                </div>

                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Site</label>
                    {refs.sites?.length > 0 ? (
                      <select className="form-control" value={form.site}
                        onChange={e => setForm({ ...form, site: e.target.value, batiment: '', salle: '' })}>
                        <option value="">-- Site --</option>
                        {refs.sites.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="form-control" value={form.site}
                        onChange={e => setForm({ ...form, site: e.target.value })} />
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Bâtiment</label>
                    {refs.batiments?.length > 0 ? (() => {
                      const siteObj = refs.sites?.find(s => s.nom === form.site)
                      const filteredBatiments = siteObj
                        ? refs.batiments.filter(b => b.site_id === siteObj.id)
                        : refs.batiments
                      return (
                        <select className="form-control" value={form.batiment}
                          onChange={e => setForm({ ...form, batiment: e.target.value, salle: '' })}>
                          <option value="">-- Bâtiment --</option>
                          {filteredBatiments.map(b => <option key={b.id} value={b.nom}>{b.nom}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="form-control" value={form.batiment}
                        onChange={e => setForm({ ...form, batiment: e.target.value })} />
                    )}
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Salle</label>
                    {refs.salles?.length > 0 ? (() => {
                      const batObj = refs.batiments?.find(b => b.nom === form.batiment)
                      const siteObj = refs.sites?.find(s => s.nom === form.site)
                      const filteredSalles = batObj
                        ? refs.salles.filter(s => s.batiment_id === batObj.id)
                        : siteObj
                          ? refs.salles.filter(s => s.site_id === siteObj.id)
                          : refs.salles
                      return (
                        <select className="form-control" value={form.salle}
                          onChange={e => setForm({ ...form, salle: e.target.value })}>
                          <option value="">-- Salle --</option>
                          {filteredSalles.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="form-control" value={form.salle}
                        onChange={e => setForm({ ...form, salle: e.target.value })} />
                    )}
                  </div>
                  <div className="form-group" />
                </div>

                <div className="form-group">
                  <label className="form-label">Volume horaire (h)</label>
                  <input type="number" className="form-control" min="0" step="0.5" value={form.duree_prevue_heures}
                    onChange={e => setForm({ ...form, duree_prevue_heures: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>
                  {saving ? 'Enregistrement...' : (editingModule ? 'Enregistrer' : 'Créer')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {confirmDialog && (
        <ConfirmModal
          message={confirmDialog.message}
          detail={confirmDialog.detail}
          onConfirm={() => { confirmDialog.onConfirm(); setConfirmDialog(null) }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {archiveTarget && (
        <TripleConfirmModal
          title="Archivage du module"
          subject={archiveTarget.module}
          onConfirm={confirmArchive}
          onCancel={() => setArchiveTarget(null)}
        />
      )}
    </div>
  )
}
