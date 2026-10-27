/**
 * Tests de l'espace étudiant MonEspace — ciblés sur la robustesse du
 * chargement initial (régression §10.10, LOT 13).
 *
 * Cet écran lance sa requête de fiche directement dans un `useEffect` dont la
 * dépendance est l'objet `toast` du contexte. Avant la stabilisation de la
 * valeur du ToastContext.Provider, un échec de chargement (toast d'erreur)
 * faisait re-rendre le provider, changeait la référence de `toast` et relançait
 * l'effet en boucle. On vérifie ici qu'il n'y a qu'une seule requête et un seul
 * toast, et que l'écran se contente d'afficher la fiche par défaut.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import MonEspace from '@/pages/scolarite/MonEspace'

const settle = async (n = 6) => {
  await act(async () => { await flushPromises(n) })
}
const ficheCalls = () =>
  apiMock.get.mock.calls.filter(([p]) => p === '/scan/me/fiche/')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
})

describe('pages/scolarite/MonEspace — chargement de la fiche', () => {
  it('affiche la fiche quand le service répond', async () => {
    apiController.setRoute('/scan/me/fiche/', () => ({
      profil: { prenom: 'Awa', nom: 'Koné', numero: 'MAT-001' },
      stats: { nb_modules_inscrits: 8, taux_presence: 92 },
    }))
    renderWithProviders(<MonEspace />, { routePattern: '*', initialEntries: ['/mon-espace'] })

    expect(await screen.findByText(/Awa Koné/)).toBeInTheDocument()
    expect(screen.getByText(/matricule MAT-001/)).toBeInTheDocument()
    expect(screen.getByText(/8 module\(s\) inscrit\(s\)/)).toBeInTheDocument()
    expect(ficheCalls()).toHaveLength(1)
  })

  it('ne relance pas la requête quand la fiche est indisponible (régression §10.10)', async () => {
    // Deux échecs programmés puis un succès : un écran sain ne doit consommer
    // que le premier appel (l'échec), sans mécanisme de réessai.
    let n = 0
    apiController.setRoute('/scan/me/fiche/', () => {
      n += 1
      if (n <= 2) {
        // eslint-disable-next-line no-throw-literal
        throw { response: { status: 500 } }
      }
      return { profil: { prenom: 'Awa', nom: 'Koné' } }
    })

    renderWithProviders(<MonEspace />, { routePattern: '*', initialEntries: ['/mon-espace'] })

    expect(await screen.findByText('Fiche personnelle indisponible.')).toBeInTheDocument()
    await settle()
    // Un seul appel et un seul toast : pas de boucle de rechargement.
    expect(ficheCalls()).toHaveLength(1)
    expect(screen.getAllByText('Fiche personnelle indisponible.')).toHaveLength(1)
    // L'écran se contente de la fiche par défaut (prénom/nom vides), sans crasher.
    expect(screen.getByRole('heading', { name: /mon espace étudiant/i })).toBeInTheDocument()
  })

  it('affiche les compteurs par défaut et la zone attestations avec une fiche vide', async () => {
    // Le service répond sans profil ni stats : les valeurs de repli doivent
    // s'afficher (0 module, taux « — ») et la zone L4 rester présente.
    apiController.setRoute('/scan/me/fiche/', () => ({}))

    renderWithProviders(<MonEspace />, { routePattern: '*', initialEntries: ['/mon-espace'] })

    expect(await screen.findByRole('heading', { name: /mes attestations/i })).toBeInTheDocument()
    expect(screen.getByText(/0 module\(s\) inscrit\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/—% de présence/)).toBeInTheDocument()
    expect(
      screen.getByText(/Les attestations de scolarité et de réussite seront disponibles ici/),
    ).toBeInTheDocument()
  })
})

describe('pages/scolarite/MonEspace — téléchargement du relevé de notes', () => {
  let clickedDownload = null

  const mount = () =>
    renderWithProviders(<MonEspace />, { routePattern: '*', initialEntries: ['/mon-espace'] })

  const fiche = (profil) =>
    apiController.setRoute('/scan/me/fiche/', () => ({
      profil,
      stats: { nb_modules_inscrits: 3, taux_presence: 88 },
    }))

  const clickTelechargement = async () => {
    await act(async () => {
      screen.getByRole('button', { name: /Télécharger mon relevé de notes/i }).click()
    })
    await settle()
  }

  beforeEach(() => {
    clickedDownload = null
    URL.createObjectURL = vi.fn(() => 'blob:notes')
    URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function () {
      clickedDownload = this.download
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('télécharge le PDF du relevé nommé avec le matricule', async () => {
    fiche({ id: 42, prenom: 'Awa', nom: 'Koné', numero: 'MAT-042' })
    mount()
    expect(await screen.findByText(/Awa Koné/)).toBeInTheDocument()
    await clickTelechargement()

    expect(apiMock.getBlob).toHaveBeenCalledTimes(1)
    expect(apiMock.getBlob.mock.calls[0][0]).toBe(
      '/presences/participant/42/notes-fiche/export/pdf/',
    )
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(clickedDownload).toBe('releve-notes-MAT-042.pdf')
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:notes')
  })

  it("retombe sur l'identifiant du dossier dans le nom du fichier en l'absence de matricule", async () => {
    fiche({ id: 42, prenom: 'Awa', nom: 'Koné' })
    mount()
    expect(await screen.findByText(/Awa Koné/)).toBeInTheDocument()
    expect(screen.queryByText(/matricule/)).not.toBeInTheDocument()
    await clickTelechargement()

    expect(apiMock.getBlob).toHaveBeenCalledTimes(1)
    expect(clickedDownload).toBe('releve-notes-42.pdf')
  })

  it("refuse le téléchargement et notifie quand aucun dossier étudiant n'est rattaché", async () => {
    apiController.setRoute('/scan/me/fiche/', () => ({}))
    mount()
    expect(await screen.findByRole('heading', { name: /mes notes/i })).toBeInTheDocument()
    await clickTelechargement()

    expect(apiMock.getBlob).not.toHaveBeenCalled()
    expect(
      await screen.findByText('Aucun dossier étudiant rattaché à ce compte.'),
    ).toBeInTheDocument()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it("notifie l'impossibilité du téléchargement quand le service échoue", async () => {
    fiche({ id: 42, prenom: 'Awa', nom: 'Koné', numero: 'MAT-042' })
    apiMock.getBlob.mockRejectedValueOnce(new Error('generation ko'))
    mount()
    expect(await screen.findByText(/Awa Koné/)).toBeInTheDocument()
    await clickTelechargement()

    expect(
      await screen.findByText('Téléchargement du relevé de notes impossible.'),
    ).toBeInTheDocument()
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  })
})
