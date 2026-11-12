/**
 * Tests du moteur commun Référentiels côté interface : export (4 formats),
 * import en 5 étapes, et services associés.
 *
 * Ces tests vérifient le comportement réel des composants rendus (pas
 * seulement l'existence des fonctions) : les boutons appellent la bonne route
 * avec le bon paramètre, le fichier est contrôlé avant envoi, et le rapport
 * final est affiché.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, act, fireEvent, waitFor, within } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import BarreExport from '@/components/referentiels/BarreExport'
import AssistantImport from '@/components/referentiels/AssistantImport'
import {
  FORMATS_EXPORT,
  MODES_IMPORT,
  controlerFichier,
  genererCsvAnomalies,
  nomDeFichierDepuis,
} from '@/services/referentiels'

const settle = async (n = 6) => {
  await act(async () => {
    await flushPromises(n)
  })
}

afterEach(async () => {
  await settle()
})

/** Construit un File-like (jsdom ne fournit pas File.text()). */
function fichier(nom, taille = 1024, type = 'text/csv') {
  const f = new File(['a'.repeat(taille)], nom, { type })
  return f
}

/** Route l'analyse et l'import vers des réponses distinctes et rejouables. */
function mockImport(analyse = ANALYSE_OK, rapport = RAPPORT_OK) {
  apiMock.post.mockReset?.()
  apiMock.post.mockImplementation((url) =>
    Promise.resolve({
      data: String(url).includes('/importer/analyse/') ? analyse : rapport,
    }),
  )
}

/** Déroule : sélection du fichier → analyse → correspondance → validation. */
async function jusquALaValidation() {
  const champ = screen.getByTestId('import-fichier')
  await act(async () => {
    fireEvent.change(champ, { target: { files: [fichier('f.csv')] } })
    await flushPromises(4)
  })
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /Analyser le fichier/i }))
    await flushPromises(6)
  })
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /Valider la correspondance/i }))
    await flushPromises(6)
  })
}

describe('Service référentiels — contrôle du fichier (étape 1)', () => {
  it('accepte les formats Excel et CSV', () => {
    expect(controlerFichier(fichier('donnees.xlsx'))).toBeNull()
    expect(controlerFichier(fichier('donnees.xls'))).toBeNull()
    expect(controlerFichier(fichier('donnees.csv'))).toBeNull()
  })

  it('refuse une extension non autorisée', () => {
    expect(controlerFichier(fichier('malware.exe'))).toMatch(/non pris en charge/i)
  })

  it('refuse un fichier vide', () => {
    expect(controlerFichier(fichier('vide.csv', 0))).toMatch(/vide/i)
  })

  it('refuse un fichier trop volumineux', () => {
    expect(controlerFichier(fichier('gros.csv', 11 * 1024 * 1024))).toMatch(/volumineux/i)
  })

  it('refuse l’absence de fichier', () => {
    expect(controlerFichier(null)).toMatch(/Aucun fichier/i)
  })
})

describe('Service référentiels — nom de fichier', () => {
  it('utilise le nom fourni par le serveur', () => {
    const nom = nomDeFichierDepuis(
      { 'content-disposition': 'attachment; filename="filieres_20261112-1400.csv"' },
      'filieres',
      'csv',
    )
    expect(nom).toBe('filieres_20261112-1400.csv')
  })

  it('reconstruit un nom horodaté à défaut', () => {
    const nom = nomDeFichierDepuis({}, 'filieres', 'pdf')
    expect(nom).toMatch(/^filieres_\d{8}-\d{4}\.pdf$/)
  })
})

