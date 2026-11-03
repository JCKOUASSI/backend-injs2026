/**
 * Hub Diplômation premium : éligibilité factuelle (états métier) et
 * diplômes (numéro unique mono, statut jamais « validé » par défaut).
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import DiplomationHub from '@/pages/diplomation/DiplomationHub'

const STATS = {
  diplomes: 60,
  par_statut: { BROUILLON: 30, VALIDATION_PENDING: 30 },
  reeditions: 0, registres: 1, registres_clotures: 0, modeles: 4,
  etudiants_fin_cycle: 710,
}

const ELIGIBLES = {
  results: [
    {
      id: 1, etudiant_id: 42, matricule: 'INJS21-0042',
      nom_complet: 'Kouassi Marie', formation: 'MASTER STAPS',
      niveau: 'M2', decision_jury: true,
      diplome_statut: 'VALIDATION_PENDING',
      diplome_statut_display: 'En attente de validation',
      etat: 'Diplôme préparé',
    },
    {
      id: 2, etudiant_id: 43, matricule: 'INJS21-0043',
      nom_complet: 'Diakité Aminata', formation: 'MASTER STAPS',
      niveau: 'M2', decision_jury: false, diplome_statut: null,
      diplome_statut_display: null, etat: 'En attente du jury',
    },
  ],
}

const DIPLOMES = {
  results: [
    {
      id: 1, etudiant_id: 42, matricule: 'INJS21-0042',
      nom_complet: 'Kouassi Marie', ref_formation: 'MASTER STAPS',
      niveau: 'Master 2', mention: 'Bien', credits_acquis: 30,
      numero_unique: '0dbc01f4-eac9-5c17-b494-1234567890ab',
      statut: 'VALIDATION_PENDING',
      statut_display: 'En attente de validation',
    },
  ],
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/graduation/stats/', () => STATS)
  apiController.setRoute('/graduation/eligibles/', () => ELIGIBLES)
  apiController.setRoute('/graduation/diplomes/', () => DIPLOMES)
  apiController.setRoute('/graduation/modeles/', () => ({ results: [] }))
  apiController.setRoute('/graduation/registres/', () => ({ results: [] }))
}

const mount = () => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<DiplomationHub />, {
    authUser: me, routePattern: '*', initialEntries: ['/diplomation/eligibilite'],
  })
}

beforeEach(preparer)

describe('Hub Diplômation premium', () => {
  it('affiche l’éligibilité factuelle des fin-de-cycle', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getAllByText('Diplôme préparé').length).toBeGreaterThanOrEqual(1))
    expect(container.textContent).toContain('En attente du jury')
    expect(container.textContent).toContain('710 étudiants en fin de cycle')
  })

  it('affiche les diplômes préparés, jamais présentés comme validés', async () => {
    const user = userEvent.setup()
    const { container } = mount()
    await waitFor(() => expect(screen.getAllByText('Diplôme préparé').length).toBeGreaterThanOrEqual(1))
    await user.click(screen.getByRole('tab', { name: /Diplômes & attestations/ }))
    await waitFor(() => {
      expect(screen.getByText('0dbc01f4-eac9-5c17-b494-1234567890ab')).toBeInTheDocument()
    })
    expect(container.textContent).not.toContain('VALIDATION_PENDING')
    expect(container.textContent).not.toContain('VALIDATED')
  })
})
