import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import DashboardEngineView, { messageErreurDashboard } from '@/pages/DashboardEngineView'

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

  it('affiche le code serveur sans fuite de détail interne et permet de réessayer', async () => {
    let appels = 0
    apiController.setRoute('/dashboard/overview/', () => {
      appels += 1
      if (appels === 1) {
        const err = new Error('Server Error')
        err.response = { status: 500, data: { detail: 'trace SQL sensible' } }
        throw err
      }
      return { annee_academique: '2026-2027', kpis: {} }
    })
    const user = makeUser('ADMIN')
    renderWithProviders(<DashboardEngineView />, { authUser: user })
    expect(await screen.findByText(/HTTP 500/)).toBeInTheDocument()
    expect(screen.queryByText(/trace SQL sensible/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Réessayer/ }))
    expect(await screen.findByText('Étudiants Inscrits')).toBeInTheDocument()
    expect(appels).toBe(2)
  })

  it('distingue expiration de session, refus et route absente sans divulguer le serveur', () => {
    expect(messageErreurDashboard({ response: { status: 401 } })).toMatch(/Reconnectez-vous/)
    expect(messageErreurDashboard({ response: { status: 403 } })).toMatch(/HTTP 403/)
    expect(messageErreurDashboard({ response: { status: 404 } })).toMatch(/HTTP 404/)
    expect(messageErreurDashboard({ response: { status: 503, data: { detail: 'secret' } } }))
      .not.toContain('secret')
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
