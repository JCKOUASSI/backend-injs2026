import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import JournalHabilitations from './JournalHabilitations'
import MatricePermissions from './MatricePermissions'
import RevueHabilitations from './RevueHabilitations'
import GestionRoles from './GestionRoles'

function monter(ui, pattern, entrée) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  render(ui, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern={pattern} initialEntries={[entrée]}>{children}</AllProviders>
    ),
  })
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

describe('JournalHabilitations', () => {
  it('affiche une erreur récupérable si le chargement du journal échoue', async () => {
    apiController.setRoute(/\/journal\/integrite\/$/, { integre: true, total: 0 })
    let tentatives = 0
    apiController.setRoute(/\/habilitations\/journal\/?(\?|$)/, () => {
      tentatives += 1
      return tentatives === 1
        ? Promise.reject({ response: { data: { detail: 'Journal temporairement indisponible.' } } })
        : { count: 0, results: [] }
    })
    monter(<JournalHabilitations />, '/administration/comptes/journal', '/administration/comptes/journal')
    expect(await screen.findByTestId('journal-erreur'))
      .toHaveTextContent('Journal temporairement indisponible.')
    expect(screen.queryByText('Chargement du journal…')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText('Aucun événement.')).toBeInTheDocument()
  })

  it('rend visible l’échec de la vérification d’intégrité sans masquer le journal', async () => {
    apiController.setRoute(/\/journal\/integrite\/$/, () => Promise.reject(new Error('échec')))
    apiController.setRoute(/\/habilitations\/journal\/?(\?|$)/, { count: 0, results: [] })
    monter(<JournalHabilitations />, '/administration/comptes/journal', '/administration/comptes/journal')
    expect(await screen.findByTestId('integrite-journal-erreur'))
      .toHaveTextContent('Vérification de l’intégrité du journal impossible.')
    expect(await screen.findByText('Aucun événement.')).toBeInTheDocument()
  })

  it('indique le chaînage intègre et liste les événements', async () => {
    apiController.setRoute(/\/journal\/integrite\/$/, { integre: true, total: 3, anomalies: [] })
    apiController.setRoute(/\/habilitations\/journal\/?(\?|$)/, {
      count: 1, results: [{
        numero: 1, horodatage: '2026-09-14T09:30:00+00:00', type_libelle: 'Compte créé',
        acteur: 'admin', objet_libelle: 'curp_a', motif: 'Recrutement',
      }],
    })
    monter(<JournalHabilitations />, '/administration/comptes/journal', '/administration/comptes/journal')
    expect(await screen.findByTestId('integrite-journal')).toHaveTextContent(/Chaînage intègre/)
    expect(screen.getByText('Compte créé')).toBeInTheDocument()
  })

  it('alerte en rouge quand une anomalie de chaînage est détectée', async () => {
    apiController.setRoute(/\/journal\/integrite\/$/, { integre: false, total: 2, anomalies: ['Rupture de chaînage'] })
    apiController.setRoute(/\/habilitations\/journal\/?(\?|$)/, { count: 0, results: [] })
    monter(<JournalHabilitations />, '/administration/comptes/journal', '/administration/comptes/journal')
    expect(await screen.findByTestId('integrite-journal')).toHaveTextContent(/ANOMALIE/)
  })

  it('filtre les événements par type', async () => {
    apiController.setRoute(/\/journal\/integrite\/$/, { integre: true, total: 0 })
    apiController.setRoute(/\/habilitations\/journal\/?(\?|$)/, { count: 0, results: [] })
    monter(<JournalHabilitations />, '/administration/comptes/journal', '/administration/comptes/journal')
    await screen.findByTestId('integrite-journal')
    fireEvent.change(screen.getByLabelText("Type d'événement"), { target: { value: 'COMPTE_SUSPENDU' } })
    await waitFor(() => expect(
      apiController.findCall('get', /journal\/\?[^)]*type=COMPTE_SUSPENDU/),
    ).toBeTruthy())
  })
})

