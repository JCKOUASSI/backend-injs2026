import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClientProvider } from '@tanstack/react-query'
import { makeUser, makeLoginResponse } from '@/test/utils/factories'
import { createTestQueryClient } from '@/test/utils/renderWithProviders'

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  setSessionExpiredCallback: vi.fn(),
}))
vi.mock('@/services/api', () => ({
  default: api,
  setSessionExpiredCallback: api.setSessionExpiredCallback,
}))

import { AuthProvider, useAuth } from '@/context/AuthContext'

function Probe() {
  const { user, isAuthenticated, loading, login, logout, refreshUser } = useAuth()
  return (
    <div>
      <div data-testid="state">
        {loading ? 'loading' : isAuthenticated ? `auth:${user.username}:${user.role}` : 'anonymous'}
      </div>
      <button
        onClick={() =>
          login('u', 'p').then(
            () => (window.__loginResult = 'ok'),
            (e) => (window.__loginResult = e?.response?.data?.detail || 'error'),
          )
        }
      >
        do-login
      </button>
      <button onClick={logout}>do-logout</button>
      <button onClick={() => refreshUser()}>refresh-user</button>
    </div>
  )
}

const renderProbe = (ui) =>
  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <AuthProvider>{ui}</AuthProvider>
    </QueryClientProvider>,
  )

describe('context/AuthContext', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    window.__loginResult = undefined
  })

  it('enregistre le callback d’expiration de session', () => {
    renderProbe(<Probe />)
    expect(api.setSessionExpiredCallback).toHaveBeenCalled()
  })

  it('sans jeton : visiteur anonyme, pas d’appel /auth/me', async () => {
    renderProbe(<Probe />)
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('anonymous'))
    expect(api.get).not.toHaveBeenCalled()
  })

  it('avec jeton et profil autorisé : restaure la session', async () => {
    window.localStorage.setItem('access_token', 't')
    api.get.mockResolvedValueOnce({ data: makeUser('SECRETARIAT', { username: 'secr' }) })
    renderProbe(<Probe />)
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth:secr:SECRETARIAT'))
  })

  it('avec jeton mais rôle web interdit : purge la session', async () => {
    window.localStorage.setItem('access_token', 't')
    api.get.mockResolvedValueOnce({ data: makeUser('AUDITEUR') })
    renderProbe(<Probe />)
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('anonymous'))
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('avec jeton mais /auth/me en échec : purge la session', async () => {
    window.localStorage.setItem('access_token', 't')
    api.get.mockRejectedValueOnce(new Error('boom'))
    renderProbe(<Probe />)
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('anonymous'))
  })

  it('connexion réussie (refresh en cookie HttpOnly) : stocke l’accès, pas le refresh', async () => {
    const user = makeUser('ADMIN', { username: 'admin' })
    api.post.mockResolvedValueOnce({ data: makeLoginResponse(user, { refreshInCookie: true }) })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('do-login'))
    await waitFor(() => expect(window.__loginResult).toBe('ok'))
    expect(window.localStorage.getItem('access_token')).toBe('access.jwt')
    expect(window.localStorage.getItem('refresh_token')).toBeNull()
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('auth:admin:ADMIN'))
  })

  it('connexion avec refresh explicite (pas de cookie) : conserve le refresh en localStorage', async () => {
    const user = makeUser('SECRETARIAT')
    api.post.mockResolvedValueOnce({ data: makeLoginResponse(user, { refreshInCookie: false }) })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('do-login'))
    await waitFor(() => expect(window.__loginResult).toBe('ok'))
    expect(window.localStorage.getItem('refresh_token')).toBe('refresh.jwt')
  })

  it('réponse sans jeton de rafraîchissement : ne stocke rien de tel', async () => {
    const user = makeUser('ADMIN')
    api.post.mockResolvedValueOnce({
      data: { access: 'access-only', refresh_in_cookie: false, user: { ...user, role: user.role } },
    })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('do-login'))
    await waitFor(() => expect(window.__loginResult).toBe('ok'))
    expect(window.localStorage.getItem('access_token')).toBe('access-only')
    expect(window.localStorage.getItem('refresh_token')).toBeNull()
  })

  it('refuse un compte FORMATEUR sur le web avec le message métier', async () => {
    const user = makeUser('FORMATEUR')
    api.post.mockResolvedValueOnce({ data: makeLoginResponse(user, { refreshInCookie: false }) })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('do-login'))
    await waitFor(() => expect(window.__loginResult).toMatch(/enseignant/i))
    expect(window.localStorage.getItem('access_token')).toBeNull()
    expect(screen.getByTestId('state')).toHaveTextContent('anonymous')
  })

  it('refuse un compte AUDITEUR (étudiant) sur le web', async () => {
    const user = makeUser('AUDITEUR')
    api.post.mockResolvedValueOnce({ data: makeLoginResponse(user, { refreshInCookie: false }) })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('do-login'))
    await waitFor(() => expect(window.__loginResult).toMatch(/étudiant/i))
  })

  it('logout : appelle le serveur et purge la session', async () => {
    api.post.mockResolvedValue({ data: {} })
    window.localStorage.setItem('access_token', 't')
    window.localStorage.setItem('refresh_token', 'r')
    api.get.mockResolvedValueOnce({ data: makeUser('ADMIN') })
    renderProbe(<Probe />)
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent(/^auth/))
    await userEvent.click(screen.getByText('do-logout'))
    expect(api.post).toHaveBeenCalledWith('/auth/logout/')
    expect(window.localStorage.getItem('access_token')).toBeNull()
    expect(window.localStorage.getItem('refresh_token')).toBeNull()
    expect(screen.getByTestId('state')).toHaveTextContent('anonymous')
  })

  it('refreshUser met à jour l’utilisateur', async () => {
    const u2 = makeUser('DIRECTION', { first_name: 'Nouveau' })
    api.get.mockResolvedValue({ data: u2 })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('refresh-user'))
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent(':DIRECTION'))
    expect(api.get).toHaveBeenCalledWith('/auth/me/')
  })

  it('refreshUser avec un rôle interdit purge la session', async () => {
    window.localStorage.setItem('access_token', 't')
    api.get.mockResolvedValue({ data: makeUser('FORMATEUR') })
    renderProbe(<Probe />)
    await userEvent.click(screen.getByText('refresh-user'))
    await waitFor(() => expect(screen.getByTestId('state')).toHaveTextContent('anonymous'))
  })

  it('useAuth hors provider lève une erreur explicite', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Probe />)).toThrow(/within an AuthProvider/)
    spy.mockRestore()
  })
})
