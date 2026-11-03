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
import ArchiveListesNotes from '@/pages/archives/ArchiveListesNotes'

const MODULES = {
  results: [
    {
      id: 1, module_id: 11,
      module: 'Sciences de la Vie et de la Santé — S1 (archivé)',
      formation: '[Démo archives] Éducation et Motricité — Licence (2025-2026)',
      statut: 'TERMINEE',
      secretariat_nom: 'Secrétariat Pédagogique ENSEPS',
      nb_participants: 12,
      date_debut: '2025-09-15', date_fin: '2026-01-30',
      grade: '', groupe: '', vague: '',
    },
  ],
  count: 1, total_pages: 1, current_page: 1,
}

function mount() {
  const user = makeUser('ARCHIVE', { username: 'archiviste' })
  apiController.setMe(user)
  return render(<ArchiveListesNotes />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/archives/listes-notes" initialEntries={['/archives/listes-notes']}>
        {children}
      </AllProviders>
    ),
  })
}

describe('pages/archives/ArchiveListesNotes.jsx — design apuré', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute('/formations/referentiels/', {
      formations_reelles: [], annees: [], types_secretariat: [],
      grades: [], groupes: [], vagues: [],
    })
    apiController.setRoute('/formations/archives/modules/', () => MODULES)
  })

  it('affiche le titre harmonisé, le héros et les cartes modules au thème archives', async () => {
    const { container } = mount()
    expect(await screen.findByText('Sciences de la Vie et de la Santé — S1 (archivé)')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Listes de notes' })).toBeInTheDocument()
    expect(screen.queryByText(/LISTES DE NOTE/)).not.toBeInTheDocument()
    expect(container.querySelector('.archives-browser-hero')).not.toBeNull()
    expect(container.querySelector('.archives-filtres')).not.toBeNull()
    expect(container.querySelector('.archives-module-card')).not.toBeNull()
    expect(screen.getByText('1 module archivé')).toBeInTheDocument()
    expect(screen.getByText('12 étudiants')).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Voir les notes/ })).toBeInTheDocument()
    })
  })
})
