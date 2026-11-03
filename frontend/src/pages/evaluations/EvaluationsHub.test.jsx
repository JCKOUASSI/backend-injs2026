/**
 * Hub Évaluations premium : sessions au format métier et avancement
 * de la saisie (notes brouillons visibles comme telles).
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
import EvaluationsHub from '@/pages/evaluations/EvaluationsHub'

const STATS = {
  sessions: 8, sessions_par_statut: { OUVERTE: 4, PUBLIEE: 2, CLOTUREE: 2 },
  evaluations: 32, participants: 800, notes: 800,
  notes_par_statut: { BROUILLON: 800 }, avancement_validation: 0.0,
  releves: 0, types_actifs: 4,
}

const SESSIONS = {
  results: [
    {
      id: 1, libelle: '[Exemple] Session normale S1 — LICENCE STAPS (2026-2027)',
      formation: 'LICENCE STAPS', niveau: 'L1', semestre: '',
      annee: '2026-2027', type_session: 'NORMALE',
      type_session_display: 'Session normale',
      date_debut: '2026-12-07', date_fin: '2027-01-15',
      statut: 'OUVERTE', statut_display: 'Ouverte',
      verrouillee: false, nb_evaluations: 4,
    },
  ],
}

const NOTES = {
  results: [
    {
      id: 1, etudiant_id: 3, matricule: 'INJS26-0003',
      nom_complet: 'Koffi Ange', evaluation: '[Exemple] Contrôle continu — UE1-E1',
      ecue: 'UE1-E1', formation: 'LICENCE STAPS', niveau: 'L1',
      valeur: 12.5, bareme: 20, statut: 'BROUILLON',
      statut_display: 'Brouillon', verrouillee: false,
    },
  ],
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/evaluations-academiques/hub/stats/', () => STATS)
  apiController.setRoute('/evaluations-academiques/hub/sessions/', () => SESSIONS)
  apiController.setRoute('/evaluations-academiques/hub/evaluations/', () => ({ results: [] }))
  apiController.setRoute('/evaluations-academiques/hub/notes/', () => NOTES)
  apiController.setRoute('/evaluations-academiques/hub/releves/', () => ({ results: [] }))
  apiController.setRoute('/evaluations-academiques/types-evaluation/', () => ({ results: [] }))
}

const mount = () => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<EvaluationsHub ongletInitial="notes" />, {
    authUser: me, routePattern: '*', initialEntries: ['/evaluations/saisie'],
  })
}

beforeEach(preparer)

describe('Hub Évaluations premium', () => {
  it('affiche les notes brouillons et l’avancement nul de validation', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('12,5')).toBeInTheDocument())
    expect(container.textContent).toContain('0 % des notes validées')
    expect(container.textContent).toContain('Brouillon')
    expect(container.textContent).not.toContain('BROUILLON')
  })

  it('affiche les sessions avec leurs dates JJ/MM/AAAA', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByText('12,5')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: /^Sessions/ }))
    await waitFor(() => {
      expect(screen.getByText('07/12/2026')).toBeInTheDocument()
    })
    expect(screen.getAllByText('Ouverte').length).toBeGreaterThanOrEqual(2)
  })
})
