import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import ConfirmModal from '../components/ConfirmModal'
import { useReferentiels } from '../hooks/useReferentiels'
import { useToast } from '../context/ToastContext'
import { useDebounce } from '../hooks/useDebounce'
import {
  buildParticipantsSearchParams,
  LIST_STORAGE_KEYS,
  parseListPage,
  readParticipantsFilters,
} from '../utils/listFilters'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import { canCreateParticipant, canManageParticipant, canViewPresences as canViewPresencesRole, peut } from '../utils/roles'
import Pagination from '../components/Pagination'
import { parsePaginatedResponse } from '../utils/paginatedResponse'
import ParticipantDetailModal from '../components/ParticipantDetailModal'
import '../styles/campagnes.css'

const emptyForm = {
  matricule: '',
  nom: '', prenom: '', sexe: '', date_naissance: '', lieu_naissance: '',
  email: '',
  telephone: '', telephone2: '',
  type_concours: '', libelle_concours: '',
  categorie: '', grade: '', groupe: '', grade_groupe: '',
  vague: '',
  site: '', salle: '',
}
const emptyRefs = { categories: [], grades: [], sites: [], salles: [], vagues: [] }

export default function Participants() {
  const { user } = useAuth()
  const [searchParams] = useSearchParams()
  const initialFilters = readParticipantsFilters(searchParams)
  const [participants, setParticipants] = useState([])
  const [refs, setRefs] = useState(emptyRefs)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [page, setPage] = useState(() => parseListPage(searchParams))
  const [totalPages, setTotalPages] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [search, setSearch] = useState(initialFilters.search)
  const [sexeFilter, setSexeFilter] = useState(initialFilters.sexe)
  const [secretariatFilter, setSecretariatFilter] = useState(initialFilters.secretariat)
  const [gradeFilter, setGradeFilter] = useState(initialFilters.grade)
  const [groupeFilter, setGroupeFilter] = useState(initialFilters.groupe)
  const [typeConcoursFilter, setTypeConcoursFilter] = useState(initialFilters.type_concours)
  const [vagueFilter, setVagueFilter] = useState(initialFilters.vague)
  const [filterOptions, setFilterOptions] = useState({ secretariats: [], grades: [], groupes: [], types_concours: [] })
  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState({ ...emptyForm })
  const [formError, setFormError] = useState('')
  const { data: referentielsData } = useReferentiels()
  useEffect(() => {
    if (referentielsData) setRefs(referentielsData)
  }, [referentielsData])
  const [saving, setSaving] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const { showToast } = useToast()
  const [showDetail, setShowDetail] = useState(null)
  const [detailFormations, setDetailFormations] = useState([])
  const [detailFormationsLoading, setDetailFormationsLoading] = useState(false)
  const [detailPointages, setDetailPointages] = useState([])
  const [detailStats, setDetailStats] = useState(null)
  const [detailNotesFiche, setDetailNotesFiche] = useState(null)
  const [detailPointagesLoading, setDetailPointagesLoading] = useState(false)
  const [exportingListeClasse, setExportingListeClasse] = useState(false)

  const debouncedSearch = useDebounce(search)

  usePersistedListQuery(
    LIST_STORAGE_KEYS.participants,
    () => buildParticipantsSearchParams(
      {
        sexe: sexeFilter,
        secretariat: secretariatFilter,
        grade: gradeFilter,
        groupe: groupeFilter,
        type_concours: typeConcoursFilter,
        vague: vagueFilter,
      },
      page,
      debouncedSearch,
    ),
    [
      page,
      debouncedSearch,
      sexeFilter,
      secretariatFilter,
      gradeFilter,
      groupeFilter,
      typeConcoursFilter,
      vagueFilter,
    ],
  )

  useEffect(() => {
    loadParticipants()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [
    page,
    debouncedSearch,
    sexeFilter,
    secretariatFilter,
    gradeFilter,
    groupeFilter,
    typeConcoursFilter,
    vagueFilter,
  ])

  const canViewPresences = canViewPresencesRole(user)

  useEffect(() => {
    if (!showDetail) {
      setDetailFormations([])
      setDetailPointages([])
      setDetailStats(null)
      setDetailNotesFiche(null)
      return
    }
    if (canViewPresences) {
      setDetailFormationsLoading(true)
      setDetailPointagesLoading(true)
      api.get(`/participant/${showDetail.id}/fiche-admin/`)
        .then(res => {
          setDetailFormations(res.data.modules || [])
          setDetailPointages(res.data.pointages || [])
          setDetailStats(res.data.stats || null)
          setDetailNotesFiche(res.data.notes_fiche || null)
        })
        .catch(() => {
          setDetailFormations([])
          setDetailPointages([])
          setDetailStats(null)
          setDetailNotesFiche(null)
        })
        .finally(() => {
          setDetailFormationsLoading(false)
          setDetailPointagesLoading(false)
        })
    } else {
      setDetailFormationsLoading(true)
      api.get(`/formations/participants/${showDetail.id}/formations/`)
        .then(res => setDetailFormations(Array.isArray(res.data) ? res.data : (res.data.results || [])))
        .catch(() => setDetailFormations([]))
        .finally(() => setDetailFormationsLoading(false))
    }
  }, [showDetail, canViewPresences])

  const loadParticipants = async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams({ page })
      if (debouncedSearch) params.set('search', debouncedSearch)
      if (sexeFilter) params.set('sexe', sexeFilter)
      if (secretariatFilter) params.set('secretariat', secretariatFilter)
      if (gradeFilter) params.set('grade', gradeFilter)
      if (groupeFilter) params.set('groupe', groupeFilter)
      if (typeConcoursFilter) params.set('type_concours', typeConcoursFilter)
      if (vagueFilter) params.set('vague', vagueFilter)
      const response = await api.get(`/formations/participants/list/?${params}`)
      const { results, count, totalPages: pages } = parsePaginatedResponse(response.data, 50)
      setParticipants(results)
      setTotalPages(pages)
      setTotalCount(count)
      const payload = Array.isArray(response.data) ? {} : response.data
      setFilterOptions(payload.filter_options || { secretariats: [], grades: [], groupes: [], types_concours: [] })
    } catch (err) {
      setError('Erreur lors du chargement des étudiants')
      console.error(err)
    } finally { setLoading(false) }
  }

  const f = (key) => (e) => setForm({ ...form, [key]: e.target.value })

  const openCreate = () => {
    setEditingId(null)
    setForm({ ...emptyForm })
    setFormError('')
    setShowModal(true)
  }

  const openEdit = (p) => {
    setEditingId(p.id)
    setForm({
      matricule: p.matricule || '',
      nom: p.nom || '',
      prenom: p.prenom || '',
      sexe: p.sexe || '',
      date_naissance: p.date_naissance || '',
      lieu_naissance: p.lieu_naissance || '',
      email: p.email || '',
      telephone: p.telephone || '',
      telephone2: p.telephone2 || '',
      type_concours: p.type_concours || '',
      libelle_concours: p.libelle_concours || '',
      categorie: p.categorie || '',
      grade: p.grade || '',
      groupe: p.groupe || '',
      grade_groupe: p.grade_groupe || '',
      vague: p.vague || '',
      site: p.site || '',
      salle: p.salle || '',
    })
    setFormError('')
    setShowModal(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      const payload = { ...form }
      if (!payload.date_naissance) delete payload.date_naissance
      if (editingId) {
        await api.patch(`/formations/participants/${editingId}/`, payload)
      } else {
        await api.post('/formations/participants/', payload)
      }
      setShowModal(false)
      loadParticipants()
      showToast(editingId ? 'Étudiant modifié' : 'Étudiant créé')
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const msgs = Object.entries(data).map(([k, v]) => `${k} : ${Array.isArray(v) ? v.join(', ') : v}`)
        setFormError(msgs.join('\n'))
      } else {
        setFormError('Erreur lors de la sauvegarde')
      }
    } finally { setSaving(false) }
  }

  const handleDelete = (id) => {
    setConfirmDialog({
      message: 'Supprimer cet étudiant ?',
      detail: 'Cette action est définitive.',
      onConfirm: async () => {
        try { await api.delete(`/formations/participants/${id}/`); loadParticipants(); showToast('Étudiant supprimé') }
        catch { showToast('Erreur lors de la suppression', 'error') }
      }
    })
  }

  const sexeLabel = (s) => ({ MASCULIN: 'Masculin', FEMININ: 'Féminin' }[s] || '-')
  const sexeBadge = (s) => s === 'MASCULIN' ? 'badge-bg-info' : s === 'FEMININ' ? 'badge-bg-warning' : ''

  const canManage = canManageParticipant(user)
  const canCreate = canCreateParticipant(user)
  const canExportListeClasse = peut(user, 'exports', 'liste_classe')

  const buildListeClasseQuery = () => {
    const params = new URLSearchParams()
    if (debouncedSearch) params.set('search', debouncedSearch)
    if (secretariatFilter) params.set('secretariat', secretariatFilter)
    if (gradeFilter) params.set('grade', gradeFilter)
    if (groupeFilter) params.set('groupe', groupeFilter)
    if (typeConcoursFilter) params.set('type_concours', typeConcoursFilter)
    if (vagueFilter) params.set('vague', vagueFilter)
    if (sexeFilter) params.set('sexe', sexeFilter)
    return params.toString()
  }

  const handleExportListeClasse = async (fmt) => {
    setExportingListeClasse(true)
    try {
      const qs = buildListeClasseQuery()
      const path = `/exports/participants/liste-classe/${fmt}/${qs ? `?${qs}` : ''}`
      const { blob, fileName } = await api.getBlob(path)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || `liste_classe.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      showToast(groupeFilter
        ? `Liste de classe exportée (${fmt.toUpperCase()}) — ${groupeFilter}`
        : `Listes de classe exportées (${fmt.toUpperCase()}) — tous les groupes`)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur export liste de classe', 'error')
    } finally {
      setExportingListeClasse(false)
    }
  }

  return (
    <div className="camp-page">
      {/* Hero premium */}
      <div className="camp-hero">
        <div className="camp-hero-text">
          <h1 className="camp-hero-title"><i className="bi bi-people"></i>Étudiants</h1>
          <p className="camp-hero-sub">Registre des étudiants · recherche, filtres par secrétariat, grade, groupe, concours, sexe et vague.</p>
        </div>
        <div className="camp-hero-side">
          <span className="plaquette plaquette-soft"><i className="bi bi-list-ul"></i>{totalCount} étudiant{totalCount > 1 ? 's' : ''}</span>
        </div>
      </div>

      {/* Search + Filter bar */}
      <div className="camp-panel card">
        <div className="camp-panel-body">
          <div className="parti-filters">
            <div className="camp-search parti-search">
              <i className="bi bi-search"></i>
              <input type="text" className="form-control" placeholder="Nom, prénom, matricule, e-mail, concours…"
                value={search} onChange={(e) => { setSearch(e.target.value); setPage(1) }} />
            </div>
            <div className="parti-filter">
              <select className="form-select camp-filter-select w-100" value={secretariatFilter}
                onChange={(e) => { setSecretariatFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (secrétariat)</option>
                {filterOptions.secretariats.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="parti-filter">
              <select className="form-select camp-filter-select w-100" value={gradeFilter}
                onChange={(e) => { setGradeFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (grade)</option>
                {filterOptions.grades.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            <div className="parti-filter">
              <select className="form-select camp-filter-select w-100" value={groupeFilter}
                onChange={(e) => { setGroupeFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (groupe)</option>
                {filterOptions.groupes.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            <div className="parti-filter">
              <select className="form-select camp-filter-select w-100" value={typeConcoursFilter}
                onChange={(e) => { setTypeConcoursFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (type concours)</option>
                {filterOptions.types_concours.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="parti-filter">
              <select className="form-select camp-filter-select w-100" value={sexeFilter}
                onChange={(e) => { setSexeFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (sexe)</option>
                <option value="MASCULIN">Masculin</option>
                <option value="FEMININ">Féminin</option>
              </select>
            </div>
            {refs.vagues && refs.vagues.length > 0 && (
              <div className="parti-filter">
                <select className="form-select camp-filter-select w-100" value={vagueFilter}
                  onChange={(e) => { setVagueFilter(e.target.value); setPage(1) }}>
                  <option value="">Toutes les vagues</option>
                  {refs.vagues.map(v => (
                    <option key={v.id} value={v.libelle}>{v.libelle}</option>
                  ))}
                </select>
              </div>
            )}
            {canCreate && (
              <button onClick={openCreate} className="camp-submit-btn btn btn-primary btn-sm">
                <i className="bi bi-plus-lg me-1"></i>Nouvel étudiant
              </button>
            )}
            {canExportListeClasse && (
              <>
                <button
                  type="button"
                  className="btn btn-outline-danger btn-sm camp-action-btn"
                  disabled={exportingListeClasse}
                  onClick={() => handleExportListeClasse('pdf')}
                  title={groupeFilter ? `Liste de classe PDF — ${groupeFilter}` : 'Liste de classe PDF — tous les groupes'}
                >
                  <i className="bi bi-file-earmark-pdf me-1"></i>
                  {groupeFilter ? 'Liste de classe PDF' : 'Listes de classe PDF'}
                </button>
                <button
                  type="button"
                  className="btn btn-outline-success btn-sm camp-action-btn"
                  disabled={exportingListeClasse}
                  onClick={() => handleExportListeClasse('excel')}
                  title={groupeFilter ? `Liste de classe Excel — ${groupeFilter}` : 'Liste de classe Excel — tous les groupes'}
                >
                  <i className="bi bi-file-earmark-excel me-1"></i>
                  {groupeFilter ? 'Liste de classe Excel' : 'Listes de classe Excel'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      {/* Table */}
      <div className="camp-panel card">
        <div className="camp-panel-head">
          <h2 className="camp-panel-title"><i className="bi bi-people"></i>Liste des étudiants</h2>
          <span className="camp-count-pill">{totalCount} résultat(s)</span>
        </div>
        <div className="camp-panel-body">
          {loading ? <div className="loading"><div className="spinner"></div></div> : (
            <>
              <div className="table-responsive">
                <table className="table table-hover align-middle mb-0 camp-table">
                  <thead className="table-light">
                    <tr>
                      <th>N° d'inscription</th>
                      <th>Nom &amp; Prénom</th>
                      <th>Sexe</th>
                      <th>Grade</th>
                      <th>Téléphone</th>
                      <th className="text-end">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {participants.length > 0 ? participants.map((p) => (
                      <tr key={p.id}>
                        <td><span className="camp-candidatures">{p.matricule || '-'}</span></td>
                        <td>
                          <span className="camp-link">{p.nom} {p.prenom}</span>
                          </td>
                        <td>
                          {p.sexe
                            ? <span className={sexeBadge(p.sexe)}>{sexeLabel(p.sexe)}</span>
                            : <span className="text-muted">-</span>}
                        </td>
                        <td>{p.grade || '-'}</td>
                        <td><small className="text-muted">{p.telephone || '-'}</small></td>
                        <td className="text-end">
                          <div className="btn-group btn-group-sm">
                            <button onClick={() => setShowDetail(p)} className="btn btn-outline-secondary camp-action-btn" title="Visualiser">
                              <i className="bi bi-eye me-1"></i>Visualiser
                            </button>
                            {canManage && (
                              <button onClick={() => openEdit(p)} className="btn btn-outline-primary camp-action-btn" title="Modifier">
                                <i className="bi bi-pencil me-1"></i>Modifier
                              </button>
                            )}
                            {canManage && (
                              <button onClick={() => handleDelete(p.id)} className="btn btn-outline-danger camp-action-btn" title="Supprimer">
                                <i className="bi bi-trash me-1"></i>Supprimer
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr><td colSpan="6"><div className="camp-empty"><i className="bi bi-inbox"></i>Aucun étudiant trouvé</div></td></tr>
                    )}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                totalItems={totalCount}
                pageSize={50}
              />
            </>
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

      {/* Detail Modal */}
      {showDetail && (
        <ParticipantDetailModal
          participant={showDetail}
          modules={detailFormations}
          pointages={detailPointages}
          stats={detailStats}
          initialNotesFiche={detailNotesFiche}
          onClose={() => setShowDetail(null)}
          loading={detailFormationsLoading || detailPointagesLoading}
          canManageNotes={peut(user, 'notes', 'gerer')}
        />
      )}

      {/* Create / Edit Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" style={{ maxWidth: '680px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-plus me-2"></i>{editingId ? "Modifier l'étudiant" : 'Nouvel étudiant'}</h5>
              <button className="btn-close" onClick={() => setShowModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body" style={{ maxHeight: '75vh', overflowY: 'auto' }}>
                {formError && <div className="alert alert-danger" style={{ whiteSpace: 'pre-line' }}>{formError}</div>}

                {/* Identité */}
                <p className="text-muted small" style={{ fontWeight: 600, marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Identité</p>
                <div className="form-group">
                  <label className="form-label">N° d'inscription *</label>
                  <input
                    type="text"
                    className="form-control"
                    placeholder="Ex : P0042"
                    required
                    value={form.matricule}
                    onChange={f('matricule')}
                  />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Nom *</label>
                    <input type="text" className="form-control" required value={form.nom} onChange={f('nom')} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Prénom *</label>
                    <input type="text" className="form-control" required value={form.prenom} onChange={f('prenom')} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Sexe</label>
                    <select className="form-control" value={form.sexe} onChange={f('sexe')}>
                      <option value="">-- Sélectionner --</option>
                      <option value="MASCULIN">Masculin</option>
                      <option value="FEMININ">Féminin</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Date de naissance</label>
                    <input type="date" className="form-control" value={form.date_naissance} onChange={f('date_naissance')} />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">Lieu de naissance</label>
                  <input type="text" className="form-control" value={form.lieu_naissance} onChange={f('lieu_naissance')} />
                </div>

                {/* Coordonnées */}
                <p className="text-muted small" style={{ fontWeight: 600, margin: '1rem 0 0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Coordonnées</p>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Adresse e-mail</label>
                    <input type="email" className="form-control" value={form.email} onChange={f('email')} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Téléphone 1</label>
                    <input type="text" className="form-control" value={form.telephone} onChange={f('telephone')} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Téléphone 2</label>
                    <input type="text" className="form-control" value={form.telephone2} onChange={f('telephone2')} />
                  </div>
                </div>

                {/* Concours */}
                <p className="text-muted small" style={{ fontWeight: 600, margin: '1rem 0 0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Concours</p>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Type concours</label>
                    <input type="text" className="form-control" value={form.type_concours} onChange={f('type_concours')} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Libellé concours</label>
                    <input type="text" className="form-control" value={form.libelle_concours} onChange={f('libelle_concours')} />
                  </div>
                </div>

                {/* Administratif */}
                <p className="text-muted small" style={{ fontWeight: 600, margin: '1rem 0 0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Administratif</p>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Catégorie</label>
                    {refs.categories.length > 0 ? (
                      <select className="form-control" value={form.categorie}
                        onChange={e => setForm(prev => ({ ...prev, categorie: e.target.value, grade: '' }))}>
                        <option value="">-- Choisir --</option>
                        {refs.categories.map(c => <option key={c.id} value={c.libelle}>{c.libelle}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="form-control" placeholder="A, B, C…" value={form.categorie} onChange={f('categorie')} />
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Grade</label>
                    {refs.grades.length > 0 ? (() => {
                      const catObj = refs.categories.find(c => c.libelle === form.categorie)
                      const filteredGrades = catObj
                        ? refs.grades.filter(g => g.categorie_id === catObj.id)
                        : refs.grades
                      return (
                        <select className="form-control" value={form.grade}
                          onChange={e => setForm(prev => ({ ...prev, grade: e.target.value }))}>
                          <option value="">-- Choisir --</option>
                          {filteredGrades.map(g => <option key={g.id} value={g.libelle}>{g.libelle}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="form-control" value={form.grade} onChange={f('grade')} />
                    )}
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Groupe</label>
                    <input type="text" className="form-control" value={form.groupe} onChange={f('groupe')} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Grade-Groupe</label>
                    <input type="text" className="form-control" value={form.grade_groupe} onChange={f('grade_groupe')} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Vague</label>
                    {refs.vagues && refs.vagues.length > 0 ? (
                      <select className="form-control" value={form.vague} onChange={f('vague')}>
                        <option value="">-- Choisir --</option>
                        {refs.vagues.map(v => <option key={v.id} value={v.libelle}>{v.libelle}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="form-control" value={form.vague} onChange={f('vague')} />
                    )}
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Site</label>
                    {refs.sites && refs.sites.length > 0 ? (
                      <select className="form-control" value={form.site}
                        onChange={e => setForm(prev => ({ ...prev, site: e.target.value, salle: '' }))}>
                        <option value="">-- Choisir --</option>
                        {refs.sites.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="form-control" value={form.site} onChange={f('site')} />
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Salle</label>
                    {refs.salles && refs.salles.length > 0 ? (() => {
                      const siteObj = refs.sites && refs.sites.find(s => s.nom === form.site)
                      const filteredSalles = siteObj
                        ? refs.salles.filter(s => s.site_id === siteObj.id)
                        : refs.salles
                      return (
                        <select className="form-control" value={form.salle}
                          onChange={e => setForm(prev => ({ ...prev, salle: e.target.value }))}>
                          <option value="">-- Choisir --</option>
                          {filteredSalles.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="form-control" value={form.salle} onChange={f('salle')} />
                    )}
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>
                  {saving ? 'Enregistrement…' : (editingId ? 'Enregistrer' : 'Créer')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
