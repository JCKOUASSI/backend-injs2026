import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import {
  AuditeursNotoiresPanel,
  AuditeursNotoiresKpiStrip,
  filterAuditeursNotoires,
} from '@/components/AuditeursNotoiresPanel'

/* ------------------------------------------------------------------ */
/* Données                                                              */
/* ------------------------------------------------------------------ */

const LISTE = [
  {
    id: 1, matricule: 'MC-001', nom: 'KOUASSI', prenom: 'Jean', sexe: 'M',
    categorie: 'A', grade: 'A1', groupe: 'G1', vague: 'V2024',
    secretariat: 'INJS Marcory', secretariat_id: 1,
    libelle_concours: 'Concours 2024', telephone: '0700000000',
    email: 'jean@test.ci', motif: 'Maladie longue durée',
  },
  {
    id: 2, matricule: 'MC-002', nom: 'TRAORE', prenom: 'Awa', sexe: 'F',
    categorie: 'B', grade: 'A2', groupe: 'G2', vague: 'V2023',
    secretariat: 'Antenne Bouaké', secretariat_id: 2,
    libelle_concours: 'Concours 2023', telephone: '—',
    email: 'awa@test.ci', motif: '',
  },
  {
    // Champs optionnels volontairement absents pour exercer les replis '—'.
    id: 3, matricule: 'MC-003', nom: 'DIALLO', prenom: 'Moussa', sexe: 'M',
    categorie: 'A', grade: '—', groupe: '—',
    secretariat: 'INJS Marcory', secretariat_id: 1,
    telephone: '', email: '', motif: null,
  },
]

const DATA = { total: 3, inscrits: 10, pct: 30, liste: LISTE }

/* ═══════════════════════════════════════════════════════════════════ */
/* filterAuditeursNotoires — fonction pure de filtrage                  */
/* ═══════════════════════════════════════════════════════════════════ */

