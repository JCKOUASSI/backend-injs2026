import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Profile from './Profile'

function renderProfile(user = makeUser('ADMIN', { first_name: 'Awa', last_name: 'Koné' })) {
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user} initialEntries={['/profile']} routePattern="/profile">
      <Profile />
    </AllProviders>,
  )
}

describe('Mon profil — photo de profil', () => {
  let createObjectURL
  let revokeObjectURL

  beforeEach(() => {
    localStorage.clear()
    createObjectURL = URL.createObjectURL
    revokeObjectURL = URL.revokeObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:profil-photo')
    URL.revokeObjectURL = vi.fn()
  })

  afterEach(() => {
    cleanup()
    apiController.reset()
    URL.createObjectURL = createObjectURL
    URL.revokeObjectURL = revokeObjectURL
  })

  it('permet de sélectionner et envoyer une image, puis affiche la photo mise à jour', async () => {
    const updated = makeUser('ADMIN', {
      first_name: 'Awa', last_name: 'Koné', photo_url: '/auth/me/photo/?v=avatar.jpg',
    })
    apiController.setRoute('/auth/me/photo/', (_path, body) => {
      expect(body).toBeInstanceOf(FormData)
      expect(body.get('photo').name).toBe('portrait.png')
      return updated
    })
    renderProfile()

    const input = await screen.findByLabelText('Choisir une photo de profil')
    const file = new File(['image bytes'], 'portrait.png', { type: 'image/png' })
    fireEvent.change(input, { target: { files: [file] } })

    await waitFor(() => expect(apiController.api.post).toHaveBeenCalledWith(
      '/auth/me/photo/', expect.any(FormData),
    ))
    expect(await screen.findByRole('img', { name: 'Photo de votre profil' })).toBeInTheDocument()
    expect(apiController.api.getBlob).toHaveBeenCalledWith('/auth/me/photo/?v=avatar.jpg')
  })

  it('permet de supprimer une photo déjà enregistrée', async () => {
    renderProfile(makeUser('ADMIN', {
      first_name: 'Awa', last_name: 'Koné', photo_url: '/auth/me/photo/?v=avatar.jpg',
    }))
    await screen.findByRole('button', { name: 'Supprimer la photo' })
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer la photo' }))
    await waitFor(() => expect(apiController.api.delete).toHaveBeenCalledWith('/auth/me/photo/'))
  })
})
