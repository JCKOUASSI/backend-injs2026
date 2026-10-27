/**
 * Tests de COMPORTEMENT du module Évaluations (E1.2).
 *
 * Ces tests verrouillent les contrats que la refonte avait rompus :
 * - `saisirNotes` doit appeler **PUT** (la vue backend n'accepte que PUT)
 *   avec un **corps liste** — un POST renvoyait 405, un objet renvoyait 400 ;
 * - les participants sont une **liste nue** (vue non paginée) ;
 * - 401 / 403 / 404 doivent être distingués, pas fusionnés en une seule
 *   alerte rouge générique.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Routes, Route } from 'react-router-dom'
import {
  ListeEvaluations, TableauDeBordEvaluations, SaisieNotes,
  ControleNotes, ResultatsEvaluations, Deliberations, Reveles,
} from '@/pages/EvaluationsModule'
import { ToastProvider } from '@/context/ToastContext'
import { AuthProvider } from '@/context/AuthContext'
import { createTestQueryClient } from '@/test/utils/renderWithProviders'
import { QueryClientProvider } from '@tanstack/react-query'
import { fetchResponse } from '@/test/utils/async'

/**
 * Droits pilotables : les actions d'écriture du module dépendent de la capacité
 * `notes.gerer` (autorité backend `peut_saisir_notes`). Sans utilisateur
 * authentifié, le repli statique renvoie `false` et les écrans s'affichent en
 * lecture seule — ce qui ne permettrait pas de tester la saisie elle-même.
 */
const ETAT_DROITS = { notes: { gerer: true }, evaluations: { consulter: true } }
vi.mock('@/hooks/useDroits', () => ({
  useDroits: () => ({
    user: null,
    charge: true,
    enChargement: false,
    erreur: null,
    capacites: null,
    niveau: null,
    perimetres: null,
    peut: (module, action) => Boolean(ETAT_DROITS[module]?.[action]),
  }),
}))

/** Retire (ou accorde) la capacité d'écriture des notes pour un test. */
function sansDroitDeSaisie() {
  ETAT_DROITS.notes.gerer = false
}

/** Payload conforme aux serializers réels du backend. */
const EVALUATION = {
  id: 7, session: 2, ecue: 5, ecue_code: 'ECUE-ANA-1',
  affectation_pedagogique: 4, type_evaluation: 3, type_code: 'EXAMEN',
  libelle: 'Examen final S1', description: '', bareme: 20.0, poids: 100.0,
  date_prevue: null, statut: 'BROUILLON', composition_verrouillee: false,
}
const PAGE = { count: 1, next: null, previous: null, results: [EVALUATION] }
const COMPOSANT = {
  id: 11, evaluation: 7, code: 'EXAMEN', libelle: 'Examen final',
  poids: 100.0, bareme: 20.0, ordre: 1, obligatoire: true, actif: true,
}
/** Vue `participants_list` : tableau simple, pas une page paginée. */
const PARTICIPANTS = [
  {
    id: 21, evaluation: 7, inscription_pedagogique: 3, matricule: 'ETU-001',
    nom_affiche: 'KOUASSI Adjoua', groupe: null, statut_participation: 'EN_ATTENTE',
    motif: '', source: 'MANUEL', eligible_rattrapage: false,
  },
]

function installFetch(routes) {
  const mock = vi.fn(async (url, init = {}) => {
    const meth = (init.method || 'GET').toUpperCase()
    const cle = `${meth} ${url.split('?')[0]}`
    if (routes[cle] === undefined) {
      return fetchResponse({ detail: 'Non trouvé.' }, { status: 404 })
    }
    const v = routes[cle]
    return typeof v === 'function' ? v(url, init) : fetchResponse(v)
  })
  vi.stubGlobal('fetch', mock)
  return mock
}

function etatHttp(statut, data = {}) {
  return fetchResponse(data, { status: statut })
}

/**
 * Rend le composant dans un routeur, avec les deux providers dont dépendent
 * les pages du module (toasts pour la saisie, droits pour les actions
 * conditionnelles).
 *
 * `SaisieNotes` lit son identifiant via `useParams()` : le paramètre `:id`
 * doit être déclaré, sinon la page charge une évaluation `undefined`.
 */
function rendre(ui, chemin = '/') {
  return render(
    // L'QueryClientProvider doit envelopper l'AuthProvider : celui-ci consomme
    // déjà les capacités via react-query.
    <QueryClientProvider client={createTestQueryClient()}>
      <AuthProvider>
        <MemoryRouter initialEntries={[chemin]}>
          <ToastProvider>
            <Routes>
              <Route path="/evaluations/saisie/:id" element={ui} />
              <Route path="*" element={ui} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      </AuthProvider>
    </QueryClientProvider>,
  )
}

