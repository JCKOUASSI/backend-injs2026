import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within, fireEvent, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import ParticipantDetailModal from '@/components/ParticipantDetailModal'

/* ------------------------------------------------------------------ */
/* Jeu de données                                                       */
/* ------------------------------------------------------------------ */

const participant = {
  id: 1, matricule: 'P0001', nom: 'Koné', prenom: 'Awa', sexe: 'FEMININ',
  date_naissance: '2001-03-15', lieu_naissance: 'Bouaké', email: 'awa@kone.ci',
  telephone: '0701010101', telephone2: '0702020202', type_concours: 'PROFESSIONNEL',
  libelle_concours: 'Concours 2024', categorie: 'A', grade: 'L2', groupe: 'G1',
  grade_groupe: 'L2-G1', vague: 'V2024', site: 'Marcory', salle: 'Salle 2',
  secretariat_nom: 'INJS Marcory',
}

const modules = [
  {
    id: 101, module: 'LSF Niveau 1', formation: 'Formation LSF 2026', formation_id: 501,
    statut: 'EN_COURS', grade: 'L2', groupe: 'G1', vague: 'V2024', site: 'Marcory',
    date_debut: '2026-01-10', date_fin: '2026-05-30', duree_prevue_heures: 10,
    nb_seances_planifiees: 0, inscrit_le: '2026-01-08',
  },
  {
    id: 102, module: 'LSF Niveau 2', formation: 'Formation LSF 2026', formation_id: 501,
    statut: 'PLANIFIEE', duree_prevue_heures: 5, nb_seances_planifiees: 3,
  },
]

const pointages = [
  {
    id: 9001, formation_id: 501, formation_titre: 'Formation LSF 2026',
    module_id: 101, module_intitule: 'LSF Niveau 1', statut: 'TERMINE',
    statut_label: 'Présent', duree_presence_minutes: 120, date_journee: '2026-02-02',
    seance_intitule: 'Séance 2', seance_numero: 2,
    timestamp_entree: '2026-02-02T08:05:00', timestamp_sortie: '2026-02-02T10:05:00',
    temps_cours: { heure_debut_prevue: '08:00:00', heure_fin_prevue: '10:00:00' },
    device_id: 'DEVICE-XYZ123456789',
    geolocalisation: { latitude: 5.3, longitude: 4.0, precision_m: 12 },
    appareil: { batterie_pct: 80, en_charge: false },
    last_heartbeat_at: '2026-02-02T09:00:00', sorties_geofence_count: 1,
  },
  {
    id: 9002, formation_id: 501, formation_titre: 'Formation LSF 2026',
    module_id: 101, module_intitule: 'LSF Niveau 1', statut: 'EN_COURS',
    duree_presence_minutes: 0, date_journee: '2026-02-03',
    seance_intitule: 'Séance 3', seance_numero: 3,
    timestamp_entree: '2026-02-03T08:02:00',
    temps_cours: { heure_debut_prevue: '08:00:00', heure_fin_prevue: '10:00:00' },
  },
  // Second groupe de formation (exerce le tri alphabétique des séances).
  {
    id: 9004, formation_id: 502, formation_titre: 'AAA Atelier précoce',
    module_id: 401, module_intitule: 'Atelier', statut: 'TERMINE',
    duree_presence_minutes: 60, date_journee: '2026-01-15',
    seance_intitule: 'Séance 1', seance_numero: 1,
    timestamp_entree: '2026-01-15T08:10:00', timestamp_sortie: '2026-01-15T09:10:00',
  },
]

const stats = {
  nb_seances_terminees: 3, total_minutes_presence: 300, nb_seances_en_cours: 1,
  nb_a_verifier: 2, nb_formations: 1, nb_modules_inscrits: 2,
}

// Moyenne 15,5 en LSF1 (40h/50h), LSF2 sans note mais 5h prévues au contrat :
// la décision calculée est AJOURNÉ (présence 40/55 = 73 % < 80).
const notesFiche = {
  modules: [
    {
      module_id: 101, colonne_id: 701, moyenne: 15.5, heures_presence: 40,
      heures_prevues: 50, taux_presence: 80, admissible: true, mention: 'BIEN',
    },
    {
      module_id: 102, colonne_id: null, moyenne: null, heures_presence: null,
      heures_prevues: null, taux_presence: null, admissible: false, mention: '',
    },
  ],
  formations: [
    { formation_id: 501, decision: null, criteres: { seuil_admission: 12, taux_presence_min: 80 } },
  ],
}

const fullSessions = [
  { id: 1, numero: 1, date_journee: '2026-02-01', heure_debut_prevue: '08:00:00', heure_fin_prevue: '10:00:00', intitule: 'Séance 1' },
  { id: 2, numero: 2, date_journee: '2026-02-02', heure_debut_prevue: '08:00:00', heure_fin_prevue: '10:00:00', intitule: 'Séance 2' },
  { id: 3, numero: 3, date_journee: '2026-02-03', heure_debut_prevue: '08:00:00', heure_fin_prevue: '10:00:00', intitule: 'Séance 3' },
]

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 4) => { await act(async () => { await flushPromises(n) }) }

