import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

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
  titre: 'EDT ÉDUCATION ET MOTRICITÉ — LICENCE — L1 S1 (exemple GET)',
  population_label: 'Formation #1',
  population_type: 'FORMATION',
  population_id: 1,
  annee_academique: '2026-2027',
  annee_academique_id: 1,
  semaine_debut: 1,
  semaine_fin: 4,
  affectations_count: 1,
  statut: 'BROUILLON',
}

const CONTEXTE = {
  niveau: 'L1', semestre: 'S1', ue: 'UE1', ecue: 'ECUE1',
  groupe: 'L1-G1', enseignant: 'Koffi Aya', effectif: 42,
}

const AFFECTATION = {
  id: 11,
  emploi_du_temps_id: 7,
  creneau: { jour: 'LUNDI', heure_debut: '08:00', heure_fin: '10:00' },
  horaire: 'Lundi 08:00–10:00',
  semaine_debut: 1,
  semaine_fin: 1,
  nature: 'COURS',
  intitule: 'Anatomie fonctionnelle',
  commentaire: '',
  enseignant_nom: '',
  groupe: null,
  salle_nom: 'Salle A',
  actif: true,
  contexte: CONTEXTE,
}

const GRILLE = {
  semaine: 1,
  jours: [{
    jour: 'LUNDI',
    creneaux: [{
      creneau_template_id: 1, jour: 'LUNDI',
      heure_debut: '08:00', heure_fin: '10:00',
      affectations: [{
        id: 11, nature: 'COURS', intitule: 'Anatomie fonctionnelle',
        enseignant_nom: '', groupe: '', salle_nom: 'Salle A',
        semaine_debut: 1, semaine_fin: 1, contexte: CONTEXTE,
      }],
    }],
  }],
}

function monter() {
  apiController.setMe(makeUser('ADMIN'))
  apiController.setRoute('/edts/emplois/', [EDT])
  apiController.setRoute('/edts/emplois/7/', EDT)
  apiController.setRoute('/edts/emplois/7/grille/', GRILLE)
  apiController.setRoute('/edts/affectations/', [AFFECTATION])
  apiController.setRoute('/edts/conflits/', [])
  apiController.setRoute('/scolarite/ref/annees/', [{ id: 1, libelle: '2026-2027' }])
  apiController.setRoute('/edts/creneaux-types/', [])
  apiController.setRoute('/edts/referentiel-enseignants/', [])
  apiController.setRoute('/formations/ref/formations/', [
    { id: 1, intitule: 'ÉDUCATION ET MOTRICITÉ — LICENCE', filiere_code: 'F01' },
  ])
  apiController.setRoute('/scolarite/ref/niveaux/', [{ id: 1, code: 'L1' }])
  return render(
    <AllProviders authUser={makeUser('ADMIN')} initialEntries={['/edt']} routePattern="/edt">
      <Edts />
    </AllProviders>,
  )
}

describe('Edts — exploitation des emplois du temps (maquette)', () => {
  beforeEach(() => {
    apiController.reset()
    window.localStorage.clear()
  })

  it('présente l’en-tête d’exploitation et ses actions', async () => {
    monter()
    expect(await screen.findByRole('heading', { name: 'Emplois du temps' }))
      .toBeInTheDocument()
    expect(screen.getByText('Exploitation')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Exporter CSV/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Imprimer la grille/ })).toBeInTheDocument()
  })

  it('sélectionne un emploi du temps par chips et affiche la grille', async () => {
    monter()
    expect(await screen.findByRole('option', { name: EDT.titre })).toBeInTheDocument()
    // Le détail se charge en deux temps (semaine) : attendre l'état final stable.
    await waitFor(() => {
      expect(screen.getByText(/Grille hebdomadaire — Semestre 1/)).toBeInTheDocument()
      expect(screen.getByText('Créneau 1')).toBeInTheDocument()
      expect(screen.getAllByText('Anatomie fonctionnelle').length)
        .toBeGreaterThanOrEqual(1)
      expect(screen.getAllByText('Lundi').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('Samedi')).toBeInTheDocument()
      expect(screen.getAllByText('UE1 · ECUE1').length).toBeGreaterThanOrEqual(1)
    })
  })

  it('affiche le détail tabulaire des séances avec le contexte LMD réel', async () => {
    monter()
    // Attendre la ligne de détail (chargement asynchrone complet de l'écran).
    await waitFor(() => {
      expect(screen.getByText('Koffi Aya')).toBeInTheDocument()
      expect(screen.getByText('1 ligne(s) affichée(s)')).toBeInTheDocument()
      expect(screen.getByText('Détail des séances')).toBeInTheDocument()
      expect(screen.getAllByText('Semestre').length).toBeGreaterThanOrEqual(1)
      expect(screen.getByText('Effectif')).toBeInTheDocument()
      expect(screen.getAllByText('42').length).toBeGreaterThanOrEqual(1)
      // Résumé des filtres : séances, natures, places couvertes.
      expect(screen.getByText('1 séance(s)')).toBeInTheDocument()
      expect(screen.getByText('42 places couvertes')).toBeInTheDocument()
    })
  })

  it('expose les filtres de la maquette (année, filière, formation, niveau, groupe, semestre)', async () => {
    monter()
    expect(await screen.findByLabelText('Année académique')).toBeInTheDocument()
    expect(screen.getByLabelText('Filière')).toBeInTheDocument()
    expect(screen.getByLabelText('Formation')).toBeInTheDocument()
    expect(screen.getByLabelText('Niveau')).toBeInTheDocument()
    expect(screen.getByLabelText('Groupe')).toBeInTheDocument()
    expect(screen.getByLabelText('Semestre')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Afficher' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Réinitialiser les filtres' }))
      .toBeInTheDocument()
  })
})
