import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import api, { setSessionExpiredCallback } from '../services/api'
import { hasAppRole, webLoginForbiddenMessage, ALLOWED_WEB_ROLES } from '../utils/roles'
import {
  CAPABILITIES_QUERY_KEY,
  FLAGS_QUERY_KEY,
  // Navigation RBAC : l'état gouverné du compte (permissions effectives CURP)
  // ne doit pas traverser les sessions, au même titre que les capacités.
  MES_ACCES_QUERY_KEY,
} from '../lib/queryClient'
import { safeLocalStorage } from '../utils/safeStorage'

const AuthContext = createContext(null)

function canAccessWeb(userData) {
  return hasAppRole(userData, ALLOWED_WEB_ROLES)
}

function normalizeUser(userData) {
  return {
    ...userData,
    role_context: userData.role_context || {},
    get_full_name: () =>
      `${userData.first_name || ''} ${userData.last_name || ''}`.trim() || userData.username,
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  // Capacités renvoyées par GET /auth/capabilities/ (P00-06), attachées à
  // l'utilisateur exposé par le contexte. Tant qu'elles ne sont pas chargées,
  // les helpers de rôles appliquent le repli statique historique.
  const [capabilities, setCapabilities] = useState(null)
  const [loading, setLoading] = useState(true)
  // Client React Query fourni par le provider (singleton applicatif en
  // production, instance dédiée en tests) : les invalidations de capacités
  // (P00-06) touchent le même cache que les hooks useCapabilities.
  const queryClient = useQueryClient()

  const _clearSession = useCallback(() => {
    safeLocalStorage.removeItem('access_token')
    safeLocalStorage.removeItem('refresh_token')
    setUser(null)
    // Purge des droits dérivés du backend (P00-06) : une autre session ne doit
    // jamais hériter des capacités du compte précédent. removeQueries détruit
    // les requêtes ; un observateur encore monté peut recréer une entrée vide,
    // on écrase donc aussi explicitement les données (défense en profondeur).
    queryClient.removeQueries({ queryKey: CAPABILITIES_QUERY_KEY })
    queryClient.setQueryData(CAPABILITIES_QUERY_KEY, undefined)
    // P00-08 : purge des feature flags de la session (même exigence de
    // non-traversée des sessions que pour les capacités).
    queryClient.removeQueries({ queryKey: FLAGS_QUERY_KEY })
    queryClient.setQueryData(FLAGS_QUERY_KEY, undefined)
    queryClient.removeQueries({ queryKey: MES_ACCES_QUERY_KEY })
    queryClient.setQueryData(MES_ACCES_QUERY_KEY, undefined)
    setCapabilities(null)
  }, [queryClient])

  // Callback stable exposée au composant CapabilitiesSync (P00-06).
  const syncCapabilities = useCallback((c) => setCapabilities(c), [])

  useEffect(() => {
    setSessionExpiredCallback(_clearSession)
  }, [_clearSession])

  useEffect(() => {
    const token = safeLocalStorage.getItem('access_token')
    if (token) {
      api.get('/auth/me/')
        .then(res => {
          if (!canAccessWeb(res.data)) {
            _clearSession()
            return
          }
          setUser(normalizeUser(res.data))
        })
        .catch(() => _clearSession())
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
  }, [_clearSession])

  // Stockage de session commun à la connexion directe et à la finalisation
  // de l'étape MFA (le backend renvoie la même forme de réponse).
  const _finaliserConnexion = (data) => {
    const { access, refresh, refresh_in_cookie: refreshInCookie, user: userData } = data

    if (!canAccessWeb(userData)) {
      const err = new Error('Web access forbidden')
      err.response = { data: { detail: webLoginForbiddenMessage(userData?.role) } }
      throw err
    }

    safeLocalStorage.setItem('access_token', access)
    // En aperçu intégré (iframe cross-site), les cookies tiers peuvent être
    // bloqués : on conserve alors aussi le refresh en stockage local pour que
    // le rafraîchissement fonctionne par le corps de la requête. Activé par
    // VITE_REFRESH_FALLBACK=1 à la construction ; en production le cookie
    // HttpOnly reste la voie unique (risque R6).
    const refreshFallback = import.meta.env.VITE_REFRESH_FALLBACK === '1'
    if (refresh && (refreshFallback || !refreshInCookie)) {
      safeLocalStorage.setItem('refresh_token', refresh)
    } else if (refreshInCookie && !refreshFallback) {
      // Risque R6 : le refresh vit dans un cookie HttpOnly — on ne le stocke
      // plus en localStorage et on purge un éventuel résidu d'ancienne session.
      safeLocalStorage.removeItem('refresh_token')
    }
    setUser(normalizeUser({
      ...userData,
      role_context: data.role_context || userData.role_context || {},
    }))
    // Les capacités et flags de la nouvelle session doivent être (re)chargés.
    queryClient.invalidateQueries({ queryKey: CAPABILITIES_QUERY_KEY })
    queryClient.invalidateQueries({ queryKey: FLAGS_QUERY_KEY })
    queryClient.invalidateQueries({ queryKey: MES_ACCES_QUERY_KEY })

    return data
  }

  const login = async (username, password) => {
    const response = await api.post('/auth/login/', { username, password })
    return _finaliserConnexion(response.data)
  }

  // Étape MFA (CURP U6) : complète la connexion demandée par
  // /auth/login/ (code 403 « MFA_REQUIRED » + jeton court) avec le code TOTP.
  const verifierMfa = async (mfaToken, code) => {
    const response = await api.post('/auth/mfa/verify/', {
      mfa_token: mfaToken, code,
    })
    return _finaliserConnexion(response.data)
  }

  const logout = () => {
    // Invalide le cookie HttpOnly du refresh côté serveur (best-effort).
    api.post('/auth/logout/').catch(() => {})
    _clearSession()
  }

  const refreshUser = useCallback(async () => {
    const res = await api.get('/auth/me/')
    if (!canAccessWeb(res.data)) {
      _clearSession()
      return
    }
    setUser(normalizeUser(res.data))
    // Un changement de rôle éventuel change capacités et flags : on rafraîchit.
    queryClient.invalidateQueries({ queryKey: CAPABILITIES_QUERY_KEY })
    queryClient.invalidateQueries({ queryKey: FLAGS_QUERY_KEY })
    queryClient.invalidateQueries({ queryKey: MES_ACCES_QUERY_KEY })
  }, [_clearSession, queryClient])

  const isAuthenticated = !!user

  // L'utilisateur exposé embarque les capacités backend dès qu'elles sont
  // connues : tous les helpers de src/utils/roles.js en dérivent sans avoir à
  // modifier chaque page.
  const exposedUser = user && capabilities ? { ...user, capabilities } : user

  return (
    <AuthContext.Provider value={{
      user: exposedUser,
      loading,
      isAuthenticated,
      login,
      verifierMfa,
      logout,
      refreshUser,
      syncCapabilities,
    }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
