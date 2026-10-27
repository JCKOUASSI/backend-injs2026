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
import EcranRessource from './EcranRessource'
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

function monter(ecran = ECRAN, { chemin = '/test' } = {}) {
  const user = makeUser('ADMIN')
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
