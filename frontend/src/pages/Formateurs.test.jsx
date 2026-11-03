/**
 * Tests de l'écran « Enseignants » (page Formateurs, variante corps
 * enseignant) : panorama de couverture des ECUE, grade académique, charge
 * réelle par enseignant et filtre par grade. La variante finance (temps /
 * montants) est couverte ailleurs et inchangée.
 */
import React from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import apiMock, { apiController } from '@/test/utils/mockApi'
import { renderWithProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import Formateurs from '@/pages/Formateurs'

const STATS = {
  enseignants: 67,
  sans_grade: 3,
  grades_disponibles: [
    { id: 2, code: 'PROFESSEUR_TITULAIRE', libelle: 'Professeur Titulaire' },
    { id: 5, code: 'MAITRE_CONFERENCES', libelle: 'Maître de Conférences' },
  ],
  par_grade: [
    { id: 2, code: 'PROFESSEUR_TITULAIRE', libelle: 'Professeur Titulaire', total: 16 },
    { id: 5, code: 'MAITRE_CONFERENCES', libelle: 'Maître de Conférences', total: 16 },
  ],
  par_statut: { Titulaire: 48, Vacataire: 16, 'Non renseigné': 3 },
  couverture: {
    annee_academique: '2026-2027', ecue_total: 779, ecue_couvertes: 779,
    taux_couverture: 100.0, formations_total: 16, formations_couvertes: 16,
    filieres_total: 8, filieres_couvertes: 8, affectations: 779,
    heures_affectees: 12000,
  },
}

const LIGNES = {
  results: [
    {
      id: 10, numerobadge: 'F004', nom: 'KOUASSI', prenom: 'Aya',
      email: 'aya.kouassi@exemple.injs.ci', telephone: '+225 07 07 14 24 34',
      specialite: 'Physiologie de l’exercice', organisation: 'INJS',
      grade_ref: 2,
      grade: { id: 2, code: 'PROFESSEUR_TITULAIRE', libelle: 'Professeur Titulaire' },
      fonction: 'Chef de département', statut_enseignant: 'Titulaire',
      secretariats: [], secretariats_noms: [], nb_formations: 0,
      enseignements: {
        nb_ecue: 14, heures: 210,
        formations: ['ENTRAÎNEMENT SPORTIF — LICENCE'],
      },
    },
    {
      id: 1, numerobadge: 'F001', nom: 'KONÉ', prenom: 'Seydou', email: '',
      telephone: '', specialite: 'Management public', organisation: '',
      grade_ref: null, grade: null, fonction: '', statut_enseignant: '',
      secretariats: [], secretariats_noms: [], nb_formations: 0,
      enseignements: { nb_ecue: 0, heures: 0, formations: [] },
    },
  ],
  count: 67, total_pages: 2, current_page: 1,
}

function preparer() {
  apiController.reset()
  apiController.setRoute('/formations/formateurs/stats/', () => STATS)
  apiController.setRoute('/formations/formateurs/list/', () => LIGNES)
  apiController.setRoute('/formations/ref/modules/', () => [])
}

const mount = () => {
  const me = makeUser('ADMIN', { username: 'admin' })
  apiController.setMe(me)
  return renderWithProviders(<Formateurs />, {
    authUser: me,
    routePattern: '*',
    initialEntries: ['/formateurs'],
  })
}

beforeEach(preparer)

describe('Enseignants — panorama premium', () => {
  it('affiche la couverture complète des ECUE et les totaux réels', async () => {
    const { container } = mount()
    await waitFor(() => expect(container.textContent).toContain('779/779'))
    expect(container.textContent).toContain('ECUE avec enseignant')
    expect(container.textContent).toMatch(/100 % des maquettes actives/)
    expect(container.textContent).toMatch(/12\s*000 h/)
    expect(container.textContent).toContain('16/16')
    // Total réel (67), pas la taille de la page affichée (2 lignes).
    // La liste attend la résolution de l'identité (l'endpoint dépend du rôle) :
    // l'assertion est donc asynchrone, comme le chargement qu'elle vérifie.
    expect(await screen.findByText(/67 enseignants/)).toBeInTheDocument()
    expect(await screen.findByText(/67 résultats/)).toBeInTheDocument()
  })

  it('présente grade académique, fonction et charge réelle de chaque enseignant', async () => {
    mount()
    await waitFor(() => expect(screen.getByText('Professeur Titulaire')).toBeInTheDocument())
    expect(screen.getByText('Chef de département')).toBeInTheDocument()
    expect(screen.getByText(/14 ECUE · 210 h/)).toBeInTheDocument()
    expect(screen.getByText('ENTRAÎNEMENT SPORTIF — LICENCE')).toBeInTheDocument()
    expect(screen.getByText(/aya\.kouassi@exemple\.injs\.ci/)).toBeInTheDocument()
    // Enseignant sans affectation : mention honnête, plus de « Modules 0 ».
    expect(screen.getByText('Aucune affectation')).toBeInTheDocument()
    expect(screen.queryByText('Modules')).not.toBeInTheDocument()
  })

  it('filtre la liste par grade côté serveur', async () => {
    const user = userEvent.setup()
    mount()
    const select = await screen.findByLabelText('Filtrer par grade')
    await waitFor(() => expect(screen.getByRole('option', { name: /Professeur Titulaire \(16\)/ })).toBeInTheDocument())
    await user.selectOptions(select, 'PROFESSEUR_TITULAIRE')
    await waitFor(() => {
      const appels = apiMock.get.mock.calls
        .map(([p]) => p)
        .filter((p) => p.startsWith('/formations/formateurs/list/'))
      expect(appels[appels.length - 1]).toContain('grade=PROFESSEUR_TITULAIRE')
    })
  })

  it('signale les enseignants sans affectation LMD cette année', async () => {
    mount()
    // KONÉ (profil historique, hors corps LMD) ≠ DIARRASSOUBA (exemple LMD).
    expect(await screen.findByText('Hors LMD')).toBeInTheDocument()
    // Un seul profil historique dans le jeu d'essai, et il n'est pas marqué
    // « [Exemple] » : les deux badges ne se cumulent jamais.
    expect(screen.getAllByText('Hors LMD')).toHaveLength(1)
    expect(screen.queryByLabelText('Données d’exemple')).not.toBeInTheDocument()
  })

  it('rappelle les filtres actifs et permet de les réinitialiser', async () => {
    const user = userEvent.setup()
    mount()
    const select = await screen.findByLabelText('Filtrer par grade')
    await user.selectOptions(select, 'PROFESSEUR_TITULAIRE')
    // Sans rappel visuel, un filtre oublié laisse croire à une liste vide.
    expect(await screen.findByText(/1 filtre actif/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /filtre de grade Professeur Titulaire/ })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Tout réinitialiser/ }))
    await waitFor(() => {
      const appels = apiMock.get.mock.calls
        .map(([p]) => p)
        .filter((p) => p.startsWith('/formations/formateurs/list/'))
      expect(appels[appels.length - 1]).not.toContain('grade=')
    })
    expect(screen.queryByRole('button', { name: /Tout réinitialiser/ })).not.toBeInTheDocument()
  })

  it('propose le grade dans la fiche de création', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Nouvel enseignant/ }))
    expect(await screen.findByText('Grade enseignant')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Maître de Conférences' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Titulaire' })).toBeInTheDocument()
  })
})

