/**
 * Référentiels — sélection multiple, panneau d'actions, exports et import.
 *
 * Ces tests vérifient ce que l'écran promet : on sélectionne des lignes
 * (individuellement, page entière), le panneau n'active que les actions
 * possibles (Visualiser/Modifier sur une seule ligne), l'export suit la
 * sélection, l'import n'écrit qu'après confirmation explicite d'un aperçu
 * valide, et la suppression produit un bilan détaillé.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { screen, act, fireEvent, within } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import ReferentielGenerique from '@/pages/referentiels/ReferentielGenerique'

const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }
afterEach(async () => { await settle() })

const ENTREE_NIVEAUX = {
  slug: 'niveaux', libelle: 'Niveaux', description: '', icone: 'bi-bar-chart-steps',
  editable: true, a_un_code: true, route_api: '/referentiels/niveaux/',
  route_ui: '/referentiels/gestion/niveaux',
  provenance_suivie: false, archivage_supporte: false, a_une_description: false,
  champs: ['cycle', 'ordre', 'credits_requis'],
  champs_choix: {
    cycle: [
      { value: 'LICENCE', label: 'Licence' },
      { value: 'MASTER', label: 'Master' },
    ],
  },
  champs_numeriques: ['ordre', 'credits_requis'],
  champs_dates: [], selecteurs: [], selecteurs_routes: {}, avertissement: '', source: '',
}

const catalogue = () => ({
  categories: [{
    cle: 'systeme-lmd', libelle: 'Système LMD', description: '', icone: 'bi-diagram-3',
    entrees: [ENTREE_NIVEAUX],
  }],
  catalogue: [{ cle: 'systeme-lmd', libelle: 'Système LMD' }],
  synthese: {
    nb_referentiels: 1, nb_referentiels_editables: 1, nb_valeurs: 3,
    nb_a_renseigner: 0, nb_sans_source: 0, nb_valeurs_tracees: 0, taux_tracabilite: null,
  },
})

const NIVEAUX = [
  { id: 1, code: 'L1', libelle: 'Licence 1', cycle: 'LICENCE', ordre: 1, credits_requis: 60, actif: true },
  { id: 2, code: 'L2', libelle: 'Licence 2', cycle: 'LICENCE', ordre: 2, credits_requis: 60, actif: true },
  { id: 3, code: 'M1', libelle: 'Master 1', cycle: 'MASTER', ordre: 4, credits_requis: 60, actif: true },
]

function monter() {
  const me = makeUser('ADMIN', { username: 'refadmin' })
  apiController.setMe(me)
  apiController.setRoute('/referentiels/tableau-de-bord/', catalogue)
  apiController.setRoute('/referentiels/niveaux/', NIVEAUX)
  return renderWithProviders(<ReferentielGenerique />, {
    authUser: me,
    routePattern: '/referentiels/gestion/:slug',
    initialEntries: ['/referentiels/gestion/niveaux'],
  })
}

const compteur = () => screen.getByTestId('gestion-compteur-selection')

describe('sélection et panneau d’actions — référentiels', () => {
  it('annonce l’absence de sélection et désactive les actions unitaires', async () => {
    apiController.reset()
    monter()
    await settle()

    expect(compteur().textContent).toMatch(/Aucune valeur sélectionnée/)
    expect(screen.getByRole('button', { name: 'Visualiser' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Modifier' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Supprimer' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Créer' })).toBeEnabled()
  })

  it('coche une ligne, met à jour le compteur et active Visualiser / Modifier', async () => {
    apiController.reset()
    monter()
    await settle()

    fireEvent.click(screen.getByLabelText('Sélectionner Licence 1'))
    await settle()
    expect(compteur().textContent).toMatch(/1 valeur sélectionnée/)
    expect(screen.getByRole('button', { name: 'Visualiser' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Modifier' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Supprimer' })).toBeEnabled()
    expect(document.querySelector('tr.is-selectionnee')).toBeTruthy()

    fireEvent.click(screen.getByLabelText('Sélectionner Licence 2'))
    await settle()
    expect(compteur().textContent).toMatch(/2 valeurs sélectionnées/)
    // Deux lignes cochées : les actions unitaires se désactivent.
    expect(screen.getByRole('button', { name: 'Visualiser' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Modifier' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Supprimer' })).toBeEnabled()
  })

  it('« tout cocher » sélectionne la page, un second clic la vide', async () => {
    apiController.reset()
    monter()
    await settle()

    const tout = screen.getByLabelText('Sélectionner les 3 valeurs de la page')
    fireEvent.click(tout)
    await settle()
    expect(compteur().textContent).toMatch(/3 valeurs sélectionnées/)
    expect(document.querySelectorAll('tr.is-selectionnee')).toHaveLength(3)

    fireEvent.click(tout)
    await settle()
    expect(compteur().textContent).toMatch(/Aucune valeur sélectionnée/)
    expect(document.querySelectorAll('tr.is-selectionnee')).toHaveLength(0)
  })

  it('la sélection survit à un changement de filtre', async () => {
    apiController.reset()
    monter()
    await settle()

    fireEvent.click(screen.getByLabelText('Sélectionner Master 1'))
    fireEvent.change(screen.getByLabelText('Afficher'), { target: { value: 'tous' } })
    await settle()
    expect(compteur().textContent).toMatch(/1 valeur sélectionnée/)
  })

  it('« Créer » ouvre le formulaire de création', async () => {
    apiController.reset()
    monter()
    await settle()

    fireEvent.click(screen.getByRole('button', { name: 'Créer' }))
    await settle()
    const dialogue = screen.getByRole('dialog')
    expect(within(dialogue).getByText('Nouvelle valeur')).toBeTruthy()
  })
})

describe('exports — référentiels', () => {
  it('exporte le périmètre filtré quand rien n’est sélectionné', async () => {
    apiController.reset()
    monter()
    await settle()

    fireEvent.click(screen.getByRole('button', { name: 'Export CSV' }))
    await settle()
    expect(apiMock.getBlob).toHaveBeenCalledWith('/referentiels/niveaux/exporter/csv/?actif=1')
  })

  it('exporte uniquement les lignes sélectionnées', async () => {
    apiController.reset()
    monter()
    await settle()

    fireEvent.click(screen.getByLabelText('Sélectionner Licence 1'))
    fireEvent.click(screen.getByLabelText('Sélectionner Master 1'))
    fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }))
    await settle()
    expect(apiMock.getBlob).toHaveBeenCalledWith(
      '/referentiels/niveaux/exporter/xlsx/?ids=1,3&actif=1',
    )
  })

  it('propose les quatre formats', async () => {
    apiController.reset()
    monter()
    await settle()
    for (const libelle of ['Export Word', 'Export PDF', 'Export Excel', 'Export CSV']) {
      expect(screen.getByRole('button', { name: libelle })).toBeTruthy()
    }
  })
})

describe('import en deux temps — référentiels', () => {
  const choisirFichier = () => {
    const fichier = new File(['CODE;LIBELLE\nL3;Licence 3\n'], 'niveaux.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByTestId('gestion-fichier-import'), {
      target: { files: [fichier] },
    })
  }

  it('affiche l’aperçu et n’écrit qu’après confirmation', async () => {
    apiController.reset()
    apiController.setRoute('/referentiels/niveaux/importer/', {
      fichier: 'niveaux.csv',
      importable: true,
      resume: { lignes: 1, creations: 1, mises_a_jour: 0, rejets: 0, avertissements: 0 },
      erreurs: [], avertissements: [], lignes: [], objets: [],
    })
    monter()
    await settle()

    choisirFichier()
    await settle()
    const apercu = screen.getByRole('dialog')
    expect(within(apercu).getByText(/Aperçu de l’import/)).toBeTruthy()
    expect(within(apercu).getByText('création(s)')).toBeTruthy()
    expect(apiMock.post).toHaveBeenCalledWith(
      '/referentiels/niveaux/importer/',
      expect.any(FormData),
    )
    const donnees = apiMock.post.mock.calls.at(-1)[1]
    expect(donnees.get('mode')).toBe('apercu')

    apiController.setRoute('/referentiels/niveaux/importer/', {
      importable: true,
      message: '1 création(s) et 0 mise(s) à jour appliquée(s).',
      resume: { lignes: 1, creations: 1, mises_a_jour: 0, rejets: 0, avertissements: 0 },
      erreurs: [], avertissements: [], lignes: [], objets: [],
    })
    fireEvent.click(within(apercu).getByRole('button', { name: 'Confirmer l’import' }))
    await settle()

    const dernier = apiMock.post.mock.calls.at(-1)
    expect(dernier[0]).toBe('/referentiels/niveaux/importer/')
    expect(dernier[1].get('mode')).toBe('importer')
    const rapport = screen.getByRole('dialog')
    expect(within(rapport).getByText('Import terminé')).toBeTruthy()
    expect(within(rapport).getByText('création(s)')).toBeTruthy()
  })

  it('bloque la confirmation quand le fichier contient des erreurs', async () => {
    apiController.reset()
    apiController.setRoute('/referentiels/niveaux/importer/', {
      fichier: 'niveaux.csv',
      importable: false,
      resume: { lignes: 2, creations: 1, mises_a_jour: 0, rejets: 1, avertissements: 0 },
      erreurs: [{ ligne: 2, message: 'CYCLE : valeur inconnue.' }],
      avertissements: [], lignes: [], objets: [],
    })
    monter()
    await settle()

    choisirFichier()
    await settle()
    const apercu = screen.getByRole('dialog')
    expect(within(apercu).getByText(/CYCLE : valeur inconnue/)).toBeTruthy()
    expect(within(apercu).getByRole('button', { name: 'Confirmer l’import' })).toBeDisabled()
  })
})

describe('suppression par lot — référentiels', () => {
  it('confirme, appelle la route de lot et affiche le bilan', async () => {
    apiController.reset()
    apiController.setRoute('/referentiels/niveaux/supprimer/', {
      mode: 'désactivation',
      supprimees: [
        { id: 1, libelle: 'Licence 1', mode: 'désactivation' },
        { id: 2, libelle: 'Licence 2', mode: 'désactivation' },
      ],
      bloquees: [{ id: 3, libelle: 'Master 1', motif: 'déjà désactivée : aucune action nécessaire.' }],
      introuvables: [],
      resume: { demandees: 3, supprimees: 2, bloquees: 1, introuvables: 0 },
    })
    monter()
    await settle()

    fireEvent.click(screen.getByLabelText('Sélectionner les 3 valeurs de la page'))
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer' }))
    await settle()

    const confirmation = screen.getByRole('alertdialog')
    expect(within(confirmation).getByText(/3 valeurs/)).toBeTruthy()
    fireEvent.click(within(confirmation).getByRole('button', { name: 'Supprimer' }))
    await settle()

    expect(apiMock.post).toHaveBeenCalledWith(
      '/referentiels/niveaux/supprimer/', { ids: [1, 2, 3] },
    )
    const bilan = screen.getByRole('dialog')
    expect(within(bilan).getByText('Non retirée(s)')).toBeTruthy()
    expect(within(bilan).getByText(/déjà désactivée/)).toBeTruthy()
    expect(compteur().textContent).toMatch(/Aucune valeur sélectionnée/)
  })
})