describe('Service référentiels — CSV des anomalies', () => {
  it('produit un CSV UTF-8 au séparateur point-virgule', () => {
    const csv = genererCsvAnomalies([
      { ligne: 3, colonne: 'Code', valeur: '', message: 'Valeur obligatoire' },
    ])
    expect(csv.startsWith('﻿')).toBe(true) // BOM UTF-8
    expect(csv).toContain('Ligne;Colonne;Valeur;Message')
    expect(csv).toContain('3;Code;;Valeur obligatoire')
  })

  it('échappe les valeurs contenant le séparateur', () => {
    const csv = genererCsvAnomalies([
      { ligne: 2, colonne: 'Libellé', valeur: 'A;B', message: 'Doublon' },
    ])
    expect(csv).toContain('"A;B"')
  })

  it('reste valide sans anomalie', () => {
    expect(genererCsvAnomalies([])).toContain('Ligne;Colonne;Valeur;Message')
  })
})

describe('Barre d’export', () => {
  beforeEach(() => {
    apiController.reset?.()
    apiMock.get.mockReset?.()
    apiMock.post.mockReset?.()
  })

  it('propose les quatre formats obligatoires', () => {
    renderWithProviders(<BarreExport slug="filieres" total={12} />)
    FORMATS_EXPORT.forEach((format) => {
      expect(
        screen.getByRole('button', { name: new RegExp(format.libelle, 'i') }),
      ).toBeTruthy()
    })
    expect(screen.getByText(/12 enregistrements/)).toBeTruthy()
  })

  it('appelle la route d’export avec le paramètre « export »', async () => {
    // « format » est réservé par DRF (négociation de contenu) : le nom du
    // document passe par « export », sinon la réponse serait un 404.
    apiMock.getBlob.mockResolvedValue({
      blob: new Blob(['contenu'], { type: 'application/vnd.ms-excel' }),
      fileName: 'f.xlsx',
      contentType: 'application/vnd.ms-excel',
    })
    renderWithProviders(<BarreExport slug="filieres" filtres={{ search: 'alpha' }} />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Excel/i }))
      await flushPromises(6)
    })
    const [url, params] = apiMock.getBlob.mock.calls.at(-1)
    expect(url).toBe('/referentiels/filieres/exporter/')
    expect(params.export).toBe('xlsx')
    expect(params.search).toBe('alpha')
  })

  it('télécharge par la voie binaire, jamais par api.get', async () => {
    // Régression du bug d'export : le service appelait
    // `api.get(..., { responseType: 'blob' })`. Le client est bâti sur
    // `fetch`, où `responseType` n'existe pas : la réponse binaire était
    // lue en texte puis passée à `JSON.parse()`, et **tous** les exports
    // échouaient. On reproduit ici le comportement réel de `api.get` sur
    // du binaire, et l'export doit malgré tout aboutir.
    apiMock.get.mockImplementation(async () => {
      const texte = new TextDecoder().decode(
        new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x80]), // en-tête ZIP (xlsx)
      )
      JSON.parse(texte) // lève exactement comme le vrai client
      return { data: null, status: 200 }
    })
    apiMock.getBlob.mockResolvedValue({
      blob: new Blob(['PK\x03\x04'], { type: 'application/vnd.ms-excel' }),
      fileName: 'filieres.xlsx',
      contentType: 'application/vnd.ms-excel',
    })
    renderWithProviders(<BarreExport slug="filieres" onMessage={() => {}} />)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Excel/i }))
      await flushPromises(6)
    })
    expect(apiMock.getBlob).toHaveBeenCalled()
    expect(apiMock.get).not.toHaveBeenCalled()
  })

  it('ne crée pas de lien de téléchargement si le serveur renvoie du JSON', async () => {
    // Une erreur d'export renvoie du JSON : mieux vaut ne rien télécharger
    // qu'un fichier corrompu silencieux.
    const creeUrl = vi.fn(() => 'blob:x')
    const originalCreate = window.URL.createObjectURL
    window.URL.createObjectURL = creeUrl
    try {
      apiMock.getBlob.mockResolvedValue({
        blob: new Blob(['{"detail":"Permission refusée."}'], {
          type: 'application/json',
        }),
        fileName: 'erreur.json',
        contentType: 'application/json',
      })
      const messages = []
      renderWithProviders(
        <BarreExport slug="filieres" onMessage={(t, m) => messages.push([t, m])} />,
      )
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /PDF/i }))
        await flushPromises(6)
      })
      expect(creeUrl).not.toHaveBeenCalled()
      expect(messages.at(-1)?.[0]).toBe('erreur')
    } finally {
      window.URL.createObjectURL = originalCreate
    }
  })

  it('signale l’erreur quand le serveur refuse', async () => {
    const messages = []
    apiMock.getBlob.mockRejectedValue({
      response: { status: 403, data: { detail: 'Permission refusée.' } },
    })
    renderWithProviders(
      <BarreExport slug="filieres" onMessage={(type, texte) => messages.push([type, texte])} />,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /PDF/i }))
      await flushPromises(6)
    })
    expect(messages.at(-1)?.[0]).toBe('erreur')
    expect(messages.at(-1)?.[1]).toMatch(/Permission refusée/)
  })
})

