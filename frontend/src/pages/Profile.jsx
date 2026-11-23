import { useState, useEffect } from 'react'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import { useToast } from '../context/ToastContext'
import ConfirmModal from '../components/ConfirmModal'

const ROLE_LABELS = {
  DIRECTION: 'Direction',
  CHEF_INJS_ADMIN: 'Chef INJS Admin',
  INJS_ADMIN: 'INJS Admin',
  CHEF_SECRETARIAT: 'Chef Secrétariat',
  SECRETARIAT: 'Secrétariat',
  FINANCE: 'Finance',
  ENCADRANT: 'Encadrant',
  FORMATEUR: 'Enseignant',
  AUDITEUR: 'Étudiant',
}

const emptyForm = {
  first_name: '',
  last_name: '',
  email: '',
  telephone: '',
  organisation: '',
  grade: '',
  matricule: '',
}

const emptyPwdForm = { old_password: '', new_password: '', confirm_password: '' }

function dash(v) {
  const s = (v ?? '').toString().trim()
  return s || '—'
}

export default function Profile() {
  const { refreshUser, logout } = useAuth()
  const { showToast } = useToast()
  const [meta, setMeta] = useState({ username: '', role: '', secretariat_nom: null, is_active: true })
  const [baseline, setBaseline] = useState({ ...emptyForm })
  const [form, setForm] = useState({ ...emptyForm })
  const [isEditing, setIsEditing] = useState(false)
  const [isEditingPwd, setIsEditingPwd] = useState(false)
  const [pwdForm, setPwdForm] = useState({ ...emptyPwdForm })
  const [pwdErrors, setPwdErrors] = useState({})
  const [pwdSaving, setPwdSaving] = useState(false)
  const [showPwdOld, setShowPwdOld] = useState(false)
  const [showPwdNew, setShowPwdNew] = useState(false)
  const [showPwdConfirm, setShowPwdConfirm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false)

  const applyProfileData = (d) => {
    setMeta({
      username: d.username || '',
      role: d.role || '',
      secretariat_nom: d.secretariat_nom || null,
      is_active: d.is_active !== false,
    })
    const next = {
      first_name: d.first_name || '',
      last_name: d.last_name || '',
      email: d.email || '',
      telephone: d.telephone || '',
      organisation: d.organisation || '',
      grade: d.grade || '',
      matricule: d.matricule || '',
    }
    setBaseline({ ...next })
    setForm({ ...next })
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .get('/auth/me/')
      .then((res) => {
        if (cancelled) return
        applyProfileData(res.data)
        setError('')
        setFieldErrors({})
        setIsEditing(false)
      })
      .catch(() => {
        if (!cancelled) setError('Impossible de charger votre profil.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const startEdit = () => {
    setForm({ ...baseline })
    setError('')
    setFieldErrors({})
    setIsEditing(true)
  }

  const cancelEdit = () => {
    setForm({ ...baseline })
    setError('')
    setFieldErrors({})
    setIsEditing(false)
  }

  const startPwdEdit = () => {
    setPwdForm({ ...emptyPwdForm })
    setPwdErrors({})
    setIsEditingPwd(true)
  }

  const cancelPwdEdit = () => {
    setPwdForm({ ...emptyPwdForm })
    setPwdErrors({})
    setShowPwdOld(false)
    setShowPwdNew(false)
    setShowPwdConfirm(false)
    setIsEditingPwd(false)
  }

  const validatePwdForm = () => {
    const e = {}
    if (!pwdForm.old_password) e.old_password = 'Champ requis.'
    if (!pwdForm.new_password) e.new_password = 'Champ requis.'
    else if (pwdForm.new_password.length < 8) e.new_password = 'Minimum 8 caractères.'
    if (pwdForm.new_password !== pwdForm.confirm_password) e.confirm_password = 'Les mots de passe ne correspondent pas.'
    return e
  }

  const handlePwdSubmit = async (e) => {
    e.preventDefault()
    const errs = validatePwdForm()
    if (Object.keys(errs).length) {
      setPwdErrors(errs)
      return
    }
    setPwdSaving(true)
    setPwdErrors({})
    try {
      await api.post('/auth/me/change-password/', {
        old_password: pwdForm.old_password,
        new_password: pwdForm.new_password,
      })
      setPwdForm({ ...emptyPwdForm })
      setShowPwdOld(false)
      setShowPwdNew(false)
      setShowPwdConfirm(false)
      setIsEditingPwd(false)
      showToast('Mot de passe modifié avec succès.')
    } catch (err) {
      const data = err?.response?.data
      if (data?.old_password) setPwdErrors({ old_password: Array.isArray(data.old_password) ? data.old_password[0] : data.old_password })
      else if (data?.new_password) setPwdErrors({ new_password: Array.isArray(data.new_password) ? data.new_password[0] : data.new_password })
      else if (data?.detail) setPwdErrors({ general: data.detail })
      else setPwdErrors({ general: 'Une erreur est survenue.' })
    } finally {
      setPwdSaving(false)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    setFieldErrors({})
    setSaving(true)
    try {
      const payload = {
        ...form,
        matricule: (form.matricule || '').trim() || null,
      }
      const { data: d } = await api.patch('/auth/me/', payload)
      applyProfileData(d)
      await refreshUser()
      setIsEditing(false)
      showToast('Profil mis à jour')
    } catch (err) {
      const data = err.response?.data
      if (data && typeof data === 'object' && !data.detail) {
        const fe = {}
        Object.entries(data).forEach(([k, v]) => {
          fe[k] = Array.isArray(v) ? v.join(' ') : String(v)
        })
        setFieldErrors(fe)
      } else {
        setError(data?.detail || 'Erreur lors de la sauvegarde.')
      }
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner"></div>
      </div>
    )
  }

  return (
    <div>
      <div className="card mb-3">
        <div className="card-body d-flex flex-wrap justify-content-between align-items-start gap-3">
          <div style={{ flex: '1 1 220px' }}>
            <h6 className="mb-1" style={{ fontWeight: 700 }}>
              <i className="bi bi-person-circle me-2"></i>Mon profil
            </h6>
            <small className="text-muted">
              {isEditing
                ? 'Modifiez les champs puis enregistrez, ou annulez pour revenir à l’affichage seul.'
                : 'Consultez vos informations. « Modifier » sous chaque bloc active l’édition (coordonnées ou mot de passe). Le rôle, le secrétariat et l’identifiant de connexion sont gérés par un administrateur.'}
            </small>
          </div>
          <button
            type="button"
            className="btn btn-outline-danger"
            title="Une confirmation vous sera demandée avant la déconnexion."
            onClick={() => setShowLogoutConfirm(true)}
          >
            <i className="bi bi-box-arrow-left me-1"></i>Déconnexion
          </button>
        </div>
      </div>

      {showLogoutConfirm && (
        <ConfirmModal
          message="Quitter la session ?"
          detail="Vous serez déconnecté et renvoyé vers l’écran de connexion. Les brouillons non enregistrés seront perdus."
          confirmLabel="Me déconnecter"
          cancelLabel="Annuler"
          variant="danger"
          onConfirm={() => {
            setShowLogoutConfirm(false)
            logout()
          }}
          onCancel={() => setShowLogoutConfirm(false)}
        />
      )}

      <div className="card">
        <div className="card-header-bar" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
          <span><i className="bi bi-person-lines-fill me-2"></i>Informations personnelles</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap', marginLeft: 'auto' }}>
            <span className={`badge ${meta.is_active ? 'badge-success' : 'badge-danger'}`}>
              {meta.is_active ? 'Compte actif' : 'Compte inactif'}
            </span>
            {!isEditing && (
              <button type="button" className="btn btn-dfrc btn-sm" onClick={startEdit}>
                <i className="bi bi-pencil me-1"></i>Modifier
              </button>
            )}
          </div>
        </div>
        <div className="card-body">
          {error && <div className="error-message mb-3">{error}</div>}

          <div className="row mb-4 pb-3" style={{ borderBottom: '1px solid var(--border-color, #e9ecef)' }}>
            <div className="col-md-6 mb-2">
              <small className="text-muted d-block">Identifiant de connexion</small>
              <code>{meta.username}</code>
            </div>
            <div className="col-md-6 mb-2">
              <small className="text-muted d-block">Rôle</small>
              <span className="badge badge-info">{ROLE_LABELS[meta.role] || meta.role}</span>
            </div>
            {meta.secretariat_nom && (
              <div className="col-12 mb-2">
                <small className="text-muted d-block">Secrétariat</small>
                <span><i className="bi bi-building me-1"></i>{meta.secretariat_nom}</span>
              </div>
            )}
          </div>

          {!isEditing ? (
            <div className="grid-2" style={{ rowGap: '1rem' }}>
              <div>
                <small className="text-muted d-block mb-1">Prénom</small>
                <div>{dash(baseline.first_name)}</div>
              </div>
              <div>
                <small className="text-muted d-block mb-1">Nom</small>
                <div>{dash(baseline.last_name)}</div>
              </div>
              <div style={{ gridColumn: '1 / -1' }}>
                <small className="text-muted d-block mb-1">Adresse e-mail</small>
                <div>{dash(baseline.email)}</div>
              </div>
              <div>
                <small className="text-muted d-block mb-1">Téléphone</small>
                <div>{dash(baseline.telephone)}</div>
              </div>
              <div>
                <small className="text-muted d-block mb-1">N° matricule (badge)</small>
                <div>{dash(baseline.matricule)}</div>
              </div>
              <div>
                <small className="text-muted d-block mb-1">Organisation</small>
                <div>{dash(baseline.organisation)}</div>
              </div>
              <div>
                <small className="text-muted d-block mb-1">Grade</small>
                <div>{dash(baseline.grade)}</div>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit}>
              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Prénom</label>
                  <input
                    type="text"
                    className={`form-control${fieldErrors.first_name ? ' is-invalid' : ''}`}
                    value={form.first_name}
                    onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  />
                  {fieldErrors.first_name && <div className="invalid-feedback d-block">{fieldErrors.first_name}</div>}
                </div>
                <div className="form-group">
                  <label className="form-label">Nom</label>
                  <input
                    type="text"
                    className={`form-control${fieldErrors.last_name ? ' is-invalid' : ''}`}
                    value={form.last_name}
                    onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                  />
                  {fieldErrors.last_name && <div className="invalid-feedback d-block">{fieldErrors.last_name}</div>}
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">Adresse e-mail</label>
                <input
                  type="email"
                  className={`form-control${fieldErrors.email ? ' is-invalid' : ''}`}
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
                {fieldErrors.email && <div className="invalid-feedback d-block">{fieldErrors.email}</div>}
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Téléphone</label>
                  <input
                    type="text"
                    className={`form-control${fieldErrors.telephone ? ' is-invalid' : ''}`}
                    value={form.telephone}
                    onChange={(e) => setForm({ ...form, telephone: e.target.value })}
                  />
                  {fieldErrors.telephone && <div className="invalid-feedback d-block">{fieldErrors.telephone}</div>}
                </div>
                <div className="form-group">
                  <label className="form-label">N° matricule (badge)</label>
                  <input
                    type="text"
                    className={`form-control${fieldErrors.matricule ? ' is-invalid' : ''}`}
                    value={form.matricule}
                    onChange={(e) => setForm({ ...form, matricule: e.target.value })}
                  />
                  {fieldErrors.matricule && <div className="invalid-feedback d-block">{fieldErrors.matricule}</div>}
                </div>
              </div>
              <div className="grid-2">
                <div className="form-group">
                  <label className="form-label">Organisation</label>
                  <input
                    type="text"
                    className={`form-control${fieldErrors.organisation ? ' is-invalid' : ''}`}
                    value={form.organisation}
                    onChange={(e) => setForm({ ...form, organisation: e.target.value })}
                  />
                  {fieldErrors.organisation && <div className="invalid-feedback d-block">{fieldErrors.organisation}</div>}
                </div>
                <div className="form-group">
                  <label className="form-label">Grade</label>
                  <input
                    type="text"
                    className={`form-control${fieldErrors.grade ? ' is-invalid' : ''}`}
                    value={form.grade}
                    onChange={(e) => setForm({ ...form, grade: e.target.value })}
                    placeholder="Ex. A4, B2…"
                  />
                  {fieldErrors.grade && <div className="invalid-feedback d-block">{fieldErrors.grade}</div>}
                </div>
              </div>
              <div className="mt-3 d-flex flex-wrap gap-2">
                <button type="submit" className="btn btn-dfrc" disabled={saving}>
                  {saving ? 'Enregistrement…' : 'Enregistrer'}
                </button>
                <button type="button" className="btn btn-secondary" disabled={saving} onClick={cancelEdit}>
                  Annuler
                </button>
              </div>
            </form>
          )}
        </div>
      </div>

      <div className="card mt-3">
        <div className="card-header-bar" style={{ flexWrap: 'wrap', gap: '0.5rem' }}>
          <span><i className="bi bi-shield-lock me-2"></i>Mot de passe</span>
          {!isEditingPwd && (
            <button type="button" className="btn btn-dfrc btn-sm" style={{ marginLeft: 'auto' }} onClick={startPwdEdit}>
              <i className="bi bi-pencil me-1"></i>Modifier
            </button>
          )}
        </div>
        <div className="card-body">
          {!isEditingPwd ? (
            <p className="text-muted small mb-0">
              Pour des raisons de sécurité, le mot de passe n’est jamais affiché. Utilisez « Modifier » pour saisir l’ancien mot de passe et en choisir un nouveau.
            </p>
          ) : (
            <form onSubmit={handlePwdSubmit}>
              {pwdErrors.general && <div className="alert alert-danger py-2 mb-3">{pwdErrors.general}</div>}
              <div className="form-group">
                <label className="form-label">Mot de passe actuel</label>
                <div className="input-group">
                  <input
                    type={showPwdOld ? 'text' : 'password'}
                    className={`form-control${pwdErrors.old_password ? ' is-invalid' : ''}`}
                    value={pwdForm.old_password}
                    onChange={(ev) => setPwdForm((f) => ({ ...f, old_password: ev.target.value }))}
                    autoComplete="current-password"
                  />
                  <button type="button" className="btn btn-outline-secondary" onClick={() => setShowPwdOld((s) => !s)} tabIndex={-1} aria-label="Afficher ou masquer">
                    <i className={`bi bi-eye${showPwdOld ? '-slash' : ''}`}></i>
                  </button>
                </div>
                {pwdErrors.old_password && <div className="invalid-feedback d-block">{pwdErrors.old_password}</div>}
              </div>
              <div className="form-group">
                <label className="form-label">Nouveau mot de passe</label>
                <div className="input-group">
                  <input
                    type={showPwdNew ? 'text' : 'password'}
                    className={`form-control${pwdErrors.new_password ? ' is-invalid' : ''}`}
                    value={pwdForm.new_password}
                    onChange={(ev) => setPwdForm((f) => ({ ...f, new_password: ev.target.value }))}
                    autoComplete="new-password"
                  />
                  <button type="button" className="btn btn-outline-secondary" onClick={() => setShowPwdNew((s) => !s)} tabIndex={-1} aria-label="Afficher ou masquer">
                    <i className={`bi bi-eye${showPwdNew ? '-slash' : ''}`}></i>
                  </button>
                </div>
                {pwdErrors.new_password && <div className="invalid-feedback d-block">{pwdErrors.new_password}</div>}
              </div>
              <div className="form-group">
                <label className="form-label">Confirmer le nouveau mot de passe</label>
                <div className="input-group">
                  <input
                    type={showPwdConfirm ? 'text' : 'password'}
                    className={`form-control${pwdErrors.confirm_password ? ' is-invalid' : ''}`}
                    value={pwdForm.confirm_password}
                    onChange={(ev) => setPwdForm((f) => ({ ...f, confirm_password: ev.target.value }))}
                    autoComplete="new-password"
                  />
                  <button type="button" className="btn btn-outline-secondary" onClick={() => setShowPwdConfirm((s) => !s)} tabIndex={-1} aria-label="Afficher ou masquer">
                    <i className={`bi bi-eye${showPwdConfirm ? '-slash' : ''}`}></i>
                  </button>
                </div>
                {pwdErrors.confirm_password && <div className="invalid-feedback d-block">{pwdErrors.confirm_password}</div>}
              </div>
              <div className="mt-3 d-flex flex-wrap gap-2">
                <button type="submit" className="btn btn-dfrc" disabled={pwdSaving}>
                  {pwdSaving ? 'Enregistrement…' : 'Enregistrer le mot de passe'}
                </button>
                <button type="button" className="btn btn-secondary" disabled={pwdSaving} onClick={cancelPwdEdit}>
                  Annuler
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  )
}
