import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import api from '../services/api'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../context/ToastContext'
import { useAuth } from '../context/AuthContext'
import {
  buildSecretariatsSearchParams,
  LIST_STORAGE_KEYS,
  readSecretariatsExpanded,
} from '../utils/listFilters'
import { usePersistedListQuery } from '../hooks/usePersistedListQuery'
import { isAdminLevelRole } from '../utils/roles'

const emptyForm = { nom: '', type: '', description: '' }

/** Utilisateurs rattachés au secrétariat hors comptes badgeage (auditeurs, formateurs). */
function membresEquipe(membres) {
  return (membres || []).filter((m) => !['AUDITEUR', 'FORMATEUR'].includes(m.role))
}

export default function Secretariats() {
  const { user: currentUser } = useAuth()
  const isDFRC = isAdminLevelRole(currentUser?.role)
  const isSecretariat = currentUser?.role === 'SECRETARIAT'
  const [secretariats, setSecretariats] = useState([])
  const [typesSecretariat, setTypesSecretariat] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [showModal, setShowModal] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState({ ...emptyForm })
  const [formError, setFormError] = useState('')
  const [saving, setSaving] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState(null)
  const { showToast } = useToast()

  const [searchParams] = useSearchParams()
  const [expanded, setExpanded] = useState(() => {
    const id = readSecretariatsExpanded(searchParams)
    return id ? Number(id) || id : null
  })

  usePersistedListQuery(
    LIST_STORAGE_KEYS.secretariats,
    () => buildSecretariatsSearchParams(expanded),
    [expanded],
  )

  useEffect(() => { loadSecretariats() }, [])

  const loadSecretariats = async () => {
    setLoading(true)
    try {
      const [secRes, typesRes] = await Promise.all([
        api.get('/formations/secretariats/'),
        api.get('/formations/ref/types-secretariat/'),
      ])
      const data = Array.isArray(secRes.data) ? secRes.data : (secRes.data.results || [])
      setSecretariats(data)
      setTypesSecretariat(Array.isArray(typesRes.data) ? typesRes.data : [])
    } catch {
      setError('Erreur lors du chargement des secrétariats')
    } finally { setLoading(false) }
  }

  const openCreate = () => {
    setEditingId(null)
    setForm({ ...emptyForm })
    setFormError('')
    setShowModal(true)
  }

  const openEdit = (s) => {
    setEditingId(s.id)
    setForm({ nom: s.nom, type: s.type || '', description: s.description || '' })
    // s.type est l'id FK retourné par l'API Django (via SecretariatSerializer)
    setFormError('')
    setShowModal(true)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setFormError('')
    setSaving(true)
    try {
      if (editingId) {
        await api.patch(`/formations/secretariats/${editingId}/`, form)
      } else {
        await api.post('/formations/secretariats/', form)
      }
      setShowModal(false)
      loadSecretariats()
      showToast(editingId ? 'Secrétariat modifié' : 'Secrétariat créé')
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object') {
        const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
        setFormError(msgs.join('\n'))
      } else {
        setFormError('Erreur lors de la sauvegarde')
      }
    } finally { setSaving(false) }
  }

  const handleDelete = (id) => {
    setConfirmDialog({
      message: 'Supprimer ce secrétariat ?',
      detail: 'Les utilisateurs associés ne seront pas supprimés.',
      onConfirm: async () => {
        try { await api.delete(`/formations/secretariats/${id}/`); loadSecretariats(); showToast('Secrétariat supprimé') }
        catch { showToast('Erreur lors de la suppression', 'error') }
      }
    })
  }

  const getTypeBadge = (typeId) => {
    const t = typesSecretariat.find(x => x.id === typeId)
    if (!t) return null
    const colors = ['#1565C0', '#125A99', '#E69700', '#6A1B9A', '#00838F']
    const idx = typesSecretariat.indexOf(t)
    return { label: t.libelle, color: colors[idx % colors.length] }
  }

  return (
    <div>
      <div className="card">
        <div className="card-body">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <h6 className="mb-0" style={{ fontWeight: 700 }}>
                <i className="bi bi-building me-2"></i>Gestion des secrétariats
              </h6>
              <small className="text-muted">Créez les secrétariats puis assignez-leur des utilisateurs via la page Utilisateurs.</small>
            </div>
            {isDFRC && (
              <button className="btn btn-dfrc" onClick={openCreate}>
                <i className="bi bi-plus-lg me-1"></i>Nouveau secrétariat
              </button>
            )}
          </div>
        </div>
      </div>

      {error && <div className="error-message">{error}</div>}

      <div className="card">
        <div className="card-header-bar">
          <span><i className="bi bi-building me-2"></i>Liste des secrétariats</span>
          <span className="badge-bg-secondary">{secretariats.length} secrétariat(s)</span>
        </div>
        <div className="card-body-flush">
          {loading ? (
            <div className="loading"><div className="spinner"></div></div>
          ) : secretariats.length === 0 ? (
            <div className="text-center py-5 text-muted">
              <i className="bi bi-building" style={{ fontSize: '2rem' }}></i>
              <p className="mt-2">Aucun secrétariat. Cliquez sur « Nouveau secrétariat » pour commencer.</p>
            </div>
          ) : (
            <div className="table-container">
              <table className="table">
                <thead>
                  <tr>
                    <th>Numéro</th>
                    <th>Nom</th>
                    <th>Type</th>
                    <th>Membres</th>
                    <th>Étudiants</th>
                    <th>Modules</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {secretariats.map(s => {
                    const equipe = membresEquipe(s.membres)
                    return (
                    <React.Fragment key={s.id}>
                      <tr>
                        <td><code>{s.numero}</code></td>
                        <td>
                          <strong>{s.nom}</strong>
                          {s.description && <><br/><small className="text-muted">{s.description}</small></>}
                        </td>
                        <td>
                          {(() => { const b = getTypeBadge(s.type); return b
                            ? <span style={{ background: b.color, color: '#fff', padding: '2px 8px', borderRadius: 4, fontSize: '0.75rem', fontWeight: 600 }}>{b.label}</span>
                            : <span className="text-muted">—</span> })()
                          }
                        </td>
                        <td>
                          <button
                            className="btn btn-outline-secondary btn-sm"
                            onClick={() => setExpanded(expanded === s.id ? null : s.id)}
                            title="Membres de l'équipe (secrétariat, encadrants…) — hors comptes étudiants"
                          >
                            <i className={`bi bi-${expanded === s.id ? 'chevron-up' : 'people'} me-1`}></i>
                            {equipe.length}
                          </button>
                        </td>
                        <td>
                          <span className="badge-bg-secondary">{s.nb_participants}</span>
                        </td>
                        <td>
                          <span className="badge-bg-secondary">{s.nb_modules}</span>
                        </td>
                        <td>
                          <div className="btn-group">
                            {(isDFRC || (isSecretariat && currentUser?.secretariat === s.id)) && (
                              <button onClick={() => openEdit(s)} className="btn btn-outline-primary btn-sm" title="Modifier">
                                <i className="bi bi-pencil"></i>
                              </button>
                            )}
                            {isDFRC && (
                              <button onClick={() => handleDelete(s.id)} className="btn btn-outline-danger btn-sm" title="Supprimer">
                                <i className="bi bi-trash"></i>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                      {expanded === s.id && (
                        <tr key={`${s.id}-membres`}>
                          <td colSpan="7" style={{ background: '#f8f9fa', padding: '0.5rem 1.5rem' }}>
                            {equipe.length > 0 ? (
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem', padding: '0.4rem 0' }}>
                                {equipe.map(m => (
                                  <span key={m.id} style={{
                                    background: m.is_active ? '#e8eff5' : '#fce4ec',
                                    border: `1px solid ${m.is_active ? '#94c0e7' : '#f48fb1'}`,
                                    borderRadius: 4, padding: '2px 8px', fontSize: '0.8rem'
                                  }}>
                                    <i className="bi bi-person me-1"></i>{m.nom}
                                    <span className="text-muted ms-1">({m.role})</span>
                                    {!m.is_active && <span className="text-danger ms-1">inactif</span>}
                                  </span>
                                ))}
                              </div>
                            ) : (
                              <small className="text-muted">
                                <i className="bi bi-info-circle me-1"></i>
                                Aucun membre d&apos;équipe (secrétariat, encadrants…). Rattachez-les depuis <strong>Utilisateurs</strong>. Les comptes badge <strong>Étudiant</strong> et <strong>Enseignant</strong> sont listés dans <strong>Utilisateurs</strong> — onglets dédiés.
                              </small>
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
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
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h5><i className="bi bi-building me-2"></i>{editingId ? 'Modifier le secrétariat' : 'Nouveau secrétariat'}</h5>
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
                  <label className="form-label">Nom *</label>
                  <input type="text" className="form-control" required
                    value={form.nom} onChange={e => setForm({ ...form, nom: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">Type</label>
                  <select className="form-control" value={form.type} onChange={e => setForm({ ...form, type: e.target.value ? parseInt(e.target.value) : '' })}>
                    <option value="">-- Aucun --</option>
                    {typesSecretariat.map(t => (
                      <option key={t.id} value={t.id}>{t.libelle}</option>
                    ))}
                  </select>
                  <small className="text-muted">Le type détermine les grades d'étudiants visibles pour ce secrétariat.</small>
                </div>
                <div className="form-group">
                  <label className="form-label">Description</label>
                  <textarea className="form-control" rows="2"
                    value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} />
                </div>
                <div style={{ background: '#fffae1', border: '1px solid #ffea82', borderRadius: 6, padding: '0.5rem 0.75rem' }}>
                  <small><i className="bi bi-info-circle me-1"></i>
                    Après création, allez dans <strong>Utilisateurs</strong> pour assigner des utilisateurs à ce secrétariat.
                  </small>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowModal(false)}>Annuler</button>
                <button type="submit" className="btn btn-dfrc" disabled={saving}>
                  {saving ? 'Enregistrement...' : (editingId ? 'Modifier' : 'Créer')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
