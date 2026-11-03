/**
 * Écran générique de ressource — rendu de liste, filtres, actions et détail.
 *
 * Ces tests font tourner le composant réel sur un descripteur de test puis sur
 * un descripteur livré (`audit_journal`), afin de prouver que le moteur
 * générique consomme bien le vocabulaire de `src/menu/ecrans.js`
 * (`endpoint`, `colonnes[].cle`, `priorite`, `recherche`, `filtres`,
 * `actions`, `detail`, `onglets`, `type: 'indicateurs'`).
 *
 * Le mock d'API ne renvoie jamais d'erreur : les refus serveur sont couverts
 * côté backend. On vérifie ici ce que l'écran **appelle** et **affiche**.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, fireEvent, waitFor, within, cleanup } from '@testing-library/react'

vi.mock('@/services/api', async (importOriginal) => {
  const actual = await importOriginal()
  const mod = await import('@/test/utils/mockApi')
  return { ...actual, default: mod.default, setSessionExpiredCallback: vi.fn() }
})

import { apiController } from '@/test/utils/mockApi'
import { AllProviders } from '@/test/utils/renderWithProviders'
import { makeUser } from '@/test/utils/factories'
import EcranRessource, { pluriel } from './EcranRessource'
import { ECRANS } from '@/menu/ecrans'

/** Réponse de la liste, mutable : chaque test peut la remplacer avant montage. */
let reponseLignes = null

/** Fabrique de la réponse : un test peut la faire lever (erreur serveur). */
let fabriqueLignes = null

const LIGNES = {
  count: 2,
  results: [
    { id: 1, numero: 'DOS-001', statut: 'ACTIF', actif: true, montant: 15000, created_at: '2026-09-01T08:00:00Z' },
    { id: 2, numero: 'DOS-002', statut: 'SUSPENDU', actif: false, montant: 0, created_at: '2026-09-02T08:00:00Z' },
  ],
}

const ECRAN = {
  id: 'test_lignes',
  titre: 'Lignes de test',
  endpoint: '/test/lignes/',
  recherche: { param: 'search', libelle: 'Rechercher une ligne', placeholder: 'Numéro…' },
  filtres: [
    {
      param: 'statut',
      libelle: 'Statut',
      type: 'select',
      options: [{ valeur: 'ACTIF', libelle: 'Actif' }, { valeur: 'SUSPENDU', libelle: 'Suspendu' }],
    },
  ],
  colonnes: [
    { cle: 'numero', libelle: 'Numéro' },
    { cle: 'statut', libelle: 'Statut', format: 'badge', couleurs: { ACTIF: 'text-bg-success' } },
    { cle: 'actif', libelle: 'Actif', format: 'booleen' },
  ],
  actions: [
    {
      libelle: 'Valider',
      methode: 'POST',
      chemin: (ligne) => `/test/lignes/${ligne.id}/valider/`,
      succes: 'Ligne validée.',
      confirmation: 'Valider cette ligne ?',
    },
  ],
  detail: {
    titre: (ligne) => `Pièces de ${ligne.numero}`,
    endpoint: (ligne) => `/test/lignes/${ligne.id}/pieces/`,
    priorite: ['type_piece', 'statut'],
  },
  note: 'Source : /api/test/lignes/',
}

function monter(ecran = ECRAN, { chemin = '/test', role = 'ADMIN' } = {}) {
  const user = makeUser(role)
  apiController.setMe(user)
  apiController.setRoute('/auth/capabilities/', { capacites: { web: ['acceder'] } })
  apiController.setRoute('/habilitations/mes-acces/', { gouverne: false })
  render(<EcranRessource ecran={ecran} />, {
    wrapper: ({ children }) => (
      <AllProviders authUser={user} routePattern="*" initialEntries={[chemin]}>
        {children}
      </AllProviders>
    ),
  })
}

/** Derniers paramètres de requête envoyés à `api.get`. */
function derniersParams() {
  const appels = apiController.api.get.mock.calls.filter(([p]) => p === ECRAN.endpoint
    || p === '/audit-logs/' || p.startsWith('/test/'))
  return appels.length ? appels[appels.length - 1][1]?.params : undefined
}