describe('AuditeursNotoiresPanel — filterAuditeursNotoires (filtrage et calculs)', () => {
  it('retourne null si aucune donnée', () => {
    expect(filterAuditeursNotoires(null)).toBeNull()
    expect(filterAuditeursNotoires(undefined)).toBeNull()
  })

  it('sans filtre : conserve toute la liste et calcule total et pct', () => {
    const res = filterAuditeursNotoires(DATA)
    expect(res.liste).toHaveLength(3)
    expect(res.total).toBe(3)
    expect(res.inscrits).toBe(10)
    expect(res.pct).toBe(30) // 3 / 10
    // Les autres propriétés de la réponse sont préservées.
    expect(res).toMatchObject({ total: 3, inscrits: 10, pct: 30 })
  })

  it("arrondit le pourcentage au dixième et gère une liste sans clé `liste`", () => {
    expect(filterAuditeursNotoires({ inscrits: 3, liste: LISTE.slice(0, 1) }).pct).toBe(33.3)
    expect(filterAuditeursNotoires({ inscrits: 10 }).pct).toBe(0)
    expect(filterAuditeursNotoires({ inscrits: 10 }).liste).toEqual([])
  })

  it('retombe sur data.inscrits puis 0 quand aucun inscrit n’est fourni', () => {
    expect(filterAuditeursNotoires({ liste: LISTE }).pct).toBe(0)
    const res = filterAuditeursNotoires({ liste: LISTE.slice(0, 2) }, { inscrits: 20 })
    expect(res.pct).toBe(10) // opts.inscrits prioritaire
  })

  it('filtre par secrétariat avec coercition chaîne (nombre vs chaîne)', () => {
    const res = filterAuditeursNotoires(DATA, { secretariatId: 1 })
    expect(res.liste.map((r) => r.id)).toEqual([1, 3])
    expect(filterAuditeursNotoires(DATA, { secretariatId: '2' }).liste.map((r) => r.id)).toEqual([2])
    expect(filterAuditeursNotoires(DATA, { secretariatId: 99 }).liste).toEqual([])
  })

  it('filtre par grade, y compris le grade de repli « — »', () => {
    expect(filterAuditeursNotoires(DATA, { grade: 'A1' }).liste.map((r) => r.id)).toEqual([1])
    expect(filterAuditeursNotoires(DATA, { grade: '—' }).liste.map((r) => r.id)).toEqual([3])
    expect(filterAuditeursNotoires(DATA, { grade: 'Z9' }).liste).toEqual([])
  })

  it('filtre par groupe, y compris le groupe de repli « — »', () => {
    expect(filterAuditeursNotoires(DATA, { groupe: 'G2' }).liste.map((r) => r.id)).toEqual([2])
    expect(filterAuditeursNotoires(DATA, { groupe: '—' }).liste.map((r) => r.id)).toEqual([3])
  })

  it('cumule les filtres secrétariat + grade', () => {
    const res = filterAuditeursNotoires(DATA, { secretariatId: 1, grade: 'A1' })
    expect(res.liste.map((r) => r.id)).toEqual([1])
    expect(res.total).toBe(1)
    // Le pct reste calculé sur le nombre d'inscrits du périmètre (10), pas
    // sur la liste filtrée.
    expect(res.pct).toBe(10)
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* AuditeursNotoiresKpiStrip — bandeau de synthèse                      */
/* ═══════════════════════════════════════════════════════════════════ */

describe('AuditeursNotoiresKpiStrip — bandeau de synthèse', () => {
  it('ne rend rien sans données', () => {
    const { container } = render(<AuditeursNotoiresKpiStrip data={null}/>)
    expect(container.firstChild).toBeNull()
  })

  it('total 0 : message vert d’absence d’absents notoires', () => {
    render(<AuditeursNotoiresKpiStrip data={{ total: 0, inscrits: 12, pct: 0 }}/>)
    expect(screen.getByText(/Aucun absent notoire/)).toBeInTheDocument()
    expect(screen.getByText(/tous les inscrits ont au moins une présence/)).toBeInTheDocument()
    expect(screen.queryByText(/% des inscrits/)).not.toBeInTheDocument()
  })

  it('total 1 : singulier et pourcentage formaté en français', () => {
    render(<AuditeursNotoiresKpiStrip data={{ total: 1, inscrits: 8, pct: 12.5 }}/>)
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText(/absent notoire/)).toBeInTheDocument()
    expect(screen.queryByText(/absents notoires/)).not.toBeInTheDocument() // pas de pluriel
    expect(screen.getByText('12,5%')).toBeInTheDocument()
    expect(screen.getByText(/des inscrits \(8\)/)).toBeInTheDocument()
    expect(screen.getByText('Module démarré · aucune présence enregistrée')).toBeInTheDocument()
  })

  it('total 2 : pluriel', () => {
    render(<AuditeursNotoiresKpiStrip data={{ total: 2, inscrits: 20, pct: 10 }}/>)
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByText(/absents notoires/)).toBeInTheDocument()
    expect(screen.getByText('10,0%')).toBeInTheDocument()
  })

  it('pct manquant : affiche 0,0 et inscrits par défaut à 0', () => {
    render(<AuditeursNotoiresKpiStrip data={{ total: 1 }}/>)
    expect(screen.getByText('0,0%')).toBeInTheDocument()
    expect(screen.getByText(/\(0\)/)).toBeInTheDocument()
  })
})

/* ═══════════════════════════════════════════════════════════════════ */
/* AuditeursNotoiresPanel — tableau détaillé                            */
/* ═══════════════════════════════════════════════════════════════════ */

describe('AuditeursNotoiresPanel — états et tableau complet', () => {
  it('données absentes : message dédié', () => {
    render(<AuditeursNotoiresPanel data={null}/>)
    expect(screen.getByText('Données non disponibles.')).toBeInTheDocument()
  })

  it('liste vide : message de périmètre vide', () => {
    render(<AuditeursNotoiresPanel data={{ total: 0, inscrits: 10, pct: 0, liste: [] }}/>)
    expect(screen.getByText('Aucun absent notoire sur ce périmètre.')).toBeInTheDocument()
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('rend les 12 colonnes du mode complet avec les valeurs et les replis', () => {
    render(<AuditeursNotoiresPanel data={DATA}/>)

    const table = screen.getByRole('table')
    const headers = within(table).getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual([
      'N°', 'Matricule', 'Nom', 'Prénom', 'Sexe', 'Catégorie',
      'Grade / Groupe', 'Vague', 'Secrétariat', 'Libellé concours',
      'Contacts', 'Motif / Obs.',
    ])

    const rows = within(table.tBodies[0]).getAllByRole('row')
    expect(rows).toHaveLength(3)

    // Numérotation séquentielle.
    expect(rows.map((r) => r.cells[0].textContent)).toEqual(['1', '2', '3'])
    // Grade / groupe combinés, puis replis en '—' (ligne 3 sans grade/groupe).
    expect(rows[0]).toHaveTextContent('A1 / G1')
    const gradeCellRow3 = rows[2].cells[6]
    expect(gradeCellRow3.textContent).toBe('—')
    // Contacts : téléphone + email joints par « · » ; un seul moyen ; aucun.
    expect(rows[0]).toHaveTextContent('0700000000 · jean@test.ci')
    expect(rows[1]).toHaveTextContent('awa@test.ci')
    expect(rows[2].cells[10].textContent).toBe('—')
    // Valeurs manquantes : libellé concours et vague de la 3e ligne → '—'.
    expect(rows[2].cells[9].textContent).toBe('—')
    expect(rows[2].cells[7].textContent).toBe('—')
    // Motif manquant → '—'.
    expect(rows[2].cells[11].textContent).toBe('—')
  })

  it('affiche un motif renseigné en rouge', () => {
    render(<AuditeursNotoiresPanel data={DATA}/>)
    const table = screen.getByRole('table')
    const rows = within(table.tBodies[0]).getAllByRole('row')
    const motifCell = rows[0].cells[11]
    expect(motifCell.textContent).toBe('Maladie longue durée')
    // Couleur d'alerte (#C62828) pour un motif présent.
    expect(motifCell.style.color).toBe('rgb(198, 40, 40)')
    // Pas de couleur d'alerte pour un motif vide ('—').
    expect(rows[1].cells[11].style.color).not.toBe('rgb(198, 40, 40)')
  })

  it('mode compact : 7 colonnes, sans sexe/catégorie/vague/libellé concours', () => {
    render(<AuditeursNotoiresPanel data={DATA} compact/>)
    const headers = within(screen.getByRole('table'))
      .getAllByRole('columnheader').map((h) => h.textContent)
    expect(headers).toEqual([
      'N°', 'Matricule', 'Nom', 'Prénom', 'Grade / Groupe',
      'Secrétariat', 'Motif',
    ])
    expect(headers).not.toContain('Sexe')
    expect(headers).not.toContain('Libellé concours')
  })

  it('applique le maxHeight au conteneur défilant et rend le pied de tableau', () => {
    render(<AuditeursNotoiresPanel data={DATA} maxHeight={280}/>)
    const scrollBox = screen.getByRole('table').parentElement
    expect(scrollBox.style.maxHeight).toBe('280px')
    expect(scrollBox.style.overflowY).toBe('auto')

    // Pied : compte + part des inscrits (pct 30, formaté 30,0).
    expect(screen.getByText((_c, el) =>
      el?.tagName === 'DIV' && /^3 absents notoires · 30,0% des 10 inscrits$/.test(el.textContent))).toBeInTheDocument()
  })

  it('pied de tableau sans la part quand le nombre d’inscrits est absent', () => {
    render(<AuditeursNotoiresPanel data={{ total: 1, pct: 0, liste: LISTE.slice(0, 1) }}/>)
    expect(screen.getByText((_c, el) =>
      el?.tagName === 'DIV' && /^1 absent notoire$/.test(el.textContent.trim()))).toBeInTheDocument()
    expect(screen.queryByText(/inscrits$/)).not.toBeInTheDocument()
  })

  it('garde une clé stable même pour des lignes sans id', () => {
    const sansId = LISTE.map(({ id: _id, ...r }) => r) // clé retirée exprès
    render(<AuditeursNotoiresPanel data={{ total: 3, inscrits: 10, pct: 30, liste: sansId }}/>)
    expect(within(screen.getByRole('table').tBodies[0]).getAllByRole('row')).toHaveLength(3)
  })
})
