/**
 * LOT 26 — Finances étudiantes (`pages/scolarite/FinancesEtudiantes.jsx`).
 * Domaine finance qui écrit : échéanciers (lecture), paiements (liste,
 * création idempotente via transaction_externe, confirmation sous
 * window.confirm avec preuve exigée), gating FINANCE/DIRECTION/SECRÉTARIAT,
 * badges de statut, états de chargement/vide/erreur.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, act, within, fireEvent, waitFor } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { flushPromises } from '@/test/utils/async'
import { makeUser } from '@/test/utils/factories'
import FinancesEtudiantes from '@/pages/scolarite/FinancesEtudiantes'

const ECH_PATH = '/finances-etudiantes/echeanciers/'
const PA_PATH = '/finances-etudiantes/paiements/'

/* ------------------------------------------------------------------ */
/* Jeux de données                                                      */
/* ------------------------------------------------------------------ */

// Une valeur de statut global inconnue exerce le badge de repli (secondary).
const echeanciers = [
  { id: 1, etudiant_id: 101, annee_academique: '2025-2026', statut_global: 'IMPAYE', lignes_count: 3 },
  { id: 2, etudiant_id: 102, annee_academique: '2025-2026', statut_global: 'PARTIELLEMENT_PAYE', lignes_count: 4 },
  { id: 3, etudiant_id: 103, annee_academique: '2025-2026', statut_global: 'COMPLETE', lignes_count: 2 },
  { id: 4, etudiant_id: 104, annee_academique: '2025-2026', statut_global: 'STATUT_BIZARRE', lignes_count: 1 },
]

const paiements = [
  { id: 5001, etudiant_id: 101, nature: 'DOSSIER', montant: 5000, devise: 'XOF', mode: 'CAISSE', statut: 'INITIE', date: '2026-09-01T10:00:00', transaction_externe: 'CAISSE-1' },
  { id: 5002, etudiant_id: 102, nature: 'SCOLARITE', montant: 150000, devise: 'XOF', mode: 'MTN_MONEY', statut: 'EN_ATTENTE', date: '2026-09-02T11:30:00', transaction_externe: 'MTN-2' },
  { id: 5003, etudiant_id: 103, nature: 'INSCRIPTION', montant: 25000, devise: 'XOF', mode: 'VIREMENT', statut: 'CONFIRME', date: '2026-09-03T09:15:00', transaction_externe: 'VIR-3' },
  { id: 5004, candidat_id: 900, nature: 'DOSSIER', montant: 5000, devise: 'XOF', mode: 'CAISSE', statut: 'ECHOUE', date: '2026-09-04T14:00:00', transaction_externe: '' },
  { id: 5005, nature: 'EXAMEN', montant: 2000, devise: 'XOF', mode: 'CAISSE', statut: 'RAPPROCHE', date: '2026-09-05T16:00:00', transaction_externe: 'RAP-5' },
]

/* ------------------------------------------------------------------ */
/* Helpers                                                              */
/* ------------------------------------------------------------------ */

const settle = async (n = 5) => { await act(async () => { await flushPromises(n) }) }

const mount = (role = 'ADMIN') => {
  const me = makeUser(role, { username: role.toLowerCase() })
  apiController.setMe(me)
  return renderWithProviders(<FinancesEtudiantes />, {
    authUser: me,
    routePattern: '/scolarite/finances',
    initialEntries: ['/scolarite/finances'],
  })
}

const goPaiements = () => fireEvent.click(screen.getByRole('button', { name: 'Paiements' }))
const rowFor = (id) => screen.getByText(String(id)).closest('tr')

// Les libellés ne sont pas reliés par htmlFor : champ du même .col que le label.
const formBox = () => screen.getByText(/enregistrer un paiement/i).closest('.card')
const formField = (labelRegex) => {
  const label = within(formBox()).getByText((_c, el) => el.tagName === 'LABEL' && labelRegex.test(el.textContent))
  // Le libellé et le champ sont frères dans la même div .col-md-*.
  return label.parentElement.querySelector('input, select')
}

const getCalls = (method, prefix) =>
  apiMock[method].mock.calls.filter(([p]) => typeof p === 'string' && p.startsWith(prefix)).length

