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
import CoursLmd from './CoursLmd'

const LIGNES = [{
  id: 12, annee: '2026-2027', ref_formation: 3, cycle: 'LICENCE ADMINISTRATION',
  parcours: '', niveau: 'Licence 1', semestre: 'S1', ue: 'Fondamentaux',
  ecue: 'ECUE1.1.1', ecue_intitule: 'Droit public', credits: 6,
  type_enseignement: 'CM', volume_horaire: 20, groupe: 7, groupe_nom: 'L1-G1',
  effectif: 22, capacite_max: 25, enseignant: 'Traoré Awa',
  dates: { debut: '2026-10-05', fin: '2027-02-01' }, statut: 'PLANIFIEE',
  nb_seances_planifiees: 10, nb_seances_realisees: 4,
  planning: [{ id: 41, jour: 'Mardi', horaire: '08:00–10:00', salle: 'Amphi 2',
               semaines: 'S1–S10', nature: 'Cours magistral' }],
}, {
  id: 13, annee: '2026-2027', ref_formation: null, cycle: '', parcours: '',
  niveau: 'Licence 1', semestre: 'S1', ue: 'Fondamentaux', ecue: 'ECUE1.1.2',
  ecue_intitule: 'Économie du sport', credits: 4, type_enseignement: 'TD',
  volume_horaire: 12, groupe: null, groupe_nom: '', effectif: null, capacite_max: null,
  enseignant: '', dates: { debut: null, fin: null }, statut: 'PROPOSEE',
  nb_seances_planifiees: 0, nb_seances_realisees: 0, planning: [],
}]

const REPONSE = { total: 2, resultats: LIGNES }

function rendre() {
  const user = makeUser('ENCADRANT')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user} initialEntries={['/cours']}>
      <CoursLmd />
    </AllProviders>,
  )
}

describe('Écran Cours (LMD) — lot B', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute('/scolarite/pedagogie/cours/', REPONSE)
  })

  it('liste les enseignements avec cycle, effectif et progression', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('ECUE1.1.1')).toBeInTheDocument())
    expect(screen.getByText('Droit public')).toBeInTheDocument()
    expect(screen.getByText(/4\/10/)).toBeInTheDocument()
    expect(screen.getByText('22')).toBeInTheDocument()
    // La ligne sans cycle l'affiche explicitement.
    expect(screen.getByText(/cycle non rattaché/)).toBeInTheDocument()
    expect(screen.getByText(/1 sans planning/)).toBeInTheDocument()
  })

  it('Ouvre le détail avec les séances et le lien présences', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('ECUE1.1.1')).toBeInTheDocument())
    await userEvent.click(screen.getByText('ECUE1.1.1').closest('tr'))
    const entete = await screen.findByText(/Détail —/)
    expect(entete).toBeInTheDocument()
    expect(screen.getAllByText(/Amphi 2/).length).toBeGreaterThanOrEqual(2)
    const lien = screen.getByRole('link', { name: /Présences/ })
    expect(lien).toHaveAttribute('href', '/edt/presences?seance=41')
  })

  it('filtre type enseignant envoyé en requête', async () => {
    rendre()
    await waitFor(() => expect(apiMock.get).toHaveBeenCalled())
    await userEvent.selectOptions(screen.getByDisplayValue('Tous types'), 'TD')
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith(
      expect.stringContaining('type_enseignement=TD'),
    ))
  })
})
