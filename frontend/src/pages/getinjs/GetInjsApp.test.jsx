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
import GetInjsApp from './GetInjsApp'

const SEANCE_PUBLIEE = {
  seance_uuid: 'd2d9dd0e-1234-4abc-8def-0123456789ab',
  statut: 'PUBLIEE',
  version: 1,
  publie_le: '2026-11-04T03:30:00Z',
  peut_ouvrir_session_presence: true,
  placement: {
    formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE',
    ue: 'EM-S1-UE03',
    ecue: 'EM-S1-UE03-EC01',
    jour: 'LUNDI',
    semestre: 'S1',
    heure_debut: '08:00',
    heure_fin: '10:00',
    duree_prevue_minutes: 120,
    enseignant: 'Kouadio Jean',
    type_seance: 'CM',
  },
}

const CAMPAGNE = {
  id: 2,
  libelle: 'Campagne d’exemple GET INJS APP — Rentrée 2026-2027',
  created_at: '2026-11-04T05:04:51Z',
  statut: 'PRET',
  statut_libelle: 'Prêt à générer',
  statistiques: {},
  totaux: {},
}

function brancherRoutes() {
  apiController.reset()
  apiController.setRoute('/scolarite/ref/annees/', [
    { id: 1, libelle: '2026-2027', courante: true },
    { id: 2, libelle: '2025-2026', courante: false },
  ])
  apiController.setRoute('/edts/emplois/', [
    { id: 1, statut: 'PUBLIE', titre: 'EDT EM Licence L1' },
    { id: 2, statut: 'BROUILLON', titre: 'EDT brouillon' },
  ])
  apiController.setRoute('/edts/interop/seances-publiees/', {
    count: 1, page: 1, page_size: 100, results: [SEANCE_PUBLIEE],
  })
  apiController.setRoute('/edts/interop/evenements/', { count: 3, results: [] })
  apiController.setRoute('/edts/conflits/', [])
  apiController.setRoute('/health/', { status: 'ok', database: 'ok' })
  apiController.setRoute('/edts/campagnes/', { count: 1, results: [CAMPAGNE] })
  apiController.setRoute('/edts/referentiel-enseignants/', [{ id: 1 }, { id: 2 }])
  apiController.setRoute('/scolarite/ref/salles/', [{ id: 1 }, { id: 2 }, { id: 3 }])
  apiController.setRoute('/edts/lmd/import/inscrits/synthese/', {
    annee_academique_id: 1, effectif_total: 70, nb_cohortes: 1,
    cohortes: [{ formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE', niveau: 'L2', effectif: 70 }],
  })
  apiController.setRoute('/edts/lmd/import/inscrits/journal/', {
    annee_academique_id: 1, nb_lots: 1,
    lots: [{ fichier: 'inscrits_exemple.xlsx', empreinte: '843114cf7a0b',
             lignes: 70, inscrits: 70, recu_le: '2026-11-04T05:02:27Z' }],
  })
}

function monter() {
  return render(
    <AllProviders>
      <GetInjsApp />
    </AllProviders>,
  )
}

describe('GET INJS APP — tableau de bord d’accueil', () => {
  beforeEach(() => { brancherRoutes() })

  it('présente l’en-tête, l’année courante et l’état des services', async () => {
    monter()
    expect(await screen.findByTestId('get-injs-app')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'GET INJS APP' })).toBeInTheDocument()
    expect(screen.getByText('Année 2026-2027')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Générer un emploi du temps/ }))
      .toHaveAttribute('href', '/edt/generation-annuelle')
    expect(screen.getByRole('link', { name: /Consulter les grilles/ }))
      .toHaveAttribute('href', '/edt')
    expect(await screen.findByTestId('etat-api')).toHaveTextContent(/opérationnels/)
  })

  it('affiche les indicateurs réels du module', async () => {
    monter()
    expect(await screen.findByTestId('kpi-etudiants')).toHaveTextContent('70')
    expect(screen.getByTestId('kpi-cohortes')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-salles')).toHaveTextContent('3')
    expect(screen.getByTestId('kpi-enseignants')).toHaveTextContent('2')
    expect(screen.getByTestId('kpi-edt-publies')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-seances-publiees')).toHaveTextContent('1')
  })

  it('calcule la charge par semestre et la population par filière', async () => {
    monter()
    expect(await screen.findByTestId('charge-semestres')).toBeInTheDocument()
    expect(screen.getByText('S1')).toBeInTheDocument()
    expect(screen.getByText('S10')).toBeInTheDocument()
    const population = await screen.findByTestId('population-filieres')
    expect(within(population).getByText('ÉDUCATION ET MOTRICITÉ — LICENCE'))
      .toBeInTheDocument()
    expect(screen.getByText('L2')).toBeInTheDocument()
  })

  it('liste les dernières générations et les 5 étapes du processus', async () => {
    monter()
    expect(await screen.findByTestId('dernieres-generations')).toBeInTheDocument()
    expect(screen.getByText(/Campagne d’exemple GET INJS APP/)).toBeInTheDocument()
    expect(screen.getByText('Prêt à générer')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Inscriptions \/ import/ }))
      .toHaveAttribute('href', '/edt/generation-annuelle')
    expect(screen.getByRole('link', { name: /Génération/ }))
      .toHaveAttribute('href', '/edt/campagnes')
  })

  it('affiche le journal des imports tracés', async () => {
    monter()
    expect(await screen.findByTestId('journal-imports')).toBeInTheDocument()
    expect(screen.getByText('inscrits_exemple.xlsx')).toBeInTheDocument()
    expect(screen.getByText('843114cf7a0b')).toBeInTheDocument()
  })

  it('liste les séances publiées prêtes pour le module Présences', async () => {
    monter()
    expect(await screen.findByText('EM-S1-UE03 · EM-S1-UE03-EC01')).toBeInTheDocument()
    expect(screen.getByText('d2d9dd0e…')).toBeInTheDocument()
    expect(screen.getByText('Ouvrable')).toBeInTheDocument()
    expect(screen.getByText(/identifiant unique permanent/)).toBeInTheDocument()
  })

  it('télécharge la conception du module via l’API', async () => {
    monter()
    await screen.findByTestId('kpi-etudiants')
    await userEvent.click(screen.getByTestId('telecharger-conception'))
    await waitFor(() => {
      expect(apiMock.getBlob).toHaveBeenCalledWith('/edts/lmd/conception/')
    })
  })

  it('affiche des états vides honnêtes sans données', async () => {
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', [
      { id: 1, libelle: '2026-2027', courante: true },
    ])
    apiController.setRoute('/edts/emplois/', [])
    apiController.setRoute('/edts/interop/seances-publiees/', {
      count: 0, page: 1, page_size: 100, results: [],
    })
    apiController.setRoute('/edts/interop/evenements/', { count: 0, results: [] })
    apiController.setRoute('/edts/conflits/', [])
    apiController.setRoute('/health/', { status: 'ok', database: 'ok' })
    apiController.setRoute('/edts/campagnes/', { count: 0, results: [] })
    apiController.setRoute('/edts/referentiel-enseignants/', [])
    apiController.setRoute('/scolarite/ref/salles/', [])
    apiController.setRoute('/edts/lmd/import/inscrits/synthese/', {
      annee_academique_id: 1, effectif_total: 0, nb_cohortes: 0, cohortes: [],
    })
    apiController.setRoute('/edts/lmd/import/inscrits/journal/', {
      annee_academique_id: 1, nb_lots: 0, lots: [],
    })
    monter()
    // État vide présent dans la carte Charge ET dans le panneau des séances.
    expect((await screen.findAllByText(/Aucune séance publiée pour le moment/)).length)
      .toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/Aucun inscrit importé pour l’année/)).toBeInTheDocument()
    expect(screen.getByText('Aucune campagne de génération pour le moment.'))
      .toBeInTheDocument()
    expect(screen.getByText('Aucun import enregistré pour cette année.'))
      .toBeInTheDocument()
    expect(screen.getByTestId('kpi-seances-publiees')).toHaveTextContent('0')
  })
})