const ANALYSE_OK = {
  etape: 'validation',
  slug: 'filieres',
  referentiel: 'Filières',
  previsualisation: {
    total_lignes: 2,
    entetes_fichier: ['Code', 'Libellé', 'Description'],
    colonnes_reconnues: [
      { cle: 'code', libelle: 'Code', colonne: 0 },
      { cle: 'libelle', libelle: 'Libellé', colonne: 1 },
    ],
    colonnes_manquantes: [],
    correspondance: { code: 0, libelle: 1, description: 2 },
    doublons: [],
    apercu: [['INFO', 'Informatique', '—']],
  },
  validation: {
    total_lignes: 2,
    lignes_valides: 2,
    lignes_en_erreur: 0,
    erreurs: [],
  },
  modes_disponibles: MODES_IMPORT.map((m) => m.cle),
}

const RAPPORT_OK = {
  slug: 'filieres',
  mode: 'les_deux',
  duree_secondes: 0.42,
  total_traite: 2,
  crees: 2,
  mis_a_jour: 0,
  ignores: 0,
  anomalies: [],
  nb_anomalies: 0,
  resume: '2 création(s), 0 mise(s) à jour, 0 ignorée(s), 0 anomalie(s) en 0.42 s.',
}

describe('Assistant d’import — parcours nominal en 5 étapes', () => {
  beforeEach(() => {
    apiController.reset?.()
    apiMock.get.mockReset?.()
    apiMock.post.mockReset?.()
  })

  it('affiche les cinq étapes et démarre au téléversement', () => {
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    expect(screen.getByText('Téléversement')).toBeTruthy()
    expect(screen.getByText('Prévisualisation')).toBeTruthy()
    expect(screen.getByText('Validation')).toBeTruthy()
    expect(screen.getByText('Importation')).toBeTruthy()
    expect(screen.getByText('Rapport')).toBeTruthy()
  })

  it('refuse un fichier au mauvais format dès la sélection', async () => {
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    const champ = screen.getByTestId('import-fichier')
    await act(async () => {
      fireEvent.change(champ, { target: { files: [fichier('doc.pdf', 512, 'application/pdf')] } })
      await flushPromises(4)
    })
    expect(screen.getByRole('alert').textContent).toMatch(/non pris en charge/i)
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('analyse le fichier puis affiche la validation', async () => {
    mockImport()
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    const champ = screen.getByTestId('import-fichier')
    await act(async () => {
      fireEvent.change(champ, { target: { files: [fichier('f.csv')] } })
      await flushPromises(4)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Analyser le fichier/i }))
      await flushPromises(6)
    })
    const [url] = apiMock.post.mock.calls.at(-1)
    expect(url).toBe('/referentiels/filieres/importer/analyse/')
    // Étape 2 : la prévisualisation annonce les lignes et colonnes reconnues.
    // Le texte est porté par plusieurs éléments : on lit le conteneur.
    expect(document.body.textContent).toMatch(/2\s*ligne\(s\) détectée\(s\)/)
    // Étape 3 : validation après accord sur la correspondance.
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Valider la correspondance/i }))
      await flushPromises(6)
    })
    expect(document.body.textContent).toMatch(/2\s*ligne\(s\) valide\(s\)/)
  })

  it('importe réellement et affiche le rapport final avec la durée', async () => {
    mockImport()
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    await jusquALaValidation()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Continuer/i }))
      await flushPromises(4)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^Importer$/i }))
      await flushPromises(8)
    })
    const appels = apiMock.post.mock.calls.map((c) => c[0])
    expect(appels).toContain('/referentiels/filieres/importer/')
    await waitFor(() => {
      expect(screen.getByText(/2 création\(s\)/)).toBeTruthy()
    })
    expect(screen.getByText('0.42 s')).toBeTruthy()
  })

  it('signale les colonnes obligatoires manquantes et les doublons', async () => {
    const avecProblemes = {
      ...ANALYSE_OK,
      previsualisation: {
        ...ANALYSE_OK.previsualisation,
        colonnes_manquantes: [{ cle: 'libelle', libelle: 'Libellé' }],
        doublons: [{ ligne: 4, valeur: 'INFO', premiere_ligne: 2 }],
      },
    }
    mockImport(avecProblemes)
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    const champ = screen.getByTestId('import-fichier')
    await act(async () => {
      fireEvent.change(champ, { target: { files: [fichier('f.csv')] } })
      await flushPromises(4)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Analyser le fichier/i }))
      await flushPromises(6)
    })
    expect(screen.getAllByRole('alert').length).toBeGreaterThan(0)
    expect(screen.getByText(/colonnes obligatoires non reconnues|Colonnes obligatoires non reconnues/i)).toBeTruthy()
    expect(screen.getByText(/doublon\(s\) détecté/i)).toBeTruthy()
  })

  it('affiche le rapport d’erreurs ligne par ligne', async () => {
    const avecErreurs = {
      ...ANALYSE_OK,
      validation: {
        total_lignes: 3,
        lignes_valides: 1,
        lignes_en_erreur: 2,
        erreurs: [
          { ligne: 3, colonne: 'Code', valeur: '', message: 'Valeur obligatoire manquante.' },
          { ligne: 4, colonne: 'Ordre', valeur: 'abc', message: '« abc » n’est pas un nombre.' },
        ],
      },
    }
    mockImport(avecErreurs)
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    await jusquALaValidation()
    expect(screen.getByText(/Valeur obligatoire manquante/)).toBeTruthy()
    expect(screen.getByText(/n’est pas un nombre/)).toBeTruthy()
  })

  it('permet de télécharger les anomalies après un import partiel', async () => {
    const rapport = {
      ...RAPPORT_OK,
      crees: 1,
      anomalies: [{ ligne: 4, colonne: '', valeur: 'X', message: 'Doublon' }],
      nb_anomalies: 1,
      resume: '1 création(s), 0 mise(s) à jour, 0 ignorée(s), 1 anomalie(s) en 0.1 s.',
    }
    mockImport(ANALYSE_OK, rapport)
    const creeUrl = vi.fn(() => 'blob:x')
    const revoqueUrl = vi.fn()
    const originalCreate = window.URL.createObjectURL
    const originalRevoke = window.URL.revokeObjectURL
    window.URL.createObjectURL = creeUrl
    window.URL.revokeObjectURL = revoqueUrl
    try {
      renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
      await jusquALaValidation()
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Continuer/i }))
        await flushPromises(4)
      })
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /^Importer$/i }))
        await flushPromises(8)
      })
      await act(async () => {
        fireEvent.click(screen.getByRole('button', { name: /Télécharger les anomalies/i }))
        await flushPromises(4)
      })
      expect(creeUrl).toHaveBeenCalled()
    } finally {
      window.URL.createObjectURL = originalCreate
      window.URL.revokeObjectURL = originalRevoke
    }
  })
})

