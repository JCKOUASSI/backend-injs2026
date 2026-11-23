import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { useListReturn, useListNavigationState } from './useListReturn'
import { LIST_STORAGE_KEYS } from '@/utils/listFilters'

function Harness({ pathname, storageKey }) {
  const goBack = useListReturn(pathname, storageKey)
  const loc = useLocation()
  const navState = useListNavigationState()
  return (
    <>
      <div data-testid="loc">{loc.pathname}{loc.search}</div>
      <div data-testid="nav-state">{navState.from}</div>
      <button onClick={goBack}>retour</button>
    </>
  )
}

const renderAt = (entry, props) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Harness {...props} />
    </MemoryRouter>,
  )

describe('hooks/useListReturn', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('revient à l’URL mémorisée dans l’état de navigation en priorité', () => {
    renderAt(
      { pathname: '/modules/42', state: { from: '/modules?statut=EN_COURS&page=3' } },
      { pathname: '/modules', storageKey: LIST_STORAGE_KEYS.modules },
    )
    fireEvent.click(screen.getByRole('button', { name: 'retour' }))
    expect(screen.getByTestId('loc')).toHaveTextContent('/modules?statut=EN_COURS&page=3')
  })

  it('utilise la query stockée en sessionStorage s’il n’y a pas d’état', () => {
    window.sessionStorage.setItem(LIST_STORAGE_KEYS.modules, 'search=ani&page=2')
    renderAt({ pathname: '/modules/42' }, { pathname: '/modules', storageKey: LIST_STORAGE_KEYS.modules })
    fireEvent.click(screen.getByRole('button', { name: 'retour' }))
    expect(screen.getByTestId('loc')).toHaveTextContent('/modules?search=ani&page=2')
  })

  it('revient au chemin brut quand rien n’est mémorisé', () => {
    renderAt({ pathname: '/participants/9' }, { pathname: '/participants', storageKey: LIST_STORAGE_KEYS.participants })
    fireEvent.click(screen.getByRole('button', { name: 'retour' }))
    expect(screen.getByTestId('loc')).toHaveTextContent('/participants')
  })

  it('useListNavigationState expose le chemin courant avec sa query', () => {
    renderAt({ pathname: '/users', search: '?tab=auditeurs' }, { pathname: '/users', storageKey: LIST_STORAGE_KEYS.users })
    expect(screen.getByTestId('nav-state')).toHaveTextContent('/users?tab=auditeurs')
  })
})
