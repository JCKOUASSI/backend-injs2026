/**
 * Tests de la page dédiée Documents scolaires — cohérence LMD / formation
 * continue : sélecteurs en cascade, recherche d'étudiant et chemins
 * d'export réellement appelés.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import DocumentsScolaires from '@/pages/scolarite/DocumentsScolaires'

const setupRoutes = () => {
  apiController.setRoute('/scolarite/annee-courante/', () => ({
    annee: { id: 3, libelle: '2026-2027' },
  }))
  apiController.setRoute('/formations/ref/formations/', () => [
    { id: 10, intitule: 'ÉDUCATION ET MOTRICITÉ — LICENCE' },
  ])
  apiController.setRoute('/scolarite/ref/niveaux/', () => [{ id: 2, code: 'L1' }])
  apiController.setRoute('/scolarite/groupes/effectifs/', () => [
    {
      id: 5, nom: 'L1-G1', ref_formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE',
      niveau: 'L1', capacite_max: 35, effectif: 30, actif: true,
    },
  ])
  apiController.setRoute('/formations/participants/list/', (path) => {
    const q = new URL(path, 'http://test').searchParams
    const cherche = (q.get('search') || '').toLowerCase()
    const tous = [
      { id: 42, nom: 'DIALLO', prenom: 'Fatoumata', matricule: 'INJS26-0004' },
      { id: 43, nom: 'DIARRA', prenom: 'Hassan', matricule: 'INJS26-0005' },
    ]
    return {
      count: 2, total_pages: 1,
      results: cherche
        ? tous.filter((p) => p.nom.toLowerCase().includes(cherche))
        : tous,
      filter_options: { groupes: ['Groupe A', 'Groupe B'] },
    }
  })
  apiController.setRoute('/formations/', () => ({
    count: 1,
    results: [{ id: 1, intitule: 'Formation en Administration de Base (FAB)' }],
  }))
  apiController.setRoute('/formations/1/modules/', () => [
    { id: 7, intitule: 'Déontologie de la Fonction Publique' },
  ])
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<DocumentsScolaires />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/documents-scolaires'],
  })
}
const settle = async (n = 6) => {
  await act(async () => { await flushPromises(n) })
}
const blobCalls = () => apiMock.getBlob.mock.calls.map(([p]) => p)

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

describe('pages/scolarite/DocumentsScolaires — cycle LMD', () => {
  it('cascade formation → niveau → groupe puis export LMD', async () => {
    mount()
    await screen.findByText('Liste du groupe TD/TP')
    await settle()

    const boutonPdf = screen.getAllByRole('button', { name: /PDF/ })[0]
    expect(boutonPdf).toBeDisabled()

    fireEvent.change(screen.getAllByLabelText(/^Formation/)[0], { target: { value: '10' } })
    fireEvent.change(screen.getByLabelText(/^Niveau/), { target: { value: '2' } })
    await settle()

    fireEvent.change(screen.getAllByLabelText(/^Groupe/)[0], { target: { value: '5' } })
    await settle()
    expect(screen.getByText(/L1-G1 — 30 étudiants affectés/)).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /PDF/ })[0])
    await settle()
    expect(blobCalls()).toContain('/scolarite/groupes/5/liste/pdf/')
  })
})

describe('pages/scolarite/DocumentsScolaires — formation continue', () => {
  it('liste de classe : groupe legacy transmis en texte, pas en identifiant LMD', async () => {
    mount()
    await screen.findByText('Liste de classe')
    await settle()

    fireEvent.change(screen.getByLabelText(/Groupe \(facultatif\)/), {
      target: { value: 'Groupe A' },
    })
    // Ordre des boutons Excel : groupe TD/TP (désactivé), liste de classe, relevé.
    const boutonsExcel = screen.getAllByRole('button', { name: /Excel/ })
    fireEvent.click(boutonsExcel[1])
    await settle()
    expect(blobCalls().at(-1)).toBe(
      '/exports/participants/liste-classe/excel/?groupe=Groupe+A',
    )
  })

  it('fiche de notes : modules de la formation continue choisie', async () => {
    mount()
    await screen.findByText('Fiche de notes d’un module')
    await settle()

    const selectsFormation = screen.getAllByLabelText(/^Formation/)
    fireEvent.change(selectsFormation[1], { target: { value: '1' } })
    await settle()
    fireEvent.change(screen.getByLabelText(/^Module/), { target: { value: '7' } })

    const boutonsPdf = screen.getAllByRole('button', { name: /PDF/ })
    fireEvent.click(boutonsPdf[2])
    await settle()
    expect(blobCalls().at(-1)).toBe('/formations/1/modules/7/notes/fiche/pdf/')
  })

  it('relevé : recherche puis sélection d’un étudiant', async () => {
    mount()
    await screen.findByText('Relevé d’un étudiant')
    await settle()

    fireEvent.change(screen.getByPlaceholderText(/Nom, prénom ou matricule/i), {
      target: { value: 'diallo' },
    })
    const proposition = await screen.findByRole('button', { name: /DIALLO Fatoumata/ })
    fireEvent.click(proposition)
    await settle()
    expect(screen.getByText('INJS26-0004')).toBeInTheDocument()

    const boutonsPdf = screen.getAllByRole('button', { name: /PDF/ })
    fireEvent.click(boutonsPdf.at(-1))
    await settle()
    expect(blobCalls().at(-1)).toBe('/participant/42/notes-fiche/export/pdf/')
  })
})
