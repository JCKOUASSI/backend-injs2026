import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Conception from './Conception'

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <Conception />
    </AllProviders>,
  )
}

describe('GET-INJS — Conception (Documentation technique)', () => {
  beforeEach(() => {
    apiController.reset()
    URL.createObjectURL = vi.fn(() => 'blob:conception')
    URL.revokeObjectURL = vi.fn()
    window.open = vi.fn()
  })

  it('présente les six cartes de la conception au format de référence', () => {
    rendre()

    expect(screen.getByRole('heading', { name: 'Conception du module GET INJS APP' }))
      .toBeInTheDocument()
    expect(screen.getByText('Documentation technique')).toBeInTheDocument()

    // Architecture en couches.
    expect(screen.getByText('Architecture en couches')).toBeInTheDocument()
    expect(screen.getByText('React 18 · Vite · React Router')).toBeInTheDocument()
    expect(screen.getByText('Python déterministe (edts/moteur)')).toBeInTheDocument()

    // Algorithme de génération.
    expect(screen.getByText('Algorithme de génération')).toBeInTheDocument()
    expect(screen.getByText(/Backtracking chronologique borné/)).toBeInTheDocument()
    expect(screen.getByText(/Publication : geste humain/)).toBeInTheDocument()

    // API du module : routes réelles du module.
    expect(screen.getByText('API du module')).toBeInTheDocument()
    expect(screen.getByText('/api/edts/lmd/import/inscrits/')).toBeInTheDocument()
    expect(screen.getByText('/api/edts/lmd/referentiels/')).toBeInTheDocument()
    expect(screen.getByText('/api/edts/campagnes/{id}/publier/')).toBeInTheDocument()

    // Modèle de données : tables réelles.
    expect(screen.getByText('Modèle de données')).toBeInTheDocument()
    expect(screen.getByText('edts_inscriptionimportee')).toBeInTheDocument()
    expect(screen.getByText('gi_seance_registre')).toBeInTheDocument()

    // Commandes d'implémentation.
    expect(screen.getByText("Commandes d'implémentation")).toBeInTheDocument()
    expect(screen.getByText('python backend/manage.py test edts')).toBeInTheDocument()

    // Exigences couvertes.
    expect(screen.getByText('Exigences couvertes')).toBeInTheDocument()
    expect(screen.getByText('Fichier externe')).toBeInTheDocument()
    expect(screen.getByText(/3 786 étudiants inscrits/)).toBeInTheDocument()
  })

  it('télécharge le document complet via l’endpoint de conception', async () => {
    const user = userEvent.setup()
    rendre()

    await user.click(screen.getByRole('button', {
      name: /Télécharger Conception-GET-INJS\.txt/,
    }))
    await waitFor(() => {
      expect(apiMock.getBlob).toHaveBeenCalledWith('/edts/lmd/conception/')
    })
  })

  it('consulte le document en ligne dans un nouvel onglet', async () => {
    const user = userEvent.setup()
    rendre()

    await user.click(screen.getByRole('button', { name: 'Consulter en ligne' }))
    await waitFor(() => {
      expect(apiMock.getBlob).toHaveBeenCalledWith('/edts/lmd/conception/')
      expect(window.open).toHaveBeenCalledWith(
        'blob:conception', '_blank', 'noopener')
    })
  })
})