describe('Assistant d’import — colonnes de rattachement (relations)', () => {
  const ANALYSE_AVEC_RELATIONS = {
    ...ANALYSE_OK,
    validation: {
      ...ANALYSE_OK.validation,
      relations: [
        {
          cle: 'ecole',
          libelle: 'Ecole',
          modele_lie: 'referentiels.refecole',
          libelle_lie: 'Référentiel – École',
          cles_metier: ['code', 'libelle'],
          obligatoire: true,
          non_resolues: 2,
        },
        {
          cle: 'mention',
          libelle: 'Mention',
          modele_lie: 'referentiels.refmention',
          libelle_lie: 'Référentiel – Mention',
          cles_metier: ['code', 'libelle'],
          obligatoire: false,
          non_resolues: 0,
        },
      ],
    },
  }

  beforeEach(() => {
    apiController.reset?.()
    apiMock.get.mockReset?.()
    apiMock.post.mockReset?.()
  })

  it('indique à quoi chaque colonne est rattachée et comment la retrouver', async () => {
    mockImport(ANALYSE_AVEC_RELATIONS)
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    await jusquALaValidation()
    // Le modèle rattaché et les clés métier reconnues sont affichés :
    // l'utilisateur n'a pas à deviner qu'il peut écrire « ENSEPS ».
    expect(screen.getByText('Référentiel – École')).toBeTruthy()
    // Les deux colonnes partagent les mêmes clés métier : plusieurs cellules.
    expect(screen.getAllByText('code, libelle').length).toBe(2)
    // Une seule des deux colonnes est obligatoire.
    expect(screen.getAllByText('obligatoire').length).toBe(1)
  })

  it('met en évidence les références non résolues, sans les associer', async () => {
    mockImport(ANALYSE_AVEC_RELATIONS)
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    await jusquALaValidation()
    // Seule la colonne fautive est comptée : « Mention » reste à zéro.
    const cellules = screen
      .getAllByText('2')
      .filter((n) => n.className.includes('ref-import-nonresolu'))
    expect(cellules.length).toBe(1)
  })

  it('n’affiche aucune section de relations quand le référentiel n’en a pas', async () => {
    mockImport()
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    await jusquALaValidation()
    expect(screen.queryByText(/Colonnes de rattachement reconnues/i)).toBeNull()
  })
})