describe('Enseignants — fiche pédagogique LMD', () => {
  const FICHE = {
    ...LIGNES.results[0], annee_academique: '2026-2027', grade_label: 'Professeur Titulaire',
    est_exemple: true, nb_formations: 1, nb_ecue: 14, heures_affectees: 210,
    heures_effectuees: null, taux_presence: null, satisfaction_etudiants: null,
    disponibilite_indicateurs: 'Aucune source de présence enseignante reliée.',
    charge: { affectee: 210, validee: 210, planifiee: 0, realisee: 0, seuil: 192, surcharge: true },
    taux_charge: 109,
    repartition: [
      { libelle: 'Cours magistral', heures: 120 },
      { libelle: 'Travaux dirigés', heures: 60 },
      { libelle: 'Travaux pratiques', heures: 30 },
    ],
    affectations: [{ id: 7, ecue_code: 'ES-S1-EC01', ecue_intitule: 'Physiologie', ue: 'Sciences',
      formation: 'ENTRAÎNEMENT SPORTIF — LICENCE', filiere: 'ES', niveau: 'L1', semestre: 'S1',
      groupe: 'L1-G1', type_enseignement: 'Cours magistral', heures: 15, statut_label: 'Validée', est_exemple: true }],
  }
  let panne = false
  beforeEach(() => {
    // `preparer()` (beforeEach global) a déjà enregistré la liste complète :
    // on repart d'une table rase pour que cette route prenne le pas.
    panne = false
    apiController.reset()
    apiController.setRoute('/formations/formateurs/stats/', () => STATS)
    apiController.setRoute('/formations/ref/modules/', () => [])
    apiController.setRoute('/formations/formateurs/list/', () => ({
      ...LIGNES, results: [{ ...LIGNES.results[0], est_exemple: true }],
      count: 1, total_pages: 1,
    }))
    apiController.setRoute('/formations/formateurs/10/fiche/', () => {
      if (panne) throw new Error('panne')
      return FICHE
    })
  })

  it('affiche la charge LMD réelle et non les zéros de la paie legacy', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Détail/ }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleName('KOUASSI Aya')
    expect(dialog).toHaveTextContent('210 h')
    expect(dialog).toHaveTextContent('[Exemple]')
    expect(dialog).toHaveTextContent('Non disponible')
    expect(apiMock.get).toHaveBeenCalledWith('/formations/formateurs/10/fiche/')
    expect(apiMock.get.mock.calls.some(([path]) => path.includes('finance-report'))).toBe(false)
    await user.click(screen.getByRole('tab', { name: /Enseignements LMD/ }))
    expect(screen.getByText(/ES-S1-EC01 · Physiologie/)).toBeInTheDocument()
    await user.click(screen.getByRole('tab', { name: /Évaluation/ }))
    expect(within(screen.getByRole('tabpanel')).getAllByText('Non disponible')).toHaveLength(3)
    await user.click(screen.getByRole('button', { name: /Export PDF/ }))
    expect(apiMock.getBlob).toHaveBeenCalledWith('/formations/formateurs/10/fiche/export/pdf/')
  })

  it('présente le formulaire de création en sections premium', async () => {
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Nouvel enseignant/ }))
    const dialog = await screen.findByRole('dialog')
    expect(dialog).toHaveAccessibleName('Nouvel enseignant')
    for (const rubrique of ['Identité', 'Affectation académique', 'Contact & organisation', 'Observations']) {
      expect(within(dialog).getByText(rubrique)).toBeInTheDocument()
    }
    // Spécialités du corps LMD (et non les modules de formation continue).
    expect(within(dialog).getByRole('option', { name: '— Non renseignée —' })).toBeInTheDocument()
    expect(within(dialog).getAllByRole('option').length).toBeGreaterThan(3)
  })

  it('ne substitue pas des zéros quand la fiche échoue', async () => {
    panne = true
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Détail/ }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Aucune donnée financière de substitution')
    expect(screen.getByRole('button', { name: /Export PDF/ })).toBeDisabled()
  })
})

