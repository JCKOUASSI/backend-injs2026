import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import VersionsPublication from './VersionsPublication'

const VERSIONS = [
  {
    id: 12,
    version: 2,
    libelle: 'V2',
    titre: 'L3 STAPS — groupe A',
    statut: 'BROUILLON',
    statut_libelle: 'Brouillon',
    annee_academique: '2026-2027',
    creee_le: '2026-10-01T09:00:00Z',
    creee_par: 'planificateur',
    motif_modification: 'Rééquilibrage du mardi',
    validee_le: null,
    validee_par: '',
    publiee_le: null,
    publiee_par: '',
    nb_seances: 24,
  },
  {
    id: 11,
    version: 1,
    libelle: 'V1',
    titre: 'L3 STAPS — groupe A',
    statut: 'PUBLIE',
    statut_libelle: 'Publié',
    annee_academique: '2026-2027',
    creee_le: '2026-09-20T09:00:00Z',
    creee_par: 'planificateur',
    motif_modification: '',
    validee_le: '2026-09-21T10:00:00Z',
    validee_par: 'directeur',
    publiee_le: '2026-09-22T08:00:00Z',
    publiee_par: 'directeur',
    nb_seances: 24,
  },
]

const AUDIT_OK = {
  emploi_du_temps_id: 12,
  version: 2,
  statut: 'OK',
  statut_edt: 'BROUILLON',
  valide: true,
  violations: [],
  warnings: [],
  couverture: { seances_placees: 24, seances_attendues: 24 },
}

const AUDIT_BLOQUANT = {
  ...AUDIT_OK,
  statut: 'BLOQUANT',
  valide: false,
  violations: [{ code: 'C2', message: 'Deux séances du même groupe se chevauchent.' }],
}

describe('VersionsPublication', () => {
  beforeEach(() => {
    apiController.reset()
  })

  const monter = () => render(
    <AllProviders user={makeUser('DIRECTION')}>
      <VersionsPublication />
    </AllProviders>,
  )

  it('affiche l’historique réel des versions avec leur statut', async () => {
    apiController.setRoute(/\/edts\/lmd\/versions\/$/, { versions: VERSIONS })
    monter()

    await waitFor(() => expect(screen.getByText('V2')).toBeInTheDocument())
    expect(screen.getByText('V1')).toBeInTheDocument()
    expect(screen.getByText('Publié')).toBeInTheDocument()
    expect(screen.getAllByText('24')).toHaveLength(2)
  })

  it('signale l’absence de version sans inventer de ligne', async () => {
    apiController.setRoute(/\/edts\/lmd\/versions\/$/, { versions: [] })
    monter()

    await waitFor(() => expect(screen.getByText(/Aucune version enregistrée/i)).toBeInTheDocument())
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('affiche l’audit de la version sélectionnée et publie après validation', async () => {
    apiController.setRoute(/\/edts\/lmd\/versions\/$/, { versions: VERSIONS })
    apiController.setRoute(/\/edts\/lmd\/12\/audit\/$/, AUDIT_OK)
    apiController.setRoute(/\/edts\/lmd\/12\/validate\/$/, {
      valide: true, statut_edt: 'VALIDE', version: 2, statut: 'OK',
      violations: [], warnings: [], couverture: AUDIT_OK.couverture,
    })

    monter()
    await waitFor(() => expect(screen.getByText('V2')).toBeInTheDocument())

    await userEvent.click(screen.getByText('V2'))
    await waitFor(() => expect(screen.getByText('Conforme')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith('/edts/lmd/12/validate/', {}))
  })

  it('n’annonce pas un succès quand la validation est refusée', async () => {
    apiController.setRoute(/\/edts\/lmd\/versions\/$/, { versions: VERSIONS })
    apiController.setRoute(/\/edts\/lmd\/12\/audit\/$/, AUDIT_BLOQUANT)
    apiController.setRoute(/\/edts\/lmd\/12\/validate\/$/, {
      valide: false, statut_edt: 'EN_VALIDATION', version: 2, statut: 'BLOQUANT',
      violations: AUDIT_BLOQUANT.violations, warnings: [], couverture: AUDIT_OK.couverture,
    })

    monter()
    await waitFor(() => expect(screen.getByText('V2')).toBeInTheDocument())
    await userEvent.click(screen.getByText('V2'))
    await waitFor(() => expect(screen.getByText('Bloquant')).toBeInTheDocument())

    await userEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => expect(screen.getByText(/Validation refusée/i)).toBeInTheDocument())
    expect(screen.getByText(/C2/)).toBeInTheDocument()
  })

  it('interdit de publier une version non validée (bouton désactivé + motif)', async () => {
    apiController.setRoute(/\/edts\/lmd\/versions\/$/, { versions: VERSIONS })
    apiController.setRoute(/\/edts\/lmd\/12\/audit\/$/, AUDIT_OK)

    monter()
    await waitFor(() => expect(screen.getByText('V2')).toBeInTheDocument())
    await userEvent.click(screen.getByText('V2'))

    const publier = await screen.findByRole('button', { name: 'Publier' })
    expect(publier).toBeDisabled()
  })
})
