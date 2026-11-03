/**
 * Écran UE / ECUE — CRUD et cycle de vie.
 *
 * Ces tests portent sur ce que l'écran promet à l'utilisateur : on peut créer,
 * modifier et supprimer une UE et un ECUE ; les seuls statuts proposés sont
 * Brouillon, Activé et Désactivé ; une maquette validée gèle l'écran ; un rôle
 * sans droit d'écriture ne voit aucun bouton qui échouerait côté serveur.
 *
 * Le serveur reste seul juge : quand il refuse, l'écran affiche son refus sans
 * maquiller l'état.
 */
import {
  describe, it, expect, beforeEach, afterEach, vi,
} from 'vitest'
import {
  render, screen, fireEvent, waitFor, cleanup, within,
} from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import EcranUeEcue from './EcranUeEcue'

const MAQUETTE_BROUILLON = {
  id: 1,
  code: 'EM-2026',
  libelle: 'Éducation et motricité — L1',
  statut: 'BROUILLON',
  niveau_id: 1,
  annee_libelle: '2026-2027',
}

const MAQUETTE_VALIDEE = {
  id: 2,
  code: 'EM-2025',
  libelle: 'Éducation et motricité — L1 (validée)',
  statut: 'VALIDEE',
  niveau_id: 1,
  annee_libelle: '2025-2026',
}

const UE = {
  id: 10,
  code: 'EM-S1-UE01',
  intitule: 'Sciences de la vie et de la santé',
  credits: 6,
  ordre: 1,
  statut: 'BROUILLON',
  caractere: 'OBLIGATOIRE',
  famille_code: 'SB',
  semestre: { id: 1, libelle: 'S1' },
  ecues: [
    {
      id: 100,
      code: 'EM-S1-UE01-EC01',
      intitule: 'Anatomie descriptive',
      credits: 0,
      coefficient: 1,
      volume_cm: 0,
      volume_td: 0,
      volume_tp: 0,
      ordre: 1,
      statut: 'BROUILLON',
    },
  ],
}

const ADMIN = { id: 1, username: 'admin', role: 'ADMIN' }
const ENSEIGNANT = { id: 2, username: 'prof', role: 'ENSEIGNANT' }

function monter({ utilisateur = ADMIN, ues = [UE], maquettes = [MAQUETTE_BROUILLON] } = {}) {
  apiController.setMe({ ...utilisateur, is_active: true })
  apiController.setRoute('/scolarite/maquettes/', maquettes)
  apiController.setRoute('/scolarite/familles/', [{ id: 7, code: 'SB', libelle: 'Sciences biomédicales' }])
  apiController.setRoute('/scolarite/ref/semestres/', [{ id: 1, libelle: 'S1' }, { id: 2, libelle: 'S2' }])
  apiController.setRoute(/^\/scolarite\/maquettes\/\d+\/ues\/$/, () => ues)
  return render(<EcranUeEcue />, {
    wrapper: ({ children }) => <AllProviders authUser={utilisateur}>{children}</AllProviders>,
  })
}

const attendreEcran = () => screen.findByTestId('ligne-ue-10')

beforeEach(() => {
  window.localStorage.clear()
})

afterEach(() => {
  cleanup()
  apiController.reset()
})

describe('affichage et lecture', () => {
  it('affiche la maquette, ses UE et les ECUE de l’UE sélectionnée', async () => {
    monter()
    expect(await attendreEcran()).toBeInTheDocument()
    expect(screen.getByText('Sciences de la vie et de la santé')).toBeInTheDocument()
    // Le panneau ECUE suit la sélection par défaut (première UE).
    expect(await screen.findByTestId('ligne-ecue-100')).toBeInTheDocument()
    expect(screen.getByTestId('etat-maquette')).toHaveTextContent('Brouillon — contenu modifiable')
  })

  it('ne propose que les trois statuts du référentiel', async () => {
    monter()
    await attendreEcran()
    // Une UE brouillon ne peut aller que vers « Activé ».
    const boutons = screen.getAllByTestId(/^ue-statut-/)
    expect(boutons).toHaveLength(1)
    expect(boutons[0]).toHaveAttribute('data-testid', 'ue-statut-ACTIVE-10')
    expect(within(boutons[0]).queryByText(/Désactiv/)).toBeNull()
  })

  it('filtre les UE par code ou intitulé', async () => {
    monter()
    await attendreEcran()
    fireEvent.change(screen.getByTestId('recherche-ue'), { target: { value: 'introuvable' } })
    await waitFor(() => expect(screen.queryByTestId('ligne-ue-10')).toBeNull())
    fireEvent.change(screen.getByTestId('recherche-ue'), { target: { value: 'EM-S1' } })
    await waitFor(() => expect(screen.getByTestId('ligne-ue-10')).toBeInTheDocument())
  })

  it('affiche « — » plutôt que 0 pour un crédit d’ECUE non publié', async () => {
    monter()
    await attendreEcran()
    const ligne = await screen.findByTestId('ligne-ecue-100')
    const cellules = within(ligne).getAllByRole('cell')
    // Colonnes : code, intitulé, ECTS, volumes, statut, actions.
    expect(cellules[2]).toHaveTextContent('—')
    expect(cellules[3]).toHaveTextContent('—')
  })
})

