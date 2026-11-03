/**
 * Hub Finances étudiantes premium : barème indicatif inactif affiché
 * comme tel, montants FCFA, situation par étudiant.
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

import { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import FinancesHub from '@/pages/finances/FinancesHub'

const SPC = (s) => s.replace(/,/g, ' ') // espaces fines Intl fr

const STATS = {
  tarifications_actives: 0, tarifications_inactives: 80, echeanciers: 60,
  montant_attendu: 12300000, montant_lignes_payees: 0,
  montant_reste: 12300000, factures: 30,
  factures_par_statut: { BROUILLON: 30 }, paiements: 40,
  paiements_par_statut: { INITIE: 20, EN_ATTENTE: 20 },
  montant_encaisse_confirme: 0, quittances: 0, remboursements: 4,
  relances: 12, rapprochements: 1,
}

const BAREME = {
  results: [
    {
      id: 1, formation: 'LICENCE STAPS', niveau: 'Tous niveaux',
      nature: 'SCOLARITE', nature_display: 'Frais de scolarité',
      montant_base: 150000, devise: 'XOF', actif: false,
    },
  ],
}

const SITUATION = {
  results: [
    {
      id: 1, etudiant_id: 5, matricule: 'INJS26-0005',
      nom_complet: 'Koffi Jean', annee: '2026-2027', nb_lignes: 5,
      total: 205000, paye: 0, reste: 205000, statut_global: 'IMPAYE',
    },
  ],
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/finances-etudiantes/hub/stats/', () => STATS)
  apiController.setRoute('/finances-etudiantes/hub/tarifications/', () => BAREME)
  apiController.setRoute('/finances-etudiantes/hub/echeanciers/', () => SITUATION)
  apiController.setRoute('/finances-etudiantes/hub/factures/', () => ({ results: [] }))
  apiController.setRoute('/finances-etudiantes/hub/paiements/', () => ({ results: [] }))
  apiController.setRoute('/finances-etudiantes/hub/quittances/', () => ({ results: [] }))
  apiController.setRoute('/finances-etudiantes/hub/remboursements/', () => ({ results: [] }))
  apiController.setRoute('/finances-etudiantes/hub/relances/', () => ({ results: [] }))
}

const mount = () => {
  const me = makeUser('FINANCE', { username: 'finance' })
  apiController.setMe(me)
  return renderWithProviders(<FinancesHub ongletInitial="bareme" />, {
    authUser: me, routePattern: '*', initialEntries: ['/finances-etudiantes/frais'],
  })
}

beforeEach(preparer)

describe('Hub Finances étudiantes premium', () => {
  it('affiche le barème indicatif inactif et l’absence d’encaissement', async () => {
    const { container } = mount()
    await waitFor(() => {
      expect(screen.getAllByText((t) => t.includes('150') && t.includes('FCFA')).length).toBeGreaterThan(0)
    })
    expect(container.textContent).toContain('Aucun barème officiel actif')
    expect(container.textContent).toContain('Encaissé et confirmé : 0 FCFA')
    expect(container.textContent).toContain('Frais de scolarité')
    expect(container.textContent).toContain('Non')
  })

  it('affiche la situation financière avec reste à payer', async () => {
    const user = userEvent.setup()
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toContain('LICENCE STAPS'))
    await user.click(screen.getByRole('tab', { name: /Situation financière/ }))
    await waitFor(() => {
      expect(screen.getByText('Impayé')).toBeInTheDocument()
    })
    expect(screen.getByRole('link', { name: /INJS26-0005/ })).toHaveAttribute(
      'href', '/scolarite/etudiants/5',
    )
    expect(SPC(container.textContent)).toBeTruthy()
  })
})
