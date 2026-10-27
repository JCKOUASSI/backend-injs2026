/**
 * Barre latérale RBAC — rendu filtré par les droits du compte connecté.
 *
 * Les assertions portent sur le comportement visible du menu : source de la
 * décision (CURP ou capacités legacy), entrées masquées, sections vides
 * supprimées, état ouvert/fermé mémorisé, et pied de barre (profil,
 * déconnexion, aide). Aucun test n'accorde de droit : on vérifie seulement ce
 * que le composant **affiche**, l'autorité restant le backend.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Sidebar from './Sidebar'

const CLE_ETAT = 'injs.sidebar.sectionsOuvertes'

/** Capacités legacy complètes d'un administrateur (contrat /auth/capabilities/). */
const CAPACITES_ADMIN = {
  capacites: {
    web: ['acceder', 'operationnel'],
    utilisateurs: ['voir', 'gerer'],
    participants: ['lister', 'creer', 'gerer'],
    presences: ['voir', 'agir', 'superviser'],
    finance: ['voir', 'exporter', 'parametrer'],
    statistiques: ['voir', 'voir_globales'],
    evaluations: ['gerer_questionnaires', 'consulter'],
    notes: ['gerer', 'valider_decisions'],
    scolarite: ['voir', 'agir'],
    exports: ['liste_classe'],
    dashboard: ['filtrer_secretariat'],
    habilitations_admin: ['gerer'],
  },
}

function monter({
  user,
  mesAcces,
  capacites = CAPACITES_ADMIN,
  chemin = '/dashboard',
  drapeauConsole = true,
} = {}) {
  const compte = user || makeUser('ADMIN')
  apiController.setMe(compte)
  apiController.setRoute('/auth/capabilities/', capacites)
  apiController.setRoute('/habilitations/mes-acces/', mesAcces ?? { gouverne: false })
  apiController.setRoute('/parametres/flags/', { flags: { 'flag.curp_ui_admin': drapeauConsole } })
  render(<Sidebar />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={compte} routePattern="*" initialEntries={[chemin]}>
        {children}
      </AllProviders>
    ),
  })
  return compte
}

/** Attend que le compte et ses capacités soient chargés (menu rendu). */
async function attendreMenu() {
  await screen.findByTestId('sidebar-identite')
  await waitFor(() => {
    expect(screen.queryAllByRole('button').length).toBeGreaterThan(0)
  })
}

/** Ouvre une section (accordion) et renvoie son conteneur. */
async function ouvrirSection(libelle) {
  await attendreMenu()
  const tete = await screen.findByRole('button', { name: new RegExp(libelle, 'i') })
  if (tete.getAttribute('aria-expanded') !== 'true') fireEvent.click(tete)
  await waitFor(() => expect(tete.getAttribute('aria-expanded')).toBe('true'))
  const sousMenu = document.getElementById(tete.getAttribute('aria-controls'))
  expect(sousMenu, 'sous-menu introuvable').toBeTruthy()
  return within(sousMenu)
}

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
  apiController.reset()
  localStorage.clear()
})

describe('identité et source des droits', () => {
  it('affiche le compte connecté et son rôle', async () => {
    monter({ user: makeUser('ADMIN', { first_name: 'Aya', last_name: 'Kone' }) })
    const identite = await screen.findByTestId('sidebar-identite')
    expect(identite.textContent).toContain('Aya Kone')
  })

  it('compte non gouverné → source LEGACY et badge « Droits legacy »', async () => {
    monter({ mesAcces: { gouverne: false, mode: 'OBSERVATION' } })
    await waitFor(() => {
      expect(document.getElementById('sidebar').dataset.sourceDroits).toBe('LEGACY')
    })
    expect(screen.getByText('Droits legacy')).toBeTruthy()
  })

  it('compte gouverné → source CURP et badge « Droits CURP »', async () => {
    monter({
      mesAcces: {
        gouverne: true,
        statut: 'ACTIF',
        permissions_effectives: ['candidatures.candidature.consulter'],
      },
    })
    await waitFor(() => {
      expect(document.getElementById('sidebar').dataset.sourceDroits).toBe('CURP')
    })
    expect(screen.getByText('Droits CURP')).toBeTruthy()
  })

  it('mes-acces renvoie un corps inexploitable → repli legacy, menu utilisable', async () => {
    const compte = makeUser('ADMIN')
    apiController.setMe(compte)
    apiController.setRoute('/auth/capabilities/', CAPACITES_ADMIN)
    // Page d'erreur / proxy de secours : ni objet exploitable ni `gouverne`.
    apiController.setRoute('/habilitations/mes-acces/', ['<html>502 Bad Gateway</html>'])
    render(<Sidebar />, {
      wrapper: ({ children }) => (
        <AllProviders authUser={compte} routePattern="*" initialEntries={['/dashboard']}>
          {children}
        </AllProviders>
      ),
    })
    await attendreMenu()
    await waitFor(() => {
      expect(document.getElementById('sidebar').dataset.sourceDroits).toBe('LEGACY')
    })
    // « Tableau de bord » est une section sans enfant : rendue en lien direct.
    expect(await screen.findByRole('link', { name: /Tableau de bord/i })).toBeTruthy()
  })
})

