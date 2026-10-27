/**
 * Tests de la page Inscriptions administratives (LOT 11) — liste, filtres et
 * validation en cascade (l'écran enchaîne lui-même les transitions jusqu'à
 * VALIDEE via CHEMIN_VALIDATION).
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Inscriptions from '@/pages/scolarite/Inscriptions'

const listCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.split('?')[0] === '/scolarite/inscriptions/')
    .map(([, opts]) => opts?.params || {})
const transitions = () =>
  apiMock.post.mock.calls
    .filter(([p]) => p.includes('/transition/'))
    .map(([p, body]) => ({ path: p, body }))

const setupRoutes = () => {
  apiController.setRoute('/scolarite/annee-courante/', () => ({ annee: { id: 1, libelle: '2025-2026' } }))
  apiController.setRoute('/formations/ref/formations/', () => [{ id: 10, intitule: 'L1 LSF' }])
  apiController.setRoute('/scolarite/ref/niveaux/', () => [{ id: 2, code: 'N1' }])
  apiController.setRoute('/scolarite/inscriptions/', () => [
    {
      id: 1, matricule: 'MAT-001', etudiant: 'Awa Koné', etudiant_id: 5,
      ref_formation: 'L1 LSF', niveau: 'N1', type_inscription_libelle: 'Nouvelle',
      statut: 'BROUILLON', statut_libelle: 'Brouillon',
      annee_academique: '2025-2026',
    },
    {
      id: 2, matricule: 'MAT-002', etudiant: 'Karim Diop', etudiant_id: 6,
      ref_formation: 'L1 LSF', niveau: 'N1', type_inscription_libelle: 'Réinscription',
      statut: 'VALIDEE', statut_libelle: 'Validée',
      annee_academique: '2025-2026',
    },
  ])
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Inscriptions />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/inscriptions'],
  })
}
const settle = async (n = 5) => {
  await act(async () => { await flushPromises(n) })
}
const rowOf = (matricule) => screen.getByText(matricule).closest('tr')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('pages/scolarite/Inscriptions — liste et filtres', () => {
  it('affiche les inscriptions, l’année et le lien vers les admissions', async () => {
    mount()
    await settle()
    expect(await screen.findByText('MAT-001')).toBeInTheDocument()
    expect(screen.getByText('Karim Diop')).toBeInTheDocument()
    const annees = await screen.getAllByText((text) => text.includes('2025-2026'))
    expect(annees).toHaveLength(2)
    annees.forEach((el) => expect(el).toBeInTheDocument())
    expect(screen.getByRole('link', { name: /inscrire un admis/i })).toHaveAttribute(
      'href',
      '/scolarite/admissions',
    )
  })

  it('passe les filtres (recherche, statut) au service', async () => {
    mount()
    await screen.findByText('MAT-001')

    fireEvent.change(screen.getByPlaceholderText(/Rechercher un étudiant/i), { target: { value: 'Koné' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ q: 'Koné' })

    fireEvent.change(screen.getByDisplayValue('Tous les statuts'), { target: { value: 'VALIDEE' } })
    await settle()
    expect(listCalls().at(-1)).toMatchObject({ q: 'Koné', statut: 'VALIDEE' })

    // Les filtres formation/niveau ne sont pas actifs dans ce composant;
    // on vérifie simplement que les recherche et statut fonctionnent.
  })
})

describe('pages/scolarite/Inscriptions — validation en cascade', () => {
  it('valide un brouillon en enchaînant EN_ATTENTE → A_VALIDER → VALIDEE puis recharge', async () => {
    mount()
    await screen.findByText('MAT-001')

    // Seul le brouillon présente le bouton Valider ; l'inscription validée non.
    const rowBrouillon = rowOf('MAT-001')
    fireEvent.click(within(rowBrouillon).getByRole('button', { name: 'Valider' }))
    await settle(7)

    expect(transitions()).toEqual([
      { path: '/scolarite/inscriptions/1/transition/', body: { statut: 'EN_ATTENTE' } },
      { path: '/scolarite/inscriptions/1/transition/', body: { statut: 'A_VALIDER' } },
      { path: '/scolarite/inscriptions/1/transition/', body: { statut: 'VALIDEE' } },
    ])
    expect(await screen.findByText('Inscription validée')).toBeInTheDocument()
    // La liste est rechargée après la cascade.
    expect(listCalls().length).toBeGreaterThan(1)
    // Une inscription déjà validée n'offre pas le bouton.
    expect(
      within(rowOf('MAT-002')).queryByRole('button', { name: 'Valider' }),
    ).not.toBeInTheDocument()
  })

  it('s’arrête et notifie si une transition de la cascade est rejetée', async () => {
    let n = 0
    apiController.setRoute(/\/scolarite\/inscriptions\/\d+\/transition\//, () => {
      n += 1
      if (n >= 2) {
        // eslint-disable-next-line no-throw-literal
        throw { response: { data: { error: 'Étape bloquée.' } } }
      }
      return {}
    })
    mount()
    await screen.findByText('MAT-001')
    fireEvent.click(within(rowOf('MAT-001')).getByRole('button', { name: 'Valider' }))
    await settle(7)

    // La cascade s'interrompt après la 2e transition (la 3e n'est pas émise).
    expect(transitions()).toHaveLength(2)
    expect(await screen.findByText('Étape bloquée.')).toBeInTheDocument()
  })
})
