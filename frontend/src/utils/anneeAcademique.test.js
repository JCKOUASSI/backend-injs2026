import { describe, it, expect } from 'vitest'
import {
  anneeAcademiqueCourante,
  anneeAcademiqueAffichee,
  anneeAcademiquePrecedente,
} from './anneeAcademique'

describe('anneeAcademique', () => {
  it('démarre en septembre', () => {
    expect(anneeAcademiqueCourante(new Date('2026-09-01T00:00:00'))).toBe('2026-2027')
    expect(anneeAcademiqueCourante(new Date('2026-08-31T23:59:59'))).toBe('2025-2026')
  })

  it('reste sur la même année de janvier à août', () => {
    expect(anneeAcademiqueCourante(new Date('2027-01-15T00:00:00'))).toBe('2026-2027')
    expect(anneeAcademiqueCourante(new Date('2027-08-31T00:00:00'))).toBe('2026-2027')
  })

  it('suit l’année civile en cours (pas de valeur figée dans le code)', () => {
    expect(anneeAcademiqueCourante(new Date('2031-10-05T00:00:00'))).toBe('2031-2032')
  })

  it('expose la variante avec tiret demi-cadratin', () => {
    expect(anneeAcademiqueAffichee(new Date('2026-10-27T00:00:00'))).toBe('2026–2027')
  })

  it('calcule l’année précédente (libellés de comparaison des KPI)', () => {
    expect(anneeAcademiquePrecedente(new Date('2026-10-27T00:00:00'))).toBe('2025-2026')
    expect(anneeAcademiquePrecedente(new Date('2026-10-27T00:00:00'), true)).toBe('2025–2026')
    // Changement de siècle de l'année de début : 2030-2031 → 2029-2030.
    expect(anneeAcademiquePrecedente(new Date('2030-09-15T00:00:00'))).toBe('2029-2030')
  })
})
