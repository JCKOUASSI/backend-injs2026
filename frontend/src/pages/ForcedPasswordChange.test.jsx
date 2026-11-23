/**
 * LOT 46 (§10.1) — écran de changement de mot de passe obligatoire :
 * validations, appel API, gestion d'erreur, déconnexion.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
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
import { makeUser } from '@/test/utils/factories'
import { FORCED_PASSWORD_PATH } from '@/components/auth/ProtectedRoute'
import ForcedPasswordChange from '@/pages/ForcedPasswordChange'

function renderPage() {
  const me = makeUser('ADMIN', { must_change_password: true })
  apiController.setMe(me)
  window.localStorage.setItem('access_token', 'test-access-token')
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[FORCED_PASSWORD_PATH]}>
        <AuthProvider>
          <ToastProvider>
            <Routes>
              <Route path={FORCED_PASSWORD_PATH} element={<ForcedPasswordChange />} />
              <Route path="/login" element={<div>PAGE LOGIN</div>} />
              <Route path="/" element={<div>PAGE ACCUEIL</div>} />
            </Routes>
          </ToastProvider>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

const fill = (label, value) =>
  fireEvent.change(screen.getByLabelText(label), { target: { value } })

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
})

describe('ForcedPasswordChange (§10.1)', () => {
  it('rend le libellé obligatoire, les trois champs et la déconnexion', async () => {
    renderPage()
    expect(await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })).toBeInTheDocument()
    expect(screen.getByLabelText(/mot de passe actuel/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/^nouveau mot de passe/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/confirmer le nouveau mot de passe/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /définir mon mot de passe/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /se déconnecter/i })).toBeInTheDocument()
  })

  it('bloque la soumission avec champs vides sans appeler l’API', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    // Ancien et nouveau manquants ; deux champs vides étant identiques, il n'y
    // a pas encore d'erreur de concordance (celle-ci apparaît dès qu'ils
    // divergent, testée dans le test suivant).
    expect(await screen.findAllByText('Champ requis.')).toHaveLength(2)
    expect(apiMock.post).not.toHaveBeenCalledWith('/auth/me/change-password/', expect.anything())
  })

  it('exige un nouveau mot de passe d’au moins 8 caractères et la confirmation', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    fill(/mot de passe actuel/i, 'Temp1234')
    fill(/^nouveau mot de passe/i, 'court')
    fill(/confirmer le nouveau mot de passe/i, 'different')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByText('Minimum 8 caractères.')).toBeInTheDocument()
    expect(screen.getByText('Les mots de passe ne correspondent pas.')).toBeInTheDocument()
    expect(apiMock.post).not.toHaveBeenCalledWith('/auth/me/change-password/', expect.anything())
  })

  it('change le mot de passe, recharge l’utilisateur puis lève le verrou vers l’accueil', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })

    // Le backend bascule le drapeau : le /auth/me suivant revient sans contrainte.
    apiController.setRoute(/change-password/, () => {
      apiController.setMe(makeUser('ADMIN', { must_change_password: false }))
      return { detail: 'Mot de passe modifié avec succès.' }
    })

    fill(/mot de passe actuel/i, 'Temp1234')
    fill(/^nouveau mot de passe/i, 'Nouveau-987')
    fill(/confirmer le nouveau mot de passe/i, 'Nouveau-987')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/auth/me/change-password/', {
      old_password: 'Temp1234', new_password: 'Nouveau-987',
    }))
    expect(await screen.findByText('PAGE ACCUEIL')).toBeInTheDocument()
  })

  it('affiche une erreur de mot de passe renvoyée par le serveur sans quitter l’écran', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    apiMock.post.mockRejectedValueOnce({
      response: { data: { new_password: ['Ce mot de passe est trop similaire à votre identifiant.'] } },
    })

    fill(/mot de passe actuel/i, 'Temp1234')
    fill(/^nouveau mot de passe/i, 'adminadmin')
    fill(/confirmer le nouveau mot de passe/i, 'adminadmin')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByText('Ce mot de passe est trop similaire à votre identifiant.')).toBeInTheDocument()
    expect(screen.queryByText('PAGE ACCUEIL')).not.toBeInTheDocument()
  })

  it('affiche l’erreur d’ancien mot de passe renvoyée par le serveur (liste)', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    apiMock.post.mockRejectedValueOnce({
      response: { data: { old_password: ['Votre ancien mot de passe est incorrect.'] } },
    })

    fill(/mot de passe actuel/i, 'Faux-0000')
    fill(/^nouveau mot de passe/i, 'Nouveau-987')
    fill(/confirmer le nouveau mot de passe/i, 'Nouveau-987')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByText('Votre ancien mot de passe est incorrect.')).toBeInTheDocument()
    expect(screen.queryByText('PAGE ACCUEIL')).not.toBeInTheDocument()
  })

  it('gère un message de nouveau mot de passe sous forme de chaîne simple et un détail global', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    // new_password renvoyé comme chaîne simple (et non un tableau DRF).
    apiMock.post.mockRejectedValueOnce({
      response: { data: { new_password: 'Ce mot de passe est trop courant.' } },
    })

    fill(/mot de passe actuel/i, 'Temp1234')
    fill(/^nouveau mot de passe/i, 'password')
    fill(/confirmer le nouveau mot de passe/i, 'password')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByText('Ce mot de passe est trop courant.')).toBeInTheDocument()
  })

  it('affiche dans l’alerte le détail fourni par le serveur', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Service momentanément indisponible.' } } })

    fill(/mot de passe actuel/i, 'Temp1234')
    fill(/^nouveau mot de passe/i, 'Nouveau-987')
    fill(/confirmer le nouveau mot de passe/i, 'Nouveau-987')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Service momentanément indisponible.')
  })

  it('affiche une erreur générique quand le serveur ne donne pas de champ', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    apiMock.post.mockRejectedValueOnce(new Error('Network'))

    fill(/mot de passe actuel/i, 'Temp1234')
    fill(/^nouveau mot de passe/i, 'Nouveau-987')
    fill(/confirmer le nouveau mot de passe/i, 'Nouveau-987')
    fireEvent.click(screen.getByRole('button', { name: /définir mon mot de passe/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('Une erreur est survenue.')
  })

  it('bascule l’affichage en clair des trois mots de passe via les boutons œil', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    const old = screen.getByLabelText(/mot de passe actuel/i)
    const next = screen.getByLabelText(/^nouveau mot de passe/i)
    const toggleOf = (input) => input.closest('.login-input').querySelector('.login-password-toggle')
    expect(old).toHaveAttribute('type', 'password')
    fireEvent.click(toggleOf(old))
    expect(old).toHaveAttribute('type', 'text')
    fireEvent.click(toggleOf(next))
    expect(next).toHaveAttribute('type', 'text')
  })

  it('la déconnexion appelle le logout et renvoie à la page de connexion', async () => {
    renderPage()
    await screen.findByRole('heading', { name: /changement de mot de passe obligatoire/i })
    fireEvent.click(screen.getByRole('button', { name: /se déconnecter/i }))

    expect(await screen.findByText('PAGE LOGIN')).toBeInTheDocument()
    expect(apiMock.post).toHaveBeenCalledWith('/auth/logout/')
    expect(window.localStorage.getItem('access_token')).toBeNull()
  })
})
