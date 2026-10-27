/**
 * Tests du module de cours — onglet Séances et onglet Présences (LOT 16,
 * domaine présence/émargement) : démarrage/fin/suppression/création de séance,
 * statistiques de présence, forçage de pointage unitaire et badgeage en masse.
 * Le LOT 18 complète l'écran : inscription/retrait des étudiants,
 * assignation/retrait des enseignants, édition du module, assignation du
 * superviseur (encadrant) et exports PDF/Excel des feuilles.
 * Le LOT 19 répare l'assignation d'enseignant (prop formateur, §10.12) et le
 * LOT 20 couvre la modale QR des séances (génération/régénération/téléchargement),
 * l'archivage TripleConfirmModal (3 confirmations) et la pagination serveur
 * des pickers.
 *
 * Reste hors périmètre (lots suivants) : l'écran miroir FormationDetail.
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
import ModuleDetail from '@/pages/ModuleDetail'

const F = 10
const M = 77
const TODAY = new Date().toISOString().slice(0, 10)
const fullPath = `/formations/${F}/modules/${M}/full/`
const presencesPath = `/formations/${F}/modules/${M}/presences/`
const forcePath = `/formations/${F}/force-pointage/`
const bulkPath = `/formations/${F}/force-badgeage-étudiants-bulk/`

const PARTICIPANTS = [
  { id: 101, nom: 'Koné', prenom: 'Awa', matricule: 'MAT-001', grade: 'L1' },
  { id: 102, nom: 'Diop', prenom: 'Karim', matricule: 'MAT-002', grade: 'L1' },
]
const FORMATEURS = [{ id: 201, nom: 'Nguessan', prenom: 'Yao', numerobadge: 'F001' }]
const ENCADRANTS = [{ id: 301, nom: 'Traoré', prenom: 'Mariam' }]

const buildModule = () => ({
  id: M,
  intitule: 'LSF Niveau 1 — A1',
  grade: 'L1', groupe: 'G1', statut: 'PLANIFIEE', formation: 'L1 LSF',
  duree_contractuelle_heures: 20, duree_planifiee_heures: 6,
  sessions: [
    { id: 1, numero: 1, intitule: 'Séance du matin', date: TODAY, heure_debut: '08:00', heure_fin: '10:00', en_cours: true, terminee: false, nb_presences: 1, nb_attendus: 4 },
    { id: 2, numero: 2, intitule: 'Séance planifiée', date: TODAY, heure_debut: '10:00', heure_fin: '12:00', en_cours: false, terminee: false, nb_presences: 0, nb_attendus: 4 },
    { id: 3, numero: 1, intitule: 'Séance ancienne', date: '2026-08-01', heure_debut: '08:00', heure_fin: '10:00', en_cours: false, terminee: true, nb_presences: 4, nb_attendus: 4 },
  ],
  participants: PARTICIPANTS,
  formateurs: FORMATEURS,
  encadrants: ENCADRANTS,
  // Une seule présence (Awa) sur la séance en cours du jour.
  presences: [
    {
      participant_id: 101, type_personne: 'participant', session_id: 1,
      session_intitule: 'Séance du matin', date_journee: TODAY,
      nom: 'Koné', prenom: 'Awa', matricule: 'MAT-001',
      timestamp_entree: `${TODAY}T08:00`, timestamp_sortie: `${TODAY}T10:00`,
      duree_minutes: 120, statut: 'PRESENT',
    },
  ],
})

const setupRoutes = () => {
  apiController.setRoute(fullPath, () => buildModule())
  apiController.setRoute(presencesPath, () => ({ presences: buildModule().presences }))
}

const mount = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<ModuleDetail />, {
    authUser: me,
    routePattern: '/formations/:formationId/modules/:moduleId',
    initialEntries: [`/formations/${F}/modules/${M}`],
  })
}
const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }
const posts = (pred) =>
  apiMock.post.mock.calls.filter(([p]) => pred(p)).map(([p, b]) => ({ path: p, body: b }))
const modal = () => document.querySelector('.modal-content')
const sessionRow = (intitule) => screen.getByText(intitule).closest('tr')
const goPresences = async () => {
  fireEvent.click(screen.getByRole('button', { name: /présences \(/i }))
  await settle()
}
const goTab = async (name) => {
  fireEvent.click(screen.getByRole('button', { name }))
  await settle()
}
const statCard = (label) => within(screen.getByText(label).parentElement)
// Les pickers et la recherche inscrite passent par un setTimeout de
// 300/400 ms (debounce) : il faut une horloge réelle.
const waitReal = async (ms = 360) => { await act(async () => { await new Promise((r) => setTimeout(r, ms)) }) }
const patches = () => apiMock.patch.mock.calls.map(([p, b]) => ({ path: p, body: b }))
const deletes = () => apiMock.delete.mock.calls.map(([p]) => p)
const stubBlobDownload = () => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('ModuleDetail — onglet Séances (démarrage/fin/suppression)', () => {
  it('affiche les séances, leurs statuts et les compteurs des onglets', async () => {
    mount()
    expect(await screen.findByText('Séance du matin')).toBeInTheDocument()
    expect(screen.getByText('Séance planifiée')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /séances \(3\)/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /étudiants \(2\)/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /présences \(1\)/i })).toBeInTheDocument()
    // La séance en cours porte le badge correspondant.
    expect(within(sessionRow('Séance du matin')).getByText('En cours')).toBeInTheDocument()
  })

  it('démarre une séance planifiée après confirmation (POST start), notifie et recharge', async () => {
    mount()
    await screen.findByText('Séance planifiée')
    fireEvent.click(within(sessionRow('Séance planifiée')).getByRole('button', { name: /démarrer/i }))

    expect(await screen.findByText(/démarrer la séance/i)).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)

    expect(posts((p) => p.includes('/start/'))).toEqual([
      { path: `/formations/${F}/sessions/2/start/`, body: undefined },
    ])
    expect(await screen.findByText('Séance démarrée')).toBeInTheDocument()
    // Rechargement du module après l'action.
    expect(apiMock.get.mock.calls.filter(([p]) => p === fullPath).length).toBeGreaterThan(1)
  })

  it("n'émet rien si la confirmation de démarrage est annulée", async () => {
    mount()
    await screen.findByText('Séance planifiée')
    fireEvent.click(within(sessionRow('Séance planifiée')).getByRole('button', { name: /démarrer/i }))
    expect(await screen.findByText(/démarrer la séance/i)).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(posts((p) => p.includes('/start/'))).toHaveLength(0)
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })

  it('termine une séance en cours (POST stop)', async () => {
    mount()
    await screen.findByText('Séance du matin')
    fireEvent.click(within(sessionRow('Séance du matin')).getByRole('button', { name: /terminer/i }))
    expect(await screen.findByText(/terminer la séance/i)).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)

    expect(posts((p) => p.includes('/stop/'))).toEqual([
      { path: `/formations/${F}/sessions/1/stop/`, body: undefined },
    ])
    expect(await screen.findByText('Séance terminée')).toBeInTheDocument()
  })

  it('supprime une séance planifiée après confirmation (DELETE), rien si annulé', async () => {
    mount()
    await screen.findByText('Séance planifiée')
    const row = sessionRow('Séance planifiée')

    fireEvent.click(within(row).getByRole('button', { name: 'Supprimer' }))
    expect(await screen.findByText('Supprimer cette séance ?')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(apiMock.delete.mock.calls).toHaveLength(0)

    fireEvent.click(within(row).getByRole('button', { name: 'Supprimer' }))
    expect(await screen.findByText('Supprimer cette séance ?')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)
    expect(apiMock.delete.mock.calls[0][0]).toBe(`/formations/${F}/sessions/2/delete/`)
    expect(await screen.findByText('Séance supprimée')).toBeInTheDocument()
  })

  it('notifie le détail renvoyé si le démarrage échoue', async () => {
    apiController.setRoute(/\/sessions\/\d+\/start\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Salle déjà occupée' } } }
    })
    mount()
    await screen.findByText('Séance planifiée')
    fireEvent.click(within(sessionRow('Séance planifiée')).getByRole('button', { name: /démarrer/i }))
    expect(await screen.findByText(/démarrer la séance/i)).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Salle déjà occupée')).toBeInTheDocument()
  })

  it('crée une séance (POST) avec les champs saisis', async () => {
    mount()
    await screen.findByText('Séance du matin')
    fireEvent.click(screen.getByRole('button', { name: /nouvelle séance/i }))

    const box = modal()
    fireEvent.change(box.querySelector('input[type="text"]'), { target: { value: 'Séance ajoutée' } })
    fireEvent.change(box.querySelector('input[type="date"]'), { target: { value: '2026-09-20' } })
    const times = box.querySelectorAll('input[type="time"]')
    fireEvent.change(times[0], { target: { value: '14:00' } })
    fireEvent.change(times[1], { target: { value: '16:00' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Créer' }))
    await settle(8)

    expect(posts((p) => p.includes('/sessions/new/'))).toEqual([
      {
        path: `/formations/${F}/modules/${M}/sessions/new/`,
        body: {
          intitule: 'Séance ajoutée', date_journee: '2026-09-20',
          heure_debut_prevue: '14:00', heure_fin_prevue: '16:00',
        },
      },
    ])
    expect(await screen.findByText('Séance créée')).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })
})

describe('ModuleDetail — habilitations', () => {
  it("pour un ENCADRANT : démarrage autorisé, mais pas de création/suppression de séance", async () => {
    mount('ENCADRANT')
    await screen.findByText('Séance planifiée')
    expect(within(sessionRow('Séance planifiée')).getByRole('button', { name: /démarrer/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nouvelle séance/i })).not.toBeInTheDocument()
    expect(within(sessionRow('Séance planifiée')).queryByRole('button', { name: 'Supprimer' })).not.toBeInTheDocument()
  })

  it("pour la DIRECTION (lecture) : aucun bouton de supervision", async () => {
    mount('DIRECTION')
    await screen.findByText('Séance planifiée')
    expect(within(sessionRow('Séance planifiée')).queryByRole('button', { name: /démarrer/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /nouvelle séance/i })).not.toBeInTheDocument()
    await goPresences()
    expect(screen.queryByRole('button', { name: /forcer étudiants/i })).not.toBeInTheDocument()
  })
})

describe('ModuleDetail — onglet Présences', () => {
  it('calcule les statistiques (attendus, présents, absents, taux, en salle)', async () => {
    mount()
    await screen.findByText('Séance du matin')
    await goPresences()

    expect(statCard('ATTENDUS').getByText('4')).toBeInTheDocument()
    expect(statCard('EN SALLE').getByText('0')).toBeInTheDocument()
    expect(statCard('PRÉSENTS').getByText('1')).toBeInTheDocument()
    expect(statCard('ABSENTS').getByText('3')).toBeInTheDocument()
    expect(statCard('TAUX PRÉSENCE').getByText('25%')).toBeInTheDocument()

    // Le présent est listé dans la feuille, les trois absents dans la liste dédiée.
    expect(screen.getByText('Koné')).toBeInTheDocument()
    expect(screen.getByText('Étudiants absents')).toBeInTheDocument()
  })

  it("affiche le message d'absence de pointage pour une date sans séance (tout le monde absent)", async () => {
    mount()
    await screen.findByText('Séance du matin')
    await goPresences()

    fireEvent.change(screen.getByDisplayValue(TODAY), { target: { value: '2026-09-30' } })
    expect(await screen.findByText(/aucun pointage enregistré pour cette date/i)).toBeInTheDocument()
    expect(statCard('ATTENDUS').getByText('4')).toBeInTheDocument()
    expect(statCard('ABSENTS').getByText('4')).toBeInTheDocument()
  })

  it('force le badgeage en masse (toutes séances) avec motif obligatoire', async () => {
    apiController.setRoute(bulkPath, () => ({
      detail: 'Forçage en masse terminé',
      sessions: [{ session_intitule: 'Séance du matin', nb_badges: 1, nb_absents: 1, taux_pct: 50 }],
    }))
    mount()
    await screen.findByText('Séance du matin')
    await goPresences()

    fireEvent.click(screen.getByRole('button', { name: /forcer étudiants/i }))
    const box = await screen.findByText('Forcer le badgeage des étudiants').then(() => modal())
    const submit = within(box).getByRole('button', { name: /confirmer le forçage/i })
    expect(submit).toBeDisabled() // motif requis
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Coupure réseau QR' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await settle(8)

    expect(posts((p) => p === bulkPath)).toEqual([
      { path: bulkPath, body: { module_id: M, date_journee: TODAY, motif: 'Coupure réseau QR' } },
    ])
    expect(await screen.findByText(/forçage en masse terminé/i)).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })

  it('force le badgeage en masse sur une séance précise (session_id transmis)', async () => {
    apiController.setRoute(bulkPath, () => ({ detail: 'OK', sessions: [] }))
    mount()
    await screen.findByText('Séance du matin')
    await goPresences()

    // Le filtre de séance n'apparaît que s'il y a des séances ce jour-là ;
    // on cible la séance 1 (la valeur 'ALL' est la sélection par défaut).
    fireEvent.change(screen.getByRole('combobox'), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: /forcer étudiants/i }))
    const box = await screen.findByText('Forcer le badgeage des étudiants').then(() => modal())
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Rattrapage collectif' } })
    fireEvent.click(within(box).getByRole('button', { name: /confirmer le forçage/i }))
    await settle(8)

    expect(posts((p) => p === bulkPath)[0].body).toMatchObject({
      module_id: M, date_journee: TODAY, motif: 'Rattrapage collectif', session_id: 1,
    })
  })

  it('notifie une erreur de forçage en masse sans fermer la modale', async () => {
    apiController.setRoute(bulkPath, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Aucune séance active' } } }
    })
    mount()
    await screen.findByText('Séance du matin')
    await goPresences()
    fireEvent.click(screen.getByRole('button', { name: /forcer étudiants/i }))
    const box = await screen.findByText('Forcer le badgeage des étudiants').then(() => modal())
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'X' } })
    fireEvent.click(within(box).getByRole('button', { name: /confirmer le forçage/i }))
    expect(await screen.findByText('Aucune séance active')).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).not.toBeNull()
  })

  it('force la présence d’un étudiant absent (pointage unitaire) avec le bon payload', async () => {
    apiController.setRoute(forcePath, () => ({ detail: 'Présence forcée — durée planifiée de la séance' }))
    mount()
    await screen.findByText('Séance du matin')
    await goPresences()

    // Karim (102) est absent : on ouvre le forçage depuis sa ligne.
    const absentRow = screen.getByText('Diop').closest('tr')
    fireEvent.click(within(absentRow).getByRole('button', {
      name: /forcer la présence \(durée planifiée de la séance\)/i,
    }))
    const box = await screen.findByText('Forcer un badgeage').then(() => modal())
    expect(within(box).getByText(/Diop Karim/i)).toBeInTheDocument()
    const submit = within(box).getByRole('button', { name: 'Forcer la présence' })
    expect(submit).toBeDisabled()
    fireEvent.change(box.querySelector('textarea'), { target: { value: 'Téléphone en panne' } })
    fireEvent.click(submit)
    await settle(8)

    expect(posts((p) => p === forcePath)).toEqual([
      {
        path: forcePath,
        body: expect.objectContaining({
          personne_id: 102, type_personne: 'participant', action: 'ENTREE',
          motif: 'Téléphone en panne', module_id: String(M), date_journee: TODAY,
        }),
      },
    ])
    expect(await screen.findByText(/présence forcée/i)).toBeInTheDocument()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// LOT 18 — onglets Étudiants / Enseignants / Informations (écritures restantes)
// ─────────────────────────────────────────────────────────────────────────────

describe('ModuleDetail — onglet Étudiants (inscriptions)', () => {
  it('liste les inscrits et filtre par recherche (debounce 400 ms)', async () => {
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/étudiants \(2\)/i)

    expect(screen.getByText('Étudiants inscrits (2)')).toBeInTheDocument()
    expect(screen.getByText('MAT-001')).toBeInTheDocument()
    expect(screen.getByText('MAT-002')).toBeInTheDocument()

    fireEvent.change(
      screen.getByPlaceholderText(/rechercher un étudiant/i),
      { target: { value: 'Diop' } },
    )
    await waitReal(450)
    expect(screen.getByText('Diop')).toBeInTheDocument()
    expect(screen.queryByText('Koné')).not.toBeInTheDocument()
  })

  it('inscrit un étudiant via le picker (POST add), en excluant les déjà inscrits', async () => {
    apiController.setRoute(`/formations/participants/list/`, () => [
      { id: 101, nom: 'Koné', prenom: 'Awa', numero_matricule: 'MAT-001' }, // déjà inscrit → filtré
      { id: 103, nom: 'Bamba', prenom: 'Issa', numero_matricule: 'MAT-003' },
      { id: 104, nom: 'Cissé', prenom: 'Fatou', numero_matricule: 'MAT-004' },
    ])
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/étudiants \(2\)/i)

    fireEvent.click(screen.getByRole('button', { name: /inscrire/i }))
    await waitReal()
    // Les inscrits sont exclus de la liste proposée.
    const box = modal()
    expect(within(box).queryByText('Awa')).not.toBeInTheDocument()
    expect(within(box).getByText('Bamba')).toBeInTheDocument()

    fireEvent.click(within(within(box).getByText('Bamba').closest('tr')).getByRole('button'))
    await settle(8)

    expect(posts((p) => p.includes('/participants/add/'))).toEqual([
      { path: `/formations/${F}/modules/${M}/participants/add/`, body: { participant_id: 103 } },
    ])
    expect(await screen.findByText('Étudiant inscrit')).toBeInTheDocument()
  })

  it("n'inscrit pas un étudiant déjà inscrit : message d'erreur affiché dans la modale", async () => {
    apiController.setRoute(`/formations/participants/list/`, () => [
      { id: 105, nom: 'Yao', prenom: 'Kouam', numero_matricule: 'MAT-005' },
    ])
    apiController.setRoute(/\/participants\/add\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Cet étudiant est déjà inscrit à ce module.' } } }
    })
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/étudiants \(2\)/i)
    fireEvent.click(screen.getByRole('button', { name: /inscrire/i }))
    await waitReal()
    const box = modal()
    fireEvent.click(within(within(box).getByText('Yao').closest('tr')).getByRole('button'))
    expect(await screen.findByText('Cet étudiant est déjà inscrit à ce module.')).toBeInTheDocument()
  })

  it('retire un étudiant après confirmation (DELETE), rien si annulé', async () => {
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/étudiants \(2\)/i)

    const row = screen.getByText('Diop').closest('tr')
    fireEvent.click(within(row).getByTitle('Retirer'))
    expect(await screen.findByText('Retirer Diop Karim de ce module ?')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(deletes()).toHaveLength(0)

    fireEvent.click(within(screen.getByText('Diop').closest('tr')).getByTitle('Retirer'))
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)
    expect(deletes()).toContain(`/formations/${F}/modules/${M}/participants/102/remove/`)
    expect(await screen.findByText('Étudiant retiré')).toBeInTheDocument()
  })

  it("pour la DIRECTION : ni inscription ni retrait (lecture seule)", async () => {
    mount('DIRECTION')
    await screen.findByText('Séance du matin')
    await goTab(/étudiants \(2\)/i)
    expect(screen.queryByRole('button', { name: /inscrire/i })).not.toBeInTheDocument()
    expect(screen.queryByTitle('Retirer')).not.toBeInTheDocument()
    // La liste reste lisible.
    expect(screen.getByText('MAT-001')).toBeInTheDocument()
  })
})

describe('ModuleDetail — onglet Enseignants (assignations)', () => {
  // §10.12 (corrigé au LOT 19) : la page passait la prop `enseignant` alors
  // que le composant lit `formateur` ; la modale plantait dès qu'une ligne
  // était renvoyée. Les parcours ci-dessous sont les tests de régression.
  it('assigne un enseignant disponible via le picker (POST add), en excluant les déjà assignés', async () => {
    apiController.setRoute('/formations/formateurs/list/', (path) => {
      expect(path).toContain(`module_id=${M}`) // préfiltrage par module
      return [
        { id: 201, nom: 'Nguessan', prenom: 'Yao' }, // déjà assigné → filtré
        { id: 202, nom: 'Koffi', prenom: 'Ado', specialite: 'LSF' },
      ]
    })
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/enseignants \(1\)/i)
    expect(screen.getByText('Enseignants assignés')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /assigner/i }))
    await waitReal()
    const box = modal()
    expect(within(box).queryByText(/Nguessan Yao/)).not.toBeInTheDocument()
    expect(within(box).getByText(/Koffi Ado/)).toBeInTheDocument()

    fireEvent.click(within(box).getByTitle('Assigner cet enseignant'))
    await settle(8)
    expect(posts((p) => p.includes('/formateurs/add/'))).toEqual([
      { path: `/formations/${F}/modules/${M}/formateurs/add/`, body: { formateur_id: 202 } },
    ])
    expect(await screen.findByText('Enseignant assigné')).toBeInTheDocument()
    // La modale reste ouverte pour permettre une deuxième assignation.
    expect(within(box).getByText(/Assigner un enseignant/i)).toBeInTheDocument()
  })

  it("en cas de refus backend (conflit d'emploi du temps), le détail reste affiché dans la modale", async () => {
    apiController.setRoute('/formations/formateurs/list/', () => [
      { id: 203, nom: 'Dosso', prenom: 'Awa' },
    ])
    apiController.setRoute(/\/formateurs\/add\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: "Conflit d'emploi du temps sur ce créneau." } } }
    })
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/enseignants \(1\)/i)
    fireEvent.click(screen.getByRole('button', { name: /assigner/i }))
    await waitReal()
    const box = modal()
    fireEvent.click(within(box).getByTitle('Assigner cet enseignant'))
    // Le message d'erreur structuré est rendu dans la fenêtre (pas seulement un toast).
    expect(await within(box).findByText(/conflit d'emploi du temps/i)).toBeInTheDocument()
    expect(within(box).getByText(/Dosso Awa/)).toBeInTheDocument()
    // Aucune assignation n'a été enregistrée.
    expect(posts((p) => p.includes('/formateurs/add/'))).toHaveLength(1)
  })

  it('masque le bouton d’assignation d’un enseignant signalé en conflit (gating §10.12)', async () => {
    apiController.setRoute('/formations/formateurs/list/', () => [
      { id: 204, nom: 'Bile', prenom: 'Eric', conflit_assignation: 'Déjà en salle B2 à 8h.' },
    ])
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/enseignants \(1\)/i)
    fireEvent.click(screen.getByRole('button', { name: /assigner/i }))
    await waitReal()
    const box = modal()
    expect(within(box).getByText(/déjà en salle b2 à 8h/i)).toBeInTheDocument()
    expect(within(box).queryByTitle('Assigner cet enseignant')).not.toBeInTheDocument()
  })

  it('gère une liste vide et transmet le module_id au chargement', async () => {
    apiController.setRoute('/formations/formateurs/list/', (path) => {
      expect(path).toContain(`module_id=${M}`)
      return []
    })
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/enseignants \(1\)/i)
    fireEvent.click(screen.getByRole('button', { name: /assigner/i }))
    await waitReal()
    expect(await screen.findByText('Aucun enseignant trouvé')).toBeInTheDocument()
  })

  it('retire un enseignant après confirmation (DELETE)', async () => {
    mount()
    await screen.findByText('Séance du matin')
    await goTab(/enseignants \(1\)/i)
    fireEvent.click(within(screen.getByText('Nguessan').closest('tr')).getByTitle('Retirer'))
    expect(await screen.findByText('Retirer Nguessan Yao de ce module ?')).toBeInTheDocument()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Confirmer' }))
    await settle(8)
    expect(deletes()).toContain(`/formations/${F}/modules/${M}/formateurs/201/remove/`)
    expect(await screen.findByText('Enseignant retiré')).toBeInTheDocument()
  })
})

describe('ModuleDetail — onglet Informations (édition, superviseur)', () => {
  const goInfo = async () => {
    await screen.findByText('Séance du matin')
    await goTab(/informations/i)
  }

  it('modifie le module (PATCH) avec les champs saisis, ferme et recharge', async () => {
    mount()
    await goInfo()
    fireEvent.click(screen.getByRole('button', { name: 'Modifier' }))
    const box = await screen.findByText('Modifier le module').then(() => modal())

    const intitule = box.querySelectorAll('input[type="text"]')[0]
    fireEvent.change(intitule, { target: { value: 'LSF Niveau 1 — A1 (groupe du matin)' } })
    fireEvent.change(box.querySelector('input[type="number"]'), { target: { value: '24' } })
    fireEvent.click(within(box).getByRole('button', { name: 'Enregistrer' }))
    await settle(8)

    expect(patches()).toEqual([
      {
        path: `/formations/${F}/modules/${M}/`,
        body: expect.objectContaining({
          intitule: 'LSF Niveau 1 — A1 (groupe du matin)',
          duree_prevue_heures: '24',
        }),
      },
    ])
    expect(await screen.findByText('Module modifié')).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })

  it('notifie le détail backend si la modification échoue', async () => {
    apiController.setRoute(new RegExp(`/modules/${M}/$`), () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Chevauchement de salle détecté.' } } }
    })
    mount()
    await goInfo()
    fireEvent.click(screen.getByRole('button', { name: 'Modifier' }))
    const box = await screen.findByText('Modifier le module').then(() => modal())
    fireEvent.click(within(box).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Chevauchement de salle détecté.')).toBeInTheDocument()
  })

  it('assigne un encadrant superviseur (POST assign-superviseur)', async () => {
    apiController.setRoute('/auth/users/', () => [
      { id: 301, first_name: 'Mariam', last_name: 'Traoré', username: 'mtraore', matricule: 'ENC-1' },
    ])
    mount()
    await goInfo()
    fireEvent.click(screen.getByRole('button', { name: /assigner encadrant/i }))
    await waitReal()
    const box = await screen.findByText('Assigner un encadrant').then(() => modal())
    expect(within(box).getByText(/Mariam Traoré/)).toBeInTheDocument()

    // Sélection de la ligne, puis enregistrement.
    fireEvent.click(within(box).getByText('mtraore').closest('tr'))
    fireEvent.click(within(box).getByRole('button', { name: 'Enregistrer' }))
    await settle(8)

    expect(posts((p) => p.includes('/assign-superviseur/'))).toEqual([
      { path: `/formations/${F}/modules/${M}/assign-superviseur/`, body: { superviseur_id: '301' } },
    ])
    expect(await screen.findByText('Encadrant assigné')).toBeInTheDocument()
    expect(document.querySelector('.modal-overlay')).toBeNull()
  })

  it("retire le superviseur en place (superviseur_id null) et affiche l'erreur dans la modale", async () => {
    apiController.reset()
    apiController.setRoute(fullPath, () => ({
      ...buildModule(),
      superviseur_id: 301, superviseur_nom: 'Mariam Traoré',
    }))
    apiController.setRoute(presencesPath, () => ({ presences: [] }))
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    renderWithProviders(<ModuleDetail />, {
      authUser: me,
      routePattern: '/formations/:formationId/modules/:moduleId',
      initialEntries: [`/formations/${F}/modules/${M}`],
    })
    await goInfo()

    fireEvent.click(screen.getByRole('button', { name: /changer encadrant/i }))
    const box = await screen.findByText('Assigner un encadrant').then(() => modal())
    const retirer = within(box).getByRole('button', { name: /retirer l'encadrant/i })
    fireEvent.click(retirer)
    fireEvent.click(within(box).getByRole('button', { name: 'Enregistrer' }))
    await settle(8)

    expect(posts((p) => p.includes('/assign-superviseur/'))).toEqual([
      { path: `/formations/${F}/modules/${M}/assign-superviseur/`, body: { superviseur_id: null } },
    ])
    expect(await screen.findByText('Encadrant retiré')).toBeInTheDocument()
  })

  it("la DIRECTION ne voit pas les boutons d'édition ni d'assignation", async () => {
    mount('DIRECTION')
    await goInfo()
    expect(screen.queryByRole('button', { name: 'Modifier' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /assigner encadrant/i })).not.toBeInTheDocument()
    // Le contenu descriptif reste lisible.
    expect(screen.getByText(/Lieu/)).toBeInTheDocument()
  })
})

describe('ModuleDetail — exports PDF / Excel', () => {
  beforeEach(() => { stubBlobDownload() })

  it('exporte toutes les séances depuis l’en-tête (getBlob module pdf/excel)', async () => {
    mount()
    await screen.findByText('Séance du matin')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /pdf — toutes séances/i }))
      fireEvent.click(screen.getByRole('button', { name: /excel — toutes séances/i }))
      await flushPromises(6)
    })
    const calls = apiMock.getBlob.mock.calls.map(([p]) => p)
    expect(calls).toContain(`/exports/module/${M}/pdf/`)
    expect(calls).toContain(`/exports/module/${M}/excel/`)
  })

  it('exporte une séance précise depuis sa ligne (getBlob session) avec nom dérivé', async () => {
    const downloaded = []
    HTMLAnchorElement.prototype.click.mockImplementation(function () { downloaded.push(this.download) })
    mount()
    await screen.findByText('Séance du matin')
    const row = sessionRow('Séance du matin')
    await act(async () => {
      fireEvent.click(within(row).getByTitle('Exporter PDF'))
      await flushPromises(6)
    })
    expect(apiMock.getBlob.mock.calls.map(([p]) => p)).toContain('/exports/session/1/pdf/')
    expect(downloaded[0]).toBe('rapport_s_ance_du_matin.pdf')
  })

  it("notifie le détail backend si l'export échoue", async () => {
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'Rapport en cours de génération.' } } })
    mount()
    await screen.findByText('Séance du matin')
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /pdf — toutes séances/i }))
      await flushPromises(6)
    })
    expect(await screen.findByText('Rapport en cours de génération.')).toBeInTheDocument()
  })
})

describe('ModuleDetail — QR code, archivage, pagination serveur (LOT 20)', () => {
  describe('QR code des séances (QRCodeModal)', () => {
    // QRCode.toCanvas tente de dessiner sur un <canvas> que jsdom ne prend
    // pas en charge (pas de contexte 2D) ; la promesse est volontairement
    // capturee par la modale. On coupe le bruit console.error attendu.
    let consoleSpy
    beforeEach(() => { consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {}) })
    afterEach(() => consoleSpy.mockRestore())

    const qrPath = `/formations/superviseur/${F}/qr/`
    const openQr = async (sessionLabel) => {
      fireEvent.click(within(sessionRow(sessionLabel)).getByTitle('QR Code'))
      await screen.findByText('QR Code — Séance')
      return modal()
    }

    it('charge le QR actif de la séance (GET qr avec session_id/module_id) et permet le téléchargement PNG', async () => {
      apiController.setRoute(qrPath, () => ({
        token: 'TOK-ACTIF', session: 1, module_id: M,
        module_intitule: 'LSF Niveau 1 — A1', module_groupe: 'G1',
        session_intitule: 'Séance du matin',
      }))
      const downloaded = []
      vi.spyOn(HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,AAA')
      stubBlobDownload()
      HTMLAnchorElement.prototype.click.mockImplementation(function () { downloaded.push(this.download) })

      mount()
      await screen.findByText('Séance du matin')
      const box = await openQr('Séance du matin')

      // Les paramètres axios (et non l'URL) portent la séance et le module.
      const qrCall = apiMock.get.mock.calls.find(([p]) => p === qrPath)
      expect(qrCall[1].params).toEqual({ session_id: 1, module_id: String(M) })
      expect(await within(box).findByRole('button', { name: /télécharger/i })).toBeInTheDocument()
      expect(within(box).getByRole('button', { name: /régénérer/i })).toBeInTheDocument()
      expect(within(box).queryByRole('button', { name: /générer le qr code/i })).not.toBeInTheDocument()

      fireEvent.click(within(box).getByRole('button', { name: /télécharger/i }))
      expect(downloaded).toEqual(['qr_seance_10_1.png'])
    })

    it("sans QR actif (404), affiche l'état vide puis génère le QR (POST generate-qr)", async () => {
      apiController.setRoute(qrPath, () => {
        // eslint-disable-next-line no-throw-literal
        throw { response: { status: 404 } }
      })
      apiController.setRoute(/\/generate-qr\/$/, () => ({ token: 'TOK-NEW', session: 2 }))

      mount()
      await screen.findByText('Séance du matin')
      const box = await openQr('Séance planifiée')

      expect(await within(box).findByText(/aucun qr code actif/i)).toBeInTheDocument()
      fireEvent.click(within(box).getByRole('button', { name: /générer le qr code/i }))
      await settle(8)

      expect(await within(box).findByRole('button', { name: /télécharger/i })).toBeInTheDocument()
      expect(posts((p) => p.includes('/generate-qr/'))).toEqual([
        { path: `/formations/${F}/sessions/2/generate-qr/`, body: { module_id: String(M) } },
      ])
    })

    it('demande confirmation avant de régénérer (le QR précédent est invalidé)', async () => {
      apiController.setRoute(qrPath, () => ({ token: 'TOK-OLD', session: 1 }))
      apiController.setRoute(/\/generate-qr\/$/, () => ({ token: 'TOK-NEW', session: 1 }))

      mount()
      await screen.findByText('Séance du matin')
      const box = await openQr('Séance du matin')
      fireEvent.click(await within(box).findByRole('button', { name: /régénérer/i }))

      // La ConfirmModal s'empile au-dessus de la modale QR (deuxième .modal-content).
      await screen.findByText(/régénérer le qr code \?/i)
      const boxes = document.querySelectorAll('.modal-content')
      const confirmBox = boxes[boxes.length - 1]
      fireEvent.click(within(confirmBox).getByRole('button', { name: 'Régénérer' }))
      await settle(8)

      const calls = posts((p) => p.includes('/generate-qr/'))
      expect(calls).toHaveLength(1)
      expect(calls[0]).toEqual({ path: `/formations/${F}/sessions/1/generate-qr/`, body: { module_id: String(M) } })
    })

    it("refuse d'afficher un QR appartenant à un autre module (garde-fou anti-course)", async () => {
      apiController.setRoute(qrPath, () => ({
        token: 'TOK-AUTRE', session: 1, module_id: 999,
        module_intitule: 'Grammaire avancée', module_groupe: 'G9',
      }))
      mount()
      await screen.findByText('Séance du matin')
      const box = await openQr('Séance du matin')
      expect(await within(box).findByText(/QR refusé/i)).toHaveTextContent(/Grammaire avancée/)
      expect(within(box).queryByRole('button', { name: /télécharger/i })).not.toBeInTheDocument()
    })

    it("affiche le détail backend si la génération échoue (aucune fausse réussite)", async () => {
      apiController.setRoute(qrPath, () => {
        // eslint-disable-next-line no-throw-literal
        throw { response: { status: 404 } }
      })
      apiController.setRoute(/\/generate-qr\/$/, () => {
        // eslint-disable-next-line no-throw-literal
        throw { response: { status: 400, data: { detail: 'Séance déjà terminée.' } } }
      })
      mount()
      await screen.findByText('Séance du matin')
      const box = await openQr('Séance planifiée')
      fireEvent.click(await within(box).findByRole('button', { name: /générer le qr code/i }))
      expect(await within(box).findByText('Séance déjà terminée.')).toBeInTheDocument()
      expect(within(box).queryByRole('button', { name: /télécharger/i })).not.toBeInTheDocument()
    })

    it('ne propose pas de QR pour une séance terminée', async () => {
      mount()
      await screen.findByText('Séance du matin')
      expect(within(sessionRow('Séance ancienne')).queryByTitle('QR Code')).not.toBeInTheDocument()
      expect(within(sessionRow('Séance ancienne')).getByText('Terminé')).toBeInTheDocument()
    })
  })

  describe('Archivage du module (TripleConfirmModal)', () => {
    const archivePath = `/formations/${F}/modules/${M}/archive/`
    const goThroughConfirm = async () => {
      await screen.findByText(/étape 1\/3/i)
      fireEvent.click(within(modal()).getByRole('button', { name: 'Continuer' }))
      await screen.findByText(/étape 2\/3/i)
      fireEvent.click(within(modal()).getByRole('button', { name: 'Je comprends' }))
      await screen.findByText(/étape 3\/3/i)
      fireEvent.click(within(modal()).getByRole('button', { name: 'Archiver définitivement' }))
      await settle(8)
    }

    it('archive le module au terme des 3 confirmations (POST archive) et notifie', async () => {
      mount()
      await screen.findByText('Séance du matin')
      fireEvent.click(screen.getByTitle('Archiver ce module (3 confirmations)'))
      await goThroughConfirm()
      const calls = posts((p) => p.endsWith('/archive/'))
      expect(calls).toHaveLength(1)
      expect(calls[0].path).toBe(archivePath)
      expect(await screen.findByText(/module archivé/i)).toBeInTheDocument()
      expect(document.querySelector('.modal-overlay')).toBeNull()
    })

    it("l'annulation à la première étape ferme la modale sans rien poster", async () => {
      mount()
      await screen.findByText('Séance du matin')
      fireEvent.click(screen.getByTitle('Archiver ce module (3 confirmations)'))
      await screen.findByText(/étape 1\/3/i)
      fireEvent.click(within(modal()).getByRole('button', { name: 'Annuler' }))
      await settle()
      expect(posts((p) => p.endsWith('/archive/'))).toHaveLength(0)
      expect(document.querySelector('.modal-overlay')).toBeNull()
    })

    it("affiche le détail backend si l'archivage échoue (sans écran de réussite)", async () => {
      apiController.setRoute(/\/archive\/$/, () => {
        // eslint-disable-next-line no-throw-literal
        throw { response: { data: { detail: 'Module non soldé : des décisions sont en attente.' } } }
      })
      mount()
      await screen.findByText('Séance du matin')
      fireEvent.click(screen.getByTitle('Archiver ce module (3 confirmations)'))
      await goThroughConfirm()
      expect(await screen.findByText(/module non soldé/i)).toBeInTheDocument()
      expect(posts((p) => p.endsWith('/archive/'))).toHaveLength(1)
    })

    it("masque le bouton si le module est déjà archivé", async () => {
      apiController.reset()
      apiController.setRoute(fullPath, () => ({ ...buildModule(), archived: true }))
      apiController.setRoute(presencesPath, () => ({ presences: [] }))
      const me = makeUser('ADMIN', { username: 'admin' })
      apiController.setMe(me)
      renderWithProviders(<ModuleDetail />, {
        authUser: me,
        routePattern: '/formations/:formationId/modules/:moduleId',
        initialEntries: [`/formations/${F}/modules/${M}`],
      })
      await screen.findByText('Séance du matin')
      expect(screen.queryByTitle('Archiver ce module (3 confirmations)')).not.toBeInTheDocument()
    })

    it("réserve l'archivage aux rôles habilités (un ENCADRANT ne voit pas le bouton)", async () => {
      mount('ENCADRANT')
      await screen.findByText('Séance du matin')
      expect(screen.queryByTitle('Archiver ce module (3 confirmations)')).not.toBeInTheDocument()
    })
  })

  describe('Pagination serveur des pickers', () => {
    it("pagine la liste des enseignants disponibles : la page suivante porte page=2, la réouverture revient page 1", async () => {
      const pagesRequested = []
      apiController.setRoute('/formations/formateurs/list/', (path) => {
        const query = new URLSearchParams(path.split('?')[1])
        pagesRequested.push(query.get('page'))
        if (query.get('page') === '2') {
          return { count: 60, total_pages: 2, results: [{ id: 230, nom: 'Page', prenom: 'Deux' }] }
        }
        return { count: 60, total_pages: 2, results: [{ id: 202, nom: 'Koffi', prenom: 'Ado' }] }
      })
      mount()
      await screen.findByText('Séance du matin')
      await goTab(/enseignants \(1\)/i)
      fireEvent.click(screen.getByRole('button', { name: /assigner/i }))
      await waitReal()
      const box = modal()
      expect(await within(box).findByText(/Koffi Ado/)).toBeInTheDocument()

      fireEvent.click(within(box).getByLabelText('Page suivante'))
      await waitReal()
      expect(within(box).getByText(/Page Deux/)).toBeInTheDocument()
      expect(within(box).queryByText(/Koffi Ado/)).not.toBeInTheDocument()
      expect(pagesRequested).toContain('2')

      // Réouverture : le compteur de page est réinitialisé.
      fireEvent.click(within(box).getByRole('button', { name: 'Fermer' }))
      await settle()
      fireEvent.click(screen.getByRole('button', { name: /assigner/i }))
      await waitReal()
      expect(await within(modal()).findByText(/Koffi Ado/)).toBeInTheDocument()
      expect(within(modal()).queryByText(/Page Deux/)).not.toBeInTheDocument()
    })

    it('pagine la liste des étudiants disponibles du picker (page=2 portée dans la requête)', async () => {
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
      await screen.findByText('Séance du matin')
      await goTab(/étudiants \(2\)/i)
      fireEvent.click(screen.getByRole('button', { name: /inscrire/i }))
      await waitReal()
      const box = modal()
      expect(await within(box).findByText('Bamba')).toBeInTheDocument()
      expect(within(box).getByText(/1–50 sur 80/)).toBeInTheDocument()

      fireEvent.click(within(box).getByLabelText('Page suivante'))
      await waitReal()
      expect(within(box).getByText('PageDeux')).toBeInTheDocument()
      expect(within(box).queryByText('Bamba')).not.toBeInTheDocument()

      const lastCall = apiMock.get.mock.calls
        .filter(([p]) => p.startsWith('/formations/participants/list/'))
        .pop()
      expect(lastCall[0]).toContain('page=2')
    })
  })
})
