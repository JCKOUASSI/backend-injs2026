import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, within } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import FileProvisionnement from './FileProvisionnement'
import NotificationsHabilitation from './NotificationsHabilitation'
import OperationsMasse from './OperationsMasse'
import Delegations from './Delegations'

function monter(ui, route) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  render(ui, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern={route} initialEntries={[route]}>{children}</AllProviders>
    ),
  })
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

function fichierCsv(contenu) {
  const fichier = new File([contenu], 'import.csv', { type: 'text/csv' })
  fichier.text = async () => contenu
  return fichier
}

describe('FileProvisionnement (U5)', () => {
  const propositions = {
    count: 1,
    compteurs: { EN_ATTENTE: 1, APPLIQUEE: 0, REJETEE: 0, ANNULEE: 0 },
    results: [{
      id: 11, declencheur: 'ADMISSION', declencheur_libelle: 'Admission',
      action_proposee: 'CREER_COMPTE', action_libelle: 'Créer un compte',
      source: 'admissions.Admission#3', source_libelle: 'Awa Kouassi — L1',
      statut: 'EN_ATTENTE', statut_libelle: 'En attente',
      motif: 'Admission DEC-1.', proposition: {},
    }],
  }

  it('liste les propositions en attente et affiche les compteurs', async () => {
    apiController.setRoute(/\/propositions\//, propositions)
    apiController.setRoute('/habilitations/roles/', [{ code: 'ETUDIANT', libelle: 'Étudiant' }])
    monter(<FileProvisionnement />, '/administration/comptes/provisionnement')
    expect(await screen.findByTestId('proposition-11')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /En attente \(1\)/ })).toBeInTheDocument()
  })

  it('approuve après saisie du motif et notifie le service', async () => {
    apiController.setRoute(/\/propositions\//, propositions)
    apiController.setRoute('/habilitations/roles/', [])
    apiController.setRoute(/approuver\/$/, { ...propositions.results[0], statut: 'APPLIQUEE' })
    monter(<FileProvisionnement />, '/administration/comptes/provisionnement')
    await screen.findByTestId('proposition-11')
    fireEvent.click(screen.getByTestId('approuver-11'))
    const modale = await screen.findByRole('dialog')
    const confirmer = within(modale).getByTestId('confirmer-decision')
    expect(confirmer).toBeDisabled()
    fireEvent.change(within(modale).getByTestId('motif-decision'),
      { target: { value: 'Admission vérifiée dans le dossier.' } })
    fireEvent.click(confirmer)
    await waitFor(() => expect(
      apiController.findCall('post', /approuver\/$/)).toBeTruthy())
    const [, corps] = apiController.findCall('post', /approuver\/$/)
    expect(corps.motif).toMatch(/vérifiée/)
  })

  it('impose de compléter le rôle pour un recrutement', async () => {
    const recrutement = {
      count: 1, compteurs: propositions.compteurs,
      results: [{
        ...propositions.results[0], id: 12, declencheur: 'RECRUTEMENT',
        proposition: { role_a_completer: true },
      }],
    }
    apiController.setRoute(/\/propositions\//, recrutement)
    apiController.setRoute('/habilitations/roles/', [
      { code: 'AGENT_INSCRIPTIONS', libelle: 'Agent inscriptions' },
    ])
    monter(<FileProvisionnement />, '/administration/comptes/provisionnement')
    await screen.findByTestId('proposition-12')
    fireEvent.click(screen.getByTestId('approuver-12'))
    const modale = await screen.findByRole('dialog')
    expect(within(modale).getByTestId('zone-role-completer')).toBeInTheDocument()
    fireEvent.change(within(modale).getByTestId('motif-decision'),
      { target: { value: 'Affectation au service des inscriptions.' } })
    // Tant que le rôle d'accès n'est pas choisi, le bouton reste désactivé.
    expect(within(modale).getByTestId('confirmer-decision')).toBeDisabled()
    fireEvent.change(within(modale).getByTestId('role-legacy'),
      { target: { value: 'SECRETARIAT' } })
    fireEvent.change(within(modale).getByTestId('role-curp'),
      { target: { value: 'AGENT_INSCRIPTIONS' } })
    expect(within(modale).getByTestId('confirmer-decision')).toBeEnabled()
  })

  it('le scan manuel affiche le bilan renvoyé par le serveur', async () => {
    apiController.setRoute(/\/propositions\//, {
      count: 0, compteurs: { EN_ATTENTE: 0 }, results: [],
    })
    apiController.setRoute('/habilitations/roles/', [])
    monter(<FileProvisionnement />, '/administration/comptes/provisionnement')
    apiController.setRoute(/\/provisions\/scanner\//, {
      bilan: { ADMISSION: 2 }, total: 2, maitre_actif: true,
    })
    await screen.findByTestId('bouton-scan')
    fireEvent.click(screen.getByTestId('bouton-scan'))
    expect(await screen.findByTestId('bilan-scan')).toHaveTextContent(/ADMISSION : 2/)
  })
})

