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
    heure_debut: '08:00',
    heure_fin: '10:00',
    enseignant: 'Kouadio Jean',
    type_seance: 'CM',
  },
}

function monter() {
  return render(
    <AllProviders>
      <GetInjsApp />
    </AllProviders>,
  )
}

describe('GET INJS APP — accueil du module', () => {
  beforeEach(() => {
    apiController.reset()
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
  })

  it('présente le module, ses compteurs réels et ses fonctionnalités', async () => {
    monter()
    expect(await screen.findByTestId('get-injs-app')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'GET INJS APP' })).toBeInTheDocument()
    // Compteurs réels branchés sur les API du module.
    expect(await screen.findByTestId('kpi-emplois')).toHaveTextContent('2')
    expect(screen.getByTestId('kpi-emplois-publies')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-seances-publiees')).toHaveTextContent('1')
    expect(screen.getByTestId('kpi-evenements')).toHaveTextContent('3')
    expect(screen.getByTestId('etat-api')).toHaveTextContent(/opérationnels/)
    // Fonctionnalités du module, reliées aux écrans existants.
    expect(screen.getByRole('link', { name: /Génération annuelle & import/ }))
      .toHaveAttribute('href', '/edt/generation-annuelle')
    expect(screen.getByRole('link', { name: /Campagnes de génération/ }))
      .toHaveAttribute('href', '/edt/campagnes')
    expect(screen.getByRole('link', { name: /Présences de séance/ }))
      .toHaveAttribute('href', '/edt/presences')
  })

  it('affiche la vue d’ensemble dynamique des séances publiées', async () => {
    monter()
    // Graphiques calculés des séances réelles chargées (jour, nature, volume).
    expect(await screen.findByTestId('vue-ensemble')).toBeInTheDocument()
    expect(screen.getByText('Séances par jour de semaine')).toBeInTheDocument()
    expect(screen.getByText('Séances par nature d’enseignement')).toBeInTheDocument()
    expect(screen.getByText('Lundi')).toBeInTheDocument()
    expect(screen.getByText('CM')).toBeInTheDocument()
    expect(screen.getByText('2 h')).toBeInTheDocument()
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
    await screen.findByTestId('kpi-emplois')
    await userEvent.click(screen.getByTestId('telecharger-conception'))
    await waitFor(() => {
      expect(apiMock.getBlob).toHaveBeenCalledWith('/edts/lmd/conception/')
    })
  })

  it('affiche un état vide honnête sans séance publiée', async () => {
    // setRoute conserve le premier match : on repose tout le périmètre.
    apiController.reset()
    apiController.setRoute('/edts/emplois/', [])
    apiController.setRoute('/edts/interop/seances-publiees/', {
      count: 0, page: 1, page_size: 100, results: [],
    })
    apiController.setRoute('/edts/interop/evenements/', { count: 0, results: [] })
    apiController.setRoute('/edts/conflits/', [])
    apiController.setRoute('/health/', { status: 'ok', database: 'ok' })
    monter()
    expect(await screen.findByText(/Aucune séance publiée pour le moment/))
      .toBeInTheDocument()
    expect(screen.getByTestId('kpi-seances-publiees')).toHaveTextContent('0')
  })
})