describe('filtrage par les capacités legacy (compte non gouverné)', () => {
  it('un administrateur voit les sections structurantes du modèle', async () => {
    monter()
    await attendreMenu()
    await waitFor(() => {
      expect(document.getElementById('sidebar').dataset.sourceDroits).toBe('LEGACY')
    })
    await screen.findByRole('button', { name: /Scolarité/i })
    const sections = screen.getAllByRole('button').map((b) => b.textContent)
    for (const attendu of ['Scolarité', 'Formations', 'Jurys', 'Statistiques', 'Audit & Traçabilité']) {
      expect(sections.some((texte) => texte.includes(attendu)), attendu).toBe(true)
    }
  })

  it('une capacité absente masque toute la section correspondante', async () => {
    const capacites = {
      capacites: { web: ['acceder', 'operationnel'], scolarite: ['voir'] },
    }
    monter({ user: makeUser('SECRETARIAT'), capacites })
    await attendreMenu()
    await screen.findByRole('button', { name: /Scolarité/i })
    // « habilitations_admin » absent → Audit & Traçabilité entièrement masquée.
    expect(screen.queryByRole('button', { name: /Audit & Traçabilité/i })).toBeNull()
  })

  it('un compte sans aucune capacité voit un menu vide explicatif', async () => {
    monter({ user: makeUser('FINANCE'), capacites: { capacites: {} } })
    expect(await screen.findByText(/Aucune entrée autorisée pour ce compte/i)).toBeTruthy()
    // Le pied de barre reste présent : on peut toujours se déconnecter.
    expect(screen.getByTestId('nav-deconnexion')).toBeTruthy()
  })
})

describe('filtrage par les permissions CURP (compte gouverné)', () => {
  const mesAcces = (codes) => ({ gouverne: true, statut: 'ACTIF', permissions_effectives: codes })

  it('n\'affiche que les entrées dont un code CURP est détenu', async () => {
    monter({ mesAcces: mesAcces(['candidatures.candidature.consulter']) })
    const scolarite = await ouvrirSection('Scolarité')
    expect(scolarite.getByTestId('nav-scolarite.candidatures')).toBeTruthy()
    // Même section, autre permission : non détenue donc masquée.
    expect(scolarite.queryByTestId('nav-scolarite.controle_dossiers')).toBeNull()
  })

  it('une capacité legacy ne repêche pas une entrée gouvernée non détenue', async () => {
    // L'utilisateur a `statistiques.voir` en legacy, mais aucune permission
    // CURP correspondante : pour un compte gouverné, le référentiel CURP fait
    // foi et la section Statistiques disparaît.
    monter({ mesAcces: mesAcces(['candidatures.candidature.consulter']) })
    await waitFor(() => {
      expect(document.getElementById('sidebar').dataset.sourceDroits).toBe('CURP')
    })
    expect(screen.queryByRole('button', { name: /Statistiques/i })).toBeNull()
  })

  it('une entrée sans volet CURP reste évaluée par les capacités legacy', async () => {
    // Les entrées de la console CURP (intégrité du journal, archives) ne
    // déclarent volontairement aucun code CURP : leur garde serveur est le
    // drapeau + le trio d'administration. Un compte gouverné qui détient la
    // capacité projetée `habilitations_admin.gerer` les voit donc toujours,
    // tandis que les entrées gouvernées par code CURP qu'il ne détient pas
    // (journal, actions…) restent masquées.
    monter({ mesAcces: mesAcces(['candidatures.candidature.consulter']) })
    const audit = await ouvrirSection('Audit & Traçabilité')
    expect(audit.getByTestId('nav-audit.integrite')).toBeTruthy()
    expect(audit.getByTestId('nav-audit.archives')).toBeTruthy()
    expect(audit.queryByTestId('nav-audit.journal')).toBeNull()
    expect(audit.queryByTestId('nav-audit.actions')).toBeNull()
  })

  it('une liste de permissions vide ferme le menu (fermeture par défaut)', async () => {
    monter({ mesAcces: mesAcces([]) })
    expect(await screen.findByText(/Aucune entrée autorisée pour ce compte/i)).toBeTruthy()
  })

  it('plusieurs permissions ouvrent plusieurs sections', async () => {
    monter({
      mesAcces: mesAcces([
        'candidatures.candidature.consulter',
        'administration.journal.consulter',
        'statistiques.tableau_bord.consulter',
      ]),
    })
    await waitFor(() => {
      expect(document.getElementById('sidebar').dataset.sourceDroits).toBe('CURP')
    })
    expect(screen.getByRole('button', { name: /Scolarité/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Audit & Traçabilité/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Statistiques/i })).toBeTruthy()
  })

  it('l\'infobulle d\'une entrée expose le droit requis (diagnostic)', async () => {
    monter({ mesAcces: mesAcces(['administration.journal.consulter']) })
    const audit = await ouvrirSection('Audit & Traçabilité')
    const lien = audit.getByTestId('nav-audit.journal')
    expect(lien.getAttribute('title')).toContain('administration.journal.consulter')
  })
})

