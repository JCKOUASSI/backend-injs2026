/**
 * Maquettes pédagogiques — gestion de liste (LOT « maquettes opérationnelles »).
 *
 * Complète `Maquettes.test.jsx` (chargement, création, workflow) sur les
 * fonctions de gestion :
 *
 * sélection (individuelle, multiple, globale), états des boutons
 * du panneau d'actions, les exports (Word/PDF/Excel/CSV, avec ou sans
 * sélection), l'import en deux temps (aperçu puis intégration transactionnelle),
 * la modification et la suppression avec bilan des blocages métier.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, within, fireEvent, waitFor } from '@testing-library/react'

const naviguer = vi.fn()

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal()
  return { ...actual, useNavigate: () => naviguer }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Maquettes from '@/pages/scolarite/Maquettes'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                     */
/* ------------------------------------------------------------------ */

const maquette = (id, overrides = {}) => ({
  id,
  libelle: `Maquette ${id}`,
  annee_academique_id: 1,
  annee_academique: '2026-2027',
  ref_formation_id: 10,
  ref_formation: `LICENCE ${id}`,
  parcours_id: null,
  parcours: null,
  niveau: 'L1',
  version: 1,
  statut: 'BROUILLON',
  nb_ue: 2,
  total_credits: 60,
  ...overrides,
})

const CATALOGUE = [
  maquette(1, { ref_formation: 'LICENCE STAPS', statut: 'BROUILLON' }),
  maquette(2, { ref_formation: 'LICENCE MANAGEMENT', statut: 'ACTIVE', version: 2 }),
  maquette(3, { ref_formation: 'LICENCE ANDRAGOGIE', statut: 'VALIDEE' }),
]

const ANALYSE_OK = {
  importable: true,
  fichier: 'maquettes.csv',
  lignes: [
    {
      ligne: 2, annee: '2026-2027', formation: 'LICENCE STAPS', parcours: '',
      niveau: 'L1', semestre: 'S1', ue_code: 'UE1', ue_intitule: 'UE test',
      ecue_code: 'EC1', ecue_intitule: 'ECUE test', statut: 'ok', messages: [],
    },
  ],
  lignes_tronquees: 0,
  maquettes: [
    {
      libelle: 'LICENCE STAPS – L1', annee: '2026-2027', formation: 'LICENCE STAPS',
      parcours: null, niveau: 'L1', action: 'creation', version: null,
      verrouillee: false, nb_ue: 1, nb_ecue: 1, credits: 6,
    },
  ],
  erreurs: [],
  avertissements: [],
  resume: {
    lignes_lues: 1, lignes_valides: 1, lignes_ignorees: 0, doublons: 0,
    maquettes: 1, ue: 1, ecue: 1, erreurs: 0, avertissements: 0,
  },
}

const RAPPORT_OK = {
  ...ANALYSE_OK,
  bilan: {
    maquettes_creees: 1, maquettes_completees: 0,
    ue_creees: 1, ue_mises_a_jour: 0, ecue_creees: 1, ecue_mises_a_jour: 0,
    maquettes: [{ id: 42, libelle: 'LICENCE STAPS – L1 – 2026-2027 (v3)', statut: 'BROUILLON', action: 'CREATION' }],
  },
}

function rendrePage() {
  apiController.setMe(makeUser('ADMIN'))
  return renderWithProviders(<Maquettes />, {
    authUser: makeUser('ADMIN'),
    initialEntries: ['/scolarite/maquettes'],
    routePattern: '/scolarite/maquettes',
  })
}

const caseLigne = (id) => screen.getByLabelText(new RegExp(`^Sélectionner la maquette Maquette ${id}`, 'i'))
const bouton = (nom) => screen.getByRole('button', { name: nom })
const compteur = () => screen.getByTestId('maq-compteur-selection').textContent

beforeEach(() => {
  apiController.reset()
  naviguer.mockClear()
  apiController.setRoute('/scolarite/maquettes/', CATALOGUE)
  apiController.setRoute('/scolarite/ref/annees/', [])
  apiController.setRoute('/scolarite/ref/formations/', [])
  apiController.setRoute('/scolarite/ref/niveaux/', [])
  apiController.setRoute('/scolarite/ref/parcours/', [])
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
})

afterEach(() => {
  vi.restoreAllMocks()
})

