/**
 * Routes génériques dérivées de l'arborescence du menu.
 *
 * L'enjeu : une **seule source de vérité**. Ajouter une entrée déclarant un
 * `ecran` dans `menu/arborescence.js` doit suffire à exposer la route (avec son
 * fil d'Ariane et sa garde d'authentification) ; retirer l'entrée doit suffire
 * à la fermer. Ces tests vérifient cette correspondance, puis font tourner une
 * route réelle de bout en bout (coquille + écran + garde).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup, act } from '@testing-library/react'
import { MemoryRouter, Routes } from 'react-router-dom'
import { QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '@/context/AuthContext'
import CapabilitiesSync from '@/components/auth/CapabilitiesSync'
import { ToastProvider } from '@/context/ToastContext'
import { createTestQueryClient } from '@/test/utils/renderWithProviders'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { makeUser } from '@/test/utils/factories'
import routesGeneriques from './routesGeneriques'
import { ARBORESCENCE, PIED_DE_BARRE, aplatir } from './arborescence'

const routes = routesGeneriques()

describe('dérivation depuis l\'arborescence', () => {
  const entreesGeneriques = aplatir(ARBORESCENCE, PIED_DE_BARRE).filter((e) => e.ecran)
  const cheminsAttendus = [...new Set(entreesGeneriques.map((e) => e.chemin))]

  it('produit une route par entrée déclarant un écran', () => {
    expect(routes.length).toBe(cheminsAttendus.length)
  })

  it('chaque route reprend exactement le chemin du menu', () => {
    const chemins = routes.map((route) => route.props.path)
    expect(chemins.sort()).toEqual([...cheminsAttendus].sort())
  })

  it('aucune route en double (une seule cible par chemin)', () => {
    const chemins = routes.map((route) => route.props.path)
    expect(new Set(chemins).size).toBe(chemins.length)
  })

  it('une entrée sans écran ne crée pas de route (pages dédiées existantes)', () => {
    const sansEcran = aplatir(ARBORESCENCE, PIED_DE_BARRE)
      .filter((e) => !e.ecran && e.chemin)
      .map((e) => e.chemin)
    const chemins = new Set(routes.map((route) => route.props.path))
    // Les chemins de pages dédiées ne sont pas doublonnés par une route générique,
    // sauf quand une autre entrée du menu pointe le même écran générique.
    const generiques = new Set(entreesGeneriques.map((e) => e.chemin))
    for (const chemin of sansEcran) {
      if (chemins.has(chemin)) expect(generiques.has(chemin), chemin).toBe(true)
    }
  })
})

describe('rendu de bout en bout', () => {
  beforeEach(() => {
    const user = makeUser('ADMIN')
    apiController.setMe(user)
    apiController.setRoute('/auth/capabilities/', {
      capacites: { web: ['acceder', 'operationnel'], habilitations_admin: ['gerer'] },
    })
    apiController.setRoute('/habilitations/mes-acces/', { gouverne: false })
    apiController.setRoute('/audit-logs/', {
      count: 1,
      results: [{
        id: 3, timestamp: '2026-09-14T09:00:00Z', action_label: 'Connexion',
        acteur_label: 'dfrc', acteur_role: 'DIRECTION', cible_nom: 'Session',
        cible_numero: null, ip_address: '10.0.0.7',
      }],
    })
  })

  afterEach(() => {
    cleanup()
    apiController.reset()
  })

  /**
   * Coquille de test : les routes génériques sont montées au **niveau racine**
   * du routeur (comme dans `App.jsx`), contrairement à `AllProviders` qui les
   * imbriquerait sous une route `*`.
   */
  function naviguer(chemin, { authUser } = {}) {
    if (authUser) window.localStorage.setItem('access_token', 'test-access-token')
    else window.localStorage.removeItem('access_token')
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <MemoryRouter initialEntries={[chemin]}>
          <AuthProvider>
            <CapabilitiesSync />
            <ToastProvider>
              <Routes>{routes}</Routes>
            </ToastProvider>
          </AuthProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  it('une route générique rend la coquille et l\'écran correspondant', async () => {
    naviguer('/audit/journal', { authUser: true })
    expect(await screen.findByTestId('ecran-audit_journal')).toBeTruthy()
    // Le titre apparaît dans la page, la barre latérale et le fil d'Ariane.
    expect(screen.getAllByText("Journal d'audit").length).toBeGreaterThan(0)
    expect(await screen.findByText('dfrc')).toBeTruthy()
  })

  it('la coquille affiche la barre latérale et le fil d\'Ariane', async () => {
    naviguer('/audit/journal', { authUser: true })
    await screen.findByTestId('ecran-audit_journal')
    expect(document.getElementById('sidebar')).toBeTruthy()
    expect(screen.getByTestId('sidebar-identite')).toBeTruthy()
    await waitFor(() => {
      const fil = document.querySelector('.breadcrumb')
      expect(fil.textContent).toContain('Audit & Traçabilité')
      expect(fil.textContent).toContain("Journal d'audit")
    })
  })

  it('un visiteur non authentifié ne voit ni coquille ni données', async () => {
    naviguer('/audit/journal')
    // Laisse AuthProvider constater l'absence de jeton et ProtectedRoute rediriger.
    await act(async () => { await new Promise((resoudre) => setTimeout(resoudre, 30)) })
    expect(document.getElementById('sidebar')).toBeNull()
    expect(screen.queryByTestId('ecran-audit_journal')).toBeNull()
    expect(apiController.findCall('get', '/audit-logs/')).toBeFalsy()
  })
})
