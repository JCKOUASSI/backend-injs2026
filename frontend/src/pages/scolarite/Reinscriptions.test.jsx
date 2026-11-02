/**
 * Tests de la page dédiée « Réinscriptions & transferts » : panorama réel
 * (total serveur, jamais 500 tronqué), pagination, filtres par type de flux,
 * dates JJ/MM/AAAA sans heure et réinscription d'un étudiant existant.
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

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Reinscriptions from '@/pages/scolarite/Reinscriptions'

const STATS = {
  annee_academique: '2026-2027',
  total_inscriptions: 3527,
  total_flux: 1867,
  taux_continuite: 53.0,
  par_type: {
    PREMIERE: 1660, REINSCRIPTION: 1798, REDOUBLEMENT: 66,
    TRANSFERT: 1, REORIENTATION: 1, REPRISE: 1,
  },
  par_niveau: { L2: 774, L3: 633, M2: 460 },
  par_statut: { VALIDEE: 1862 },
}

const FLUX = {
  id: 1, etudiant_id: 7, matricule: 'INJS25-0007', etudiant: 'Kouassi Yao',
  type_inscription: 'REINSCRIPTION', type_inscription_libelle: 'Réinscription',
  ref_formation: 'LICENCE STAPS', niveau: 'L2',
  annee_academique: '2026-2027',
  statut: 'VALIDEE', statut_libelle: 'Validée',
  date_inscription: '2026-09-25',
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/scolarite/annee-courante/', () => ({
    annee: { id: 2, libelle: '2026-2027' },
  }))
  apiController.setRoute('/scolarite/ref/annees/', () => [{ id: 2, libelle: '2026-2027' }])
  apiController.setRoute('/scolarite/ref/formations/', () => [{ id: 3, intitule: 'LICENCE STAPS' }])
  apiController.setRoute('/scolarite/ref/niveaux/', () => [{ id: 4, code: 'L2' }])
  apiController.setRoute('/scolarite/reinscriptions/stats/', () => STATS)
  apiController.setRoute('/scolarite/reinscriptions/', () => ({
    results: [FLUX], count: 1867, total_pages: 75, page: 1, page_size: 25,
  }))
  apiController.setRoute('/scolarite/etudiants/', () => ({
    results: [{ id: 7, matricule: 'INJS25-0007', nom_complet: 'Kouassi Yao' }],
    count: 1, total_pages: 1,
  }))
}

const mount = () => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<Reinscriptions />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/reinscriptions'],
  })
}

const dernierParamsListe = () => {
  const appels = apiMock.get.mock.calls.filter(([p]) => p === '/scolarite/reinscriptions/')
  return appels.length ? appels[appels.length - 1][1]?.params : undefined
}

beforeEach(preparer)

describe('Réinscriptions & transferts — écran premium', () => {
  it('affiche le panorama réel (1 867 flux, pas 500) avec taux de continuité', async () => {
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toMatch(/1\s*867 élément/))
    expect(screen.getByText(/53 % de continuité/)).toBeInTheDocument()
    expect(container.textContent).toMatch(/1\s*798/)
    expect(container.textContent).not.toContain('500 éléments')
  })

  it('affiche le flux avec libellés métier et date JJ/MM/AAAA sans heure', async () => {
    const { container } = mount()
    await waitFor(() => expect(screen.getByText('25/09/2026')).toBeInTheDocument())
    expect(container.textContent).not.toContain('00:00')
    expect(screen.getByRole('link', { name: /Kouassi/i })).toHaveAttribute(
      'href', '/scolarite/etudiants/7',
    )
    expect(container.textContent).toContain('Validée')
  })

  it('filtre par segment de flux côté serveur et repart page 1', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByText('25/09/2026')).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /Transferts/ }))
    await waitFor(() => {
      expect(dernierParamsListe()?.type_inscription).toBe('TRANSFERT')
    })
    expect(dernierParamsListe()?.page).toBe(1)
  })

  it('pagine côté serveur avec le total exact', async () => {
    const user = userEvent.setup()
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toMatch(/sur 75/))
    await user.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => expect(dernierParamsListe()?.page).toBe(2))
    expect(dernierParamsListe()?.page_size).toBe(25)
  })

  it('réinscrit un étudiant existant via le panneau dédié', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByLabelText(/Année académique \*/)).toHaveValue('2'))
    await user.type(screen.getByLabelText(/Étudiant \*/), 'Kouado')
    const proposition = await screen.findByRole('button', { name: /Kouassi Yao/ })
    await user.click(proposition)
    await user.selectOptions(screen.getByLabelText(/Niveau d’arrivée \*/), '4')
    await user.click(screen.getByRole('button', { name: /^Réinscrire$/ }))
    await waitFor(() => {
      expect(apiController.lastBody('post')).toMatchObject({
        etudiant_id: 7, annee_academique_id: 2, niveau_id: 4,
        type_inscription: 'REINSCRIPTION', valider: false,
      })
    })
  })
})
