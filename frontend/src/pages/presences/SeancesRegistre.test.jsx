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
import SeancesRegistre, { identifiantPermanent } from './SeancesRegistre'

const DONNEES = {
  date: '2026-09-15', genere_le: '2026-09-15T08:30:00+00:00',
  resume: {
    seances_total: 2, seances_en_cours: 1, participants_presents: 12,
    sessions_qr_ouvertes: 1, emargements_manuels: 3,
  },
  seances: [
    {
      id: 41, date: '2026-09-15', debut: '2026-09-15T08:00:00+00:00',
      fin: '2026-09-15T10:00:00+00:00', statut: 'EN_COURS', statut_libelle: 'En cours',
      intitule: 'Physique appliquée', ecue_code: 'PHY101', ecue_libelle: 'Physique appliquée',
      ue_code: 'UE-PHY1', nature_libelle: 'Cours', parcours_libelle: 'EPS',
      niveau_libelle: 'Licence 1', semestre_libelle: 'Semestre 1',
      formation_libelle: 'Licence STAPS', groupe_libelle: 'L1-G1',
      libelle: 'Awa Traoré', encadrants: ['Kouadio N’Guessan'],
      salle_libelle: 'Amphi 1', effectif_attendu: 20, session_qr_ouverte: true,
      presences: { presents: 12, source_manuelle: 2, presences_hors_perimetre: 1 },
    },
    {
      id: 42, date: '2026-09-15', debut: '2026-09-15T10:00:00+00:00',
      fin: '2026-09-15T12:00:00+00:00', statut: 'ANNULEE', statut_libelle: 'Annulée',
      intitule: 'Chimie organique', ecue_code: 'CHI110', ecue_libelle: 'Chimie organique',
      ue_code: 'UE-CHI1', nature_libelle: 'TD', groupe_libelle: null,
      libelle: null, encadrants: [], salle_libelle: 'Labo 2',
      effectif_attendu: null, session_qr_ouverte: false,
      presences: { presents: 0, source_manuelle: 0, presences_hors_perimetre: 0 },
    },
  ],
}

function preparer() {
  vi.clearAllMocks()
  apiController.reset()
  apiController.setRoute('/presences/seances-edt/supervision/', DONNEES)
}

beforeEach(preparer)

describe('SeancesRegistre — module Séances refondu', () => {
  it('affiche le registre complet : identifiant, ECUE→UE, encadrant, anomalies, statut', async () => {
    render(
      <AllProviders user={makeUser('ENSEIGNANT')}>
        <SeancesRegistre />
      </AllProviders>,
    )
    await waitFor(() => expect(screen.getByText('INJS-S-000041')).toBeTruthy())
    expect(screen.getByText(/PHY101 · Physique appliquée/)).toBeTruthy()
    expect(screen.getByText('UE-PHY1 · Cours')).toBeTruthy()
    expect(screen.getByText(/EPS · Licence 1 · Semestre 1/)).toBeTruthy()
    expect(screen.getByText('Licence STAPS')).toBeTruthy()
    expect(screen.getByText('Enc. Kouadio N’Guessan')).toBeTruthy()
    expect(screen.getByText('Annulation logique tracée dans l’EDT')).toBeTruthy()
    // Légende de l'identifiant permanent.
    expect(screen.getByText(/L’identifiant permanent/)).toBeTruthy()
    // Synthèse d'en-tête.
    expect(screen.getByText('2 séance(s)')).toBeTruthy()
  })

  it('envoie le filtre statut au serveur', async () => {
    const user = userEvent.setup()
    render(
      <AllProviders user={makeUser('ENSEIGNANT')}>
        <SeancesRegistre />
      </AllProviders>,
    )
    await waitFor(() => expect(screen.getByText('INJS-S-000041')).toBeTruthy())
    await user.selectOptions(screen.getByLabelText('Statut'), 'ANNULEE')
    await waitFor(() => {
      const appels = apiMock.get.mock.calls.map((c) => String(c[0]))
      expect(appels.some((u) => u.includes('statut=ANNULEE'))).toBe(true)
    })
  })

  it('identifiantPermanent : format INJS-S-###### stable', () => {
    expect(identifiantPermanent(7)).toBe('INJS-S-000007')
    expect(identifiantPermanent(123456)).toBe('INJS-S-123456')
  })
})