describe('pages/EvaluationsModule — comportement', () => {
  beforeEach(() => {
    window.localStorage.clear()
    // Chaque test repart des droits par défaut (droit de saisie accordé).
    ETAT_DROITS.notes.gerer = true
    ETAT_DROITS.evaluations.consulter = true
  })

  describe('1. ListeEvaluations', () => {
    it('affiche les évaluations renvoyées par l’API', async () => {
      installFetch({ 'GET /api/evaluations-academiques/evaluations/': PAGE })
      rendre(<ListeEvaluations />)
      expect(await screen.findByText('Examen final S1')).toBeInTheDocument()
      expect(screen.getByText('ECUE-ANA-1')).toBeInTheDocument()
      expect(screen.getByText('EXAMEN')).toBeInTheDocument()
    })

    it('reste sur l’onglet Évaluations : aucune requête Sessions', async () => {
      const f = installFetch({ 'GET /api/evaluations-academiques/evaluations/': PAGE })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      const urls = f.mock.calls.map((c) => c[0])
      expect(urls.some((u) => u.includes('/sessions/'))).toBe(false)
    })

    it('affiche un état vide explicite quand la page est vide', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<ListeEvaluations />)
      expect(await screen.findByText('Aucune évaluation disponible')).toBeInTheDocument()
    })

    it('affiche l’état de chargement avant la réponse', async () => {
      installFetch({ 'GET /api/evaluations-academiques/evaluations/': PAGE })
      rendre(<ListeEvaluations />)
      expect(screen.getByText('Chargement en cours…')).toBeInTheDocument()
      await screen.findByText('Examen final S1')
    })

    it('l’onglet Sessions parle de sessions, jamais d’évaluations', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': PAGE,
        'GET /api/evaluations-academiques/sessions/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      await userEvent.click(screen.getByRole('button', { name: 'Sessions' }))
      // Un registre vide de sessions ne doit pas annoncer « Aucune évaluation ».
      expect(await screen.findByText('Aucune session disponible')).toBeInTheDocument()
      expect(screen.getByText(/session d’évaluation n’est rattachée/i)).toBeInTheDocument()
      expect(screen.queryByText('Aucune évaluation disponible')).not.toBeInTheDocument()
    })

    it('la recherche n’annonce que des champs réellement filtrés', async () => {
      installFetch({ 'GET /api/evaluations-academiques/evaluations/': PAGE })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      // `EvaluationSerializer` ne contient AUCUN `annee_libelle` : l'annoncer
      // dans le placeholder promettait une recherche inopérante.
      expect(screen.getByPlaceholderText('Libellé, ECUE, type, état…')).toBeInTheDocument()
      expect(screen.queryByPlaceholderText(/année/i)).not.toBeInTheDocument()
    })

    it('la recherche porte sur le type et l’état des évaluations', async () => {
      installFetch({ 'GET /api/evaluations-academiques/evaluations/': PAGE })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      await userEvent.type(screen.getByLabelText('Recherche'), 'BROUILLON')
      // Le statut est un champ réel du payload : le filtre le trouve.
      expect(screen.getByText('Examen final S1')).toBeInTheDocument()
      await userEvent.clear(screen.getByLabelText('Recherche'))
      await userEvent.type(screen.getByLabelText('Recherche'), 'zzz-inexistant')
      expect(await screen.findByText('Aucun résultat')).toBeInTheDocument()
    })

    it('la recherche est remise à zéro au changement d’onglet', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': PAGE,
        'GET /api/evaluations-academiques/sessions/': {
          count: 1, next: null, previous: null,
          results: [{
            id: 3, libelle: 'Session S1', annee_libelle: '2026-2027',
            type_session: 'RATTRAPAGE', niveau_code: 'L6', date_debut: null,
            date_fin: null, statut: 'BROUILLON', nb_evaluations: 0,
          }],
        },
      })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      await userEvent.click(screen.getByRole('button', { name: 'Sessions' }))
      expect(await screen.findByText('Session S1')).toBeInTheDocument()
      // Une recherche portant sur l'année des sessions ne doit pas survivre au
      // retour sur l'onglet Évaluations, où ce champ n'existe pas.
      await userEvent.click(screen.getByRole('button', { name: 'Évaluations' }))
      expect(await screen.findByText('Examen final S1')).toBeInTheDocument()
      expect(screen.getByLabelText('Recherche')).toHaveValue('')
    })

    it('l’en-tête porte l’unique action de saisie, l’état vide n’en duplique aucune', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<ListeEvaluations />)
      expect(await screen.findByText('Aucune évaluation disponible')).toBeInTheDocument()
      // Une seule action de saisie sur l'écran : celle de l'en-tête. Le vide ne
      // propose plus de raccourci vers une saisie qui n'aurait rien à afficher.
      expect(screen.getAllByRole('button', { name: /Saisir des notes/i })).toHaveLength(1)
    })

    it('masque l’action de saisie sur l’onglet Sessions', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': PAGE,
        'GET /api/evaluations-academiques/sessions/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      await userEvent.click(screen.getByRole('button', { name: 'Sessions' }))
      await screen.findByText('Aucune session disponible')
      // Saisir des notes porte sur une évaluation : hors de propos ici.
      expect(screen.queryByRole('button', { name: /Saisir des notes/i })).not.toBeInTheDocument()
    })
  })

  describe('2. TableauDeBordEvaluations', () => {
    it('agrège sessions et évaluations sans calcul métier', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': PAGE,
        'GET /api/evaluations-academiques/sessions/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<TableauDeBordEvaluations />)
      expect(await screen.findByText('Tableau de bord des évaluations')).toBeInTheDocument()
      expect(screen.getByText('Examen final S1')).toBeInTheDocument()
    })
  })

  describe('3. SaisieNotes — cycle complet', () => {
    const base = {
      'GET /api/evaluations-academiques/evaluations/7/': EVALUATION,
      'GET /api/evaluations-academiques/evaluations/7/composants/': [COMPOSANT],
      'GET /api/evaluations-academiques/evaluations/7/participants/': PARTICIPANTS,
    }

    it('liste les participants avec leur nom (jamais l’identifiant brut)', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      expect(await screen.findByText('KOUASSI Adjoua')).toBeInTheDocument()
      expect(screen.getByText('EN ATTENTE')).toBeInTheDocument()
    })

    it('envoie PUT et un corps liste (et non POST / un objet)', async () => {
      const f = installFetch({
        ...base,
        'PUT /api/evaluations-academiques/composants/11/notes/': [{ id: 1, valeur: 15.5 }],
      })
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      await userEvent.type(screen.getByLabelText('Note de KOUASSI Adjoua'), '15.5')
      await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))

      await waitFor(() => {
        const put = f.mock.calls.find((c) => (c[1]?.method || 'GET') === 'PUT')
        expect(put).toBeTruthy()
        expect(put[0]).toContain('/composants/11/notes/')
        // Corps = liste de lignes { evaluation_participant_id, valeur }.
        expect(Array.isArray(JSON.parse(put[1].body))).toBe(true)
        expect(JSON.parse(put[1].body)).toEqual([
          { evaluation_participant_id: 21, valeur: 15.5 },
        ])
      })
      expect(f.mock.calls.some((c) => c[1]?.method === 'POST')).toBe(false)
    })

    it('n’envoie rien et avertit quand aucun champ n’est rempli', async () => {
      const f = installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))
      expect(await screen.findByText(/Aucune note saisie/i)).toBeInTheDocument()
      expect(f.mock.calls.some((c) => c[1]?.method === 'PUT')).toBe(false)
    })

    it('désactive l’enregistrement tant qu’aucune composante n’est choisie', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      expect(screen.getByRole('button', { name: /enregistrer/i })).toBeDisabled()
    })

    it('efface les valeurs saisies quand on change de composante', async () => {
      // Changer de composante change la colonne notée : reporter l'ancienne
      // valeur sur la nouvelle réécrirait une note sur une colonne qui n'a
      // pas été saisie.
      const f = installFetch({
        ...base,
        'GET /api/evaluations-academiques/evaluations/7/composants/':
          [COMPOSANT, { ...COMPOSANT, id: 12, code: 'RATTRAPAGE', libelle: 'Rattrapage', bareme: 10.0 }],
        'PUT /api/evaluations-academiques/composants/12/notes/': [{ id: 1, valeur: 5 }],
      })
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      await userEvent.type(screen.getByLabelText('Note de KOUASSI Adjoua'), '15.5')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '12')
      // Le champ repart vide : aucune valeur n'est reportée d'une composante à l'autre.
      expect(screen.getByLabelText('Note de KOUASSI Adjoua')).toHaveValue(null)
      await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))
      await waitFor(() => {
        const put = f.mock.calls.find((c) => (c[1]?.method || 'GET') === 'PUT')
        // Rien à enregistrer : aucune note d'une autre composante n'est envoyée.
        expect(put).toBeUndefined()
      })
    })

    it('le sélecteur n’invite pas à une création que le registre ne permet pas', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<SaisieNotes />, '/evaluations/saisie')
      expect(await screen.findByText('Aucune évaluation disponible')).toBeInTheDocument()
      // Le registre n'expose aucune création d'évaluation : inviter à « créer
      // depuis le registre » renvoyait vers une action inexistante.
      expect(screen.queryByText(/Créez une évaluation depuis le registre/i)).not.toBeInTheDocument()
      expect(screen.getByText(/créées par le service académique/i)).toBeInTheDocument()
    })

    it('distingue « saisir » et « consulter » selon l’état de la composition', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': {
          count: 2, next: null, previous: null,
          results: [
            { ...EVALUATION, id: 1, libelle: 'Composition ouverte', composition_verrouillee: false },
            { ...EVALUATION, id: 2, libelle: 'Composition close', composition_verrouillee: true },
          ],
        },
      })
      rendre(<SaisieNotes />, '/evaluations/saisie')
      await screen.findByText('Composition ouverte')
      // Ouverte et autorisée → saisir ; verrouillée → consulter (lecture seule).
      expect(screen.getByRole('button', { name: /Saisir les notes de Composition ouverte/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Consulter les notes de Composition close/i })).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /Saisir les notes de Composition close/i })).not.toBeInTheDocument()
    })

    it('passe en lecture seule quand la composition est verrouillée', async () => {
      installFetch({
        ...base,
        'GET /api/evaluations-academiques/evaluations/7/':
          { ...EVALUATION, composition_verrouillee: true },
      })
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      expect(await screen.findByText(/lecture seule/i)).toBeInTheDocument()
      // Une composition verrouillée ne s'ouvre pas en écriture : le sélecteur de
      // composante reste consultable, mais l'enregistrement disparaît.
      expect(screen.queryByRole('button', { name: /enregistrer/i })).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Note de KOUASSI Adjoua')).not.toBeInTheDocument()
    })

    it('passe en lecture seule quand le profil n’a pas le droit de saisir', async () => {
      sansDroitDeSaisie()
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      // L'API refuserait toute écriture (403) : l'IHM ne propose pas de saisir.
      expect(screen.getByText(/Saisie non autorisée/i)).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: /enregistrer/i })).not.toBeInTheDocument()
      expect(screen.queryByLabelText('Note de KOUASSI Adjoua')).not.toBeInTheDocument()
    })

    it('signale le refus backend (403) sans masquer la cause', async () => {
      installFetch({
        ...base,
        'PUT /api/evaluations-academiques/composants/11/notes/': () =>
          etatHttp(403, { detail: 'Saisie de notes non autorisée.', code: 'NOTE_SAISIE_REFUSEE' }),
      })
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      await userEvent.type(screen.getByLabelText('Note de KOUASSI Adjoua'), '12')
      await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))
      expect(await screen.findByText(/Accès refusé/i)).toBeInTheDocument()
    })
  })

  describe('4. ControleNotes', () => {
    it('ne liste que les compositions non verrouillées', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': {
          count: 2, next: null, previous: null,
          results: [
            { ...EVALUATION, id: 1, libelle: 'À vérifier', composition_verrouillee: false },
            { ...EVALUATION, id: 2, libelle: 'Vérifiée', composition_verrouillee: true },
          ],
        },
      })
      rendre(<ControleNotes />)
      expect(await screen.findByText('À vérifier')).toBeInTheDocument()
      expect(screen.queryByText('Vérifiée')).not.toBeInTheDocument()
    })
  })

  describe('6. ResultatsEvaluations', () => {
    it('charge les résultats ECUE puis bascule sur UE', async () => {
      const f = installFetch({
        'GET /api/evaluations-academiques/resultats/ecue/':
          { count: 0, next: null, previous: null, results: [] },
        'GET /api/evaluations-academiques/resultats/ue/':
          { count: 0, next: null, previous: null, results: [] },
      })
      rendre(<ResultatsEvaluations />)
      await screen.findByText('Résultats')
      await userEvent.click(screen.getByRole('button', { name: 'UE' }))
      await waitFor(() => {
        expect(f.mock.calls.some((c) => c[0].includes('/resultats/ue/'))).toBe(true)
      })
    })

    it('reste sur des endpoints réellement exposés par l’API', async () => {
      const f = installFetch({
        'GET /api/evaluations-academiques/resultats/ecue/': PAGE,
        'GET /api/evaluations-academiques/resultats/ue/': PAGE,
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE,
      })
      rendre(<ResultatsEvaluations />)
      await screen.findByText('Résultats')
      const urls = f.mock.calls.map((c) => c[0])
      // Aucun endpoint fictif (rattrapage, délibérations, relevés).
      expect(urls.every((u) => /resultats\/(ecue|ue|semestre)\//.test(u))).toBe(true)
    })
  })

  // ── 6b. Passage de niveau : calcul backend, lecture seule (D10) ─────────
  describe('6b. Passage de niveau — panneau de consultation', () => {
    /** Payload conforme à `SemesterResultSerializer`. */
    const LIGNE_SEMESTRE = {
      id: 51, inscription: 3, session: 2, semestre: 'S3', statut_semestre: 'VALIDE',
      moyenne: '14.00', credits_attendus: 30, credits_acquis: 30, statut: 'VALIDE',
    }
    const PAGE_SEMESTRE = {
      count: 1, next: null, previous: null, results: [LIGNE_SEMESTRE],
    }
    /** Payload conforme à `PassageNiveauSerializer` (moteur `passage.py`). */
    const PASSAGE = {
      niveau_cible: 'L2', eligibilite: 'ELIGIBLE', code: 'PASSAGE_ELIGIBLE',
      credits_acquis: 60, credits_requis: 60,
      justification: 'Niveau L2 complet : 60/60 ECTS, tous les semestres validés.',
      empreinte: 'sha256:abc', decision_jury: null,
      semestres: [
        { semestre: 'S3', numero: 3, statut: 'VALIDE', credits_attendus: 30, credits_acquis: 30 },
        { semestre: 'S4', numero: 4, statut: 'VALIDE', credits_attendus: 30, credits_acquis: 30 },
      ],
    }
    const VIDE = { count: 0, next: null, previous: null, results: [] }

    /** Bascule sur l'onglet Semestre puis ouvre le panneau de passage. */
    async function ouvrirPassage(routes) {
      const f = installFetch({
        'GET /api/evaluations-academiques/resultats/ecue/': VIDE,
        ...routes,
      })
      rendre(<ResultatsEvaluations />)
      await screen.findByRole('button', { name: 'Semestre' })
      await userEvent.click(screen.getByRole('button', { name: 'Semestre' }))
      await userEvent.click(
        await screen.findByRole('button', { name: 'Passage de niveau' }),
      )
      return f
    }

    it('ouvre le panneau et affiche le calcul tel que renvoyé par le moteur', async () => {
      const f = installFetch({
        'GET /api/evaluations-academiques/resultats/ecue/': VIDE,
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE_SEMESTRE,
        'GET /api/evaluations-academiques/resultats/passage/': PASSAGE,
      })
      rendre(<ResultatsEvaluations />)
      await userEvent.click(await screen.findByRole('button', { name: 'Semestre' }))
      await screen.findByRole('button', { name: 'Passage de niveau' })
      // Aucun panneau avant la demande explicite de l'utilisateur.
      expect(screen.queryByTestId('passage-detail')).not.toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: 'Passage de niveau' }))
      expect(await screen.findByTestId('passage-detail')).toBeInTheDocument()
      // L'appel porte les identifiants de la ligne, en GET exclusif (D10 :
      // le calcul ne modifie rien, aucune décision n'est produite ici).
      const appel = f.mock.calls.find(([u]) => u.includes('/resultats/passage/'))
      expect(appel[0]).toContain('inscription_id=3')
      expect(appel[0]).toContain('session_id=2')
      expect(f.mock.calls.every((c) => (c[1]?.method || 'GET') === 'GET')).toBe(true)
      // Valeurs backend affichées telles quelles.
      expect(screen.getByText('ELIGIBLE')).toBeInTheDocument()
      expect(screen.getByText(/PASSAGE_ELIGIBLE/)).toBeInTheDocument()
      expect(screen.getByText('60 / 60')).toBeInTheDocument()
      expect(screen.getAllByText('S3').length).toBeGreaterThan(0)
      expect(screen.getAllByText('S4').length).toBeGreaterThan(0)
      // Aucune décision de jury : jamais une validation supposée (D6).
      expect(screen.getByText('Aucune décision enregistrée')).toBeInTheDocument()
    })

    it('affiche l’état de chargement tant que le moteur ne répond pas', async () => {
      let liberer
      await ouvrirPassage({
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE_SEMESTRE,
        'GET /api/evaluations-academiques/resultats/passage/': () =>
          new Promise((resolve) => { liberer = resolve }),
      })
      expect(screen.getByText('Chargement…')).toBeInTheDocument()
      expect(screen.getByText('Calcul du passage de niveau.')).toBeInTheDocument()
      await waitFor(() => expect(typeof liberer).toBe('function'))
      liberer(fetchResponse(PASSAGE))
      expect(await screen.findByText('Aucune décision enregistrée')).toBeInTheDocument()
    })

    it('signale l’absence de semestre sans conclure au passage', async () => {
      await ouvrirPassage({
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE_SEMESTRE,
        'GET /api/evaluations-academiques/resultats/passage/': { ...PASSAGE, semestres: [] },
      })
      expect(await screen.findByText('Aucun semestre')).toBeInTheDocument()
      expect(screen.getByText(/le passage ne peut pas être conclu/i)).toBeInTheDocument()
    })

    it('signale l’erreur du calcul et recharge sur « Réessayer »', async () => {
      let tentatives = 0
      await ouvrirPassage({
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE_SEMESTRE,
        'GET /api/evaluations-academiques/resultats/passage/': () => {
          tentatives += 1
          return tentatives === 1
            ? etatHttp(403, { detail: 'Consultation non autorisée.', code: 'ACCES_REFUSE' })
            : fetchResponse(PASSAGE)
        },
      })
      // Le refus backend est nommé, pas fondu dans un message générique.
      expect(await screen.findByText('Accès refusé')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /Réessayer/i }))
      expect(await screen.findByText('Aucune décision enregistrée')).toBeInTheDocument()
      expect(tentatives).toBe(2)
    })

    it('reproduit la décision EXCLUSION du jury sans la contredire', async () => {
      await ouvrirPassage({
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE_SEMESTRE,
        'GET /api/evaluations-academiques/resultats/passage/': {
          ...PASSAGE,
          eligibilite: 'BLOQUE',
          code: 'DECISION_JURY_BLOQUANTE',
          justification: 'Décision officielle du jury : Exclusion — aucun passage automatique ne peut être proposé.',
          decision_jury: {
            valeur: 'EXCLUSION', libelle: 'Exclusion', decide_le: '2026-06-30T10:00:00Z',
          },
        },
      })
      const panneau = await screen.findByTestId('passage-detail')
      expect(within(panneau).getByText('BLOQUE')).toBeInTheDocument()
      expect(within(panneau).getByText('EXCLUSION')).toBeInTheDocument()
      expect(within(panneau).queryByText('Aucune décision enregistrée')).not.toBeInTheDocument()
    })

    it('ne convertit jamais null en 0 (crédits et décision)', async () => {
      await ouvrirPassage({
        'GET /api/evaluations-academiques/resultats/semestre/': PAGE_SEMESTRE,
        'GET /api/evaluations-academiques/resultats/passage/': {
          ...PASSAGE, credits_acquis: null, credits_requis: null,
        },
      })
      const panneau = await screen.findByTestId('passage-detail')
      expect(within(panneau).getByText('Non renseigné / Non renseigné')).toBeInTheDocument()
      expect(within(panneau).getByText('Aucune décision enregistrée')).toBeInTheDocument()
      expect(within(panneau).queryByText(/^0$/)).not.toBeInTheDocument()
    })

    it('un refus de consultation (403) n’expose aucun bouton de passage', async () => {
      installFetch({
        'GET /api/evaluations-academiques/resultats/ecue/': VIDE,
        'GET /api/evaluations-academiques/resultats/semestre/': () =>
          etatHttp(403, { detail: 'Accès à la consultation des évaluations refusé.' }),
      })
      rendre(<ResultatsEvaluations />)
      const seg = await screen.findByRole('button', { name: 'Semestre' })
      await userEvent.click(seg)
      expect(await screen.findByText('Accès refusé')).toBeInTheDocument()
      expect(screen.queryByRole('button', { name: 'Passage de niveau' })).not.toBeInTheDocument()
    })
  })

  describe('5/7. Délibérations branchées sur l’API Jurys (source de vérité)', () => {
    // La décision académique est UNIQUE : elle vient du moteur LMD/ECTS exposé
    // par `/api/jurys/`. L'écran ne doit plus être un « écran d'indisponibilité »
    // et ne doit calculer ni moyenne ni seuil.
    const SESSION = {
      id: 7, libelle: 'Jury L1 2026', statut: 'DELIBERATION',
      type_session: 'NORMALE', verrouillee: false,
    }

    it('liste les sessions de jury depuis /jurys/sessions/', async () => {
      const f = installFetch({ 'GET /api/jurys/sessions/': { count: 1, results: [SESSION] } })
      rendre(<Deliberations />)
      await waitFor(() => {
        expect(screen.getByText('Jury L1 2026')).toBeInTheDocument()
      })
      expect(f.mock.calls.some(([u]) => u.includes('/jurys/sessions/'))).toBe(true)
    })

    it('affiche le détail (statistiques + anomalies) de la session choisie', async () => {
      installFetch({
        'GET /api/jurys/sessions/': { count: 1, results: [SESSION] },
        'GET /api/jurys/sessions/7/anomalies/': {
          session_id: 7, total: 1, bloquantes: 1, verrouillage_possible: false,
          anomalies: [{
            code: 'DECISION_ABSENTE', gravite: 'BLOQUANTE',
            message: 'Aucune décision de jury enregistrée.', participant_id: 42, bloquante: true,
          }],
        },
        'GET /api/jurys/sessions/7/statistiques/': {
          session_id: 7, participants: 10, admis: 7, ajournes: 3,
          decisions: { enregistrees: 10, completes: true, manquantes: 0 },
          anomalies: { total: 1, bloquantes: 1 },
        },
      })
      rendre(<Deliberations />)
      await waitFor(() => {
        expect(screen.getByText('Jury L1 2026')).toBeInTheDocument()
      })
      await userEvent.click(screen.getByTestId('deliberation-7'))
      await waitFor(() => {
        expect(screen.getByTestId('deliberation-detail')).toBeInTheDocument()
      })
      // Valeurs produites par le backend, jamais recalculées.
      expect(screen.getByText('10')).toBeInTheDocument()
      expect(screen.getByText('Aucune décision de jury enregistrée.')).toBeInTheDocument()
    })

    it('affiche un état vide quand aucune session n’existe', async () => {
      installFetch({ 'GET /api/jurys/sessions/': { count: 0, results: [] } })
      rendre(<Deliberations />)
      await waitFor(() => {
        expect(screen.getByText('Aucune session de jury')).toBeInTheDocument()
      })
    })

    it('relevés appelle l’API des relevés et affiche son contenu', async () => {
      const f = installFetch({
        'GET /api/evaluations-academiques/releves/': {
          count: 1,
          results: [{
            id: 7, version: 2, sha256: 'abc123def456',
            participant_matricule: 'MAT-001', decision_valeur: 'ADMIS',
            genere_le: '2026-01-15T10:00:00Z',
          }],
        },
        'GET /api/evaluations-academiques/releves/7/': {
          id: 7, version: 2, sha256: 'abc123def456',
          participant_matricule: 'MAT-001', decision_valeur: 'ADMIS',
          genere_le: '2026-01-15T10:00:00Z',
          contenu: {
            participant: { matricule: 'MAT-001', nom_complet: 'ABDOU KONE' },
            niveau: 'L1', formation: 'LMD-L1',
            semestres: [{ semestre: 'S1', niveau: 'L1', credits_acquis: 30, credits_attendus: 30, statut: 'VALIDE' }],
            unites_enseignement: [{
              ue_code: 'UE1', ue_libelle: 'UE Intitule', credits_ue: 30,
              moyenne: '14.50', statut: 'VALIDE',
              ecues: [{
                ecue_code: 'ECUE1', ecue_libelle: 'ECUE Intitule',
                note: null, bareme: '20', statut: 'BROUILLON',
              }],
            }],
            decision: { valeur: 'ADMIS' },
          },
        },
      })
      rendre(<Reveles />)
      await waitFor(() => {
        expect(screen.getByText('MAT-001')).toBeInTheDocument()
      })
      // La version du relevé est affichée telle que renvoyée par l'API.
      expect(screen.getByText('v2')).toBeInTheDocument()
      // La décision officielle est exposée, jamais recalculée.
      expect(f.mock.calls.some((c) => String(c[0]).includes('/releves/'))).toBe(true)

      await userEvent.click(screen.getByTestId('releve-7'))
      await waitFor(() => {
        expect(screen.getByTestId('releve-detail')).toBeInTheDocument()
      })
      expect(screen.getByText('ABDOU KONE')).toBeInTheDocument()
      expect(screen.getByText('UE1')).toBeInTheDocument()
      expect(screen.getByText('ECUE1')).toBeInTheDocument()
      // Note absente (null) : affichée « Non renseigné », jamais 0.
      expect(screen.getByText('Non renseigné')).toBeInTheDocument()
    })

    it('relevés affiche un état vide quand l’API ne renvoie rien', async () => {
      installFetch({
        'GET /api/evaluations-academiques/releves/': { count: 0, results: [] },
      })
      rendre(<Reveles />)
      await waitFor(() => {
        expect(screen.getByText('Aucun relevé')).toBeInTheDocument()
      })
    })

    it('relevés propage l’erreur API sans la masquer', async () => {
      installFetch({
        'GET /api/evaluations-academiques/releves/': () =>
          etatHttp(500, { detail: 'Service indisponible.' }),
      })
      rendre(<Reveles />)
      await waitFor(() => {
        expect(screen.getByText(/indisponible/i)).toBeInTheDocument()
      })
    })
  })

  describe('Gestion des erreurs HTTP (403 / 404 / 500)', () => {
    it('distingue le 403 (accès refusé)', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': () =>
          etatHttp(403, { detail: 'Accès à la consultation des évaluations refusé.' }),
      })
      rendre(<ListeEvaluations />)
      expect(await screen.findByText(/Accès refusé/i)).toBeInTheDocument()
    })

    it('distingue le 404 (ressource introuvable) au lieu du message générique', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': () =>
          etatHttp(404, { detail: 'Évaluation introuvable.', code: 'EVALUATION_INTROUVABLE' }),
      })
      rendre(<ListeEvaluations />)
      expect(await screen.findByText(/Ressource introuvable/i)).toBeInTheDocument()
      expect(screen.queryByText('Erreur lors du chargement des données.')).not.toBeInTheDocument()
    })

    it('affiche un panneau explicite pour une panne non typée (500)', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': () => etatHttp(500, {}),
      })
      rendre(<ListeEvaluations />)
      // E1.3 §7F : plus jamais « Erreur lors du chargement » seul — le
      // panneau nomme la panne et propose un « Réessayer ».
      expect(await screen.findByText(/Impossible de charger les évaluations/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /Réessayer/i })).toBeInTheDocument()
    })
  })

  describe('Invariants métier (D2 / D6 : null n’est jamais 0)', () => {
    it('rend « Non renseigné » pour une valeur null du backend', async () => {
installFetch({
        'GET /api/evaluations-academiques/evaluations/': {
          count: 1, next: null, previous: null,
          results: [{ ...EVALUATION, date_prevue: null }],
        },
      })
      rendre(<ListeEvaluations />)
      await screen.findByText('Examen final S1')
      expect(screen.getAllByText('Non renseigné').length).toBeGreaterThan(0)
      expect(screen.queryByText('0')).not.toBeInTheDocument()
    })
  })
