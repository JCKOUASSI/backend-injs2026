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
import CampagnesGeneration from './CampagnesGeneration'

const ANNEES = [
  { id: 1, libelle: '2024-2025', courante: false },
  { id: 2, libelle: '2025-2026', courante: true },
]

const CAMPAGNE = {
  id: 7,
  libelle: 'Génération annuelle — session 1',
  annee_academique_id: 2,
  annee_academique: '2025-2026',
  statut: 'PRET',
  statut_libelle: 'Prêt',
  semaines: [1],
  parametres: { persister: true },
  created_at: '2026-10-01T09:00:00Z',
  statistiques: {},
  anomalies: [],
  totaux: {},
  execution_courante: null,
}

const RESULTAT = {
  campagne: {
    ...CAMPAGNE,
    statut: 'TERMINE_AVEC_ANOMALIES',
    statistiques: { duree_ms: 2400, requetes_sql: 128 },
    execution_courante: { id: 3, numero: 1, statut: 'TERMINE_AVEC_ANOMALIES', duree_ms: 2400, erreur: '' },
  },
  groupes: [
    {
      groupe_id: 11, groupe: 'L1-G1', formation: 'Licence en Journalisme',
      niveau: 'L1', effectif: 1751, statut: 'GENERATION_OK',
      seances_attendues: 6, seances_placees: 6, motif_echec: null,
    },
    {
      groupe_id: 12, groupe: 'L1-G2', formation: 'Licence en Communication',
      niveau: 'L1', effectif: 2001, statut: 'NON_PLANIFIE',
      seances_attendues: 0, seances_placees: 0, motif_echec: 'AUCUN_BESOIN_PLANIFIABLE',
    },
  ],
  anomalies: [
    {
      niveau: 'BLOQUANT', nature: 'GROUPE_NON_PLANIFIE', groupe_id: 12, groupe: 'L1-G2',
      motif: 'AUCUN_BESOIN_PLANIFIABLE',
      explication: 'Aucun besoin horaire calculable pour ce groupe.',
    },
  ],
  totaux: {
    nb_groupes: 2, nb_groupes_planifies: 1, nb_groupes_complets: 1,
    seances_placees: 6, seances_non_placees: 0, etudiants_couverts: 3752,
  },
  executions: [
    { id: 3, numero: 1, statut: 'TERMINE_AVEC_ANOMALIES', duree_ms: 2400, erreur: '' },
  ],
}

function routes({ campagnes = [CAMPAGNE], demarrer } = {}) {
  apiController.setRoute('/scolarite/ref/annees/', ANNEES)
  apiController.setRoute('/edts/campagnes/', { count: campagnes.length, results: campagnes })
  apiController.setRoute('/edts/campagnes/7/resultat/', RESULTAT)
  apiController.setRoute(
    '/edts/campagnes/7/demarrer/',
    demarrer || { campagne_id: 7, execution_id: 1 },
  )
}

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <CampagnesGeneration />
    </AllProviders>,
  )
}

describe('GET-INJS — campagnes de génération', () => {
  beforeEach(() => {
    apiController.reset()
    routes()
  })

  it('affiche les campagnes réelles de l’année courante', async () => {
    rendre()
    await waitFor(() => {
      expect(screen.getByText('Génération annuelle — session 1')).toBeInTheDocument()
      expect(screen.getByText('Prêt')).toBeInTheDocument()
    })
  })

  it('n’invente aucun compteur avant la première exécution', async () => {
    rendre()
    await screen.findByText('Génération annuelle — session 1')
    // Aucun « 0 groupe / 0 séance » trompeur : tant qu'aucune exécution n'a eu
    // lieu, les compteurs du résultat ne sont pas affichés du tout.
    expect(screen.queryByText('Résultat — Génération annuelle — session 1')).not.toBeInTheDocument()
    expect(screen.queryByText('0')).not.toBeInTheDocument()
  })

  it('affiche le bilan réel : groupes, anomalies et historique', async () => {
    rendre()
    await screen.findByText('Génération annuelle — session 1')
    await userEvent.click(screen.getByText('Génération annuelle — session 1'))

    expect(await screen.findByText(/Résultat — Génération annuelle/)).toBeInTheDocument()
    expect(screen.getByText('L1-G2')).toBeInTheDocument()
    expect(screen.getByText(/Aucun besoin horaire calculable/)).toBeInTheDocument()
    expect(screen.getByText(/Exécution 1 — TERMINE_AVEC_ANOMALIES/)).toBeInTheDocument()
    // La durée et les requêtes SQL viennent des mesures réelles.
    expect(screen.getByText('2.4 s')).toBeInTheDocument()
    expect(screen.getByText('128')).toBeInTheDocument()
  })

  it('lance la génération via l’API quand la campagne est prête', async () => {
    rendre()
    await screen.findByText('Génération annuelle — session 1')
    await userEvent.click(screen.getByRole('button', { name: 'Générer' }))
    await waitFor(() => {
      expect(apiMock.post.mock.calls.some(([p]) => p === '/edts/campagnes/7/demarrer/')).toBe(true)
    })
  })

  it('affiche le refus métier renvoyé par le serveur (409) au lieu de le masquer', async () => {
    apiController.reset()
    routes({
      demarrer: () => {
        const erreur = new Error('Conflict')
        erreur.response = {
          status: 409,
          data: {
            status: 'BLOCKING',
            motif_echec: 'CAMPAGNE_DEJA_EN_COURS',
            detail: { explication: 'Une exécution est déjà en cours pour cette campagne.' },
          },
        }
        throw erreur
      },
    })
    rendre()
    await screen.findByText('Génération annuelle — session 1')
    await userEvent.click(screen.getByRole('button', { name: 'Générer' }))
    expect(
      await screen.findByText(/Une exécution est déjà en cours pour cette campagne/),
    ).toBeInTheDocument()
  })

  it('crée une campagne avec l’année sélectionnée', async () => {
    rendre()
    await waitFor(() =>
      expect(screen.getByLabelText('Année académique')).toHaveValue('2'))
    await userEvent.type(screen.getByLabelText('Libellé'), 'Campagne de mars')
    await userEvent.click(screen.getByRole('button', { name: 'Créer' }))
    await waitFor(() => expect(apiMock.post.mock.calls.some(([p]) => p === '/edts/campagnes/')).toBe(true))
  })
})
