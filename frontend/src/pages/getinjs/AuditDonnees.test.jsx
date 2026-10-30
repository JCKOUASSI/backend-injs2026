import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import AuditDonnees from './AuditDonnees'

const ANNEES = [{ id: 1, libelle: '2026-2027', courante: true }]

const CONTRAINTES = {
  dures: [
    { code: 'C1', libelle: 'Un enseignant ne peut pas assurer deux séances simultanément.' },
    { code: 'C2', libelle: 'Un groupe ne peut pas suivre deux séances simultanément.' },
  ],
  avertissements: ['Préférence horaire de l’enseignant'],
  capacite_inconnue: 'Une salle sans capacité renseignée n’est jamais considérée comme suffisante.',
}

const AUDIT_OK = {
  statut: 'OK',
  generable: true,
  controles: [
    { niveau: 'OK', code: 'CANEVAS_HORAIRE_OK', message: '24 créneaux type(s).', action_recommandee: '' },
  ],
  resume: { ok: 1, warning: 0, blocking: 0 },
}

const AUDIT_BLOQUE = {
  statut: 'BLOCKING',
  generable: false,
  controles: [
    {
      niveau: 'BLOCKING',
      code: 'AFFECTATIONS_PEDAGOGIQUES_VIDES',
      message: 'Aucun besoin calculable pour l’année.',
      action_recommandee: 'Saisir les affectations pédagogiques.',
    },
    {
      niveau: 'WARNING',
      code: 'CAPACITE_INCONNUE',
      message: '2 salle(s) sans capacité renseignée.',
      action_recommandee: 'Renseigner la capacité des salles.',
    },
  ],
  resume: { ok: 0, warning: 1, blocking: 1 },
}

describe('AuditDonnees', () => {
  beforeEach(() => {
    apiController.reset()
    apiController.setRoute(/\/scolarite\/ref\/annees\/$/, { results: ANNEES })
    apiController.setRoute(/\/edts\/lmd\/constraints\/$/, CONTRAINTES)
  })

  const monter = () => render(
    <AllProviders user={makeUser('DIRECTION')}>
      <AuditDonnees />
    </AllProviders>,
  )

  it('affiche les contrôles réels et confirme la génération quand tout est OK', async () => {
    apiController.setRoute(/\/edts\/lmd\/audit\//, AUDIT_OK)
    monter()

    await waitFor(() => expect(screen.getByText(/Génération possible/i)).toBeInTheDocument())
    expect(screen.getByText('CANEVAS_HORAIRE_OK')).toBeInTheDocument()
    expect(screen.getByText(/1 OK/)).toBeInTheDocument()
  })

  it('annonce clairement une génération impossible et expose les actions recommandées', async () => {
    apiController.setRoute(/\/edts\/lmd\/audit\//, AUDIT_BLOQUE)
    monter()

    await waitFor(() => expect(screen.getByText(/Génération impossible en l’état/i)).toBeInTheDocument())
    expect(screen.getByText('AFFECTATIONS_PEDAGOGIQUES_VIDES')).toBeInTheDocument()
    expect(screen.getByText('Saisir les affectations pédagogiques.')).toBeInTheDocument()
    expect(screen.getByText(/1 bloquant/)).toBeInTheDocument()
  })

  it('rappelle les contraintes dures C1/C2 séparées des préférences', async () => {
    apiController.setRoute(/\/edts\/lmd\/audit\//, AUDIT_OK)
    monter()

    await waitFor(() => expect(screen.getByText('Contraintes appliquées par le moteur')).toBeInTheDocument())
    expect(screen.getByText(/Un groupe ne peut pas suivre deux séances simultanément/)).toBeInTheDocument()
    expect(screen.getByText(/Préférences \(non bloquantes\)/)).toBeInTheDocument()
  })

  it('affiche l’erreur serveur plutôt qu’un écran vide', async () => {
    apiController.setRoute(/\/edts\/lmd\/audit\//, () =>
      Promise.reject({ response: { status: 404, data: { detail: 'Année académique introuvable' } } }))
    monter()

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/Année académique introuvable/)).toBeInTheDocument()
  })
})