describe('Notifications (U5)', () => {
  it('marque une notification comme lu puis toutes les notifications', async () => {
    apiController.setRoute(/\/notifications\//, {
      count: 1, results: [{
        id: 7, categorie: 'PREAVIS_SUSPENSION', categorie_libelle: 'Préavis',
        titre: 'Suspension imminente', message: 'Inactivité 170 jours.',
        lu: false, date_creation: '2026-09-14T08:00:00Z',
      }],
    })
    monter(<NotificationsHabilitation />, '/administration/comptes/notifications')
    await screen.findByTestId('notification-7')
    fireEvent.click(screen.getByTestId('marquer-lu-7'))
    await waitFor(() => expect(
      apiController.findCall('post', /notifications\/7\/lire\//)).toBeTruthy())
    fireEvent.click(screen.getByTestId('tout-lire'))
    await waitFor(() => expect(
      apiController.findCall('post', /tout-lire\//)).toBeTruthy())
  })
})

describe('OperationsMasse — exécution et annulation (U5)', () => {
  const apercuValide = {
    total: 1, valides: 1, erreurs: 0,
    lignes: [{
      numero: 1, etat: 'VALIDE', roles: ['ETUDIANT'], problemes: [],
      valeurs: { username: 'etu0001', nom: 'Traoré', prenoms: 'Awa', roles: 'ETUDIANT' },
    }],
  }
  const execution = {
    id: 3, reference: 'IMP-20260914-0003', statut: 'TERMINE',
    statut_libelle: 'Terminé', total: 1, crees: 1, nom_fichier: 'import.csv',
    rapport: {},
  }

  it('exécute un lot valide puis permet son annulation motivée', async () => {
    monter(<OperationsMasse />, '/administration/comptes/operations-masse')
    apiController.setRoute(/import-simuler\/$/, apercuValide)
    apiController.setRoute(/comptes\/imports\/$/, execution)
    apiController.setRoute(/annuler\/$/, { ...execution, statut: 'ANNULE' })
    const csv = 'identifiant,nom,prenoms,mot_de_passe,roles\netu0001,Traoré,Awa,Essai#2026xx,ETUDIANT'
    fireEvent.change(screen.getByTestId('fichier-import'), { target: { files: [fichierCsv(csv)] } })
    const ecrire = await screen.findByTestId('bouton-ecrire')
    expect(ecrire).toBeEnabled()
    fireEvent.click(ecrire)
    const panel = await screen.findByTestId('rapport-execution')
    expect(panel).toHaveTextContent('IMP-20260914-0003')
    fireEvent.click(screen.getByTestId('bouton-annuler-import'))
    const modale = await screen.findByRole('dialog')
    fireEvent.change(within(modale).getByTestId('motif-input'),
      { target: { value: 'Lot saisi en double, annulation.' } })
    fireEvent.click(within(modale).getByTestId('motif-confirmation'))
    await waitFor(() => expect(
      apiController.findCall('post', /annuler\/$/)).toBeTruthy())
    const [, corps] = apiController.findCall('post', /annuler\/$/)
    expect(corps.motif).toMatch(/double/)
  })

  it('retrouve une exécution par sa référence', async () => {
    monter(<OperationsMasse />, '/administration/comptes/operations-masse')
    apiController.setRoute(/comptes\/imports\/IMP-/, execution)
    fireEvent.change(screen.getByTestId('reference-recherche'),
      { target: { value: 'IMP-20260914-0003' } })
    fireEvent.click(screen.getByTestId('bouton-retrouver'))
    expect(await screen.findByTestId('rapport-execution')).toBeInTheDocument()
  })
})

describe('Delegations — activation et action tracée (U5)', () => {
  const comptes = { count: 2, results: [
    { id: 1, username: 'curp_a' }, { id: 2, username: 'curp_b' },
  ] }

  it('active une délégation proposée avec motif', async () => {
    apiController.setRoute(/\/habilitations\/comptes\//, comptes)
    apiController.setRoute('/habilitations/roles/', [{ code: 'ENSEIGNANT', libelle: 'Enseignant' }])
    apiController.setRoute(/\/delegations\/?(\?|$)/, { count: 1, results: [{
      id: 9, delegant: 'curp_a', delegataire: 'curp_b', roles: ['ENSEIGNANT'],
      date_fin: '2026-12-31', statut: 'PROPOSEE',
    }] })
    monter(<Delegations />, '/administration/comptes/delegations')
    await screen.findByTestId('delegation-9')
    fireEvent.click(screen.getByTestId('activer-9'))
    const modale = await screen.findByRole('dialog')
    fireEvent.change(within(modale).getByTestId('motif-input'),
      { target: { value: 'Contrôle des droits fait.' } })
    fireEvent.click(within(modale).getByTestId('motif-confirmation'))
    await waitFor(() => expect(
      apiController.findCall('post', /activer\/$/)).toBeTruthy())
  })

  it('journalise une action du délégataire avec mention du délégant', async () => {
    apiController.setRoute(/\/habilitations\/comptes\//, comptes)
    apiController.setRoute('/habilitations/roles/', [])
    apiController.setRoute(/\/delegations\/?(\?|$)/, { count: 1, results: [{
      id: 10, delegant: 'curp_a', delegataire: 'curp_b', roles: [],
      date_fin: '2026-12-31', statut: 'ACTIVE',
    }] })
    apiController.setRoute(/action\/$/, { numero: 424, delegation: 10, delegant: 'curp_a' })
    monter(<Delegations />, '/administration/comptes/delegations')
    await screen.findByTestId('delegation-10')
    fireEvent.click(screen.getByTestId('action-10'))
    const modale = await screen.findByRole('dialog')
    fireEvent.change(within(modale).getByTestId('action-deleguee-input'),
      { target: { value: 'Validation de la décision 12' } })
    fireEvent.click(within(modale).getByTestId('action-deleguee-valider'))
    await waitFor(() => expect(
      apiController.findCall('post', /action\/$/)).toBeTruthy())
    const [, corps] = apiController.findCall('post', /action\/$/)
    expect(corps.action).toMatch(/décision 12/)
  })
})
