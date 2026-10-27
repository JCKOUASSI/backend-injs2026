/**
 * LOT 46 (§10.1) — garde d'accès et changement de mot de passe obligatoire.
 * Un compte marqué `must_change_password` est reconduit vers l'écran dédié,
 * quelle que soit la page demandée, jusqu'au changement effectif.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AuthProvider } from '@/context/AuthContext'
import { ToastProvider } from '@/context/ToastContext'
import { makeUser, makeLoginResponse } from '@/test/utils/factories'
import ProtectedRoute, { FORCED_PASSWORD_PATH } from '@/components/auth/ProtectedRoute'
import ForcedPasswordChange from '@/pages/ForcedPasswordChange'
import Login from '@/pages/Login'

const FORCED_HEADING = /changement de mot de passe obligatoire/i

function renderApp({ me, initial = '/secret', loginResponse = null } = {}) {
  apiController.setMe(me)
  if (me) window.localStorage.setItem('access_token', 'test-access-token')
  if (loginResponse) apiMock.post.mockResolvedValueOnce(loginResponse)

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initial]}>
        <AuthProvider>
          <ToastProvider>
            <Routes>
              <Route path="/login" element={<Login />} />
              <Route path={FORCED_PASSWORD_PATH} element={
                <ProtectedRoute><ForcedPasswordChange /></ProtectedRoute>
              } />
              <Route path="/secret" element={
                <ProtectedRoute><div>PAGE SECRÈTE</div></ProtectedRoute>
              } />
              <Route path="/" element={<ProtectedRoute><div>PAGE ACCUEIL</div></ProtectedRoute>} />
              <Route path="/admin-only" element={
                <ProtectedRoute allowedRoles={['ADMIN']}><div>PAGE ADMIN</div></ProtectedRoute>
              } />
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
})

describe('ProtectedRoute — forçage du changement de mot de passe (§10.1)', () => {
  it('un compte marqué must_change_password est renvoyé vers l’écran dédié depuis n’importe quelle page', async () => {
    const me = makeUser('ADMIN', { must_change_password: true })
    renderApp({ me, initial: '/secret' })

    expect(await screen.findByRole('heading', { name: FORCED_HEADING })).toBeInTheDocument()
    expect(screen.queryByText('PAGE SECRÈTE')).not.toBeInTheDocument()
  })

  it('l’écran dédié reste accessible au compte marqué (pas de boucle de redirection)', async () => {
    const me = makeUser('ADMIN', { must_change_password: true })
    renderApp({ me, initial: FORCED_PASSWORD_PATH })

    expect(await screen.findByRole('heading', { name: FORCED_HEADING })).toBeInTheDocument()
    expect(screen.getByLabelText(/mot de passe actuel/i)).toBeInTheDocument()
  })

  it('un compte sans contrainte accède normalement à la page protégée', async () => {
    const me = makeUser('ADMIN', { must_change_password: false })
    renderApp({ me, initial: '/secret' })
    expect(await screen.findByText('PAGE SECRÈTE')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: FORCED_HEADING })).not.toBeInTheDocument()
  })

  it('un visiteur non authentifié est renvoyé vers la connexion', async () => {
    renderApp({ me: null, initial: '/secret' })
    // La page de login est rendue (champ identifiant) ; pas de page secrète.
    expect(await screen.findByLabelText(/nom d'utilisateur/i)).toBeInTheDocument()
    expect(screen.queryByText('PAGE SECRÈTE')).not.toBeInTheDocument()
  })

  it('un compte sans contrainte qui ouvrirait l’URL dédiée est reconduit à l’accueil', async () => {
    const me = makeUser('ADMIN', { must_change_password: false })
    renderApp({ me, initial: FORCED_PASSWORD_PATH })
    expect(await screen.findByText('PAGE ACCUEIL')).toBeInTheDocument()
  })

  it('applique aussi la restriction de rôle : un encadrant ne peut entrer dans une zone ADMIN', async () => {
    const me = makeUser('ENCADRANT', { must_change_password: false })
    renderApp({ me, initial: '/admin-only' })
    expect(await screen.findByText('PAGE ACCUEIL')).toBeInTheDocument()
    expect(screen.queryByText('PAGE ADMIN')).not.toBeInTheDocument()
  })

  it('un ADMIN autorisé atteint la zone à rôle restreint', async () => {
    const me = makeUser('ADMIN', { must_change_password: false })
    renderApp({ me, initial: '/admin-only' })
    expect(await screen.findByText('PAGE ADMIN')).toBeInTheDocument()
  })

  it('parcours de connexion complet : login d’un compte marqué → redirection forcée', async () => {
    const flagged = makeUser('ADMIN', { username: 'badgeadmin', must_change_password: true })
    renderApp({ me: null, initial: '/login', loginResponse: { data: makeLoginResponse(flagged) } })

    await userEvent.type(await screen.findByLabelText(/nom d'utilisateur/i), 'badgeadmin')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'admin123')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    // Après la connexion, le garde intercepte la navigation vers l'accueil.
    expect(await screen.findByRole('heading', { name: FORCED_HEADING })).toBeInTheDocument()
  })

  it('une fois le mot de passe changé (le drapeau retombe), l’utilisateur accède à sa destination', async () => {
    const flagged = makeUser('ADMIN', { must_change_password: true })
    const cleared = makeUser('ADMIN', { must_change_password: false })
    apiController.setMe(flagged)
    window.localStorage.setItem('access_token', 'test-access-token')
    // Le POST de changement fait basculer le /auth/me suivant (drapeau levé).
    apiController.setRoute(/change-password/, () => {
      apiController.setMe(cleared)
      return { detail: 'Mot de passe modifié avec succès.' }
    })

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/secret']}>
          <AuthProvider>
            <ToastProvider>
              <Routes>
                <Route path={FORCED_PASSWORD_PATH} element={
                  <ProtectedRoute><ForcedPasswordChange /></ProtectedRoute>
                } />
                <Route path="/secret" element={
                  <ProtectedRoute><div>PAGE SECRÈTE</div></ProtectedRoute>
                } />
                <Route path="/" element={<ProtectedRoute><div>PAGE ACCUEIL</div></ProtectedRoute>} />
              </Routes>
            </ToastProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await screen.findByRole('heading', { name: FORCED_HEADING })
    fireEvent.change(screen.getByLabelText(/mot de passe actuel/i), { target: { value: 'Temp1234' } })
    fireEvent.change(screen.getByLabelText(/^nouveau mot de passe/i), { target: { value: 'Nouveau-987' } })
    fireEvent.change(screen.getByLabelText(/confirmer le nouveau mot de passe/i), { target: { value: 'Nouveau-987' } })
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByText('PAGE SECRÈTE')).toBeInTheDocument()
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/auth/me/change-password/', {
      old_password: 'Temp1234', new_password: 'Nouveau-987',
    }))
  })
})
