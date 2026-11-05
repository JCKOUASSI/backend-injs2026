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
import Referentiels from './Referentiels'

const ANNEES = [
  { id: 1, libelle: '2025-2026', courante: false },
  { id: 2, libelle: '2026-2027', courante: true },
]

const DONNEES = {
  annee_academique_id: 2,
  compteurs: {
    filieres: 2, formations: 8, modules: 779, groupes: 139,
    vagues: 4, salles: 166, enseignants: 101,
  },
  mentions: [
    { code: 'STAPS', nom: 'Sciences et Techniques des APS', ecole: 'ENSEPS' },
    { code: 'STASE', nom: "Sciences et Techniques de l'Animation", ecole: 'ENSEP' },
  ],
  parcours: [
    { code: 'AND', libelle: 'Andragogie', mention: 'STASE', maquette: 'publiée', groupes: 17 },
    { code: 'JOURNALI', libelle: 'Journalisme sportif', mention: 'STAPS', maquette: 'paramétrable', groupes: 3 },
  ],
  maquettes: [
    {
      id: 7, formation: 'ANDRAGOGIE — LICENCE', niveau: 'L1', version: 1,
      statut: 'ACTIVE', statut_libelle: 'Publiée', publiee: true,
      ues: 18, modules: 24, credits: 88,
    },
  ],
  infrastructure: {
    sites: 1,
    batiments: 16,
    salles: [
      { code: 'SAL-007', nom: 'Archives', batiment: 'Bibliothèque', site: 'INJS Marcory', capacite: null, type: 'Salle' },
    ],
  },
  enseignants: [
    { nom: 'Kouadio', prenom: 'Adjoua', specialite: 'Recherche, langues et TIC', grade: 'Maître-Assistant', statut: 'Titulaire' },
  ],
  groupes: [
    { nom: 'L1-G1', formation: 'ANDRAGOGIE — LICENCE', niveau: 'L1', vague: '', capacite: 35, effectif: 31 },
  ],
  vagues: [
    { code: 'VAGUE_1', libelle: 'PREMIERE VAGUE', groupes: 12 },
  ],
}

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <Referentiels />
    </AllProviders>,
  )
}

describe('GET-INJS — Référentiels (Données de référence)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', ANNEES)
    apiController.setRoute('/edts/lmd/referentiels/', DONNEES)
  })

  it('présente en-tête, compteurs et premier onglet au format de référence', async () => {
    rendre()

    expect(await screen.findByRole('heading', { name: 'Données de référence 2026-2027' }))
      .toBeInTheDocument()
    expect(screen.getByText('Référentiels INJS')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Générer depuis ces référentiels/ }))
      .toHaveAttribute('href', '/edt/generation-annuelle')
    expect(screen.getByRole('button', { name: /Voir la conception/ }))
      .toBeInTheDocument()

    // Onglet Filières & formations : mentions/écoles et parcours.
    expect(await screen.findByText('Filières (mentions)')).toBeInTheDocument()

    // Compteurs réels renvoyés par l'API.
    expect(screen.getByText('Filières')).toBeInTheDocument()
    expect(screen.getByText('779')).toBeInTheDocument()
    expect(screen.getByText('139')).toBeInTheDocument()
    expect(screen.getByText('166')).toBeInTheDocument()
    expect(screen.getByText('101')).toBeInTheDocument()
    expect(screen.getByText('Formations (parcours)')).toBeInTheDocument()
    // Mention (tableau de gauche) et filière des parcours (tableau de droite).
    expect(screen.getAllByText('STAPS').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('ENSEPS')).toBeInTheDocument()
    expect(screen.getByText('Journalisme sportif')).toBeInTheDocument()
    expect(screen.getByText('publiée')).toBeInTheDocument()
    expect(screen.getByText('paramétrable')).toBeInTheDocument()
    expect(screen.getByText('17')).toBeInTheDocument()
  })

  it('bascule entre les onglets du sous-module', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByText('Filières (mentions)')

    await user.click(screen.getByRole('tab', { name: 'Maquettes & modules' }))
    expect(await screen.findByText('ANDRAGOGIE — LICENCE')).toBeInTheDocument()
    expect(screen.getByText('Publiée')).toBeInTheDocument()
    expect(screen.getByText('24')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Bâtiments & salles' }))
    expect(await screen.findByText('Archives')).toBeInTheDocument()
    expect(screen.getByText('Bibliothèque')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Enseignants' }))
    expect(await screen.findByText('Kouadio')).toBeInTheDocument()
    expect(screen.getByText('Maître-Assistant')).toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Groupes & vagues' }))
    expect(await screen.findByText('L1-G1')).toBeInTheDocument()
    expect(screen.getByText('PREMIERE VAGUE')).toBeInTheDocument()
    expect(screen.getByText('31')).toBeInTheDocument()
  })

  it('télécharge le document de conception', async () => {
    const user = userEvent.setup()
    URL.createObjectURL = vi.fn(() => 'blob:conception')
    URL.revokeObjectURL = vi.fn()
    rendre()
    await screen.findByText('Filières (mentions)')

    await user.click(screen.getByRole('button', { name: /Voir la conception/ }))
    expect(apiMock.getBlob).toHaveBeenCalledWith('/edts/lmd/conception/')
  })

  it('recharge les référentiels quand l’année change', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByText('Filières (mentions)')

    await user.selectOptions(screen.getByLabelText('Année académique'), '1')
    const appels = apiMock.get.mock.calls
      .filter(([chemin]) => chemin === '/edts/lmd/referentiels/')
    expect(appels[appels.length - 1][1].params).toMatchObject({ annee: '1' })
  })
})
