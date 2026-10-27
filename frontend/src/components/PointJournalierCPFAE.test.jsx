import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import PointJournalierTableauCPFAE, { pjPct } from '@/components/PointJournalierCPFAE'

/* ------------------------------------------------------------------ */
/* Données                                                              */
/* ------------------------------------------------------------------ */

const groupe = (moduleId, label, vals = {}) => ({
  module_id: moduleId, label, salle: '—',
  effectif: 0, presents: 0, absents: 0,
  taux_presence: 0, taux_absence: 0, ...vals,
})

const TB = {
  titre_ligne1: 'INJS MARCORY — POINT JOURNALIER',
  jour: 15, mois_libelle: 'Septembre', annee: 2026,
  organisme: 'INJS — Marcory',
  vague_sidebar: 'SECONDE VAGUE',
  taux_presence_jour: 0.82, taux_absence_jour: 0.18,
  matin: {
    horaire: '08h-12h',
    groupes: [
      groupe(11, 'Groupe 1', {
        salle: 'Salle A1', effectif: 30, presents: 28, absents: 2,
        taux_presence: 0.9333, taux_absence: 0.0667,
      }),
      groupe(12, 'Groupe 2', {
        effectif: 25, presents: 20, absents: 5,
        taux_presence: 0.8, taux_absence: 0.2,
      }),
    ],
    total: {
      effectif: 55, presents: 48, absents: 7,
      taux_presence: 0.8727, taux_absence: 0.1273,
    },
  },
  soir: {
    horaire: '14h-18h',
    groupes: [
      groupe(11, 'Groupe 1', {
        salle: 'Salle A1', effectif: 30, presents: 27, absents: 3,
        taux_presence: 0.9, taux_absence: 0.1,
      }),
    ],
    total: {
      effectif: 30, presents: 27, absents: 3,
      taux_presence: 0.9, taux_absence: 0.1,
    },
  },
}

const allRows = () => within(screen.getByRole('table')).getAllByRole('row')

/**
 * Les 9 lignes d'un créneau : en-tête horaire, espaceur, GROUPES, SALLES
 * puis les 5 lignes de données (effectif, présents, absents, 2 taux).
 */
const blockRows = (label) => {
  const rows = allRows()
  const idx = rows.findIndex((r) => r.textContent.includes(`${label}:`))
  if (idx < 0) return null
  return rows.slice(idx, idx + 9)
}

/* ═══════════════════════════════════════════════════════════════════ */
/* pjPct — formatage des pourcentages                                   */
/* ═══════════════════════════════════════════════════════════════════ */

