import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import api, { API_BASE_URL, ADMIN_URL, setSessionExpiredCallback } from '@/services/api'
import { fetchResponse, flushPromises } from '@/test/utils/async'

const REFRESH_URL = `${API_BASE_URL}/auth/token/refresh/`
const LOGOUT_URL = `${API_BASE_URL}/auth/logout/`

function installFetch(handler) {
  const mock = vi.fn(handler)
  vi.stubGlobal('fetch', mock)
  return mock
}

describe('services/api.js', () => {
  let expiredHandler

  beforeEach(() => {
    window.localStorage.clear()
    expiredHandler = vi.fn()
    setSessionExpiredCallback(expiredHandler) // réarme aussi _sessionExpiredFired
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  describe('URL de base et admin', () => {
    it('expose une URL d’API finissant par /api', () => {
      expect(API_BASE_URL).toMatch(/\/api$/)
    })
    it("dérive l'URL admin de VITE_API_URL (.../api → .../admin/)", () => {
      expect(ADMIN_URL.endsWith('/admin/')).toBe(true)
    })
  })

  describe('en-têtes d’authentification', () => {
    it('n’envoie pas d’en-tête d’auth sans jeton', async () => {
      const f = installFetch(async () => fetchResponse({ ok: true }))
      await api.get('/formations/formations/')
      expect(f).toHaveBeenCalledOnce()
      const init = f.mock.calls[0][1]
      expect(init.headers.Authorization).toBeUndefined()
    })

    it('envoie Authorization et X-JWT-Access avec le jeton local', async () => {
      window.localStorage.setItem('access_token', 'jwt-abc')
      const f = installFetch(async () => fetchResponse({ a: 1 }))
      await api.get('/formations/formations/')
      const init = f.mock.calls[0][1]
      expect(init.headers.Authorization).toBe('Bearer jwt-abc')
      expect(init.headers['X-JWT-Access']).toBe('jwt-abc')
    })
  })

  describe('construction des URL et requêtes', () => {
    it('concatène les paramètres non vides et ignore les valeurs creuses', async () => {
      const f = installFetch(async () => fetchResponse([]))
      await api.get('/x/', { params: { a: 1, vide: '', nul: null, undef: undefined, b: 'deux' } })
      const url = f.mock.calls[0][0]
      expect(url).toContain('a=1')
      expect(url).toContain('b=deux')
      expect(url).not.toContain('vide')
      expect(url).not.toContain('nul')
      expect(url).not.toContain('undef')
    })

    it('ajoute le paramètre avec & si l’URL contient déjà un ?', async () => {
      const f = installFetch(async () => fetchResponse([]))
      await api.get('/x/?fixe=1', { params: { p: 2 } })
      expect(f.mock.calls[0][0]).toMatch(/\?fixe=1&p=2/)
    })

    it('sérialise le corps JSON et pose Content-Type', async () => {
      const f = installFetch(async () => fetchResponse({ id: 1 }))
      await api.post('/x/', { nom: 'test' })
      const init = f.mock.calls[0][1]
      expect(init.headers['Content-Type']).toBe('application/json')
      expect(JSON.parse(init.body)).toEqual({ nom: 'test' })
    })

    it('ne force pas Content-Type pour FormData', async () => {
      const f = installFetch(async () => fetchResponse({}))
      const fd = new FormData()
      fd.append('f', 'v')
      await api.post('/x/', fd)
      const init = f.mock.calls[0][1]
      expect(init.headers['Content-Type']).toBeUndefined()
      expect(init.body).toBe(fd)
    })

    it('retourne data=null pour une réponse 204 vide', async () => {
      installFetch(async () => fetchResponse('', { status: 204 }))
      const res = await api.delete('/x/1/')
      expect(res.data).toBeNull()
      expect(res.status).toBe(204)
    })

    it('lève une erreur portant response.status et response.data', async () => {
      installFetch(async () => fetchResponse({ detail: 'Interdit' }, { status: 403 }))
      await expect(api.get('/x/')).rejects.toMatchObject({
        response: { status: 403, data: { detail: 'Interdit' } },
      })
    })
  })

  describe('rafraîchissement sur 401 (single-flight)', () => {
    it('rafraîchit via le cookie HttpOnly puis réessaie la requête', async () => {
      window.localStorage.setItem('access_token', 'vieux')
      const f = installFetch(async (url, init) => {
        if (url.includes('/formations/')) {
          // 401 la première fois (vieux jeton), 200 après rafraîchissement.
          return init.headers.Authorization === 'Bearer nouveau'
            ? fetchResponse({ ok: true })
            : fetchResponse({ detail: 'expiré' }, { status: 401 })
        }
        if (url === REFRESH_URL) return fetchResponse({ access: 'nouveau' })
        return fetchResponse({}, { status: 404 })
      })

      const res = await api.get('/formations/formations/')
      expect(res.data).toEqual({ ok: true })
      expect(window.localStorage.getItem('access_token')).toBe('nouveau')
      // Un seul refresh malgré l'échec initial.
      expect(f.mock.calls.filter(([u]) => u === REFRESH_URL)).toHaveLength(1)
    })

    it('partage UN seul refresh entre plusieurs requêtes parallèles (file d’attente)', async () => {
      window.localStorage.setItem('access_token', 'vieux')
      let refreshCalls = 0
      installFetch(async (url, init) => {
        if (url === REFRESH_URL) {
          refreshCalls += 1
          return fetchResponse({ access: 'partage' })
        }
        return init.headers.Authorization === 'Bearer partage'
          ? fetchResponse([])
          : fetchResponse({}, { status: 401 })
      })

      const [r1, r2, r3] = await Promise.all([
        api.get('/a/'),
        api.get('/b/'),
        api.get('/c/'),
      ])
      expect([r1.data, r2.data, r3.data]).toEqual([[], [], []])
      expect(refreshCalls).toBe(1)
    })

    it('bascule sur le refresh localStorage si le cookie échoue', async () => {
      window.localStorage.setItem('access_token', 'vieux')
      window.localStorage.setItem('refresh_token', 'refresh-local')
      let cookieAttempts = 0
      installFetch(async (url, init) => {
        if (url === REFRESH_URL) {
          const body = JSON.parse(init.body || '{}')
          if (!body.refresh) {
            cookieAttempts += 1
            return fetchResponse({}, { status: 401 }) // cookie absent cross-origin
          }
          return fetchResponse({ access: 'via-local' })
        }
        if (url.includes('/formations/'))
          return init.headers.Authorization === 'Bearer via-local'
            ? fetchResponse({ ok: 1 })
            : fetchResponse({}, { status: 401 })
        return fetchResponse({}, { status: 404 })
      })

      const res = await api.get('/formations/formations/')
      expect(cookieAttempts).toBe(1)
      expect(res.data).toEqual({ ok: 1 })
      expect(window.localStorage.getItem('access_token')).toBe('via-local')
    })

    it('échec total du refresh → session expirée, jetons purgés et erreur', async () => {
      window.localStorage.setItem('access_token', 'vieux')
      window.localStorage.setItem('refresh_token', 'refresh-local')
      const f = installFetch(async (url) => {
        if (url === LOGOUT_URL) return fetchResponse({}, { status: 204 })
        if (url === REFRESH_URL) return fetchResponse({}, { status: 401 })
        return fetchResponse({}, { status: 401 })
      })

      await expect(api.get('/formations/formations/')).rejects.toThrow('Session expired')
      await flushPromises()
      expect(window.localStorage.getItem('access_token')).toBeNull()
      expect(window.localStorage.getItem('refresh_token')).toBeNull()
      expect(expiredHandler).toHaveBeenCalledOnce()
      expect(f.mock.calls.some(([u]) => u === LOGOUT_URL)).toBe(true)
    })

    it('ne rafraîchit PAS sur la route de connexion', async () => {
      const f = installFetch(async (url) => {
        if (url === REFRESH_URL) return fetchResponse({ access: 'ne-devrait-pas' })
        return fetchResponse({ detail: 'mauvais identifiants' }, { status: 401 })
      })
      await expect(api.post('/auth/login/', { username: 'x', password: 'y' })).rejects.toThrow()
      expect(f.mock.calls.some(([u]) => u === REFRESH_URL)).toBe(false)
    })
  })

  describe('session expirée', () => {
    it('ne déclenche le callback qu’une seule fois pour des 401 parallèles', async () => {
      window.localStorage.setItem('access_token', 'vieux')
      installFetch(async (url) => {
        if (url === LOGOUT_URL) return fetchResponse({}, { status: 204 })
        return fetchResponse({}, { status: 401 })
      })
      await Promise.allSettled([api.get('/a/'), api.get('/b/')])
      await flushPromises()
      expect(expiredHandler).toHaveBeenCalledOnce()
    })
  })

  describe('getBlob (exports)', () => {
    it('retourne blob, contentType et nom de fichier', async () => {
      installFetch(async () =>
        fetchResponse(new Blob(['pdf'], { type: 'application/pdf' }), {
          status: 200,
          headers: {
            'Content-Type': 'application/pdf',
            'Content-Disposition': "attachment; filename*=UTF-8''export_%C3%A9l%C3%A8ves.pdf",
          },
        }),
      )
      const out = await api.getBlob('/exports/x/pdf/')
      expect(out.contentType).toContain('pdf')
      expect(out.fileName).toBe('export_élèves.pdf')
    })

    it("considère une réponse JSON comme une erreur d'export", async () => {
      installFetch(async () => fetchResponse({ detail: 'ko' }, { status: 200, headers: { 'Content-Type': 'application/json' } }))
      await expect(api.getBlob('/exports/x/pdf/')).rejects.toThrow('Export failed')
    })

    it('lève une erreur HTTP standard sur échec non-401', async () => {
      installFetch(async () => fetchResponse({ detail: 'nf' }, { status: 404 }))
      await expect(api.getBlob('/exports/x/pdf/')).rejects.toMatchObject({
        response: { status: 404 },
      })
    })

    it('rafraîchit puis réessaie sur 401', async () => {
      window.localStorage.setItem('access_token', 'vieux')
      installFetch(async (url, init) => {
        if (url === REFRESH_URL) return fetchResponse({ access: 'new' })
        if (url.includes('/exports/'))
          return init.headers.Authorization === 'Bearer new'
            ? fetchResponse(new Blob(['x'], { type: 'text/csv' }), { status: 200, headers: { 'Content-Type': 'text/csv' } })
            : fetchResponse({}, { status: 401 })
        return fetchResponse({})
      })
      const out = await api.getBlob('/exports/x/csv/')
      expect(out.contentType).toBe('text/csv')
    })
  })

  describe('absence de fuite de jeton', () => {
    it('n’écrit jamais le jeton dans les logs ni dans l’URL', async () => {
      window.localStorage.setItem('access_token', 'secret-jwt')
      const spies = ['log', 'warn', 'error'].map((m) => vi.spyOn(console, m).mockImplementation(() => {}))
      const f = installFetch(async () => fetchResponse({ ok: true }))
      await api.get('/formations/formations/')
      const url = f.mock.calls[0][0]
      expect(url).not.toContain('secret-jwt')
      for (const spy of spies) {
        for (const call of spy.mock.calls) {
          expect(JSON.stringify(call)).not.toContain('secret-jwt')
        }
      }
    })
  })
})
