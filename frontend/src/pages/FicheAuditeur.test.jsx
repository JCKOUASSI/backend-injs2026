/**
 * Tests de la fiche de suivi d'un auditeur dans une formation (FicheAuditeur,
 * LOT 15 — domaine présence/suivi) : fiche en lecture, suivi par module,
 * décision finale, exports PDF/Excel, cas d'erreur.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import FicheAuditeur from '@/pages/FicheAuditeur'

const PID = 7
const FID = 10
const fichePath = `/suiviEvaluation/auditeurs/${PID}/formations/${FID}/fiche/`

const FICHE = {
  participant_nom: 'Awa Koné',
  formation_libelle: 'L1 LSF 2025-2026',
  moyenne_generale: '14.50',
  classement: 3,
  decision_finale_detail: { decision_display: 'Admis(e) de droit' },
  suivi_modules: [
    {
      id: 1, module_intitule: 'LSF Niveau 1 — A1', nb_epreuves: 3,
      heures_presence: 18, heures_prevues: 20, taux_presence: 90, moyenne_module: '15.00',
    },
    {
      id: 2, module_intitule: 'Culture sourde', nb_epreuves: 1,
      heures_presence: 8, heures_prevues: 10, taux_presence: 80, moyenne_module: '12.00',
    },
  ],
}

let ficheData = FICHE
let ficheFailures = 0
const setupRoutes = () => {
  apiController.setRoute(fichePath, () => {
    if (ficheFailures > 0) {
      ficheFailures -= 1
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { detail: 'Fiche verrouillée.' } } }
    }
    return ficheData
  })
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<FicheAuditeur />, {
    authUser: me,
    routePattern: '/auditeurs/:participantId/formations/:formationId/fiche',
    initialEntries: [`/auditeurs/${PID}/formations/${FID}/fiche`],
  })
}
const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  ficheData = FICHE
  ficheFailures = 0
  setupRoutes()
})

describe('FicheAuditeur — affichage', () => {
  it('affiche la synthèse et le suivi par module', async () => {
    mount()
    expect(await screen.findByText(/Awa Koné/)).toBeInTheDocument()
    expect(screen.getByText('L1 LSF 2025-2026')).toBeInTheDocument()
    expect(screen.getByText('14.50')).toBeInTheDocument()
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('Admis(e) de droit')).toBeInTheDocument()

    // Deux modules suivis.
    expect(screen.getByText('LSF Niveau 1 — A1')).toBeInTheDocument()
    expect(screen.getByText('Culture sourde')).toBeInTheDocument()
    expect(screen.getByText('3 épreuve(s)')).toBeInTheDocument()
    expect(screen.getAllByText('90%').length).toBeGreaterThan(0)
  })

  it("affiche un état vide si l'étudiant n'a aucun module", async () => {
    ficheData = { ...FICHE, suivi_modules: [] }
    mount()
    expect(await screen.findByText('Aucun module')).toBeInTheDocument()
  })

  it('affiche des tirets pour les champs absents', async () => {
    ficheData = {
      participant_nom: 'Karim Diop',
      formation_libelle: 'L1 LSF',
      moyenne_generale: null,
      classement: null,
      decision_finale_detail: null,
      suivi_modules: [],
    }
    mount()
    expect(await screen.findByText(/Karim Diop/)).toBeInTheDocument()
    // Moyenne / classement / décision non rendus → trois tirets.
    expect(screen.getAllByText('—')).toHaveLength(3)
  })

  it("signale l'erreur et affiche « fiche introuvable » quand le chargement échoue", async () => {
    ficheFailures = 1
    mount()
    expect(await screen.findByText('Fiche verrouillée.')).toBeInTheDocument()
    expect(screen.getByText('Fiche introuvable')).toBeInTheDocument()
  })
})

describe('FicheAuditeur — exports', () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:fiche')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
  })

  it('exporte la fiche en PDF', async () => {
    mount()
    await screen.findByText(/Awa Koné/)
    await act(async () => { screen.getByRole('button', { name: 'Export PDF' }).click() })
    await settle()
    expect(apiMock.getBlob.mock.calls[0][0]).toBe(`${fichePath}export/pdf/`)
  })

  it('exporte la fiche en Excel', async () => {
    mount()
    await screen.findByText(/Awa Koné/)
    await act(async () => { screen.getByRole('button', { name: 'Export Excel' }).click() })
    await settle()
    expect(apiMock.getBlob.mock.calls[0][0]).toBe(`${fichePath}export/xlsx/`)
  })

  it("notifie l'erreur si l'export échoue", async () => {
    apiMock.getBlob.mockRejectedValueOnce({ response: { data: { detail: 'Génération impossible' } } })
    mount()
    await screen.findByText(/Awa Koné/)
    await act(async () => { screen.getByRole('button', { name: 'Export PDF' }).click() })
    expect(await screen.findByText('Génération impossible')).toBeInTheDocument()
  })

  it('retombe sur un nom de fichier par défaut sans nom fourni', async () => {
    // Réponse SANS fileName : la page doit construire le nom elle-même.
    apiMock.getBlob.mockResolvedValueOnce({ blob: new Blob(['x']) })
    let clickedName = null
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      clickedName = this.download
    })
    mount()
    await screen.findByText(/Awa Koné/)
    await act(async () => { screen.getByRole('button', { name: 'Export Excel' }).click() })
    await settle()
    expect(clickedName).toBe(`fiche_auditeur_${PID}_${FID}.xlsx`)
  })
})
