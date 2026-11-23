import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Derogations from './Derogations'
import Delegations from './Delegations'

function monter(ui, pattern, entrée) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  apiController.setRoute(/\/habilitations\/comptes\/?(\?|$)/, {
    count: 2, results: [
      { id: 1, username: 'curp_a' }, { id: 2, username: 'curp_b' },
    ],
  })
  apiController.setRoute('/habilitations/roles/', [
    { code: 'ENSEIGNANT', libelle: 'Enseignant' },
  ])
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

describe('Derogations', () => {
  it('affiche une erreur et permet de relancer le chargement', async () => {
    let tentatives = 0
    apiController.setRoute(/\/habilitations\/derogations\/?$/, () => {
      tentatives += 1
      return tentatives === 1
        ? Promise.reject({ response: { data: { detail: 'Dérogations temporairement indisponibles.' } } })
        : { count: 0, results: [] }
    })
    monter(<Derogations />, '/administration/comptes/derogations', '/administration/comptes/derogations')
    expect(await screen.findByTestId('derogations-erreur'))
      .toHaveTextContent('Dérogations temporairement indisponibles.')
    expect(screen.queryByText(/Chargement des dérogations/)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText('Aucune dérogation.')).toBeInTheDocument()
  })

  it('affiche le résultat vide après un chargement réussi', async () => {
    apiController.setRoute(/\/habilitations\/derogations\/?$/, { count: 0, results: [] })
    monter(<Derogations />, '/administration/comptes/derogations', '/administration/comptes/derogations')
    expect(await screen.findByText('Aucune dérogation.')).toBeInTheDocument()
  })

  it('propose une dérogation d\'octroi bornée avec motif', async () => {
    monter(<Derogations />, '/administration/comptes/derogations', '/administration/comptes/derogations')
    apiController.setRoute(/\/habilitations\/derogations\/?$/, { count: 0, results: [] })
    const form = await screen.findByTestId('form-derogation')
    const selects = within(form).getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: '1' } }) // compte
    fireEvent.change(selects[1], { target: { value: 'OCTROI' } }) // sens
    fireEvent.change(within(form).getByPlaceholderText(/Code permission/), {
      target: { value: 'evaluations.note.saisir' },
    })
    fireEvent.change(form.querySelector('input[type=date]'), { target: { value: '2026-12-31' } })
    fireEvent.change(within(form).getByPlaceholderText('Motif'), {
      target: { value: 'Renfort exceptionnel jury' },
    })
    fireEvent.click(screen.getByTestId('bouton-creer-derogation'))
    await waitFor(() => expect(
      apiController.findCall('post', '/habilitations/derogations/'),
    ).toBeTruthy())
    const [, corps] = apiController.findCall('post', '/habilitations/derogations/')
    expect(corps).toMatchObject({
      compte: 1, permission: 'evaluations.note.saisir', sens: 'OCTROI',
      date_fin: '2026-12-31',
    })
  })

  it('révoque une dérogation active après saisie du motif', async () => {
    apiController.setRoute(/\/habilitations\/derogations\/?$/, {
      count: 1, results: [{
        id: 5, username: 'curp_a', permission: 'x.y.z', sens: 'OCTROI',
        date_fin: '2026-12-31', statut: 'ACTIVE', sensible: false,
      }],
    })
    monter(<Derogations />, '/administration/comptes/derogations', '/administration/comptes/derogations')
    const bouton = await screen.findByRole('button', { name: 'Révoquer' })
    fireEvent.click(bouton)
    const modale = await screen.findByRole('dialog')
    const confirmer = within(modale).getByTestId('motif-confirmation')
    fireEvent.change(within(modale).getByTestId('motif-input'), { target: { value: 'Fin de la mission' } })
    fireEvent.click(confirmer)
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    expect(apiController.findCall('post', /revoquer\/$/)[1]).toEqual({ motif: 'Fin de la mission' })
  })
})

describe('Delegations', () => {
  it('affiche une erreur et permet de relancer le chargement', async () => {
    let tentatives = 0
    apiController.setRoute(/\/habilitations\/delegations\/?(\?|$)/, () => {
      tentatives += 1
      return tentatives === 1
        ? Promise.reject({ response: { data: { detail: 'Délégations temporairement indisponibles.' } } })
        : { count: 0, results: [] }
    })
    monter(<Delegations />, '/administration/comptes/delegations', '/administration/comptes/delegations')
    expect(await screen.findByTestId('delegations-erreur'))
      .toHaveTextContent('Délégations temporairement indisponibles.')
    expect(screen.queryByText(/Chargement des délégations/)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByText('Aucune délégation.')).toBeInTheDocument()
  })

  it('affiche le résultat vide après un chargement réussi', async () => {
    apiController.setRoute(/\/habilitations\/delegations\/?(\?|$)/, { count: 0, results: [] })
    monter(<Delegations />, '/administration/comptes/delegations', '/administration/comptes/delegations')
    expect(await screen.findByText('Aucune délégation.')).toBeInTheDocument()
  })

  it('refuse une délégation de soi à soi avant l\'appel API', async () => {
    monter(<Delegations />, '/administration/comptes/delegations', '/administration/comptes/delegations')
    apiController.setRoute(/\/habilitations\/delegations\/?(\?|$)/, { count: 0, results: [] })
    const form = await screen.findByTestId('form-delegation')
    const selects = within(form).getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: '1' } })
    fireEvent.change(selects[1], { target: { value: '1' } })
    const inputs = form.querySelectorAll('input')
    fireEvent.change(inputs[0], { target: { value: '2026-12-31' } })
    fireEvent.change(inputs[1], { target: { value: 'Absence pour formation' } })
    fireEvent.click(screen.getByTestId('bouton-creer-delegation'))
    expect(apiController.findCall('post', /\/habilitations\/delegations\/$/)).toBeFalsy()
  })

  it('propose une délégation entre deux comptes distincts', async () => {
    monter(<Delegations />, '/administration/comptes/delegations', '/administration/comptes/delegations')
    apiController.setRoute(/\/habilitations\/delegations\/?(\?|$)/, { count: 0, results: [] })
    const form = await screen.findByTestId('form-delegation')
    const selects = within(form).getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: '1' } })
    fireEvent.change(selects[1], { target: { value: '2' } })
    const inputs = form.querySelectorAll('input')
    fireEvent.change(inputs[0], { target: { value: '2026-12-31' } })
    fireEvent.change(inputs[1], { target: { value: 'Congé maternité' } })
    fireEvent.click(screen.getByTestId('bouton-creer-delegation'))
    await waitFor(() => expect(
      apiController.findCall('post', /\/habilitations\/delegations\/$/),
    ).toBeTruthy())
    const [, corps] = apiController.findCall('post', /\/habilitations\/delegations\/$/)
    expect(corps).toMatchObject({ delegant: 1, delegataire: 2, date_fin: '2026-12-31' })
  })
})
