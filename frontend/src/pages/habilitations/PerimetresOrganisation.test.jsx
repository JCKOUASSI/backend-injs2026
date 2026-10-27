/**
 * LOT 5 (L4-02) — sélecteur de bornage Direction / Département.
 *
 * Deux niveaux : la fonction de bascule pure (un type remplacé, l'autre
 * conservé) et le composant contrôlé (options rendues, événement, reflet de
 * la valeur). Le chargement autonome (services) est testé via le mock
 * d'API du socle.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import PerimetresOrganisation, { basculerBorne } from './PerimetresOrganisation'

describe('basculerBorne — sémantique par type', () => {
  it('remplace uniquement le type sélectionné', () => {
    const actuels = [{ type: 'DEPARTEMENT', object_id: 11 }]
    const suivant = basculerBorne(actuels, 'DIRECTION', [3, 4])
    expect(suivant).toEqual([
      { type: 'DEPARTEMENT', object_id: 11 },
      { type: 'DIRECTION', object_id: 3 },
      { type: 'DIRECTION', object_id: 4 },
    ])
  })
  it('vide un type sans sélection courante laisse les autres intacts', () => {
    const actuels = [
      { type: 'DIRECTION', object_id: 3 },
      { type: 'DEPARTEMENT', object_id: 11 },
    ]
    expect(basculerBorne(actuels, 'DIRECTION', [])).toEqual([
      { type: 'DEPARTEMENT', object_id: 11 },
    ])
  })
})

describe('PerimetresOrganisation — composant contrôlé', () => {
  beforeEach(() => { cleanup(); apiController.reset() })

  const D = [
    { id: 3, code: 'DG', libelle: 'Direction générale' },
    { id: 4, code: 'DAE', libelle: 'Direction des études' },
  ]
  const DEP = [{ id: 11, code: 'DEPT-A', libelle: 'Département A' }]

  it('rend les deux listes et remonte la sélection', () => {
    const on = vi.fn()
    render(<PerimetresOrganisation directions={D} departements={DEP}
                                    perimetres={[]} onChange={on} />)
    expect(screen.getByTestId('select-directions')).toBeInTheDocument()
    expect(screen.getByTestId('select-departements')).toBeInTheDocument()
    const sel = screen.getByTestId('select-directions')
    Array.from(sel.options).forEach((o) => { o.selected = o.value === '4' })
    fireEvent.change(sel)
    expect(on).toHaveBeenCalledWith([{ type: 'DIRECTION', object_id: 4 }])
  })

  it('reflète les périmètres déjà posés', () => {
    render(<PerimetresOrganisation directions={D} departements={DEP}
                                    perimetres={[{ type: 'DEPARTEMENT', object_id: 11 }]}
                                    onChange={vi.fn()} />)
    const sel = screen.getByTestId('select-departements')
    Array.from(sel.options).forEach((o) => { expect(o.selected).toBe(o.value === '11') })
  })

  it('ne rend rien sans données', () => {
    render(<PerimetresOrganisation directions={[]} departements={[]}
                                    perimetres={[]} onChange={vi.fn()} />)
    expect(screen.queryByTestId('bornage-organisation')).not.toBeInTheDocument()
  })
})

describe('PerimetresOrganisation — chargement autonome (console ouverte)', () => {
  beforeEach(() => { cleanup(); apiController.reset() })

  it('va chercher directions et départements via les endpoints orga', async () => {
    apiController.setRoute('/habilitations/organisation/directions/',
      { results: [{ id: 3, code: 'DG', libelle: 'Direction générale' }] })
    apiController.setRoute('/habilitations/organisation/departements/',
      { results: [{ id: 11, code: 'DEPT-A', libelle: 'Département A' }] })
    render(<PerimetresOrganisation perimetres={[]} onChange={vi.fn()} />)
    await waitFor(() => {
      expect(screen.getByTestId('bornage-organisation')).toBeInTheDocument()
    })
    expect(screen.getByText('Direction générale (DG)')).toBeInTheDocument()
    expect(apiMock.get).toHaveBeenCalledWith('/habilitations/organisation/directions/')
    expect(apiMock.get).toHaveBeenCalledWith('/habilitations/organisation/departements/')
  })
})
