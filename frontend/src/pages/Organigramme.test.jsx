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
import Organigramme from './Organigramme'

const BASE = '/administrations/organigramme'

const DIRECTIONS = [{
  id: 1, code: 'DG', libelle: 'Direction Générale', description: 'pilote l’établissement',
  ordre: 0, actif: true, responsable: { id: 7, nom: 'Awa Traoré' }, adjoint: null,
  telephone: '+225 27 20 00 00 00', email: 'dg@injs.ci', localisation: 'Bâtiment A, 3e étage',
  nb_departements: 1, nb_secretariats: 0, effectif: 3,
}, {
  id: 2, code: 'DAF', libelle: 'Direction Administrative et Financière', description: '',
  ordre: 1, actif: true, responsable: null, adjoint: null, telephone: '', email: '',
  localisation: '', nb_departements: 0, nb_secretariats: 0, effectif: 0,
}]
const DEPARTEMENTS = [{
  id: 4, code: 'DEP-PED', libelle: 'Département Pédagogie', description: '',
  direction: 1, direction_libelle: 'Direction Générale', ordre: 0, actif: true,
  responsable: null, adjoint: null, telephone: '', email: '', localisation: '',
  nb_services: 1, nb_secretariats: 1, effectif: 2,
}]
const SERVICES = [{
  id: 6, code: 'SCOL01', nom: 'Service Scolarité', libelle: 'Service Scolarité', description: '',
  departement: 4, departement_libelle: 'Département Pédagogie', actif: true,
  responsable: null, adjoint: null, telephone: '', email: '', localisation: '', effectif: 1,
}]
const SECRETARIATS = [{
  id: 9, numero: 'S0001', nom: 'Secrétariat Scolaire', libelle: 'Secrétariat Scolaire',
  description: '', type: 2, type_libelle: 'Scolarité', responsable: { id: 7, nom: 'Awa Traoré' },
  adjoint: null, telephone: '', email: '', localisation: '',
  direction: null, direction_libelle: '', departement: 4, departement_libelle: 'Département Pédagogie',
  actif: true, nb_participants: 12, nb_modules: 3,
}]
const ARBRE = {
  directions: [{
    ...DIRECTIONS[0],
    departements: [{ ...DEPARTEMENTS[0], services: SERVICES, secretariats: SECRETARIATS }],
    secretariats: [],
  }],
  non_rattaches: { departements: [], services: [], secretariats: [] },
}

function routes() {
  apiController.setRoute(`${BASE}/directions/`, DIRECTIONS)
  apiController.setRoute(`${BASE}/departements/`, DEPARTEMENTS)
  apiController.setRoute(`${BASE}/services/`, SERVICES)
  apiController.setRoute(`${BASE}/secretariats/`, SECRETARIATS)
  apiController.setRoute(`${BASE}/responsables/`, [{ id: 7, nom: 'Awa Traoré', role: 'ADMIN' }])
  apiController.setRoute(`${BASE}/types-secretariat/`, [{ id: 2, libelle: 'Scolarité' }])
  apiController.setRoute(`${BASE}/arbre/`, ARBRE)
}

function rendre({ role = 'ADMIN', entry = '/organisation' } = {}) {
  const user = makeUser(role)
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user} initialEntries={[entry]}>
      <Organigramme />
    </AllProviders>,
  )
}