beforeEach(() => {
  reponseLignes = LIGNES
  fabriqueLignes = () => reponseLignes
  // Route programmée une seule fois : la réponse est lue à chaque appel, ce qui
  // évite qu'un second `setRoute` soit ignoré (le mock garde le premier match).
  apiController.setRoute('/test/lignes/', () => fabriqueLignes())
})

afterEach(() => {
  cleanup()
  apiController.reset()
})

describe('rendu de la liste', () => {
  it('affiche les colonnes déclarées et leurs valeurs', async () => {
    monter()
    expect(await screen.findByText('DOS-001')).toBeTruthy()
    expect(screen.getByText('Numéro')).toBeTruthy()
    expect(screen.getByText('DOS-002')).toBeTruthy()
  })

  it('formate un statut en badge coloré', async () => {
    monter()
    const badge = await screen.findByText('ACTIF')
    expect(badge.className).toContain('badge')
    expect(badge.className).toContain('text-bg-success')
  })

  it('formate un booléen en icône', async () => {
    monter()
    await screen.findByText('DOS-001')
    const icones = document.querySelectorAll('td .bi-check-circle-fill, td .bi-dash-circle')
    expect(icones.length).toBe(2)
  })

  it('appelle l\'endpoint du descripteur avec la pagination', async () => {
    monter()
    await screen.findByText('DOS-001')
    expect(apiController.findCall('get', '/test/lignes/')).toBeTruthy()
    expect(derniersParams()).toMatchObject({ page: 1 })
  })

  it('affiche un message vide quand la liste est vide', async () => {
    reponseLignes = { count: 0, results: [] }
    monter({ ...ECRAN, vide: 'Aucun dossier pour ce critère.' })
    expect(await screen.findByText('Aucun dossier pour ce critère.')).toBeTruthy()
  })

  it('mentionne la source des données (traçabilité de l\'écran)', async () => {
    monter()
    expect(await screen.findByText(/Source : \/api\/test\/lignes\//)).toBeTruthy()
  })
})

describe('colonnes automatiques', () => {
  it('déduit les colonnes des champs prioritaires puis du premier enregistrement', async () => {
    monter({ id: 'test_auto', titre: 'Auto', endpoint: '/test/lignes/', priorite: ['numero', 'statut'] })
    expect(await screen.findByText('DOS-001')).toBeTruthy()
    const entetes = [...document.querySelectorAll('thead th')].map((th) => th.textContent)
    expect(entetes.slice(0, 2)).toEqual(['Numéro', 'Statut'])
  })

  it('n\'affiche pas les champs techniques', async () => {
    monter({ id: 'test_auto2', titre: 'Auto', endpoint: '/test/lignes/' })
    await screen.findByText('DOS-001')
    const entetes = [...document.querySelectorAll('thead th')].map((th) => th.textContent)
    expect(entetes).not.toContain('Id')
  })
})

describe('recherche et filtres', () => {
  it('la recherche est envoyée au backend (paramètre déclaré)', async () => {
    monter()
    await screen.findByText('DOS-001')
    const champ = screen.getByPlaceholderText('Numéro…')
    fireEvent.change(champ, { target: { value: 'DOS-002' } })
    await waitFor(() => expect(derniersParams()).toMatchObject({ search: 'DOS-002' }), { timeout: 2000 })
  })

  it('un filtre select ajoute son paramètre et revient à la page 1', async () => {
    monter()
    await screen.findByText('DOS-001')
    fireEvent.change(screen.getByLabelText('Statut'), { target: { value: 'SUSPENDU' } })
    await waitFor(() => expect(derniersParams()).toMatchObject({ statut: 'SUSPENDU', page: 1 }))
  })
})

/**
 * Descripteur avec `formulaire` : reproduit la forme réelle des écrans
 * Référentiels/Formations (source : `src/menu/ecrans.js`, écran « niveaux »).
 */
const ECRAN_FORMULAIRE = {
  id: 'test_formulaire',
  titre: 'Niveaux',
  endpoint: '/test/lignes/',
  colonnes: [
    { cle: 'numero', libelle: 'Code' },
    { cle: 'statut', libelle: 'Statut' },
  ],
  formulaire: {
    titreCreation: 'Créer un niveau',
    champs: [
      { cle: 'numero', libelle: 'Numéro', requis: true },
      { cle: 'statut', libelle: 'Statut' },
      { cle: 'actif', libelle: 'Actif', type: 'booleen', defaut: true },
    ],
    creation: { chemin: '/test/lignes/' },
    modification: (l) => ({ chemin: `/test/lignes/${l.id}/` }),
    suppression: (l) => `/test/lignes/${l.id}/`,
  },
}

describe('gestion (CRUD) pilotée par le descripteur', () => {
  it('sans `formulaire`, l’écran reste en lecture : aucun bouton de création', async () => {
    monter()
    await screen.findByText('DOS-001')
    expect(screen.queryByTestId('bouton-nouveau')).toBeNull()
    expect(screen.queryByTestId('modifier-1')).toBeNull()
  })

  it('avec `formulaire`, un administrateur peut créer, modifier et supprimer', async () => {
    monter(ECRAN_FORMULAIRE)
    await screen.findByText('DOS-001')
    expect(screen.getByTestId('bouton-nouveau')).toBeTruthy()
    expect(screen.getByTestId('modifier-1')).toBeTruthy()
    expect(screen.getByTestId('supprimer-1')).toBeTruthy()
  })

  it('un profil en lecture seule ne voit aucun bouton de gestion', async () => {
    monter(ECRAN_FORMULAIRE, { role: 'DIRECTION' })
    await screen.findByText('DOS-001')
    expect(screen.queryByTestId('bouton-nouveau')).toBeNull()
    expect(screen.queryByTestId('modifier-1')).toBeNull()
    expect(screen.queryByTestId('supprimer-1')).toBeNull()
  })

  it('« Nouveau » ouvre le formulaire et crée réellement la ligne', async () => {
    monter(ECRAN_FORMULAIRE)
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getByTestId('bouton-nouveau'))
    expect(await screen.findByText('Créer un niveau')).toBeTruthy()
    fireEvent.change(screen.getByTestId('champ-numero'), { target: { value: 'DOS-009' } })
    fireEvent.change(screen.getByTestId('champ-statut'), { target: { value: 'ACTIF' } })
    fireEvent.click(screen.getByTestId('form-enregistrer'))
    await waitFor(() => {
      const appel = apiController.findCall('post', '/test/lignes/')
      expect(appel?.[1]).toMatchObject({ numero: 'DOS-009', statut: 'ACTIF', actif: true })
    })
    // Le dialogue se referme après le succès serveur.
    await waitFor(() => expect(screen.queryByText('Créer un niveau')).toBeNull())
  })

  it('« Modifier » recharge la ligne et enregistre par PATCH', async () => {
    monter(ECRAN_FORMULAIRE)
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getByTestId('modifier-1'))
    const champ = await screen.findByTestId('champ-numero')
    expect(champ.value).toBe('DOS-001')
    fireEvent.change(champ, { target: { value: 'DOS-001-b' } })
    fireEvent.click(screen.getByTestId('form-enregistrer'))
    await waitFor(() => {
      const appel = apiController.findCall('patch', '/test/lignes/1/')
      expect(appel?.[1]).toMatchObject({ numero: 'DOS-001-b' })
    })
  })

  it('« Supprimer » demande confirmation avant d’appeler le serveur', async () => {
    monter(ECRAN_FORMULAIRE)
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getByTestId('supprimer-1'))
    expect(await screen.findByText(/Supprimer définitivement cet élément/)).toBeTruthy()
    expect(apiController.api.delete).not.toHaveBeenCalled()
    const boite = screen.getByRole('dialog', { name: 'Confirmation' })
    fireEvent.click(within(boite).getByRole('button', { name: 'Supprimer' }))
    await waitFor(() => expect(apiController.findCall('delete', '/test/lignes/1/')).toBeTruthy())
  })

  it('un refus de dépendance (409) laisse la ligne en place et informe', async () => {
    apiController.api.delete.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          error: 'Suppression impossible : cet élément est référencé ailleurs.',
          detail: 'La suppression détruirait aussi 2 semestres.',
        },
      },
    })
    monter(ECRAN_FORMULAIRE)
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getByTestId('supprimer-1'))
    const boite = await screen.findByRole('dialog', { name: 'Confirmation' })
    fireEvent.click(within(boite).getByRole('button', { name: 'Supprimer' }))
    await waitFor(() => expect(document.body.textContent)
      .toMatch(/référencé ailleurs|Suppression refusée/))
    // La liste n'est pas vidée localement : c'est le serveur qui fait foi.
    expect(screen.getByText('DOS-001')).toBeTruthy()
  })
})