const renderModal = (props = {}) => {
  const onClose = vi.fn()
  const utils = renderWithProviders(
    <ParticipantDetailModal
      participant={participant}
      modules={modules}
      pointages={pointages}
      stats={stats}
      initialNotesFiche={notesFiche}
      onClose={onClose}
      loading={false}
      canManageNotes
      {...props}
    />,
    { initialEntries: ['/participants'], routePattern: '/participants' },
  )
  return { ...utils, onClose }
}

const tab = (name) => screen.getByRole('button', { name: new RegExp(name, 'i') })
const goTab = async (name) => {
  fireEvent.click(tab(name))
  await settle()
}
const box = () => document.querySelector('.modal-content')

// Certains libellés sont fragmentés entre un <strong> et un nœud texte frère
// (« <strong>1</strong> présence ») : getByText ne les trouve pas. On renvoie
// l'élément le plus profond dont le textContent complet correspond.
const depth = (el) => {
  let d = 0
  let cur = el
  while (cur.parentElement) { d += 1; cur = cur.parentElement }
  return d
}
const deepText = (container, re) => {
  const matches = [...container.querySelectorAll('*')]
    .filter((el) => re.test(el.textContent.trim()))
    .sort((a, b) => depth(a) - depth(b))
  return matches.at(-1)
}

// Le titre « Synthèse & décision finale » est un frère des cartes de
// synthèse (pas leur ancêtre) : on passe par le conteneur de section.
const synthesisSection = () =>
  screen.getByText(/Synthèse & décision finale/).parentElement
const synthesisCard = () => synthesisSection().querySelector('.card')
const synthesisCards = () => [...synthesisSection().querySelectorAll('.card')]

