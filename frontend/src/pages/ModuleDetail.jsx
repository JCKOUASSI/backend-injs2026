import { useState, useEffect, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import QRCodeModal from '../components/QRCodeModal'
import ConfirmModal from '../components/ConfirmModal'
import TripleConfirmModal from '../components/TripleConfirmModal'
import { useToast } from '../context/ToastContext'
import { formatDate } from '../utils/dates'
import { fmtHeuresLabel, fmtEdtVsObjectif, sessionDureeHeures, sommeSeancesHeures, sessionNumeroLabel, nextSessionNumeroForDate } from '../utils/duree'
import { LIST_STORAGE_KEYS } from '../utils/listFilters'
import { useListReturn } from '../hooks/useListReturn'
import { useClientPagination, TABLE_PAGE_SIZE, PICKER_PAGE_SIZE } from '../hooks/useClientPagination'
import { usePickerPagination } from '../hooks/usePickerPagination'
import Pagination from '../components/Pagination'
import { canMutateFormations, canArchiveModuleFromUser, canSuperviseSessions, hasAppRole, NOTE_GESTION_ROLES } from '../utils/roles'
import { formatApiErrors } from '../utils/apiErrors'
import FormateurAssignPickerItem from '../components/formateurs/FormateurAssignPickerItem'
import { useReferentiels } from '../hooks/useReferentiels'
import { useVisibilityPolling } from '../hooks/useVisibilityPolling'
import { useDebounce } from '../hooks/useDebounce'

const MODULE_PRESENCES_POLL_MS = 60 * 1000

export default function ModuleDetail() {
  const { formationId, moduleId } = useParams()
  const { user } = useAuth()
  const { showToast } = useToast()
  const backToModulesList = useListReturn('/modules', LIST_STORAGE_KEYS.modules)
  const canManageNotes = hasAppRole(user, NOTE_GESTION_ROLES)
  const canViewDecisions = hasAppRole(user, NOTE_GESTION_ROLES)

  const [module, setModule] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('seances')
  const [qrModalOpen, setQrModalOpen] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState(null)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [archiveOpen, setArchiveOpen] = useState(false)
  const [startingSession, setStartingSession] = useState(null)
  const [stoppingSession, setStoppingSession] = useState(null)
  const [editSession, setEditSession] = useState(null)
  const [editSessionForm, setEditSessionForm] = useState({ intitule: '', date_journee: '', heure_debut_prevue: '', heure_fin_prevue: '' })
  const [savingSession, setSavingSession] = useState(false)
  const [editModuleOpen, setEditModuleOpen] = useState(false)
  const [editModuleForm, setEditModuleForm] = useState({})
  const [savingModule, setSavingModule] = useState(false)

  // Superviseur (encadrant) assignment
  const [showAssignSup, setShowAssignSup] = useState(false)
  const [encadrants, setEncadrants] = useState([])
  const [selectedSup, setSelectedSup] = useState('')
  const [assignSupError, setAssignSupError] = useState('')
  const [assignSupSaving, setAssignSupSaving] = useState(false)
  const [encadrantSearch, setEncadrantSearch] = useState('')
  const [encadrantLoading, setEncadrantLoading] = useState(false)

  // Participants
  const [showAddParticipant, setShowAddParticipant] = useState(false)
  const [allParticipants, setAllParticipants] = useState([])
  const [participantSearch, setParticipantSearch] = useState('')
  const [participantLoading, setParticipantLoading] = useState(false)
  const [enrolledSearch, setEnrolledSearch] = useState('')

  // Formateurs
  const [showAddFormateur, setShowAddFormateur] = useState(false)
  const [allFormateurs, setAllFormateurs] = useState([])
  const [formateurSearch, setFormateurSearch] = useState('')
  const [formateurAssignError, setFormateurAssignError] = useState('')
  const [formateurLoading, setFormateurLoading] = useState(false)

  const participantsList = module?.participants ?? []
  const formateursList = module?.formateurs ?? []
  const debouncedEnrolledSearch = useDebounce(enrolledSearch)
  const filteredParticipants = participantsList.filter(p =>
    !debouncedEnrolledSearch ||
    `${p.nom} ${p.prenom}`.toLowerCase().includes(debouncedEnrolledSearch.toLowerCase()) ||
    (p.numero_matricule || p.matricule || '').toLowerCase().includes(debouncedEnrolledSearch.toLowerCase())
  )
  const participantsPager = useClientPagination(filteredParticipants, TABLE_PAGE_SIZE, [moduleId, debouncedEnrolledSearch])
  const formateursPager = useClientPagination(formateursList, TABLE_PAGE_SIZE, [moduleId, formateursList.length])
  const participantPicker = usePickerPagination(showAddParticipant)
  const formateurPicker = usePickerPagination(showAddFormateur)
  const encadrantPicker = usePickerPagination(showAssignSup)

  // Séances
  const [showNewSession, setShowNewSession] = useState(false)
  const [newSessionForm, setNewSessionForm] = useState({ intitule: '', date_journee: '', heure_debut_prevue: '', heure_fin_prevue: '' })
  const [savingNewSession, setSavingNewSession] = useState(false)

  // Présences
  const [selectedPresenceDate, setSelectedPresenceDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [selectedPresenceSessionId, setSelectedPresenceSessionId] = useState('ALL')
  const [presenceSearch, setPresenceSearch] = useState('')

  // Forçage de badgeage
  const [forceModal, setForceModal] = useState(false)
  const [forceForm, setForceForm] = useState({ personne_id: '', type_personne: 'participant', action: 'ENTREE', motif: '' })
  const [forceSaving, setForceSaving] = useState(false)
  const [bulkForceModal, setBulkForceModal] = useState(false)
  const [bulkForceMotif, setBulkForceMotif] = useState('')
  const [bulkForceSaving, setBulkForceSaving] = useState(false)
  const [refs, setRefs] = useState({ sites: [], batiments: [], salles: [], vagues: [] })
  const { data: referentielsData } = useReferentiels()

  const canSupervise = canSuperviseSessions(user)
  const canManageSessions = canMutateFormations(user)
  const canManageModule = canMutateFormations(user)
  const canArchive = canArchiveModuleFromUser(user)

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { loadModule() }, [formationId, moduleId])
  useEffect(() => {
    setSelectedSessionId(null)
    setQrModalOpen(false)
  }, [moduleId])
  useEffect(() => {
    if (referentielsData) setRefs(referentielsData)
  }, [referentielsData])

  const refreshPresences = useCallback(async (silent = true) => {
    if (!formationId || !moduleId) return
    try {
      const res = await api.get(`/formations/${formationId}/modules/${moduleId}/presences/`)
      setModule(prev => prev ? { ...prev, presences: res.data.presences } : prev)
    } catch (err) {
      if (!silent) console.error('Rafraîchissement présences:', err)
    }
  }, [formationId, moduleId])

  useVisibilityPolling(refreshPresences, MODULE_PRESENCES_POLL_MS, activeTab === 'presences')

  const loadModule = async (silent = false) => {
    if (!formationId || !moduleId) {
      if (!silent) setError('Formation ou module introuvable dans l\'URL.')
      return
    }
    if (!silent) setLoading(true)
    try {
      const res = await api.get(`/formations/${formationId}/modules/${moduleId}/full/`)
      setModule(res.data)
    } catch (err) {
      console.error('Chargement module:', err)
      if (!silent) setError(formatApiErrors(err.response?.data, { fallback: 'Erreur lors du chargement du module.' }))
    } finally {
      if (!silent) setLoading(false)
    }
  }

  const getStatutBadge = (s) => ({ PLANIFIEE: 'badge-planifiee', EN_COURS: 'badge-en-cours', TERMINEE: 'badge-terminee' }[s] || 'badge-info')
  const getStatutLabel = (s) => ({ PLANIFIEE: 'Planifiée', EN_COURS: 'En cours', TERMINEE: 'Terminée' }[s] || s)

  const handleStartSession = (sid, label) => {
    setConfirmDialog({
      message: `Démarrer la séance « ${label} » ?`,
      detail: "Attention : la séance passera immédiatement en cours et les badgeages seront ouverts.",
      onConfirm: async () => {
        setStartingSession(sid)
        try { await api.post(`/formations/${formationId}/sessions/${sid}/start/`); loadModule(); showToast('Séance démarrée') }
        catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
        finally { setStartingSession(null) }
      },
    })
  }

  const handleStopSession = (sid, label) => {
    setConfirmDialog({
      message: `Terminer la séance « ${label} » ?`,
      detail: 'Cette action est irréversible.',
      onConfirm: async () => {
        setStoppingSession(sid)
        try { await api.post(`/formations/${formationId}/sessions/${sid}/stop/`); loadModule(); showToast('Séance terminée') }
        catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
        finally { setStoppingSession(null) }
      }
    })
  }

  const handleDeleteSession = (sid) => {
    setConfirmDialog({
      message: 'Supprimer cette séance ?',
      onConfirm: async () => {
        try { await api.delete(`/formations/${formationId}/sessions/${sid}/delete/`); loadModule(); showToast('Séance supprimée') }
        catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
      }
    })
  }

  const confirmArchiveModule = async () => {
    setArchiveOpen(false)
    try {
      await api.post(`/formations/${formationId}/modules/${moduleId}/archive/`)
      showToast('Module archivé — visible uniquement dans l\'espace Archives')
      backToModulesList()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de l\'archivage', 'error')
    }
  }

  const openEditSession = (s) => {
    setEditSession(s)
    setEditSessionForm({ intitule: s.intitule || '', date_journee: s.date || '', heure_debut_prevue: s.heure_debut || '', heure_fin_prevue: s.heure_fin || '' })
  }

  const handleUpdateSession = async (e) => {
    e.preventDefault()
    if (!editSessionForm.date_journee) { showToast('La date est obligatoire.', 'error'); return }
    setSavingSession(true)
    try {
      const res = await api.patch(`/formations/${formationId}/sessions/${editSession.id}/update/`, editSessionForm)
      setEditSession(null); loadModule(); showToast(res.data?.detail || 'Séance modifiée')
    } catch (err) {
      showToast(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de la modification de la séance.' }), 'error')
    } finally { setSavingSession(false) }
  }

  const loadAvailableParticipants = async () => {
    setParticipantLoading(true)
    try {
      const params = new URLSearchParams({ page: participantPicker.page, page_size: PICKER_PAGE_SIZE })
      if (participantSearch) params.set('search', participantSearch)
      const res = await api.get(`/formations/participants/list/?${params}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      const enrolled = new Set((module?.participants || []).map(p => p.id))
      setAllParticipants(data.filter(p => !enrolled.has(p.id)))
      participantPicker.applyResponse(res.data, data.length)
    } catch (err) {
      console.error('Chargement étudiants module:', err)
      showToast(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger la liste des étudiants.' }), 'error')
    } finally { setParticipantLoading(false) }
  }

  const openAddParticipant = () => {
    setParticipantSearch('')
    loadAvailableParticipants()
    setShowAddParticipant(true)
  }

  useEffect(() => {
    if (showAddParticipant) participantPicker.resetPage()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [participantSearch])

  useEffect(() => {
    if (!showAddParticipant) return
    const t = setTimeout(() => loadAvailableParticipants(), 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [participantSearch, showAddParticipant, participantPicker.page])

  const handleAddParticipant = async (pid) => {
    try {
      await api.post(`/formations/${formationId}/modules/${moduleId}/participants/add/`, { participant_id: pid })
      loadModule()
      loadAvailableParticipants(participantSearch)
      showToast('Étudiant inscrit')
    } catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
  }

  const handleRemoveParticipant = (pid, nom) => {
    setConfirmDialog({
      message: `Retirer ${nom} de ce module ?`,
      onConfirm: async () => {
        try {
          await api.delete(`/formations/${formationId}/modules/${moduleId}/participants/${pid}/remove/`)
          loadModule()
          showToast('Étudiant retiré')
        } catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
      }
    })
  }

  const loadAvailableFormateurs = async () => {
    setFormateurLoading(true)
    try {
      const params = new URLSearchParams({ page: formateurPicker.page, page_size: PICKER_PAGE_SIZE, module_id: moduleId })
      if (formateurSearch) params.set('search', formateurSearch)
      const res = await api.get(`/formations/formateurs/list/?${params}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      const assigned = new Set((module?.formateurs || []).map(f => f.id))
      setAllFormateurs(data.filter(f => !assigned.has(f.id)))
      formateurPicker.applyResponse(res.data, data.length)
    } catch (err) {
      console.error('Chargement enseignants module:', err)
      showToast(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger la liste des enseignants.' }), 'error')
    } finally { setFormateurLoading(false) }
  }

  const openAddFormateur = () => {
    setFormateurSearch('')
    setFormateurAssignError('')
    loadAvailableFormateurs()
    setShowAddFormateur(true)
  }

  useEffect(() => {
    if (showAddFormateur) formateurPicker.resetPage()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [formateurSearch])

  useEffect(() => {
    if (!showAddFormateur) return
    const t = setTimeout(() => loadAvailableFormateurs(), 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [formateurSearch, showAddFormateur, formateurPicker.page])

  const handleAddFormateur = async (fid) => {
    setFormateurAssignError('')
    try {
      await api.post(`/formations/${formationId}/modules/${moduleId}/formateurs/add/`, { formateur_id: fid })
      loadModule()
      loadAvailableFormateurs(formateurSearch)
      showToast('Enseignant assigné')
    } catch (err) {
      const message = formatApiErrors(err.response?.data, { fallback: 'Impossible d\'assigner cet enseignant.' })
      setFormateurAssignError(message)
      showToast('Assignation refusée — voir le détail dans la fenêtre.', 'error')
    }
  }

  const handleRemoveFormateur = (fid, nom) => {
    setConfirmDialog({
      message: `Retirer ${nom} de ce module ?`,
      onConfirm: async () => {
        try {
          await api.delete(`/formations/${formationId}/modules/${moduleId}/formateurs/${fid}/remove/`)
          loadModule()
          showToast('Enseignant retiré')
        } catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
      }
    })
  }

  const handleCreateSession = async (e) => {
    e.preventDefault()
    setSavingNewSession(true)
    try {
      await api.post(`/formations/${formationId}/modules/${moduleId}/sessions/new/`, newSessionForm)
      setShowNewSession(false)
      setNewSessionForm({ intitule: '', date_journee: '', heure_debut_prevue: '', heure_fin_prevue: '' })
      loadModule()
      showToast('Séance créée')
    } catch (err) { showToast(err.response?.data?.detail || 'Erreur', 'error') }
    finally { setSavingNewSession(false) }
  }

  const openEditModule = () => {
    setEditModuleForm({
      intitule: module.intitule || '',
      grade: module.grade || '',
      groupe: module.groupe || '',
      vague: module.vague || '',
      statut: module.statut || 'PLANIFIEE',
      site: module.site || '',
      batiment: module.batiment || '',
      salle: module.salle || '',
      date_debut: module.date_debut ? module.date_debut.slice(0, 10) : '',
      date_fin: module.date_fin ? module.date_fin.slice(0, 10) : '',
      duree_prevue_heures: module.duree_prevue_heures || '',
    })
    setEditModuleOpen(true)
  }

  const _downloadBlob = (blob, type, filename) => {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleExportSession = async (sessionId, sessionLabel, type) => {
    try {
      const { blob } = await api.getBlob(`/exports/session/${sessionId}/${type}/`)
      const safeName = (sessionLabel || `session_${sessionId}`).replace(/[^a-z0-9]/gi, '_').toLowerCase()
      _downloadBlob(blob, type, `rapport_${safeName}.${type === 'pdf' ? 'pdf' : 'xlsx'}`)
    } catch (err) {
      showToast(err.response?.data?.detail || `Erreur export ${type.toUpperCase()} séance.`, 'error')
    }
  }

  const handleExportAllSeances = async (type) => {
    try {
      const { blob } = await api.getBlob(`/exports/module/${moduleId}/${type}/`)
      _downloadBlob(blob, type, `rapport_module_${moduleId}.${type === 'pdf' ? 'pdf' : 'xlsx'}`)
    } catch (err) {
      showToast(err.response?.data?.detail || `Erreur export ${type.toUpperCase()} (toutes séances).`, 'error')
    }
  }

  const openForceModal = (personneId = '', action = 'ENTREE', typePersonne = 'participant') => {
    setForceForm({ personne_id: String(personneId), type_personne: typePersonne, action, motif: '' })
    setForceModal(true)
  }

  const handleForcePointage = async (e) => {
    e.preventDefault()
    setForceSaving(true)
    try {
      const res = await api.post(`/formations/${formationId}/force-pointage/`, {
        ...forceForm,
        personne_id: parseInt(forceForm.personne_id),
        module_id: moduleId,
        date_journee: selectedPresenceDate,
      })
      showToast(res.data?.detail || (
        forceForm.type_personne === 'participant' && forceForm.action === 'ENTREE'
          ? 'Présence forcée — durée planifiée de la séance'
          : `${forceForm.action === 'ENTREE' ? 'Entrée' : 'Sortie'} forcée enregistrée`
      ))
      setForceModal(false)
      setForceForm({ personne_id: '', type_personne: 'participant', action: 'ENTREE', motif: '' })
      loadModule(true)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors du forçage', 'error')
    } finally {
      setForceSaving(false)
    }
  }

  const handleBulkForceAuditeurs = async (e) => {
    e.preventDefault()
    const motif = bulkForceMotif.trim()
    if (!motif) return
    setBulkForceSaving(true)
    try {
      const body = {
        module_id: parseInt(moduleId, 10),
        date_journee: selectedPresenceDate,
        motif,
      }
      if (selectedPresenceSessionId !== 'ALL') {
        body.session_id = parseInt(selectedPresenceSessionId, 10)
      }
      const res = await api.post(`/formations/${formationId}/force-badgeage-étudiants-bulk/`, body)
      const sessionsInfo = (res.data.sessions || [])
        .filter(s => s.nb_badges > 0)
        .map(s => `${s.session_intitule}: ${s.nb_badges}/${s.nb_absents} (${s.taux_pct}%)`)
        .join(' · ')
      showToast(sessionsInfo ? `${res.data.detail} — ${sessionsInfo}` : res.data.detail)
      setBulkForceModal(false)
      setBulkForceMotif('')
      loadModule(true)
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors du forçage en masse', 'error')
    } finally {
      setBulkForceSaving(false)
    }
  }

  const handleSaveModule = async (e) => {
    e.preventDefault()
    setSavingModule(true)
    try {
      await api.patch(`/formations/${formationId}/modules/${moduleId}/`, editModuleForm)
      setEditModuleOpen(false)
      loadModule()
      showToast('Module modifié')
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur', 'error')
    } finally {
      setSavingModule(false)
    }
  }

  const loadEncadrants = async () => {
    setEncadrantLoading(true)
    try {
      const params = new URLSearchParams({
        role: 'ENCADRANT',
        page: encadrantPicker.page,
      })
      if (encadrantSearch) params.set('search', encadrantSearch)
      const res = await api.get(`/auth/users/?${params}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setEncadrants(data)
      encadrantPicker.applyResponse(res.data, data.length)
    } catch (err) {
      console.error('Chargement encadrants:', err)
      setAssignSupError(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger la liste des encadrants.' }))
    } finally { setEncadrantLoading(false) }
  }

  const openAssignSuperviseur = () => {
    setSelectedSup(module?.superviseur_id || '')
    setAssignSupError('')
    setEncadrantSearch('')
    setShowAssignSup(true)
  }

  useEffect(() => {
    if (showAssignSup) encadrantPicker.resetPage()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [encadrantSearch])

  useEffect(() => {
    if (!showAssignSup) return
    const t = setTimeout(() => loadEncadrants(), 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [encadrantSearch, showAssignSup, encadrantPicker.page])

  const handleAssignSuperviseur = async () => {
    setAssignSupSaving(true)
    setAssignSupError('')
    try {
      await api.post(
        `/formations/${formationId}/modules/${moduleId}/assign-superviseur/`,
        { superviseur_id: selectedSup || null },
      )
      setShowAssignSup(false)
      loadModule()
      showToast(selectedSup ? 'Encadrant assigné' : 'Encadrant retiré')
    } catch (err) {
      setAssignSupError(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de l\'assignation de l\'encadrant.' }))
    } finally {
      setAssignSupSaving(false)
    }
  }

  const tabStyle = (tab) => ({
    padding: '0.6rem 0.9rem', cursor: 'pointer', fontWeight: 500,
    color: activeTab === tab ? 'var(--ci-success)' : 'var(--text-muted)',
    background: 'none', border: 'none', whiteSpace: 'nowrap', flexShrink: 0,
    borderBottom: `3px solid ${activeTab === tab ? 'var(--ci-success)' : 'transparent'}`,
  })

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (error || !module) return (
    <div className="card"><div className="card-body">
      <div className="error-message">{error || 'Module non trouvé'}</div>
      <button type="button" onClick={backToModulesList} className="btn btn-secondary mt-2">
        <i className="bi bi-arrow-left me-1"></i>Retour
      </button>
    </div></div>
  )

  const sessions = module.sessions || []
  const participants = module.participants || []
  const presences = module.presences || []
  const formateurs = module.formateurs || []
  const encadrantsAttendus = module.encadrants || []

  return (
    <div>
      {/* Header */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="card-header-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <div>
              <span style={{ fontWeight: 600, fontSize: '1.05rem' }}>
                <i className="bi bi-book me-2"></i>{module.intitule}
              </span>
              <span style={{ marginLeft: '0.6rem', fontSize: '0.85rem', color: '#64748b' }}>
                {module.grade} / {module.groupe}
              </span>
            </div>
            <span className={`badge ${getStatutBadge(module.statut)}`}>{getStatutLabel(module.statut)}</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'flex-end' }}>
            {canManageNotes && (
            <Link
              to={`/formations/${formationId}/modules/${moduleId}/notes`}
              className="btn btn-outline-primary btn-sm"
              title="Saisir les notes des étudiants"
            >
              <i className="bi bi-pencil-square me-1"></i>Notes étudiants
            </Link>
            )}
            {canViewDecisions && (
            <Link
              to={`/formations/${formationId}/decisions`}
              className="btn btn-outline-secondary btn-sm"
              title="Décisions pédagogiques (moyenne + assiduité)"
            >
              <i className="bi bi-clipboard-check me-1"></i>Décisions
            </Link>
            )}
            {canArchive && !module.archived && (
              <button
                onClick={() => setArchiveOpen(true)}
                className="btn btn-warning btn-sm"
                title="Archiver ce module (3 confirmations)"
              >
                <i className="bi bi-archive me-1"></i>Archiver
              </button>
            )}
            <button
              onClick={() => handleExportAllSeances('pdf')}
              className="btn btn-outline-danger btn-sm"
              title="Exporter PDF (toutes les séances)"
            >
              <i className="bi bi-file-earmark-pdf me-1"></i>PDF — Toutes séances
            </button>
            <button
              onClick={() => handleExportAllSeances('excel')}
              className="btn btn-outline-success btn-sm"
              title="Exporter Excel (toutes les séances)"
            >
              <i className="bi bi-file-earmark-excel me-1"></i>Excel — Toutes séances
            </button>
            <div style={{ fontSize: '0.82rem', color: '#94a3b8', width: '100%', textAlign: 'right' }}>
              <i className="bi bi-mortarboard me-1"></i>Formation : {module.formation}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', paddingLeft: '1rem', overflowX: 'auto' }}>
          {[
            { key: 'seances',      label: `Séances (${sessions.length})`,       icon: 'bi-calendar3' },
            { key: 'info',         label: 'Informations',                        icon: 'bi-info-circle' },
            { key: 'participants', label: `Étudiants (${participants.length})`,  icon: 'bi-people' },
            { key: 'presences',   label: `Présences (${presences.length})`,    icon: 'bi-check2-circle' },
            { key: 'formateurs',  label: `Enseignants (${formateurs.length})`,   icon: 'bi-person-video3' },
          ].map(t => (
            <button key={t.key} style={tabStyle(t.key)} onClick={() => setActiveTab(t.key)}>
              <i className={`bi ${t.icon} me-1`}></i>{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── TAB: SÉANCES ── */}
      {activeTab === 'seances' && (() => {
        const objectifHeures = module.duree_contractuelle_heures ?? module.duree_prevue_heures
        const planifieHeures = module.duree_planifiee_heures ?? sommeSeancesHeures(sessions)
        const edtResume = fmtEdtVsObjectif(objectifHeures, planifieHeures)
        return (
        <div className="card">
          <div className="card-header-bar" style={{ background: '#f0f6fd' }}>
            <span style={{ fontWeight: 600, color: 'var(--ci-success-dark)' }}>
              <i className="bi bi-calendar3 me-2"></i>Séances — {module.intitule}
              <span className="badge ms-2" style={{ background: '#d1e3fa', color: '#082a5d', fontSize: '0.78rem' }}>
                {sessions.length} séance{sessions.length > 1 ? 's' : ''}
              </span>
              {planifieHeures != null && objectifHeures != null && (
                <span className="badge ms-2" style={{ background: '#ecf3fd', color: '#093473', fontSize: '0.78rem', fontWeight: 500 }}>
                  Σ {fmtHeuresLabel(planifieHeures) ?? '—'} / {fmtHeuresLabel(objectifHeures) ?? '—'}
                </span>
              )}
            </span>
            {canManageSessions && (
              <button onClick={() => setShowNewSession(true)} className="btn btn-dfrc btn-sm">
                <i className="bi bi-plus-lg me-1"></i>Nouvelle séance
              </button>
            )}
          </div>
          {edtResume && (
            <div style={{ padding: '0.55rem 1rem', borderBottom: '1px solid #ecf3fd', fontSize: '0.84rem', color: '#64748b' }}>
              <i className="bi bi-clock-history me-1"></i>{edtResume}
              <span style={{ marginLeft: '0.35rem', color: '#94a3b8' }}>
                (Σ durées de chaque séance)
              </span>
            </div>
          )}
          <div className="card-body-flush">
            {sessions.length > 0 ? (
              <div className="table-container">
                <table className="table">
                  <thead>
                    <tr><th>N°</th><th>Intitulé</th><th>Date</th><th>Horaire</th><th>Durée</th><th>Statut</th><th>Présences</th><th>Exports</th><th>Actions</th></tr>
                  </thead>
                  <tbody>
                    {sessions.map(s => (
                      <tr key={s.id}>
                        <td><span className="badge-bg-info">{sessionNumeroLabel(s)}</span></td>
                        <td><strong>{s.intitule || '—'}</strong></td>
                        <td>{s.date ? formatDate(s.date) : '—'}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{s.heure_debut || '—'} — {s.heure_fin || '—'}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{fmtHeuresLabel(sessionDureeHeures(s)) || '—'}</td>
                        <td>
                          <span className={`badge ${s.en_cours ? 'badge-en-cours' : s.terminee ? 'badge-terminee' : 'badge-planifiee'}`}>
                            {s.en_cours ? 'En cours' : s.terminee ? 'Terminée' : 'Planifiée'}
                          </span>
                        </td>
                        <td><span className="badge-bg-success">{s.nb_presences || 0}</span> / {s.nb_attendus || 0}</td>
                        <td>
                          <div style={{ display: 'flex', gap: '4px' }}>
                            <button onClick={() => handleExportSession(s.id, s.intitule || `seance_${s.numero}`, 'pdf')} className="btn btn-outline-danger btn-sm" title="Exporter PDF">
                              <i className="bi bi-file-earmark-pdf"></i>
                            </button>
                            <button onClick={() => handleExportSession(s.id, s.intitule || `seance_${s.numero}`, 'excel')} className="btn btn-outline-success btn-sm" title="Exporter Excel">
                              <i className="bi bi-file-earmark-excel"></i>
                            </button>
                          </div>
                        </td>
                        <td>
                          <div className="btn-group">
                            {canSupervise && !s.en_cours && !s.terminee && (
                              <button onClick={() => handleStartSession(s.id, s.intitule || `Séance ${s.numero}`)} className="btn btn-outline-success btn-sm" disabled={startingSession === s.id}>
                                {startingSession === s.id ? <span className="spinner" style={{ width: '0.8rem', height: '0.8rem', display: 'inline-block' }}></span> : <><i className="bi bi-play-fill me-1"></i>Démarrer</>}
                              </button>
                            )}
                            {s.en_cours && canSupervise && (
                              <button onClick={() => handleStopSession(s.id, s.intitule || `Séance ${s.numero}`)} className="btn btn-warning btn-sm" disabled={stoppingSession === s.id}>
                                {stoppingSession === s.id ? <span className="spinner" style={{ width: '0.8rem', height: '0.8rem', display: 'inline-block' }}></span> : <><i className="bi bi-stop-fill me-1"></i>Terminer</>}
                              </button>
                            )}
                            {!s.terminee && (
                              <button onClick={() => { setSelectedSessionId(s.id); setQrModalOpen(true) }} className="btn btn-outline-primary btn-sm" title="QR Code">
                                <i className="bi bi-qr-code"></i>
                              </button>
                            )}
                            {s.terminee && (
                              <span className="badge badge-terminee">Terminé</span>
                            )}
                            {canManageSessions && !s.terminee && (
                              <button onClick={() => openEditSession(s)} className="btn btn-outline-secondary btn-sm" title="Modifier">
                                <i className="bi bi-pencil"></i>
                              </button>
                            )}
                            {canManageSessions && !s.en_cours && !s.terminee && (
                              <button onClick={() => handleDeleteSession(s.id)} className="btn btn-outline-danger btn-sm" title="Supprimer">
                                <i className="bi bi-trash"></i>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-center py-4 text-muted">
                <i className="bi bi-calendar-x" style={{ fontSize: '2rem' }}></i>
                <p className="mt-2">Aucune séance planifiée pour ce module</p>
              </div>
            )}
          </div>
        </div>
        )
      })()}

      {/* ── TAB: INFO ── */}
      {activeTab === 'info' && (() => {
        const nbTerminees = sessions.filter(s => s.statut === 'TERMINEE' || s.statut === 'TERMINÉE').length
        const dureeContractuelle = module.duree_contractuelle_heures ?? module.duree_prevue_heures
        const dureePlanifiee = module.duree_planifiee_heures ?? sommeSeancesHeures(sessions)
        const dureeAffichee = fmtHeuresLabel(dureeContractuelle ?? dureePlanifiee)
        const dureeDetail = fmtEdtVsObjectif(dureeContractuelle, dureePlanifiee)
        const infoRow = (icon, label, value, iconColor = 'var(--ci-warning)', extra = null) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', padding: '0.6rem 0', borderBottom: '1px solid #f1f5f9', gap: '0.75rem' }}>
            <i className={`bi ${icon}`} style={{ width: 18, color: iconColor, flexShrink: 0, fontSize: '1rem' }}></i>
            <span style={{ minWidth: 90, fontWeight: 600, fontSize: '0.86rem', color: '#64748b' }}>{label}</span>
            <span style={{ fontSize: '0.92rem', color: '#1e293b' }}>
              {value || <span style={{ color: '#cbd5e1' }}>—</span>}
              {extra && <small style={{ display: 'block', color: '#94a3b8', fontSize: '0.78rem', marginTop: '0.15rem' }}>{extra}</small>}
            </span>
          </div>
        )
        return (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 280px', gap: '1rem', alignItems: 'start' }}>

            {/* ── Colonne gauche ── */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

              {/* Lieu & Calendrier */}
              <div className="card">
                <div style={{ padding: '1rem 1.2rem', borderBottom: '1px solid #f1f5f9' }}>
                  <span style={{ fontWeight: 700, color: '#1e293b', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <i className="bi bi-geo-alt" style={{ color: 'var(--ci-warning)' }}></i>Lieu &amp; Calendrier
                  </span>
                </div>
                <div style={{ padding: '0.5rem 1.2rem 0.75rem' }}>
                  {infoRow('bi-building',        'Site',    module.site)}
                  {infoRow('bi-buildings',        'Bâtiment', module.batiment)}
                  {infoRow('bi-layout-text-window-reverse', 'Salle', module.salle)}
                  {infoRow('bi-calendar',         'Début',   formatDate(module.date_debut))}
                  {infoRow('bi-calendar-check',   'Fin',     formatDate(module.date_fin))}
                  {infoRow('bi-clock',            'Durée',   dureeAffichee, 'var(--ci-warning)', dureeDetail)}
                </div>
              </div>

              {/* Classification & Intervenants */}
              <div className="card">
                <div style={{ padding: '1rem 1.2rem', borderBottom: '1px solid #f1f5f9', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <span style={{ fontWeight: 700, color: '#1e293b', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <i className="bi bi-people" style={{ color: 'var(--ci-warning)' }}></i>Classification &amp; Intervenants
                  </span>
                  {canManageModule && (
                    <button onClick={openAssignSuperviseur} className="btn btn-outline-primary btn-sm" title="Assigner un encadrant">
                      <i className="bi bi-person-gear me-1"></i>
                      {module.superviseur_id ? 'Changer encadrant' : 'Assigner encadrant'}
                    </button>
                  )}
                </div>
                <div style={{ padding: '0.5rem 1.2rem 0.75rem' }}>
                  {infoRow('bi-tag',          'Catégorie', module.categorie)}
                  {infoRow('bi-award',        'Grade',     module.grade)}
                  {infoRow('bi-book',         'Module',    module.intitule)}
                  {infoRow('bi-mortarboard',  'Formation', module.formation)}
                  {infoRow('bi-people',       'Groupe',    module.groupe)}
                  {infoRow('bi-flag',         'Vague',     module.vague)}
                  {infoRow('bi-person-video3','Enseignant', formateurs.length > 0
                    ? formateurs.map(f => `${f.prenom} ${f.nom}`).join(', ')
                    : null)}
                  {infoRow('bi-person-gear',  'Encadrant', module.superviseur_nom)}
                </div>
              </div>
            </div>

            {/* ── Colonne droite ── */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

              {/* Résumé stats */}
              <div className="card" style={{ borderTop: '3px solid var(--ci-success)' }}>
                <div style={{ padding: '0.75rem 1rem', textAlign: 'center', borderBottom: '1px solid #f1f5f9' }}>
                  <span style={{ fontSize: '0.7rem', letterSpacing: '0.1em', color: '#94a3b8', fontWeight: 600 }}>RÉSUMÉ</span>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0', borderBottom: '1px solid #f1f5f9' }}>
                  {[
                    { icon: 'bi-calendar3',   value: sessions.length,      label: 'SÉANCES',    color: '#0e58ab' },
                    { icon: 'bi-people',      value: participants.length,   label: 'AUDITEURS',  color: '#1d4ed8' },
                    { icon: 'bi-check-circle',value: nbTerminees,           label: 'TERMINÉES',  color: '#7c3aed' },
                    { icon: 'bi-person-video3',value: formateurs.length,    label: 'ENSEIGNANTS', color: 'var(--ci-warning)' },
                  ].map((c, i) => (
                    <div key={c.label} style={{
                      padding: '1.1rem 0.5rem', textAlign: 'center',
                      borderRight: i % 2 === 0 ? '1px solid #f1f5f9' : 'none',
                      borderTop: i >= 2 ? '1px solid #f1f5f9' : 'none',
                    }}>
                      <i className={`bi ${c.icon}`} style={{ fontSize: '1.3rem', color: c.color, display: 'block', marginBottom: '0.3rem' }}></i>
                      <div style={{ fontSize: '1.6rem', fontWeight: 700, color: c.color, lineHeight: 1 }}>{c.value}</div>
                      <div style={{ fontSize: '0.65rem', color: '#94a3b8', letterSpacing: '0.08em', marginTop: '0.3rem' }}>{c.label}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Statut */}
              <div className="card" style={{ borderTop: '3px solid var(--ci-warning)' }}>
                <div style={{ padding: '0.75rem 1rem', borderBottom: '1px solid #f1f5f9' }}>
                  <span style={{ fontSize: '0.7rem', letterSpacing: '0.1em', color: '#94a3b8', fontWeight: 600 }}>STATUT</span>
                </div>
                <div style={{ padding: '0.9rem 1rem' }}>
                  <span className={`badge ${getStatutBadge(module.statut)}`} style={{ fontSize: '0.85rem', padding: '0.4rem 0.9rem' }}>
                    {getStatutLabel(module.statut)}
                  </span>
                  {module.secretariat_nom && (
                    <div style={{ marginTop: '0.75rem', fontSize: '0.88rem', color: '#374151', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <i className="bi bi-building" style={{ color: '#94a3b8' }}></i>
                      <strong>Secrétariat :</strong> {module.secretariat_nom}
                    </div>
                  )}
                  {canManageModule && (
                    <button onClick={openEditModule} className="btn btn-outline-secondary btn-sm" style={{ marginTop: '0.85rem', width: '100%' }}>
                      <i className="bi bi-pencil me-1"></i>Modifier
                    </button>
                  )}
                </div>
              </div>
            </div>

          </div>
        )
      })()}

      {/* ── TAB: PARTICIPANTS ── */}
      {activeTab === 'participants' && (
        <div className="card">
          <div className="card-header-bar">
            <span><i className="bi bi-people me-2"></i>Étudiants inscrits ({participants.length})</span>
            {canManageModule && (
              <button onClick={openAddParticipant} className="btn btn-dfrc btn-sm">
                <i className="bi bi-person-plus me-1"></i>Inscrire
              </button>
            )}
          </div>
          <div className="card-body-flush">
            {participants.length > 0 && (
              <div className="p-3 pb-0">
                <input
                  className="form-control form-control-sm"
                  placeholder="Rechercher un étudiant (nom, prénom, matricule)…"
                  value={enrolledSearch}
                  onChange={e => setEnrolledSearch(e.target.value)}
                  style={{ maxWidth: 360 }}
                />
              </div>
            )}
            {filteredParticipants.length > 0 ? (
              <>
              <div className="table-container">
                <table className="table">
                  <thead><tr><th>Matricule</th><th>Nom</th><th>Prénom</th><th>Grade</th><th>Groupe</th>{canManageModule && <th></th>}</tr></thead>
                  <tbody>
                    {participantsPager.pageItems.map(p => (
                      <tr key={p.id}>
                        <td><span className="badge-bg-info">{p.numero_matricule || p.matricule || '—'}</span></td>
                        <td><strong>{p.nom}</strong></td>
                        <td>{p.prenom}</td>
                        <td>{p.grade || '—'}</td>
                        <td>{p.groupe || '—'}</td>
                        {canManageModule && (
                          <td>
                            <button onClick={() => handleRemoveParticipant(p.id, `${p.nom} ${p.prenom}`)} className="btn btn-outline-danger btn-sm" title="Retirer">
                              <i className="bi bi-person-dash"></i>
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={participantsPager.page}
                totalPages={participantsPager.totalPages}
                onPageChange={participantsPager.setPage}
                totalItems={participantsPager.totalItems}
                pageSize={participantsPager.pageSize}
              />
              </>
            ) : (
              <div className="text-center py-4 text-muted">
                <i className="bi bi-person-x" style={{ fontSize: '2rem' }}></i>
                <p className="mt-2">
                  {participants.length > 0 ? 'Aucun étudiant ne correspond à cette recherche.' : 'Aucun étudiant inscrit'}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB: FORMATEURS ── */}
      {activeTab === 'formateurs' && (
        <div className="card">
          <div className="card-header-bar" style={{ background: '#fdf4ff' }}>
            <span style={{ fontWeight: 600, color: '#7e22ce' }}>
              <i className="bi bi-person-video3 me-2"></i>Enseignants assignés
              <span className="badge ms-2" style={{ background: '#f3e8ff', color: '#6b21a8', fontSize: '0.78rem' }}>
                {formateurs.length} enseignant{formateurs.length > 1 ? 's' : ''}
              </span>
            </span>
            {canManageModule && (
              <button onClick={openAddFormateur} className="btn btn-dfrc btn-sm">
                <i className="bi bi-person-plus me-1"></i>Assigner
              </button>
            )}
          </div>
          <div className="card-body-flush">
            {formateurs.length > 0 ? (
              <>
              <div className="table-container">
                <table className="table">
                  <thead><tr><th>N° Badge</th><th>Nom</th><th>Prénom</th><th>Spécialité</th><th>Email</th>{canManageModule && <th></th>}</tr></thead>
                  <tbody>
                    {formateursPager.pageItems.map(f => (
                      <tr key={f.id}>
                        <td>
                          <span className="badge-bg-info" style={{ fontFamily: 'monospace', fontWeight: 700 }}>{f.numerobadge || '—'}</span>
                          {f.numerobadge && (
                            <div style={{ fontSize: '0.72rem', color: '#64748b', marginTop: '2px' }}>
                              <i className="bi bi-qr-code me-1"></i>N° de badgeage
                            </div>
                          )}
                        </td>
                        <td><strong>{f.nom}</strong></td>
                        <td>{f.prenom}</td>
                        <td>{f.specialite || '—'}</td>
                        <td>{f.email || '—'}</td>
                        {canManageModule && (
                          <td>
                            <button onClick={() => handleRemoveFormateur(f.id, `${f.nom} ${f.prenom}`)} className="btn btn-outline-danger btn-sm" title="Retirer">
                              <i className="bi bi-person-dash"></i>
                            </button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={formateursPager.page}
                totalPages={formateursPager.totalPages}
                onPageChange={formateursPager.setPage}
                totalItems={formateursPager.totalItems}
                pageSize={formateursPager.pageSize}
              />
              </>
            ) : (
              <div className="text-center py-4 text-muted">
                <i className="bi bi-person-x" style={{ fontSize: '2rem' }}></i>
                <p className="mt-2">Aucun enseignant assigné à ce module</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── TAB: PRÉSENCES ── */}
      {activeTab === 'presences' && (() => {
        const sessionsOfDay = sessions.filter(s => s.date === selectedPresenceDate)
        const ptDateAll = presences.filter(pt => (pt.date_journee || pt.session_date) === selectedPresenceDate)
        const ptDate = selectedPresenceSessionId === 'ALL'
          ? ptDateAll
          : ptDateAll.filter(pt => String(pt.session_id) === String(selectedPresenceSessionId))
        const q = presenceSearch.toLowerCase().trim()
        const ptFiltered = q
          ? ptDate.filter(pt => `${pt.nom} ${pt.prenom} ${pt.matricule || ''} ${pt.numerobadge || ''}`.toLowerCase().includes(q))
          : ptDate

        // Séparer participants, formateurs, encadrants
        const ptPart = ptDate.filter(pt => pt.type_personne === 'participant')
        const ptFmt  = ptDate.filter(pt => pt.type_personne === 'formateur')
        const ptEnc  = ptDate.filter(pt => pt.type_personne === 'encadrant')

        const presentPartIds = new Set(ptPart.map(pt => pt.participant_id))
        const presentFmtIds  = new Set(ptFmt.map(pt => pt.formateur_id))
        const presentEncIds  = new Set(ptEnc.map(pt => pt.encadrant_id))

        const nbAttendus = participants.length + formateurs.length + encadrantsAttendus.length
        const nbPresents = (
          [...new Set(ptPart.filter(pt => pt.timestamp_sortie && (pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE').map(pt => pt.participant_id))].length
          + [...new Set(ptFmt.filter(pt => pt.timestamp_sortie && (pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE').map(pt => pt.formateur_id))].length
          + [...new Set(ptEnc.filter(pt => pt.timestamp_sortie && (pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE').map(pt => pt.encadrant_id))].length
        )
        const nbEnSalle = (
          [...new Set(ptPart.filter(pt => pt.timestamp_entree && !pt.timestamp_sortie).map(pt => pt.participant_id))].length
          + [...new Set(ptFmt.filter(pt => pt.timestamp_entree && !pt.timestamp_sortie).map(pt => pt.formateur_id))].length
          + [...new Set(ptEnc.filter(pt => pt.timestamp_entree && !pt.timestamp_sortie).map(pt => pt.encadrant_id))].length
        )
        const presentOuSallePartIds = new Set(ptPart.filter(pt => !pt.timestamp_sortie || ((pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE')).map(pt => pt.participant_id))
        const presentOuSalleFmtIds  = new Set(ptFmt.filter(pt => !pt.timestamp_sortie || ((pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE')).map(pt => pt.formateur_id))
        const presentOuSalleEncIds  = new Set(ptEnc.filter(pt => !pt.timestamp_sortie || ((pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE')).map(pt => pt.encadrant_id))
        const nbAbsents = (
          participants.filter(p => !presentOuSallePartIds.has(p.id)).length
          + formateurs.filter(f => !presentOuSalleFmtIds.has(f.id)).length
          + encadrantsAttendus.filter(e => !presentOuSalleEncIds.has(e.id)).length
        )
        const taux = nbAttendus > 0 ? Math.round(((nbPresents + nbEnSalle) / nbAttendus) * 100) : 0

        const seanceIds = [...new Set(ptFiltered.map(pt => pt.session_id))]
        const seancesDuJour = seanceIds.map(sid => {
          const pts = ptFiltered.filter(pt => pt.session_id === sid)
          return {
            session_id: sid,
            session_intitule: pts[0].session_intitule || `Séance ${pts[0].session_numero || ''}`,
            pointages: pts,
          }
        })

        // Absents : participants + formateurs + encadrants qui n'ont pas encore badgé
        const absentsParticipants = participants
          .filter(p => !presentPartIds.has(p.id))
          .map(p => ({ ...p, type_personne: 'participant' }))
        const absentsFormateurs = formateurs
          .filter(f => !presentFmtIds.has(f.id))
          .map(f => ({ ...f, type_personne: 'formateur' }))
        const absentsEncadrants = encadrantsAttendus
          .filter(e => !presentEncIds.has(e.id))
          .map(e => ({ ...e, type_personne: 'encadrant' }))
        const absentsAll = [...absentsParticipants, ...absentsFormateurs, ...absentsEncadrants]
        const absentsFiltered = q
          ? absentsAll.filter(p =>
              `${p.nom} ${p.prenom} ${p.matricule || p.numero_matricule || ''} ${p.numerobadge || ''}`.toLowerCase().includes(q)
            )
          : absentsAll

        return (
          <div>
            {/* ── Barre filtre ── */}
            <div className="card" style={{ marginBottom: '1rem' }}>
              <div style={{ padding: '0.85rem 1.2rem', display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <i className="bi bi-calendar3" style={{ color: '#64748b' }}></i>
                  <span style={{ fontWeight: 500, color: '#374151' }}>Présences du :</span>
                  <input type="date" className="form-control" style={{ width: 'auto' }}
                    value={selectedPresenceDate}
                    onChange={e => { setSelectedPresenceDate(e.target.value); setSelectedPresenceSessionId('ALL') }} />
                  {sessionsOfDay.length > 0 && (
                    <select className="form-control" style={{ width: 'auto' }}
                      value={selectedPresenceSessionId}
                      onChange={e => setSelectedPresenceSessionId(e.target.value)}>
                      <option value="ALL">Toutes les séances{sessionsOfDay.length > 1 ? ` (${sessionsOfDay.length})` : ''}</option>
                      {sessionsOfDay.map(s => {
                        const label = s.intitule || `Séance ${s.numero}`
                        const horaire = (s.heure_debut || s.heure_fin) ? ` — ${s.heure_debut || '?'}${s.heure_fin ? ` → ${s.heure_fin}` : ''}` : ''
                        return <option key={s.id} value={s.id}>{label}{horaire}</option>
                      })}
                    </select>
                  )}
                  <button className="btn btn-warning btn-sm" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                    onClick={() => { setSelectedPresenceDate(new Date().toISOString().slice(0, 10)); setSelectedPresenceSessionId('ALL'); loadModule() }}>
                    <i className="bi bi-arrow-clockwise"></i> Actualiser
                  </button>
                  {canSupervise && sessionsOfDay.some(s => s.en_cours) && (
                    <button
                      type="button"
                      className="btn btn-success btn-sm"
                      style={{ display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                      title="Forcer l'entrée de 80 à 95 % des étudiants absents, tirage aléatoire par séance"
                      onClick={() => { setBulkForceMotif(''); setBulkForceModal(true) }}
                    >
                      <i className="bi bi-shuffle"></i> Forcer étudiants (80–95 %)
                    </button>
                  )}
                </div>
                <div style={{ marginLeft: 'auto', minWidth: '220px' }}>
                  <div className="input-group">
                    <span className="input-group-text" style={{ background: '#f8fafc' }}><i className="bi bi-search"></i></span>
                    <input type="text" className="form-control" placeholder="Rechercher par nom, matricule, N° badge…"
                      value={presenceSearch} onChange={e => setPresenceSearch(e.target.value)} />
                  </div>
                </div>
              </div>
            </div>

            {/* ── Stats cards ── */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
              {[
                { label: 'ATTENDUS',      value: nbAttendus, icon: 'bi-people',             bg: '#f8fafc', border: '#cbd5e1', color: '#475569' },
                { label: 'EN SALLE',      value: nbEnSalle,  icon: 'bi-person-check',        bg: '#eff6ff', border: '#93c5fd', color: '#1d4ed8' },
                { label: 'PRÉSENTS',      value: nbPresents, icon: 'bi-check-circle',         bg: '#f0f6fd', border: '#80b7f5', color: '#0b478a' },
                { label: 'ABSENTS',       value: nbAbsents,  icon: 'bi-person-x',             bg: '#fef2f2', border: '#fca5a5', color: '#dc2626' },
                { label: 'TAUX PRÉSENCE', value: `${taux}%`, icon: 'bi-graph-up',             bg: '#fefce8', border: '#fcdf4d', color: taux < 50 ? '#dc2626' : '#d9a106' },
              ].map(c => (
                <div key={c.label} style={{ background: c.bg, border: `1.5px solid ${c.border}`, borderRadius: '12px', padding: '1rem', textAlign: 'center' }}>
                  <i className={`bi ${c.icon}`} style={{ fontSize: '1.4rem', color: c.color, display: 'block', marginBottom: '0.3rem' }}></i>
                  <div style={{ fontSize: '1.7rem', fontWeight: 700, color: c.color, lineHeight: 1 }}>{c.value}</div>
                  <div style={{ fontSize: '0.7rem', color: '#94a3b8', letterSpacing: '0.05em', marginTop: '0.35rem' }}>{c.label}</div>
                </div>
              ))}
            </div>

            {/* ── Contenu ── */}
            {ptDate.length === 0 && (
              <div className="card" style={{ marginBottom: '1rem' }}>
                <div style={{ padding: '2.5rem', textAlign: 'center', color: '#94a3b8' }}>
                  <i className="bi bi-calendar-x" style={{ fontSize: '2.5rem', display: 'block', marginBottom: '0.75rem' }}></i>
                  Aucun pointage enregistré pour cette date.
                  <div style={{ marginTop: '0.35rem', fontSize: '0.85rem' }}>
                    Les étudiants/formateurs/encadrants attendus restent visibles dans la liste des absents ci-dessous.
                  </div>
                </div>
              </div>
            )}
            <>
                {/* Présents par séance */}
                {seancesDuJour.map(seance => {
                  const countPresencesTerminees = (pts) =>
                    pts.filter(pt => pt.timestamp_sortie && (pt.duree_minutes || 0) > 0 && pt.statut !== 'ABSENT_NON_BADGE').length
                  const nPresSeance = countPresencesTerminees(seance.pointages)
                  const ptsAud = seance.pointages.filter(pt => pt.type_personne !== 'formateur' && pt.type_personne !== 'encadrant')
                  const ptsFmt = seance.pointages.filter(pt => pt.type_personne === 'formateur')
                  const ptsEnc = seance.pointages.filter(pt => pt.type_personne === 'encadrant')

                  const presenceRow = (pt, i) => (
                    <tr key={`${pt.type_personne || 'participant'}_${pt.participant_id ?? pt.formateur_id ?? pt.encadrant_id}_${i}`}>
                      <td>
                        <span className="badge-bg-info" style={{ fontFamily: pt.type_personne === 'formateur' ? 'monospace' : undefined }}>
                          {pt.type_personne === 'formateur' ? (pt.numerobadge || '—') : (pt.matricule || '—')}
                        </span>
                      </td>
                      <td><strong>{pt.nom}</strong></td>
                      <td>{pt.prenom}</td>
                      <td><small>{pt.timestamp_entree ? new Date(pt.timestamp_entree).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '—'}</small></td>
                      <td><small>{pt.timestamp_sortie ? new Date(pt.timestamp_sortie).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : <span className="text-warning">En cours</span>}</small></td>
                      <td><small>{pt.duree_minutes > 0 ? `${Math.round(pt.duree_minutes)} min` : '—'}</small></td>
                      <td>
                        <span
                          className={`badge ${
                          pt.statut === 'ABSENT_NON_BADGE' ? 'badge-danger'
                          : (pt.statut === 'FORCE_DFRC' && (pt.duree_minutes || 0) === 0 && !!pt.timestamp_sortie) ? 'badge-danger'
                          : pt.statut === 'FORCE_DFRC' ? 'badge-info'
                          : pt.timestamp_sortie ? 'badge-terminee'
                          : 'badge-en-cours'
                        }`}
                          style={{ fontSize: '0.72rem' }}
                          title={pt.statut === 'FORCE_DFRC' && (pt.duree_minutes || 0) > 0 ? 'Présence forcée — durée planifiée de la séance' : undefined}
                        >
                          {pt.statut === 'ABSENT_NON_BADGE' ? 'Absent'
                          : (pt.statut === 'FORCE_DFRC' && (pt.duree_minutes || 0) === 0 && !!pt.timestamp_sortie) ? 'Absent'
                          : pt.statut === 'FORCE_DFRC' ? 'Forcé'
                          : pt.timestamp_sortie ? 'Terminé'
                          : 'En cours'}
                        </span>
                      </td>
                      {canSupervise && (
                        <td>
                          {!pt.timestamp_sortie && (
                            <button className="btn btn-outline-warning btn-sm" title="Forcer la sortie"
                              onClick={() => openForceModal(pt.participant_id || pt.enseignant_id || pt.encadrant_id, 'SORTIE', pt.type_personne || 'participant')}>
                              <i className="bi bi-box-arrow-right"></i>
                            </button>
                          )}
                        </td>
                      )}
                    </tr>
                  )

                  const theadPresence = (
                    <thead>
                      <tr><th>N° / Matricule</th><th>Nom</th><th>Prénom</th><th>Entrée</th><th>Sortie</th><th>Durée</th><th>Statut</th>{canSupervise && <th></th>}</tr>
                    </thead>
                  )

                  const subBar = (icon, label, bg, border, color, count) => (
                    <div style={{
                      padding: '0.45rem 1rem',
                      background: bg,
                      borderTop: border ? `1px solid ${border}` : undefined,
                      borderBottom: `1px solid ${border || '#e2e8f0'}`,
                      fontWeight: 600,
                      fontSize: '0.82rem',
                      color,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}>
                      <i className={`bi ${icon}`}></i>
                      {label}
                      <span className="badge" style={{ fontSize: '0.72rem', fontWeight: 600, background: '#fff', color, border: `1px solid ${border || '#e2e8f0'}` }}>{count}</span>
                    </div>
                  )

                  return (
                    <div className="card" key={seance.session_id} style={{ marginBottom: '1rem' }}>
                      <div className="card-header-bar" style={{ background: '#f0f6fd', borderBottom: '2px solid #bbd7f7' }}>
                        <span style={{ fontWeight: 600 }}>
                          <i className="bi bi-calendar3 me-2" style={{ color: '#0e58ab' }}></i>
                          {seance.session_intitule}
                        </span>
                        <span className="badge" style={{ background: '#d1e3fa', color: '#082a5d', fontSize: '0.78rem' }}>
                          {nPresSeance} présence{nPresSeance > 1 ? 's' : ''}
                          {(ptsAud.length > 0 || ptsFmt.length > 0 || ptsEnc.length > 0) && (
                            <span style={{ fontWeight: 400, marginLeft: '0.35rem', opacity: 0.95 }}>
                              ({countPresencesTerminees(ptsAud)} aud.{ptsFmt.length > 0 ? ` · ${countPresencesTerminees(ptsFmt)} form.` : ''}{ptsEnc.length > 0 ? ` · ${countPresencesTerminees(ptsEnc)} enc.` : ''})
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="card-body-flush">
                        {ptsAud.length === 0 && ptsFmt.length === 0 && ptsEnc.length === 0 && (
                          <div className="p-3 text-muted text-center" style={{ fontSize: '0.9rem' }}>Aucune ligne pour cette séance.</div>
                        )}
                        {ptsAud.length > 0 && (
                          <>
                            {subBar('bi-people', 'Étudiants', '#eff6ff', '#bfdbfe', '#1d4ed8', ptsAud.length)}
                            <table className="table mb-0">
                              {theadPresence}
                              <tbody>{ptsAud.map(presenceRow)}</tbody>
                            </table>
                          </>
                        )}
                        {ptsFmt.length > 0 && (
                          <>
                            {subBar('bi-person-video3', 'Enseignants', '#faf5ff', '#e9d5ff', '#6b21a8', ptsFmt.length)}
                            <table className="table mb-0">
                              {theadPresence}
                              <tbody>{ptsFmt.map(presenceRow)}</tbody>
                            </table>
                          </>
                        )}
                        {ptsEnc.length > 0 && (
                          <>
                            {subBar('bi-person-badge', 'Encadrants', '#fffceb', '#fdec8a', '#9c4221', ptsEnc.length)}
                            <table className="table mb-0">
                              {theadPresence}
                              <tbody>{ptsEnc.map(presenceRow)}</tbody>
                            </table>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}

                {/* Absents du jour */}
                {absentsFiltered.length > 0 && (() => {
                  const absAud = absentsFiltered.filter(p => p.type_personne !== 'formateur' && p.type_personne !== 'encadrant')
                  const absFmt = absentsFiltered.filter(p => p.type_personne === 'formateur')
                  const absEnc = absentsFiltered.filter(p => p.type_personne === 'encadrant')

                  const absentSubBar = (icon, label, bg, border, color, count) => (
                    <div style={{
                      padding: '0.45rem 1rem',
                      background: bg,
                      borderTop: border ? `1px solid ${border}` : undefined,
                      borderBottom: `1px solid ${border || '#e2e8f0'}`,
                      fontWeight: 600,
                      fontSize: '0.82rem',
                      color,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}>
                      <i className={`bi ${icon}`}></i>
                      {label}
                      <span className="badge" style={{ fontSize: '0.72rem', fontWeight: 600, background: '#fff', color, border: `1px solid ${border || '#e2e8f0'}` }}>{count}</span>
                    </div>
                  )

                  const absentRow = (p, idx) => (
                    <tr key={`${p.type_personne}_${p.id}_${idx}`}>
                      <td>
                        <span className="badge-bg-info" style={{ fontFamily: p.type_personne === 'formateur' ? 'monospace' : undefined }}>
                          {p.type_personne === 'formateur' ? (p.numerobadge || '—') : (p.matricule || p.numero_matricule || '—')}
                        </span>
                      </td>
                      <td><strong>{p.nom}</strong></td>
                      <td>{p.prenom}</td>
                      <td>
                        {p.type_personne === 'formateur'
                          ? <span className="badge" style={{ background: '#f3e8ff', color: '#6b21a8', fontSize: '0.72rem' }}><i className="bi bi-person-video3 me-1"></i>Enseignant</span>
                          : p.type_personne === 'encadrant'
                            ? <span className="badge" style={{ background: '#fffae6', color: '#9c4221', fontSize: '0.72rem' }}><i className="bi bi-person-badge me-1"></i>Encadrant</span>
                            : (p.grade || '—')}
                      </td>
                      {canSupervise && (
                        <td>
                          <button className="btn btn-outline-success btn-sm" title="Forcer la présence (durée planifiée de la séance)"
                            onClick={() => openForceModal(p.id, 'ENTREE', p.type_personne || 'participant')}>
                            <i className="bi bi-box-arrow-in-right"></i>
                          </button>
                        </td>
                      )}
                    </tr>
                  )

                  const theadAbsent = (
                    <thead>
                      <tr><th>N° / Matricule</th><th>Nom</th><th>Prénom</th><th>Type / Grade</th>{canSupervise && <th></th>}</tr>
                    </thead>
                  )

                  return (
                    <div className="card" style={{ marginBottom: '1rem' }}>
                      <div className="card-header-bar" style={{ background: '#fef2f2', borderBottom: '2px solid #fecaca' }}>
                        <span style={{ fontWeight: 600, color: '#dc2626' }}>
                          <i className="bi bi-person-x me-2"></i>Absents
                        </span>
                        <span className="badge" style={{ background: '#fee2e2', color: '#991b1b', fontSize: '0.78rem' }}>
                          {absentsFiltered.length} absent{absentsFiltered.length > 1 ? 's' : ''}
                          {(absAud.length > 0 || absFmt.length > 0 || absEnc.length > 0) && (
                            <span style={{ fontWeight: 400, marginLeft: '0.35rem', opacity: 0.95 }}>
                              ({absAud.length} aud.{absFmt.length > 0 ? ` · ${absFmt.length} form.` : ''}{absEnc.length > 0 ? ` · ${absEnc.length} enc.` : ''})
                            </span>
                          )}
                        </span>
                      </div>
                      <div className="card-body-flush">
                        {absAud.length > 0 && (
                          <>
                            {absentSubBar('bi-people', 'Étudiants absents', '#eff6ff', '#bfdbfe', '#1d4ed8', absAud.length)}
                            <table className="table mb-0">
                              {theadAbsent}
                              <tbody>{absAud.map(absentRow)}</tbody>
                            </table>
                          </>
                        )}
                        {absFmt.length > 0 && (
                          <>
                            {absentSubBar('bi-person-video3', 'Enseignants absents', '#faf5ff', '#e9d5ff', '#6b21a8', absFmt.length)}
                            <table className="table mb-0">
                              {theadAbsent}
                              <tbody>{absFmt.map(absentRow)}</tbody>
                            </table>
                          </>
                        )}
                        {absEnc.length > 0 && (
                          <>
                            {absentSubBar('bi-person-badge', 'Encadrants absents', '#fffceb', '#fdec8a', '#9c4221', absEnc.length)}
                            <table className="table mb-0">
                              {theadAbsent}
                              <tbody>{absEnc.map(absentRow)}</tbody>
                            </table>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })()}
              </>
          </div>
        )
      })()}

      {/* ── MODAL: FORÇAGE BADGEAGE EN MASSE (étudiants) ── */}
      {bulkForceModal && (
        <div className="modal-overlay" onClick={() => !bulkForceSaving && setBulkForceModal(false)}>
          <div className="modal-content" style={{ maxWidth: '520px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-shuffle me-2"></i>Forcer le badgeage des étudiants</h5>
              <button className="btn-close" disabled={bulkForceSaving} onClick={() => setBulkForceModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleBulkForceAuditeurs}>
              <div className="modal-body">
                <p style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '0.75rem' }}>
                  Pour chaque séance active du {formatDate(selectedPresenceDate)}
                  {selectedPresenceSessionId !== 'ALL' ? ' (séance sélectionnée uniquement)' : ''},
                  un tirage aléatoire badge <strong>entre 80 % et 95 %</strong> des étudiants encore absents.
                  Chaque étudiant badgé reçoit la <strong>durée planifiée de la séance</strong> (horaires EDT).
                  Les enseignants et encadrants ne sont pas concernés.
                </p>
                <label className="form-label">Motif <span className="text-danger">*</span></label>
                <textarea className="form-control" rows={3} required
                  placeholder="Ex. : Rattrapage collectif — problème réseau QR"
                  value={bulkForceMotif} onChange={e => setBulkForceMotif(e.target.value)} />
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" disabled={bulkForceSaving} onClick={() => setBulkForceModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-success" disabled={bulkForceSaving || !bulkForceMotif.trim()}>
                  {bulkForceSaving ? 'Traitement…' : 'Confirmer le forçage'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: FORÇAGE BADGEAGE ── */}
      {forceModal && (
        <div className="modal-overlay" onClick={() => setForceModal(false)}>
          <div className="modal-content" style={{ maxWidth: '480px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-check me-2"></i>Forcer un badgeage</h5>
              <button className="btn-close" onClick={() => setForceModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleForcePointage}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label fw-semibold">
                    {forceForm.type_personne === 'formateur' ? 'Enseignant' : forceForm.type_personne === 'encadrant' ? 'Encadrant' : 'Étudiant'}
                  </label>
                  {(() => {
                    const source = forceForm.type_personne === 'formateur' ? formateurs : forceForm.type_personne === 'encadrant' ? encadrantsAttendus : participants
                    const p = source.find(x => String(x.id) === String(forceForm.personne_id))
                    return p ? (
                      <div style={{ padding: '0.5rem 0.75rem', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px', fontWeight: 500 }}>
                        {p.nom} {p.prenom}
                      </div>
                    ) : null
                  })()}
                </div>
                {forceForm.type_personne === 'participant' && forceForm.action === 'ENTREE' && (
                  <p style={{ fontSize: '0.85rem', color: '#475569', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '0.65rem 0.75rem' }}>
                    <i className="bi bi-info-circle me-1"></i>
                    La présence sera enregistrée sur <strong>toute la durée planifiée de la séance</strong>
                    {(() => {
                      if (selectedPresenceSessionId === 'ALL') return ' (horaires EDT de la séance).'
                      const s = sessions.find(
                        x => x.date === selectedPresenceDate && String(x.id) === String(selectedPresenceSessionId),
                      )
                      if (!s?.heure_debut) return ' (horaires EDT de la séance).'
                      return s.heure_fin ? ` (${s.heure_debut} → ${s.heure_fin}).` : ` (${s.heure_debut}).`
                    })()}
                  </p>
                )}
                <div className="form-group">
                  <label className="form-label fw-semibold">Motif *</label>
                  <textarea className="form-control" rows={2} placeholder="Ex: téléphone en panne, problème réseau…"
                    required value={forceForm.motif} onChange={e => setForceForm({ ...forceForm, motif: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setForceModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-danger" disabled={forceSaving || !forceForm.personne_id || !forceForm.motif.trim()}>
                  {forceSaving ? 'Enregistrement…' : (
                    forceForm.type_personne === 'participant' && forceForm.action === 'ENTREE'
                      ? 'Forcer la présence'
                      : `Forcer ${forceForm.action === 'ENTREE' ? "l'entrée" : 'la sortie'}`
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: NOUVELLE SÉANCE ── */}
      {showNewSession && (
        <div className="modal-overlay" onClick={() => setShowNewSession(false)}>
          <div className="modal-content" style={{ maxWidth: '480px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-calendar-plus me-2"></i>Nouvelle séance</h5>
              <button className="btn-close" onClick={() => setShowNewSession(false)}>&times;</button>
            </div>
            <form onSubmit={handleCreateSession}>
              <div className="modal-body">
                {newSessionForm.date_journee && (
                  <div className="alert alert-light py-2 mb-3" style={{ fontSize: '0.88rem' }}>
                    <i className="bi bi-hash me-1"></i>
                    Numéro attribué automatiquement : <strong>{sessionNumeroLabel({ numero: nextSessionNumeroForDate(sessions, newSessionForm.date_journee) })}</strong>
                    <span className="text-muted ms-1">(créneau du jour)</span>
                  </div>
                )}
                <div className="form-group">
                  <label className="form-label">Intitulé</label>
                  <input type="text" className="form-control" value={newSessionForm.intitule}
                    onChange={e => setNewSessionForm({ ...newSessionForm, intitule: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">Date *</label>
                  <input type="date" className="form-control" required value={newSessionForm.date_journee}
                    onChange={e => setNewSessionForm({ ...newSessionForm, date_journee: e.target.value })} />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Heure début</label>
                    <input type="time" className="form-control" value={newSessionForm.heure_debut_prevue}
                      onChange={e => setNewSessionForm({ ...newSessionForm, heure_debut_prevue: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Heure fin</label>
                    <input type="time" className="form-control" value={newSessionForm.heure_fin_prevue}
                      onChange={e => setNewSessionForm({ ...newSessionForm, heure_fin_prevue: e.target.value })} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowNewSession(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={savingNewSession}>
                  {savingNewSession ? 'Création...' : 'Créer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MODAL: INSCRIRE AUDITEUR ── */}
      {showAddParticipant && (
        <div className="modal-overlay" onClick={() => setShowAddParticipant(false)}>
          <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-plus me-2"></i>Inscrire un étudiant</h5>
              <button className="btn-close" onClick={() => setShowAddParticipant(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="input-group mb-3">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input type="text" className="form-control" placeholder="Rechercher par nom, prénom, matricule…"
                  value={participantSearch} onChange={e => setParticipantSearch(e.target.value)} autoFocus />
              </div>
              {participantLoading && <div className="text-center py-2"><div className="spinner" style={{ width: 20, height: 20 }}></div></div>}
              {!participantLoading && allParticipants.length === 0 && (
                <p className="text-muted text-center py-2">Aucun étudiant disponible</p>
              )}
              {!participantLoading && allParticipants.length > 0 && (
                <div style={{ maxHeight: '320px', overflowY: 'auto' }}>
                  <table className="table table-sm">
                    <thead><tr><th>Matricule</th><th>Nom</th><th>Prénom</th><th></th></tr></thead>
                    <tbody>
                      {allParticipants.map(p => (
                        <tr key={p.id}>
                          <td><span className="badge-bg-info">{p.numero_matricule || p.matricule || '—'}</span></td>
                          <td>{p.nom}</td>
                          <td>{p.prenom}</td>
                          <td>
                            <button onClick={() => handleAddParticipant(p.id)} className="btn btn-outline-success btn-sm">
                              <i className="bi bi-plus"></i>
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              <Pagination
                page={participantPicker.page}
                totalPages={participantPicker.totalPages}
                onPageChange={participantPicker.setPage}
                totalItems={participantPicker.totalCount}
                pageSize={participantPicker.pageSize}
              />
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowAddParticipant(false)}>Fermer</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: ASSIGNER FORMATEUR ── */}
      {showAddFormateur && (
        <div className="modal-overlay" onClick={() => setShowAddFormateur(false)}>
          <div className="modal-content" style={{ maxWidth: '640px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-video3 me-2"></i>Assigner un enseignant</h5>
              <button className="btn-close" onClick={() => setShowAddFormateur(false)}>&times;</button>
            </div>
            <div className="modal-body">
              {formateurAssignError && (
                <div className="alert alert-danger py-2 small" role="alert">
                  <div className="d-flex align-items-start gap-2">
                    <i className="bi bi-exclamation-triangle-fill flex-shrink-0 mt-1" aria-hidden="true"></i>
                    <span style={{ lineHeight: 1.45, whiteSpace: 'pre-wrap' }}>{formateurAssignError}</span>
                  </div>
                </div>
              )}
              <div className="input-group mb-3">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input type="text" className="form-control" placeholder="Rechercher par nom, prénom…"
                  value={formateurSearch} onChange={e => { setFormateurSearch(e.target.value); setFormateurAssignError('') }} autoFocus />
              </div>
              {formateurLoading && <div className="text-center py-2"><div className="spinner" style={{ width: 20, height: 20 }}></div></div>}
              {!formateurLoading && allFormateurs.length === 0 && (
                <p className="text-muted text-center py-2">Aucun enseignant trouvé</p>
              )}
              {!formateurLoading && allFormateurs.length > 0 && (
                <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
                  {allFormateurs.map(f => (
                    <FormateurAssignPickerItem
                      key={f.id}
                      formateur={f}
                      onAssign={handleAddFormateur}
                    />
                  ))}
                </div>
              )}
              <Pagination
                page={formateurPicker.page}
                totalPages={formateurPicker.totalPages}
                onPageChange={formateurPicker.setPage}
                totalItems={formateurPicker.totalCount}
                pageSize={formateurPicker.pageSize}
              />
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowAddFormateur(false)}>Fermer</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: ÉDITION MODULE ── */}
      {editModuleOpen && (
        <div className="modal-overlay" onClick={() => setEditModuleOpen(false)}>
          <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-pencil me-2"></i>Modifier le module</h5>
              <button className="btn-close" onClick={() => setEditModuleOpen(false)}>&times;</button>
            </div>
            <form onSubmit={handleSaveModule}>
              <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                <div className="form-group">
                  <label className="form-label">Intitulé *</label>
                  <input type="text" className="form-control" required value={editModuleForm.intitule}
                    onChange={e => setEditModuleForm({ ...editModuleForm, intitule: e.target.value })} />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Grade</label>
                    <input type="text" className="form-control" value={editModuleForm.grade}
                      onChange={e => setEditModuleForm({ ...editModuleForm, grade: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Groupe</label>
                    <input type="text" className="form-control" value={editModuleForm.groupe}
                      onChange={e => setEditModuleForm({ ...editModuleForm, groupe: e.target.value })} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Vague</label>
                    <select className="form-control" value={editModuleForm.vague}
                      onChange={e => setEditModuleForm({ ...editModuleForm, vague: e.target.value })}>
                      <option value="">-- Sélectionner --</option>
                      {(refs.vagues || []).map(v => (
                        <option key={v.id} value={v.libelle}>{v.libelle}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">Statut</label>
                    <select className="form-control" value={editModuleForm.statut}
                      onChange={e => setEditModuleForm({ ...editModuleForm, statut: e.target.value })}>
                      <option value="PLANIFIEE">Planifiée</option>
                      <option value="EN_COURS">En cours</option>
                      <option value="SUSPENDUE">Suspendue</option>
                      <option value="TERMINEE">Terminée</option>
                    </select>
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Date début</label>
                    <input type="date" className="form-control" value={editModuleForm.date_debut}
                      onChange={e => setEditModuleForm({ ...editModuleForm, date_debut: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Date fin</label>
                    <input type="date" className="form-control" value={editModuleForm.date_fin}
                      onChange={e => setEditModuleForm({ ...editModuleForm, date_fin: e.target.value })} />
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Site</label>
                    {refs.sites?.length > 0 ? (
                      <select className="form-control" value={editModuleForm.site}
                        onChange={e => setEditModuleForm({ ...editModuleForm, site: e.target.value, batiment: '', salle: '' })}>
                        <option value="">-- Site --</option>
                        {refs.sites.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                      </select>
                    ) : (
                      <input type="text" className="form-control" value={editModuleForm.site}
                        onChange={e => setEditModuleForm({ ...editModuleForm, site: e.target.value })} />
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">Bâtiment</label>
                    {refs.batiments?.length > 0 ? (() => {
                      const siteObj = refs.sites?.find(s => s.nom === editModuleForm.site)
                      const filteredBatiments = siteObj ? refs.batiments.filter(b => b.site_id === siteObj.id) : refs.batiments
                      return (
                        <select className="form-control" value={editModuleForm.batiment}
                          onChange={e => setEditModuleForm({ ...editModuleForm, batiment: e.target.value, salle: '' })}>
                          <option value="">-- Bâtiment --</option>
                          {filteredBatiments.map(b => <option key={b.id} value={b.nom}>{b.nom}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="form-control" value={editModuleForm.batiment}
                        onChange={e => setEditModuleForm({ ...editModuleForm, batiment: e.target.value })} />
                    )}
                  </div>
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Salle</label>
                    {refs.salles?.length > 0 ? (() => {
                      const batObj = refs.batiments?.find(b => b.nom === editModuleForm.batiment)
                      const siteObj = refs.sites?.find(s => s.nom === editModuleForm.site)
                      const filteredSalles = batObj
                        ? refs.salles.filter(s => s.batiment_id === batObj.id)
                        : siteObj ? refs.salles.filter(s => s.site_id === siteObj.id) : refs.salles
                      return (
                        <select className="form-control" value={editModuleForm.salle}
                          onChange={e => setEditModuleForm({ ...editModuleForm, salle: e.target.value })}>
                          <option value="">-- Salle --</option>
                          {filteredSalles.map(s => <option key={s.id} value={s.nom}>{s.nom}</option>)}
                        </select>
                      )
                    })() : (
                      <input type="text" className="form-control" value={editModuleForm.salle}
                        onChange={e => setEditModuleForm({ ...editModuleForm, salle: e.target.value })} />
                    )}
                  </div>
                  <div className="form-group" />
                </div>
                <div className="form-group">
                  <label className="form-label">Volume horaire (h)</label>
                  <input type="number" className="form-control" min="0" step="0.5" value={editModuleForm.duree_prevue_heures}
                    onChange={e => setEditModuleForm({ ...editModuleForm, duree_prevue_heures: e.target.value })} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setEditModuleOpen(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={savingModule}>
                  {savingModule ? 'Enregistrement...' : 'Enregistrer'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modals */}
      <QRCodeModal
        isOpen={qrModalOpen}
        onClose={() => setQrModalOpen(false)}
        formationId={formationId}
        sessionId={selectedSessionId}
        moduleId={moduleId}
        moduleLabel={module?.intitule}
        moduleGroupe={module?.groupe}
      />

      {editSession && (
        <div className="modal-overlay" onClick={() => setEditSession(null)}>
          <div className="modal-content" style={{ maxWidth: '480px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-pencil me-2"></i>Modifier la séance {sessionNumeroLabel(editSession)}</h5>
              <button className="btn-close" onClick={() => setEditSession(null)}>&times;</button>
            </div>
            <form onSubmit={handleUpdateSession}>
              <div className="modal-body">
                <div className="form-group">
                  <label className="form-label">Numéro (dans la journée)</label>
                  <input type="text" className="form-control" readOnly disabled value={sessionNumeroLabel(editSession)}
                    title="Identifiant unique par date — utilisé pour détecter les doublons" />
                  <small className="text-muted">Une seule séance {sessionNumeroLabel(editSession)} par date. Changer la date peut entrer en conflit avec une autre séance.</small>
                </div>
                <div className="form-group">
                  <label className="form-label">Intitulé *</label>
                  <input type="text" className="form-control" required value={editSessionForm.intitule}
                    onChange={e => setEditSessionForm({ ...editSessionForm, intitule: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">Date *</label>
                  <input type="date" className="form-control" required value={editSessionForm.date_journee}
                    onChange={e => setEditSessionForm({ ...editSessionForm, date_journee: e.target.value })} />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Heure début</label>
                    <input type="time" className="form-control" value={editSessionForm.heure_debut_prevue}
                      onChange={e => setEditSessionForm({ ...editSessionForm, heure_debut_prevue: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Heure fin</label>
                    <input type="time" className="form-control" value={editSessionForm.heure_fin_prevue}
                      onChange={e => setEditSessionForm({ ...editSessionForm, heure_fin_prevue: e.target.value })} />
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setEditSession(null)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={savingSession}>
                  {savingSession ? 'Enregistrement...' : 'Enregistrer'}
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
          onConfirm={() => { setConfirmDialog(null); confirmDialog.onConfirm() }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {archiveOpen && module && (
        <TripleConfirmModal
          title="Archivage du module"
          subject={module.intitule}
          onConfirm={confirmArchiveModule}
          onCancel={() => setArchiveOpen(false)}
        />
      )}

      {/* ── MODAL: ASSIGNER ENCADRANT ── */}
      {showAssignSup && (
        <div className="modal-overlay" onClick={() => setShowAssignSup(false)}>
          <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-gear me-2"></i>Assigner un encadrant</h5>
              <button className="btn-close" onClick={() => setShowAssignSup(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <p className="text-muted" style={{ fontSize: '0.88rem' }}>
                Choisir l'encadrant superviseur pour le module « <strong>{module.intitule}</strong> ».
              </p>
              {assignSupError && <div className="error-message">{assignSupError}</div>}
              {module.superviseur_id && (
                <button
                  type="button"
                  className={`btn btn-sm mb-3 ${!selectedSup ? 'btn-warning' : 'btn-outline-secondary'}`}
                  onClick={() => setSelectedSup('')}
                >
                  <i className="bi bi-person-x me-1"></i>Retirer l'encadrant
                </button>
              )}
              <div className="input-group mb-3">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input
                  type="text"
                  className="form-control"
                  placeholder="Rechercher par nom, identifiant, matricule…"
                  value={encadrantSearch}
                  onChange={e => setEncadrantSearch(e.target.value)}
                  autoFocus
                />
              </div>
              {encadrantLoading && (
                <div className="text-center text-muted py-2">
                  <div className="spinner" style={{ width: 20, height: 20 }}></div>
                </div>
              )}
              {!encadrantLoading && encadrants.length === 0 && (
                <p className="text-muted text-center py-2">Aucun encadrant trouvé</p>
              )}
              {!encadrantLoading && encadrants.length > 0 && (
                <div style={{ maxHeight: '320px', overflowY: 'auto', overflowX: 'auto' }}>
                  <table className="table table-sm">
                    <thead>
                      <tr>
                        <th>Nom</th>
                        <th>Identifiant</th>
                        <th>Matricule</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {encadrants.map(u => {
                        const fullName = `${u.first_name || ''} ${u.last_name || ''}`.trim() || u.username
                        const isSelected = String(selectedSup) === String(u.id)
                        return (
                          <tr
                            key={u.id}
                            onClick={() => setSelectedSup(String(u.id))}
                            style={{ cursor: 'pointer', background: isSelected ? '#f0f6fd' : undefined }}
                          >
                            <td>{fullName}</td>
                            <td>{u.username}</td>
                            <td>{u.matricule || '—'}</td>
                            <td>
                              {isSelected && <i className="bi bi-check-circle-fill text-success"></i>}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}
              <Pagination
                page={encadrantPicker.page}
                totalPages={encadrantPicker.totalPages}
                onPageChange={encadrantPicker.setPage}
                totalItems={encadrantPicker.totalCount}
                pageSize={encadrantPicker.pageSize}
              />
            </div>
            <div className="modal-footer">
              <button className="btn btn-secondary" onClick={() => setShowAssignSup(false)}>Annuler</button>
              <button
                className="btn btn-dfrc"
                onClick={handleAssignSuperviseur}
                disabled={assignSupSaving}
              >
                {assignSupSaving ? 'Enregistrement...' : 'Enregistrer'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
