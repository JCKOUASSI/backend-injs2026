import { useState, useEffect } from 'react'
import { formatDate } from '../utils/dates'
import api from '../services/api'
import { useToast } from '../context/ToastContext'

const PARTICIPANT_DETAIL_TABS = [
  { id: 'statistiques', label: 'Statistiques', icon: 'bi-graph-up' },
  { id: 'identite', label: 'Identité', icon: 'bi-person-badge' },
  { id: 'modules', label: 'Modules', icon: 'bi-journal-bookmark' },
  { id: 'notes', label: 'Notes', icon: 'bi-pencil-square' },
  { id: 'seances', label: 'Séances', icon: 'bi-clock-history' },
]

const MENTION_LABELS = {
  TRES_BIEN: 'Très bien',
  BIEN: 'Bien',
  ASSEZ_BIEN: 'Assez bien',
  PASSABLE: 'Passable',
  INSUFFISANT: 'Insuffisant',
  '': '—',
}

const DECISION_LABELS = {
  ADMIS: 'Admis',
  AJOURNE: 'Ajourné',
  EXCLUSION: 'Exclusion',
  EN_ATTENTE: 'En attente',
}

const DECISION_COLORS = {
  ADMIS: { background: '#e8eff5', color: '#093f70' },
  AJOURNE: { background: '#fff8e0', color: '#e69700' },
  EXCLUSION: { background: '#ffebee', color: '#b71c1c' },
  EN_ATTENTE: { background: '#f5f5f5', color: '#616161' },
}

const DEFAULT_CRITERES = { seuil_admission: 12, taux_presence_min: 80 }

function mentionFromMoyenne(moyenne) {
  const n = parseFloat(moyenne)
  if (isNaN(n)) return ''
  if (n >= 16) return 'TRES_BIEN'
  if (n >= 14) return 'BIEN'
  if (n >= 12) return 'ASSEZ_BIEN'
  if (n >= 10) return 'PASSABLE'
  return 'INSUFFISANT'
}

function formatHeuresModule(heures) {
  const h = parseFloat(heures)
  if (isNaN(h) || h <= 0) return null
  return Number.isInteger(h) ? `${h}h` : `${Math.round(h * 10) / 10}h`
}

function moduleMetaParts(m) {
  return [
    m.grade && { icon: 'bi-people', label: m.grade },
    m.groupe && { icon: 'bi-people-fill', label: `Groupe ${m.groupe}` },
    m.vague && { icon: 'bi-layers', label: m.vague },
    m.site && { icon: 'bi-building', label: m.site },
  ].filter(Boolean)
}

function buildDraftFromRow(row) {
  return {
    moyenne: row?.moyenne != null ? String(row.moyenne) : '',
  }
}

function mapNotesFicheToState(data) {
  const results = {}
  for (const m of data.modules || []) {
    const row = {
      moyenne: m.moyenne,
      heures_presence: m.heures_presence,
      heures_prevues: m.heures_prevues,
      taux_presence: m.taux_presence,
      admissible: m.admissible,
      mention: m.mention,
    }
    results[m.module_id] = {
      colonneId: m.colonne_id ?? null,
      row,
      draft: buildDraftFromRow(row),
      dirty: false,
    }
  }
  const decisions = {}
  for (const f of data.formations || []) {
    decisions[f.formation_id] = {
      decision: f.decision,
      criteres: f.criteres || DEFAULT_CRITERES,
    }
  }
  return { moduleNotes: results, formationDecisions: decisions }
}

function computeFormationSummary(formationModules, moduleNotes, criteres = DEFAULT_CRITERES) {
  let somme = 0
  let totalPoids = 0
  let totalPresence = 0
  let totalPrevu = 0

  formationModules.forEach((m) => {
    const d = moduleNotes[m.id]
    const moyenne = parseFloat(d?.draft?.moyenne ?? d?.row?.moyenne)
    const poids = parseFloat(m.duree_prevue_heures) || 1
    if (!isNaN(moyenne)) {
      somme += moyenne * poids
      totalPoids += poids
    }
    const hp = parseFloat(d?.row?.heures_presence)
    const hprev = parseFloat(d?.row?.heures_prevues ?? m.duree_prevue_heures)
    if (!isNaN(hp)) totalPresence += hp
    if (!isNaN(hprev) && hprev > 0) totalPrevu += hprev
  })

  const moyenneGenerale = totalPoids > 0 ? Math.round((somme / totalPoids) * 100) / 100 : null
  const tauxPresence = totalPrevu > 0 ? Math.round((totalPresence / totalPrevu) * 10000) / 100 : null

  const seuilNote = criteres?.seuil_admission ?? DEFAULT_CRITERES.seuil_admission
  const seuilTaux = criteres?.taux_presence_min ?? DEFAULT_CRITERES.taux_presence_min
  let decision = 'EN_ATTENTE'
  if (moyenneGenerale != null && tauxPresence != null) {
    if (moyenneGenerale >= seuilNote && tauxPresence >= seuilTaux) decision = 'ADMIS'
    else if (moyenneGenerale < 8 || tauxPresence < 50) decision = 'EXCLUSION'
    else decision = 'AJOURNE'
  }

  return {
    moyenneGenerale,
    tauxPresence,
    totalPresence: Math.round(totalPresence * 100) / 100,
    totalPrevu: Math.round(totalPrevu * 100) / 100,
    decision,
    mention: moyenneGenerale != null ? mentionFromMoyenne(moyenneGenerale) : '',
  }
}

