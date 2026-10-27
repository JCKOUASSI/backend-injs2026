import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import DifferentialPanel from './DifferentialPanel'

const differential = {
  gagnes: ['evaluations.note.saisir', 'evaluations.qcm.creer', 'scolarite.inscription.creer'],
  perdus: ['finance.engagement.valider'],
  conserves: [],
  roles_ajoutes: ['SCOLARITE_CPFAE'],
  roles_retires: ['FINANCE_CPFAE'],
  avertissements: [],
  total_actuel: 10,
  total_cible: 12,
}

describe('DifferentialPanel — règle d\'interface S2', () => {
  it('affiche les droits gagnés en vert et perdus en rouge, par module', () => {
    render(<DifferentialPanel differentiel={differential} acquitte={false} onAcquitte={vi.fn()} />)
    expect(screen.getByTestId('differential-panel')).toBeInTheDocument()
    expect(screen.getByText(/Droits gagnés \(3\)/)).toBeInTheDocument()
    expect(screen.getByText(/Droits perdus \(1\)/)).toBeInTheDocument()
    expect(screen.getByText(/Rôles ajoutés : SCOLARITE_CPFAE/)).toBeInTheDocument()
    expect(screen.getByText(/Rôles retirés : FINANCE_CPFAE/)).toBeInTheDocument()
  })

  it('n\'affiche pas de case d\'acquittement quand rien ne change', () => {
    render(<DifferentialPanel differentiel={{ gagnes: [], perdus: [], avertissements: [] }}
                              acquitte={false} onAcquitte={vi.fn()} />)
    expect(screen.queryByTestId('diff-acquittement')).not.toBeInTheDocument()
    expect(screen.getByText(/droits restent identiques/)).toBeInTheDocument()
  })

  it('retransmet l\'acquittement', () => {
    const onAcquitte = vi.fn()
    render(<DifferentialPanel differentiel={differential} acquitte={false} onAcquitte={onAcquitte} />)
    fireEvent.click(screen.getByTestId('diff-acquittement'))
    expect(onAcquitte).toHaveBeenCalledWith(true)
  })

  it('bloque l\'acquittement et signale le franchissement du seuil administrateurs', () => {
    const bloquant = {
      ...differential,
      avertissements: [{ code: 'SEUIL_ADMINISTRATEURS', message: 'sous deux administrateurs' }],
    }
    render(<DifferentialPanel differentiel={bloquant} acquitte={false} onAcquitte={vi.fn()} />)
    expect(screen.getByTestId('diff-acquittement')).toBeDisabled()
    expect(screen.getByTestId('diff-bloque')).toBeInTheDocument()
  })
})
