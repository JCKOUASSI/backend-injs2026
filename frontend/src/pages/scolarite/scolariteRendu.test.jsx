/**
 * Régressions §10.8 (LOT 7) — quatre écrans Scolarité avaient une fonction
 * de gestion (transition de campagne, enregistrement de note, application
 * d'équivalence, archivage d'ECUE) dont l'accolade de fermeture manquait :
 * tout le `return` de la page se retrouvait alors *à l'intérieur* de cette
 * fonction, jamais appelée, et l'écran rendait un composant vide (page
 * blanche) sans pour autant planter (le smoke « pas de crash » passait).
 *
 * Ces tests affirment le RENDU EFFECTIF du contenu de chaque page.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act } from '@testing-library/react'

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

const callsTo = (pathOnly) =>
  apiMock.get.mock.calls.filter(([p]) => p.split('?')[0] === pathOnly)

const mount = (Component, { pattern, url }) => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Component />, {
    authUser: me,
    routePattern: pattern,
    initialEntries: [url],
  })
}

const settle = async () => {
  await act(async () => {
    await flushPromises(5)
  })
}

beforeEach(() => {
  apiController.reset()
  window.localStorage.clear()
})

describe('§10.8 — les pages Scolarité rendent réellement leur contenu (pas de page blanche)', () => {
  it('Campagnes affiche son titre (le return n’est pas avalé par transition)', async () => {
    apiController.setRoute('/admissions/campagnes/', () => [])
    mount(Campagnes, { pattern: '/scolarite/campagnes', url: '/scolarite/campagnes' })
    await settle()
    expect(
      await screen.findByRole('heading', { name: /campagnes d'admission/i }),
    ).toBeInTheDocument()
  })

  it('CampagneDetail affiche le libellé de la campagne (pas avalé par enregistrerNote)', async () => {
    apiController.setRoute(/\/admissions\/campagnes\/\d+\/$/, () => ({
      libelle: 'Campagne test 2026', statut: 'BROUILLON', epreuves: [],
    }))
    apiController.setRoute('/admissions/candidatures/', () => [])
    apiController.setRoute(/classement\/$/, () => [])
    mount(CampagneDetail, { pattern: '/scolarite/campagnes/:id', url: '/scolarite/campagnes/1' })
    await settle()
    expect(
      await screen.findByRole('heading', { name: 'Campagne test 2026' }),
    ).toBeInTheDocument()
  })

  it('Équivalences affiche son titre (pas avalé par appliquer)', async () => {
    apiController.setRoute('/equivalences/demandes/', () => [])
    mount(Equivalences, { pattern: '/scolarite/equivalences', url: '/scolarite/equivalences' })
    await settle()
    expect(
      await screen.findByRole('heading', { name: /équivalences et dispenses/i }),
    ).toBeInTheDocument()
  })

  it('MaquetteDetail affiche le libellé de la maquette (pas avalé par supprimerEcue)', async () => {
    apiController.setRoute(/\/scolarite\/maquettes\/\d+\/$/, () => ({
      libelle: 'Maquette L1 LSF', ref_formation: 'L1',
      unites_enseignement: [],
    }))
    apiController.setRoute(/journal\/$/, () => [])
    mount(MaquetteDetail, { pattern: '/scolarite/maquettes/:id', url: '/scolarite/maquettes/1' })
    await settle()
    expect(
      await screen.findByRole('heading', { name: 'Maquette L1 LSF' }),
    ).toBeInTheDocument()
  })

  it('ChargesEnseignants charge l’année courante au montage puis l’occupation (§10.8)', async () => {
    apiController.setRoute('/scolarite/annee-courante/', () => ({ id: 9, libelle: '2025-2026' }))
    apiController.setRoute('/enseignants/occupation/', () => ({ occupation: [] }))
    apiController.setRoute('/enseignants/anomalies/', () => ({ anomalies: [] }))

    mount(ChargesEnseignants, { pattern: '/scolarite/charges', url: '/scolarite/charges' })
    await settle()

    // 1) l'année courante est bien requêtée au montage (avant : jamais) ;
    expect(callsTo('/scolarite/annee-courante/').length).toBeGreaterThan(0)
    // 2) l'effet [annee] s'enchaîne et requête l'occupation avec le bon id.
    const occCalls = callsTo('/enseignants/occupation/')
    expect(occCalls.length).toBeGreaterThan(0)
    expect(occCalls.at(-1)[1].params.annee_id).toBe(9)
    expect(
      await screen.findByRole('heading', { name: /charges pédagogiques des enseignants/i }),
    ).toBeInTheDocument()
  })
})
