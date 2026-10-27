import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { usePersistedListQuery } from './usePersistedListQuery'

const STORAGE_KEY = 'test_list_query'

function Harness({ build, deps }) {
  const params = usePersistedListQuery(STORAGE_KEY, build, deps)
  const loc = useLocation()
  return (
    <>
      <div data-testid="url">{loc.pathname}{loc.search}</div>
      <div data-testid="params">{params.toString()}</div>
    </>
  )
}

const renderAt = (entry, build, deps) =>
  render(
    <MemoryRouter initialEntries={[entry]}>
      <Harness build={build} deps={deps} />
    </MemoryRouter>,
  )

describe('hooks/usePersistedListQuery', () => {
  beforeEach(() => window.sessionStorage.clear())

  it('pousse les paramètres construits dans l’URL et dans sessionStorage', async () => {
    const build = () => new URLSearchParams('search=dupont&page=2')
    await act(async () => {
      renderAt('/modules', build, ['dupont', 2])
    })
    expect(screen.getByTestId('url')).toHaveTextContent('/modules?search=dupont&page=2')
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBe('search=dupont&page=2')
  })

  it('nettoie l’URL quand les paramètres sont vides', async () => {
    const build = () => new URLSearchParams('')
    await act(async () => {
      renderAt({ pathname: '/modules', search: '?vieux=1' }, build, [])
    })
    expect(screen.getByTestId('url')).toHaveTextContent('/modules')
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBe('')
  })

  it('remet à jour l’URL quand une dépendance change', async () => {
    const build = ({ text }) => new URLSearchParams(text ? `search=${text}` : '')
    let utils
    await act(async () => {
      utils = render(
        <MemoryRouter initialEntries={['/modules']}>
          <Harness build={() => build({ text: 'alpha' })} deps={['alpha']} />
        </MemoryRouter>,
      )
    })
    expect(screen.getByTestId('url')).toHaveTextContent('/modules?search=alpha')

    await act(async () => {
      utils.rerender(
        <MemoryRouter initialEntries={['/modules']}>
          <Harness build={() => build({ text: 'beta' })} deps={['beta']} />
        </MemoryRouter>,
      )
    })
    expect(screen.getByTestId('url')).toHaveTextContent('/modules?search=beta')
    expect(window.sessionStorage.getItem(STORAGE_KEY)).toBe('search=beta')
  })
})
