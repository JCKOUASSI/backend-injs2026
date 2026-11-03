import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import DashboardEngineView from '@/pages/DashboardEngineView'

/**
 * Le tableau de bord doit rester utilisable pendant le chargement et lorsque
 * l'API échoue.
 *
 * Constat : après suppression des chiffres inventés (`?? 1248`, jauges à 75 %),
 * plus rien ne masquait l'état réel — si l'écran plantait sur `data === null`
 * ou sur une erreur réseau, l'utilisateur voyait une page vide ou un écran
 * d'erreur sans explication.
 */
describe('DashboardEngineView — chargement et panne de l’API', () => {
  const admin = makeUser('ADMIN')

  beforeEach(() => {
    apiController.reset()
    apiController.setMe(admin)
  })

  it('affiche un état de chargement quand la réponse ne vient pas', async () => {
    // La requête ne se résout jamais : on observe l'état `data === null`.
    apiController.setRoute(/^\/dashboard\//, () => new Promise(() => {}))
    const { container } = renderWithProviders(<DashboardEngineView />, {
      authUser: admin,
    })
    // Pas de démontage en erreur : l'écran reste monté et vide de données.
    expect(container.firstChild).not.toBeNull()
    expect(screen.queryByText(/Erreur lors du chargement/i)).not.toBeInTheDocument()
  })

  it('annonce l’échec de l’API au lieu d’afficher des chiffres', async () => {
    apiController.setRoute(/^\/dashboard\//, () => {
      throw new Error('panne réseau')
    })
    renderWithProviders(<DashboardEngineView />, { authUser: admin })
    expect(
      await screen.findByText(/Erreur lors du chargement des indicateurs/i),
    ).toBeInTheDocument()
  })

  it('n’invente aucun effectif quand l’API ne renvoie rien', async () => {
    apiController.setRoute(/^\/dashboard\//, { annee_academique: '2026-2027', kpis: {} })
    renderWithProviders(<DashboardEngineView />, { authUser: admin })
    expect(await screen.findByText('Étudiants Inscrits')).toBeInTheDocument()
    // Les valeurs de la maquette (1 248 / 2 340 / 186) ne doivent jamais revenir.
    expect(screen.queryByText('1 248')).not.toBeInTheDocument()
    expect(screen.queryByText('1248')).not.toBeInTheDocument()
    expect(screen.queryByText('2 340')).not.toBeInTheDocument()
    expect(screen.queryByText('186')).not.toBeInTheDocument()
  })

  it('n’affiche aucune année académique inventée quand l’API n’en fournit pas', async () => {
    apiController.setRoute(/^\/dashboard\//, { annee_academique: null, kpis: {} })
    renderWithProviders(<DashboardEngineView />, { authUser: admin })
    await screen.findByText('Étudiants Inscrits')
    // Le repli codé en dur « 2026 – 2027 » affichait une année qui pouvait
    // ne pas exister dans le référentiel.
    expect(screen.queryByText(/2026\s*[–-]\s*2027/)).not.toBeInTheDocument()
  })

  it('affiche l’année académique réellement renvoyée par l’API', async () => {
    apiController.setRoute(/^\/dashboard\//, { annee_academique: '2024-2025', kpis: {} })
    renderWithProviders(<DashboardEngineView />, { authUser: admin })
    expect(await screen.findByText(/2024-2025/)).toBeInTheDocument()
  })
})
