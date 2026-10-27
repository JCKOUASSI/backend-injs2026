/**
 * Tests de la page Candidatures d'admission (LOT 9) — un écran qui écrit.
 * La page passe par les helpers de `services/scolarite.js` :
 *   liste + référentiels en lecture, puis via le panneau « Dossier » des
 *   transitions de statut, la vérification de pièces et l'ouverture
 *   d'admission, et un formulaire de création candidat + candidature.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import Candidatures from '@/pages/scolarite/Candidatures'

const listCalls = () =>
  apiMock.get.mock.calls
    .filter(([p]) => p.split('?')[0] === '/admissions/candidatures/')
    .map(([p, opts]) => ({ path: p, params: opts?.params || {} }))
const posts = (predicate) =>
  apiMock.post.mock.calls
    .filter(([p]) => predicate(p))
    .map(([p, body]) => ({ path: p, body }))

const setupRoutes = () => {
  apiController.setRoute('/scolarite/annee-courante/', () => ({
    annee: { id: 1, libelle: '2025-2026' },
  }))
  apiController.setRoute('/formations/ref/formations/', () => [
    { id: 10, intitule: 'L1 Langue des signes' },
  ])
  apiController.setRoute('/scolarite/ref/niveaux/', () => [
    { id: 2, code: 'N1', libelle: 'Niveau 1' },
  ])
  apiController.setRoute('/admissions/candidatures/', () => [
    { id: 5, numero: 'C-005', candidat: 'Awa Koné', ref_formation: 'L1 LSF', niveau: 'N1', statut: 'SOUMISE', statut_libelle: 'Soumise', pieces_validees: 1, pieces_obligatoires: 3, taux_completude: 33 },
    { id: 6, numero: 'C-006', candidat: 'Karim Diop', ref_formation: 'L1 LSF', niveau: 'N1', statut: 'ADMISSIBLE', statut_libelle: 'Admissible', pieces_validees: 3, pieces_obligatoires: 3, taux_completude: 100 },
  ])
  apiController.setRoute(/\/admissions\/candidatures\/\d+\/$/, (path) => {
    const id = Number(path.match(/(\d+)/)[1])
    if (id === 6) {
      return {
        id, numero: 'C-006', candidat: 'Karim Diop', statut: 'ADMISSIBLE',
        statut_libelle: 'Admissible', ref_formation: 'L1 LSF', niveau: 'N1',
        annee_academique: '2025-2026', transitions_possibles: [],
        pieces_validees: 3, pieces_obligatoires: 3, taux_completude: 100,
      }
    }
    return {
      id, numero: 'C-005', candidat: 'Awa Koné', statut: 'SOUMISE',
      statut_libelle: 'Soumise', ref_formation: 'L1 LSF', niveau: 'N1',
      annee_academique: '2025-2026',
      transitions_possibles: ['EN_ATTENTE_DE_VERIFICATION', 'ANNULE'],
      pieces_validees: 1, pieces_obligatoires: 3, taux_completude: 33,
    }
  })
  apiController.setRoute(/\/admissions\/candidatures\/\d+\/pieces\/$/, () => ({
    pieces: [
      { id: 51, type_piece: 'CNI', statut: 'FOURNIE', statut_libelle: 'Fournie', a_fichier: true, obligatoire: true },
      { id: 52, type_piece: 'Diplôme', statut: 'MANQUANTE', statut_libelle: 'Manquante', a_fichier: false, obligatoire: true },
    ],
  }))
  apiController.setRoute('/admissions/candidats/', () => ({ id: 99 }))
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Candidatures />, {
    authUser: me,
    routePattern: '/scolarite/candidatures',
    initialEntries: ['/scolarite/candidatures'],
  })
}
const settle = async (n = 5) => {
  await act(async () => { await flushPromises(n) })
}

const rowOf = (numero) => screen.getByText(numero).closest('tr')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('pages/scolarite/Candidatures — liste et filtres', () => {
  it('charge les candidatures et les affiche avec leur badge de statut', async () => {
    mount()
    expect(await screen.findByText('C-005')).toBeInTheDocument()
    expect(screen.getByText('Awa Koné')).toBeInTheDocument()
    expect(screen.getByText('C-006')).toBeInTheDocument()
    expect(within(rowOf('C-006')).getByText('Admissible')).toBeInTheDocument()
    expect(screen.getByText(/année 2025-2026/i)).toBeInTheDocument()
  })

  it('recherche et filtre par statut en passant les paramètres au service', async () => {
    mount()
    await screen.findByText('C-005')

    fireEvent.change(screen.getByPlaceholderText(/rechercher un numéro/i), { target: { value: 'Koné' } })
    await settle()
    expect(listCalls().at(-1).params).toMatchObject({ q: 'Koné' })

    fireEvent.change(screen.getByDisplayValue('Tous les statuts'), { target: { value: 'SOUMISE' } })
    await settle()
    expect(listCalls().at(-1).params).toMatchObject({ statut: 'SOUMISE' })
  })
})

describe('pages/scolarite/Candidatures — panneau Dossier (écritures)', () => {
  it('applique une transition de statut puis recharge et notifie', async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(within(rowOf('C-005')).getByRole('button', { name: 'Ouvrir' }))

    const panel = await screen.findByText('Pièces justificatives')
    expect(panel).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'En attente de vérification' }))
    await settle()

    const t = posts((p) => p.includes('/transition/'))
    expect(t).toHaveLength(1)
    expect(t[0].path).toBe('/admissions/candidatures/5/transition/')
    expect(t[0].body).toEqual({ statut: 'EN_ATTENTE_DE_VERIFICATION' })
    expect(await screen.findByText(/statut mis à jour/i)).toBeInTheDocument()
  })

  it('valide une pièce fournie (POST verifier) ; le bouton reste désactivé sans fichier', async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(within(rowOf('C-005')).getByRole('button', { name: 'Ouvrir' }))
    await screen.findByText('CNI')

    const pieceRow = screen.getByText('CNI').closest('tr')
    fireEvent.click(within(pieceRow).getByRole('button', { name: 'Valider' }))
    await settle()

    const v = posts((p) => p.includes('/verifier/'))
    expect(v).toHaveLength(1)
    expect(v[0].path).toBe('/admissions/pieces/51/verifier/')
    expect(v[0].body).toEqual({ statut: 'VALIDEE' })

    // La pièce sans fichier (Diplôme) ne peut pas être validée.
    const missingRow = screen.getByText('Diplôme').closest('tr')
    expect(within(missingRow).getByRole('button', { name: 'Valider' })).toBeDisabled()
    expect(within(missingRow).getByRole('button', { name: 'Refuser' })).toBeDisabled()
  })

  it('ouvre une admission pour une candidature admissible', async () => {
    mount()
    await screen.findByText('C-006')
    fireEvent.click(within(rowOf('C-006')).getByRole('button', { name: 'Ouvrir' }))
    await screen.findByText('Suite du parcours')

    fireEvent.click(screen.getByRole('button', { name: /ouvrir une admission/i }))
    await settle()

    const a = posts((p) => p === '/admissions/admissions/')
    expect(a).toHaveLength(1)
    expect(a[0].body).toEqual({ candidature_id: 6 })
    expect(await screen.findByText(/admission ouverte/i)).toBeInTheDocument()
  })

  it('affiche le message serveur si la transition est refusée', async () => {
    apiController.setRoute(/\/transition\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Transition métier impossible.' } } }
    })
    mount()
    await screen.findByText('C-005')
    fireEvent.click(within(rowOf('C-005')).getByRole('button', { name: 'Ouvrir' }))
    await screen.findByText('Pièces justificatives')

    fireEvent.click(screen.getByRole('button', { name: 'En attente de vérification' }))
    await settle()

    expect(await screen.findByText('Transition métier impossible.')).toBeInTheDocument()
  })

  it('dépose un fichier pour une pièce (POST FormData multipart)', async () => {
    mount()
    await screen.findByText('C-005')
    fireEvent.click(within(rowOf('C-005')).getByRole('button', { name: 'Ouvrir' }))
    await screen.findByText('CNI')

    const input = screen
      .getByText('CNI')
      .closest('tr')
      .querySelector('input[type="file"]')
    expect(input).not.toBeNull()
    fireEvent.change(input, {
      target: { files: [new File(['contenu'], 'cni.pdf', { type: 'application/pdf' })] },
    })
    await settle()

    const depots = posts((p) => p.includes('/deposer/'))
    expect(depots).toHaveLength(1)
    expect(depots[0].path).toBe('/admissions/pieces/51/deposer/')
    expect(depots[0].body).toBeInstanceOf(FormData)
    expect(await screen.findByText('CNI déposée')).toBeInTheDocument()
  })
})

describe('pages/scolarite/Candidatures — création', () => {
  it('crée le candidat puis sa candidature avec l’année courante', async () => {
    mount()
    await screen.findByText('C-005')

    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const cardTitle = screen.getByText(
      (_c, el) => el.tagName === 'STRONG' && el.textContent === 'Nouvelle candidature',
    )
    const card = cardTitle.closest('.card')

    const inputs = within(card).getAllByRole('textbox').filter((el) => el.tagName === 'INPUT')
    fireEvent.change(inputs[0], { target: { value: 'Traoré' } }) // nom
    fireEvent.change(inputs[1], { target: { value: 'Mariam' } }) // prénoms
    const combos = within(card).getAllByRole('combobox')
    fireEvent.change(combos[1], { target: { value: '10' } }) // formation
    fireEvent.change(combos[2], { target: { value: '2' } }) // niveau

    const enregistrer = within(card).getByRole('button', { name: 'Enregistrer' })
    await waitFor(() => expect(enregistrer).not.toBeDisabled())
    fireEvent.click(enregistrer)
    await settle()

    const candidats = posts((p) => p === '/admissions/candidats/')
    expect(candidats).toHaveLength(1)
    expect(candidats[0].body).toMatchObject({ nom: 'Traoré', prenom: 'Mariam' })

    const dossiers = posts((p) => p === '/admissions/candidatures/')
    expect(dossiers).toHaveLength(1)
    expect(dossiers[0].body).toMatchObject({
      candidat_id: 99,
      annee_academique_id: 1,
      ref_formation_id: '10',
      niveau_id: '2',
    })
    expect(await screen.findByText('Candidature enregistrée')).toBeInTheDocument()
  })

  it('affiche l’erreur serveur dans le formulaire sans créer de candidature', async () => {
    // On réenregistre la route en échec AVANT les routes de setup : la première
    // correspondance l'emporte dans le mock.
    apiController.reset()
    apiController.setRoute('/admissions/candidats/', () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { nom: 'Ce champ est obligatoire.' } } }
    })
    setupRoutes()
    mount()
    await screen.findByText('C-005')

    fireEvent.click(screen.getByRole('button', { name: /nouvelle candidature/i }))
    const cardTitle = screen.getByText(
      (_c, el) => el.tagName === 'STRONG' && el.textContent === 'Nouvelle candidature',
    )
    const card = cardTitle.closest('.card')

    const inputs = within(card).getAllByRole('textbox').filter((el) => el.tagName === 'INPUT')
    fireEvent.change(inputs[0], { target: { value: 'Traoré' } })
    fireEvent.change(inputs[1], { target: { value: 'Mariam' } })
    const combos = within(card).getAllByRole('combobox')
    fireEvent.change(combos[1], { target: { value: '10' } })
    fireEvent.change(combos[2], { target: { value: '2' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    await settle()

    expect(await within(card).findByText(/nom : ce champ est obligatoire/i)).toBeInTheDocument()
    // Aucune candidature n'a été créée (le candidat a échoué).
    expect(posts((p) => p === '/admissions/candidatures/')).toHaveLength(0)
  })
})
