import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Organisation from './Organisation'

const DIRECTIONS = [{
  id: 1, code: 'DG', libelle: 'Direction Générale', description: '',
  ordre: 1, actif: true, nb_departements: 1,
}]
const DEPARTEMENTS = [{
  id: 1, code: 'DAF', libelle: 'Affaires Financières', description: '',
  direction_id: 1, direction: { id: 1, libelle: 'Direction Générale' },
  ordre: 0, actif: true, nb_services: 1, nb_comptes: 1,
}]
const SERVICES = [{
  id: 1, nom: 'Comptabilité', description: '', departement_id: 1,
  departement: { id: 1, code: 'DAF', libelle: 'Affaires Financières' },
  actif: true, nb_comptes: 0,
}]
const DETAIL_DEPARTEMENT = {
  ...DEPARTEMENTS[0],
  services: SERVICES,
  comptes: [{ id: 10, username: 'curp_a', personne: 'Awa Ba', statut: 'ACTIF' }],
}
const DETAIL_SERVICE = {
  ...SERVICES[0],
  comptes: [],
}
const COMPTES = {
  count: 2,
  results: [
    { id: 10, username: 'curp_a', email: 'a@injs.ci', statut: 'ACTIF' },
    { id: 11, username: 'curp_b', email: 'b@injs.ci', statut: 'SUSPENDU' },
  ],
}

function monter() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  apiController.setRoute('/habilitations/organisation/directions/', { results: DIRECTIONS })
  apiController.setRoute('/habilitations/organisation/departements/', { results: DEPARTEMENTS })
  apiController.setRoute('/habilitations/organisation/services/', { results: SERVICES })
  apiController.setRoute('/habilitations/organisation/departements/1/', DETAIL_DEPARTEMENT)
  apiController.setRoute('/habilitations/organisation/services/1/', DETAIL_SERVICE)
  apiController.setRoute('/habilitations/comptes/', COMPTES)
  apiController.setRoute('/habilitations/organisation/departements/1/comptes/', {
    detail: 'OK', compte_id: 11, departement_id: 1,
    comptes: [DETAIL_DEPARTEMENT.comptes[0], { id: 11, username: 'curp_b', personne: 'Bouba Ndiaye', statut: 'SUSPENDU' }],
  })
  apiController.setRoute('/habilitations/organisation/services/1/comptes/', {
    detail: 'OK', compte_id: 10, service_id: 1,
    comptes: [{ id: 10, username: 'curp_a', personne: 'Awa Ba', statut: 'ACTIF' }],
  })
  render(<Organisation />, {
    wrapper: ({ children }) => (
      <AllProviders
        authUser={user}
        routePattern="/administration/comptes/organisation"
        initialEntries={['/administration/comptes/organisation']}
      >
        {children}
      </AllProviders>
    ),
  })
}

