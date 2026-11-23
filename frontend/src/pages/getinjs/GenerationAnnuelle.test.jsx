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
import GenerationAnnuelle from './GenerationAnnuelle'

const ANNEES = [
  { id: 1, libelle: '2024-2025', courante: false },
  { id: 2, libelle: '2025-2026', courante: true, date_debut: '2025-10-01', date_fin: '2026-06-30' },
]

const SYNTHESE = {
  annee_academique_id: 2,
  effectif_total: 3752,
  nb_cohortes: 2,
  cohortes: [
    {
      formation: 'Licence en Journalisme', filiere_code: 'F01', parcours: 'Journalisme',
      niveau: 'L1', groupe: 'L1-G1', vague: 'Vague A', effectif: 1751,
    },
    {
      formation: 'Licence en Communication', filiere_code: 'F02', parcours: 'Communication',
      niveau: 'L1', groupe: 'L1-G2', vague: 'Vague A', effectif: 2001,
    },
  ],
}

const RAPPORT = {
  applique: false,
  fichier: 'inscrits_2025.csv',
  lignes_lues: 5,
  lignes_valides: 3,
  lignes_rejetees: 2,
  creees: 0,
  mises_a_jour: 0,
  effectif_total: 3,
  erreurs: [
    { ligne: 3, motif: 'MATRICULE_MANQUANT', detail: 'La colonne matricule est vide.' },
    { ligne: 5, motif: 'NIVEAU_INCONNU', detail: 'Niveau « L9 » inconnu du référentiel INJS.' },
  ],
  erreurs_tronquees: 0,
  colonnes_reconnues: { matricule: 'Matricule', nom: 'Nom' },
  colonnes_ignorees: [],
  cohortes: [
    { formation: 'Licence en Journalisme', niveau: 'L1', groupe: 'L1-G1', vague: 'Vague A', effectif: 3 },
  ],
  motif_echec: null,
  detail: {},
  succes: true,
}

const BILAN = {
  status_global: 'PARTIELLE',
  annee_academique_id: 2,
  semaines: { debut: 1, fin: 1 },
  totaux: {
    nb_groupes: 2, nb_groupes_planifies: 2, nb_groupes_complets: 1,
    nb_groupes_non_planifies: 0, etudiants_couverts: 3752,
    seances_attendues: 12, seances_placees: 9, seances_non_placees: 3,
    heures_attendues: 18.0, edts_persistes: 0, groupes_hors_perimetre: 1,
  },
  groupes: [
    {
      groupe_id: 11, groupe: 'L1-G1', formation: 'Licence en Journalisme',
      parcours: 'Journalisme', niveau: 'L1', vague: 'Vague A', effectif: 1751,
      statut: 'GENERATION_OK', motif_echec: null, seances_attendues: 6,
      seances_placees: 6, seances_non_placees: 0,
    },
    {
      groupe_id: 12, groupe: 'L1-G2', formation: 'Licence en Communication',
      parcours: 'Communication', niveau: 'L1', vague: 'Vague A', effectif: 2001,
      statut: 'GENERATION_PARTIELLE', motif_echec: 'CAPACITE_SALLE_INSUFFISANTE',
      seances_attendues: 6, seances_placees: 3, seances_non_placees: 3,
    },
  ],
  persistence_demandee: false,
}

const RESULTAT_CAMPAGNE = {
  campagne: { id: 1, status_global: 'PARTIELLE' },
  totaux: BILAN.totaux,
  groupes: BILAN.groupes,
  anomalies: [],
}

const HISTORIQUE = {
  count: 1,
  executions: [{
    id: 5,
    campagne_id: 1,
    libelle: 'Génération 2025-2026',
    annee_academique: '2025-2026',
    date: '2026-11-04T02:39:00Z',
    statut: 'TERMINE',
    duree_ms: 12500,
    perimetre: { filieres: [], formations: [], niveaux: [], groupes: [] },
    semestres: ['S1', 'S2'],
    seances_placees: 9,
    seances_attendues: 12,
    couverture_pct: 75.0,
    conflits: 0,
  }],
}

const VERSIONS = {
  versions: [{
    id: 3,
    version: 1,
    libelle: 'V1',
    titre: 'EDT Licence en Journalisme L1 — S1 (exemple GET)',
    statut: 'PUBLIE',
    statut_libelle: 'Publié',
    annee_academique: '2025-2026',
    creee_le: '2026-11-04T02:39:41Z',
    nb_seances: 12,
  }],
}