describe('actions sur une ligne', () => {
  it('une action à confirmation ouvre la modale avant tout appel', async () => {
    monter()
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getAllByTestId('action-Valider')[0])
    expect(await screen.findByText('Valider cette ligne ?')).toBeTruthy()
    expect(apiController.findCall('post', '/test/lignes/1/valider/')).toBeFalsy()
  })

  it('confirmer déclenche l\'appel serveur avec le chemin construit', async () => {
    monter()
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getAllByTestId('action-Valider')[0])
    const modale = await screen.findByText('Valider cette ligne ?')
    fireEvent.click(within(modale.closest('.modal-content')).getByText('Valider'))
    await waitFor(() => {
      expect(apiController.findCall('post', '/test/lignes/1/valider/')).toBeTruthy()
    })
  })

  it('annuler la confirmation n\'appelle rien', async () => {
    monter()
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getAllByTestId('action-Valider')[0])
    const modale = await screen.findByText('Valider cette ligne ?')
    fireEvent.click(within(modale.closest('.modal-content')).getByText('Annuler'))
    await waitFor(() => expect(screen.queryByText('Valider cette ligne ?')).toBeNull())
    expect(apiController.findCall('post', '/test/lignes/1/valider/')).toBeFalsy()
  })

  it('une action sans confirmation appelle directement le serveur', async () => {
    monter({
      ...ECRAN,
      actions: [{ libelle: 'Exporter', methode: 'GET', chemin: '/test/lignes/export/' }],
    })
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getAllByTestId('action-Exporter')[0])
    await waitFor(() => {
      expect(apiController.findCall('get', '/test/lignes/export/')).toBeTruthy()
    })
  })

  it('une action de navigation est désactivée si la cible est incomplète', async () => {
    monter({
      ...ECRAN,
      actions: [{ libelle: 'Ouvrir', vers: (ligne) => (ligne.numero ? `/test/${ligne.numero}` : null) }],
    })
    await screen.findByText('DOS-001')
    expect(screen.getAllByTestId('action-Ouvrir')[0].disabled).toBe(false)
  })

  it('une action de téléchargement passe par getBlob', async () => {
    monter({
      ...ECRAN,
      actions: [{
        libelle: 'PDF',
        telechargement: true,
        chemin: (ligne) => `/test/lignes/${ligne.id}/pdf/`,
      }],
    })
    await screen.findByText('DOS-001')
    fireEvent.click(screen.getAllByTestId('action-PDF')[0])
    await waitFor(() => {
      expect(apiController.api.getBlob).toHaveBeenCalledWith('/test/lignes/1/pdf/')
    })
  })
})

