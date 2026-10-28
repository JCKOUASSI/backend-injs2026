import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, within, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PlancheDeStyle from '@/pages/design/PlancheDeStyle'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import * as planche from '@/lib/plancheStyle'

/**
 * Planche de style — l'écran lit le CSS réel : les tests fournissent donc de
 * fausses feuilles de style et une fausse déclaration calculée, pour vérifier
 * que les valeurs affichées viennent bien de la lecture et non d'une constante.
 */

const VALEURS = {
  '--injs-navy': '#071B3A',
  '--injs-danger': '#DC3545',
  '--injs-space-4': '1rem',
  '--injs-fs-lg': '1.125rem',
}

function fausseDeclaration() {
  const declaration = { length: Object.keys(VALEURS).length }
  Object.keys(VALEURS).forEach((nom, index) => { declaration[index] = nom })
  declaration.getPropertyValue = (nom) => VALEURS[nom] ?? ''
  return declaration
}

function fausseFeuille() {
  return {
    cssRules: [
      { style: (() => { const d = { length: 2 }; d[0] = '--injs-navy'; d[1] = 'color'; return d })() },
      { cssRules: [{ style: (() => { const d = { length: 1 }; d[0] = '--injs-danger'; return d })() }] },
    ],
  }
}

let spyStyle
let styleSheetsInitial

beforeEach(() => {
  spyStyle = vi.spyOn(window, 'getComputedStyle').mockReturnValue(fausseDeclaration())
  styleSheetsInitial = Object.getOwnPropertyDescriptor(document, 'styleSheets')
  Object.defineProperty(document, 'styleSheets', {
    configurable: true,
    value: [fausseFeuille()],
  })
})

afterEach(() => {
  spyStyle.mockRestore()
  if (styleSheetsInitial) Object.defineProperty(document, 'styleSheets', styleSheetsInitial)
  else delete document.styleSheets
  vi.restoreAllMocks()
})

/**
 * Bloc « socle réel » : au lieu de doubles, on injecte le VRAI
 * `designSystem.css` dans le document. jsdom résout les propriétés
 * personnalisées, ce qui permet de vérifier la chaîne complète
 * feuille de style → lecture → affichage, et non seulement la logique.
 */
const CHEMIN_SOCLE = require('node:path').resolve(process.cwd(), 'src/styles/designSystem.css')

function rendre() {
  return renderWithProviders(<PlancheDeStyle />, {
    routePattern: '/referentiels/planche-de-style',
    initialEntries: ['/referentiels/planche-de-style'],
  })
}

describe('pages/design/PlancheDeStyle — lecture du socle réel', () => {
  it('affiche les jetons lus dans le CSS, groupés par catégorie', async () => {
    rendre()
    // Attendu après l'effet de lecture.
    const tableauCouleurs = await screen.findByRole('table', { name: /Couleurs \(2\)/ })
    expect(within(tableauCouleurs).getByText('--injs-navy')).toBeInTheDocument()
    expect(within(tableauCouleurs).getByText('#071B3A')).toBeInTheDocument()
    expect(within(tableauCouleurs).getByText('--injs-danger')).toBeInTheDocument()

    const tableauEspace = screen.getByRole('table', { name: /Espacements \(1\)/ })
    expect(within(tableauEspace).getByText('1rem')).toBeInTheDocument()
  })

  it('compte les jetons dans le repère et distingue le total filtré', async () => {
    rendre()
    await screen.findByText('--injs-navy')
    expect(screen.getByText('4')).toBeInTheDocument() // total affiché
  })

  it('filtre les jetons par nom', async () => {
    const utilisateur = userEvent.setup()
    rendre()
    await screen.findByText('--injs-navy')

    await utilisateur.type(screen.getByLabelText(/Filtrer les jetons/i), 'danger')
    expect(screen.getByText('--injs-danger')).toBeInTheDocument()
    expect(screen.queryByText('--injs-navy')).not.toBeInTheDocument()
  })

  it('filtre aussi par valeur et affiche un état vide explicite', async () => {
    const utilisateur = userEvent.setup()
    rendre()
    await screen.findByText('--injs-navy')

    const champ = screen.getByLabelText(/Filtrer les jetons/i)
    await utilisateur.type(champ, 'zzz-introuvable')

    expect(screen.queryByText('--injs-navy')).not.toBeInTheDocument()
    expect(screen.getByText(/Aucun jeton de couleur ne correspond au filtre/i)).toBeInTheDocument()
  })
})

describe('pages/design/PlancheDeStyle — copie d’un jeton', () => {
  it('copie « nom: valeur; » et annonce le résultat', async () => {
    const utilisateur = userEvent.setup()
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })

    rendre()
    await screen.findByText('--injs-navy')

    await utilisateur.click(screen.getByRole('button', { name: 'Copier --injs-navy' }))

    expect(writeText).toHaveBeenCalledWith('--injs-navy: #071B3A;')
    expect(screen.getByTestId('retour-copie')).toHaveTextContent('Copié : --injs-navy')
  })

  it('nomme chaque bouton de copie (aucune icône muette)', async () => {
    rendre()
    await screen.findByText('--injs-navy')
    const boutons = screen.getAllByRole('button', { name: /^Copier --injs-/ })
    expect(boutons).toHaveLength(4)
    for (const bouton of boutons) expect(bouton).toHaveAccessibleName()
  })
})

