/**
 * LOT 16 — complétion des écritures des campagnes d'admission.
 *
 * Le LOT 8 (scolariteActions.test.jsx) couvrait la transition Planifier/Ouvrir
 * et l'enregistrement d'une note. Ce fichier couvre le reste du domaine :
 *  - Campagnes : CRÉATION d'une campagne en brouillon (formulaire, typage du
 *    payload, réinitialisation, échec), transitions restantes du workflow
 *    (Suspendre/Clôturer/Réouvrir/Archiver, avec et sans confirmation) et
 *    lecture seule pour la direction ;
 *  - CampagneDetail : AJOUT d'épreuve (payload typé, valeurs par défaut,
 *    échec), génération des convocations, verrouillage des résultats,
 *    calcul/publication du classement, épreuve verrouillée exclue de la saisie
 *    de note, campagne fermée, lecture seule.
 *
 * Le LOT 17 (feu vert explicite, §10.11) corrige les deux constats relevés en
 * LOT 16 : les quotas sont désormais saisissables à la création (et transmis
 * en nombres), et la carte de saisie de notes / calcul-publication du
 * classement est masquée sur une campagne fermée. Les tests correspondants
 * sont des tests de régression.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
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

import Campagnes from '@/pages/scolarite/Campagnes'
import CampagneDetail from '@/pages/scolarite/CampagneDetail'

const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }
const writes = (method) =>
  apiMock[method].mock.calls.map(([p, body]) => ({ path: p, body }))

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
})
afterEach(() => { vi.restoreAllMocks() })

const mountCampagnes = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role === 'ADMIN' ? 'admin' : 'direction' })
  apiController.setMe(me)
  return renderWithProviders(<Campagnes />, {
    authUser: me,
    routePattern: '/scolarite/campagnes',
    initialEntries: ['/scolarite/campagnes'],
  })
}

const setupCampagnesRoutes = (list) => {
  apiController.setRoute('/scolarite/ref/annees/', () => [
    { id: 1, libelle: '2025-2026' }, { id: 2, libelle: '2024-2025' },
  ])
  apiController.setRoute('/scolarite/ref/formations/', () => [
    { id: 10, intitule: 'L1 LSF' }, { id: 11, intitule: 'L2 LSF' },
  ])
  apiController.setRoute('/admissions/campagnes/', list)
}

const nouvelleCampagneCard = () => screen.getByText('Nouvelle campagne').closest('.card')

describe('Campagnes — création en brouillon', () => {
  it('crée une campagne avec les champs typés, notifie, réinitialise et recharge', async () => {
    setupCampagnesRoutes(() => [
      { id: 1, libelle: 'Ancienne campagne', statut: 'BROUILLON', nb_candidatures: 0 },
    ])
    mountCampagnes()
    await settle()

    const card = nouvelleCampagneCard()
    fireEvent.change(within(card).getByPlaceholderText('Libellé'), { target: { value: 'Concours 2026' } })
    const [comboAnnee, comboFormation] = within(card).getAllByRole('combobox')
    fireEvent.change(comboAnnee, { target: { value: '1' } })
    fireEvent.change(comboFormation, { target: { value: '10' } })
    // Les deux seuls champs date du formulaire (les selects vides ont aussi
    // une valeur d'affichage '', donc on les cible par type d'input).
    const [dateOuverture, dateFermeture] = card.querySelectorAll('input[type="date"]')
    fireEvent.change(dateOuverture, { target: { value: '2026-03-01' } })
    fireEvent.change(dateFermeture, { target: { value: '2026-04-30' } })
    // Quotas (régression §10.11 : ils étaient absents du formulaire au LOT 16).
    const [quotaAdmissibles, quotaAdmis] = card.querySelectorAll('input[type="number"]')
    fireEvent.change(quotaAdmissibles, { target: { value: '30' } })
    fireEvent.change(quotaAdmis, { target: { value: '25' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Créer' }))
    await settle(8)

    const posts = writes('post').filter(w => w.path === '/admissions/campagnes/')
    expect(posts).toHaveLength(1)
    expect(posts[0].body).toMatchObject({
      libelle: 'Concours 2026',
      annee_academique_id: 1,
      ref_formation_id: 10,
      date_ouverture: '2026-03-01',
      date_fermeture: '2026-04-30',
      // Les quotas sont numérisés comme les identifiants.
      quota_admissibles: 30,
      quota_admis: 25,
    })

    expect(await screen.findByText('Campagne créée en brouillon.')).toBeInTheDocument()
    // Formulaire réinitialisé, quotas compris.
    expect(within(card).getByPlaceholderText('Libellé')).toHaveValue('')
    expect(quotaAdmissibles).toHaveValue(null)
    expect(quotaAdmis).toHaveValue(null)
    // Liste rechargée après création.
    const listGets = apiMock.get.mock.calls.filter(([p]) => p === '/admissions/campagnes/')
    expect(listGets.length).toBeGreaterThan(1)
  })

  it('laisse les quotas optionnels : non saisis, ils ne sont pas transmis (undefined)', async () => {
    setupCampagnesRoutes(() => [])
    mountCampagnes()
    await settle()

    const card = nouvelleCampagneCard()
    fireEvent.change(within(card).getByPlaceholderText('Libellé'), { target: { value: 'Sans quotas' } })
    const [comboAnnee, comboFormation] = within(card).getAllByRole('combobox')
    fireEvent.change(comboAnnee, { target: { value: '1' } })
    fireEvent.change(comboFormation, { target: { value: '10' } })
    // Aucune valeur dans les deux champs quota.
    fireEvent.click(within(card).getByRole('button', { name: 'Créer' }))
    await settle(8)

    const body = writes('post').find(w => w.path === '/admissions/campagnes/').body
    expect(body.quota_admissibles).toBeUndefined()
    expect(body.quota_admis).toBeUndefined()
  })

  it("sur erreur serveur, notifie et conserve le libellé saisi", async () => {
    setupCampagnesRoutes((path, body) => {
      // Le mock ne distingue pas la méthode : un corps présent = le POST de
      // création, un GET de liste arrive sans corps.
      if (body) {
        // eslint-disable-next-line no-throw-literal
        throw { response: { data: { error: 'Libellé déjà utilisé.' } } }
      }
      return []
    })
    mountCampagnes()
    await settle()

    const card = nouvelleCampagneCard()
    fireEvent.change(within(card).getByPlaceholderText('Libellé'), { target: { value: 'Doublon' } })
    // Les deux selects sont « required » : la validation native bloquerait la
    // soumission sinon (jsdom n'émet pas 'submit' sur un formulaire invalide).
    const [comboAnnee, comboFormation] = within(card).getAllByRole('combobox')
    fireEvent.change(comboAnnee, { target: { value: '1' } })
    fireEvent.change(comboFormation, { target: { value: '10' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Créer' }))
    await settle(8)

    expect(await screen.findByText('Libellé déjà utilisé.')).toBeInTheDocument()
    expect(within(card).getByPlaceholderText('Libellé')).toHaveValue('Doublon')
  })

  it('ne restitue ni formulaire de création ni actions pour la direction (lecture seule)', async () => {
    setupCampagnesRoutes(() => [
      { id: 1, libelle: 'Camp B', statut: 'BROUILLON', nb_candidatures: 0 },
    ])
    mountCampagnes('DIRECTION')
    await settle()
    expect(screen.queryByText('Nouvelle campagne')).not.toBeInTheDocument()
    expect(screen.getByText('Camp B')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Planifier' })).not.toBeInTheDocument()
    // Les référentiels ne sont pas chargés pour un profil en lecture.
    expect(apiMock.get.mock.calls.some(([p]) => p.startsWith('/scolarite/ref/'))).toBe(false)
  })
})

describe('Campagnes — transitions de statut restantes', () => {
  const CAMPAGNES = [
    { id: 1, libelle: 'Camp ouverte', statut: 'OUVERTE', nb_candidatures: 3 },
    { id: 2, libelle: 'Camp suspendue', statut: 'SUSPENDUE', nb_candidatures: 1 },
    { id: 3, libelle: 'Camp cloturée', statut: 'CLOTUREE', nb_candidatures: 5 },
  ]

  it('Suspendre et Réouvrir/Archiver sans confirmation ; Clôturer exige une confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    setupCampagnesRoutes(() => CAMPAGNES)
    mountCampagnes()
    await settle()

    // OUVERTE : Suspendre (pas de confirmation), puis Clôturer (confirm).
    const rowOuverte = screen.getByText('Camp ouverte').closest('tr')
    fireEvent.click(within(rowOuverte).getByRole('button', { name: 'Suspendre' }))
    await settle()
    fireEvent.click(within(rowOuverte).getByRole('button', { name: 'Clôturer' }))
    await settle()

    // SUSPENDUE : Réouvrir sans confirmation.
    fireEvent.click(within(screen.getByText('Camp suspendue').closest('tr'))
      .getByRole('button', { name: 'Réouvrir' }))
    await settle()

    // CLOTUREE : Archiver sans confirmation.
    fireEvent.click(within(screen.getByText('Camp cloturée').closest('tr'))
      .getByRole('button', { name: 'Archiver' }))
    await settle()

    const transitions = writes('post').filter(w => w.path.includes('/transition/'))
    expect(transitions.map(t => t.body.statut)).toEqual([
      'SUSPENDUE', 'CLOTUREE', 'OUVERTE', 'ARCHIVEE',
    ])
    // Deux actions sur la campagne 1 (suspendre puis clôturer), puis 2 et 3.
    expect(transitions.map(t => t.path)).toEqual([1, 1, 2, 3].map(id => `/admissions/campagnes/${id}/transition/`))
    // Une seule confirmation sur les 4 actions : la clôture.
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(confirmSpy.mock.calls[0][0]).toMatch(/plus aucune candidature/i)
  })

  it("annuler la clôture n'émet aucune transition", async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    setupCampagnesRoutes(() => [CAMPAGNES[0]])
    mountCampagnes()
    await settle()
    fireEvent.click(within(screen.getByText('Camp ouverte').closest('tr'))
      .getByRole('button', { name: 'Clôturer' }))
    await settle()
    expect(writes('post')).toHaveLength(0)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// CampagneDetail
// ─────────────────────────────────────────────────────────────────────────────

const CAMP = {
  id: 1, libelle: 'Concours L1 2026', statut: 'PLANIFIEE',
  nb_candidatures: 2, nb_epreuves: 2, quota_admissibles: 30,
  epreuves: [
    { id: 5, intitule: 'Écrit général', type: 'ECRIT', date: '2026-03-10', heure_debut: '08:00', duree_minutes: 120, coefficient: 2, nb_convocations: 4, verrouillee: false },
    { id: 6, intitule: 'Oral', type: 'ORAL', date: '2026-03-11', heure_debut: '10:00', duree_minutes: 30, coefficient: 1, nb_convocations: 2, verrouillee: true },
  ],
}
const CANDIDATURES = [
  { id: 8, campagne_id: 1, numero: 'C008', candidat: 'Awa Koné' },
  { id: 9, campagne_id: 1, numero: 'C009', candidat: 'Karim Diop' },
  { id: 10, campagne_id: 2, numero: 'C010', candidat: 'Autre campagne' },
]
const CLASSEMENT = [
  { rang: 1, candidature: 'C008', candidat: 'Awa Koné', score_total: 16.5, liste: 'ADMISSIBLE', publie: true },
  { rang: 2, candidature: 'C009', candidat: 'Karim Diop', score_total: 11, liste: 'LISTE_ATTENTE', publie: true },
  { rang: 3, candidature: 'C011', candidat: 'Mariam Traoré', score_total: 7, liste: 'NON_ADMIS', publie: false },
]

const mountDetail = (role = 'ADMIN', camp = CAMP) => {
  apiController.setRoute('/scolarite/ref/salles/', () => [
    { id: 20, nom: 'Salle A', capacite: 50 },
    { id: 21, nom: 'Salle B', capacite: 20 },
  ])
  // GET du classement uniquement : les écritures ont des sous-chemins dédiés.
  apiController.setRoute(/classement\/$/, () => CLASSEMENT)
  apiController.setRoute(/classement\/(calculer|publier)\/$/, () => ({ detail: 'Classement calculé' }))
  apiController.setRoute(/\/admissions\/campagnes\/\d+\/$/, () => camp)
  apiController.setRoute('/admissions/candidatures/', () => CANDIDATURES)

  const me = makeUser(role, { username: role === 'ADMIN' ? 'admin' : 'direction' })
  apiController.setMe(me)
  return renderWithProviders(<CampagneDetail />, {
    authUser: me,
    routePattern: '/scolarite/campagnes/:id',
    initialEntries: ['/scolarite/campagnes/1'],
  })
}

const epreuvesCard = () => screen.getByText('Épreuves de concours').closest('.card')
const notesCard = () => screen.getByText('Saisie des notes').closest('.card')

describe('CampagneDetail — rendu du concours', () => {
  it('affiche les compteurs, les épreuves, le classement et masque une épreuve verrouillée de la saisie', async () => {
    mountDetail()
    expect(await screen.findByText('Concours L1 2026')).toBeInTheDocument()
    expect(screen.getByText(/2 candidature\(s\) · 2 épreuve\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/quota admissibles : 30/)).toBeInTheDocument()

    // Épreuves : détails rendus + badge verrouillée.
    expect(screen.getByText('Écrit général')).toBeInTheDocument()
    expect(screen.getByText(/120 min/)).toBeInTheDocument()
    expect(screen.getByText(/4 convocation\(s\)/)).toBeInTheDocument()
    expect(screen.getByText('verrouillée')).toBeInTheDocument()

    // Classement : rangs, scores, badges de liste, publication.
    expect(screen.getByText('Awa Koné')).toBeInTheDocument()
    expect(screen.getByText('16.5')).toBeInTheDocument()
    expect(screen.getByText('ADMISSIBLE')).toBeInTheDocument()
    expect(screen.getByText('LISTE_ATTENTE')).toBeInTheDocument()
    expect(screen.getByText('NON_ADMIS')).toBeInTheDocument()
    const publie = screen.getAllByText('oui')
    expect(publie).toHaveLength(2)
    expect(screen.getByText('non')).toBeInTheDocument()

    // Seule l'épreuve non verrouillée est proposée à la saisie de note.
    const comboEpreuves = within(notesCard()).getAllByRole('combobox')[0]
    expect(within(comboEpreuves).getByText(/Écrit général/)).toBeInTheDocument()
    expect(within(comboEpreuves).queryByText(/Oral/)).not.toBeInTheDocument()
    // Les candidatures d'autres campagnes ne sont pas proposées.
    expect(within(notesCard()).queryByText(/Autre campagne/)).not.toBeInTheDocument()
  })
})

describe('CampagneDetail — ajout d’épreuve', () => {
  it('ajoute une épreuve orale en salle avec le payload typé, notifie et réinitialise', async () => {
    mountDetail()
    await screen.findByText('Concours L1 2026')

    const card = epreuvesCard()
    const combos = within(card).getAllByRole('combobox')
    fireEvent.change(combos[0], { target: { value: 'ORAL' } })   // type
    fireEvent.change(combos[1], { target: { value: '20' } })    // salle
    fireEvent.change(within(card).getByPlaceholderText('Intitulé'), { target: { value: 'Entretien individuel' } })
    fireEvent.change(card.querySelector('input[type="date"]'), { target: { value: '2026-03-12' } })
    fireEvent.change(card.querySelector('input[type="time"]'), { target: { value: '14:00' } })
    fireEvent.click(within(card).getByRole('button', { name: '+' }))
    await settle(8)

    const posts = writes('post').filter(w => w.path.endsWith('/epreuves/'))
    expect(posts).toHaveLength(1)
    expect(posts[0]).toEqual({
      path: '/admissions/campagnes/1/epreuves/',
      body: {
        type: 'ORAL', intitule: 'Entretien individuel', date: '2026-03-12',
        heure_debut: '14:00', duree_minutes: 60, salle_id: 20, coefficient: 1,
      },
    })
    expect(await screen.findByText('Épreuve ajoutée.')).toBeInTheDocument()
    expect(within(card).getByPlaceholderText('Intitulé')).toHaveValue('')
  })

  it("sans salle choisie, salle_id reste undefined (valeurs par défaut conservées)", async () => {
    mountDetail()
    await screen.findByText('Concours L1 2026')
    const card = epreuvesCard()
    fireEvent.change(within(card).getByPlaceholderText('Intitulé'), { target: { value: 'Épreuve sans salle' } })
    fireEvent.change(card.querySelector('input[type="date"]'), { target: { value: '2026-03-13' } })
    fireEvent.click(within(card).getByRole('button', { name: '+' }))
    await settle(8)

    const body = writes('post').find(w => w.path.endsWith('/epreuves/')).body
    expect(body).toMatchObject({
      type: 'ECRIT', intitule: 'Épreuve sans salle', date: '2026-03-13',
      heure_debut: '08:00', duree_minutes: 60, coefficient: 1,
    })
    expect(body.salle_id).toBeUndefined()
  })

  it("sur échec, affiche le détail JSON du serveur et conserve le formulaire", async () => {
    apiController.setRoute(/\/epreuves\/$/, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { date: ['Une épreuve existe déjà à cette date.'] } } }
    })
    mountDetail()
    await screen.findByText('Concours L1 2026')
    const card = epreuvesCard()
    fireEvent.change(within(card).getByPlaceholderText('Intitulé'), { target: { value: 'Conflit' } })
    fireEvent.change(within(card).getByDisplayValue(''), { target: { value: '2026-03-10' } })
    fireEvent.click(within(card).getByRole('button', { name: '+' }))

    expect(await screen.findByText(/une épreuve existe déjà/i)).toBeInTheDocument()
    expect(within(card).getByPlaceholderText('Intitulé')).toHaveValue('Conflit')
  })
})

describe('CampagneDetail — actions sur épreuves et classement', () => {
  it('génère les convocations après confirmation (rien si annulé)', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mountDetail()
    await screen.findByText('Concours L1 2026')

    const epreuveRow = screen.getByText('Écrit général').closest('.d-flex')
    fireEvent.click(within(epreuveRow).getByRole('button', { name: 'Convocations' }))
    await settle()
    expect(writes('post').filter(w => w.path.includes('convocations'))).toHaveLength(0)

    confirmSpy.mockReturnValue(true)
    fireEvent.click(within(epreuveRow).getByRole('button', { name: 'Convocations' }))
    await settle(8)
    expect(writes('post').filter(w => w.path === '/admissions/epreuves/5/convocations/generer/'))
      .toHaveLength(1)
    expect(confirmSpy.mock.calls[1][0]).toMatch(/générer les convocations/i)
    expect(await screen.findByText('Opération effectuée.')).toBeInTheDocument()
  })

  it('verrouille les résultats après confirmation d’irréversibilité', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    mountDetail()
    await screen.findByText('Concours L1 2026')
    const epreuveRow = screen.getByText('Écrit général').closest('.d-flex')
    fireEvent.click(within(epreuveRow).getByRole('button', { name: 'Verrouiller' }))
    await settle(8)
    expect(writes('post').map(w => w.path)).toContain('/admissions/epreuves/5/verrouiller/')
  })

  it('ne propose ni convocations ni verrouillage sur une épreuve déjà verrouillée', async () => {
    mountDetail()
    await screen.findByText('Concours L1 2026')
    // « Oral » apparaît aussi comme <option> du sélecteur de type : on prend
    // le <strong> de la ligne d'épreuve, qui porte l'ancêtre .d-flex.
    const rowVerrouillee = screen.getAllByText('Oral')
      .map(n => n.closest('.d-flex')).find(Boolean)
    expect(within(rowVerrouillee).queryByRole('button', { name: 'Convocations' })).not.toBeInTheDocument()
    expect(within(rowVerrouillee).queryByRole('button', { name: 'Verrouiller' })).not.toBeInTheDocument()
  })

  it('calcule le classement sans confirmation et publie les listes avec confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mountDetail()
    await screen.findByText('Concours L1 2026')

    fireEvent.click(screen.getByRole('button', { name: /calculer le classement/i }))
    await settle(8)
    expect(writes('post').map(w => w.path)).toContain('/admissions/campagnes/1/classement/calculer/')
    expect(confirmSpy).not.toHaveBeenCalled()

    // Publication : confirmation obligatoire, d'abord annulée.
    fireEvent.click(screen.getByRole('button', { name: /publier les listes/i }))
    await settle()
    expect(writes('post').some(w => w.path.includes('classement/publier'))).toBe(false)
    confirmSpy.mockReturnValue(true)
    fireEvent.click(screen.getByRole('button', { name: /publier les listes/i }))
    await settle(8)
    expect(writes('post').map(w => w.path)).toContain('/admissions/campagnes/1/classement/publier/')
    expect(confirmSpy.mock.calls.at(-1)[0]).toMatch(/plus de recalcul possible/i)
  })

  it('échec d’une action d’épreuve : le message d’erreur serveur est notifié', async () => {
    apiController.setRoute(/verrouiller\/$/, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Des notes sont manquantes.' } } }
    })
    mountDetail()
    await screen.findByText('Concours L1 2026')
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const epreuveRow = screen.getByText('Écrit général').closest('.d-flex')
    fireEvent.click(within(epreuveRow).getByRole('button', { name: 'Verrouiller' }))
    expect(await screen.findByText('Des notes sont manquantes.')).toBeInTheDocument()
  })
})

describe('CampagneDetail — états fermés et habilitations', () => {
  it('campagne clôturée : plus d’ajout d’épreuve ni d’actions d’épreuve', async () => {
    const campFermee = { ...CAMP, statut: 'CLOTUREE' }
    mountDetail('ADMIN', campFermee)
    await screen.findByText('Concours L1 2026')

    // Le formulaire d'ajout d'épreuve disparaît…
    expect(within(epreuvesCard()).queryByRole('button', { name: '+' })).not.toBeInTheDocument()
    // …ainsi que Convocations/Verrouiller, même pour une épreuve non verrouillée.
    const epreuveRow = screen.getByText('Écrit général').closest('.d-flex')
    expect(within(epreuveRow).queryByRole('button', { name: 'Convocations' })).not.toBeInTheDocument()
    expect(within(epreuveRow).queryByRole('button', { name: 'Verrouiller' })).not.toBeInTheDocument()
  })

  it('régression §10.11 : la saisie de notes et les actions de classement sont masquées sur campagne clôturée', async () => {
    const campFermee = { ...CAMP, statut: 'CLOTUREE' }
    mountDetail('ADMIN', campFermee)
    await screen.findByText('Concours L1 2026')
    // Au LOT 16 cette carte et ces boutons restaient actifs (constat §10.11) ;
    // le LOT 17 les masque sur campagne CLOTUREE/ANNULEE/ARCHIVEE, comme le
    // formulaire d'épreuve et les boutons Convocations/Verrouiller.
    expect(screen.queryByText('Saisie des notes')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /calculer le classement/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /publier les listes/i })).not.toBeInTheDocument()
  })

  it('régression §10.11 : même chose pour une campagne annulée, le classement reste consultable', async () => {
    const campAnnulee = { ...CAMP, statut: 'ANNULEE' }
    mountDetail('ADMIN', campAnnulee)
    await screen.findByText('Concours L1 2026')
    expect(screen.queryByText('Saisie des notes')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /calculer le classement/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /publier les listes/i })).not.toBeInTheDocument()
    // Le tableau de classement en lecture reste affiché.
    expect(screen.getByText('Awa Koné')).toBeInTheDocument()
  })

  it('direction : aucune carte d’action (épreuves, notes), le classement reste lisible', async () => {
    mountDetail('DIRECTION')
    await screen.findByText('Concours L1 2026')
    expect(screen.queryByText('Épreuves de concours')).not.toBeInTheDocument()
    expect(screen.queryByText('Saisie des notes')).not.toBeInTheDocument()
    expect(screen.getByText('Awa Koné')).toBeInTheDocument()
    // Les salles ne sont pas chargées en lecture seule.
    expect(apiMock.get.mock.calls.some(([p]) => p.includes('/ref/salles'))).toBe(false)
  })
})
