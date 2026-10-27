import { safeLocalStorage } from '../utils/safeStorage'
const API_BASE_URL = import.meta.env.VITE_API_URL || '/api'

/** URL admin Django : VITE_ADMIN_URL ou dérivée de VITE_API_URL (…/api → …/admin/). */
const ADMIN_URL = (() => {
  const explicit = (import.meta.env.VITE_ADMIN_URL || '').trim()
  if (explicit) return explicit.replace(/\/?$/, '/')
  const base = (import.meta.env.VITE_API_URL || '/api').replace(/\/api\/?$/, '')
  return `${base || ''}/admin/`
})()

let _sessionExpiredCallback = null
let _sessionExpiredFired = false
export function setSessionExpiredCallback(cb) {
  _sessionExpiredCallback = cb
  _sessionExpiredFired = false
}

function _onSessionExpired() {
  // Évite d'émettre dix déconnexions/logouts quand plusieurs requêtes
  // échouent en parallèle avec une session réellement expirée.
  if (_sessionExpiredFired) return
  _sessionExpiredFired = true
  safeLocalStorage.removeItem('access_token')
  safeLocalStorage.removeItem('refresh_token')
  // Best-effort : invalide le cookie HttpOnly du refresh côté serveur.
  fetch(`${API_BASE_URL}/auth/logout/`, { method: 'POST', credentials: 'include' }).catch(() => {})
  if (_sessionExpiredCallback) {
    _sessionExpiredCallback()
  } else {
    window.location.href = '/login'
  }
}

const getAuthHeaders = () => {
  const token = safeLocalStorage.getItem('access_token')
  if (!token) return {}
  return {
    Authorization: `Bearer ${token}`,
    // En-tête de secours : certaines passerelles d'aperçu (iframe) filtrent
    // « Authorization » ; l'en-tête personnalisé X-JWT-Access est transmis et
    // accepté par FlexibleJWTAuthentication côté Django.
    'X-JWT-Access': token,
  }
}

const _doRefreshAccessToken = async () => {
  // 1) Voie privilégiée (risque R6) : refresh dans le cookie HttpOnly.
  //    Le cookie circule en same-site ; en dev cross-origin, le navigateur
  //    ne l'enverra pas → on bascule sur le fallback historique.
  try {
    const cookieRes = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({}),
    })
    if (cookieRes.ok) {
      const data = await cookieRes.json()
      safeLocalStorage.setItem('access_token', data.access)
      return data.access
    }
  } catch {
    // cookie indisponible → fallback ci-dessous
  }
  // 2) Fallback de transition : refresh en localStorage (ancien comportement).
  const refreshToken = safeLocalStorage.getItem('refresh_token')
  if (!refreshToken) throw new Error('No refresh token')
  const res = await fetch(`${API_BASE_URL}/auth/token/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'include',
    body: JSON.stringify({ refresh: refreshToken }),
  })
  if (!res.ok) throw new Error('Refresh failed')
  const data = await res.json()
  safeLocalStorage.setItem('access_token', data.access)
  return data.access
}

// Single-flight : quand plusieurs requêtes reçoivent 401 en même temps
// (chargement du dashboard), on ne lance qu'UN seul refresh partagé par tous
// les appels, afin d'éviter une tempête de refresh et une déconnexion en cascade.
let _refreshPromise = null
const refreshAccessToken = () => {
  if (!_refreshPromise) {
    _refreshPromise = _doRefreshAccessToken()
      .finally(() => { _refreshPromise = null })
  }
  return _refreshPromise
}

const handleResponse = async (res) => {
  if (!res.ok) {
    let data
    try { data = await res.clone().json() } catch { data = null }
    const err = new Error(res.statusText)
    err.response = { status: res.status, data }
    throw err
  }
  const text = await res.text()
  return { data: text ? JSON.parse(text) : null, status: res.status }
}

/** Concatène config.params à l'URL ; les valeurs vides sont omises. */
const buildUrl = (path, params) => {
  const url = `${API_BASE_URL}${path}`
  if (!params) return url
  const qs = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') continue
    qs.set(key, String(value))
  }
  const suffix = qs.toString()
  if (!suffix) return url
  return `${url}${url.includes('?') ? '&' : '?'}${suffix}`
}

const request = async (method, path, body, config = {}) => {
  const url = buildUrl(path, config.params)
  const isFormData = body instanceof FormData
  const headers = {
    ...(!isFormData && body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...getAuthHeaders(),
    ...(config.headers || {}),
  }
  const init = {
    method,
    headers,
    ...(config.signal ? { signal: config.signal } : {}),
    ...(body !== undefined ? { body: isFormData ? body : JSON.stringify(body) } : {}),
  }

  let res = await fetch(url, init)

  const isLoginRequest = path === '/auth/login/' || path.startsWith('/auth/login?')
  if (isLoginRequest && res.ok) {
    // Nouvelle session : réarmer le garde-fou d'expiration.
    _sessionExpiredFired = false
  }
  if (res.status === 401 && !isLoginRequest) {
    try {
      const newToken = await refreshAccessToken()
      init.headers.Authorization = `Bearer ${newToken}`
      res = await fetch(url, init)
    } catch {
      _onSessionExpired()
      throw new Error('Session expired')
    }
  }

  return handleResponse(res)
}

const getBlob = async (path) => {
  const url = `${API_BASE_URL}${path}`
  const headers = getAuthHeaders()
  let res = await fetch(url, { method: 'GET', headers })
  if (res.status === 401) {
    try {
      const newToken = await refreshAccessToken()
      res = await fetch(url, { method: 'GET', headers: { ...headers, Authorization: `Bearer ${newToken}` } })
    } catch {
      _onSessionExpired()
      throw new Error('Session expired')
    }
  }
  if (!res.ok) {
    let data = null
    try { data = await res.clone().json() } catch { data = null }
    const err = new Error(res.statusText)
    err.response = { status: res.status, data }
    throw err
  }
  const blob = await res.blob()
  const ctype = res.headers.get('Content-Type') || ''
  if (ctype.includes('application/json')) {
    let data = null
    try { data = JSON.parse(await blob.text()) } catch { data = null }
    const err = new Error('Export failed')
    err.response = { status: res.status, data }
    throw err
  }
  const disp = res.headers.get('Content-Disposition') || ''
  const m = disp.match(/filename\*?=(?:UTF-8''|"?)([^";]+)/i)
  const fileName = m ? decodeURIComponent(m[1].replace(/"/g, '')) : null
  return { blob, fileName, contentType: ctype }
}

const api = {
  get:     (path, config = {})         => request('GET',    path, undefined, config),
  post:    (path, body, config = {})   => request('POST',   path, body,       config),
  patch:   (path, body, config = {})   => request('PATCH',  path, body,       config),
  put:     (path, body, config = {})   => request('PUT',    path, body,       config),
  delete:  (path, config = {})         => request('DELETE', path, undefined,  config),
  getBlob: (path)                      => getBlob(path),
}

export { API_BASE_URL, ADMIN_URL }
export default api
