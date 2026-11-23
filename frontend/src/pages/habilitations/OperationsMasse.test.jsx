import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import OperationsMasse from './OperationsMasse'

function monter() {
  const user = makeUser('ADMIN')
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { habilitations_admin: ['gerer'] } })
  render(<OperationsMasse />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="/administration/comptes/operations-masse"
                    initialEntries={['/administration/comptes/operations-masse']}>{children}</AllProviders>
    ),
  })
}

function fichierCsv(contenu) {
  const fichier = new File([contenu], 'import.csv', { type: 'text/csv' })
  // jsdom peut ne pas implémenter Blob.text() selon les versions.
  fichier.text = async () => contenu
  return fichier
}

const rapport = {
  total: 2, valides: 1, erreurs: 1, ecriture: false,
  message: 'Aperçu uniquement.',
  lignes: [
    { numero: 1, etat: 'VALIDE', problemes: [], roles: ['ENSEIGNANT'],
      valeurs: { username: 'curp_a', nom: 'Diop', prenoms: 'Moussa', roles: 'ENSEIGNANT' } },
    { numero: 2, etat: 'ERREUR', problemes: ['Mot de passe initial manquant.'],
      valeurs: { username: 'curp_b', nom: 'Ba', prenoms: 'Awa', roles: 'SECRETARIAT' } },
  ],
}

beforeEach(() => {
  cleanup()
  apiController.reset()
  window.localStorage.clear()
})

describe('OperationsMasse — prévisualisation intégrale (écriture en U5)', () => {
  it('affiche le rapport ligne à ligne et interdit l\'écriture', async () => {
    monter()
    apiController.setRoute(/import-simuler\/$/, rapport)
    const csv = 'identifiant;nom;prenoms;mot_de_passe;roles\ncurp_a;Diop;Moussa;secret123;ENSEIGNANT\ncurp_b;Ba;Awa;;SECRETARIAT'
    fireEvent.change(screen.getByTestId('fichier-import'), { target: { files: [fichierCsv(csv)] } })

    expect(await screen.findByTestId('rapport-import')).toBeInTheDocument()
    expect(screen.getByText(/2 ligne\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/1 valide\(s\)/)).toBeInTheDocument()
    expect(screen.getByText(/1 en erreur/)).toBeInTheDocument()
    expect(screen.getByText('Mot de passe initial manquant.')).toBeInTheDocument()
    expect(screen.getByTestId('bouton-ecrire')).toBeDisabled()
  })

  it('envoie au simulateur les lignes parsées avec les en-têtes normalisés', async () => {
    monter()
    apiController.setRoute(/import-simuler\/$/, (path, body) => {
      expect(body.lignes[0]).toMatchObject({
        username: 'curp_a', nom: 'Diop', prenoms: 'Moussa',
        mot_de_passe: 'secret123', roles: 'ENSEIGNANT',
      })
      return rapport
    })
    const csv = 'identifiant,nom,prenoms,mot_de_passe,roles\ncurp_a,Diop,Moussa,secret123,ENSEIGNANT'
    fireEvent.change(screen.getByTestId('fichier-import'), { target: { files: [fichierCsv(csv)] } })
    await waitFor(() => expect(apiMock.post).toHaveBeenCalled())
  })

  it('signale un fichier sans données sans appeler l\'API', async () => {
    monter()
    fireEvent.change(screen.getByTestId('fichier-import'), { target: { files: [fichierCsv('identifiant,nom\n')] } })
    expect(await screen.findByText(/aucune ligne de données/i)).toBeInTheDocument()
    expect(apiController.findCall('post', /import-simuler\/$/)).toBeFalsy()
  })
})
