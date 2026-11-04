import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

vi.mock('qrcode', () => ({
  default: { toCanvas: vi.fn((canvas, token, opts, cb) => cb && cb()) },
}))

import apiMock, { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import PresencesHub from './PresencesHub'
import PresencesRegistre from './PresencesRegistre'
import PresencesAudit from './PresencesAudit'
import PresencesGeofence from './PresencesGeofence'
import PosteBadgeage from './PosteBadgeage'
import PresencesContrat from './PresencesContrat'

const SUPERVISION = {
  date: '2026-09-15', genere_le: '2026-09-15T08:30:00+00:00',
  resume: {
    seances_total: 2, seances_en_cours: 1, enseignants_actifs: 1,
    salles_occupees: 1, participants_presents: 12, anomalies: 1,
    sessions_qr_ouvertes: 1, emargements_manuels: 3,
    par_population: { etudiants: 10, enseignants: 1, encadrants: 1 },
  },
  seances: [
    {
      id: 41, debut: '2026-09-15T08:00:00+00:00', fin: '2026-09-15T10:00:00+00:00',
      statut: 'EN_COURS', statut_libelle: 'En cours', intitule: 'Physique appliquée',
      ecue_code: 'PHY101', ecue_libelle: 'Physique appliquée', ue_code: 'UE-PHY1',
      niveau_libelle: 'Licence 1', semestre_libelle: 'Semestre 1', nature_libelle: 'Cours',
      libelle: 'Awa Traoré', session_qr_ouverte: true, formation_libelle: 'Licence STAPS',
      groupe_libelle: 'L1-G1', salle_libelle: 'Amphi 1', effectif_attendu: 20,
      presences: {
        presents: 12, retards: 1, absents_injustifies: 0, absents_justifies: 0,
        source_qr: 10, source_manuelle: 2, presences_hors_perimetre: 0,
        en_salle: 5, entrees_en_retard: 2, retard_moyen_min: 6.5,
        par_population: { etudiants: 10, enseignants: 1, encadrants: 1 },
      }, non_pointes: 8, taux_presence: 0.6,
    },
    {
      id: 42, debut: '2026-09-15T10:00:00+00:00', fin: '2026-09-15T12:00:00+00:00',
      statut: 'PLANIFIEE', statut_libelle: 'Planifiée', intitule: 'Chimie organique',
      session_qr_ouverte: false,
      formation_libelle: 'Licence STAPS',
      groupe_libelle: null, salle_libelle: 'Labo 2', effectif_attendu: null,
      presences: {
        presents: 0, retards: 0, source_manuelle: 1, presences_hors_perimetre: 0,
        en_salle: 0, entrees_en_retard: 0, retard_moyen_min: null,
        par_population: { etudiants: 0, enseignants: 0, encadrants: 0 },
      }, non_pointes: null, taux_presence: null,
    },
  ],
}

function preparer() {
  vi.clearAllMocks()
  apiController.reset()
  apiController.setRoute('/presences/seances-edt/supervision/', SUPERVISION)
  apiController.setRoute('/presences/seances-edt/du-jour/', [{
    id: 41, debut: '2026-09-15T08:00:00+00:00', fin: '2026-09-15T10:00:00+00:00',
    intitule: 'Physique appliquée', groupe_libelle: 'L1-G1', salle: 'Amphi 1',
  }])
  apiController.setRoute('/presences/seances-edt/historique/', {
    date_debut: '2026-09-15', date_fin: '2026-09-15', total: 2,
    resultats: [
      {
        id: 5, nom: 'Ba Awa', matricule: 'MAT011', type_participant: 'ETUDIANT',
        seance_id: 41, seance: 'PHY101 · Physique appliquée', groupe: 'L1-G1',
        date_seance: '2026-09-15', timestamp_entree: '2026-09-15T08:02:00+00:00',
        timestamp_sortie: '2026-09-15T09:47:00+00:00', duree_minutes: 105,
        heartbeats: 1, mode: 'QR_AUTOMATIQUE', motif_manuel: null, auteur_manuel: null,
        verdict_geofence: 'DANS_PERIMETRE', accuracy_m: 72.4, statut: 'TERMINE',
        statut_assiduite: 'PRESENT', type_sortie: 'SORTIE_QR', anomalies: [],
      },
      {
        id: 6, nom: 'Nadia Diallo', matricule: 'MAT099', type_participant: 'ETUDIANT',
        seance_id: 41, seance: 'PHY101 · Physique appliquée', groupe: 'L1-G1',
        date_seance: '2026-09-15', timestamp_entree: '2026-09-15T08:07:00+00:00',
        timestamp_sortie: null, duree_minutes: null,
        heartbeats: 0, mode: 'MANUEL', motif_manuel: 'QR_NON_LISIBLE',
        auteur_manuel: 'Admin Test',
        verdict_geofence: null, accuracy_m: null, statut: 'EN_COURS',
        statut_assiduite: 'PRESENT', type_sortie: null, anomalies: ['HORS_PERIMETRE'],
      },
    ],
  })
  apiController.setRoute('/presences/seances-edt/41/presences/', {
    seance: { id: 41 },
    attendus: 2, presents: 1, retards: 0, absents: 0, non_pointes: 1,
    presences_manuelles: 1, anomalies_gps: 0, sorties_automatiques: 0, absents_non_badges: 0,
    lignes: [
      {
        participant: 'MAT011', matricule: 'MAT011', nom: 'Awa Traoré',
        badge_entree: '2026-09-15T08:02:00+00:00', badge_sortie: null,
        statut: 'PRESENT', statut_badgeage: 'COMPLET_VALIDÉ', pointage_id: 5,
        mode: 'MANUEL', motif_manuel: 'QR_NON_LISIBLE', type_sortie: null,
      },
      {
        participant: 'MAT012', matricule: 'MAT012', nom: 'Nadia Diallo',
        badge_entree: null, badge_sortie: null, statut: null, statut_badgeage: null,
        pointage_id: null, mode: null, motif_manuel: null, type_sortie: null,
      },
    ],
  })
  apiController.setRoute('/audit-logs/', (path) => {
    if (path.includes('SCAN_HEARTBEAT')) return { count: 7, results: [] }
    if (path.includes('date_debut')) {
      return {
        count: 1,
        results: [{
          id: 9, timestamp: '2026-09-15T08:04:00+00:00', action: 'SCAN_SECURE_ENTREE',
          action_label: 'Entrée (scan sécurisé)', acteur_label: 'Nadia Diallo',
          acteur_role: 'ETUDIANT', cible_nom: 'Nadia Diallo', cible_numero: 'MAT099',
          formation_titre: '', device_id: 'dev-9', extra: {},
        }],
      }
    }
    return {
      count: 1,
      results: [{
        id: 1, timestamp: '2026-09-15T08:05:00+00:00', action: 'FORCE_ENTREE',
        action_label: 'Entrée forcée', acteur_label: 'Awa Traoré', acteur_role: 'ENSEIGNANT',
        cible_type: 'participant', cible_nom: 'Awa Traoré', cible_numero: 'MAT011',
        formation_titre: '', pointage_id: 5,
        device_id: 'dev-1',
        extra: {
          mode: 'MANUEL', motif: 'QR_NON_LISIBLE', commentaire: 'QR illisible',
          avant: { statut: 'EN_COURS', statut_assiduite: 'NON_RENSEIGNE' },
          apres: { statut: 'FORCE_DFRC', statut_assiduite: 'PRESENT' },
        },
      }],
    }
  })
  apiController.setRoute('/formations/ref/sites/', [{
    id: 3, nom: 'INJS Marcory', actif: true,
    geofence_latitude: 5.3083, geofence_longitude: -3.9825, geofence_rayon_m: 200,
  }])
  apiController.setRoute('/presences/seances-edt/41/qr/', { token: 'jeton-uuid-41' })
  apiController.setRoute('/presences/seances-edt/scan/', {
    statut: 'IN', action: 'ENTREE', participant: 'MAT011',
    seance_intitule: 'Physique appliquée', timestamp: '2026-09-15T08:03:00+00:00',
    mode: 'QR_AUTOMATIQUE',
  })
}

function monter(ui) {
  return render(
    <AllProviders user={makeUser('ENSEIGNANT')}>
      {ui}
    </AllProviders>,
  )
}

beforeEach(preparer)

describe('PresencesHub — tableau de bord refondu (plaquettes INJS)', () => {
  it('affiche plaquettes, cours débutés, services académiques et derniers pointages', async () => {
    monter(<PresencesHub />)
    await waitFor(() => expect(screen.getByText(/PHY101 · Physique appliquée/)).toBeTruthy())
    // Terminologie INJS : Étudiants / Enseignants / En Salle-Espace.
    expect(screen.getByText('Étudiants présents / attendus')).toBeTruthy()
    expect(screen.getByText('12/20')).toBeTruthy()
    expect(screen.getAllByText('1/1').length).toBeGreaterThan(0)
    expect(screen.getByText('En Salle/Espace maintenant')).toBeTruthy()
    expect(screen.getByText('Volume horaire')).toBeTruthy()
    expect(screen.getByText('Séances du jour')).toBeTruthy()
    expect(screen.getByText(/dont 7 signaux heartbeat/)).toBeTruthy()
    // Qualité : retard moyen du jour, format français.
    expect(screen.getByText(/6,5 min de retard moyen/)).toBeTruthy()
    // Présences du jour : présents / absents / attendus.
    expect(screen.getByText(/12 présents · 0 absents · 20 attendus/)).toBeTruthy()
    // Cours débutés et prochaines séances.
    expect(screen.getByText('Prochaines séances')).toBeTruthy()
    expect(screen.getAllByText('Chimie organique').length).toBeGreaterThan(0)
    // Rail : filtre période + services académiques (formations du jour
    // uniquement) + anomalies + répartition.
    expect(screen.getByText('Taux de présence du jour')).toBeTruthy()
    expect(screen.getByText('Services académiques')).toBeTruthy()
    expect(screen.getByText('Licence STAPS')).toBeTruthy()
    expect(screen.getByText('SANS GROUPE')).toBeTruthy()
    expect(screen.getByText('Encadrants')).toBeTruthy()
    // Derniers pointages issus du journal (scans uniquement).
    expect(screen.getByText('Derniers pointages')).toBeTruthy()
    expect(screen.getByText('Nadia Diallo')).toBeTruthy()
    // Modules du hub et CTA badgeage.
    expect(screen.getByText('Badgeage')).toBeTruthy()
    expect(screen.getByText('Configuration')).toBeTruthy()
    expect(screen.getByText('Ouvrir le poste de badgeage')).toBeTruthy()
  })

  it('filtre les compteurs par service académique (formation du jour)', async () => {
    const user = userEvent.setup()
    monter(<PresencesHub />)
    await waitFor(() => expect(screen.getByText('Licence STAPS')).toBeTruthy())
    await user.click(screen.getByRole('button', { name: 'Licence STAPS' }))
    // Les deux séances sont en Licence STAPS : les compteurs restent cohérents.
    expect(screen.getByText('12/20')).toBeTruthy()
  })
})

describe('PresencesRegistre — historique refondu', () => {
  it('affiche l’historique transversal avec types, verdicts et anomalies', async () => {
    monter(<PresencesRegistre />)
    await waitFor(() => expect(screen.getByText('Ba Awa')).toBeTruthy())
    expect(screen.getAllByText('ETUDIANT').length).toBe(2)
    expect(screen.getByText('Dans le périmètre')).toBeTruthy()
    expect(screen.getByText('±72 m')).toBeTruthy()
    expect(screen.getByText(/1 heartbeat/)).toBeTruthy()
    expect(screen.getByText('105 min')).toBeTruthy()
    expect(screen.getAllByText('Manuel').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/QR_NON_LISIBLE · Admin Test/)).toBeTruthy()
    expect(screen.getByText('HORS_PERIMETRE')).toBeTruthy()
    expect(screen.getByText('Émargement manuel et corrections')).toBeTruthy()
  })
})

