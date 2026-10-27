import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock du client API (même instance que celle importée par AuthContext).
vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser, makeLoginResponse } from '@/test/utils/factories'
import Login from '@/pages/Login'

const renderLogin = (options) =>
  renderWithProviders(<Login />, { initialEntries: ['/login'], routePattern: '/login', ...options })

describe('pages/Login.jsx', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche le formulaire de connexion et la marque INJS', () => {
    renderLogin()
    expect(screen.getByLabelText("Nom d'utilisateur")).toBeInTheDocument()
    expect(screen.getByLabelText('Mot de passe')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /se connecter/i })).toBeInTheDocument()
    expect(screen.getAllByText(/INJS/i).length).toBeGreaterThan(0)
  })

  it('soumet les identifiants et établit la session', async () => {
    const user = makeUser('ADMIN', { username: 'admin' })
    apiMock.post.mockResolvedValueOnce({ data: makeLoginResponse(user) })
    renderLogin()

    await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'admin')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'admin123')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    await waitFor(() =>
  expect(apiMock.post).toHaveBeenCalledWith('/auth/login/', {
    username: 'admin',
    password: 'admin123',
  })
)
    await waitFor(() => expect(window.localStorage.getItem('access_token')).toBe('access.jwt'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('affiche le message d’erreur renvoyé par le serveur', async () => {
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Compte verrouillé' } } })
    renderLogin()

    await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'x')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'y')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Compte verrouillé')
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('affiche un message générique quand le serveur ne donne pas de détail', async () => {
    apiMock.post.mockRejectedValueOnce(new Error('Network'))
    renderLogin()

    await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'x')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'y')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Identifiants incorrects')
  })

  it('refuse un compte FORMATEUR (réservé mobile)', async () => {
    const formateur = makeUser('FORMATEUR')
    apiMock.post.mockResolvedValueOnce({ data: makeLoginResponse(formateur, { refreshInCookie: false }) })
    renderLogin()

    await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'f001')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'f001')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/enseignant/i)
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('refuse un compte AUDITEUR / étudiant (réservé mobile)', async () => {
    const etudiant = makeUser('AUDITEUR')
    apiMock.post.mockResolvedValueOnce({ data: makeLoginResponse(etudiant, { refreshInCookie: false }) })
    renderLogin()

    await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'p001')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'p001')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/étudiant/i)
  })

  it('bascule l’affichage du mot de passe', async () => {
    renderLogin()
    const pwd = screen.getByLabelText('Mot de passe')
    expect(pwd).toHaveAttribute('type', 'password')
    await userEvent.click(screen.getByRole('button', { name: /voir le mot de passe/i }))
    expect(pwd).toHaveAttribute('type', 'text')
    await userEvent.click(screen.getByRole('button', { name: /masquer le mot de passe/i }))
    expect(pwd).toHaveAttribute('type', 'password')
  })

  it('redirige vers l’accueil si déjà authentifié', async () => {
    const admin = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(admin)
    renderLogin({ authUser: admin, initialEntries: ['/login'], routePattern: '/login' })
    // Le formulaire de connexion ne doit pas être rendu (Navigate to="/").
    await waitFor(() => expect(screen.queryByLabelText(/nom d'utilisateur/i)).not.toBeInTheDocument())
  })

  // Régression §10.1 (corrigé au LOT 46) : un compte WEB autorisé marqué
  // must_change_password se connecte normalement ; Login navigue vers
  // l'accueil, et le garde ProtectedRoute le renvoie alors vers l'écran de
  // changement obligatoire (cette redirection est testée en bout en bout
  // dans ProtectedRoute.test.jsx, avec le vrai Login et la vraie page forcée).
  it('connecte un compte web marqué must_change_password sans erreur (§10.1)', async () => {
    const user = makeUser('ADMIN', { username: 'badgeadmin', must_change_password: true })
    apiMock.post.mockResolvedValueOnce({ data: makeLoginResponse(user) })
    renderLogin()
    await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'badgeadmin')
    await userEvent.type(screen.getByLabelText('Mot de passe'), 'admin123')
    await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))

    await waitFor(() => expect(window.localStorage.getItem('access_token')).toBe('access.jwt'))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