describe('Assistant d’import — rapport final et phases d’anomalies', () => {
  beforeEach(() => {
    apiController.reset?.()
    apiMock.get.mockReset?.()
    apiMock.post.mockReset?.()
  })

  it('distingue les lignes rejetées en validation des anomalies d’écriture', async () => {
    const rapport = {
      ...RAPPORT_OK,
      crees: 2,
      lignes_rejetees: 3,
      anomalies: [
        { ligne: 4, colonne: 'Ecole', valeur: 'X', message: 'Référence inexistante', phase: 'validation' },
        { ligne: 7, colonne: 'Code', valeur: 'Y', message: 'Doublon en base', phase: 'ecriture' },
      ],
      nb_anomalies: 2,
      resume: '2 création(s), 0 mise(s) à jour, 0 ignorée(s), 2 anomalie(s) en 0.3 s.',
    }
    mockImport(ANALYSE_OK, rapport)
    renderWithProviders(<AssistantImport slug="filieres" referentiel="Filières" />)
    await jusquALaValidation()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Continuer/i }))
      await flushPromises(4)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^Importer$/i }))
      await flushPromises(8)
    })
    // Les deux phases sont nommées, sinon l'utilisateur ne sait pas si la
    // ligne a été écartée avant ou pendant l'écriture. Le libellé
    // « Validation » étant aussi celui d'une étape, on se limite au tableau.
    const tableau = document.querySelector('.ref-table-defilement')
    expect(tableau).toBeTruthy()
    expect(within(tableau).getByText('Validation')).toBeTruthy()
    expect(within(tableau).getByText('Écriture')).toBeTruthy()
    expect(screen.getByText(/Référence inexistante/)).toBeTruthy()
    expect(screen.getByText(/Doublon en base/)).toBeTruthy()
    // Les lignes écartées dès la validation sont comptées à part.
    expect(screen.getByText(/ligne\(s\) rejetée\(s\) en validation/)).toBeTruthy()
  })
})