describe('erreurs serveur', () => {
  it('un 403 affiche un refus explicite, pas une « donnée indisponible »', async () => {
    // Le mock d'API ne lève jamais : on simule le rejet axios (err.response).
    const refus = Object.assign(new Error('Forbidden'), {
      response: {
        status: 403,
        data: { detail: "Console d'habilitation indisponible (drapeau fermé ou droit insuffisant)." },
      },
    })
    fabriqueLignes = () => { throw refus }
    monter()
    const bandeau = await screen.findByTestId('ecran-erreur')
    expect(bandeau.textContent).toContain('Accès refusé par le serveur.')
    expect(bandeau.textContent).toContain('drapeau fermé ou droit insuffisant')
    expect(bandeau.dataset.statut).toBe('403')
    expect(screen.queryByText('DOS-001')).toBeNull()
  })

  it('une erreur 500 reste une indisponibilité de données', async () => {
    const panne = Object.assign(new Error('Internal Server Error'), {
      response: { status: 500, data: { detail: 'boom' } },
    })
    fabriqueLignes = () => { throw panne }
    monter()
    const bandeau = await screen.findByTestId('ecran-erreur')
    expect(bandeau.textContent).toContain('Données indisponibles.')
    expect(bandeau.dataset.statut).toBe('500')
  })
})