describe('pages/design/PlancheDeStyle — contrastes calculés', () => {
  it('affiche des ratios calculés, jamais des valeurs en dur', async () => {
    rendre()
    const table = await screen.findByRole('table', { name: /Texte sur fond/i })
    // Le ratio du texte principal sur blanc est calculé par la même fonction
    // pure que la bibliothèque : on vérifie la cohérence, pas une constante.
    const attendu = planche.ratioContraste('#0F1F33', '#FFFFFF').toFixed(2)
    expect(within(table).getByText(`${attendu} : 1`)).toBeInTheDocument()
  })

  it('signale un écart AA sans le masquer', async () => {
    rendre()
    const table = await screen.findByRole('table', { name: /Texte sur fond/i })
    const ligneVert = within(table).getByText(/Vert succès/i).closest('tr')
    // Le vert succès du socle n'atteint pas AA sur fond blanc : la planche le dit.
    expect(within(ligneVert).getByText(/AA — grand texte/i)).toBeInTheDocument()
  })
})

describe('pages/design/PlancheDeStyle — repère responsive et repères', () => {
  it('affiche la largeur mesurée et le point de rupture correspondant', async () => {
    rendre()
    expect(await screen.findByText(/Point de rupture/i)).toBeInTheDocument()
    const libelle = screen.getByText(planche.pointDeRupture(window.innerWidth || 0))
    expect(libelle).toBeInTheDocument()
  })

  it('se met à jour au redimensionnement', async () => {
    rendre()
    await act(async () => {
      window.innerWidth = 400
      window.dispatchEvent(new Event('resize'))
    })
    // 400 px tombe dans le palier mobile (≤ 480 px), pas dans tablette.
    expect(screen.getByText(/≤ 480 px — mobile/)).toBeInTheDocument()
    window.innerWidth = 1024
  })
})

describe('pages/design/PlancheDeStyle — composants de démonstration', () => {
  it('rend le sommaire, les boutons, le tableau et les messages du socle', async () => {
    rendre()
    await screen.findByText('--injs-navy')

    expect(screen.getByRole('navigation', { name: /Sommaire/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Action principale' })).toHaveClass('btn', 'btn-primary')
    expect(screen.getByRole('button', { name: 'Supprimer' })).toHaveClass('btn-danger')
    expect(screen.getByRole('table', { name: /tableau de données/i })).toBeInTheDocument()
    // Plusieurs messages portent un rôle « status » (dont la zone de copie) :
    // on vérifie le contenu, pas l'unicité du rôle.
    expect(screen.getByText(/Opération enregistrée avec succès/i)).toBeInTheDocument()
    expect(screen.getByText(/Action refusée/i).closest('.alert')).toHaveAttribute('role', 'alert')
  })

  it('ouvre la modale réelle et la referme par Échap', async () => {
    const utilisateur = userEvent.setup()
    rendre()
    await screen.findByText('--injs-navy')

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await utilisateur.click(screen.getByRole('button', { name: /Ouvrir la modale/i }))

    const dialogue = screen.getByRole('dialog')
    expect(dialogue).toHaveAttribute('aria-modal', 'true')
    expect(within(dialogue).getByText(/Confirmer la suppression/i)).toBeInTheDocument()

    await utilisateur.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('imprime la planche sans quitter l’écran', async () => {
    const utilisateur = userEvent.setup()
    const imprimer = vi.fn()
    window.print = imprimer

    rendre()
    await screen.findByText('--injs-navy')

    await utilisateur.click(screen.getByRole('button', { name: /Imprimer la planche/i }))
    expect(imprimer).toHaveBeenCalledTimes(1)
  })

  it('ne déclenche aucun appel API (l’apparence n’en dépend pas)', async () => {
    const api = (await import('@/services/api')).default
    const espion = vi.spyOn(api, 'get')
    rendre()
    await screen.findByText('--injs-navy')
    expect(espion).not.toHaveBeenCalled()
    espion.mockRestore()
  })
})

describe('pages/design/PlancheDeStyle — avec le socle réel', () => {
  let baliseStyle = null

  beforeEach(() => {
    // On retire les doubles du bloc précédent pour lire le vrai document.
    spyStyle.mockRestore()
    if (styleSheetsInitial) Object.defineProperty(document, 'styleSheets', styleSheetsInitial)
    else delete document.styleSheets
    const cssReel = require('node:fs').readFileSync(CHEMIN_SOCLE, 'utf8')
    baliseStyle = document.createElement('style')
    baliseStyle.textContent = cssReel
    document.head.appendChild(baliseStyle)
  })

  afterEach(() => {
    baliseStyle?.remove()
  })

  it('affiche le jeton navy avec sa valeur réellement résolue', async () => {
    rendre()
    const table = await screen.findByRole('table', { name: /Couleurs \(\d+\)/ })
    expect(within(table).getByText('--injs-navy')).toBeInTheDocument()
    expect(within(table).getAllByText('#071B3A').length).toBeGreaterThan(0)
  })

  it('couvre TOUS les jetons déclarés dans le fichier de socle', async () => {
    rendre()
    await screen.findByText('--injs-navy')

    const cssReel = require('node:fs').readFileSync(CHEMIN_SOCLE, 'utf8')
    const attendus = [...new Set([...cssReel.matchAll(/(--injs-[a-z0-9-]+)\s*:/g)].map((m) => m[1]))]
    const rendus = screen.getAllByRole('rowheader').map((cellule) => cellule.textContent)

    const manquants = attendus.filter((nom) => !rendus.includes(nom))
    expect(manquants).toEqual([])
    expect(attendus.length).toBeGreaterThan(60)
  })

  it('la palette nomme ses pastilles et affiche la valeur réelle', async () => {
    rendre()
    await screen.findByText('--injs-navy')

    const palette = screen.getByRole('list', { name: /Palette officielle/i })
    const pastille = within(palette).getByText('navy').closest('.planche__teinte')
    expect(pastille).toBeTruthy()
    expect(within(pastille).getByText('#071B3A')).toBeInTheDocument()
  })
})
