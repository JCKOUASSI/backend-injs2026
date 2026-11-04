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
  { id: 2, libelle: '2025-2026', courante: true },
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
    duree_ms: 300,
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
  apiController.setRoute('/edts/campagnes/1/resultat/', RESULTAT_CAMPAGNE)
}

function rendre() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  return render(
    <AllProviders authUser={user}>
      <GenerationAnnuelle />
    </AllProviders>,
  )
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
    expect(screen.getByLabelText('Filière (mention)')).toBeInTheDocument()
    expect(screen.getByLabelText('Formation / parcours')).toBeInTheDocument()
    expect(screen.getByLabelText('Niveau')).toBeInTheDocument()
    expect(screen.getByLabelText('Groupe (optionnel)')).toBeInTheDocument()
    expect(screen.getByLabelText('Semestre')).toBeInTheDocument()
    expect(screen.getByLabelText('Séances max / groupe / semaine')).toHaveValue(30)
    expect(screen.getByLabelText(/Inclure le samedi/)).toBeChecked()
    expect(screen.getByLabelText(/Éviter la pause méridienne/)).toBeChecked()
    expect(screen.getByText('Comment le moteur décide')).toBeInTheDocument()
    expect(screen.getByText('Règles métier appliquées par le moteur')).toBeInTheDocument()
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
        { headers: { 'Content-Type': 'multipart/form-data' } },
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
        expect.anything(),
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

  it('lance la génération : campagne créée, préparée, démarrée, bilan affiché', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)
    await user.click(screen.getByRole('button', { name: /Lancer la génération/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/', expect.objectContaining({
        annee_academique_id: 2,
        perimetre: { formations: [], niveaux: [], groupes: [], semestres: [] },
        parametres: expect.objectContaining({
          persister: true,
          inclure_samedi: true,
          eviter_pause_meridienne: true,
          max_seances_par_groupe_semaine: 30,
        }),
      })),
    )
    expect(apiMock.post).toHaveBeenCalledWith('/edts/campagnes/1/donnees-pretes/', {})
    expect(apiMock.post).toHaveBeenCalledWith(
      '/edts/campagnes/1/demarrer/', { asynchrone: false })

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

  it('prévisualise sans persister (aucun brouillon écrit)', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText(/Année académique/)

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
        formations: [],
        niveaux: [],
        groupes: [],
        semestres: [],
        inclure_samedi: true,
        eviter_pause_meridienne: true,
        max_seances_par_groupe_semaine: 30,
      }),
    )

    expect((await screen.findAllByText('Partiel')).length).toBeGreaterThanOrEqual(2)
    const bilanTable = screen.getByRole('table', { name: /Bilan par groupe/i })
    expect(within(bilanTable).getByRole('cell', { name: 'L1-G2' })).toBeInTheDocument()
    const couverts = screen.getByText('étudiants couverts').closest('.getinjs-compte')
    expect(within(couverts).getByText('3752')).toBeInTheDocument()
    const nonPlacees = screen.getByText('séances non placées').closest('.getinjs-compte')
    expect(within(nonPlacees).getByText('3')).toBeInTheDocument()
  })

  it('affiche l’historique réel des générations et les EDT versionnés', async () => {
    rendre()
    expect(await screen.findByText('Historique des générations')).toBeInTheDocument()
    expect(await screen.findByText('Toutes filières')).toBeInTheDocument()
    expect(screen.getByText('S1, S2')).toBeInTheDocument()
    expect(screen.getByText('75 %')).toBeInTheDocument()
    expect(screen.getByText('0.3 s')).toBeInTheDocument()
    expect(screen.getByText('terminée')).toBeInTheDocument()
    expect(screen.getByText('Emplois du temps versionnés')).toBeInTheDocument()
    expect(screen.getByText('EDT Licence en Journalisme L1 — S1 (exemple GET)'))
      .toBeInTheDocument()
    expect(screen.getByText(/12 séances · V1/)).toBeInTheDocument()
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