// ── E1.3 : navigation, libellés et identité visuelle ───────────────────
  describe('E1.3 — titre de page : « Saisie des notes », jamais « Évaluations »', () => {
    const base = {
      'GET /api/evaluations-academiques/evaluations/': PAGE,
      'GET /api/evaluations-academiques/evaluations/7/': EVALUATION,
      'GET /api/evaluations-academiques/evaluations/7/composants/': [COMPOSANT],
      'GET /api/evaluations-academiques/evaluations/7/participants/': PARTICIPANTS,
    }

    it('/evaluations/saisie/:id affiche « Saisie des notes » en H1', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      const h1 = await screen.findByRole('heading', { level: 1 })
      expect(h1).toHaveTextContent('Saisie des notes')
      expect(h1).not.toHaveTextContent('Évaluations')
    })

    it('/evaluations/saisie (sans id) affiche aussi « Saisie des notes »', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie')
      const h1 = await screen.findByRole('heading', { level: 1 })
      expect(h1).toHaveTextContent('Saisie des notes')
      expect(h1).not.toHaveTextContent('Évaluations')
    })

    it('le sous-titre de saisie est celui de la saisie, pas celui du registre', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      expect(
        await screen.findByText(/Saisie et enregistrement des notes/i),
      ).toBeInTheDocument()
    })

    it('l’en-tête contextualisé affiche l’ECUE et le type réels', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      expect(screen.getByText('ECUE-ANA-1')).toBeInTheDocument()
      expect(screen.getByText('EXAMEN')).toBeInTheDocument()
    })

    it('le tableau de saisie expose Matricule, Participant, Note, Absence, Statut', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      for (const entete of ['Matricule', 'Participant', 'Note', 'Absence', 'Statut']) {
        expect(screen.getByRole('columnheader', { name: entete })).toBeInTheDocument()
      }
    })

    it('affiche l’identité réelle (matricule + nom), jamais un ID technique', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      expect(screen.getByText('ETU-001')).toBeInTheDocument()
    })
  })

  describe('E1.3 — le zéro est une note réelle', () => {
    const base = {
      'GET /api/evaluations-academiques/evaluations/7/': EVALUATION,
      'GET /api/evaluations-academiques/evaluations/7/composants/': [COMPOSANT],
      'GET /api/evaluations-academiques/evaluations/7/participants/': PARTICIPANTS,
    }

    it('accepte et transmet 0 comme note valide', async () => {
      const f = installFetch({
        ...base,
        'PUT /api/evaluations-academiques/composants/11/notes/': [{ id: 1, valeur: 0 }],
      })
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      await userEvent.type(screen.getByLabelText('Note de KOUASSI Adjoua'), '0')
      await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))
      await waitFor(() => {
        const put = f.mock.calls.find((c) => (c[1]?.method || 'GET') === 'PUT')
        expect(put).toBeTruthy()
        expect(JSON.parse(put[1].body)).toEqual([
          { evaluation_participant_id: 21, valeur: 0 },
        ])
      })
    })

    it('indique le barème réel à côté du champ', async () => {
      installFetch(base)
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      expect(await screen.findByText('/ 20')).toBeInTheDocument()
    })
  })
  describe('E1.3 — identité visuelle des 7 fenêtres', () => {
    const EMPTY = { count: 0, next: null, previous: null, results: [] }

    it('chaque page a un H1 unique et propre à son sous-module', async () => {
      const cas = [
        [ListeEvaluations, {}, 'Évaluations'],
        [TableauDeBordEvaluations, {
          'GET /api/evaluations-academiques/evaluations/': EMPTY,
          'GET /api/evaluations-academiques/sessions/': EMPTY,
        }, 'Tableau de bord des évaluations'],
        [ControleNotes, {}, 'Contrôle des notes'],
        [ResultatsEvaluations, {}, 'Résultats'],
        [Deliberations, {}, 'Délibérations'],
        [Reveles, {}, 'Relevés de notes'],
      ]
      for (const [Composant, routes, titre] of cas) {
        installFetch(routes)
        const vue = rendre(<Composant />)
        const h1 = await screen.findByRole('heading', { level: 1 })
        expect(h1).toHaveTextContent(titre)
        vue.unmount()
      }
    })

    it('l’état vide du registre est travaillé, pas une phrase nue', async () => {
      installFetch({ 'GET /api/evaluations-academiques/evaluations/': EMPTY })
      rendre(<ListeEvaluations />)
      expect(await screen.findByText('Aucune évaluation disponible')).toBeInTheDocument()
      expect(screen.getByText(/votre périmètre pédagogique/i)).toBeInTheDocument()
      expect(screen.queryByText('Aucune donnée trouvée.')).not.toBeInTheDocument()
    })

    it('le tableau de bord n’affiche que des indicateurs réellement comptés', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': {
          count: 2, next: null, previous: null,
          results: [
            { ...EVALUATION, id: 1, composition_verrouillee: false },
            { ...EVALUATION, id: 2, composition_verrouillee: true },
          ],
        },
        'GET /api/evaluations-academiques/sessions/': EMPTY,
      })
      rendre(<TableauDeBordEvaluations />)
      await screen.findByText('Dernières évaluations')
      // 2 évaluations → 1 ouverte, 1 verrouillée. Aucun chiffre inventé.
      // On cible les TUILES par leur classe (le libellé existe aussi en jauge).
      const valeurs = Array.from(document.querySelectorAll('.ev-stat-valeur'))
        .map((n) => n.textContent)
      expect(valeurs).toEqual(['2', '1', '1', '0'])
    })

    it('la tuile « Évaluations » lit le `count` de l’API, pas la page affichée', async () => {
      installFetch({
        // 120 évaluations au total, 50 renvoyées sur la page courante.
        'GET /api/evaluations-academiques/evaluations/': {
          count: 120, next: 'http://x/page/2', previous: null,
          results: Array.from({ length: 50 }, (_, i) => ({
            ...EVALUATION, id: i + 1, composition_verrouillee: false,
          })),
        },
        'GET /api/evaluations-academiques/sessions/': EMPTY,
      })
      rendre(<TableauDeBordEvaluations />)
      await screen.findByText('Dernières évaluations')
      const valeurs = Array.from(document.querySelectorAll('.ev-stat-valeur'))
        .map((n) => n.textContent)
      // 120 (count), 50 ouvertes (page), 0 verrouillées, 0 session.
      expect(valeurs).toEqual(['120', '50', '0', '0'])
      // La pagination est annoncée : les jauges ne sont pas présentées comme
      // couvrant l’intégralité du périmètre.
      expect(screen.getByText(/Page affichée : 50 compositions sur 120/)).toBeInTheDocument()
    })

    it('n’expose aucune action de saisie à un profil sans capacité notes.gerer', async () => {
      sansDroitDeSaisie()
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': PAGE,
        'GET /api/evaluations-academiques/sessions/': EMPTY,
      })
      rendre(<TableauDeBordEvaluations />)
      await screen.findByText('Dernières évaluations')
      expect(screen.queryByRole('button', { name: /Saisir/i })).not.toBeInTheDocument()
    })

    it('ne propose pas la saisie quand aucune évaluation n’existe', async () => {
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': EMPTY,
        'GET /api/evaluations-academiques/sessions/': EMPTY,
      })
      rendre(<TableauDeBordEvaluations />)
      expect(await screen.findByText('Aucune évaluation disponible')).toBeInTheDocument()
      expect(screen.queryByText(/Accéder à la saisie/i)).not.toBeInTheDocument()
    })

    it('« Réessayer » recharge aussi les sessions, pas seulement les évaluations', async () => {
      let tentatives = 0
      installFetch({
        'GET /api/evaluations-academiques/evaluations/': PAGE,
        'GET /api/evaluations-academiques/sessions/': () => {
          tentatives += 1
          return tentatives === 1
            ? etatHttp(503, {})
            : fetchResponse({ count: 4, next: null, previous: null, results: [] })
        },
      })
      const vue = rendre(<TableauDeBordEvaluations />)
      await screen.findByText('Dernières évaluations')
      expect(screen.getByText('Non disponible')).toBeInTheDocument()
      await userEvent.click(screen.getByRole('button', { name: /Actualiser/i }))
      await waitFor(() => {
        const valeurs = Array.from(document.querySelectorAll('.ev-stat-valeur'))
          .map((n) => n.textContent)
        expect(valeurs).toEqual(['1', '1', '0', '4'])
      })
      expect(tentatives).toBe(2)
      vue.unmount()
    })
  })

  describe('E1.3 — non-régression API (aucun contrat modifié)', () => {
    it('la saisie reste un PUT vers composants/<id>/notes avec un corps liste', async () => {
      const f = installFetch({
        'GET /api/evaluations-academiques/evaluations/7/': EVALUATION,
        'GET /api/evaluations-academiques/evaluations/7/composants/': [COMPOSANT],
        'GET /api/evaluations-academiques/evaluations/7/participants/': PARTICIPANTS,
        'PUT /api/evaluations-academiques/composants/11/notes/': [{ id: 1 }],
      })
      rendre(<SaisieNotes />, '/evaluations/saisie/7')
      await screen.findByText('KOUASSI Adjoua')
      await userEvent.selectOptions(screen.getByLabelText('Composante'), '11')
      await userEvent.type(screen.getByLabelText('Note de KOUASSI Adjoua'), '15.5')
      await userEvent.click(screen.getByRole('button', { name: /enregistrer/i }))
      await waitFor(() => {
        const put = f.mock.calls.find((c) => (c[1]?.method || 'GET') === 'PUT')
        expect(put[0]).toBe('/api/evaluations-academiques/composants/11/notes/')
      })
      // Aucune méthode mutante autre que PUT.
      expect(f.mock.calls.every((c) => (c[1]?.method || 'GET') !== 'POST')).toBe(true)
    })

    it('le contrôle ne lit que evaluations/ (aucun endpoint de notes)', async () => {
      const f = installFetch({ 'GET /api/evaluations-academiques/evaluations/': PAGE })
      rendre(<ControleNotes />)
      await screen.findByText('ECUE-ANA-1')
      expect(f.mock.calls.every((c) => c[0].includes('/evaluations/'))).toBe(true)
    })

    it('le verrouillage est lu depuis composition_verrouillee', async () => {
      const source = await import('@/pages/EvaluationsModule?raw')
      expect(source.default).toContain('composition_verrouillee')
      // Le champ obsolète « verrouillee » ne doit jamais revenir.
      expect(source.default).not.toMatch(/composition_verrouillee[^_]*\bverrouillee\b/)
    })
  })
})