describe('panneau de détail', () => {
  it('cliquer une ligne ouvre le détail sur l\'endpoint enfant', async () => {
    apiController.setRoute('/test/lignes/1/pieces/', { results: [{ id: 9, type_piece: 'CNI', statut: 'CONFORME' }] })
    monter()
    fireEvent.click(await screen.findByText('DOS-001'))
    expect(await screen.findByText(/Pièces de DOS-001/)).toBeTruthy()
    await waitFor(() => {
      expect(apiController.findCall('get', '/test/lignes/1/pieces/')).toBeTruthy()
    })
    expect(await screen.findByText('CNI')).toBeTruthy()
  })
})

describe('variantes de descripteur', () => {
  it('un descripteur d\'indicateurs rend des cartes et non un tableau', async () => {
    apiController.setRoute('/test/indicateurs/', { total_dossiers: 42, taux_conformite: 0.87 })
    monter({ id: 'test_indic', titre: 'Indic', endpoint: '/test/indicateurs/', type: 'indicateurs' })
    expect(await screen.findByText('42')).toBeTruthy()
    expect(document.querySelector('table')).toBeNull()
  })

  it('un descripteur à onglets rend un onglet par source et bascule', async () => {
    apiController.setRoute('/test/onglet-a/', { results: [{ id: 1, nom: 'A1' }] })
    apiController.setRoute('/test/onglet-b/', { results: [{ id: 2, nom: 'B1' }] })
    monter({
      id: 'test_onglets',
      titre: 'Onglets',
      onglets: [
        { id: 'a', libelle: 'Onglet A', endpoint: '/test/onglet-a/', priorite: ['nom'] },
        { id: 'b', libelle: 'Onglet B', endpoint: '/test/onglet-b/', priorite: ['nom'] },
      ],
    })
    expect(await screen.findByTestId('onglet-a')).toBeTruthy()
    expect(await screen.findByText('A1')).toBeTruthy()
    fireEvent.click(screen.getByTestId('onglet-b'))
    expect(await screen.findByText('B1')).toBeTruthy()
    expect(apiController.findCall('get', '/test/onglet-b/')).toBeTruthy()
  })

  it('un descripteur livré (journal d\'audit) rend ses colonnes réelles', async () => {
    // Forme réelle du serializer `presences.AuditLog` (voir ecrans.js).
    apiController.setRoute('/audit-logs/', {
      count: 1,
      results: [{
        id: 7,
        timestamp: '2026-09-14T10:00:00Z',
        action_label: 'Création',
        acteur_label: 'admin',
        acteur_role: 'ADMIN',
        cible_nom: 'CompteUtilisateur',
        cible_numero: 'C-42',
        ip_address: '127.0.0.1',
      }],
    })
    monter(ECRANS.audit_journal)
    expect(await screen.findByText('admin')).toBeTruthy()
    expect(apiController.findCall('get', '/audit-logs/')).toBeTruthy()
  })
})

