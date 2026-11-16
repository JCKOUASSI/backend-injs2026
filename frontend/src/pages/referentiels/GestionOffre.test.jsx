import { describe, it, expect, vi } from 'vitest'
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
import TableauDeBordReferentiels from './TableauDeBordReferentiels'
import ReferentielGenerique from './ReferentielGenerique'

const entries = [
  { slug: 'formations', libelle: 'Formations (cycles)', champs: ['type_diplome'], selecteurs: [], a_un_code: true },
  { slug: 'modules-officiels', libelle: 'Modules officiels', champs: ['semestre'], selecteurs: ['formation'], a_un_code: false },
  { slug: 'volumes-modules', libelle: 'Volumes horaires (modélisation)', champs: ['heures_cm'], selecteurs: ['formation'], a_un_code: false },
].map(item => ({
  ...item, editable: true, description: '', icone: 'bi-dot', source: '',
  route_gestion: `/referentiels/gestion-donnees/${item.slug}/`,
  libelle_bouton: 'Gérer',
  provenance_suivie: true, archivage_supporte: true,
  a_une_description: item.slug === 'formations',
  total: 1, actifs: 1, archives: 0, a_renseigner: 0,
  champs_dates: [], champs_numeriques: [], champs_choix: {},
  selecteurs_routes: item.selecteurs.length
    ? { formation: { route: '/formations/ref/formations/', editable: true } } : {},
}))
const settle = async () => { await act(async () => { await flushPromises(8) }) }
const setup = (slug, { routeProvisoireInexistante = false } = {}) => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  apiController.setRoute('/referentiels/tableau-de-bord/', {
    categories: [{ cle: 'offre-formation', libelle: 'Offre', icone: 'bi-dot', description: '', entrees: entries }],
    catalogue: [{ cle: 'offre-formation', libelle: 'Offre', icone: 'bi-dot' }],
    synthese: { nb_referentiels: 3, nb_valeurs: 3, nb_a_renseigner: 0, taux_tracabilite: 1 },
  })
  apiController.setRoute('/formations/ref/formations/', [{ id: 4, intitule: 'Licence Sports' }])
  if (routeProvisoireInexistante) {
    apiController.setRoute('/referentiels/formations/', () => {
      throw { response: { status: 404, data: { detail: 'Route inexistante' } } } // eslint-disable-line no-throw-literal
    })
  }
  if (slug) apiController.setRoute(`/referentiels/gestion-donnees/${slug}/`, [
    { id: 7, code: 'LS', libelle: 'Licence Sports', actif: true, archive: false, fiabilite: 'OFFICIEL' },
  ])
  return renderWithProviders(slug ? <ReferentielGenerique /> : <TableauDeBordReferentiels />, {
    authUser: me,
    routePattern: slug ? '/referentiels/gestion/:slug' : '/referentiels',
    initialEntries: [slug ? `/referentiels/gestion/${slug}` : '/referentiels'],
  })
}

describe('plaquettes Offre de formation', () => {
  it('charge les cycles directement par la route du catalogue, jamais par la route initiale 404', async () => {
    setup('formations', { routeProvisoireInexistante: true })
    await settle()
    expect(screen.getByText('Licence Sports')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(apiMock.get).toHaveBeenCalledWith('/referentiels/gestion-donnees/formations/',
      { params: { archives: 1, page_size: 1000 } })
    expect(apiMock.get.mock.calls.some(([path]) => path === '/referentiels/formations/')).toBe(false)
  })

  it('ouvre les trois écrans de gestion depuis le tableau de bord', async () => {
    setup()
    await settle()
    for (const item of entries) {
      const lien = document.querySelector(`a[href="/referentiels/gestion/${item.slug}"]`)
      expect(lien).toBeTruthy()
      expect(lien.textContent).toContain('Gérer')
      expect(lien.textContent).not.toContain('Consulter')
    }
  })

  it.each(entries.map(x => [x.slug, x.libelle]))('%s affiche CRUD, archivage et quatre exports', async (slug, libelle) => {
    setup(slug)
    await settle()
    expect(screen.getByRole('button', { name: /Ajouter/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Visualiser/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Modifier/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Supprimer Licence Sports' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Archiver Licence Sports' })).toBeTruthy()
    for (const format of ['Word', 'Excel', 'CSV', 'PDF']) {
      expect(screen.getByRole('button', { name: `Exporter ${libelle} en ${format}` })).toBeTruthy()
    }
    expect(screen.getByLabelText('Importer un fichier CSV ou Excel')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Supprimer Licence Sports' }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /^Supprimer$/ }))
    await settle()
    expect(apiMock.delete).toHaveBeenCalledWith(`/referentiels/gestion-donnees/${slug}/7/`)
  })

  it('coche la page, confirme un lot et ne l’envoie qu’après confirmation', async () => {
    setup('formations')
    await settle()
    const bouton = screen.getByRole('button', { name: 'Supprimer la sélection' })
    expect(bouton.disabled).toBe(true)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence Sports' }))
    await settle()
    expect(bouton.disabled).toBe(false)
    fireEvent.click(bouton)
    await settle()
    expect(apiMock.post).not.toHaveBeenCalledWith('/referentiels/gestion-donnees/formations/lot/',
      { ids: [7], action: 'supprimer' })
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    await settle()
    fireEvent.click(bouton)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmer supprimer' }))
    await settle()
    expect(apiMock.post).toHaveBeenCalledWith('/referentiels/gestion-donnees/formations/lot/',
      { ids: [7], action: 'supprimer' })
    expect(screen.getByRole('checkbox', { name: 'Sélectionner Licence Sports' }).checked).toBe(false)
  })

  it('propose aussi les cases à cocher en cartes et oublie la sélection après filtre', async () => {
    setup('formations')
    await settle()
    fireEvent.click(screen.getByRole('button', { name: 'Cartes' }))
    await settle()
    fireEvent.click(screen.getByRole('checkbox', { name: 'Sélectionner Licence Sports' }))
    await settle()
    expect(screen.getByRole('button', { name: 'Archiver la sélection' }).disabled).toBe(false)
    fireEvent.change(screen.getByLabelText('Rechercher'), { target: { value: 'lic' } })
    await settle()
    expect(screen.getByRole('button', { name: 'Archiver la sélection' }).disabled).toBe(true)
  })

  it('transmet un CSV au serveur en multipart et appelle le téléchargement binaire', async () => {
    setup('formations')
    await settle()
    fireEvent.change(screen.getByLabelText('Importer un fichier CSV ou Excel'), {
      target: { files: [new File(['libelle,code\nLicence,LIC'], 'formations.csv', { type: 'text/csv' })] },
    })
    await settle()
    const importCall = apiMock.post.mock.calls.find(([path]) => path.endsWith('/import/'))
    expect(importCall?.[1]).toBeInstanceOf(FormData)
    expect(importCall[1].get('fichier').name).toBe('formations.csv')
    // Le mock ne simule pas un vrai Blob : on vérifie l'URL utilisée par le client.
    fireEvent.click(screen.getByRole('button', { name: 'Exporter Formations (cycles) en CSV' }))
    await settle()
    expect(apiMock.getBlob).toHaveBeenCalledWith('/referentiels/gestion-donnees/formations/export/?export=csv')
  })
})
