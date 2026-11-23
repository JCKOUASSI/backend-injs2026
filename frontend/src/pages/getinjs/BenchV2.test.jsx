import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import BenchV2 from './BenchV2'

const post = vi.fn()
vi.mock('../../services/api', () => ({ default: { post: (...args) => post(...args), get: vi.fn() } }))

describe('Prototype v2 fictif', () => {
  beforeEach(() => { post.mockReset(); vi.stubGlobal('confirm', vi.fn(() => false)) })

  it('ne place rien pendant une simulation et impose une confirmation explicite', async () => {
    post.mockResolvedValue({ data: { decision: { statut: 'PLACEE', code: 'PLACEMENT_POSSIBLE',
      jour: '2098-10-05', creneau_id: 2, salle_id: 3, alternatives: [] } } })
    render(<BenchV2 />)
    for (const [label, value] of [
      ['Année BENCHMARK', '1'], ['Groupe fictif', '2'], ['Effectif fictif', '20'],
      ['Formateur fictif', '3'], ['Date ciblée', '2098-10-05'],
      ['Source fictive de test', 'BENCH FICTIF'],
    ]) fireEvent.change(screen.getByLabelText(label), { target: { value } })
    fireEvent.click(screen.getByRole('button', { name: 'Simuler sans écriture' }))
    await waitFor(() => expect(screen.getByText(/PLACEMENT_POSSIBLE/)).toBeTruthy())
    expect(post).toHaveBeenCalledTimes(1)
    expect(post.mock.calls[0][0]).toBe('/edts/v2/bench/simuler-ligne/')
    fireEvent.click(screen.getByRole('button', { name: /Confirmer le placement fictif/ }))
    expect(window.confirm).toHaveBeenCalledOnce()
    expect(post).toHaveBeenCalledTimes(1)
  })
})