/* ------------------------------------------------------------------ */
/* Sélection                                                           */
/* ------------------------------------------------------------------ */

describe('Maquettes — sélection', () => {
  it('affiche une case par maquette et la case d’en-tête', async () => {
    rendrePage()
    await flushPromises(2)

    expect(screen.getByLabelText('Sélectionner toutes les maquettes')).toBeInTheDocument()
    expect(caseLigne(1)).toBeInTheDocument()
    expect(caseLigne(2)).toBeInTheDocument()
    expect(caseLigne(3)).toBeInTheDocument()
    expect(compteur()).toContain('0 sélectionnée')
  })

  it('sélectionne une maquette et met à jour le compteur', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    await flushPromises()

    expect(caseLigne(1)).toBeChecked()
    expect(compteur()).toContain('1 sélectionnée')
    expect(screen.queryByText('Aucune maquette sélectionnée')).not.toBeInTheDocument()
  })

  it('sélectionne plusieurs maquettes simultanément', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    fireEvent.click(caseLigne(3))
    await flushPromises()

    expect(caseLigne(1)).toBeChecked()
    expect(caseLigne(3)).toBeChecked()
    expect(compteur()).toContain('2 sélectionnées')
  })

  it('sélectionne puis désélectionne toutes les maquettes', async () => {
    rendrePage()
    await flushPromises(2)

    const entete = screen.getByLabelText('Sélectionner toutes les maquettes')
    fireEvent.click(entete)
    await flushPromises()

    expect(caseLigne(1)).toBeChecked()
    expect(caseLigne(2)).toBeChecked()
    expect(caseLigne(3)).toBeChecked()
    expect(compteur()).toContain('3 sélectionnées')

    fireEvent.click(entete)
    await flushPromises()

    expect(caseLigne(1)).not.toBeChecked()
    expect(compteur()).toContain('0 sélectionnée')
  })

  it('conserve la sélection lors d’un changement de filtre', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(2))
    await flushPromises()

    // Le filtre « formation » est local : la maquette 2 (MANAGEMENT) sort de
    // la vue, mais reste sélectionnée pour les exports et suppressions.
    fireEvent.change(screen.getByLabelText('Filtrer par formation'), {
      target: { value: 'LICENCE STAPS' },
    })
    await flushPromises()

    expect(screen.queryByLabelText(/Sélectionner la maquette Maquette 2/)).not.toBeInTheDocument()
    expect(caseLigne(1)).toBeInTheDocument()
    expect(compteur()).toContain('1 sélectionnée')
  })
})

/* ------------------------------------------------------------------ */
/* Panneau d'actions                                                   */
/* ------------------------------------------------------------------ */

describe('Maquettes — panneau d’actions', () => {
  it('désactive Visualiser/Modifier/Supprimer sans sélection', async () => {
    rendrePage()
    await flushPromises(2)

    expect(bouton('Créer une maquette')).toBeEnabled()
    expect(bouton('Visualiser la maquette sélectionnée')).toBeDisabled()
    expect(bouton('Modifier la maquette sélectionnée')).toBeDisabled()
    expect(bouton('Supprimer les maquettes sélectionnées')).toBeDisabled()
  })

  it('active Visualiser et Modifier sur une seule maquette brouillon', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    await flushPromises()

    expect(bouton('Visualiser la maquette sélectionnée')).toBeEnabled()
    expect(bouton('Modifier la maquette sélectionnée')).toBeEnabled()
  })

  it('désactive Modifier sur une maquette gelée et sur une sélection multiple', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(2)) // ACTIVE
    await flushPromises()
    expect(bouton('Modifier la maquette sélectionnée')).toBeDisabled()
    expect(bouton('Visualiser la maquette sélectionnée')).toBeEnabled()

    fireEvent.click(caseLigne(1))
    await flushPromises()
    expect(bouton('Visualiser la maquette sélectionnée')).toBeDisabled()
    expect(bouton('Supprimer les maquettes sélectionnées')).toBeEnabled()
  })

  it('ouvre la fiche détaillée avec Visualiser', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    fireEvent.click(bouton('Visualiser la maquette sélectionnée'))
    await flushPromises()

    expect(naviguer).toHaveBeenCalledWith('/scolarite/maquettes/1')
  })

  it('modifie le libellé d’une maquette brouillon', async () => {
    apiController.setRoute(/\/scolarite\/maquettes\/1\/modifier\/$/, { id: 1 })
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    fireEvent.click(bouton('Modifier la maquette sélectionnée'))
    await flushPromises(2)

    const dialogue = screen.getByRole('dialog')
    const champ = within(dialogue).getByLabelText('Libellé')
    fireEvent.change(champ, { target: { value: 'Nouveau libellé' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await flushPromises(2)

    const appel = apiMock.patch.mock.calls.find(([chemin]) => /\/scolarite\/maquettes\/1\/modifier\/$/.test(chemin))
    expect(appel).toBeTruthy()
    expect(appel[1].libelle).toBe('Nouveau libellé')
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument())
  })

  it('« Créer » amène au formulaire existant sans le dupliquer', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(bouton('Créer une maquette'))
    await flushPromises()

    // Un seul formulaire de création dans la page (réutilisation, pas de doublon).
    expect(screen.getAllByLabelText(/Année académique \*/)).toHaveLength(1)
    expect(document.activeElement).toBe(screen.getByLabelText(/Année académique \*/))
  })
})