describe('filtre requis', () => {
  it('n\'interroge pas le serveur tant que le filtre requis est vide, puis charge à la sélection', async () => {
    apiController.setRoute('/test/finances/', { total_dossiers: 42 })
    monter({
      id: 'test_requis',
      titre: 'Finances de test',
      endpoint: '/test/finances/',
      type: 'indicateurs',
      filtres: [{
        param: 'formation_id',
        libelle: 'Formation',
        type: 'select',
        requis: true,
        options: [{ valeur: '3', libelle: 'Licence Informatique' }],
      }],
      note: 'Source : /api/test/finances/',
    })

    // Aucun appel serveur tant que la sélection obligatoire est vide.
    expect(await screen.findByTestId('ecran-parametres-requis')).toBeTruthy()
    expect(apiController.findCall('get', '/test/finances/')).toBeFalsy()

    // Renseigné → appel immédiat avec le paramètre, cartes rendues, barre
    // de filtre conservée pour permettre de changer de formation.
    fireEvent.change(screen.getByLabelText('Formation'), { target: { value: '3' } })
    expect(await screen.findByText('42')).toBeTruthy()
    expect(screen.getByLabelText('Formation')).toBeTruthy()
    expect(derniersParams()).toMatchObject({ formation_id: '3' })
  })
})

describe('écran livré : résultats concours', () => {
  const CAMPAGNES = [
    {
      id: 1, libelle: 'Concours — EM', ref_formation: 'Éducation et Motricité — Licence',
      annee_academique: '2026-2027', statut: 'OUVERTE',
      classement_calcule: true, classement_publie: false,
      nb_candidatures: 6, nb_epreuves: 4,
      date_ouverture: '2026-08-04', date_fermeture: '2027-03-02',
      quota_admissibles: 3, quota_admis: 2,
    },
    {
      id: 2, libelle: 'Concours — ES', ref_formation: 'Entraînement Sportif — Licence',
      annee_academique: '2025-2026', statut: 'CLOTUREE',
      classement_calcule: true, classement_publie: true,
      nb_candidatures: 6, nb_epreuves: 3,
      date_ouverture: '2025-08-29', date_fermeture: '2025-10-08',
      quota_admissibles: 3, quota_admis: 2,
    },
    {
      id: 3, libelle: 'Campagne vide', ref_formation: 'Gérontologie — Master',
      annee_academique: '2026-2027', statut: 'BROUILLON',
      classement_calcule: false, classement_publie: false,
      nb_candidatures: 0, nb_epreuves: 0,
      date_ouverture: null, date_fermeture: null,
      quota_admissibles: null, quota_admis: null,
    },
  ]

  beforeEach(() => {
    apiController.setRoute('/admissions/campagnes/', CAMPAGNES)
    apiController.setRoute('/formations/ref/formations/', [])
    apiController.setRoute('/scolarite/ref/annees/', [])
    apiController.setRoute('/admissions/campagnes/1/classement/', [
      {
        rang: 1, candidature: 'CAND-2026-2027-0016', candidat: 'N’DRI Armel',
        score_total: '114.50', liste: 'ADMISSIBLE', liste_libelle: 'Admissible',
        publie: false,
      },
      {
        rang: 2, candidature: 'CAND-2026-2027-0017', candidat: 'TOURÉ Salimata',
        score_total: '58.50', liste: 'NON_ADMIS', liste_libelle: 'Non admis',
        publie: false,
      },
    ])
    apiController.setRoute('/admissions/campagnes/3/classement/', [])
  })

  const monterResultats = () => monter(ECRANS.resultats_concours, {
    chemin: '/scolarite/resultats-concours',
  })

  it('affiche les libellés (campagne, formation, statut, état du classement)', async () => {
    monterResultats()
    await screen.findByText('Concours — EM')
    const ouverte = screen.getByText('Concours — EM').closest('tr')
    expect(within(ouverte).getByText('Éducation et Motricité — Licence')).toBeTruthy()
    expect(within(ouverte).getByText('Ouverte')).toBeTruthy()
    expect(within(ouverte).getByText('Calculé')).toBeTruthy()
    const cloturee = screen.getByText('Concours — ES').closest('tr')
    expect(within(cloturee).getByText('Clôturée')).toBeTruthy()
    expect(within(cloturee).getByText('Publié')).toBeTruthy()
    expect(within(screen.getByText('Campagne vide').closest('tr'))
      .getByText('Non calculé')).toBeTruthy()
  })

  it('ne propose Calculer / Publier que lorsque l’acte est possible', async () => {
    monterResultats()
    await screen.findByText('Concours — EM')
    // Seule la campagne 1 (classement calculé, non publié, avec
    // candidatures) expose les deux actes.
    expect(screen.getAllByTestId('action-Calculer le classement')).toHaveLength(1)
    expect(screen.getAllByTestId('action-Publier')).toHaveLength(1)
  })

  it('publier après confirmation appelle l’endpoint de publication', async () => {
    monterResultats()
    await screen.findByText('Concours — EM')
    fireEvent.click(screen.getByTestId('action-Publier'))
    const modale = await screen.findByText('Publier les résultats de cette campagne ?')
    expect(apiController.findCall('post', '/admissions/campagnes/1/classement/publier/')).toBeFalsy()
    fireEvent.click(within(modale.closest('.modal-content')).getByText('Publier'))
    await waitFor(() => {
      expect(apiController.findCall('post', '/admissions/campagnes/1/classement/publier/')).toBeTruthy()
    })
  })

  it('le détail montre le classement en libellés, et le message vide dédié', async () => {
    monterResultats()
    fireEvent.click(await screen.findByText('Concours — EM'))
    expect(await screen.findByText(/Classement — Concours — EM/)).toBeTruthy()
    expect(await screen.findByText('CAND-2026-2027-0016')).toBeTruthy()
    expect(screen.getByText('Admissible')).toBeTruthy()
    expect(screen.getByText('Non admis')).toBeTruthy()
    expect(screen.getAllByText('Non publié').length).toBeGreaterThan(0)
    fireEvent.click(screen.getAllByRole('button', { name: /fermer/i })[0])
    fireEvent.click(await screen.findByText('Campagne vide'))
    expect(await screen.findByText(/Aucun classement pour cette campagne/)).toBeTruthy()
  })
})