export default function ParticipantDetailModal({
  participant,
  modules,
  pointages,
  stats,
  initialNotesFiche = null,
  onClose,
  loading,
  canManageNotes = false,
}) {
  const { showToast } = useToast()
  const [activeTab, setActiveTab] = useState('statistiques')
  const [expandedModule, setExpandedModule] = useState(null)
  const [moduleSessions, setModuleSessions] = useState({})
  const [loadingSessions, setLoadingSessions] = useState(false)
  const [moduleNotes, setModuleNotes] = useState({})
  const [notesLoading, setNotesLoading] = useState(false)
  const [notesSaving, setNotesSaving] = useState({})
  const [formationDecisions, setFormationDecisions] = useState({})
  const [decisionRecalculating, setDecisionRecalculating] = useState({})
  const [exportingNotes, setExportingNotes] = useState(null)

  useEffect(() => {
    if (initialNotesFiche) {
      const mapped = mapNotesFicheToState(initialNotesFiche)
      setModuleNotes(mapped.moduleNotes)
      setFormationDecisions(mapped.formationDecisions)
      setNotesLoading(false)
    } else {
      setModuleNotes({})
      setFormationDecisions({})
    }
  }, [initialNotesFiche, participant?.id])

  useEffect(() => {
    if (activeTab !== 'notes' || !participant?.id || initialNotesFiche) return

    let cancelled = false
    const loadNotes = async () => {
      setNotesLoading(true)
      try {
        const { data } = await api.get(`/participant/${participant.id}/notes-fiche/`)
        if (!cancelled) {
          const mapped = mapNotesFicheToState(data)
          setModuleNotes(mapped.moduleNotes)
          setFormationDecisions(mapped.formationDecisions)
        }
      } catch {
        if (!cancelled) {
          setModuleNotes({})
          setFormationDecisions({})
          showToast('Erreur chargement des notes', 'error')
        }
      } finally {
        if (!cancelled) setNotesLoading(false)
      }
    }
    loadNotes()
    return () => { cancelled = true }
  }, [activeTab, participant?.id, initialNotesFiche, showToast])

  if (!participant) return null

  const sexeLabel = (s) => ({ MASCULIN: 'Masculin', FEMININ: 'Féminin' }[s] || '-')
  const sexeBadge = (s) => s === 'MASCULIN' ? 'badge-bg-info' : s === 'FEMININ' ? 'badge-bg-warning' : ''

  // Grouper les séances par formation/module
  const sessionsByModule = pointages?.reduce((acc, pt) => {
    const key = `${pt.formation_id || 'none'}-${pt.module_intitule || 'none'}`
    if (!acc[key]) {
      acc[key] = {
        formation_titre: pt.formation_titre || 'Formation',
        module_intitule: pt.module_intitule || '',
        sessions: []
      }
    }
    acc[key].sessions.push(pt)
    return acc
  }, {}) || {}

  const sessionsByModuleList = Object.values(sessionsByModule).sort((a, b) => {
    return a.formation_titre.localeCompare(b.formation_titre)
  })

  // Calculer les statistiques par module (pour l'onglet Modules)
  const moduleStats = modules?.reduce((acc, m) => {
    // Trouver les pointages pour ce module
    const modulePointages = pointages?.filter(pt =>
      pt.module_intitule === m.module || pt.module_id === m.id
    ) || []

    // Calculer les heures effectuées (uniquement pour les séances terminées)
    const totalMinutes = modulePointages
      .filter(pt => pt.statut === 'TERMINE' && pt.duree_presence_minutes > 0)
      .reduce((sum, pt) => sum + (pt.duree_presence_minutes || 0), 0)

    const heuresEffectuees = Math.round(totalMinutes / 60 * 10) / 10
    const nbSeances = modulePointages.filter(pt => pt.statut === 'TERMINE').length
    const nbSeancesEnCours = modulePointages.filter(pt => pt.statut === 'EN_COURS').length

    acc[m.id] = {
      heuresEffectuees,
      nbSeances,
      nbSeancesEnCours,
      heuresPrevues: m.duree_prevue_heures || 0,
      tauxRealisation: m.duree_prevue_heures > 0
        ? Math.min(100, Math.round((heuresEffectuees / m.duree_prevue_heures) * 100))
        : 0
    }
    return acc
  }, {}) || {}

  const refreshNotesFiche = async () => {
    setNotesLoading(true)
    try {
      const { data } = await api.get(`/participant/${participant.id}/notes-fiche/`)
      const mapped = mapNotesFicheToState(data)
      setModuleNotes(mapped.moduleNotes)
      setFormationDecisions(mapped.formationDecisions)
      return mapped
    } finally {
      setNotesLoading(false)
    }
  }

  const downloadNotesExport = async (fmt) => {
    setExportingNotes(fmt)
    try {
      const { blob, fileName } = await api.getBlob(
        `/participant/${participant.id}/notes-fiche/export/${fmt}/`,
      )
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = fileName || `releve_notes_${participant.id}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur export', 'error')
    } finally {
      setExportingNotes(null)
    }
  }

  const handleRecalcDecision = async (formationId) => {
    setDecisionRecalculating(prev => ({ ...prev, [formationId]: true }))
    try {
      await api.post(`/evaluations/formations/${formationId}/decisions/recalculer/`)
      await refreshNotesFiche()
      showToast('Décision recalculée', 'success')
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur recalcul décision', 'error')
    } finally {
      setDecisionRecalculating(prev => ({ ...prev, [formationId]: false }))
    }
  }

  const updateModuleDraft = (moduleId, updater) => {
    setModuleNotes(prev => {
      const current = prev[moduleId]
      if (!current || current.error) return prev
      return {
        ...prev,
        [moduleId]: {
          ...current,
          draft: updater(current.draft),
          dirty: true,
        },
      }
    })
  }

  const handleSaveModuleNotes = async (module) => {
    const noteData = moduleNotes[module.id]
    if (!noteData || noteData.error || !noteData.dirty || !noteData.colonneId) return

    const draft = noteData.draft
    const moyenneVal = (draft.moyenne || '').trim()
    const notePayload = []
    const synthesePayload = []

    if (moyenneVal !== '') {
      const note = parseFloat(moyenneVal)
      if (isNaN(note) || note < 0 || note > 20) {
        showToast('La moyenne doit être comprise entre 0 et 20', 'error')
        return
      }
      notePayload.push({
        participant_id: participant.id,
        colonne_id: noteData.colonneId,
        note,
      })
      synthesePayload.push({
        participant_id: participant.id,
        mention: mentionFromMoyenne(note),
        observations: '',
      })
    }

    setNotesSaving(prev => ({ ...prev, [module.id]: true }))
    try {
      const { data } = await api.post(
        `/formations/${module.formation_id}/modules/${module.id}/notes/bulk/`,
        { notes: notePayload, syntheses: synthesePayload },
      )
      if (data.errors?.length > 0) {
        showToast(`${data.saved} enregistrement(s), ${data.errors.length} erreur(s)`, 'warning')
      } else {
        showToast('Moyenne enregistrée', 'success')
      }
      if (module.formation_id) {
        try {
          await api.post(`/evaluations/formations/${module.formation_id}/decisions/recalculer/`)
        } catch {
          // La moyenne est enregistrée ; le recalcul de décision peut être fait manuellement
        }
      }
      await refreshNotesFiche()
    } catch (err) {
      showToast(err?.response?.data?.detail || 'Erreur lors de la sauvegarde', 'error')
    } finally {
      setNotesSaving(prev => ({ ...prev, [module.id]: false }))
    }
  }

  // Charger les séances d'un module
  const handleModuleClick = async (module) => {
    if (expandedModule === module.id) {
      setExpandedModule(null)
      return
    }
    setExpandedModule(module.id)

    if (!moduleSessions[module.id]) {
      setLoadingSessions(true)
      try {
        // Charger les séances du module
        const res = await api.get(`/formations/${module.formation_id}/modules/${module.id}/full/`)
        const sessions = res.data.sessions || []

        // Récupérer les pointages du participant pour ces séances
        const participantPointages = pointages?.filter(pt => pt.module_id === module.id) || []
        const pointagesBySession = participantPointages.reduce((acc, pt) => {
          if (pt.seance_numero) {
            acc[pt.seance_numero] = pt
          }
          return acc
        }, {})

        // Associer les pointages aux séances
        const sessionsWithPointages = sessions.map(s => ({
          ...s,
          pointage: pointagesBySession[s.numero] || null
        }))

        setModuleSessions(prev => ({ ...prev, [module.id]: sessionsWithPointages }))
      } catch (err) {
        console.error('Erreur chargement séances:', err)
      } finally {
        setLoadingSessions(false)
      }
    }
  }

  return (
    <div className="modal-overlay finance-modal" onClick={onClose}>
      <div
        className="modal-content"
        style={{ width: 'min(96vw, 1100px)', maxWidth: '1100px', maxHeight: '92vh', display: 'flex', flexDirection: 'column' }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h5>
            <i className="bi bi-person-badge me-2"></i>
            {participant.nom} {participant.prenom}
            {participant.matricule && (
              <small className="ms-2 opacity-75">({participant.matricule})</small>
            )}
          </h5>
          <button type="button" className="btn-close" disabled={loading} onClick={onClose}>&times;</button>
        </div>

        <div className="modal-body" style={{ overflowY: 'auto', flex: 1, padding: '1rem 1.25rem' }}>
          {loading ? (
            <div className="loading py-5"><div className="spinner"></div></div>
          ) : (
            <>
              <ul className="finance-detail-tabs" role="tablist">
                {PARTICIPANT_DETAIL_TABS.map((tab) => (
                  <li key={tab.id} role="presentation">
                    <button
                      type="button"
                      className={`finance-detail-tab${activeTab === tab.id ? ' active' : ''}`}
                      onClick={() => setActiveTab(tab.id)}
                    >
                      <i className={`bi ${tab.icon}`}></i>
                      <span>{tab.label}</span>
                    </button>
                  </li>
                ))}
              </ul>

              <div className="finance-modal-summary">
                <span><i className="bi bi-journal-bookmark"></i>Modules <strong>{modules?.length ?? 0}</strong></span>
                <span><i className="bi bi-check-circle"></i>Présences <strong>{stats?.nb_seances_terminees ?? 0}</strong></span>
                <span><i className="bi bi-clock-history"></i>Temps total <strong>{Math.round((stats?.total_minutes_presence ?? 0) / 60 * 10) / 10}h</strong></span>
                <span><i className="bi bi-hourglass-split"></i>En cours <strong>{stats?.nb_seances_en_cours ?? 0}</strong></span>
                {stats?.nb_a_verifier > 0 && (
                  <span className="text-danger"><i className="bi bi-exclamation-triangle"></i>À vérifier <strong>{stats.nb_a_verifier}</strong></span>
                )}
              </div>

              {activeTab === 'statistiques' && (
                <div className="grid-2">
                  <div className="card" style={{ padding: '1rem' }}>
                    <h6 className="text-muted mb-3"><i className="bi bi-graph-up me-2"></i>Vue d'ensemble</h6>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                      <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--primary)' }}>{stats?.nb_seances_terminees ?? 0}</div>
                        <small className="text-muted">Présences terminées</small>
                      </div>
                      <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--warning)' }}>{stats?.nb_seances_en_cours ?? 0}</div>
                        <small className="text-muted">En cours</small>
                      </div>
                      <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--success)' }}>{Math.round((stats?.total_minutes_presence ?? 0) / 60 * 10) / 10}h</div>
                        <small className="text-muted">Temps total</small>
                      </div>
                      <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '2rem', fontWeight: 600, color: 'var(--info)' }}>{modules?.length ?? 0}</div>
                        <small className="text-muted">Modules</small>
                      </div>
                    </div>
                  </div>
                  
                  <div className="card" style={{ padding: '1rem' }}>
                    <h6 className="text-muted mb-3"><i className="bi bi-building me-2"></i>Répartition par formation</h6>
                    {(stats?.nb_formations ?? 0) > 0 ? (
                      <div>
                        <div className="mb-2"><strong>{stats.nb_formations}</strong> formation(s) suivie(s)</div>
                        <div className="mb-2"><strong>{stats.nb_modules_inscrits ?? stats.nb_modules_badges ?? 0}</strong> module(s) inscrit(s)</div>
                        {stats.nb_a_verifier > 0 && (
                          <div className="alert alert-warning py-2 small">
                            <i className="bi bi-exclamation-triangle me-1"></i>
                            {stats.nb_a_verifier} pointage(s) nécessitent une vérification
                          </div>
                        )}
                      </div>
                    ) : (
                      <div className="text-muted">Aucune donnée disponible</div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'identite' && (
                <div className="grid-2">
                  <div><small className="text-muted">N° d'inscription</small><div><span className="badge-bg-info">{participant.matricule || '-'}</span></div></div>
                  <div><small className="text-muted">Nom</small><div><strong>{participant.nom || '-'}</strong></div></div>
                  <div><small className="text-muted">Prénom</small><div><strong>{participant.prenom || '-'}</strong></div></div>
                  <div><small className="text-muted">Genre</small><div>{participant.sexe ? <span className={sexeBadge(participant.sexe)}>{sexeLabel(participant.sexe)}</span> : '-'}</div></div>
                  <div><small className="text-muted">Date de naissance</small><div>{formatDate(participant.date_naissance)}</div></div>
                  <div><small className="text-muted">Lieu de naissance</small><div>{participant.lieu_naissance || '-'}</div></div>
                  <div><small className="text-muted">E-mail</small><div>{participant.email || '-'}</div></div>
                  <div><small className="text-muted">Téléphone</small><div>{participant.telephone || '-'}</div></div>
                  <div><small className="text-muted">Téléphone 2</small><div>{participant.telephone2 || '-'}</div></div>
                  <div><small className="text-muted">Type concours</small><div>{participant.type_concours || '-'}</div></div>
                  <div><small className="text-muted">Libellé concours</small><div>{participant.libelle_concours || '-'}</div></div>
                  <div><small className="text-muted">Catégorie</small><div>{participant.categorie || '-'}</div></div>
                  <div><small className="text-muted">Grade</small><div>{participant.grade || '-'}</div></div>
                  <div><small className="text-muted">Groupe</small><div>{participant.groupe || '-'}</div></div>
                  <div><small className="text-muted">Grade-Groupe</small><div>{participant.grade_groupe || '-'}</div></div>
                  <div><small className="text-muted">Vague</small><div>{participant.vague || '-'}</div></div>
                  <div><small className="text-muted">Site</small><div>{participant.site || '-'}</div></div>
                  <div><small className="text-muted">Salle</small><div>{participant.salle || '-'}</div></div>
                  <div style={{ gridColumn: '1 / -1' }}><small className="text-muted">Secrétariat</small><div>{participant.secretariat_nom || '-'}</div></div>
                </div>
              )}

              {activeTab === 'modules' && (
                <>
                  {modules?.length === 0 ? (
                    <div className="finance-empty"><i className="bi bi-journal-bookmark"></i>Aucun module inscrit</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      {modules.map((m) => {
                        const heuresPrevues = m.duree_prevue_heures || 0
                        const stats = moduleStats[m.id] || {
                          heuresEffectuees: 0,
                          nbSeances: 0,
                          nbSeancesEnCours: 0,
                          heuresPrevues,
                          tauxRealisation: 0,
                        }
                        const heuresPrevuesLabel = formatHeuresModule(heuresPrevues)
                        const heuresEffectueesLabel = formatHeuresModule(stats.heuresEffectuees) || '0h'
                        const metaParts = moduleMetaParts(m)
                        const nbSeancesPlanifiees = m.nb_seances_planifiees ?? 0
                        const isExpanded = expandedModule === m.id
                        const sessions = moduleSessions[m.id] || []
                        return (
                          <div key={m.id} className="card" style={{ padding: '0.9rem', cursor: 'pointer' }} onClick={() => handleModuleClick(m)}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.75rem' }}>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 700, fontSize: '0.95rem', lineHeight: 1.35 }}>{m.module}</div>
                                {m.formation && (
                                  <div className="text-muted" style={{ fontSize: '0.85rem', marginTop: '0.2rem' }}>{m.formation}</div>
                                )}
                                {metaParts.length > 0 && (
                                  <div style={{
                                    display: 'flex',
                                    flexWrap: 'wrap',
                                    gap: '0.35rem 0.75rem',
                                    fontSize: '0.8rem',
                                    marginTop: '0.45rem',
                                    color: 'var(--text-muted)',
                                  }}>
                                    {metaParts.map((part, idx) => (
                                      <span key={`${part.label}-${idx}`}>
                                        <i className={`bi ${part.icon} me-1`}></i>{part.label}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {m.date_debut && (
                                  <div className="text-muted" style={{ fontSize: '0.8rem', marginTop: '0.35rem' }}>
                                    <i className="bi bi-calendar3 me-1"></i>
                                    {formatDate(m.date_debut)} → {m.date_fin ? formatDate(m.date_fin) : '?'}
                                  </div>
                                )}
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexShrink: 0 }}>
                                <span className={`badge ${{ 'PLANIFIEE': 'badge-planifiee', 'EN_COURS': 'badge-en-cours', 'TERMINEE': 'badge-terminee', 'SUSPENDUE': 'badge-suspendue' }[m.statut] || 'badge-info'}`}>
                                  {{ 'PLANIFIEE': 'Planifiée', 'EN_COURS': 'En cours', 'TERMINEE': 'Terminée', 'SUSPENDUE': 'Suspendue' }[m.statut] || m.statut}
                                </span>
                                <i className={`bi bi-chevron-${isExpanded ? 'up' : 'down'} text-muted`}></i>
                              </div>
                            </div>

                            <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.65rem', background: 'var(--bg-secondary)', borderRadius: '6px' }}>
                              <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.85rem' }}>
                                <span title="Heures effectuées / heures prévues">
                                  <i className="bi bi-clock-history me-1 text-primary"></i>
                                  <strong>{heuresEffectueesLabel}</strong>
                                  {' / '}
                                  {heuresPrevuesLabel || '—'}
                                  {stats.tauxRealisation > 0 && (
                                    <span className={`ms-1 badge ${stats.tauxRealisation >= 100 ? 'badge-bg-success' : stats.tauxRealisation >= 75 ? 'badge-bg-info' : stats.tauxRealisation >= 50 ? 'badge-bg-warning' : 'badge-bg-danger'}`}
                                          style={{ fontSize: '0.7rem' }}>
                                      {stats.tauxRealisation}%
                                    </span>
                                  )}
                                </span>
                                {stats.nbSeances > 0 ? (
                                  <span title="Séances avec présence terminée">
                                    <i className="bi bi-check-circle me-1 text-success"></i>
                                    <strong>{stats.nbSeances}</strong> présence{stats.nbSeances > 1 ? 's' : ''}
                                  </span>
                                ) : nbSeancesPlanifiees > 0 ? (
                                  <span title="Séances planifiées">
                                    <i className="bi bi-calendar-week me-1 text-info"></i>
                                    <strong>{nbSeancesPlanifiees}</strong> séance{nbSeancesPlanifiees > 1 ? 's' : ''} planifiée{nbSeancesPlanifiees > 1 ? 's' : ''}
                                  </span>
                                ) : (
                                  <span className="text-muted">
                                    <i className="bi bi-calendar-x me-1"></i>Aucune séance
                                  </span>
                                )}
                                {stats.nbSeancesEnCours > 0 && (
                                  <span title="Séances en cours" className="text-warning">
                                    <i className="bi bi-hourglass-split me-1"></i>
                                    {stats.nbSeancesEnCours} en cours
                                  </span>
                                )}
                              </div>
                              {heuresPrevues > 0 && (
                                <div style={{ marginTop: '0.4rem' }}>
                                  <div style={{ height: '6px', background: 'var(--border)', borderRadius: '3px', overflow: 'hidden' }}>
                                    <div style={{
                                      height: '100%',
                                      width: `${Math.min(100, stats.tauxRealisation)}%`,
                                      background: stats.tauxRealisation >= 100 ? 'var(--success)' : stats.tauxRealisation >= 75 ? 'var(--info)' : stats.tauxRealisation >= 50 ? 'var(--warning)' : 'var(--danger)',
                                      transition: 'width 0.3s ease',
                                    }}></div>
                                  </div>
                                </div>
                              )}
                            </div>

                            <div style={{
                              marginTop: '0.5rem',
                              fontSize: '0.8rem',
                              display: 'flex',
                              flexWrap: 'wrap',
                              gap: '0.35rem 1rem',
                              color: 'var(--text-muted)',
                            }}>
                              <span>
                                Volume contractuel : <strong>{heuresPrevuesLabel || 'Non renseigné'}</strong>
                              </span>
                              {m.inscrit_le && (
                                <span>
                                  Inscrit le <strong>{formatDate(m.inscrit_le)}</strong>
                                </span>
                              )}
                            </div>

                            {/* Séances du module (affichage expandé) */}
                            {isExpanded && (
                              <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--border)' }} onClick={(e) => e.stopPropagation()}>
                                <h6 className="text-muted mb-2" style={{ fontSize: '0.85rem' }}>
                                  <i className="bi bi-clock-history me-1"></i>Séances
                                  {loadingSessions && <span className="ms-2 spinner-border spinner-border-sm" style={{ width: '0.8rem', height: '0.8rem' }}></span>}
                                </h6>
                                {sessions.length === 0 ? (
                                  <div className="text-muted small">
                                    {loadingSessions ? 'Chargement...' : 'Aucune séance planifiée'}
                                  </div>
                                ) : (
                                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                    {sessions.map((s) => (
                                      <div key={s.id} style={{
                                        background: 'var(--bg-secondary)',
                                        borderRadius: '6px',
                                        padding: '0.6rem',
                                        borderLeft: `4px solid ${s.pointage ? (s.pointage.statut === 'TERMINE' ? 'var(--success)' : s.pointage.statut === 'EN_COURS' ? 'var(--warning)' : 'var(--secondary)') : 'var(--border)'}`,
                                      }}>
                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                          <div>
                                            <div style={{ fontWeight: 500, fontSize: '0.85rem' }}>
                                              <i className="bi bi-calendar3 me-1"></i>
                                              {formatDate(s.date_journee)}
                                              {s.heure_debut_prevue && (
                                                <span className="text-muted ms-2" style={{ fontSize: '0.8rem' }}>
                                                  <i className="bi bi-clock me-1"></i>
                                                  {s.heure_debut_prevue?.substring(0, 5)} → {s.heure_fin_prevue?.substring(0, 5)}
                                              </span>
                                              )}
                                            </div>
                                            {s.intitule && <div className="text-muted small">{s.intitule}</div>}
                                          </div>
                                          {s.pointage ? (
                                            <span className={`badge ${s.pointage.statut === 'TERMINE' ? 'badge-bg-success' : s.pointage.statut === 'EN_COURS' ? 'badge-bg-warning' : 'badge-bg-secondary'}`} style={{ fontSize: '0.7rem' }}>
                                              {s.pointage.statut === 'TERMINE' ? 'Présent' : s.pointage.statut === 'EN_COURS' ? 'En cours' : s.pointage.statut_label || s.pointage.statut}
                                            </span>
                                          ) : (
                                            <span className="badge badge-bg-secondary" style={{ fontSize: '0.7rem' }}>Non badgé</span>
                                          )}
                                        </div>
                                        {s.pointage && (
                                          <div style={{ fontSize: '0.75rem', marginTop: '0.3rem', color: 'var(--text-muted)' }}>
                                            {s.pointage.timestamp_entree && (
                                              <span className="me-2">
                                                <i className="bi bi-arrow-right-circle me-1 text-success"></i>
                                                {new Date(s.pointage.timestamp_entree).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                                              </span>
                                            )}
                                            {s.pointage.timestamp_sortie && (
                                              <span className="me-2">
                                                <i className="bi bi-arrow-left-circle me-1 text-danger"></i>
                                                {new Date(s.pointage.timestamp_sortie).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                                              </span>
                                            )}
                                            {s.pointage.duree_presence_minutes > 0 && (
                                              <span>
                                                <i className="bi bi-stopwatch me-1 text-info"></i>
                                                {Math.round(s.pointage.duree_presence_minutes)} min
                                              </span>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )
                      })}
                    </div>
                  )}
                </>
              )}

              {activeTab === 'notes' && (
                <>
                  {notesLoading ? (
                    <div className="loading py-4"><div className="spinner"></div></div>
                  ) : modules?.length === 0 ? (
                    <div className="finance-empty"><i className="bi bi-pencil-square"></i>Aucun module inscrit</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="btn btn-outline-primary btn-sm"
                          disabled={!!exportingNotes}
                          onClick={() => downloadNotesExport('pdf')}
                        >
                          {exportingNotes === 'pdf' ? (
                            <><span className="spinner-border spinner-border-sm me-1"></span>Export…</>
                          ) : (
                            <><i className="bi bi-file-earmark-pdf me-1"></i>Export PDF</>
                          )}
                        </button>
                        <button
                          type="button"
                          className="btn btn-outline-secondary btn-sm"
                          disabled={!!exportingNotes}
                          onClick={() => downloadNotesExport('xlsx')}
                        >
                          {exportingNotes === 'xlsx' ? (
                            <><span className="spinner-border spinner-border-sm me-1"></span>Export…</>
                          ) : (
                            <><i className="bi bi-file-earmark-excel me-1"></i>Export Excel</>
                          )}
                        </button>
                      </div>

                      {modules.map((m) => {
                        const noteData = moduleNotes[m.id]
                        const isSaving = notesSaving[m.id]
                        if (!noteData && notesLoading) {
                          return (
                            <div key={m.id} className="card" style={{ padding: '0.9rem' }}>
                              <div className="loading py-2"><div className="spinner"></div></div>
                            </div>
                          )
                        }
                        if (!noteData || noteData.error) {
                          return (
                            <div key={m.id} className="card" style={{ padding: '0.9rem' }}>
                              <strong>{m.module}</strong>
                              <div className="text-muted small mt-1">Impossible de charger la moyenne pour ce cours.</div>
                            </div>
                          )
                        }

                        const draft = noteData.draft || { moyenne: '' }
                        const row = noteData.row
                        const displayMoyenne = draft.moyenne || (row?.moyenne != null ? String(row.moyenne) : '')
                        const mention = mentionFromMoyenne(displayMoyenne) || row?.mention || ''
                        const tauxPresence = row?.taux_presence
                        const heuresPresence = row?.heures_presence
                        const heuresPrevues = row?.heures_prevues ?? m.duree_prevue_heures
                        const seuilTaux = DEFAULT_CRITERES.taux_presence_min
                        const tauxOk = tauxPresence != null && tauxPresence >= seuilTaux

                        return (
                          <div key={m.id} className="card" style={{ padding: '0.9rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                              <div style={{ flex: 1, minWidth: '200px' }}>
                                <strong>{m.module}</strong>
                                {m.formation && <div className="text-muted" style={{ fontSize: '0.85rem' }}>{m.formation}</div>}
                              </div>

                              <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.25rem', flexWrap: 'wrap' }}>
                                <div>
                                  <label className="form-label small text-muted mb-1">Temps effectué / contractuel</label>
                                  <div style={{
                                    fontSize: '1.1rem',
                                    fontWeight: 700,
                                    color: tauxPresence == null ? 'var(--text-muted)' : tauxOk ? 'var(--success)' : 'var(--danger)',
                                  }}>
                                    {tauxPresence != null ? `${tauxPresence}%` : '—'}
                                  </div>
                                  {heuresPresence != null && heuresPrevues != null && (
                                    <small className="text-muted">{heuresPresence}h / {heuresPrevues}h</small>
                                  )}
                                </div>
                                <div>
                                  <label className="form-label small text-muted mb-1">Moyenne /20</label>
                                  {canManageNotes ? (
                                    <input
                                      type="number"
                                      className="form-control form-control-sm"
                                      style={{ width: '100px', fontWeight: 600, fontSize: '1.1rem' }}
                                      min="0"
                                      max="20"
                                      step="0.01"
                                      placeholder="—"
                                      value={draft.moyenne ?? ''}
                                      onChange={(e) => updateModuleDraft(m.id, (prev) => ({
                                        ...prev,
                                        moyenne: e.target.value,
                                      }))}
                                    />
                                  ) : (
                                    <div style={{ fontSize: '1.25rem', fontWeight: 700, minWidth: '60px' }}>
                                      {displayMoyenne || '—'}
                                    </div>
                                  )}
                                </div>
                                {mention && (
                                  <span style={{
                                    fontSize: '0.72rem',
                                    fontWeight: 700,
                                    padding: '4px 10px',
                                    borderRadius: '20px',
                                    background: 'var(--bg-secondary)',
                                    marginBottom: '2px',
                                  }}>
                                    {MENTION_LABELS[mention] || mention}
                                  </span>
                                )}
                              </div>
                            </div>

                            {canManageNotes && (
                              <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  disabled={!noteData.dirty || isSaving || !noteData.colonneId}
                                  onClick={() => handleSaveModuleNotes(m)}
                                >
                                  {isSaving ? (
                                    <><span className="spinner-border spinner-border-sm me-1"></span>Enregistrement…</>
                                  ) : (
                                    <><i className="bi bi-save me-1"></i>Enregistrer</>
                                  )}
                                </button>
                              </div>
                            )}
                          </div>
                        )
                      })}

                      {(() => {
                        const formationsGrouped = Object.values(
                          modules.reduce((acc, m) => {
                            if (!m.formation_id) return acc
                            if (!acc[m.formation_id]) {
                              acc[m.formation_id] = {
                                formationId: m.formation_id,
                                formationLibelle: m.formation || 'Formation',
                                modules: [],
                              }
                            }
                            acc[m.formation_id].modules.push(m)
                            return acc
                          }, {}),
                        )

                        if (!formationsGrouped.length) return null

                        return (
                          <div style={{ marginTop: '0.5rem', paddingTop: '1rem', borderTop: '2px solid var(--border)' }}>
                            <h6 className="text-muted mb-3">
                              <i className="bi bi-clipboard-check me-2"></i>
                              Synthèse & décision finale
                            </h6>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                              {formationsGrouped.map((fg) => {
                                const fd = formationDecisions[fg.formationId]
                                const criteres = fd?.criteres || DEFAULT_CRITERES
                                const computed = computeFormationSummary(fg.modules, moduleNotes, criteres)
                                const apiDec = fd?.decision
                                const moyenneGenerale = apiDec?.moyenne_generale ?? computed.moyenneGenerale
                                const tauxPresence = apiDec?.taux_presence ?? computed.tauxPresence
                                const heuresPresence = apiDec?.total_heures_presence ?? computed.totalPresence
                                const heuresPrevues = apiDec?.total_heures_prevues ?? computed.totalPrevu
                                const decision = apiDec?.decision ?? computed.decision
                                const mention = apiDec?.mention || computed.mention
                                const isRecalculating = decisionRecalculating[fg.formationId]
                                const decisionStyle = DECISION_COLORS[decision] || DECISION_COLORS.EN_ATTENTE
                                const seuilNote = criteres.seuil_admission ?? 12
                                const seuilTaux = criteres.taux_presence_min ?? 80
                                const noteOk = moyenneGenerale != null && moyenneGenerale >= seuilNote
                                const tauxOk = tauxPresence != null && tauxPresence >= seuilTaux

                                return (
                                  <div key={fg.formationId} className="card" style={{ padding: '1rem', background: 'var(--bg-secondary)' }}>
                                    {formationsGrouped.length > 1 && (
                                      <div style={{ fontWeight: 700, marginBottom: '0.75rem' }}>{fg.formationLibelle}</div>
                                    )}
                                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '1rem' }}>
                                      <div>
                                        <small className="text-muted d-block">Moyenne générale</small>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color: noteOk ? 'var(--success)' : moyenneGenerale != null ? 'var(--danger)' : 'var(--text-muted)' }}>
                                          {moyenneGenerale != null ? `${moyenneGenerale}/20` : '—'}
                                        </div>
                                        <small className="text-muted">Seuil : {seuilNote}/20</small>
                                      </div>
                                      <div>
                                        <small className="text-muted d-block">Temps effectué / contractuel</small>
                                        <div style={{ fontSize: '1.5rem', fontWeight: 700, color: tauxOk ? 'var(--success)' : tauxPresence != null ? 'var(--danger)' : 'var(--text-muted)' }}>
                                          {tauxPresence != null ? `${tauxPresence}%` : '—'}
                                        </div>
                                        <small className="text-muted">
                                          {heuresPresence != null && heuresPrevues != null
                                            ? `${heuresPresence}h / ${heuresPrevues}h · Seuil : ${seuilTaux}%`
                                            : `Seuil : ${seuilTaux}%`}
                                        </small>
                                      </div>
                                      <div>
                                        <small className="text-muted d-block">Décision finale</small>
                                        <div style={{ marginTop: '0.35rem' }}>
                                          <span style={{
                                            ...decisionStyle,
                                            fontSize: '0.85rem',
                                            fontWeight: 700,
                                            padding: '4px 12px',
                                            borderRadius: '20px',
                                          }}>
                                            {DECISION_LABELS[decision] || decision}
                                          </span>
                                          {mention && (
                                            <span className="ms-2 text-muted small">{MENTION_LABELS[mention] || mention}</span>
                                          )}
                                        </div>
                                        {apiDec?.generee_auto === false && apiDec?.validee_le && (
                                          <small className="text-muted d-block mt-1">
                                            <i className="bi bi-check-circle me-1"></i>Validée manuellement
                                          </small>
                                        )}
                                      </div>
                                    </div>
                                    <div className="text-muted small mt-2">
                                      <i className="bi bi-info-circle me-1"></i>
                                      Admis si moyenne ≥ {seuilNote}/20 et présence au module ≥ {seuilTaux}%
                                    </div>
                                    {canManageNotes && (
                                      <div style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'flex-end' }}>
                                        <button
                                          type="button"
                                          className="btn btn-outline-primary btn-sm"
                                          disabled={isRecalculating}
                                          onClick={() => handleRecalcDecision(fg.formationId)}
                                        >
                                          {isRecalculating ? (
                                            <><span className="spinner-border spinner-border-sm me-1"></span>Calcul…</>
                                          ) : (
                                            <><i className="bi bi-arrow-clockwise me-1"></i>Recalculer la décision</>
                                          )}
                                        </button>
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )
                      })()}
                    </div>
                  )}
                </>
              )}

              {activeTab === 'seances' && (
                <>
                  {pointages?.length === 0 ? (
                    <div className="finance-empty"><i className="bi bi-clock-history"></i>Aucun badgeage enregistré</div>
                  ) : (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                      {/* Résumé par module */}
                      <div className="card" style={{ padding: '0.75rem', background: 'var(--bg-secondary)' }}>
                        <h6 className="text-muted mb-2" style={{ fontSize: '0.85rem' }}>
                          <i className="bi bi-graph-up me-1"></i>Résumé par module
                        </h6>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                          {sessionsByModuleList.map((group) => {
                            const totalMinutes = group.sessions
                              .filter(pt => pt.statut === 'TERMINE' && pt.duree_presence_minutes > 0)
                              .reduce((sum, pt) => sum + (pt.duree_presence_minutes || 0), 0)
                            const heures = Math.round(totalMinutes / 60 * 10) / 10
                            const nbTerminees = group.sessions.filter(pt => pt.statut === 'TERMINE').length
                            const nbEnCours = group.sessions.filter(pt => pt.statut === 'EN_COURS').length
                            return (
                              <div key={`summary-${group.formation_titre}-${group.module_intitule}`}
                                   style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.85rem' }}>
                                <span><i className="bi bi-journal-bookmark me-1 text-primary"></i>{group.formation_titre}{group.module_intitule && ` — ${group.module_intitule}`}</span>
                                <span>
                                  <span className="me-2" title="Heures effectuées"><i className="bi bi-clock me-1 text-success"></i><strong>{heures}h</strong></span>
                                  <span className="me-2" title="Séances terminées"><i className="bi bi-check-circle me-1 text-success"></i>{nbTerminees}</span>
                                  {nbEnCours > 0 && <span className="text-warning" title="En cours"><i className="bi bi-hourglass-split me-1"></i>{nbEnCours}</span>}
                                </span>
                              </div>
                            )
                          })}
                        </div>
                      </div>

                      {sessionsByModuleList.map((group) => (
                        <div key={`${group.formation_titre}-${group.module_intitule}`} className="card" style={{ padding: '1rem' }}>
                          <h6 style={{ marginBottom: '0.75rem', paddingBottom: '0.5rem', borderBottom: '1px solid var(--border)' }}>
                            <i className="bi bi-journal-bookmark me-2"></i>
                            {group.formation_titre}
                            {group.module_intitule && <span className="text-muted"> — {group.module_intitule}</span>}
                          </h6>
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                            {group.sessions.map((pt) => (
                              <div key={pt.id} style={{ 
                                background: 'var(--bg-secondary)', 
                                borderRadius: '6px', 
                                padding: '0.75rem',
                                borderLeft: `4px solid ${pt.statut === 'TERMINE' ? 'var(--success)' : pt.statut === 'EN_COURS' ? 'var(--warning)' : 'var(--secondary)'}`,
                              }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
                                  <div>
                                    <div style={{ fontWeight: 500 }}>
                                      <i className="bi bi-calendar3 me-1"></i>
                                      {pt.date_journee}
                                      {pt.temps_cours?.heure_debut_prevue && (
                                        <span className="text-muted ms-2" style={{ fontSize: '0.85rem' }}>
                                          <i className="bi bi-clock me-1"></i>
                                          {pt.temps_cours.heure_debut_prevue?.substring(0, 5)} → {pt.temps_cours.heure_fin_prevue?.substring(0, 5)}
                                        </span>
                                      )}
                                    </div>
                                    <div style={{ fontSize: '0.8rem', marginTop: '0.25rem' }}>
                                      {pt.seance_intitule && <span className="me-2">{pt.seance_intitule}</span>}
                                      {pt.seance_numero && <span className="text-muted">(Séance {pt.seance_numero})</span>}
                                    </div>
                                  </div>
                                  <span className={`badge ${pt.statut === 'TERMINE' ? 'badge-bg-success' : pt.statut === 'EN_COURS' ? 'badge-bg-warning' : 'badge-bg-secondary'}`}>
                                    {pt.statut_label || pt.statut}
                                  </span>
                                </div>
                                
                                <div style={{ display: 'flex', gap: '1.5rem', marginTop: '0.5rem', flexWrap: 'wrap', fontSize: '0.8rem' }}>
                                  <span>
                                    <i className="bi bi-arrow-right-circle me-1 text-success"></i>
                                    Entrée : {pt.timestamp_entree ? new Date(pt.timestamp_entree).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '-'}
                                  </span>
                                  <span>
                                    <i className="bi bi-arrow-left-circle me-1 text-danger"></i>
                                    Sortie : {pt.timestamp_sortie ? new Date(pt.timestamp_sortie).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }) : '-'}
                                  </span>
                                  {pt.duree_presence_minutes > 0 && (
                                    <span>
                                      <i className="bi bi-stopwatch me-1 text-info"></i>
                                      Durée : <strong>{Math.round(pt.duree_presence_minutes)} min</strong>
                                    </span>
                                  )}
                                </div>

                                {/* Détails techniques du badgeage */}
                                <div style={{ display: 'flex', gap: '1rem', marginTop: '0.5rem', flexWrap: 'wrap', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                                  {pt.device_id && (
                                    <span title={`Appareil: ${pt.device_id}`}>
                                      <i className="bi bi-phone me-1"></i>
                                      {pt.device_id.substring(0, 12)}...
                                    </span>
                                  )}
                                  {pt.geolocalisation && (
                                    <span title={`Lat: ${pt.geolocalisation.latitude}, Lng: ${pt.geolocalisation.longitude}`}>
                                      <i className="bi bi-geo-alt me-1 text-primary"></i>
                                      📍 {pt.geolocalisation.precision_m ? `±${Math.round(pt.geolocalisation.precision_m)}m` : ''}
                                    </span>
                                  )}
                                  {pt.appareil?.batterie_pct !== undefined && (
                                    <span title={`Batterie: ${pt.appareil.batterie_pct}%${pt.appareil.en_charge ? ' (en charge)' : ''}`}>
                                      <i className={`bi bi-battery-${pt.appareil.batterie_pct > 50 ? 'full' : pt.appareil.batterie_pct > 25 ? 'half' : 'low'} me-1`}></i>
                                      {pt.appareil.batterie_pct}%
                                    </span>
                                  )}
                                  {pt.last_heartbeat_at && (
                                    <span title={`Dernier heartbeat: ${new Date(pt.last_heartbeat_at).toLocaleString('fr-FR')}`}>
                                      <i className="bi bi-activity me-1"></i>
                                      {new Date(pt.last_heartbeat_at).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}
                                    </span>
                                  )}
                                  {pt.sorties_geofence_count > 0 && (
                                    <span className="text-danger" title={`Sorties du périmètre: ${pt.sorties_geofence_count}`}>
                                      <i className="bi bi-exclamation-triangle me-1"></i>
                                      {pt.sorties_geofence_count} sortie(s) geofence
                                    </span>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </>
              )}
            </>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn-secondary" disabled={loading} onClick={onClose}>Fermer</button>
        </div>
      </div>
    </div>
  )
}
