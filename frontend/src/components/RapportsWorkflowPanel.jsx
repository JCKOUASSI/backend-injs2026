import { useCallback, useEffect, useMemo, useState } from 'react'
import api from '../services/api'
import { useToast } from '../context/ToastContext'
import { appendPeriodToSearchParams } from '../utils/financePeriod'

const GENERATION_ROLES = ['ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN', 'CHEF_SECRETARIAT', 'SECRETARIAT']
const VALIDATION_ROLES = ['ADMIN', 'DIRECTION', 'CHEF_INJS_ADMIN', 'INJS_ADMIN']

const RAPPORT_TYPES = [
  { value: 'MENSUEL', label: 'Mensuel' },
  { value: 'HEBDOMADAIRE', label: 'Hebdomadaire' },
  { value: 'TRIMESTRIEL', label: 'Trimestriel' },
  { value: 'SEMESTRIEL', label: 'Semestriel' },
  { value: 'ANNUEL', label: 'Annuel' },
  { value: 'QUOTIDIEN', label: 'Quotidien' },
  { value: 'MI_PARCOURS', label: 'Mi-parcours' },
  { value: 'CONSOLIDE', label: 'Consolidé FAB + FAC' },
  { value: 'FAB', label: 'FAB' },
  { value: 'FAC', label: 'FAC' },
]

const STATUT_META = {
  BROUILLON: { label: 'Brouillon', bg: '#f1f5f9', color: '#475569' },
  EN_VALIDATION: { label: 'En validation', bg: '#fffae1', color: '#f5b417' },
  VALIDE: { label: 'Validé', bg: '#e8eff5', color: '#125a99' },
  PUBLIE: { label: 'Publié', bg: '#e3f2fd', color: '#1565c0' },
  REJETE: { label: 'Rejeté', bg: '#ffebee', color: '#c62828' },
}

function fmtDate(d) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleDateString('fr-FR')
  } catch {
    return d
  }
}

