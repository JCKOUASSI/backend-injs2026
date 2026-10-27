/**
 * Tests du composant de disposition globale Layout.
 *
 * Vérifie :
 * - Le fonctionnement du bouton de bascule (.sidebar-toggle) pour masquer/afficher la sidebar
 * - La classe .sidebar-collapsed sur .app-container
 * - Le bouton de masquage direct (.sidebar-hide-toggle) présent dans l'en-tête de la sidebar
 * - Le comportement responsive (tiroir mobile + fond dépoli d'occultation)
 * - La barre de recherche globale
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Layout from './Layout'

const CAPACITES_ADMIN = {
  capacites: {
    web: ['acceder', 'operationnel'],
    scolarite: ['voir'],
    habilitations_admin: ['gerer'],
  },
}

function monterLayout({ user, initialEntries = ['/dashboard'] } = {}) {
  const compte = user || makeUser('ADMIN', { first_name: 'Directeur', last_name: 'INJS' })
  apiController.setMe(compte)
  apiController.setRoute('/auth/capabilities/', CAPACITES_ADMIN)
  apiController.setRoute('/habilitations/mes-acces/', { gouverne: false })
  apiController.setRoute('/parametres/flags/', { flags: { 'flag.curp_ui_admin': true } })

  return render(
    <AllProviders authUser={compte} routePattern="*" initialEntries={initialEntries}>
      <Layout>
        <div data-testid="page-enfant">Contenu de la page test</div>
      </Layout>
    </AllProviders>,
  )
}

describe('Layout — Fonctionnement du masquage de la barre latérale', () => {
  const innerWidthOriginal = window.innerWidth

  beforeEach(() => {
    localStorage.clear()
    window.innerWidth = 1200
  })

  afterEach(() => {
    cleanup()
    apiController.reset()
    window.innerWidth = innerWidthOriginal
  })

  it('affiche le contenu enfant et la barre latérale par défaut sur bureau', async () => {
    monterLayout()
    expect(await screen.findByTestId('page-enfant')).toBeInTheDocument()
    expect(document.getElementById('sidebar')).toBeInTheDocument()
    const conteneur = document.querySelector('.app-container')
    expect(conteneur.classList.contains('sidebar-collapsed')).toBe(false)
  })

  it('le bouton .sidebar-toggle masque la barre latérale en mode bureau', async () => {
    monterLayout()
    await screen.findByTestId('page-enfant')

    const boutonBasculer = screen.getByTestId('sidebar-toggle')
    expect(boutonBasculer).toBeInTheDocument()
    expect(boutonBasculer.getAttribute('title')).toBe('Masquer le menu latéral')

    // Clic pour masquer
    fireEvent.click(boutonBasculer)

    const conteneur = document.querySelector('.app-container')
    expect(conteneur.classList.contains('sidebar-collapsed')).toBe(true)
    expect(boutonBasculer.getAttribute('title')).toBe('Afficher le menu latéral')

    // Clic pour réafficher
    fireEvent.click(boutonBasculer)
    expect(conteneur.classList.contains('sidebar-collapsed')).toBe(false)
    expect(boutonBasculer.getAttribute('title')).toBe('Masquer le menu latéral')
  })

  it('le bouton chevron .sidebar-hide-toggle dans l\'en-tête de la sidebar masque la barre', async () => {
    monterLayout()
    await screen.findByTestId('page-enfant')

    const boutonFermerEnTete = screen.getByTestId('sidebar-hide-toggle')
    expect(boutonFermerEnTete).toBeInTheDocument()

    fireEvent.click(boutonFermerEnTete)

    const conteneur = document.querySelector('.app-container')
    expect(conteneur.classList.contains('sidebar-collapsed')).toBe(true)
  })

  it('en affichage mobile (<= 992px), le bouton ouvre et referme le tiroir avec fond dépoli', async () => {
    window.innerWidth = 600
    fireEvent(window, new Event('resize'))

    monterLayout()
    await screen.findByTestId('page-enfant')

    const sidebar = document.getElementById('sidebar')
    expect(sidebar.classList.contains('show')).toBe(false)
    expect(screen.queryByTestId('sidebar-backdrop')).not.toBeInTheDocument()

    const boutonBasculer = screen.getByTestId('sidebar-toggle')

    // Ouvre la sidebar sur mobile
    fireEvent.click(boutonBasculer)
    expect(sidebar.classList.contains('show')).toBe(true)
    const backdrop = screen.getByTestId('sidebar-backdrop')
    expect(backdrop).toBeInTheDocument()

    // Clic sur le fond dépoli referme la sidebar
    fireEvent.click(backdrop)
    expect(sidebar.classList.contains('show')).toBe(false)
    expect(screen.queryByTestId('sidebar-backdrop')).not.toBeInTheDocument()
  })

  it('la barre de recherche globale soumet correctement une recherche', async () => {
    monterLayout()
    await screen.findByTestId('page-enfant')

    const champRecherche = screen.getByPlaceholderText(/Rechercher un étudiant/i)
    expect(champRecherche).toBeInTheDocument()

    fireEvent.change(champRecherche, { target: { value: 'licence staps' } })
    fireEvent.submit(champRecherche.closest('form'))
  })
})
