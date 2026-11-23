/**
 * Système LMD gérable depuis le module « Référentiels ».
 *
 * Niveaux, semestres, parcours et types de formation ouvrent l'écran de
 * gestion générique (bouton « Gérer ») avec un formulaire adapté aux
 * capacités réelles de leurs modèles scolarité (pas de provenance, pas
 * d'archivage, semestre sans code distinct, cycle en liste de choix).
 * La carte UE / ECUE renvoie au module Maquettes, toujours par « Gérer ».
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
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
import TableauDeBordReferentiels from '@/pages/referentiels/TableauDeBordReferentiels'
import ReferentielGenerique from '@/pages/referentiels/ReferentielGenerique'

const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }

afterEach(async () => { await settle() })

const entreeBase = {
  description: '', icone: 'bi-dot', source: '', total: 3, actifs: 3,
  archives: 0, a_renseigner: null, sans_source: null,
  provenance_suivie: false, archivage_supporte: false, libelle_bouton: '',
  champs: [], selecteurs: [], champs_choix: {}, champs_numeriques: [],
  selecteurs_routes: {}, avertissement: '',
}

const ENTREES_LMD = [
  {
    ...entreeBase, slug: 'niveaux', libelle: 'Niveaux', editable: true,
    a_un_code: true, route_api: '/referentiels/niveaux/',
    route_ui: '/referentiels/gestion/niveaux',
    champs: ['cycle', 'ordre', 'credits_requis'],
    champs_choix: {
      cycle: [
        { value: 'LICENCE', label: 'Licence' },
        { value: 'MASTER', label: 'Master' },
        { value: 'DOCTORAT', label: 'Doctorat' },
      ],
    },
    champs_numeriques: ['ordre', 'credits_requis'],
  },
  {
    ...entreeBase, slug: 'semestres', libelle: 'Semestres', editable: true,
    a_un_code: false, route_api: '/referentiels/semestres/',
    route_ui: '/referentiels/gestion/semestres',
    champs: ['numero'], selecteurs: ['niveau'],
    champs_numeriques: ['numero'],
    selecteurs_routes: {
      niveau: { slug: 'niveaux', route: '/referentiels/niveaux/', editable: true },
    },
  },
  {
    ...entreeBase, slug: 'parcours', libelle: 'Parcours', editable: true,
    a_un_code: true, route_api: '/referentiels/parcours/',
    route_ui: '/referentiels/gestion/parcours',
  },
  {
    ...entreeBase, slug: 'ue-ecue', libelle: 'UE / ECUE', editable: false,
    a_un_code: true, route_api: '/referentiels/ue-ecue/',
    route_ui: '/scolarite/maquettes', libelle_bouton: 'Gérer', total: 331,
  },
]

const catalogue = () => ({
  categories: [{
    cle: 'systeme-lmd', libelle: 'Système LMD', description: '', icone: 'bi-diagram-3',
    entrees: ENTREES_LMD,
  }],
  catalogue: [{ cle: 'systeme-lmd', libelle: 'Système LMD' }],
  synthese: {
    nb_referentiels: ENTREES_LMD.length, nb_referentiels_editables: 3,
    nb_valeurs: 340, nb_a_renseigner: 0, nb_sans_source: 0,
    nb_valeurs_tracees: 0, taux_tracabilite: null,
  },
})

const monter = (ui, routePattern, url) => {
  const me = makeUser('ADMIN', { username: 'refadmin' })
  apiController.setMe(me)
  apiController.setRoute('/referentiels/tableau-de-bord/', catalogue)
  return renderWithProviders(ui, {
    authUser: me,
    routePattern,
    initialEntries: [url],
  })
}

describe('cartes « Système LMD » du tableau de bord', () => {
  it('chaque carte propose « Gérer », UE/ECUE vers le module Maquettes', async () => {
    monter(<TableauDeBordReferentiels />, '/referentiels', '/referentiels')
    await settle()

    const liens = screen.getAllByRole('link', { name: /Gérer/ })
    const destinations = liens.map((a) => a.getAttribute('href'))
    expect(destinations).toEqual(expect.arrayContaining([
      '/referentiels/gestion/niveaux',
      '/referentiels/gestion/semestres',
      '/referentiels/gestion/parcours',
      '/scolarite/maquettes',
    ]))
    expect(screen.queryByText('Sans écran dédié')).toBeNull()
    expect(screen.queryByRole('link', { name: /Consulter/ })).toBeNull()
  })
})

describe('écran générique — niveaux (modèle hors socle)', () => {
  const monterNiveaux = () => {
    apiController.setRoute('/referentiels/niveaux/', [
      { id: 1, code: 'L1', libelle: 'Licence 1', cycle: 'LICENCE', ordre: 1, credits_requis: 60, actif: true },
      { id: 6, code: 'D1', libelle: 'Doctorat 1', cycle: 'DOCTORAT', ordre: 6, credits_requis: 60, actif: true },
    ])
    return monter(
      <ReferentielGenerique />,
      '/referentiels/gestion/:slug',
      '/referentiels/gestion/niveaux',
    )
  }

  it('affiche les valeurs avec le cycle en libellé humain, sans provenance ni archivage', async () => {
    monterNiveaux()
    await settle()

    expect(screen.getByText('Doctorat')).toBeTruthy() // label du choix, pas DOCTORAT
    expect(screen.queryByText('Fiabilité')).toBeNull()
    expect(screen.queryByRole('option', { name: 'Archivés' })).toBeNull()
    expect(document.querySelector('button[title="Archiver"]')).toBeNull()
    expect(screen.getByRole('button', { name: 'Modifier Doctorat 1' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Désactiver Doctorat 1' })).toBeTruthy()
  })

  it('crée un niveau : cycle en liste de choix, nombres typés, aucun champ socle envoyé', async () => {
    monterNiveaux()
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /Ajouter/ }))
    await settle()

    fireEvent.change(screen.getByLabelText(/Code métier/), { target: { value: 'D2' } })
    fireEvent.change(screen.getByLabelText(/Libellé officiel/), { target: { value: 'Doctorat 2' } })
    fireEvent.change(screen.getByLabelText('Cycle'), { target: { value: 'DOCTORAT' } })
    fireEvent.change(screen.getByLabelText("Ordre d'affichage"), { target: { value: '7' } })
    fireEvent.change(screen.getByLabelText('Crédits ECTS requis'), { target: { value: '60' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await settle()

    const post = apiMock.post.mock.calls.find(([p]) => p === '/referentiels/niveaux/')
    expect(post).toBeTruthy()
    const corps = post[1]
    expect(corps).toMatchObject({
      code: 'D2', libelle: 'Doctorat 2', cycle: 'DOCTORAT', ordre: 7, credits_requis: 60,
    })
    expect(corps.fiabilite).toBeUndefined()
    expect(corps.source_document).toBeUndefined()
    expect(corps.description).toBeUndefined()
  })
})

describe('écran générique — semestres (sans colonne code)', () => {
  it('le formulaire de création ne demande pas de code métier', async () => {
    apiController.setRoute('/referentiels/semestres/', [
      { id: 1, code: 'S1', libelle: 'S1', numero: 1, niveau: 1, niveau_libelle: 'Licence 1', actif: true },
    ])
    apiController.setRoute('/referentiels/niveaux/', [
      { id: 1, code: 'L1', libelle: 'Licence 1', actif: true },
    ])
    monter(
      <ReferentielGenerique />,
      '/referentiels/gestion/:slug',
      '/referentiels/gestion/semestres',
    )
    await settle()

    expect(screen.getByText('Licence 1')).toBeTruthy() // colonne du sélecteur
    fireEvent.click(screen.getByRole('button', { name: /Ajouter/ }))
    await settle()
    expect(screen.queryByLabelText(/Code métier/)).toBeNull()
    expect(screen.getByLabelText(/Libellé officiel/)).toBeTruthy()
    expect(screen.getByLabelText('Niveau')).toBeTruthy()
    expect(screen.getByLabelText('Numéro global')).toBeTruthy()
  })
})
