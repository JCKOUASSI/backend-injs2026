import { beforeEach, describe, expect, it, vi } from 'vitest'
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
import Simulation from './Simulation'

const CAMPAGNE = {
  id: 41, annee_academique_id: 2, libelle: 'Simulation de test', statut: 'TERMINE',
  statut_libelle: 'Terminé', status_global: 'PARTIELLE',
  parametres: { simulation: true, simulation_acceptee: { par: 'admin' } },
}
const RESULTAT = {
  campagne: { ...CAMPAGNE, parametres: { simulation: true } },
  totaux: { seances_placees: 3, seances_attendues: 4, seances_non_placees: 1, conflits: 0 },
  sources: { nb_groupes: 1 },
  groupes: [{ groupe_id: 11, formation: 'Licence test', niveau: 'L1', groupe: 'L1-G1',
    statut: 'GENERATION_PARTIELLE', seances_placees: 3, seances_attendues: 4,
    seances_non_placees: 1, motif_echec: 'OCCURRENCES_NON_PLACEES' }],
  anomalies: [],
}

function setup() {
  apiController.reset()
  apiController.setMe(makeUser('ADMIN'))
  apiController.setRoute('/scolarite/ref/annees/', [{ id: 2, libelle: '2025-2026', courante: true }])
  apiController.setRoute('/formations/ref/formations/', [{ id: 8, intitule: 'Licence test' }])
  apiController.setRoute('/scolarite/ref/niveaux/', [{ id: 3, code: 'L1' }])
  apiController.setRoute('/scolarite/ref/groupes/', [{ id: 11, nom: 'L1-G1', niveau_code: 'L1', ref_formation_id: 8, niveau_id: 3 }])
  apiController.setRoute('/edts/campagnes/', { count: 0, results: [] })
  apiController.setRoute('/edts/simulations/', CAMPAGNE, 201)
  apiController.setRoute('/edts/campagnes/41/donnees-pretes/', {})
  apiController.setRoute('/edts/campagnes/41/demarrer/', { campagne_id: 41, execution_id: 4 })
  apiController.setRoute('/edts/campagnes/41/statut/', { id: 41, statut: 'TERMINE', en_cours: false })
  apiController.setRoute('/edts/campagnes/41/resultat/', RESULTAT)
  apiController.setRoute('/edts/simulations/41/accepter/', { ...CAMPAGNE, parametres: { ...CAMPAGNE.parametres } })
  return render(<AllProviders authUser={makeUser('ADMIN')}><Simulation /></AllProviders>)
}

describe('GET INJS — simulation non destructive', () => {
  beforeEach(() => { vi.stubGlobal('confirm', vi.fn(() => true)) })

  it('utilise les sélections réelles, affiche le bilan puis propose le transfert après acceptation', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(await screen.findByRole('checkbox', { name: 'Licence test' }))
    await user.click(screen.getByRole('checkbox', { name: 'L1' }))
    await user.click(screen.getByRole('checkbox', { name: 'L1-G1 — L1' }))
    await user.click(screen.getByRole('checkbox', { name: 'Semestre 1 (S1)' }))
    await user.click(screen.getByRole('button', { name: 'Simuler avec le moteur EDT' }))
    expect(await screen.findByRole('heading', { name: /Résultat : PARTIELLE/ })).toBeInTheDocument()
    expect(screen.getByText('75 %')).toBeInTheDocument()
    expect(screen.getByText('OCCURRENCES_NON_PLACEES')).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Pistes d’amélioration de la couverture' }))
      .toHaveTextContent(/ajouter des semaines valides/)
    expect(screen.getByText(/ne garantissent pas un optimum/)).toBeInTheDocument()
    const body = apiMock.post.mock.calls.find(([path]) => path === '/edts/simulations/')[1]
    expect(body.perimetre).toEqual({ formations: [8], niveaux: [3], groupes: [11], semestres: [1] })
    expect(body.parametres.persister).toBeUndefined()
    await user.click(screen.getByRole('button', { name: 'Accepter après revue humaine' }))
    expect(await screen.findByRole('link', { name: 'Transférer vers Génération → Manuel' }))
      .toHaveAttribute('href', '/edt/generation-annuelle?simulation_id=41')
    expect(apiMock.post).toHaveBeenCalledWith('/edts/simulations/41/accepter/', {})
  })

  it('priorise une cause de salle réelle au lieu de suggérer des semaines comme remède', async () => {
    const user = userEvent.setup()
    setup()
    apiController.replaceRoute('/edts/campagnes/41/resultat/', {
      ...RESULTAT,
      campagne: { ...RESULTAT.campagne, status_global: 'IMPOSSIBLE', statut: 'TERMINE_AVEC_ANOMALIES' },
      totaux: { seances_placees: 0, seances_attendues: 4, seances_non_placees: 4, conflits: 0 },
      groupes: [{ ...RESULTAT.groupes[0], statut: 'GENERATION_IMPOSSIBLE',
        seances_placees: 0, seances_attendues: 4, seances_non_placees: 4,
        motif_echec: 'AUCUNE_SALLE_COMPATIBLE' }],
    })
    await user.click(await screen.findByRole('checkbox', { name: 'Licence test' }))
    await user.click(screen.getByRole('checkbox', { name: 'L1' }))
    await user.click(screen.getByRole('checkbox', { name: 'L1-G1 — L1' }))
    await user.click(screen.getByRole('checkbox', { name: 'Semestre 1 (S1)' }))
    await user.click(screen.getByRole('button', { name: 'Simuler avec le moteur EDT' }))
    const pistes = await screen.findByRole('region', { name: 'Pistes d’amélioration de la couverture' })
    expect(pistes).toHaveTextContent(/Corriger d’abord les salles compatibles/)
    expect(pistes).toHaveTextContent(/C4\/C7/)
    expect(pistes).toHaveTextContent(/ne corrigera pas cette cause à lui seul/)
    expect(pistes).not.toHaveTextContent(/ajouter des semaines valides/)
  })

  it('permet de cocher les options individuellement ou de tout sélectionner', async () => {
    const user = userEvent.setup()
    setup()
    const tout = await screen.findByRole('button', { name: 'Tout sélectionner : Niveaux' })
    await user.click(tout)
    expect(screen.getByRole('checkbox', { name: 'L1' })).toBeChecked()
    expect(screen.getByRole('button', { name: 'Tout désélectionner : Niveaux' })).toBeInTheDocument()
  })

  it('refuse de simuler tant que le périmètre requis n’est pas sélectionné', async () => {
    const user = userEvent.setup()
    setup()
    await screen.findByLabelText(/Année académique/)
    await user.click(screen.getByRole('button', { name: 'Simuler avec le moteur EDT' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Sélectionnez une année, au moins une formation/)
    expect(apiMock.post).not.toHaveBeenCalledWith('/edts/simulations/', expect.anything())
  })
})