describe('PresencesAudit — traçabilité non destructive', () => {
  it('liste compacte : auteur, entité, motif ; détail déployable avant/après', async () => {
    const user = userEvent.setup()
    monter(<PresencesAudit />)
    await waitFor(() => expect(screen.getByText('Entrée forcée')).toBeTruthy())
    // Chargement explicite visible dans l'écran et demandé au serveur.
    expect(screen.getAllByText(/Chargement explicite : 200 événements/).length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText('1 chargé(s)')).toBeTruthy()
    expect(apiController.findCall('get', /audit-logs\/\?.*limite=200/)).toBeTruthy()
    expect(screen.getByText('motif : QR_NON_LISIBLE')).toBeTruthy()
    // Détail replié par défaut : les valeurs ne sont pas encore affichées.
    expect(screen.queryByText('Ancienne valeur')).toBeNull()
    await user.click(screen.getByRole('button', { name: /Détails/ }))
    // Correction non destructive : ancienne et nouvelle valeurs côte à côte.
    expect(screen.getByText('Ancienne valeur')).toBeTruthy()
    expect(screen.getByText('Nouvelle valeur')).toBeTruthy()
    expect(screen.getByText(/FORCE_DFRC/)).toBeTruthy()
    expect(screen.getByText(/NON_RENSEIGNE/)).toBeTruthy()
    expect(screen.getByText(/mode MANUEL/)).toBeTruthy()
    expect(screen.getByText(/participant #MAT011/)).toBeTruthy()
  })

  it('pagine par 12 : page suivante, plage et compteurs', async () => {
    const user = userEvent.setup()
    apiController.reset()
    apiController.setRoute('/audit-logs/', {
      count: 15,
      results: Array.from({ length: 15 }, (_, i) => ({
        id: 100 + i, timestamp: '2026-09-15T08:05:00+00:00',
        action: 'SCAN_HEARTBEAT', action_label: `Événement ${i + 1}`,
        acteur_label: 'Testeur', acteur_role: 'ETUDIANT',
        cible_type: 'participant', cible_nom: `Cible ${i + 1}`,
        cible_numero: `MAT${100 + i}`, formation_titre: '', extra: {},
      })),
    })
    monter(<PresencesAudit />)
    await waitFor(() => expect(screen.getByText('Événement 1')).toBeTruthy())
    expect(screen.getByText('Événements 1 à 12 sur 15')).toBeTruthy()
    expect(screen.getByText('Page 1 sur 2')).toBeTruthy()
    expect(screen.queryByText('Événement 13')).toBeNull()
    await user.click(screen.getByRole('button', { name: /Suivant/ }))
    expect(screen.getByText('Événements 13 à 15 sur 15')).toBeTruthy()
    expect(screen.getByText('Événement 13')).toBeTruthy()
    expect(screen.queryByText('Événement 1', { exact: true })).toBeNull()
  })
})

describe('PresencesGeofence', () => {
  it('affiche les sites et simule une position sans produire de verdict', async () => {
    const user = userEvent.setup()
    monter(<PresencesGeofence />)
    await waitFor(() => expect(screen.getByText('INJS Marcory')).toBeTruthy())
    expect(screen.getByText('200 m')).toBeTruthy()
    await user.click(screen.getByText('INJS Marcory'))
    await user.type(screen.getByLabelText('Latitude test'), '5.3083')
    await user.type(screen.getByLabelText('Longitude test'), '-3.9825')
    await waitFor(() => expect(screen.getByText('0 m')).toBeTruthy())
    expect(screen.getByText(/Simulation d’affichage uniquement/)).toBeTruthy()
  })
})

describe('PosteBadgeage', () => {
  it('badge via le serveur et démarre le heartbeat après l’entrée', async () => {
    const user = userEvent.setup()
    monter(<PosteBadgeage />)
    await waitFor(() => expect(screen.getByText('Prêt à badger')).toBeTruthy())
    await user.click(screen.getByRole('button', { name: /Badger \(entrée \/ sortie\)/ }))
    await waitFor(() => expect(screen.getByText('Entrée enregistrée')).toBeTruthy())
    expect(apiMock.post).toHaveBeenCalledWith(
      '/presences/seances-edt/scan/',
      expect.objectContaining({ token_qr: 'jeton-uuid-41' }),
    )
    expect(screen.getByText(/Arrêter le heartbeat/)).toBeTruthy()
  })
})

describe('PresencesContrat', () => {
  it('documente endpoints et codes normalisés du backend réel', () => {
    monter(<PresencesContrat />)
    expect(screen.getByText('/api/presences/seances-edt/scan/')).toBeTruthy()
    expect(screen.getByText('MOTIF_AUTRE_SANS_COMMENTAIRE')).toBeTruthy()
    expect(screen.getByText('HORS_PERIMETRE')).toBeTruthy()
  })
})
