/**
 * Hub Administration premium : panorama, courrier formaté métier et
 * onglet organigramme (responsable non désigné affiché « — »).
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
import AdministrationHub from '@/pages/administration/AdministrationHub'

const STATS = {
  courriers: 40, courriers_en_traitement: 10,
  courriers_par_sens: { ENTRANT: 20, SORTANT: 20 },
  documents: 12, documents_publies: 4, reunions: 16, reunions_a_venir: 9,
  missions: 12, missions_en_cours: 1, directions: 5, departements: 10,
  services: 14,
}

const COURRIERS = {
  results: [
    {
      id: 1, reference: 'EX-2026/CE-001',
      objet: 'Transmission de la liste des admis aux concours d’entrée',
      sens: 'ENTRANT', sens_display: 'Entrant',
      expediteur: 'Cabinet du ministère de tutelle',
      destinataire: 'Direction Générale',
      date_courrier: '2026-10-05', statut: 'EN_COURS',
      statut_display: 'En cours de traitement',
    },
  ],
}

const SERVICES = [
  {
    id: 3, code: 'SRV-ADM', libelle: 'Service des admissions et des inscriptions',
    type_unite: 'SERVICE', departement_libelle: 'Département scolarité et vie étudiante',
    responsable: null, effectif: 0, actif: true,
  },
]

function preparer() {
  apiController.reset()
  apiController.setRoute('/administrations/stats/', () => STATS)
  apiController.setRoute('/administrations/courriers/', () => COURRIERS)
  apiController.setRoute('/administrations/documents/', () => ({ results: [] }))
  apiController.setRoute('/administrations/reunions/', () => ({ results: [] }))
  apiController.setRoute('/administrations/missions/', () => ({ results: [] }))
  apiController.setRoute('/administrations/organigramme/directions/', () => [])
  apiController.setRoute('/administrations/organigramme/departements/', () => [])
  apiController.setRoute('/administrations/organigramme/services/', () => SERVICES)
}

const mount = (ongletInitial = 'courrier') => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<AdministrationHub ongletInitial={ongletInitial} />, {
    authUser: me, routePattern: '*', initialEntries: ['/administration/courrier'],
  })
}

beforeEach(preparer)

describe('Hub Administration premium', () => {
  it('affiche panorama et courrier au format métier', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('EX-2026/CE-001')).toBeInTheDocument())
    expect(screen.getByText('05/10/2026')).toBeInTheDocument()
    expect(container.textContent).toContain('En cours de traitement')
    expect(container.textContent).not.toContain('EN_COURS')
    expect(container.textContent).toContain('5 directions · 10 départements · 14 services')
  })

  it('affiche l’organigramme des services avec responsable non désigné', async () => {
    const user = userEvent.setup()
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('EX-2026/CE-001')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: /^Services/ }))
    await waitFor(() => {
      expect(screen.getByText('SRV-ADM')).toBeInTheDocument()
    })
    expect(container.textContent).toContain('Département scolarité et vie étudiante')
  })
})
