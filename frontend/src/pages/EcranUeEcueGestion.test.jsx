/**
 * Écran UE / ECUE — panneau d'actions, exports et import.
 *
 * Complète la couverture du CRUD par ce que la refonte ajoute : une sélection
 * unique réutilisée par le panneau (Créer / Visualiser / Modifier / Supprimer),
 * des exports Word/PDF/Excel/CSV limités à la sélection, un import Excel/CSV
 * borné à la maquette (aperçu obligatoire) et un bilan détaillé de suppression.
 */
import {
  describe, it, expect, beforeEach, afterEach, vi,
} from 'vitest'
import {
  render, screen, fireEvent, cleanup, within, waitFor,
} from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import EcranUeEcue from './EcranUeEcue'

const MAQUETTE_BROUILLON = {
  id: 1, code: 'EM-2026', libelle: 'Éducation et motricité — L1',
  statut: 'BROUILLON', niveau_id: 1, annee_libelle: '2026-2027',
}

const MAQUETTE_VALIDEE = {
  id: 2, code: 'EM-2025', libelle: 'Éducation et motricité — L1 (validée)',
  statut: 'VALIDEE', niveau_id: 1, annee_libelle: '2025-2026',
}

const ue = (id, code, intitule, statut = 'BROUILLON') => ({
  id,
  code,
  intitule,
  credits: 6,
  ordre: 1,
  statut,
  caractere: 'OBLIGATOIRE',
  semestre: { id: 1, libelle: 'S1' },
  ecues: [],
})

const ADMIN = { id: 1, username: 'admin', role: 'ADMIN' }

function monter({ maquettes = [MAQUETTE_BROUILLON], ues = [ue(10, 'UE10', 'Sciences')] } = {}) {
  apiController.setMe({ ...ADMIN, is_active: true })
  apiController.setRoute('/scolarite/maquettes/', maquettes)
  apiController.setRoute('/scolarite/familles/', [])
  apiController.setRoute('/scolarite/ref/semestres/', [{ id: 1, libelle: 'S1' }])
  apiController.setRoute(/^\/scolarite\/maquettes\/\d+\/ues\/$/, () => ues)
  return render(<EcranUeEcue />, {
    wrapper: ({ children }) => <AllProviders authUser={ADMIN}>{children}</AllProviders>,
  })
}

const attendreEcran = () => screen.findByTestId('ligne-ue-10')
const compteur = () => screen.getByTestId('gestion-compteur-selection')
const panneau = () => screen.getByRole('complementary', { name: /Actions sur les unités/ })

beforeEach(() => { window.localStorage.clear() })

afterEach(() => {
  cleanup()
  apiController.reset()
})

describe('panneau d’actions UE', () => {
  it('affiche les quatre actions, seules les actions unitaires sont désactivées', async () => {
    monter()
    await attendreEcran()

    expect(compteur().textContent).toMatch(/Aucune UE sélectionnée/)
    expect(within(panneau()).getByRole('button', { name: 'Créer' })).toBeEnabled()
    expect(within(panneau()).getByRole('button', { name: 'Visualiser' })).toBeDisabled()
    expect(within(panneau()).getByRole('button', { name: 'Modifier' })).toBeDisabled()
    expect(within(panneau()).getByRole('button', { name: 'Supprimer' })).toBeDisabled()
  })

  it('sélectionner une UE active Visualiser / Modifier et met à jour le compteur', async () => {
    monter({ ues: [ue(10, 'UE10', 'Sciences'), ue(11, 'UE11', 'Physiologie')] })
    await attendreEcran()

    fireEvent.click(screen.getByLabelText('Sélectionner l’UE UE10'))
    expect(compteur().textContent).toMatch(/1 UE sélectionnée/)
    expect(within(panneau()).getByRole('button', { name: 'Visualiser' })).toBeEnabled()
    expect(within(panneau()).getByRole('button', { name: 'Modifier' })).toBeEnabled()

    fireEvent.click(screen.getByLabelText('Sélectionner l’UE UE11'))
    expect(compteur().textContent).toMatch(/2 UE sélectionnées/)
    expect(within(panneau()).getByRole('button', { name: 'Modifier' })).toBeDisabled()
    expect(within(panneau()).getByRole('button', { name: 'Supprimer' })).toBeEnabled()
  })

  it('« Créer » ouvre le formulaire de création d’UE', async () => {
    monter()
    await attendreEcran()

    fireEvent.click(within(panneau()).getByRole('button', { name: 'Créer' }))
    const dialogue = await screen.findByRole('dialog')
    expect(within(dialogue).getByText('Créer une unité d’enseignement')).toBeTruthy()
  })

  it('n’affiche aucune action d’écriture sur une maquette gelée', async () => {
    monter({ maquettes: [MAQUETTE_VALIDEE] })
    await screen.findByTestId('maquette-verrouillee')
    expect(screen.queryByTestId('gestion-compteur-selection')).toBeNull()
    expect(screen.queryByRole('button', { name: 'Importer un fichier CSV' })).toBeNull()
  })
})

