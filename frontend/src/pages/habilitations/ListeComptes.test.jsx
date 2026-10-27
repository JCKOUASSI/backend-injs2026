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
import ListeComptes from './ListeComptes'

const COMPTES = {
  count: 2,
  results: [
    { id: 1, username: 'curp_a', statut: 'ACTIF', canal: 'WEB', nb_roles_sensibles: 1,
      personne: { prenoms: 'Moussa', nom: 'Diop' },
      roles_actifs: [{ id: 11, role: 'ADMIN_SYSTEME', role_libelle: 'Administrateur', sensible: true }],
      derniere_connexion: '2026-09-13T10:00:00' },
    { id: 2, username: 'curp_b', statut: 'SUSPENDU', canal: 'MOBILE', nb_roles_sensibles: 0,
      personne: { prenoms: 'Awa', nom: 'Ba' },
      roles_actifs: [{ id: 12, role: 'ENSEIGNANT', role_libelle: 'Enseignant', sensible: false }],
      derniere_connexion: null },
  ],
}

function monter() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  apiController.setRoute('/habilitations/roles/', [
    { code: 'ENSEIGNANT', libelle: 'Enseignant', domaine: 'PEDAGOGIE' },
  ])
  apiController.setRoute(/\/habilitations\/comptes\/?(\?|$)/, (path) => {
    if (path.includes('statut=SUSPENDU')) return { count: 1, results: [COMPTES.results[1]] }
    return COMPTES
  })
  render(<ListeComptes />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/administration/comptes"
                    initialEntries={['/administration/comptes']}>{children}</AllProviders>
    ),
  })
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn(() => {})
})

describe('ListeComptes', () => {
  it('affiche les comptes, leur statut et le badge sensible', async () => {
    monter()
    expect(await screen.findByTestId('table-comptes')).toBeInTheDocument()
    expect(screen.getByText('Moussa Diop')).toBeInTheDocument()
    expect(screen.getByText('curp_b')).toBeInTheDocument()
    expect(screen.getByText('Comptes gouvernés (2)')).toBeInTheDocument()
    expect(within(screen.getByTestId('table-comptes')).getAllByText(/Sensible/).length).toBeGreaterThan(0)
  })

  it('exporte la vue filtrée courante en CSV', async () => {
    monter()
    await screen.findByTestId('table-comptes')
    fireEvent.click(screen.getByTestId('export-comptes'))
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
  })

  it('répercute le filtre de statut dans l\'appel API', async () => {
    monter()
    await screen.findByTestId('table-comptes')
    fireEvent.change(screen.getByLabelText('Filtrer par statut'), { target: { value: 'SUSPENDU' } })
    await waitFor(() => expect(
      apiController.findCall('get', /comptes\/\?[^)]*statut=SUSPENDU/),
    ).toBeTruthy())
  })

  it('exige un motif avant de suspendre un compte (action tracée)', async () => {
    monter()
    await screen.findByTestId('table-comptes')
    fireEvent.click(screen.getByTestId('suspendre-curp_a'))
    const modale = await screen.findByRole('dialog')
    const confirmer = within(modale).getByTestId('motif-confirmation')
    expect(confirmer).toBeDisabled()
    fireEvent.change(within(modale).getByTestId('motif-input'), { target: { value: 'Compromission détectée' } })
    expect(confirmer).toBeEnabled()
    fireEvent.click(confirmer)
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    const appel = apiController.findCall('post', /\/statut\/$/)
    expect(appel[1]).toEqual({ transition: 'suspendre', motif: 'Compromission détectée' })
  })
})