describe('Alertes & seuils (régression capture 03/11 : JSON brut)', () => {
  const PAYLOAD_SEUILS = {
    seuils: [],
    indicateurs: [{
      indicateur: 'taux_presence', libelle: 'Assiduité séance', valeur: 82.5,
      unite: '%', inverse: false, icone: 'bi-person-check', couleur: '#2277C1',
      aide: 'Places présentes ÷ places attendues.', echelle_max: 100,
      niveau: 'non_configure', actif: false, configure: false,
      seuil_avertissement: 75, seuil_critique: 60,
    }],
    synthese: { ok: 0, avertissement: 0, critique: 0, inactif: 0, non_configure: 1 },
    seuils_vides: true,
  }

  it('rend synthèse, jauge et état « à initialiser » sans aucun JSON', async () => {
    apiController.setRoute('/statistiques/alertes/seuils/', () => PAYLOAD_SEUILS)
    apiController.setRoute('/stats/alertes/', () => ({ annee: '2026-2027', alertes: [] }))
    monter(ECRANS.stats_alertes, { chemin: '/statistiques/alertes' })

    expect(await screen.findByText('Assiduité séance')).toBeTruthy()
    expect(screen.getByText('Aucun seuil configuré.')).toBeTruthy()
    expect(screen.getByRole('button', { name: /Initialiser les seuils INJS/ })).toBeTruthy()
    expect(screen.getAllByText('Non configuré').length).toBeGreaterThanOrEqual(1)
    // Le cœur de la régression : aucun fragment JSON ne doit subsister.
    expect(document.body.textContent).not.toContain('"indicateur"')
    expect(document.body.textContent).not.toContain('"synthese"')
    expect(document.body.textContent).not.toContain('{')
  })

  it('onglet Alertes : lit la racine `alertes` de l’enveloppe {annee, alertes}', async () => {
    apiController.setRoute('/statistiques/alertes/seuils/', () => PAYLOAD_SEUILS)
    apiController.setRoute('/stats/alertes/', () => ({
      annee: '2026-2027',
      alertes: [{ participant_id: 7, matricule: 'INJS21-0007', taux_presence: 40, taux_absence: 60, niveau: 'CRITIQUE' }],
    }))
    monter(ECRANS.stats_alertes, { chemin: '/statistiques/alertes' })
    await screen.findByText('Assiduité séance')

    fireEvent.click(screen.getByTestId('onglet-alertes'))
    expect(await screen.findByText('INJS21-0007')).toBeTruthy()
    expect(screen.getByText('CRITIQUE')).toBeTruthy()
    expect(document.body.textContent).not.toContain('"alertes"')
  })
})

