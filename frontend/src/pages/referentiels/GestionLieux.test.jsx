/**
 * Lieux et vagues gérables depuis le module « Référentiels ».
 *
 * Sites, bâtiments, salles et espaces, vagues ouvrent l'écran de gestion
 * générique (bouton « Gérer ») avec un formulaire adapté aux capacités
 * réelles de leurs modèles formations : provenance suivie mais pas de
 * champ description, pas d'archivage, type de lieu en liste de choix,
 * dates d'indisponibilité, bâtiment filtré par le site choisi.
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
  archives: 0, a_renseigner: 0, sans_source: 0,
  provenance_suivie: true, a_une_description: false,
  archivage_supporte: false, libelle_bouton: '',
  champs: [], selecteurs: [], champs_choix: {}, champs_numeriques: [],
  champs_dates: [], selecteurs_routes: {}, avertissement: '',
}

const ENTREES_LIEUX = [
  {
    ...entreeBase, slug: 'sites', libelle: 'Sites', editable: true,
    a_un_code: false, route_api: '/referentiels/sites/',
    route_ui: '/referentiels/gestion/sites',
    champs: ['geofence_latitude', 'geofence_longitude', 'geofence_rayon_m'],
    champs_numeriques: ['geofence_latitude', 'geofence_longitude', 'geofence_rayon_m'],
  },
  {
    ...entreeBase, slug: 'batiments', libelle: 'Bâtiments', editable: true,
    a_un_code: false, route_api: '/referentiels/batiments/',
    route_ui: '/referentiels/gestion/batiments',
    selecteurs: ['site'],
    selecteurs_routes: { site: { slug: 'sites', route: '/referentiels/sites/', editable: true } },
  },
  {
    ...entreeBase, slug: 'salles', libelle: 'Salles et espaces', editable: true,
    a_un_code: true, route_api: '/referentiels/salles/',
    route_ui: '/referentiels/gestion/salles',
    champs: ['type_lieu', 'capacite', 'equipements', 'indisponible_du', 'indisponible_au'],
    champs_choix: {
      type_lieu: [
        { value: 'COURS', label: 'Salle de cours' },
        { value: 'GYMNASE', label: 'Gymnase' },
      ],
    },
    champs_numeriques: ['capacite'],
    champs_dates: ['indisponible_du', 'indisponible_au'],
    selecteurs: ['site', 'batiment', 'type_espace'],
    selecteurs_routes: {
      site: { slug: 'sites', route: '/referentiels/sites/', editable: true },
      batiment: { slug: 'batiments', route: '/referentiels/batiments/', editable: true },
      type_espace: { slug: 'types-espace-sportif', route: '/referentiels/types-espace-sportif/', editable: true },
    },
  },
  {
    ...entreeBase, slug: 'vagues', libelle: 'Vagues', editable: true,
    a_un_code: true, route_api: '/referentiels/vagues/',
    route_ui: '/referentiels/gestion/vagues',
    champs: ['ordre', 'periode_debut', 'periode_fin', 'effectif_prevu', 'effectif_reel'],
    champs_numeriques: ['effectif_prevu', 'effectif_reel'],
    champs_dates: ['periode_debut', 'periode_fin'],
    selecteurs: ['formation', 'site', 'statut'],
    selecteurs_routes: {
      formation: { slug: '', route: '/formations/ref/formations/', editable: false },
      site: { slug: 'sites', route: '/referentiels/sites/', editable: true },
      statut: { slug: 'statuts-vague', route: '/referentiels/statuts-vague/', editable: true },
    },
  },
]

const catalogue = () => ({
  categories: [{
    cle: 'organisation', libelle: 'Organisation pédagogique',
    description: '', icone: 'bi-diagram-3', entrees: ENTREES_LIEUX,
  }],
  catalogue: [{ cle: 'organisation', libelle: 'Organisation pédagogique' }],
  synthese: {
    nb_referentiels: ENTREES_LIEUX.length, nb_referentiels_editables: 4,
    nb_valeurs: 12, nb_a_renseigner: 0, nb_sans_source: 0,
    nb_valeurs_tracees: 12, taux_tracabilite: 100,
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

describe('cartes lieux et vagues du tableau de bord', () => {
  it('chaque carte propose « Gérer » vers son écran générique', async () => {
    monter(<TableauDeBordReferentiels />, '/referentiels', '/referentiels')
    await settle()

    const liens = screen.getAllByRole('link', { name: /Gérer/ })
    const destinations = liens.map((a) => a.getAttribute('href'))
    expect(destinations).toEqual(expect.arrayContaining([
      '/referentiels/gestion/sites',
      '/referentiels/gestion/batiments',
      '/referentiels/gestion/salles',
      '/referentiels/gestion/vagues',
    ]))
  })
})

describe('écran générique — présentations liste / cartes et pagination', () => {
  const fabriqueSalles = (n = 30) => Array.from({ length: n }, (_, i) => ({
    id: i + 1,
    code: `SC-${String(i + 1).padStart(3, '0')}`,
    libelle: `Salle de cours ${String(i + 1).padStart(2, '0')}`,
    type_lieu: 'COURS', capacite: 40, equipements: 'Tableau blanc, Vidéoprojecteur',
    indisponible_du: '', indisponible_au: '',
    site: 7, site_libelle: 'INJS Marcory',
    batiment: i % 2 ? 4 : 3,
    batiment_libelle: i % 2 ? 'Bâtiment annexe' : 'Bloc administratif',
    type_espace: null, type_espace_libelle: '',
    actif: true, source_document: 'Inventaire des lieux', fiabilite: 'CADRAGE',
  }))

  const monter30 = () => {
    apiController.reset()
    localStorage.clear()
    apiController.setRoute('/referentiels/salles/', fabriqueSalles())
    apiController.setRoute('/referentiels/sites/', [
      { id: 7, code: 'INJS Marcory', libelle: 'INJS Marcory', actif: true },
    ])
    apiController.setRoute('/referentiels/batiments/', [
      { id: 3, code: 'Bloc administratif', libelle: 'Bloc administratif', site: 7, actif: true },
      { id: 4, code: 'Bâtiment annexe', libelle: 'Bâtiment annexe', site: 7, actif: true },
    ])
    apiController.setRoute('/referentiels/types-espace-sportif/', [])
    return monter(
      <ReferentielGenerique />,
      '/referentiels/gestion/:slug',
      '/referentiels/gestion/salles',
    )
  }

  it('pagine la liste par 24 au lieu d’afficher toutes les lignes', async () => {
    monter30()
    await settle()

    expect(document.querySelectorAll('tbody tr')).toHaveLength(24)
    expect(screen.getByText('Éléments 1 à 24 sur 30')).toBeTruthy()
    expect(screen.getByText('Page 1 sur 2')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Suivant' }))
    await settle()
    expect(document.querySelectorAll('tbody tr')).toHaveLength(6)
    expect(screen.getByText('Éléments 25 à 30 sur 30')).toBeTruthy()
    expect(screen.getByText('Page 2 sur 2')).toBeTruthy()
  })

  it('bascule en vue cartes (capacité mise en avant) et revient en liste', async () => {
    monter30()
    await settle()

    fireEvent.click(screen.getByRole('button', { name: /Cartes/ }))
    await settle()
    expect(screen.queryByRole('table')).toBeNull()
    const cartes = screen.getAllByRole('listitem')
    expect(cartes).toHaveLength(24)
    expect(screen.getAllByText('40 places').length).toBeGreaterThanOrEqual(20)
    expect(screen.getByText('SC-001')).toBeTruthy()
    expect(screen.getByText('Salle de cours 01')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /Liste/ }))
    await settle()
    expect(screen.getByRole('table')).toBeTruthy()
  })

  it('filtre par bâtiment via le sélecteur rapide', async () => {
    monter30()
    await settle()

    fireEvent.change(screen.getByLabelText('Bâtiment'), { target: { value: '4' } })
    await settle()
    expect(screen.getByText('15 / 30')).toBeTruthy()
    expect(document.querySelectorAll('tbody tr')).toHaveLength(15)
    expect(screen.queryByText('Salle de cours 01')).toBeNull()
    expect(screen.getByText('Salle de cours 02')).toBeTruthy()
  })
})

describe('écran générique — salles et espaces', () => {
  const monterSalles = () => {
    apiController.reset()
    apiController.setRoute('/referentiels/salles/', [
      {
        id: 1, code: 'AMP-001', libelle: 'Amphithéâtre principal',
        type_lieu: 'AMPHITHEATRE', capacite: 400, equipements: '',
        indisponible_du: '', indisponible_au: '',
        site: 7, site_libelle: 'INJS Marcory',
        batiment: 3, batiment_libelle: 'Bloc administratif',
        type_espace: null, type_espace_libelle: '',
        actif: true, source_document: 'Inventaire des lieux',
        fiabilite: 'MODELISE',
      },
    ])
    apiController.setRoute('/referentiels/sites/', [
      { id: 7, code: 'INJS Marcory', libelle: 'INJS Marcory', actif: true },
      { id: 8, code: 'Annexe', libelle: 'Site annexe', actif: true },
    ])
    apiController.setRoute('/referentiels/batiments/', [
      { id: 3, code: 'Bloc administratif', libelle: 'Bloc administratif', site: 7, actif: true },
      { id: 4, code: 'Bâtiment annexe', libelle: 'Bâtiment annexe', site: 8, actif: true },
    ])
    apiController.setRoute('/referentiels/types-espace-sportif/', [
      { id: 1, code: 'GYMNASE', libelle: 'Gymnase sportif', actif: true },
    ])
    return monter(
      <ReferentielGenerique />,
      '/referentiels/gestion/:slug',
      '/referentiels/gestion/salles',
    )
  }

  it('affiche les salles sans archivage et crée une salle complète', async () => {
    monterSalles()
    await settle()

    expect(screen.getByText('AMP-001')).toBeTruthy()
    expect(screen.getByText('INJS Marcory')).toBeTruthy() // colonne Site
    expect(document.querySelector('button[title="Archiver"]')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Ajouter/ }))
    await settle()

    // Provenance suivie mais aucune description sur ces modèles hérités.
    expect(screen.getByLabelText('Fiabilité')).toBeTruthy()
    expect(screen.queryByLabelText('Description')).toBeNull()
    expect(screen.getByLabelText('Type de lieu')).toBeTruthy()
    expect(screen.getByRole('option', { name: 'Gymnase' })).toBeTruthy()
    expect(screen.getByLabelText('Capacité')).toHaveProperty('type', 'number')
    expect(screen.getByLabelText('Indisponible du')).toHaveProperty('type', 'date')

    // Le bâtiment est filtré par le site choisi.
    fireEvent.change(screen.getByLabelText('Site'), { target: { value: '7' } })
    await settle()
    expect(screen.getByRole('option', { name: 'Bloc administratif' })).toBeTruthy()
    expect(screen.queryByRole('option', { name: 'Bâtiment annexe' })).toBeNull()

    fireEvent.change(screen.getByLabelText(/Code métier/), { target: { value: 'GYM-001' } })
    fireEvent.change(screen.getByLabelText(/Libellé officiel/), { target: { value: 'Gymnase 1' } })
    fireEvent.change(screen.getByLabelText('Type de lieu'), { target: { value: 'GYMNASE' } })
    fireEvent.change(screen.getByLabelText('Bâtiment'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await settle()

    const post = apiMock.post.mock.calls.find(([p]) => p === '/referentiels/salles/')
    expect(post).toBeTruthy()
    const corps = post[1]
    expect(corps).toMatchObject({
      code: 'GYM-001', libelle: 'Gymnase 1', type_lieu: 'GYMNASE',
      site: 7, batiment: 3,
    })
    expect(corps.description).toBeUndefined()
    expect(corps.indisponible_du).toBeNull()
  })
})
