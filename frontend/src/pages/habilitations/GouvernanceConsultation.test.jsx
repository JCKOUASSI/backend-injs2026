/** Tests « gouvernance consultable » : catalogue filtrable côté serveur,
 * matrice avec actions réelles et titulaires, accès effectifs enrichis
 * (sélecteur, attribuant, période, périmètres, modules, délégations).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import CataloguePermissions from './CataloguePermissions'
import MatricePermissions from './MatricePermissions'
import AccesEffectifs from './AccesEffectifs'

function monter(element, chemin) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  return render(element, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern={chemin}
                    initialEntries={[chemin]}>{children}</AllProviders>
    ),
  })
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

describe('CataloguePermissions — filtres serveur', () => {
  it('filtre par module côté API et affiche les rôles octroyants', async () => {
    apiController.setRoute(/\/habilitations\/permissions\/\?.*$/, (path) => {
      const moduleCorrespond = path.includes('module=scolarite')
      return {
        count: moduleCorrespond ? 1 : 2,
        results: moduleCorrespond
          ? [{
              code: 'scolarite.annee.consulter', libelle: 'Consulter une année',
              module: 'scolarite', ressource: 'annee', action: 'consulter',
              criticite: 'NORMALE', necessite_motif: false,
              total_roles: 3,
            }]
          : [{
              code: 'evaluations.note.modifier', libelle: 'Modifier une note',
              module: 'evaluations', ressource: 'note', action: 'modifier',
              criticite: 'CRITIQUE', necessite_motif: true,
              total_roles: 0,
            }],
      }
    })
    monter(<CataloguePermissions />, '/administration/comptes/permissions')
    expect(await screen.findByTestId('catalogue-ligne-evaluations.note.modifier'))
      .toBeInTheDocument()
    expect(screen.getByTestId('catalogue-roles-evaluations.note.modifier'))
      .toHaveTextContent('0')

    await userEvent.type(screen.getByTestId('catalogue-module'), 'scolarite')
    expect(await screen.findByTestId('catalogue-ligne-scolarite.annee.consulter'))
      .toBeInTheDocument()
    expect(screen.getByTestId('catalogue-roles-scolarite.annee.consulter'))
      .toHaveTextContent('3')
    const dernierAppel = apiMock.get.mock.calls.at(-1)?.[0] ?? ''
    expect(dernierAppel).toContain('module=scolarite')
  })

  it('propose le filtre de criticité', async () => {
    apiController.setRoute(/\/habilitations\/permissions\/\?.*$/, {
      count: 0, results: [],
    })
    monter(<CataloguePermissions />, '/administration/comptes/permissions')
    await screen.findByTestId('catalogue-total')
    await userEvent.selectOptions(
      screen.getByTestId('catalogue-criticite'), 'CRITIQUE',
    )
    await waitFor(() => expect(
      apiController.findCall('get', /permissions\/\?.*criticite=CRITIQUE/),
    ).toBeTruthy())
  })
})

describe('MatricePermissions — vue détaillée', () => {
  it('affiche les actions réelles et les titulaires', async () => {
    apiController.setRoute(/\/matrice\/$/, {
      modules: [{ code: 'scolarite', libelle: 'Scolarité' }],
      lignes: [{
        code: 'SCOLARITE', libelle: 'Scolarité', domaine: 'ADMINISTRATION',
        sensible: false,
        niveaux: { scolarite: { niveau: 'N3', origine: 'A2' } },
        permissions_count: 4,
        actions_par_module: { scolarite: ['consulter', 'modifier'] },
        comptes_titulaires: 2,
      }],
    })
    monter(<MatricePermissions />, '/administration/comptes/matrice')
    expect(await screen.findByTestId('ecran-matrice')).toBeInTheDocument()
    expect(screen.getByTestId('matrice-titulaires-SCOLARITE'))
      .toHaveTextContent('2')
    // Vue compacte : pas d'actions affichées.
    expect(screen.queryByTestId('matrice-actions-SCOLARITE-scolarite'))
      .toBeNull()
    await userEvent.click(screen.getByTestId('matrice-detaillee'))
    const cellule = screen.getByTestId('matrice-actions-SCOLARITE-scolarite')
    expect(cellule).toHaveTextContent('consulter')
    expect(cellule).toHaveTextContent('modifier')
  })
})

describe('AccesEffectifs — écran enrichi', () => {
  const impact = {
    type: 'utilisateur', user_id: 14, username: 'curp.agent',
    statut: 'ACTIF', total_effectives: 3,
    modules_effectifs: [
      { module: 'scolarite', module_libelle: 'Scolarité',
        permissions: ['scolarite.annee.consulter'] },
    ],
    actions_sensibles_effectives: ['evaluations.note.valider'],
    delegations_recues: [{
      id: 9, delegant: { username: 'chef.dir' },
      roles: ['SCOLARITE'], permissions: [], date_fin: '2026-12-31',
    }],
    arbre: {
      roles: [{
        code: 'SCOLARITE', libelle: 'Scolarité', sensible: false,
        niveau_effectif: 'N3',
        perimetres: [{ id: 3, type: 'SECRETARIAT', libelle: 'Secrétariat A' }],
        date_debut: '2026-09-01', date_fin: null, attribue_par: 'admin5',
        modules: [{ module: 'scolarite', module_libelle: 'Scolarité',
                    permissions: ['scolarite.annee.consulter'] }],
      }],
      derogations: [], retraits: [],
    },
  }

  it('sélectionne un compte et affiche l\'arbre enrichi', async () => {
    apiController.setRoute(/\/comptes\/\?/, {
      count: 1,
      results: [{ id: 14, user_id: 140, username: 'curp.agent', nom: 'Kone' }],
    })
    apiController.setRoute(/impact\/utilisateur\/140\//, impact)
    monter(<AccesEffectifs />, '/administration/comptes/acces-effectifs')
    expect(await screen.findByTestId('acces-effectifs-choix')).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByTestId('acces-effectifs-choix'), '140')
    expect(await screen.findByTestId('acces-effectifs-resultat')).toBeInTheDocument()
    expect(apiMock.get.mock.calls.some(([url]) => url.includes('/impact/utilisateur/140/')))
      .toBe(true)
    expect(screen.getByTestId('acces-effectifs-periode-SCOLARITE'))
      .toHaveTextContent('2026-09-01')
    expect(screen.getByTestId('acces-effectifs-attribue-par-SCOLARITE'))
      .toHaveTextContent('admin5')
    expect(screen.getByTestId('acces-effectifs-perimetres-SCOLARITE'))
      .toHaveTextContent('Secrétariat A')
    expect(screen.getByTestId('acces-effectifs-modules')).toBeInTheDocument()
    expect(screen.getByTestId('acces-effectifs-actions-sensibles'))
      .toHaveTextContent('evaluations.note.valider')
    expect(screen.getByTestId('acces-effectifs-delegations'))
      .toHaveTextContent('chef.dir')
  })

  it('affiche les retraits actifs sur un compte sans rôle', async () => {
    apiController.setRoute(/\/comptes\/\?/, { count: 1, results: [] })
    apiController.setRoute(/impact\/utilisateur\/14\//, {
      ...impact,
      arbre: { ...impact.arbre, roles: [], derogations: [],
               retraits: ['scolarite.annee.consulter'] },
      actions_sensibles_effectives: [],
      modules_effectifs: [],
      delegations_recues: [],
    })
    monter(<AccesEffectifs />, '/administration/comptes/acces-effectifs')
    await userEvent.type(screen.getByTestId('acces-effectifs-id'), '14')
    await userEvent.click(screen.getByTestId('acces-effectifs-analyser'))
    expect(await screen.findByTestId('arbre-acces')).toBeInTheDocument()
    // Avec un retrait actif, l'arbre n'est pas vide : la restriction est visible.
    expect(screen.queryByTestId('arbre-acces-vide')).toBeNull()
    expect(screen.getByText('scolarite.annee.consulter')).toBeInTheDocument()
  })
})