function fmtDateTime(d) {
  if (!d) return '—'
  try {
    return new Date(d).toLocaleString('fr-FR', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch {
    return d
  }
}

function StatutBadge({ statut }) {
  const m = STATUT_META[statut] || { label: statut, bg: '#f1f5f9', color: '#64748b' }
  return (
    <span style={{
      display: 'inline-block', padding: '0.12rem 0.45rem', borderRadius: 6,
      fontSize: '0.72rem', fontWeight: 700, background: m.bg, color: m.color,
    }}>
      {m.label}
    </span>
  )
}

function scopeQuery(formationId, secretariatId, appliedVhPeriod) {
  const params = new URLSearchParams()
  if (formationId) params.set('formation_id', formationId)
  if (secretariatId) params.set('secretariat_id', secretariatId)
  appendPeriodToSearchParams(params, appliedVhPeriod)
  const qs = params.toString()
  return qs ? `?${qs}` : ''
}

export default function RapportsWorkflowPanel({
  user,
  formationId,
  secretariatId,
  appliedVhPeriod,
}) {
  const { showToast } = useToast()
  const role = user?.role || ''
  const canGenerate = GENERATION_ROLES.includes(role)
  const canValidate = VALIDATION_ROLES.includes(role)
  const canAdmin = canValidate

  const [rapports, setRapports] = useState([])
  const [loading, setLoading] = useState(false)
  const [selectedId, setSelectedId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  const [showCreate, setShowCreate] = useState(false)
  const [createForm, setCreateForm] = useState({ type: 'MENSUEL', titre: '', commentaire: '' })

  const [showEdit, setShowEdit] = useState(false)
  const [editForm, setEditForm] = useState({ titre: '', commentaire: '', type: 'MENSUEL', motif: '' })

  const [promptAction, setPromptAction] = useState(null)
  const [promptText, setPromptText] = useState('')

  const scopeQs = useMemo(
    () => scopeQuery(formationId, secretariatId, appliedVhPeriod),
    [formationId, secretariatId, appliedVhPeriod],
  )

  const fetchList = useCallback(async () => {
    setLoading(true)
    try {
      const { data } = await api.get(`/statistiques/rapports/${scopeQs}`)
      setRapports(Array.isArray(data) ? data : [])
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erreur chargement rapports', 'error')
      setRapports([])
    } finally {
      setLoading(false)
    }
  }, [scopeQs, showToast])

  const fetchDetail = useCallback(async (id) => {
    if (!id) {
      setDetail(null)
      return
    }
    setLoadingDetail(true)
    try {
      const { data } = await api.get(`/statistiques/rapports/${id}/`)
      setDetail(data)
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erreur chargement détail', 'error')
      setDetail(null)
    } finally {
      setLoadingDetail(false)
    }
  }, [showToast])

  useEffect(() => { fetchList() }, [fetchList])

  useEffect(() => {
    fetchDetail(selectedId)
  }, [selectedId, fetchDetail])

  const selected = useMemo(
    () => rapports.find(r => r.id === selectedId) || null,
    [rapports, selectedId],
  )

  const refresh = async (id = selectedId) => {
    await fetchList()
    if (id) await fetchDetail(id)
  }

  const runWorkflow = async (action, extra = {}) => {
    if (!selectedId) return
    setActionLoading(true)
    try {
      await api.post(`/statistiques/rapports/${selectedId}/workflow/`, { action, ...extra })
      showToast(`Action « ${action} » effectuée`, 'success')
      setPromptAction(null)
      setPromptText('')
      await refresh(selectedId)
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erreur workflow', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  const handleCreate = async () => {
    setActionLoading(true)
    try {
      const { data } = await api.post(`/statistiques/rapports/${scopeQs}`, createForm)
      showToast('Rapport généré', 'success')
      setShowCreate(false)
      setCreateForm({ type: 'MENSUEL', titre: '', commentaire: '' })
      await fetchList()
      if (data?.id) setSelectedId(data.id)
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erreur génération', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  const handleEdit = async () => {
    if (!selectedId) return
    setActionLoading(true)
    try {
      const payload = {
        titre: editForm.titre,
        commentaire: editForm.commentaire,
        type: editForm.type,
      }
      if (editForm.motif?.trim()) payload.motif = editForm.motif.trim()
      await api.patch(`/statistiques/rapports/${selectedId}/`, payload)
      showToast('Rapport modifié', 'success')
      setShowEdit(false)
      await refresh(selectedId)
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erreur modification', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  const handleDelete = async (motif) => {
    if (!selectedId) return
    setActionLoading(true)
    try {
      await api.delete(`/statistiques/rapports/${selectedId}/`, { data: { motif } })
      showToast('Rapport supprimé', 'success')
      setPromptAction(null)
      setPromptText('')
      setSelectedId(null)
      setDetail(null)
      await fetchList()
    } catch (e) {
      showToast(e.response?.data?.detail || 'Erreur suppression', 'error')
    } finally {
      setActionLoading(false)
    }
  }

  const openEdit = () => {
    const src = detail || selected
    if (!src) return
    setEditForm({
      titre: src.titre || '',
      commentaire: src.commentaire || '',
      type: src.type || 'MENSUEL',
      motif: '',
    })
    setShowEdit(true)
  }

  const canEditSelected = () => {
    const st = (detail || selected)?.statut
    if (!st) return false
    if (canAdmin) return true
    if (!canGenerate) return false
    return !['VALIDE', 'PUBLIE'].includes(st)
  }

  const kpis = detail?.donnees_json?.kpis

  const promptSubmit = () => {
    if (promptAction === 'rejeter') {
      if (!promptText.trim()) {
        showToast('Motif de rejet requis', 'error')
        return
      }
      runWorkflow('rejeter', { commentaire: promptText.trim(), motif: promptText.trim() })
      return
    }
    if (promptAction === 'supprimer') {
      handleDelete(promptText.trim())
      return
    }
    if (promptAction === 'valider' || promptAction === 'publier') {
      runWorkflow(promptAction, { commentaire: promptText.trim() })
    }
  }

  return (
    <div style={{ marginBottom: '1.25rem' }}>
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center',
        marginBottom: '0.75rem',
      }}>
        <h3 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 700, color: '#1e293b', flex: 1 }}>
          <i className="bi bi-file-earmark-check me-2" style={{ color: '#125a99' }}/>
          Rapports périodiques — validation
        </h3>
        <button type="button" className="btn btn-sm btn-outline-secondary" onClick={fetchList} disabled={loading}>
          <i className="bi bi-arrow-clockwise me-1"/>Actualiser
        </button>
        {canGenerate && (
          <button type="button" className="btn btn-sm btn-success" onClick={() => setShowCreate(true)}>
            <i className="bi bi-plus-lg me-1"/>Générer un rapport
          </button>
        )}
      </div>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'minmax(260px, 320px) 1fr',
        gap: '1rem',
        alignItems: 'start',
      }}>
        <div style={{
          background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
          overflow: 'hidden', maxHeight: '52vh', overflowY: 'auto',
        }}>
          <div style={{
            padding: '0.6rem 0.85rem', background: '#f8fafc', borderBottom: '1px solid #e2e8f0',
            fontSize: '0.78rem', color: '#64748b', fontWeight: 600,
          }}>
            {loading ? 'Chargement…' : `${rapports.length} rapport${rapports.length > 1 ? 's' : ''}`}
          </div>
          {!loading && rapports.length === 0 && (
            <div style={{ padding: '1.5rem', color: '#94a3b8', fontSize: '0.85rem', textAlign: 'center' }}>
              Aucun rapport pour ce périmètre.
            </div>
          )}
          {rapports.map(r => (
            <button
              key={r.id}
              type="button"
              onClick={() => setSelectedId(r.id)}
              style={{
                display: 'block', width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                padding: '0.6rem 0.85rem', borderBottom: '1px solid #f1f5f9',
                background: selectedId === r.id ? '#f0f6fd' : '#fff',
              }}
            >
              <div style={{ fontWeight: 700, fontSize: '0.82rem', color: '#1e293b', marginBottom: '0.2rem' }}>
                {r.titre}
              </div>
              <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap', alignItems: 'center' }}>
                <StatutBadge statut={r.statut}/>
                <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>
                  {fmtDate(r.periode_debut)} → {fmtDate(r.periode_fin)}
                </span>
              </div>
            </button>
          ))}
        </div>

        <div style={{
          background: '#fff', borderRadius: 10, boxShadow: '0 1px 4px rgba(0,0,0,0.07)',
          padding: '1rem', minHeight: 220,
        }}>
          {!selectedId ? (
            <div style={{ color: '#94a3b8', fontSize: '0.88rem', textAlign: 'center', padding: '2rem 1rem' }}>
              Sélectionnez un rapport dans la liste.
            </div>
          ) : loadingDetail ? (
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <div className="spinner"/>
            </div>
          ) : (
            <>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'flex-start', marginBottom: '0.85rem' }}>
                <div style={{ flex: 1, minWidth: 200 }}>
                  <h4 style={{ margin: '0 0 0.35rem', fontSize: '1rem', fontWeight: 700 }}>{detail?.titre || selected?.titre}</h4>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', fontSize: '0.78rem', color: '#64748b' }}>
                    <StatutBadge statut={detail?.statut || selected?.statut}/>
                    <span>Type : {RAPPORT_TYPES.find(t => t.value === (detail?.type || selected?.type))?.label || detail?.type}</span>
                    <span>Période : {fmtDate(detail?.periode_debut || selected?.periode_debut)} — {fmtDate(detail?.periode_fin || selected?.periode_fin)}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem' }}>
                  {canEditSelected() && (
                    <button type="button" className="btn btn-sm btn-outline-secondary" disabled={actionLoading} onClick={openEdit}>
                      <i className="bi bi-pencil me-1"/>Modifier
                    </button>
                  )}
                  {canAdmin && (
                    <button
                      type="button"
                      className="btn btn-sm btn-outline-danger"
                      disabled={actionLoading}
                      onClick={() => { setPromptAction('supprimer'); setPromptText('') }}
                    >
                      <i className="bi bi-trash me-1"/>Supprimer
                    </button>
                  )}
                </div>
              </div>

              <div style={{ fontSize: '0.8rem', color: '#64748b', marginBottom: '0.85rem', lineHeight: 1.5 }}>
                <div><strong>Générateur :</strong> {detail?.generateur || selected?.generateur__username || '—'}</div>
                <div><strong>Validateur :</strong> {detail?.validateur || selected?.validateur__username || '—'}</div>
                <div><strong>Créé le :</strong> {fmtDateTime(detail?.created_at || selected?.created_at)}</div>
                {(detail?.commentaire || selected?.commentaire) && (
                  <div style={{ marginTop: '0.35rem' }}>
                    <strong>Commentaire :</strong> {detail?.commentaire || selected?.commentaire}
                  </div>
                )}
              </div>

              {kpis && (
                <div style={{
                  display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
                  gap: '0.5rem', marginBottom: '0.85rem',
                }}>
                  {[
                    { label: 'Assiduité', value: `${kpis.taux_presence ?? '—'} %` },
                    { label: 'Exéc. VH', value: `${kpis.taux_execution_vh ?? '—'} %` },
                    { label: 'Séances', value: kpis.nb_seances ?? '—' },
                    { label: 'Étudiants', value: kpis.nb_auditeurs ?? '—' },
                  ].map(k => (
                    <div key={k.label} style={{ background: '#f8fafc', borderRadius: 8, padding: '0.5rem 0.65rem' }}>
                      <div style={{ fontSize: '0.68rem', color: '#94a3b8' }}>{k.label}</div>
                      <div style={{ fontWeight: 700, fontSize: '0.9rem' }}>{k.value}</div>
                    </div>
                  ))}
                </div>
              )}

              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', paddingTop: '0.5rem', borderTop: '1px solid #f1f5f9' }}>
                {canGenerate && (detail?.statut || selected?.statut) === 'BROUILLON' && (
                  <button type="button" className="btn btn-sm btn-primary" disabled={actionLoading} onClick={() => runWorkflow('soumettre')}>
                    <i className="bi bi-send me-1"/>Soumettre à validation
                  </button>
                )}
                {canValidate && (detail?.statut || selected?.statut) === 'EN_VALIDATION' && (
                  <>
                    <button type="button" className="btn btn-sm btn-success" disabled={actionLoading} onClick={() => { setPromptAction('valider'); setPromptText('') }}>
                      <i className="bi bi-check2-circle me-1"/>Valider
                    </button>
                    <button type="button" className="btn btn-sm btn-outline-danger" disabled={actionLoading} onClick={() => { setPromptAction('rejeter'); setPromptText('') }}>
                      <i className="bi bi-x-circle me-1"/>Rejeter
                    </button>
                  </>
                )}
                {canValidate && (detail?.statut || selected?.statut) === 'VALIDE' && (
                  <button type="button" className="btn btn-sm btn-success" disabled={actionLoading} onClick={() => { setPromptAction('publier'); setPromptText('') }}>
                    <i className="bi bi-globe me-1"/>Publier
                  </button>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {showCreate && (
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Générer un rapport</h5>
                <button type="button" className="btn-close" onClick={() => setShowCreate(false)}/>
              </div>
              <div className="modal-body">
                <p className="text-muted small">Snapshot des statistiques du périmètre filtré (formation / secrétariat).</p>
                <div className="mb-3">
                  <label className="form-label">Type</label>
                  <select className="form-select form-select-sm" value={createForm.type} onChange={e => setCreateForm(f => ({ ...f, type: e.target.value }))}>
                    {RAPPORT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div className="mb-3">
                  <label className="form-label">Titre (optionnel)</label>
                  <input className="form-control form-control-sm" value={createForm.titre} onChange={e => setCreateForm(f => ({ ...f, titre: e.target.value }))} placeholder="Auto si vide"/>
                </div>
                <div className="mb-0">
                  <label className="form-label">Commentaire</label>
                  <textarea className="form-control form-control-sm" rows={2} value={createForm.commentaire} onChange={e => setCreateForm(f => ({ ...f, commentaire: e.target.value }))}/>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowCreate(false)}>Annuler</button>
                <button type="button" className="btn btn-success btn-sm" disabled={actionLoading} onClick={handleCreate}>Générer</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showEdit && (
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">Modifier le rapport</h5>
                <button type="button" className="btn-close" onClick={() => setShowEdit(false)}/>
              </div>
              <div className="modal-body">
                <div className="mb-3">
                  <label className="form-label">Titre</label>
                  <input className="form-control form-control-sm" value={editForm.titre} onChange={e => setEditForm(f => ({ ...f, titre: e.target.value }))}/>
                </div>
                <div className="mb-3">
                  <label className="form-label">Type</label>
                  <select className="form-select form-select-sm" value={editForm.type} onChange={e => setEditForm(f => ({ ...f, type: e.target.value }))}>
                    {RAPPORT_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
                  </select>
                </div>
                <div className="mb-3">
                  <label className="form-label">Commentaire</label>
                  <textarea className="form-control form-control-sm" rows={2} value={editForm.commentaire} onChange={e => setEditForm(f => ({ ...f, commentaire: e.target.value }))}/>
                </div>
                {canAdmin && (
                  <div className="mb-0">
                    <label className="form-label">Motif (notification)</label>
                    <input className="form-control form-control-sm" value={editForm.motif} onChange={e => setEditForm(f => ({ ...f, motif: e.target.value }))} placeholder="Optionnel"/>
                  </div>
                )}
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowEdit(false)}>Annuler</button>
                <button type="button" className="btn btn-primary btn-sm" disabled={actionLoading} onClick={handleEdit}>Enregistrer</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {promptAction && (
        <div className="modal show d-block" tabIndex={-1} style={{ background: 'rgba(0,0,0,0.4)' }}>
          <div className="modal-dialog modal-dialog-centered">
            <div className="modal-content">
              <div className="modal-header">
                <h5 className="modal-title">
                  {promptAction === 'rejeter' && 'Rejeter le rapport'}
                  {promptAction === 'supprimer' && 'Supprimer le rapport'}
                  {promptAction === 'valider' && 'Valider le rapport'}
                  {promptAction === 'publier' && 'Publier le rapport'}
                </h5>
                <button type="button" className="btn-close" onClick={() => { setPromptAction(null); setPromptText('') }}/>
              </div>
              <div className="modal-body">
                <label className="form-label">
                  {promptAction === 'rejeter' ? 'Motif de rejet (obligatoire)' : 'Commentaire (optionnel)'}
                </label>
                <textarea className="form-control form-control-sm" rows={3} value={promptText} onChange={e => setPromptText(e.target.value)}/>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setPromptAction(null); setPromptText('') }}>Annuler</button>
                <button
                  type="button"
                  className={`btn btn-sm ${promptAction === 'rejeter' || promptAction === 'supprimer' ? 'btn-danger' : 'btn-success'}`}
                  disabled={actionLoading}
                  onClick={promptSubmit}
                >
                  Confirmer
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
