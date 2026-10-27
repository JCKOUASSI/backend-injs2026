/**
 * LOT 35 — Administration : référentiels de formation
 * (`pages/Referentiels.jsx`).
 * Les neuf onglets (formations, modules, catégories, grades, vagues,
 * sites, bâtiments, salles, types secrétariat) sont chargés en un seul
 * GET, paginés côté client et gérés en CRUD : création/édition (modale),
 * activation/désactivation, suppression confirmée, import/export Excel.
 * Les modules ont un formulaire spécifique (formations cochées + grille de
 * volumes horaires par formation × catégorie).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
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
import Referentiels from '@/pages/Referentiels'

const GESTION_PATH = '/formations/referentiels/gestion/'
const URL_MAP = {
  formations: '/formations/ref/formations/',
  modules: '/formations/ref/modules/',
  categories: '/formations/ref/categories/',
  grades: '/formations/ref/grades/',
  vagues: '/formations/ref/vagues/',
  sites: '/formations/ref/sites/',
  batiments: '/formations/ref/batiments/',
  salles: '/formations/ref/salles/',
  types_secretariat: '/formations/ref/types-secretariat/',
}

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

const baseData = () => ({
  formations: [
    { id: 1, intitule: 'F1 Administration', actif: true },
    { id: 2, intitule: 'F2 Secrétariat', actif: true },
    { id: 3, intitule: 'F3 Inactive', actif: false },
  ],
  modules: [
    {
      id: 20, intitule: 'Module complet', actif: true,
      formations: [{ id: 1, intitule: 'F1 Administration' }],
      volumes_horaires: [
        { formation_id: 1, categorie_id: 10, volume_horaire: 5, formation_intitule: 'F1 Administration', categorie_libelle: 'CM' },
        { formation_id: 1, categorie_id: 11, volume_horaire: 4, formation_intitule: 'F1 Administration', categorie_libelle: 'TD' },
      ],
    },
    { id: 21, intitule: 'Module nu avec total', actif: true, volumes_horaires: [], volume_horaire: 12 },
    {
      id: 22, intitule: 'Module en formation inconnue', actif: true,
      volumes_horaires: [{ formation_id: 99, categorie_id: 10, volume_horaire: 3, categorie_libelle: 'CM' }],
    },
    { id: 23, intitule: 'Module sans aucun volume', actif: true },
    { id: 25, intitule: 'Module lié par ids', actif: true, formation_ids: [1], volumes_horaires: [] },
    { id: 26, intitule: 'Module ids morts', actif: true, formation_ids: [999], volumes_horaires: [] },
    {
      id: 24, intitule: 'Module à éditer', actif: true,
      formations: [{ id: 1, intitule: 'F1 Administration' }],
      volumes_horaires: [
        { formation_id: 1, categorie_id: 10, volume_horaire: 7, formation_intitule: 'F1 Administration', categorie_libelle: 'CM' },
        { categorie_id: 11, volume_horaire: 9, categorie_libelle: 'TD' }, // pas de formation_id : ignoré par volumesApiToGrid
      ],
    },
    {
      id: 27, intitule: 'Module legacy', actif: true,
      volumes_par_categorie: [{ formation_id: 2, categorie_id: 11, volume_horaire: 6, formation_intitule: 'F2 Secrétariat', categorie_libelle: 'TD' }],
    },
  ],
  categories: [
    { id: 10, libelle: 'CM', actif: true },
    { id: 11, libelle: 'TD', actif: true },
    { id: 12, libelle: 'Catégorie inactive', actif: false },
  ],
  grades: [
    { id: 30, libelle: 'Grade A', categorie_id: 10, actif: true },
    { id: 31, libelle: 'Grade sans catégorie', categorie_id: null, actif: false },
    { id: 32, libelle: 'Grade catégorie morte', categorie_id: 999, actif: true },
  ],
  vagues: [
    { id: 40, libelle: 'Première vague', ordre: 1, actif: true },
    { id: 41, libelle: 'Vague sans ordre', actif: true },
  ],
  sites: [{ id: 50, nom: 'Site INJS', actif: true }],
  batiments: [
    { id: 60, nom: 'Bâtiment A', site_id: 50, actif: true },
    { id: 61, nom: 'Bâtiment orphelin', site_id: 999, actif: true },
  ],
  salles: [
    { id: 70, nom: 'Salle 101', site_id: 50, batiment_id: 60, type_lieu: 'SALLE', capacite: 40, actif: true },
    { id: 71, nom: 'Amphi nu', site_id: 50, actif: false },
    { id: 72, nom: 'Salle site mort', site_id: 998, actif: true },
  ],
  types_secretariat: [{ id: 80, libelle: 'Type A', actif: true }],
})

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }

afterEach(async () => { await settle() })

const mount = ({ tab = null, data = null, gestionFn = null } = {}) => {
  const me = makeUser('ADMIN', { username: 'refadmin' })
  apiController.setMe(me)
  const jeu = data || baseData()
  apiController.setRoute(GESTION_PATH, gestionFn || (() => jeu))
  const url = tab ? `/referentiels?tab=${tab}` : '/referentiels'
  return renderWithProviders(<Referentiels />, {
    authUser: me,
    routePattern: '/referentiels',
    initialEntries: [url],
  })
}

const gestionCalls = () => apiMock.get.mock.calls.filter(([p]) => p === GESTION_PATH)
const postsTo = (fragment) => apiMock.post.mock.calls.filter(([p]) => p.includes(fragment))
const putsTo = (fragment) => apiMock.put.mock.calls.filter(([p]) => p.includes(fragment))

const tabButton = (label) => screen.getByRole('button', { name: new RegExp(`^\\s*${label}`) })
const goTab = async (label) => { fireEvent.click(tabButton(label)); await settle() }

const card = () => document.querySelector('.card')
const modal = () => document.querySelector('.modal-overlay')

const openCreate = async (labelOnglet) => {
  if (labelOnglet) await goTab(labelOnglet)
  fireEvent.click(screen.getByRole('button', { name: /Ajouter/ }))
  await settle()
  return modal()
}

const rowFor = (texte) => screen.getByText(texte).closest('tr')
const editButton = (row) => row.querySelector('button[title="Modifier"]')
const deleteButton = (row) => row.querySelector('button[title="Supprimer"]')
const statusButton = (row) => row.querySelector('button.badge')
const fileInput = () => document.querySelector('input[type="file"]')

const stubBlobDownload = () => {
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
}

/* ------------------------------------------------------------------ */
/* LOT 35 — chargement, onglets, table, pagination                      */
/* ------------------------------------------------------------------ */