describe('MatricePermissions', () => {
  it('affiche la croisée rôle × module et exporte en CSV', async () => {
    window.URL.createObjectURL = vi.fn(() => 'blob:test')
    window.URL.revokeObjectURL = vi.fn()
    // jsdom ne sait pas naviguer sur un clic d'ancre de téléchargement.
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    apiController.setRoute(/\/matrice\/$/, {
      modules: [{ code: 'evaluations', libelle: 'Évaluations' }],
      lignes: [{
        code: 'SUPERVISEUR', libelle: 'Superviseur', domaine: 'EVALUATIONS', sensible: false,
        niveaux: { evaluations: { niveau: 'N3', origine: 'A2' } }, permissions_count: 4,
      }],
    })
    monter(<MatricePermissions />, '/administration/comptes/matrice', '/administration/comptes/matrice')
    expect(await screen.findByTestId('ecran-matrice')).toBeInTheDocument()
    expect(screen.getByText('N3')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('export-matrice'))
    expect(window.URL.createObjectURL).toHaveBeenCalled()
  })
})

describe('RevueHabilitations — consultation en U4', () => {
  it('affiche une erreur récupérable puis l’état vide après rechargement', async () => {
    let tentatives = 0
    apiController.setRoute(/\/comptes\/revue\/$/, () => {
      tentatives += 1
      return tentatives === 1
        ? Promise.reject({ response: { data: { detail: 'Revue temporairement indisponible.' } } })
        : { message: 'Consultation seule.', groupes: {} }
    })
    monter(<RevueHabilitations />, '/administration/comptes/revue', '/administration/comptes/revue')
    expect(await screen.findByTestId('revue-erreur'))
      .toHaveTextContent('Revue temporairement indisponible.')
    expect(screen.queryByText('Chargement de la revue…')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText("Aucun compte gouverné pour l'instant.")).toBeInTheDocument()
  })

  it('affiche le message de consultation seule et les groupes', async () => {
    apiController.setRoute(/\/comptes\/revue\/$/, {
      consultation_seule: true,
      message: 'La campagne signée sera disponible en U7.',
      groupes: { 'Direction pédagogique': [{ compte: 1, username: 'curp_a', prenoms: 'A', nom: 'B', statut: 'ACTIF', roles: ['ENSEIGNANT'], sensible: false }] },
    })
    monter(<RevueHabilitations />, '/administration/comptes/revue', '/administration/comptes/revue')
    expect(await screen.findByText(/U7/)).toBeInTheDocument()
    expect(screen.getByText('Direction pédagogique')).toBeInTheDocument()
  })
})

describe('GestionRoles — référentiel dérivé de l\'API', () => {
  it('filtre les rôles et ouvre la fiche avec les titulaires', async () => {
    apiController.setRoute('/habilitations/roles/', [
      { code: 'ENSEIGNANT', libelle: 'Enseignant', domaine: 'PEDAGOGIE', niveau_defaut: 'N1',
        sensible: false, canal_impose: null, disponible: true, permissions_count: 12,
        incompatible_avec: [] },
      { code: 'ARCHIVISTE', libelle: 'Archiviste', domaine: 'DIPLOMATION', niveau_defaut: 'N1',
        sensible: false, canal_impose: null, disponible: true, permissions_count: 3,
        incompatible_avec: [] },
    ])
    monter(<GestionRoles />, '/administration/comptes/roles', '/administration/comptes/roles')
    await screen.findByTestId('ecran-roles')
    fireEvent.change(screen.getByTestId('filtre-roles'), { target: { value: 'archiv' } })
    expect(screen.queryByTestId('ligne-role-ENSEIGNANT')).not.toBeInTheDocument()
    fireEvent.change(screen.getByTestId('filtre-roles'), { target: { value: '' } })
    apiController.setRoute('/habilitations/roles/ARCHIVISTE/', {
      code: 'ARCHIVISTE', libelle: 'Archiviste', description: 'Gère les archives.',
      domaine: 'DIPLOMATION', perimetre_defaut: 'NATIONAL', incompatible_avec: [],
      comptes_titulaires: [{ compte: 2, prenoms: 'Awa', nom: 'Ba', username: 'curp_b', statut: 'ACTIF' }],
    })
    fireEvent.click(await screen.findByTestId('ligne-role-ARCHIVISTE'))
    expect(await screen.findByTestId('detail-role')).toHaveTextContent('curp_b')
  })
})
