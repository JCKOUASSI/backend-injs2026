import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import AssistantCreation from './AssistantCreation'

const ROLES = [
  {
    code: 'ENSEIGNANT', libelle: 'Enseignant', domaine: 'PEDAGOGIE',
    niveau_defaut: 'N1', sensible: false, canal_impose: null,
    perimetre_defaut: 'NATIONAL', incompatible_avec: ['RESPONSABLE_SCOLARITE'],
  },
  {
    code: 'RESPONSABLE_SCOLARITE', libelle: 'Responsable de scolarité', domaine: 'SCOLARITE',
    niveau_defaut: 'N2', sensible: true, canal_impose: null,
    perimetre_defaut: 'NATIONAL', incompatible_avec: ['ENSEIGNANT'],
  },
]

function monter() {
  const user = makeUser('ADMIN', { role_context: { labels: { ADMIN: 'Administrateur' } } })
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  apiController.setRoute('/habilitations/roles/', ROLES)
  apiController.setRoute(/\/habilitations\/personnes\//, {
    resultats: [{ id: 9, matricule: 'P-2026-009', nom: 'Touré', prenoms: 'Mariam' }],
  })
  apiController.setRoute('/habilitations/comptes/', { id: 77, username: 'curp_mtoure' })
  render(<AssistantCreation />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/administration/comptes/nouveau"
                    initialEntries={['/administration/comptes/nouveau']}>{children}</AllProviders>
    ),
  })
}

const suivant = () => screen.getByTestId('bouton-suivant')

describe('AssistantCreation — 5 étapes', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('bloque l\'étape 1 tant qu\'aucune personne n\'est identifiée', async () => {
    monter()
    expect(await screen.findByTestId('etape-personne')).toBeInTheDocument()
    expect(suivant()).toBeDisabled()
    fireEvent.change(screen.getByTestId('input-nom'), { target: { value: 'Koné' } })
    expect(suivant()).toBeEnabled()
  })

  it('propose de rattacher une personne déjà connue (anti-doublon)', async () => {
    monter()
    fireEvent.change(await screen.findByTestId('recherche-personne'), { target: { value: 'Toure' } })
    expect(await screen.findByTestId('resultats-personne')).toBeInTheDocument()
    fireEvent.click(within(screen.getByTestId('resultats-personne')).getByRole('button'))
    expect(await screen.findByTestId('personne-trouvee')).toBeInTheDocument()
    expect(suivant()).toBeEnabled()
  })

  it('exige identifiant, mot de passe robuste et rôle d\'accès à l\'étape 2', async () => {
    monter()
    fireEvent.change(await screen.findByTestId('input-nom'), { target: { value: 'Koné' } })
    fireEvent.click(suivant())
    expect(await screen.findByTestId('etape-compte')).toBeInTheDocument()
    expect(suivant()).toBeDisabled()
    fireEvent.change(screen.getByTestId('input-username'), { target: { value: 'curp_kone' } })
    expect(suivant()).toBeDisabled()
    fireEvent.change(screen.getByTestId('input-mdp'), { target: { value: 'Essai#2026' } })
    expect(suivant()).toBeDisabled()
    fireEvent.change(screen.getByTestId('select-role-legacy'), { target: { value: 'ADMIN' } })
    expect(suivant()).toBeEnabled()
  })

  it('refuse le cumul de rôles incompatibles (séparation des tâches)', async () => {
    monter()
    fireEvent.change(await screen.findByTestId('input-nom'), { target: { value: 'X' } })
    fireEvent.click(suivant())
    fireEvent.change(await screen.findByTestId('input-username'), { target: { value: 'u1' } })
    fireEvent.change(screen.getByTestId('input-mdp'), { target: { value: 'secret123' } })
    fireEvent.change(screen.getByTestId('select-role-legacy'), { target: { value: 'ADMIN' } })
    fireEvent.click(suivant())
    expect(await screen.findByTestId('etape-roles')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('role-ENSEIGNANT'))
    fireEvent.click(screen.getByTestId('role-RESPONSABLE_SCOLARITE'))
    expect(screen.getByTestId('incompatibilite')).toBeInTheDocument()
    expect(suivant()).toBeDisabled()
  })

  it('exige la seconde signature pour un rôle sensible puis un motif', async () => {
    monter()
    fireEvent.change(await screen.findByTestId('input-nom'), { target: { value: 'Y' } })
    fireEvent.click(suivant())
    fireEvent.change(await screen.findByTestId('input-username'), { target: { value: 'u2' } })
    fireEvent.change(screen.getByTestId('input-mdp'), { target: { value: 'secret123' } })
    fireEvent.change(screen.getByTestId('select-role-legacy'), { target: { value: 'ADMIN' } })
    fireEvent.click(suivant())
    await screen.findByTestId('etape-roles')
    fireEvent.click(screen.getByTestId('role-RESPONSABLE_SCOLARITE'))
    // Tant que la seconde signature n'est pas cochée, l'étape est bloquée.
    fireEvent.click(suivant())
    expect(screen.queryByTestId('etape-perimetres')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('signature-RESPONSABLE_SCOLARITE'))
    fireEvent.click(suivant())
    expect(await screen.findByTestId('etape-perimetres')).toBeInTheDocument()
    // Le motif reste obligatoire (8 caractères minimum).
    expect(suivant()).toBeDisabled()
    fireEvent.change(screen.getByTestId('input-motif'), { target: { value: 'Affectation nouvelle' } })
    await waitFor(() => expect(suivant()).toBeEnabled())
  })

  it('crée le compte à l\'étape récapitulatif avec le motif et les rôles', async () => {
    monter()
    fireEvent.change(await screen.findByTestId('input-nom'), { target: { value: 'Zadi' } })
    fireEvent.click(suivant())
    fireEvent.change(await screen.findByTestId('input-username'), { target: { value: 'curp_zadi' } })
    fireEvent.change(screen.getByTestId('input-mdp'), { target: { value: 'secret123' } })
    fireEvent.change(screen.getByTestId('select-role-legacy'), { target: { value: 'ADMIN' } })
    fireEvent.click(suivant())
    await screen.findByTestId('etape-roles')
    fireEvent.click(screen.getByTestId('role-ENSEIGNANT'))
    fireEvent.click(suivant())
    fireEvent.change(await screen.findByTestId('input-motif'), { target: { value: 'Recrutement à la pédagogie' } })
    fireEvent.click(suivant())
    expect(await screen.findByTestId('etape-recap')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('bouton-creer'))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    const appel = apiController.findCall('post', '/habilitations/comptes/')
    expect(appel).toBeTruthy()
    const corps = appel[1]
    expect(corps.motif).toBe('Recrutement à la pédagogie')
    expect(corps.identifiants.username).toBe('curp_zadi')
    expect(corps.roles[0].role).toBe('ENSEIGNANT')
  })
})
