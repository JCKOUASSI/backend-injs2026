import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

// Mock du client API (même instance que celle importée par AuthContext).
vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser, makeLoginResponse } from '@/test/utils/factories'
import Login from '@/pages/Login'

const renderLogin = () =>
  renderWithProviders(<Login />, { initialEntries: ['/login'], routePattern: '/login' })

const refuser = (data, status = 403) =>
  Promise.reject({ response: { status, data } })

const saisirIdentifiants = async () => {
  await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), 'admin')
  await userEvent.type(screen.getByLabelText('Mot de passe'), 'admin123')
  await userEvent.click(screen.getByRole('button', { name: /se connecter/i }))
}

describe('pages/Login.jsx — étape MFA (LOT 3)', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('demande le code TOTP quand le backend répond MFA_REQUIRED puis établit la session', async () => {
    const user = makeUser('ADMIN', { username: 'admin' })
    apiMock.post.mockImplementation((path) => {
      if (path === '/auth/login/') {
        return refuser({
          code: 'MFA_REQUIRED',
          detail: 'Vérification en deux étapes.',
          mfa_token: 'mfa.jeton',
          mfa_duree: 5,
        })
      }
      return Promise.resolve({ data: makeLoginResponse(user) })
    })
    renderLogin()
    await saisirIdentifiants()

    const saisieCode = await screen.findByTestId('mfa-code-input')
    expect(screen.getByText(/deuxième étape/i)).toBeInTheDocument()
    expect(screen.getByText('admin', { selector: 'strong' })).toBeInTheDocument()

    await userEvent.type(saisieCode, '123456')
    await userEvent.click(screen.getByRole('button', { name: /vérifier le code/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/auth/mfa/verify/', {
        mfa_token: 'mfa.jeton', code: '123456',
      })
    )
    await waitFor(() =>
      expect(window.localStorage.getItem('access_token')).toBe('access.jwt'))
  })

  it('garde le formulaire de code quand le code est invalide', async () => {
    apiMock.post.mockImplementation((path) => {
      if (path === '/auth/login/') {
        return refuser({ code: 'MFA_REQUIRED', detail: '', mfa_token: 'mfa.jeton' })
      }
      return refuser({ code: 'MFA_CODE_INVALIDE', detail: 'Code MFA invalide' }, 400)
    })
    renderLogin()
    await saisirIdentifiants()
    const saisieCode = await screen.findByTestId('mfa-code-input')

    await userEvent.type(saisieCode, '000000')
    await userEvent.click(screen.getByRole('button', { name: /vérifier le code/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Code MFA invalide')
    expect(screen.getByTestId('mfa-code-input')).toBeInTheDocument()
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('reprend la saisie des identifiants quand le jeton a expiré', async () => {
    apiMock.post.mockImplementation((path) => {
      if (path === '/auth/login/') {
        return refuser({ code: 'MFA_REQUIRED', detail: '', mfa_token: 'mfa.jeton' })
      }
      return refuser({ code: 'MFA_JETON_INVALIDE', detail: 'Jeton MFA invalide ou expiré' }, 400)
    })
    renderLogin()
    await saisirIdentifiants()
    const saisieCode = await screen.findByTestId('mfa-code-input')

    await userEvent.type(saisieCode, '123456')
    await userEvent.click(screen.getByRole('button', { name: /vérifier le code/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent(/expiré/i)
    expect(screen.queryByTestId('mfa-code-input')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /se connecter/i })).toBeInTheDocument()
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('bloque la connexion quand le MFA est obligatoire et non armé (MFA_OBLIGATOIRE)', async () => {
    apiMock.post.mockImplementation((path) => {
      if (path === '/auth/login/') {
        return refuser({
          code: 'MFA_OBLIGATOIRE',
          detail:
            'Ce compte porte un rôle sensible : l’authentification ' +
            'multifactor (MFA) doit être activée par un ' +
            'administrateur avant de pouvoir se connecter.',
        })
      }
      return Promise.resolve({ data: {} })
    })
    renderLogin()
    await saisirIdentifiants()

    expect(await screen.findByRole('alert')).toHaveTextContent(/multifactor/i)
    expect(screen.queryByTestId('mfa-code-input')).not.toBeInTheDocument()
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('affiche le message de compte verrouillé (COMPTE_VERROUILLE)', async () => {
    apiMock.post.mockImplementation((path) => {
      if (path === '/auth/login/') {
        return refuser({ code: 'COMPTE_VERROUILLE', detail: 'Ce compte est verrouillé' })
      }
      return Promise.resolve({ data: {} })
    })
    renderLogin()
    await saisirIdentifiants()

    expect(await screen.findByRole('alert')).toHaveTextContent('Ce compte est verrouillé')
    expect(screen.queryByTestId('mfa-code-input')).not.toBeInTheDocument()
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })

  it('retourne aux identifiants via le lien de retour', async () => {
    apiMock.post.mockImplementation((path) => {
      if (path === '/auth/login/') {
        return refuser({ code: 'MFA_REQUIRED', detail: '', mfa_token: 'mfa.jeton' })
      }
      return Promise.resolve({ data: {} })
    })
    renderLogin()
    await saisirIdentifiants()
    await screen.findByTestId('mfa-code-input')

    await userEvent.click(screen.getByTestId('mfa-back'))
    expect(screen.queryByTestId('mfa-code-input')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /se connecter/i })).toBeInTheDocument()
  })
})
