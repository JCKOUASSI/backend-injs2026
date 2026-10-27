import { useState, useEffect, useRef } from 'react'
import { useParams, Link } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import QRCodeModal from '../components/QRCodeModal'
import ConfirmModal from '../components/ConfirmModal'
import TripleConfirmModal from '../components/TripleConfirmModal'
import { useToast } from '../context/ToastContext'
import { formatDate } from '../utils/dates'
import { fmtHeuresLabel, sommeSeancesHeures, sessionNumeroLabel } from '../utils/duree'
import { LIST_STORAGE_KEYS } from '../utils/listFilters'
import { useListNavigationState, useListReturn } from '../hooks/useListReturn'
import { useClientPagination, TABLE_PAGE_SIZE, PICKER_PAGE_SIZE } from '../hooks/useClientPagination'
import { usePickerPagination } from '../hooks/usePickerPagination'
import Pagination from '../components/Pagination'
import {
  canMutateFormations,
  canArchiveModuleFromUser,
  canPresenceAction,
  canSuperviseSessions,
  canViewPresences,
} from '../utils/roles'
import { formatApiErrors } from '../utils/apiErrors'

export default function FormationDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const listNavState = useListNavigationState()
  const backToModulesList = useListReturn('/modules', LIST_STORAGE_KEYS.modules)

  // Core state
  const [formation, setFormation] = useState(null)
  const [sessions, setSessions] = useState([])
  const [participants, setParticipants] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // Tabs
  const [activeTab, setActiveTab] = useState('info')

  // QR modal
  const [qrModalOpen, setQrModalOpen] = useState(false)
  const [selectedSessionId, setSelectedSessionId] = useState(null)
  const [selectedQrModule, setSelectedQrModule] = useState(null)

  // Session creation
  const [newSession, setNewSession] = useState({ date_journee: '', numero: 1, heure_debut_prevue: '', heure_fin_prevue: '' })
  const [showNewSession, setShowNewSession] = useState(false)

  // Présences dashboard
  const [dashboard, setDashboard] = useState(null)
  const [dashboardLoading, setDashboardLoading] = useState(false)
  const [dashboardDate, setDashboardDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [dashboardError, setDashboardError] = useState('')
  const [dashboardSession, setDashboardSession] = useState(null) // null = toutes séances

  // Assign superviseur
  const [showAssignModal, setShowAssignModal] = useState(false)
  const [superviseurs, setSuperviseurs] = useState([])
  const [selectedSup, setSelectedSup] = useState('')
  const [assignError, setAssignError] = useState('')
  const [encadrantSearch, setEncadrantSearch] = useState('')
  const [encadrantLoading, setEncadrantLoading] = useState(false)

  // Add participant to formation
  const [showAddParticipant, setShowAddParticipant] = useState(false)
  const [allParticipants, setAllParticipants] = useState([])
  const [addSearch, setAddSearch] = useState('')
  const [addLoading, setAddLoading] = useState(false)

  // Formateurs tab
  const [formateurs, setFormateurs] = useState([])
  const [showAddFormateur, setShowAddFormateur] = useState(false)
  const [allFormateurs, setAllFormateurs] = useState([])
  const [formateurSearch, setFormateurSearch] = useState('')
  const [formateurLoading, setFormateurLoading] = useState(false)

  // Présences search
  const [presenceSearch, setPresenceSearch] = useState('')

  // Close session / force badge
  const [closingSession, setClosingSession] = useState(null)
  const [badgingEntree, setBadgingEntree] = useState(null)

  // Motif popup for forced badging
  const [forceMotifDialog, setForceMotifDialog] = useState(null) // { personne, action: 'ENTREE'|'SORTIE' }
  const [forceMotifText, setForceMotifText] = useState('')
  const [forceMotifError, setForceMotifError] = useState('')
  const [forceHeureEntree, setForceHeureEntree] = useState('')
  const [forceHeureSortie, setForceHeureSortie] = useState('')

  const { showToast } = useToast()
  const [confirmDialog, setConfirmDialog] = useState(null)
  const [archiveTarget, setArchiveTarget] = useState(null)

  const participantsPager = useClientPagination(participants, TABLE_PAGE_SIZE, [id, participants.length])
  const formateursPager = useClientPagination(formateurs, TABLE_PAGE_SIZE, [id, formateurs.length])
  const participantPicker = usePickerPagination(showAddParticipant)
  const formateurPicker = usePickerPagination(showAddFormateur)
  const encadrantPicker = usePickerPagination(showAssignModal)

  // Import séances Excel
  const [importingSeances, setImportingSeances] = useState(false)
  const [importSeancesMsg, setImportSeancesMsg] = useState(null)
  const importFileRef = useRef()

  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  useEffect(() => { loadFormationData() }, [id])

  const loadFormationData = async () => {
    setLoading(true)
    try {
      const response = await api.get(`/formations/${id}/detail/`)
      setFormation(response.data)
      const rawSessions = Array.isArray(response.data.sessions) ? response.data.sessions : []
      rawSessions.sort((a, b) => {
        const dateA = `${a.date || ''}${a.heure_debut || ''}${String(a.numero || 0).padStart(4, '0')}`
        const dateB = `${b.date || ''}${b.heure_debut || ''}${String(b.numero || 0).padStart(4, '0')}`
        return dateA.localeCompare(dateB)
      })
      setSessions(rawSessions)
      const p = response.data.participants || response.data.participants_attendus || []
      setParticipants(Array.isArray(p) ? p : [])
    } catch (err) {
      setError('Erreur lors du chargement de la formation')
    } finally { setLoading(false) }
  }

  const loadFormateurs = async () => {
    try {
      const res = await api.get(`/formations/${id}/formateurs/`)
      setFormateurs(Array.isArray(res.data) ? res.data : [])
    } catch (err) {
      console.error('Chargement enseignants formation:', err)
      showToast(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger les enseignants.' }), 'error')
    }
  }

  useEffect(() => {
    if (activeTab === 'formateurs') loadFormateurs()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [activeTab])

  const loadAllFormateurs = async () => {
    setFormateurLoading(true)
    try {
      const params = new URLSearchParams({ page: formateurPicker.page, page_size: PICKER_PAGE_SIZE })
      if (formateurSearch) params.set('search', formateurSearch)
      const res = await api.get(`/formations/formateurs/list/?${params}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      const assigned = new Set(formateurs.map(f => f.id))
      setAllFormateurs(data.filter(f => !assigned.has(f.id)))
      formateurPicker.applyResponse(res.data, data.length)
    } catch (err) {
      console.error('Chargement liste enseignants:', err)
      showToast(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger la liste des enseignants.' }), 'error')
    } finally { setFormateurLoading(false) }
  }

  const openAddFormateur = () => {
    setFormateurSearch('')
    loadAllFormateurs()
    setShowAddFormateur(true)
  }

  useEffect(() => {
    if (showAddFormateur) formateurPicker.resetPage()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [formateurSearch])

  useEffect(() => {
    if (!showAddFormateur) return
    const t = setTimeout(() => loadAllFormateurs(), 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [formateurSearch, showAddFormateur, formateurPicker.page])

  const handleAddFormateur = async (formateurId) => {
    try {
      await api.post(`/formations/${id}/formateurs/add/`, { formateur_id: formateurId })
      loadFormateurs()
      loadAllFormateurs()
      showToast('Enseignant ajouté')
    } catch (err) {
      showToast(err.response?.data?.detail || "Erreur lors de l'ajout", 'error')
    }
  }

  const handleRemoveFormateur = (formateurId) => {
    setConfirmDialog({
      message: 'Retirer cet enseignant de la formation ?',
      onConfirm: async () => {
        try {
          await api.delete(`/formations/${id}/formateurs/${formateurId}/remove/`)
          loadFormateurs()
          showToast('Enseignant retiré')
        } catch (err) {
          showToast(err.response?.data?.detail || 'Erreur lors du retrait', 'error')
        }
      }
    })
  }

  const loadDashboard = async (date, sessionId) => {
    setDashboardLoading(true)
    setDashboardError('')
    try {
      const params = new URLSearchParams()
      if (date) params.set('date', date)
      if (sessionId) params.set('session_id', sessionId)
      const response = await api.get(`/formations/${id}/dashboard/?${params}`)
      setDashboard(response.data)
    } catch (err) {
      setDashboard(null)
      if (err.response?.status === 403) {
        setDashboardError('Accès non autorisé au tableau de présences.')
      } else if (err.response?.status === 404) {
        setDashboardError('Formation introuvable.')
      } else {
        setDashboardError('Erreur lors du chargement des présences.')
      }
    } finally { setDashboardLoading(false) }
  }

  useEffect(() => {
    if (activeTab === 'presences') loadDashboard(dashboardDate, dashboardSession)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [activeTab, dashboardDate, dashboardSession])

  const isJourPasse = (dateStr) => {
    const today = new Date().toISOString().slice(0, 10)
    return dateStr && dateStr < today
  }

  const buildTimestamp = (dateStr, heureStr) => {
    if (!dateStr || !heureStr) return null
    return `${dateStr}T${heureStr}:00`
  }

  const closeSession = async (personne, motif, heureSortie) => {
    setClosingSession(personne.id)
    try {
      const payload = {
        action: 'SORTIE',
        personne_id: personne.id,
        type_personne: personne.type_personne || 'participant',
        motif,
        date_journee: dashboardDate,
      }
      const ts = buildTimestamp(dashboardDate, heureSortie)
      if (ts) payload.timestamp_sortie = ts
      await api.post(`/formations/${id}/force-pointage/`, payload)
      await loadDashboard(dashboardDate)
      showToast('Session fermée')
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de la fermeture de session', 'error')
    } finally { setClosingSession(null) }
  }

  const badgerEntree = async (personne, motif, heureEntree, heureSortie) => {
    setBadgingEntree(personne.id)
    const isAuditeur = (personne.type_personne || 'participant') === 'participant'
    try {
      const payload = {
        action: 'ENTREE',
        personne_id: personne.id,
        type_personne: personne.type_personne || 'participant',
        motif,
        date_journee: dashboardDate,
      }
      const tsEntree = buildTimestamp(dashboardDate, heureEntree)
      const tsSortie = buildTimestamp(dashboardDate, heureSortie)
      if (tsEntree) payload.timestamp_entree = tsEntree
      if (tsSortie) payload.timestamp_sortie = tsSortie
      const res = await api.post(`/formations/${id}/force-pointage/`, payload)
      await loadDashboard(dashboardDate)
      showToast(res.data?.detail || (isAuditeur ? 'Présence forcée — durée planifiée de la séance' : 'Entrée badgée'))
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors du badgeage', 'error')
    } finally { setBadgingEntree(null) }
  }

  const openForceMotifDialog = (personne, action) => {
    setForceMotifText('')
    setForceMotifError('')
    setForceHeureEntree('')
    setForceHeureSortie('')
    setForceMotifDialog({ personne, action })
  }

  const submitForceMotif = () => {
    if (!forceMotifText.trim()) {
      setForceMotifError('Le motif est obligatoire.')
      return
    }
    const jourPasse = isJourPasse(dashboardDate)
    if (jourPasse && forceMotifDialog.action === 'ENTREE' && !forceHeureEntree) {
      setForceMotifError("L'heure d'entrée est obligatoire pour un jour passé.")
      return
    }
    const { personne, action } = forceMotifDialog
    setForceMotifDialog(null)
    if (action === 'ENTREE') badgerEntree(personne, forceMotifText.trim(), forceHeureEntree || null, forceHeureSortie || null)
    else closeSession(personne, forceMotifText.trim(), forceHeureSortie || null)
  }

  const loadSuperviseurs = async () => {
    setEncadrantLoading(true)
    try {
      const params = new URLSearchParams({
        role: 'ENCADRANT',
        page: encadrantPicker.page,
      })
      if (encadrantSearch) params.set('search', encadrantSearch)
      const res = await api.get(`/auth/users/?${params}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      setSuperviseurs(data)
      encadrantPicker.applyResponse(res.data, data.length)
    } catch (err) {
      console.error('Chargement encadrants:', err)
      setAssignError(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger la liste des encadrants.' }))
    } finally { setEncadrantLoading(false) }
  }

  const openAssignModal = () => {
    setSelectedSup(formation?.superviseur || '')
    setAssignError('')
    setEncadrantSearch('')
    setShowAssignModal(true)
  }

  useEffect(() => {
    if (showAssignModal) encadrantPicker.resetPage()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [encadrantSearch])

  useEffect(() => {
    if (!showAssignModal) return
    const t = setTimeout(() => loadSuperviseurs(), 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [encadrantSearch, showAssignModal, encadrantPicker.page])

  const handleAssignSuperviseur = async () => {
    if (!selectedSup) { setAssignError('Veuillez sélectionner un encadrant'); return }
    try {
      await api.post(`/formations/${id}/assign-superviseur/`, { superviseur_id: selectedSup })
      setShowAssignModal(false)
      loadFormationData()
    } catch (err) {
      setAssignError(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de l\'assignation de l\'encadrant.' }))
    }
  }

  const loadAllParticipants = async () => {
    setAddLoading(true)
    try {
      const params = new URLSearchParams({ page: participantPicker.page, page_size: PICKER_PAGE_SIZE })
      if (addSearch) params.set('search', addSearch)
      const res = await api.get(`/formations/participants/list/?${params}`)
      const data = Array.isArray(res.data) ? res.data : (res.data.results || [])
      const enrolled = new Set(participants.map(p => p.id))
      setAllParticipants(data.filter(p => !enrolled.has(p.id)))
      participantPicker.applyResponse(res.data, data.length)
    } catch (err) {
      console.error('Chargement étudiants:', err)
      showToast(formatApiErrors(err.response?.data, { fallback: 'Impossible de charger la liste des étudiants.' }), 'error')
    } finally { setAddLoading(false) }
  }

  const openAddParticipant = () => {
    setAddSearch('')
    loadAllParticipants()
    setShowAddParticipant(true)
  }

  useEffect(() => {
    if (showAddParticipant) participantPicker.resetPage()
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [addSearch])

  useEffect(() => {
    if (!showAddParticipant) return
    const t = setTimeout(() => loadAllParticipants(), 300)
    return () => clearTimeout(t)
  // eslint-disable-next-line react-hooks/exhaustive-deps -- rechargement intentionnel : la fonction de chargement n’est pas mémoïsée (l’ajouter provoquerait une boucle) ; les dépendances de données présentes pilotent déjà le (re)chargement.
  }, [addSearch, showAddParticipant, participantPicker.page])

  const handleAddParticipant = async (participantId) => {
    try {
      await api.post(`/formations/${id}/participants/add/`, { participant_id: participantId })
      loadFormationData()
      loadAllParticipants()
      showToast('Étudiant ajouté')
    } catch (err) {
      showToast(err.response?.data?.detail || err.response?.data?.participant_id || "Erreur lors de l'ajout", 'error')
    }
  }

  const handleRemoveParticipant = (participantId) => {
    setConfirmDialog({
      message: 'Retirer cet étudiant de la formation ?',
      onConfirm: async () => {
        try {
          await api.delete(`/formations/${id}/participants/${participantId}/remove/`)
          loadFormationData()
          showToast('Étudiant retiré')
        } catch (err) {
          showToast(err.response?.data?.detail || 'Erreur lors du retrait', 'error')
        }
      }
    })
  }

  const _downloadBlob = (blob, type, filename) => {
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }

  const handleExport = async (type) => {
    try {
      const { blob } = await api.getBlob(`/exports/formation/${id}/${type}/`)
      _downloadBlob(blob, type, `rapport_formation_${id}.${type === 'pdf' ? 'pdf' : 'xlsx'}`)
    } catch (err) {
      console.error('[handleExport] erreur:', err, err.response)
      showToast(err.response?.data?.detail || `Erreur export ${type.toUpperCase()}.`, 'error')
    }
  }

  const handleExportSession = async (sessionId, sessionLabel, type) => {
    try {
      const { blob } = await api.getBlob(`/exports/session/${sessionId}/${type}/`)
      const safeName = (sessionLabel || `session_${sessionId}`).replace(/[^a-z0-9]/gi, '_').toLowerCase()
      _downloadBlob(blob, type, `rapport_${safeName}.${type === 'pdf' ? 'pdf' : 'xlsx'}`)
    } catch (err) {
      console.error('[handleExportSession] erreur:', err, err.response)
      showToast(err.response?.data?.detail || `Erreur export ${type.toUpperCase()} séance.`, 'error')
    }
  }

  const [startingSession, setStartingSession] = useState(null)
  const [stoppingSession, setStoppingSession] = useState(null)
  const [editSession, setEditSession] = useState(null)
  const [editSessionForm, setEditSessionForm] = useState({ intitule: '', date_journee: '', heure_debut_prevue: '', heure_fin_prevue: '' })
  const [savingSession, setSavingSession] = useState(false)

  // Session handlers
  const handleStartSession = (sid, label) => {
    setConfirmDialog({
      message: `Démarrer la séance « ${label} » ?`,
      detail: "Attention : la séance passera immédiatement en cours et les badgeages seront ouverts.",
      onConfirm: async () => {
        setStartingSession(sid)
        try { await api.post(`/formations/${id}/sessions/${sid}/start/`); loadFormationData(); showToast('Séance démarrée') }
        catch (err) { showToast(err.response?.data?.detail || 'Erreur lors du démarrage', 'error') }
        finally { setStartingSession(null) }
      },
    })
  }
  const handleStopSession = (sid, label) => {
    setConfirmDialog({
      message: `Terminer la séance «\u00A0${label}\u00A0» ?`,
      detail: 'Cette action est irréversible.',
      onConfirm: async () => {
        setStoppingSession(sid)
        try { await api.post(`/formations/${id}/sessions/${sid}/stop/`); loadFormationData(); showToast('Séance terminée') }
        catch (err) { showToast(err.response?.data?.detail || "Erreur lors de l'arrêt", 'error') }
        finally { setStoppingSession(null) }
      }
    })
  }
  const handleDeleteSession = (sid) => {
    setConfirmDialog({
      message: 'Supprimer cette séance ?',
      onConfirm: async () => {
        try { await api.delete(`/formations/${id}/sessions/${sid}/delete/`); loadFormationData(); showToast('Séance supprimée') }
        catch (err) { showToast(err.response?.data?.detail || 'Erreur lors de la suppression', 'error') }
      }
    })
  }
  const handleCreateSession = async (e) => {
    e.preventDefault()
    try {
      const nextNumero = sessions.length + 1
      const payload = {
        ...newSession,
        numero: nextNumero,
        intitule: `Séance ${nextNumero}`,
      }
      await api.post(`/formations/${id}/sessions/new/`, payload)
      setShowNewSession(false)
      setNewSession({ date_journee: '', heure_debut_prevue: '', heure_fin_prevue: '' })
      loadFormationData()
      showToast('Séance créée')
    } catch (err) { showToast(err.response?.data?.detail || 'Erreur lors de la création', 'error') }
  }

  const handleGenerateQR = (session) => {
    setSelectedSessionId(session.id)
    setSelectedQrModule({
      id: session.module_id,
      label: session.module_intitule,
      groupe: session.module_groupe,
    })
    setQrModalOpen(true)
  }

  const openEditSession = (s) => {
    setEditSession(s)
    setEditSessionForm({
      intitule: s.intitule || `Séance ${s.numero}`,
      date_journee: s.date || '',
      heure_debut_prevue: s.heure_debut || '',
      heure_fin_prevue: s.heure_fin || '',
    })
  }

  const handleUpdateSession = async (e) => {
    e.preventDefault()
    if (!editSessionForm.date_journee) {
      showToast('La date de la séance est obligatoire.', 'error')
      return
    }
    setSavingSession(true)
    try {
      const res = await api.patch(`/formations/${id}/sessions/${editSession.id}/update/`, editSessionForm)
      setEditSession(null)
      loadFormationData()
      showToast(res.data?.detail || 'Séance modifiée')
    } catch (err) {
      showToast(formatApiErrors(err.response?.data, { fallback: 'Erreur lors de la modification de la séance.' }), 'error')
    } finally { setSavingSession(false) }
  }

  const confirmArchiveModule = async () => {
    const target = archiveTarget
    if (!target) return
    setArchiveTarget(null)
    try {
      await api.post(`/formations/${id}/modules/${target.moduleId}/archive/`)
      showToast('Module archivé — visible uniquement dans l\'espace Archives')
      loadFormationData()
    } catch (err) {
      showToast(err.response?.data?.detail || 'Erreur lors de l\'archivage', 'error')
    }
  }

  const getStatutBadge = (s) => ({ 'PLANIFIEE': 'badge-planifiee', 'EN_COURS': 'badge-en-cours', 'TERMINEE': 'badge-terminee', 'SUSPENDUE': 'badge-suspendue' }[s] || 'badge-info')
  const getStatutLabel = (s) => ({ 'PLANIFIEE': 'Planifié', 'EN_COURS': 'En cours', 'TERMINEE': 'Terminé', 'SUSPENDUE': 'Suspendu' }[s] || s)

  const canEdit = canMutateFormations(user)
  const canSupervise = canSuperviseSessions(user)
  const canManageSessions = canMutateFormations(user)
  const canArchive = canArchiveModuleFromUser(user)
  const canImport = user?.role === 'SECRETARIAT'
  const canViewPresencesTab = canViewPresences(user)

  if (loading) return <div className="loading"><div className="spinner"></div></div>
  if (error || !formation) return (
    <div className="card"><div className="card-body">
      <div className="error-message">{error || 'Formation non trouvée'}</div>
      <button onClick={backToModulesList} className="btn btn-secondary mt-2"><i className="bi bi-arrow-left me-1"></i>Retour</button>
    </div></div>
  )

  const tabStyle = (tab) => ({
    padding: '0.6rem 0.9rem', cursor: 'pointer', fontWeight: 500,
    color: activeTab === tab ? 'var(--ci-success)' : 'var(--text-muted)',
    background: 'none', border: 'none', whiteSpace: 'nowrap', flexShrink: 0,
    borderBottom: `3px solid ${activeTab === tab ? 'var(--ci-success)' : 'transparent'}`,
  })

  const formationModules = (Array.isArray(formation.modules) && formation.modules.length)
    ? formation.modules
    : (formation.modules_list || [])

  return (
    <div>
      {/* Header */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div className="card-header-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <span style={{ fontWeight: 600, fontSize: '1.05rem' }}><i className="bi bi-mortarboard me-2"></i>{formation.formation}</span>
            {formationModules.length > 0 && (
              <span className="badge-bg-secondary">{formationModules.length} module{formationModules.length > 1 ? 's' : ''}</span>
            )}
            <span className={`badge ${getStatutBadge(formation.statut)}`}>{getStatutLabel(formation.statut)}</span>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button onClick={() => handleExport('pdf')} className="btn btn-outline-danger btn-sm" title="Exporter PDF (toutes les séances)">
              <i className="bi bi-file-earmark-pdf me-1"></i>PDF — Toutes séances
            </button>
            <button onClick={() => handleExport('excel')} className="btn btn-outline-success btn-sm" title="Exporter Excel (toutes les séances)">
              <i className="bi bi-file-earmark-excel me-1"></i>Excel — Toutes séances
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', borderBottom: '1px solid #e2e8f0', paddingLeft: '1rem', overflowX: 'auto', WebkitOverflowScrolling: 'touch' }}>
          {[
            { key: 'info', label: 'Informations', icon: 'bi-info-circle', show: true },
            { key: 'presences', label: 'Présences', icon: 'bi-person-check', show: canViewPresencesTab },
            { key: 'seances', label: `Séances (${sessions.length})`, icon: 'bi-calendar3', show: true },
            { key: 'participants', label: `Étudiants (${participants.length})`, icon: 'bi-people', show: true },
            { key: 'formateurs', label: `Enseignants (${formateurs.length})`, icon: 'bi-person-video3', show: true },
          ].filter(t => t.show).map(t => (
            <button key={t.key} style={tabStyle(t.key)} onClick={() => setActiveTab(t.key)}>
              <i className={`bi ${t.icon} me-1`}></i>{t.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── TAB: INFO ── */}
      {activeTab === 'info' && (
        <div className="row">
          <div className="col-lg-8">
            <div className="card">
              <div className="card-header-bar">
                <span><i className="bi bi-geo-alt me-2 text-muted"></i>Lieu & Calendrier</span>
              </div>
              <div className="card-body">
                {[
                  { icon: 'bi-building',        label: 'Site',      value: formation.site },
                  { icon: 'bi-door-open',        label: 'Bâtiment',  value: formation.batiment },
                  { icon: 'bi-grid-1x2',         label: 'Salle',     value: formation.salle },
                  { icon: 'bi-calendar',         label: 'Début',     value: formatDate(formation.date_debut) },
                  { icon: 'bi-calendar-check',   label: 'Fin',       value: formatDate(formation.date_fin) },
                  { icon: 'bi-clock',            label: 'Durée',     value: fmtHeuresLabel(sommeSeancesHeures(sessions)) },
                ].map(({ icon, label, value }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', padding: '0.55rem 0', borderBottom: '1px solid #f1f5f9' }}>
                    <i className={`bi ${icon} me-2`} style={{ width: 18, color: 'var(--ci-warning)', flexShrink: 0 }}></i>
                    <span style={{ minWidth: 90, fontWeight: 600, fontSize: '0.88rem', color: '#64748b' }}>{label}</span>
                    <span style={{ fontSize: '0.92rem' }}>{value || <span className="text-muted">—</span>}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="card">
              <div className="card-header-bar">
                <span><i className="bi bi-person-lines-fill me-2 text-muted"></i>Classification & Intervenants</span>
              </div>
              <div className="card-body">
                {[
                  { icon: 'bi-tag',          label: 'Catégorie',   value: formation.categorie },
                  { icon: 'bi-award',        label: 'Grade',       value: formation.grade },
                  { icon: 'bi-people',       label: 'Groupe',      value: formation.groupe },
                ].map(({ icon, label, value }) => (
                  <div key={label} style={{ display: 'flex', alignItems: 'center', padding: '0.55rem 0', borderBottom: '1px solid #f1f5f9' }}>
                    <i className={`bi ${icon} me-2`} style={{ width: 18, color: 'var(--ci-warning)', flexShrink: 0 }}></i>
                    <span style={{ minWidth: 90, fontWeight: 600, fontSize: '0.88rem', color: '#64748b' }}>{label}</span>
                    <span style={{ fontSize: '0.92rem' }}>{value || <span className="text-muted">—</span>}</span>
                  </div>
                ))}

                <div style={{ display: 'flex', alignItems: 'flex-start', padding: '0.55rem 0', borderBottom: '1px solid #f1f5f9' }}>
                  <i className="bi bi-book me-2" style={{ width: 18, color: 'var(--ci-warning)', flexShrink: 0, marginTop: 2 }}></i>
                  <span style={{ minWidth: 90, fontWeight: 600, fontSize: '0.88rem', color: '#64748b', flexShrink: 0 }}>Module(s)</span>
                  <div>
                    {formationModules.length > 0 ? (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                        {formationModules.map(m => (
                          <Link
                            key={m.id}
                            to={`/formations/${id}/modules/${m.id}`}
                            state={listNavState}
                            style={{
                              background: '#f5f3ff', color: '#5b21b6',
                              border: '1px solid #ddd6fe', borderRadius: 6,
                              padding: '0.15rem 0.55rem', fontSize: '0.82rem', fontWeight: 500,
                              textDecoration: 'none',
                            }}
                          >
                            {m.intitule}
                          </Link>
                        ))}
                      </div>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                    <div style={{ fontSize: '0.78rem', color: '#64748b', marginTop: 4 }}>
                      Une formation peut regrouper un ou plusieurs modules.
                    </div>
                  </div>
                </div>

                {/* Encadrant */}
                <div style={{ display: 'flex', alignItems: 'center', padding: '0.55rem 0', borderBottom: '1px solid #f1f5f9' }}>
                  <i className="bi bi-person-badge me-2" style={{ width: 18, color: 'var(--ci-warning)', flexShrink: 0 }}></i>
                  <span style={{ minWidth: 90, fontWeight: 600, fontSize: '0.88rem', color: '#64748b' }}>Encadrant</span>
                  <span style={{ fontSize: '0.92rem' }}>
                    {formation.superviseur_nom || <span className="text-muted">—</span>}
                    {canEdit && (
                      <button onClick={openAssignModal} className="btn btn-outline-primary btn-sm ms-2" style={{ padding: '0.1rem 0.4rem', fontSize: '0.75rem' }}>
                        <i className="bi bi-pencil"></i>
                      </button>
                    )}
                  </span>
                </div>

                {/* Formateurs */}
                <div style={{ display: 'flex', alignItems: 'flex-start', padding: '0.55rem 0' }}>
                  <i className="bi bi-person-video3 me-2" style={{ width: 18, color: 'var(--ci-warning)', flexShrink: 0, marginTop: 2 }}></i>
                  <span style={{ minWidth: 90, fontWeight: 600, fontSize: '0.88rem', color: '#64748b', flexShrink: 0 }}>Enseignant(s)</span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                    {formation.formateurs?.length > 0
                      ? formation.formateurs.map(f => (
                          <span key={f.id} style={{
                            background: '#f0f7ff', color: '#11407d',
                            border: '1px solid #c6ddf6', borderRadius: 6,
                            padding: '0.15rem 0.55rem', fontSize: '0.82rem', fontWeight: 500,
                          }}>
                            <i className="bi bi-person-fill me-1"></i>{f.prenom} {f.nom}
                          </span>
                        ))
                      : <span className="text-muted" style={{ fontSize: '0.92rem' }}>—</span>}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div className="col-lg-4">
            <div className="card" style={{ borderTop: '4px solid var(--ci-success)' }}>
              <div className="card-body text-center" style={{ padding: '1.5rem 1rem' }}>
                <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: 1, color: '#94a3b8', marginBottom: '1rem' }}>Résumé</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                  {[
                    { value: sessions.length,      label: 'Séances',   color: 'var(--ci-success)',  icon: 'bi-calendar3' },
                    { value: participants.length,   label: 'Étudiants', color: 'var(--ci-blue)',   icon: 'bi-people' },
                    { value: sessions.filter(s => s.terminee).length, label: 'Terminées', color: '#805ad5', icon: 'bi-check-circle' },
                    { value: formation.formateurs?.length || 0, label: 'Enseignants', color: 'var(--ci-warning)', icon: 'bi-person-video3' },
                  ].map(({ value, label, color, icon }) => (
                    <div key={label} style={{ background: '#f8fafc', borderRadius: 10, padding: '0.85rem 0.5rem' }}>
                      <i className={`bi ${icon}`} style={{ color, fontSize: '1.1rem' }}></i>
                      <div style={{ fontSize: '1.6rem', fontWeight: 700, color, lineHeight: 1.2, marginTop: '0.25rem' }}>{value}</div>
                      <small style={{ color: '#94a3b8', fontSize: '0.72rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</small>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="card" style={{ borderTop: '4px solid var(--ci-warning)' }}>
              <div className="card-body" style={{ padding: '1rem' }}>
                <div style={{ fontSize: '0.75rem', textTransform: 'uppercase', letterSpacing: 1, color: '#94a3b8', marginBottom: '0.75rem' }}>Statut</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                  <span className={`badge ${getStatutBadge(formation.statut)}`} style={{ fontSize: '0.85rem', padding: '0.4em 0.9em' }}>
                    {getStatutLabel(formation.statut)}
                  </span>
                </div>
                {formation.secretariat_nom && (
                  <div style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: '#64748b' }}>
                    <i className="bi bi-building me-1"></i>
                    <strong>Secrétariat :</strong> {formation.secretariat_nom}
                  </div>
                )}
                {formation.creee_par_nom && (
                  <div style={{ marginTop: '0.5rem', fontSize: '0.85rem', color: '#64748b' }}>
                    <i className="bi bi-person me-1"></i>
                    <strong>Créé par :</strong> {formation.creee_par_nom}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── TAB: PRÉSENCES ── */}
      {activeTab === 'presences' && (
        <div>
          <div className="card">
            <div className="card-body" style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <i className="bi bi-calendar3 text-muted"></i>
                <label className="form-label mb-0 me-1" style={{ whiteSpace: 'nowrap' }}>Présences du :</label>
                <input
                  type="date"
                  className="form-control form-control-sm"
                  style={{ width: 'auto' }}
                  value={dashboardDate}
                  onChange={e => { setDashboardDate(e.target.value); setDashboardSession(null) }}
                />
              </div>
              {/* Sélecteur de séance — affiché si l'API retourne des séances ce jour */}
              {dashboard?.seances_jour?.length > 0 && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <i className="bi bi-collection text-muted"></i>
                  <select
                    className="form-select form-select-sm"
                    style={{ width: 'auto', minWidth: 180 }}
                    value={dashboardSession || ''}
                    onChange={e => setDashboardSession(e.target.value || null)}
                  >
                    <option value="">Toutes les séances</option>
                    {dashboard.seances_jour.map(s => (
                      <option key={s.id} value={s.id}>
                        {s.intitule}{s.heure_debut ? ` (${s.heure_debut}${s.heure_fin ? `–${s.heure_fin}` : ''})` : ''}
                        {s.en_cours ? ' ●' : s.terminee ? ' ✓' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <button onClick={() => loadDashboard(dashboardDate, dashboardSession)} className="btn btn-dfrc btn-sm" disabled={dashboardLoading}>
                <i className="bi bi-arrow-clockwise me-1"></i>{dashboardLoading ? 'Chargement...' : 'Actualiser'}
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginLeft: 'auto' }}>
                <i className="bi bi-search text-muted"></i>
                <input
                  type="text"
                  className="form-control form-control-sm"
                  placeholder="Rechercher un étudiant…"
                  style={{ width: 220 }}
                  value={presenceSearch}
                  onChange={e => setPresenceSearch(e.target.value)}
                />
                {presenceSearch && (
                  <button className="btn btn-sm btn-outline-secondary" onClick={() => setPresenceSearch('')} title="Effacer">
                    <i className="bi bi-x"></i>
                  </button>
                )}
              </div>
              {(dashboardDate !== new Date().toISOString().slice(0, 10) || dashboardSession) && (
                <button
                  className="btn btn-outline-secondary btn-sm"
                  onClick={() => { setDashboardDate(new Date().toISOString().slice(0, 10)); setDashboardSession(null) }}
                  title="Revenir à aujourd'hui, toutes séances"
                >
                  <i className="bi bi-calendar-check me-1"></i>Aujourd'hui
                </button>
              )}
            </div>
          </div>

          {dashboardError && !dashboardLoading && (
            <div className="alert alert-danger">{dashboardError}</div>
          )}

          {dashboardLoading && <div className="loading"><div className="spinner"></div></div>}

          {dashboard && !dashboardLoading && (() => {
            const canAction = canPresenceAction(user)
            const fmtTime = (ts) => ts ? new Date(ts).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '—'
            const fmtMin = (m) => m != null ? `${Math.round(m)} min` : '—'
            const matricule = (p) => p.matricule || p.numero_matricule || p.numero || '—'
            const personLabel = (p) => (p.type_personne === 'formateur' ? 'Enseignant' : p.type_personne === 'encadrant' ? 'Encadrant' : 'Étudiant')
            const personIcon = (p) => (p.type_personne === 'formateur' ? 'bi-person-video3' : p.type_personne === 'encadrant' ? 'bi-person-badge' : 'bi-person')
            const personBadgeStyle = (p) => {
              if (p.type_personne === 'formateur') return { background: '#ebf8ff', color: '#2b6cb0', border: '1px solid #bee3f8' }
              if (p.type_personne === 'encadrant') return { background: '#fffae6', color: '#9c4221', border: '1px solid #fbe38d' }
              return { background: '#f7fafc', color: '#4a5568', border: '1px solid #e2e8f0' }
            }
            const searchFilter = (p) => {
              if (!presenceSearch.trim()) return true
              const q = presenceSearch.toLowerCase()
              return (
                (p.nom || '').toLowerCase().includes(q) ||
                (p.prenom || '').toLowerCase().includes(q) ||
                (p.matricule || p.numero_matricule || p.numero || '').toLowerCase().includes(q)
              )
            }
            const enSalleFiltres = (dashboard.en_salle || []).filter(searchFilter)
            const presentsFiltres = (dashboard.presents || []).filter(searchFilter)
            const absentsFiltres = (dashboard.absents || []).filter(searchFilter)
            const taux = dashboard.taux_presence ?? 0
            const tauxColor = taux >= 75 ? 'var(--ci-success)' : taux >= 50 ? 'var(--ci-warning)' : '#e53e3e'

            return (
              <>
                {/* ── Stats ── */}
                {(() => {
                  const nbSeances = dashboard.nb_seances_jour || 1
                  const nbInscrits = dashboard.nb_inscrits || dashboard.total_attendus || 0
                  const seanceActive = dashboard.seances_jour?.find(s => String(s.id) === String(dashboard.seance_selectionnee_id))
                  const labelAttendus = dashboard.seance_selectionnee_id
                    ? `Attendus — ${seanceActive?.intitule || 'Séance'}`
                    : nbSeances > 1
                      ? `Inscrits × ${nbSeances} séances`
                      : 'Attendus'
                  const subAttendus = dashboard.seance_selectionnee_id
                    ? null
                    : nbSeances > 1
                      ? `${nbInscrits} inscrits`
                      : null
                  return (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                      {[
                        { label: labelAttendus, sub: subAttendus, value: dashboard.total_attendus, color: '#64748b', icon: 'bi-people',        bg: '#f8fafc' },
                        { label: 'En salle',    sub: null, value: dashboard.en_salle?.length || 0,  color: '#2b6cb0', icon: 'bi-person-check',  bg: '#ebf8ff' },
                        { label: 'Présents',    sub: null, value: dashboard.presents?.length || 0,  color: '#11407d', icon: 'bi-check-circle',  bg: '#f0f7ff' },
                        { label: 'Absents',     sub: null, value: dashboard.absents?.length || 0,   color: '#c53030', icon: 'bi-person-x',      bg: '#fff5f5' },
                        { label: 'Taux présence', sub: null, value: `${taux}%`,                     color: tauxColor,  icon: 'bi-graph-up',     bg: '#fefce8' },
                      ].map(({ label, sub, value, color, icon, bg }) => (
                        <div key={label} className="card" style={{ margin: 0, borderTop: `3px solid ${color}` }}>
                          <div className="card-body text-center" style={{ padding: '0.85rem 0.5rem', background: bg }}>
                            <i className={`bi ${icon}`} style={{ color, fontSize: '1.1rem' }}></i>
                            <div style={{ fontSize: '1.5rem', fontWeight: 700, color, lineHeight: 1.2, marginTop: '0.2rem' }}>{value}</div>
                            <small style={{ color: '#94a3b8', fontSize: '0.7rem', textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</small>
                            {sub && <div style={{ color: '#94a3b8', fontSize: '0.68rem', marginTop: '0.1rem' }}>{sub}</div>}
                          </div>
                        </div>
                      ))}
                    </div>
                  )
                })()}

                {/* ── En salle ── */}
                {enSalleFiltres.length > 0 && (
                  <div className="card">
                    <div className="card-header-bar" style={{ background: '#ebf8ff' }}>
                      <span style={{ color: '#2b6cb0', fontWeight: 600 }}>
                        <i className="bi bi-person-check me-2"></i>En salle ({enSalleFiltres.length}{presenceSearch ? ` / ${dashboard.en_salle.length}` : ''})
                      </span>
                    </div>
                    <div className="card-body-flush">
                      <div className="table-container">
                        <table className="table">
                          <thead><tr>
                            <th>Nom & Prénom</th><th>Matricule</th><th>Grade</th><th>Site</th>
                            <th>Entrée</th><th>Durée actuelle</th><th>Sessions</th>
                            {canAction && <th>Action</th>}
                          </tr></thead>
                          <tbody>
                            {enSalleFiltres.map((p, i) => (
                              <tr key={p.id != null ? `ensalle_${p.id}` : i}>
                                <td>
                                  <div style={{ fontWeight: 600 }}>{p.nom} {p.prenom}</div>
                                  <small style={{ color: '#718096' }}>
                                    <span style={{ ...personBadgeStyle(p), borderRadius: 999, padding: '1px 8px', fontSize: '0.72rem', fontWeight: 600 }}>
                                      <i className={`bi ${personIcon(p)} me-1`}></i>
                                      {personLabel(p)}
                                    </span>
                                    {p.rattrapage && (
                                      <span style={{ marginLeft: 4, background: '#fef6c7', color: '#92660e', borderRadius: 999, padding: '1px 8px', fontSize: '0.72rem', fontWeight: 600 }} title="Étudiant d'une autre cohorte en rattrapage sur cette séance">
                                        <i className="bi bi-arrow-left-right me-1"></i>Rattrapage
                                      </span>
                                    )}
                                  </small>
                                </td>
                                <td><code style={{ fontSize: '0.82rem' }}>{matricule(p)}</code></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.grade || '—'}</span></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.site || '—'}</span></td>
                                <td style={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{fmtTime(p.timestamp_entree)}</td>
                                <td>
                                  <span style={{ background: '#bee3f8', color: '#2b6cb0', borderRadius: 5, padding: '2px 8px', fontSize: '0.82rem', fontWeight: 600 }}>
                                    {fmtMin(p.duree_actuelle_minutes)}
                                  </span>
                                </td>
                                <td><span style={{ fontSize: '0.82rem', color: '#64748b' }}>{p.nb_sessions || 1}</span></td>
                                {canAction && (
                                  <td>
                                    <button className="btn btn-outline-warning btn-sm" disabled={closingSession === p.id}
                                      onClick={() => openForceMotifDialog(p, 'SORTIE')}>
                                      {closingSession === p.id
                                        ? <span className="spinner" style={{ width: '0.9rem', height: '0.9rem', display: 'inline-block' }}></span>
                                        : <><i className="bi bi-box-arrow-right me-1"></i>Fermer</>}
                                    </button>
                                  </td>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {/* ── Présents (sortis) ── */}
                {presentsFiltres.length > 0 && (
                  <div className="card">
                    <div className="card-header-bar" style={{ background: '#f0f7ff' }}>
                      <span style={{ color: '#11407d', fontWeight: 600 }}>
                        <i className="bi bi-check-circle me-2"></i>Présents — sortis ({presentsFiltres.length}{presenceSearch ? ` / ${dashboard.presents.length}` : ''})
                      </span>
                    </div>
                    <div className="card-body-flush">
                      <div className="table-container">
                        <table className="table">
                          <thead><tr>
                            <th>Nom & Prénom</th><th>Matricule</th><th>Grade</th><th>Site</th>
                            <th>Entrée</th><th>Sortie</th><th>Durée totale</th><th>Sessions</th>
                          </tr></thead>
                          <tbody>
                            {presentsFiltres.map((p, i) => (
                              <tr key={p.id != null ? `present_${p.id}` : i}>
                                <td>
                                  <div style={{ fontWeight: 600 }}>{p.nom} {p.prenom}</div>
                                  <small style={{ color: '#718096' }}>
                                    <span style={{ ...personBadgeStyle(p), borderRadius: 999, padding: '1px 8px', fontSize: '0.72rem', fontWeight: 600 }}>
                                      <i className={`bi ${personIcon(p)} me-1`}></i>
                                      {personLabel(p)}
                                    </span>
                                    {p.rattrapage && (
                                      <span style={{ marginLeft: 4, background: '#fef6c7', color: '#92660e', borderRadius: 999, padding: '1px 8px', fontSize: '0.72rem', fontWeight: 600 }} title="Étudiant d'une autre cohorte en rattrapage sur cette séance">
                                        <i className="bi bi-arrow-left-right me-1"></i>Rattrapage
                                      </span>
                                    )}
                                  </small>
                                </td>
                                <td><code style={{ fontSize: '0.82rem' }}>{matricule(p)}</code></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.grade || '—'}</span></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.site || '—'}</span></td>
                                <td style={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{fmtTime(p.timestamp_entree)}</td>
                                <td style={{ fontFamily: 'monospace', whiteSpace: 'nowrap' }}>{fmtTime(p.timestamp_sortie)}</td>
                                <td>
                                  <span style={{ background: '#c6ddf6', color: '#11407d', borderRadius: 5, padding: '2px 8px', fontSize: '0.82rem', fontWeight: 600 }}>
                                    {fmtMin(p.duree_presence_minutes)}
                                  </span>
                                </td>
                                <td><span style={{ fontSize: '0.82rem', color: '#64748b' }}>{p.nb_sessions || 1}</span></td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {/* ── Absents ── */}
                {absentsFiltres.length > 0 && (
                  <div className="card">
                    <div className="card-header-bar" style={{ background: '#fff5f5' }}>
                      <span style={{ color: '#c53030', fontWeight: 600 }}>
                        <i className="bi bi-person-x me-2"></i>Absents ({absentsFiltres.length}{presenceSearch ? ` / ${dashboard.absents.length}` : ''})
                      </span>
                    </div>
                    <div className="card-body-flush">
                      <div className="table-container">
                        <table className="table">
                          <thead><tr>
                            <th>Nom & Prénom</th><th>Matricule</th><th>Grade</th><th>Site</th><th>Adresse e-mail</th><th>Tél.</th>
                            {canAction && <th>Action</th>}
                          </tr></thead>
                          <tbody>
                            {absentsFiltres.map((p, i) => (
                              <tr key={p.id != null ? `absent_${p.id}` : i}>
                                <td>
                                  <div style={{ fontWeight: 600 }}>{p.nom} {p.prenom}</div>
                                  <small style={{ color: '#718096' }}>
                                    <span style={{ ...personBadgeStyle(p), borderRadius: 999, padding: '1px 8px', fontSize: '0.72rem', fontWeight: 600 }}>
                                      <i className={`bi ${personIcon(p)} me-1`}></i>
                                      {personLabel(p)}
                                    </span>
                                    {p.rattrapage && (
                                      <span style={{ marginLeft: 4, background: '#fef6c7', color: '#92660e', borderRadius: 999, padding: '1px 8px', fontSize: '0.72rem', fontWeight: 600 }} title="Étudiant d'une autre cohorte en rattrapage sur cette séance">
                                        <i className="bi bi-arrow-left-right me-1"></i>Rattrapage
                                      </span>
                                    )}
                                  </small>
                                </td>
                                <td><code style={{ fontSize: '0.82rem' }}>{matricule(p)}</code></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.grade || '—'}</span></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.site || '—'}</span></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.email || '—'}</span></td>
                                <td><span style={{ fontSize: '0.82rem' }}>{p.telephone || '—'}</span></td>
                                {canAction && (
                                  <td>
                                    <button className="btn btn-outline-success btn-sm" disabled={badgingEntree === p.id}
                                      onClick={() => openForceMotifDialog(p, 'ENTREE')}>
                                      {badgingEntree === p.id
                                        ? <span className="spinner" style={{ width: '0.9rem', height: '0.9rem', display: 'inline-block' }}></span>
                                        : ((p.type_personne || 'participant') === 'participant'
                                          ? <><i className="bi bi-person-check me-1"></i>Forcer présence</>
                                          : <><i className="bi bi-box-arrow-in-right me-1"></i>Badger</>)}
                                    </button>
                                  </td>
                                )}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )}

                {(!enSalleFiltres.length && !presentsFiltres.length && !absentsFiltres.length) && (
                  <div className="card"><div className="card-body text-center text-muted py-4">
                    <i className="bi bi-calendar-x" style={{ fontSize: '2rem' }}></i>
                    <p className="mt-2">Aucune donnée de présence pour cette date</p>
                  </div></div>
                )}

              </>
            )
          })()}

        </div>
      )}

      {/* ── TAB: SÉANCES ── */}
      {activeTab === 'seances' && (
        <div>
          {canManageSessions && (
            <div className="card">
              <div className="card-body">
                {showNewSession ? (
                  <form onSubmit={handleCreateSession} style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
                    <div className="form-group" style={{ flex: '1 1 140px' }}>
                      <label className="form-label">Date *</label>
                      <input type="date" className="form-control form-control-sm" required value={newSession.date_journee}
                        onChange={e => setNewSession({...newSession, date_journee: e.target.value})} />
                    </div>
                    <div className="form-group" style={{ flex: '1 1 100px' }}>
                      <label className="form-label">Début</label>
                      <input type="time" className="form-control form-control-sm" value={newSession.heure_debut_prevue}
                        onChange={e => setNewSession({...newSession, heure_debut_prevue: e.target.value})} />
                    </div>
                    <div className="form-group" style={{ flex: '1 1 100px' }}>
                      <label className="form-label">Fin</label>
                      <input type="time" className="form-control form-control-sm" value={newSession.heure_fin_prevue}
                        onChange={e => setNewSession({...newSession, heure_fin_prevue: e.target.value})} />
                    </div>
                    <div style={{ display: 'flex', gap: '0.5rem' }}>
                      <button type="submit" className="btn btn-success btn-sm">Créer</button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowNewSession(false)}>Annuler</button>
                    </div>
                  </form>
                ) : (
                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                    <button onClick={() => setShowNewSession(true)} className="btn btn-dfrc btn-sm">
                      <i className="bi bi-plus-lg me-1"></i>Ajouter une séance
                    </button>
                    {canImport && (
                      <>
                        <button
                          className="btn btn-secondary btn-sm"
                          disabled={importingSeances}
                          onClick={() => { setImportSeancesMsg(null); importFileRef.current?.click() }}
                        >
                          <i className="bi bi-file-earmark-excel me-1"></i>
                          {importingSeances ? 'Import...' : 'Importer Excel'}
                        </button>
                        <input
                          type="file" accept=".xlsx,.xls" ref={importFileRef} style={{ display: 'none' }}
                          onChange={async (e) => {
                            const file = e.target.files[0]
                            if (!file) return
                            setImportingSeances(true)
                            setImportSeancesMsg(null)
                            const fd = new FormData()
                            fd.append('file', file)
                            fd.append('type', 'seances')
                            fd.append('formation_id', id)
                            try {
                              const res = await api.post('/formations/import-excel/', fd)
                              const created = res.data.created || 0
                              const upd = res.data.updated || 0
                              const txt = created > 0
                                ? `${created} séance(s) créée(s)`
                                : upd > 0
                                  ? `${upd} séance(s) déjà existante(s)`
                                  : 'Aucune séance traitée'
                              setImportSeancesMsg({ ok: true, text: txt, errors: res.data.errors })
                              loadFormationData()
                            } catch (err) {
                              setImportSeancesMsg({ ok: false, text: err.response?.data?.error || "Erreur lors de l'import" })
                            } finally {
                              setImportingSeances(false)
                              e.target.value = ''
                            }
                          }}
                        />
                        {importSeancesMsg && (
                          <span className={`badge ${importSeancesMsg.ok ? 'badge-bg-success' : 'badge-bg-danger'}`} style={{ fontSize: '0.8rem' }}>
                            {importSeancesMsg.text}
                            {importSeancesMsg.errors?.length > 0 && ` (${importSeancesMsg.errors.length} erreur(s))`}
                          </span>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Barre d'export globale */}
          <div className="card">
            <div className="card-body" style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 600, color: 'var(--ci-success-dark)' }}>
                <i className="bi bi-download me-2"></i>Exporter toutes les séances :
              </span>
              <button onClick={() => handleExport('pdf')} className="btn btn-outline-danger btn-sm" title="Exporter PDF toutes séances">
                <i className="bi bi-file-earmark-pdf me-1"></i>PDF — Toutes séances
              </button>
              <button onClick={() => handleExport('excel')} className="btn btn-outline-success btn-sm" title="Exporter Excel toutes séances">
                <i className="bi bi-file-earmark-excel me-1"></i>Excel — Toutes séances
              </button>
            </div>
          </div>

          {sessions.length > 0 ? (() => {
            // Regrouper les séances par module_intitule + module_id pour éviter
            // les collisions entre modules de formations différentes de même intitulé
            const grouped = {}
            sessions.forEach(s => {
              const moduleKey = s.module_id
                ? `${s.module_id}`
                : s.module_intitule || s.intitule || 'Sans module'
              if (!grouped[moduleKey]) grouped[moduleKey] = { label: s.module_intitule || s.intitule || 'Sans module', sessions: [] }
              grouped[moduleKey].sessions.push(s)
            })
            return Object.entries(grouped).map(([moduleKey, group]) => {
              const { label: moduleLabel, sessions: moduleSessions } = group
              return (
              <div className="card" key={moduleKey}>
                <div className="card-header-bar" style={{ background: '#f0f6fd' }}>
                  <span style={{ fontWeight: 600, color: 'var(--ci-success-dark)' }}>
                    <i className="bi bi-book me-2"></i>
                    <Link
                      to={`/formations/${id}/modules/${moduleKey}`}
                      state={listNavState}
                      style={{ color: 'var(--ci-success-dark)', textDecoration: 'none' }}
                      title="Voir le détail du module"
                    >
                      {moduleLabel}
                    </Link>
                    <span className="badge ms-2" style={{ background: '#d1e3fa', color: '#082a5d', fontSize: '0.78rem' }}>
                      {moduleSessions.length} séance{moduleSessions.length > 1 ? 's' : ''}
                    </span>
                  </span>
                  <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                    {canArchive && moduleKey !== 'Sans module' && (
                      <button
                        type="button"
                        className="btn btn-warning btn-sm"
                        title="Archiver ce module (3 confirmations)"
                        onClick={() => setArchiveTarget({ moduleId: moduleKey, label: moduleLabel })}
                      >
                        <i className="bi bi-archive me-1"></i>Archiver
                      </button>
                    )}
                    <Link
                      to={`/formations/${id}/modules/${moduleKey}`}
                      state={listNavState}
                      className="btn btn-outline-secondary btn-sm"
                      title="Détail du module"
                    >
                      <i className="bi bi-arrow-right"></i>
                    </Link>
                  </div>
                </div>
                <div className="card-body-flush">
                  <div className="table-container">
                    <table className="table">
                      <thead><tr><th>N°</th><th>Intitulé</th><th>Date</th><th>Horaire</th><th>Statut</th><th>Présences</th><th>Exports</th><th>Actions</th></tr></thead>
                      <tbody>
                        {moduleSessions.map((s) => (
                          <tr key={s.id}>
                            <td><span className="badge-bg-info">{sessionNumeroLabel(s)}</span></td>
                            <td><strong>{s.intitule || '—'}</strong></td>
                            <td>{s.date ? formatDate(s.date) : '-'}</td>
                            <td style={{ whiteSpace: 'nowrap' }}>{s.heure_debut || '-'} — {s.heure_fin || '-'}</td>
                            <td><span className={`badge ${s.en_cours ? 'badge-en-cours' : s.terminee ? 'badge-terminee' : 'badge-planifiee'}`}>
                              {s.en_cours ? 'En cours' : s.terminee ? 'Terminé' : 'Planifié'}
                            </span></td>
                            <td><span className="badge-bg-success">{s.nb_presences || 0}</span> / {s.nb_attendus || 0}</td>
                            <td>
                              <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap' }}>
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
                                  <button onClick={() => handleStartSession(s.id, s.intitule || `Séance ${s.numero}`)} className="btn btn-outline-success btn-sm" disabled={startingSession === s.id} title="Démarrer">
                                    {startingSession === s.id ? <span className="spinner" style={{ width: '0.8rem', height: '0.8rem', display: 'inline-block' }}></span> : <><i className="bi bi-play-fill me-1"></i>Démarrer</>}
                                  </button>
                                )}
                                {s.en_cours && canSupervise && (
                                  <button onClick={() => handleStopSession(s.id, s.intitule || `Séance ${s.numero}`)} className="btn btn-warning btn-sm" disabled={stoppingSession === s.id} title="Terminer">
                                    {stoppingSession === s.id ? <span className="spinner" style={{ width: '0.8rem', height: '0.8rem', display: 'inline-block' }}></span> : <><i className="bi bi-stop-fill me-1"></i>Terminer</>}
                                  </button>
                                )}
                                {!s.terminee && (
                                  <button onClick={() => handleGenerateQR(s)} className="btn btn-outline-primary btn-sm" title="QR Code">
                                    <i className="bi bi-qr-code"></i>
                                  </button>
                                )}
                                {s.terminee && (
                                  <span className="badge badge-terminee">Terminé</span>
                                )}
                                {canManageSessions && !s.terminee && (
                                  <button onClick={() => openEditSession(s)} className="btn btn-outline-secondary btn-sm" title="Modifier"><i className="bi bi-pencil"></i></button>
                                )}
                                {canManageSessions && !s.en_cours && !s.terminee && (
                                  <button onClick={() => handleDeleteSession(s.id)} className="btn btn-outline-danger btn-sm" title="Supprimer"><i className="bi bi-trash"></i></button>
                                )}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              )
            })
          })() : (
            <div className="card"><div className="text-center py-4 text-muted">
              <i className="bi bi-calendar-x" style={{ fontSize: '2rem' }}></i>
              <p className="mt-2">Aucune séance planifiée</p>
            </div></div>
          )}
        </div>
      )}

      {/* ── TAB: PARTICIPANTS ── */}
      {activeTab === 'participants' && (
        <div>
          {canEdit && (
            <div className="card">
              <div className="card-body">
                <button onClick={openAddParticipant} className="btn btn-dfrc btn-sm">
                  <i className="bi bi-person-plus me-1"></i>Ajouter un étudiant
                </button>
              </div>
            </div>
          )}
          <div className="card">
            <div className="card-header-bar">
              <span><i className="bi bi-people me-2"></i>Étudiants inscrits ({participants.length})</span>
            </div>
            <div className="card-body-flush">
              {participants.length > 0 ? (
                <>
                <div className="table-container">
                  <table className="table">
                    <thead><tr><th>Matricule</th><th>Nom</th><th>Prénom</th><th>Adresse e-mail</th><th>Téléphone</th><th>Structure</th>{canEdit && <th>Actions</th>}</tr></thead>
                    <tbody>
                      {participantsPager.pageItems.map((p) => (
                        <tr key={p.id}>
                          <td><span className="badge-bg-info">{p.numero_matricule || p.matricule || p.numero || '-'}</span></td>
                          <td><strong>{p.nom}</strong></td>
                          <td>{p.prenom}</td>
                          <td>{p.email || '-'}</td>
                          <td>{p.telephone || '-'}</td>
                          <td>{p.structure || p.organisation || '-'}</td>
                          {canEdit && (
                            <td>
                              <button onClick={() => handleRemoveParticipant(p.id)} className="btn btn-outline-danger btn-sm" title="Retirer">
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
                  <p className="mt-2">Aucun étudiant inscrit</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── TAB: FORMATEURS ── */}
      {activeTab === 'formateurs' && (
        <div>
          {canEdit && (
            <div className="card">
              <div className="card-body">
                <button onClick={openAddFormateur} className="btn btn-dfrc btn-sm">
                  <i className="bi bi-person-plus me-1"></i>Ajouter un enseignant
                </button>
              </div>
            </div>
          )}
          <div className="card">
            <div className="card-header-bar">
              <span><i className="bi bi-person-video3 me-2"></i>Enseignants assignés ({formateurs.length})</span>
            </div>
            <div className="card-body-flush">
              {formateurs.length > 0 ? (
                <>
                <div className="table-container">
                  <table className="table">
                    <thead><tr><th>Numéro</th><th>Nom</th><th>Prénom</th><th>Spécialité</th><th>Adresse e-mail</th><th>Téléphone</th>{canEdit && <th>Actions</th>}</tr></thead>
                    <tbody>
                      {formateursPager.pageItems.map((f) => (
                        <tr key={f.id}>
                          <td><span className="badge-bg-info">{f.numerobadge || '-'}</span></td>
                          <td><strong>{f.nom}</strong></td>
                          <td>{f.prenom}</td>
                          <td>{f.specialite || '-'}</td>
                          <td>{f.email || '-'}</td>
                          <td>{f.telephone || '-'}</td>
                          {canEdit && (
                            <td>
                              <button onClick={() => handleRemoveFormateur(f.id)} className="btn btn-outline-danger btn-sm" title="Retirer">
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
                  <i className="bi bi-person-video3" style={{ fontSize: '2rem' }}></i>
                  <p className="mt-2">Aucun enseignant assigné</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: QR Code ── */}
      <QRCodeModal
        isOpen={qrModalOpen}
        onClose={() => setQrModalOpen(false)}
        formationId={id}
        sessionId={selectedSessionId}
        moduleId={selectedQrModule?.id}
        moduleLabel={selectedQrModule?.label}
        moduleGroupe={selectedQrModule?.groupe}
      />

      {/* ── MODAL: Modifier séance ── */}
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
                  <input type="text" className="form-control" readOnly disabled value={sessionNumeroLabel(editSession)} />
                  <small className="text-muted">Une seule séance {sessionNumeroLabel(editSession)} par date.</small>
                </div>
                <div className="form-group">
                  <label className="form-label">Intitulé *</label>
                  <input type="text" className="form-control" required
                    value={editSessionForm.intitule}
                    onChange={e => setEditSessionForm({...editSessionForm, intitule: e.target.value})} />
                </div>
                <div className="form-group">
                  <label className="form-label">Date *</label>
                  <input type="date" className="form-control" required
                    value={editSessionForm.date_journee}
                    onChange={e => setEditSessionForm({...editSessionForm, date_journee: e.target.value})} />
                </div>
                <div className="grid-2">
                  <div className="form-group">
                    <label className="form-label">Heure début</label>
                    <input type="time" className="form-control"
                      value={editSessionForm.heure_debut_prevue}
                      onChange={e => setEditSessionForm({...editSessionForm, heure_debut_prevue: e.target.value})} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">Heure fin</label>
                    <input type="time" className="form-control"
                      value={editSessionForm.heure_fin_prevue}
                      onChange={e => setEditSessionForm({...editSessionForm, heure_fin_prevue: e.target.value})} />
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
          variant={confirmDialog.variant || 'danger'}
          confirmLabel={confirmDialog.confirmLabel}
          onConfirm={() => { setConfirmDialog(null); confirmDialog.onConfirm() }}
          onCancel={() => setConfirmDialog(null)}
        />
      )}

      {archiveTarget && (
        <TripleConfirmModal
          title="Archivage du module"
          subject={archiveTarget.label}
          onConfirm={confirmArchiveModule}
          onCancel={() => setArchiveTarget(null)}
        />
      )}

      {/* ── MODAL: Assign superviseur ── */}
      {showAssignModal && (
        <div className="modal-overlay" onClick={() => setShowAssignModal(false)}>
          <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-badge me-2"></i>Assigner un encadrant</h5>
              <button className="btn-close" onClick={() => setShowAssignModal(false)}>&times;</button>
            </div>
            <div className="modal-body">
              {assignError && <div className="alert alert-danger">{assignError}</div>}
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
              {!encadrantLoading && superviseurs.length === 0 && (
                <p className="text-muted text-center py-2">Aucun encadrant trouvé</p>
              )}
              {!encadrantLoading && superviseurs.length > 0 && (
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
                      {superviseurs.map(s => {
                        const fullName = `${s.first_name || ''} ${s.last_name || ''}`.trim() || s.username
                        const isSelected = String(selectedSup) === String(s.id)
                        return (
                          <tr
                            key={s.id}
                            onClick={() => setSelectedSup(String(s.id))}
                            style={{ cursor: 'pointer', background: isSelected ? '#f0f6fd' : undefined }}
                          >
                            <td>{fullName}</td>
                            <td>{s.username}</td>
                            <td>{s.matricule || '—'}</td>
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
              <button className="btn btn-secondary" onClick={() => setShowAssignModal(false)}>Annuler</button>
              <button className="btn btn-dfrc" onClick={handleAssignSuperviseur}>Assigner</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: Add enseignant ── */}
      {showAddFormateur && (
        <div className="modal-overlay" onClick={() => setShowAddFormateur(false)}>
          <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-plus me-2"></i>Ajouter un enseignant</h5>
              <button className="btn-close" onClick={() => setShowAddFormateur(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="input-group mb-3">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input type="text" className="form-control" placeholder="Rechercher par nom, prénom, spécialité…"
                  value={formateurSearch} onChange={e => setFormateurSearch(e.target.value)} autoFocus />
              </div>
              {formateurLoading && <div className="text-center text-muted py-2"><div className="spinner" style={{ width: 20, height: 20 }}></div></div>}
              {!formateurLoading && allFormateurs.length === 0 && (
                <p className="text-muted text-center py-2">Aucun enseignant disponible</p>
              )}
              {!formateurLoading && allFormateurs.length > 0 && (
                <div style={{ maxHeight: '320px', overflowY: 'auto', overflowX: 'auto' }}>
                  <table className="table table-sm">
                    <thead><tr><th>Numéro</th><th>Nom</th><th>Spécialité</th><th></th></tr></thead>
                    <tbody>
                      {allFormateurs.map(f => (
                        <tr key={f.id}>
                          <td><span className="badge-bg-info">{f.numerobadge || '-'}</span></td>
                          <td>{f.nom} {f.prenom}</td>
                          <td>{f.specialite || '-'}</td>
                          <td>
                            <button onClick={() => handleAddFormateur(f.id)} className="btn btn-outline-success btn-sm">
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

      {/* Motif popup pour badgeage forcé */}
      {forceMotifDialog && (() => {
        const jourPasse = isJourPasse(dashboardDate)
        const isÉtudiant = (forceMotifDialog.personne.type_personne || 'participant') === 'participant'
        return (
          <div className="modal-overlay" onClick={() => setForceMotifDialog(null)}>
            <div className="modal-content" style={{ maxWidth: '460px' }} onClick={e => e.stopPropagation()}>
              <div className="modal-header">
                <h5>
                  {forceMotifDialog.action === 'ENTREE'
                    ? (isÉtudiant
                      ? <><i className="bi bi-person-check me-2 text-success"></i>Forcer la présence</>
                      : <><i className="bi bi-box-arrow-in-right me-2 text-success"></i>Badger l'entrée</>)
                    : <><i className="bi bi-box-arrow-right me-2 text-warning"></i>Fermer la session</>}
                </h5>
                <button className="btn-close" onClick={() => setForceMotifDialog(null)}>&times;</button>
              </div>
              <div className="modal-body">
                <p className="mb-3" style={{ color: '#4a5568' }}>
                  {forceMotifDialog.action === 'ENTREE'
                    ? (isÉtudiant
                      ? <>Présence forcée pour <strong>{forceMotifDialog.personne.nom} {forceMotifDialog.personne.prenom}</strong> — durée planifiée de la séance.</>
                      : <>Badgeage forcé de l'entrée pour <strong>{forceMotifDialog.personne.nom} {forceMotifDialog.personne.prenom}</strong>.</>)
                    : <>Sortie forcée pour <strong>{forceMotifDialog.personne.nom} {forceMotifDialog.personne.prenom}</strong>.</>}
                  {jourPasse && (
                    <span className="badge ms-2" style={{ background: '#FFF8E0', color: '#7B5500', border: '1px solid #F5B100', fontSize: '0.78rem' }}>
                      <i className="bi bi-clock-history me-1"></i>Jour passé — {dashboardDate}
                    </span>
                  )}
                </p>

                {isÉtudiant && forceMotifDialog.action === 'ENTREE' && !jourPasse && (
                  <p style={{ fontSize: '0.85rem', color: '#475569', background: '#eff6ff', border: '1px solid #bfdbfe', borderRadius: '8px', padding: '0.65rem 0.75rem', marginBottom: '0.75rem' }}>
                    <i className="bi bi-info-circle me-1"></i>
                    Entrée et sortie seront enregistrées sur <strong>toute la durée planifiée de la séance</strong> (horaires EDT).
                  </p>
                )}

                {/* Champs heure — uniquement sur jour passé */}
                {jourPasse && forceMotifDialog.action === 'ENTREE' && (
                  <div className="grid-2 mb-3">
                    <div className="form-group">
                      <label className="form-label">Heure d'entrée <span style={{ color: '#e53e3e' }}>*</span></label>
                      <input type="time" className="form-control"
                        value={forceHeureEntree}
                        onChange={e => { setForceHeureEntree(e.target.value); setForceMotifError('') }} />
                    </div>
                    <div className="form-group">
                      <label className="form-label">Heure de sortie <small style={{ color: '#718096' }}>(optionnel)</small></label>
                      <input type="time" className="form-control"
                        value={forceHeureSortie}
                        onChange={e => setForceHeureSortie(e.target.value)} />
                    </div>
                  </div>
                )}

                {jourPasse && forceMotifDialog.action === 'SORTIE' && (
                  <div className="form-group mb-3">
                    <label className="form-label">Heure de sortie <small style={{ color: '#718096' }}>(optionnel — maintenant si vide)</small></label>
                    <input type="time" className="form-control"
                      value={forceHeureSortie}
                      onChange={e => setForceHeureSortie(e.target.value)} />
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label" htmlFor="force-motif-input">
                    Motif <span style={{ color: '#e53e3e' }}>*</span>
                  </label>
                  <textarea
                    id="force-motif-input"
                    className="form-control"
                    rows={3}
                    placeholder="Saisir le motif du badgeage forcé…"
                    value={forceMotifText}
                    onChange={e => { setForceMotifText(e.target.value); setForceMotifError('') }}
                    autoFocus
                  />
                  {forceMotifError && (
                    <div style={{ color: '#e53e3e', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                      <i className="bi bi-exclamation-circle me-1"></i>{forceMotifError}
                    </div>
                  )}
                </div>
              </div>
              <div className="modal-footer">
                <button className="btn btn-secondary" onClick={() => setForceMotifDialog(null)}>Annuler</button>
                <button
                  className={`btn ${forceMotifDialog.action === 'ENTREE' ? 'btn-success' : 'btn-warning'}`}
                  onClick={submitForceMotif}
                >
                  {forceMotifDialog.action === 'ENTREE'
                    ? (isÉtudiant
                      ? <><i className="bi bi-person-check me-1"></i>Confirmer la présence</>
                      : <><i className="bi bi-box-arrow-in-right me-1"></i>Confirmer le badgeage</>)
                    : <><i className="bi bi-box-arrow-right me-1"></i>Confirmer la sortie</>}
                </button>
              </div>
            </div>
          </div>
        )
      })()}

      {showAddParticipant && (
        <div className="modal-overlay" onClick={() => setShowAddParticipant(false)}>
          <div className="modal-content" style={{ maxWidth: '560px' }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-person-plus me-2"></i>Ajouter un étudiant</h5>
              <button className="btn-close" onClick={() => setShowAddParticipant(false)}>&times;</button>
            </div>
            <div className="modal-body">
              <div className="input-group mb-3">
                <span className="input-group-text"><i className="bi bi-search"></i></span>
                <input type="text" className="form-control" placeholder="Rechercher par nom, prénom, matricule…"
                  value={addSearch} onChange={e => setAddSearch(e.target.value)} autoFocus />
              </div>
              {addLoading && <div className="text-center text-muted py-2"><div className="spinner" style={{ width: 20, height: 20 }}></div></div>}
              {!addLoading && allParticipants.length === 0 && (
                <p className="text-muted text-center py-2">Aucun étudiant disponible</p>
              )}
              {!addLoading && allParticipants.length > 0 && (
                <div style={{ maxHeight: '320px', overflowY: 'auto', overflowX: 'auto' }}>
                  <table className="table table-sm">
                    <thead><tr><th>Matricule</th><th>Nom</th><th>Prénom</th><th></th></tr></thead>
                    <tbody>
                      {allParticipants.map(p => (
                        <tr key={p.id}>
                          <td><span className="badge-bg-info">{p.numero_matricule || p.matricule || p.numero || '-'}</span></td>
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
    </div>
  )
}
