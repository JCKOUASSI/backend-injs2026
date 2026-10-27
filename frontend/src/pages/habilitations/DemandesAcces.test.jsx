/** Tests Lot C — DemandesAcces : liste, création (justification obligatoire),
 * décision avec motif obligatoire. Harnais mockApi identique aux tests IMPACT.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import DemandesAcces from './DemandesAcces'

function monter(chemin = '/administration/comptes/demandes') {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  return render(<DemandesAcces />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern={chemin}
                    initialEntries={[chemin]}>{children}</AllProviders>
    ),
  })
}

const demande = {
  id: 7, type_demande: 'ATTRIBUTION_ROLE',
  type_libelle: 'Attribution de rôle', statut: 'SOUMISE',
  statut_libelle: 'Soumise', compte_cible: 3, username_cible: 'scol1',
  role: 'SCOLARITE', permission: '', justification: 'Remplacement.',
  demandeur: 'admin5', approbateur: '', motif_decision: '',
  date_soumission: '2026-10-06T09:00:00', date_decision: null,
  date_creation: '2026-10-06T08:00:00', provisionnement: null,
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
  apiController.setRoute(/demandes\/\??.*$/, { count: 1, results: [demande] })
  apiController.setRoute(/roles\/$/, [{ code: 'SCOLARITE', id: 4 }])
  apiController.setRoute(/comptes\/\?.*$/, {
    count: 1,
    results: [{ id: 3, username: 'scol1', nom: 'Diop' }],
  })
})

describe('DemandesAcces — liste et décisions (Lot C)', () => {
  it('affiche la liste et les actions légales du statut', async () => {
    monter()
    expect(await screen.findByTestId('demandes-liste')).toBeInTheDocument()
    expect(screen.getByTestId('demande-7')).toHaveTextContent('Soumise')
    // Actions légales en SOUMISE.
    expect(screen.getByTestId('action-approuver-7')).toBeInTheDocument()
    expect(screen.getByTestId('action-refuser-7')).toBeInTheDocument()
    // Action illégale en SOUMISE : pas de bouton « soumettre ».
    expect(screen.queryByTestId('action-soumettre-7')).toBeNull()
  })

  it('exige un motif avant approbation puis poste la décision', async () => {
    monter()
    await screen.findByTestId('demandes-liste')
    await userEvent.click(screen.getByTestId('action-approuver-7'))
    expect(screen.getByTestId('demandes-message'))
      .toHaveTextContent('motif de décision est obligatoire')
    expect(apiController.findCall('post', /action\/$/)).toBeUndefined()

    await userEvent.type(screen.getByTestId('motif-decision'), 'Validé en commission')
    await userEvent.click(screen.getByTestId('action-approuver-7'))
    const appel = apiController.findCall('post', /action\/$/)
    expect(appel).toBeDefined()
    expect(appel[1]).toEqual({
      action: 'approuver', motif_decision: 'Validé en commission',
    })
  })

  it('crée une demande avec justification obligatoire', async () => {
    monter()
    await screen.findByTestId('demandes-liste')
    await userEvent.click(screen.getByTestId('ouvrir-formulaire'))
    expect(screen.getByTestId('formulaire-demande')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('creer-demande'))
    expect(screen.getByTestId('demandes-message'))
      .toHaveTextContent('justification est obligatoire')
    expect(apiController.findCall('post', /demandes\/$/)).toBeUndefined()

    await userEvent.selectOptions(screen.getByTestId('compte-cible'), '3')
    await userEvent.selectOptions(screen.getByTestId('role-demande'), '4')
    await userEvent.type(screen.getByTestId('justification-demande'),
                         'Remplacement durant congé')
    await userEvent.click(screen.getByTestId('creer-demande'))
    const appel = apiController.findCall('post', /demandes\/$/)
    expect(appel).toBeDefined()
    expect(appel[1].justification).toBe('Remplacement durant congé')
    expect(appel[1].role).toBe('4')
  })

  it('affiche l’état vide explicite', async () => {
    apiController.reset()
    apiController.setRoute(/demandes\/\??.*$/, { count: 0, results: [] })
    apiController.setRoute(/roles\/$/, [])
    apiController.setRoute(/comptes\/\?.*$/, { count: 0, results: [] })
    monter()
    expect(await screen.findByTestId('demandes-vide')).toBeInTheDocument()
  })
})
