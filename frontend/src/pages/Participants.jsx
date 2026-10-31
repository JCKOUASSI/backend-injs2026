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
import '../styles/candidatures.css'
import '../styles/modale-premium.css'
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

  /* Retour à la liste complète : un seul geste plutôt que sept remises à zéro. */
  const reinitialiserFiltres = () => {
    setSearch('')
    setSexeFilter('')
    setSecretariatFilter('')
    setGradeFilter('')
    setGroupeFilter('')
    setTypeConcoursFilter('')
    setVagueFilter('')
    setPage(1)
  }

  /* Nombre de filtres réellement posés : sert de repère dans l'en-tête du
     panneau, l'utilisateur n'a pas à recompter les listes déroulantes. */
  const filtresActifs = [sexeFilter, secretariatFilter, gradeFilter, groupeFilter,
    typeConcoursFilter, vagueFilter].filter(Boolean).length

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
    <div className="cand-page">
      {/* ── Bandeau d'accueil, même matière que les autres écrans Scolarité ── */}
      <div className="cand-hero">
        <div className="cand-hero-identite">
          <span className="cand-hero-icone" aria-hidden="true">
            <i className="bi bi-people"></i>
          </span>
          <div className="cand-hero-text">
            <span className="cand-hero-badge">Scolarité — Étudiants</span>
            <h1 className="cand-hero-title">Étudiants</h1>
            <p className="cand-hero-sub">Registre, recherche et filtres des étudiants</p>
          </div>
        </div>
        <div className="camp-pastilles">
          <span className="cand-count-pill">
            <i className="bi bi-person-badge" aria-hidden="true"></i>
            {totalCount} étudiant{totalCount > 1 ? 's' : ''}
          </span>
        </div>
      </div>

      {/* ── Recherche, filtres et actions ── */}
      <section className="cand-panel" aria-labelledby="titre-filtres-etudiants">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-filtres-etudiants">
            <i className="bi bi-funnel" aria-hidden="true"></i>Recherche et filtres
          </h2>
          {filtresActifs > 0 && (
            <span className="cand-count-pill">
              <i className="bi bi-sliders" aria-hidden="true"></i>
              {filtresActifs} filtre{filtresActifs > 1 ? 's' : ''} actif{filtresActifs > 1 ? 's' : ''}
            </span>
          )}
        </header>
        <div className="cand-panel-body">
          <div className="cand-filters etud-filtres">
            <div className="cand-search etud-recherche">
              <i className="bi bi-search"></i>
              <input
                type="search" className="cand-input"
                placeholder="Nom, prénom, matricule, e-mail, concours…"
                aria-label="Rechercher un étudiant"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              />
            </div>
            <div className="etud-filtre">
              <select className="cand-filter-select" aria-label="Filtrer par secrétariat" value={secretariatFilter}
                onChange={(e) => { setSecretariatFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (secrétariat)</option>
                {filterOptions.secretariats.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </div>
            <div className="etud-filtre">
              <select className="cand-filter-select" aria-label="Filtrer par grade" value={gradeFilter}
                onChange={(e) => { setGradeFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (grade)</option>
                {filterOptions.grades.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            <div className="etud-filtre">
              <select className="cand-filter-select" aria-label="Filtrer par groupe" value={groupeFilter}
                onChange={(e) => { setGroupeFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (groupe)</option>
                {filterOptions.groupes.map((g) => (
                  <option key={g} value={g}>{g}</option>
                ))}
              </select>
            </div>
            <div className="etud-filtre">
              <select className="cand-filter-select" aria-label="Filtrer par type de concours" value={typeConcoursFilter}
                onChange={(e) => { setTypeConcoursFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (type concours)</option>
                {filterOptions.types_concours.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
            </div>
            <div className="etud-filtre">
              <select className="cand-filter-select" aria-label="Filtrer par sexe" value={sexeFilter}
                onChange={(e) => { setSexeFilter(e.target.value); setPage(1) }}>
                <option value="">Tous (sexe)</option>
                <option value="MASCULIN">Masculin</option>
                <option value="FEMININ">Féminin</option>
              </select>
            </div>
            {refs.vagues && refs.vagues.length > 0 && (
              <div className="etud-filtre">
                <select className="cand-filter-select" aria-label="Filtrer par vague" value={vagueFilter}
                  onChange={(e) => { setVagueFilter(e.target.value); setPage(1) }}>
                  <option value="">Toutes les vagues</option>
                  {refs.vagues.map(v => (
                    <option key={v.id} value={v.libelle}>{v.libelle}</option>
                  ))}
                </select>
              </div>
            )}
          </div>

          <div className="etud-actions">
            {canCreate && (
              <button type="button" onClick={openCreate} className="cand-btn-principal">
                <i className="bi bi-plus-lg" aria-hidden="true"></i>
                Nouvel étudiant
              </button>
            )}
            {canExportListeClasse && (
              <>
                <button
                  type="button"
                  className="cand-btn-fantome etud-btn-export etud-btn-export--pdf"
                  disabled={exportingListeClasse}
                  onClick={() => handleExportListeClasse('pdf')}
                  title={groupeFilter ? `Liste de classe PDF — ${groupeFilter}` : 'Liste de classe PDF — tous les groupes'}
                >
                  <i className="bi bi-file-earmark-pdf" aria-hidden="true"></i>
                  {groupeFilter ? 'Liste de classe PDF' : 'Listes de classe PDF'}
                </button>
                <button
                  type="button"
                  className="cand-btn-fantome etud-btn-export etud-btn-export--excel"
                  disabled={exportingListeClasse}
                  onClick={() => handleExportListeClasse('excel')}
                  title={groupeFilter ? `Liste de classe Excel — ${groupeFilter}` : 'Liste de classe Excel — tous les groupes'}
                >
                  <i className="bi bi-file-earmark-excel" aria-hidden="true"></i>
                  {groupeFilter ? 'Liste de classe Excel' : 'Listes de classe Excel'}
                </button>
              </>
            )}
            {(filtresActifs > 0 || search) && (
              <button type="button" className="cand-btn-fantome etud-btn-reset" onClick={reinitialiserFiltres}>
                <i className="bi bi-x-circle" aria-hidden="true"></i>
                Réinitialiser
              </button>
            )}
          </div>
        </div>
      </section>

      {error && <div className="cand-alerte" role="alert">{error}</div>}

      {/* ── Registre ── */}
      <section className="cand-panel" aria-labelledby="titre-liste-etudiants">
        <header className="cand-panel-head">
          <h2 className="cand-panel-title" id="titre-liste-etudiants">
            <i className="bi bi-person-lines-fill" aria-hidden="true"></i>Liste des étudiants
          </h2>
          <span className="cand-count-pill">{totalCount} résultat(s)</span>
        </header>
        <div className="cand-panel-body">
          {loading ? (
            <div className="cand-chargement">
              <span className="spinner-border" aria-hidden="true"></span>Chargement des étudiants…
            </div>
          ) : (
            <>
              <div className="cand-table-wrap">
                <table className="cand-table cand-table--etudiants">
                  <thead>
                    <tr>
                      <th scope="col">N° d&apos;inscription</th>
                      <th scope="col">Nom &amp; Prénom</th>
                      <th scope="col">Sexe</th>
                      <th scope="col">Grade</th>
                      <th scope="col">Téléphone</th>
                      <th scope="col" className="cand-th-actions">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {participants.length > 0 ? participants.map((p) => (
                      <tr key={p.id}>
                        <td className="cand-col-etroit">
                          {p.matricule
                            ? <span className="cand-numero">{p.matricule}</span>
                            : <span className="cand-texte-doux">-</span>}
                        </td>
                        <td className="etud-col-identite">
                          <span className="cand-etudiant">{p.nom} {p.prenom}</span>
                          {p.secretariat && (
                            <span className="etud-sous">
                              <i className="bi bi-geo-alt" aria-hidden="true"></i>{p.secretariat}
                            </span>
                          )}
                        </td>
                        <td>
                          {p.sexe
                            ? (
                              <span className={`etud-sexe etud-sexe--${p.sexe === 'FEMININ' ? 'f' : 'm'}`}>
                                <i className={`bi ${p.sexe === 'FEMININ' ? 'bi-gender-female' : 'bi-gender-male'}`} aria-hidden="true"></i>
                                {sexeLabel(p.sexe)}
                              </span>
                            )
                            : <span className="cand-texte-doux">-</span>}
                        </td>
                        <td>
                          {p.grade
                            ? <span className="cand-badge-neutre">{p.grade}</span>
                            : <span className="cand-texte-doux">-</span>}
                        </td>
                        <td>
                          {p.telephone
                            ? <span className="etud-tel">{p.telephone}</span>
                            : <span className="cand-texte-doux">-</span>}
                        </td>
                        <td className="cand-col-actions">
                          <div className="cand-actions">
                            <button
                              type="button" onClick={() => setShowDetail(p)}
                              className="cand-action cand-action--ouvrir" title="Visualiser"
                              aria-label={`Visualiser ${p.nom} ${p.prenom}`}
                            >
                              <i className="bi bi-eye" aria-hidden="true"></i>
                            </button>
                            {canManage && (
                              <button
                                type="button" onClick={() => openEdit(p)}
                                className="cand-action" title="Modifier"
                                aria-label={`Modifier ${p.nom} ${p.prenom}`}
                              >
                                <i className="bi bi-pencil" aria-hidden="true"></i>
                              </button>
                            )}
                            {canManage && (
                              <button
                                type="button" onClick={() => handleDelete(p.id)}
                                className="cand-action cand-action--danger" title="Supprimer"
                                aria-label={`Supprimer ${p.nom} ${p.prenom}`}
                              >
                                <i className="bi bi-trash" aria-hidden="true"></i>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    )) : (
                      <tr>
                        <td colSpan="6">
                          <div className="cand-vide">
                            <span className="cand-vide-icone" aria-hidden="true">
                              <i className="bi bi-person-x"></i>
                            </span>
                            <p className="cand-vide-titre">Aucun étudiant trouvé</p>
                            <p className="cand-vide-texte">
                              Aucun étudiant ne correspond à la recherche ou aux filtres sélectionnés.
                            </p>
                          </div>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="cand-defile" aria-hidden="true">
                <i className="bi bi-arrow-left-right"></i>
                Faites défiler le tableau horizontalement
              </p>
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
      </section>

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
          <div className="modal-content etud-modale" style={{ maxWidth: '720px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="etud-modale-titre">
                <i className="bi bi-person-plus" aria-hidden="true"></i>
                {editingId ? "Modifier l'étudiant" : 'Nouvel étudiant'}
              </h2>
              <button type="button" className="mp-fermer" onClick={() => setShowModal(false)} aria-label="Fermer">
                <span className="etud-fermer-glyphe" aria-hidden="true">×</span>
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body etud-modale-corps" style={{ maxHeight: '75vh', overflowY: 'auto' }}>
                {formError && <div className="cand-alerte" role="alert" style={{ whiteSpace: 'pre-line' }}>{formError}</div>}

                <h3 className="cand-section-titre">
                  <i className="bi bi-person-vcard" aria-hidden="true"></i>Identité
                </h3>
                <div className="etud-form">
                  <div className="cand-champ form-group etud-plein">
                    <label className="cand-etiquette">N° d&apos;inscription *</label>
                    <input
                      type="text" className="cand-saisie" placeholder="Ex : P0042" required
                      value={form.matricule} onChange={f('matricule')}
                    />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Nom *</label>
                    <input type="text" className="cand-saisie" required value={form.nom} onChange={f('nom')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Prénom *</label>
                    <input type="text" className="cand-saisie" required value={form.prenom} onChange={f('prenom')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Sexe</label>
                    <select className="cand-saisie" value={form.sexe} onChange={f('sexe')}>
                      <option value="">-- Sélectionner --</option>
                      <option value="MASCULIN">Masculin</option>
                      <option value="FEMININ">Féminin</option>
                    </select>
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Date de naissance</label>
                    <input type="date" className="cand-saisie" value={form.date_naissance} onChange={f('date_naissance')} />
                  </div>
                  <div className="cand-champ form-group etud-plein">
                    <label className="cand-etiquette">Lieu de naissance</label>
                    <input type="text" className="cand-saisie" value={form.lieu_naissance} onChange={f('lieu_naissance')} />
                  </div>
                </div>

                <h3 className="cand-section-titre">
                  <i className="bi bi-telephone" aria-hidden="true"></i>Coordonnées
                </h3>
                <div className="etud-form">
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Adresse e-mail</label>
                    <input type="email" className="cand-saisie" value={form.email} onChange={f('email')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Téléphone 1</label>
                    <input type="text" className="cand-saisie" value={form.telephone} onChange={f('telephone')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Téléphone 2</label>
                    <input type="text" className="cand-saisie" value={form.telephone2} onChange={f('telephone2')} />
                  </div>
                </div>

                <h3 className="cand-section-titre">
                  <i className="bi bi-trophy" aria-hidden="true"></i>Concours
                </h3>
                <div className="etud-form">
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Type concours</label>
                    <input type="text" className="cand-saisie" value={form.type_concours} onChange={f('type_concours')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Libellé concours</label>
                    <input type="text" className="cand-saisie" value={form.libelle_concours} onChange={f('libelle_concours')} />
                  </div>
                </div>

                <h3 className="cand-section-titre">
                  <i className="bi bi-clipboard-data" aria-hidden="true"></i>Administratif
                </h3>
                <div className="etud-form">
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Catégorie</label>
                    {refs.categories.length > 0 ? (
                      <select className="cand-saisie" value={form.categorie}
                        onChange={e => setForm(prev => ({ ...prev, categorie: e.target.value, grade: '' }))}>
                        <option value="">-- Choisir --</option>
                        {refs.categories.map(c => <option key={c.id} value={c.libelle}>{c.libelle}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="cand-saisie" placeholder="A, B, C…" value={form.categorie} onChange={f('categorie')} />
                    )}
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Grade</label>
                    {refs.grades.length > 0 ? (() => {
                      const catObj = refs.categories.find(c => c.libelle === form.categorie)
                      const filteredGrades = catObj
                        ? refs.grades.filter(g => g.categorie_id === catObj.id)
                        : refs.grades
                      return (
                        <select className="cand-saisie" value={form.grade}
                          onChange={e => setForm(prev => ({ ...prev, grade: e.target.value }))}>
                          <option value="">-- Choisir --</option>
                          {filteredGrades.map(g => <option key={g.id} value={g.libelle}>{g.libelle}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="cand-saisie" value={form.grade} onChange={f('grade')} />
                    )}
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Groupe</label>
                    <input type="text" className="cand-saisie" value={form.groupe} onChange={f('groupe')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Grade-Groupe</label>
                    <input type="text" className="cand-saisie" value={form.grade_groupe} onChange={f('grade_groupe')} />
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Vague</label>
                    {refs.vagues && refs.vagues.length > 0 ? (
                      <select className="cand-saisie" value={form.vague} onChange={f('vague')}>
                        <option value="">-- Choisir --</option>
                        {refs.vagues.map(v => <option key={v.id} value={v.libelle}>{v.libelle}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="cand-saisie" value={form.vague} onChange={f('vague')} />
                    )}
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Site</label>
                    {refs.sites && refs.sites.length > 0 ? (
                      <select className="cand-saisie" value={form.site}
                        onChange={e => setForm(prev => ({ ...prev, site: e.target.value, salle: '' }))}>
                        <option value="">-- Choisir --</option>
                        {refs.sites.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="cand-saisie" value={form.site} onChange={f('site')} />
                    )}
                  </div>
                  <div className="cand-champ form-group">
                    <label className="cand-etiquette">Salle</label>
                    {refs.salles && refs.salles.length > 0 ? (() => {
                      const siteObj = refs.sites && refs.sites.find(s => s.nom === form.site)
                      const filteredSalles = siteObj
                        ? refs.salles.filter(s => s.site_id === siteObj.id)
                        : refs.salles
                      return (
                        <select className="cand-saisie" value={form.salle}
                          onChange={e => setForm(prev => ({ ...prev, salle: e.target.value }))}>
                          <option value="">-- Choisir --</option>
                          {filteredSalles.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="cand-saisie" value={form.salle} onChange={f('salle')} />
                    )}
                  </div>
                </div>
              </div>
              <div className="modal-footer etud-modale-pied">
                <button type="button" className="cand-btn-fantome" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="cand-btn-principal" disabled={saving}>
                  {saving
                    ? 'Enregistrement…'
                    : (
                      <>
                        <i className="bi bi-check2" aria-hidden="true"></i>
                        {editingId ? 'Enregistrer' : 'Créer'}
                      </>
                    )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