function routes({ synthese = SYNTHESE } = {}) {
  apiController.setRoute('/scolarite/ref/annees/', ANNEES)
  apiController.setRoute('/formations/ref/formations/', [
    { id: 1, intitule: 'Licence en Journalisme', filiere_code: 'F01' },
    { id: 2, intitule: 'Licence en Communication', filiere_code: 'F02' },
  ])
  apiController.setRoute('/scolarite/ref/niveaux/', [
    { id: 1, code: 'L1', libelle: 'Licence 1' },
  ])
  apiController.setRoute('/scolarite/ref/groupes/', [
    { id: 11, nom: 'L1-G1', ref_formation_id: 1, niveau_id: 1, capacite_max: 40 },
  ])
  apiController.setRoute('/edts/lmd/import/inscrits/synthese/', synthese)
  apiController.setRoute('/edts/lmd/import/inscrits/analyser/', RAPPORT)
  apiController.setRoute('/edts/lmd/import/inscrits/', { ...RAPPORT, applique: true, creees: 3 })
  apiController.setRoute('/edts/lmd/generate-annee/', BILAN)
  apiController.setRoute('/edts/campagnes/historique/', HISTORIQUE)
  apiController.setRoute('/edts/lmd/versions/', VERSIONS)
  apiController.setRoute('/edts/campagnes/', { id: 1, libelle: 'Génération 2025-2026' })
  apiController.setRoute('/edts/campagnes/1/donnees-pretes/', {})
  apiController.setRoute('/edts/campagnes/1/demarrer/', { campagne_id: 1, execution_id: 5 })
  apiController.setRoute('/edts/campagnes/1/statut/', {
    id: 1, statut: 'TERMINE', en_cours: false, erreur: '',
  })
  apiController.setRoute('/edts/campagnes/1/resultat/', RESULTAT_CAMPAGNE)
}

function rendre({ initialEntries = ['/'] } = {}) {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user} initialEntries={initialEntries}>
      <GenerationAnnuelle />
    </AllProviders>,
  )
}

async function choisirModeAutomatique(user) {
  await user.click(screen.getByRole('radio', { name: /Automatique \(toute l’année\)/ }))
}

async function choisirPerimetre(user) {
  await screen.findByText('L1-G1 — Licence en Journalisme')
  await user.click(within(screen.getByRole('group', { name: /Formations \/ parcours/ }))
    .getByRole('checkbox', { name: 'Licence en Journalisme' }))
  await user.click(within(screen.getByRole('group', { name: /Niveaux/ }))
    .getByRole('checkbox', { name: /L1 — Licence 1/ }))
  await user.click(within(screen.getByRole('group', { name: /Groupes/ }))
    .getByRole('checkbox', { name: /L1-G1/ }))
  await user.click(within(screen.getByRole('group', { name: /Semestres/ }))
    .getByRole('checkbox', { name: 'Semestre 1 (S1)' }))
}

