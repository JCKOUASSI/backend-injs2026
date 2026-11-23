import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { ToastProvider } from '@/context/ToastContext'
import { apiController } from '@/test/utils/mockApi'
import FormateurFicheModal from './FormateurFicheModal'

const formateur = {
  id: 17,
  nom: 'KOUASSI',
  prenom: 'Aya',
  email: 'aya@example.injs.ci',
  numerobadge: 'F017',
}

function monter(props = {}) {
  return render(
    <ToastProvider>
      <FormateurFicheModal formateur={formateur} onClose={vi.fn()} {...props} />
    </ToastProvider>,
  )
}

beforeEach(() => {
  apiController.reset()
  apiController.setRoute('/formations/formateurs/finance-report/', [{
    ...formateur,
    total_duree_minutes: 120,
    total_duree_realisee_minutes: 90,
    statistiques: { taux_realisation_pct: 75 },
    modules: [],
  }])
})

describe('FormateurFicheModal', () => {
  it('présente les sections comme des onglets accessibles et affiche la section choisie', async () => {
    monter()

    const identityTab = await screen.findByRole('tab', { name: 'Identité' })
    expect(screen.getByRole('tab', { name: 'Statistiques' })).toHaveAttribute('aria-selected', 'true')

    fireEvent.click(identityTab)

    expect(identityTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel', { name: 'Identité' })).toHaveTextContent('aya@example.injs.ci')
    expect(screen.queryByText('Données confidentielles')).not.toBeInTheDocument()
  })

  it('délègue les exports PDF et Excel au gestionnaire fourni', async () => {
    const onExport = vi.fn()
    monter({ onExport })
    await waitFor(() => expect(screen.getByRole('button', { name: 'Exporter en PDF' })).toBeEnabled())

    fireEvent.click(screen.getByRole('button', { name: 'Exporter en PDF' }))
    fireEvent.click(screen.getByRole('button', { name: 'Exporter en Excel' }))

    expect(onExport).toHaveBeenNthCalledWith(1, formateur, 'pdf')
    expect(onExport).toHaveBeenNthCalledWith(2, formateur, 'excel')
  })
})
