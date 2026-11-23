import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MotifModal from './MotifModal'

describe('MotifModal — geste irréversible', () => {
  it('nomme l\'action et ses conséquences', () => {
    render(<MotifModal titre="Suspendre" action="Suspendre le compte curp_x"
                      consequences="L'accès est bloqué."
                      onConfirmer={vi.fn()} onAnnuler={vi.fn()} />)
    expect(screen.getByText('Suspendre le compte curp_x')).toBeInTheDocument()
    expect(screen.getByText("L'accès est bloqué.")).toBeInTheDocument()
  })

  it('garde le bouton désactivé tant que le motif fait moins de 8 caractères', () => {
    render(<MotifModal titre="Suspendre" action="action" onConfirmer={vi.fn()} onAnnuler={vi.fn()} />)
    const bouton = screen.getByTestId('motif-confirmation')
    expect(bouton).toBeDisabled()
    fireEvent.change(screen.getByTestId('motif-input'), { target: { value: 'court' } })
    expect(bouton).toBeDisabled()
    fireEvent.change(screen.getByTestId('motif-input'), { target: { value: 'Absence prolongée non justifiée' } })
    expect(bouton).toBeEnabled()
  })

  it('transmet le motif saisi (rogné) à la confirmation', () => {
    const onConfirmer = vi.fn()
    render(<MotifModal titre="Suspendre" action="action" onConfirmer={onConfirmer} onAnnuler={vi.fn()} />)
    fireEvent.change(screen.getByTestId('motif-input'), { target: { value: '  Motif valide de suspension  ' } })
    fireEvent.click(screen.getByTestId('motif-confirmation'))
    expect(onConfirmer).toHaveBeenCalledWith('Motif valide de suspension')
  })
})