/* ------------------------------------------------------------------ */
/* LOT 26 — chargement et onglet Échéanciers                           */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/FinancesEtudiantes.jsx — chargement et échéanciers (LOT 26)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    // Échéanciers en objet paginé, paiements en tableau nu : les deux
    // normalisations (data.results || data) sont ainsi exercées.
    apiController.setRoute(ECH_PATH, () => ({ results: echeanciers }))
    apiController.setRoute(PA_PATH, () => paiements)
  })

  it('charge les deux ressources au montage et affiche titre, onglets et bouton Actualiser', async () => {
    mount()
    await settle()
    expect(screen.getByRole('heading', { name: /finances étudiantes/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Échéanciers' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Paiements' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /actualiser/i })).toBeInTheDocument()
    expect(apiMock.get).toHaveBeenCalledWith(ECH_PATH)
    expect(apiMock.get).toHaveBeenCalledWith(PA_PATH)
  })

  it("affiche d'abord le spinner puis les échéanciers avec leurs badges", async () => {
    const { container } = mount()
    expect(container.querySelector('.spinner-border')).toBeTruthy()
    await settle()

    expect(screen.getByText('Étudiant #101')).toBeInTheDocument()
    expect(screen.getAllByText('2025-2026').length).toBeGreaterThan(0)
    expect(screen.getByText('IMPAYE')).toHaveClass('text-bg-danger')
    expect(screen.getByText('PARTIELLEMENT_PAYE')).toHaveClass('text-bg-warning')
    expect(screen.getByText('COMPLETE')).toHaveClass('text-bg-success')
    // Statut inconnu : badge de repli secondaire.
    expect(screen.getByText('STATUT_BIZARRE')).toHaveClass('text-bg-secondary')
    // lignes_count affiché.
    expect(within(screen.getByText('Étudiant #101').closest('tr')).getByText('3')).toBeInTheDocument()
  })

  it("affiche l'état vide quand il n'y a aucun échéancier", async () => {
    apiController.reset()
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(ECH_PATH, () => ({ results: [] }))
    apiController.setRoute(PA_PATH, () => [])
    renderWithProviders(<FinancesEtudiantes />, {
      authUser: me, routePattern: '/scolarite/finances', initialEntries: ['/scolarite/finances'],
    })
    await settle()
    expect(screen.getByText('Aucun échéancier.')).toBeInTheDocument()
  })

  it("notifie le message d'erreur serveur au chargement", async () => {
    apiController.reset()
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(ECH_PATH, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: { error: 'Maintenance du module finance' } } }
    })
    apiController.setRoute(PA_PATH, () => paiements)
    renderWithProviders(<FinancesEtudiantes />, {
      authUser: me, routePattern: '/scolarite/finances', initialEntries: ['/scolarite/finances'],
    })
    expect(await screen.findByText('Maintenance du module finance')).toBeInTheDocument()
  })

  it("notifie un message générique quand l'erreur de chargement n'a pas de détail", async () => {
    apiController.reset()
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(ECH_PATH, () => {
      // eslint-disable-next-line no-throw-literal
      throw { response: { data: {} } }
    })
    apiController.setRoute(PA_PATH, () => paiements)
    renderWithProviders(<FinancesEtudiantes />, {
      authUser: me, routePattern: '/scolarite/finances', initialEntries: ['/scolarite/finances'],
    })
    expect(await screen.findByText('Chargement des finances étudiantes impossible.')).toBeInTheDocument()
  })

  it("navigue d'un onglet à l'autre et revient aux échéanciers", async () => {
    mount()
    await settle()
    // Onglet initial : échéanciers.
    expect(screen.getByText('Étudiant #101')).toBeInTheDocument()
    goPaiements()
    expect(screen.getByRole('columnheader', { name: 'Référence' })).toBeInTheDocument()
    // Retour à l'onglet Échéanciers.
    fireEvent.click(screen.getByRole('button', { name: 'Échéanciers' }))
    expect(screen.getByText('Étudiant #101')).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Référence' })).not.toBeInTheDocument()
  })

  it('recharge les deux ressources au clic sur Actualiser', async () => {
    mount()
    await settle()
    const avant = getCalls('get', ECH_PATH)
    fireEvent.click(screen.getByRole('button', { name: /actualiser/i }))
    await settle()
    expect(getCalls('get', ECH_PATH)).toBe(avant + 1)
    expect(getCalls('get', PA_PATH)).toBeGreaterThan(avant)
  })
})

