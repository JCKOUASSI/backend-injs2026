/**
 * Page hôte des écrans génériques — résolution du descripteur et garde
 * d'autorisation côté interface.
 *
 * Trois comportements vérifiés :
 * 1. un identifiant inconnu n'affiche aucune donnée ;
 * 2. une URL saisie à la main vers une entrée **masquée** pour le compte
 *    affiche un refus explicite avec les droits requis (défense en profondeur,
 *    jamais une décision : le serveur reste seul juge) ;
 * 3. un écran autorisé rend son titre, son fil et appelle son endpoint — y
 *    compris pour les variantes `documents` et `indicateurs`.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import EcranGenerique from './EcranGenerique'

const CAPACITES_ADMIN = {
  capacites: {
    web: ['acceder', 'operationnel'],
    scolarite: ['voir', 'agir'],
    statistiques: ['voir', 'voir_globales'],
    habilitations_admin: ['gerer'],
    exports: ['liste_classe'],
    participants: ['lister', 'gerer'],
  },
}

function monter(id, { chemin, mesAcces = { gouverne: false }, capacites = CAPACITES_ADMIN, role = 'ADMIN' } = {}) {
  const user = makeUser(role)
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', capacites)
  apiController.setRoute('/habilitations/mes-acces/', mesAcces)
  render(<EcranGenerique id={id} />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="*" initialEntries={[chemin || '/']}>
        {children}
      </AllProviders>
    ),
  })
}

beforeEach(() => {
  apiController.setRoute('/audit-logs/', {
    count: 1,
    results: [{
      id: 7,
      timestamp: '2026-09-14T10:00:00Z',
      action_label: 'Création',
      acteur_label: 'admin',
      acteur_role: 'ADMIN',
      cible_nom: 'CompteUtilisateur',
      cible_numero: 'C-42',
      ip_address: '127.0.0.1',
    }],
  })
  apiController.setRoute('/admissions/candidatures/stats/', { total: 128, admis: 96 })
  apiController.setRoute('/exports/participants/liste-classe/pdf/', { count: 0, results: [] })
})

afterEach(() => {
  cleanup()
  apiController.reset()
})

describe('résolution du descripteur', () => {
  it('un identifiant inconnu affiche un avertissement, aucune donnée', async () => {
    monter('ecran_inexistant', { chemin: '/audit/journal' })
    expect(await screen.findByText(/Écran inconnu/i)).toBeTruthy()
    expect(screen.queryByTestId('ecran-ecran_inexistant')).toBeNull()
  })
})

describe('garde d\'autorisation côté interface', () => {
  it('entrée masquée : URL directe → refus explicite et droits requis', async () => {
    // Compte gouverné sans la permission du journal d'audit : le menu masque
    // l'entrée, et l'URL saisie à la main ne doit rien afficher non plus.
    monter('audit_journal', {
      chemin: '/audit/journal',
      mesAcces: { gouverne: true, permissions_effectives: ['candidatures.candidature.consulter'] },
    })
    expect(await screen.findByText(/Accès non autorisé/i)).toBeTruthy()
    expect(screen.getByText('administration.journal.consulter')).toBeTruthy()
    expect(screen.queryByTestId('ecran-audit_journal')).toBeNull()
    expect(apiController.findCall('get', '/audit-logs/')).toBeFalsy()
  })

  it('le refus indique la source de la décision (CURP ou capacités)', async () => {
    monter('audit_journal', {
      chemin: '/audit/journal',
      mesAcces: { gouverne: true, permissions_effectives: [] },
    })
    expect(await screen.findByText(/Accès non autorisé/i)).toBeTruthy()
    // La source CURP n'apparaît qu'après résolution de GET /habilitations/mes-acces/.
    expect(await screen.findByText(/permissions effectives CURP/i)).toBeTruthy()
  })

  it('entrée autorisée : l\'écran s\'affiche', async () => {
    monter('audit_journal', { chemin: '/audit/journal' })
    expect(await screen.findByTestId('ecran-audit_journal')).toBeTruthy()
    expect(screen.queryByText(/Accès non autorisé/i)).toBeNull()
  })
})

describe('rendu des variantes de descripteur', () => {
  it('liste : titre, fil et appel de l\'endpoint', async () => {
    monter('audit_journal', { chemin: '/audit/journal' })
    expect(await screen.findByText("Journal d'audit")).toBeTruthy()
    expect(screen.getByText('Audit & Traçabilité')).toBeTruthy()
    expect(await screen.findByText('admin')).toBeTruthy()
    await waitFor(() => {
      expect(apiController.findCall('get', '/audit-logs/')).toBeTruthy()
    })
  })

  it('indicateurs : cartes de chiffres, aucun tableau', async () => {
    monter('stats_candidatures', { chemin: '/statistiques/candidatures' })
    expect(await screen.findByText('128')).toBeTruthy()
    expect(document.querySelector('table')).toBeNull()
    await waitFor(() => {
      expect(apiController.findCall('get', '/admissions/candidatures/stats/')).toBeTruthy()
    })
  })

  it('documents : cartes de génération avec leurs formats', async () => {
    monter('documents_scolaires', { chemin: '/scolarite/documents-scolaires' })
    expect(await screen.findByTestId('ecran-documents_scolaires')).toBeTruthy()
    expect(screen.getByText('Liste de classe')).toBeTruthy()
    expect(screen.getByTestId('doc-liste_classe-pdf')).toBeTruthy()
    expect(screen.getByTestId('doc-liste_classe-excel')).toBeTruthy()
  })
})
