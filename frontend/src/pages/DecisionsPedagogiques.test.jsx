import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within, fireEvent } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import DecisionsPedagogiques from '@/pages/DecisionsPedagogiques'

const FORMATION_ID = '7'
const FORMATION_PATH = `/formations/${FORMATION_ID}/`
const DECISIONS_PATH = `/evaluations/formations/${FORMATION_ID}/decisions/`

const decisions = [
  {
    id: 1, participant_nom: 'Awa Koffi', participant_matricule: 'ETU001',
    moyenne_generale: 14.5, taux_presence: 92, total_heures_prevues: 100, total_heures_presence: 92,
    decision: 'ADMIS', mention: 'BIEN', validee_le: '2026-07-01', validee_par_nom: 'M. le Directeur',
    decision_officielle: { decision: 'ADMIS', autorite: 'officielle', source: 'jurys.DecisionJury' },
  },
  {
    id: 2, participant_nom: 'Jean Yao', participant_matricule: 'ETU002',
    moyenne_generale: 9, taux_presence: 60, total_heures_prevues: 100, total_heures_presence: 60,
    decision: 'AJOURNE', mention: '', validee_le: null, validee_par_nom: null,
    decision_officielle: null,
  },
  {
    id: 3, participant_nom: 'Exclu Test', participant_matricule: 'ETU003',
    moyenne_generale: null, taux_presence: null, total_heures_prevues: 0, total_heures_presence: 0,
    decision: 'EXCLUSION', mention: null, validee_le: null, validee_par_nom: null,
    // L'EXCLUSION officielle (moteur LMD) ne doit jamais être rabattue.
    decision_officielle: { decision: 'EXCLUSION', autorite: 'officielle', source: 'jurys.DecisionJury' },
  },
  {
    id: 4, participant_nom: 'Attente Eleve', participant_matricule: 'ETU004',
    moyenne_generale: 12, taux_presence: 80, total_heures_prevues: 50, total_heures_presence: 40,
    decision: 'EN_ATTENTE', mention: 'PASSABLE', validee_le: null, validee_par_nom: null,
    decision_officielle: { decision: 'ADMIS_RESERVES', autorite: 'officielle', source: 'jurys.DecisionJury' },
  },
]
const criteres = { seuil_admission: 12, taux_presence_min: 80 }

const renderPage = () =>
  renderWithProviders(<DecisionsPedagogiques />, {
    initialEntries: [`/formations/${FORMATION_ID}/decisions`],
    routePattern: '/formations/:formationId/decisions',
  })

const loadRoutes = (decPayload = { decisions, criteres }) => {
  apiController.setRoute(FORMATION_PATH, { id: 7, formation: 'Licence 1 LSF (2025-2026)' })
  apiController.setRoute(new RegExp(`${DECISIONS_PATH}$`), decPayload)
}