/* ------------------------------------------------------------------ */
/* LOT 26 — onglet Paiements : lecture                                 */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/FinancesEtudiantes.jsx — onglet Paiements en lecture (LOT 26)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute(ECH_PATH, () => ({ results: echeanciers }))
    apiController.setRoute(PA_PATH, () => paiements)
  })

  it('affiche le spinner de l’onglet puis toutes les colonnes et les lignes', async () => {
    const { container } = mount()
    // Bascule immédiatement, pendant le chargement initial.
    goPaiements()
    expect(container.querySelector('.spinner-border')).toBeTruthy()
    await settle()

    for (const h of ['ID', 'Étudiant', 'Nature', 'Montant', 'Mode', 'Statut', 'Date', 'Référence', 'Action']) {
      expect(screen.getByRole('columnheader', { name: h })).toBeInTheDocument()
    }
    // Étudiant, candidat et cas sans identifiant.
    expect(within(rowFor(5001)).getByText('Étudiant #101')).toBeInTheDocument()
    expect(within(rowFor(5004)).getByText('Candidat #900')).toBeInTheDocument()
    expect(within(rowFor(5005)).getByText('—')).toBeInTheDocument()
    // Montant + devise, mode, référence.
    expect(within(rowFor(5001)).getByText('5000 XOF')).toBeInTheDocument()
    expect(within(rowFor(5002)).getByText('MTN_MONEY')).toBeInTheDocument()
    expect(within(rowFor(5001)).getByText('CAISSE-1')).toBeInTheDocument()
    // Référence absente : tiret.
    expect(within(rowFor(5004)).getAllByText('—').length).toBeGreaterThan(0)
  })

  it('badges les statuts de paiement selon la table de couleurs', async () => {
    mount()
    await settle()
    goPaiements()
    expect(within(rowFor(5001)).getByText('INITIE')).toHaveClass('text-bg-secondary')
    expect(within(rowFor(5002)).getByText('EN_ATTENTE')).toHaveClass('text-bg-info')
    expect(within(rowFor(5003)).getByText('CONFIRME')).toHaveClass('text-bg-success')
    expect(within(rowFor(5004)).getByText('ECHOUE')).toHaveClass('text-bg-warning')
    expect(within(rowFor(5005)).getByText('RAPPROCHE')).toHaveClass('text-bg-primary')
  })

  it("ne propose Confirmer que pour les statuts INITIE et EN_ATTENTE", async () => {
    mount()
    await settle()
    goPaiements()
    expect(within(rowFor(5001)).getByRole('button', { name: 'Confirmer' })).toBeInTheDocument()
    expect(within(rowFor(5002)).getByRole('button', { name: 'Confirmer' })).toBeInTheDocument()
    expect(within(rowFor(5003)).queryByRole('button', { name: 'Confirmer' })).not.toBeInTheDocument()
    expect(within(rowFor(5004)).queryByRole('button', { name: 'Confirmer' })).not.toBeInTheDocument()
  })

  it("affiche l'état vide quand il n'y a aucun paiement", async () => {
    apiController.reset()
    const me = makeUser('ADMIN', { username: 'admin' })
    apiController.setMe(me)
    apiController.setRoute(ECH_PATH, () => ({ results: [] }))
    apiController.setRoute(PA_PATH, () => [])
    renderWithProviders(<FinancesEtudiantes />, {
      authUser: me, routePattern: '/scolarite/finances', initialEntries: ['/scolarite/finances'],
    })
    await settle()
    goPaiements()
    expect(screen.getByText('Aucun paiement.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 26 — enregistrement d'un paiement                               */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/FinancesEtudiantes.jsx — enregistrement de paiement (LOT 26)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute(ECH_PATH, () => ({ results: echeanciers }))
    apiController.setRoute(PA_PATH, () => paiements)
  })

  it('crée un paiement (POST exact), notifie, réinitialise le formulaire et recharge', async () => {
    mount()
    await settle()
    goPaiements()

    fireEvent.change(formField(/étudiant id/i), { target: { value: '101' } })
    fireEvent.change(formField(/^Nature/i), { target: { value: 'SCOLARITE' } })
    fireEvent.change(formField(/^Montant/i), { target: { value: '150000' } })
    // La devise est un champ texte libre (XOF par défaut) : on l'édite.
    fireEvent.change(formField(/^Devise/i), { target: { value: 'EUR' } })
    fireEvent.change(formField(/^Mode/i), { target: { value: 'MTN_MONEY' } })
    fireEvent.change(formField(/transaction/i), { target: { value: 'MTN-NEW-42' } })

    fireEvent.click(within(formBox()).getByRole('button', { name: 'OK' }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(PA_PATH, {
        etudiant_id: '101', nature: 'SCOLARITE', montant: '150000', devise: 'EUR',
        mode: 'MTN_MONEY', transaction_externe: 'MTN-NEW-42',
      }),
    )
    expect(await screen.findByText(/Paiement enregistré/)).toBeInTheDocument()
    // Formulaire réinitialisé. NB: jest-dom traduit un <input type=number>
    // vide en valeur null ; seul le champ texte transaction reste ''.
    expect(formField(/étudiant id/i)).toHaveValue(null)
    expect(formField(/^Montant/i)).toHaveValue(null)
    expect(formField(/transaction/i)).toHaveValue('')
    expect(formField(/^Nature/i)).toHaveValue('DOSSIER')
    // La liste est rechargée.
    expect(getCalls('get', PA_PATH)).toBeGreaterThanOrEqual(2)
  })

  it("notifie le détail d'une erreur serveur à la création", async () => {
    mount()
    await settle()
    goPaiements()
    fireEvent.change(formField(/étudiant id/i), { target: { value: '101' } })
    fireEvent.change(formField(/^Montant/i), { target: { value: '5000' } })
    fireEvent.change(formField(/transaction/i), { target: { value: 'DUP-1' } })
    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Doublon bloqué par le serveur' } } })
    fireEvent.click(within(formBox()).getByRole('button', { name: 'OK' }))
    expect(await screen.findByText('Doublon bloqué par le serveur')).toBeInTheDocument()
  })

  it("notifie un message générique quand la création échoue sans détail", async () => {
    mount()
    await settle()
    goPaiements()
    fireEvent.change(formField(/étudiant id/i), { target: { value: '101' } })
    fireEvent.change(formField(/^Montant/i), { target: { value: '5000' } })
    fireEvent.change(formField(/transaction/i), { target: { value: 'X-2' } })
    apiMock.post.mockRejectedValueOnce(new Error('réseau'))
    fireEvent.click(within(formBox()).getByRole('button', { name: 'OK' }))
    expect(await screen.findByText('Enregistrement du paiement impossible.')).toBeInTheDocument()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 26 — confirmation d'un paiement                                 */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/FinancesEtudiantes.jsx — confirmation de paiement (LOT 26)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute(ECH_PATH, () => ({ results: echeanciers }))
    apiController.setRoute(PA_PATH, () => paiements)
  })

  it("n'envoie rien si la confirmation native est annulée", async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false)
    mount()
    await settle()
    goPaiements()
    fireEvent.click(within(rowFor(5001)).getByRole('button', { name: 'Confirmer' }))
    expect(confirmSpy).toHaveBeenCalledTimes(1)
    expect(confirmSpy.mock.calls[0][0]).toMatch(/Confirmer le paiement 5001 de 5000 XOF/)
    expect(apiMock.post).not.toHaveBeenCalled()
    confirmSpy.mockRestore()
  })

  it('confirme (POST), notifie la quittance et recharge la liste', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await settle()
    goPaiements()
    fireEvent.click(within(rowFor(5002)).getByRole('button', { name: 'Confirmer' }))
    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith('/finances-etudiantes/paiements/5002/confirmer/'),
    )
    expect(await screen.findByText('Paiement confirmé. Quittance générée.')).toBeInTheDocument()
    expect(getCalls('get', PA_PATH)).toBeGreaterThanOrEqual(2)
    confirmSpy.mockRestore()
  })

  it("notifie le détail d'un échec de confirmation (preuve manquante)", async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await settle()
    goPaiements()
    apiMock.post.mockRejectedValueOnce({ response: { data: { error: 'Preuve de paiement obligatoire' } } })
    fireEvent.click(within(rowFor(5001)).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Preuve de paiement obligatoire')).toBeInTheDocument()
    confirmSpy.mockRestore()
  })

  it("notifie un message générique d'échec de confirmation sans détail", async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true)
    mount()
    await settle()
    goPaiements()
    apiMock.post.mockRejectedValueOnce(new Error('boom'))
    fireEvent.click(within(rowFor(5001)).getByRole('button', { name: 'Confirmer' }))
    expect(await screen.findByText('Confirmation impossible (preuve manquante ?).')).toBeInTheDocument()
    confirmSpy.mockRestore()
  })
})

