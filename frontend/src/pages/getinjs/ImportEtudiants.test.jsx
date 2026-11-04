import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import ImportEtudiants from './ImportEtudiants'

const ANNEES = [
  { id: 1, libelle: '2024-2025', courante: false },
  { id: 2, libelle: '2025-2026', courante: true },
]

const JOURNAL = {
  annee_academique_id: 2,
  nb_lots: 1,
  lots: [{
    fichier: 'inscrits-rentree.csv',
    empreinte: 'abcdef012345',
    lignes: 120,
    inscrits: 118,
    ignores: 2,
    formations: 2,
    groupes: 8,
    vagues: 1,
    recu_le: '2026-11-04T02:50:00Z',
  }],
}

const RAPPORT = {
  applique: true,
  fichier: 'inscrits-rentree.csv',
  lignes_lues: 5,
  lignes_valides: 3,
  lignes_rejetees: 2,
  creees: 3,
  mises_a_jour: 0,
  effectif_total: 3,
  erreurs: [
    { ligne: 3, motif: 'PARCOURS_NON_RESOLU', detail: 'Groupe « L1-G9 » absent.' },
  ],
  erreurs_tronquees: 0,
  cohortes: [
    { formation: 'Licence en Journalisme', niveau: 'L1', groupe: 'L1-G1', vague: 'V1', effectif: 3 },
  ],
  motif_echec: null,
  detail: {},
}

function routes() {
  apiController.setRoute('/scolarite/ref/annees/', ANNEES)
  apiController.setRoute('/edts/lmd/import/inscrits/journal/', JOURNAL)
  apiController.setRoute('/edts/lmd/import/inscrits/analyser/', { ...RAPPORT, applique: false })
  apiController.setRoute('/edts/lmd/import/inscrits/', RAPPORT)
  apiController.setRoute('/edts/campagnes/', { id: 7, libelle: 'Génération après import' })
  apiController.setRoute('/edts/campagnes/7/donnees-pretes/', {})
  apiController.setRoute('/edts/campagnes/7/demarrer/', { campagne_id: 7, execution_id: 9 })
}

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <ImportEtudiants />
    </AllProviders>,
  )
}

describe('GET-INJS — Importer les étudiants inscrits (fenêtre dédiée)', () => {
  beforeEach(() => {
    apiController.reset()
    routes()
  })

  it('présente la fenêtre selon la maquette', async () => {
    rendre()
    expect(await screen.findByRole('heading', { name: 'Importer les étudiants inscrits' }))
      .toBeInTheDocument()
    expect(screen.getByText('Situation 2 · Fichier externe')).toBeInTheDocument()
    expect(screen.getByText('Déposez ou sélectionnez le fichier des inscrits'))
      .toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Parcourir/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Importer les inscrits/ })).toBeInTheDocument()
    expect(screen.getByLabelText('Année académique cible')).toBeInTheDocument()
    expect(screen.getByLabelText('Reconstruire le parcours')).toBeChecked()
    expect(screen.getByLabelText('Générer les EDT après import')).toBeChecked()
    expect(screen.getByLabelText('Semestre à générer (optionnel)')).toBeInTheDocument()
    expect(screen.getByText('Colonnes acceptées')).toBeInTheDocument()
    expect(screen.getByText('Situations couvertes')).toBeInTheDocument()
    expect(screen.getByText('Journal des imports')).toBeInTheDocument()
  })

  it('sélectionne l’année courante et affiche le journal réel des lots', async () => {
    rendre()
    const select = await screen.findByLabelText('Année académique cible')
    await waitFor(() => expect(select).toHaveValue('2'))
    expect(await screen.findByText('inscrits-rentree.csv')).toBeInTheDocument()
    expect(screen.getByText('118')).toBeInTheDocument()
    expect(screen.getByText('04/11/26 02:50')).toBeInTheDocument()
    expect(apiMock.get).toHaveBeenCalledWith(
      '/edts/lmd/import/inscrits/journal/', { params: { annee: '2' } })
  })

  it('importe le fichier avec l’option de reconstruction, puis enchaîne la génération', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique cible')

    const fichier = new File(['matricule;nom\nM1;Ba'], 'inscrits-rentree.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Fichier des inscrits'), fichier)
    await user.click(screen.getByRole('button', { name: /Importer les inscrits/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/edts/lmd/import/inscrits/',
        expect.any(FormData),
        { headers: { 'Content-Type': 'multipart/form-data' } },
      ),
    )
    const envoi = apiMock.post.mock.calls.find(
      ([chemin]) => chemin === '/edts/lmd/import/inscrits/')[1]
    expect(envoi.get('annee_academique_id')).toBe('2')
    expect(envoi.get('reconstruire_parcours')).toBe('true')
    expect(envoi.get('fichier')).toBe(fichier)

    // Rapport réel : compteurs et rejet motivé affichés.
    expect(await screen.findByText('PARCOURS_NON_RESOLU')).toBeInTheDocument()
    const creees = screen.getByText('créées').closest('.getinjs-compte')
    expect(within(creees).getByText('3')).toBeInTheDocument()

    // Génération enchaînée : campagne créée, préparée, démarrée en async.
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/edts/campagnes/7/demarrer/', { asynchrone: true }))
  })

  it('analyse sans écrire et sans enchaîner de génération', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique cible')

    const fichier = new File(['matricule;nom\nM1;Ba'], 'inscrits.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Fichier des inscrits'), fichier)
    await user.click(screen.getByRole('button', { name: /Analyser sans importer/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/edts/lmd/import/inscrits/analyser/',
        expect.any(FormData),
        expect.anything(),
      ),
    )
    expect(apiMock.post.mock.calls.some(([c]) => c === '/edts/campagnes/')).toBe(false)
  })

  it('refuse l’import sans fichier choisi', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique cible')
    await user.click(screen.getByRole('button', { name: /Importer les inscrits/i }))
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('télécharge le modèle CSV aux en-têtes reconnus par le moteur', async () => {
    const user = userEvent.setup()
    const clickOriginal = HTMLAnchorElement.prototype.click
    HTMLAnchorElement.prototype.click = vi.fn()
    URL.createObjectURL = vi.fn(() => 'blob:modele')
    URL.revokeObjectURL = vi.fn()

    rendre()
    await user.click(screen.getByRole('button', { name: 'Modèle CSV' }))
    expect(URL.createObjectURL).toHaveBeenCalled()
    HTMLAnchorElement.prototype.click = clickOriginal
  })
})
