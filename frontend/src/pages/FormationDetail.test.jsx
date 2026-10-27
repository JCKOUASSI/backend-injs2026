/**
 * Tests de la fiche formation (niveau « formation », écran miroir de
 * ModuleDetail), domaine présence/émargement — LOT 21 (fondations) et
 * LOT 22 (achèvement), par l'extérieur :
 * - LOT 21 : chargement GET /formations/:id/detail/, en-tête, onglets et
 *   habilitations ; onglet Séances (regroupement par module, démarrage/fin
 *   via ConfirmModal, création inline, modification PATCH, suppression
 *   DELETE, erreurs) ; onglets Étudiants et Enseignants (pickers, ajouts,
 *   retraits) ; assignation de l'encadrant superviseur.
 * - LOT 22 : onglet Présences (dashboard temps réel, sélecteur de séance,
 *   recherche, états d'erreur, forçage de pointage unitaire — entrée
 *   étudiant / badgeage enseignant / fermeture de session —, jour passé avec
 *   heures et timestamps, bouton « Aujourd'hui », habilitations), exports
 *   PDF/Excel formation et séance (getBlob), QR de séance (intégration
 *   QRCodeModal), archivage TripleConfirmModal depuis l'en-tête de groupe,
 *   import Excel des séances réservé au SECRETARIAT, pagination serveur des
 *   pickers enseignants/étudiants.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import FormationDetail from '@/pages/FormationDetail'

const F = 10
const TODAY = new Date().toISOString().slice(0, 10)
const detailPath = `/formations/${F}/detail/`
const formateursPath = `/formations/${F}/formateurs/`

const PARTICIPANTS = [
  { id: 101, nom: 'Koné', prenom: 'Awa', matricule: 'MAT-001', email: 'awa@kone.ci', telephone: '0701010101', structure: 'INJS' },
  { id: 102, nom: 'Diop', prenom: 'Karim', matricule: 'MAT-002' },
]
const FORMATEURS = [{ id: 201, nom: 'Nguessan', prenom: 'Yao', numerobadge: 'F001', specialite: 'LSF' }]

const buildFormation = () => ({
  id: F,
  formation: 'LSF — Promotion 2026',
  statut: 'PLANIFIEE',
  site: 'Marcory', batiment: 'B', salle: 'B2',
  date_debut: '2026-09-01', date_fin: '2026-12-15',
  categorie: 'Continu', grade: 'L1', groupe: 'G1',
  superviseur: 301, superviseur_nom: 'Mariam Traoré',
  secretariat_nom: 'Secrétariat INJS Marcory',
  modules: [{ id: 77, intitule: 'LSF Niveau 1 — A1' }],
  formateurs: FORMATEURS,
  participants: PARTICIPANTS,
  sessions: [
    { id: 1, numero: 1, intitule: 'Séance du matin', module_id: 77, module_intitule: 'LSF Niveau 1 — A1', module_groupe: 'G1', date: TODAY, heure_debut: '08:00', heure_fin: '10:00', en_cours: true, terminee: false, nb_presences: 1, nb_attendus: 4 },
    { id: 2, numero: 2, intitule: 'Séance planifiée', module_id: 77, module_intitule: 'LSF Niveau 1 — A1', module_groupe: 'G1', date: TODAY, heure_debut: '10:00', heure_fin: '12:00', en_cours: false, terminee: false, nb_presences: 0, nb_attendus: 4 },
    { id: 3, numero: 1, intitule: 'Séance ancienne', module_id: 77, module_intitule: 'LSF Niveau 1 — A1', module_groupe: 'G1', date: '2026-08-01', heure_debut: '08:00', heure_fin: '10:00', en_cours: false, terminee: true, nb_presences: 4, nb_attendus: 4 },
  ],
})

const setupRoutes = () => {
  apiController.setRoute(detailPath, () => buildFormation())
  apiController.setRoute(formateursPath, () => FORMATEURS)
}

const mount = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<FormationDetail />, {
    authUser: me,
    routePattern: '/formations/:id',
    initialEntries: [`/formations/${F}`],
  })
}
const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }
const posts = (pred) =>
  apiMock.post.mock.calls.filter(([p]) => pred(p)).map(([p, b]) => ({ path: p, body: b }))
const patches = () => apiMock.patch.mock.calls.map(([p, b]) => ({ path: p, body: b }))
const deletes = () => apiMock.delete.mock.calls.map(([p]) => p)
const modal = () => document.querySelector('.modal-content')
const sessionRow = (intitule) => screen.getByText(intitule).closest('tr')
const goTab = async (name) => {
  fireEvent.click(screen.getByRole('button', { name }))
  await settle()
}
// Les pickers passent par un setTimeout de 300 ms (debounce) : horloge réelle.
const waitReal = async (ms = 360) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)) }) }
const clickConfirm = async () => {
  fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
  await settle(8)
}
const dashboardPath = `/formations/${F}/dashboard/`
const forcePath = `/formations/${F}/force-pointage/`
const dashCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.startsWith(dashboardPath))
    .map(([p]) => new URLSearchParams(p.split('?')[1] || ''))
const stubBlobDownload = () => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

// Dashboard d'une journée : un étudiant en salle, un encadrant déjà sorti,
// un étudiant et un enseignant absents.
const buildDashboard = () => ({
  total_attendus: 4,
  nb_inscrits: 4,
  nb_seances_jour: 1,
  taux_presence: 50,
  seance_selectionnee_id: null,
  seances_jour: [
    { id: 1, intitule: 'Séance du matin', heure_debut: '08:00', heure_fin: '10:00', en_cours: true, terminee: false },
  ],
  en_salle: [
    { id: 101, nom: 'Koné', prenom: 'Awa', type_personne: 'participant', matricule: 'MAT-001', grade: 'L1', site: 'Marcory', timestamp_entree: `${TODAY}T08:00`, duree_actuelle_minutes: 42, nb_sessions: 1 },
  ],
  presents: [
    { id: 301, nom: 'Traoré', prenom: 'Mariam', type_personne: 'encadrant', matricule: 'ENC-1', grade: '—', site: 'Marcory', timestamp_entree: `${TODAY}T08:00`, timestamp_sortie: `${TODAY}T09:30`, duree_presence_minutes: 90, nb_sessions: 1 },
  ],
  absents: [
    { id: 102, nom: 'Diop', prenom: 'Karim', type_personne: 'participant', matricule: 'MAT-002', grade: 'L1', site: 'Marcory', email: 'karim@diop.ci', telephone: '0702020202' },
    { id: 201, nom: 'Nguessan', prenom: 'Yao', type_personne: 'formateur', numerobadge: 'F001', grade: '—', site: 'Marcory' },
  ],
})

// Monte la page puis ouvre l'onglet Présences (le dashboard se charge alors).
const openPresences = async (role = 'ADMIN') => {
  mount(role)
  await screen.findByText('LSF — Promotion 2026')
  await goTab(/présences/i)
}

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('FormationDetail — chargement, en-tête et onglets', () => {
  it('affiche la formation, son statut, ses modules et les compteurs de résumé', async () => {
    mount()
    expect(await screen.findByText('LSF — Promotion 2026')).toBeInTheDocument()

    // En-tête : badge statut et nombre de modules.
    expect(screen.getAllByText('Planifié').length).toBeGreaterThan(0)
    expect(screen.getByText('1 module')).toBeInTheDocument()
    // Le module est un lien vers sa fiche détaillée.
    expect(screen.getByRole('link', { name: 'LSF Niveau 1 — A1' })).toHaveAttribute(
      'href',
      `/formations/${F}/modules/77`,
    )

    // Les quatre cartes de résumé portent bien une valeur numérique.
    for (const label of ['Séances', 'Étudiants', 'Terminées', 'Enseignants']) {
      expect(screen.getByText(label).parentElement).toHaveTextContent(/[0-9]/)
    }
    expect(screen.getByText('Mariam Traoré')).toBeInTheDocument()
  })

  it("affiche un message d'erreur et un retour si le chargement échoue", async () => {
    // La route par défaut de beforeEach est déjà enregistrée : on repart à zéro
    // (matchRoute renvoie la première correspondance, donc un reset est requis).
    apiController.reset()
    apiController.setRoute(detailPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { status: 500 } }
    })
    mount()
    expect(await screen.findByText('Erreur lors du chargement de la formation')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /retour/i }))
  })

  it("masque l'onglet Présences pour un rôle non habilité (SUPERVISEUR)", async () => {
    mount('SUPERVISEUR')
    expect(await screen.findByText('LSF — Promotion 2026')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Informations' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /présences/i })).not.toBeInTheDocument()
    // Les autres onglets restent accessibles.
    expect(screen.getByRole('button', { name: /séances \(3\)/i })).toBeInTheDocument()
  })
})

describe('FormationDetail — onglet Séances (cycle de vie)', () => {
  beforeEach(async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
  })

  it('regroupe les séances par module et affiche statuts et compteurs de présence', () => {
    // En-tête de groupe : lien module + nombre de séances.
    expect(screen.getAllByText('LSF Niveau 1 — A1').length).toBeGreaterThan(0)
    expect(screen.getByText('3 séances')).toBeInTheDocument()
    expect(sessionRow('Séance du matin')).toHaveTextContent('En cours')
    expect(sessionRow('Séance ancienne')).toHaveTextContent('Terminé')
    expect(sessionRow('Séance planifiée')).toHaveTextContent('Planifié')
    expect(sessionRow('Séance du matin')).toHaveTextContent('1')
  })

  it('démarre une séance planifiée après confirmation (POST start), notifie et recharge', async () => {
    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Démarrer'))
    expect(await screen.findByText(/démarrer la séance/i)).toBeInTheDocument()
    await clickConfirm()
    expect(posts((p) => p.endsWith('/sessions/2/start/'))).toEqual([
      { path: `/formations/${F}/sessions/2/start/`, body: undefined },
    ])
    expect(await screen.findByText('Séance démarrée')).toBeInTheDocument()
  })

  it("n'émet rien si la confirmation de démarrage est annulée", async () => {
    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Démarrer'))
    await screen.findByText(/démarrer la séance/i)
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(posts((p) => p.includes('/start/'))).toHaveLength(0)
  })

  it('termine une séance en cours (POST stop)', async () => {
    fireEvent.click(within(sessionRow('Séance du matin')).getByTitle('Terminer'))
    expect(await screen.findByText(/terminer la séance/i)).toBeInTheDocument()
    await clickConfirm()
    expect(posts((p) => p.endsWith('/sessions/1/stop/'))).toHaveLength(1)
    expect(await screen.findByText('Séance terminée')).toBeInTheDocument()
  })

  it('supprime une séance planifiée après confirmation (DELETE), rien si annulé', async () => {
    const row = sessionRow('Séance planifiée')
    fireEvent.click(within(row).getByTitle('Supprimer'))
    expect(await screen.findByText('Supprimer cette séance ?')).toBeInTheDocument()
    // Annulation d'abord.
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(deletes()).toHaveLength(0)
    // Puis confirmation.
    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Supprimer'))
    await screen.findByText('Supprimer cette séance ?')
    await clickConfirm()
    expect(deletes()).toContain(`/formations/${F}/sessions/2/delete/`)
    expect(await screen.findByText('Séance supprimée')).toBeInTheDocument()
  })

  it('crée une séance via le formulaire inline (POST new, numero et intitulé calculés)', async () => {
    fireEvent.click(screen.getByRole('button', { name: /ajouter une séance/i }))
    const form = screen.getByRole('button', { name: 'Créer' }).closest('form')
    fireEvent.change(form.querySelector('input[type="date"]'), { target: { value: '2026-09-20' } })
    const times = form.querySelectorAll('input[type="time"]')
    fireEvent.change(times[0], { target: { value: '14:00' } })
    fireEvent.change(times[1], { target: { value: '16:00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))
    await settle(8)

    expect(posts((p) => p.endsWith('/sessions/new/'))).toEqual([
      {
        path: `/formations/${F}/sessions/new/`,
        body: expect.objectContaining({
          date_journee: '2026-09-20',
          heure_debut_prevue: '14:00',
          heure_fin_prevue: '16:00',
          numero: 4, // sessions.length + 1
          intitule: 'Séance 4',
        }),
      },
    ])
    expect(await screen.findByText('Séance créée')).toBeInTheDocument()
  })

  it('modifie une séance (PATCH update) avec les champs saisis', async () => {
    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Modifier'))
    const box = await screen.findByRole('heading', { name: /modifier la séance/i })
    const form = box.closest('.modal-content')
    // Le premier champ texte est le numéro (lecture seule), le second est l'intitulé.
    fireEvent.change(form.querySelectorAll('input[type="text"]')[1], { target: { value: 'Séance reportée' } })
    fireEvent.change(form.querySelector('input[type="date"]'), { target: { value: '2026-09-21' } })
    fireEvent.click(within(form).getByRole('button', { name: 'Enregistrer' }))
    await settle(8)

    expect(patches()).toEqual([
      {
        path: `/formations/${F}/sessions/2/update/`,
        body: expect.objectContaining({ intitule: 'Séance reportée', date_journee: '2026-09-21' }),
      },
    ])
    expect(await screen.findByText('Séance modifiée')).toBeInTheDocument()
  })

  it('notifie le détail renvoyé si le démarrage échoue', async () => {
    apiController.setRoute(/\/sessions\/2\/start\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Conflit de salle détecté.' } } }
    })
    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Démarrer'))
    await screen.findByText(/démarrer la séance/i)
    await clickConfirm()
    expect(await screen.findByText('Conflit de salle détecté.')).toBeInTheDocument()
  })
})

describe('FormationDetail — habilitations', () => {
  it("pour un ENCADRANT : démarrage/fin autorisés, mais pas de création/suppression/modification", async () => {
    mount('ENCADRANT')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)

    expect(screen.queryByRole('button', { name: /ajouter une séance/i })).not.toBeInTheDocument()
    const planned = sessionRow('Séance planifiée')
    expect(within(planned).getByTitle('Démarrer')).toBeInTheDocument()
    expect(within(planned).queryByTitle('Supprimer')).not.toBeInTheDocument()
    expect(within(planned).queryByTitle('Modifier')).not.toBeInTheDocument()
  })

  it("pour la DIRECTION : lecture seule (pas de séance, ni d'action de supervision)", async () => {
    mount('DIRECTION')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    expect(screen.queryByRole('button', { name: /ajouter une séance/i })).not.toBeInTheDocument()
    expect(within(sessionRow('Séance planifiée')).queryByTitle('Démarrer')).not.toBeInTheDocument()
    expect(within(sessionRow('Séance du matin')).queryByTitle('Terminer')).not.toBeInTheDocument()
  })

  it("pour la DIRECTION : pas d'ajout ni de retrait d'étudiant (lecture seule)", async () => {
    mount('DIRECTION')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/étudiants \(2\)/i)
    expect(screen.queryByRole('button', { name: /ajouter un étudiant/i })).not.toBeInTheDocument()
    expect(within(screen.getByText('Koné').closest('tr')).queryByTitle('Retirer')).not.toBeInTheDocument()
    // La liste reste consultable.
    expect(screen.getByText('Étudiants inscrits (2)')).toBeInTheDocument()
  })

  it("n'offre aucune action de vie sur une séance terminée (hors QR et exports)", async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    const old = sessionRow('Séance ancienne')
    expect(within(old).queryByTitle('Démarrer')).not.toBeInTheDocument()
    expect(within(old).queryByTitle('Terminer')).not.toBeInTheDocument()
    expect(within(old).queryByTitle('Modifier')).not.toBeInTheDocument()
    expect(within(old).queryByTitle('Supprimer')).not.toBeInTheDocument()
    expect(within(old).queryByTitle('QR Code')).not.toBeInTheDocument()
    // Le badge « Terminé » est rendu dans la cellule statut.
    expect(within(old).getAllByText('Terminé').length).toBeGreaterThan(0)
  })
})

describe('FormationDetail — onglet Étudiants', () => {
  beforeEach(async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/étudiants \(2\)/i)
  })

  it('liste les inscrits avec leurs coordonnées', () => {
    expect(screen.getByText('Étudiants inscrits (2)')).toBeInTheDocument()
    expect(screen.getByText('Koné')).toBeInTheDocument()
    expect(screen.getByText('awa@kone.ci')).toBeInTheDocument()
    expect(screen.getByText('MAT-001')).toBeInTheDocument()
  })

  it('ajoute un étudiant via le picker (POST add), en excluant les déjà inscrits', async () => {
    apiController.setRoute('/formations/participants/list/', () => [
      { id: 101, nom: 'Koné', prenom: 'Awa' }, // déjà inscrit → filtré
      { id: 103, nom: 'Bamba', prenom: 'Issa', numero_matricule: 'MAT-003' },
    ])
    fireEvent.click(screen.getByRole('button', { name: /ajouter un étudiant/i }))
    await waitReal()
    const box = modal()
    expect(within(box).queryByText('Awa')).not.toBeInTheDocument()
    expect(within(box).getByText('Bamba')).toBeInTheDocument()

    fireEvent.click(within(within(box).getByText('Bamba').closest('tr')).getByRole('button'))
    await settle(8)
    expect(posts((p) => p.includes('/participants/add/'))).toEqual([
      { path: `/formations/${F}/participants/add/`, body: { participant_id: 103 } },
    ])
    expect(await screen.findByText('Étudiant ajouté')).toBeInTheDocument()
  })

  it("notifie le détail backend si l'ajout échoue", async () => {
    apiController.setRoute('/formations/participants/list/', () => [
      { id: 105, nom: 'Yao', prenom: 'Kouam' },
    ])
    apiController.setRoute(/\/participants\/add\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Cet étudiant est déjà inscrit à cette formation.' } } }
    })
    fireEvent.click(screen.getByRole('button', { name: /ajouter un étudiant/i }))
    await waitReal()
    const box = modal()
    fireEvent.click(within(within(box).getByText('Yao').closest('tr')).getByRole('button'))
    expect(await screen.findByText('Cet étudiant est déjà inscrit à cette formation.')).toBeInTheDocument()
  })

  it('retire un étudiant après confirmation (DELETE)', async () => {
    fireEvent.click(within(screen.getByText('Koné').closest('tr')).getByTitle('Retirer'))
    expect(await screen.findByText('Retirer cet étudiant de la formation ?')).toBeInTheDocument()
    await clickConfirm()
    expect(deletes()).toContain(`/formations/${F}/participants/101/remove/`)
    expect(await screen.findByText('Étudiant retiré')).toBeInTheDocument()
  })
})

describe('FormationDetail — onglet Enseignants', () => {
  it('charge les enseignants assignés à l’activation de l’onglet (GET formateurs)', async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    expect(apiMock.get.mock.calls.some(([p]) => p === formateursPath)).toBe(false)
    await goTab(/enseignants/i)
    expect(apiMock.get.mock.calls.some(([p]) => p === formateursPath)).toBe(true)
    expect(screen.getByText('Enseignants assignés (1)')).toBeInTheDocument()
    expect(screen.getByText('Nguessan')).toBeInTheDocument()
    expect(screen.getByText('F001')).toBeInTheDocument()
  })

  it('ajoute un enseignant via le picker (POST add au niveau formation, sans module_id)', async () => {
    apiController.setRoute('/formations/formateurs/list/', (path) => {
      expect(path).not.toContain('module_id=') // périmètre formation, pas module
      return [
        { id: 201, nom: 'Nguessan', prenom: 'Yao' }, // déjà assigné → filtré
        { id: 202, nom: 'Koffi', prenom: 'Ado', specialite: 'LSF' },
      ]
    })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/enseignants/i)

    fireEvent.click(screen.getByRole('button', { name: /ajouter un enseignant/i }))
    await waitReal()
    const box = modal()
    expect(within(box).queryByText(/Nguessan Yao/)).not.toBeInTheDocument()
    expect(within(box).getByText(/Koffi Ado/)).toBeInTheDocument()

    fireEvent.click(within(within(box).getByText(/Koffi Ado/).closest('tr')).getByRole('button'))
    await settle(8)
    expect(posts((p) => p.includes('/formateurs/add/'))).toEqual([
      { path: `/formations/${F}/formateurs/add/`, body: { formateur_id: 202 } },
    ])
    expect(await screen.findByText('Enseignant ajouté')).toBeInTheDocument()
  })

  it('retire un enseignant après confirmation (DELETE)', async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/enseignants/i)
    fireEvent.click(within(screen.getByText('Nguessan').closest('tr')).getByTitle('Retirer'))
    expect(await screen.findByText('Retirer cet enseignant de la formation ?')).toBeInTheDocument()
    await clickConfirm()
    expect(deletes()).toContain(`/formations/${F}/formateurs/201/remove/`)
    expect(await screen.findByText('Enseignant retiré')).toBeInTheDocument()
  })
})

describe('FormationDetail — onglet Informations (encadrant)', () => {
  it('assigne un encadrant superviseur (GET users ENCADRANT puis POST assign-superviseur)', async () => {
    apiController.setRoute('/auth/users/', () => [
      { id: 302, first_name: 'Issa', last_name: 'Bamba', username: 'ibamba', matricule: 'ENC-2' },
    ])
    mount()
    await screen.findByText('LSF — Promotion 2026')
    // Le petit crayon près du nom de l'encadrant ouvre la modale.
    const encadrantRow = screen.getByText('Encadrant').closest('div')
    fireEvent.click(within(encadrantRow).getByRole('button'))
    await waitReal()
    const box = await screen.findByRole('heading', { name: 'Assigner un encadrant' })
    const form = box.closest('.modal-content')
    expect(within(form).getByText('ibamba')).toBeInTheDocument()

    fireEvent.click(within(form).getByText('ibamba').closest('tr'))
    fireEvent.click(within(form).getByRole('button', { name: 'Assigner' }))
    await settle(8)

    expect(posts((p) => p.includes('/assign-superviseur/'))).toEqual([
      { path: `/formations/${F}/assign-superviseur/`, body: { superviseur_id: '302' } },
    ])
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })

  it("refuse l'enregistrement sans sélection (message dans la modale)", async () => {
    // Variante sans encadrant assigné (selectedSup initial vide).
    apiController.reset()
    apiController.setRoute(detailPath, () => ({ ...buildFormation(), superviseur: null, superviseur_nom: null }))
    apiController.setRoute(formateursPath, () => FORMATEURS)
    apiController.setRoute('/auth/users/', () => [
      { id: 302, first_name: 'Issa', last_name: 'Bamba', username: 'ibamba' },
    ])
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    renderWithProviders(<FormationDetail />, {
      authUser: me,
      routePattern: '/formations/:id',
      initialEntries: [`/formations/${F}`],
    })
    await screen.findByText('LSF — Promotion 2026')
    const encadrantRow = screen.getByText('Encadrant').closest('div')
    fireEvent.click(within(encadrantRow).getByRole('button'))
    await waitReal()
    const box = await screen.findByRole('heading', { name: 'Assigner un encadrant' })
    const form = box.closest('.modal-content')
    fireEvent.click(within(form).getByRole('button', { name: 'Assigner' }))
    await settle()
    expect(within(form).getByText('Veuillez sélectionner un encadrant')).toBeInTheDocument()
    expect(posts((p) => p.includes('/assign-superviseur/'))).toHaveLength(0)
  })

  it("la DIRECTION ne voit pas le crayon d'assignation", async () => {
    mount('DIRECTION')
    await screen.findByText('LSF — Promotion 2026')
    const encadrantRow = screen.getByText('Encadrant').closest('div')
    expect(within(encadrantRow).queryByRole('button')).not.toBeInTheDocument()
  })
})

// ════════════════════════════════════════════════════════════════════════
// LOT 22 — achèvement de la fiche formation
// ════════════════════════════════════════════════════════════════════════

describe('FormationDetail — onglet Présences (dashboard temps réel)', () => {
  it('affiche les 5 cartes de stats et les sections En salle / Sortis / Absents avec les types de personne', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()

    // Cartes de statistiques.
    expect(screen.getByText('Attendus')).toBeInTheDocument()
    expect(screen.getByText('En salle')).toBeInTheDocument()
    expect(screen.getByText('Taux présence')).toBeInTheDocument()
    expect(screen.getByText('50%')).toBeInTheDocument()

    // Trois sections avec leurs personnes.
    expect(screen.getByText(/En salle \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Présents — sortis \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Absents \(2\)/)).toBeInTheDocument()
    expect(screen.getByText('Koné Awa')).toBeInTheDocument()
    expect(screen.getByText('Traoré Mariam')).toBeInTheDocument()
    expect(screen.getByText('Diop Karim')).toBeInTheDocument()
    expect(screen.getByText('Nguessan Yao')).toBeInTheDocument()

    // Badges de type de personne et durées formatées.
    expect(screen.getAllByText('Étudiant').length).toBeGreaterThan(0)
    expect(screen.getByText('Encadrant')).toBeInTheDocument()
    expect(screen.getByText('Enseignant')).toBeInTheDocument()
    expect(screen.getByText('42 min')).toBeInTheDocument()
    expect(screen.getByText('90 min')).toBeInTheDocument()

    // Le sélecteur de séance est proposé (une séance ce jour).
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  it('filtre la liste par séance (session_id transmis au rechargement)', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } })
    await settle(6)
    const params = dashCalls().pop()
    expect(params.get('session_id')).toBe('1')
  })

  it('filtre les personnes par recherche côté client, avec le compteur filtré / total', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()
    fireEvent.change(screen.getByPlaceholderText('Rechercher un étudiant…'), { target: { value: 'Diop' } })

    // Seul Karim Diop subsiste (absent) ; les autres sections se vident.
    expect(screen.getByText(/Absents \(1 \/ 2\)/)).toBeInTheDocument()
    expect(screen.getByText('Diop Karim')).toBeInTheDocument()
    expect(screen.queryByText('Nguessan Yao')).not.toBeInTheDocument()
    expect(screen.queryByText('Koné Awa')).not.toBeInTheDocument()

    // Le bouton d'effacement rétablit la liste complète.
    fireEvent.click(screen.getByTitle('Effacer'))
    expect(screen.getByText(/Absents \(2\)/)).toBeInTheDocument()
  })

  it("affiche l'état vide quand aucune personne n'est retournée", async () => {
    apiController.setRoute(dashboardPath, () => ({ en_salle: [], presents: [], absents: [] }))
    await openPresences()
    expect(await screen.findByText('Aucune donnée de présence pour cette date')).toBeInTheDocument()
  })

  it("affiche le message d'accès refusé (403) au tableau de présences", async () => {
    apiController.setRoute(dashboardPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { status: 403 } }
    })
    await openPresences()
    expect(await screen.findByText('Accès non autorisé au tableau de présences.')).toBeInTheDocument()
  })

  it("affiche un message générique pour une autre erreur de chargement", async () => {
    apiController.setRoute(dashboardPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { status: 500 } }
    })
    await openPresences()
    expect(await screen.findByText('Erreur lors du chargement des présences.')).toBeInTheDocument()
  })

  it('force la présence d’un étudiant absent aujourd’hui (motif obligatoire, pas de timestamps)', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()

    fireEvent.click(within(screen.getByText('Diop Karim').closest('tr')).getByRole('button', { name: /forcer présence/i }))
    const box = await screen.findByRole('heading', { name: 'Forcer la présence' }).then((h) => h.closest('.modal-content'))
    expect(within(box).getByText(/Diop Karim/)).toBeInTheDocument()
    // Aujourd'hui : pas de champs d'heures, toute la durée planifiée est prise.
    expect(box.querySelectorAll('input[type="time"]')).toHaveLength(0)

    const submit = within(box).getByRole('button', { name: 'Confirmer la présence' })
    fireEvent.click(submit)
    expect(within(box).getByText('Le motif est obligatoire.')).toBeInTheDocument()
    expect(posts((p) => p === forcePath)).toHaveLength(0)

    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Transport en panne' } })
    fireEvent.click(submit)
    await settle(10)

    expect(posts((p) => p === forcePath)).toEqual([
      {
        path: forcePath,
        body: {
          action: 'ENTREE', personne_id: 102, type_personne: 'participant',
          motif: 'Transport en panne', date_journee: TODAY,
        },
      },
    ])
    expect(await screen.findByText('Présence forcée — durée planifiée de la séance')).toBeInTheDocument()
  })

  it("badge l'entrée d'un enseignant absent (type formateur, intitulé adapté)", async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()

    fireEvent.click(within(screen.getByText('Nguessan Yao').closest('tr')).getByRole('button', { name: /^badger/i }))
    const box = await screen.findByRole('heading', { name: /badger l'entrée/i }).then((h) => h.closest('.modal-content'))
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Remplacement en salle' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Confirmer le badgeage' }))
    await settle(10)

    expect(posts((p) => p === forcePath)).toEqual([
      {
        path: forcePath,
        body: {
          action: 'ENTREE', personne_id: 201, type_personne: 'formateur',
          motif: 'Remplacement en salle', date_journee: TODAY,
        },
      },
    ])
    expect(await screen.findByText('Entrée badgée')).toBeInTheDocument()
  })

  it('ferme la session d’une personne en salle (SORTIE) avec motif', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()

    fireEvent.click(within(screen.getByText('Koné Awa').closest('tr')).getByRole('button', { name: /^fermer/i }))
    const box = await screen.findByRole('heading', { name: 'Fermer la session' }).then((h) => h.closest('.modal-content'))
    expect(box.querySelectorAll('input[type="time"]')).toHaveLength(0) // aujourd'hui : pas d'heures
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Départ anticipé autorisé' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Confirmer la sortie' }))
    await settle(10)

    expect(posts((p) => p === forcePath)).toEqual([
      {
        path: forcePath,
        body: {
          action: 'SORTIE', personne_id: 101, type_personne: 'participant',
          motif: 'Départ anticipé autorisé', date_journee: TODAY,
        },
      },
    ])
    expect(await screen.findByText('Session fermée')).toBeInTheDocument()
  })

  it("un jour passé : l'heure d'entrée est obligatoire et les timestamps sont transmis", async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()

    fireEvent.change(screen.getByDisplayValue(TODAY), { target: { value: '2026-09-05' } })
    await settle(6)

    fireEvent.click(within(screen.getByText('Diop Karim').closest('tr')).getByRole('button', { name: /forcer présence/i }))
    const box = await screen.findByRole('heading', { name: 'Forcer la présence' }).then((h) => h.closest('.modal-content'))
    expect(within(box).getByText(/Jour passé — 2026-09-05/)).toBeInTheDocument()
    const times = box.querySelectorAll('input[type="time"]')
    expect(times).toHaveLength(2)

    // Motif seul → l'heure d'entrée reste exigée.
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Rattrapage administratif' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Confirmer la présence' }))
    expect(within(box).getByText("L'heure d'entrée est obligatoire pour un jour passé.")).toBeInTheDocument()

    // Heures d'entrée et de sortie fournies.
    fireEvent.change(times[0], { target: { value: '09:00' } })
    fireEvent.change(times[1], { target: { value: '10:30' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Confirmer la présence' }))
    await settle(10)

    expect(posts((p) => p === forcePath)).toEqual([
      {
        path: forcePath,
        body: {
          action: 'ENTREE', personne_id: 102, type_personne: 'participant',
          motif: 'Rattrapage administratif', date_journee: '2026-09-05',
          timestamp_entree: '2026-09-05T09:00:00',
          timestamp_sortie: '2026-09-05T10:30:00',
        },
      },
    ])
  })

  it('une SORTIE un jour passé transmet uniquement timestamp_sortie', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()
    fireEvent.change(screen.getByDisplayValue(TODAY), { target: { value: '2026-09-05' } })
    await settle(6)

    fireEvent.click(within(screen.getByText('Koné Awa').closest('tr')).getByRole('button', { name: /^fermer/i }))
    const box = await screen.findByRole('heading', { name: 'Fermer la session' }).then((h) => h.closest('.modal-content'))
    const times = box.querySelectorAll('input[type="time"]')
    expect(times).toHaveLength(1) // une seule heure (sortie, optionnelle)
    fireEvent.change(times[0], { target: { value: '11:00' } })
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Fermeture a posteriori' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Confirmer la sortie' }))
    await settle(10)

    expect(posts((p) => p === forcePath)).toEqual([
      {
        path: forcePath,
        body: {
          action: 'SORTIE', personne_id: 101, type_personne: 'participant',
          motif: 'Fermeture a posteriori', date_journee: '2026-09-05',
          timestamp_sortie: '2026-09-05T11:00:00',
        },
      },
    ])
  })

  it("le bouton « Aujourd'hui » réinitialise la date et la séance sélectionnée", async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences()
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } })
    await settle(4)
    fireEvent.change(screen.getByDisplayValue(TODAY), { target: { value: '2026-09-05' } })
    await settle(6)

    const reset = screen.getByTitle("Revenir à aujourd'hui, toutes séances")
    fireEvent.click(reset)
    await settle(6)
    const params = dashCalls().pop()
    expect(params.get('date')).toBe(TODAY)
    // session_id n'est simplement plus sérialisé (null) côté construction d'URL.
    expect(params.get('session_id')).toBeNull()
  })

  it("pour la DIRECTION : lecture des présences mais aucun forçage (pas de boutons d'action)", async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    await openPresences('DIRECTION')
    expect(screen.getByText('Diop Karim')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /forcer présence/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^badger/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^fermer/i })).not.toBeInTheDocument()
  })
})

describe('FormationDetail — exports PDF / Excel', () => {
  beforeEach(() => stubBlobDownload())

  it('exporte toute la formation depuis l’en-tête (getBlob pdf et xlsx, noms dérivés)', async () => {
    const downloaded = []
    HTMLAnchorElement.prototype.click.mockImplementation(function () { downloaded.push(this.download) })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /pdf — toutes séances/i }))
      fireEvent.click(screen.getByRole('button', { name: /excel — toutes séances/i }))
      await flushPromises(8)
    })
    const calls = apiMock.getBlob.mock.calls.map(([p]) => p)
    expect(calls).toContain(`/exports/formation/${F}/pdf/`)
    expect(calls).toContain(`/exports/formation/${F}/excel/`)
    expect(downloaded).toEqual([`rapport_formation_${F}.pdf`, `rapport_formation_${F}.xlsx`])
  })

  it('exporte une séance précise depuis sa ligne (nom de fichier dérivé de l’intitulé)', async () => {
    const downloaded = []
    HTMLAnchorElement.prototype.click.mockImplementation(function () { downloaded.push(this.download) })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    await act(async () => {
      fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Exporter PDF'))
      await flushPromises(8)
    })
    expect(apiMock.getBlob.mock.calls.map(([p]) => p)).toContain('/exports/session/2/pdf/')
    expect(downloaded[0]).toBe('rapport_s_ance_planifi_e.pdf')
  })

  it('notifie le détail backend si l’export échoue', async () => {
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'Rapport en cours de génération.' } } })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /pdf — toutes séances/i }))
      await flushPromises(8)
    })
    expect(await screen.findByText('Rapport en cours de génération.')).toBeInTheDocument()
  })
})

describe('FormationDetail — QR code des séances (intégration QRCodeModal)', () => {
  // QRCode.toCanvas tente de dessiner sur un canvas (jsdom sans contexte 2D) ;
  // l'erreur est capturée par la modale elle-même. On coupe le bruit attendu.
  let consoleSpy
  beforeEach(() => { consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {}) })
  afterEach(() => consoleSpy.mockRestore())

  it('ouvre la modale QR de la séance avec son module (GET qr session_id/module_id)', async () => {
    apiController.setRoute(`/formations/superviseur/${F}/qr/`, () => ({
      token: 'TOK-F', session: 2, module_id: 77,
      module_intitule: 'LSF Niveau 1 — A1', module_groupe: 'G1',
      session_intitule: 'Séance planifiée',
    }))
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)

    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('QR Code'))
    const box = await screen.findByRole('heading', { name: 'QR Code — Séance' }).then((h) => h.closest('.modal-content'))
    const qrCall = apiMock.get.mock.calls.find(([p]) => p === `/formations/superviseur/${F}/qr/`)
    expect(qrCall[1].params).toEqual({ session_id: 2, module_id: 77 })
    // Le token chargé débloque le téléchargement.
    expect(await within(box).findByRole('button', { name: /télécharger/i })).toBeInTheDocument()
  })
})

describe('FormationDetail — archivage depuis les groupes de séances', () => {
  const goSessions = async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
  }

  it('archive le module au terme des 3 confirmations (POST archive), rien si annulé', async () => {
    await goSessions()
    fireEvent.click(screen.getByTitle('Archiver ce module (3 confirmations)'))
    await screen.findByRole('heading', { name: /archivage du module — étape 1\/3/i })
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(posts((p) => p.endsWith('/archive/'))).toHaveLength(0)

    fireEvent.click(screen.getByTitle('Archiver ce module (3 confirmations)'))
    await screen.findByRole('heading', { name: /étape 1\/3/i })
    fireEvent.click(within(modal()).getByRole('button', { name: 'Continuer' }))
    await screen.findByRole('heading', { name: /étape 2\/3/i })
    fireEvent.click(within(modal()).getByRole('button', { name: 'Je comprends' }))
    await screen.findByRole('heading', { name: /étape 3\/3/i })
    fireEvent.click(within(modal()).getByRole('button', { name: 'Archiver définitivement' }))
    await settle(10)

    expect(posts((p) => p.endsWith('/archive/'))).toEqual([
      { path: `/formations/${F}/modules/77/archive/`, body: undefined },
    ])
    expect(await screen.findByText(/module archivé/i)).toBeInTheDocument()
  })

  it("ne propose pas l'archivage à un ENCADRANT", async () => {
    mount('ENCADRANT')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    expect(screen.queryByTitle('Archiver ce module (3 confirmations)')).not.toBeInTheDocument()
  })

  it("n'affiche pas le bouton archiver pour un groupe « Sans module »", async () => {
    apiController.reset()
    apiController.setRoute(detailPath, () => ({
      ...buildFormation(),
      sessions: [
        { id: 9, numero: 1, intitule: null, module_id: null, module_intitule: null, date: TODAY, heure_debut: '08:00', heure_fin: '10:00', en_cours: false, terminee: false },
      ],
    }))
    apiController.setRoute(formateursPath, () => FORMATEURS)
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    renderWithProviders(<FormationDetail />, {
      authUser: me,
      routePattern: '/formations/:id',
      initialEntries: [`/formations/${F}`],
    })
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(1\)/i)
    expect(screen.getByText('Sans module')).toBeInTheDocument()
    expect(screen.queryByTitle('Archiver ce module (3 confirmations)')).not.toBeInTheDocument()
  })
})

describe('FormationDetail — import Excel des séances (SECRETARIAT)', () => {
  const pickFile = async () => {
    const input = document.querySelector('input[type="file"]')
    const file = new File(['xlsx-binary'], 'seances.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    await act(async () => {
      fireEvent.change(input, { target: { files: [file] } })
      await flushPromises(10)
    })
  }

  it('téléverse le fichier (FormData type/formation_id) et affiche le nombre de séances créées', async () => {
    mount('SECRETARIAT')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    expect(screen.getByRole('button', { name: /importer excel/i })).toBeInTheDocument()

    apiController.setRoute('/formations/import-excel/', () => ({ created: 3, updated: 0, errors: [] }))
    await pickFile()

    const calls = posts((p) => p === '/formations/import-excel/')
    expect(calls).toHaveLength(1)
    const fd = calls[0].body
    expect(fd.get('type')).toBe('seances')
    expect(fd.get('formation_id')).toBe(String(F))
    expect(fd.get('file').name).toBe('seances.xlsx')
    expect(await screen.findByText('3 séance(s) créée(s)')).toBeInTheDocument()
  })

  it("affiche le détail d'erreur backend si l'import échoue", async () => {
    mount('SECRETARIAT')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    apiController.setRoute('/formations/import-excel/', () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Format de fichier invalide.' } } }
    })
    await pickFile()
    expect(await screen.findByText('Format de fichier invalide.')).toBeInTheDocument()
  })

  it("réserve l'import au SECRETARIAT (un ADMIN ne voit pas le bouton)", async () => {
    mount('ADMIN')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    expect(screen.queryByRole('button', { name: /importer excel/i })).not.toBeInTheDocument()
  })
})

describe('FormationDetail — pagination serveur des pickers', () => {
  it('pagine la liste des enseignants disponibles (page=2)', async () => {
    apiController.setRoute('/formations/formateurs/list/', (path) => {
      const query = new URLSearchParams(path.split('?')[1])
      if (query.get('page') === '2') {
        return { count: 60, total_pages: 2, results: [{ id: 230, nom: 'Page', prenom: 'Deux' }] }
      }
      return { count: 60, total_pages: 2, results: [{ id: 202, nom: 'Koffi', prenom: 'Ado' }] }
    })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/enseignants/i)
    fireEvent.click(screen.getByRole('button', { name: /ajouter un enseignant/i }))
    await waitReal()
    const box = modal()
    expect(await within(box).findByText(/Koffi Ado/)).toBeInTheDocument()

    fireEvent.click(within(box).getByLabelText('Page suivante'))
    await waitReal()
    expect(within(box).getByText(/Page Deux/)).toBeInTheDocument()
    expect(within(box).queryByText(/Koffi Ado/)).not.toBeInTheDocument()
  })

  it('pagine la liste des étudiants disponibles (page=2, intervalle 1–50 sur 80)', async () => {
    apiController.setRoute('/formations/participants/list/', (path) => {
      const query = new URLSearchParams(path.split('?')[1])
      if (query.get('page') === '2') {
        return { count: 80, total_pages: 2, results: [{ id: 180, nom: 'PageDeux', prenom: 'Etud' }] }
      }
      return {
        count: 80, total_pages: 2,
        results: [{ id: 103, nom: 'Bamba', prenom: 'Issa', numero_matricule: 'MAT-003' }],
      }
    })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/étudiants \(2\)/i)
    fireEvent.click(screen.getByRole('button', { name: /ajouter un étudiant/i }))
    await waitReal()
    const box = modal()
    expect(await within(box).findByText('Bamba')).toBeInTheDocument()
    expect(within(box).getByText(/1–50 sur 80/)).toBeInTheDocument()

    fireEvent.click(within(box).getByLabelText('Page suivante'))
    await waitReal()
    expect(within(box).getByText('PageDeux')).toBeInTheDocument()
    expect(within(box).queryByText('Bamba')).not.toBeInTheDocument()
  })
})

describe('FormationDetail — états limites et filets d’erreur (LOT 22)', () => {
  const mountWith = (overrides = {}) => {
    apiController.reset()
    apiController.setRoute(detailPath, () => ({ ...buildFormation(), ...overrides }))
    apiController.setRoute(formateursPath, () => overrides.formateurs ?? FORMATEURS)
    const me = makeUser(overrides.__role || 'ADMIN', { username: 'admin' })
    apiController.setMe(me)
    renderWithProviders(<FormationDetail />, {
      authUser: me,
      routePattern: '/formations/:id',
      initialEntries: [`/formations/${F}`],
    })
    return me
  }

  it('affiche un état dédié quand aucune séance n’est planifiée', async () => {
    mountWith({ sessions: [] })
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(0\)/i)
    expect(screen.getByText('Aucune séance planifiée')).toBeInTheDocument()
  })

  it('affiche les états vides des onglets Étudiants et Enseignants', async () => {
    apiController.reset()
    apiController.setRoute(detailPath, () => ({ ...buildFormation(), participants: [], formateurs: [] }))
    apiController.setRoute(formateursPath, () => [])
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    renderWithProviders(<FormationDetail />, {
      authUser: me, routePattern: '/formations/:id', initialEntries: [`/formations/${F}`],
    })
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/étudiants \(0\)/i)
    expect(screen.getByText('Aucun étudiant inscrit')).toBeInTheDocument()
    await goTab(/enseignants \(0\)/i)
    expect(screen.getByText('Aucun enseignant assigné')).toBeInTheDocument()
  })

  it("adapte le libellé des attendus en multi-séances puis pour une séance sélectionnée", async () => {
    apiController.setRoute(dashboardPath, (path) => {
      const base = buildDashboard()
      if (path.includes('session_id=1')) {
        return { ...base, seance_selectionnee_id: 1, total_attendus: 4 }
      }
      return { ...base, nb_seances_jour: 2, nb_inscrits: 4, total_attendus: 8, seance_selectionnee_id: null }
    })
    await openPresences()
    expect(screen.getByText('Inscrits × 2 séances')).toBeInTheDocument()
    expect(screen.getByText('4 inscrits')).toBeInTheDocument()

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } })
    await settle(6)
    expect(screen.getByText('Attendus — Séance du matin')).toBeInTheDocument()
  })

  it('signale les personnes en rattrapage inter-cohortes par un badge', async () => {
    apiController.setRoute(dashboardPath, () => {
      const d = buildDashboard()
      d.absents = [
        { id: 109, nom: 'Bamba', prenom: 'Issa', type_personne: 'participant', matricule: 'MAT-009', rattrapage: true },
      ]
      return d
    })
    await openPresences()
    expect(screen.getByTitle("Étudiant d'une autre cohorte en rattrapage sur cette séance")).toBeInTheDocument()
    expect(screen.getByText('Rattrapage')).toBeInTheDocument()
  })

  it('import Excel : distingue les séances déjà existantes, les erreurs, puis « rien traité »', async () => {
    // Une seule route, qui change de réponse selon le nombre d'envois.
    let envoi = 0
    apiController.setRoute('/formations/import-excel/', () => {
      envoi += 1
      if (envoi === 1) return { created: 0, updated: 2, errors: ['Ligne 3 : date manquante'] }
      return { created: 0, updated: 0, errors: [] }
    })
    mount('SECRETARIAT')
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    const input = document.querySelector('input[type="file"]')

    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['a'], 'upd.xlsx')] } })
      await flushPromises(10)
    })
    // Le badge porte deux fragments texte (bilan + compteur d'erreurs) : regex.
    expect(await screen.findByText(/déjà existante/)).toBeInTheDocument()
    expect(screen.getByText(/1 erreur\(s\)/)).toBeInTheDocument()

    await act(async () => {
      fireEvent.change(input, { target: { files: [new File(['b'], 'vide.xlsx')] } })
      await flushPromises(10)
    })
    expect(await screen.findByText('Aucune séance traitée')).toBeInTheDocument()
  })

  it("refuse la modification d'une séance sans date (garde locale, aucun PATCH)", async () => {
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Modifier'))
    const box = await screen.findByRole('heading', { name: /modifier la séance/i }).then((h) => h.closest('.modal-content'))
    const dateInput = box.querySelector('input[type="date"]')
    // jsdom bloque la soumission native d'un champ required vide : on neutralise
    // la validation pour exercer la garde applicative (showToast + return).
    dateInput.removeAttribute('required')
    fireEvent.change(dateInput, { target: { value: '' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('La date de la séance est obligatoire.')).toBeInTheDocument()
    expect(patches()).toHaveLength(0)
  })

  it("notifie l'impossibilité de charger les enseignants assignés (erreur de liste)", async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    // La route succès est déjà enregistrée par beforeEach : reset puis
    // reprogrammation ciblée (matchRoute choisit la première correspondance).
    apiController.reset()
    apiController.setRoute(detailPath, () => buildFormation())
    apiController.setRoute(formateursPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: {} } }
    })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/enseignants/i)
    expect(await screen.findByText('Impossible de charger les enseignants.')).toBeInTheDocument()
    spy.mockRestore()
  })

  it("garde l'erreur d'assignation de l'encadrant dans la modale", async () => {
    apiController.setRoute('/auth/users/', () => [
      { id: 302, first_name: 'Issa', last_name: 'Bamba', username: 'ibamba' },
    ])
    apiController.setRoute(/\/assign-superviseur\/$/, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Formation clôturée, encadrant non modifiable.' } } }
    })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    fireEvent.click(within(screen.getByText('Encadrant').closest('div')).getByRole('button'))
    await waitReal()
    const box = await screen.findByRole('heading', { name: 'Assigner un encadrant' }).then((h) => h.closest('.modal-content'))
    fireEvent.click(within(box).getByText('ibamba').closest('tr'))
    fireEvent.click(within(box).getByRole('button', { name: 'Assigner' }))
    await settle(8)
    expect(within(box).getByText('Formation clôturée, encadrant non modifiable.')).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).not.toBeNull()
  })

  it('affiche les messages dédiés des pickers quand aucune personne n’est disponible', async () => {
    apiController.setRoute('/formations/formateurs/list/', () => [])
    apiController.setRoute('/formations/participants/list/', () => [])
    mount()
    await screen.findByText('LSF — Promotion 2026')

    await goTab(/enseignants/i)
    fireEvent.click(screen.getByRole('button', { name: /ajouter un enseignant/i }))
    await waitReal()
    expect(within(modal()).getByText('Aucun enseignant disponible')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Fermer' }))
    await settle()

    await goTab(/étudiants \(2\)/i)
    fireEvent.click(screen.getByRole('button', { name: /ajouter un étudiant/i }))
    await waitReal()
    expect(within(modal()).getByText('Aucun étudiant disponible')).toBeInTheDocument()
  })

  it("notifie le détail backend si l'archivage échoue (sans écran de réussite)", async () => {
    apiController.setRoute(/\/archive\/$/, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Des séances ne sont pas soldées.' } } }
    })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    fireEvent.click(screen.getByTitle('Archiver ce module (3 confirmations)'))
    for (const label of ['Continuer', 'Je comprends', 'Archiver définitivement']) {
      await screen.findByRole('heading', { name: /étape/i })
      fireEvent.click(within(modal()).getByRole('button', { name: label }))
    }
    await settle(10)
    expect(await screen.findByText('Des séances ne sont pas soldées.')).toBeInTheDocument()
  })

  it('notifie une erreur de fermeture de session (SORTIE) sans faux succès', async () => {
    apiController.setRoute(dashboardPath, () => buildDashboard())
    apiController.setRoute(forcePath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Hors plage horaire autorisée.' } } }
    })
    await openPresences()
    fireEvent.click(within(screen.getByText('Koné Awa').closest('tr')).getByRole('button', { name: /^fermer/i }))
    const box = await screen.findByRole('heading', { name: 'Fermer la session' }).then((h) => h.closest('.modal-content'))
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Oubli de badgeage' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Confirmer la sortie' }))
    expect(await screen.findByText('Hors plage horaire autorisée.')).toBeInTheDocument()
  })

  it("notifie une erreur d'export d'une séance précise", async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    stubBlobDownload()
    apiMock.getBlob.mockRejectedValueOnce({ response: { status: 500 } })
    mount()
    await screen.findByText('LSF — Promotion 2026')
    await goTab(/séances \(3\)/i)
    await act(async () => {
      fireEvent.click(within(sessionRow('Séance planifiée')).getByTitle('Exporter PDF'))
      await flushPromises(8)
    })
    expect(await screen.findByText('Erreur export PDF séance.')).toBeInTheDocument()
    spy.mockRestore()
  })

  it("renseigne « Formation introuvable » quand le dashboard répond 404", async () => {
    apiController.setRoute(dashboardPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { status: 404 } }
    })
    await openPresences()
    expect(await screen.findByText('Formation introuvable.')).toBeInTheDocument()
  })
})
