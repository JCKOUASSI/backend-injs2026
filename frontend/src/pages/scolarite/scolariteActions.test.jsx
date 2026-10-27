/**
 * Tests des ACTIONS rétablies au LOT 7 (§10.8) — les gestionnaires sont de
 * nouveau câblés dans le JSX ; ce fichier les exerce AU CLIC et vérifie les
 * écritures API (POST/DELETE), le message de succès et le rechargement.
 *
 * Flux couverts :
 *  - Campagnes        : transition de statut (avec/sans window.confirm) ;
 *  - CampagneDetail   : enregistrement d'une note ;
 *  - Equivalences     : application d'une dispense/équivalence (confirm) ;
 *  - MaquetteDetail   : archivage d'une ECUE (confirm, DELETE) ;
 *  - ChargesEnseignants : création d'une affectation pédagogique.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest'
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

import Campagnes from '@/pages/scolarite/Campagnes'
import CampagneDetail from '@/pages/scolarite/CampagneDetail'
import Equivalences from '@/pages/scolarite/Equivalences'
import MaquetteDetail from '@/pages/scolarite/MaquetteDetail'
import ChargesEnseignants from '@/pages/scolarite/ChargesEnseignants'

const admin = () => makeUser('ADMIN', { username: 'admin' })

const mount = (Component, { pattern, url }) => {
  const me = admin()
  apiController.setMe(me)
  return renderWithProviders(<Component />, {
    authUser: me,
    routePattern: pattern,
    initialEntries: [url],
  })
}

const settle = async (n = 5) => {
  await act(async () => {
    await flushPromises(n)
  })
}

const calls = (method, predicate) =>
  apiMock[method].mock.calls.filter(([p]) => predicate(p))
const writes = (method) =>
  apiMock[method].mock.calls.map(([p, body]) => ({ path: p, body }))

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
})
afterEach(() => {
  vi.restoreAllMocks()
})

describe('§10.8 LOT 8 — actions Scolarité au clic (écritures API)', () => {
  it('Campagnes : Planifier (sans confirm) puis Ouvrir (avec confirm) émettent les bonnes transitions', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiController.setRoute('/admissions/campagnes/', () => [
      { id: 1, libelle: 'Camp B', statut: 'BROUILLON', ref_formation_id: 1, annee_academique_id: 1, nb_candidatures: 0 },
      { id: 2, libelle: 'Camp P', statut: 'PLANIFIEE', ref_formation_id: 1, annee_academique_id: 1, nb_candidatures: 0 },
    ])
    mount(Campagnes, { pattern: '/scolarite/campagnes', url: '/scolarite/campagnes' })
    await settle()

    // BROUILLON → PLANIFIEE : pas de confirmation demandée.
    const rowB = screen.getByText('Camp B').closest('tr')
    fireEvent.click(within(rowB).getByRole('button', { name: 'Planifier' }))
    await settle()

    // PLANIFIEE → OUVERTE : confirmation explicite.
    const rowP = screen.getByText('Camp P').closest('tr')
    fireEvent.click(within(rowP).getByRole('button', { name: 'Ouvrir' }))
    await settle()

    const transitions = writes('post').filter((w) => w.path.includes('/transition/'))
    expect(transitions).toHaveLength(2)
    expect(transitions[0].path).toBe('/admissions/campagnes/1/transition/')
    expect(transitions[0].body).toEqual({ statut: 'PLANIFIEE' })
    expect(transitions[1].path).toBe('/admissions/campagnes/2/transition/')
    expect(transitions[1].body).toEqual({ statut: 'OUVERTE' })

    // La confirmation n'est requise que pour l'ouverture (message dédié).
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(confirmSpy.mock.calls[0][0]).toMatch(/ouvrir la campagne aux candidatures/i)
    // Chaque transition réussie recharge la liste.
    expect(calls('get', (p) => p.split('?')[0] === '/admissions/campagnes/').length).toBeGreaterThan(2)
    expect(await screen.findByText(/campagne ouverte/i)).toBeInTheDocument()
  })

  it('CampagneDetail : enregistre une note (POST) puis recharge et notifie', async () => {
    apiController.setRoute(/classement\/$/, () => [])
    apiController.setRoute(/\/admissions\/campagnes\/\d+\/$/, () => ({
      id: 1, libelle: 'Campagne 2026', statut: 'PLANIFIEE',
      epreuves: [{ id: 5, intitule: 'Écrit 1', date: '2026-02-01', verrouillee: false }],
    }))
    apiController.setRoute('/admissions/candidatures/', () => [
      { id: 8, campagne_id: 1, numero: 'C008', candidat: 'Awa Koné' },
      { id: 9, campagne_id: 2, numero: 'C009', candidat: 'Autre campagne' },
    ])
    mount(CampagneDetail, { pattern: '/scolarite/campagnes/:id', url: '/scolarite/campagnes/1' })
    await settle()

    const card = screen.getByText('Saisie des notes').closest('.card')
    const combos = within(card).getAllByRole('combobox')
    fireEvent.change(combos[0], { target: { value: '5' } }) // épreuve
    fireEvent.change(combos[1], { target: { value: '8' } }) // candidature
    fireEvent.change(within(card).getByPlaceholderText('Note /20'), { target: { value: '12.5' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Enregistrer' }))
    await settle()

    const postNotes = writes('post').filter((w) => w.path.includes('/notes/'))
    expect(postNotes).toHaveLength(1)
    expect(postNotes[0].path).toBe('/admissions/epreuves/5/notes/')
    expect(postNotes[0].body).toEqual({ candidature_id: 8, note: '12.5' })
    expect(await screen.findByText('Note enregistrée.')).toBeInTheDocument()
  })

  it('Équivalences : applique une demande validée (confirm, POST) et notifie', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiController.setRoute('/equivalences/demandes/', () => [
      { id: 3, type_demande: 'DISPENSE', matricule: 'A001', ref_formation: 'L1 LSF', decision: '', statut: 'VALIDEE', credits_reconnus: 6 },
    ])
    mount(Equivalences, { pattern: '/scolarite/equivalences', url: '/scolarite/equivalences' })
    await settle()

    fireEvent.click(screen.getByRole('button', { name: 'Appliquer' }))
    await settle()

    const applied = writes('post').filter((w) => w.path.includes('/appliquer/'))
    expect(applied).toHaveLength(1)
    expect(applied[0].path).toBe('/equivalences/demandes/3/appliquer/')
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/effet académique/i))
    expect(await screen.findByText('Dispense/équivalence appliquée.')).toBeInTheDocument()
  })

  it('MaquetteDetail : archive une ECUE (confirm, DELETE ?mode=archive) et recharge', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    apiController.setRoute(/journal\/$/, () => [])
    apiController.setRoute(/\/scolarite\/maquettes\/\d+\/$/, () => ({
      libelle: 'Maquette L1', statut: 'BROUILLON', version: 1, credits_total: 60, volume_horaire_total: 600,
      unites_enseignement: [{
        id: 50, code: 'UE1', intitule: 'Fondements', credits: 6, caractere: 'OB',
        semestre: { id: 1, libelle: 'Semestre 1' },
        ecues: [{ id: 77, code: 'EC77', intitule: 'Introduction', credits: 3, coefficient: 1, volume_total: 20, archive: false }],
      }],
    }))
    mount(MaquetteDetail, { pattern: '/scolarite/maquettes/:id', url: '/scolarite/maquettes/1' })
    await settle()

    fireEvent.click(screen.getByRole('button', { name: 'archiver' }))
    await settle()

    const del = writes('delete')
    expect(del).toHaveLength(1)
    expect(del[0].path).toBe('/scolarite/ecues/77/?mode=archive')
    expect(window.confirm).toHaveBeenCalledWith(expect.stringMatching(/archiver cette ecue/i))
    expect(await screen.findByText('ECUE archivée.')).toBeInTheDocument()
  })

  it('ChargesEnseignants : crée une affectation (POST avec l’année courante) et notifie', async () => {
    apiController.setRoute('/scolarite/annee-courante/', () => ({ id: 9, libelle: '2025-2026' }))
    apiController.setRoute('/enseignants/occupation/', () => ({ occupation: [] }))
    apiController.setRoute('/enseignants/anomalies/', () => ({ anomalies: [] }))
    apiController.setRoute('/scolarite/ref/annees/', () => [{ id: 9, libelle: '2025-2026' }])
    apiController.setRoute('/scolarite/ref/formations/', () => [{ id: 1, intitule: 'L1 LSF' }])
    apiController.setRoute('/scolarite/ref/niveaux/', () => [{ id: 2, code: 'N1' }])
    apiController.setRoute('/scolarite/ref/semestres/', () => [{ id: 3, libelle: 'S1', niveau_id: 2 }])
    apiController.setRoute('/formateurs/list/', () => [{ id: 4, nom: 'Dupont', prenom: 'Jean' }])
    mount(ChargesEnseignants, { pattern: '/scolarite/charges', url: '/scolarite/charges' })
    await settle(7)

    const card = screen.getByText('Nouvelle affectation pédagogique').closest('.card')
    const combos = within(card).getAllByRole('combobox')
    fireEvent.change(combos[0], { target: { value: '4' } }) // enseignant
    fireEvent.change(combos[1], { target: { value: '1' } }) // formation
    fireEvent.change(combos[2], { target: { value: '2' } }) // niveau
    await settle()
    fireEvent.change(combos[3], { target: { value: '3' } }) // semestre (filtré par niveau)
    fireEvent.change(within(card).getByPlaceholderText('Volume (h)'), { target: { value: '12' } })

    const submit = within(card).getByRole('button', { name: /créer l'affectation/i })
    await waitFor(() => expect(submit).not.toBeDisabled())
    fireEvent.click(submit)
    await settle()

    const posted = writes('post').filter((w) => w.path === '/enseignants/affectations/')
    expect(posted).toHaveLength(1)
    expect(posted[0].body).toMatchObject({
      annee_academique_id: 9,
      enseignant_id: 4,
      ref_formation_id: 1,
      niveau_id: 2,
      semestre_id: 3,
      volume_horaire: 12,
    })
    expect(await screen.findByText('Affectation créée.')).toBeInTheDocument()
  })

  it('Campagnes : une transition rejetée affiche l’erreur serveur sans planter', async () => {
    apiController.setRoute('/admissions/campagnes/', () => [
      { id: 1, libelle: 'Camp B', statut: 'BROUILLON', ref_formation_id: 1, annee_academique_id: 1, nb_candidatures: 0 },
    ])
    apiController.setRoute(/\/transition\//, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Règle métier non satisfaite.' } } }
    })
    mount(Campagnes, { pattern: '/scolarite/campagnes', url: '/scolarite/campagnes' })
    await settle()

    fireEvent.click(screen.getByRole('button', { name: 'Planifier' }))
    await settle()

    expect(writes('post').filter((w) => w.path.includes('/transition/'))).toHaveLength(1)
    expect(await screen.findByText('Règle métier non satisfaite.')).toBeInTheDocument()
  })
})