/* ------------------------------------------------------------------ */
/* Suppression                                                         */
/* ------------------------------------------------------------------ */

describe('Maquettes — suppression', () => {
  it('demande confirmation en précisant le nombre de maquettes', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    fireEvent.click(caseLigne(2))
    fireEvent.click(bouton('Supprimer les maquettes sélectionnées'))
    await flushPromises()

    const dialogue = screen.getByRole('dialog')
    expect(within(dialogue).getByText(/Supprimer 2 maquettes/)).toBeInTheDocument()
  })

  it('supprime les maquettes confirmées', async () => {
    apiController.setRoute('/scolarite/maquettes/supprimer/', {
      supprimees: [{ id: 1, libelle: 'Maquette 1' }],
      bloquees: [],
      introuvables: [],
      resume: { demandees: 1, supprimees: 1, bloquees: 0, introuvables: 0 },
    })
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    fireEvent.click(bouton('Supprimer les maquettes sélectionnées'))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
    await flushPromises(2)

    const appel = apiMock.post.mock.calls.find(([chemin]) => chemin === '/scolarite/maquettes/supprimer/')
    expect(appel[1]).toEqual({ ids: [1] })
  })

  it('affiche le bilan des maquettes bloquées (maquette gelée)', async () => {
    apiController.setRoute(
      '/scolarite/maquettes/supprimer/',
      {
        error: 'Aucune maquette supprimée : toutes sont bloquées.',
        supprimees: [],
        bloquees: [{ id: 2, libelle: 'Maquette 2', motif: 'maquette active : immuable.' }],
        introuvables: [],
        resume: { demandees: 1, supprimees: 0, bloquees: 1, introuvables: 0 },
      },
      409,
    )
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(2))
    fireEvent.click(bouton('Supprimer les maquettes sélectionnées'))
    fireEvent.click(await screen.findByRole('button', { name: 'Supprimer' }))
    await flushPromises(2)

    const bilan = await screen.findByRole('dialog', { name: /Bilan de la suppression/ })
    expect(within(bilan).getByText(/immuable/)).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* Exports                                                             */
/* ------------------------------------------------------------------ */

describe('Maquettes — exports', () => {
  it('propose les quatre formats', async () => {
    rendrePage()
    await flushPromises(2)

    expect(bouton('Export Word')).toBeInTheDocument()
    expect(bouton('Export PDF')).toBeInTheDocument()
    expect(bouton('Export Excel')).toBeInTheDocument()
    expect(bouton('Export CSV')).toBeInTheDocument()
  })

  it('exporte toutes les maquettes sans sélection', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(bouton('Export CSV'))
    await flushPromises(2)

    const chemin = apiMock.getBlob.mock.calls[0][0]
    expect(chemin).toContain('/scolarite/maquettes/exporter/csv/')
    expect(chemin).not.toContain('ids=')
    expect(URL.createObjectURL).toHaveBeenCalled()
  })

  it('exporte uniquement les maquettes sélectionnées', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(caseLigne(1))
    fireEvent.click(caseLigne(3))
    fireEvent.click(bouton('Export Excel'))
    await flushPromises(2)

    const chemin = apiMock.getBlob.mock.calls[0][0]
    expect(chemin).toContain('/scolarite/maquettes/exporter/xlsx/')
    expect(chemin).toContain('ids=1%2C3')
  })

  it('ajoute le détail pédagogique à la demande', async () => {
    rendrePage()
    await flushPromises(2)

    fireEvent.click(screen.getByLabelText(/Inclure le détail pédagogique/))
    fireEvent.click(bouton('Export PDF'))
    await flushPromises(2)

    expect(apiMock.getBlob.mock.calls[0][0]).toContain('detail=1')
  })
})

