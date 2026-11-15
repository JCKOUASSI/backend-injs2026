/**
 * Écran générique — export (.docx, .xlsx, .csv, .pdf) et import (.xlsx, .csv)
 * des référentiels éditables.
 *
 * Le composant réutilise les mêmes routes que le backend expose pour TOUTES
 * les entrées du registre : `/referentiels/{slug}/export/?fmt=…` et
 * `/referentiels/{slug}/import/` (multipart « fichier », atomique).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
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
import ReferentielGenerique from '@/pages/referentiels/ReferentielGenerique'

const settle = async (n = 6) => { await act(async () => { await flushPromises(n) }) }

afterEach(async () => { await settle() })

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
  URL.createObjectURL = vi.fn(() => 'blob:test')
  URL.revokeObjectURL = vi.fn()
  HTMLAnchorElement.prototype.click = vi.fn()
})

const ENTREE_VOLUMES = {
  slug: 'volumes-modules', libelle: 'Volumes horaires (modélisation)',
  description: 'Répartition CM/TD/TP/stage.',
  icone: 'bi-clock-history', source: 'Modéliser les volumes horaires',
  total: 1, actifs: 1, archives: 0, a_renseigner: 0, sans_source: 0,
  editable: true, a_un_code: false,
  provenance_suivie: true, a_une_description: false,
  archivage_supporte: true, libelle_bouton: '',
  route_api: '/referentiels/volumes-modules/',
  route_ui: '/referentiels/gestion/volumes-modules',
  champs: ['heures_cm', 'heures_td', 'heures_tp', 'heures_stage', 'heures_total'],
  selecteurs: ['formation'], champs_choix: {},
  champs_numeriques: ['heures_cm', 'heures_td', 'heures_tp', 'heures_stage', 'heures_total'],
  champs_dates: [],
  selecteurs_routes: { formation: { route: '/referentiels/formations/' } },
  filtres_liste: { formation: 'formation_id' },
  avertissement: '',
}

const ENTREE_LECTURE_SEULE = {
  ...ENTREE_VOLUMES,
  slug: 'ue-ecue', libelle: 'UE et ECUE', icone: 'bi-diagram-3',
  editable: false, archivage_supporte: false,
}

const monter = (entree, url = `/referentiels/gestion/${entree.slug}`) => {
  const me = makeUser('ADMIN', { username: 'refadmin' })
  apiController.setMe(me)
  apiController.setRoute('/referentiels/tableau-de-bord/', {
    categories: [{
      cle: 'offre-formation', libelle: 'Offre de formation',
      description: '', icone: 'bi-mortarboard', entrees: [entree],
    }],
    catalogue: [{ cle: 'offre-formation', libelle: 'Offre de formation' }],
    synthese: {
      nb_referentiels: 1, nb_referentiels_editables: entree.editable ? 1 : 0,
      nb_valeurs: 1, nb_a_renseigner: 0, nb_sans_source: 0,
      nb_valeurs_tracees: 1, taux_tracabilite: 1,
    },
  })
  return renderWithProviders(
    <ReferentielGenerique />,
    { authUser: me, routePattern: '/referentiels/gestion/:slug', initialEntries: [url] },
  )
}

describe('écran générique — export des référentiels', () => {
  it('propose les quatre formats et télécharge le fichier via getBlob', async () => {
    apiController.setRoute('/referentiels/volumes-modules/', [
      { id: 1, code: 'Biomécanique', libelle: 'Biomécanique', heures_cm: 30, heures_td: 15, heures_tp: 0, heures_stage: 0, heures_total: 45, actif: true, archive: false, fiabilite: 'MODELISE', formation: 9, formation_libelle: 'ÉDUCATION ET MOTRICITÉ — LICENCE' },
    ])
    monter(ENTREE_VOLUMES)
    await settle()

    fireEvent.click(screen.getByRole('button', { name: /Exporter/ }))
    const xlsx = screen.getByRole('menuitem', { name: /Excel/ })
    expect(screen.getByRole('menuitem', { name: /CSV/ })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: /Word/ })).toBeTruthy()
    expect(screen.getByRole('menuitem', { name: /PDF/ })).toBeTruthy()

    fireEvent.click(xlsx)
    await settle()

    expect(apiMock.getBlob).toHaveBeenCalledTimes(1)
    const [chemin] = apiMock.getBlob.mock.calls[0]
    expect(chemin).toContain('/referentiels/volumes-modules/export/?fmt=xlsx')
    expect(chemin).toContain('actif=true')
    expect(window.URL.createObjectURL).toHaveBeenCalled()
  })
})

describe('écran générique — import des référentiels', () => {
  it('envoie le fichier en multipart et recharge la liste en cas de succès', async () => {
    apiController.setRoute('/referentiels/volumes-modules/', [])
    apiController.setRoute('/referentiels/formations/', [])
    apiController.setRoute('/referentiels/volumes-modules/import/', {
      created: 1, updated: 0, processed: 1, colonnes_ignorees: [],
    })
    monter(ENTREE_VOLUMES)
    await settle()

    const bouton = screen.getByRole('button', { name: /Importer/ })
    expect(bouton).toBeTruthy()

    const entreeFichier = document.querySelector('.ref-import-input')
    const fichier = new File(['Libellé;Heures CM\r\nPhysiologie;20\r\n'], 'volumes.csv', { type: 'text/csv' })
    fireEvent.change(entreeFichier, { target: { files: [fichier] } })
    await settle()

    const appel = apiMock.post.mock.calls.find(([chemin]) => chemin === '/referentiels/volumes-modules/import/')
    expect(appel).toBeTruthy()
    expect(appel[1]).toBeInstanceOf(FormData)
    expect(appel[1].get('fichier')).toBeTruthy()
  })

  it('affiche le détail ligne par ligne quand le serveur refuse le fichier', async () => {
    apiController.setRoute('/referentiels/volumes-modules/', [])
    apiController.setRoute('/referentiels/formations/', [])
    apiController.setRoute('/referentiels/volumes-modules/import/', () => Promise.reject(
      Object.assign(new Error('refusé'), {
        response: {
          status: 400,
          data: {
            detail: 'Aucune donnée importée : corrigez les lignes indiquées puis relancez l’import.',
            erreurs: ['Ligne 2 : « abc » n’est pas un entier valide pour « Heures CM ».'],
          },
        },
      }),
    ))
    monter(ENTREE_VOLUMES)
    await settle()

    const entreeFichier = document.querySelector('.ref-import-input')
    const fichier = new File(['x'], 'volumes.csv', { type: 'text/csv' })
    fireEvent.change(entreeFichier, { target: { files: [fichier] } })
    await settle()

    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText(/Aucune donnée importée/)).toBeTruthy()
    expect(screen.getByText(/Ligne 2/)).toBeTruthy()
  })

  it('masque l’import (lecture seule) mais conserve l’export', async () => {
    apiController.setRoute('/referentiels/ue-ecue/', [])
    monter(ENTREE_LECTURE_SEULE, '/referentiels/gestion/ue-ecue')
    await settle()

    expect(screen.queryByRole('button', { name: /Importer/ })).toBeNull()
    expect(screen.getByRole('button', { name: /Exporter/ })).toBeTruthy()
  })
})
