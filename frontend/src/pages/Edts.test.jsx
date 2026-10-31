import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Edts from './Edts'

const EDT = {
  id: 7,
  titre: 'EDT FORMATION DÉMONSTRATION GET-INJS — L1 DEMO-G4',
  population_label: 'FORMATION DÉMONSTRATION GET-INJS — L1 DEMO-G4',
  annee_academique: 'DEMO-2026-2027',
  semaine_debut: 1,
  semaine_fin: 4,
  affectations_count: 3,
  statut: 'BROUILLON',
}

const GRILLE = {
  emploi_du_temps: EDT,
  semaine: 1,
  creneaux: [],
  jours: [],
  seances: [],
  conflits: [],
}

function monter() {
  apiController.setMe(makeUser('ADMIN'))
  apiController.setRoute('/edts/emplois/', [EDT])
  apiController.setRoute('/edts/emplois/7/', EDT)
  apiController.setRoute('/edts/emplois/7/grille/', GRILLE)
  apiController.setRoute('/edts/affectations/', [])
  apiController.setRoute('/edts/conflits/', [])
  apiController.setRoute('/scolarite/ref/annees/', [])
  apiController.setRoute('/edts/creneaux-types/', [])
  apiController.setRoute('/edts/referentiel-enseignants/', [])
  return render(
    <AllProviders authUser={makeUser('ADMIN')} initialEntries={['/edt']} routePattern="/edt">
      <Edts />
    </AllProviders>,
  )
}

describe('Edts — liste des emplois du temps', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche le titre et la ligne secondaire (année · semaines · créneaux)', async () => {
    monter()
    // Le titre apparaît deux fois : dans la liste et dans le panneau de détail.
    expect((await screen.findAllByText(EDT.titre)).length).toBeGreaterThan(0)
    const ligne = screen.getByText(/DEMO-2026-2027 · s1–s4 · 3 créneaux/)
    expect(ligne).toBeInTheDocument()
    // Régression de capture d'écran : la ligne secondaire doit rester un bloc,
    // sinon elle se collait au titre une fois la ligne sélectionnée.
    expect(ligne.className).toMatch(/\bd-block\b/)
  })

  it('garde `d-block` sur la ligne secondaire après sélection de l’EDT', async () => {
    const utilisateur = userEvent.setup()
    monter()
    const bouton = await screen.findByRole('button', { name: new RegExp(EDT.titre.slice(4, 20)) })
    await utilisateur.click(bouton)
    await waitFor(() => expect(apiController.findCall('get', '/edts/emplois/7/')).toBeTruthy())
    const ligne = screen.getByText(/DEMO-2026-2027 · s1–s4 · 3 créneaux/)
    expect(ligne.className).toMatch(/\bd-block\b/)
  })
})
