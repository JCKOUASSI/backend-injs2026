import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

vi.mock('qrcode', () => ({
  default: { toCanvas: vi.fn((canvas, token, opts, cb) => cb && cb()) },
}))

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import EdtPresences from './EdtPresences'

const API = '/presences/seances-edt'

const SEANCES = [{
  id: 41, date: '2026-09-15', intitule: 'Physique appliquée', nature: 'COURS',
  salle: 'Amphi 1', groupe: 7, groupe_libelle: 'L1-G1', formation: null, formation_libelle: '',
  enseignant_nom: 'Awa Traoré', debut: '2026-09-15T08:00:00+00:00', fin: '2026-09-15T10:00:00+00:00',
  peut_gerer: true,
}]

const EMARGEMENT = {
  seance: { id: 41, date: '2026-09-15', groupe_libelle: 'L1-G1', intitule: 'Physique appliquée' },
  effectif: 2,
  presents: 1,
  lignes: [
    { participant: 11, matricule: 'MAT011', nom: 'Ba Awa', badge_entree: '2026-09-15T07:58:00Z',
      badge_sortie: null, statut_badgeage: 'EN_COURS', statut: 'PRESENT', pointage_id: 91 },
    { participant: 12, matricule: 'MAT012', nom: 'Diallo Moussa', badge_entree: null,
      badge_sortie: null, statut_badgeage: null, statut: null, pointage_id: null },
  ],
}

function routes() {
  apiController.setRoute(`${API}/du-jour/`, SEANCES)
  apiController.setRoute(`${API}/41/presences/`, EMARGEMENT)
  apiController.setRoute(`${API}/41/qr/`, { actif: false, token: null, expire_a: null })
  apiController.setRoute(`${API}/41/emargement/`, () => ({ detail: '1 ligne(s) enregistrée(s).' }))
  apiController.setRoute(`${API}/41/autoclore/`, () => ({ pointages_clotures: 1, absents_marques: 1 }))
}

function rendre() {
  const user = makeUser('ENCADRANT')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user} initialEntries={[`/edt/presences?seance=41&date=${'2026-09-15'}`]}>
      <EdtPresences />
    </AllProviders>,
  )
}

describe('Écran Présences de séance LMD (lot C)', () => {
  beforeEach(() => {
    apiController.reset()
    routes()
  })

  it('liste les séances du jour et ouvre la sélection deep-linkée', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('Physique appliquée')).toBeInTheDocument())
    expect(screen.getByText('L1-G1')).toBeInTheDocument()
    // La sélection via query string monte directement la liste d'émargement.
    await waitFor(() => expect(screen.getByText(/Liste d.émargement/)).toBeInTheDocument())
    expect(screen.getByText('Ba Awa')).toBeInTheDocument()
    expect(screen.getByText('Diallo Moussa')).toBeInTheDocument()
  })

  it('valide un émargement manuel avec motif pour les corrections', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('Diallo Moussa')).toBeInTheDocument())
    const ligne = screen.getByText('Diallo Moussa').closest('tr')
    await userEvent.selectOptions(within(ligne).getByRole('combobox'), 'PRESENT')
    await userEvent.type(screen.getByLabelText(/Motif global/), 'groupe électro absent ce matin')
    await userEvent.click(screen.getByRole('button', { name: /Valider l.émargement/ }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(
      `${API}/41/emargement/?date=2026-09-15`,
      expect.objectContaining({
        entries: [{ participant: 12, statut: 'PRESENT', motif: 'groupe électro absent ce matin' }],
      }),
    ))
  })

  it('propose la clôture automatique et affiche le bilan', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('Ba Awa')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /Clôturer/ }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(`${API}/41/autoclore/?date=2026-09-15`))
    await waitFor(() => expect(screen.getByText(/Séance clôturée : 1 pointage\(s\) refermé\(s\), 1 absent\(s\) marqué\(s\)/))
      .toBeInTheDocument())
  })

  it('ouvre le modal QR et permet la génération du jeton', async () => {
    rendre()
    await waitFor(() => expect(screen.getByRole('button', { name: /QR/ })).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /^QR$/ }))
    const titre = await screen.findByText(/QR de séance — Physique appliquée/)
    const modal = titre.closest('.modal-card')
    expect(within(modal).getByText(/Aucun QR actif/)).toBeInTheDocument()
    await userEvent.click(within(modal).getByRole('button', { name: /Ouvrir le QR/ }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(`${API}/41/qr/?date=2026-09-15`))
  })

  it('"Tous présents" pré-coche les lignes sans statut', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('Diallo Moussa')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /Tous présents/ }))
    const ligne = screen.getByText('Diallo Moussa').closest('tr')
    await waitFor(() => expect(within(ligne).getByRole('combobox')).toHaveValue('PRESENT'))
  })
})
