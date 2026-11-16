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
const setup = (slug) => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  apiController.setRoute('/referentiels/tableau-de-bord/', {
    categories: [{ cle: 'offre-formation', libelle: 'Offre', icone: 'bi-dot', description: '', entrees: entries }],
    catalogue: [{ cle: 'offre-formation', libelle: 'Offre', icone: 'bi-dot' }],
    synthese: { nb_referentiels: 3, nb_valeurs: 3, nb_a_renseigner: 0, taux_tracabilite: 1 },
  })
  apiController.setRoute('/formations/ref/formations/', [{ id: 4, intitule: 'Licence Sports' }])
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
    expect(screen.getByRole('button', { name: /Supprimer/ })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Archiver/ })).toBeTruthy()
    for (const format of ['Word', 'Excel', 'CSV', 'PDF']) {
      expect(screen.getByRole('button', { name: `Exporter ${libelle} en ${format}` })).toBeTruthy()
    }
    expect(screen.getByLabelText('Importer un fichier CSV ou Excel')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /Supprimer/ }))
    await settle()
    fireEvent.click(screen.getByRole('button', { name: /^Supprimer$/ }))
    await settle()
    expect(apiMock.delete).toHaveBeenCalledWith(`/referentiels/gestion-donnees/${slug}/7/`)
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
