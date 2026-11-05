import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Dimensionnement from './Dimensionnement'

const ANNEES = [
  { id: 1, libelle: '2025-2026', courante: false },
  { id: 2, libelle: '2026-2027', courante: true },
]

const RAPPORT = {
  annee_academique_id: 2,
  capacite_cible_par_groupe: 60,
  effectif_total_a_planifier: 3716,
  promotions: [
    {
      ref_formation_id: 3, formation: 'ANDRAGOGIE — LICENCE', niveau_id: 1,
      niveau: 'L1', parcours_id: null, effectif: 130, groupes_existants: 1,
      capacite_groupes_existants: 30, groupes_necessaires: 3, deficit_groupes: 2,
    },
    {
      ref_formation_id: 4, formation: 'EPS — LICENCE', niveau_id: 1,
      niveau: 'L1', parcours_id: 7, effectif: 25, groupes_existants: 1,
      capacite_groupes_existants: 60, groupes_necessaires: 1, deficit_groupes: 0,
    },
  ],
  totaux: {
    promotions_a_planifier: 2, groupes_existants: 2, groupes_necessaires: 4,
    deficit_groupes: 2, emplois_du_temps_a_produire: 4,
    emplois_du_temps_existants: 1, seances_a_programmer: 30062,
    heures_a_programmer: 60314, salles_actives: 166, capacite_max_salle: 500,
    formateurs_enregistres: 101,
  },
  anomalies: [
    {
      type: 'PROMOTION_SANS_GROUPE', promotion: 'EPS — LICENCE — L2',
      detail: '12 inscrit(s) validé(s) sans aucun groupe pédagogique actif.',
    },
    {
      type: 'GROUPES_INSUFFISANTS', promotion: 'ANDRAGOGIE — LICENCE — L1',
      detail: '1 groupe(s) existant(s), 3 requis à 60 étudiants/groupe (déficit 2).',
    },
  ],
}

const PLAN = {
  annee_academique_id: 2,
  capacite_cible_par_groupe: 60,
  creations: [
    {
      ref_formation_id: 3, formation: 'ANDRAGOGIE — LICENCE', niveau_id: 1,
      niveau: 'L1', parcours_id: null, effectif: 130, groupes_existants: 1,
      groupes_a_creer: [
        { nom: 'L1-G2', capacite_max: 60 },
        { nom: 'L1-G3', capacite_max: 60 },
      ],
    },
  ],
  total_a_creer: 2,
}

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <Dimensionnement />
    </AllProviders>,
  )
}

describe('GET-INJS — Dimensionnement (Besoins de planification)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', ANNEES)
    apiController.setRoute('/edts/lmd/dimensionnement/', RAPPORT)
    apiController.setRoute('/edts/lmd/dimensionnement/constituer/', (path, body) => (
      body?.simulation
        ? { simulation: true, groupes_crees: [], total_crees: 0, plan: PLAN }
        : {
          simulation: false, total_crees: 2,
          groupes_crees: [
            { id: 11, nom: 'L1-G2' }, { id: 12, nom: 'L1-G3' },
          ],
          plan: PLAN,
        }
    ))
  })

  it('affiche les indicateurs dérivés, les promotions et les anomalies', async () => {
    rendre()

    expect(await screen.findByRole('heading', { name: 'Besoins de planification 2026-2027' }))
      .toBeInTheDocument()
    expect(screen.getByText('Dimensionnement GET-INJS')).toBeInTheDocument()

    // Indicateurs calculés par le moteur (format fr-FR).
    expect(await screen.findByText('Étudiants à planifier')).toBeInTheDocument()
    expect(screen.getByText('3 716')).toBeInTheDocument()
    expect(screen.getByText('EDT de groupe à produire')).toBeInTheDocument()
    expect(screen.getByText('Séances à programmer')).toBeInTheDocument()
    expect(screen.getByText('30 062')).toBeInTheDocument()

    // Promotions : effectifs, groupes et déficit explicite.
    expect(await screen.findByText('ANDRAGOGIE — LICENCE')).toBeInTheDocument()
    expect(screen.getByText('(30 places)')).toBeInTheDocument()

    // Anomalies nommées, jamais masquées.
    expect(screen.getByText('Anomalies à traiter avant génération (2)')).toBeInTheDocument()
    expect(screen.getByText('Sans groupe')).toBeInTheDocument()
    expect(screen.getByText('Groupes insuffisants')).toBeInTheDocument()
    expect(screen.getByText(/sans aucun groupe pédagogique actif/)).toBeInTheDocument()
  })

  it('recalcule avec la capacité cible saisie', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByText('ANDRAGOGIE — LICENCE')

    const champ = screen.getByLabelText('Capacité cible par groupe')
    await user.clear(champ)
    await user.type(champ, '30')
    await user.click(screen.getByRole('button', { name: 'Recalculer' }))

    const appels = apiMock.get.mock.calls
      .filter(([chemin]) => chemin === '/edts/lmd/dimensionnement/')
    expect(appels[appels.length - 1][1].params)
      .toMatchObject({ annee: '2', capacite: 30 })
  })

  it('constitue les groupes manquants après prévisualisation et confirmation', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByText('ANDRAGOGIE — LICENCE')

    // Déficit > 0 → action proposée ; la prévisualisation n'écrit rien.
    await user.click(screen.getByRole('button', { name: 'Constituer les groupes manquants' }))
    expect(await screen.findByText(/Plan de constitution — 2 groupe\(s\) à créer/))
      .toBeInTheDocument()
    expect(screen.getByText(/L1-G2/)).toBeInTheDocument()
    expect(screen.getByText(/L1-G3/)).toBeInTheDocument()
    const appelsSimulation = apiMock.post.mock.calls
      .filter(([chemin]) => chemin === '/edts/lmd/dimensionnement/constituer/')
    expect(appelsSimulation).toHaveLength(1)
    expect(appelsSimulation[0][1]).toMatchObject({ simulation: true })

    // Confirmation explicite → création, puis rapport rechargé.
    await user.click(screen.getByRole('button', { name: 'Confirmer la création' }))
    const appels = apiMock.post.mock.calls
      .filter(([chemin]) => chemin === '/edts/lmd/dimensionnement/constituer/')
    expect(appels).toHaveLength(2)
    expect(appels[1][1]).not.toHaveProperty('simulation')
    expect(await screen.findByText(/2 groupe\(s\) constitué\(s\)/)).toBeInTheDocument()
    expect(screen.queryByText(/Plan de constitution/)).not.toBeInTheDocument()
  })

  it('année sans inscription validée : état vide honnête', async () => {
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', ANNEES)
    apiController.setRoute('/edts/lmd/dimensionnement/', {
      ...RAPPORT, effectif_total_a_planifier: 0, promotions: [], anomalies: [],
      totaux: {
        ...RAPPORT.totaux, promotions_a_planifier: 0, groupes_necessaires: 0,
        deficit_groupes: 0, emplois_du_temps_a_produire: 0,
        seances_a_programmer: null, heures_a_programmer: null,
      },
    })
    rendre()

    expect(await screen.findByText(/Aucune inscription administrative validée/))
      .toBeInTheDocument()
    expect(screen.getByText(/Aucune anomalie : groupes, maquettes et salles/))
      .toBeInTheDocument()
  })
})