/* ------------------------------------------------------------------ */
/* Imports                                                             */
/* ------------------------------------------------------------------ */

describe('Maquettes — imports', () => {
  const champFichier = (conteneur) => conteneur.querySelector('input[type="file"]')

  const choisirFichier = (conteneur, nom = 'maquettes.csv') => {
    const fichier = new File(['ANNEE;FORMATION'], nom, { type: 'text/csv' })
    fireEvent.change(champFichier(conteneur), { target: { files: [fichier] } })
  }

  it('analyse le fichier et affiche la prévisualisation', async () => {
    apiController.setRoute('/scolarite/maquettes/importer/', ANALYSE_OK)
    const { container } = rendrePage()
    await flushPromises(2)

    choisirFichier(container)
    await flushPromises(2)

    const dialogue = await screen.findByRole('dialog')
    expect(within(dialogue).getByText(/Prévisualisation de l’import/)).toBeInTheDocument()
    expect(within(dialogue).getByText('LICENCE STAPS – L1')).toBeInTheDocument()
    expect(within(dialogue).getByText('création')).toBeInTheDocument()

    const appel = apiMock.post.mock.calls.find(([chemin]) => chemin === '/scolarite/maquettes/importer/')
    expect(appel[1].get('mode')).toBe('apercu')
  })

  it('confirme l’import et affiche le rapport final', async () => {
    apiController.setRoute('/scolarite/maquettes/importer/', (chemin, corps) => (
      corps instanceof FormData && corps.get('mode') === 'importer' ? RAPPORT_OK : ANALYSE_OK
    ))
    const { container } = rendrePage()
    await flushPromises(2)

    choisirFichier(container)
    await flushPromises(2)

    fireEvent.click(await screen.findByRole('button', { name: "Confirmer l'import" }))
    await flushPromises(3)

    expect(await screen.findByText(/Import terminé/)).toBeInTheDocument()
    const appels = apiMock.post.mock.calls.filter(([chemin]) => chemin === '/scolarite/maquettes/importer/')
    expect(appels).toHaveLength(2)
    expect(appels[1][1].get('mode')).toBe('importer')
  })

  it('bloque la confirmation quand le fichier contient des erreurs', async () => {
    apiController.setRoute('/scolarite/maquettes/importer/', {
      ...ANALYSE_OK,
      importable: false,
      erreurs: [{ ligne: 3, message: 'formation « INCONNUE » absente du référentiel.' }],
      resume: { ...ANALYSE_OK.resume, erreurs: 1, lignes_valides: 0 },
    })
    const { container } = rendrePage()
    await flushPromises(2)

    choisirFichier(container)
    await flushPromises(2)

    const dialogue = await screen.findByRole('dialog')
    expect(within(dialogue).getByText(/Erreurs bloquantes/)).toBeInTheDocument()
    expect(within(dialogue).getByText(/INCONNUE/)).toBeInTheDocument()
    expect(within(dialogue).getByRole('button', { name: "Confirmer l'import" })).toBeDisabled()
  })

  it('signale un fichier refusé avant analyse', async () => {
    // Refus serveur : la route rejette comme le ferait `services/api` sur 400.
    apiController.setRoute(
      '/scolarite/maquettes/importer/',
      () => Promise.reject(Object.assign(new Error('Bad Request'), {
        response: {
          status: 400,
          data: { error: 'Format non pris en charge : utilisez un fichier .xlsx ou .csv.' },
        },
      })),
    )
    const { container } = rendrePage()
    await flushPromises(2)

    choisirFichier(container, 'notes.pdf')
    await flushPromises(2)

    expect(await screen.findByRole('alert')).toHaveTextContent(/Format non pris en charge/)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