describe('lecture impossible ou vide', () => {
  it('affiche le refus du serveur au lieu d’un écran vide', async () => {
    apiController.setMe({ ...ADMIN, is_active: true })
    apiController.setRoute('/scolarite/maquettes/', () => Promise.reject({
      response: {
        status: 403,
        data: { detail: "Vous n'avez pas la permission d'effectuer cette action." },
      },
    }))
    render(<EcranUeEcue />, {
      wrapper: ({ children }) => <AllProviders authUser={ADMIN}>{children}</AllProviders>,
    })
    const alerte = await screen.findByTestId('erreur-maquettes')
    expect(alerte).toHaveTextContent("Vous n'avez pas la permission d'effectuer cette action.")
    // Rien n'est proposé puisque rien n'est lisible : pas de bouton mort.
    expect(screen.queryByTestId('nouvelle-ue')).toBeNull()
  })

  it('explique l’absence de maquette plutôt que de rester muet', async () => {
    monter({ maquettes: [] })
    expect(await screen.findByTestId('aucune-maquette')).toHaveTextContent(/Aucune maquette/)
  })
})

describe('création', () => {
  it('crée une UE et envoie un corps typé à l’API', async () => {
    monter()
    await attendreEcran()
    fireEvent.click(screen.getByTestId('nouvelle-ue'))
    const formulaire = await screen.findByTestId('formulaire-element')
    fireEvent.change(screen.getByTestId('element-code'), { target: { value: 'EM-S1-UE99' } })
    fireEvent.change(screen.getByTestId('element-intitule'), { target: { value: 'Nouvelle UE' } })
    fireEvent.change(screen.getByTestId('element-credits'), { target: { value: '4' } })
    fireEvent.submit(formulaire)

    await waitFor(() => expect(apiController.findCall('post', '/scolarite/maquettes/1/ues/')).toBeTruthy())
    expect(apiController.lastBody('post')).toMatchObject({
      code: 'EM-S1-UE99',
      intitule: 'Nouvelle UE',
      credits: 4,
      semestre_id: 1,
    })
    // Le formulaire se referme, le message de confirmation s'affiche.
    await waitFor(() => expect(screen.queryByTestId('formulaire-element')).toBeNull())
    expect(await screen.findByText('Élément créé.')).toBeInTheDocument()
  })

  it('refuse la soumission sans code ni intitulé, sans appeler l’API', async () => {
    monter()
    await attendreEcran()
    fireEvent.click(screen.getByTestId('nouvelle-ue'))
    const formulaire = await screen.findByTestId('formulaire-element')
    fireEvent.change(screen.getByTestId('element-code'), { target: { value: '   ' } })
    fireEvent.submit(formulaire)
    expect(await screen.findByTestId('element-erreur')).toHaveTextContent('Le code est obligatoire')
    expect(apiController.findCall('post', '/scolarite/maquettes/1/ues/')).toBeFalsy()
  })

  it('affiche le refus du serveur dans le formulaire, sans perdre la saisie', async () => {
    monter()
    await attendreEcran()
    // Le serveur refuse : on simule le rejet HTTP 400 tel qu'axios le renvoie.
    apiController.api.post.mockRejectedValueOnce({
      response: {
        status: 400,
        data: { error: 'Le code « EM-S1-UE01 » existe déjà dans cette maquette.' },
      },
    })
    fireEvent.click(screen.getByTestId('nouvelle-ue'))
    const formulaire = await screen.findByTestId('formulaire-element')
    fireEvent.change(screen.getByTestId('element-code'), { target: { value: 'EM-S1-UE01' } })
    fireEvent.change(screen.getByTestId('element-intitule'), { target: { value: 'Doublon' } })
    fireEvent.submit(formulaire)

    expect(await screen.findByTestId('element-erreur'))
      .toHaveTextContent('existe déjà dans cette maquette')
    // La saisie est conservée : rien n'est perdu à cause d'un refus.
    expect(screen.getByTestId('element-intitule')).toHaveValue('Doublon')
  })
})

