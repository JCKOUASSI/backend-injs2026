/**
 * Tests de la barre d'actions unifiée Importer / Exporter.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, render, fireEvent } from '@testing-library/react'
import BarreImportExport from './BarreImportExport'

describe('Barre d’actions Importer / Exporter', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('réunit les deux actions et les quatre formats', () => {
    render(<BarreImportExport slug="filieres" total={12} />)
    expect(screen.getByRole('button', { name: /Importer/i })).toBeTruthy()
    for (const libelle of ['Excel', 'Word', 'CSV', 'PDF']) {
      expect(screen.getByRole('button', { name: new RegExp(libelle, 'i') })).toBeTruthy()
    }
  })

  it('déclenche l’ouverture de l’assistant au clic sur Importer', () => {
    const onImporter = vi.fn()
    render(<BarreImportExport slug="filieres" onImporter={onImporter} />)
    fireEvent.click(screen.getByRole('button', { name: /^Importer$/i }))
    expect(onImporter).toHaveBeenCalledTimes(1)
  })

  it('masque l’import sur un référentiel en lecture seule, en expliquant pourquoi', () => {
    render(<BarreImportExport slug="formations" lectureSeule />)
    expect(screen.queryByRole('button', { name: /^Importer$/i })).toBeNull()
    // La lecture reste permise et l'absence d'import est explicitée.
    expect(screen.getByText(/consultable et exportable/i)).toBeTruthy()
    expect(screen.getByRole('button', { name: /Excel/i })).toBeTruthy()
  })

  it('porte la variante visuelle « import » et non une teinte d’export', () => {
    render(<BarreImportExport slug="filieres" />)
    const bouton = screen.getByRole('button', { name: /^Importer$/i })
    expect(bouton.className).toContain('ref-btn--import')
  })
})