/* ------------------------------------------------------------------ */
/* LOT 26 — habilitations                                              */
/* ------------------------------------------------------------------ */

describe('pages/scolarite/FinancesEtudiantes.jsx — habilitations (LOT 26)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
    apiController.setRoute(ECH_PATH, () => ({ results: echeanciers }))
    apiController.setRoute(PA_PATH, () => paiements)
  })

  it.each([
    ['FINANCE', true],
    ['DIRECTION', true],
    ['CHEF_INJS_ADMIN', true],
    ['INJS_ADMIN', true],
  ])('rôle %s : formulaire de saisie ET colonne Action (confirmation)', async (role) => {
    mount(role)
    await settle()
    goPaiements()
    expect(screen.getByText(/enregistrer un paiement/i)).toBeInTheDocument()
    expect(screen.getByRole('columnheader', { name: 'Action' })).toBeInTheDocument()
  })

  it.each([
    ['SECRETARIAT'],
    ['CHEF_SECRETARIAT'],
  ])('rôle %s : peut saisir un paiement mais PAS confirmer', async (role) => {
    mount(role)
    await settle()
    goPaiements()
    expect(screen.getByText(/enregistrer un paiement/i)).toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Action' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Confirmer' })).not.toBeInTheDocument()
  })

  it("rôle non financier (ENCADRANT) : lecture stricte, sans formulaire ni action", async () => {
    mount('ENCADRANT')
    await settle()
    goPaiements()
    expect(screen.queryByText(/enregistrer un paiement/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('columnheader', { name: 'Action' })).not.toBeInTheDocument()
    // Les données restent consultables.
    expect(within(rowFor(5001)).getByText('CAISSE-1')).toBeInTheDocument()
  })
})