describe('components/ParticipantDetailModal.jsx — en-tête, navigation et chargement (LOT 24)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it("affiche l'identité dans l'en-tête et le résumé chiffré", () => {
    renderModal()
    expect(screen.getByRole('heading', { name: /Koné Awa/ })).toBeInTheDocument()
    expect(screen.getByText('(P0001)')).toBeInTheDocument()
    // Pastilles du résumé.
    expect(box()).toHaveTextContent('Modules 2')
    expect(box()).toHaveTextContent('Présences 3')
    expect(box()).toHaveTextContent('Temps total 5h')
    expect(box()).toHaveTextContent('En cours 1')
    expect(box()).toHaveTextContent('À vérifier 2')
  })

  it("n'affiche pas le matricule quand il est absent", () => {
    renderModal({ participant: { ...participant, matricule: '' } })
    expect(screen.queryByText(/^\(P0001\)$/)).not.toBeInTheDocument()
  })

  it('montre le spinner et désactive les boutons pendant le chargement', () => {
    renderModal({ loading: true })
    expect(document.querySelector('.spinner')).toBeInTheDocument()
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Fermer' })).toBeDisabled()
  })

  it('se ferme via le bouton Fermer, le X et un clic sur le voile', () => {
    const { onClose } = renderModal()
    fireEvent.click(screen.getByRole('button', { name: 'Fermer' }))
    expect(onClose).toHaveBeenCalledTimes(1)

    fireEvent.click(document.querySelector('.btn-close'))
    expect(onClose).toHaveBeenCalledTimes(2)

    fireEvent.click(document.querySelector('.modal-overlay'))
    expect(onClose).toHaveBeenCalledTimes(3)
  })

  it("un clic dans le contenu ne ferme pas la modale", () => {
    const { onClose } = renderModal()
    fireEvent.click(box())
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('components/ParticipantDetailModal.jsx — onglet Statistiques (LOT 24)', () => {
  beforeEach(() => { apiController.reset() })

  it('cartes de synthèse et répartition par formation', () => {
    renderModal()
    expect(screen.getByText('Présences terminées')).toBeInTheDocument()
    expect(screen.getAllByText('3').length).toBeGreaterThan(0)
    // Le grand « 5h » figure à la fois dans la pastille d'en-tête et dans
    // la carte « Temps total ».
    expect(screen.getAllByText('5h').length).toBeGreaterThan(1)
    expect(screen.getByText(/formation\(s\) suivie\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/module\(s\) inscrit\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/2 pointage\(s\) nécessitent une vérification/)).toBeInTheDocument()
  })

  it("état vide de répartition quand aucune formation n'est suivie", () => {
    renderModal({ stats: { nb_formations: 0 } })
    expect(screen.getByText('Aucune donnée disponible')).toBeInTheDocument()
    expect(screen.queryByText(/formation\(s\) suivie/)).not.toBeInTheDocument()
  })
})

describe('components/ParticipantDetailModal.jsx — onglet Identité (LOT 24)', () => {
  beforeEach(() => { apiController.reset() })

  it('affiche tous les champs formatés, y compris la date et le badge sexe', async () => {
    renderModal()
    await goTab('Identité')
    expect(screen.getByText('15/03/2001')).toBeInTheDocument()
    expect(screen.getByText('Féminin')).toBeInTheDocument()
    expect(screen.getByText('Bouaké')).toBeInTheDocument()
    expect(screen.getByText('awa@kone.ci')).toBeInTheDocument()
    expect(screen.getByText('0701010101')).toBeInTheDocument()
    expect(screen.getByText('Concours 2024')).toBeInTheDocument()
    expect(screen.getByText('INJS Marcory')).toBeInTheDocument()
    expect(screen.getByText('L2-G1')).toBeInTheDocument()
  })

  it('place des tirets et un format date neutre pour les champs absents', async () => {
    renderModal({ participant: { id: 2, nom: 'Doe', prenom: 'John' } })
    await goTab('Identité')
    // Le matricule, le genre, la date… sont tous des tirets.
    expect(within(box()).getAllByText('-').length).toBeGreaterThan(8)
    expect(screen.getByText('John')).toBeInTheDocument()
  })
})

describe('components/ParticipantDetailModal.jsx — onglet Modules (LOT 24)', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute('/formations/501/modules/101/full/', () => ({ sessions: fullSessions }))
  })

  it('état vide sans module inscrit', async () => {
    renderModal({ modules: [] })
    await goTab('Modules')
    expect(screen.getByText('Aucun module inscrit')).toBeInTheDocument()
  })

  it('détaille chaque module : méta, dates, statut, heures, taux, séances, contrat', async () => {
    renderModal()
    await goTab('Modules')

    const card = screen.getByText('LSF Niveau 1').closest('.card')
    expect(within(card).getByText('Formation LSF 2026')).toBeInTheDocument()
    expect(within(card).getByText(/Groupe G1/)).toBeInTheDocument()
    expect(within(card).getByText('V2024')).toBeInTheDocument()
    expect(within(card).getByText('Marcory')).toBeInTheDocument()
    expect(within(card).getByText('L2')).toBeInTheDocument()
    expect(within(card).getByText(/10\/01\/2026/)).toBeInTheDocument()
    expect(within(card).getByText(/30\/05\/2026/)).toBeInTheDocument()
    expect(within(card).getByText('En cours')).toBeInTheDocument()
    // 120 min terminées sur 10h prévues = 2h / 10h, taux 20 %.
    expect(within(card).getByText('2h')).toBeInTheDocument()
    expect(within(card).getByText('10h')).toBeInTheDocument()
    expect(within(card).getByText('20%')).toBeInTheDocument()
    expect(deepText(card, /^1 présence$/)).toBeTruthy()
    expect(deepText(card, /^1 en cours$/)).toBeTruthy()
    expect(within(card).getByText(/Volume contractuel/)).toHaveTextContent('10h')
    expect(within(card).getByText(/Inscrit le/)).toHaveTextContent('08/01/2026')

    // Module planifié sans présence : séances planifiées affichées.
    const card2 = screen.getByText('LSF Niveau 2').closest('.card')
    expect(within(card2).getByText('Planifiée')).toBeInTheDocument()
    expect(deepText(card2, /^3 séances planifiées$/)).toBeTruthy()
  })

  it('calcule les heures fractionnaires et le taux pour un module terminé', async () => {
    const mod = [{
      id: 103, module: 'Atelier pratique', formation: 'Ateliers 2026', formation_id: 503,
      statut: 'TERMINEE', duree_prevue_heures: 2.5, nb_seances_planifiees: 0,
    }]
    const pts = [{
      id: 9003, formation_id: 503, formation_titre: 'Ateliers 2026', module_id: 103,
      module_intitule: 'Atelier pratique', statut: 'TERMINE', duree_presence_minutes: 90,
    }]
    renderModal({ modules: mod, pointages: pts })
    await goTab('Modules')
    const card = screen.getByText('Atelier pratique').closest('.card')
    expect(within(card).getByText('Terminée')).toBeInTheDocument()
    // 150 min = 1,5h sur 2,5h → 60 %, 1 présence terminée.
    expect(within(card).getByText('1.5h')).toBeInTheDocument()
    expect(within(card).getByText('2.5h')).toBeInTheDocument()
    expect(within(card).getByText('60%')).toBeInTheDocument()
    expect(deepText(card, /^1 présence$/)).toBeTruthy()
  })

  it('affiche « Aucune séance » pour un module sans présence ni planification', async () => {
    const modVide = [{
      id: 104, module: 'Module vierge', formation: 'Ateliers 2026', formation_id: 503,
      statut: 'PLANIFIEE', duree_prevue_heures: 0, nb_seances_planifiees: 0,
    }]
    renderModal({ modules: modVide, pointages: [] })
    await goTab('Modules')
    expect(screen.getByText('Aucune séance')).toBeInTheDocument()
  })

  it('déploie les séances du module (GET full), badge les pointages et met en cache', async () => {
    renderModal()
    await goTab('Modules')
    fireEvent.click(screen.getByText('LSF Niveau 1'))
    await waitFor(() =>
      expect(apiMock.get).toHaveBeenCalledWith('/formations/501/modules/101/full/'),
    )

    const card = screen.getByText('LSF Niveau 1').closest('.card')
    // Séance 1 : aucun pointage ; séance 2 : terminé (Présent) ;
    // séance 3 : pointage EN_COURS (En cours).
    expect(within(card).getAllByText('Non badgé')).toHaveLength(1)
    expect(within(card).getByText('Présent')).toBeInTheDocument()
    expect(within(card).getAllByText('En cours').length).toBeGreaterThan(0)
    expect(within(card).getByText(/Séance 1/)).toBeInTheDocument()
    expect(within(card).getAllByText(/08:00/).length).toBeGreaterThan(0)

    // Repli puis redéploiement : la ressource est en cache (un seul GET).
    fireEvent.click(screen.getByText('LSF Niveau 1'))
    await settle()
    fireEvent.click(screen.getByText('LSF Niveau 1'))
    await settle()
    expect(
      apiMock.get.mock.calls.filter(([p]) => p === '/formations/501/modules/101/full/'),
    ).toHaveLength(1)
  })

  it('un clic dans la zone déployée des séances ne replie pas la carte', async () => {
    renderModal()
    await goTab('Modules')
    fireEvent.click(screen.getByText('LSF Niveau 1'))
    await waitFor(() =>
      expect(apiMock.get).toHaveBeenCalledWith('/formations/501/modules/101/full/'),
    )
    // Le conteneur déployé arrête la propagation : la carte reste ouverte.
    fireEvent.click(within(screen.getByText('LSF Niveau 1').closest('.card')).getByText(/^Séances$/))
    await settle()
    const card = screen.getByText('LSF Niveau 1').closest('.card')
    expect(within(card).getByText('Présent')).toBeInTheDocument()
    expect(
      apiMock.get.mock.calls.filter(([p]) => p === '/formations/501/modules/101/full/'),
    ).toHaveLength(1)
  })

  it("reste fonctionnel si le détail complet du module échoue au déploiement", async () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    apiController.reset()
    apiController.setRoute('/formations/501/modules/101/full/', () => {
      throw { response: { status: 500, data: {} } }
    })
    renderModal()
    await goTab('Modules')
    fireEvent.click(screen.getByText('LSF Niveau 1'))
    await waitFor(() =>
      expect(apiMock.get).toHaveBeenCalledWith('/formations/501/modules/101/full/'),
    )
    const card = screen.getByText('LSF Niveau 1').closest('.card')
    expect(within(card).getByText('Aucune séance planifiée')).toBeInTheDocument()
    spy.mockRestore()
  })
})

