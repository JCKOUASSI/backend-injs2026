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
    // Compteur du bandeau + en-tête du groupe de date.
    expect(screen.getAllByText('2 séance(s)').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/15 septembre 2026/)).toBeTruthy()
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

  it('chargement explicite de 200 séances appliqué dès l’ouverture', async () => {
    render(
      <AllProviders user={makeUser('ENSEIGNANT')}>
        <SeancesRegistre />
      </AllProviders>,
    )
    // Sans aucun clic : la première requête demande déjà limite=200
    // et l'écran affiche la pastille du chargement explicite.
    await waitFor(() => expect(
      apiController.findCall('get', /supervision\/\?.*limite=200/)).toBeTruthy())
    expect(screen.getByText('Chargement explicite : 200 séances')).toBeTruthy()
    expect(screen.getByRole('button', { name: '200 séances' })).toHaveClass('actif')
  })

  it('chargement explicite : 200 séances demandées et affichées', async () => {
    const user = userEvent.setup()
    render(
      <AllProviders user={makeUser('ENSEIGNANT')}>
        <SeancesRegistre />
      </AllProviders>,
    )
    await waitFor(() => expect(screen.getByText('INJS-S-000041')).toBeTruthy())
    await user.click(screen.getByRole('button', { name: '200 séances' }))
    await waitFor(() => expect(
      apiController.findCall('get', /supervision\/\?.*limite=200/)).toBeTruthy())
    expect(screen.getByText('Chargement explicite : 200 séances')).toBeTruthy()
    expect(screen.getByText(/Chargement explicite : 200 séances autour du/)).toBeTruthy()
    expect(screen.getByText('2 chargée(s)')).toBeTruthy()
    expect(screen.getByLabelText('Autour du')).toBeTruthy()
  })

  it('pagine par 15, regroupe par date et recherche dans la sélection', async () => {
    const user = userEvent.setup()
    apiController.reset()
    apiController.setRoute('/presences/seances-edt/supervision/', {
      date: '2026-09-15', genere_le: '2026-09-15T08:30:00+00:00',
      resume: { seances_total: 20, participants_presents: 0, sessions_qr_ouvertes: 0, emargements_manuels: 0 },
      periode: { date_reference: '2026-09-15', date_debut: '2026-09-14', date_fin: '2026-09-15', limite: 200, horizon_jours: 120, tronque: false },
      seances: Array.from({ length: 20 }, (_, i) => ({
        id: 100 + i, date: i < 17 ? '2026-09-14' : '2026-09-15',
        debut: '2026-09-15T08:00:00+00:00', fin: '2026-09-15T10:00:00+00:00',
        statut: 'TERMINEE', statut_libelle: 'Terminée',
        ecue_code: `EC${100 + i}`, ecue_libelle: `Cours ${i + 1}`, ue_code: 'UE-X',
        nature_libelle: 'Cours', groupe_libelle: 'L1-G1',
        libelle: `Enseignant ${String(i + 1).padStart(2, '0')}`, encadrants: [],
        salle_libelle: 'Amphi 1', effectif_attendu: 20, session_qr_ouverte: false,
        presences: { presents: 0, source_manuelle: 0, presences_hors_perimetre: 0 },
      })),
    })
    render(
      <AllProviders user={makeUser('ENSEIGNANT')}>
        <SeancesRegistre />
      </AllProviders>,
    )
    await waitFor(() => expect(screen.getByText('INJS-S-000100')).toBeTruthy())
    expect(screen.getByText(/20 séance\(s\) · 1 à 15 affichée\(s\)/)).toBeTruthy()
    expect(screen.getByText(/14 septembre 2026/)).toBeTruthy()
    expect(screen.getByText('Page 1 sur 2')).toBeTruthy()
    expect(screen.queryByText('INJS-S-000116')).toBeNull()

    await user.click(screen.getByRole('button', { name: /Suivant/ }))
    expect(screen.getByText('INJS-S-000116')).toBeTruthy()
    expect(screen.getByText(/15 septembre 2026/)).toBeTruthy()
    expect(screen.getByText('Page 2 sur 2')).toBeTruthy()

    // Recherche instantanée dans la sélection chargée.
    await user.type(screen.getByLabelText('Rechercher dans les séances chargées'), 'Cours 20')
    expect(screen.getByText('INJS-S-000119')).toBeTruthy()
    expect(screen.queryByText('INJS-S-000116')).toBeNull()
  })

  it('identifiantPermanent : format INJS-S-###### stable', () => {
    expect(identifiantPermanent(7)).toBe('INJS-S-000007')
    expect(identifiantPermanent(123456)).toBe('INJS-S-123456')
  })
})
