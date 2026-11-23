/** Tests Lot B — GestionRoles : versions (capture/restauration avec motif)
 * et comparaison de deux rôles. Harnais mockApi identique aux tests IMPACT.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import GestionRoles from './GestionRoles'

function monter(chemin = '/administration/comptes/roles') {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  return render(<GestionRoles />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern={chemin}
                    initialEntries={[chemin]}>{children}</AllProviders>
    ),
  })
}

const roles = [
  { code: 'SCOLARITE', libelle: 'Scolarité', domaine: 'ADMINISTRATION',
    niveau_defaut: 'N3', sensible: false, disponible: true,
    canal_impose: '', permissions_count: 2 },
  { code: 'DIRECTION', libelle: 'Direction', domaine: 'ADMINISTRATION',
    niveau_defaut: 'N4', sensible: true, disponible: true,
    canal_impose: '', permissions_count: 5 },
]

const detailScolarite = {
  code: 'SCOLARITE', libelle: 'Scolarité',
  description: 'Coordonne les inscriptions.',
  domaine: 'ADMINISTRATION', perimetre_defaut: 'SECRETARIAT',
  incompatible_avec: [], comptes_titulaires: [],
}

const versionsVides = { role: 'SCOLARITE', total: 0, versions: [] }

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

describe('GestionRoles — versions (Lot B)', () => {
  it('affiche une erreur récupérable si le chargement du référentiel échoue', async () => {
    let tentatives = 0
    apiController.setRoute('/habilitations/roles/', () => {
      tentatives += 1
      return tentatives === 1
        ? Promise.reject({ response: { data: { detail: 'Référentiel temporairement indisponible.' } } })
        : roles
    })
    monter()
    expect(await screen.findByTestId('roles-erreur'))
      .toHaveTextContent('Référentiel temporairement indisponible.')
    expect(screen.queryByText('Chargement…')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: 'Réessayer' }))
    expect(await screen.findByTestId('ecran-roles')).toBeInTheDocument()
    expect(screen.getByTestId('ligne-role-SCOLARITE')).toBeInTheDocument()
  })

  it('affiche le référentiel et le panneau de comparaison', async () => {
    apiController.setRoute(/roles\/$/, roles)
    monter()
    expect(await screen.findByTestId('ecran-roles')).toBeInTheDocument()
    expect(screen.getByTestId('comparaison-roles')).toBeInTheDocument()
  })

  it('affiche un état vide si le référentiel ne contient aucun rôle', async () => {
    apiController.setRoute('/habilitations/roles/', [])
    monter()
    expect(await screen.findByText('Aucun rôle ne correspond au filtre.')).toBeInTheDocument()
  })

  it('exige un motif avant capture et poste la version', async () => {
    apiController.setRoute(/roles\/$/, roles)
    apiController.setRoute(/roles\/SCOLARITE\/$/, detailScolarite)
    apiController.setRoute(/roles\/SCOLARITE\/versions\/$/, versionsVides)
    monter()
    const ligne = await screen.findByTestId('ligne-role-SCOLARITE')
    await userEvent.click(ligne)
    expect(await screen.findByTestId('detail-role')).toBeInTheDocument()

    // Sans motif : pas d'appel POST, message affiché.
    await userEvent.click(screen.getByTestId('capturer-version'))
    expect(screen.getByTestId('versions-message'))
      .toHaveTextContent('motif est obligatoire')
    expect(apiController.findCall(
      'post', /roles\/SCOLARITE\/versions\/$/,
    )).toBeUndefined()

    // Avec motif : POST émis avec le motif saisi.
    await userEvent.type(screen.getByTestId('motif-version'), 'Instantané initial')
    await userEvent.click(screen.getByTestId('capturer-version'))
    const appel = apiController.findCall('post', /roles\/SCOLARITE\/versions\/$/)
    expect(appel).toBeDefined()
    expect(appel[1]).toEqual({ motif: 'Instantané initial' })
  })

  it('liste les versions et propose la restauration avec motif', async () => {
    apiController.setRoute(/roles\/$/, roles)
    apiController.setRoute(/roles\/SCOLARITE\/$/, detailScolarite)
    apiController.setRoute(/roles\/SCOLARITE\/versions\/$/, {
      role: 'SCOLARITE',
      total: 1,
      versions: [{
        numero: 1,
        instant: '2026-10-06T09:00:00',
        auteur: 'admin5',
        motif: 'Instantané initial.',
        source: 'MANUEL',
        source_libelle: 'Capture manuelle',
        donnees: {},
      }],
    })
    monter()
    await userEvent.click(await screen.findByTestId('ligne-role-SCOLARITE'))
    expect(await screen.findByTestId('versions-liste')).toBeInTheDocument()
    expect(screen.getByTestId('version-1')).toBeInTheDocument()

    // Sans motif : la restauration est refusée côté interface.
    await userEvent.click(screen.getByTestId('restaurer-version-1'))
    expect(screen.getByTestId('versions-message'))
      .toHaveTextContent('motif est obligatoire')
    expect(apiController.findCall(
      'post', /versions\/1\/restaurer\/$/,
    )).toBeUndefined()

    await userEvent.type(screen.getByTestId('motif-version'), 'Retour arrière validé')
    await userEvent.click(screen.getByTestId('restaurer-version-1'))
    const appel = apiController.findCall('post', /versions\/1\/restaurer\/$/)
    expect(appel).toBeDefined()
    expect(appel[1]).toEqual({ motif: 'Retour arrière validé' })
    await waitFor(() => expect(
      screen.getByTestId('versions-message'),
    ).toHaveTextContent('Version 1 restaurée'))
  })
})

describe('GestionRoles — comparaison de deux rôles (Lot B)', () => {
  it('affiche le diff champs + permissions ajoutées/retirées', async () => {
    apiController.setRoute(/roles\/$/, roles)
    apiController.setRoute(/comparer\/\?.*avec=/, {
      role_a: { code: 'SCOLARITE', libelle: 'Scolarité' },
      role_b: { code: 'DIRECTION', libelle: 'Direction' },
      champs: [{ champ: 'libelle', avant: 'Scolarité', apres: 'Direction' }],
      permissions_ajoutees: ['administration.compte.desactiver'],
      permissions_retirees: ['scolarite.inscription.creer'],
      incompatibilites_ajoutees: [],
      incompatibilites_retirees: [],
    })
    monter()
    await screen.findByTestId('ecran-roles')
    await userEvent.selectOptions(screen.getByTestId('comparer-a'), 'SCOLARITE')
    await userEvent.selectOptions(screen.getByTestId('comparer-b'), 'DIRECTION')
    await userEvent.click(screen.getByTestId('lancer-comparaison'))
    expect(await screen.findByTestId('comparaison-resultat')).toBeInTheDocument()
    expect(screen.getByTestId('comparaison-ajouts'))
      .toHaveTextContent('administration.compte.desactiver')
    expect(screen.getByTestId('comparaison-retraits'))
      .toHaveTextContent('scolarite.inscription.creer')
  })

  it('refuse deux rôles identiques sans appel API', async () => {
    apiController.setRoute(/roles\/$/, roles)
    monter()
    await screen.findByTestId('ecran-roles')
    await userEvent.selectOptions(screen.getByTestId('comparer-a'), 'SCOLARITE')
    await userEvent.selectOptions(screen.getByTestId('comparer-b'), 'SCOLARITE')
    await userEvent.click(screen.getByTestId('lancer-comparaison'))
    expect(screen.getByTestId('comparaison-erreur'))
      .toHaveTextContent('deux rôles différents')
    expect(apiController.findCall('get', /comparer\//)).toBeUndefined()
  })
})