describe('Enseignants — cohérence des appels et du design', () => {
  it('envoie une taille de page explicite au serveur', async () => {
    mount()
    await screen.findByText(/KOUASSI/)
    const appels = apiMock.get.mock.calls.map(([url]) => String(url))
    const liste = appels.find((u) => u.includes('/formations/formateurs/list/'))
    expect(liste).toBeTruthy()
    // Les deux endpoints de liste n'ont pas le même défaut côté serveur
    // (50 pour « list », 25 pour « finance-report ») : sans valeur explicite,
    // la pagination annonçait 50 lignes pour 25 affichées.
    expect(liste).toContain('page_size=50')
  })

  it('affiche le total du corps enseignant dans l’en-tête, pas le total filtré', async () => {
    apiController.reset()
    apiController.setRoute('/formations/formateurs/stats/', () => STATS)
    apiController.setRoute('/formations/formateurs/list/', () => ({
      ...LIGNES, results: [LIGNES.results[0]], count: 3, total_pages: 1,
    }))
    mount()
    // 67 = total du panorama serveur (STATS.enseignants), 3 = résultats filtrés.
    expect(await screen.findByText(/67 enseignants/)).toBeInTheDocument()
    expect(await screen.findByText(/3 résultats/)).toBeInTheDocument()
  })

  const FICHE_PREMIUM = {
    ...LIGNES.results[0], annee_academique: '2026-2027', grade_label: 'Professeur Titulaire',
    est_exemple: true, nb_formations: 1, nb_ecue: 14, heures_affectees: 210,
    heures_effectuees: null, taux_presence: null, satisfaction_etudiants: null,
    disponibilite_indicateurs: 'Aucune source de présence enseignante reliée.',
    charge: { affectee: 210, validee: 210, planifiee: 0, realisee: 0, seuil: 192, surcharge: true },
    taux_charge: 109,
    repartition: [
      { libelle: 'Cours magistral', heures: 120 },
      { libelle: 'Travaux dirigés', heures: 60 },
      { libelle: 'Travaux pratiques', heures: 30 },
    ],
    affectations: [],
  }

  it('présente la fiche premium : rail d’identité, anneau de charge et répartition', async () => {
    apiController.reset()
    apiController.setRoute('/formations/formateurs/stats/', () => STATS)
    apiController.setRoute('/formations/formateurs/list/', () => ({
      ...LIGNES, results: [{ ...LIGNES.results[0], est_exemple: true }], count: 1, total_pages: 1,
    }))
    apiController.setRoute('/formations/formateurs/10/fiche/', () => FICHE_PREMIUM)
    const user = userEvent.setup()
    mount()
    await user.click(await screen.findByRole('button', { name: /Détail/ }))
    const dialog = await screen.findByRole('dialog')
    // Rail d'identité : l'enseignant reste nommé quel que soit l'onglet.
    expect(within(dialog).getByText('aya.kouassi@exemple.injs.ci')).toBeInTheDocument()
    expect(within(dialog).getByText(/Source : affectations pédagogiques 2026-2027/)).toBeInTheDocument()
    // Anneau de charge : pourcentage issu du serveur, jamais recalculé ici.
    expect(within(dialog).getByRole('img', { name: /Charge à 109 % du seuil/ })).toBeInTheDocument()
    expect(within(dialog).getByText(/18 h de dépassement/)).toBeInTheDocument()
    // Répartition par nature d'enseignement (agrégée côté serveur).
    await user.click(screen.getByRole('tab', { name: /Charge annuelle/ }))
    expect(within(dialog).getByText('Répartition par nature d’enseignement')).toBeInTheDocument()
    expect(within(dialog).getByText('Travaux dirigés')).toBeInTheDocument()
    expect(within(dialog).getByText('120 h')).toBeInTheDocument()
  })
})