describe('pages/DecisionsPedagogiques.jsx — tableau et décisions', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('affiche un indicateur de chargement puis les en-têtes, critères et lignes', async () => {
    loadRoutes()
    renderPage()
    expect(document.querySelector('.spinner')).toBeInTheDocument()

    // Le nom est un fragment de texte interfolié dans le <p> d'en-tête :
    // une expression régulière est requise (la correspondance exacte échoue).
    expect(await screen.findByText(/Licence 1 LSF/)).toBeInTheDocument()
    expect(screen.getByText(/4 étudiants/)).toBeInTheDocument()
    // Critères d'admission issus du backend (dans le paragraphe d'en-tête,
    // car les libellés 12/20 et 80 % existent aussi dans les lignes).
    const entete = screen
      .getByRole('heading', { name: 'Verdicts pédagogiques (opérationnels)' })
      .closest('div')
    expect(within(entete).getByText('12/20')).toBeInTheDocument()
    expect(within(entete).getByText('80%')).toBeInTheDocument()

    // Étudiants, matricules, moyennes, présence, mentions.
    expect(screen.getByText('Awa Koffi')).toBeInTheDocument()
    expect(screen.getByText('ETU002')).toBeInTheDocument()
    expect(screen.getByText('14.5/20')).toBeInTheDocument()
    expect(screen.getByText('9/20')).toBeInTheDocument()
    expect(screen.getByText('92h / 100h')).toBeInTheDocument()
    expect(screen.getByText('Bien')).toBeInTheDocument()
    expect(screen.getByText('Passable')).toBeInTheDocument()

    // Moyenne/présence nulles affichent « — » ; pas de bloc d'heures si 0 h prévue.
    const rowExclu = screen.getByText('Exclu Test').closest('tr')
    expect(within(rowExclu).getAllByText('—').length).toBeGreaterThanOrEqual(3)
    expect(within(rowExclu).queryByText(/h \/ 0h/)).not.toBeInTheDocument()

    // Décision validée manuellement vs « auto ».
    expect(screen.getByTitle('Validée par M. le Directeur')).toBeInTheDocument()
    const rowAjourne = screen.getByText('Jean Yao').closest('tr')
    expect(within(rowAjourne).getByText('auto')).toBeInTheDocument()

    // Lien Retour vers la formation.
    expect(screen.getByRole('link', { name: /retour/i })).toHaveAttribute(
      'href',
      `/formations/${FORMATION_ID}`,
    )
  })

  it('accepte une réponse de décisions directement sous forme de tableau', async () => {
    loadRoutes(decisions) // pas de clé « decisions » ni « criteres »
    renderPage()
    expect(await screen.findByText('Awa Koffi')).toBeInTheDocument()
    // Critères par défaut du frontend.
    const entete = screen.getByRole('heading', { name: 'Verdicts pédagogiques (opérationnels)' }).closest('div')
    expect(within(entete).getByText('12/20')).toBeInTheDocument()
  })

  it('filtre les lignes par décision via les cartes KPI, puis réaffiche tout', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Awa Koffi')

    // Cliquer la carte KPI « Ajourné » (le badge du tableau porte aussi ce
    // libellé : la carte est le premier élément, rendue avant le tableau).
    fireEvent.click(screen.getAllByText('Ajourné')[0])
    expect(screen.getByText('Jean Yao')).toBeInTheDocument()
    expect(screen.queryByText('Awa Koffi')).not.toBeInTheDocument()
    expect(screen.queryByText('Exclu Test')).not.toBeInTheDocument()

    // Second clic : le filtre est retiré.
    fireEvent.click(screen.getAllByText('Ajourné')[0])
    expect(screen.getByText('Awa Koffi')).toBeInTheDocument()
    expect(screen.getByText('Exclu Test')).toBeInTheDocument()
  })

  it('affiche l’état vide quand il n’y a aucune décision', async () => {
    loadRoutes({ decisions: [], criteres })
    renderPage()
    expect(await screen.findByText(/aucune décision/i)).toBeInTheDocument()
    expect(screen.queryByText('Awa Koffi')).not.toBeInTheDocument()
  })

  it('recalcule les décisions (POST), notifie et recharge les données', async () => {
    loadRoutes()
    apiController.setRoute(/recalculer\/$/, { detail: 'Recalcul terminé (12 admis)' })
    renderPage()
    await screen.findByText('Awa Koffi')
    const getCallsBefore = apiMock.get.mock.calls.filter(([p]) => p === DECISIONS_PATH).length

    fireEvent.click(screen.getByRole('button', { name: /recalculer/i }))

    await waitFor(() =>
      expect(apiMock.post).toHaveBeenCalledWith(
        `/evaluations/formations/${FORMATION_ID}/decisions/recalculer/`,
      ),
    )
    expect(await screen.findByText('Recalcul terminé (12 admis)')).toBeInTheDocument()
    await waitFor(() => {
      const after = apiMock.get.mock.calls.filter(([p]) => p === DECISIONS_PATH).length
      expect(after).toBe(getCallsBefore + 1)
    })
  })

  it('ouvre le formulaire d’ajustement puis valide via PATCH et referme', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Awa Koffi')

    // Aucun sélecteur tant qu’on n’édite pas.
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()

    // Ajuster la première ligne (Awa, ADMIS).
    const rowAwa = screen.getByText('Awa Koffi').closest('tr')
    fireEvent.click(within(rowAwa).getByRole('button', { name: /ajuster/i }))

    const select = screen.getByRole('combobox')
    expect(within(rowAwa).getByRole('option', { name: 'Admis' }).selected).toBe(true)

    fireEvent.change(select, { target: { value: 'EXCLUSION' } })

    await waitFor(() =>
      expect(apiMock.patch).toHaveBeenCalledWith('/evaluations/decisions/1/', {
        decision: 'EXCLUSION',
      }),
    )
    expect(await screen.findByText('Décision validée')).toBeInTheDocument()
    // Le formulaire se referme après validation.
    await waitFor(() => expect(screen.queryByRole('combobox')).not.toBeInTheDocument())
  })

  it('annule l’ajustement avec « Fermer » sans rien envoyer', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Jean Yao')
    const row = screen.getByText('Jean Yao').closest('tr')
    fireEvent.click(within(row).getByRole('button', { name: /ajuster/i }))
    expect(screen.getByRole('combobox')).toBeInTheDocument()

    fireEvent.click(within(row).getByRole('button', { name: /fermer/i }))
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(apiMock.patch).not.toHaveBeenCalled()
  })

  it('signale une erreur si le chargement initial échoue', async () => {
    loadRoutes()
    apiMock.get.mockRejectedValueOnce(new Error('réseau'))
    renderPage()
    expect(await screen.findByText('Erreur lors du chargement')).toBeInTheDocument()
    expect(await screen.findByText(/aucune décision/i)).toBeInTheDocument()
  })

  it('signale une erreur si le recalcul échoue (sans fermeture ni rechargement)', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Awa Koffi')
    const getCallsBefore = apiMock.get.mock.calls.filter(([p]) => p === DECISIONS_PATH).length
    apiMock.post.mockRejectedValueOnce(new Error('boom'))

    fireEvent.click(screen.getByRole('button', { name: /recalculer/i }))
    expect(await screen.findByText('Erreur recalcul')).toBeInTheDocument()

    // Pas de rechargement après échec.
    expect(apiMock.get.mock.calls.filter(([p]) => p === DECISIONS_PATH).length).toBe(getCallsBefore)
  })

  it('laisse le formulaire ouvert quand la validation échoue', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Awa Koffi')
    apiMock.patch.mockRejectedValueOnce(new Error('boom'))

    const rowAwa = screen.getByText('Awa Koffi').closest('tr')
    fireEvent.click(within(rowAwa).getByRole('button', { name: /ajuster/i }))
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'AJOURNE' } })

    expect(await screen.findByText('Erreur validation')).toBeInTheDocument()
    // L'édition n'est pas refermée : l'utilisateur peut réessayer.
    expect(screen.getByRole('combobox')).toBeInTheDocument()
  })

  // ── Anti-ambiguïté : verdict opérationnel vs décision officielle ──────
  it('explicite que la page ne montre que des verdicts opérationnels', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Awa Koffi')

    expect(
      screen.getByText(/ne valent pas décision de jury/i),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('columnheader', { name: 'Verdict opérationnel' }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole('columnheader', { name: 'Décision officielle' }),
    ).toBeInTheDocument()
  })

  it('affiche la décision officielle du jury dans sa colonne dédiée', async () => {
    loadRoutes()
    renderPage()
    await screen.findByText('Awa Koffi')

    // Awa : verdict ADMIS + décision officielle ADMIS (source jurys.DecisionJury).
    const rowAwa = screen.getByText('Awa Koffi').closest('tr')
    expect(
      within(rowAwa).getByTitle('Source : jurys.DecisionJury'),
    ).toBeInTheDocument()

    // Exclu Test : verdict « Exclusion » + décision officielle « Exclusion ».
    const rowExclu = screen.getByText('Exclu Test').closest('tr')
    const badgesExclu = within(rowExclu).getAllByText('Exclusion')
    expect(badgesExclu.length).toBe(2) // verdict + décision officielle

    // Attente Eleve : « Admis avec réserves » n'existe QUE côté officiel
    // (jamais dans le jeu de valeurs du verdict opérationnel).
    const rowAttente = screen.getByText('Attente Eleve').closest('tr')
    expect(within(rowAttente).getByText('Admis avec réserves')).toBeInTheDocument()

    // Jean Yao : jury non statué.
    const rowJean = screen.getByText('Jean Yao').closest('tr')
    expect(within(rowJean).getByText('Jury non statué')).toBeInTheDocument()
  })
})