describe('Écran Organigramme (lot A — refonte « Secrétariats »)', () => {
  beforeEach(() => {
    apiController.reset()
    routes()
  })

  it('affiche les quatre onglets et la liste des directions', async () => {
    rendre()
    for (const libelle of ['Directions', 'Départements', 'Services', 'Secrétariats']) {
      expect(screen.getByRole('button', { name: new RegExp(libelle) })).toBeInTheDocument()
    }
    await waitFor(() => expect(screen.getByText('Direction Générale')).toBeInTheDocument())
    expect(screen.getByText('Awa Traoré')).toBeInTheDocument()   // responsable
    expect(screen.getByText('Bâtiment A, 3e étage')).toBeInTheDocument() // localisation
  })

  it('bascule sur l’onglet secretariats via l’URL et montre le rattachement', async () => {
    rendre({ entry: '/organisation?onglet=secretariats' })
    await waitFor(() => expect(screen.getByText('Secrétariat Scolaire')).toBeInTheDocument())
    expect(screen.getByText('Scolarité')).toBeInTheDocument()          // type
    expect(screen.getByText('Département Pédagogie')).toBeInTheDocument() // rattachement
  })

  it('créé une unité en POSTant vers l’API organigramme avec le motif', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('Direction Générale')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /Nouvelle unité/ }))
    const modal = await screen.findByText('Nouvelle unité — directions')
    const dialog = modal.closest('.modal-card')
    await userEvent.type(within(dialog).getByLabelText(/Code/), 'DSP')
    await userEvent.type(within(dialog).getByLabelText(/Libellé/), 'Direction des Sports')
    await userEvent.type(within(dialog).getByPlaceholderText('journalisé avec la modification'), 'Nouvelle direction')
    await userEvent.click(within(dialog).getByRole('button', { name: /Enregistrer/ }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(
      `${BASE}/directions/`,
      expect.objectContaining({ code: 'DSP', libelle: 'Direction des Sports', motif: 'Nouvelle direction' }),
    ))
  })

  it('désactive (pas de suppression physique) après confirmation', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('DAF')).toBeInTheDocument())
    const bouton = within(screen.getByText('DAF').closest('tr')).getByTitle('Désactiver')
    await userEvent.click(bouton)
    await userEvent.click(await screen.findByRole('button', { name: /Confirmer/i }))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith(`${BASE}/directions/2/`))
  })

  it('greffe les sous-unités (bureau/unité/cellule) sous leur service dans l’arbre', async () => {
    // Modèle 13.4 : le service de premier niveau chapeaute le département et
    // ses sous-unités apparaissent en enfants, typées.
    const servicesArbre = [{ ...SERVICES[0], nb_sous_unites: 1, sous_unites: [{
      id: 8, code: 'BD', nom: 'Bureau des délibérations', libelle: 'Bureau des délibérations',
      type_unite: 'BUREAU', effectif: 0, sous_unites: [],
    }] }]
    // Le mock résout au premier enregistrement : on repart d'un contrôleur
    // vierge et on pose l'arbre enrichi avant les routes par défaut.
    apiController.reset()
    apiController.setRoute(`${BASE}/arbre/`, {
      directions: [{
        ...DIRECTIONS[0],
        departements: [{ ...DEPARTEMENTS[0], services: servicesArbre, secretariats: [] }],
        secretariats: [],
      }],
      non_rattaches: { departements: [], services: [], secretariats: [] },
    })
    routes()
    rendre()
    await waitFor(() => expect(screen.getByText('Direction Générale')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /Arbre/ }))
    expect(await screen.findByText('Service Scolarité')).toBeInTheDocument()
    expect(await screen.findByText(/BUREAU — Bureau des délibérations/)).toBeInTheDocument()
  })

  it('masque les boutons d’action aux non-DFRC', async () => {
    rendre({ role: 'SECRETARIAT' })
    await waitFor(() => expect(screen.getByText('Direction Générale')).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /Nouvelle unité/ })).not.toBeInTheDocument()
    expect(screen.queryByTitle('Désactiver')).not.toBeInTheDocument()
  })

  it('montre l’arbre hiérarchique (directions → départements → services)', async () => {
    rendre()
    await waitFor(() => expect(screen.getByText('Direction Générale')).toBeInTheDocument())
    await userEvent.click(screen.getByRole('button', { name: /Arbre/ }))
    await waitFor(() => expect(screen.getByText('Arbre de l’organisation')).toBeInTheDocument())
    expect(screen.getByText('Service Scolarité')).toBeInTheDocument()
    expect(screen.getByText('Secrétariat — Secrétariat Scolaire')).toBeInTheDocument()
  })
})
