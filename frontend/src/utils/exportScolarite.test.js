import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { exporterScolarite, scolariteExportRows } from './exportScolarite'

const stats = {
  etudiantsInscrits: 13, professeurs: 3, presentsAujourdhui: 9, tauxPresence: 70,
  niveaux: { L1: 7, L2: 0, L3: 6, M1: 0, M2: 0 },
  fraisPayes: 10, fraisEnAttente: 2,
}

describe('exports scolarité', () => {
  let anchorClick
  beforeEach(() => {
    anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    URL.createObjectURL = vi.fn(() => 'blob:rapport')
    URL.revokeObjectURL = vi.fn()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('exporte des données distinctes pour chaque section', () => {
    expect(scolariteExportRows('Repartition_Niveaux', stats)).toEqual([
      ['L1', 7], ['L2', 0], ['L3', 6], ['M1', 0], ['M2', 0],
    ])
    expect(scolariteExportRows('Finances_Etudiants', stats)).toEqual([
      ['Frais payés', 10], ['Frais en attente', 2],
    ])
  })

  it.each([['Excel', '.csv'], ['Word', '.doc']])('télécharge %s avec le bon suffixe', async (format, suffix) => {
    anchorClick.mockImplementation(function () {
      expect(this.isConnected).toBe(true)
      expect(this.download.endsWith(suffix)).toBe(true)
    })
    await exporterScolarite(format, 'Finances_Etudiants', stats, '2026-2027')
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
    vi.runAllTimers()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:rapport')
  })

  it('génère un vrai fichier PDF sans ouvrir la boîte d’impression', async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {})
    anchorClick.mockImplementation(function () {
      expect(this.download).toBe('INJS_Scolarite_Synthese_Generale.pdf')
    })
    await exporterScolarite('PDF', 'Synthese_Generale', stats, '2026-2027')
    expect(anchorClick).toHaveBeenCalledOnce()
    expect(print).not.toHaveBeenCalled()
  })

  it('rejette un format inconnu au lieu de ne rien faire', async () => {
    await expect(exporterScolarite('inconnu', 'Synthese_Generale', stats, '2026-2027'))
      .rejects.toThrow('Format inconnu')
  })
})
