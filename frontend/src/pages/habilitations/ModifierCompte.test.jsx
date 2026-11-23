import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import ModifierCompte from './ModifierCompte'

const ROLES = [
  { code: 'ENSEIGNANT', libelle: 'Enseignant', domaine: 'PEDAGOGIE', niveau_defaut: 'N1',
    sensible: false, perimetre_defaut: 'NATIONAL' },
  { code: 'ADMIN_SYSTEME', libelle: 'Administrateur système', domaine: 'ADMINISTRATION',
    niveau_defaut: 'N4', sensible: true, perimetre_defaut: 'NATIONAL' },
]

const COMPTE = {
  id: 42, username: 'curp_x', statut: 'ACTIF', canal: 'WEB', role_legacy: 'ADMIN',
  personne: { id: 1, prenoms: 'Salif', nom: 'Traoré' },
  roles_actifs: [{ id: 1, role: 'ENSEIGNANT', role_libelle: 'Enseignant', niveau: 'N1',
                   sensible: false, validee: true, perimetres: [] }],
}

const DIFF_SIMPLE = {
  gagnes: ['pedagogie.cours.creer'], perdus: [], conserves: ['pedagogie.cours.voir'],
  roles_ajoutes: [], roles_retires: [], avertissements: [],
  total_actuel: 5, total_cible: 6,
}

function monter(simulateur) {
  const user = makeUser('ADMIN', { role_context: { labels: { ADMIN: 'Administrateur' } } })
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  apiController.setRoute('/habilitations/roles/', ROLES)
  apiController.setRoute('/habilitations/comptes/42/', COMPTE)
  apiController.setRoute(/simuler-modification\/$/, simulateur || (() => DIFF_SIMPLE))
  apiController.setRoute(/\/modifier\/$/, { ok: true })
  render(<ModifierCompte />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/administration/comptes/:id/modifier"
                    initialEntries={['/administration/comptes/42/modifier']}>{children}</AllProviders>
    ),
  })
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

describe('ModifierCompte — différentiel obligatoire avant validation', () => {
  it('refuse toute validation tant que le différentiel n\'a pas été calculé puis acquitté', async () => {
    monter()
    expect(await screen.findByTestId('ecran-modification')).toBeInTheDocument()
    expect(screen.getByTestId('bouton-valider')).toBeDisabled()

    fireEvent.click(screen.getByTestId('bouton-calculer'))
    expect(await screen.findByTestId('differential-panel')).toBeInTheDocument()
    const appelSimul = apiController.findCall('post', /simuler-modification\/$/)
    expect(appelSimul).toBeTruthy()

    fireEvent.change(screen.getByTestId('input-motif-modif'), { target: { value: 'Changement de fonction' } })
    expect(screen.getByTestId('bouton-valider')).toBeDisabled()
    fireEvent.click(screen.getByTestId('diff-acquittement'))
    await waitFor(() => expect(screen.getByTestId('bouton-valider')).toBeEnabled())

    fireEvent.click(screen.getByTestId('bouton-valider'))
    await waitFor(() => expect(apiMock.patch).toHaveBeenCalled())
    const [, corps] = apiController.findCall('patch', /\/modifier\/$/)
    expect(corps.differential_accepte).toBe(true)
    expect(corps.motif).toBe('Changement de fonction')
  })

  it('bloque la validation quand le seuil administrateurs est franchi', async () => {
    monter(() => ({
      gagnes: [], perdus: ['administration.comptes.gerer'], conserves: [],
      roles_ajoutes: [], roles_retires: ['ADMIN_SYSTEME'],
      avertissements: [{ code: 'SEUIL_ADMINISTRATEURS', message: 'passerait sous deux' }],
      total_actuel: 100, total_cible: 50,
    }))
    expect(await screen.findByTestId('ecran-modification')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('bouton-calculer'))
    expect(await screen.findByTestId('diff-bloque')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('input-motif-modif'), { target: { value: 'Démission actée' } })
    expect(screen.getByTestId('diff-acquittement')).toBeDisabled()
    expect(screen.getByTestId('bouton-valider')).toBeDisabled()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it('affiche le message renvoyé par l\'API quand la simulation est refusée', async () => {
    monter(() => {
      throw { response: { status: 400, data: { detail: 'Rôle inconnu dans la cible.' } } }
    })
    expect(await screen.findByTestId('ecran-modification')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('bouton-calculer'))
    expect(await screen.findByTestId('modif-erreur')).toHaveTextContent('Rôle inconnu')
  })
})
