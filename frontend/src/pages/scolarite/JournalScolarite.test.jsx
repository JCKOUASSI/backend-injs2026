/**
 * Tests de la page dédiée « Journal de scolarité » : chronologie des
 * événements de parcours (dont la marque « Reconstitué »), distinction des
 * deux journaux (parcours vs traçabilité), filtres et enregistrement.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import JournalScolarite from '@/pages/scolarite/JournalScolarite'

const STATS = {
  total: 1872,
  dossiers_concernes: 1867,
  reconstitues: 1863,
  par_type: {
    PASSAGE: 1797, REDOUBLEMENT: 64, TRANSFERT: 1, REPRISE: 1,
    EQUIVALENCE_DISPENSE: 9, REORIENTATION: 0, CHANGEMENT_FORMATION: 0,
    CHANGEMENT_GROUPE: 0, SUSPENSION: 0, RADIATION: 0, ABANDON: 0,
    DIPLOMATION: 0,
  },
  par_mois: [{ mois: '2026-09', total: 1500 }],
  audit_total: 1158,
  audit_par_action: [
    { action: 'PIECE_DEPOSEE', libelle: 'Pièce déposée', total: 255 },
  ],
  audit_par_objet: [{ objet_type: 'Candidature', total: 228 }],
}

const EVENEMENTS = {
  results: [
    {
      id: 1, type_evenement: 'PASSAGE', type_libelle: 'Passage en année supérieure',
      date_evenement: '2026-09-25', etudiant_id: 7, matricule: 'INJS25-0007',
      etudiant: 'Kouassi Yao', inscription_id: 11,
      formation: 'LICENCE STAPS', niveau: 'L2', annee_academique: '2026-2027',
      ancienne_valeur: '', nouvelle_valeur: 'L2',
      commentaire: '[Reconstitué] Événement déduit de l’inscription.',
      enregistre_par: null, reconstitue: true,
    },
    {
      id: 2, type_evenement: 'SUSPENSION', type_libelle: 'Suspension',
      date_evenement: '2026-09-25', etudiant_id: 8, matricule: 'INJS25-0008',
      etudiant: 'Fati Bamba', inscription_id: 12,
      formation: 'LICENCE STAPS', niveau: 'L2', annee_academique: '2026-2027',
      ancienne_valeur: 'Inscrite', nouvelle_valeur: 'Suspendue',
      commentaire: 'Décision du conseil de discipline.',
      enregistre_par: 'secretariat', reconstitue: false,
    },
  ],
  count: 1872, total_pages: 75, page: 1, page_size: 25,
}

const AUDIT = {
  results: [
    {
      id: 1, action: 'PIECE_DEPOSEE', action_libelle: 'Pièce déposée',
      objet_type: 'PieceCandidature', objet_id: 12,
      objet_libelle: 'CNI — Jean-Marie', acteur: 'secretariat',
      acteur_label: 'secretariat', ancienne_valeur: '',
      nouvelle_valeur: 'DEPOSEE', commentaire: 'Déposée au portail.',
      timestamp: '2026-09-12T08:30:00+00:00',
    },
  ],
  count: 1158, total_pages: 47, page: 1, page_size: 25,
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/scolarite/journal/stats/', () => STATS)
  apiController.setRoute('/scolarite/journal/evenements/', () => EVENEMENTS)
  apiController.setRoute('/scolarite/journal/audit/', () => AUDIT)
  apiController.setRoute('/scolarite/etudiants/', () => ({
    results: [{ id: 7, matricule: 'INJS25-0007', nom_complet: 'Kouassi Yao' }],
    count: 1, total_pages: 1,
  }))
}

const mount = () => {
  const me = makeUser('SECRETARIAT', { username: 'secretariat' })
  apiController.setMe(me)
  return renderWithProviders(<JournalScolarite />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/scolarite/journal'],
  })
}

const dernierParams = (chemin) => {
  const appels = apiMock.get.mock.calls.filter(([p]) => p === chemin)
  return appels.length ? appels[appels.length - 1][1]?.params : undefined
}

beforeEach(preparer)

describe('Journal de scolarité — écran premium', () => {
  it('affiche le panorama et la chronologie, événements reconstitués distingués', async () => {
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toMatch(/1\s*872/))
    expect(screen.getByText(/25 septembre 2026/i)).toBeInTheDocument()
    expect(container.querySelector('.jou-type')?.textContent).toContain('Passage en année supérieure')
    expect(screen.getByText('Reconstitué')).toBeInTheDocument()
    expect(screen.getByText('par secretariat')).toBeInTheDocument()
    expect(screen.getByText('Décision du conseil de discipline.')).toBeInTheDocument()
    // Le commentaire technique des lignes reconstituées n'est pas affiché.
    expect(container.textContent).not.toContain('Événement déduit')
    expect(screen.getByRole('link', { name: /INJS25-0007/ })).toHaveAttribute(
      'href', '/scolarite/etudiants/7',
    )
    expect(container.textContent).toMatch(/1\s*158/)
  })

  it('filtre la chronologie par type d’événement côté serveur', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByText(/25 septembre 2026/i)).toBeInTheDocument())
    await user.click(screen.getByRole('button', { name: /^Redoublement/ }))
    await waitFor(() => {
      expect(dernierParams('/scolarite/journal/evenements/')?.type_evenement).toBe('REDOUBLEMENT')
    })
    expect(dernierParams('/scolarite/journal/evenements/')?.page).toBe(1)
  })

  it('pagine la chronologie côté serveur', async () => {
    const user = userEvent.setup()
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toMatch(/sur 75/))
    await user.click(screen.getByRole('button', { name: /Suivant/ }))
    await waitFor(() => {
      expect(dernierParams('/scolarite/journal/evenements/')?.page).toBe(2)
    })
  })

  it('bascule vers la traçabilité avec horodatage JJ/MM/AAAA heure réelle', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByText(/25 septembre 2026/i)).toBeInTheDocument())
    await user.click(screen.getByRole('tab', { name: /Traçabilité des opérations/ }))
    await waitFor(() => expect(screen.getByText('12/09/2026 08:30')).toBeInTheDocument())
    expect(screen.getAllByText('Pièce déposée').length).toBeGreaterThan(0)
    expect(screen.getByText('CNI — Jean-Marie')).toBeInTheDocument()
    expect(screen.getByLabelText('Action')).toBeInTheDocument()
  })

  it('enregistre un événement manuel sur le dossier d’un étudiant', async () => {
    const user = userEvent.setup()
    mount()
    await waitFor(() => expect(screen.getByText(/25 septembre 2026/i)).toBeInTheDocument())
    await user.type(screen.getByLabelText(/Étudiant \*/), 'Kouassi')
    const proposition = await screen.findByRole('button', { name: /Kouassi Yao/ })
    await user.click(proposition)
    await user.selectOptions(screen.getByLabelText(/Type d’événement \*/), 'SUSPENSION')
    await user.type(screen.getByLabelText('Commentaire'), 'Conseil de discipline')
    await user.click(screen.getByRole('button', { name: /^Enregistrer$/ }))
    await waitFor(() => {
      const appels = apiMock.post.mock.calls
      const dernier = appels[appels.length - 1]
      expect(dernier[0]).toBe('/scolarite/etudiants/7/evenements/')
      expect(dernier[1]).toMatchObject({
        type_evenement: 'SUSPENSION', commentaire: 'Conseil de discipline',
      })
    })
  })
})
