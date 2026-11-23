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
import AnnulerSeance from './AnnulerSeance'

const AFFECTATION = { id: 42, intitule: 'Didactique et Pédagogie STAPS' }

describe('AnnulerSeance', () => {
  beforeEach(() => { apiController.reset() })

  const monter = (props = {}) => render(
    <AllProviders user={makeUser('SECRETARIAT')}>
      <AnnulerSeance affectation={AFFECTATION} onClose={vi.fn()} onDone={vi.fn()} {...props} />
    </AllProviders>,
  )

  it('exige un motif avant d’envoyer', async () => {
    monter()
    const bouton = screen.getByRole('button', { name: 'Annuler la séance' })
    expect(bouton).toBeDisabled()

    await userEvent.type(screen.getByLabelText(/Motif/), 'Enseignant indisponible')
    expect(bouton).toBeEnabled()
  })

  it('transmet le motif au serveur et signale la réussite', async () => {
    apiController.setRoute('/edts/lmd/items/42/cancel/', { annulee: true, motif: 'Salle fermée', reversible: true })
    const onDone = vi.fn()
    monter({ onDone })

    await userEvent.type(screen.getByLabelText(/Motif/), 'Salle fermée')
    await userEvent.click(screen.getByRole('button', { name: 'Annuler la séance' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(
      '/edts/lmd/items/42/cancel/',
      { motif: 'Salle fermée' },
    ))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('réactivation : envoie reactiver=true', async () => {
    apiController.setRoute('/edts/lmd/items/42/cancel/', { reactivee: true, reversible: true })
    const onDone = vi.fn()
    monter({ reactiver: true, onDone })

    await userEvent.type(screen.getByLabelText(/Motif/), 'Erreur de saisie corrigée')
    await userEvent.click(screen.getByRole('button', { name: 'Réactiver' }))

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(
      '/edts/lmd/items/42/cancel/',
      { motif: 'Erreur de saisie corrigée', reactiver: true },
    ))
    await waitFor(() => expect(onDone).toHaveBeenCalled())
  })

  it('affiche le refus serveur et ne ferme pas', async () => {
    apiController.setRoute('/edts/lmd/items/42/cancel/', () =>
      Promise.reject({
        response: {
          status: 409,
          data: { motif_echec: 'STATUT_EDT_INVALIDE', explication: 'Le statut « PUBLIE » interdit toute modification.' },
        },
      }))
    const onDone = vi.fn()
    monter({ onDone })

    await userEvent.type(screen.getByLabelText(/Motif/), 'Test refus')
    await userEvent.click(screen.getByRole('button', { name: 'Annuler la séance' }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/PUBLIE/)).toBeInTheDocument()
    expect(onDone).not.toHaveBeenCalled()
  })
})
