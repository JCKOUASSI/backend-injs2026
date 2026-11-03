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

function routes({ synthese = SYNTHESE } = {}) {
  apiController.setRoute('/scolarite/ref/annees/', ANNEES)
  apiController.setRoute('/edts/lmd/import/inscrits/synthese/', synthese)
  apiController.setRoute('/edts/lmd/import/inscrits/analyser/', RAPPORT)
  apiController.setRoute('/edts/lmd/import/inscrits/', { ...RAPPORT, applique: true, creees: 3 })
  apiController.setRoute('/edts/lmd/generate-annee/', BILAN)
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

describe('GET-INJS — génération annuelle et import des inscrits', () => {
  beforeEach(() => {
    apiController.reset()
    routes()
  })

  it('charge les années et sélectionne l’année courante', async () => {
    rendre()
    const select = await screen.findByLabelText('Année académique')
    await waitFor(() => expect(select).toHaveValue('2'))
    expect(
      within(select).getByRole('option', { name: '2025-2026 (courante)' }),
    ).toBeInTheDocument()
  })

  it('affiche l’effectif réel importé, sans valeur inventée', async () => {
    rendre()
    expect(await screen.findByText('3752')).toBeInTheDocument()
    expect(screen.getByText('étudiants importés')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
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
    await screen.findByLabelText('Année académique')
    expect(screen.queryByText('étudiants importés')).not.toBeInTheDocument()
  })

  it('analyse le fichier sans écrire et rend le rapport ligne par ligne', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique')

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

    // Chaque rejet est motivé : aucun rejet silencieux.
    expect(await screen.findByText('MATRICULE_MANQUANT')).toBeInTheDocument()
    expect(screen.getByText('NIVEAU_INCONNU')).toBeInTheDocument()
    expect(screen.getByText('Niveau « L9 » inconnu du référentiel INJS.')).toBeInTheDocument()

    // Compteurs lus dans le rapport, chacun sous son libellé.
    const valides = screen.getByText('valides').closest('.getinjs-compte')
    expect(within(valides).getByText('3')).toBeInTheDocument()
    const rejetees = screen.getByText('rejetées').closest('.getinjs-compte')
    expect(within(rejetees).getByText('2')).toBeInTheDocument()
  })

  it('importe réellement puis réactualise l’effectif', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique')

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
    // L'effectif affiché vient du backend après import, pas du fichier.
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

  it('génère l’année et expose le bilan par groupe, sans masquer les échecs', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique')

    await user.clear(screen.getByLabelText('Semaines planifiées'))
    await user.type(screen.getByLabelText('Semaines planifiées'), '1,2')
    await user.click(screen.getByRole('button', { name: /Générer l’année/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/edts/lmd/generate-annee/', {
        annee_academique_id: 2,
        semaines: [1, 2],
        persister: false,
        remplacer: true,
        inclure_maquette: true,
      }),
    )

    // « Partiel » apparaît deux fois : statut global et statut du groupe G2.
    expect((await screen.findAllByText('Partiel')).length).toBeGreaterThanOrEqual(2)
    // Le groupe complet et le groupe partiel sont tous deux listés — et
    // uniquement dans le tableau de bilan (le tableau des cohortes importées
    // porte les mêmes libellés mais un autre objet).
    const bilan = screen.getByRole('table', { name: /Bilan par groupe/i })
    expect(within(bilan).getByRole('cell', { name: 'L1-G1' })).toBeInTheDocument()
    expect(within(bilan).getByRole('cell', { name: 'L1-G2' })).toBeInTheDocument()
    expect(within(bilan).getByText('CAPACITE_SALLE_INSUFFISANTE')).toBeInTheDocument()
    expect(screen.queryByText('Impossible', { selector: '.badge' })).not.toBeInTheDocument()
    // Totaux réels du moteur (l'effectif de la synthèse apparaît aussi en
    // haut d'écran : on cible le libellé du bilan).
    const couverts = screen.getByText('étudiants couverts').closest('.getinjs-compte')
    expect(within(couverts).getByText('3752')).toBeInTheDocument()
    const nonPlacees = screen.getByText('séances non placées').closest('.getinjs-compte')
    expect(within(nonPlacees).getByText('3')).toBeInTheDocument()
  })

  it('ne persiste pas par défaut : aucun brouillon écrit sans action explicite', async () => {
    const user = userEvent.setup()
    rendre()
    await screen.findByLabelText('Année académique')
    await user.click(screen.getByRole('button', { name: /Générer l’année/i }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
    expect(apiMock.post.mock.calls[0][1]).toMatchObject({ persister: false })
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
    await screen.findByLabelText('Année académique')
    await user.click(screen.getByRole('button', { name: /Générer l’année/i }))
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