describe('PointJournalierCPFAE — pjPct', () => {
  it('formate une fraction en pourcentage français à 2 décimales', () => {
    expect(pjPct(0)).toBe('0,00%')
    expect(pjPct(0.5)).toBe('50,00%')
    expect(pjPct(1)).toBe('100,00%')
    expect(pjPct(0.125)).toBe('12,50%')
    expect(pjPct(0.9333)).toBe('93,33%')
  })

  it('accepte une valeur numérique sous forme de chaîne', () => {
    expect(pjPct('0.25')).toBe('25,00%')
  })

  it('retourne « — » pour les valeurs nulles, manquantes ou non numériques', () => {
    expect(pjPct(null)).toBe('—')
    expect(pjPct(undefined)).toBe('—')
    expect(pjPct(NaN)).toBe('—')
    expect(pjPct('abc')).toBe('—')
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* PointJournalierTableauCPFAE — structure générale                    */
/* ═══════════════════════════════════════════════════════════════════ */

describe('PointJournalierTableauCPFAE — en-têtes du modèle Excel', () => {
  it('ne rend rien sans données', () => {
    const { container } = render(<PointJournalierTableauCPFAE tb={null}/>)
    expect(container.firstChild).toBeNull()
  })

  it('rend le titre, la ligne DATE, l’organisme et la barre latérale de vague', () => {
    render(<PointJournalierTableauCPFAE tb={TB}/>)
    const table = screen.getByRole('table')

    expect(within(table).getByText('INJS MARCORY — POINT JOURNALIER')).toBeInTheDocument()
    expect(within(table).getByText('DATE')).toBeInTheDocument()
    expect(within(table).getByText('15')).toBeInTheDocument()
    expect(within(table).getByText('Septembre')).toBeInTheDocument()
    expect(within(table).getByText('2026')).toBeInTheDocument()
    expect(within(table).getByText('INJS — Marcory')).toBeInTheDocument()
    expect(within(table).getByText('SECONDE VAGUE')).toBeInTheDocument()
  })

  it('retombe sur « SECONDE VAGUE » si la sidebar est absente, et accepte une valeur personnalisée', () => {
    const { rerender } = render(<PointJournalierTableauCPFAE tb={{ ...TB, vague_sidebar: undefined }}/>)
    expect(screen.getByText('SECONDE VAGUE')).toBeInTheDocument()

    rerender(<PointJournalierTableauCPFAE tb={{ ...TB, vague_sidebar: '  PREMIÈRE VAGUE  ' }}/>)
    expect(screen.getByText('PREMIÈRE VAGUE')).toBeInTheDocument() // valeur trimée
  })

  it('affiche les taux du jour en pied de tableau', () => {
    render(<PointJournalierTableauCPFAE tb={TB}/>)
    expect(screen.getByText('Taux de présence du jour')).toBeInTheDocument()
    expect(screen.getByText("Taux d'absence du jour")).toBeInTheDocument()
    expect(screen.getByText('82,00%')).toBeInTheDocument()
    expect(screen.getByText('18,00%')).toBeInTheDocument()
  })

  it('affiche « — » pour les taux du jour manquants', () => {
    render(<PointJournalierTableauCPFAE tb={{
      ...TB, taux_presence_jour: null, taux_absence_jour: undefined,
    }}/>)
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(2)
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* Blocs matin / soir                                                   */
/* ═══════════════════════════════════════════════════════════════════ */

describe('PointJournalierTableauCPFAE — créneaux matin et soir', () => {
  it('rend l’en-tête horaire, les groupes, les salles et les 5 lignes de données du matin', () => {
    render(<PointJournalierTableauCPFAE tb={TB}/>)
    const rows = blockRows('MATIN')
    expect(rows).toHaveLength(9)

    expect(rows[0].textContent).toBe('MATIN: 08h-12h')
    // GROUPES : libellé + 2 groupes (la colonne TOTAL est en rowSpan sur
    // la ligne d'espacement).
    expect(rows[2].cells[0]).toHaveTextContent('GROUPES')
    expect(rows[2].cells[1]).toHaveTextContent('Groupe 1')
    expect(rows[2].cells[2]).toHaveTextContent('Groupe 2')
    // SALLES : salle renseignée, « — », puis cellule TOTAL.
    expect(rows[3].cells[0]).toHaveTextContent('SALLES')
    expect(rows[3].cells[1]).toHaveTextContent('Salle A1')
    expect(rows[3].cells[2]).toHaveTextContent('—')

    // Les 5 libellés de lignes, dans l'ordre du modèle.
    expect(rows.slice(4).map((r) => r.cells[0].textContent)).toEqual([
      'ÉFFECTIF', 'PRÉSENTS', 'ABSENTS', 'TAUX DE PRÉSENCE', "TAUX D'ABSENCE",
    ])

    // Effectifs bruts du groupe 1 (colonne 1).
    expect(rows[4].cells[1]).toHaveTextContent('30')
    expect(rows[5].cells[1]).toHaveTextContent('28')
    expect(rows[6].cells[1]).toHaveTextContent('2')
    // Taux formatés du groupe 1.
    expect(rows[7].cells[1]).toHaveTextContent('93,33%')
    expect(rows[8].cells[1]).toHaveTextContent('6,67%')
  })

  it('rend les totaux du créneau dans la dernière colonne', () => {
    render(<PointJournalierTableauCPFAE tb={TB}/>)
    const rows = blockRows('MATIN')
    // HTMLCollection n'expose pas .at() : helper de dernière cellule.
    const lastCell = (row) => row.cells[row.cells.length - 1]

    // La dernière cellule de chaque ligne de données porte le total.
    expect(lastCell(rows[4])).toHaveTextContent('55')
    expect(lastCell(rows[5])).toHaveTextContent('48')
    expect(lastCell(rows[6])).toHaveTextContent('7')
    expect(lastCell(rows[7])).toHaveTextContent('87,27%')
    expect(lastCell(rows[8])).toHaveTextContent('12,73%')
  })

  it('complète par des cellules vides quand un créneau a moins de groupes que le maximum', () => {
    render(<PointJournalierTableauCPFAE tb={TB}/>)
    // Le MAX des groupes matin/soir est 2 (matin) : le soir n'a qu'un seul
    // groupe → une cellule de padding par ligne.
    const rows = blockRows('SOIR')
    expect(rows).toHaveLength(9)
    expect(rows[0].textContent).toBe('SOIR: 14h-18h')

    // GROUPES du soir : 1 groupe rempli + 1 cellule de padding vide.
    expect(rows[2].cells[1]).toHaveTextContent('Groupe 1')
    expect(rows[2].cells[2].textContent).toBe('')
    // La ligne effectif du soir : libellé, valeur, padding, TOTAL.
    expect(rows[4].cells[1]).toHaveTextContent('30')
    expect(rows[4].cells[2].textContent).toBe('')
    expect(rows[4].cells[3]).toHaveTextContent('30')
  })

  it('n’émet aucun bloc (et ne plante pas) pour un créneau absent', () => {
    render(<PointJournalierTableauCPFAE tb={{ ...TB, soir: null }}/>)
    expect(blockRows('MATIN')).not.toBeNull()
    expect(blockRows('SOIR')).toBeNull()
    // Le maximum retombe sur les 2 groupes du matin.
    expect(screen.getByText('MATIN: 08h-12h')).toBeInTheDocument()
  })

  it('fonctionne avec un seul groupe sur chaque créneau (minimum nGroups = 1)', () => {
    render(<PointJournalierTableauCPFAE tb={{
      ...TB,
      matin: { horaire: null, groupes: [], total: {} },
      soir: {
        horaire: '14h-18h',
        groupes: [groupe(11, 'Groupe 1', {
          effectif: 10, presents: 9, absents: 1, taux_presence: 0.9, taux_absence: 0.1,
        })],
        total: { effectif: 10, presents: 9, absents: 1, taux_presence: 0.9, taux_absence: 0.1 },
      },
    }}/>)

    // Horaire manquant → repli '—'.
    expect(screen.getByText('MATIN: —')).toBeInTheDocument()
    const rows = blockRows('SOIR')
    expect(rows[4].cells[1]).toHaveTextContent('10')
  })

  it('affiche 0 et « — » pour les valeurs de cellules manquantes', () => {
    render(<PointJournalierTableauCPFAE tb={{
      ...TB,
      matin: {
        horaire: '08h-12h',
        groupes: [{ module_id: 11, label: 'Groupe 1', salle: '' }],
        total: {},
      },
      soir: null,
    }}/>)
    const rows = blockRows('MATIN')
    // Grandeur brute manquante → 0 ; taux manquants → '—'.
    expect(rows[4].cells[1]).toHaveTextContent('0')
    expect(rows[5].cells[1]).toHaveTextContent('0')
    expect(rows[7].cells[1]).toHaveTextContent('—')
    expect(rows[8].cells[1]).toHaveTextContent('—')
    // Salle chaîne vide → '—'.
    expect(rows[3].cells[1]).toHaveTextContent('—')
  })
})
