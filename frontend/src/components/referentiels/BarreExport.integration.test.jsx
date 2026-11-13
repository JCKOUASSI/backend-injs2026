/**
 * Test d'intégration de la barre d'export : **aucun mock du client API**.
 *
 * Les tests unitaires de `BarreExport` remplacent `api` par un double, ce qui
 * ne prouve pas que la chaîne réelle fonctionne (c'est ainsi que le bug
 * d'export est passé inaperçu). Ici, seul `fetch` est remplacé : le client,
 * le décodage binaire et le déclenchement du téléchargement sont les vrais.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { screen, render, fireEvent, waitFor } from '@testing-library/react'
import BarreExport from './BarreExport'
import { ToastProvider, useToast } from '../../context/ToastContext'

/** Vraie Response binaire, avec en-têtes de téléchargement. */
const reponseFichier = (octets, type, nom) =>
  new Response(octets, {
    status: 200,
    headers: {
      'Content-Type': type,
      'Content-Disposition': `attachment; filename="${nom}"`,
    },
  })

const PDF = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34])
const XLSX = new Uint8Array([0x50, 0x4b, 0x03, 0x04, 0x14, 0x00, 0x06, 0x00])

describe('Barre d’export — chaîne réelle (fetch → blob → téléchargement)', () => {
  let urlsCreees
  let nomsTelecharges

  beforeEach(() => {
    urlsCreees = []
    nomsTelecharges = []
    window.URL.createObjectURL = vi.fn((blob) => {
      urlsCreees.push(blob)
      return 'blob:reel'
    })
    window.URL.revokeObjectURL = vi.fn()
    HTMLAnchorElement.prototype.click = vi.fn(function () {
      nomsTelecharges.push(this.download)
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  it('télécharge réellement un PDF au clic, avec le nom du serveur', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reponseFichier(PDF, 'application/pdf', 'f.pdf')))

    render(<BarreExport slug="filieres" />)
    fireEvent.click(screen.getByRole('button', { name: /PDF/i }))

    await waitFor(() => expect(nomsTelecharges).toHaveLength(1))
    expect(nomsTelecharges[0]).toBe('f.pdf')
    // Le blob reçu contient exactement les octets du serveur.
    const lu = new Uint8Array(await urlsCreees[0].arrayBuffer())
    expect([...lu]).toEqual([...PDF])
  })

  it('télécharge réellement un XLSX sans le corrompre', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reponseFichier(
      XLSX,
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'f.xlsx',
    )))

    render(<BarreExport slug="filieres" />)
    fireEvent.click(screen.getByRole('button', { name: /Excel/i }))

    await waitFor(() => expect(nomsTelecharges).toHaveLength(1))
    expect(nomsTelecharges[0]).toBe('f.xlsx')
    const lu = new Uint8Array(await urlsCreees[0].arrayBuffer())
    expect(lu[0]).toBe(0x50)
    expect(lu[1]).toBe(0x4b)
  })

  it('appelle la bonne URL avec le format ET les filtres', async () => {
    const fetchMock = vi.fn(async () => reponseFichier(PDF, 'application/pdf', 'f.pdf'))
    vi.stubGlobal('fetch', fetchMock)

    render(<BarreExport slug="filieres" filtres={{ search: 'alpha' }} />)
    fireEvent.click(screen.getByRole('button', { name: /PDF/i }))

    await waitFor(() => expect(nomsTelecharges).toHaveLength(1))
    const url = fetchMock.mock.calls[0][0]
    expect(url).toContain('/api/referentiels/filieres/exporter/')
    expect(url).toContain('export=pdf')
    expect(url).toContain('search=alpha')
  })

  it('n’affiche aucune erreur quand tout se passe bien', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reponseFichier(PDF, 'application/pdf', 'f.pdf')))
    const messages = []

    render(<BarreExport slug="filieres" onMessage={(t, m) => messages.push([t, m])} />)
    fireEvent.click(screen.getByRole('button', { name: /PDF/i }))

    await waitFor(() => expect(messages).toHaveLength(1))
    expect(messages[0][0]).toBe('ok')
    expect(messages[0][1]).toMatch(/f\.pdf/)
  })

  it('signale proprement un refus du serveur (403)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(
      JSON.stringify({ detail: 'Permission refusée.' }),
      { status: 403, headers: { 'Content-Type': 'application/json' } },
    )))
    const messages = []

    render(<BarreExport slug="filieres" onMessage={(t, m) => messages.push([t, m])} />)
    fireEvent.click(screen.getByRole('button', { name: /PDF/i }))

    await waitFor(() => expect(messages).toHaveLength(1))
    expect(messages[0][0]).toBe('erreur')
    expect(messages[0][1]).toMatch(/Permission refusée/)
    // Aucun fichier ne doit être téléchargé.
    expect(nomsTelecharges).toHaveLength(0)
  })
})

/**
 * Régression du « je clique et rien ne se passe » : le message de la barre
 * passait par `toast.success?.()`, méthode que le contexte n'exposait pas.
 * L'optional chaining avalait l'appel : le fichier était bien produit, mais
 * aucune confirmation ne s'affichait. Ce test rejoue le câblage réel de
 * l'écran (barre + fournisseur de notifications) et exige un retour visible.
 */
describe('Barre d’export — retour visible pour l’utilisateur', () => {
  beforeEach(() => {
    window.URL.createObjectURL = vi.fn(() => 'blob:reel')
    window.URL.revokeObjectURL = vi.fn()
    HTMLAnchorElement.prototype.click = vi.fn()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
  })

  /** Reproduit le câblage de l'écran : onMessage → toast.success / toast.error. */
  function Ecran() {
    const toast = useToast()
    return (
      <BarreExport
        slug="filieres"
        onMessage={(type, texte) =>
          type === 'ok' ? toast.success?.(texte) : toast.error?.(texte)
        }
      />
    )
  }

  it('affiche une confirmation visible après un export réussi', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => reponseFichier(PDF, 'application/pdf', 'f.pdf')))

    render(
      <ToastProvider>
        <Ecran />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: /PDF/i }))

    await waitFor(() => expect(screen.getByText(/Export PDF généré/)).toBeTruthy())
  })

  it('affiche l’erreur visible quand le serveur refuse l’export', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 403 })))

    render(
      <ToastProvider>
        <Ecran />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: /Excel/i }))

    await waitFor(() => expect(screen.getByText(/permission/i)).toBeTruthy())
  })
})
