import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Pagination from '@/components/Pagination'

describe('components/Pagination.jsx — tableau générique (pagination)', () => {
  it('ne rend rien quand il n’y a qu’une seule page', () => {
    const { container } = render(<Pagination page={1} totalPages={1} onPageChange={() => {}} />)
    expect(container.firstChild).toBeNull()
  })

  it('rend les boutons et désactive « Précédent » en première page', () => {
    render(<Pagination page={1} totalPages={3} onPageChange={() => {}} />)
    expect(screen.getByRole('button', { name: /page précédente/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /page suivante/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^Page 2$/i })).toBeInTheDocument()
  })

  it('appelle onPageChange borné quand on change de page', async () => {
    const onChange = vi.fn()
    render(<Pagination page={1} totalPages={3} onPageChange={onChange} />)
    await userEvent.click(screen.getByRole('button', { name: /^Page 2$/i }))
    expect(onChange).toHaveBeenCalledWith(2)
    await userEvent.click(screen.getByRole('button', { name: /page suivante/i }))
    expect(onChange).toHaveBeenLastCalledWith(2)
  })

  it('désactive « Suivant » sur la dernière page et borne le numéro courant', async () => {
    const onChange = vi.fn()
    render(<Pagination page={99} totalPages={3} onPageChange={onChange} />)
    expect(screen.getByRole('button', { name: /page suivante/i })).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: /page précédente/i }))
    expect(onChange).toHaveBeenCalledWith(2) // 99 borné à 3 → 3-1
  })

  it('calcule le nombre de pages et l’intervalle depuis totalItems/pageSize', () => {
    render(<Pagination page={1} totalItems={55} pageSize={25} onPageChange={() => {}} />)
    // 55/25 → 3 pages ; intervalle « 1–25 sur 55 »
    expect(screen.getByText(/1–25 sur 55/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Page 3$/i })).toBeInTheDocument()
  })

  it('affiche un ellipsis pour un grand nombre de pages', () => {
    render(<Pagination page={10} totalItems={500} pageSize={10} onPageChange={() => {}} />)
    expect(screen.getAllByText('…').length).toBeGreaterThan(0)
  })
})
