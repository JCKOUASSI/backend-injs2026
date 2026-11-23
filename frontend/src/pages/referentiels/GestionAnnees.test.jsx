/**
 * Années académiques gérables depuis le module « Référentiels ».
 *
 * La plaquette suit les mêmes normes que les autres : bouton « Gérer »,
 * provenance suivie (fiabilité, source, description), calendrier de
 * l'Institut avec dates typées et drapeaux « Année courante » / « Clôturée »
 * en cases à cocher. Le libellé (2026-2027) tient lieu de code : aucun
 * champ code métier n'est demandé.
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

const ENTREE_ANNEES = {
  slug: 'annees', libelle: 'Années académiques',
  description: 'Périodes de référence de la scolarité.',
  icone: 'bi-calendar-range', source: 'ADMINISTRATIF & SCOLARITÉ (PDF) — §6',
  total: 8, actifs: 4, archives: 0, a_renseigner: 0, sans_source: 0,
  editable: true, a_un_code: false,
  provenance_suivie: true, a_une_description: true,
  archivage_supporte: false, libelle_bouton: '',
  route_api: '/referentiels/annees/',
  route_ui: '/referentiels/gestion/annees',
  champs: ['date_debut', 'date_fin', 'courante', 'cloturee', 'date_cloture'],
  selecteurs: [], champs_choix: {}, champs_numeriques: [],
  champs_dates: ['date_debut', 'date_fin', 'date_cloture'],
  selecteurs_routes: {}, avertissement: '',
}

const catalogue = () => ({
  categories: [{
    cle: 'administratif-scolarite', libelle: 'Administratif & scolarité',
    description: '', icone: 'bi-folder', entrees: [ENTREE_ANNEES],
  }],
  catalogue: [{ cle: 'administratif-scolarite', libelle: 'Administratif & scolarité' }],
  synthese: {
    nb_referentiels: 1, nb_referentiels_editables: 1,
    nb_valeurs: 8, nb_a_renseigner: 0, nb_sans_source: 0,
    nb_valeurs_tracees: 8, taux_tracabilite: 100,
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

describe('carte « Années académiques » du tableau de bord', () => {
  it('propose « Gérer » vers l’écran générique', async () => {
    monter(<TableauDeBordReferentiels />, '/referentiels', '/referentiels')
    await settle()

    const lien = screen.getByRole('link', { name: /Gérer/ })
    expect(lien.getAttribute('href')).toBe('/referentiels/gestion/annees')
  })
})

describe('écran générique — années académiques', () => {
  it('affiche le calendrier avec provenance et crée une année planifiée', async () => {
    apiController.setRoute('/referentiels/annees/', [
      {
        id: 6, code: '2026-2027', libelle: '2026-2027',
        date_debut: '2026-10-01', date_fin: '2027-07-31',
        courante: true, cloturee: false, date_cloture: '',
        description: 'Année de référence',
        actif: true, source_document: 'PDF §6', fiabilite: 'OFFICIEL',
      },
      {
        id: 7, code: '2027-2028', libelle: '2027-2028',
        date_debut: '2027-10-01', date_fin: '2028-07-31',
        courante: false, cloturee: false, date_cloture: '',
        description: 'Ouverture des campagnes au printemps 2027',
        actif: true, source_document: 'PDF §6', fiabilite: 'CADRAGE',
      },
    ])
    monter(
      <ReferentielGenerique />,
      '/referentiels/gestion/:slug',
      '/referentiels/gestion/annees',
    )
    await settle()

    // Le libellé tient lieu de code : il apparaît dans les deux colonnes.
    expect(screen.getAllByText('2026-2027').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('Officiel')).toBeTruthy()
    expect(document.querySelector('button[title="Archiver"]')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Ajouter/ }))
    await settle()

    // Le libellé tient lieu de code : pas de champ code métier.
    expect(screen.queryByLabelText(/Code métier/)).toBeNull()
    expect(screen.getByLabelText(/Libellé officiel/)).toBeTruthy()
    expect(screen.getByLabelText('Fiabilité')).toBeTruthy()
    expect(screen.getByLabelText('Description')).toBeTruthy()
    expect(screen.getByLabelText('Date de début')).toHaveProperty('type', 'date')
    expect(screen.getByLabelText('Date de fin')).toHaveProperty('type', 'date')
    expect(screen.getByLabelText('Date de clôture')).toHaveProperty('type', 'date')
    // Les deux drapeaux du processus sont des cases à cocher.
    const caseCourante = document.getElementById('ref-courante')
    const caseCloturee = document.getElementById('ref-cloturee')
    expect(caseCourante).toHaveProperty('type', 'checkbox')
    expect(caseCourante.checked).toBe(false)
    expect(caseCloturee).toHaveProperty('type', 'checkbox')

    fireEvent.change(screen.getByLabelText(/Libellé officiel/), { target: { value: '2029-2030' } })
    fireEvent.change(screen.getByLabelText('Date de début'), { target: { value: '2029-10-01' } })
    fireEvent.change(screen.getByLabelText('Date de fin'), { target: { value: '2030-07-31' } })
    fireEvent.click(screen.getByRole('button', { name: 'Enregistrer' }))
    await settle()

    const post = apiMock.post.mock.calls.find(([p]) => p === '/referentiels/annees/')
    expect(post).toBeTruthy()
    const corps = post[1]
    expect(corps.code).toBeUndefined()
    expect(corps).toMatchObject({
      libelle: '2029-2030', date_debut: '2029-10-01',
      date_fin: '2030-07-31', courante: false, cloturee: false,
    })
    expect(corps.date_cloture).toBeNull()
  })
})
