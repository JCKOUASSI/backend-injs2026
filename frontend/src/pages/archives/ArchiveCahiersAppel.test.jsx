import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import ArchiveCahiersAppel from '@/pages/archives/ArchiveCahiersAppel'

const MODULES = {
  results: [
    {
      id: 1, module_id: 11,
      module: 'Sciences de la Vie et de la Santé — S1 (archivé)',
      formation: '[Démo archives] Éducation et Motricité — Licence (2025-2026)',
      statut: 'TERMINEE',
      secretariat_nom: 'Secrétariat Pédagogique ENSEPS',
      nb_participants: 2,
      date_debut: '2025-09-15', date_fin: '2026-01-30',
      grade: '', groupe: '', vague: '',
    },
  ],
  count: 1, total_pages: 1, current_page: 1,
}

const CAHIER = {
  sessions: [
    { id: 101, numero: 1, intitule: 'Séance 1 (archivée)', date: '2025-09-22' },
    { id: 102, numero: 2, intitule: 'Séance 2 (archivée)', date: '2025-09-29' },
  ],
  participants: [
    { id: 201, nom: 'Koné', prenom: 'Aya Marie', matricule: 'DEMO-ARCH-2025-002' },
    { id: 202, nom: 'Touré', prenom: 'Ibrahim', matricule: 'DEMO-ARCH-2025-003' },
  ],
  presences: [
    { type_personne: 'participant', participant_id: 201, session_id: 101 },
    { type_personne: 'participant', participant_id: 201, session_id: 102 },
    { type_personne: 'participant', participant_id: 202, session_id: 101 },
  ],
}

function mount() {
  const user = makeUser('ARCHIVE', { username: 'archiviste' })
  apiController.setMe(user)
  return render(<ArchiveCahiersAppel />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/archives/cahiers-appel" initialEntries={['/archives/cahiers-appel']}>
        {children}
      </AllProviders>
    ),
  })
}

describe('pages/archives/ArchiveCahiersAppel.jsx — cahier premium sobre', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute('/formations/referentiels/', {
      formations_reelles: [], annees: [], types_secretariat: [],
      grades: [], groupes: [], vagues: [],
    })
    apiController.setRoute('/formations/archives/modules/', () => MODULES)
    apiController.setRoute('/formations/1/modules/11/archives/cahier/', () => CAHIER)
  })

  it('ouvre le cahier : héros, indicateurs réels, séances sans mention « (archivée) » répétée', async () => {
    const { container } = mount()
    fireEvent.click(await screen.findByRole('button', { name: /Voir le cahier d'appel/ }))

    expect(await screen.findByRole('heading', { name: "Cahier d'appel" })).toBeInTheDocument()
    expect(container.querySelector('.archives-cahier-hero')).not.toBeNull()
    expect(container.querySelector('.archives-cahier-table')).not.toBeNull()
    // Indicateurs calculés : 3 présences émargées sur 4 attendues → 75 %
    expect(screen.getAllByText('3/4').length).toBeGreaterThan(0)
    expect(screen.getAllByText('75%').length).toBeGreaterThan(0)
    expect(screen.getByText('taux de présence global')).toBeInTheDocument()
    // Pied de tableau : présents par séance
    expect(screen.getByText('Présents par séance')).toBeInTheDocument()
    expect(screen.getAllByText('2/2').length).toBeGreaterThan(0)
    // La mention « (archivée) » ne se répète plus sur chaque colonne de séance
    expect(screen.queryByText('Séance 1 (archivée)')).not.toBeInTheDocument()
    expect(screen.getByText('Séance 1')).toBeInTheDocument()
    // Légende présent / absent
    expect(screen.getByText('Présent')).toBeInTheDocument()
    expect(screen.getByText('Absent')).toBeInTheDocument()
  })

  it('filtre les étudiants par la recherche', async () => {
    mount()
    fireEvent.click(await screen.findByRole('button', { name: /Voir le cahier d'appel/ }))
    expect(await screen.findByText('Koné Aya Marie')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Rechercher un étudiant'), { target: { value: 'Touré' } })
    await waitFor(() => {
      expect(screen.queryByText('Koné Aya Marie')).not.toBeInTheDocument()
    })
    expect(screen.getByText('Touré Ibrahim')).toBeInTheDocument()
    expect(screen.getByText('1 étudiant affiché')).toBeInTheDocument()
  })
})