describe('GET-INJS — génération des emplois du temps (maquette) et import', () => {
  beforeEach(() => {
    apiController.reset()
    routes()
  })

  it('présente l’en-tête du moteur et les paramètres de la maquette', async () => {
    rendre()
    expect(await screen.findByRole('heading', { name: 'Générer les emplois du temps' }))
      .toBeInTheDocument()
    expect(screen.getByText('Moteur LMD')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Consulter les grilles/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Vérifier les référentiels/ })).toBeInTheDocument()
    expect(screen.getByLabelText(/Année académique/)).toBeInTheDocument()
    for (const titre of ['Filières', 'Formations / parcours', 'Niveaux', 'Groupes', 'Semestres']) {
      expect(screen.getByRole('group', { name: new RegExp(titre) })).toBeInTheDocument()
    }
    expect(screen.getByLabelText('Séances max / groupe / semaine')).toHaveValue(30)
    expect(screen.getByLabelText(/Inclure le samedi/)).toBeChecked()
    expect(screen.getByLabelText(/Éviter la pause méridienne/)).toBeChecked()
    expect(screen.getByText('Comment le moteur décide')).toBeInTheDocument()
    expect(screen.getByText('Règles métier appliquées par le moteur')).toBeInTheDocument()
  })

  it('recharge le périmètre accepté depuis le serveur après navigation/actualisation', async () => {
    apiController.setRoute('/edts/campagnes/41/', {
      id: 41, annee_academique_id: 2, semaines: [2, 3],
      perimetre: { formations: [1], niveaux: [1], groupes: [11], semestres: [1] },
      parametres: { simulation: true, simulation_acceptee: { par: 'admin' },
        inclure_samedi: false, eviter_pause_meridienne: true, max_seances_par_groupe_semaine: 12 },
    })
    rendre({ initialEntries: ['/edt/generation-annuelle?simulation_id=41'] })
    await waitFor(() => expect(screen.getByLabelText('Semaines planifiées')).toHaveValue('2,3'))
    expect(within(screen.getByRole('group', { name: /Formations \/ parcours/ }))
      .getByRole('checkbox', { name: 'Licence en Journalisme' })).toBeChecked()
    await screen.findByText('L1-G1 — Licence en Journalisme')
    expect(within(screen.getByRole('group', { name: /Groupes/ }))
      .getByRole('checkbox', { name: /L1-G1/ })).toBeChecked()
    expect(screen.getByLabelText(/Inclure le samedi/)).not.toBeChecked()
    expect(screen.getByLabelText(/Éviter la pause méridienne/)).toBeChecked()
    expect(screen.getByRole('button', { name: 'Lancer la génération manuelle' })).toBeDisabled()
    expect(screen.getByText(/Prévisualisez à nouveau avant toute génération/)).toBeInTheDocument()
  })

  it('charge les années et sélectionne l’année courante', async () => {
    rendre()
    const select = await screen.findByLabelText(/Année académique/)
    await waitFor(() => expect(select).toHaveValue('2'))
    expect(
      within(select).getByRole('option', { name: 'Année académique 2025-2026 (courante)' }),
    ).toBeInTheDocument()
  })

  it('affiche l’effectif réel importé, sans valeur inventée', async () => {
    rendre()
    expect(await screen.findByText('3752')).toBeInTheDocument()
    expect(screen.getByText('étudiants importés')).toBeInTheDocument()
    expect(apiMock.get).toHaveBeenCalledWith(
      '/edts/lmd/import/inscrits/synthese/',
      { params: { annee: '2' } },
    )
  })

  it('n’affiche aucun compteur tant que la synthèse n’est pas chargée', async () => {
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', ANNEES)
    apiController.setRoute('/edts/lmd/import/inscrits/synthese/', { detail: 'absent' })
    rendre()
    await screen.findByLabelText(/Année académique/)
    expect(screen.queryByText('étudiants importés')).not.toBeInTheDocument()
  })

  it('analyse le fichier sans écrire et rend le rapport ligne par ligne', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)

    const fichier = new File(['matricule;nom\nM1;Ba'], 'inscrits_2025.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Fichier des inscrits'), fichier)
    await user.click(screen.getByRole('button', { name: /Analyser sans importer/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/edts/lmd/import/inscrits/analyser/',
        expect.any(FormData),
      ),
    )

    const envoi = apiMock.post.mock.calls[0][1]
    expect(envoi.get('annee_academique_id')).toBe('2')
    expect(envoi.get('fichier')).toBe(fichier)

    expect(await screen.findByText('MATRICULE_MANQUANT')).toBeInTheDocument()
    expect(screen.getByText('NIVEAU_INCONNU')).toBeInTheDocument()
    expect(screen.getByText('Niveau « L9 » inconnu du référentiel INJS.')).toBeInTheDocument()

    const valides = screen.getByText('valides').closest('.getinjs-compte')
    expect(within(valides).getByText('3')).toBeInTheDocument()
    const rejetees = screen.getByText('rejetées').closest('.getinjs-compte')
    expect(within(rejetees).getByText('2')).toBeInTheDocument()
  })

  it('importe réellement puis réactualise l’effectif', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)

    const fichier = new File(['matricule;nom\nM1;Ba'], 'inscrits_2025.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Fichier des inscrits'), fichier)
    await user.click(screen.getByRole('button', { name: /^Importer$/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        '/edts/lmd/import/inscrits/',
        expect.any(FormData),
      ),
    )
    await waitFor(() =>
      expect(apiMock.get.mock.calls.filter(
        ([chemin]) => chemin === '/edts/lmd/import/inscrits/synthese/',
      )).toHaveLength(2),
    )
  })

  it('refuse d’envoyer un fichier sans année choisie', async () => {
    const user = userEvent.setup()
    apiController.reset()
    apiController.setRoute('/scolarite/ref/annees/', [])
    rendre()

    const fichier = new File(['matricule;nom\nM1;Ba'], 'inscrits.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Fichier des inscrits'), fichier)
    await user.click(screen.getByRole('button', { name: /Analyser sans importer/i }))

    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('lance la génération automatique après confirmation explicite du périmètre total', async () => {
    const user = userEvent.setup()
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(true)
    rendre()
    await screen.findByLabelText(/Année académique/)
    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '1,2')
    await choisirModeAutomatique(user)
    await user.click(screen.getByRole('button', { name: /Lancer la génération automatique/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/', expect.objectContaining({
        annee_academique_id: 2,
        perimetre: { formations: [], niveaux: [], groupes: [], semestres: [] },
        parametres: expect.objectContaining({
          mode_generation: 'automatique',
          persister: true,
          inclure_samedi: true,
          eviter_pause_meridienne: true,
          max_seances_par_groupe_semaine: null,
          calendrier_previsionnel_confirme: true,
          publier_direct: false,
        }),
      })),
    )
    expect(confirmation).toHaveBeenCalledWith(expect.stringContaining('CALENDRIER PROVISOIRE NON OFFICIEL'))
    confirmation.mockRestore()
    expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/1/donnees-pretes/', {})
    // Démarrage asynchrone (le synchrone expirait en HTTP) + statut suivi.
    expect(apiMock.post).toHaveBeenCalledWith(
      '/edts/campagnes/1/demarrer/', { asynchrone: true })
    expect(apiMock.get).toHaveBeenCalledWith('/edts/campagnes/1/statut/', expect.anything())

    const bilanTable = await screen.findByRole('table', { name: /Bilan par groupe/i })
    expect(within(bilanTable).getByRole('cell', { name: 'L1-G1' })).toBeInTheDocument()
    expect(within(bilanTable).getByText('CAPACITE_SALLE_INSUFFISANTE')).toBeInTheDocument()
    // L'historique et les versions sont rechargés après le passage.
    await waitFor(() =>
      expect(apiMock.get.mock.calls.filter(
        ([chemin]) => chemin === '/edts/campagnes/historique/',
      ).length).toBeGreaterThanOrEqual(2),
    )
  })

  it('distingue le calcul de l’enregistrement et explique les causes du bilan partiel', async () => {
    apiController.reset()
    apiController.setRoute('/edts/campagnes/1/resultat/', {
      campagne: { id: 1, status_global: 'PARTIELLE' },
      totaux: {
        nb_groupes: 2, nb_groupes_planifies_calcules: 2, nb_groupes_planifies: 1,
        nb_groupes_non_planifies: 1, nb_groupes_complets: 1,
        etudiants_couverts_calcules: 3752, etudiants_couverts: 1751,
        seances_calculees: 9, seances_persistees: 6, seances_non_placees: 6,
        edts_persistes: 1, affectations_salle_cadrage_calculees: 4,
        affectations_salle_cadrage_persistees: 2,
        salles_cadrage_utilisees: [{ id: 8, nom: 'Laboratoire biomécanique',
          type_lieu: 'LABORATOIRE', capacite: 20 }],
      },
      groupes: [
        { ...BILAN.groupes[0], seances_persistees: 6, persistance: { effectuee: true },
          affectations_salle_cadrage_calculees: 2, affectations_salle_cadrage_persistees: 2 },
        { ...BILAN.groupes[1], statut: 'NON_PERSISTE', motif_echec: 'VALIDATION_BLOQUANTE',
          seances_persistees: 0, persistance: { effectuee: false, motif_refus: 'VALIDATION_BLOQUANTE' },
          affectations_salle_cadrage_calculees: 2, affectations_salle_cadrage_persistees: 0 },
      ],
    })
    routes()
    const user = userEvent.setup()
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(true)
    rendre()
    await screen.findByLabelText(/Année académique/)
    await user.click(screen.getByLabelText(/Publier directement/))
    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '3,4')
    await choisirModeAutomatique(user)
    expect(screen.queryByLabelText(/Publier directement/)).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Semaines planifiées')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Séances max / groupe / semaine')).not.toBeInTheDocument()
    expect(screen.queryByRole('group', { name: /Formations \/ parcours/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Prévisualiser sans persister/ })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Lancer la génération automatique/ }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/',
      expect.objectContaining({ semaines: [], parametres: expect.objectContaining({
        mode_generation: 'automatique', publier_direct: false,
        max_seances_par_groupe_semaine: null,
      }) })))
    expect(apiMock.post).not.toHaveBeenCalledWith('/edts/campagnes/1/publier/', expect.anything())
    const causes = await screen.findByText('Pourquoi ce bilan est partiel :')
    expect(causes.closest('[role="alert"]')).toHaveTextContent('Validation bloquante : 1 groupe(s)')
    for (const [libelle, valeur] of [
      ['groupes planifiés (calculés)', '2'], ['groupes enregistrés', '1'],
      ['étudiants couverts (calculés)', '3752'], ['étudiants couverts (enregistrés)', '1751'],
      ['séances placées (calculées)', '9'], ['séances enregistrées', '6'],
      ['EDT enregistrés', '1'],
    ]) {
      expect(within(screen.getByText(libelle).closest('.getinjs-compte')).getByText(valeur))
        .toBeInTheDocument()
    }
    const alerte = screen.getByRole('status')
    expect(alerte).toHaveTextContent('4 bloc(s) calculé(s)')
    expect(alerte).toHaveTextContent('2 bloc(s) enregistré(s)')
    expect(alerte).toHaveTextContent('1 salle(s) distincte(s)')
    expect(within(alerte).getByText('Afficher les salles CADRAGE concernées').closest('details'))
      .not.toHaveAttribute('open')
    const table = screen.getByRole('table', { name: /Bilan par groupe/ })
    expect(within(table).getByRole('columnheader', { name: 'Enregistrées' })).toBeInTheDocument()
    expect(within(table).getByRole('row', { name: /L1-G2/ })).toHaveTextContent('0')
    confirmation.mockRestore()
  })

  it('signale immédiatement un suivi HTTP 401 sans prétendre que le calcul a échoué', async () => {
    const user = userEvent.setup()
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiController.replaceRoute('/edts/campagnes/1/statut/', () =>
      Promise.reject(Object.assign(new Error('Accès refusé'), { response: { status: 401 } })))
    rendre()
    await screen.findByLabelText(/Année académique/)
    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '1,2')
    await choisirModeAutomatique(user)
    await user.click(screen.getByRole('button', { name: /Lancer la génération automatique/i }))
    expect(await screen.findByRole('alert')).toHaveTextContent(/Suivi indisponible.*HTTP 401/)
    expect(apiMock.get).not.toHaveBeenCalledWith('/edts/campagnes/1/resultat/')
    confirmation.mockRestore()
  })

  it('ignore les cases cochées dans le mode automatique, après confirmation', async () => {
    const user = userEvent.setup()
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(true)
    rendre()
    await choisirPerimetre(user)
    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '1,2')
    await choisirModeAutomatique(user)
    await user.click(screen.getByRole('button', { name: /Lancer la génération automatique/i }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/',
      expect.objectContaining({ perimetre: {
        formations: [], niveaux: [], groupes: [], semestres: [],
      } })))
    confirmation.mockRestore()
  })

  it('Tout sélectionner coche uniquement les options visibles et se décoche', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByText('L1-G1 — Licence en Journalisme')
    const filieres = screen.getByRole('group', { name: /Filières/ })
    const formations = screen.getByRole('group', { name: /Formations \/ parcours/ })
    const niveaux = screen.getByRole('group', { name: /Niveaux/ })
    const groupes = screen.getByRole('group', { name: /Groupes/ })
    const semestres = screen.getByRole('group', { name: /Semestres/ })
    await user.click(within(filieres).getByRole('checkbox', { name: 'F01' }))
    await user.click(within(formations).getByRole('checkbox', { name: /Tout sélectionner/ }))
    expect(within(formations).getByRole('checkbox', { name: 'Licence en Journalisme' })).toBeChecked()
    expect(within(formations).queryByRole('checkbox', { name: 'Licence en Communication' })).not.toBeInTheDocument()
    await user.click(within(niveaux).getByRole('checkbox', { name: /Tout sélectionner/ }))
    await user.click(within(groupes).getByRole('checkbox', { name: /Tout sélectionner/ }))
    await user.click(within(semestres).getByRole('checkbox', { name: /Tout sélectionner/ }))
    expect(within(groupes).getByRole('checkbox', { name: /L1-G1/ })).toBeChecked()
    expect(within(semestres).getByRole('checkbox', { name: 'Semestre 10 (S10)' })).toBeChecked()
    await user.click(within(groupes).getByRole('checkbox', { name: /Tout sélectionner/ }))
    expect(within(groupes).getByRole('checkbox', { name: /L1-G1/ })).not.toBeChecked()
  })

  it('propose une année provisoire même si le champ manuel contient seulement 1', async () => {
    const user = userEvent.setup()
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(false)
    rendre()
    await choisirModeAutomatique(user)
    await screen.findByText(/Calendrier automatique provisoire/)
    await user.click(screen.getByRole('button', { name: /Lancer la génération automatique/i }))
    expect(confirmation).toHaveBeenCalledWith(expect.stringContaining('semaines 1 à'))
    expect(apiMock.post).not.toHaveBeenCalledWith('/edts/campagnes/', expect.anything())
    confirmation.mockRestore()
  })

  it('ne lance pas la génération automatique si la confirmation est refusée', async () => {
    const user = userEvent.setup()
    const confirmation = vi.spyOn(window, 'confirm').mockReturnValue(false)
    rendre()
    await screen.findByLabelText(/Année académique/)
    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '1,2')
    await choisirModeAutomatique(user)
    await user.click(screen.getByRole('button', { name: /Lancer la génération automatique/i }))
    expect(apiMock.post).not.toHaveBeenCalledWith('/edts/campagnes/', expect.anything())
    confirmation.mockRestore()
  })

  it('refuse une génération manuelle sans sélection et sans prévisualisation correspondante', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)
    // Sans aperçu : le bouton de génération manuelle est désactivé.
    const boutonGen = screen.getByRole('button', { name: /Lancer la génération manuelle/i })
    expect(boutonGen).toBeDisabled()
    expect(apiMock.post).not.toHaveBeenCalledWith('/edts/campagnes/', expect.anything())
    await choisirPerimetre(user)
    // Après sélection mais sans prévisualisation : le bouton reste désactivé.
    expect(screen.getByRole('button', { name: /Lancer la génération manuelle/i })).toBeDisabled()
    expect(apiMock.post).not.toHaveBeenCalledWith('/edts/campagnes/', expect.anything())
    // Prévisualiser crée l'aperçu : le bouton devient activé et l'API peut être appelée.
    await user.click(screen.getByRole('button', { name: /Prévisualiser sans persister/i }))
    await screen.findByRole('table', { name: /Bilan par groupe/i })
    const boutonGenApres = screen.getByRole('button', { name: /Lancer la génération manuelle/i })
    expect(boutonGenApres).not.toBeDisabled()
    await user.click(boutonGenApres)
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/', expect.anything()),
    )
  })

  it('prévisualise puis lance la génération manuelle pour les seules cases cochées', async () => {
    const user = userEvent.setup()
    rendre()
    await choisirPerimetre(user)
    await user.click(screen.getByRole('button', { name: /Prévisualiser sans persister/i }))
    await screen.findByRole('table', { name: /Bilan par groupe/i })
    await user.click(screen.getByRole('button', { name: /Lancer la génération manuelle/i }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/',
      expect.objectContaining({ perimetre: {
        formations: [1], niveaux: [1], groupes: [11], semestres: [1],
      } })))
  })

  it('prévisualise sans persister (aucun brouillon écrit)', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)

    await choisirPerimetre(user)
    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '1,2')
    await user.click(screen.getByRole('button', { name: /Prévisualiser sans persister/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/edts/lmd/generate-annee/', {
        annee_academique_id: 2,
        semaines: [1, 2],
        persister: false,
        remplacer: true,
        inclure_maquette: true,
        formations: [1],
        niveaux: [1],
        groupes: [11],
        semestres: [1],
        inclure_samedi: true,
        eviter_pause_meridienne: true,
        max_seances_par_groupe_semaine: 30,
      }),
    )

    expect((await screen.findAllByText('Partiel')).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('Pourquoi ce bilan est partiel :').closest('[role="alert"]'))
      .toHaveTextContent('CAPACITE_SALLE_INSUFFISANTE : 1 groupe(s)')
    const bilanTable = screen.getByRole('table', { name: /Bilan par groupe/i })
    expect(within(bilanTable).getByRole('cell', { name: 'L1-G2' })).toBeInTheDocument()
    const couverts = screen.getByText('étudiants couverts').closest('.getinjs-compte')
    expect(within(couverts).getByText('3752')).toBeInTheDocument()
    const nonPlacees = screen.getByText('séances non placées').closest('.getinjs-compte')
    expect(within(nonPlacees).getByText('3')).toBeInTheDocument()
  })

  it('signale les affectations fondées sur des salles CADRAGE', async () => {
    apiController.reset()
    apiController.setRoute('/edts/lmd/generate-annee/', {
      ...BILAN,
      totaux: {
        ...BILAN.totaux,
        affectations_salle_cadrage: 2,
        salles_cadrage_utilisees: [{
          id: 8, nom: 'Laboratoire biomécanique', type_lieu: 'LABORATOIRE',
          capacite: 20, fiabilite: 'CADRAGE',
          source_document: 'Inventaire ; Estimation heuristique completer_salles',
        }],
      },
      groupes: [{
        ...BILAN.groupes[0],
        affectations_salle_cadrage: 2,
        salles_cadrage: [{
          id: 8, nom: 'Laboratoire biomécanique', type_lieu: 'LABORATOIRE',
          capacite: 20, fiabilite: 'CADRAGE',
          source_document: 'Inventaire ; Estimation heuristique completer_salles',
        }],
      }],
    })
    routes()
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)
    await choisirPerimetre(user)
    await user.click(screen.getByRole('button', { name: /Prévisualiser sans persister/i }))

    const alerte = await screen.findByRole('status')
    expect(alerte).toHaveTextContent('2 bloc(s) calculé(s)')
    expect(alerte).toHaveTextContent('1 salle(s) distincte(s)')
    const liste = within(alerte).getByText('Afficher les salles CADRAGE concernées').closest('details')
    expect(liste).not.toHaveAttribute('open')
    await user.click(within(alerte).getByText('Afficher les salles CADRAGE concernées'))
    expect(liste).toHaveAttribute('open')
    expect(within(liste).getByText(/Laboratoire biomécanique/)).toBeInTheDocument()
    const bilanTable = screen.getByRole('table', { name: /Bilan par groupe/i })
    expect(within(bilanTable).getByText(/Salle CADRAGE : 2 bloc\(s\) calculé\(s\)/))
      .toBeInTheDocument()
  })

  it('traduit le motif d’échec des groupes et compte les non planifiés', async () => {
    // Route surchargée : reset puis déclaration AVANT routes() (premier
    // motif gagnant dans le mock, le beforeEach a déjà posé la route type).
    apiController.reset()
    apiController.setRoute('/edts/lmd/generate-annee/', {
      ...BILAN,
      status_global: 'IMPOSSIBLE',
      totaux: {
        ...BILAN.totaux,
        nb_groupes_planifies: 0, nb_groupes_complets: 0, nb_groupes_non_planifies: 2,
        seances_placees: 0, seances_non_placees: 12,
      },
      groupes: [{
        groupe_id: 13, groupe: 'L1-G9', formation: 'Licence en Journalisme',
        parcours: null, niveau: 'L1', vague: null, effectif: 33,
        statut: 'GENERATION_IMPOSSIBLE', motif_echec: 'PLACEMENT_IMPOSSIBLE',
        seances_attendues: 12, seances_placees: 0, seances_non_placees: 12,
      }],
    })
    routes()
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)
    await choisirPerimetre(user)
    await user.click(screen.getByRole('button', { name: /Prévisualiser sans persister/i }))

    const bilanTable = await screen.findByRole('table', { name: /Bilan par groupe/i })
    expect(within(bilanTable).getByText(
      'Aucune combinaison créneau/salle ne satisfait les contraintes',
    )).toBeInTheDocument()
    expect(within(bilanTable).queryByText('PLACEMENT_IMPOSSIBLE')).not.toBeInTheDocument()
    const nonPlanifies = screen.getByText('non planifiés').closest('.getinjs-compte')
    expect(within(nonPlanifies).getByText('2')).toBeInTheDocument()
  })

  it('affiche l’historique réel des générations et les EDT versionnés', async () => {
    rendre()
    expect(await screen.findByText('Historique des générations')).toBeInTheDocument()
    expect(await screen.findByText('Toutes filières')).toBeInTheDocument()
    expect(screen.getByText('S1, S2')).toBeInTheDocument()
    expect(screen.getByText('75 %')).toBeInTheDocument()
    expect(screen.getByText('12,5 s')).toBeInTheDocument()
    expect(screen.getByText('terminée')).toBeInTheDocument()
    expect(screen.getByText('Emplois du temps versionnés')).toBeInTheDocument()
    expect(screen.getByText('EDT Licence en Journalisme L1 — S1 (exemple GET)'))
      .toBeInTheDocument()
    expect(screen.getByText(/12 séances · V1/)).toBeInTheDocument()
  })

  it('affiche la cause persistante d’une génération en échec dans l’historique', async () => {
    apiController.reset()
    apiController.setRoute('/edts/campagnes/historique/', {
      executions: [{ ...HISTORIQUE.executions[0], statut: 'ECHEC',
        erreur: 'Exécution interrompue : le serveur a redémarré pendant la génération.' }],
    })
    routes()
    rendre()
    expect(await screen.findByRole('alert')).toHaveTextContent('Exécution interrompue')
  })

  it('charge explicitement 500 événements et pagine l’historique par 15', async () => {
    const user = userEvent.setup()
    // 20 exécutions : la première requête demande limite=500 au serveur.
    apiController.reset()
    // Déclarée AVANT routes() : premier match gagnant dans le mock.
    apiController.setRoute('/edts/campagnes/historique/', {
      executions: Array.from({ length: 20 }, (_, i) => ({
        id: 50 + i, libelle: `Génération ${i + 1}`, annee_academique: '2026-2027',
        date: '2026-11-04T02:39:00Z', statut: 'TERMINE', duree_ms: 300,
        perimetre: { filieres: [], formations: [`Formation ${i + 1}`], niveaux: [], groupes: [] },
        semestres: ['S1'], seances_placees: 9, seances_attendues: 12,
        couverture_pct: 75.0, conflits: 0,
      })),
    })
    routes()
    rendre()
    expect(await screen.findByText('Formation 1')).toBeInTheDocument()
    expect(screen.getByText('Chargement explicite : 500 événements')).toBeInTheDocument()
    expect(screen.getByText('20 chargé(s)')).toBeInTheDocument()
    const appelHistorique = apiController.api.get.mock.calls
      .find(([chemin]) => chemin.includes('/edts/campagnes/historique/'))
    expect(appelHistorique).toBeTruthy()
    expect(appelHistorique[1]).toEqual({ params: { limite: 500 } })
    expect(screen.getByText('Événements 1 à 15 sur 20')).toBeInTheDocument()
    expect(screen.getByText('Page 1 sur 2')).toBeInTheDocument()
    expect(screen.queryByText('Formation 16')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Suivant/ }))
    expect(screen.getByText('Formation 16')).toBeInTheDocument()
    expect(screen.getByText('Événements 16 à 20 sur 20')).toBeInTheDocument()
  })

  it('télécharge le document de conception depuis le backend', async () => {
    const user = userEvent.setup()
    const clickOriginal = HTMLAnchorElement.prototype.click
    HTMLAnchorElement.prototype.click = vi.fn()
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn()
    apiMock.getBlob.mockResolvedValueOnce({
      blob: new Blob(['conception']), fileName: 'Conception-GET-INJS.txt',
    })

    rendre()
    await user.click(screen.getByRole('button', { name: /Conception GET-INJS/i }))

    await waitFor(() => expect(apiMock.getBlob).toHaveBeenCalledWith('/edts/lmd/conception/'))
    HTMLAnchorElement.prototype.click = clickOriginal
  })

  it('nomme chaque tableau par une légende (accessibilité)', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)
    await choisirPerimetre(user)
    await user.click(screen.getByRole('button', { name: /Prévisualiser sans persister/i }))
    await screen.findByText('Bilan par groupe — aucune ligne n’est masquée')
    expect(screen.getByRole('table', { name: /Bilan par groupe/i })).toBeInTheDocument()
  })

  it('affiche la liste des cohortes importées de l’année', async () => {
    rendre()
    expect(await screen.findByRole('table', { name: /Cohortes importées/i })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '1751' })).toBeInTheDocument()
    expect(screen.getByRole('cell', { name: '2001' })).toBeInTheDocument()
  })
})
