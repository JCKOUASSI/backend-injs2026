/**
 * Intégration du moteur commun dans l'écran de gestion d'un référentiel.
 *
 * Vérifie que l'écran expose bien l'export, l'import et les trois opérations
 * distinctes (activer / désactiver / archiver / supprimer) en appelant les
 * routes backend correspondantes — et pas un simple champ « actif ».
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

const settle = async (n = 6) => {
  await act(async () => {
    await flushPromises(n)
  })
}

afterEach(async () => {
  await settle()
})

const ENTREE = {
  slug: 'types-evaluation',
  libelle: "Types d'évaluation",
  description: "Natures d'évaluation.",
  icone: 'bi-clipboard-check',
  source: 'RÉFÉRENTIEL PÉDAGOGIQUE',
  total: 2, actifs: 2, archives: 0, a_renseigner: 0, sans_source: 0,
  editable: true, a_un_code: true,
  provenance_suivie: true, a_une_description: true,
  archivage_supporte: true, libelle_bouton: '',
  route_api: '/referentiels/types-evaluation/',
  route_ui: '/referentiels/gestion/types-evaluation',
  champs: [], selecteurs: [], champs_choix: {},
  champs_numeriques: [], champs_dates: [], selecteurs_routes: {},
  avertissement: '',
}

const LIGNES = [
  {
    id: 1, code: 'EXAM', libelle: 'Examen', description: 'Épreuve finale',
    actif: true, archive: false, fiabilite: 'OFFICIEL',
  },
  {
    id: 2, code: 'CC', libelle: 'Contrôle continu', description: '',
    actif: false, archive: false, fiabilite: 'A_RENSEIGNER',
  },
]

/**
 * Monte l'écran sur le référentiel « types-evaluation » avec le mécanisme
 * de routes du projet (apiController), comme les autres tests du module.
 */
function monter(lignes = LIGNES) {
  const utilisateur = makeUser('ADMIN', { username: 'refadmin' })
  apiController.setMe(utilisateur)
  apiController.setRoute('/referentiels/tableau-de-bord/', {
    categories: [{ cle: 'pedagogique', libelle: 'Pédagogique', entrees: [ENTREE] }],
  })
  apiController.setRoute('/referentiels/types-evaluation/', {
    results: lignes,
    count: lignes.length,
  })
  return renderWithProviders(<ReferentielGenerique />, {
    authUser: utilisateur,
    routePattern: '/referentiels/gestion/:slug',
    initialEntries: ['/referentiels/gestion/types-evaluation'],
  })
}

beforeEach(() => {
  apiController.reset?.()
})

describe('Écran référentiel — moteur commun', () => {
  it('expose les quatre formats d’export', async () => {
    monter()
    await settle(8)
    const groupe = screen.getByRole('group', { name: /Exporter le référentiel/i })
    const libelles = Array.from(groupe.querySelectorAll('button')).map((b) =>
      b.textContent.trim(),
    )
    expect(libelles.join(' ')).toMatch(/Excel/)
    expect(libelles.join(' ')).toMatch(/Word/)
    expect(libelles.join(' ')).toMatch(/CSV/)
    expect(libelles.join(' ')).toMatch(/PDF/)
  })

  it('ouvre l’assistant d’import', async () => {
    monter()
    await settle(8)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Importer/i }))
      await flushPromises(6)
    })
    expect(
      screen.getByRole('dialog', { name: /Importer des données/i }),
    ).toBeTruthy()
    expect(screen.getByText('Téléversement')).toBeTruthy()
  })

  it('désactive une valeur via la route dédiée (pas un simple patch)', async () => {
    monter()
    await settle(8)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Désactiver Examen/i }))
      await flushPromises(8)
    })
    const appels = apiMock.post.mock.calls.map((c) => c[0])
    expect(appels).toContain('/referentiels/types-evaluation/1/desactiver/')
  })

  it('active une valeur inactive via la route dédiée', async () => {
    monter()
    await settle(8)
    // Le filtre par défaut n'affiche que les actifs : on passe sur « Tous ».
    await act(async () => {
      fireEvent.change(screen.getByLabelText(/Afficher/i), { target: { value: 'tous' } })
      await flushPromises(6)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Activer Contrôle continu/i }))
      await flushPromises(8)
    })
    const appels = apiMock.post.mock.calls.map((c) => c[0])
    expect(appels).toContain('/referentiels/types-evaluation/2/activer/')
  })

  it('propose la suppression distincte de l’archivage', async () => {
    monter()
    await settle(8)
    // Trois opérations indépendantes : supprimer, archiver et désactiver.
    expect(screen.getByRole('button', { name: /Supprimer Examen/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Archiver Examen/i })).toBeTruthy()
    expect(screen.getByRole('button', { name: /Désactiver Examen/i })).toBeTruthy()
  })

  it('demande confirmation avant de supprimer', async () => {
    monter()
    await settle(8)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Supprimer Examen/i }))
      await flushPromises(6)
    })
    expect(screen.getByRole('alertdialog')).toBeTruthy()
    expect(screen.getByText(/Supprimer cette valeur/i)).toBeTruthy()
    // Rien n'est envoyé tant que l'utilisateur n'a pas confirmé.
    const appels = apiMock.post.mock.calls.map((c) => c[0])
    expect(appels.some((u) => u.includes('/supprimer/'))).toBe(false)
  })

  it('envoie la confirmation au backend lors de la suppression', async () => {
    monter()
    await settle(8)
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Supprimer Examen/i }))
      await flushPromises(6)
    })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /Confirmer la suppression/i }))
      await flushPromises(8)
    })
    const appel = apiMock.post.mock.calls.find((c) => String(c[0]).includes('/supprimer/'))
    expect(appel).toBeTruthy()
    expect(appel[1]).toMatchObject({ confirmation: 'confirmer' })
  })
})