describe('sélection d’une UE', () => {
  it('ouvre les ECUE de l’UE choisie au clavier, via un bouton nommé', async () => {
    monter({
      ues: [
        UE,
        {
          ...UE,
          id: 11,
          code: 'EM-S1-UE02',
          intitule: 'Sciences humaines',
          ecues: [{ ...UE.ecues[0], id: 200, code: 'EM-S1-UE02-EC01', intitule: 'Psychologie' }],
        },
      ],
    })
    await attendreEcran()
    // Par défaut, la première UE est ouverte.
    expect(await screen.findByTestId('ligne-ecue-100')).toBeInTheDocument()
    const choix = screen.getByRole('button', { name: /Afficher les ECUE de l’UE EM-S1-UE02/ })
    expect(choix).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(choix)
    expect(await screen.findByTestId('ligne-ecue-200')).toBeInTheDocument()
    expect(screen.queryByTestId('ligne-ecue-100')).toBeNull()
  })
})

describe('ECUE : création, modification, suppression', () => {
  it('crée un ECUE sous l’UE sélectionnée', async () => {
    monter()
    await attendreEcran()
    fireEvent.click(screen.getByTestId('nouvel-ecue'))
    const formulaire = await screen.findByTestId('formulaire-element')
    fireEvent.change(screen.getByTestId('element-code'), { target: { value: 'EM-S1-UE01-EC02' } })
    fireEvent.change(screen.getByTestId('element-intitule'), { target: { value: 'Physiologie' } })
    fireEvent.change(screen.getByTestId('element-volume_cm'), { target: { value: '18' } })
    fireEvent.submit(formulaire)

    await waitFor(() => expect(
      apiController.findCall('post', '/scolarite/ues/10/ecues/'),
    ).toBeTruthy())
    expect(apiController.lastBody('post')).toMatchObject({
      code: 'EM-S1-UE01-EC02',
      intitule: 'Physiologie',
      volume_cm: 18,
    })
  })

  it('modifie un ECUE en brouillon par PATCH', async () => {
    monter()
    await attendreEcran()
    await screen.findByTestId('ligne-ecue-100')
    fireEvent.click(screen.getByTestId('modifier-ecue-100'))
    await screen.findByTestId('formulaire-element')
    fireEvent.change(screen.getByTestId('element-intitule'), { target: { value: 'Anatomie (corrigé)' } })
    fireEvent.submit(screen.getByTestId('formulaire-element'))

    await waitFor(() => expect(apiController.findCall('patch', '/scolarite/ecues/100/')).toBeTruthy())
    expect(apiController.lastBody('patch')).toMatchObject({ intitule: 'Anatomie (corrigé)' })
  })

  it('supprime un ECUE après confirmation', async () => {
    monter()
    await attendreEcran()
    await screen.findByTestId('ligne-ecue-100')
    fireEvent.click(screen.getByTestId('supprimer-ecue-100'))
    const boite = await screen.findByRole('dialog')
    fireEvent.click(within(boite).getByText('Supprimer'))
    await waitFor(() => expect(
      apiController.findCall('delete', '/scolarite/ecues/100/'),
    ).toBeTruthy())
  })

  it('change le statut d’un ECUE via son endpoint dédié', async () => {
    monter()
    await attendreEcran()
    await screen.findByTestId('ligne-ecue-100')
    apiController.setRoute('/scolarite/ecues/100/statut/', { id: 100, statut: 'ACTIVE' })
    fireEvent.click(screen.getByTestId('ecue-statut-ACTIVE-100'))
    await waitFor(() => expect(
      apiController.findCall('post', '/scolarite/ecues/100/statut/'),
    ).toBeTruthy())
    expect(apiController.lastBody('post')).toEqual({ statut: 'ACTIVE' })
  })
})