describe('components/ParticipantDetailModal.jsx — onglet Notes et décision (LOT 24)', () => {
  beforeEach(() => { apiController.reset() })

  it('affiche les moyennes, mentions et taux depuis la fiche chargée par le parent', async () => {
    renderModal()
    await goTab('Notes')
    // Aucun chargement paresseux : la fiche est fournie via initialNotesFiche.
    expect(
      apiMock.get.mock.calls.some(([p]) => p?.startsWith('/participant/1/notes-fiche/')),
    ).toBe(false)

    const card = screen.getByText('LSF Niveau 1').closest('.card')
    const input = within(card).getByDisplayValue('15.5')
    expect(input).toHaveAttribute('type', 'number')
    expect(within(card).getByText('80%')).toBeInTheDocument()
    expect(within(card).getByText('40h / 50h')).toBeInTheDocument()
    expect(within(card).getByText('Bien')).toBeInTheDocument()
    // Non encore modifié : Enregistrer désactivé.
    expect(within(card).getByRole('button', { name: 'Enregistrer' })).toBeDisabled()
  })

  it('est strictement en lecture quand canManageNotes est faux', async () => {
    renderModal({ canManageNotes: false })
    await goTab('Notes')
    expect(within(box()).queryByDisplayValue('15.5')).not.toBeInTheDocument()
    expect(within(box()).getAllByText('15.5').length).toBeGreaterThan(0)
    expect(within(box()).queryByRole('button', { name: 'Enregistrer' })).not.toBeInTheDocument()
    expect(within(box()).queryByRole('button', { name: /recalculer la décision/i })).not.toBeInTheDocument()
  })

  it("signale un module dont la moyenne est introuvable", async () => {
    const extra = [...modules, {
      id: 105, module: 'Module sans notes', formation: 'Formation LSF 2026',
      formation_id: 501, statut: 'PLANIFIEE', duree_prevue_heures: 2,
    }]
    renderModal({ modules: extra })
    await goTab('Notes')
    expect(screen.getByText('Impossible de charger la moyenne pour ce cours.')).toBeInTheDocument()
  })

  it('calcule une décision AJOURNÉ (moyenne suffisante mais présence sous seuil)', async () => {
    renderModal()
    await goTab('Notes')
    const s = synthesisCard()
    expect(within(s).getByText('15.5/20')).toBeInTheDocument()
    // 40 h présentes sur 55 h prévues (50 h LSF1 + 5 h LSF2) = 72,73 %.
    expect(within(s).getByText('72.73%')).toBeInTheDocument()
    expect(within(s).getByText('Ajourné')).toBeInTheDocument()
  })

  it('calcule ADMIS quand les deux seuils sont atteints', async () => {
    const fiche = {
      modules: [{
        module_id: 101, colonne_id: 701, moyenne: 14, heures_presence: 50,
        heures_prevues: 50, taux_presence: 100, admissible: true, mention: 'BIEN',
      }],
      formations: [{ formation_id: 501, decision: null }],
    }
    renderModal({ modules: [modules[0]], pointages: [], initialNotesFiche: fiche })
    await goTab('Notes')
    const s = synthesisCard()
    expect(within(s).getByText('Admis')).toBeInTheDocument()
    expect(within(s).getByText('14/20')).toBeInTheDocument()
    expect(within(s).getByText('100%')).toBeInTheDocument()
  })

  it("calcule EXCLUSION quand la moyenne est très basse", async () => {
    const fiche = {
      modules: [{
        module_id: 101, colonne_id: 701, moyenne: 7, heures_presence: 10,
        heures_prevues: 50, taux_presence: 20, admissible: false, mention: 'INSUFFISANT',
      }],
      formations: [{ formation_id: 501, decision: null }],
    }
    renderModal({ modules: [modules[0]], pointages: [], initialNotesFiche: fiche })
    await goTab('Notes')
    expect(within(synthesisCard()).getByText('Exclusion')).toBeInTheDocument()
    expect(within(synthesisCard()).getByText('Insuffisant')).toBeInTheDocument()
  })

  it("affiche EN ATTENTE quand aucune donnée n'est exploitable", async () => {
    const fiche = { modules: [], formations: [] }
    const mod = [{
      id: 106, module: 'Module nouveau', formation: 'Formation LSF 2026',
      formation_id: 501, statut: 'PLANIFIEE', duree_prevue_heures: 10,
    }]
    renderModal({ modules: mod, pointages: [], initialNotesFiche: fiche })
    await goTab('Notes')
    const s = synthesisCard()
    expect(within(s).getByText('En attente')).toBeInTheDocument()
    expect(within(s).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('privilégie une décision backend et mentionne la validation manuelle', async () => {
    const fiche = {
      modules: notesFiche.modules,
      formations: [{
        formation_id: 501,
        criteres: { seuil_admission: 12, taux_presence_min: 80 },
        decision: {
          decision: 'ADMIS', moyenne_generale: 16, taux_presence: 95,
          total_heures_presence: 47.5, total_heures_prevues: 50, mention: 'TRES_BIEN',
          generee_auto: false, validee_le: '2026-06-01T10:00:00',
        },
      }],
    }
    renderModal({ initialNotesFiche: fiche })
    await goTab('Notes')
    const s = synthesisCard()
    expect(within(s).getByText('16/20')).toBeInTheDocument()
    expect(within(s).getByText('95%')).toBeInTheDocument()
    expect(within(s).getByText('Admis')).toBeInTheDocument()
    expect(within(s).getByText('Très bien')).toBeInTheDocument()
    expect(within(s).getByText('Validée manuellement')).toBeInTheDocument()
    expect(within(s).getByText(/47\.5h \/ 50h/)).toBeInTheDocument()
  })

  it('regroupe et titre la synthèse par formation (plusieurs formations)', async () => {
    const mod = [
      { id: 201, module: 'Module A', formation: 'Formation Alpha', formation_id: 601, statut: 'TERMINEE', duree_prevue_heures: 4 },
      { id: 202, module: 'Module B', formation: 'Formation Bêta', formation_id: 602, statut: 'EN_COURS', duree_prevue_heures: 4 },
    ]
    const fiche = {
      modules: [
        { module_id: 201, colonne_id: 801, moyenne: 14, heures_presence: 20, heures_prevues: 20, taux_presence: 100, admissible: true, mention: 'BIEN' },
        { module_id: 202, colonne_id: 802, moyenne: 13, heures_presence: 18, heures_prevues: 20, taux_presence: 90, admissible: true, mention: 'ASSEZ_BIEN' },
      ],
      formations: [
        { formation_id: 601, decision: null },
        { formation_id: 602, decision: null },
      ],
    }
    renderModal({ modules: mod, pointages: [], initialNotesFiche: fiche })
    await goTab('Notes')
    // Les titres de formation ne s'affichent que dans les cartes de synthèse.
    const cards = synthesisCards()
    expect(cards).toHaveLength(2)
    expect(within(cards[0]).getByText('Formation Alpha')).toBeInTheDocument()
    expect(within(cards[1]).getByText('Formation Bêta')).toBeInTheDocument()
    expect(screen.getAllByText('Admis')).toHaveLength(2)
  })

  it('charge paresseusement la fiche de notes à l’ouverture de l’onglet si non fournie', async () => {
    apiController.setRoute('/participant/1/notes-fiche/', () => ({
      modules: [{
        module_id: 101, colonne_id: 701, moyenne: 11, heures_presence: 30,
        heures_prevues: 50, taux_presence: 60, admissible: false, mention: 'PASSABLE',
      }],
      formations: [{ formation_id: 501, decision: null }],
    }))
    renderModal({ initialNotesFiche: null })
    await goTab('Notes')
    await waitFor(() =>
      expect(apiMock.get).toHaveBeenCalledWith('/participant/1/notes-fiche/'),
    )
    expect(await within(box()).findByDisplayValue('11')).toBeInTheDocument()
  })

  it('affiche le spinner de l’onglet pendant le chargement paresseux, puis les données', async () => {
    // NB: le squelette « par module » est du code mort — tant que notesLoading
    // est vrai, l'onglet affiche le grand spinner et n'exécute pas le map ;
    // c'est ce spinner réel que l'on vérifie ici.
    let resolveLoad
    apiMock.get.mockImplementationOnce(
      () => new Promise((resolve) => { resolveLoad = resolve }),
    )
    renderModal({ initialNotesFiche: null })
    await goTab('Notes')
    expect(box().querySelector('.loading.py-4 .spinner')).toBeTruthy()
    const lazyFiche = {
      modules: [{
        module_id: 101, colonne_id: 701, moyenne: 11, heures_presence: 30,
        heures_prevues: 50, taux_presence: 60, admissible: false, mention: 'PASSABLE',
      }],
      formations: [{ formation_id: 501, decision: null }],
    }
    await act(async () => {
      resolveLoad({ data: lazyFiche })
      await flushPromises(4)
    })
    expect(within(box()).getByDisplayValue('11')).toBeInTheDocument()
    expect(box().querySelector('.loading.py-4')).toBeNull()
  })

  it('notifie l’échec du chargement paresseux des notes', async () => {
    apiController.setRoute('/participant/1/notes-fiche/', () => {
      throw { response: { status: 500, data: {} } }
    })
    renderModal({ initialNotesFiche: null })
    await goTab('Notes')
    expect(await screen.findByText('Erreur chargement des notes')).toBeInTheDocument()
  })

  it('état vide des notes sans module inscrit', async () => {
    renderModal({ modules: [], initialNotesFiche: { modules: [], formations: [] } })
    await goTab('Notes')
    expect(screen.getByText('Aucun module inscrit')).toBeInTheDocument()
  })
})

describe('components/ParticipantDetailModal.jsx — onglet Séances (LOT 24)', () => {
  beforeEach(() => { apiController.reset() })

  it('état vide sans badgeage', async () => {
    renderModal({ pointages: [] })
    await goTab('Séances')
    expect(screen.getByText('Aucun badgeage enregistré')).toBeInTheDocument()
  })

  it('résumé par module et détail technique de chaque badgeage', async () => {
    renderModal()
    await goTab('Séances')

    // Résumé : 120 min terminées = 2h, 1 terminée, 1 en cours ; le second
    // groupe (60 min) affiche 1h.
    expect(screen.getByText('2h')).toBeInTheDocument()
    expect(screen.getByText('1h')).toBeInTheDocument()
    expect(screen.getAllByText(/Formation LSF 2026/).length).toBeGreaterThan(0)

    // Les groupes sont triés par titre de formation : « AAA Atelier précoce »
    // avant « Formation LSF 2026 ».
    const groupHeadings = [...box().querySelectorAll('h6')].map((h) => h.textContent)
    const idxAaa = groupHeadings.findIndex((t) => /AAA Atelier précoce/.test(t))
    const idxLsf = groupHeadings.findIndex((t) => /Formation LSF 2026/.test(t))
    expect(idxAaa).toBeGreaterThanOrEqual(0)
    expect(idxLsf).toBeGreaterThan(idxAaa)
    expect(screen.getByText('2026-01-15')).toBeInTheDocument()

    // Ligne du badgeage terminé (les deux pointages ont la même plage horaire).
    expect(screen.getByText('2026-02-02')).toBeInTheDocument()
    expect(screen.getAllByText('08:00 → 10:00')).toHaveLength(2)
    expect(screen.getByText(/\(Séance 2\)/)).toBeInTheDocument()
    expect(screen.getAllByText('Présent').length).toBeGreaterThan(0)
    expect(screen.getAllByText(/08:05/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/10:05/).length).toBeGreaterThan(0)
    expect(screen.getByText(/120 min/)).toBeInTheDocument()
    expect(screen.getByText(/DEVICE-XYZ12\.\.\./)).toBeInTheDocument()
    expect(screen.getByText(/±12m/)).toBeInTheDocument()
    expect(screen.getByText(/80%/)).toBeInTheDocument()
    expect(screen.getByText(/1 sortie\(s\) geofence/)).toBeInTheDocument()

    // Ligne en cours : pas de sortie, statut EN_COURS brut (sans libellé).
    expect(screen.getByText('2026-02-03')).toBeInTheDocument()
    expect(screen.getAllByText('EN_COURS').length).toBeGreaterThan(0)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 25 — écritures : saisie de moyenne, recalcul, exports relevé    */
/* ------------------------------------------------------------------ */

const stubBlobDownload = () => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

describe('components/ParticipantDetailModal.jsx — saisie d’une moyenne (LOT 25)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    // Après toute écriture, le composant recharge la fiche de notes.
    apiController.setRoute('/participant/1/notes-fiche/', () => notesFiche)
  })

  const openNotes = async () => {
    renderModal()
    await goTab('Notes')
    return screen.getByText('LSF Niveau 1').closest('.card')
  }

  it('active Enregistrer après modification puis poste la note et la synthèse', async () => {
    const card = await openNotes()
    const button = within(card).getByRole('button', { name: 'Enregistrer' })
    expect(button).toBeDisabled()

    fireEvent.change(within(card).getByDisplayValue('15.5'), { target: { value: '15' } })
    expect(button).toBeEnabled()

    fireEvent.click(button)
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/formations/501/modules/101/notes/bulk/',
        {
          notes: [{ participant_id: 1, colonne_id: 701, note: 15 }],
          syntheses: [{ participant_id: 1, mention: 'BIEN', observations: '' }],
        },
      ),
    )
    // La sauvegarde enchaîne le recalcul de la décision de formation…
    expect(apiMock.post).toHaveBeenCalledWith(
      '/evaluations/formations/501/decisions/recalculer/',
    )
    // …puis le rechargement de la fiche, avec un toast de succès.
    expect(apiMock.get).toHaveBeenCalledWith('/participant/1/notes-fiche/')
    expect(await screen.findByText('Moyenne enregistrée')).toBeInTheDocument()
  })

  it("refuse une moyenne négative ou supérieure à 20 sans aucun appel", async () => {
    const card = await openNotes()
    const input = within(card).getByDisplayValue('15.5')
    fireEvent.change(input, { target: { value: '22' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('La moyenne doit être comprise entre 0 et 20')).toBeInTheDocument()
    expect(apiMock.post).not.toHaveBeenCalled()

    fireEvent.change(input, { target: { value: '-1' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findAllByText('La moyenne doit être comprise entre 0 et 20')).toHaveLength(2)
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  // NB: la branche NaN de la garde est inaccessible par l'UI (le navigateur
  // comme jsdom vident un <input type="number"> dont la saisie n'est pas un
  // nombre) : elle n'est pas testable « par l'extérieur ».

  it("garde le bouton désactivé tant que la fiche n'est pas modifiée", async () => {
    const card = await openNotes()
    fireEvent.click(within(card).getByDisplayValue('15.5'))
    expect(within(card).getByRole('button', { name: 'Enregistrer' })).toBeDisabled()
  })

  it("n'active pas Enregistrer pour un module sans colonne de notes", async () => {
    renderModal()
    await goTab('Notes')
    // Carte LSF Niveau 2 (colonne_id null dans la fiche).
    const card2 = screen.getByText('LSF Niveau 2').closest('.card')
    const input = within(card2).getByRole('spinbutton')
    fireEvent.change(input, { target: { value: '12' } })
    expect(within(card2).getByRole('button', { name: 'Enregistrer' })).toBeDisabled()
  })

  it('poste des tableaux vides quand la moyenne est effacée', async () => {
    const card = await openNotes()
    fireEvent.change(within(card).getByDisplayValue('15.5'), { target: { value: '' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/formations/501/modules/101/notes/bulk/',
        { notes: [], syntheses: [] },
      ),
    )
    expect(await screen.findByText('Moyenne enregistrée')).toBeInTheDocument()
  })

  it('avertit quand le serveur renvoie des erreurs partielles', async () => {
    apiController.setRoute('/formations/501/modules/101/notes/bulk/', () => ({
      saved: 0, errors: [{ ligne: 1 }, { ligne: 2 }],
    }))
    const card = await openNotes()
    fireEvent.change(within(card).getByDisplayValue('15.5'), { target: { value: '9' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('0 enregistrement(s), 2 erreur(s)')).toBeInTheDocument()
  })

  it("notifie l'erreur du serveur de sauvegarde", async () => {
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Verrou de saisie' } } })
    const card = await openNotes()
    fireEvent.change(within(card).getByDisplayValue('15.5'), { target: { value: '9' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Verrou de saisie')).toBeInTheDocument()
  })

  it("notifie une erreur générique sans détail serveur", async () => {
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    const card = await openNotes()
    fireEvent.change(within(card).getByDisplayValue('15.5'), { target: { value: '9' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Erreur lors de la sauvegarde')).toBeInTheDocument()
  })

  it("avale un échec de recalcul post-sauvegarde sans masquer le succès", async () => {
    // Le bulk (sans route explicite) réussit ; seul le recalcul échoue.
    apiController.setRoute('/evaluations/formations/501/decisions/recalculer/', () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Calcul indisponible' } } }
    })
    const card = await openNotes()
    fireEvent.change(within(card).getByDisplayValue('15.5'), { target: { value: '14' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    // La moyenne est bien enregistrée et la fiche rechargée malgré le recalcul KO.
    expect(await screen.findByText('Moyenne enregistrée')).toBeInTheDocument()
    expect(apiMock.get).toHaveBeenCalledWith('/participant/1/notes-fiche/')
  })

  it("ne recalcule pas de décision pour un module sans formation rattachée", async () => {
    const mod = [{
      id: 301, module: 'Module hors formation', formation: '', formation_id: null,
      statut: 'EN_COURS', duree_prevue_heures: 4,
    }]
    const fiche = {
      modules: [{
        module_id: 301, colonne_id: 901, moyenne: 11, heures_presence: 20,
        heures_prevues: 20, taux_presence: 100, admissible: true, mention: 'PASSABLE',
      }],
      formations: [],
    }
    renderModal({ modules: mod, pointages: [], initialNotesFiche: fiche })
    await goTab('Notes')
    const card = screen.getByText('Module hors formation').closest('.card')
    fireEvent.change(within(card).getByDisplayValue('11'), { target: { value: '13' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/formations/null/modules/301/notes/bulk/',
        expect.objectContaining({ notes: [{ participant_id: 1, colonne_id: 901, note: 13 }] }),
      ),
    )
    expect(
      apiMock.post.mock.calls.some(([p]) => typeof p === 'string' && p.includes('decisions/recalculer')),
    ).toBe(false)
    expect(await screen.findByText('Moyenne enregistrée')).toBeInTheDocument()
  })
})

describe('components/ParticipantDetailModal.jsx — recalcul manuel de décision (LOT 25)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute('/participant/1/notes-fiche/', () => notesFiche)
  })

  it('recalcule la décision, recharge la fiche et notifie', async () => {
    renderModal()
    await goTab('Notes')
    fireEvent.click(within(synthesisCard()).getByRole('button', { name: /recalculer la décision/i }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/evaluations/formations/501/decisions/recalculer/',
      ),
    )
    expect(apiMock.get).toHaveBeenCalledWith('/participant/1/notes-fiche/')
    expect(await screen.findByText('Décision recalculée')).toBeInTheDocument()
  })

  it("notifie le détail d'un échec de recalcul", async () => {
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Période verrouillée' } } })
    renderModal()
    await goTab('Notes')
    fireEvent.click(within(synthesisCard()).getByRole('button', { name: /recalculer la décision/i }))
    expect(await screen.findByText('Période verrouillée')).toBeInTheDocument()
  })

  it("notifie une erreur générique de recalcul", async () => {
    apiMock.post.mockRejectedValueOnce(new Error('boom'))
    renderModal()
    await goTab('Notes')
    fireEvent.click(within(synthesisCard()).getByRole('button', { name: /recalculer la décision/i }))
    expect(await screen.findByText('Erreur recalcul décision')).toBeInTheDocument()
  })

  it('masque le recalcul (et la sauvegarde) en lecture seule', async () => {
    renderModal({ canManageNotes: false })
    await goTab('Notes')
    expect(screen.queryByRole('button', { name: /recalculer la décision/i })).not.toBeInTheDocument()
  })
})

describe('components/ParticipantDetailModal.jsx — exports relevé de notes (LOT 25)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    stubBlobDownload()
  })

  it('exporte le relevé PDF avec le nom de fichier par défaut', async () => {
    apiMock.getBlob.mockResolvedValueOnce({
      blob: new Blob(['pdf'], { type: 'application/pdf' }), fileName: '',
    })
    renderModal()
    await goTab('Notes')
    fireEvent.click(screen.getByRole('button', { name: /export PDF/i }))
    await waitFor(() =>
      expect(apiMock.getBlob).toHaveBeenCalledWith('/participant/1/notes-fiche/export/pdf/'),
    )
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(URL.revokeObjectURL).toHaveBeenCalled()
  })

  it('exporte le relevé Excel', async () => {
    renderModal()
    await goTab('Notes')
    fireEvent.click(screen.getByRole('button', { name: /export Excel/i }))
    await waitFor(() =>
      expect(apiMock.getBlob).toHaveBeenCalledWith('/participant/1/notes-fiche/export/xlsx/'),
    )
  })

  it("notifie le détail d'un échec d'export", async () => {
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'Génération KO' } } })
    renderModal()
    await goTab('Notes')
    fireEvent.click(screen.getByRole('button', { name: /export PDF/i }))
    expect(await screen.findByText('Génération KO')).toBeInTheDocument()
  })

  it("notifie une erreur générique d'export", async () => {
    apiMock.getBlob.mockRejectedValueOnce(new Error('réseau'))
    renderModal()
    await goTab('Notes')
    fireEvent.click(screen.getByRole('button', { name: /export PDF/i }))
    expect(await screen.findByText('Erreur export')).toBeInTheDocument()
  })
})