describe('Enseignants — variante finance (temps et montants)', () => {
  const LIGNES_FINANCE = {
    count: 68, total_pages: 2, current_page: 1, page: 1, periode: null,
    results: Array.from({ length: 50 }, (_, i) => ({
      id: 100 + i, numerobadge: `F${100 + i}`, nom: `ENSEIGNANT${i}`, prenom: 'Test',
      specialite: 'Physiologie', grades: 'Maître de Conférences', groupes: 'L1-G1',
      sessions_count: 3, total_duree_minutes: 300, total_duree_realisee_minutes: 240,
      montant_total_realise: 75000, statistiques: { taux_realisation_pct: 80 },
    })),
  }

  it('affiche le total du référentiel et une taille de page explicite', async () => {
    apiController.reset()
    apiController.setRoute('/formations/finance/settings/', () => ({ afficher_montants_exports: true }))
    apiController.setRoute('/formations/formateurs/finance-report/', () => LIGNES_FINANCE)
    const me = makeUser('FINANCE', { username: 'finance' })
    apiController.setMe(me)
    renderWithProviders(<Formateurs />, { authUser: me, routePattern: '*', initialEntries: ['/formateurs'] })

    // Le badge annonce le total du référentiel (68), pas la longueur de la page (50).
    expect(await screen.findByText(/68 résultats/, undefined, { timeout: 5000 })).toBeInTheDocument()
    expect(await screen.findByText(/ENSEIGNANT0/, undefined, { timeout: 5000 })).toBeInTheDocument()
    const appel = apiMock.get.mock.calls
      .map(([url]) => String(url)).find((u) => u.includes('finance-report'))
    expect(appel).toBeTruthy()
    // Même règle de taille de page pour les deux endpoints (le serveur met 25 par défaut ici).
    expect(appel).toContain('page_size=50')
  })
})
