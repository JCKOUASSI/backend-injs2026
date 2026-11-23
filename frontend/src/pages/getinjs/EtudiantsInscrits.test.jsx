import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import EtudiantsInscrits from './EtudiantsInscrits'

const ANNEES = [
  { id: 1, libelle: '2025-2026', courante: false },
  { id: 2, libelle: '2026-2027', courante: true },
]

const LIGNE_BASE = {
  matricule: 'INJS-2026-000001', nom: 'DIABATE', prenoms: 'Awa', sexe: 'F',
  formation_code: 'LIC-JOURN', formation: 'Licence en Journalisme',
  niveau: 'L2', groupe: 'JS-L2-G1', vague: 'VAG-3',
  statut: 'Inscrit', source: 'Base',
}
const LIGNE_IMPORT = {
  matricule: 'EXT-0007', nom: 'KOUASSI', prenoms: 'Séverin', sexe: 'M',
  formation_code: 'LIC-JOURN', formation: 'Licence en Journalisme',
  niveau: 'L2', groupe: 'JS-L2-G1', vague: 'VAG-3',
  statut: 'Inscrit', source: 'Import',
}

function page(numero, lignes, total = 30) {
  return {
    annee_academique_id: 2,
    total,
    page: numero,
    taille_page: 25,
    total_pages: total ? 2 : 0,
    formations: [{ id: 5, code: 'LIC-JOURN', intitule: 'Licence en Journalisme' }],
    niveaux: [{ id: 3, code: 'L2', ordre: 2 }],
    resultats: lignes,
  }
}

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <EtudiantsInscrits />
    </AllProviders>,
  )
}

function dernierAppelPopulation() {
  const appels = apiMock.get.mock.calls
    .filter(([chemin]) => chemin === '/edts/lmd/inscrits/')
  return appels[appels.length - 1]
}

describe('GET-INJS — Étudiants inscrits (POPULATIONS LMD)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', ANNEES)
  })

  it('présente la population fusionnée au format du module', async () => {
    apiController.setRoute(
      '/edts/lmd/inscrits/', page(1, [LIGNE_BASE, LIGNE_IMPORT]),
    )
    rendre()

    expect(await screen.findByRole('heading', { name: 'Étudiants inscrits' }))
      .toBeInTheDocument()
    expect(screen.getByText('Populations LMD')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Importer un fichier/ }))
      .toHaveAttribute('href', '/edt/import-etudiants')
    expect(screen.getByRole('link', { name: /Emplois du temps/ }))
      .toHaveAttribute('href', '/edt')

    // Indicateurs : total filtré réel, page, répartition de la page affichée.
    expect(await screen.findByText('DIABATE')).toBeInTheDocument()
    expect(screen.getByText('Étudiants filtrés')).toBeInTheDocument()
    expect(screen.getByText('30')).toBeInTheDocument()
    expect(screen.getByText('1 / 2')).toBeInTheDocument()
    expect(screen.getByText('25 par page')).toBeInTheDocument()
    expect(screen.getByText('1 / 1')).toBeInTheDocument() // Femmes / Hommes
    expect(screen.getByText('Origine import')).toBeInTheDocument()

    // Lignes : parcours complet et origine de chaque étudiant.
    expect(screen.getByText('INJS-2026-000001')).toBeInTheDocument()
    expect(screen.getByText('KOUASSI')).toBeInTheDocument()
    expect(screen.getAllByText('JS-L2-G1')).toHaveLength(2)
    expect(screen.getByText('Base')).toBeInTheDocument()
    expect(screen.getByText('Import')).toBeInTheDocument()
    expect(screen.getByText('Source : base + imports')).toBeInTheDocument()
    expect(screen.getByText('30 étudiant(s)')).toBeInTheDocument()

    // Année courante sélectionnée par défaut.
    expect(screen.getByLabelText('Année académique')).toHaveValue('2')
    expect(dernierAppelPopulation()[1].params).toMatchObject({ annee: '2', page: 1 })
  })

  it('applique recherche, formation et niveau au clic sur Filtrer', async () => {
    const user = userEvent.setup()
    apiController.setRoute(
      '/edts/lmd/inscrits/', page(1, [LIGNE_IMPORT], 1),
    )
    rendre()
    await screen.findByText('KOUASSI')

    await user.type(
      screen.getByLabelText('Recherche (matricule, nom, prénom)'), 'kouassi')
    await user.selectOptions(screen.getByLabelText('Formation'), '5')
    await user.selectOptions(screen.getByLabelText('Niveau'), '3')
    await user.click(screen.getByRole('button', { name: 'Filtrer' }))

    await waitFor(() => {
      expect(dernierAppelPopulation()[1].params).toMatchObject({
        annee: '2', page: 1, q: 'kouassi', formation: '5', niveau: '3',
      })
    })
  })

  it('pagine à 25 par page avec Précédent / Suivant', async () => {
    const user = userEvent.setup()
    let appels = 0
    apiController.setRoute('/edts/lmd/inscrits/', () => {
      appels += 1
      return appels === 1
        ? page(1, [LIGNE_BASE])
        : page(2, [{ ...LIGNE_IMPORT, matricule: 'EXT-0099', nom: 'ZZPAGE2' }])
    })
    rendre()
    expect(await screen.findByText('DIABATE')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Suivant' }))
    expect(await screen.findByText('ZZPAGE2')).toBeInTheDocument()
    expect(screen.getByText('2 / 2')).toBeInTheDocument()
    expect(dernierAppelPopulation()[1].params).toMatchObject({ page: 2 })
    expect(screen.getByRole('button', { name: 'Suivant' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: 'Précédent' }))
    await waitFor(() => {
      expect(dernierAppelPopulation()[1].params).toMatchObject({ page: 1 })
    })
  })

  it('affiche un état vide explicite sans inventer d’effectif', async () => {
    apiController.setRoute('/edts/lmd/inscrits/', page(1, [], 0))
    rendre()
    expect(await screen.findByText(
      'Aucun étudiant inscrit ne correspond à ces critères.',
    )).toBeInTheDocument()
    expect(screen.getByText('0 étudiant(s)')).toBeInTheDocument()
  })
})
