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
import DeplacerSeance from './DeplacerSeance'

const AFFECTATION = {
  id: 42,
  intitule: 'Didactique et Pédagogie STAPS',
  horaire: 'Lundi 08:00–10:00',
  creneau_template_id: 7,
  salle_nom: 'Salle STAPS 101',
  semaine_debut: 1,
  semaine_fin: 10,
}

const CANDIDATS = [
  { creneau_template_id: 8, jour: 'MARDI', heure_debut: '08:00', heure_fin: '10:00', salle_id: 3, salle_nom: 'Salle STAPS 102', salle_capacite: 40 },
  { creneau_template_id: 9, jour: 'JEUDI', heure_debut: '14:00', heure_fin: '16:00', salle_id: 4, salle_nom: 'Amphithéâtre A', salle_capacite: null },
]

describe('DeplacerSeance', () => {
  beforeEach(() => { apiController.reset() })

  const monter = (props = {}) => render(
    <AllProviders user={makeUser('SECRETARIAT')}>
      <DeplacerSeance affectation={AFFECTATION} onClose={vi.fn()} onMoved={vi.fn()} {...props} />
    </AllProviders>,
  )

  it('n’affiche que les positions validées par le moteur', async () => {
    apiController.setRoute('/edts/lmd/items/42/move/', { affectation_id: 42, nb_candidats: 2, candidats: CANDIDATS })
    monter()

    await waitFor(() => expect(screen.getByText(/2 position\(s\) validée\(s\)/)).toBeInTheDocument())
    expect(screen.getByText('Salle STAPS 102')).toBeInTheDocument()
    expect(screen.getByText('Amphithéâtre A')).toBeInTheDocument()
    // Une capacité inconnue reste affichée comme inconnue, jamais « suffisante ».
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('dit clairement qu’aucune position n’est compatible', async () => {
    apiController.setRoute('/edts/lmd/items/42/move/', { candidats: [] })
    monter()

    await waitFor(() => expect(screen.getByText(/Aucune position compatible/)).toBeInTheDocument())
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })

  it('explique qu’un plan déjà invalide bloque tout déplacement', async () => {
    apiController.setRoute('/edts/lmd/items/42/move/', {
      nb_candidats: 0,
      candidats: [],
      plan_valide: false,
      violations_plan: [{ contrainte: 'C8_COHERENCE_PEDAGOGIQUE', message: 'séance sans ancrage pédagogique — C8.' }],
      explication: 'Le plan actuel viole déjà 8 contrainte(s).',
      action_recommandee: 'Corrigez d’abord les séances signalées.',
    })
    monter()

    await waitFor(() => expect(screen.getByText(/plan actuel est déjà en violation/)).toBeInTheDocument())
    expect(screen.getByText(/C8_COHERENCE_PEDAGOGIQUE/)).toBeInTheDocument()
    expect(screen.getByText(/Corrigez d’abord/)).toBeInTheDocument()
    // Le message « aucune position compatible » ne doit pas masquer la cause.
    expect(screen.queryByText(/Aucune position compatible/)).not.toBeInTheDocument()
  })

  it('déplace la séance vers la position choisie', async () => {
    apiController.setRoute('/edts/lmd/items/42/move/', { candidats: CANDIDATS })
    const onMoved = vi.fn()
    monter({ onMoved })

    await waitFor(() => expect(screen.getByText('Salle STAPS 102')).toBeInTheDocument())
    const bouton = screen.getByRole('button', { name: 'Déplacer ici' })
    expect(bouton).toBeDisabled()

    await userEvent.click(screen.getAllByRole('radio')[0])
    await userEvent.click(bouton)

    await waitFor(() => expect(apiMock.post).toHaveBeenCalledWith(
      '/edts/lmd/items/42/move/',
      { creneau_template_id: 8, salle_id: 3 },
    ))
    await waitFor(() => expect(onMoved).toHaveBeenCalled())
  })

  it('affiche un refus 409 comme un refus, avec ses codes de contrainte', async () => {
    // Première requête (GET des candidats) : succès. Deuxième (POST) : refus 409.
    let appels = 0
    apiController.setRoute('/edts/lmd/items/42/move/', () => {
      appels += 1
      if (appels === 1) return { candidats: CANDIDATS }
      return Promise.reject({
        response: {
          status: 409,
          data: {
            accepted: false,
            explication: 'Déplacement refusé : la position demandée viole une contrainte forte.',
            action_recommandee: 'Choisissez un autre créneau compatible.',
            violations: [{ code: 'C1', message: 'Enseignant déjà occupé sur ce créneau.' }],
          },
        },
      })
    })
    const onMoved = vi.fn()
    monter({ onMoved })

    await waitFor(() => expect(screen.getByText('Salle STAPS 102')).toBeInTheDocument())
    await userEvent.click(screen.getAllByRole('radio')[0])
    await userEvent.click(screen.getByRole('button', { name: 'Déplacer ici' }))

    await waitFor(() => expect(screen.getByRole('alert')).toBeInTheDocument())
    expect(screen.getByText(/Déplacement refusé par le moteur/)).toBeInTheDocument()
    expect(screen.getByText(/C1/)).toBeInTheDocument()
    expect(screen.getByText(/Enseignant déjà occupé/)).toBeInTheDocument()
    expect(onMoved).not.toHaveBeenCalled()
  })

  it('ne propose pas la validation si le serveur refuse la liste', async () => {
    apiController.setRoute('/edts/lmd/items/42/move/', () =>
      Promise.reject({ response: { status: 403, data: { detail: 'Planification requise.' } } }))
    monter()

    await waitFor(() => expect(screen.getByText(/Planification requise/)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Déplacer ici' })).toBeDisabled()
  })
})
