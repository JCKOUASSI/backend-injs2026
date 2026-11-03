import { describe, it, expect } from 'vitest'
import { anneesAcademiquesFiltre } from './ecrans'

describe('filtre « Année » des écrans génériques', () => {
  it('propose l’année courante puis la précédente', () => {
    expect(anneesAcademiquesFiltre(new Date('2026-10-27T00:00:00'))).toEqual([
      { valeur: '2026-2027', libelle: '2026 – 2027' },
      { valeur: '2025-2026', libelle: '2025 – 2026' },
    ])
  })

  it('suit le calendrier (aucune valeur figée dans le code)', () => {
    expect(anneesAcademiquesFiltre(new Date('2033-02-01T00:00:00'))[0]).toEqual({
      valeur: '2032-2033',
      libelle: '2032 – 2033',
    })
  })
})
