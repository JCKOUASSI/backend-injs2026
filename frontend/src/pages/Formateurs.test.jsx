/**
 * Tests de l'écran « Enseignants » (page Formateurs, variante corps
 * enseignant) : panorama de couverture des ECUE, grade académique, charge
 * réelle par enseignant et filtre par grade. La variante finance (temps /
 * montants) est couverte ailleurs et inchangée.
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
import Formateurs from '@/pages/Formateurs'

const STATS = {
  enseignants: 67,
  sans_grade: 3,
  grades_disponibles: [
    { id: 2, code: 'PROFESSEUR_TITULAIRE', libelle: 'Professeur Titulaire' },
    { id: 5, code: 'MAITRE_CONFERENCES', libelle: 'Maître de Conférences' },
  ],
  par_grade: [
    { id: 2, code: 'PROFESSEUR_TITULAIRE', libelle: 'Professeur Titulaire', total: 16 },
    { id: 5, code: 'MAITRE_CONFERENCES', libelle: 'Maître de Conférences', total: 16 },
  ],
  par_statut: { Titulaire: 48, Vacataire: 16, 'Non renseigné': 3 },
  couverture: {
    annee_academique: '2026-2027', ecue_total: 779, ecue_couvertes: 779,
    taux_couverture: 100.0, formations_total: 16, formations_couvertes: 16,
    filieres_total: 8, filieres_couvertes: 8, affectations: 779,
    heures_affectees: 12000,
  },
}

const LIGNES = {
  results: [
    {
      id: 10, numerobadge: 'F004', nom: 'KOUASSI', prenom: 'Aya',
      email: 'aya.kouassi@exemple.injs.ci', telephone: '+225 07 07 14 24 34',
      specialite: 'Physiologie de l’exercice', organisation: 'INJS',
      grade_ref: 2,
      grade: { id: 2, code: 'PROFESSEUR_TITULAIRE', libelle: 'Professeur Titulaire' },
      fonction: 'Chef de département', statut_enseignant: 'Titulaire',
      secretariats: [], secretariats_noms: [], nb_formations: 0,
      enseignements: {
        nb_ecue: 14, heures: 210,
        formations: ['ENTRAÎNEMENT SPORTIF — LICENCE'],
      },
    },
    {
      id: 1, numerobadge: 'F001', nom: 'KONÉ', prenom: 'Seydou', email: '',
      telephone: '', specialite: 'Management public', organisation: '',
      grade_ref: null, grade: null, fonction: '', statut_enseignant: '',
      secretariats: [], secretariats_noms: [], nb_formations: 0,
      enseignements: { nb_ecue: 0, heures: 0, formations: [] },
    },
  ],
  count: 67, total_pages: 2, current_page: 1,
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/formations/formateurs/stats/', () => STATS)
  apiController.setRoute('/formations/formateurs/list/', () => LIGNES)
  apiController.setRoute('/formations/ref/modules/', () => [])
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Formateurs />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/formateurs'],
  })
}

beforeEach(preparer)

describe('Enseignants — panorama premium', () => {
  it('affiche la couverture complète des ECUE et les totaux réels', async () => {
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toContain('779/779'))
    expect(container.textContent).toContain('ECUE avec enseignant')
    expect(container.textContent).toMatch(/100 % des maquettes actives/)
    expect(container.textContent).toMatch(/12\s*000 h/)
    expect(container.textContent).toContain('16/16')
    // Total réel (67), pas la taille de la page affichée (2 lignes).
    expect(screen.getByText(/67 enseignants/)).toBeInTheDocument()
    expect(screen.getByText(/67 résultats/)).toBeInTheDocument()
  })

  it('présente grade académique, fonction et charge réelle de chaque enseignant', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('Professeur Titulaire')).toBeInTheDocument())
    expect(screen.getByText('Chef de département')).toBeInTheDocument()
    expect(screen.getByText(/14 ECUE · 210 h/)).toBeInTheDocument()
    expect(screen.getByText('ENTRAÎNEMENT SPORTIF — LICENCE')).toBeInTheDocument()
    expect(screen.getByText(/aya\.kouassi@exemple\.injs\.ci/)).toBeInTheDocument()
    // Enseignant sans affectation : mention honnête, plus de « Modules 0 ».
    expect(screen.getByText('Aucune affectation')).toBeInTheDocument()
    expect(screen.queryByText('Modules')).not.toBeInTheDocument()
  })

  it('filtre la liste par grade côté serveur', async () => {
    const user = userEvent.setup()
    mount()
    const select = await screen.findByLabelText('Filtrer par grade')
    await waitFor(() => expect(screen.getByRole('option', { name: /Professeur Titulaire \(16\)/ })).toBeInTheDocument())
    await user.selectOptions(select, 'PROFESSEUR_TITULAIRE')
    await waitFor(() => {
      const appels = apiMock.get.mock.calls
        .map(([p]) => p)
        .filter((p) => p.startsWith('/formations/formateurs/list/'))
      expect(appels[appels.length - 1]).toContain('grade=PROFESSEUR_TITULAIRE')
    })
  })

  it('propose le grade dans la fiche de création', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Nouvel enseignant/ }))
    expect(await screen.findByText('Grade enseignant')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Maître de Conférences' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Titulaire' })).toBeInTheDocument()
  })
})