describe('exports UE / ECUE', () => {
  it('exporte toute la maquette quand rien n’est sélectionné', async () => {
    monter()
    await attendreEcran()

    fireEvent.click(screen.getByRole('button', { name: 'Export PDF' }))
    await waitFor(() => {
      expect(apiMock.getBlob).toHaveBeenCalledWith('/scolarite/maquettes/1/ues/exporter/pdf/')
    })
  })

  it('exporte uniquement les UE sélectionnées', async () => {
    monter({ ues: [ue(10, 'UE10', 'Sciences'), ue(11, 'UE11', 'Physiologie')] })
    await attendreEcran()

    fireEvent.click(screen.getByLabelText('Sélectionner l’UE UE11'))
    fireEvent.click(screen.getByRole('button', { name: 'Export Word' }))
    await waitFor(() => {
      expect(apiMock.getBlob).toHaveBeenCalledWith(
        '/scolarite/maquettes/1/ues/exporter/docx/?ids=11',
      )
    })
  })
})

describe('import UE / ECUE', () => {
  const choisirFichier = () => {
    const fichier = new File(['UE_CODE;UE_INTITULE\n'], 'ue.csv', { type: 'text/csv' })
    fireEvent.change(screen.getByTestId('gestion-fichier-import'), {
      target: { files: [fichier] },
    })
  }

  it('affiche l’aperçu puis applique après confirmation', async () => {
    apiController.setRoute('/scolarite/maquettes/1/ues/importer/', {
      fichier: 'ue.csv',
      importable: true,
      resume: { lignes: 2, ues_creees: 1, ues_mises_a_jour: 0, ecues_creees: 2, ecues_mises_a_jour: 0, rejets: 0, avertissements: 0 },
      erreurs: [], avertissements: [], lignes: [], objets: [],
    })
    monter()
    await attendreEcran()

    choisirFichier()
    const apercu = await screen.findByRole('dialog')
    expect(within(apercu).getByText(/Aperçu de l’import/)).toBeTruthy()
    expect(within(apercu).getByText('UE créée(s)')).toBeTruthy()
    expect(apiMock.post.mock.calls.at(-1)[1].get('mode')).toBe('apercu')

    apiController.setRoute('/scolarite/maquettes/1/ues/importer/', {
      importable: true,
      message: '1 UE créée(s).',
      resume: { lignes: 2, ues_creees: 1, ues_mises_a_jour: 0, ecues_creees: 2, ecues_mises_a_jour: 0, rejets: 0, avertissements: 0 },
      erreurs: [], avertissements: [], lignes: [], objets: [],
    })
    fireEvent.click(within(apercu).getByRole('button', { name: 'Confirmer l’import' }))
    const rapport = await screen.findByText('Import terminé')
    expect(rapport).toBeTruthy()
    expect(apiMock.post.mock.calls.at(-1)[1].get('mode')).toBe('importer')
  })

  it('refuse la confirmation d’un aperçu en erreur', async () => {
    apiController.setRoute('/scolarite/maquettes/1/ues/importer/', {
      fichier: 'ue.csv',
      importable: false,
      resume: { lignes: 1, ues_creees: 0, ues_mises_a_jour: 0, ecues_creees: 0, ecues_mises_a_jour: 0, rejets: 1, avertissements: 0 },
      erreurs: [{ ligne: 1, message: 'UE_CREDITS : nombre entier attendu.' }],
      avertissements: [], lignes: [], objets: [],
    })
    monter()
    await attendreEcran()

    choisirFichier()
    const apercu = await screen.findByRole('dialog')
    expect(within(apercu).getByText(/UE_CREDITS/)).toBeTruthy()
    expect(within(apercu).getByRole('button', { name: 'Confirmer l’import' })).toBeDisabled()
  })
})

describe('suppression en lot UE — bilan', () => {
  it('liste les refus serveur dans le bilan', async () => {
    apiController.setRoute('/scolarite/maquettes/1/ues/', [
      ue(11, 'UE11', 'Sciences'),
      ue(12, 'UE12', 'Physiologie'),
    ])
    apiMock.delete
      .mockResolvedValueOnce({ status: 204, data: null })
      .mockRejectedValueOnce({
        response: { status: 409, data: { error: 'UE référencée par une inscription.' } },
      })
    monter()
    await screen.findByTestId('ligne-ue-11')

    fireEvent.click(screen.getByTestId('tout-cocher-ue'))
    fireEvent.click(within(panneau()).getByRole('button', { name: 'Supprimer' }))
    const confirmation = await screen.findByRole('dialog')
    fireEvent.click(within(confirmation).getByText('Supprimer la sélection'))

    const bilan = await screen.findByRole('dialog')
    expect(within(bilan).getByText('Bilan de la suppression')).toBeTruthy()
    expect(within(bilan).getByText('Non retirée(s)')).toBeTruthy()
    expect(within(bilan).getByText(/UE référencée par une inscription/)).toBeTruthy()
    expect(compteur().textContent).toMatch(/Aucune UE sélectionnée/)
  })
})
