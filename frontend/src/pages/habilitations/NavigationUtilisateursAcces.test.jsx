import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AuthProvider } from '@/context/AuthContext'
import CapabilitiesSync from '@/components/auth/CapabilitiesSync'
import { makeUser } from '@/test/utils/factories'
import { CAPABILITIES_QUERY_KEY, FLAGS_QUERY_KEY } from '@/lib/queryClient'
import NavigationUtilisateursAcces from './NavigationUtilisateursAcces'

function monter(flags, capacites) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  qc.setQueryData(FLAGS_QUERY_KEY, flags)
  qc.setQueryData(CAPABILITIES_QUERY_KEY, {
    role: 'ADMIN', roles: ['ADMIN'], niveau: 'N4', capacites,
  })
  window.localStorage.setItem('access_token', 'jeton-test')
  apiController.setMe(makeUser('ADMIN'))
  apiController.setRoute('/auth/capabilities/', { capacites })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/users']}>
        <AuthProvider>
          <CapabilitiesSync />
          <NavigationUtilisateursAcces />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('NavigationUtilisateursAcces', () => {
  beforeEach(() => {
    cleanup()
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche les sections Profils et CURP si drapeau et capacité sont présents', async () => {
    monter({ 'flag.curp_ui_admin': true }, { habilitations_admin: ['gerer'] })
    expect(await screen.findByRole('link', { name: /Profils/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Comptes/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Rôles/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Matrice des permissions/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Dérogations/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Délégations/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Revue des habilitations/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /File de provisionnement/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Impact module/ })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Journal/ })).toBeInTheDocument()
  })

  it('masque toute entrée CURP si le drapeau est fermé ou absent', async () => {
    monter({}, { habilitations_admin: ['gerer'] })
    expect(await screen.findByRole('link', { name: /Profils/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Comptes/ })).not.toBeInTheDocument()
  })

  it('masque la console si la capacité manque même lorsque le drapeau est ouvert', async () => {
    monter({ 'flag.curp_ui_admin': true }, {})
    expect(await screen.findByRole('link', { name: /Profils/ })).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Comptes/ })).not.toBeInTheDocument()
  })
})