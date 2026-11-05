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

const RELEVE = {
  colonnes: [
    { id: 1, libelle: 'Contrôle continu', note_max: 20 },
    { id: 2, libelle: 'Examen', note_max: 20 },
  ],
  criteres: { seuil_admission: 12, taux_presence_min: 80 },
  rows: [
    {
      participant_id: 201, nom: 'Koné', prenom: 'Aya Marie', matricule: 'DEMO-ARCH-2025-002',
      grade: '', notes: { 1: { note: 15 }, 2: { note: 16 } },
      moyenne: 15.5, mention: 'BIEN', taux_presence: 83.33, admissible: true,
    },
    {
      participant_id: 202, nom: 'Touré', prenom: 'Ibrahim', matricule: 'DEMO-ARCH-2025-003',
      grade: '', notes: { 1: { note: 9 }, 2: { note: 9.5 } },
      moyenne: 9.25, mention: 'PASSABLE', taux_presence: 83.33, admissible: false,
    },
  ],
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
    apiController.setRoute('/formations/1/modules/11/notes/', () => RELEVE)
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

  it('ouvre le relevé : héros, indicateurs réels, mentions et temps de cours effectué', async () => {
    const { container } = mount()
    fireEvent.click(await screen.findByRole('button', { name: /Voir les notes/ }))

    expect(await screen.findByRole('heading', { name: 'Liste de notes' })).toBeInTheDocument()
    expect(container.querySelector('.archives-notes-hero')).not.toBeNull()
    expect(container.querySelector('.archives-notes-table')).not.toBeNull()
    // Indicateurs calculés : moyenne de la classe (15.5 + 9.25) / 2 et 1 admis sur 2
    expect(screen.getByText('12.38/20')).toBeInTheDocument()
    expect(screen.getByText('admis sur 2 évalués')).toBeInTheDocument()
    // Libellé aligné sur la fiche officielle : « Temps de cours effectué »
    expect(screen.getByText('Temps de cours effectué')).toBeInTheDocument()
    expect(screen.queryByText('Présence au module')).not.toBeInTheDocument()
    expect(screen.getAllByText('83.33%').length).toBeGreaterThan(0)
    // Mentions issues des synthèses, badge admis et pied de moyennes
    expect(screen.getByText('Bien')).toBeInTheDocument()
    expect(screen.getByText('Passable')).toBeInTheDocument()
    expect(screen.getByText('Moyenne de la classe')).toBeInTheDocument()
    expect(screen.getByText('1/2 admis')).toBeInTheDocument()
  })
})
