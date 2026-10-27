/**
 * MFA (TOTP) — gestion du compte cible (CURP U6, LOT 3).
 *
 * Les routes /auth/mfa/* sont gardées côté Django : par défaut elles agissent
 * sur soi-même ; pour un tiers, le demandeur doit détenir
 * ``authentication.mutate_users`` et passer la PK de l'utilisateur Django
 * (``compte_id``). L'interface n'accorde aucun droit : le backend est la
 * seule autorité.
 */
import api from './api'

export const messageErreurMfa = (erreur, repli = 'Une erreur MFA est survenue.') => {
  const data = erreur?.response?.data
  if (data?.detail) return data.detail
  if (data && typeof data === 'object') {
    const champs = Object.entries(data)
      .map(([champ, valeur]) => {
        const texte = Array.isArray(valeur) ? valeur.join(' ') : String(valeur)
        return `${champ} : ${texte}`
      })
      .join(' — ')
    if (champs) return champs
  }
  return repli
}

/** Arme un secret TOTP — renvoie { secret, otpauth_url }. */
export const mfaSetup = (compteId) =>
  api.post('/auth/mfa/setup/', compteId ? { compte_id: compteId } : {})
    .then((r) => r.data)

/** Confirme l'activation avec un code valide sur le secret armé. */
export const mfaConfirm = (compteId, code) =>
  api.post('/auth/mfa/confirm/', { ...(compteId ? { compte_id: compteId } : {}), code })
    .then((r) => r.data)

/** Désactive le MFA (code exigé pour soi ; 409 sous obligation sensible). */
export const mfaDisable = (compteId, code) =>
  api.post('/auth/mfa/disable/', { ...(compteId ? { compte_id: compteId } : {}), code: code || '' })
    .then((r) => r.data)
