import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import ArchivesDashboard from '@/pages/archives/ArchivesDashboard'

function mount() {
  const user = makeUser('ARCHIVE', { username: 'archiviste', first_name: 'Awa' })
  apiController.setMe(user)
  return render(<ArchivesDashboard />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/archives" initialEntries={['/archives']}>
        {children}
      </AllProviders>
    ),
  })
}

describe('pages/archives/ArchivesDashboard.jsx — design premium sobre', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche héros, compteurs réels et cartes documents au thème archives', async () => {
    apiController.setRoute('/formations/archives/stats/', {
      modules: 2, participants: 12, formateurs: 2,
    })
    const { container } = mount()

    expect(await screen.findByText('Espace Archives')).toBeInTheDocument()
    expect(screen.getByText(/Bienvenue, Awa/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('Modules archivés')).toBeInTheDocument())
    expect(container.querySelector('.archives-page .archives-hero')).not.toBeNull()
    expect(container.querySelectorAll('.archives-kpi')).toHaveLength(3)
    expect(container.querySelectorAll('.archives-doc-card')).toHaveLength(2)
    // Libellé harmonisé avec le menu (« Listes de notes archivées »).
    expect(screen.getByRole('link', { name: /Listes de notes/ })).toHaveAttribute(
      'href', '/archives/listes-notes')
    expect(screen.getByRole('link', { name: /Cahiers d'appel/ })).toHaveAttribute(
      'href', '/archives/cahiers-appel')
  })

  it('affiche la note explicative quand aucun module n’est archivé', async () => {
    apiController.setRoute('/formations/archives/stats/', {
      modules: 0, participants: 0, formateurs: 0,
    })
    mount()
    expect(await screen.findByText(/Aucun module archivé pour l'instant/)).toBeInTheDocument()
    expect(screen.getByText(/bouton orange « Archiver »/)).toBeInTheDocument()
  })
})
