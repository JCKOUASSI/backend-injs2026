/**
 * Tests du hub Stages premium : panorama, onglets par sous-module et
 * formatage métier (badges de statut, dates JJ/MM/AAAA, lien étudiant).
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
import StagesHub from '@/pages/stages/StagesHub'

const STATS = {
  conventions: 160, en_cours: 62, par_statut: { EN_COURS: 62 },
  organismes: 20, tuteurs: 33, etudiants_en_stage: 158,
  evaluations: 56, note_moyenne: 13.84, par_formation: [],
}

const CONVENTIONS = {
  results: [
    {
      id: 1, etudiant_id: 7, etudiant_nom_complet: 'Kouassi Yao',
      etudiant_matricule: 'INJS24-0007',
      organisme_nom: 'Complexe Sportif Municipal de Treichville',
      intitule: 'Stage — Encadrement d’activités physiques…',
      date_debut: '2026-10-19', date_fin: '2027-01-11',
      statut: 'EN_COURS', statut_display: 'En cours',
      ref_formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE',
      tuteur_externe: 'TRAORÉ Issa', lieu: 'Abidjan',
    },
  ],
}

const ORGANISMES = {
  results: [
    {
      id: 1, nom: 'Complexe Sportif Municipal de Treichville',
      raison_sociale: 'Gestion des équipements sportifs', ville: 'Abidjan',
      contact_nom: 'Service des stages',
      contact_email: 'stages01@exemple.injs.ci',
      contact_telephone: '+225 27 21 40 10 20', actif: true,
    },
  ],
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/stages/stats/', () => STATS)
  apiController.setRoute('/stages/conventions/', () => CONVENTIONS)
  apiController.setRoute('/stages/organismes/', () => ORGANISMES)
  apiController.setRoute('/stages/tuteurs/', () => ({ results: [] }))
  apiController.setRoute('/stages/evaluations/', () => ({ results: [] }))
}

const mount = (ongletInitial) => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<StagesHub ongletInitial={ongletInitial} />, {
    authUser: me, routePattern: '*', initialEntries: ['/stages/conventions'],
  })
}

beforeEach(preparer)

describe('Hub Stages premium', () => {
  it('affiche le panorama et les conventions formatées métier', async () => {
    const { container } = mount('conventions')
    await waitFor(() => expect(screen.getByText('160')).toBeInTheDocument())
    expect(container.textContent).toContain('13,84 /20')
    expect(screen.getByText('19/10/2026')).toBeInTheDocument()
    expect(screen.getAllByText('En cours').length).toBeGreaterThanOrEqual(2)
    expect(container.textContent).not.toContain('EN_COURS')
    expect(screen.getByRole('link', { name: /INJS24-0007/ })).toHaveAttribute(
      'href', '/scolarite/etudiants/7',
    )
  })

  it('bascule vers l’onglet organismes et charge ses données', async () => {
    const user = userEvent.setup()
    mount('conventions')
    await waitFor(() => expect(screen.getByText('160')).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: /Organismes/ }))
    await waitFor(() => {
      expect(screen.getByText('stages01@exemple.injs.ci')).toBeInTheDocument()
    })
    expect(screen.getByText('Gestion des équipements sportifs')).toBeInTheDocument()
  })

  it('ouvre directement l’onglet demandé par la route du sous-module', async () => {
    mount('organismes')
    await waitFor(() => {
      expect(screen.getByText('stages01@exemple.injs.ci')).toBeInTheDocument()
    })
  })
})
