/**
 * Hub Personnel premium : panorama RH, agents au format métier (contrat
 * en badge, fonction actuelle dérivée des affectations) et navigation.
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
import PersonnelHub from '@/pages/personnel/PersonnelHub'

const STATS = {
  agents: 24, agents_actifs: 22,
  par_contrat: { FONCTIONNAIRE: 9, CONTRAT: 9, VACATAIRE: 6 },
  services: 14, fonctions: 28, indisponibilites_en_cours: 2, documents: 20,
}

const AGENTS = {
  results: [
    {
      id: 1, matricule: 'EX-AGT-001', nom: 'DIABY', prenom: 'Aïcha',
      email: 'agent01@exemple.injs.ci',
      type_contrat: 'FONCTIONNAIRE', type_contrat_display: 'Fonctionnaire',
      statut: 'ACTIF', statut_display: 'Actif',
      date_entree: '2020-09-01', date_sortie: null,
      affectations: [
        { fonction: 'Chef du service des examens', service: 'Service des examens et concours', date_debut: '2020-09-01', date_fin: null },
      ],
    },
  ],
}

const DISPONIBILITES = {
  results: [
    {
      id: 1, agent_id: 1, agent: 'DIABY Aïcha', agent_matricule: 'EX-AGT-001',
      type_indispo: 'CONGE', type_indispo_display: 'Congé',
      motif: '[Exemple] Congé annuel',
      date_debut: '2026-10-05', date_fin: '2026-10-16',
    },
  ],
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/rh/stats/', () => STATS)
  apiController.setRoute('/rh/agents/', () => AGENTS)
  apiController.setRoute('/rh/affectations/', () => ({ results: [] }))
  apiController.setRoute('/rh/disponibilites/', () => DISPONIBILITES)
  apiController.setRoute('/rh/documents/', () => ({ results: [] }))
  apiController.setRoute('/rh/fonctions/', () => ({ results: [] }))
  apiController.setRoute('/rh/services/', () => ({ results: [] }))
}

const mount = () => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<PersonnelHub />, {
    authUser: me, routePattern: '*', initialEntries: ['/personnel/agents'],
  })
}

beforeEach(preparer)

describe('Hub Personnel premium', () => {
  it('affiche le panorama et les agents avec fonction actuelle', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('EX-AGT-001')).toBeInTheDocument())
    // Le prénom (sousCle) est rendu en seconde ligne : l'agent n'est plus
    // identifié par son seul nom de famille.
    expect(screen.getByText('Aïcha')).toBeInTheDocument()
    expect(container.textContent).toContain('Chef du service des examens')
    expect(container.textContent).toContain('22 agents actifs sur 24')
    expect(container.textContent).not.toContain('FONCTIONNAIRE')
    expect(screen.getByText('01/09/2020')).toBeInTheDocument()
  })

  it('bascule vers les disponibilités', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByText('EX-AGT-001')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: /Disponibilités/ }))
    await waitFor(() => {
      expect(screen.getByText('[Exemple] Congé annuel')).toBeInTheDocument()
    })
    expect(screen.getByText('16/10/2026')).toBeInTheDocument()
  })
})

describe('Hub Personnel — design premium sobre', () => {
  it('applique le thème hub-personnel et des icônes Bootstrap valides', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('EX-AGT-001')).toBeInTheDocument())
    expect(container.querySelector('.hub-personnel .cand-hero')).not.toBeNull()
    expect(container.querySelector('.hub-personnel .hub-onglet.is-active')).not.toBeNull()
    // Aucun nom d'icône Lucide résiduel (ils ne produisaient aucune icône).
    expect(container.innerHTML).not.toContain('bi contactRound')
    expect(container.innerHTML).not.toContain('bi calendarOff')
  })

  it('rend l’icône de la tuile Fonctions et le libellé Indisponibilités', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('EX-AGT-001')).toBeInTheDocument())
    // 'briefcase' seul produisait « bi briefcase », classe inexistante :
    // la tuile Fonctions doit porter une vraie icône Bootstrap.
    expect(container.querySelector('.cand-kpi-icon .bi-briefcase')).not.toBeNull()
    expect(container.innerHTML).not.toContain('"bi briefcase"')
    // Terminologie alignée sur l'onglet et l'API (indisponibilités).
    expect(screen.getByText('Indisponibilités en cours')).toBeInTheDocument()
    expect(screen.queryByText('Absences en cours')).not.toBeInTheDocument()
  })
})
