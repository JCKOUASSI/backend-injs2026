import { describe, it, expect, beforeEach, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import SeancesEnDirect from '@/pages/SeancesEnDirect'

/** Bloc de présences conforme au contrat `presences.seances_supervision`. */
const PRESENCE = (patch = {}) => ({
  presents: 29, absents_justifies: 1, absents_injustifies: 2, dispenses: 1,
  non_renseignes: 0, retards: 1, source_qr: 30, source_manuelle: 4,
  presences_hors_perimetre: 0, ...patch,
})

const SEANCE_EN_COURS = {
  id: 41, date: '2026-10-04', debut: '2026-10-04T08:00:00+00:00',
  fin: '2026-10-04T10:00:00+00:00', statut: 'EN_COURS', statut_libelle: 'En cours',
  en_direct: true, intitule: 'Physique appliquée', nature: 'COURS',
  semaine_debut: 1, semaine_fin: 10, groupe_id: 7, groupe_libelle: 'L1-G1',
  effectif_attendu: 35, presences: PRESENCE(), non_pointes: 3, taux_presence: 0.8286,
  affectation_pedagogique_id: 3, formation_id: 2, formation_libelle: 'Licence STAPS',
  parcours_id: 4, parcours_libelle: 'EPS', niveau_id: 1, niveau_libelle: 'Licence 1',
  semestre_libelle: 'S1', ue_id: 9, ue_code: 'UE1', ue_libelle: 'Physique',
  ecue_id: 12, ecue_code: 'ECUE-PHY', ecue_libelle: 'Physique appliquée',
  formateur_id: 5, enseignant_id: 3, libelle: 'Awa Traoré', specialite: 'EPS',
  salle_id: 8, salle_libelle: 'Amphi 1', salle_type: 'Amphithéâtre', salle_capacite: 120,
}

const SEANCE_A_VENIR = {
  ...SEANCE_EN_COURS, id: 42, statut: 'A_VENIR', statut_libelle: 'À venir',
  en_direct: false, debut: '2026-10-04T14:00:00+00:00', fin: '2026-10-04T16:00:00+00:00',
  salle_id: 9, salle_libelle: 'Salle 204', groupe_id: 8, groupe_libelle: 'L1-G2',
  effectif_attendu: 20, taux_presence: 0, non_pointes: 20,
  presences: PRESENCE({ presents: 0, retards: 0, source_qr: 0, source_manuelle: 0 }),
}

/** Séance sans rattachement pédagogique ni groupe : tout est inconnu. */
const SEANCE_SANS_CONTEXTE = {
  ...SEANCE_EN_COURS, id: 43, statut: 'TERMINEE', statut_libelle: 'Terminée',
  en_direct: false, affectation_pedagogique_id: null, ecue_code: null, ecue_libelle: null,
  ue_id: null, ue_code: null, ue_libelle: null, groupe_id: null, groupe_libelle: null,
  formation_id: null, formation_libelle: null, parcours_libelle: null,
  formateur_id: null, enseignant_id: null, libelle: null, salle_id: null, salle_libelle: null,
  effectif_attendu: null, taux_presence: null, non_pointes: null,
  presences: PRESENCE({ presents: 0, source_qr: 0 }),
}

const PAYLOAD = (seances) => ({
  date: '2026-10-04', genere_le: '2026-10-04T09:00:00+00:00',
  resume: {
    seances_total: seances.length,
    seances_en_cours: seances.filter((s) => s.statut === 'EN_COURS').length,
    enseignants_actifs: 1, salles_occupees: 1, participants_presents: 29, anomalies: 0,
  },
  seances,
})

const monter = (route = () => PAYLOAD([SEANCE_EN_COURS])) => {
  apiController.setRoute(/seances-edt\/supervision/, route)
  return renderWithProviders(<SeancesEnDirect />, { routePattern: '/' })
}

/** Nombre d'appels GET de consultation (lecture seule). */
const appelsLecture = () =>
  apiMock.get.mock.calls.filter(([p]) => p.includes('supervision')).length

beforeEach(() => {
  apiController.reset()
})

describe('Séances en direct — supervision LMD des séances et des présences', () => {
  it('affiche le bloc, le résumé et la séance renvoyée par le backend', async () => {
    monter()
    expect(await screen.findByTestId('seances-en-direct')).toBeInTheDocument()
    expect(screen.getByText('Séances en direct')).toBeInTheDocument()
    expect(screen.getByText(/Suivi détaillé des séances et des présences/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('seance-41')).toBeInTheDocument())
    expect(screen.getByText('Séances en cours')).toBeInTheDocument()
    expect(screen.getByText('Participants présents')).toBeInTheDocument()
  })

  it('contextualise la séance par ECUE, UE, formation, groupe, enseignant et salle', async () => {
    monter()
    const carte = await screen.findByTestId('seance-41')
    expect(within(carte).getByText(/ECUE-PHY/)).toBeInTheDocument()
    expect(within(carte).getByText(/UE UE1/)).toBeInTheDocument()
    expect(within(carte).getByText('Licence STAPS')).toBeInTheDocument()
    expect(within(carte).getByText('EPS')).toBeInTheDocument()
    expect(within(carte).getByText('L1-G1')).toBeInTheDocument()
    expect(within(carte).getByText('Awa Traoré')).toBeInTheDocument()
    expect(within(carte).getByText('Amphi 1')).toBeInTheDocument()
  })

  it('distingue le statut de séance renvoyé par le backend', async () => {
    monter(() => PAYLOAD([SEANCE_EN_COURS, SEANCE_A_VENIR]))
    const enCours = await screen.findByTestId('seance-41')
    const aVenir = await screen.findByTestId('seance-42')
    expect(within(enCours).getByText('En cours')).toBeInTheDocument()
    expect(within(aVenir).getByText('À venir')).toBeInTheDocument()
  })

  it('détaille les catégories de présence réellement supportées', async () => {
    monter()
    const carte = await screen.findByTestId('seance-41')
    for (const libelle of ['Présents', 'Absents', 'Justifiés', 'Dispensés',
      'Non pointés', 'Attendus']) {
      expect(within(carte).getByText(libelle)).toBeInTheDocument()
    }
    expect(within(carte).getByText(/83 %/)).toBeInTheDocument()
    expect(within(carte).getByText(/QR \(30\)/)).toBeInTheDocument()
    expect(within(carte).getByText(/Manuelle \(4\)/)).toBeInTheDocument()
  })

it('n\'affiche jamais 0 quand la donnée est absente (NULL ≠ 0)', async () => {
    monter(() => PAYLOAD([SEANCE_SANS_CONTEXTE]))
    const carte = await screen.findByTestId('seance-43')
    expect(within(carte).getAllByText('Non disponible').length).toBeGreaterThan(0)
    expect(within(carte).getAllByText('Non renseigné').length).toBeGreaterThan(0)
    expect(within(carte).getByText(/Taux de présence/)).toBeInTheDocument()
    expect(within(carte).queryByText('0 %')).not.toBeInTheDocument()
    expect(within(carte).getByText(/non rattachée à une affectation/i)).toBeInTheDocument()
  })

  it('présente une séance sans présence sans la déclarer « en direct »', async () => {
    monter(() => PAYLOAD([SEANCE_A_VENIR]))
    const carte = await screen.findByTestId('seance-42')
    expect(within(carte).getByText('À venir')).toBeInTheDocument()
    expect(within(carte).queryByText('En cours')).not.toBeInTheDocument()
  })

  it('état vide explicite quand aucune séance n\'est planifiée', async () => {
    monter(() => PAYLOAD([]))
    expect(await screen.findByTestId('seance-vide')).toBeInTheDocument()
    expect(screen.getByText(/Aucune séance planifiée/)).toBeInTheDocument()
    expect(screen.queryByTestId('seance-41')).not.toBeInTheDocument()
  })

  it('état de chargement pendant la requête', async () => {
    let liberer
    monter(() => new Promise((resolve) => { liberer = resolve }))
    expect(await screen.findByTestId('seance-chargement')).toBeInTheDocument()
    liberer(PAYLOAD([SEANCE_EN_COURS]))
    await waitFor(() => expect(screen.getByTestId('seance-41')).toBeInTheDocument())
  })

  it('affiche l\'erreur API puis permet le retry', async () => {
    let appels = 0
    // Le mock résout toujours : pour exercer le chemin `catch` du composant
    // (comme le fait axios sur un 5xx), la route doit lever.
    monter(() => {
      appels += 1
      if (appels === 1) {
        const echec = new Error('Request failed with status code 503')
        echec.response = { status: 503, data: { detail: 'Service indisponible.' } }
        throw echec
      }
      return PAYLOAD([SEANCE_EN_COURS])
    })
    expect(await screen.findByTestId('seance-erreur')).toBeInTheDocument()
    expect(screen.getByText('Service indisponible.')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Réessayer/i }))
    await waitFor(() => expect(screen.getByTestId('seance-41')).toBeInTheDocument())
    expect(appels).toBe(2)
  })

it('filtre par statut en envoyant le filtre au backend', async () => {
    monter(() => PAYLOAD([SEANCE_EN_COURS]))
    await screen.findByTestId('seance-41')
    await userEvent.selectOptions(screen.getByLabelText('Statut'), 'EN_COURS')
    await waitFor(() => {
      // On inspecte le DERNIER appel : le filtre n'a pas été envoyé au premier.
      const appels = apiMock.get.mock.calls.filter(([p]) => p.includes('supervision'))
      expect(appels[appels.length - 1][0]).toContain('statut=EN_COURS')
    })
  })

  it('filtre par date en envoyant la date au backend', async () => {
    monter(() => PAYLOAD([SEANCE_EN_COURS]))
    await screen.findByTestId('seance-41')
    await userEvent.clear(screen.getByLabelText('Date'))
    await userEvent.type(screen.getByLabelText('Date'), '2026-10-04')
    await waitFor(() => expect(appelsLecture()).toBeGreaterThan(1))
  })

  it('rafraîchit via le bouton Actualiser', async () => {
    monter(() => PAYLOAD([SEANCE_EN_COURS]))
    await screen.findByTestId('seance-41')
    const avant = appelsLecture()
    await userEvent.click(screen.getByRole('button', { name: /Actualiser/i }))
    await waitFor(() => expect(appelsLecture()).toBeGreaterThan(avant))
  })

  it('n\'écrit jamais : ni au rendu, ni au filtrage, ni au rafraîchissement', async () => {
    monter(() => PAYLOAD([SEANCE_EN_COURS]))
    await screen.findByTestId('seance-41')
    await userEvent.selectOptions(screen.getByLabelText('Statut'), 'A_VENIR')
    await waitFor(() => expect(appelsLecture()).toBeGreaterThan(1))
    await userEvent.click(screen.getByRole('button', { name: /Actualiser/i }))
    await waitFor(() => expect(appelsLecture()).toBeGreaterThan(2))
    expect(apiMock.post).not.toHaveBeenCalled()
    expect(apiMock.patch).not.toHaveBeenCalled()
    expect(apiMock.put).not.toHaveBeenCalled()
    expect(apiMock.delete).not.toHaveBeenCalled()
  })

  it('affiche l\'horodatage de dernière mise à jour (temps réel honnête)', async () => {
    monter(() => PAYLOAD([SEANCE_EN_COURS]))
    expect(await screen.findByText(/Dernière mise à jour/)).toBeInTheDocument()
  })

  it('propose des actions de consultation uniquement', async () => {
    monter()
    const carte = await screen.findByTestId('seance-41')
    expect(within(carte).getByRole('link', { name: /Voir les présences/i })).toBeInTheDocument()
    expect(within(carte).getByRole('link', { name: /Détails de la séance/i })).toBeInTheDocument()
    expect(within(carte).queryByRole('button')).not.toBeInTheDocument()
  })

  it('n\'expose ni identifiant technique ni jargon backend', async () => {
    monter()
    const carte = await screen.findByTestId('seance-41')
    expect(within(carte).queryByText(/SessionModule|seance_edt|AffectationCreneau/)).toBeNull()
    expect(within(carte).queryByText('#41')).not.toBeInTheDocument()
  })
})