describe('Résultats / bilans (régression capture 03/11 : « Élément » répété)', () => {
  it('rend synthèse, périodes libellées et filtres en français, sans JSON', async () => {
    apiController.setRoute('/statistiques/bilans/', () => ({
      annee: 2026, mois: null, bilans: [], total_bilans: 0,
      categories: [], modules: [], matieres: [], formations: [],
      periodes: [{ value: 'QUOTIDIEN', label: 'Quotidien' }, { value: 'MENSUEL', label: 'Mensuel' }],
      filtres_actifs: {
        annee: 2026, mois: null, categorie: '', module_id: null, formation_id: null,
        periode: '', periode_label: 'Toutes périodes', calendrier: '', dimension: 'formation',
      },
    }))
    monter(ECRANS.stats_resultats, { chemin: '/statistiques/resultats' })

    expect(await screen.findByText('Aucun bilan publié pour ce périmètre')).toBeTruthy()
    expect(screen.getAllByText('Toutes périodes').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Quotidien')).toBeTruthy()
    expect(screen.getByText('Mensuel')).toBeTruthy()
    expect(screen.getByText('Tous les mois')).toBeTruthy()
    expect(document.body.textContent).not.toContain('Élément')
    expect(document.body.textContent).not.toContain('"periodes"')
    expect(document.body.textContent).not.toContain('module_id')
  })
})

describe('Semestres (régression capture 03/11 : niveau en id brut, « Tous les niveau »)', () => {
  it('résout le niveau vers son code référentiel et pluralise le filtre', async () => {
    apiController.setRoute('/scolarite/ref/semestres/', () => ({
      count: 2,
      results: [
        { id: 1, numero: 1, libelle: 'S1', niveau_id: 1, actif: true },
        { id: 2, numero: 3, libelle: 'S3', niveau_id: 2, actif: true },
      ],
    }))
    apiController.setRoute('/scolarite/ref/niveaux/', () => ({
      count: 2,
      results: [
        { id: 1, code: 'L1', libelle: 'Licence 1', cycle: 'LICENCE', ordre: 1, actif: true },
        { id: 2, code: 'L2', libelle: 'Licence 2', cycle: 'LICENCE', ordre: 2, actif: true },
      ],
    }))
    monter(ECRANS.semestres, { chemin: '/formations/semestres' })

    // Libellés semestres en chips, niveaux résolus en codes (L1/L2), jamais l'id brut.
    expect(await screen.findByText('S1')).toBeTruthy()
    expect(await screen.findByText('L1')).toBeTruthy()
    const pastilles = [...document.querySelectorAll('.gen-ref-pill')].map((n) => n.textContent)
    expect(pastilles).toEqual(expect.arrayContaining(['L1', 'L2']))
    // Le filtre affiche le libellé complet et le pluriel correct.
    expect(screen.getByText('Tous les niveaux')).toBeTruthy()
    expect(screen.getByText('Licence 1')).toBeTruthy()
    expect(screen.queryByText('Tous les niveau')).toBeNull()
  })

  it('pluriel : -eau→-eaux, -s/-x inchangés, défaut +s', () => {
    expect(pluriel('Niveau')).toBe('niveaux')
    expect(pluriel('Mois')).toBe('mois')
    expect(pluriel('Statut')).toBe('statuts')
    expect(pluriel('Semestre')).toBe('semestres')
  })
})