describe('modification et statuts', () => {
  it('modifie une UE en brouillon par PATCH', async () => {
    monter()
    await attendreEcran()
    fireEvent.click(screen.getByTestId('modifier-ue-10'))
    await screen.findByTestId('formulaire-element')
    fireEvent.change(screen.getByTestId('element-intitule'), { target: { value: 'Intitulé corrigé' } })
    fireEvent.submit(screen.getByTestId('formulaire-element'))

    await waitFor(() => expect(apiController.findCall('patch', '/scolarite/ues/10/')).toBeTruthy())
    expect(apiController.lastBody('patch')).toMatchObject({ intitule: 'Intitulé corrigé' })
    expect(await screen.findByText('Modification enregistrée.')).toBeInTheDocument()
  })

  it('active une UE puis propose sa désactivation', async () => {
    monter()
    await attendreEcran()
    apiController.setRoute('/scolarite/ues/10/statut/', { id: 10, statut: 'ACTIVE' })
    fireEvent.click(screen.getByTestId('ue-statut-ACTIVE-10'))
    await waitFor(() => expect(
      apiController.findCall('post', '/scolarite/ues/10/statut/'),
    ).toBeTruthy())
    expect(apiController.lastBody('post')).toEqual({ statut: 'ACTIVE' })
    expect(await screen.findByText('Statut modifié.')).toBeInTheDocument()
  })

  it('annonce les ECUE désactivées en cascade par le serveur', async () => {
    monter()
    await attendreEcran()
    apiController.setRoute('/scolarite/ues/10/statut/', {
      id: 10,
      statut: 'DESACTIVEE',
      ecues_desactivees: [{ id: 100, code: 'EM-S1-UE01-EC01' }],
    })
    fireEvent.click(screen.getByTestId('ue-statut-ACTIVE-10'))
    expect(await screen.findByText(/L’ECUE active a été désactivée avec l’UE\./))
      .toBeInTheDocument()
  })

  it('affiche le refus de transition renvoyé par le serveur', async () => {
    monter()
    await attendreEcran()
    apiController.api.post.mockRejectedValueOnce({
      response: { status: 409, data: { error: 'Transition ACTIVE → BROUILLON interdite.' } },
    })
    fireEvent.click(screen.getByTestId('ue-statut-ACTIVE-10'))
    expect(await screen.findByText('Transition ACTIVE → BROUILLON interdite.'))
      .toBeInTheDocument()
  })

  it('n’affiche aucune action d’écriture sur une maquette validée', async () => {
    monter({ maquettes: [MAQUETTE_VALIDEE] })
    expect(await screen.findByTestId('maquette-verrouillee')).toBeInTheDocument()
    expect(screen.queryByTestId('nouvelle-ue')).toBeNull()
    expect(screen.queryByTestId('nouvel-ecue')).toBeNull()
    expect(screen.queryByTestId('modifier-ue-10')).toBeNull()
    expect(screen.queryByTestId(/^ue-statut-/)).toBeNull()
  })
})

describe('suppression', () => {
  it('supprime une UE après confirmation explicite', async () => {
    monter({ ues: [{ ...UE, ecues: [] }] })
    await attendreEcran()
    fireEvent.click(screen.getByTestId('supprimer-ue-10'))
    const boite = await screen.findByRole('dialog')
    fireEvent.click(within(boite).getByText('Supprimer'))
    await waitFor(() => expect(apiController.findCall('delete', '/scolarite/ues/10/')).toBeTruthy())
    expect(await screen.findByText('Élément supprimé.')).toBeInTheDocument()
  })

  it('ne supprime rien si l’utilisateur annule', async () => {
    monter({ ues: [{ ...UE, ecues: [] }] })
    await attendreEcran()
    fireEvent.click(screen.getByTestId('supprimer-ue-10'))
    const boite = await screen.findByRole('dialog')
    fireEvent.click(within(boite).getByText('Annuler'))
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    expect(apiController.findCall('delete', '/scolarite/ues/10/')).toBeFalsy()
  })

  it('relaie le refus de suppression du serveur (UE portant des ECUE)', async () => {
    monter()
    await attendreEcran()
    apiController.api.delete.mockRejectedValueOnce({
      response: { data: { error: 'Suppression refusée : cette UE porte 1 ECUE.' } },
    })
    fireEvent.click(screen.getByTestId('supprimer-ue-10'))
    const boite = await screen.findByRole('dialog')
    fireEvent.click(within(boite).getByText('Supprimer'))
    expect(await screen.findByText('Suppression refusée : cette UE porte 1 ECUE.'))
      .toBeInTheDocument()
  })
})

describe('rôles', () => {
  it('un rôle sans droit d’écriture consulte sans bouton de gestion', async () => {
    monter({ utilisateur: ENSEIGNANT })
    expect(await attendreEcran()).toBeInTheDocument()
    expect(screen.queryByTestId('nouvelle-ue')).toBeNull()
    expect(screen.queryByTestId('nouvel-ecue')).toBeNull()
    expect(screen.queryByTestId('modifier-ue-10')).toBeNull()
    expect(screen.queryByTestId('supprimer-ue-10')).toBeNull()
    expect(screen.queryByTestId(/^ue-statut-/)).toBeNull()
    // La consultation reste complète : les ECUE sont visibles.
    expect(await screen.findByTestId('ligne-ecue-100')).toBeInTheDocument()
  })
})
