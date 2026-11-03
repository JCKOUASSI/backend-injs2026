/**
 * Hub Jurys premium : panorama, sessions avec étape en badge et
 * decisions (moyenne fr, décision métier, lien étudiant).
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
import JurysHub from '@/pages/jurys/JurysHub'

const STATS = {
  sessions: 16, par_statut: { PUBLIE: 2 }, sessions_publiees: 2,
  pv_generes: 0, membres: 48, propositions: 0, decisions: 84,
  par_decision: { ADMIS: 52, ADMIS_RESERVES: 12, AJOURNE: 20 },
  taux_admis: 76.2,
}

const SESSIONS = {
  results: [
    {
      id: 1, libelle: '[Exemple] Session normale — LICENCE STAPS L3 (2026-2027)',
      formation: 'LICENCE STAPS', niveau: 'L3', semestre: 'Semestre 5',
      annee: '2026-2027', type_session: 'NORMALE',
      type_session_display: 'Session normale', statut: 'DELIBERATION',
      statut_display: 'Délibération', nb_membres: 3, nb_decisions: 0,
      pv: false, created_at: '2026-11-03T08:00:00',
    },
  ],
}

const DECISIONS = {
  results: [
    {
      id: 1, etudiant_id: 9, matricule: 'INJS24-0009', nom: 'Koné Aïcha',
      formation: 'LICENCE STAPS', niveau: 'L3', decision: 'ADMIS',
      decision_display: 'Admis', credits_acquis: 30,
      moyenne_generale: 13.75, mention: 'Bien', justification: '[Exemple]…',
    },
  ],
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/juries/hub/stats/', () => STATS)
  apiController.setRoute('/juries/hub/sessions/', (ctx) => (
    ctx?.params?.avec_pv === '1' ? { results: [] } : SESSIONS
  ))
  apiController.setRoute('/juries/hub/membres/', () => ({ results: [] }))
  apiController.setRoute('/juries/hub/decisions/', () => DECISIONS)
}

const mount = () => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<JurysHub />, {
    authUser: me, routePattern: '*', initialEntries: ['/jurys/composition'],
  })
}

beforeEach(preparer)

describe('Hub Jurys premium', () => {
  it('affiche les sessions avec étape métier et le taux d’admission', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getAllByText('Délibération').length).toBeGreaterThanOrEqual(1))
    expect(container.textContent).toContain('Admission : 76,2 % des décisions')
    expect(container.textContent).not.toContain('DELIBERATION')
  })

  it('affiche les décisions avec moyenne et lien étudiant', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getAllByText('Délibération').length).toBeGreaterThanOrEqual(1))
    await user.click(screen.getByRole('tab', { name: /Décisions/ }))
    await waitFor(() => {
      expect(screen.getByText('13,75')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /INJS24-0009/ })).toHaveAttribute(
      'href', '/scolarite/etudiants/9',
    )
  })
})
