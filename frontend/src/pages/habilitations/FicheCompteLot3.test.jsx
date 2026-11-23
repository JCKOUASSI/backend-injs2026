import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import FicheCompte from './FicheCompte'

const COMTE_DE_BASE = {
  id: 1,
  user_id: 42,
  username: 'curp_a',
  email: 'curp_a@injs.ci',
  is_active: true,
  role_legacy: 'SECRETARIAT',
  personne: { prenoms: 'Awa', nom: 'Ba' },
  statut: 'ACTIF',
  canal: 'WEB',
  mfa_actif: false,
  notes: '',
  date_creation: '2026-09-01T00:00:00',
  derniere_connexion: null,
  roles_actifs: [],
  nb_roles: 0,
  nb_roles_sensibles: 0,
  domaines: [],
  roles_inactifs: [],
  derogations: [],
  delegations_recues: [],
  journal: [],
}

const monter = (compte = COMTE_DE_BASE, permissions = {
  compte_id: 1, username: 'curp_a', codes: ['a.b.c', 'd.e.f'], count: 2,
}) => {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', {
    capacites: { habilitations_admin: ['gerer'] },
  })
  apiController.setRoute('/habilitations/comptes/1/', compte)
  apiController.setRoute(
    '/habilitations/comptes/1/effective-permissions/', permissions)
  apiController.setRoute('/auth/mfa/setup/', {
    secret: 'BASE32SECRET',
    otpauth_url: 'otpauth://totp/INJS:curp_a?secret=BASE32SECRET&issuer=INJS',
  })
  apiController.setRoute('/auth/mfa/confirm/', { detail: 'MFA activé.' })
  apiController.setRoute('/auth/mfa/disable/', { detail: 'MFA désactivé.' })
  return renderFiche(user)
}

function renderFiche(authUser) {
  render(<FicheCompte />, {
    wrapper: ({ children }) => (
      <AllProviders
        authUser={authUser}
        routePattern="/administration/comptes/:id"
        initialEntries={['/administration/comptes/1']}
      >
        {children}
      </AllProviders>
    ),
  })
}

describe('pages/habilitations/FicheCompte.jsx — MFA et permissions effectives (LOT 3)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    vi.restoreAllMocks()
  })

  it('affiche les permissions effectives calculées par le backend', async () => {
    monter()
    expect(await screen.findByText(/permissions effectives \(2\)/i)).toBeInTheDocument()
    await userEvent.click(screen.getByText(/afficher les 2 codes/i))
    expect(screen.getByText('a.b.c')).toBeInTheDocument()
    expect(screen.getByText('d.e.f')).toBeInTheDocument()
  })

  it('affiche “aucune permission” quand le compte n’a aucun droit', async () => {
    monter(COMTE_DE_BASE, { compte_id: 1, username: 'curp_a', codes: [], count: 0 })
    expect(await screen.findByText(/permissions effectives \(0\)/i)).toBeInTheDocument()
    expect(screen.getByText(/aucune permission effective/i)).toBeInTheDocument()
  })

  it('active le MFA d’un tiers : armement du secret puis confirmation par code', async () => {
    monter()
    expect(await screen.findByTestId('mfa-activer')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('mfa-activer'))
    expect(screen.getByTestId('mfa-configuration')).toBeInTheDocument()

    await userEvent.click(screen.getByTestId('mfa-generer'))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/auth/mfa/setup/', { compte_id: 42 })
    )
    expect(await screen.findByText('BASE32SECRET')).toBeInTheDocument()
    expect(screen.getByText(/otpauth:\/\/totp/i)).toBeInTheDocument()

    await userEvent.type(screen.getByTestId('mfa-code-confirm'), '654321')
    await userEvent.click(screen.getByTestId('mfa-confirmer'))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/auth/mfa/confirm/', {
        compte_id: 42, code: '654321',
      })
    )
  })

  it('ne permet pas de confirmer sans code complet', () => {
    monter()
    // Le panneau n'est pas ouvert : impossible de confirmer.
    expect(screen.queryByTestId('mfa-confirmer')).not.toBeInTheDocument()
  })

  it('désactive le MFA après confirmation, en ciblant l’utilisateur Django', async () => {
    const compteMfa = { ...COMTE_DE_BASE, mfa_actif: true }
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    monter(compteMfa, { compte_id: 1, username: 'curp_a', codes: [], count: 0 })

    const bouton = await screen.findByTestId('mfa-desactiver')
    expect(screen.getByText(/activé \(totp\)/i)).toBeInTheDocument()

    await userEvent.click(bouton)
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/auth/mfa/disable/', {
        compte_id: 42, code: '',
      })
    )
  })

  it('annule la désactivation quand l’utilisateur refuse', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    const compteMfa = { ...COMTE_DE_BASE, mfa_actif: true }
    monter(compteMfa, { compte_id: 1, username: 'curp_a', codes: [], count: 0 })

    await userEvent.click(await screen.findByTestId('mfa-desactiver'))
    // Après un micro-tick, aucun appel n’a été fait.
    await new Promise((r) => setTimeout(r, 50))
    expect(apiMock.post).not.toHaveBeenCalledWith(
      expect.stringContaining('/auth/mfa/disable/'),
      expect.anything(),
    )
  })
})
