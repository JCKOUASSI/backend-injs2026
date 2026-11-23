/* Test — source « Présences » de la cloche (rapport de refonte, écart n°2).
   L'alerte d'absence née d'une clôture de séance LMD arrive dans l'inbox
   /stats/notifications/recues/ et le marquage lu PATCH le même endpoint. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('../services/api', () => {
  const get = vi.fn()
  const patch = vi.fn()
  return { default: { get, patch } }
})

import api from '../services/api'
import AppNotificationsBell from './AppNotificationsBell'

function reponseBell(id = 1) {
  return Promise.resolve({
    data: {
      notifications: [{
        id, message: 'Absences critique : MAT000 — taux de présence 0 % (séance LMD « Physique »)',
        niveau: 'CRITIQUE', lu: false, created_at: '2026-09-15T10:00:00Z',
        matricule: 'MAT000', seance: 'Physique appliquée',
      }],
      non_lues: 1,
    },
  })
}

describe('AppNotificationsBell — source Présences', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    api.get.mockImplementation((url) => {
      if (url === '/stats/notifications/recues/') return reponseBell()
      return Promise.resolve({ data: { notifications: [] } })
    })
    api.patch.mockResolvedValue({ data: { marquees: 1 } })
  })

  it('ne charge la source présences que si showPresences', async () => {
    render(<MemoryRouter><AppNotificationsBell /></MemoryRouter>)
    // Aucune source activée : la cloche ne doit appeler aucun endpoint.
    await new Promise((r) => setTimeout(r, 0))
    expect(api.get).not.toHaveBeenCalled()
  })

  it('affiche l’alerte d’absence LMD et le badge de non-lues', async () => {
    render(<MemoryRouter><AppNotificationsBell showPresences /></MemoryRouter>)
    await waitFor(() => expect(api.get).toHaveBeenCalledWith('/stats/notifications/recues/'))
    fireEvent.click(screen.getByTitle('Notifications'))
    expect(await screen.findByText('Présences')).toBeInTheDocument()
    expect(screen.getByText(/taux de présence 0 %/)).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument() // badge non lues
  })

  it('marque lue via le PATCH de la source présences', async () => {
    render(<MemoryRouter><AppNotificationsBell showPresences /></MemoryRouter>)
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    fireEvent.click(screen.getByTitle('Notifications'))
    fireEvent.click(await screen.findByText(/taux de présence 0 %/))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/stats/notifications/recues/', { ids: [1] },
    ))
  })

  it('« Tout marquer lu » PATCH {tout:true}', async () => {
    render(<MemoryRouter><AppNotificationsBell showPresences /></MemoryRouter>)
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    fireEvent.click(screen.getByTitle('Notifications'))
    fireEvent.click(await screen.findByText('Tout marquer lu'))
    await waitFor(() => expect(api.patch).toHaveBeenCalledWith(
      '/stats/notifications/recues/', { tout: true },
    ))
  })
})