describe('pages/habilitations/Organisation.jsx (LOT 3)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('charge les trois niveaux et affiche l’arborescence', async () => {
    monter()
    expect(await screen.findByText('Direction Générale')).toBeInTheDocument()
    expect(screen.getByText('DG')).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('onglet-departements'))
    expect(await screen.findByText('Affaires Financières')).toBeInTheDocument()
    await userEvent.click(screen.getByTestId('onglet-services'))
    expect(await screen.findByText('Comptabilité')).toBeInTheDocument()
  })

  it('crée une direction', async () => {
    monter()
    await screen.findByText('Direction Générale')

    await userEvent.type(screen.getByPlaceholderText('DG'), 'SG')
    await userEvent.type(screen.getByPlaceholderText('Direction Générale'), 'Secrétariat Général')
    await userEvent.click(screen.getByTestId('creer-direction'))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/habilitations/organisation/directions/',
        expect.objectContaining({ code: 'SG', libelle: 'Secrétariat Général' }),
      )
    )
  })

  it('affiche une erreur de création sur doublon de code', async () => {
    apiController.reset()
    const user = makeUser('ADMIN')
    apiController.setMe(user)
    apiController.setRoute('/auth/capabilities/', { capacites: {} })
    apiController.setRoute('/habilitations/organisation/directions/', { results: [] })
    apiController.setRoute('/habilitations/organisation/departements/', { results: [] })
    apiController.setRoute('/habilitations/organisation/services/', { results: [] })
    // Comme le vrai client : un 400 rejette la promesse.
    apiMock.post.mockImplementation((path, body) => {
      if (path === '/habilitations/organisation/directions/' && body?.code) {
        return Promise.reject({
          response: { status: 400, data: { detail: 'Le code « DG » existe déjà.' } },
        })
      }
      return Promise.resolve({ data: {} })
    })
    render(<Organisation />, {
      wrapper: ({ children }) => (
        <AllProviders authUser={user}
                      routePattern="/administration/comptes/organisation"
                      initialEntries={['/administration/comptes/organisation']}>
          {children}
        </AllProviders>
      ),
    })
    await waitFor(() => expect(screen.getByText('Aucune direction.')).toBeInTheDocument())
    await userEvent.type(screen.getByPlaceholderText('DG'), 'DG')
    await userEvent.type(screen.getByPlaceholderText('Direction Générale'), 'Doublon')
    await userEvent.click(screen.getByTestId('creer-direction'))
    expect(await screen.findByText(/existe déjà/i)).toBeInTheDocument()
  })

  it('ouvre le détail d’un département avec services et comptes rattachés', async () => {
    monter()
    await screen.findByText('Direction Générale')
    await userEvent.click(screen.getByTestId('onglet-departements'))
    await screen.findByText('Affaires Financières')

    await userEvent.click(screen.getByTestId('detail-departement-1'))
    const detail = await screen.findByTestId('detail-departement')
    expect(within(detail).getByText('Comptabilité')).toBeInTheDocument()
    expect(within(detail).getByText(/curp_a/)).toBeInTheDocument()
    expect(within(detail).getByTestId('rattachements-panel')).toBeInTheDocument()
  })

  it('rattache un compte à un département puis le détache', async () => {
    monter()
    await screen.findByText('Direction Générale')
    await userEvent.click(screen.getByTestId('onglet-departements'))
    await screen.findByText('Affaires Financières')
    await userEvent.click(screen.getByTestId('detail-departement-1'))
    const detail = await screen.findByTestId('detail-departement')

    await userEvent.selectOptions(within(detail).getByTestId('rattachement-select'), '11')
    await userEvent.click(within(detail).getByTestId('rattachement-ajouter'))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/habilitations/organisation/departements/1/comptes/',
        { compte_id: 11 },
      )
    )

    // Le compte détachable (curp_a) figure dans la liste.
    await userEvent.click(within(detail).getByTestId('detacher-10'))
    expect(apiMock.delete).toHaveBeenCalled()
  })

  it('rattache un compte à un service', async () => {
    monter()
    await screen.findByText('Direction Générale')
    await userEvent.click(screen.getByTestId('onglet-services'))
    await screen.findByText('Comptabilité')

    await userEvent.click(screen.getByTestId('detail-service-1'))
    const detail = await screen.findByTestId('detail-service')

    await userEvent.selectOptions(within(detail).getByTestId('rattachement-select'), '10')
    await userEvent.click(within(detail).getByTestId('rattachement-ajouter'))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/habilitations/organisation/services/1/comptes/',
        { compte_id: 10 },
      )
    )
  })

  it('modifie et désactive une direction', async () => {
    monter()
    await screen.findByText('Direction Générale')

    await userEvent.click(screen.getByTestId('modifier-1'))
    const saisie = screen.getByDisplayValue('Direction Générale')
    await userEvent.clear(saisie)
    await userEvent.type(saisie, 'Direction Générale (DGT)')
    await userEvent.click(screen.getByTestId('valider-1'))
    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith(
        '/habilitations/organisation/directions/1/',
        expect.objectContaining({ libelle: 'Direction Générale (DGT)' }),
      )
    )

    // La liste mockée est statique : on vérifie que le PATCH de désactivation est possible.
    const boutons = screen.getAllByRole('button')
    const desactiver = boutons.find((b) => b.textContent === 'Désactiver')
    await userEvent.click(desactiver)
    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith(
        '/habilitations/organisation/directions/1/',
        { actif: false },
      )
    )
  })
})