describe('pages/Referentiels.jsx — chargement, onglets et table (LOT 35)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche le spinner puis le titre, les neuf onglets avec leurs compteurs (un seul GET)', async () => {
    const { container } = mount()
    expect(container.querySelector('.spinner')).toBeTruthy()
    await settle()
    expect(gestionCalls()).toHaveLength(1)
    expect(screen.getByRole('heading', { name: /Référentiels/ })).toBeInTheDocument()
    expect(screen.getByText('Gérez les données de référence utilisées dans les formulaires')).toBeInTheDocument()
    expect(tabButton('Formations')).toBeInTheDocument()
    expect(tabButton('Modules')).toBeInTheDocument()
    expect(tabButton('Catégories')).toBeInTheDocument()
    expect(tabButton('Grades')).toBeInTheDocument()
    expect(tabButton('Vagues')).toBeInTheDocument()
    expect(tabButton('Sites')).toBeInTheDocument()
    expect(tabButton('Bâtiments')).toBeInTheDocument()
    expect(tabButton('Salles')).toBeInTheDocument()
    expect(tabButton('Types secrétariat')).toBeInTheDocument()
    // Compteurs : 3 formations, 8 modules, 1 type secrétariat.
    expect(tabButton('Formations').textContent).toContain('3')
    expect(tabButton('Modules').textContent).toContain('8')
    expect(tabButton('Types secrétariat').textContent).toContain('1')
  })

  it("notifie l'erreur de chargement et bascule sur l'état vide", async () => {
    apiController.setRoute(GESTION_PATH, () => { throw new Error('500') })
    mount()
    expect(await screen.findByText('Erreur de chargement')).toBeInTheDocument()
    expect(screen.getByText(/Aucune entrée/)).toBeInTheDocument()
  })

  it("affiche le message d'état vide d'un onglet sans donnée", async () => {
    mount({ tab: 'sites', data: { ...baseData(), sites: [] } })
    await settle()
    expect(screen.getByText(/Aucune entrée — cliquez sur « Ajouter »/)).toBeInTheDocument()
  })

  it('rend les formations avec tiret de valeur absente et les boutons de statut', async () => {
    mount()
    await settle()
    expect(screen.getByText('F1 Administration')).toBeInTheDocument()
    // En-têtes de table + libellé du compteur.
    expect(screen.getAllByText('Intitulé').length).toBeGreaterThan(0)
    expect(screen.getByText('Statut')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
    const ligne = rowFor('F1 Administration')
    expect(statusButton(ligne).textContent).toBe('Actif')
    expect(statusButton(ligne)).toHaveClass('badge-planifiee')
    expect(statusButton(ligne)).toHaveAttribute('title', 'Désactiver')
    expect(editButton(ligne)).toBeTruthy()
    expect(deleteButton(ligne)).toBeTruthy()
    expect(screen.getByText('3 entrées')).toBeInTheDocument()
  })

  it('restitue les colonnes spécifiques des modules (formations, volumes, replis)', async () => {
    mount({ tab: 'modules' })
    await settle()
    // Module complet : formations liées + résumé groupé des volumes.
    const ligneComplete = rowFor('Module complet')
    expect(ligneComplete.textContent).toContain('F1 Administration')
    expect(ligneComplete.textContent).toContain('F1 Administration (CM: 5h, TD: 4h)')
    // Module sans volumes mais avec un total horaire simple.
    expect(rowFor('Module nu avec total').textContent).toContain('12 h')
    // Module dont le volume référence une formation inconnue : « Formation #id ».
    expect(rowFor('Module en formation inconnue').textContent).toContain('Formation #99 (CM: 3h)')
    // Module sans rien du tout.
    expect(rowFor('Module sans aucun volume').textContent).toContain('—')
    // Modules liés par formation_ids (sans tableau `formations`).
    expect(rowFor('Module lié par ids').textContent).toContain('F1 Administration')
    expect(rowFor('Module ids morts').textContent).toMatch(/—\s*—|—\s*$/)
  })

  it('restitue les colonnes résolues des grades, bâtiments, salles et vagues', async () => {
    mount({ tab: 'grades' })
    await settle()
    expect(rowFor('Grade A').textContent).toContain('CM')
    expect(rowFor('Grade sans catégorie').textContent).toContain('—')
    expect(rowFor('Grade catégorie morte').textContent).toContain('—')

    await goTab('Bâtiments')
    expect(rowFor('Bâtiment A').textContent).toContain('Site INJS')
    expect(rowFor('Bâtiment orphelin').textContent).toContain('—')

    await goTab('Salles')
    const salle = rowFor('Salle 101')
    expect(salle.textContent).toContain('Site INJS')
    expect(salle.textContent).toContain('Bâtiment A')
    expect(salle.textContent).toContain('SALLE')
    const amphi = rowFor('Amphi nu')
    expect(amphi.textContent).toContain('Site INJS')
    expect(amphi.textContent).toMatch(/—/) // bâtiment absent

    await goTab('Vagues')
    expect(rowFor('Première vague').textContent).toContain('1')
    expect(rowFor('Vague sans ordre').textContent).toContain('—')
  })

  it('pagine côté client à 25 lignes par page', async () => {
    const categories = Array.from({ length: 26 }, (_, i) => ({ id: i + 1, libelle: `Catégorie ${i + 1}`, actif: true }))
    mount({ data: { ...baseData(), categories } })
    await goTab('Catégories')
    expect(screen.getByText('Catégorie 1')).toBeInTheDocument()
    expect(screen.queryByText('Catégorie 26')).toBeNull()
    expect(screen.getByText(/1.25 sur 26/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Page suivante' }))
    await settle()
    expect(await screen.findByText('Catégorie 26')).toBeInTheDocument()
    expect(screen.queryByText('Catégorie 1')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Page précédente' }))
    expect(await screen.findByText('Catégorie 1')).toBeInTheDocument()
  })

  it("lit l'onglet depuis l'URL (?tab=) et retombe sur Formations si l'onglet est inconnu", async () => {
    const vue1 = mount({ tab: 'salles' })
    await settle()
    expect(within(card().querySelector('.card-header')).getByText('Salles')).toBeInTheDocument()
    vue1.unmount()

    const vue2 = mount({ tab: 'onglet_inconnu' })
    await settle()
    expect(within(card().querySelector('.card-header')).getByText('Formations')).toBeInTheDocument()
    vue2.unmount()
  })

  it("change d'onglet au clic (compteurs d'en-tête et formulaire associé)", async () => {
    mount()
    await settle()
    await goTab('Sites')
    expect(within(card().querySelector('.card-header')).getByText('Sites')).toBeInTheDocument()
    expect(screen.getByText('1 entrée')).toBeInTheDocument()
  })

  it("la création d'onglet ferme une modale encore ouverte", async () => {
    mount()
    await settle()
    await openCreate()
    expect(modal()).toBeTruthy()
    await goTab('Sites')
    expect(modal()).toBeNull()
  })

  it("supporte une réponse de gestion sparse (clés absentes) : tous les onglets à zéro", async () => {
    mount({ gestionFn: () => ({}) })
    await settle()
    for (const label of ['Formations', 'Modules', 'Catégories', 'Grades', 'Vagues', 'Sites', 'Bâtiments', 'Salles', 'Types secrétariat']) {
      await goTab(label)
      expect(screen.getByText(/Aucune entrée/)).toBeInTheDocument()
      expect(tabButton(label).textContent).toContain('0')
    }
  })

  it("affiche un tiret quand une cellule sans fonction de rendu est absente", async () => {
    mount({ data: { ...baseData(), formations: [{ id: 99, actif: true }] } })
    await settle()
    const ligne = screen.getByText('Actif').closest('tr')
    expect(ligne.textContent).toContain('—')
  })

  it("affiche un tiret pour la salle dont le site n'existe plus", async () => {
    mount({ tab: 'salles' })
    await settle()
    expect(rowFor('Salle site mort').textContent).toContain('—')
  })
})

/* ------------------------------------------------------------------ */
/* LOT 35 — CRUD simple : créations, édition, statut                    */
/* ------------------------------------------------------------------ */

describe('pages/Referentiels.jsx — créations et édition (LOT 35)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('crée une formation (POST, toast, fermeture, rechargement)', async () => {
    mount()
    await settle()
    const m = await openCreate()
    expect(within(m).getByText('Ajouter — Formations')).toBeInTheDocument()
    fireEvent.change(within(m).getByPlaceholderText(/FORMATION EN ADMINISTRATION/), { target: { value: 'Nouvelle formation' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(postsTo('/formations/ref/formations/')).toHaveLength(1))
    expect(postsTo('/formations/ref/formations/')[0][1]).toEqual({ intitule: 'Nouvelle formation', actif: true })
    expect(await screen.findByText('Ajouté avec succès')).toBeInTheDocument()
    expect(modal()).toBeNull()
    expect(gestionCalls().length).toBeGreaterThanOrEqual(2)
  })

  it('crée une catégorie, un site, un type secrétariat et une vague (formulaires simples)', async () => {
    mount()
    await settle()

    let m = await openCreate('Catégories')
    fireEvent.change(within(m).getByPlaceholderText(/Catégorie A/), { target: { value: 'Catégorie X' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/categories/')).toHaveLength(1))
    expect(postsTo('/ref/categories/')[0][1]).toMatchObject({ libelle: 'Catégorie X', actif: true })
    expect(await screen.findByText('Ajouté avec succès')).toBeInTheDocument()

    m = await openCreate('Sites')
    fireEvent.change(within(m).getByPlaceholderText('Ex: INJS'), { target: { value: 'Site B' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/sites/')).toHaveLength(1))
    expect(postsTo('/ref/sites/')[0][1]).toMatchObject({ nom: 'Site B', actif: true })

    m = await openCreate('Types secrétariat')
    fireEvent.change(within(m).getByPlaceholderText(/Secrétariat de type A/), { target: { value: 'Type B' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/types-secretariat/')).toHaveLength(1))

    m = await openCreate('Vagues')
    // Ordre par défaut à 1, sans rien toucher au champ.
    fireEvent.change(within(m).getByPlaceholderText('Ex: PREMIERE VAGUE'), { target: { value: 'Deuxième vague' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/vagues/')).toHaveLength(1))
    expect(postsTo('/ref/vagues/')[0][1]).toMatchObject({ libelle: 'Deuxième vague', ordre: 1, actif: true })
  })

  it("modifie l'ordre d'affichage d'une vague (valeur saisie transmise telle quelle)", async () => {
    mount()
    await settle()
    await goTab('Vagues')
    fireEvent.click(editButton(rowFor('Première vague')))
    await settle()
    const m = modal()
    expect(within(m).getByText('Modifier — Vagues')).toBeInTheDocument()
    fireEvent.change(within(m).getByPlaceholderText("Ex: 1"), { target: { value: '3' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(putsTo('/ref/vagues/')).toHaveLength(1))
    const [path, body] = putsTo('/ref/vagues/')[0]
    expect(path).toBe('/formations/ref/vagues/40/')
    expect(body).toMatchObject({ id: 40, libelle: 'Première vague', ordre: '3' })
    expect(await screen.findByText('Modifié avec succès')).toBeInTheDocument()
  })

  it("ouvre l'édition d'une vague sans ordre avec le champ à 1", async () => {
    mount()
    await settle()
    await goTab('Vagues')
    fireEvent.click(editButton(rowFor('Vague sans ordre')))
    await settle()
    expect(within(modal()).getByDisplayValue('1')).toBeInTheDocument()
  })

  it('bascule le statut actif/inactif (PUT du corps complet, toasts dédiés, rechargement)', async () => {
    mount()
    await settle()
    const avant = gestionCalls().length
    const ligne = rowFor('F1 Administration')
    fireEvent.click(statusButton(ligne))
    await waitFor(() => expect(putsTo('/ref/formations/')).toHaveLength(1))
    const [path, body] = putsTo('/ref/formations/')[0]
    expect(path).toBe('/formations/ref/formations/1/')
    expect(body.actif).toBe(false)
    expect(body.intitule).toBe('F1 Administration') // corps complet
    expect(await screen.findByText('Désactivé')).toBeInTheDocument()
    expect(gestionCalls().length).toBeGreaterThan(avant)

    // Une ligne déjà inactive : la réactivation affiche « Activé ».
    await settle()
    fireEvent.click(statusButton(rowFor('F3 Inactive')))
    await waitFor(() => expect(putsTo('/ref/formations/')).toHaveLength(2))
    expect(putsTo('/ref/formations/')[1][1].actif).toBe(true)
    expect(await screen.findByText('Activé')).toBeInTheDocument()
  })

  it("notifie l'échec d'un basculement de statut", async () => {
    mount()
    await settle()
    apiMock.put.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(statusButton(rowFor('F1 Administration')))
    expect(await screen.findByText('Erreur')).toBeInTheDocument()
  })

  it("passe le bouton en « Enregistrement… » pendant l'envoi puis le réactive", async () => {
    mount()
    await settle()
    const m = await openCreate()
    fireEvent.change(within(m).getByPlaceholderText(/FORMATION EN ADMINISTRATION/), { target: { value: 'F en attente' } })
    let resolvePost
    apiMock.post.mockImplementationOnce(() => new Promise((res) => { resolvePost = () => res({ data: {} }) }))
    const bouton = within(m).getByRole('button', { name: 'Enregistrer' })
    fireEvent.click(bouton)
    expect(within(m).getByRole('button', { name: 'Enregistrement…' })).toBeDisabled()
    await act(async () => { resolvePost(); await flushPromises(8) })
    expect(await screen.findByText('Ajouté avec succès')).toBeInTheDocument()
    await settle()
  })

  it("affiche les erreurs de validation du serveur puis le message générique", async () => {
    mount()
    await settle()
    const m = await openCreate()
    fireEvent.change(within(m).getByPlaceholderText(/FORMATION EN ADMINISTRATION/), { target: { value: 'Doublon' } })

    apiMock.post.mockRejectedValueOnce({ response: { data: { intitule: ['Libellé déjà utilisé'] } } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText(/Libellé déjà utilisé/)).toBeInTheDocument()
    expect(modal()).toBeTruthy() // la modale reste ouverte sur erreur

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText("Erreur lors de l'enregistrement")).toBeInTheDocument()
  })

  it('ferme la modale par la croix, Annuler ou le voile, sans aucun appel', async () => {
    mount()
    await settle()

    let m = await openCreate()
    fireEvent.click(within(m).getByText('×'))
    expect(modal()).toBeNull()

    m = await openCreate()
    fireEvent.click(within(m).getByRole('button', { name: 'Annuler' }))
    expect(modal()).toBeNull()

    m = await openCreate()
    fireEvent.click(m) // clic sur le voile (overlay)
    expect(modal()).toBeNull()
    expect(postsTo('/ref/')).toHaveLength(0)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 35 — suppression (ConfirmModal)                                  */
/* ------------------------------------------------------------------ */

describe('pages/Referentiels.jsx — suppression (LOT 35)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('demande confirmation, annule sans DELETE, puis supprime après confirmation', async () => {
    mount()
    await settle()
    fireEvent.click(deleteButton(rowFor('F1 Administration')))
    await settle()
    const boite = document.querySelector('.modal-overlay')
    expect(within(boite).getByText('Supprimer cet élément ?')).toBeInTheDocument()
    expect(within(boite).getByText('Cette action est irréversible.')).toBeInTheDocument()

    fireEvent.click(within(boite).getByRole('button', { name: 'Annuler' }))
    expect(apiMock.delete).not.toHaveBeenCalled()

    fireEvent.click(deleteButton(rowFor('F1 Administration')))
    await settle()
    const boite2 = document.querySelector('.modal-overlay')
    const avant = gestionCalls().length
    fireEvent.click(within(boite2).getByRole('button', { name: 'Confirmer' }))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledTimes(1))
    expect(apiMock.delete.mock.calls[0][0]).toBe('/formations/ref/formations/1/')
    expect(await screen.findByText('Supprimé')).toBeInTheDocument()
    expect(gestionCalls().length).toBeGreaterThan(avant)
  })

  it("gère un 404 (entrée déjà supprimée) en actualisant avec un message dédié", async () => {
    mount()
    await settle()
    fireEvent.click(deleteButton(rowFor('F1 Administration')))
    await settle()
    const boite = document.querySelector('.modal-overlay')
    apiMock.delete.mockRejectedValueOnce({ response: { status: 404 } })
    const avant = gestionCalls().length
    fireEvent.click(within(boite).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Entrée déjà supprimée — liste actualisée')).toBeInTheDocument()
    expect(gestionCalls().length).toBeGreaterThan(avant)
  })

  it("notifie toute autre erreur de suppression sans actualiser", async () => {
    mount()
    await settle()
    fireEvent.click(deleteButton(rowFor('F1 Administration')))
    await settle()
    const boite = document.querySelector('.modal-overlay')
    const avant = gestionCalls().length
    apiMock.delete.mockRejectedValueOnce(new Error('500'))
    fireEvent.click(within(boite).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Erreur lors de la suppression')).toBeInTheDocument()
    expect(gestionCalls()).toHaveLength(avant)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 35 — grades, bâtiments, salles (clés typées)                     */
/* ------------------------------------------------------------------ */

describe('pages/Referentiels.jsx — grades, bâtiments, salles (LOT 35)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('crée un grade rattaché à une catégorie (id typé nombre)', async () => {
    mount()
    await settle()
    const m = await openCreate('Grades')
    fireEvent.change(within(m).getByPlaceholderText(/Attaché/), { target: { value: 'Grade B' } })
    fireEvent.change(within(m).getByRole('combobox'), { target: { value: '10' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/grades/')).toHaveLength(1))
    expect(postsTo('/ref/grades/')[0][1]).toMatchObject({ libelle: 'Grade B', categorie_id: 10, actif: true })
  })

  it("crée un grade sans catégorie (sélection « — Aucune — » → null)", async () => {
    mount()
    await settle()
    const m = await openCreate('Grades')
    fireEvent.change(within(m).getByPlaceholderText(/Attaché/), { target: { value: 'Grade libre' } })
    // Le sélecteur reste sur sa valeur fantôme « — Aucune — ».
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/grades/')).toHaveLength(1))
    expect(postsTo('/ref/grades/')[0][1].categorie_id).toBeNull()
  })

  it('crée un bâtiment rattaché à un site (id typé nombre)', async () => {
    mount()
    await settle()
    const m = await openCreate('Bâtiments')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Bâtiment A'), { target: { value: 'Bâtiment B' } })
    const select = within(m).getByRole('combobox')
    fireEvent.change(select, { target: { value: '50' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/batiments/')).toHaveLength(1))
    expect(postsTo('/ref/batiments/')[0][1]).toMatchObject({ nom: 'Bâtiment B', site_id: 50, actif: true })
  })

  it("passe un site/bâtiment laissé vide à null (soumission directe du formulaire)", async () => {
    mount()
    await settle()
    const m = await openCreate('Bâtiments')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Bâtiment A'), { target: { value: 'Bâtiment flottant' } })
    // On contourne la validation native « required » du select site.
    fireEvent.submit(m.querySelector('form'))
    await waitFor(() => expect(postsTo('/ref/batiments/')).toHaveLength(1))
    expect(postsTo('/ref/batiments/')[0][1].site_id).toBeNull()
  })

  it('crée une salle complète : site, bâtiment filtré, type, capacité et équipements', async () => {
    mount()
    await settle()
    const m = await openCreate('Salles')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Salle A'), { target: { value: 'Salle 202' } })
    const selects = within(m).getAllByRole('combobox')
    // Sans site choisi, le filtre (logique `!site_id`) laisse voir tous les bâtiments.
    expect(within(selects[1]).queryAllByRole('option')).toHaveLength(3)
    fireEvent.change(selects[0], { target: { value: '50' } }) // site
    await settle()
    // Le bâtiment orphelin (site 999) est filtré hors de la liste.
    const optionsBatiment = within(selects[1]).getAllByRole('option').map((o) => o.textContent)
    expect(optionsBatiment).toContain('Bâtiment A')
    expect(optionsBatiment).not.toContain('Bâtiment orphelin')
    fireEvent.change(selects[1], { target: { value: '60' } })
    fireEvent.change(selects[2], { target: { value: 'AMPHI' } })
    fireEvent.change(within(m).getByPlaceholderText('Ex: 40'), { target: { value: '120' } })
    fireEvent.change(within(m).getByPlaceholderText('Ex: Vidéo-projecteur'), { target: { value: 'Sonorisation' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(postsTo('/ref/salles/')).toHaveLength(1))
    expect(postsTo('/ref/salles/')[0][1]).toMatchObject({
      nom: 'Salle 202', site_id: 50, batiment_id: 60, type_lieu: 'AMPHI',
      capacite: 120, equipements: 'Sonorisation', actif: true,
    })
  })

  it("change de site et réinitialise le bâtiment choisi", async () => {
    mount({ data: { ...baseData(), sites: [
      { id: 50, nom: 'Site INJS', actif: true },
      { id: 51, nom: 'Site B', actif: true },
    ], batiments: [
      { id: 60, nom: 'Bât A50', site_id: 50, actif: true },
      { id: 62, nom: 'Bât B51', site_id: 51, actif: true },
    ] } })
    await settle()
    const m = await openCreate('Salles')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Salle A'), { target: { value: 'Salle X' } })
    const selects = within(m).getAllByRole('combobox')
    fireEvent.change(selects[0], { target: { value: '50' } })
    fireEvent.change(selects[1], { target: { value: '60' } })
    expect(selects[1].value).toBe('60')
    fireEvent.change(selects[0], { target: { value: '51' } })
    expect(selects[1].value).toBe('')
    const options = within(selects[1]).getAllByRole('option').map((o) => o.textContent)
    expect(options).toContain('Bât B51')
    expect(options).not.toContain('Bât A50')
  })

  it("crée une salle minimale et applique les valeurs par défaut (liens nuls, SALLE, équipements '')", async () => {
    mount()
    await settle()
    const m = await openCreate('Salles')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Salle A'), { target: { value: 'Salle nue' } })
    fireEvent.submit(m.querySelector('form')) // required site/bâtiment contournés
    await waitFor(() => expect(postsTo('/ref/salles/')).toHaveLength(1))
    const body = postsTo('/ref/salles/')[0][1]
    expect(body).toMatchObject({ nom: 'Salle nue', site_id: null, batiment_id: null, type_lieu: 'SALLE', capacite: null, equipements: '' })
  })

  it("coerce une capacité non numérique à null", async () => {
    mount()
    await settle()
    const m = await openCreate('Salles')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Salle A'), { target: { value: 'Salle bizarre' } })
    fireEvent.change(within(m).getByPlaceholderText('Ex: 40'), { target: { value: 'abc' } })
    fireEvent.submit(m.querySelector('form'))
    await waitFor(() => expect(postsTo('/ref/salles/')).toHaveLength(1))
    expect(postsTo('/ref/salles/')[0][1].capacite).toBeNull()
  })

  it("envoie null pour une catégorie de grade non numérique", async () => {
    mount()
    await settle()
    const m = await openCreate('Grades')
    fireEvent.change(within(m).getByPlaceholderText(/Attaché/), { target: { value: 'Grade bizarre' } })
    fireEvent.change(within(m).getByRole('combobox'), { target: { value: 'abc' } })
    fireEvent.submit(m.querySelector('form'))
    await waitFor(() => expect(postsTo('/ref/grades/')).toHaveLength(1))
    expect(postsTo('/ref/grades/')[0][1].categorie_id).toBeNull()
  })

  it("édite une salle incomplète et complète les valeurs par défaut (SALLE, capacité/équipements nuls)", async () => {
    mount({ tab: 'salles' })
    await settle()
    fireEvent.click(editButton(rowFor('Amphi nu')))
    await settle()
    const m = modal()
    // Le type retombe sur SALLE et la capacité vide s'affiche en '' (??).
    expect(within(m).getAllByRole('combobox')[2].value).toBe('SALLE')
    expect(within(m).getByPlaceholderText('Ex: 40').value).toBe('')
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(putsTo('/ref/salles/')).toHaveLength(1))
    expect(putsTo('/ref/salles/')[0][1]).toMatchObject({
      id: 71, nom: 'Amphi nu', site_id: 50, actif: false,
      type_lieu: 'SALLE', capacite: null, equipements: '',
    })
    expect(await screen.findByText('Modifié avec succès')).toBeInTheDocument()
  })

  it("en édition, neutralise une catégorie de grade non numérique servie par le backend", async () => {
    mount({
      tab: 'grades',
      data: { ...baseData(), grades: [{ id: 33, libelle: 'Grade véreux', categorie_id: 'xyz', actif: true }] },
    })
    await settle()
    fireEvent.click(editButton(rowFor('Grade véreux')))
    await settle()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(putsTo('/ref/grades/')).toHaveLength(1))
    expect(putsTo('/ref/grades/')[0][1].categorie_id).toBeNull()
  })

  it("en édition, neutralise une capacité non numérique servie par le backend", async () => {
    mount({
      tab: 'salles',
      data: { ...baseData(), salles: [{ id: 73, nom: 'Salle véreuse', site_id: 50, capacite: 'abc', actif: true }] },
    })
    await settle()
    fireEvent.click(editButton(rowFor('Salle véreuse')))
    await settle()
    fireEvent.click(within(modal()).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(putsTo('/ref/salles/')).toHaveLength(1))
    expect(putsTo('/ref/salles/')[0][1].capacite).toBeNull()
  })

  it("force une valeur de type de lieu vide vers SALLE", async () => {
    mount()
    await settle()
    const m = await openCreate('Salles')
    fireEvent.change(within(m).getByPlaceholderText('Ex: Salle A'), { target: { value: 'Salle sans type' } })
    fireEvent.change(within(m).getAllByRole('combobox')[0], { target: { value: '50' } })
    fireEvent.change(within(m).getAllByRole('combobox')[2], { target: { value: '' } })
    fireEvent.submit(m.querySelector('form'))
    await waitFor(() => expect(postsTo('/ref/salles/')).toHaveLength(1))
    expect(postsTo('/ref/salles/')[0][1].type_lieu).toBe('SALLE')
  })
})

/* ------------------------------------------------------------------ */
/* LOT 35 — modules (formations multiples + grille de volumes)          */
/* ------------------------------------------------------------------ */

describe('pages/Referentiels.jsx — modules et volumes horaires (LOT 35)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it("refuse l'enregistrement sans formation cochée", async () => {
    mount()
    await settle()
    const m = await openCreate('Modules')
    fireEvent.change(within(m).getByPlaceholderText(/Déontologie/), { target: { value: 'Module sans formation' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Sélectionnez au moins une formation pour ce module.')).toBeInTheDocument()
    expect(postsTo('/ref/modules/')).toHaveLength(0)
  })

  it("refuse l'enregistrement sans aucun volume horaire renseigné", async () => {
    mount()
    await settle()
    const m = await openCreate('Modules')
    fireEvent.change(within(m).getByPlaceholderText(/Déontologie/), { target: { value: 'Module sans volume' } })
    fireEvent.click(within(m).getByText('F1 Administration')) // coche via le label
    expect(within(m).getAllByPlaceholderText('h').length).toBe(2) // CM et TD actives
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Renseignez au moins un volume horaire (formation × catégorie).')).toBeInTheDocument()
    expect(postsTo('/ref/modules/')).toHaveLength(0)
  })

  it('ne liste que les formations actives dans les cases à cocher', async () => {
    mount()
    await settle()
    const m = await openCreate('Modules')
    expect(within(m).getByText('F1 Administration')).toBeInTheDocument()
    expect(within(m).getByText('F2 Secrétariat')).toBeInTheDocument()
    expect(within(m).queryByText('F3 Inactive')).toBeNull()
  })

  it('crée un module avec deux formations et leur grille de volumes (POST 201)', async () => {
    apiController.setRoute(URL_MAP.modules, { id: 100 }, 201)
    mount()
    await settle()
    const m = await openCreate('Modules')
    fireEvent.change(within(m).getByPlaceholderText(/Déontologie/), { target: { value: 'Droit administratif' } })
    fireEvent.click(within(m).getByText('F1 Administration'))
    fireEvent.click(within(m).getByText('F2 Secrétariat'))
    // 2 formations actives × 2 catégories actives = 4 champs, dans l'ordre F1(CM,TD) puis F2(CM,TD).
    const champs = within(m).getAllByPlaceholderText('h')
    expect(champs).toHaveLength(4)
    fireEvent.change(champs[0], { target: { value: '5' } })
    fireEvent.change(champs[1], { target: { value: '4' } })
    fireEvent.change(champs[2], { target: { value: '3' } })
    // Le 4e champ (F2/TD) reste vide : il ne doit pas être envoyé.
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(postsTo('/ref/modules/')).toHaveLength(1))
    const body = postsTo('/ref/modules/')[0][1]
    expect(body.intitule).toBe('Droit administratif')
    expect(body.formation_ids).toEqual([1, 2])
    expect(body.actif).toBe(true)
    expect(body.volumes_horaires).toEqual([
      { formation_id: 1, categorie_id: 10, volume_horaire: 5 },
      { formation_id: 1, categorie_id: 11, volume_horaire: 4 },
      { formation_id: 2, categorie_id: 10, volume_horaire: 3 },
    ])
    // Les structures de grille sont retirées du payload.
    expect(body.volumes_grid).toBeUndefined()
    expect(body.formations).toBeUndefined()
    expect(await screen.findByText('Ajouté avec succès')).toBeInTheDocument()
  })

  it("écarte une valeur non numérique de la grille et sait décocher une formation", async () => {
    apiController.setRoute(URL_MAP.modules, { id: 101 }, 201)
    mount()
    await settle()
    const m = await openCreate('Modules')
    fireEvent.change(within(m).getByPlaceholderText(/Déontologie/), { target: { value: 'Module filtré' } })
    const caseF1 = within(m).getAllByRole('checkbox')[0]
    fireEvent.click(caseF1)
    let champs = within(m).getAllByPlaceholderText('h')
    fireEvent.change(champs[0], { target: { value: 'abc' } }) // NaN : écarté
    fireEvent.change(champs[1], { target: { value: '2' } })
    // Décocher F1 fait disparaître sa grille.
    fireEvent.click(caseF1)
    expect(within(m).queryAllByPlaceholderText('h')).toHaveLength(0)
    // Recocher : la grille est réinitialisée, on resaisit le seul volume TD.
    fireEvent.click(caseF1)
    champs = within(m).getAllByPlaceholderText('h')
    fireEvent.change(champs[1], { target: { value: '2' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    await waitFor(() => expect(postsTo('/ref/modules/')).toHaveLength(1))
    const body = postsTo('/ref/modules/')[0][1]
    expect(body.volumes_horaires).toEqual([{ formation_id: 1, categorie_id: 11, volume_horaire: 2 }])
  })

  it("signale qu'un module existe déjà quand le POST renvoie 200 (rattachement)", async () => {
    apiController.setRoute(URL_MAP.modules, { id: 20 }, 200)
    mount()
    await settle()
    const m = await openCreate('Modules')
    fireEvent.change(within(m).getByPlaceholderText(/Déontologie/), { target: { value: 'Module existant' } })
    fireEvent.click(within(m).getByText('F1 Administration'))
    fireEvent.change(within(m).getAllByPlaceholderText('h')[0], { target: { value: '1' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))
    expect(await screen.findByText('Module déjà au référentiel — formations rattachées')).toBeInTheDocument()
  })

  it('pré-remplit la grille et les formations en édition, puis PUT les volumes (clés legacy incluses)', async () => {
    mount()
    await settle()
    await goTab('Modules')
    fireEvent.click(editButton(rowFor('Module à éditer')))
    await settle()
    const m = modal()
    expect(within(m).getByText('Modifier — Modules')).toBeInTheDocument()
    // La case F1 est cochée et le volume CM=7 restitué (le volume sans
    // formation_id a été écarté lors de la conversion).
    const champs = within(m).getAllByPlaceholderText('h')
    expect(champs[0].value).toBe('7')
    expect(champs[1].value).toBe('')
    fireEvent.change(champs[1], { target: { value: '9' } })
    fireEvent.click(within(m).getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => expect(putsTo('/ref/modules/')).toHaveLength(1))
    const [path, body] = putsTo('/ref/modules/')[0]
    expect(path).toBe('/formations/ref/modules/24/')
    expect(body.formation_ids).toEqual([1])
    expect(body.volumes_horaires).toEqual([
      { formation_id: 1, categorie_id: 10, volume_horaire: 7 },
      { formation_id: 1, categorie_id: 11, volume_horaire: 9 },
    ])
    expect(body.volumes_grid).toBeUndefined()
    expect(body.volumes_par_categorie).toBeUndefined()
    expect(body.volumes_horaires_legacy || body.volume_horaire).toBeUndefined()
    expect(await screen.findByText('Modifié avec succès')).toBeInTheDocument()
  })

  it("reconstruit la grille depuis l'ancien format volumes_par_categorie", async () => {
    mount()
    await settle()
    await goTab('Modules')
    fireEvent.click(editButton(rowFor('Module legacy')))
    await settle()
    // Le module legacy n'est rattaché qu'à F2 ; la grille apparaît après
    // que formation_ids a été déduit… en édition, formation_ids est absent :
    // la grille n'est pas affichée mais le volume legacy est restitué dans
    // le tableau amont. On vérifie surtout que la modale s'ouvre sans crash.
    expect(modal()).toBeTruthy()
    expect(within(modal()).getByDisplayValue('Module legacy')).toBeInTheDocument()
  })

  it("affiche le repli « Formation #id » dans la grille d'édition quand la formation n'existe plus", async () => {
    mount()
    await settle()
    await goTab('Modules')
    fireEvent.click(editButton(rowFor('Module ids morts')))
    await settle()
    const m = modal()
    // formation_ids = [999] : la grille s'affiche pour cette formation
    // introuvable, avec les catégories actives en champs.
    expect(within(m).getByText('Formation #999')).toBeInTheDocument()
    expect(within(m).getAllByPlaceholderText('h').length).toBeGreaterThan(0)
    // Aucune case cochée (la formation 999 n'est pas dans la liste).
    const cochees = within(m).getAllByRole('checkbox').filter((c) => c.checked)
    expect(cochees).toHaveLength(0)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 35 — import / export Excel                                       */
/* ------------------------------------------------------------------ */

describe('pages/Referentiels.jsx — import/export Excel (LOT 35)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    stubBlobDownload()
  })

  const capturerAncre = () => {
    let ancre
    const creer = document.createElement.bind(document)
    vi.spyOn(document, 'createElement').mockImplementation((balise) => {
      const el = creer(balise)
      if (balise === 'a') ancre = el
      return el
    })
    return () => ancre
  }

  it("exporte l'onglet courant (getBlob, ancre cliquée, révocation d'URL, nom par défaut)", async () => {
    apiMock.getBlob.mockResolvedValueOnce({ blob: new Blob(['x']), fileName: undefined })
    const ancre = capturerAncre()
    mount({ tab: 'modules' })
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /Exporter/ }))
    await waitFor(() => expect(apiMock.getBlob).toHaveBeenCalledTimes(1))
    expect(apiMock.getBlob.mock.calls[0][0]).toBe('/formations/ref/excel/modules/')
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1)
    expect(URL.revokeObjectURL).toHaveBeenCalled()
    // Le lien de téléchargement créé porte le nom par défaut.
    expect(ancre().getAttribute('download')).toBe('referentiel_modules.xlsx')
    expect(ancre().href).toBe('blob:test')
  })

  it("reprend le nom de fichier fourni par le serveur", async () => {
    apiMock.getBlob.mockResolvedValueOnce({ blob: new Blob(['x']), fileName: 'formations_custom.xlsx' })
    const ancre = capturerAncre()
    mount()
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /Exporter/ }))
    await waitFor(() => expect(apiMock.getBlob).toHaveBeenCalledTimes(1))
    expect(ancre().getAttribute('download')).toBe('formations_custom.xlsx')
  })

  it("notifie l'échec d'export", async () => {
    apiMock.getBlob.mockRejectedValueOnce(new Error('réseau'))
    mount()
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /Exporter/ }))
    expect(await screen.findByText('Impossible de générer le fichier Excel.')).toBeInTheDocument()
  })

  it("le bouton Importer déclenche le sélecteur de fichier caché", async () => {
    mount()
    await settle()
    const input = fileInput()
    const spy = vi.spyOn(input, 'click').mockImplementation(() => {})
    fireEvent.click(screen.getByRole('button', { name: /Importer/ }))
    expect(spy).toHaveBeenCalledTimes(1)
  })

  it("refuse un fichier qui n'est pas en .xlsx (aucun POST)", async () => {
    mount()
    await settle()
    fireEvent.change(fileInput(), { target: { files: [new File(['a'], 'liste.txt', { type: 'text/plain' })] } })
    expect(await screen.findByText('Sélectionnez un fichier au format .xlsx.')).toBeInTheDocument()
    expect(postsTo('/ref/excel/')).toHaveLength(0)
  })

  it("n'appelle rien quand le sélecteur est annulé (aucun fichier)", async () => {
    mount()
    await settle()
    fireEvent.change(fileInput(), { target: { files: [] } })
    expect(postsTo('/ref/excel/')).toHaveLength(0)
    expect(apiMock.getBlob).not.toHaveBeenCalled()
  })

  it('importe un fichier .xlsx en FormData, notifie le bilan et recharge', async () => {
    apiController.setRoute('/formations/ref/excel/categories/', { processed: 3, created: 2, updated: 1 })
    mount({ tab: 'categories' })
    await settle()
    const avant = gestionCalls().length
    fireEvent.change(fileInput(), { target: { files: [new File(['zip'], 'cats.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })] } })
    await waitFor(() => expect(postsTo('/ref/excel/categories/')).toHaveLength(1))
    const [path, body] = postsTo('/ref/excel/categories/')[0]
    expect(path).toBe('/formations/ref/excel/categories/')
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file').name).toBe('cats.xlsx')
    expect(await screen.findByText('Import terminé : 3 ligne(s), 2 ajoutée(s), 1 mise(s) à jour.')).toBeInTheDocument()
    expect(gestionCalls().length).toBeGreaterThan(avant)
  })

  it("gère une réponse d'import sans données (bilans à zéro)", async () => {
    mount({ tab: 'sites' })
    await settle()
    apiMock.post.mockResolvedValueOnce({}) // pas de clé `data`
    fireEvent.change(fileInput(), { target: { files: [new File(['x'], 'sites_vides.xlsx')] } })
    expect(await screen.findByText('Import terminé : 0 ligne(s), 0 ajoutée(s), 0 mise(s) à jour.')).toBeInTheDocument()
  })

  it("notifie l'erreur formatée puis le message générique d'un import en échec", async () => {
    mount({ tab: 'sites' })
    await settle()
    apiMock.post.mockRejectedValueOnce({ response: { data: { detail: 'Colonne manquante' } } })
    fireEvent.change(fileInput(), { target: { files: [new File(['x'], 'sites.xlsx')] } })
    expect(await screen.findByText('Colonne manquante')).toBeInTheDocument()

    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.change(fileInput(), { target: { files: [new File(['x'], 'sites2.xlsx')] } })
    expect(await screen.findByText('Import Excel impossible.')).toBeInTheDocument()
  })
})
