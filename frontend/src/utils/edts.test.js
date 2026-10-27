import { describe, expect, it } from 'vitest'
import {
  construireMatriceGrille, formatDuree, formatHeure, libelleJour, libelleStatut,
  messageErreurApi, lireMutationAffectation, classeBadgeStatut,
} from './edts'

describe('utils/edts — formatage', () => {
  it('normalise les heures en HH:MM', () => {
    expect(formatHeure('08:00:00')).toBe('08:00')
    expect(formatHeure('8:30')).toBe('08:30')
    expect(formatHeure(null)).toBe('')
  })

  it('affiche des libellés français, jamais l’enum brut', () => {
    expect(libelleJour('LUNDI')).toBe('Lundi')
    expect(libelleJour('INCONNU')).toBe('INCONNU') // repli sans crash
    expect(libelleStatut('EN_VALIDATION')).toBe('En validation')
    expect(libelleStatut('PUBLIE')).toBe('Publié')
    expect(classeBadgeStatut('PUBLIE')).toContain('text-bg-success')
    expect(classeBadgeStatut('???')).toContain('text-bg-secondary')
  })

  it('formate les durées de créneau', () => {
    expect(formatDuree(90)).toBe('1 h 30')
    expect(formatDuree(120)).toBe('2 h')
    expect(formatDuree(45)).toBe('45 min')
    expect(formatDuree(null)).toBe('')
  })
})

describe('utils/edts — grille hebdomadaire', () => {
  const grille = {
    jours: [
      {
        jour: 'MARDI',
        creneaux: [
          { creneau_template_id: 2, heure_debut: '10:00', heure_fin: '12:00', affectations: [{ id: 11 }] },
          { creneau_template_id: 1, heure_debut: '08:00', heure_fin: '10:00', affectations: [{ id: 10 }] },
        ],
      },
      {
        jour: 'LUNDI',
        creneaux: [
          { creneau_template_id: 1, heure_debut: '08:00', heure_fin: '10:00', affectations: [{ id: 12 }] },
        ],
      },
    ],
  }

  it('trie les jours dans l’ordre de la semaine académique et l’heure croissante', () => {
    const matrice = construireMatriceGrille(grille, [])
    expect(matrice.map((j) => j.jour)).toEqual(['LUNDI', 'MARDI'])
    expect(matrice[1].lignes.map((c) => c.heure_debut)).toEqual(['08:00', '10:00'])
  })

  it('marque les cellules dont une affectation est en conflit actif', () => {
    const conflits = [{ id: 1, lignes_creneaux: [12] }]
    const matrice = construireMatriceGrille(grille, conflits)
    const lundi = matrice.find((j) => j.jour === 'LUNDI')
    expect(lundi.lignes[0].enConflit).toBe(true)
    const mardi = matrice.find((j) => j.jour === 'MARDI')
    expect(mardi.lignes.every((c) => !c.enConflit)).toBe(true)
  })

  it('ignore les jours sans occupation', () => {
    const matrice = construireMatriceGrille({ jours: [] }, [])
    expect(matrice).toEqual([])
  })
})

describe('utils/edts — robustesse des réponses', () => {
  it('extrait un message d’erreur lisible des réponses DRF (detail, dict de champs)', () => {
    expect(messageErreurApi({ response: { data: { detail: 'Non.' } } })).toBe('Non.')
    expect(messageErreurApi({ response: { data: { semaine_fin: ['doit être ≥'] } } }))
      .toContain('semaine_fin')
    expect(messageErreurApi(new Error('réseau'), 'repli')).toBe('réseau')
    expect(messageErreurApi(null, 'repli')).toBe('repli')
  })

  it('lit {affectation, avertissements_conflits} et tolère l’ancien format plat', () => {
    const riche = lireMutationAffectation({ data: { affectation: { id: 3 }, avertissements_conflits: ['x'] } })
    expect(riche.affectation.id).toBe(3)
    expect(riche.avertissements).toEqual(['x'])
    const plat = lireMutationAffectation({ data: { id: 4 } })
    expect(plat.affectation.id).toBe(4)
    expect(plat.avertissements).toEqual([])
  })
})
