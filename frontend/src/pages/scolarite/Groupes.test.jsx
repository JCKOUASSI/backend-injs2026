/**
 * Tests de la page Groupes pédagogiques — indicateurs, cohortes,
 * non-affectés, filtres et répartition automatique.
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
import Groupes from '@/pages/scolarite/Groupes'

const effectifsCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.split('?')[0] === '/scolarite/groupes/effectifs/')
    .map(([, opts]) => opts?.params || {})
const repartitionCalls = () =>
  apiMock.post.mock.calls.filter(([p]) => p.includes('/groupes/repartition/'))

const GROUPES = [
  {
    id: 1, nom: 'L1-G1', annee_academique: '2026-2027',
    ref_formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE', niveau: 'L1',
    capacite_max: 35, effectif: 30, places_restantes: 5, actif: true,
  },
  {
    id: 2, nom: 'L1-G2', annee_academique: '2026-2027',
    ref_formation: 'ÉDUCATION ET MOTRICITÉ — LICENCE', niveau: 'L1',
    capacite_max: 35, effectif: 35, places_restantes: 0, actif: true,
  },
  {
    id: 3, nom: 'M2-G1', annee_academique: '2026-2027',
    ref_formation: 'LOISIR — MASTER', niveau: 'M2',
    capacite_max: null, effectif: 0, places_restantes: null, actif: false,
  },
]

const setupRoutes = () => {
  apiController.setRoute('/scolarite/annee-courante/', () => ({
    annee: { id: 3, libelle: '2026-2027' },
  }))
  apiController.setRoute('/formations/ref/formations/', () => [
    { id: 10, intitule: 'ÉDUCATION ET MOTRICITÉ — LICENCE' },
  ])
  apiController.setRoute('/scolarite/ref/niveaux/', () => [{ id: 2, code: 'L1' }])
  apiController.setRoute('/scolarite/groupes/effectifs/', () => GROUPES)
  apiController.setRoute('/scolarite/groupes/non-affectes/', () => ({ non_affectes: 4 }))
  apiController.setRoute('/scolarite/groupes/repartition/', () => ({
    affectations: 4, echecs: [],
  }))
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Groupes />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/groupes'],
  })
}
const settle = async (n = 6) => {
  await act(async () => { await flushPromises(n) })
}

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('pages/scolarite/Groupes — affichage premium', () => {
  it('affiche indicateurs, cohortes, remplissage et alerte non-affectés', async () => {
    mount()
    await screen.findByText('L1-G1')
    await settle()

    // Bandeau : année + étudiants affectés (30 + 35 + 0).
    expect(screen.getByText(/Année 2026-2027/)).toBeInTheDocument()
    expect(screen.getByText(/65 étudiant\(s\) affecté\(s\)/)).toBeInTheDocument()
    // KPI enrichis.
    expect(screen.getByText('Total groupes')).toBeInTheDocument()
    expect(screen.getByText(/2 formations · 2 niveaux/)).toBeInTheDocument()
    expect(screen.getByText('4 sans groupe')).toBeInTheDocument()
    expect(screen.getByText('Groupes actifs')).toBeInTheDocument()
    // Alerte non-affectés.
    expect(screen.getByText(/4 étudiant\(s\) validé\(s\) sans groupe/)).toBeInTheDocument()
    // Cohortes et états de remplissage.
    expect(screen.getAllByText('ÉDUCATION ET MOTRICITÉ — LICENCE').length).toBeGreaterThan(0)
    expect(screen.getByText(/L1 · 2 groupes · 65 étudiants/)).toBeInTheDocument()
    // KPI (total) + ligne du groupe L1-G1.
    expect(screen.getAllByText('5 places restantes')).toHaveLength(2)
    expect(screen.getByText('Complet')).toBeInTheDocument()
    expect(screen.getByText('Sans limite')).toBeInTheDocument()
    expect(screen.getByText('Inactif')).toBeInTheDocument()
  })

  it('filtre localement par recherche sans rappeler le serveur', async () => {
    mount()
    await screen.findByText('L1-G1')
    const appelsAvant = effectifsCalls().length

    fireEvent.change(screen.getByPlaceholderText(/Rechercher un groupe/i), {
      target: { value: 'L1-G2' },
    })
    await settle()

    expect(screen.queryByText('L1-G1')).not.toBeInTheDocument()
    expect(screen.getByText('L1-G2')).toBeInTheDocument()
    expect(effectifsCalls().length).toBe(appelsAvant)
  })

  it('transmet les filtres formation et état au service', async () => {
    mount()
    await screen.findByText('L1-G1')

    fireEvent.change(screen.getByDisplayValue('Toutes les formations'), {
      target: { value: '10' },
    })
    await settle()
    expect(effectifsCalls().at(-1)).toMatchObject({ ref_formation_id: '10' })

    fireEvent.change(screen.getByDisplayValue('Tous les états'), {
      target: { value: '1' },
    })
    await settle()
    expect(effectifsCalls().at(-1)).toMatchObject({ ref_formation_id: '10', actif: '1' })
  })

  it('répartit automatiquement la cohorte choisie et notifie', async () => {
    mount()
    await screen.findByText('L1-G1')

    fireEvent.change(screen.getByDisplayValue('Toutes les formations'), {
      target: { value: '10' },
    })
    fireEvent.change(screen.getByDisplayValue('Tous les niveaux'), {
      target: { value: '2' },
    })
    await settle()

    fireEvent.click(screen.getByRole('button', { name: /répartir automatiquement/i }))
    await settle(8)

    expect(repartitionCalls()).toHaveLength(1)
    expect(repartitionCalls()[0][1]).toMatchObject({
      ref_formation_id: '10', niveau_id: '2', annee_academique_id: 3,
    })
    expect(await screen.findByText('4 étudiant(s) affecté(s)')).toBeInTheDocument()
  })
})
