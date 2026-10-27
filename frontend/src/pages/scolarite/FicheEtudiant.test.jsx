/**
 * Tests de la fiche étudiant (LOT 11) — termine le parcours après inscription :
 * génération/retrait du programme pédagogique, affectation à un groupe et
 * rattachement aux cours (passerelle). La fiche sans inscription validée doit
 * afficher l'alerte d'attente.
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
import FicheEtudiant from '@/pages/scolarite/FicheEtudiant'

const posts = (predicate) =>
  apiMock.post.mock.calls.filter(([p]) => predicate(p)).map(([p, body]) => ({ path: p, body }))

const courante = {
  id: 3, annee_academique_id: 1, ref_formation_id: 10, niveau_id: 2,
  annee_academique: '2025-2026', ref_formation: 'L1 LSF', niveau: 'N1',
  type_inscription_libelle: 'Nouvelle', statut: 'VALIDEE', statut_libelle: 'Validée',
}
const etudiantAvecInscription = {
  id: 5, nom_complet: 'Awa Koné', matricule: 'MAT-001', sexe: 'F',
  date_naissance: '2002-04-01', inscriptions: [courante], inscription_courante: courante,
}

const setupRoutes = (etudiant = etudiantAvecInscription) => {
  apiController.setRoute(/\/scolarite\/etudiants\/\d+\/$/, () => etudiant)
  apiController.setRoute(/\/evenements\/$/, () => [])
  apiController.setRoute(/\/scolarite\/inscriptions\/3\/pedagogie\/$/, () => ({
    recapitulatif: { total_ecues: 1, total_credits: 6, par_semestre: { 'S1': { credits: 6, volume_horaire: 40 } } },
    lignes: [
      {
        id: 70, semestre: 'S1', ue_code: 'UE1', ecue_code: 'ECUE1',
        ecue_intitule: 'Fondements LSF', type_enseignement: 'CM', credits: 6,
        volume_horaire: 40, groupe: null, origine: 'MAQUETTE',
      },
    ],
  }))
  apiController.setRoute(/\/pedagogie\/generer\/$/, () => ({ creees: 4 }))
  apiController.setRoute(/\/scolarite\/inscriptions\/3\/affectations\/$/, () => [
    { id: 1, groupe: 'Groupe A', active: true, date_debut: '2026-01-01', date_fin: null },
  ])
  apiController.setRoute('/scolarite/groupes/effectifs/', () => [
    { id: 7, nom: 'Groupe B', effectif: 10, capacite_max: 30, places_restantes: 20 },
    { id: 8, nom: 'Groupe plein', effectif: 30, capacite_max: 30, places_restantes: 0 },
  ])
  apiController.setRoute('/formations/formations/', () => [{ id: 1, formation: 'Module opérationnel 1' }])
  apiController.setRoute(/\/passerelle\/analyser\/$/, () => ({
    a_creer: [{ ecue: 'ECUE1', module: 'Module opérationnel 1' }], existantes: [], non_rapprochees: [],
  }))
  apiController.setRoute(/\/inscriptions\/3\/passerelle\/$/, () => ({ creees: 3 }))
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<FicheEtudiant />, {
    authUser: me,
    routePattern: '/scolarite/etudiants/:id',
    initialEntries: ['/scolarite/etudiants/5'],
  })
}
const settle = async (n = 5) => {
  await act(async () => { await flushPromises(n) })
}
const section = (titre) => screen.getByText(titre).closest('.card')

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  setupRoutes()
})

describe('FicheEtudiant avec inscription validée — pédagogie', () => {
  it('affiche l’identité, le programme, le groupe actuel et la passerelle', async () => {
    mount()
    expect(await screen.findByRole('heading', { name: 'Awa Koné' })).toBeInTheDocument()
    expect(await screen.findByText('ECUE1 — Fondements LSF')).toBeInTheDocument()
    expect(screen.getByText('Groupe A')).toBeInTheDocument()
    expect(screen.getByText('Programme pédagogique')).toBeInTheDocument()
    expect(screen.getByText('Rattachement aux cours')).toBeInTheDocument()
    expect(screen.getByText(/6 crédits/)).toBeInTheDocument()
  })

  it('génère le programme depuis la maquette (POST) et notifie le nombre d’ajouts', async () => {
    mount()
    await screen.findByText('ECUE1 — Fondements LSF')

    const card = section('Programme pédagogique')
    fireEvent.click(within(card).getByRole('button', { name: /générer depuis la maquette/i }))
    await settle()

    const g = posts((p) => p.includes('/pedagogie/generer/'))
    expect(g).toHaveLength(1)
    expect(g[0].path).toBe('/scolarite/inscriptions/3/pedagogie/generer/')
    expect(await screen.findByText('4 enseignement(s) ajouté(s)')).toBeInTheDocument()
  })

  // Régression §10.9 (corrigé au LOT 45) : le retrait d'une ECUE est une
  // action destructrice qui passe désormais par une ConfirmModal, comme
  // l'archivage d'une ECUE de maquette ou l'annulation d'une admission.
  it('demande confirmation avant de retirer une ECUE ; annuler ne supprime rien (§10.9)', async () => {
    mount()
    await screen.findByText('ECUE1 — Fondements LSF')

    // Aucune modale avant le clic.
    expect(document.querySelector('.modal-overlay')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Retirer' }))

    // La modale s'ouvre et mentionne l'ECUE ; aucun DELETE n'est encore parti.
    expect(document.querySelector('.modal-overlay')).not.toBeNull()
    expect(document.querySelector('.modal-overlay').textContent).toMatch(/Retirer/)
    expect(apiMock.delete).not.toHaveBeenCalled()

    // Annulation : la modale se ferme et aucun DELETE n'est émis.
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await settle()
    expect(document.querySelector('.modal-overlay')).toBeNull()
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it('confirme le retrait d’une ECUE (DELETE) après validation de la modale et notifie (§10.9)', async () => {
    mount()
    await screen.findByText('ECUE1 — Fondements LSF')

    fireEvent.click(screen.getByRole('button', { name: 'Retirer' }))
    expect(await screen.findByText(/du programme pédagogique/)).toBeInTheDocument()
    expect(apiMock.delete).not.toHaveBeenCalled()

    fireEvent.click(screen.getAllByRole('button', { name: 'Retirer' }).pop())
    await settle()

    expect(apiMock.delete).toHaveBeenCalledWith('/scolarite/pedagogie/70/')
    expect(document.querySelector('.modal-overlay')).toBeNull()
    expect(await screen.findByText('ECUE1 retirée')).toBeInTheDocument()
  })
})

describe('FicheEtudiant — groupe pédagogique', () => {
  it('affecte à un groupe disponible ; l’option d’un groupe complet est désactivée', async () => {
    mount()
    await screen.findByText('Groupe A')

    const card = section('Groupe pédagogique')
    const submit = within(card).getByRole('button', { name: 'Affecter' })
    expect(submit).toBeDisabled() // tant qu'aucun groupe n'est choisi

    const select = within(card).getByRole('combobox')
    expect(within(card).getByRole('option', { name: /Groupe plein/ })).toBeDisabled()
    fireEvent.change(select, { target: { value: '7' } })
    expect(submit).toBeEnabled()
    fireEvent.click(submit)
    await settle()

    const a = posts((p) => /\/affectations\/$/.test(p))
    expect(a).toHaveLength(1)
    expect(a[0].path).toBe('/scolarite/inscriptions/3/affectations/')
    expect(a[0].body).toEqual({ groupe_id: '7' })
    expect(await screen.findByText('Affectation enregistrée')).toBeInTheDocument()
  })
})

describe('FicheEtudiant — passerelle de rattachement aux cours', () => {
  it('prévisualise puis synchronise les inscriptions au module opérationnel', async () => {
    mount()
    await screen.findByText('Rattachement aux cours')
    const card = section('Rattachement aux cours')

    fireEvent.change(within(card).getByRole('combobox'), { target: { value: '1' } })
    fireEvent.click(within(card).getByRole('button', { name: 'Prévisualiser' }))
    await settle()
    expect(await within(card).findByText(/1 inscription\(s\) à créer/i)).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: 'Synchroniser' }))
    await settle()
    const synchro = posts((p) => /\/inscriptions\/3\/passerelle\/$/.test(p))
    expect(synchro).toHaveLength(1)
    expect(synchro[0].body).toEqual({ formation_id: '1' })
    expect(await screen.findByText('3 inscription(s) au module créée(s)')).toBeInTheDocument()
  })
})

describe('FicheEtudiant sans inscription validée', () => {
  it('affiche l’alerte et masque les outils pédagogiques', async () => {
    apiController.reset()
    setupRoutes({
      id: 6, nom_complet: 'Mariam Traoré', matricule: 'MAT-009', sexe: 'F',
      inscriptions: [], inscription_courante: null,
    })
    mount()
    expect(await screen.findByRole('heading', { name: 'Mariam Traoré' })).toBeInTheDocument()
    expect(
      await screen.findByText(/aucune inscription validée pour cet étudiant/i),
    ).toBeInTheDocument()
    expect(screen.queryByText('Programme pédagogique')).not.toBeInTheDocument()
    expect(screen.queryByText('Groupe pédagogique')).not.toBeInTheDocument()
  })
})
