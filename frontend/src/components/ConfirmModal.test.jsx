import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ConfirmModal from '@/components/ConfirmModal'

/**
 * ConfirmModal est le « formulaire de décision » générique utilisé pour
 * valider/annuler une action sensible (validation d'inscription, suppression).
 */
describe('components/ConfirmModal.jsx — formulaire de décision', () => {
  it('affiche le message, le détail et les libellés par défaut', () => {
    render(<ConfirmModal message="Valider cette inscription ?" detail="Action tracée." onConfirm={() => {}} onCancel={() => {}} />)
    expect(screen.getByText('Valider cette inscription ?')).toBeInTheDocument()
    expect(screen.getByText('Action tracée.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmer' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Annuler' })).toBeInTheDocument()
  })

  it('appelle onConfirm lors de la confirmation', async () => {
    const onConfirm = vi.fn()
    render(<ConfirmModal message="Décision" confirmLabel="Valider l’inscription" onConfirm={onConfirm} onCancel={() => {}} />)
    await userEvent.click(screen.getByRole('button', { name: 'Valider l’inscription' }))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('appelle onCancel par le bouton annuler, la croix ou le clic sur le voile', async () => {
    const onCancel = vi.fn()
    const { rerender } = render(<ConfirmModal message="x" onConfirm={() => {}} onCancel={onCancel} />)
    await userEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    rerender(<ConfirmModal message="x" onConfirm={() => {}} onCancel={onCancel} />)
    await userEvent.click(screen.getByText('×'))
    rerender(<ConfirmModal message="x" onConfirm={() => {}} onCancel={onCancel} />)
    await userEvent.click(document.querySelector('.modal-overlay'))
    expect(onCancel).toHaveBeenCalledTimes(3)
  })

  it('un clic dans la boîte de dialogue ne déclenche pas l’annulation (stopPropagation)', async () => {
    const onCancel = vi.fn()
    render(<ConfirmModal message="x" onConfirm={() => {}} onCancel={onCancel} />)
    await userEvent.click(screen.getByText('Confirmation'))
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('utilise les libellés personnalisés et la variante de succès', () => {
    render(<ConfirmModal message="x" variant="success" confirmLabel="Publier" cancelLabel="Retour" onConfirm={() => {}} onCancel={() => {}} />)
    expect(screen.getByRole('button', { name: 'Publier' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retour' })).toBeInTheDocument()
  })
})