describe('comportement de la navigation', () => {
  it('ouvrir une section révèle ses entrées, la refermer les masque', async () => {
    monter()
    await attendreMenu()
    const tete = await screen.findByRole('button', { name: /Scolarité/i })
    expect(tete.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(tete)
    await waitFor(() => expect(tete.getAttribute('aria-expanded')).toBe('true'))
    expect(screen.getByTestId('nav-scolarite.candidatures')).toBeTruthy()
    fireEvent.click(tete)
    await waitFor(() => expect(tete.getAttribute('aria-expanded')).toBe('false'))
    expect(screen.queryByTestId('nav-scolarite.candidatures')).toBeNull()
  })

  it('l\'état ouvert/fermé est mémorisé entre deux rendus', async () => {
    monter()
    await attendreMenu()
    fireEvent.click(await screen.findByRole('button', { name: /Scolarité/i }))
    await waitFor(() => {
      const brut = localStorage.getItem(CLE_ETAT)
      expect(brut && JSON.parse(brut).scolarite).toBe(true)
    })
  })

  it('la section de la route courante est ouverte d\'office et marquée active', async () => {
    monter({ chemin: '/audit/journal' })
    const tete = await screen.findByRole('button', { name: /Audit & Traçabilité/i })
    await waitFor(() => expect(tete.getAttribute('aria-expanded')).toBe('true'))
    expect(tete.className).toContain('active')
  })

  it('kill-switch fermé : les entrées de console disparaissent même pour un super-compte', async () => {
    // Capacités complètes (projection super-utilisateur) mais drapeau
    // `flag.curp_ui_admin` fermé : le serveur refuserait la console, le menu
    // ne doit donc pas la proposer.
    monter({ drapeauConsole: false })
    const audit = await ouvrirSection('Audit & Traçabilité')
    expect(audit.queryByTestId('nav-audit.integrite')).toBeNull()
    expect(audit.queryByTestId('nav-audit.archives')).toBeNull()
    // … tandis que les entrées hors console restent proposées.
    expect(audit.getByTestId('nav-audit.journal')).toBeTruthy()
  })

  it('chaque entrée rend un lien vers son chemin', async () => {
    monter({ chemin: '/audit/journal' })
    const audit = await ouvrirSection('Audit & Traçabilité')
    expect(audit.getByTestId('nav-audit.journal').getAttribute('href')).toBe('/audit/journal')
    expect(audit.getByTestId('nav-audit.actions').getAttribute('href')).toBe('/audit/actions')
  })

  it('le pied de barre propose Profil et Déconnexion', async () => {
    monter()
    expect(screen.getByTestId('nav-profil').getAttribute('href')).toBe('/profile')
    expect(screen.getByTestId('nav-deconnexion')).toBeTruthy()
  })

  it('la déconnexion appelle la fermeture de session', async () => {
    monter()
    fireEvent.click(screen.getByTestId('nav-deconnexion'))
    await waitFor(() => {
      expect(apiController.findCall('post', '/auth/logout/')).toBeTruthy()
    })
  })
})
