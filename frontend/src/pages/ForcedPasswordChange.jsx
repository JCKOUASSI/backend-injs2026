import { useState } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import api from '../services/api'
import { useAuth } from '../context/AuthContext'
import logo from '../assets/logo-injs.svg'

const emptyForm = { old_password: '', new_password: '', confirm_password: '' }

/**
 * Écran de changement de mot de passe OBLIGATOIRE (§10.1, LOT 46).
 *
 * Un compte marqué `must_change_password` (première connexion d'un compte
 * badge créé par l'administration) est renvoyé ici par `ProtectedRoute`, qui
 * verrouille toutes les autres pages. Le changement appelle
 * `POST /auth/me/change-password/` puis `refreshUser()` : le backend bascule
 * le drapeau à faux, et l'utilisateur est alors reconduit vers sa destination
 * initiale. La déconnexion reste possible.
 */
export default function ForcedPasswordChange() {
  const { user, refreshUser, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [form, setForm] = useState(emptyForm)
  const [errors, setErrors] = useState({})
  const [saving, setSaving] = useState(false)
  const [showOld, setShowOld] = useState(false)
  const [showNew, setShowNew] = useState(false)
  const [showConfirm, setShowConfirm] = useState(false)

  const destination = location.state?.from?.pathname || '/'

  // Un utilisateur sans contrainte qui atterrirait ici (mot de passe déjà
  // changé, saisie directe de l'URL) est reconduit vers l'application.
  if (user && !user.must_change_password) {
    return <Navigate to={destination === '/changement-mot-de-passe-obligatoire' ? '/' : destination} replace />
  }

  const setField = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }))

  const validate = () => {
    const e = {}
    if (!form.old_password) e.old_password = 'Champ requis.'
    if (!form.new_password) e.new_password = 'Champ requis.'
    else if (form.new_password.length < 8) e.new_password = 'Minimum 8 caractères.'
    if (form.new_password !== form.confirm_password) e.confirm_password = 'Les mots de passe ne correspondent pas.'
    return e
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    const validationErrors = validate()
    if (Object.keys(validationErrors).length) {
      setErrors(validationErrors)
      return
    }
    setSaving(true)
    setErrors({})
    try {
      await api.post('/auth/me/change-password/', {
        old_password: form.old_password,
        new_password: form.new_password,
      })
      // Le backend vient de passer must_change_password à faux : on recharge
      // l'utilisateur avant de lever le verrou, puis on reconduit à la cible.
      await refreshUser()
      navigate(destination, { replace: true })
    } catch (err) {
      const data = err?.response?.data
      if (data?.old_password) {
        setErrors({ old_password: Array.isArray(data.old_password) ? data.old_password[0] : data.old_password })
      } else if (data?.new_password) {
        setErrors({ new_password: Array.isArray(data.new_password) ? data.new_password[0] : data.new_password })
      } else if (data?.detail) {
        setErrors({ general: data.detail })
      } else {
        setErrors({ general: 'Une erreur est survenue.' })
      }
    } finally {
      setSaving(false)
    }
  }

  const handleLogout = () => {
    logout()
    navigate('/login', { replace: true })
  }

  const passwordInput = (id, label, value, shown, toggle, autoComplete, onChange, error) => (
    <div className="login-field">
      <label htmlFor={id}>{label}</label>
      <div className="login-input">
        <i className="bi bi-lock"></i>
        <input
          id={id}
          type={shown ? 'text' : 'password'}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
        />
        <button
          type="button"
          className="login-password-toggle"
          onClick={toggle}
          title={shown ? 'Masquer le mot de passe' : 'Voir le mot de passe'}
          aria-label={shown ? 'Masquer le mot de passe' : 'Voir le mot de passe'}
        >
          <i className={`bi ${shown ? 'bi-eye-slash' : 'bi-eye'}`}></i>
        </button>
      </div>
      {error && <div className="invalid-feedback d-block">{error}</div>}
    </div>
  )

  return (
    <div className="login-container">
      <div className="login-orb login-orb-a" aria-hidden="true" />
      <div className="login-orb login-orb-b" aria-hidden="true" />
      <div className="login-orb login-orb-c" aria-hidden="true" />

      <div
        style={{
          position: 'relative',
          zIndex: 1,
          width: '100%',
          maxWidth: 460,
          background: 'rgba(255,255,255,0.92)',
          borderRadius: 22,
          padding: '2.25rem 1.85rem 1.5rem',
          boxShadow: '0 30px 80px rgba(2,12,32,0.55)',
          backdropFilter: 'blur(20px) saturate(160%)',
          WebkitBackdropFilter: 'blur(20px) saturate(160%)',
        }}
      >
        <div style={{ textAlign: 'center', marginBottom: '1.25rem' }}>
          <img src={logo} alt="INJS Abidjan" style={{ height: 56, marginBottom: '0.6rem' }} />
          <h2 style={{ fontSize: '1.45rem', fontWeight: 800, color: '#0d2137', margin: 0 }}>
            Changement de mot de passe obligatoire
          </h2>
          <p className="login-form-lead" style={{ marginTop: '0.5rem', marginBottom: 0 }}>
            Pour votre sécurité, vous devez définir un nouveau mot de passe avant d'accéder à l'application.
          </p>
        </div>

        {errors.general && (
          <div className="login-error" role="alert">
            <i className="bi bi-exclamation-triangle-fill"></i>
            {errors.general}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          {passwordInput(
            'forced-old-password', 'Mot de passe actuel', form.old_password, showOld,
            () => setShowOld((v) => !v), 'current-password', setField('old_password'), errors.old_password,
          )}
          {passwordInput(
            'forced-new-password', 'Nouveau mot de passe', form.new_password, showNew,
            () => setShowNew((v) => !v), 'new-password', setField('new_password'), errors.new_password,
          )}
          {passwordInput(
            'forced-confirm-password', 'Confirmer le nouveau mot de passe', form.confirm_password, showConfirm,
            () => setShowConfirm((v) => !v), 'new-password', setField('confirm_password'), errors.confirm_password,
          )}

          <button type="submit" className="btn-login" disabled={saving}>
            <i className="bi bi-shield-lock"></i>
            {saving ? 'Enregistrement…' : 'Définir mon mot de passe'}
          </button>
        </form>

        <div className="text-center" style={{ marginTop: '1rem' }}>
          <button type="button" className="btn btn-link btn-sm" onClick={handleLogout}>
            Se déconnecter
          </button>
        </div>
      </div>
    </div>
  )
}
